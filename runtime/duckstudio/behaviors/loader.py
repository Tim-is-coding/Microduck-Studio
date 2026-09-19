"""YAML loader for behavior packs plus cross-validation against a skill registry."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from ..skills.registry import SkillRegistry
from ..yamlio import dump_yaml, load_yaml
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


def pack_to_yaml(pack: BehaviorPack) -> str:
    """The pack as the Studio saves it: block style, defaults and empties left out."""
    data = pack.model_dump(by_alias=True, mode="json", exclude_none=True, exclude_defaults=True)
    return dump_yaml(data)


def behavior_path(directory: Path, behavior_id: str) -> Path:
    return Path(directory) / f"{behavior_id}.behavior.yaml"


def save_behavior_pack(pack: BehaviorPack, directory: Path) -> Path:
    """Write `<id>.behavior.yaml` atomically (temp file + rename) and return its path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = behavior_path(directory, pack.id)
    fd, tmp = tempfile.mkstemp(prefix=f".{pack.id}.", suffix=".yaml", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(pack_to_yaml(pack))
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return target


def delete_behavior_pack(behavior_id: str, directory: Path) -> bool:
    target = behavior_path(directory, behavior_id)
    if not target.exists():
        return False
    target.unlink()
    return True
