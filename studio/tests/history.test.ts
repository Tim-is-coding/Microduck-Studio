import { describe, expect, it } from "vitest";

import { COALESCE_MS, LIMIT, NO_HISTORY, record, redo, sameShape, undo } from "../src/editor/history";
import { addStep, newBehavior, newWaitStep, removeStep, renameBehavior } from "../src/editor/model";
import type { BehaviorPack } from "../src/schemas";

const base = addStep(addStep(newBehavior("Test"), { skill: "quack", with: {} }), newWaitStep());
const rename = (p: BehaviorPack, name: string) => renameBehavior(p, name, true);

describe("sameShape", () => {
  it("ignores values and notices structure", () => {
    expect(sameShape(base, rename(base, "Anders"))).toBe(true);
    expect(sameShape(base, addStep(base, newWaitStep()))).toBe(false);
    expect(sameShape(base, removeStep(base, 0))).toBe(false);
    expect(sameShape(base, { ...base, steps: [base.steps[1]!, base.steps[0]!] })).toBe(false);
    expect(sameShape(base, { ...base, trigger: { kind: "speech", phrases: { de: ["Los"] } } })).toBe(false);
  });
});

describe("record", () => {
  it("folds a burst of typing into one entry", () => {
    let h = record(NO_HISTORY, base, rename(base, "T"), 1000);
    h = record(h, rename(base, "T"), rename(base, "Te"), 1100);
    h = record(h, rename(base, "Te"), rename(base, "Tes"), 1200);
    expect(h.past).toHaveLength(1);
    expect(h.past[0]).toEqual(base); // undo goes back to before the first keystroke
  });

  it("starts a new entry after a pause", () => {
    let h = record(NO_HISTORY, base, rename(base, "T"), 1000);
    h = record(h, rename(base, "T"), rename(base, "Te"), 1000 + COALESCE_MS + 1);
    expect(h.past).toHaveLength(2);
  });

  it("never folds two structural changes", () => {
    const one = addStep(base, newWaitStep());
    let h = record(NO_HISTORY, base, one, 1000);
    h = record(h, one, addStep(one, newWaitStep()), 1010);
    expect(h.past).toHaveLength(2);
  });

  it("drops the oldest entries past the limit", () => {
    let h = NO_HISTORY;
    for (let i = 0; i < LIMIT + 10; i++) h = record(h, addStep(base, { wait: `${i + 1}s` }), base, i * 10_000);
    expect(h.past).toHaveLength(LIMIT);
    expect(h.past[0]).toEqual(addStep(base, { wait: "11s" }));
  });

  it("forgets the redo stack as soon as you edit again", () => {
    const changed = addStep(base, newWaitStep());
    const back = undo(record(NO_HISTORY, base, changed, 1000), changed)!;
    expect(back.history.future).toHaveLength(1);
    expect(record(back.history, base, rename(base, "Neu"), 5000).future).toEqual([]);
  });
});

describe("undo and redo", () => {
  it("walk the same path in both directions", () => {
    const named = rename(base, "Zwei");
    const more = addStep(named, newWaitStep());
    let h = record(NO_HISTORY, base, named, 1000);
    h = record(h, named, more, 9000);

    const first = undo(h, more)!;
    expect(first.draft).toEqual(named);
    const second = undo(first.history, first.draft)!;
    expect(second.draft).toEqual(base);
    expect(undo(second.history, second.draft)).toBeNull();

    const forward = redo(second.history, second.draft)!;
    expect(forward.draft).toEqual(named);
    expect(redo(forward.history, forward.draft)!.draft).toEqual(more);
  });

  it("does nothing on an untouched draft", () => {
    expect(undo(NO_HISTORY, base)).toBeNull();
    expect(redo(NO_HISTORY, base)).toBeNull();
  });
});
