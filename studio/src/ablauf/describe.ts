/** Turn schema values into the sentences the cards show, in the Studio's language. */
import { formatDuration, number, phrases as phraseList, quote, quoteJoin, t, tOr, text } from "../i18n";
import { parseCondition, type SkillManifest, type StopCondition, type Trigger } from "../schemas";

export function describeTrigger(trigger: Trigger): string {
  if (trigger.kind === "speech") return t("route.trigger.speech", { phrases: quoteJoin(phraseList(trigger.phrases), ", ") });
  return t("route.trigger.manual");
}

export function describeSignal(condition: string): string {
  const cond = parseCondition(condition);
  const name = tOr(`signal.${cond.signal}`, cond.signal);
  if (!cond.op || cond.value === undefined) return name;
  const comparator = cond.op.startsWith("<") ? t("cond.lt") : t("cond.gt");
  return `${name} ${comparator} ${formatSignalValue(cond.signal, cond.value)}`;
}

export function formatSignalValue(signal: string, value: number): string {
  if (signal === "battery") return `${Math.round(value * 100)} %`;
  if (signal.endsWith("distance")) return `${number(value, 2)} m`;
  return number(value, 1);
}

export function describeCondition(c: StopCondition): string {
  if ("speech" in c) return t("cond.speech", { phrases: quoteJoin(phraseList(c.speech), ` ${t("cond.or").trim()} `) });
  if ("elapsed" in c) return t("cond.elapsed", { duration: formatDuration(c.elapsed) });
  return describeSignal(c.signal);
}

export function describeConditions(conditions: StopCondition[], mode: "any" | "all"): string {
  return conditions.map(describeCondition).join(mode === "any" ? t("cond.or") : t("cond.and"));
}

export function optionLabel(value: string | number | boolean, unit?: string | null): string {
  if (typeof value === "string") return tOr(`opt.${value}`, value);
  if (typeof value === "boolean") return value ? "✓" : "–";
  return `${number(value, Number.isInteger(value) ? 0 : 1)}${unit ? ` ${unit}` : ""}`;
}

export function controlUnit(skill: SkillManifest | undefined, key: string): string | null {
  const control = skill?.ui[key];
  return control && "unit" in control && control.unit ? control.unit : null;
}

export function actionLabel(action: string, skills: Map<string, SkillManifest>): string {
  const skill = skills.get(action);
  return skill ? text(skill.name) : tOr(`action.${action}`, action);
}

export { quote };
