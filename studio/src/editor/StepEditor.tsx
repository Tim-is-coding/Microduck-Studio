import { t, tOr } from "../i18n";
import { isPerceive, isSkill, isWait, type SkillManifest, type Step, type StopCondition } from "../schemas";
import {
  AFTER_ACTIONS as _AFTER,
  DURATION_UNITS,
  PERCEIVE_QUERIES,
  SIGNALS,
  THEN_OPTIONS,
  conditionKind,
  formatDurationInput,
  isVlmQuery,
  newStopCondition,
  parseDurationInput,
  setOnNone,
  setPerceiveQuery,
  setQuestion,
  setUntil,
  splitPhrases,
  untilConditions,
} from "./model";
import { UiControl } from "./UiControl";

interface Props {
  index: number;
  step: Step;
  skills: Map<string, SkillManifest>;
  count: number;
  onChange: (step: Step) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}

export function StepEditor({ index, step, skills, count, onChange, onMove, onRemove }: Props) {
  return (
    <div className="step editing">
      <div className="num">{index + 1}</div>
      <div className="card">
        <div className="card-actions">
          <button disabled={index === 0} onClick={() => onMove(-1)} title={t("editor.step.up")} type="button">↑</button>
          <button disabled={index === count - 1} onClick={() => onMove(1)} title={t("editor.step.down")} type="button">↓</button>
          <button className="danger-text" onClick={onRemove} title={t("editor.step.remove")} type="button">✕</button>
        </div>
        {isSkill(step) && <SkillBody onChange={onChange} skill={skills.get(step.skill)} step={step} />}
        {isPerceive(step) && <PerceiveBody onChange={onChange} skills={skills} step={step} />}
        {isWait(step) && <WaitBody onChange={onChange} step={step} />}
      </div>
    </div>
  );
}

function SkillBody({ step, skill, onChange }: { step: Extract<Step, { skill: string }>; skill: SkillManifest | undefined; onChange: (s: Step) => void }) {
  if (!skill) return <div className="title problems">{t("editor.step.unknown_skill", { id: step.skill })}</div>;
  const conditions = untilConditions(step);
  return (
    <>
      <div className="title">{skill.name.de}</div>
      {skill.summary && <div className="sub">{skill.summary.de}</div>}
      <div className="fields">
        {Object.entries(skill.ui).map(([key, spec]) => (
          <UiControl key={key} name={key} onChange={(v) => onChange({ ...step, with: { ...step.with, [key]: v } })} spec={spec} value={step.with[key]} />
        ))}
      </div>
      <div className="branch until editing">
        <div className="field-label">{t("editor.until")}</div>
        {conditions.length === 0 && <div className="sub">{t("editor.until.none")}</div>}
        {conditions.map((c, i) => (
          <div className="cond" key={i}>
            {i > 0 && <span className="or">{t("editor.until.or")}</span>}
            <ConditionEditor condition={c} onChange={(nc) => onChange(setUntil(step, conditions.map((x, j) => (j === i ? nc : x))))} />
            <button className="danger-text" onClick={() => onChange(setUntil(step, conditions.filter((_, j) => j !== i)))} type="button">✕</button>
          </div>
        ))}
        <div className="chips">
          {(["speech", "elapsed", "signal"] as const).map((kind) => (
            <button className="chip clickable" key={kind} onClick={() => onChange(setUntil(step, [...conditions, newStopCondition(kind)]))} type="button">
              {t(`editor.until.add.${kind}`)}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

function ConditionEditor({ condition, onChange }: { condition: StopCondition; onChange: (c: StopCondition) => void }) {
  const kind = conditionKind(condition);
  if (kind === "speech" && "speech" in condition) {
    return (
      <label className="inline">
        <span>{t("editor.until.speech")}</span>
        <input
          onChange={(e) => onChange({ speech: { de: splitPhrases(e.target.value).length ? splitPhrases(e.target.value) : [e.target.value] } })}
          value={condition.speech.de.join(", ")}
        />
      </label>
    );
  }
  if (kind === "elapsed" && "elapsed" in condition) {
    const { value, unit } = parseDurationInput(condition.elapsed);
    return (
      <span className="inline">
        <span>{t("editor.until.elapsed")}</span>
        <input min={1} onChange={(e) => onChange({ elapsed: formatDurationInput(Number(e.target.value), unit) })} type="number" value={value} />
        <select onChange={(e) => onChange({ elapsed: formatDurationInput(value, e.target.value as (typeof DURATION_UNITS)[number]) })} value={unit}>
          {DURATION_UNITS.map((u) => <option key={u} value={u}>{t(`editor.unit.${u}`)}</option>)}
        </select>
      </span>
    );
  }
  if ("signal" in condition) {
    const m = /^([a-z_]+)(?:\s*(<|>)\s*(-?\d+(?:\.\d+)?))?$/.exec(condition.signal);
    const signal = m?.[1] ?? "tof_distance";
    const op = m?.[2] ?? null;
    const val = m?.[3] ?? "0.25";
    const numeric = signal === "battery" || signal === "tof_distance";
    const build = (s: string, o: string | null, v: string) => ({ signal: numeric && o ? `${s} ${o} ${v}` : s });
    return (
      <span className="inline">
        <span>{t("editor.until.signal")}</span>
        <select onChange={(e) => onChange(build(e.target.value, e.target.value === "battery" || e.target.value === "tof_distance" ? (op ?? "<") : null, val))} value={signal}>
          {SIGNALS.map((s) => <option key={s} value={s}>{tOr(`signal.${s}`, s)}</option>)}
        </select>
        {numeric && (
          <>
            <select onChange={(e) => onChange(build(signal, e.target.value, val))} value={op ?? "<"}>
              <option value="<">{t("editor.op.lt")}</option>
              <option value=">">{t("editor.op.gt")}</option>
            </select>
            <input onChange={(e) => onChange(build(signal, op ?? "<", e.target.value))} step={0.05} type="number" value={val} />
          </>
        )}
      </span>
    );
  }
  return null;
}

function PerceiveBody({ step, skills, onChange }: { step: Extract<Step, { perceive: string }>; skills: Map<string, SkillManifest>; onChange: (s: Step) => void }) {
  const onNone = step.on_none ?? null;
  return (
    <>
      <label className="field">
        <span className="field-label">{t("editor.perceive.what")}</span>
        <select onChange={(e) => onChange(setPerceiveQuery(step, e.target.value))} value={step.perceive}>
          {PERCEIVE_QUERIES.map((q) => <option key={q} value={q}>{tOr(`perceive.${q}`, q)}</option>)}
        </select>
      </label>
      {isVlmQuery(step.perceive) && (
        <>
          <label className="field">
            <span className="field-label">{t("editor.perceive.question")}</span>
            <input
              onChange={(e) => onChange(setQuestion(step, e.target.value))}
              placeholder={t("editor.perceive.question.placeholder")}
              value={step.question?.de ?? ""}
            />
          </label>
          <div className="vlm">{t("editor.perceive.question.hint")}</div>
        </>
      )}
      <div className="branch editing">
        <label className="inline">
          <input
            checked={onNone !== null}
            onChange={(e) => onChange(setOnNone(step, e.target.checked ? { do: "look_around", seconds: 5, then: "retry" } : null))}
            type="checkbox"
          />
          <span className="field-label">{t("editor.perceive.on_none")}</span>
        </label>
        {onNone && (
          <span className="inline wrap">
            <span>{t("editor.perceive.on_none.do")}</span>
            <select onChange={(e) => onChange({ ...step, on_none: { ...onNone, do: e.target.value } })} value={onNone.do}>
              {[...skills.values()].map((s) => <option key={s.id} value={s.id}>{s.name.de}</option>)}
            </select>
            <input max={600} min={1} onChange={(e) => onChange({ ...step, on_none: { ...onNone, seconds: Number(e.target.value) } })} type="number" value={onNone.seconds} />
            <span>{t("editor.perceive.on_none.seconds")}, {t("editor.perceive.on_none.then")}</span>
            <select onChange={(e) => onChange({ ...step, on_none: { ...onNone, then: e.target.value as (typeof THEN_OPTIONS)[number] } })} value={onNone.then}>
              {THEN_OPTIONS.map((o) => <option key={o} value={o}>{t(`then.${o}`)}</option>)}
            </select>
          </span>
        )}
      </div>
    </>
  );
}

function WaitBody({ step, onChange }: { step: Extract<Step, { wait: string }>; onChange: (s: Step) => void }) {
  const { value, unit } = parseDurationInput(step.wait);
  return (
    <label className="field">
      <span className="field-label">{t("editor.wait.duration")}</span>
      <span className="inline">
        <input min={1} onChange={(e) => onChange({ wait: formatDurationInput(Number(e.target.value), unit) })} type="number" value={value} />
        <select onChange={(e) => onChange({ wait: formatDurationInput(value, e.target.value as (typeof DURATION_UNITS)[number]) })} value={unit}>
          {DURATION_UNITS.map((u) => <option key={u} value={u}>{t(`editor.unit.${u}`)}</option>)}
        </select>
      </span>
    </label>
  );
}
