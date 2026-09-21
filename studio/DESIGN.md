# Studio design notes

Subject: a studio where someone without a terminal composes what a small yellow duck robot
does, then watches it happen. Audience: duck owners, makers, families, educators; German
first, English beside it. Primary job: build a sequence → run it → see the duck react. Not a
dashboard, not an IDE.

## Direction (decided 2026-09-21, first drafted on the `studio-design-ablauf-2026-09-20` tag)

One vertical rail is the memorable thing. A behavior reads top-down like a route: the
trigger is where it starts, steps are stations, side branches hang off a station as notes,
the running station glows duck-yellow. Everything else stays quiet.

Two panes, not three: left the route (Ablauf), right the stage (Live: what the duck sees and
does, and the stop). Building blocks are not a permanent column; they appear when you add a
step, and have their own tab for browsing and the Hub. Viewing and editing are the same
cards; "Bearbeiten" only turns the controls on.

## Tokens (`src/styles.css`, light and dark)

- Paper `--surface`, app background `--bg` (cool grey, not cream), ink, muted, line.
- Duck yellow `--accent #F5B700`: the running station, the primary action, the current tab.
  Spent only there.
- Pond teal `--stage #155E63`: the Live pane's block. `--link` is the readable teal for text
  and quiet buttons on both backgrounds.
- Signal red `--danger`: Notstopp and errors only.
- Type: Bricolage Grotesque for names and station titles (600/700), DM Sans for everything
  else. Scale 12 · 13 · 15 · 18 · 22. Sentence case, no all-caps labels.

## Writing

Buttons say what happens: "Start", "Anhalten", "Speichern", "Speichern & Starten". Status is
a sentence, not chips: "Die Ente steht. Person 2,0 m genau voraus." Empty states invite:
"Noch keine Schritte. Füge unten den ersten hinzu."

## Tried / rejected

- Three columns with a permanent Bausteine list: dead space, nothing to do there.
- Separate editor layout: two renderings of the same thing drifted apart.
- Cream background + mustard accent + uppercase eyebrows: the generated-page default.
- Two sessions redesigning the same surface in parallel (2026-09-20): `CLAUDE.md` §10.
