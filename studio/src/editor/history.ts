/**
 * Undo for the draft. A non-technical user's first reflex after a wrong click is Strg+Z, and
 * a step list you can drag, delete and retype is exactly where that reflex belongs (§3.1).
 *
 * The unit of undo is a *move*, not a keystroke: typing a name and dragging a slider fold
 * into one entry as long as they follow each other closely and leave the shape of the
 * behavior alone. Adding, removing, moving or retyping a step changes the shape, so it always
 * starts a new entry — undo never swallows two structural changes at once.
 */
import type { BehaviorPack, Step } from "../schemas";

/** How far apart two edits may be and still count as one move. */
export const COALESCE_MS = 1200;
/** Deep enough to undo a session of fiddling, short enough to stay cheap. */
export const LIMIT = 50;

export interface History {
  past: BehaviorPack[];
  future: BehaviorPack[];
  /** When the newest entry was recorded, for coalescing. */
  at: number;
}

export const NO_HISTORY: History = { past: [], future: [], at: 0 };

function stepKey(step: Step): string {
  if ("skill" in step) return `skill:${step.skill}`;
  if ("perceive" in step) return `perceive:${step.perceive}`;
  return "wait";
}

/** Same steps in the same order, same branches, same trigger kind — only values differ. */
export function sameShape(a: BehaviorPack, b: BehaviorPack): boolean {
  return (
    a.id === b.id &&
    a.trigger.kind === b.trigger.kind &&
    a.always.length === b.always.length &&
    Boolean(a.vlm) === Boolean(b.vlm) &&
    a.steps.length === b.steps.length &&
    a.steps.every((step, i) => stepKey(step) === stepKey(b.steps[i]!))
  );
}

/** Remember `before` because the draft just became `after`. */
export function record(history: History, before: BehaviorPack, after: BehaviorPack, now: number): History {
  if (before === after) return history;
  const coalesce = history.past.length > 0 && now - history.at < COALESCE_MS && sameShape(before, after);
  return {
    past: coalesce ? history.past : [...history.past, before].slice(-LIMIT),
    future: [],
    at: now,
  };
}

export function undo(history: History, current: BehaviorPack): { history: History; draft: BehaviorPack } | null {
  const previous = history.past.at(-1);
  if (!previous) return null;
  return {
    draft: previous,
    history: { past: history.past.slice(0, -1), future: [current, ...history.future], at: 0 },
  };
}

export function redo(history: History, current: BehaviorPack): { history: History; draft: BehaviorPack } | null {
  const next = history.future[0];
  if (!next) return null;
  return {
    draft: next,
    history: { past: [...history.past, current], future: history.future.slice(1), at: 0 },
  };
}
