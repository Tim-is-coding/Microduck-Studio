"""YAML loader for behavior packs plus cross-validation against a skill registry."""

from __future__ import annotations

from pathlib import Path

from ..skills.registry import SkillRegistry
from ..yamlio import load_yaml
from .schema import RESERVED_ACTIONS, BehaviorPack, PerceiveStep, SkillStep


def load_behavior_pack(path: Path) -> BehaviorPack:
    raw = load_yaml(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    try:
        return BehaviorPack.model_validate(raw)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from e


def load_behavior_packs(directory: Path) -> dict[str, BehaviorPack]:
    packs: dict[str, BehaviorPack] = {}
    for p in sorted(Path(directory).glob("*.behavior.yaml")):
        pack = load_behavior_pack(p)
        if pack.id in packs:
            raise ValueError(f"{p}: duplicate behavior id {pack.id!r}")
        packs[pack.id] = pack
    return packs


def validate_against_registry(pack: BehaviorPack, registry: SkillRegistry) -> list[str]:
    """Return human-readable problems (empty list = the pack can run with this registry)."""
    problems: list[str] = []
    for i, step in enumerate(pack.steps, start=1):
        if isinstance(step, SkillStep):
            if step.skill not in registry:
                problems.append(f"step {i}: unknown skill {step.skill!r}")
                continue
            try:
                registry.resolve_ui(step.skill, step.with_)
            except ValueError as e:
                problems.append(f"step {i}: {e}")
        elif isinstance(step, PerceiveStep) and step.on_none:
            if step.on_none.do not in registry:
                problems.append(f"step {i}: on_none.do: unknown skill {step.on_none.do!r}")
    for j, rule in enumerate(pack.always, start=1):
        for action in rule.do:
            if action not in RESERVED_ACTIONS and action not in registry:
                problems.append(f"always[{j}] ({rule.on}): unknown skill {action!r}")
    return problems
