/** Turn schema values into the sentences the cards show. German first (CLAUDE.md §3.7). */
import { formatDuration, t, tOr } from "../i18n";
import { parseCondition, type SkillManifest, type StopCondition, type Trigger } from "../schemas";

export function describeTrigger(trigger: Trigger): string {
  if (trigger.kind === "speech") return t("trigger.speech", { phrases: quoteAll(trigger.phrases.de) });
  return t("trigger.manual");
}

export function quoteAll(phrases: string[]): string {
  return phrases.map((p) => `„${p}“`).join(", ");
}

export function describeSignal(text: string): string {
  const cond = parseCondition(text);
  const name = tOr(`signal.${cond.signal}`, cond.signal);
  if (!cond.op || cond.value === undefined) return name;
  const comparator = cond.op.startsWith("<") ? t("cond.lt") : t("cond.gt");
  return `${name} ${comparator} ${formatSignalValue(cond.signal, cond.value)}`;
}

export function formatSignalValue(signal: string, value: number): string {
  if (signal === "battery") return `${Math.round(value * 100)} %`;
  if (signal.endsWith("distance")) return `${value.toLocaleString("de-DE")} m`;
  return value.toLocaleString("de-DE");
}

export function describeCondition(c: StopCondition): string {
  if ("speech" in c) return t("cond.speech", { phrases: c.speech.de.join("“ oder „") });
  if ("elapsed" in c) return t("cond.elapsed", { duration: formatDuration(c.elapsed) });
  return describeSignal(c.signal);
}

export function describeConditions(conditions: StopCondition[], mode: "any" | "all"): string {
  return conditions.map(describeCondition).join(mode === "any" ? t("cond.or") : t("cond.and"));
}

export function optionLabel(value: string | number | boolean, unit?: string | null): string {
  if (typeof value === "string") return tOr(`opt.${value}`, value);
  if (typeof value === "boolean") return value ? "ja" : "nein";
  return `${value.toLocaleString("de-DE")}${unit ? ` ${unit}` : ""}`;
}

export function controlUnit(skill: SkillManifest | undefined, key: string): string | null {
  const control = skill?.ui[key];
  return control && "unit" in control && control.unit ? control.unit : null;
}

export function actionLabel(action: string, skills: Map<string, SkillManifest>): string {
  return skills.get(action)?.name.de ?? tOr(`action.${action}`, action);
}
