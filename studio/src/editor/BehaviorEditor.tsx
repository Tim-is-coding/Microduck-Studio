import { useCallback, useEffect, useRef, useState } from "react";
import { stringify } from "yaml";

import { t, tOr } from "../i18n";
import type { BehaviorPack, SkillManifest } from "../schemas";
import {
  AFTER_ACTIONS,
  SIGNALS,
  addAlwaysRule,
  addStep,
  moveStep,
  moveStepTo,
  newPerceiveStep,
  newSkillStep,
  newWaitStep,
  removeAlwaysRule,
  removeStep,
  renameBehavior,
  replaceStep,
  asksVlm,
  setAlwaysRule,
  setTrigger,
  setVlm,
  withVlmIfNeeded,
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
  const [insertAt, setInsertAt] = useState<number | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dropAt, setDropAt] = useState<number | null>(null);
  const stepsRef = useRef<HTMLDivElement | null>(null);
  const dropRef = useRef<number | null>(null); // what the pointerup handler reads

  /** Which gap is the pointer nearest? Gaps mark themselves with `data-gap`. */
  const gapNear = useCallback((clientY: number): number | null => {
    const root = stepsRef.current;
    if (!root) return null;
    let best: { at: number; distance: number } | null = null;
    for (const gap of root.querySelectorAll<HTMLElement>("[data-gap]")) {
      const box = gap.getBoundingClientRect();
      const distance = Math.abs(clientY - (box.top + box.height / 2));
      const at = Number(gap.dataset.gap);
      if (!best || distance < best.distance) best = { at, distance };
    }
    return best?.at ?? null;
  }, []);

  // Dragging a step is pointer-based on purpose: it works with a finger, it can be tested,
  // and the drop line is ours to draw. HTML5 drag-and-drop does none of those well.
  useEffect(() => {
    if (dragFrom === null) return;
    const move = (e: PointerEvent) => {
      e.preventDefault();
      const at = gapNear(e.clientY);
      dropRef.current = at;
      setDropAt(at);
    };
    const finish = () => {
      const at = dropRef.current;
      if (at !== null) onChange(moveStepTo(draft, dragFrom, at));
      dropRef.current = null;
      setDragFrom(null);
      setDropAt(null);
    };
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
    };
  }, [dragFrom, draft, gapNear, onChange]);
  const [phrases, setPhrases] = useState(draft.trigger.kind === "speech" ? draft.trigger.phrases.de.join(", ") : "");
  useEffect(() => {
    if (draft.trigger.kind === "speech") setPhrases(draft.trigger.phrases.de.join(", "));
  }, [draft.id, draft.trigger]);
  // An empty step list already shows its own hint; pydantic's English "at least 1 item" is noise.
  const shownProblems = draft.steps.length === 0 ? problems.filter((p) => !p.startsWith("steps:")) : problems;
  const canStart = connected && problems.length === 0 && draft.steps.length > 0;
  const skillList = [...skills.values()];

  const add = (step: Parameters<typeof addStep>[1], at: number) => {
    onChange(withVlmIfNeeded(addStep(draft, step, at)));
    setInsertAt(null);
  };

  /** The chips that create a step, aimed at one gap in the list. */
  function AddButtons({ at }: { at: number }) {
    return (
      <>
        <button className="chip clickable" onClick={() => add(newPerceiveStep(), at)} type="button">👁 {t("editor.add.perceive")}</button>
        {skillList.map((s) => (
          <button className="chip clickable" key={s.id} onClick={() => add(newSkillStep(s), at)} type="button">+ {s.name.de}</button>
        ))}
        <button className="chip clickable" onClick={() => add(newWaitStep(), at)} type="button">⏱ {t("editor.add.wait")}</button>
      </>
    );
  }

  /** The gap between two steps: drop a dragged step here, or add a new one in between. */
  function InsertRow({ at }: { at: number }) {
    const open = insertAt === at;
    const dragActive = dragFrom !== null;
    const over = dropAt === at && dragActive;
    return (
      <div
        className={`insert${open ? " open" : ""}${dragActive ? " dragging" : ""}${over ? " over" : ""}`}
        data-gap={at}
      >
        {open ? (
          <div className="insert-menu">
            <AddButtons at={at} />
            <button className="chip clickable" onClick={() => setInsertAt(null)} type="button">{t("editor.insert.cancel")}</button>
          </div>
        ) : (
          <button className="insert-open" onClick={() => setInsertAt(at)} title={t("editor.insert")} type="button">
            +
          </button>
        )}
      </div>
    );
  }

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
      <div className={`steps${dragFrom !== null ? " dragging" : ""}`} ref={stepsRef}>
      {draft.steps.map((step, i) => (
        <div key={i}>
          <InsertRow at={i} />
          <StepEditor
            count={draft.steps.length}
            dragging={dragFrom === i}
            index={i}
            onChange={(s) => onChange(withVlmIfNeeded(replaceStep(draft, i, s)))}
            onDragStart={(e) => {
              e.preventDefault();
              dropRef.current = null;
              setDragFrom(i);
            }}
            onMove={(d) => onChange(moveStep(draft, i, d))}
            onRemove={() => onChange(removeStep(draft, i))}
            skills={skills}
            step={step}
          />
        </div>
      ))}
      {draft.steps.length > 0 && <InsertRow at={draft.steps.length} />}
      </div>

      <div className="add-menu">
        <span className="field-label">{t("editor.add")}:</span>
        <AddButtons at={draft.steps.length} />
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
          <input
            checked={Boolean(draft.vlm)}
            disabled={asksVlm(draft)}
            onChange={(e) => onChange(setVlm(draft, e.target.checked ? "anthropic" : null))}
            type="checkbox"
          />
          <span className="field-label">{t("editor.vlm.toggle")}</span>
        </label>
        {asksVlm(draft) && <div className="sub">{t("editor.vlm.required")}</div>}
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
