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

## Layout

Three columns (Bausteine · Ablauf · Live). Above 1100 px each column scrolls on its own so
the log never pushes the editor away, and the Notstopp sticks to the bottom of the live
column. Below that the columns stack — Ablauf, Live, Bausteine — and the Notstopp scrolls
with the rest instead of covering the camera.
