"""The slow half of perception (§4): one question, one frame, one answer, 0.5–2 Hz.

A VLM answers questions the local detectors cannot ("Wo ist der rote Ball?") and points at
the thing; the executor turns that pixel into a bearing and steers to it. It never runs in
the loop that brakes the duck — the perception service calls it in its own task and the
executor reads the last answer (§6.4).

The provider is an adapter so the model stays swappable (ADR-0004):

  `AnthropicVlm`  Claude, via the official SDK. Frames leave the machine — only ever for a
                  behavior that opted in, and the Studio says so in red (§7).
  `StubVlm`       the local blob detector wearing a VLM's clothes. No key, no network, no
                  frame leaving the runtime; the Studio and the executor work end to end.

Default is the stub: sending pictures to a paid service is something you switch on
(`DUCKSTUDIO_VLM=anthropic`), never something that happens because a key was lying around.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
import time
from base64 import standard_b64encode
from typing import Any, Protocol, runtime_checkable

from PIL import Image

from ..common import Strict, Text
from .base import TargetSighting
from .person_local import FX, UPRIGHT_WIDTH, fuse_distance

log = logging.getLogger(__name__)

MAX_HZ = 2.0  # §4: the VLM may never run faster than this
DEFAULT_HZ = 0.5
MIN_HZ = 0.1
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_TIMEOUT_S = 20.0
MAX_TOKENS = 256

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class VlmError(RuntimeError):
    """The provider could not answer this question about this frame."""


class VlmNotConfigured(VlmError):
    """No key, no package, no provider — nothing was sent anywhere."""


class VlmAnswer(Strict):
    """One answer, as the Studio's log and the executor see it."""

    timestamp: float
    question: str
    found: bool
    answer: str = ""
    pixel_x: float | None = None
    pixel_y: float | None = None
    provider: str
    model: str
    latency_s: float


@runtime_checkable
class VlmProvider(Protocol):
    """What the perception service needs from a model. Swap the class, keep the runtime."""

    name: str
    model: str
    sends_frames: bool  # does a camera frame leave this machine?

    @property
    def configured(self) -> bool: ...

    async def look(
        self, frame: bytes, question: str, *, timestamp: float | None = None
    ) -> VlmAnswer: ...


# -- geometry ----------------------------------------------------------------------------


def frame_size(frame: bytes) -> tuple[int, int]:
    """(width, height) of an encoded frame, read from the header."""
    with Image.open(io.BytesIO(frame)) as img:
        return int(img.width), int(img.height)


def media_type(frame: bytes) -> str:
    return "image/png" if frame[:8] == PNG_SIGNATURE else "image/jpeg"


def sighting_from_answer(
    answer: VlmAnswer,
    *,
    width: int,
    height: int,
    label: Text,
    tof_rows: list[list[float]] | None = None,
) -> TargetSighting | None:
    """Turn a target pixel into something the executor can steer by.

    Same optics as the local detector (`person_local`): the focal length scales with the
    image width, a pixel right of centre is a negative bearing, and the ToF supplies the
    range when a zone agrees with where the thing appears to be.
    """
    if not answer.found or answer.pixel_x is None or answer.pixel_y is None:
        return None
    if not (0 <= answer.pixel_x <= width and 0 <= answer.pixel_y <= height):
        log.warning("vlm answer points outside the frame: %s/%s", answer.pixel_x, answer.pixel_y)
        return None
    fx = FX * width / UPRIGHT_WIDTH
    bearing = -math.atan2(answer.pixel_x - width / 2.0, fx)
    sighting = TargetSighting(
        timestamp=answer.timestamp,
        bearing_rad=bearing,
        distance_m=None,
        pixel_x=answer.pixel_x,
        pixel_y=answer.pixel_y,
        frame_width=width,
        frame_height=height,
        label=label,
        source=answer.provider,
    )
    return fuse_distance(sighting, tof_rows)


# -- providers ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are the eyes of a small walking robot duck. You get one camera frame and one "
    "question about it, and you answer with JSON only.\n"
    "- `found` is true only when you can actually see the thing in this frame. Guessing "
    "where it might be sends the robot walking into a wall.\n"
    "- `x` and `y` are the centre of the thing in pixels: x from the left edge, y from the "
    "top edge of the image as given. Set both to -1 when `found` is false.\n"
    "- `answer` is one short German sentence for the person watching the robot."
)

ANSWER_SCHEMA: dict[str, Any] = {
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


class AnthropicVlm:
    """Claude as the duck's slow eyes, through the official SDK (ADR-0004).

    Structured output pins the answer to `ANSWER_SCHEMA`, `effort: low` keeps the latency
    in the second range, and the client's own timeout bounds the call — a hanging provider
    delays the next question and nothing else.
    """

    name = "anthropic"
    sends_frames = True

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.environ.get("DUCKSTUDIO_VLM_MODEL") or DEFAULT_MODEL
        self.timeout_s = timeout_s
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = client

    @property
    def configured(self) -> bool:
        if self._client is not None:
            return True
        if not (self._api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False
        try:
            import anthropic  # noqa: F401
        except ModuleNotFoundError:
            return False
        return True

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from anthropic import AsyncAnthropic
        except ModuleNotFoundError as e:  # pragma: no cover - depends on the install
            raise VlmNotConfigured(
                "the `anthropic` package is missing; install the extra: uv sync --extra vlm"
            ) from e
        if not (self._api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise VlmNotConfigured("ANTHROPIC_API_KEY is not set")
        self._client = AsyncAnthropic(api_key=self._api_key, timeout=self.timeout_s, max_retries=1)
        return self._client

    async def look(
        self, frame: bytes, question: str, *, timestamp: float | None = None
    ) -> VlmAnswer:
        client = self._ensure_client()
        width, height = frame_size(frame)
        started = time.monotonic()
        try:
            message = await client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type(frame),
                                    "data": standard_b64encode(frame).decode("ascii"),
                                },
                            },
                            {
                                "type": "text",
                                "text": f"Bild: {width}x{height} Pixel.\nFrage: {question}",
                            },
                        ],
                    }
                ],
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
                },
            )
        except VlmError:
            raise
        except Exception as e:  # noqa: BLE001 - every provider failure is one kind to us
            raise VlmError(f"{type(e).__name__}: {e}") from e
        latency = time.monotonic() - started
        return self._parse(message, question, latency, timestamp)

    def _parse(
        self, message: Any, question: str, latency: float, timestamp: float | None
    ) -> VlmAnswer:
        text = next(
            (b.text for b in getattr(message, "content", []) if getattr(b, "type", "") == "text"),
            None,
        )
        if text is None:
            raise VlmError(f"no text block in the answer (stop_reason={message.stop_reason!r})")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise VlmError(f"answer was not JSON: {text[:120]!r}") from e
        found = bool(data.get("found"))
        return VlmAnswer(
            timestamp=time.monotonic() if timestamp is None else timestamp,
            question=question,
            found=found,
            answer=str(data.get("answer", "")),
            pixel_x=float(data["x"]) if found and data.get("x") is not None else None,
            pixel_y=float(data["y"]) if found and data.get("y") is not None else None,
            provider=self.name,
            model=getattr(message, "model", None) or self.model,
            latency_s=latency,
        )


class StubVlm:
    """A VLM-shaped stand-in that runs on the machine it is asked on.

    It re-uses the local blob detector, so it "finds" the same marker the person detector
    finds and answers in the same shape a real model would. It is not clever and says so;
    what it buys is a Studio, an editor and an executor that work without a key, and a test
    suite that never touches the network.
    """

    name = "stub"
    model = "local-blob"
    sends_frames = False
    configured = True

    def __init__(self, detector: Any, *, delay_s: float = 0.0) -> None:
        self.detector = detector
        self.delay_s = delay_s

    async def look(
        self, frame: bytes, question: str, *, timestamp: float | None = None
    ) -> VlmAnswer:
        started = time.monotonic()
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        try:
            seen = self.detector.detect(frame)
        except Exception as e:  # noqa: BLE001 - a bad frame is an unanswered question
            raise VlmError(f"{type(e).__name__}: {e}") from e
        now = time.monotonic() if timestamp is None else timestamp
        if seen is None:
            return VlmAnswer(
                timestamp=now,
                question=question,
                found=False,
                answer="",  # the sentence for the log is written in `texts.py`, in both languages
                provider=self.name,
                model=self.model,
                latency_s=time.monotonic() - started,
            )
        return VlmAnswer(
            timestamp=now,
            question=question,
            found=True,
            answer="",
            pixel_x=seen.pixel_x,
            pixel_y=seen.pixel_y,
            provider=self.name,
            model=self.model,
            latency_s=time.monotonic() - started,
        )


def vlm_hz(value: str | float | None = None) -> float:
    """Ask rate, clamped to the band §4 allows (0.5–2 Hz, slower on request)."""
    raw = os.environ.get("DUCKSTUDIO_VLM_HZ", "") if value is None else str(value)
    try:
        hz = float(raw)
    except ValueError:
        hz = DEFAULT_HZ
    if hz <= 0:
        hz = DEFAULT_HZ
    return max(MIN_HZ, min(MAX_HZ, hz))


def make_vlm(kind: str | None = None, *, detector: Any | None = None) -> VlmProvider:
    """The provider the runtime runs with. `DUCKSTUDIO_VLM=anthropic` opts into the API."""
    chosen = (kind or os.environ.get("DUCKSTUDIO_VLM") or "stub").strip().lower()
    if chosen in ("anthropic", "claude"):
        return AnthropicVlm()
    if chosen != "stub":
        log.warning("unknown DUCKSTUDIO_VLM=%r, falling back to the local stub", chosen)
    if detector is None:
        from .person_local import MagentaPersonDetector

        detector = MagentaPersonDetector()
    return StubVlm(detector)
