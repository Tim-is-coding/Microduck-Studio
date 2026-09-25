"""Behavior pack schema (`duckstudio.behavior/v0`, CLAUDE.md §6.2).

A behavior is a vertical list of steps with side branches (§3.2): `only_if` to skip a step
(ADR-0012), `on_none` when a perception step finds nothing, `until` to end a skill step, and
`always` rules that interrupt any step. No free-form graphs.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..common import ConditionStr, DurationStr, Identifier, Phrases, Strict, Text

BEHAVIOR_SCHEMA_ID = "duckstudio.behavior/v0"

# Reserved words allowed in `do:` lists next to skill ids.
RESERVED_ACTIONS = frozenset({"resume", "abort", "stop", "retry", "continue"})

# What a `perceive:` step may ask for. `person.*` is answered by a local detector on every
# frame; `vlm.*` by the model the behavior opted into, 0.5–2 Hz (§4, ADR-0004).
PERCEIVE_QUERIES = frozenset({"person.nearest", "vlm.target"})
VLM_QUERY_PREFIX = "vlm."
# What `only_if: {signal: …}` may look at: what the duck and its sensors say right now
# (executor/conditions.py, `signal_value`).
CHECK_SIGNALS = frozenset(
    {
        "battery",
        "motor_hot",
        "standing",
        "fallen",
        "sitting",
        "moving",
        "steady",
        "tof_distance",
        "person_found",
        "person_distance",
        "target_found",
        "target_distance",
    }
)

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


class SignalCheck(Strict):
    """Run the step only if a signal holds right now: `person_found`, `tof_distance < 0.5`."""

    signal: ConditionStr

    @model_validator(mode="after")
    def _known_signal(self) -> SignalCheck:
        # An unknown signal is never true, so the step would be skipped every time without a
        # word. Step-context signals (`timeout`, `elapsed`, `target_reached`) mean nothing
        # before the step has started.
        name = re.split(r"\s|[<>=!]", self.signal.strip(), maxsplit=1)[0]
        if name not in CHECK_SIGNALS:
            known = ", ".join(sorted(CHECK_SIGNALS))
            raise ValueError(f"`only_if` cannot check {name!r} (it can: {known})")
        return self


class AskCheck(Strict):
    """Run the step only if the model the behavior opted into answers yes (or no) to a
    question about the current frame (ADR-0012). Needs the `vlm:` opt-in like any frame that
    leaves the runtime (§7)."""

    ask: Text
    expect: Literal["yes", "no"] = "yes"


Check = SignalCheck | AskCheck


class PerceiveStep(Strict):
    perceive: str = Field(
        pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
        description="Perception query, e.g. person.nearest",
    )
    question: Text | None = None  # what the VLM is asked, in the user's own words
    on_none: OnNone | None = None
    only_if: Check | None = None

    @property
    def uses_vlm(self) -> bool:
        return self.perceive.startswith(VLM_QUERY_PREFIX)

    @model_validator(mode="after")
    def _known_query(self) -> PerceiveStep:
        if self.perceive not in PERCEIVE_QUERIES:
            known = ", ".join(sorted(PERCEIVE_QUERIES))
            raise ValueError(f"unknown perception query {self.perceive!r} (known: {known})")
        if self.uses_vlm and self.question is None:
            raise ValueError(f"{self.perceive} needs a `question` — what should it look for?")
        if not self.uses_vlm and self.question is not None:
            raise ValueError(f"{self.perceive} answers on its own; it takes no `question`")
        return self


class SkillStep(Strict):
    skill: Identifier
    with_: dict[str, Scalar] = Field(default_factory=dict, alias="with")
    until: Until | None = None
    only_if: Check | None = None


class WaitStep(Strict):
    wait: DurationStr
    only_if: Check | None = None


Step = PerceiveStep | SkillStep | WaitStep


def step_uses_vlm(step: Step) -> bool:
    """Does this step send a frame to a model — to find something, or to ask about it?"""
    if isinstance(step.only_if, AskCheck):
        return True
    return isinstance(step, PerceiveStep) and step.uses_vlm


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

    @model_validator(mode="after")
    def _vlm_steps_need_opt_in(self) -> BehaviorPack:
        """§7: a frame only ever leaves the runtime for a behavior that says so, by name."""
        if self.vlm is None and any(step_uses_vlm(s) for s in self.steps):
            raise ValueError(
                "a step asks a VLM, so the behavior needs a `vlm:` opt-in naming the provider"
            )
        return self

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
