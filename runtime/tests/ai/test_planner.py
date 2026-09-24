"""Drafting a behavior from a sentence (ADR-0011): checked like any pack, never saved or run."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from duckstudio import behaviors_dir
from duckstudio.api import create_app
from duckstudio.backends.mock import MockBackend
from duckstudio.keys import AiSettings, KeyStore
from duckstudio.perception import vendors as vendors_mod
from duckstudio.perception.vendors import env_names
from duckstudio.planner import AnthropicText, GeminiText, PlannerError, draft_behavior

KEY = "AIza-test-key-0123456789"

GOOD = {
    "id": "follow-me",  # taken: must come back renamed
    "name": {"de": "Hallo-Ente", "en": "Hello duck"},
    "summary": {"de": "Sucht dich und quakt zweimal.", "en": "Finds you and quacks twice."},
    "trigger": {"kind": "speech", "phrases": {"de": ["Hallo"], "en": ["Hello"]}},
    "steps": [
        {"perceive": "person.nearest", "on_none": {"do": "look_around", "seconds": 5}},
        {
            "skill": "walk",
            "with": {"direction": "toward_person", "tempo": "easy", "distance": 60},
            "until": {"any": [{"elapsed": "2m"}]},
        },
        {"skill": "quack", "with": {"style": "double"}},
    ],
    "always": [{"on": "fallen", "do": ["getup", "resume"]}],
}


class Scripted:
    """A text model that answers from a list, and remembers what it was asked."""

    name = "google"
    model = "gemini-test"

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.asked.append((system, user))
        return self.answers.pop(0)


async def draft(model, registry, packs):
    return await draft_behavior(
        "Wenn ich Hallo sage, such mich, lauf zu mir und quak zweimal.",
        model,
        registry,
        examples=[packs["follow-me"]],
        taken_ids=set(packs),
        vlm_vendor="google",
    )


async def test_a_good_draft_passes_and_gets_a_free_id(registry, packs) -> None:
    model = Scripted(json.dumps(GOOD))
    d = await draft(model, registry, packs)
    assert d.pack.id == "follow-me-2" and d.attempts == 1 and d.problems == []
    system, user = model.asked[0]
    assert '"id": "walk"' in system and "Hallo" in user


async def test_a_broken_draft_gets_one_more_try_with_its_problems(registry, packs) -> None:
    bad = {**GOOD, "steps": [{"skill": "fly", "with": {}}]}
    model = Scripted("not json at all", json.dumps(bad), json.dumps(GOOD))
    with pytest.raises(PlannerError) as e:
        await draft(Scripted("not json at all", json.dumps(bad)), registry, packs)
    assert e.value.reason == "invalid" and "fly" in e.value.detail
    model = Scripted(json.dumps(bad), json.dumps(GOOD))
    d = await draft(model, registry, packs)
    assert d.attempts == 2 and "unknown skill 'fly'" in model.asked[1][1]


async def test_empty_and_overlong_descriptions_are_refused(registry, packs) -> None:
    for text, reason in (("  ", "empty_description"), ("x" * 1001, "too_long")):
        with pytest.raises(PlannerError) as e:
            await draft_behavior(
                text, Scripted(), registry, examples=[], taken_ids=set(), vlm_vendor="google"
            )
        assert e.value.reason == reason


async def test_gemini_text_sends_json_mode_and_the_key_in_a_header() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"] = str(request.url), request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert (
        await GeminiText(api_key=KEY, model="gemini-3.8-flash", client=client).complete("s", "u")
        == "{}"
    )
    assert KEY not in seen["url"] and seen["key"] == KEY
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


async def test_claude_is_asked_with_server_side_fallbacks() -> None:
    seen: dict = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text="{}")]
        )

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    text = await AnthropicText(api_key=KEY, model="claude-opus-5", client=client).complete("s", "u")
    assert text == "{}" and seen["model"] == "claude-opus-5"
    assert seen["fallbacks"] == "default" and seen["betas"] == ["server-side-fallback-2026-07-01"]


async def test_a_refusal_is_a_planner_error() -> None:
    async def create(**kwargs):
        return SimpleNamespace(stop_reason="refusal", content=[])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(PlannerError) as e:
        await AnthropicText(api_key=KEY, model="m", client=client).complete("s", "u")
    assert e.value.reason == "refused"


# -- API -------------------------------------------------------------------------------------


@pytest.fixture
async def api(mock: MockBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = KeyStore(tmp_path / "keys.json", env={}, env_names=env_names())
    scripted = Scripted(json.dumps(GOOD))
    fake = dataclasses.replace(vendors_mod.GOOGLE, make_text=lambda key, model: scripted)
    monkeypatch.setitem(vendors_mod.VENDORS, "google", fake)
    app = create_app(
        mock, auto_connect=False, keys=store, ai_settings=AiSettings(tmp_path / "ai.json")
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, store


async def test_without_a_key_the_studio_is_told_so(api) -> None:
    client, _ = api
    r = await client.post("/api/planner/draft", json={"description": "Quak einmal."})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "no_key"


async def test_a_draft_comes_back_and_nothing_is_saved(api) -> None:
    client, store = api
    store.set("google", KEY)
    before = sorted(p.name for p in behaviors_dir().glob("*.yaml"))
    r = await client.post("/api/planner/draft", json={"description": "Such mich und quak zweimal."})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft"]["id"] == "follow-me-2" and body["vendor"] == "google"
    assert sorted(p.name for p in behaviors_dir().glob("*.yaml")) == before
    assert "follow-me-2" not in [b["id"] for b in (await client.get("/api/behaviors")).json()]
    events = (await client.get("/api/events")).text
    assert "Entwurf von Google" in events and KEY not in events + r.text
