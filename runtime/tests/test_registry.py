from __future__ import annotations

import pytest

from duckstudio.skills import SkillNotFound, SkillRegistry


def test_resolve_ui_maps_choice_to_param(registry: SkillRegistry) -> None:
    params, extras = registry.resolve_ui(
        "walk", {"tempo": "easy", "direction": "toward_person", "distance": 60}
    )
    assert params == {"vx": 0.08}
    assert extras == {"direction": "toward_person", "distance": 60}


def test_resolve_ui_accepts_direct_params_for_developers(registry: SkillRegistry) -> None:
    params, extras = registry.resolve_ui("walk", {"vx": 0.1, "vyaw": 0.2})
    assert params == {"vx": 0.1, "vyaw": 0.2} and extras == {}


def test_resolve_ui_rejects_unknown_option(registry: SkillRegistry) -> None:
    with pytest.raises(ValueError, match="unknown option"):
        registry.resolve_ui("walk", {"speed": 3})


def test_get_unknown_skill(registry: SkillRegistry) -> None:
    with pytest.raises(SkillNotFound):
        registry.get("fly")
