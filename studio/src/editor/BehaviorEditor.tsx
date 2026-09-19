import { useEffect, useState } from "react";
import { stringify } from "yaml";

import { t, tOr } from "../i18n";
import type { BehaviorPack, SkillManifest } from "../schemas";
import {
  AFTER_ACTIONS,
  SIGNALS,
  addAlwaysRule,
  addStep,
  moveStep,
  newPerceiveStep,
  newSkillStep,
  newWaitStep,
  removeAlwaysRule,
  removeStep,
  renameBehavior,
  replaceStep,
  setAlwaysRule,
  setTrigger,
  setVlm,
  speechTrigger,
  tidy,
} from "./model";
import { StepEditor } from "./StepEditor";

interface Props {
  draft: BehaviorPack;
  isNew: boolean;
  skills: Map<string, SkillManifest>;
  problems: string[];
  dirty: boolean;
  saving: boolean;
  connected: boolean;
  onChange: (pack: BehaviorPack) => void;
  onSave: () => void;
  onSaveAndRun: () => void;
  onDiscard: () => void;
  onDelete: () => void;
}

/** The visual editor (§3.1): every field on a card comes from the behavior schema or a
 *  skill manifest's `ui`; nothing here needs the YAML. */
export function BehaviorEditor({ draft, isNew, skills, problems, dirty, saving, connected, onChange, onSave, onSaveAndRun, onDiscard, onDelete }: Props) {
  const [showYaml, setShowYaml] = useState(false);
  const [phrases, setPhrases] = useState(draft.trigger.kind === "speech" ? draft.trigger.phrases.de.join(", ") : "");
  useEffect(() => {
    if (draft.trigger.kind === "speech") setPhrases(draft.trigger.phrases.de.join(", "));
  }, [draft.id, draft.trigger]);
  // An empty step list already shows its own hint; pydantic's English "at least 1 item" is noise.
  const shownProblems = draft.steps.length === 0 ? problems.filter((p) => !p.startsWith("steps:")) : problems;
  const canStart = connected && problems.length === 0 && draft.steps.length > 0;
  const skillList = [...skills.values()];

  return (
    <div className="editor">
      <div className="runbar">
        <button className="btn primary" disabled={saving || draft.steps.length === 0} onClick={onSave} type="button">{saving ? t("editor.saving") : t("editor.save")}</button>
        <button className="btn" disabled={saving || !canStart} onClick={onSaveAndRun} type="button">▶ {t("editor.save_run")}</button>
        <button className="btn" onClick={onDiscard} type="button">{t("editor.discard")}</button>
        {!isNew && <button className="btn danger-text" onClick={onDelete} type="button">{t("editor.delete")}</button>}
        {dirty && <span className="runstate">{t("editor.unsaved")}</span>}
      </div>

      {shownProblems.length > 0 && (
        <div className="card problems">
          <div className="title">{t("editor.problems")}</div>
          <ul>{shownProblems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      <div className="card">
        <label className="field">
          <span className="field-label">{t("editor.name")}</span>
          <input onChange={(e) => onChange(renameBehavior(draft, e.target.value, !isNew))} value={draft.name.de} />
        </label>
        <div className="sub">{t("editor.id")}: <code>{draft.id}</code></div>
        <label className="field">
          <span className="field-label">{t("editor.summary")}</span>
          <input onChange={(e) => onChange({ ...draft, summary: e.target.value ? { de: e.target.value } : undefined })} value={draft.summary?.de ?? ""} />
        </label>
      </div>

      <div className="step editing">
        <div className="num trigger">▶</div>
        <div className="card">
          <div className="field-label">{t("editor.trigger")}</div>
          <div className="seg">
            <button className={draft.trigger.kind === "manual" ? "active" : ""} onClick={() => onChange(setTrigger(draft, { kind: "manual" }))} type="button">{t("editor.trigger.kind.manual")}</button>
            <button className={draft.trigger.kind === "speech" ? "active" : ""} onClick={() => onChange(setTrigger(draft, speechTrigger(phrases || "Los")))} type="button">{t("editor.trigger.kind.speech")}</button>
          </div>
          {draft.trigger.kind === "speech" && (
            <label className="field">
              <span className="field-label">{t("editor.trigger.phrases")}</span>
              <input
                onBlur={() => onChange(setTrigger(draft, speechTrigger(phrases)))}
                onChange={(e) => setPhrases(e.target.value)}
                value={phrases}
              />
            </label>
          )}
        </div>
      </div>

      {draft.steps.length === 0 && <div className="sub empty">{t("editor.steps.empty")}</div>}
      {draft.steps.map((step, i) => (
        <StepEditor
          count={draft.steps.length}
          index={i}
          key={i}
          onChange={(s) => onChange(replaceStep(draft, i, s))}
          onMove={(d) => onChange(moveStep(draft, i, d))}
          onRemove={() => onChange(removeStep(draft, i))}
          skills={skills}
          step={step}
        />
      ))}

      <div className="add-menu">
        <span className="field-label">{t("editor.add")}:</span>
        <button className="chip clickable" onClick={() => onChange(addStep(draft, newPerceiveStep()))} type="button">👁 {t("editor.add.perceive")}</button>
        {skillList.map((s) => (
          <button className="chip clickable" key={s.id} onClick={() => onChange(addStep(draft, newSkillStep(s)))} type="button">+ {s.name.de}</button>
        ))}
        <button className="chip clickable" onClick={() => onChange(addStep(draft, newWaitStep()))} type="button">⏱ {t("editor.add.wait")}</button>
      </div>

      <div className="card">
        <div className="field-label">{t("editor.always")}</div>
        {draft.always.map((rule, i) => {
          const skill = rule.do.find((a) => skills.has(a)) ?? null;
          const after = rule.do.find((a) => (AFTER_ACTIONS as readonly string[]).includes(a)) ?? "resume";
          return (
            <div className="cond" key={i}>
              <span className="inline wrap">
                <span>{t("editor.always.on")}</span>
                <select onChange={(e) => onChange(setAlwaysRule(draft, i, e.target.value, skill, after))} value={rule.on}>
                  {SIGNALS.map((s) => <option key={s} value={s}>{tOr(`signal.${s}`, s)}</option>)}
                </select>
                <span>{t("editor.always.do")}</span>
                <select onChange={(e) => onChange(setAlwaysRule(draft, i, rule.on, e.target.value || null, after))} value={skill ?? ""}>
                  <option value="">–</option>
                  {skillList.map((s) => <option key={s.id} value={s.id}>{s.name.de}</option>)}
                </select>
                <span>{t("editor.always.after")}</span>
                <select onChange={(e) => onChange(setAlwaysRule(draft, i, rule.on, skill, e.target.value))} value={after}>
                  {AFTER_ACTIONS.map((a) => <option key={a} value={a}>{t(`action.${a}`)}</option>)}
                </select>
              </span>
              <button className="danger-text" onClick={() => onChange(removeAlwaysRule(draft, i))} type="button">✕</button>
            </div>
          );
        })}
        <button className="chip clickable" onClick={() => onChange(addAlwaysRule(draft))} type="button">{t("editor.always.add")}</button>
      </div>

      <div className={`card${draft.vlm ? " vlm-on" : ""}`}>
        <label className="field inline">
          <input checked={Boolean(draft.vlm)} onChange={(e) => onChange(setVlm(draft, e.target.checked ? "anthropic" : null))} type="checkbox" />
          <span className="field-label">{t("editor.vlm.toggle")}</span>
        </label>
        {draft.vlm && (
          <>
            <label className="field">
              <span className="field-label">{t("editor.vlm.provider")}</span>
              <input onChange={(e) => onChange(setVlm(draft, e.target.value || "anthropic"))} value={draft.vlm.provider} />
            </label>
            <div className="vlm">{t("editor.vlm", { provider: draft.vlm.provider })}</div>
          </>
        )}
      </div>

      <details className="yaml" onToggle={(e) => setShowYaml((e.target as HTMLDetailsElement).open)}>
        <summary>{t("editor.yaml")}</summary>
        {showYaml && <pre>{stringify(tidy(draft))}</pre>}
      </details>
    </div>
  );
}
