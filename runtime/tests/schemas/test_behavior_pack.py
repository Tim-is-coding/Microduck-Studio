from __future__ import annotations

import pytest
from pydantic import ValidationError

from duckstudio.behaviors import BehaviorPack, validate_against_registry
from duckstudio.behaviors.schema import (
    ElapsedCondition,
    PerceiveStep,
    SkillStep,
    SpeechCondition,
    SpeechTrigger,
)
from duckstudio.common import parse_duration
from duckstudio.skills import SkillRegistry


def test_follow_me_loads_as_specified(packs: dict[str, BehaviorPack]) -> None:
    pack = packs["follow-me"]
    assert isinstance(pack.trigger, SpeechTrigger)
    assert pack.trigger.phrases.de == ["Folge mir", "Komm mit"]
    perceive, walk, quack = pack.steps
    assert isinstance(perceive, PerceiveStep) and perceive.perceive == "person.nearest"
    assert perceive.on_none is not None and perceive.on_none.do == "look_around"
    assert isinstance(walk, SkillStep) and walk.with_ == {
        "direction": "toward_person",
        "tempo": "easy",
        "distance": 60,
    }
    assert walk.until is not None and walk.until.any is not None
    speech, elapsed = walk.until.any
    assert isinstance(speech, SpeechCondition) and speech.speech.de == ["Stopp"]
    assert isinstance(elapsed, ElapsedCondition) and parse_duration(elapsed.elapsed) == 600.0
    assert isinstance(quack, SkillStep) and quack.skill == "quack"
    assert pack.always[0].do == ["getup", "resume"]
    assert pack.skill_ids == {"look_around", "walk", "quack", "getup"}


def test_follow_me_is_consistent_with_registry(
    packs: dict[str, BehaviorPack], registry: SkillRegistry
) -> None:
    assert validate_against_registry(packs["follow-me"], registry) == []


def test_unknown_skill_and_bad_option_are_reported(registry: SkillRegistry) -> None:
    pack = BehaviorPack.model_validate(
        {
            "schema": "duckstudio.behavior/v0",
            "id": "broken",
            "name": {"de": "Kaputt"},
            "trigger": {"kind": "manual"},
            "steps": [
                {"skill": "fly"},
                {"skill": "walk", "with": {"tempo": "warp"}},
                {"skill": "walk", "with": {"distance": 999}},
            ],
            "always": [{"on": "fallen", "do": ["teleport", "resume"]}],
        }
    )
    problems = validate_against_registry(pack, registry)
    assert len(problems) == 4
    assert "unknown skill 'fly'" in problems[0]
    assert "'warp' is not one of" in problems[1]
    assert "outside [30.0, 150.0]" in problems[2]
    assert "unknown skill 'teleport'" in problems[3]


def test_until_requires_any_or_all() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        BehaviorPack.model_validate(
            {
                "schema": "duckstudio.behavior/v0",
                "id": "b",
                "name": {"de": "B"},
                "trigger": {"kind": "manual"},
                "steps": [{"skill": "walk", "until": {}}],
            }
        )


@pytest.mark.parametrize(
    ("text", "seconds"), [("500ms", 0.5), ("5s", 5.0), ("10m", 600.0), ("1.5h", 5400.0)]
)
def test_parse_duration(text: str, seconds: float) -> None:
    assert parse_duration(text) == seconds


def test_parse_duration_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_yaml_on_key_stays_a_string() -> None:
    """PyYAML would read `on:` as boolean True; our loader keeps YAML 1.2 semantics."""
    from duckstudio.yamlio import load_yaml_str

    assert load_yaml_str("on: fallen\noff: x\nyes: y\nflag: true\n") == {
        "on": "fallen",
        "off": "x",
        "yes": "y",
        "flag": True,
    }
