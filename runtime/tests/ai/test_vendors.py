"""AI vendors with keys from the Studio (ADR-0009): providers, router, API."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from duckstudio.api import create_app
from duckstudio.backends.mock import MockBackend
from duckstudio.keys import AiSettings, KeyStore
from duckstudio.perception import MockBarDetector, StubVlm
from duckstudio.perception import vendors as vendors_mod
from duckstudio.perception.vendors import KeyRejected, VlmRouter, env_names
from duckstudio.perception.vlm import VlmError
from duckstudio.perception.vlm_rest import GeminiVlm, OpenAiVlm

KEY = "AIza-test-key-0123456789"


def frame(width: int = 480, height: int = 360) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 200, 200)).save(out, format="JPEG")
    return out.getvalue()


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# -- providers -------------------------------------------------------------------------------


async def test_gemini_points_are_scaled_from_0_1000_to_pixels() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        answer = {"found": True, "point": [500, 250], "answer": "Da steht jemand."}
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}
        )

    vlm = GeminiVlm(api_key=KEY, model="gemini-robotics-er-2-preview", client=mock_client(handler))
    a = await vlm.look(frame(480, 360), "Wo ist die nächste Person?")
    assert a.found and (a.pixel_x, a.pixel_y) == (120.0, 180.0)  # [y, x] → x 25 %, y 50 %
    assert seen["url"].endswith("/models/gemini-robotics-er-2-preview:generateContent")
    assert seen["key"] == KEY and KEY not in seen["url"], "the key goes in a header, not the URL"
    body = seen["body"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "inline_data" in body["contents"][0]["parts"][0]


async def test_gemini_not_found_has_no_point() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        text = json.dumps({"found": False, "point": [-1, -1], "answer": "Niemand da."})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    a = await GeminiVlm(api_key=KEY, model="m", client=mock_client(handler)).look(frame(), "?")
    assert not a.found and a.pixel_x is None


async def test_openai_reads_pixels_and_does_not_store() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        text = json.dumps({"found": True, "x": 100, "y": 50, "answer": "Links."})
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": text}]}]}
        )

    a = await OpenAiVlm(api_key=KEY, model="gpt-6-luna", client=mock_client(handler)).look(
        frame(), "Wo?"
    )
    assert a.found and (a.pixel_x, a.pixel_y) == (100.0, 50.0)
    assert seen["body"]["store"] is False
    assert seen["body"]["text"]["format"]["type"] == "json_schema"
    assert seen["auth"] == f"Bearer {KEY}"


@pytest.mark.parametrize("cls", [GeminiVlm, OpenAiVlm])
async def test_a_failed_call_never_carries_the_key(cls) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"bad key {KEY}"}})

    with pytest.raises(VlmError) as e:
        await cls(api_key=KEY, model="m", client=mock_client(handler)).look(frame(), "?")
    assert KEY not in str(e.value) and "401" in str(e.value)


# -- router ----------------------------------------------------------------------------------


def router(tmp_path: Path) -> VlmRouter:
    return VlmRouter(KeyStore(tmp_path / "keys.json", env={}), StubVlm(MockBarDetector()))


def test_without_a_key_the_stub_stands_in(tmp_path: Path) -> None:
    r = router(tmp_path)
    assert r.resolve("google") is r.stub and r.configured() == []


def test_with_a_key_the_named_vendor_answers(tmp_path: Path) -> None:
    r = router(tmp_path)
    r.keys.set("google", KEY)
    p = r.resolve("google")
    assert isinstance(p, GeminiVlm) and p.model == "gemini-robotics-er-2-preview"
    assert r.resolve("google") is p, "built once per key and model"
    r.models["google"] = "gemini-3.5-flash-lite"
    assert r.resolve("google").model == "gemini-3.5-flash-lite"
    assert r.resolve("anthropic") is r.stub, "a key for one vendor is not consent for another"


def test_every_vendor_has_what_the_studio_shows() -> None:
    for v in vendors_mod.VENDORS.values():
        assert v.key_url.startswith("https://") and v.pricing_url.startswith("https://")
        assert v.models and v.note["de"] and v.note["en"]
    assert list(vendors_mod.VENDORS)[0] == "google" and vendors_mod.GOOGLE.recommended
    assert env_names()["google"] == "GEMINI_API_KEY"


# -- API -------------------------------------------------------------------------------------


@pytest.fixture
async def api(mock: MockBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []

    async def check(key: str, model: str) -> None:
        calls.append((key, model))
        if key != KEY:
            raise KeyRejected()

    fake = dataclasses.replace(vendors_mod.GOOGLE, check=check)  # never calls Google
    monkeypatch.setitem(vendors_mod.VENDORS, "google", fake)
    store = KeyStore(tmp_path / "keys.json", env={}, env_names=env_names())
    app = create_app(
        mock, auto_connect=False, keys=store, ai_settings=AiSettings(tmp_path / "ai.json")
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, store, calls


async def test_the_studio_lists_vendors_without_keys(api) -> None:
    client, _, _ = api
    body = (await client.get("/api/ai")).json()
    google = body["vendors"][0]
    assert google["id"] == "google" and google["key"] is None and google["free_tier"] is True
    assert google["key_url"] == "https://aistudio.google.com/apikey"


async def test_a_good_key_is_checked_kept_and_never_sent_back(api) -> None:
    client, store, calls = api
    r = await client.put("/api/ai/google/key", json={"key": KEY})
    assert r.status_code == 200
    assert calls == [(KEY, "gemini-robotics-er-2-preview")]
    assert store.get("google") == KEY
    listed = (await client.get("/api/ai")).text + (await client.get("/api/health")).text
    events = (await client.get("/api/events")).text
    assert KEY not in listed + events + r.text
    assert r.json()["key"] == {"source": "studio", "hint": "…6789"}
    assert (await client.get("/api/health")).json()["vlm"]["vendors"] == ["google"]


async def test_a_rejected_key_is_not_kept(api) -> None:
    client, store, _ = api
    r = await client.put("/api/ai/google/key", json={"key": "AIza-wrong-key-000000"})
    assert r.status_code == 422 and r.json()["detail"] == {"reason": "rejected"}
    assert store.get("google") is None


async def test_remove_and_model_choice(api) -> None:
    client, store, _ = api
    await client.put("/api/ai/google/key", json={"key": KEY})
    r = await client.put("/api/ai/google/model", json={"model": "gemini-3.5-flash-lite"})
    assert r.json()["model"] == "gemini-3.5-flash-lite"
    bad = await client.put("/api/ai/google/model", json={"model": "gpt-6-luna"})
    assert bad.status_code == 422
    await client.delete("/api/ai/google/key")
    assert store.get("google") is None


async def test_unknown_vendor_and_bad_format(api) -> None:
    client, _, _ = api
    assert (await client.put("/api/ai/skynet/key", json={"key": KEY})).status_code == 404
    r = await client.put("/api/ai/google/key", json={"key": "has a space"})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "format"
