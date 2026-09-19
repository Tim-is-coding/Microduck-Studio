from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from duckstudio.common import Condition, Interrupt
from duckstudio.skills import SkillManifest, SkillRegistry, load_skill_manifest


def test_all_example_manifests_load(root: Path) -> None:
    paths = sorted((root / "skills").glob("*.skill.yaml"))
    assert paths, "no skill manifests found"
    for p in paths:
        m = load_skill_manifest(p)
        assert m.id == p.name.removesuffix(".skill.yaml")


def test_walk_manifest_matches_handover(registry: SkillRegistry) -> None:
    walk = registry.get("walk")
    assert walk.intent == "robot.move"
    assert walk.params["vx"].max == 0.15
    assert walk.is_movement
    assert Condition.parse(walk.preconditions[1]) == Condition("battery", ">", 0.15)
    assert Interrupt.parse(walk.interrupts[0]) == Interrupt("fallen", ("getup", "resume"))


def _minimal(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": "duckstudio.skill/v0",
        "id": "x",
        "name": {"de": "X"},
        "source": {"kind": "builtin", "policy": "p"},
        "intent": "robot.x",
        "params": {"vx": {"type": "float", "min": -1, "max": 1}},
    }
    base.update(over)
    return base


def test_rejects_wrong_schema_id() -> None:
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(_minimal(schema="duckstudio.skill/v1"))


def test_rejects_intent_and_behavior_together() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        SkillManifest.model_validate(_minimal(behavior="stand"))


def test_rejects_ui_mapping_to_unknown_param() -> None:
    ui = {
        "tempo": {"control": "choice", "options": ["a", "b"], "maps_to": "nope", "values": [1, 2]}
    }
    with pytest.raises(ValidationError, match="unknown param"):
        SkillManifest.model_validate(_minimal(ui=ui))


def test_rejects_choice_values_length_mismatch() -> None:
    ui = {"tempo": {"control": "choice", "options": ["a", "b"], "maps_to": "vx", "values": [1]}}
    with pytest.raises(ValidationError, match="one entry per option"):
        SkillManifest.model_validate(_minimal(ui=ui))


def test_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(_minimal(joints=[0.0]))


def test_rejects_malformed_condition() -> None:
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(_minimal(preconditions=["battery >> 1"]))
