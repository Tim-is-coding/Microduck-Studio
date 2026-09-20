# Studio design notes

Subject: a studio where someone without a terminal composes what a small yellow duck robot
does, then watches it happen. Audience: duck owners, makers, families, educators; German
first. Primary job: build a sequence → run it → see the duck react. Not a dashboard, not an IDE.

## Direction (2026-09-20)

One vertical rail is the memorable thing. A behavior reads top-down like a route: the
trigger is where it starts, steps are stations, side branches hang off a station as notes,
the running station glows duck-yellow. Everything else stays quiet.

Two panes, not three: left the route (Ablauf), right the stage (Live: what the duck sees and
does, and the stop). Building blocks are not a permanent column; they appear when you add a
step. Viewing and editing are the same cards; "Bearbeiten" only turns controls on.

## Tokens

- Paper `#FFFFFF`, app background `#EEF1F2` (cool grey, not cream), ink `#151A1E`,
  muted `#5B6670`, line `#D9DEE1`.
- Duck yellow `#F5B700` — running step, primary action, current tab. Spent only there.
- Pond teal `#155E63` — the Live pane's frame, camera surround, headings there.
- Signal red `#C8102E` — Notstopp and errors only.
- Type: Bricolage Grotesque for names and step titles (600/700), DM Sans for everything
  else (400/500). Scale 13 · 14 · 16 · 20 · 28. Sentence case, no all-caps labels.
- Radius: 12 for cards, 8 for controls, 999 for the rail nodes. One shadow, only on the
  running card.

## Writing

Buttons say what happens: "Starten", "Anhalten", "Ablauf speichern", "Speichern und
starten". Status is a sentence, not chips: "Die Ente steht. Person 2,0 m voraus, leicht
links." Empty states invite: "Noch keine Schritte. Füge den ersten hinzu."

## Tried / rejected

- Three columns with a permanent Bausteine list: dead space, nothing to do there.
- Separate editor layout: two renderings of the same thing drifted apart.
- Cream background + mustard accent + uppercase eyebrows: the generated-page default.
