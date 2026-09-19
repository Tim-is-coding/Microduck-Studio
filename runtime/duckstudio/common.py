"""Shared value types: localized text, identifiers, condition/duration strings.

Conditions, interrupts and durations are stored as short strings in YAML so that
non-technical users can read them ("battery > 0.15", "fallen -> getup -> resume", "10m").
The regexes below validate them at load time; `Condition.parse` / `Interrupt.parse` /
`parse_duration` turn them into structured values for the executor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Base for every schema model: unknown keys are errors, not silently dropped."""

    model_config = ConfigDict(extra="forbid")


class Text(Strict):
    """Human-readable text. German first (CLAUDE.md §3.7); `en` optional until it lands."""

    de: str = Field(min_length=1)
    en: str | None = None

    def get(self, lang: str = "de") -> str:
        return getattr(self, lang, None) or self.de


class Phrases(Strict):
    """Localized list of phrases, e.g. trigger words."""

    de: list[str] = Field(min_length=1)
    en: list[str] | None = None


ID_PATTERN = r"^[a-z][a-z0-9_-]*$"
Identifier = Annotated[str, Field(pattern=ID_PATTERN, max_length=64)]

# "standing" | "battery > 0.15" | "tof_distance < 0.25"
CONDITION_PATTERN = r"^[a-z][a-z0-9_.]*(\s*(<=|>=|==|!=|<|>)\s*-?\d+(\.\d+)?)?$"
ConditionStr = Annotated[
    str,
    Field(
        pattern=CONDITION_PATTERN,
        description="A signal name, optionally compared to a number: 'battery > 0.15'.",
    ),
]

# "fallen -> getup -> resume"
INTERRUPT_PATTERN = r"^[a-z][a-z0-9_.]*(\s*->\s*[a-z][a-z0-9_-]*)+$"
InterruptStr = Annotated[
    str,
    Field(
        pattern=INTERRUPT_PATTERN,
        description="Signal followed by actions: 'fallen -> getup -> resume'.",
    ),
]

# "500ms" | "10s" | "10m" | "1h"
DURATION_PATTERN = r"^\d+(\.\d+)?(ms|s|m|h)$"
DurationStr = Annotated[
    str, Field(pattern=DURATION_PATTERN, description="Duration such as '5s' or '10m'.")
]

Op = Literal["<", "<=", ">", ">=", "==", "!="]

_CONDITION_RE = re.compile(r"^([a-z][a-z0-9_.]*)(?:\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?))?$")
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$")
_DURATION_FACTORS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


@dataclass(frozen=True)
class Condition:
    """A parsed condition string: a signal, optionally compared against a number."""

    signal: str
    op: Op | None = None
    value: float | None = None

    @classmethod
    def parse(cls, text: str) -> Condition:
        m = _CONDITION_RE.match(text.strip())
        if not m:
            raise ValueError(f"invalid condition: {text!r}")
        signal, op, value = m.groups()
        if op is None:
            return cls(signal=signal)
        return cls(signal=signal, op=op, value=float(value))  # type: ignore[arg-type]

    def __str__(self) -> str:
        if self.op is None:
            return self.signal
        return f"{self.signal} {self.op} {self.value:g}"


@dataclass(frozen=True)
class Interrupt:
    """A parsed interrupt string: on `on`, run `do` in order ('resume' continues the step)."""

    on: str
    do: tuple[str, ...]

    @classmethod
    def parse(cls, text: str) -> Interrupt:
        parts = [p.strip() for p in text.split("->")]
        if len(parts) < 2 or not all(parts):
            raise ValueError(f"invalid interrupt: {text!r}")
        return cls(on=parts[0], do=tuple(parts[1:]))


def parse_duration(text: str) -> float:
    """'10m' -> 600.0 seconds."""
    m = _DURATION_RE.match(text.strip())
    if not m:
        raise ValueError(f"invalid duration: {text!r}")
    return float(m.group(1)) * _DURATION_FACTORS[m.group(2)]
