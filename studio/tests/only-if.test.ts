import { describe, expect, it } from "vitest";

import { describeCheck } from "../src/ablauf/describe";
import {
  addStep,
  asksVlm,
  changeCheckKind,
  newBehavior,
  newWaitStep,
  readCheck,
  setOnlyIf,
  tidy,
  withVlmIfNeeded,
  writeCheck,
  type CheckForm,
} from "../src/editor/model";
import { setLanguage } from "../src/i18n";
import { BehaviorPack, type Check, type Step } from "../src/schemas";

const quack: Step = { skill: "quack", with: { style: "short" } };

describe("only_if (ADR-0012)", () => {
  it("every choice on the card writes a check and reads back as the same choice", () => {
    const forms: CheckForm[] = [
      { kind: "someone" },
      { kind: "nobody" },
      { kind: "obstacle", amount: 40 },
      { kind: "clear", amount: 80 },
      { kind: "battery", amount: 30 },
      { kind: "ask_yes", question: { de: "Liegt da ein Ball?" } },
      { kind: "ask_no", question: { de: "Ist die Tür zu?" } },
    ];
    for (const form of forms) expect(readCheck(writeCheck(form))).toEqual(form);
  });

  it("writes the signals the runtime knows", () => {
    expect(writeCheck({ kind: "nobody" })).toEqual({ signal: "person_found == 0" });
    expect(writeCheck({ kind: "obstacle", amount: 40 })).toEqual({ signal: "tof_distance < 0.4" });
    expect(writeCheck({ kind: "battery", amount: 30 })).toEqual({ signal: "battery > 0.3" });
  });

  it("keeps a hand-written signal it has no choice for", () => {
    const check: Check = { signal: "person_distance < 1.5" };
    expect(readCheck(check)).toEqual({ kind: "other", signal: "person_distance < 1.5" });
  });

  it("switching obstacle ↔ clear keeps the distance, switching to battery does not", () => {
    const obstacle = writeCheck({ kind: "obstacle", amount: 70 });
    expect(readCheck(changeCheckKind(obstacle, "clear")).amount).toBe(70);
    expect(readCheck(changeCheckKind(obstacle, "battery")).amount).toBe(30);
  });

  it("survives tidy() — saving must not drop it", () => {
    let pack = addStep(newBehavior("Test"), setOnlyIf(quack, { signal: "person_found" }));
    pack = addStep(pack, setOnlyIf(newWaitStep(), { ask: { de: "Ball?" }, expect: "no" }));
    const steps = tidy(withVlmIfNeeded(pack)).steps;
    expect(steps.at(-2)).toEqual({ skill: "quack", with: { style: "short" }, only_if: { signal: "person_found" } });
    expect(steps.at(-1)).toEqual({ wait: "2s", only_if: { ask: { de: "Ball?" }, expect: "no" } });
  });

  it("asking the model is a VLM use: the opt-in comes with it", () => {
    const pack = addStep(newBehavior("Test"), setOnlyIf(quack, writeCheck({ kind: "ask_yes" })));
    expect(asksVlm(pack)).toBe(true);
    expect(withVlmIfNeeded(pack).vlm).toBeTruthy();
    expect(asksVlm(addStep(newBehavior("Test"), setOnlyIf(quack, writeCheck({ kind: "someone" }))))).toBe(false);
  });

  it("switching the check off removes the field", () => {
    expect(setOnlyIf(setOnlyIf(quack, { signal: "person_found" }), null)).toEqual(quack);
  });

  it("the schema refuses what only a running step knows", () => {
    const pack = { ...newBehavior("Test"), id: "test", steps: [setOnlyIf(quack, { signal: "timeout" })] };
    expect(BehaviorPack.safeParse(pack).success).toBe(false);
    const ok = { ...pack, steps: [setOnlyIf(quack, { signal: "tof_distance < 0.5" })] };
    expect(BehaviorPack.safeParse(ok).success).toBe(true);
  });

  it("reads as a sentence, in both languages", () => {
    setLanguage("de");
    expect(describeCheck({ signal: "tof_distance < 0.5" })).toBe("ein Hindernis näher als 50 cm ist");
    expect(describeCheck({ ask: { de: "Liegt da ein Ball?" }, expect: "yes" })).toBe("die KI auf „Liegt da ein Ball?“ ja sagt");
    setLanguage("en");
    expect(describeCheck({ signal: "person_found == 0" })).toBe("nobody is in view");
    setLanguage("de");
  });
});
