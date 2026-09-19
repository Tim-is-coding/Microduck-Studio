"""Skill registry: every `*.skill.yaml` in a directory, by id, plus UI→param resolution."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .manifest import ChoiceControl, RangeControl, SkillManifest, load_skill_manifest

Scalar = str | float | int | bool


class SkillNotFound(KeyError):
    pass


class SkillRegistry:
    def __init__(self, manifests: Iterable[SkillManifest] = ()) -> None:
        self._by_id: dict[str, SkillManifest] = {}
        for m in manifests:
            self.add(m)

    @classmethod
    def load(cls, directory: Path) -> SkillRegistry:
        paths = sorted(Path(directory).glob("*.skill.yaml"))
        return cls(load_skill_manifest(p) for p in paths)

    def add(self, manifest: SkillManifest) -> None:
        if manifest.id in self._by_id:
            raise ValueError(f"duplicate skill id {manifest.id!r}")
        self._by_id[manifest.id] = manifest

    def get(self, skill_id: str) -> SkillManifest:
        try:
            return self._by_id[skill_id]
        except KeyError:
            raise SkillNotFound(skill_id) from None

    def __contains__(self, skill_id: object) -> bool:
        return skill_id in self._by_id

    def __iter__(self) -> Iterator[SkillManifest]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    @property
    def ids(self) -> list[str]:
        return list(self._by_id)

    def resolve_ui(
        self, skill_id: str, chosen: Mapping[str, Scalar]
    ) -> tuple[dict[str, float], dict[str, Scalar]]:
        """Turn a step's `with:` values into (intent params, executor-level extras).

        `tempo: easy` on a choice control with `maps_to: vx` becomes `{"vx": 0.08}`; controls
        without `maps_to` (direction, distance) are returned as extras for the executor.
        Unknown keys and invalid options raise ValueError so the Studio can show them.
        """
        manifest = self.get(skill_id)
        params: dict[str, float] = {}
        extras: dict[str, Scalar] = {}
        for key, value in chosen.items():
            control = manifest.ui.get(key)
            if control is None:
                if key in manifest.params:
                    params[key] = float(value)  # direct param, developer view
                    continue
                raise ValueError(f"{skill_id}: unknown option {key!r}")
            self._check_option(skill_id, key, control, value)
            target = getattr(control, "maps_to", None)
            if isinstance(control, ChoiceControl) and control.values is not None:
                params[target] = control.values[control.options.index(str(value))]  # type: ignore[index]
            elif target is not None:
                params[target] = float(value)  # type: ignore[arg-type]
            else:
                extras[key] = value
        return params, extras

    @staticmethod
    def _check_option(skill_id: str, key: str, control: Any, value: Scalar) -> None:
        options = getattr(control, "options", None)
        if options is not None and str(value) not in options:
            raise ValueError(f"{skill_id}.{key}: {value!r} is not one of {options}")
        if isinstance(control, RangeControl):
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"{skill_id}.{key}: expected a number, got {value!r}")
            if not (control.min <= value <= control.max):
                raise ValueError(
                    f"{skill_id}.{key}: {value} outside [{control.min}, {control.max}]"
                )
