from __future__ import annotations

import httpx
import pytest

from duckstudio.api import create_app
from duckstudio.backends.mock import MockBackend


@pytest.fixture
async def client(mock: MockBackend):
    app = create_app(mock, connect_on_startup=False)
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


async def test_skills_and_behaviors_are_served(client: httpx.AsyncClient) -> None:
    skills = (await client.get("/api/skills")).json()
    assert {s["id"] for s in skills} >= {"walk", "quack", "getup", "look_around"}
    assert skills[0]["schema"] == "duckstudio.skill/v0"
    pack = (await client.get("/api/behaviors/follow-me")).json()
    assert pack["name"]["de"] == "Folge mir"
    assert pack["problems"] == []
    assert pack["steps"][1]["with"]["tempo"] == "easy"
    assert (await client.get("/api/behaviors/nope")).status_code == 404


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
