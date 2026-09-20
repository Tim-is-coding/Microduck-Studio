"""The Studio's side of an import: search, add, use, remove — through the API."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

from duckstudio import behaviors_dir, skills_dir
from duckstudio.api import create_app
from duckstudio.backends.mock import MockBackend
from duckstudio.hub import HubClient

from .fake_hub import client as fake_client


@pytest.fixture
def skills_tmp(tmp_path: Path) -> Path:
    target = tmp_path / "skills"
    target.mkdir()
    for p in skills_dir().glob("*.skill.yaml"):
        shutil.copy(p, target / p.name)
    return target


@pytest.fixture
def behaviors_tmp(tmp_path: Path) -> Path:
    target = tmp_path / "behaviors"
    target.mkdir()
    for p in behaviors_dir().glob("*.behavior.yaml"):
        shutil.copy(p, target / p.name)
    return target


@pytest.fixture
async def client(mock: MockBackend, skills_tmp: Path, behaviors_tmp: Path):
    app = create_app(
        mock,
        skills_path=skills_tmp,
        behaviors_path=behaviors_tmp,
        auto_connect=False,
        hub=HubClient(client=fake_client()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_search_is_served_to_the_studio(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/hub/policies", params={"q": "basketball"})
    assert r.status_code == 200
    (found,) = r.json()
    assert found["repo"] == "HannesVonEssen/microduck-basketball"
    assert found["slot_guess"] == "stand"  # a guess from its name and tags


async def test_import_writes_a_building_block_the_registry_serves(
    client: httpx.AsyncClient, skills_tmp: Path
) -> None:
    r = await client.post(
        "/api/hub/import",
        json={"repo": "HannesVonEssen/microduck-basketball", "slot": "walk"},
    )
    assert r.status_code == 200, r.text
    skill = r.json()
    assert skill["id"] == "basketball" and skill["source"]["kind"] == "hub"
    assert (skills_tmp / "basketball.skill.yaml").exists()

    ids = {s["id"] for s in (await client.get("/api/skills")).json()}
    assert "basketball" in ids

    events = (await client.get("/api/events")).json()
    imported = next(e for e in events if e["kind"] == "skill.imported")
    assert "HannesVonEssen/microduck-basketball" in imported["text"]["de"]
    assert imported["text"]["en"].startswith("Building block")


async def test_an_imported_block_can_be_removed_again_a_builtin_cannot(
    client: httpx.AsyncClient, skills_tmp: Path
) -> None:
    await client.post("/api/hub/import", json={"repo": "cdeplanne/microduck-walk", "slot": "walk"})
    assert (await client.delete("/api/skills/walk")).status_code == 409  # the repo's own
    r = await client.delete("/api/skills/walk_2")
    assert r.status_code == 200, r.text
    assert not (skills_tmp / "walk_2.skill.yaml").exists()
    assert "walk_2" not in {s["id"] for s in (await client.get("/api/skills")).json()}


async def test_a_block_a_behavior_still_uses_stays(client: httpx.AsyncClient) -> None:
    await client.post("/api/hub/import", json={"repo": "cdeplanne/microduck-walk", "slot": "walk"})
    pack = (await client.get("/api/behaviors/follow-me")).json()
    pack.pop("problems")  # the Studio strips it too before saving
    pack["steps"][1]["skill"] = "walk_2"
    assert (await client.put("/api/behaviors/follow-me", json=pack)).status_code == 200
    r = await client.delete("/api/skills/walk_2")
    assert r.status_code == 409 and "follow-me" in r.json()["detail"]


async def test_nonsense_requests_are_refused_with_a_reason(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/hub/import", json={"repo": "nobody/nothing", "slot": "walk"})
    assert r.status_code == 502  # the Hub knows no such repo
    r = await client.post(
        "/api/hub/import", json={"repo": "cdeplanne/microduck-walk", "slot": "teleport"}
    )
    assert r.status_code == 422 and "teleport" in r.json()["detail"]
