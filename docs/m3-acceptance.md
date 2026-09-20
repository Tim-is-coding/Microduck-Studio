# M3 acceptance: a first behavior in under two minutes

`CLAUDE.md` §8 gives M3 a number, not an opinion: *"Erstes Behavior aus leerem Studio in
unter zwei Minuten (Nutzertest)."* This is the measurement, what it exposed and what it
changed. Re-run it whenever the first screen or the editor changes.

## How it is measured

`scripts/firstrun.mjs` drives a real browser against a real runtime with an **empty
workspace**: no behaviors on disk, only the eight builtin skill manifests. It clicks the way
a person clicks and types the name letter by letter; between steps it waits — 2.5 s where
somebody meets a new screen and has to decide, 1.2 s for a glance at something familiar.
Those pauses are the honest part of the number: without them the robot "builds" a behavior
in three seconds and the measurement means nothing.

Two paths are timed, because an empty Studio offers two:

- **A — from the empty card:** new behavior → type a name → add two blocks → Speichern & Starten.
- **B — from an example:** click a starter template → Speichern & Starten.

The clock starts when the page is requested and stops when the runtime reports the behavior
finished. Nothing is stubbed: the pack is written to disk as YAML, validated by the runtime
and run by the executor against the `mock` backend.

```bash
cd runtime && DUCKSTUDIO_BACKEND=mock DUCKSTUDIO_ROOT=/tmp/ds-firstrun uv run python -m duckstudio
cd studio && pnpm dev
node scripts/firstrun.mjs          # THINK=2500 READ=1200 by default
```

## Result (2026-09-20, mock backend, 1500×940)

| Path | Time | Interactions |
| --- | --- | --- |
| A — empty card, named "Begrüßung", Quaken + Hinsetzen | **21.3 s** | 6 |
| B — starter template "Begrüßung" | **10.4 s** | 3 |

Both well inside the two minutes, with room for a person who is slower than the pauses
above. Path A in detail: 1.8 s Studio open · 5.2 s new behavior · 10.0 s name typed ·
13.7 s first block · 16.2 s second block · 21.1 s saved, started, finished.

## What the run exposed, and what changed

The number was never the interesting part — watching the screens was.

1. **The name field arrived prefilled with "Neuer Ablauf".** A script `fill()`s over it and
   never notices; a person has to select the text and delete it before typing. A new draft
   is now born nameless (`newBehavior()`), so the placeholder shows and typing just works.
2. **The id appeared before the name did.** "Kennung: neuer-ablauf" was on screen before
   anybody had named anything. `slugify("")` now returns no id at all, and the editor shows
   the hint "Gib dem Ablauf einen Namen." in that line until there is one.
3. **An unfinished draft was reported as broken.** The live validation returned `id: String
   should match pattern …` and `name.de: String should have at least 1 character` — English
   schema talk, about fields the user had not reached yet. Those complaints are suppressed
   while the name is empty, exactly as `steps: at least 1 item` already was, and Speichern
   stays out of reach until there is a name and a step.
4. **The empty Studio taught nothing.** One dashed card and "leere Schrittliste" is a poor
   first lesson. While the list is empty it now also offers starter templates
   (`studio/src/editor/templates.ts`): complete, runnable packs that open as a *draft* —
   nothing is written until you press Speichern. They are offered only if every skill they
   name is in the registry, and each skill card is filled from its manifest's defaults.

## What this does not measure

- A person reading the screen for the first time. The pauses are a stand-in; a real user
  test with someone who has never seen the Studio is still owed (`CLAUDE.md` §8, M3).
- Anything on hardware. The duck here is the `mock` backend, so "finished" means the
  executor ran the steps, not that a duck quacked (M4).
- The second behavior. This measures the first one, which is the one that decides whether
  somebody stays.
