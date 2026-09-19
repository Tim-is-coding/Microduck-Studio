# ADR-0003: Behavior packs stay YAML files; the Studio edits them through the runtime

- Status: accepted
- Date: 2026-09-19

## Context

M3 (`CLAUDE.md` §8) makes behaviors editable without code: change → save → run. Where does
an edited behavior live? The Studio is a browser app, the runtime runs on a laptop next to
the duck, packs are `behaviors/*.behavior.yaml` in the repo (`CLAUDE.md` §5, §6.2), and
`CLAUDE.md` §3.1 wants the developer view beside the visual one, never in front of it.

## Decision

1. The file stays the source of truth. `PUT /api/behaviors/{id}` validates the pack (schema,
   then against the skill registry), writes `behaviors/<id>.behavior.yaml` atomically and
   reloads it into the running catalog; `DELETE` removes the file. A behavior that is
   running cannot be saved over or deleted (409).
2. The runtime writes YAML the way the loader reads it: block style, lists indented under
   their key, bare `on:` keys (YAML 1.2 booleans), defaults and empty fields left out — so a
   saved file reads like a hand-written one and a hand-written one survives a round trip.
3. `POST /api/behaviors/validate` gives the Studio the same problem list without saving, so
   cards can show what is wrong while editing. Saving needs a schema-valid pack; registry
   problems (unknown skill, bad option) are allowed in a saved draft but block "Start".
4. `GET /api/behaviors/{id}/yaml` is the developer view: the Studio shows it in a collapsed
   panel under the cards. Nobody has to open it.

## Alternatives considered

- **Browser storage (localStorage/IndexedDB).** Rejected: the pack must reach the runtime to
  run and must be shareable (Hub, M4); a browser is the wrong owner for a file.
- **A database in the runtime.** Rejected for v1: it hides the YAML the handover defines as
  the exchange format, and a directory of files is what git, the Hub and a text editor
  already understand.
- **Editing the YAML text in the Studio.** Rejected as the primary path (§3.1); kept as the
  read-only developer view.

## Consequences

- `behaviors/` in the repo changes when someone saves from the Studio. That is intended: the
  repo is the workspace. Anyone who wants a scratch space sets `DUCKSTUDIO_ROOT`.
- Comments in hand-written YAML are lost on the first save from the Studio.
- The zod mirror in the Studio must stay aligned with pydantic; the existing schema tests
  guard that.
