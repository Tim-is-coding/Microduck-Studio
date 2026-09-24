# The Studio's look

One stylesheet, no UI kit (`CLAUDE.md` §5) and no font CDN — Geist ships with the Studio
(`@fontsource-variable/geist`, OFL), so nothing is fetched from Google and it works offline.
`studio/src/styles.css` holds tokens first, then components. Everything else reads those
tokens, so a change lands everywhere at once and dark mode is a swap of values rather than a
second stylesheet.

## Tokens

| Group | Tokens | Rule of thumb |
| --- | --- | --- |
| Surfaces | `--bg`, `--surface`, `--surface-2`, `--surface-3` | ground, the two sheets, wells inside a sheet, hover on wells |
| Lines | `--line`, `--line-mid`, `--line-strong`, `--mark-faint` | hairlines between rows, input borders, controls that must be found, decoration |
| Text | `--ink`, `--ink-2`, `--muted` | names, body, labels |
| Action | `--action`, `--on-action`, `--action-hover` | the primary button is ink, not a colour |
| Running | `--accent`, `--accent-halo`, `--accent-weak`, `--accent-line` | the running dot and bar, nothing else |
| State | `--danger`, `--danger-solid`, `--danger-weak`, `--ok`, `--warn`, `--info`, `--focus` | `--danger` is text, `--danger-solid` is the Notstopp red and stays the same in both themes |
| Perception | `--mark-person`, `--mark-target` | the camera overlay and the chips that describe it agree by construction |
| Type | `--t-xs` … `--t-xl`, `--font`, `--mono` | 12 / 13 / 14.5 / 16 / 26 px |
| Shape | `--r-sm`, `--r-btn`, `--r-md`, `--r-lg`, `--shadow-sheet`, `--shadow-pop` | 6 inputs, 8 buttons, 10 camera and menus, 14 sheets |

Measurements (distances, battery, log times) use `font-variant-numeric: tabular-nums` so
they stop jittering while they update.

## Dark mode

`prefers-color-scheme` decides unless the Studio was told otherwise; the switch in the top
bar (system / hell / dunkel) writes `data-theme` on `<html>` and remembers the choice in
`localStorage` (`studio/src/theme.ts`, per browser, never in a behavior). Anything drawn in
JavaScript asks `useIsDark()` — that is how the ToF grid keeps "clear" pale on paper and
quiet at night (`live/overlay.ts`).

## Rules that keep it coherent

- **One accent, spent on one thing.** Yellow marks what runs right now; the primary action is
  ink. Red is reserved for the Notstopp, errors and "a picture is leaving this machine" (§7).
- **Rows, not boxes.** Inside a sheet, content is separated by hairlines; a well
  (`--surface-2`) appears only for something being filled in (a condition, the AI draft).
- **Drawn icons, no emoji** (`ui/Icon.tsx`): they inherit `currentColor` and the font size,
  so a button looks the same on every machine.
- **Every interactive element shows focus** via `:focus-visible` and the `--focus` token.
- **Variants state their own hover.** `.btn:hover:not(:disabled)` outranks `.btn.danger`, so
  each variant repeats its background in its hover rule — the Notstopp red never turns into
  white-on-white under the pointer.
- **Nothing in the live column may be squeezed** (`.live > * { flex: none }`): a flex column
  inside a scrolling panel would otherwise collapse the camera to a line as the log grows.
- **Reduced motion is honoured**: the breathing „läuft“ dot and the listening microphone
  stop under `prefers-reduced-motion`.

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

- **The overview with no behaviors** keeps the "Neuer Ablauf" row and adds a row of
  starter templates (`editor/templates.ts`) — complete, runnable packs that open as a draft;
  nothing is written until Speichern. The row disappears as soon as there is one behavior.
- **A new draft is nameless.** The name field shows its placeholder and the id line shows
  "Gib dem Ablauf einen Namen." until there is a name — no prefilled text to delete first,
  and no `Kennung: neuer-ablauf` before anybody named anything.
- **A Studio without a runtime says so.** The Studio only ever talks to the runtime (§4), so
  when nothing answers, the place where the behaviors would be carries the reason and the one
  command that fixes it — an empty overview would read as "you have nothing" instead. The
  live panel says the same in its status line, the blocks panel in its empty list, and the
  page reconnects by itself: the catalog is loaded whenever the runtime answers and the
  Studio does not have it yet, so a Studio opened before `python -m duckstudio` fills in
  rather than staying empty until somebody reloads. The Notstopp stays pressable — never
  gate the emergency stop, not even on a connection.
- **Unfinished is not broken.** While the name is empty or the step list is, the schema's
  English complaints about those fields stay hidden and Speichern stays out of reach; the
  empty field and the empty list already say what is missing (`docs/m3-acceptance.md`).

## Layout

Two sheets: the route (tabs, then the rows of a behavior) and Live (380 px, sticky). The
building blocks and the AI vendors are pages behind the tabs on the right, not a permanent
column. Below 960 px Live moves on top as a compact grid (camera beside the sentence) and the
route follows; below 700 px the tabs scroll sideways instead of wrapping.
