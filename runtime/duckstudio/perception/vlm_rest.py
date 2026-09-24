"""Google Gemini and OpenAI as the duck's slow eyes, over plain HTTPS (ADR-0009).

Same contract as `AnthropicVlm`: one frame, one question, `VlmAnswer` back, every failure a
`VlmError`. `httpx` is already a dependency; one POST per question needs no vendor SDK.

Request shapes were read from the vendors' references on 2026-09-24 (docs/adr/0009):

- Gemini `POST /v1beta/models/{model}:generateContent`, key in `x-goog-api-key` (never in the
  URL), image as `inline_data`, JSON through `generationConfig.responseMimeType` +
  `responseSchema`. Gemini points as `[y, x]` normalised to 0–1000 — the convention its
  image-understanding and Robotics-ER docs use — so the prompt asks for exactly that and the
  answer is scaled back to pixels here.
- OpenAI `POST /v1/responses`, bearer key, image as a base64 `input_image` data URL, JSON
  through `text.format` (`json_schema`, strict), `store: false`. OpenAI documents that its
  models struggle with precise spatial localisation; the Studio says so next to the vendor.
"""

from __future__ import annotations

import json
import re
import time
from base64 import standard_b64encode
from typing import Any

import httpx

from .vlm import DEFAULT_TIMEOUT_S, VlmAnswer, VlmError, frame_size, media_type

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_BASE = "https://api.openai.com/v1"

POINT_PROMPT = (
    "You are the eyes of a small walking robot duck. You get one camera frame and one "
    "question about it. Answer with JSON only.\n"
    "- `found` is true only when you can actually see the thing in this frame. Guessing "
    "where it might be sends the robot walking into a wall.\n"
    "- `point` is the centre of the thing as [y, x], each normalised to 0-1000 (0,0 is the "
    "top left corner). Use [-1, -1] when `found` is false.\n"
    "- `answer` is one short German sentence for the person watching the robot."
)

PIXEL_PROMPT = (
    "You are the eyes of a small walking robot duck. You get one camera frame and one "
    "question about it. Answer with JSON only.\n"
    "- `found` is true only when you can actually see the thing in this frame. Guessing "
    "where it might be sends the robot walking into a wall.\n"
    "- `x` and `y` are the centre of the thing in pixels: x from the left edge, y from the "
    "top edge of the image as given. Set both to -1 when `found` is false.\n"
    "- `answer` is one short German sentence for the person watching the robot."
)

# Gemini's schema dialect (an OpenAPI subset); types by their enum names.
GEMINI_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "found": {"type": "BOOLEAN"},
        "point": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "answer": {"type": "STRING"},
    },
    "required": ["found", "point", "answer"],
}

OPENAI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "answer": {"type": "string"},
    },
    "required": ["found", "x", "y", "answer"],
    "additionalProperties": False,
}


def json_from_text(text: str) -> dict[str, Any]:
    """The answer's JSON, also when a model wrapped it in a code fence anyway."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise VlmError(f"answer was not JSON: {text[:120]!r}") from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise VlmError(f"answer was not JSON: {text[:120]!r}") from e
    if not isinstance(data, dict):
        raise VlmError("answer was not a JSON object")
    return data


def _http_error(vendor: str, response: httpx.Response) -> VlmError:
    # The body may echo the request; never put the key or the frame into an error.
    return VlmError(f"{vendor} answered HTTP {response.status_code}")


class GeminiVlm:
    name = "google"
    sends_frames = True
    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def look(
        self, frame: bytes, question: str, *, timestamp: float | None = None
    ) -> VlmAnswer:
        width, height = frame_size(frame)
        body = {
            "systemInstruction": {"parts": [{"text": POINT_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": media_type(frame),
                                "data": standard_b64encode(frame).decode("ascii"),
                            }
                        },
                        {"text": f"Frage: {question}"},
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_SCHEMA,
            },
        }
        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{GEMINI_BASE}/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self._key},
                json=body,
            )
        except httpx.HTTPError as e:
            raise VlmError(f"google unreachable: {type(e).__name__}") from e
        if response.status_code != 200:
            raise _http_error("google", response)
        try:
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise VlmError("google answered without text") from e
        data = json_from_text(text)
        found = bool(data.get("found"))
        point = data.get("point")
        px = py = None
        if found and isinstance(point, list) and len(point) == 2:
            y, x = float(point[0]), float(point[1])
            if 0 <= x <= 1000 and 0 <= y <= 1000:
                px, py = x / 1000.0 * width, y / 1000.0 * height
        return VlmAnswer(
            timestamp=time.monotonic() if timestamp is None else timestamp,
            question=question,
            found=found and px is not None,
            answer=str(data.get("answer", "")),
            pixel_x=px,
            pixel_y=py,
            provider=self.name,
            model=self.model,
            latency_s=time.monotonic() - started,
        )


class OpenAiVlm:
    name = "openai"
    sends_frames = True
    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def look(
        self, frame: bytes, question: str, *, timestamp: float | None = None
    ) -> VlmAnswer:
        width, height = frame_size(frame)
        image = f"data:{media_type(frame)};base64,{standard_b64encode(frame).decode('ascii')}"
        body = {
            "model": self.model,
            "store": False,
            "instructions": PIXEL_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": image, "detail": "low"},
                        {
                            "type": "input_text",
                            "text": f"Bild: {width}x{height} Pixel.\nFrage: {question}",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "duck_look",
                    "schema": OPENAI_SCHEMA,
                    "strict": True,
                }
            },
        }
        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{OPENAI_BASE}/responses",
                headers={"Authorization": f"Bearer {self._key}"},
                json=body,
            )
        except httpx.HTTPError as e:
            raise VlmError(f"openai unreachable: {type(e).__name__}") from e
        if response.status_code != 200:
            raise _http_error("openai", response)
        text = _openai_text(response)
        data = json_from_text(text)
        found = bool(data.get("found"))
        return VlmAnswer(
            timestamp=time.monotonic() if timestamp is None else timestamp,
            question=question,
            found=found,
            answer=str(data.get("answer", "")),
            pixel_x=float(data["x"]) if found and data.get("x") is not None else None,
            pixel_y=float(data["y"]) if found and data.get("y") is not None else None,
            provider=self.name,
            model=self.model,
            latency_s=time.monotonic() - started,
        )


def _openai_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError as e:
        raise VlmError("openai answered without JSON") from e
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output", []) or []:
        for part in item.get("content", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
    raise VlmError("openai answered without text")
