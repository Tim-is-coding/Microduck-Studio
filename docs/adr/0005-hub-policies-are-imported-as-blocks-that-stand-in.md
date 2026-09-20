# ADR-0005: A Hub policy is imported as a building block that stands in for a builtin one

- Status: accepted
- Date: 2026-09-20

## Context

`CLAUDE.md` §5 puts "Bausteine-Panel, Hub-Suche" in the Studio, and §2 points at the Hub as
where community policies live. Until now the eight building blocks were hand-written files
and the Studio had no way to gain a ninth.

What is actually on the Hub (verified 2026-09-20 against the live API, recorded in
`docs/upstream-notes.md` §Hugging Face Hub): 25 repos tagged `microduck-policy`, each with a
`policy.onnx`, most with a `manifest.json` of their own. Those manifests are a community
convention, not a standard: `schema_version` runs 1…5, `model_api` 1…2, and the `command`
block is a sentence in one repo, a list of free-text lines in the next, and missing in a
third. **One repo of twenty-five states its velocity ranges in a form a machine can read.**

Two facts decide the design. A policy on the Hub is not something our runtime can run: it is
loaded onto a duck into one of `robotd`'s fixed slots (`robot.loadPolicy {slot, path}`,
upstream-notes §robotd), and the slot is what decides how it is driven. And the free text
around it cannot be trusted to say which slot that is — "flamingo-cycle" describes its
`twist` as a flag and a side, which as walking speeds would send a duck into a wall.

## Decision

1. **Search is browsing, and it is honest about what it knows.** `GET /api/hub/policies`
   returns what the Hub's model list gives: name, author, downloads, likes, tags, link. The
   repo's own `manifest.json` is read only when someone moves to import a policy
   (`GET /api/hub/policy?repo=…`), and what it says — description, `status`,
   `hardware_tested`, its command description — is shown at that moment, before the import.
2. **The person picks the slot; the Studio guesses.** `POST /api/hub/import {repo, slot}`
   writes a manifest that means "this policy, where `slot` drives". `slot_guess` comes from
   the repo's words and is only a pre-selection.
3. **Behaviour comes from the builtin, words come from the Hub.** Intent (or named
   behavior), params, `ui`, preconditions, `terminates_on` and `rate_hz` are copied from the
   builtin skill the person picked — those we verified against upstream. From the Hub come
   `name`, `summary` and `source: {kind: hub, repo, file, version: <commit sha>}`.
4. **Limits are never widened.** A policy's own twist ranges are read only when they are
   machine-readable (`±0.15 m/s, ±0.10 m/s, ±0.50 rad/s`) and then applied as
   `min(ours, theirs)` (§7: the manifest's `params` are the only clamps a movement intent
   has). Prose gets our bounds, silently and deliberately.
5. **Hub text is data** (§10): shown, never followed. Every string is flattened to one line,
   stripped of markup and capped; ids come from the repo name, slugified and de-duplicated;
   nothing from a repo chooses a slot, a limit or a file path.
6. **What was imported can be removed again.** `DELETE /api/skills/{id}` deletes a
   `kind: hub` manifest — never a builtin (409), never one a behavior still uses (409).
7. **Downloading and installing the policy is M4.** We record which policy a behavior means;
   putting it on a duck (`policy.fetch` on `updaterd`, then `robot.loadPolicy`) happens when
   there is a duck, with those methods verified against upstream first.

## Alternatives considered

- **Parse the manifests and derive the skill automatically.** Rejected on the evidence: one
  repo in twenty-five is machine-readable enough, and a wrong guess is a duck walking into
  something.
- **Import only policies we fully understand** (the one with ranges). Rejected: it would make
  the panel useless, and browsing provenance is valuable on its own.
- **Download the ONNX into the repo.** Rejected: v1 is a client of the upstream API (§3.5),
  the duck fetches its own policies, and a binary in the repo is a supply-chain surface we do
  not need.
- **Let a repo define its own card (`ui`) or limits.** Rejected: that is exactly the part
  §7 says is ours.

## Consequences

- An imported block behaves like the builtin it stands in for until a duck actually has the
  policy loaded. The Studio says so: the card carries the repo and the "not hardware-tested"
  line when the repo admits it.
- `skills/` changes when someone imports — like `behaviors/`, the repo is the workspace
  (ADR-0003).
- The runtime now talks to huggingface.co. Only search terms leave the machine, and only when
  someone searches; no token, no upload, no download.
- If the community's manifests converge on a real standard (`model_api` 3?), the conversion
  can read more and guess less — the place to change is `runtime/duckstudio/hub.py`.
