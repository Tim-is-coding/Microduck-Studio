from __future__ import annotations

import asyncio

import httpx
import pytest

from duckstudio.api import create_app
from duckstudio.backends.mock import MockBackend


@pytest.fixture
async def client(mock: MockBackend):
    app = create_app(mock, auto_connect=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_reports_backend_and_unverified_methods(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "mock" and body["connected"] is True
    assert 0 <= body["health"]["battery"] <= 1
    assert body["unverified_upstream_methods"] == []


async def test_health_says_which_vlm_is_wired_up(client: httpx.AsyncClient) -> None:
    """The Studio has to be able to say where pictures would go before anything is run."""
    vlm = (await client.get("/api/health")).json()["vlm"]
    assert vlm["provider"] == "stub"  # no DUCKSTUDIO_VLM in the test environment
    assert vlm["sends_frames"] is False and vlm["configured"] is True
    assert 0.1 <= vlm["hz"] <= 2.0


async def test_executor_payload_carries_target_and_vlm_state(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/executor")).json()
    assert body["target"] is None
    assert body["vlm"] == {
        "provider": "stub",
        "sends_frames": False,
        "question": None,  # {"de": …, "en": …} while a behavior is asking
        "asked": 0,
        "answer": None,
    }


async def test_skills_and_behaviors_are_served(client: httpx.AsyncClient) -> None:
    skills = (await client.get("/api/skills")).json()
    assert {s["id"] for s in skills} >= {"walk", "quack", "getup", "look_around"}
    assert skills[0]["schema"] == "duckstudio.skill/v0"
    pack = (await client.get("/api/behaviors/follow-me")).json()
    assert pack["name"]["de"] == "Folge mir"
    assert pack["problems"] == []
    assert pack["steps"][1]["with"]["tempo"] == "easy"
    assert (await client.get("/api/behaviors/nope")).status_code == 404


async def test_state_is_served(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/state")
    assert r.status_code == 200
    assert len(r.json()["joints"]) == 15 and r.json()["flags"]["standing"] is True


async def test_frame_is_jpeg(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/frame")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content[:2] == b"\xff\xd8"


async def test_stop_reaches_backend_and_logs_in_german(
    client: httpx.AsyncClient, mock: MockBackend
) -> None:
    r = await client.post("/api/stop")
    assert r.json() == {"ok": True} and mock.stopped
    events = (await client.get("/api/events")).json()
    assert events[-1]["kind"] == "stop" and "Notstopp" in events[-1]["text"]["de"]


async def test_default_backend_is_sim_and_unreachable_sim_is_reported(monkeypatch) -> None:
    """§3.3: simulation is the normal state; without duck-sim the runtime says so and stays up."""
    monkeypatch.delenv("DUCKSTUDIO_BACKEND", raising=False)
    monkeypatch.setenv("DUCK_SIM_STATE", "/tmp/ds-no-sim-here")
    app = create_app(auto_connect=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        body = (await c.get("/api/health")).json()
        assert body["backend"] == "sim" and body["connected"] is False
        assert (await c.get("/api/frame")).status_code == 503
        assert (await c.get("/api/state")).status_code == 503
        assert (await c.post("/api/stop")).json() == {"ok": True}


async def test_run_status_abort_and_say(client: httpx.AsyncClient, mock: MockBackend) -> None:
    await client.get("/api/health")  # gives the gate a battery reading
    await client.get("/api/state")
    status = (await client.get("/api/executor")).json()
    assert status["state"] == "idle" and status["person"] is None

    r = await client.post("/api/behaviors/follow-me/run")
    assert r.status_code == 200 and r.json()["state"] == "running"
    assert (await client.post("/api/behaviors/follow-me/run")).status_code == 409
    assert (await client.post("/api/behaviors/nope/run")).status_code == 404
    await asyncio.sleep(0.25)  # a couple of real-time ticks: nobody in sight → look_around
    status = (await client.get("/api/executor")).json()
    assert status["state"] == "running" and status["active_skill"] == "look_around"

    r = await client.post("/api/executor/abort")
    assert r.json()["state"] == "aborted" and mock.stopped

    r = await client.post("/api/say", json={"text": "Folge mir"})
    assert r.json()["started"] == "follow-me" and r.json()["state"] == "running"
    r = await client.post("/api/say", json={"text": "Stopp"})
    assert r.json()["started"] is None and r.json()["state"] == "running"
    r = await client.post("/api/stop")  # Notstopp aborts the executor too
    assert r.json() == {"ok": True}
    assert (await client.get("/api/executor")).json()["state"] == "aborted"
