"""Ändern → Speichern → Ausführen (§3.1, M3): the Studio edits packs through the runtime."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

from duckstudio import behaviors_dir
from duckstudio.api import create_app
from duckstudio.backends.mock import MockBackend
from duckstudio.behaviors import load_behavior_pack, pack_to_yaml
from duckstudio.yamlio import load_yaml_str


@pytest.fixture
def behaviors_tmp(tmp_path: Path) -> Path:
    for p in behaviors_dir().glob("*.behavior.yaml"):
        shutil.copy(p, tmp_path / p.name)
    return tmp_path


@pytest.fixture
async def client(mock: MockBackend, behaviors_tmp: Path):
    app = create_app(mock, behaviors_path=behaviors_tmp, auto_connect=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


NEW_PACK = {
    "schema": "duckstudio.behavior/v0",
    "id": "begruessung",
    "name": {"de": "Begrüßung"},
    "trigger": {"kind": "manual"},
    "steps": [
        {"skill": "quack", "with": {"style": "double"}},
        {"wait": "2s"},
        {
            "skill": "look_around",
            "with": {"pattern": "left"},
            "until": {"any": [{"elapsed": "3s"}]},
        },
    ],
    "always": [{"on": "fallen", "do": ["getup", "resume"]}],
}


async def test_save_lists_and_persists_a_new_behavior(
    client: httpx.AsyncClient, behaviors_tmp: Path
) -> None:
    r = await client.put("/api/behaviors/begruessung", json=NEW_PACK)
    assert r.status_code == 200, r.text
    assert r.json()["problems"] == []
    path = behaviors_tmp / "begruessung.behavior.yaml"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "id: begruessung" in text and "on: fallen" in text and "'on'" not in text
    reloaded = load_behavior_pack(path)
    assert reloaded.id == "begruessung" and len(reloaded.steps) == 3
    ids = {b["id"] for b in (await client.get("/api/behaviors")).json()}
    assert ids == {"follow-me", "begruessung"}
    yaml_text = (await client.get("/api/behaviors/begruessung/yaml")).text
    assert yaml_text.startswith("schema: duckstudio.behavior/v0\nid: begruessung\n")


async def test_saved_yaml_round_trips_the_spec_example(behaviors_tmp: Path) -> None:
    original = load_behavior_pack(behaviors_tmp / "follow-me.behavior.yaml")
    dumped = pack_to_yaml(original)
    again = original.model_validate(load_yaml_str(dumped))
    assert again == original
    assert "until:\n      any:\n        - speech:" in dumped  # lists indented under their key


async def test_validate_reports_schema_and_registry_problems(client: httpx.AsyncClient) -> None:
    broken = dict(NEW_PACK, steps=[{"skill": "fly"}, {"skill": "walk", "with": {"tempo": "warp"}}])
    r = await client.post("/api/behaviors/validate", json=broken)
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert any("unknown skill 'fly'" in p for p in body["problems"])
    assert any("'warp' is not one of" in p for p in body["problems"])
    r = await client.post(
        "/api/behaviors/validate", json={"schema": "duckstudio.behavior/v0", "id": "x"}
    )
    assert r.json()["valid"] is False and any(p.startswith("name") for p in r.json()["problems"])
    assert (await client.post("/api/behaviors/validate", json=NEW_PACK)).json() == {
        "valid": True,
        "problems": [],
    }


async def test_save_rejects_bad_ids_and_schema(client: httpx.AsyncClient) -> None:
    assert (await client.put("/api/behaviors/other", json=NEW_PACK)).status_code == 400
    bad = dict(NEW_PACK, steps=[])
    r = await client.put("/api/behaviors/begruessung", json=bad)
    assert r.status_code == 422 and "steps" in r.json()["detail"]["problems"][0]


async def test_delete_and_running_guard(client: httpx.AsyncClient, behaviors_tmp: Path) -> None:
    await client.put("/api/behaviors/begruessung", json=NEW_PACK)
    await client.get("/api/health")
    assert (await client.post("/api/behaviors/begruessung/run")).status_code == 200
    assert (await client.delete("/api/behaviors/begruessung")).status_code == 409
    assert (await client.put("/api/behaviors/begruessung", json=NEW_PACK)).status_code == 409
    await client.post("/api/executor/abort")
    assert (await client.delete("/api/behaviors/begruessung")).json() == {"ok": True}
    assert not (behaviors_tmp / "begruessung.behavior.yaml").exists()
    assert (await client.delete("/api/behaviors/begruessung")).status_code == 404
    assert (await client.get("/api/behaviors/begruessung")).status_code == 404
