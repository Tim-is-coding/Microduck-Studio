"""Behavior pack schema (`duckstudio.behavior/v0`, CLAUDE.md §6.2).

A behavior is a vertical list of steps with side branches (§3.2): `on_none` when a
perception step finds nothing, `until` to end a skill step, and `always` rules that
interrupt any step. No free-form graphs.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..common import ConditionStr, DurationStr, Identifier, Phrases, Strict, Text

BEHAVIOR_SCHEMA_ID = "duckstudio.behavior/v0"

# Reserved words allowed in `do:` lists next to skill ids.
RESERVED_ACTIONS = frozenset({"resume", "abort", "stop", "retry", "continue"})

Scalar = str | float | int | bool


class SpeechTrigger(Strict):
    kind: Literal["speech"]
    phrases: Phrases


class ManualTrigger(Strict):
    """Started from the Studio ("Start" button). Also what the speech button simulates in v1."""

    kind: Literal["manual"]


Trigger = Annotated[SpeechTrigger | ManualTrigger, Field(discriminator="kind")]


class SpeechCondition(Strict):
    speech: Phrases


class ElapsedCondition(Strict):
    elapsed: DurationStr


class SignalCondition(Strict):
    signal: ConditionStr


StopCondition = SpeechCondition | ElapsedCondition | SignalCondition


class Until(Strict):
    any: list[StopCondition] | None = Field(default=None, min_length=1)
    all: list[StopCondition] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _any_xor_all(self) -> Until:
        if (self.any is None) == (self.all is None):
            raise ValueError("`until` needs exactly one of `any` or `all`")
        return self


class OnNone(Strict):
    do: Identifier
    seconds: float = Field(gt=0, le=600)
    then: Literal["retry", "abort", "continue"] = "retry"


class PerceiveStep(Strict):
    perceive: str = Field(
        pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        description="Perception query, e.g. person.nearest",
    )
    on_none: OnNone | None = None


class SkillStep(Strict):
    skill: Identifier
    with_: dict[str, Scalar] = Field(default_factory=dict, alias="with")
    until: Until | None = None


class WaitStep(Strict):
    wait: DurationStr


Step = PerceiveStep | SkillStep | WaitStep


class AlwaysRule(Strict):
    on: ConditionStr
    do: list[Identifier] = Field(min_length=1)


class VlmOptIn(Strict):
    """Opt-in per behavior (§7). The Studio shows "Bild wird an <provider> gesendet"."""

    provider: str = Field(min_length=1)
    purpose: Text | None = None


class BehaviorPack(Strict):
    schema_: Literal["duckstudio.behavior/v0"] = Field(alias="schema")
    id: Identifier
    name: Text
    summary: Text | None = None
    trigger: Trigger
    steps: list[Step] = Field(min_length=1)
    always: list[AlwaysRule] = Field(default_factory=list)
    vlm: VlmOptIn | None = None

    @property
    def skill_ids(self) -> set[str]:
        ids: set[str] = set()
        for step in self.steps:
            if isinstance(step, SkillStep):
                ids.add(step.skill)
            elif isinstance(step, PerceiveStep) and step.on_none:
                ids.add(step.on_none.do)
        for rule in self.always:
            ids.update(a for a in rule.do if a not in RESERVED_ACTIONS)
        return ids
