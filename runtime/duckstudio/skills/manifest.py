"""Skill manifest schema (`duckstudio.skill/v0`, CLAUDE.md §6.1) and YAML loader.

One file, two views: `ui` is what the Studio renders as a card for non-technical users;
everything else is what the runtime needs to run and gate the underlying policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..common import ConditionStr, Identifier, InterruptStr, Strict, Text
from ..yamlio import load_yaml

SKILL_SCHEMA_ID = "duckstudio.skill/v0"


class ParamSpec(Strict):
    """A runtime parameter of the underlying intent; `min`/`max` are the clamp bounds."""

    type: Literal["float", "int", "bool", "string"] = "float"
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    default: float | int | bool | str | None = None

    @model_validator(mode="after")
    def _bounds(self) -> ParamSpec:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must be <= max")
        return self


class Source(Strict):
    kind: Literal["builtin", "hub"]
    policy: str | None = None  # builtin: upstream policy name
    repo: str | None = None  # hub: <user>/<repo>
    file: str | None = None  # hub: path inside the repo
    version: int | str | None = None

    @model_validator(mode="after")
    def _kind_fields(self) -> Source:
        if self.kind == "builtin" and not self.policy:
            raise ValueError("builtin source needs `policy`")
        if self.kind == "hub" and not self.repo:
            raise ValueError("hub source needs `repo`")
        return self


class ChoiceControl(Strict):
    """A few named options (slow/easy/brisk) that map onto numeric param values."""

    control: Literal["choice"]
    options: list[str] = Field(min_length=2)
    maps_to: str | None = None
    values: list[float] | None = None
    default: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> ChoiceControl:
        if self.values is not None and len(self.values) != len(self.options):
            raise ValueError("`values` must have one entry per option")
        if (self.values is None) != (self.maps_to is None):
            raise ValueError("`maps_to` and `values` go together")
        if self.default is not None and self.default not in self.options:
            raise ValueError("default must be one of the options")
        return self


class SelectControl(Strict):
    """Symbolic options interpreted by the executor (toward_person, straight, ...)."""

    control: Literal["select"]
    options: list[str] = Field(min_length=1)
    default: str | None = None

    @model_validator(mode="after")
    def _default(self) -> SelectControl:
        if self.default is not None and self.default not in self.options:
            raise ValueError("default must be one of the options")
        return self


class RangeControl(Strict):
    control: Literal["range"]
    min: float
    max: float
    default: float | None = None
    step: float | None = None
    unit: str | None = None
    maps_to: str | None = None

    @model_validator(mode="after")
    def _bounds(self) -> RangeControl:
        if self.min >= self.max:
            raise ValueError("min must be < max")
        if self.default is not None and not (self.min <= self.default <= self.max):
            raise ValueError("default must lie within [min, max]")
        return self


class ToggleControl(Strict):
    control: Literal["toggle"]
    default: bool = False
    maps_to: str | None = None


UiControl = Annotated[
    ChoiceControl | SelectControl | RangeControl | ToggleControl,
    Field(discriminator="control"),
]


class SkillManifest(Strict):
    schema_: Literal["duckstudio.skill/v0"] = Field(alias="schema")
    id: Identifier
    name: Text
    summary: Text | None = None
    source: Source
    intent: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$",
        description="JSON-RPC intent on robotd, e.g. robot.move. Exclusive with `behavior`.",
    )
    behavior: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Named upstream behavior (sit, stand, getup, ...). Exclusive with `intent`.",
    )
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    ui: dict[str, UiControl] = Field(default_factory=dict)
    preconditions: list[ConditionStr] = Field(default_factory=list)
    terminates_on: list[ConditionStr] = Field(default_factory=list)
    interrupts: list[InterruptStr] = Field(default_factory=list)
    rate_hz: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _intent_xor_behavior(self) -> SkillManifest:
        if (self.intent is None) == (self.behavior is None):
            raise ValueError("exactly one of `intent` or `behavior` is required")
        if self.behavior is not None and self.params:
            raise ValueError("named behaviors take no params (§6.3)")
        return self

    @model_validator(mode="after")
    def _ui_maps_to_known_params(self) -> SkillManifest:
        for key, control in self.ui.items():
            target = getattr(control, "maps_to", None)
            if target is not None and target not in self.params:
                raise ValueError(f"ui.{key}.maps_to references unknown param {target!r}")
        return self

    @property
    def is_movement(self) -> bool:
        """Movement intents are the ones the safety layer clamps and gates hardest."""
        return self.intent is not None and any(
            spec.unit in ("m/s", "rad/s") for spec in self.params.values()
        )


def load_skill_manifest(path: Path) -> SkillManifest:
    raw = load_yaml(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    try:
        return SkillManifest.model_validate(raw)
    except ValueError as e:  # pydantic.ValidationError is a ValueError
        raise ValueError(f"{path}: {e}") from e
