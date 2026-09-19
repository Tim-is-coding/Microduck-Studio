# Behavior pack (`duckstudio.behavior/v0`)

A behavior is a vertical list of steps with side branches (`CLAUDE.md` §3.2). No free
graphs: the shape is trigger → steps → always-rules, and every branch is attached to a step.

- Files: `behaviors/<id>.behavior.yaml`.
- Schema: `runtime/duckstudio/behaviors/schema.py`, exported as
  `docs/schemas/behavior.v0.schema.json`, mirrored by zod in `studio/src/schemas/`.
- Spec example: `CLAUDE.md` §6.2 = `behaviors/follow-me.behavior.yaml` (kept verbatim; the
  loader must accept the spec as written, flow-style lists included).

## Shape

```yaml
schema: duckstudio.behavior/v0
id: follow-me
name: { de: Folge mir }
trigger: { kind: speech, phrases: { de: ["Folge mir"] } }   # or { kind: manual }
steps:
  - perceive: person.nearest                # PerceiveStep
    on_none: { do: look_around, seconds: 5, then: retry }
  - skill: walk                             # SkillStep
    with: { direction: toward_person, tempo: easy, distance: 60 }
    until: { any: [speech: { de: ["Stopp"] }, elapsed: 10m] }
  - wait: 2s                                # WaitStep
always:
  - on: fallen
    do: [getup, resume]
vlm: { provider: anthropic }                # optional opt-in, shown in the Studio
```

- `with` keys must be `ui` controls (or params) of the skill; values are checked against the
  control's options/range by `validate_against_registry`.
- `until` has exactly one of `any` / `all`, each a list of `speech`, `elapsed` or `signal`
  conditions.
- `always.do` and `on_none.do` list skill ids or the reserved words `resume`, `abort`,
  `stop`, `retry`, `continue`.
- `vlm` is the per-behavior opt-in required by `CLAUDE.md` §7; without it no frame leaves
  the runtime except to the user's Studio.

## YAML note

The runtime reads YAML with 1.2 booleans (`duckstudio/yamlio.py`): `on`, `off`, `yes`, `no`
stay strings, so `on: fallen` works as written. Only `true`/`false` are booleans. The
Studio's `yaml` package behaves the same way.

## Editing

The Studio edits packs through the runtime (ADR-0003): `PUT /api/behaviors/{id}` saves,
`DELETE` removes, `POST /api/behaviors/validate` returns the problem list while editing and
`GET /api/behaviors/{id}/yaml` is the developer view. The runtime writes YAML the way it
reads it (block style, bare `on:`, defaults omitted), so hand-written and saved files look
alike. Card controls come from the skill manifests' `ui`; nothing in the editor knows YAML.
