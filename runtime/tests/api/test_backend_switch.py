"""Choosing the duck in the Studio (ADR-0007): simulation, practice duck or the real one.

What must hold: the old duck is stopped and let go before the new one is asked anything,
nothing it reported survives, a running behavior is never switched out from under, and a
missing tunnel is a sentence the Studio can show.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from duckstudio.api import create_app
from duckstudio.backends import make_backend
from duckstudio.backends.base import DuckBackend
from duckstudio.backends.mock import MockBackend


@pytest.fixture
def app_and_mock(mock: MockBackend, tmp_path: Path):
    def factory(kind: str, **options: Any) -> DuckBackend:
        if kind == "duck":  # a tunnel directory with no tunnel in it
            options.setdefault("tunnel_dir", str(tmp_path / "tunnel"))
            options.setdefault("console_url", None)
        return make_backend(kind, **options)

    return create_app(mock, auto_connect=False, backend_factory=factory), mock


@pytest.fixture
async def client(app_and_mock):
    app, _ = app_and_mock
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def events(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return (await client.get("/api/events")).json()


async def test_health_lists_the_choices(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    assert body["backends"] == ["mock", "sim", "duck"]
    assert body["backend"] == "mock" and body["connected"] is True
    assert body["backend_error"] is None and body["duck_host"] == ""


async def test_the_same_backend_again_changes_nothing(client, app_and_mock) -> None:
    app, mock = app_and_mock
    r = await client.put("/api/backend", json={"kind": "mock"})
    assert r.status_code == 200 and r.json()["connected"] is True
    assert app.state.backend is mock and not mock.stopped
    assert not any(e["kind"] == "backend.switched" for e in await events(client))


async def test_unknown_backends_and_odd_hosts_are_refused(client: httpx.AsyncClient) -> None:
    assert (await client.put("/api/backend", json={"kind": "robot"})).status_code == 422
    for host in ["duck.local; rm -rf ~", "$(whoami)", "-oProxyCommand=x", "a b"]:
        r = await client.put("/api/backend", json={"kind": "duck", "host": host})
        assert r.status_code == 422, host
    assert (await client.get("/api/health")).json()["backend"] == "mock"


async def test_to_the_duck_without_a_tunnel_says_how_to_open_one(client, app_and_mock) -> None:
    app, mock = app_and_mock
    app.state.gate.observe(state=await mock.state(), health=await mock.health())

    r = await client.put("/api/backend", json={"kind": "duck", "host": "duck.local"})
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "duck" and body["connected"] is False
    assert body["duck_host"] == "duck.local"
    assert "no tunnel" in body["backend_error"]
    assert "duck-tunnel.sh duck.local" in body["backend_error"]

    # the old duck was stopped and let go, and nothing it said is left behind
    assert mock.stopped and not mock.connected
    snap = app.state.gate.snapshot
    assert snap.state is None and snap.health is None and snap.tof_rows is None
    assert app.state.gate.backend is app.state.backend is app.state.perception.backend

    log = await events(client)
    assert not any(e["kind"] == "stop" for e in log)  # a switch is not a Notstopp
    switched = next(e for e in log if e["kind"] == "backend.switched")
    assert switched["text"] == {"de": "Gewechselt zu: Ente.", "en": "Switched to the duck."}
    unavailable = next(e for e in log if e["kind"] == "backend.unavailable")
    assert "scripts/duck-tunnel.sh duck.local" in unavailable["text"]["de"]

    # and nothing can be started against a duck that is not there
    assert (await client.post("/api/behaviors/follow-me/run")).status_code == 503


async def test_back_to_the_practice_duck(client: httpx.AsyncClient, app_and_mock) -> None:
    app, mock = app_and_mock
    await client.put("/api/backend", json={"kind": "duck"})
    r = await client.put("/api/backend", json={"kind": "mock"})
    body = r.json()
    assert body["backend"] == "mock" and body["connected"] is True
    assert body["backend_error"] is None
    assert app.state.backend is not mock  # a fresh one, not the duck we let go
    assert (await client.get("/api/state")).status_code == 200


async def test_a_running_behavior_is_not_switched_out_from_under(
    client: httpx.AsyncClient, app_and_mock
) -> None:
    app, mock = app_and_mock
    assert (await client.post("/api/behaviors/follow-me/run")).json()["state"] == "running"
    r = await client.put("/api/backend", json={"kind": "sim"})
    assert r.status_code == 409
    assert app.state.backend is mock and mock.connected
    await client.post("/api/executor/abort")
    assert (await client.put("/api/backend", json={"kind": "sim"})).json()["backend"] == "sim"
