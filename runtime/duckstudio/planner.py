"""A behavior drafted from a sentence, by the vendor whose key is in the Studio (ADR-0011).

„Wenn ich ‚Hallo‘ sage, such mich, lauf zu mir und quak zweimal" goes to a text model together
with the building blocks this Studio has and the rules of `duckstudio.behavior/v0`. What comes
back is checked like any pack the Studio loads — schema, then the skill registry — and a
draft that fails gets one more try with the problems listed. The result is a *draft*: it opens
in the editor, and nothing is saved or run until the person does it (§3, §4: the human builds
the behavior; the model only drafts it).

No camera frame is involved and none is sent; the model sees the sentence and the catalogue.
Model output is data, never instructions (§10): it is parsed as JSON and validated, nothing in
it is executed or followed.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from .behaviors import BehaviorPack, validate_against_registry
from .perception.vlm_rest import GEMINI_BASE, OPENAI_BASE, json_from_text
from .skills import SkillRegistry

log = logging.getLogger(__name__)

TIMEOUT_S = 90.0
MAX_DESCRIPTION = 1000


class PlannerError(RuntimeError):
    """The vendor could not produce a usable draft. Never carries a key."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class TextModel(Protocol):
    name: str
    model: str

    async def complete(self, system: str, user: str) -> str: ...


# -- the three vendors, text only ------------------------------------------------------------


class AnthropicText:
    """Claude through the official SDK. Server-side fallbacks (`"default"`) so a declined
    request is answered by the model Anthropic recommends instead of failing the draft."""

    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self.model = model
        self._key = api_key
        self._client = client

    async def complete(self, system: str, user: str) -> str:
        from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic

        client = self._client or AsyncAnthropic(api_key=self._key, timeout=TIMEOUT_S, max_retries=1)
        try:
            message = await client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "medium"},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except APIStatusError as e:
            raise PlannerError("vendor", f"HTTP {e.status_code}") from e
        except APIConnectionError as e:
            raise PlannerError("unreachable", type(e).__name__) from e
        finally:
            if self._client is None:
                await client.close()
        if message.stop_reason == "refusal":
            raise PlannerError("refused")
        text = next((b.text for b in message.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise PlannerError("empty", f"stop_reason={message.stop_reason}")
        return text


class GeminiText:
    name = "google"

    def __init__(
        self, *, api_key: str, model: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self._key = api_key
        self._client = client

    async def complete(self, system: str, user: str) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        response = await _post(
            self._client,
            f"{GEMINI_BASE}/models/{self.model}:generateContent",
            {"x-goog-api-key": self._key},
            body,
        )
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise PlannerError("empty") from e


class OpenAiText:
    name = "openai"

    def __init__(
        self, *, api_key: str, model: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self._key = api_key
        self._client = client

    async def complete(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "store": False,
            "instructions": system,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": user}]}],
            "text": {"format": {"type": "json_object"}},
        }
        response = await _post(
            self._client,
            f"{OPENAI_BASE}/responses",
            {"Authorization": f"Bearer {self._key}"},
            body,
        )
        payload = response.json()
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        for item in payload.get("output", []) or []:
            for part in item.get("content", []) or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    return part["text"]
        raise PlannerError("empty")


async def _post(
    client: httpx.AsyncClient | None, url: str, headers: dict[str, str], body: dict[str, Any]
) -> httpx.Response:
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_S)
    try:
        response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as e:
        raise PlannerError("unreachable", type(e).__name__) from e
    finally:
        if own:
            await client.aclose()
    if response.status_code != 200:
        raise PlannerError("vendor", f"HTTP {response.status_code}")  # no body: it may echo
    return response


# -- the prompt ------------------------------------------------------------------------------


def catalogue(registry: SkillRegistry) -> list[dict[str, Any]]:
    """The building blocks as the model needs them: what each is called, and its card."""
    out = []
    for skill in registry:
        controls: dict[str, Any] = {}
        for key, control in skill.ui.items():
            spec = control.model_dump(exclude_none=True)
            spec.pop("maps_to", None)
            spec.pop("values", None)
            controls[key] = spec
        out.append(
            {
                "id": skill.id,
                "name": skill.name.de,
                "what": skill.summary.de if skill.summary else "",
                "with": controls,
                "moves": skill.is_movement,
            }
        )
    return out


def system_prompt(
    registry: SkillRegistry, examples: Iterable[BehaviorPack], *, vlm_vendor: str
) -> str:
    example_json = [p.model_dump(by_alias=True, exclude_none=True, mode="json") for p in examples]
    return "\n".join(
        [
            "You draft behaviors for Duck Studio, a visual editor for a small walking robot "
            "duck (25 cm, camera, depth sensor, it quacks but cannot speak). A behavior is a "
            "vertical list of steps; the person who asked will review your draft in the "
            "editor before anything runs.",
            "",
            "Answer with ONE JSON object: a behavior pack, schema `duckstudio.behavior/v0`. "
            "No prose, no code fence.",
            "",
            "Rules:",
            "- Use only the building blocks listed below, by `id`, and only the controls "
            "listed under their `with`, with values from their `options` or within "
            "`min`..`max`. Leave out a control to use its default.",
            "- Steps are one of: {skill, with, until?} — {perceive, on_none?, question?} — "
            "{wait: '5s'}. Durations look like 30s, 5m.",
            "- `perceive: person.nearest` finds the nearest person on this computer. Use it "
            "whenever the behavior is about a person; then walk with direction toward_person.",
            "- `perceive: vlm.target` asks an AI model about the picture and needs "
            "`question: {de, en}` and a top-level `vlm: {provider: "
            f'"{vlm_vendor}", purpose: {{de, en}}}}`; then walk with direction '
            "toward_target. Use it only for things that are not a person (a ball, a door).",
            "- A walk step that could go on for ever gets `until`, e.g. "
            '{"any": [{"speech": {"de": ["Stopp"], "en": ["Stop"]}}, {"elapsed": "5m"}]}.',
            "- Say how it starts: `trigger` {kind: speech, phrases: {de: [...], en: [...]}} "
            "when the person mentions something to say, else {kind: manual}.",
            "- Always add `always: [{on: fallen, do: [getup, resume]}]` when the behavior "
            "walks and a getup block exists.",
            "- `id`: short kebab-case, English. `name` and `summary`: {de, en}, German "
            "first, plain words a child understands; the summary says what the duck does.",
            "- Signals for `until`/`always`: fallen, motor_hot, battery, tof_distance, "
            "person_found, target_found, target_reached, standing, sitting "
            "(e.g. 'tof_distance < 0.3').",
            "- If the request asks for something no block can do (talking, flying, "
            "picking a person up), draft the closest safe behavior and put what is missing "
            "into the summary.",
            "",
            "Building blocks:",
            json.dumps(catalogue(registry), ensure_ascii=False, indent=1),
            "",
            "Examples of valid packs:",
            json.dumps(example_json, ensure_ascii=False, indent=1),
        ]
    )


# -- drafting --------------------------------------------------------------------------------


@dataclass
class Draft:
    pack: BehaviorPack
    problems: list[str]
    vendor: str
    model: str
    attempts: int
    seconds: float


def _parse(text: str) -> tuple[BehaviorPack | None, list[str]]:
    try:
        data = json_from_text(text)
    except Exception as e:  # noqa: BLE001 - a broken answer is a problem to report back
        return None, [f"not JSON: {e}"]
    data.setdefault("schema", "duckstudio.behavior/v0")
    try:
        return BehaviorPack.model_validate(data), []
    except ValidationError as e:
        problems = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:12]
        ]
        return None, problems


def _unique_id(pack: BehaviorPack, taken: set[str]) -> BehaviorPack:
    if pack.id not in taken:
        return pack
    base = re.sub(r"-\d+$", "", pack.id)
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return pack.model_copy(update={"id": f"{base}-{n}"})


async def draft_behavior(
    description: str,
    model: TextModel,
    registry: SkillRegistry,
    *,
    examples: Iterable[BehaviorPack],
    taken_ids: set[str],
    vlm_vendor: str,
) -> Draft:
    description = description.strip()
    if not description:
        raise PlannerError("empty_description")
    if len(description) > MAX_DESCRIPTION:
        raise PlannerError("too_long")
    system = system_prompt(registry, list(examples), vlm_vendor=vlm_vendor)
    user = f"Beschreibung des Ablaufs, in den Worten der Person:\n{description}"
    started = time.monotonic()
    problems: list[str] = []
    for attempt in (1, 2):
        text = await model.complete(system, user)
        pack, problems = _parse(text)
        if pack is not None:
            problems = validate_against_registry(pack, registry)
            if not problems:
                return Draft(
                    pack=_unique_id(pack, taken_ids),
                    problems=[],
                    vendor=model.name,
                    model=model.model,
                    attempts=attempt,
                    seconds=time.monotonic() - started,
                )
        log.info("draft attempt %d had %d problems", attempt, len(problems))
        user = (
            f"Beschreibung des Ablaufs, in den Worten der Person:\n{description}\n\n"
            "Your last draft could not be used. Fix exactly these problems and answer with "
            "the whole corrected JSON object:\n- " + "\n- ".join(problems)
        )
    raise PlannerError("invalid", "; ".join(problems[:5]))
