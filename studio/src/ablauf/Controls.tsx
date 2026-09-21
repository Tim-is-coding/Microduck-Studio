import { t, tOr } from "../i18n";
import type { SkillManifest, StopCondition, UiControl as UiControlSpec } from "../schemas";
import {
  DURATION_UNITS,
  SIGNALS,
  conditionKind,
  formatDurationInput,
  parseDurationInput,
  splitPhrases,
} from "../editor/model";

type Scalar = string | number | boolean;

/** One card control, rendered from a skill manifest's `ui` entry (§6.1). */
export function UiControl({ name, spec, value, onChange }: { name: string; spec: UiControlSpec; value: Scalar | undefined; onChange: (v: Scalar) => void }) {
  const label = tOr(`ui.${name}`, name);
  switch (spec.control) {
    case "choice": {
      const current = value ?? spec.default;
      return (
        <div className="field">
          <span>{label}</span>
          <div className="seg">
            {spec.options.map((opt) => (
              <button className={current === opt ? "active" : ""} key={opt} onClick={() => onChange(opt)} type="button">
                {tOr(`opt.${opt}`, opt)}
              </button>
            ))}
          </div>
        </div>
      );
    }
    case "select":
      return (
        <label className="field">
          <span>{label}</span>
          <select onChange={(e) => onChange(e.target.value)} value={String(value ?? spec.default ?? spec.options[0])}>
            {spec.options.map((opt) => (
              <option key={opt} value={opt}>{tOr(`opt.${opt}`, opt)}</option>
            ))}
          </select>
        </label>
      );
    case "range": {
      const v = typeof value === "number" ? value : (spec.default ?? spec.min);
      return (
        <label className="field">
          <span>{label}: <b>{v}{spec.unit ? ` ${spec.unit}` : ""}</b></span>
          <input max={spec.max} min={spec.min} onChange={(e) => onChange(Number(e.target.value))} step={spec.step ?? 1} type="range" value={v} />
        </label>
      );
    }
    case "toggle":
      return (
        <label className="field inline">
          <input checked={Boolean(value ?? spec.default)} onChange={(e) => onChange(e.target.checked)} type="checkbox" />
          <span>{label}</span>
        </label>
      );
  }
}

export function DurationInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const parsed = parseDurationInput(value);
  return (
    <span className="inline">
      <input min={1} onChange={(e) => onChange(formatDurationInput(Number(e.target.value), parsed.unit))} type="number" value={parsed.value} />
      <select onChange={(e) => onChange(formatDurationInput(parsed.value, e.target.value as (typeof DURATION_UNITS)[number]))} value={parsed.unit}>
        {DURATION_UNITS.map((u) => <option key={u} value={u}>{t(`editor.unit.${u}`)}</option>)}
      </select>
    </span>
  );
}

const NUMERIC_SIGNALS = new Set(["battery", "tof_distance", "person_distance"]);

export function ConditionEditor({ condition, onChange }: { condition: StopCondition; onChange: (c: StopCondition) => void }) {
  const kind = conditionKind(condition);
  if (kind === "speech" && "speech" in condition) {
    return (
      <label className="inline">
        <span>{t("route.until.speech")}</span>
        <input
          onChange={(e) => {
            const parts = splitPhrases(e.target.value);
            onChange({ speech: { ...condition.speech, de: parts.length ? parts : [e.target.value] } });
          }}
          value={condition.speech.de.join(", ")}
        />
      </label>
    );
  }
  if (kind === "elapsed" && "elapsed" in condition) {
    return (
      <span className="inline">
        <span>{t("route.until.elapsed")}</span>
        <DurationInput onChange={(v) => onChange({ elapsed: v })} value={condition.elapsed} />
      </span>
    );
  }
  if ("signal" in condition) {
    const m = /^([a-z_]+)(?:\s*(<|>)\s*(-?\d+(?:\.\d+)?))?$/.exec(condition.signal);
    const signal = m?.[1] ?? "tof_distance";
    const op = m?.[2] ?? "<";
    const val = m?.[3] ?? "0.25";
    const numeric = NUMERIC_SIGNALS.has(signal);
    const build = (s: string, o: string, v: string) => ({ signal: NUMERIC_SIGNALS.has(s) ? `${s} ${o} ${v}` : s });
    return (
      <span className="inline">
        <span>{t("route.until.signal")}</span>
        <select onChange={(e) => onChange(build(e.target.value, op, val))} value={signal}>
          {SIGNALS.map((s) => <option key={s} value={s}>{tOr(`signal.${s}`, s)}</option>)}
        </select>
        {numeric && (
          <>
            <select onChange={(e) => onChange(build(signal, e.target.value, val))} value={op}>
              <option value="<">{t("cond.lt")}</option>
              <option value=">">{t("cond.gt")}</option>
            </select>
            <input onChange={(e) => onChange(build(signal, op, e.target.value))} step={0.05} type="number" value={val} />
          </>
        )}
      </span>
    );
  }
  return null;
}

export function skillGroups(skills: SkillManifest[]): { move: SkillManifest[]; behavior: SkillManifest[] } {
  return { move: skills.filter((s) => s.intent), behavior: skills.filter((s) => s.behavior) };
}
