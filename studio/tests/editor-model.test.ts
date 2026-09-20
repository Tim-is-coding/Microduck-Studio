import { describe, expect, it } from "vitest";

import {
  addAlwaysRule,
  addStep,
  asksVlm,
  moveStep,
  moveStepTo,
  newBehavior,
  newPerceiveStep,
  newWaitStep,
  parseDurationInput,
  removeStep,
  setOnNone,
  setPerceiveQuery,
  setQuestion,
  setUntil,
  slugify,
  splitPhrases,
  tidy,
  untilConditions,
  withVlmIfNeeded,
} from "../src/editor/model";
import { BehaviorPack, type Step } from "../src/schemas";

describe("slugify", () => {
  it("makes valid ids from German names", () => {
    expect(slugify("Folge mir!")).toBe("folge-mir");
    expect(slugify("Begrüßung am Morgen")).toBe("begruessung-am-morgen");
    expect(slugify("42 Enten")).toBe("ablauf-42-enten");
    expect(slugify("  ")).toBe("ablauf");
  });
});

describe("draft operations keep the pack schema-valid", () => {
  it("builds a runnable pack from empty", () => {
    let pack = newBehavior("Hallo Ente");
    pack = addStep(pack, newPerceiveStep());
    pack = addStep(pack, { skill: "quack", with: { style: "short" } });
    pack = addStep(pack, newWaitStep());
    pack = addAlwaysRule(pack);
    pack = moveStep(pack, 2, -1);
    expect(pack.steps.map((s) => Object.keys(s)[0])).toEqual(["perceive", "wait", "skill"]);
    pack = removeStep(pack, 1);
    const parsed = BehaviorPack.safeParse(tidy(pack));
    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
    expect(parsed.data!.id).toBe("hallo-ente");
  });

  it("edits until conditions as `any`", () => {
    let step: Step = { skill: "walk", with: {} };
    step = setUntil(step, [{ speech: { de: ["Stopp"] } }, { elapsed: "1m" }]);
    expect(untilConditions(step)).toHaveLength(2);
    expect(setUntil(step, [])).toEqual({ skill: "walk", with: {} });
  });

  it("parses and splits inputs leniently", () => {
    expect(splitPhrases("Folge mir, Komm mit;  ")).toEqual(["Folge mir", "Komm mit"]);
    expect(parseDurationInput("10m")).toEqual({ value: 10, unit: "m" });
    expect(parseDurationInput("500ms")).toEqual({ value: 1, unit: "s" });
    expect(parseDurationInput("garbage")).toEqual({ value: 2, unit: "s" });
  });
});

describe("a perceive card that asks a model", () => {
  it("adds a question when switched to the KI query and drops it when switched back", () => {
    const step = newPerceiveStep();
    const asking = setPerceiveQuery(step, "vlm.target");
    expect(asking).toMatchObject({ perceive: "vlm.target", question: { de: expect.any(String) } });
    const edited = setQuestion(asking, "Wo ist meine Tasse?");
    expect((edited as { question: { de: string } }).question.de).toBe("Wo ist meine Tasse?");
    const back = setPerceiveQuery(edited, "person.nearest");
    expect(back).toEqual({ perceive: "person.nearest", on_none: { do: "look_around", seconds: 5, then: "retry" } });
    expect("question" in back).toBe(false); // the local detector takes no question
  });

  it("keeps the question when the side branch is switched off", () => {
    const asking = setQuestion(setPerceiveQuery(newPerceiveStep(), "vlm.target"), "Wo ist der Ball?");
    const plain = setOnNone(asking, null);
    expect(plain).toEqual({ perceive: "vlm.target", question: { de: "Wo ist der Ball?" } });
  });

  it("brings the opt-in with it, and the pack stays valid", () => {
    let pack = newBehavior("Such das Ding");
    pack = addStep(pack, setPerceiveQuery(newPerceiveStep(), "vlm.target"));
    expect(pack.vlm).toBeUndefined();
    pack = withVlmIfNeeded(pack);
    expect(pack.vlm).toEqual({ provider: "anthropic" });
    expect(asksVlm(pack)).toBe(true);
    pack = addStep(pack, { skill: "walk", with: { direction: "toward_target", tempo: "easy", distance: 50 } });
    const parsed = BehaviorPack.safeParse(tidy(pack));
    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true);
    expect(tidy(pack).steps[0]).toEqual({ perceive: "vlm.target", question: { de: "Wo ist der rote Ball?" }, on_none: { do: "look_around", seconds: 5, then: "retry" } });
  });

  it("leaves a pack without a KI step alone", () => {
    const pack = addStep(newBehavior("Folge"), newPerceiveStep());
    expect(withVlmIfNeeded(pack).vlm).toBeUndefined();
    expect(asksVlm(pack)).toBe(false);
  });
});

describe("moving a step by dropping it", () => {
  const pack = () => {
    let p = newBehavior("Reihenfolge");
    p = addStep(p, newPerceiveStep());
    p = addStep(p, { skill: "walk", with: {} });
    p = addStep(p, { skill: "quack", with: {} });
    return p;
  };
  const kinds = (p: ReturnType<typeof pack>) => p.steps.map((s) => ("skill" in s ? s.skill : Object.keys(s)[0]));

  it("drops a step further down", () => {
    expect(kinds(moveStepTo(pack(), 0, 3))).toEqual(["walk", "quack", "perceive"]);
    expect(kinds(moveStepTo(pack(), 0, 2))).toEqual(["walk", "perceive", "quack"]);
  });

  it("drops a step further up", () => {
    expect(kinds(moveStepTo(pack(), 2, 0))).toEqual(["quack", "perceive", "walk"]);
  });

  it("is a no-op when the step lands where it already was", () => {
    const p = pack();
    expect(moveStepTo(p, 1, 1)).toBe(p);
    expect(moveStepTo(p, 1, 2)).toBe(p);
    expect(moveStepTo(p, 7, 0)).toBe(p);
  });
});
