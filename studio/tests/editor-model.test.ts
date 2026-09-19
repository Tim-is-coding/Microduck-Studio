import { describe, expect, it } from "vitest";

import {
  addAlwaysRule,
  addStep,
  moveStep,
  newBehavior,
  newPerceiveStep,
  newWaitStep,
  parseDurationInput,
  removeStep,
  setUntil,
  slugify,
  splitPhrases,
  tidy,
  untilConditions,
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
