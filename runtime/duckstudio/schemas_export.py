"""Export the JSON Schemas for skill manifests and behavior packs to docs/schemas/.

`python -m duckstudio.schemas_export` writes them; `--check` fails if they are stale.
The Studio's zod schemas and the golden-file test both compare against these files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import repo_root
from .behaviors.schema import BehaviorPack
from .skills.manifest import SkillManifest

FILES = {
    "skill.v0.schema.json": SkillManifest,
    "behavior.v0.schema.json": BehaviorPack,
}


def render(model: type) -> str:
    schema = model.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def export(out_dir: Path | None = None, *, check: bool = False) -> list[str]:
    out_dir = out_dir or repo_root() / "docs" / "schemas"
    out_dir.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    for filename, model in FILES.items():
        target = out_dir / filename
        content = render(model)
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(str(target))
        else:
            target.write_text(content, encoding="utf-8")
    return stale


if __name__ == "__main__":
    if "--check" in sys.argv:
        stale = export(check=True)
        if stale:
            print("stale JSON schemas (run `python -m duckstudio.schemas_export`):")
            print("\n".join(f"  {s}" for s in stale))
            sys.exit(1)
        print("JSON schemas up to date")
    else:
        export()
        print("JSON schemas written to docs/schemas/")
