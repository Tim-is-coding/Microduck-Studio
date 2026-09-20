# Skill manifest (`duckstudio.skill/v0`)

A manifest turns a policy (upstream builtin or Hugging Face Hub) into a building block that
both the Studio and the executor understand. One YAML file, two views: `ui` for
non-technical users, everything else for the runtime.

- Files: `skills/<id>.skill.yaml`; the file name must equal `id`.
- Schema: pydantic `runtime/duckstudio/skills/manifest.py`, exported as
  `docs/schemas/skill.v0.schema.json` (golden file, regenerate with
  `uv run python -m duckstudio.schemas_export`), mirrored by zod in `studio/src/schemas/`.
- Spec example: `CLAUDE.md` §6.1, real file: `skills/walk.skill.yaml`.

## Fields

| Field | Meaning |
| --- | --- |
| `schema` | Always `duckstudio.skill/v0`. |
| `id` | Lowercase identifier; what behavior packs reference. |
| `name`, `summary` | Localized text, `de` required, `en` optional. |
| `source` | `builtin` (upstream policy name) or `hub` (`repo`, `file`, `version`). |
| `intent` **xor** `behavior` | Either a `robot.*` JSON-RPC intent with `params`, or a named upstream behavior (`sit`, `stand`, `getup`, `pickup`, `kick`, `quack`) which takes no params. |
| `params` | Runtime parameters with `min`/`max`: these are the **clamp bounds** the IntentGate enforces. |
| `ui` | Controls the Studio renders: `choice` (named options mapping to numeric `values`), `select` (symbolic options the executor interprets), `range`, `toggle`. `maps_to` must name a param. |
| `preconditions` | Condition strings that must all be true before the gate sends anything. |
| `terminates_on` | Signals that end the skill. |
| `interrupts` | `signal -> action -> action`, e.g. `fallen -> getup -> resume`. |
| `rate_hz` | Executor tick rate for this skill (1–50). Not the 50 Hz loop in `robotd`. |

## Condition strings

`signal` or `signal <op> number`, e.g. `standing`, `battery > 0.15`, `tof_distance < 0.25`.
Known signals (`runtime/duckstudio/executor/conditions.py`): `battery`, `motor_hot`,
`standing`, `fallen`, `sitting`, `moving`, `tof_distance`, `person_distance`, `elapsed`.
Unknown signals evaluate to "unknown", which never passes a precondition.

## UI → params

`SkillRegistry.resolve_ui("walk", {"tempo": "easy", "direction": "toward_person"})` returns
`({"vx": 0.08}, {"direction": "toward_person"})`: the first dict goes to the intent (after
clamping), the second stays with the executor. Developers may also pass params directly
(`{"vx": 0.1}`); the Studio never does.

## Where a block comes from

`source.kind` is `builtin` (a policy the duck ships, named in `source.policy`) or `hub` (a
community policy, `source.repo` + `source.file` + `source.version` = the commit we imported).

A `hub` block is written by the Studio's Hub search (ADR-0005), and it only ever borrows
words from the Hub: name, summary, provenance. Everything that decides what the duck does —
`intent`/`behavior`, `params`, `ui`, `preconditions`, `terminates_on`, `rate_hz` — is copied
from the builtin block a person said it stands in for. Limits move in one direction only: a
repo that states its own velocity ranges can narrow ours, never widen them (§7).

Only `hub` blocks can be deleted through the API; the builtins are the repo's own files.

## Upstream verification

`intent` names and behavior names are **unverified** until `docs/upstream-notes.md` lists
them with a commit hash. `duckstudio/upstream.py` is the single source for those names.
