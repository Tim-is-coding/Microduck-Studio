import type { PointerEvent as ReactPointerEvent } from "react";

import { formatDuration, t, tOr, text, type Language } from "../i18n";
import { isPerceive, isSkill, isWait, type Check, type SkillManifest, type Step } from "../schemas";
import {
  CHECK_KINDS,
  PERCEIVE_QUERIES,
  THEN_OPTIONS,
  changeCheckKind,
  isAsk,
  isVlmQuery,
  readCheck,
  setLocalized,
  setOnlyIf,
  writeCheck,
  newStopCondition,
  setOnNone,
  setPerceiveQuery,
  setQuestion,
  setUntil,
  untilConditions,
} from "../editor/model";
import { Icon } from "../ui/Icon";
import { ConditionEditor, DurationInput, UiControl } from "./Controls";
import { controlUnit, describeCheck, describeConditions, optionLabel } from "./describe";

interface Props {
  index: number;
  count: number;
  step: Step;
  skills: Map<string, SkillManifest>;
  lang: Language;
  editable: boolean;
  active: boolean;
  done: boolean;
  /** its `only_if` said no in this run (ADR-0012) */
  skipped?: boolean;
  /** active, and its `only_if` is not settled yet */
  checking?: boolean;
  dragging: boolean;
  onChange: (step: Step) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
  onDragStart: (e: ReactPointerEvent) => void;
}

/** One station on the route: a step, viewed or edited in place. */
export function StationCard({ index, count, step, skills, lang, editable, active, done, skipped = false, checking = false, dragging, onChange, onMove, onRemove, onDragStart }: Props) {
  const cls = ["station", active ? "active" : "", done ? "done" : "", skipped ? "skipped" : "", editable ? "editing" : "", dragging ? "dragging" : ""].filter(Boolean).join(" ");
  const nodeTitle = skipped ? t("route.step.skipped") : done ? t("route.step.done") : undefined;
  return (
    <div className={cls}>
      <div className="node" title={nodeTitle}>{done && !skipped ? <Icon name="check" title={t("route.step.done")} /> : index + 1}</div>
      <div className="card">
        <div className="head">
          {editable && (
            <button className="handle" onPointerDown={onDragStart} title={t("route.drag")} type="button" aria-label={t("route.drag")}>⋮⋮</button>
          )}
          <div className="titles">
            {isSkill(step) && <SkillHead skill={skills.get(step.skill)} step={step} />}
            {isPerceive(step) && (
              <div className="title">
                {t("route.perceive", { what: isVlmQuery(step.perceive) && step.question ? text(step.question) : tOr(`perceive.${step.perceive}`, step.perceive) })}
              </div>
            )}
            {isWait(step) && <div className="title">{t("route.wait", { duration: formatDuration(step.wait) })}</div>}
          </div>
          {active && !editable && <span className="running"><span className="dot" />{t(checking ? "route.step.checking" : "route.step.running")}</span>}
          {skipped && !active && !editable && <span className="skipnote">{t("route.step.skipped")}</span>}
          {editable && (
            <div className="actions">
              <button className="iconbtn" disabled={index === 0} onClick={() => onMove(-1)} title={t("editor.step.up")} type="button">↑</button>
              <button className="iconbtn" disabled={index === count - 1} onClick={() => onMove(1)} title={t("editor.step.down")} type="button">↓</button>
              <button className="iconbtn danger" onClick={onRemove} title={t("editor.step.remove")} type="button"><Icon name="close" title={t("editor.step.remove")} /></button>
            </div>
          )}
        </div>
        {editable ? (
          <CheckEditor check={step.only_if ?? null} lang={lang} onChange={(c) => onChange(setOnlyIf(step, c))} />
        ) : (
          step.only_if && <CheckNote check={step.only_if} />
        )}
        {isSkill(step) && <SkillBody editable={editable} onChange={onChange} skill={skills.get(step.skill)} step={step} />}
        {isPerceive(step) && <PerceiveBody editable={editable} lang={lang} onChange={onChange} skills={skills} step={step} />}
        {isWait(step) && editable && (
          <div className="fields">
            <label className="field">
              <span>{t("route.wait.label")}</span>
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
  if (!skill) return <div className="title problem">{t("editor.step.unknown_skill", { id: step.skill })}</div>;
  return (
    <>
      <div className="title">{text(skill.name)}</div>
      {skill.summary && <div className="sub">{text(skill.summary)}</div>}
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
        {conditions.length > 0 && <div className="note until">{t("route.until", { conditions: describeConditions(conditions, mode) })}</div>}
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
        <span className="lead">{t("route.until.title")}</span>
        {conditions.length === 0 && <div className="empty">{t("route.until.none")}</div>}
        {conditions.map((c, i) => (
          <div className="row" key={i}>
            {i > 0 && <span className="or">{t("editor.until.or")}</span>}
            <ConditionEditor condition={c} onChange={(nc) => onChange(setUntil(step, conditions.map((x, j) => (j === i ? nc : x))))} />
            <button className="iconbtn danger" onClick={() => onChange(setUntil(step, conditions.filter((_, j) => j !== i)))} title={t("editor.until.remove")} type="button">
              <Icon name="close" title={t("editor.until.remove")} />
            </button>
          </div>
        ))}
        <div className="row">
          {(["speech", "elapsed", "signal"] as const).map((kind) => (
            <button className="chipbtn" key={kind} onClick={() => onChange(setUntil(step, [...conditions, newStopCondition(kind)]))} type="button">
              + {t(`route.until.add.${kind}`)}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

function PerceiveBody({ step, skills, lang, editable, onChange }: { step: PerceiveStep; skills: Map<string, SkillManifest>; lang: Language; editable: boolean; onChange: (s: Step) => void }) {
  const onNone = step.on_none ?? null;
  const vlm = isVlmQuery(step.perceive);
  if (!editable) {
    return (
      <>
        {vlm && <div className="vlm">{t("editor.perceive.question.hint")}</div>}
        {onNone && (
          <div className="note branch">
            {t("route.on_none", {
              do: text(skills.get(onNone.do)?.name, onNone.do),
              seconds: onNone.seconds,
              then: t(`then.${onNone.then}`),
            })}
          </div>
        )}
      </>
    );
  }
  return (
    <>
      <div className="fields">
        <label className="field">
          <span>{t("route.perceive.what")}</span>
          <select onChange={(e) => onChange(setPerceiveQuery(step, e.target.value, lang))} value={step.perceive}>
            {PERCEIVE_QUERIES.map((q) => <option key={q} value={q}>{tOr(`perceive.${q}`, q)}</option>)}
          </select>
        </label>
        {vlm && (
          <label className="field wide">
            <span>{t("route.perceive.question")}</span>
            <input onChange={(e) => onChange(setQuestion(step, e.target.value, lang))} placeholder={t("editor.perceive.question.placeholder")} value={text(step.question)} />
          </label>
        )}
      </div>
      {vlm && <div className="vlm">{t("editor.perceive.question.hint")}</div>}
      <div className="note branch">
        <label className="inline">
          <input
            checked={onNone !== null}
            onChange={(e) => onChange(setOnNone(step, e.target.checked ? { do: "look_around", seconds: 5, then: "retry" } : null))}
            type="checkbox"
          />
          <span className="lead">{t("route.on_none.title")}</span>
        </label>
        {onNone && (
          <div className="row">
            <span>{t("route.on_none.do")}</span>
            <select onChange={(e) => onChange({ ...step, on_none: { ...onNone, do: e.target.value } })} value={onNone.do}>
              {[...skills.values()].map((s) => <option key={s.id} value={s.id}>{text(s.name)}</option>)}
            </select>
            <input max={600} min={1} onChange={(e) => onChange({ ...step, on_none: { ...onNone, seconds: Number(e.target.value) } })} type="number" value={onNone.seconds} />
            <span>{t("route.on_none.seconds")}</span>
            <select onChange={(e) => onChange({ ...step, on_none: { ...onNone, then: e.target.value as (typeof THEN_OPTIONS)[number] } })} value={onNone.then}>
              {THEN_OPTIONS.map((o) => <option key={o} value={o}>{t(`then.${o}`)}</option>)}
            </select>
          </div>
        )}
      </div>
    </>
  );
}

function CheckNote({ check }: { check: Check }) {
  return (
    <>
      <div className="note check">{t("route.only_if", { clause: describeCheck(check) })}</div>
      {isAsk(check) && <div className="vlm">{t("editor.perceive.question.hint")}</div>}
    </>
  );
}

const CHECK_LIMITS: Record<string, { min: number; max: number; unit: string }> = {
  obstacle: { min: 10, max: 300, unit: "route.only_if.cm" },
  clear: { min: 10, max: 300, unit: "route.only_if.cm" },
  battery: { min: 5, max: 95, unit: "route.only_if.percent" },
};

/** „Nur wenn …“: a side branch that decides whether the step runs at all (ADR-0012). */
function CheckEditor({ check, lang, onChange }: { check: Check | null; lang: Language; onChange: (c: Check | null) => void }) {
  const form = check ? readCheck(check) : null;
  const limits = form ? CHECK_LIMITS[form.kind] : undefined;
  const ask = form?.kind === "ask_yes" || form?.kind === "ask_no";
  return (
    <div className="note check">
      <label className="inline">
        <input checked={check !== null} onChange={(e) => onChange(e.target.checked ? writeCheck({ kind: "someone" }, lang) : null)} type="checkbox" />
        <span className="lead">{t("route.only_if.title")}</span>
      </label>
      {check && form && (
        <>
          <div className="row">
            <select aria-label={t("route.only_if.title")} onChange={(e) => onChange(changeCheckKind(check, e.target.value as (typeof CHECK_KINDS)[number], lang))} value={form.kind}>
              {CHECK_KINDS.map((k) => <option key={k} value={k}>{t(`check.kind.${k}`)}</option>)}
              {form.kind === "other" && <option value="other">{describeCheck(check)}</option>}
            </select>
            {limits && (
              <>
                <input
                  aria-label={t(limits.unit)}
                  max={limits.max}
                  min={limits.min}
                  onChange={(e) => {
                    const amount = Math.min(limits.max, Math.max(limits.min, Math.round(Number(e.target.value) || limits.min)));
                    onChange(writeCheck({ ...form, amount }, lang));
                  }}
                  type="number"
                  value={form.amount ?? ""}
                />
                <span>{t(limits.unit)}</span>
              </>
            )}
          </div>
          {ask && (
            <label className="field wide">
              <span>{t("route.only_if.question")}</span>
              <input
                onChange={(e) => onChange(writeCheck({ ...form, question: setLocalized(form.question, e.target.value, lang) ?? { de: e.target.value } }, lang))}
                value={text(form.question)}
              />
            </label>
          )}
          <div className="sub">{t("route.only_if.else")}</div>
          {ask && <div className="vlm">{t("editor.perceive.question.hint")}</div>}
        </>
      )}
    </div>
  );
}
