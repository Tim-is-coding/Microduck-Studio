import { useCallback, useEffect, useRef, useState } from "react";
import { stringify } from "yaml";

import { phrases as phraseList, t, text, tOr, type Language } from "../i18n";
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
  setSummary,
  asksVlm,
  setAlwaysRule,
  setTrigger,
  setVlm,
  withVlmIfNeeded,
  speechTrigger,
  tidy,
} from "./model";
import { Icon } from "../ui/Icon";
import { StepEditor } from "./StepEditor";

interface Props {
  draft: BehaviorPack;
  isNew: boolean;
  lang: Language;
  skills: Map<string, SkillManifest>;
  problems: string[];
  notice: string | null;
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  saving: boolean;
  connected: boolean;
  onChange: (pack: BehaviorPack) => void;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onSaveAndRun: () => void;
  onDiscard: () => void;
  onDelete: () => void;
}

/** The visual editor (§3.1): every field on a card comes from the behavior schema or a
 *  skill manifest's `ui`; nothing here needs the YAML. */
export function BehaviorEditor({ draft, isNew, lang, skills, problems, notice, dirty, saving, connected, canUndo, canRedo, onChange, onUndo, onRedo, onSave, onSaveAndRun, onDiscard, onDelete }: Props) {
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
  // Strg+Z / Strg+Umschalt+Z for the draft. Inside a text field the browser's own text undo
  // is the better one, so leave that alone and let it handle the keys.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      e.preventDefault();
      if (e.shiftKey) onRedo();
      else onUndo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onRedo, onUndo]);
  const [phrases, setPhrases] = useState(
    draft.trigger.kind === "speech" ? phraseList(draft.trigger.phrases).join(", ") : "",
  );
  useEffect(() => {
    if (draft.trigger.kind === "speech") setPhrases(phraseList(draft.trigger.phrases).join(", "));
  }, [draft.id, draft.trigger]);
  // A draft you have just started is not broken, it is unfinished: the empty step list and the
  // empty name field each say so themselves, so the schema's English complaints about them are
  // noise until you have actually filled something in.
  const named = text(draft.name).trim().length > 0;
  const shownProblems = problems.filter(
    (p) => !(draft.steps.length === 0 && p.startsWith("steps:")) && !(!named && (p.startsWith("name") || p.startsWith("id:"))),
  );
  const canSave = named && Boolean(draft.id) && draft.steps.length > 0;
  const canStart = connected && canSave && problems.length === 0;
  const skillList = [...skills.values()];

  const add = (step: Parameters<typeof addStep>[1], at: number) => {
    onChange(withVlmIfNeeded(addStep(draft, step, at)));
    setInsertAt(null);
  };

  /** The chips that create a step, aimed at one gap in the list. */
  function AddButtons({ at }: { at: number }) {
    return (
      <>
        <button className="chip clickable" onClick={() => add(newPerceiveStep(), at)} type="button"><Icon name="eye" /> {t("editor.add.perceive")}</button>
        {skillList.map((s) => (
          <button className="chip clickable" key={s.id} onClick={() => add(newSkillStep(s), at)} type="button">+ {text(s.name)}</button>
        ))}
        <button className="chip clickable" onClick={() => add(newWaitStep(), at)} type="button"><Icon name="clock" /> {t("editor.add.wait")}</button>
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
            <Icon name="plus" size={0.9} title={t("editor.insert")} />
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="editor">
      <div className="runbar">
        <button className="btn primary" disabled={saving || !canSave} onClick={onSave} type="button">{saving ? t("editor.saving") : t("editor.save")}</button>
        <button className="btn" disabled={saving || !canStart} onClick={onSaveAndRun} type="button"><Icon name="play" /> {t("editor.save_run")}</button>
        <button className="btn icon-only" disabled={!canUndo} onClick={onUndo} title={t("editor.undo")} type="button"><Icon name="undo" title={t("editor.undo")} /></button>
        <button className="btn icon-only" disabled={!canRedo} onClick={onRedo} title={t("editor.redo")} type="button"><Icon name="redo" title={t("editor.redo")} /></button>
        <button className="btn" onClick={onDiscard} type="button">{t("editor.discard")}</button>
        {!isNew && <button className="btn danger-text" onClick={onDelete} type="button">{t("editor.delete")}</button>}
        {dirty && <span className="runstate">{t("editor.unsaved")}</span>}
      </div>

      {notice && <div className="card notice">{notice}</div>}

      {shownProblems.length > 0 && (
        <div className="card problems">
          <div className="title">{t("editor.problems")}</div>
          <ul>{shownProblems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      <div className="card">
        <label className="field">
          <span className="field-label">{t("editor.name")}</span>
          <input
            autoFocus={isNew && !named}
            onChange={(e) => onChange(renameBehavior(draft, e.target.value, !isNew, lang, isNew))}
            placeholder={t("editor.name.placeholder")}
            value={text(draft.name)}
          />
        </label>
        {draft.id ? <div className="sub">{t("editor.id")}: <code>{draft.id}</code></div> : <div className="sub">{t("editor.name.hint")}</div>}
        <label className="field">
          <span className="field-label">{t("editor.summary")}</span>
          <input onChange={(e) => onChange(setSummary(draft, e.target.value, lang))} value={text(draft.summary)} />
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
            lang={lang}
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
                  {skillList.map((s) => <option key={s.id} value={s.id}>{text(s.name)}</option>)}
                </select>
                <span>{t("editor.always.after")}</span>
                <select onChange={(e) => onChange(setAlwaysRule(draft, i, rule.on, skill, e.target.value))} value={after}>
                  {AFTER_ACTIONS.map((a) => <option key={a} value={a}>{t(`action.${a}`)}</option>)}
                </select>
              </span>
              <button className="danger-text" onClick={() => onChange(removeAlwaysRule(draft, i))} title={t("editor.always.remove")} type="button">
              <Icon name="close" title={t("editor.always.remove")} />
            </button>
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
