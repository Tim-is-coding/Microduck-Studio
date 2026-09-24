from __future__ import annotations

import time
from pathlib import Path

import pytest

from duckstudio import behaviors_dir, repo_root, skills_dir
from duckstudio.backends.mock import ManualClock, MockBackend
from duckstudio.behaviors import BehaviorPack, load_behavior_packs
from duckstudio.perception.vlm import VlmAnswer
from duckstudio.skills import SkillRegistry


@pytest.fixture(autouse=True)
def _no_real_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test ever reads or writes the person's real AI keys (ADR-0009), or uses theirs."""
    monkeypatch.setenv("DUCKSTUDIO_KEYS", str(tmp_path / "keys.json"))
    monkeypatch.setenv("DUCKSTUDIO_MODELS", str(tmp_path / "models"))  # nor a downloaded model
    for name in ("DUCKSTUDIO_VLM", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def root() -> Path:
    return repo_root()


@pytest.fixture(scope="session")
def registry() -> SkillRegistry:
    return SkillRegistry.load(skills_dir())


@pytest.fixture(scope="session")
def packs() -> dict[str, BehaviorPack]:
    return load_behavior_packs(behaviors_dir())


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
async def mock(clock: ManualClock) -> MockBackend:
    b = MockBackend(clock=clock)
    await b.connect()
    return b


class RecordingVlm:
    """A provider that answers from a script and remembers every frame it was handed.

    `sends_frames` is what the opt-in check in the perception service cares about, so tests
    can play both a service that would leave the machine and one that never does.
    """

    def __init__(
        self,
        *,
        name: str = "anthropic",
        sends_frames: bool = True,
        configured: bool = True,
        found: bool = True,
        pixel_x: float = 90.0,
        pixel_y: float = 300.0,
        answer: str = "Ich sehe den Ball links.",
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.model = "test-model"
        self.sends_frames = sends_frames
        self.configured = configured
        self.found = found
        self.pixel_x = pixel_x
        self.pixel_y = pixel_y
        self.answer = answer
        self.error = error
        self.calls: list[tuple[int, str]] = []  # (frame size in bytes, question)

    async def look(self, frame: bytes, question: str, *, timestamp: float | None = None):
        self.calls.append((len(frame), question))
        if self.error is not None:
            raise self.error
        return VlmAnswer(
            timestamp=time.monotonic() if timestamp is None else timestamp,
            question=question,
            found=self.found,
            answer=self.answer,
            pixel_x=self.pixel_x if self.found else None,
            pixel_y=self.pixel_y if self.found else None,
            provider=self.name,
            model=self.model,
            latency_s=0.01,
        )
