# The Studio's look

One stylesheet, no UI kit (`CLAUDE.md` §5) and no web fonts: `studio/src/styles.css` holds
tokens first, then components. Everything else reads those tokens, so a change lands
everywhere at once and dark mode is a swap of values rather than a second stylesheet.

## Tokens

| Group | Tokens | Rule of thumb |
| --- | --- | --- |
| Surfaces | `--bg`, `--surface`, `--surface-2`, `--surface-3` | page, cards, insets, wells |
| Lines | `--line`, `--line-strong` | quiet borders vs. control borders |
| Text | `--ink`, `--ink-2`, `--muted` | headline, body, labels |
| Accent | `--accent`, `--accent-hover`, `--accent-ink`, `--accent-weak`, `--accent-line` | the duck's amber: steps, the active thing, primary buttons |
| State | `--danger`, `--danger-solid`, `--danger-weak`, `--danger-line`, `--ok`, `--warn`, `--info` | `--danger` is text, `--danger-solid` is the Notstopp red and stays the same in both themes |
| Perception | `--mark-person`, `--mark-target` | the camera overlay and the chips that describe it agree by construction |
| Type | `--t-xs` … `--t-xl`, `--font`, `--mono` | 11.5 / 12.5 / 14 / 15.5 / 19 px |
| Space | `--s-1` … `--s-6` | 4 / 8 / 12 / 16 / 22 / 32 px |
| Shape | `--r-sm`, `--r-md`, `--r-lg`, `--r-pill`, `--shadow-1`, `--shadow-2`, `--ring` | |

Measurements (distances, battery, log times) use `font-variant-numeric: tabular-nums` so
they stop jittering while they update.

## Dark mode

`prefers-color-scheme` decides unless the Studio was told otherwise; the switch in the top
bar (system / hell / dunkel) writes `data-theme` on `<html>` and remembers the choice in
`localStorage` (`studio/src/theme.ts`, per browser, never in a behavior). Anything drawn in
JavaScript asks `useIsDark()` — that is how the ToF grid keeps "clear" pale on paper and
quiet at night (`live/overlay.ts`).

## Rules that keep it coherent

- **One accent.** Amber marks what is active or primary; red is reserved for danger and for
  "a picture is leaving this machine" (§7). Nothing else competes.
- **Drawn icons, no emoji** (`ui/Icon.tsx`): they inherit `currentColor` and the font size,
  so a button looks the same on every machine.
- **Every interactive element shows focus** via `:focus-visible` and the `--ring` token.
- **Variants state their own hover.** `.btn:hover:not(:disabled)` outranks `.btn.danger`, so
  each variant repeats its background in its hover rule — the Notstopp red never turns into
  white-on-white under the pointer.
- **Nothing in the live column may be squeezed** (`.live > * { flex: none }`): a flex column
  inside a scrolling panel would otherwise collapse the camera to a line as the log grows.
- **Reduced motion is honoured**: the pulsing step number stops under
  `prefers-reduced-motion`.

## Undo

Strg+Z is the first reflex after a wrong click, so the editor has it (`editor/history.ts`,
buttons in the run bar). The unit of undo is a *move*, not a keystroke: edits that follow
each other closely and leave the shape of the behavior alone — typing a name, dragging a
slider — fold into one entry, while adding, removing, moving or retyping a step always
starts a new one, so a single undo never swallows two structural changes. Inside a text
field the browser's own text undo is the better one and keeps the keys; the buttons still
undo the draft. Opening another behavior, saving or discarding clears the history.

## Empty states

An empty screen is a first lesson, so it says what to do next rather than what is missing.

- **The overview with no behaviors** keeps the dashed "Neuer Ablauf" card and adds a row of
  starter templates (`editor/templates.ts`) — complete, runnable packs that open as a draft;
  nothing is written until Speichern. The row disappears as soon as there is one behavior.
- **A new draft is nameless.** The name field shows its placeholder and the id line shows
  "Gib dem Ablauf einen Namen." until there is a name — no prefilled text to delete first,
  and no `Kennung: neuer-ablauf` before anybody named anything.
- **Unfinished is not broken.** While the name is empty or the step list is, the schema's
  English complaints about those fields stay hidden and Speichern stays out of reach; the
  empty field and the empty list already say what is missing (`docs/m3-acceptance.md`).

## Layout

Three columns (Bausteine · Ablauf · Live). Above 1100 px each column scrolls on its own so
the log never pushes the editor away, and the Notstopp sticks to the bottom of the live
column. Below that the columns stack — Ablauf, Live, Bausteine — and the Notstopp scrolls
with the rest instead of covering the camera.
