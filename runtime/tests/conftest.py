from __future__ import annotations

from pathlib import Path

import pytest

from duckstudio import behaviors_dir, repo_root, skills_dir
from duckstudio.backends.mock import ManualClock, MockBackend
from duckstudio.behaviors import BehaviorPack, load_behavior_packs
from duckstudio.skills import SkillRegistry


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
