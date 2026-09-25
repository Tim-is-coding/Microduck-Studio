/**
 * Pure editing operations on a behavior pack draft. No React here, so the rules the editor
 * enforces (ids, step shapes, condition forms) can be unit-tested.
 */
import type { Language, Localized } from "../i18n";
import type { BehaviorPack, Check, SkillManifest, Step, StopCondition, Trigger } from "../schemas";

export const BEHAVIOR_SCHEMA_ID = "duckstudio.behavior/v0";
export const PERCEIVE_QUERIES = ["person.nearest", "vlm.target"] as const;
export const VLM_QUERY_PREFIX = "vlm.";
export const DEFAULT_VLM_PROVIDER = "anthropic";
export const DEFAULT_QUESTION = "Wo ist der rote Ball?";
export const DEFAULT_QUESTION_EN = "Where is the red ball?";
export const SIGNALS = ["fallen", "motor_hot", "battery", "tof_distance", "person_found", "target_found", "target_reached", "standing", "sitting"] as const;
export const AFTER_ACTIONS = ["resume", "abort", "stop"] as const;
export const THEN_OPTIONS = ["retry", "abort", "continue"] as const;
export const DURATION_UNITS = ["s", "m"] as const;

const UMLAUTS: Record<string, string> = { ä: "ae", ö: "oe", ü: "ue", ß: "ss" };

/** "Folge mir!" → "folge-mir"; ids must start with a letter and match ^[a-z][a-z0-9_-]*$.
 *  A name with nothing to slugify has no id yet — an unnamed draft says so instead of
 *  inventing one (the editor then hides the id line and keeps Save out of reach). */
export function slugify(name: string): string {
  let s = name
    .toLowerCase()
    .replace(/[äöüß]/g, (c) => UMLAUTS[c] ?? c)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (!s) return "";
  if (!/^[a-z]/.test(s)) s = `ablauf-${s}`.replace(/-$/, "");
  return s.slice(0, 64);
}

/** A new draft is born nameless: the name field shows its placeholder and typing just works,
 *  instead of making somebody clear a prefilled "Neuer Ablauf" first. */
export function newBehavior(name = ""): BehaviorPack {
  return {
    schema: BEHAVIOR_SCHEMA_ID,
    id: slugify(name),
    name: { de: name },
    trigger: { kind: "manual" },
    steps: [],
    always: [],
  };
}

/**
 * Text you type goes into the language you are typing in. `de` is what the schema requires,
 * so it is also the fallback: writing English into a pack that has no German fills both, and
 * a pack that carries both keeps the other language untouched (§3.7).
 */
export function setLocalized(current: Localized | null | undefined, value: string, lang: Language): Localized | undefined {
  if (!value) return undefined;
  if (lang === "de") return { ...current, de: value };
  return { de: current?.de || value, en: value };
}

/**
 * `fresh` means the name is still the placeholder a new draft was born with: there is no
 * translation to protect, so the typed text becomes the behavior's name in every language
 * the editing language implies.
 */
export function renameBehavior(
  pack: BehaviorPack,
  name: string,
  keepId: boolean,
  lang: Language = "de",
  fresh = false,
): BehaviorPack {
  const next = setLocalized(fresh ? undefined : pack.name, name, lang) ?? { de: name };
  return { ...pack, name: next, id: keepId ? pack.id : slugify(name) };
}

export function setSummary(pack: BehaviorPack, value: string, lang: Language): BehaviorPack {
  const summary = setLocalized(pack.summary, value, lang);
  const { summary: _summary, ...rest } = pack;
  return summary ? { ...rest, summary } : rest;
}

/** Default `with` values for a skill card: every ui control that declares a default. */
export function defaultWith(skill: SkillManifest): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, control] of Object.entries(skill.ui)) {
    if (control.default !== undefined && control.default !== null) out[key] = control.default;
  }
  return out;
}

export function newSkillStep(skill: SkillManifest): Step {
  return { skill: skill.id, with: defaultWith(skill) };
}

export function newPerceiveStep(): Step {
  return { perceive: "person.nearest", on_none: { do: "look_around", seconds: 5, then: "retry" } };
}

export function isVlmQuery(query: string): boolean {
  return query.startsWith(VLM_QUERY_PREFIX);
}

/** Switching a perceive card between "die nächste Person" and "per KI suchen".
 *  A KI query needs a question; the local one must not carry one (the runtime rejects it). */
export function setPerceiveQuery(step: Step, query: string, lang: Language = "de"): Step {
  if (!("perceive" in step)) return step;
  const { question: _question, ...rest } = step;
  if (!isVlmQuery(query)) return { ...rest, perceive: query };
  const fallback = lang === "en" ? { de: DEFAULT_QUESTION, en: DEFAULT_QUESTION_EN } : { de: DEFAULT_QUESTION };
  return { ...rest, perceive: query, question: step.question ?? fallback };
}

export function setOnNone(step: Step, onNone: { do: string; seconds: number; then: "retry" | "abort" | "continue" } | null): Step {
  if (!("perceive" in step)) return step;
  const { on_none: _onNone, ...rest } = step;
  return onNone ? { ...rest, on_none: onNone } : rest;
}

export function setQuestion(step: Step, value: string, lang: Language = "de"): Step {
  if (!("perceive" in step)) return step;
  return { ...step, question: setLocalized(step.question, value, lang) ?? { de: value } };
}

export function asksVlm(pack: BehaviorPack): boolean {
  return pack.steps.some((s) => ("perceive" in s && isVlmQuery(s.perceive)) || isAsk(s.only_if));
}

// -- only_if (ADR-0012) ------------------------------------------------------------------

/** The choices the card offers. Each is one plain sentence; `other` keeps a signal written
 *  by hand in YAML that none of them expresses, instead of quietly rewriting it. */
export const CHECK_KINDS = ["someone", "nobody", "obstacle", "clear", "battery", "ask_yes", "ask_no"] as const;
export type CheckKind = (typeof CHECK_KINDS)[number] | "other";

export interface CheckForm {
  kind: CheckKind;
  /** cm for obstacle/clear, % for battery */
  amount?: number;
  question?: Localized;
  signal?: string;
}

const CHECK_DEFAULT_AMOUNT: Partial<Record<CheckKind, number>> = { obstacle: 50, clear: 50, battery: 30 };

export function isAsk(check: Check | null | undefined): check is Extract<Check, { ask: unknown }> {
  return !!check && "ask" in check;
}

export function readCheck(check: Check): CheckForm {
  if (isAsk(check)) return { kind: check.expect === "no" ? "ask_no" : "ask_yes", question: check.ask };
  const sig = check.signal.replace(/\s+/g, " ").trim();
  if (sig === "person_found" || sig === "person_found == 1" || sig === "person_found != 0") return { kind: "someone" };
  if (sig === "person_found == 0" || sig === "person_found != 1") return { kind: "nobody" };
  const m = /^(tof_distance|battery) (<|>=|>|<=) (-?\d+(?:\.\d+)?)$/.exec(sig);
  if (m) {
    const value = Number(m[3]);
    if (m[1] === "tof_distance" && m[2] === "<") return { kind: "obstacle", amount: Math.round(value * 100) };
    if (m[1] === "tof_distance" && m[2] === ">=") return { kind: "clear", amount: Math.round(value * 100) };
    if (m[1] === "battery" && m[2] === ">") return { kind: "battery", amount: Math.round(value * 100) };
  }
  return { kind: "other", signal: check.signal };
}

export function writeCheck(form: CheckForm, lang: Language = "de"): Check {
  const amount = form.amount ?? CHECK_DEFAULT_AMOUNT[form.kind] ?? 0;
  switch (form.kind) {
    case "someone":
      return { signal: "person_found" };
    case "nobody":
      return { signal: "person_found == 0" };
    case "obstacle":
      return { signal: `tof_distance < ${amount / 100}` };
    case "clear":
      return { signal: `tof_distance >= ${amount / 100}` };
    case "battery":
      return { signal: `battery > ${amount / 100}` };
    case "ask_yes":
    case "ask_no": {
      const fallback = lang === "en" ? { de: DEFAULT_CHECK_QUESTION, en: DEFAULT_CHECK_QUESTION_EN } : { de: DEFAULT_CHECK_QUESTION };
      return { ask: form.question ?? fallback, expect: form.kind === "ask_no" ? "no" : "yes" };
    }
    default:
      return { signal: form.signal ?? "person_found" };
  }
}

export const DEFAULT_CHECK_QUESTION = "Liegt ein Ball auf dem Boden?";
export const DEFAULT_CHECK_QUESTION_EN = "Is there a ball on the floor?";

/** Switch the check on or off; keeps the rest of the step as it was. */
export function setOnlyIf(step: Step, check: Check | null): Step {
  const { only_if: _onlyIf, ...rest } = step;
  return check ? ({ ...rest, only_if: check } as Step) : (rest as Step);
}

/** Change the check's kind, keeping an amount or a question where it still fits. */
export function changeCheckKind(check: Check, kind: CheckKind, lang: Language = "de"): Check {
  const form = readCheck(check);
  const keepAmount = form.kind === kind || (["obstacle", "clear"].includes(form.kind) && ["obstacle", "clear"].includes(kind));
  return writeCheck({ kind, amount: keepAmount ? form.amount : undefined, question: form.question }, lang);
}

/** A step that asks a model implies the opt-in (§7): the Studio shows the red line either
 *  way, so the consent stays visible — it just does not make the user hunt for a checkbox. */
export function withVlmIfNeeded(pack: BehaviorPack): BehaviorPack {
  if (!asksVlm(pack) || pack.vlm) return pack;
  return { ...pack, vlm: { provider: DEFAULT_VLM_PROVIDER } };
}

export function newWaitStep(): Step {
  return { wait: "2s" };
}

export function addStep(pack: BehaviorPack, step: Step, at?: number): BehaviorPack {
  const steps = [...pack.steps];
  steps.splice(at ?? steps.length, 0, step);
  return { ...pack, steps };
}

export function removeStep(pack: BehaviorPack, index: number): BehaviorPack {
  return { ...pack, steps: pack.steps.filter((_, i) => i !== index) };
}

export function moveStep(pack: BehaviorPack, index: number, delta: -1 | 1): BehaviorPack {
  const target = index + delta;
  if (target < 0 || target >= pack.steps.length) return pack;
  const steps = [...pack.steps];
  const [step] = steps.splice(index, 1);
  steps.splice(target, 0, step!);
  return { ...pack, steps };
}

/**
 * Move a step to a gap in the list, the way dropping it there reads: `to` counts gaps in the
 * current list (0 = before the first step, steps.length = after the last one).
 */
export function moveStepTo(pack: BehaviorPack, from: number, to: number): BehaviorPack {
  if (from < 0 || from >= pack.steps.length) return pack;
  if (to === from || to === from + 1) return pack; // dropped where it already is
  const steps = [...pack.steps];
  const [step] = steps.splice(from, 1);
  steps.splice(to > from ? to - 1 : to, 0, step!);
  return { ...pack, steps };
}

export function replaceStep(pack: BehaviorPack, index: number, step: Step): BehaviorPack {
  return { ...pack, steps: pack.steps.map((s, i) => (i === index ? step : s)) };
}

export function setTrigger(pack: BehaviorPack, trigger: Trigger): BehaviorPack {
  return { ...pack, trigger };
}

export function speechTrigger(phrasesText: string): Trigger {
  const de = splitPhrases(phrasesText);
  return { kind: "speech", phrases: { de: de.length ? de : ["Los"] } };
}

export function splitPhrases(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function formatDurationInput(value: number, unit: (typeof DURATION_UNITS)[number]): string {
  const n = Number.isFinite(value) && value > 0 ? value : 1;
  return `${Number.isInteger(n) ? n : n.toFixed(1)}${unit}`;
}

export function parseDurationInput(text: string): { value: number; unit: (typeof DURATION_UNITS)[number] } {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(text.trim());
  if (!m) return { value: 2, unit: "s" };
  const value = Number(m[1]);
  switch (m[2]) {
    case "ms":
      return { value: Math.max(1, Math.round(value / 1000)), unit: "s" };
    case "h":
      return { value: value * 60, unit: "m" };
    case "m":
      return { value, unit: "m" };
    default:
      return { value, unit: "s" };
  }
}

export type StopConditionKind = "speech" | "elapsed" | "signal";

export function conditionKind(c: StopCondition): StopConditionKind {
  if ("speech" in c) return "speech";
  if ("elapsed" in c) return "elapsed";
  return "signal";
}

export function newStopCondition(kind: StopConditionKind): StopCondition {
  switch (kind) {
    case "speech":
      return { speech: { de: ["Stopp"] } };
    case "elapsed":
      return { elapsed: "1m" };
    default:
      return { signal: "tof_distance < 0.25" };
  }
}

/** `until` in the editor always uses `any` (oder). */
export function setUntil(step: Step, conditions: StopCondition[]): Step {
  if (!("skill" in step)) return step;
  const { until: _until, ...rest } = step;
  return conditions.length ? { ...rest, until: { any: conditions } } : rest;
}

export function untilConditions(step: Step): StopCondition[] {
  if (!("skill" in step) || !step.until) return [];
  return step.until.any ?? step.until.all ?? [];
}

export function setAlwaysRule(pack: BehaviorPack, index: number, on: string, skill: string | null, after: string): BehaviorPack {
  const rule = { on, do: skill ? [skill, after] : [after] };
  const always = pack.always.map((r, i) => (i === index ? rule : r));
  return { ...pack, always };
}

export function addAlwaysRule(pack: BehaviorPack): BehaviorPack {
  return { ...pack, always: [...pack.always, { on: "fallen", do: ["getup", "resume"] }] };
}

export function removeAlwaysRule(pack: BehaviorPack, index: number): BehaviorPack {
  return { ...pack, always: pack.always.filter((_, i) => i !== index) };
}

export function setVlm(pack: BehaviorPack, provider: string | null): BehaviorPack {
  const { vlm: _vlm, ...rest } = pack;
  return provider ? { ...rest, vlm: { provider } } : rest;
}

function tidyCheck(check: Check): Check {
  if (!isAsk(check)) return { signal: check.signal };
  const ask = check.ask.en ? { de: check.ask.de, en: check.ask.en } : { de: check.ask.de };
  return check.expect === "no" ? { ask, expect: "no" } : { ask, expect: "yes" };
}

/** Strip nulls and empty defaults so the saved YAML stays as short as a hand-written one. */
export function tidy(pack: BehaviorPack): BehaviorPack {
  const out: BehaviorPack = {
    schema: pack.schema,
    id: pack.id,
    name: pack.name.en ? { de: pack.name.de, en: pack.name.en } : { de: pack.name.de },
    trigger: pack.trigger,
    steps: pack.steps.map((s) => {
      const onlyIf = s.only_if ? tidyCheck(s.only_if) : undefined;
      if ("skill" in s) {
        const step: Step = { skill: s.skill, with: s.with };
        if (s.until) Object.assign(step, { until: s.until });
        return onlyIf ? { ...step, only_if: onlyIf } : step;
      }
      if ("perceive" in s) {
        const step: Step = { perceive: s.perceive };
        if (s.question?.de) {
          Object.assign(step, {
            question: s.question.en ? { de: s.question.de, en: s.question.en } : { de: s.question.de },
          });
        }
        if (s.on_none) Object.assign(step, { on_none: s.on_none });
        return onlyIf ? { ...step, only_if: onlyIf } : step;
      }
      const { only_if: _onlyIf, ...wait } = s;
      return onlyIf ? { ...wait, only_if: onlyIf } : wait;
    }),
    always: pack.always,
  };
  if (pack.summary?.de) {
    out.summary = pack.summary.en ? { de: pack.summary.de, en: pack.summary.en } : { de: pack.summary.de };
  }
  if (pack.vlm) out.vlm = pack.vlm;
  return out;
}
