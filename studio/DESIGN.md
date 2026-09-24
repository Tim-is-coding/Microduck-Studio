# Studio design notes

Subject: a studio where someone without a terminal composes what a small yellow duck robot
does, then watches it happen. Audience: duck owners, makers, families, educators; German
first, English beside it. Primary job: build a sequence → run it → see the duck react. Not a
dashboard, not an IDE.

## Direction „Stille“ (2026-09-25; reference: Claude Design system
https://claude.ai/artifact/JYhoevE5GeEu1JxM3K1KV8)

Calm and exact, almost monochrome. Two white sheets on a cool grey ground — left the route
(Ablauf), right the stage (Live: camera, one sentence, three figures, the Notstopp, the log).
Inside a sheet there are no boxes: rows separated by hairlines, a number column on the left
(Start · 1 · 2 · 3 · Immer), settings as a small label over its value. The memorable thing is
the one row that runs: a 3 px duck-yellow bar at the sheet's edge, a bigger title and a dot
with the word „läuft“. Nothing else is yellow.

The first pass (Bricolage + DM Sans, teal Live block, round yellow nodes on a rail, pill
buttons) read as playful and „wie ein MVP“; this one trades that for restraint: one family,
small radii (inputs 6, buttons 8, camera/menus 10, sheets 14), ink as the primary action.

## Tokens (`src/styles.css`, light and dark)

- Ground `--bg #f4f5f5`, sheets `--surface #fff`, wells `--surface-2`, hairlines `--line`,
  input borders `--line-mid`, controls that must be found `--line-strong` (3.4:1).
- Ink `--ink #1a1c1e`, body `--ink-2`, labels `--muted #61666b` (5.8:1). The primary button is
  ink with white text (`--action`, `--on-action`); links are ink, underlined.
- Duck yellow `--accent #f2b705`: the running dot and bar only. Never text, never under text.
- Red `--danger-solid #d1242f`: the Notstopp, and the dot that says a picture leaves this
  computer. `--danger` is the readable red for error text.
- Type: Geist (bundled via fontsource, no font CDN) 400/500/600, Geist Mono for file names.
  Scale 12 · 13 · 14.5 · 16 · 18/20 (names, the running step) · 26 (page titles). Sentence
  case, no all-caps, no emoji.

## Writing

Buttons say what happens: "Start", "Anhalten", "Speichern", "Speichern & Starten". Status is
a sentence, not chips: "Die Ente steht. Person 2,0 m genau voraus." Empty states invite:
"Noch keine Schritte. Füge unten den ersten hinzu."

## Tried / rejected

- Three columns with a permanent Bausteine list: dead space, nothing to do there.
- Separate editor layout: two renderings of the same thing drifted apart.
- Cream background + mustard accent + uppercase eyebrows: the generated-page default.
- Yellow primary buttons, a teal Live block, round numbered nodes on a line (2026-09-21 to
  09-24): friendly, but read as childish next to a robot you trust with a Notstopp.
- Two sessions redesigning the same surface in parallel (2026-09-20): `CLAUDE.md` §10.
