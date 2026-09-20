/**
 * Pure editing operations on a behavior pack draft. No React here, so the rules the editor
 * enforces (ids, step shapes, condition forms) can be unit-tested.
 */
import type { Language, Localized } from "../i18n";
import type { BehaviorPack, SkillManifest, Step, StopCondition, Trigger } from "../schemas";

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

/** "Folge mir!" → "folge-mir"; ids must start with a letter and match ^[a-z][a-z0-9_-]*$. */
export function slugify(name: string): string {
  let s = name
    .toLowerCase()
    .replace(/[äöüß]/g, (c) => UMLAUTS[c] ?? c)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (!/^[a-z]/.test(s)) s = `ablauf-${s}`.replace(/-$/, "");
  return s.slice(0, 64);
}

export function newBehavior(name: string): BehaviorPack {
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
  return pack.steps.some((s) => "perceive" in s && isVlmQuery(s.perceive));
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

/** Strip nulls and empty defaults so the saved YAML stays as short as a hand-written one. */
export function tidy(pack: BehaviorPack): BehaviorPack {
  const out: BehaviorPack = {
    schema: pack.schema,
    id: pack.id,
    name: pack.name.en ? { de: pack.name.de, en: pack.name.en } : { de: pack.name.de },
    trigger: pack.trigger,
    steps: pack.steps.map((s) => {
      if ("skill" in s) {
        const step: Step = { skill: s.skill, with: s.with };
        if (s.until) return { ...step, until: s.until };
        return step;
      }
      if ("perceive" in s) {
        const step: Step = { perceive: s.perceive };
        if (s.question?.de) {
          Object.assign(step, {
            question: s.question.en ? { de: s.question.de, en: s.question.en } : { de: s.question.de },
          });
        }
        return s.on_none ? { ...step, on_none: s.on_none } : step;
      }
      return s;
    }),
    always: pack.always,
  };
  if (pack.summary?.de) {
    out.summary = pack.summary.en ? { de: pack.summary.de, en: pack.summary.en } : { de: pack.summary.de };
  }
  if (pack.vlm) out.vlm = pack.vlm;
  return out;
}
