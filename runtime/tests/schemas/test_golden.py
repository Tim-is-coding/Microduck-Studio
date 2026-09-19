"""docs/schemas/*.json are golden files: regenerate with `python -m duckstudio.schemas_export`."""

from __future__ import annotations

from pathlib import Path

from duckstudio.schemas_export import FILES, render


def test_exported_json_schemas_are_current(root: Path) -> None:
    for filename, model in FILES.items():
        target = root / "docs" / "schemas" / filename
        assert target.exists(), f"missing {target}; run python -m duckstudio.schemas_export"
        assert target.read_text(encoding="utf-8") == render(model), f"{filename} is stale"
