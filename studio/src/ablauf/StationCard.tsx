import { formatDuration, t, tOr } from "../i18n";
import { isPerceive, isSkill, isWait, type SkillManifest, type Step } from "../schemas";
import { PERCEIVE_QUERIES, THEN_OPTIONS, newStopCondition, setUntil, untilConditions } from "../editor/model";
import { ConditionEditor, DurationInput, UiControl } from "./Controls";
import { controlUnit, describeConditions, optionLabel } from "./describe";

interface Props {
  index: number;
  count: number;
  step: Step;
  skills: Map<string, SkillManifest>;
  editable: boolean;
  active: boolean;
  done: boolean;
  onChange: (step: Step) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}

/** One station on the rail: a step, viewed or edited in place. */
export function StationCard({ index, count, step, skills, editable, active, done, onChange, onMove, onRemove }: Props) {
  const cls = ["station", active ? "active" : "", done ? "done" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      <div className="node" title={done ? t("step.done") : undefined}>{done ? "✓" : index + 1}</div>
      <div className="card">
        <div className="head">
          <div className="titles">
            {isSkill(step) && <SkillHead skill={skills.get(step.skill)} step={step} />}
            {isPerceive(step) && (
              <div className="title">{t("step.perceive", { what: tOr(`perceive.${step.perceive}`, step.perceive) })}</div>
            )}
            {isWait(step) && <div className="title">{t("step.wait", { duration: formatDuration(step.wait) })}</div>}
          </div>
          {editable && (
            <div className="actions">
              <button className="iconbtn" disabled={index === 0} onClick={() => onMove(-1)} title={t("step.up")} type="button">↑</button>
              <button className="iconbtn" disabled={index === count - 1} onClick={() => onMove(1)} title={t("step.down")} type="button">↓</button>
              <button className="iconbtn danger" onClick={onRemove} title={t("step.remove")} type="button">✕</button>
            </div>
          )}
        </div>
        {isSkill(step) && <SkillBody editable={editable} onChange={onChange} skill={skills.get(step.skill)} step={step} />}
        {isPerceive(step) && <PerceiveBody editable={editable} onChange={onChange} skills={skills} step={step} />}
        {isWait(step) && editable && (
          <div className="fields">
            <label className="field">
              <span>{t("step.wait.label")}</span>
              <DurationInput onChange={(v) => onChange({ wait: v })} value={step.wait} />
            </label>
          </div>
        )}
      </div>
    </div>
  );
}

type SkillStep = Extract<Step, { skill: string }>;
type PerceiveStep = Extract<Step, { perceive: string }>;

function SkillHead({ step, skill }: { step: SkillStep; skill: SkillManifest | undefined }) {
  if (!skill) return <div className="title problems">{t("step.unknown_skill", { id: step.skill })}</div>;
  return (
    <>
      <div className="title">{skill.name.de}</div>
      {skill.summary && <div className="sub">{skill.summary.de}</div>}
    </>
  );
}

function SkillBody({ step, skill, editable, onChange }: { step: SkillStep; skill: SkillManifest | undefined; editable: boolean; onChange: (s: Step) => void }) {
  if (!skill) return null;
  const conditions = untilConditions(step);
  const mode = step.until?.all ? "all" : "any";
  if (!editable) {
    const facts = Object.entries(step.with);
    return (
      <>
        {facts.length > 0 && (
          <div className="facts">
            {facts.map(([key, value]) => (
              <span key={key}>
                <span className="k">{tOr(`ui.${key}`, key)} </span>
                <b>{optionLabel(value, controlUnit(skill, key))}</b>
              </span>
            ))}
          </div>
        )}
        {conditions.length > 0 && (
          <div className="note until">{t("step.until", { conditions: describeConditions(conditions, mode) })}</div>
        )}
      </>
    );
  }
  return (
    <>
      {Object.keys(skill.ui).length > 0 && (
        <div className="fields">
          {Object.entries(skill.ui).map(([key, spec]) => (
            <UiControl key={key} name={key} onChange={(v) => onChange({ ...step, with: { ...step.with, [key]: v } })} spec={spec} value={step.with[key]} />
          ))}
        </div>
      )}
      <div className="note until">
        <span className="lead">{t("step.until.title")}</span>
        {conditions.length === 0 && <div className="empty">{t("step.until.none")}</div>}
        {conditions.map((c, i) => (
          <div className="row" key={i}>
            {i > 0 && <span className="or">{t("step.until.or")}</span>}
            <ConditionEditor condition={c} onChange={(nc) => onChange(setUntil(step, conditions.map((x, j) => (j === i ? nc : x))))} />
            <button className="iconbtn danger" onClick={() => onChange(setUntil(step, conditions.filter((_, j) => j !== i)))} title={t("step.remove")} type="button">✕</button>
          </div>
        ))}
        <div className="row">
          {(["speech", "elapsed", "signal"] as const).map((kind) => (
            <button className="chipbtn" key={kind} onClick={() => onChange(setUntil(step, [...conditions, newStopCondition(kind)]))} type="button">
              + {t(`step.until.add.${kind}`)}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

function PerceiveBody({ step, skills, editable, onChange }: { step: PerceiveStep; skills: Map<string, SkillManifest>; editable: boolean; onChange: (s: Step) => void }) {
  const onNone = step.on_none ?? null;
  if (!editable) {
    if (!onNone) return null;
    return (
      <div className="note branch">
        {t("step.on_none", {
          do: skills.get(onNone.do)?.name.de ?? onNone.do,
          seconds: onNone.seconds,
          then: t(`then.${onNone.then}`),
        })}
      </div>
    );
  }
  return (
    <>
      <div className="fields">
        <label className="field">
          <span>{t("step.perceive.what")}</span>
          <select onChange={(e) => onChange({ ...step, perceive: e.target.value })} value={step.perceive}>
            {PERCEIVE_QUERIES.map((q) => <option key={q} value={q}>{tOr(`perceive.${q}`, q)}</option>)}
          </select>
        </label>
      </div>
      <div className="note branch">
        <label className="inline">
          <input
            checked={onNone !== null}
            onChange={(e) => onChange(e.target.checked ? { ...step, on_none: { do: "look_around", seconds: 5, then: "retry" } } : { perceive: step.perceive })}
            type="checkbox"
          />
          <span className="lead">{t("step.on_none.toggle")}</span>
        </label>
        {onNone && (
          <div className="row">
            <span>{t("step.on_none.do")}</span>
            <select onChange={(e) => onChange({ ...step, on_none: { ...onNone, do: e.target.value } })} value={onNone.do}>
              {[...skills.values()].map((s) => <option key={s.id} value={s.id}>{s.name.de}</option>)}
            </select>
            <input max={600} min={1} onChange={(e) => onChange({ ...step, on_none: { ...onNone, seconds: Number(e.target.value) } })} type="number" value={onNone.seconds} />
            <span>{t("step.on_none.seconds")}</span>
            <select onChange={(e) => onChange({ ...step, on_none: { ...onNone, then: e.target.value as (typeof THEN_OPTIONS)[number] } })} value={onNone.then}>
              {THEN_OPTIONS.map((o) => <option key={o} value={o}>{t(`then.${o}`)}</option>)}
            </select>
          </div>
        )}
      </div>
    </>
  );
}
