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
  - perceive: person.nearest                # PerceiveStep, answered locally
    on_none: { do: look_around, seconds: 5, then: retry }
  - perceive: vlm.target                    # answered by the model the behavior opted into
    question: { de: "Wo ist der rote Ball?" }
  - skill: walk                             # SkillStep
    with: { direction: toward_person, tempo: easy, distance: 60 }
    until: { any: [speech: { de: ["Stopp"] }, elapsed: 10m] }
  - wait: 2s                                # WaitStep
  - skill: quack
    only_if: { signal: person_found }       # any step: skipped unless it holds (ADR-0012)
  - skill: walk
    with: { direction: toward_target, distance: 40 }
    only_if: { ask: { de: "Liegt der Ball auf dem Boden?" }, expect: yes }   # needs `vlm:`
always:
  - on: fallen
    do: [getup, resume]
vlm: { provider: anthropic }                # optional opt-in, shown in the Studio
```

- `perceive` takes a known query: `person.nearest` (local detector, every frame) or
  `vlm.target` (ADR-0004, 0.5 Hz). A `vlm.*` query needs a `question` and a `vlm:` opt-in;
  `person.*` takes no question. The schema refuses anything else, so a pack that cannot run
  cannot be saved.
- `with` keys must be `ui` controls (or params) of the skill; values are checked against the
  control's options/range by `validate_against_registry`.
- `until` has exactly one of `any` / `all`, each a list of `speech`, `elapsed` or `signal`
  conditions.
- `only_if` (ADR-0012) decides whether a step runs at all: `{signal: …}` with the
  condition language, limited to what the duck reports right now (`person_found`,
  `tof_distance`, `battery`, `standing`, …; not `timeout`/`elapsed`/`target_reached`), or
  `{ask: {de, en}, expect: yes|no}`, a yes/no question to the model, which needs the `vlm:`
  opt-in like `vlm.target`. No means the step is skipped with a sentence in the log; there
  is no `else`.
- `always.do` and `on_none.do` list skill ids or the reserved words `resume`, `abort`,
  `stop`, `retry`, `continue`.
- `vlm` is the per-behavior opt-in required by `CLAUDE.md` §7; without it no frame leaves
  the runtime except to the user's Studio. The named provider is what the runtime checks
  against before it sends anything (`docs/concepts/perception.md`).

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

## Copies and files

Hub sharing waits for hardware (`CLAUDE.md` §8, M4), but a behavior still has to be able to
leave the machine it was built on, so the overview can copy one and write it to a file, and
load one back (`studio/src/editor/transfer.ts`):

- **Kopie anlegen** suffixes the name in every language the pack carries — "Folge mir
  (Kopie)", "Follow me (copy)" — and takes the first free id (`follow-me-copy`,
  `follow-me-copy-2`, …). Ids stay English, names follow the content (§3.7).
- **Als Datei speichern** downloads exactly the YAML the runtime writes (`tidy()` then
  dump), named `<id>.behavior.yaml`. It is a local download; nothing is uploaded anywhere.
- **Aus Datei laden** parses the file, checks it against the pack schema and gives it a free
  id if that id is taken — the draft then says so. A file is data, never an instruction: it
  becomes a *draft*, so it goes through the editor, the live validation and Speichern like
  anything else, and an unreadable file gets a sentence saying what is wrong with it rather
  than a stack trace.

A copy and an import both stop short of the disk; nothing is written until somebody presses
Speichern.
