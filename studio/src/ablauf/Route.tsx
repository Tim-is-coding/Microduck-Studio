import { useEffect, useState } from "react";
import { stringify } from "yaml";

import { t, tOr } from "../i18n";
import type { BehaviorPack, ExecutorStatus, SkillManifest } from "../schemas";
import {
  AFTER_ACTIONS,
  SIGNALS,
  addAlwaysRule,
  addStep,
  moveStep,
  removeAlwaysRule,
  removeStep,
  renameBehavior,
  replaceStep,
  setAlwaysRule,
  setTrigger,
  setVlm,
  speechTrigger,
  tidy,
} from "../editor/model";
import { useStudio } from "../store/useStudio";
import { AddStep } from "./AddStep";
import { StationCard } from "./StationCard";
import { actionLabel, describeSignal, describeTrigger, quoteAll } from "./describe";

/** The route: tabs, the run/edit toolbar and the rail of stations. Viewing and editing
 *  are the same cards; `editable` only turns the controls on. */
export function Route() {
  const s = useStudio();
  const skillMap = new Map(s.skills.map((k) => [k.id, k]));
  const connected = s.health?.connected ?? false;
  const draft = s.draft;
  const pack: BehaviorPack | null = draft ?? s.behaviors.find((b) => b.id === s.selectedBehaviorId) ?? null;
  const saved = draft ? null : (s.behaviors.find((b) => b.id === s.selectedBehaviorId) ?? null);
  const running = s.executor?.state === "running";
  const runningThis = running && s.executor?.behavior === pack?.id && !draft;
  const problems = draft ? s.draftProblems : (saved?.problems ?? []);
  const editable = draft !== null;
  const onChange = (next: BehaviorPack) => s.updateDraft(() => next);

  if (!pack) {
    return (
      <section className="route">
        <Tabs />
        <p className="empty-steps">{t("steps.empty")}</p>
      </section>
    );
  }

  return (
    <section className="route">
      <Tabs />
      {editable ? (
        <EditToolbar canStart={connected && problems.length === 0 && pack.steps.length > 0} />
      ) : (
        <RunToolbar connected={connected} executor={s.executor} pack={pack} running={running} runningThis={runningThis} />
      )}
      {!editable && <SayRow connected={connected} pack={pack} />}

      {editable && problems.length > 0 && !(pack.steps.length === 0 && problems.every((p) => p.startsWith("steps:"))) && (
        <div className="card problems" style={{ marginBottom: 14 }}>
          <div className="title" style={{ fontSize: 16 }}>{t("edit.problems")}</div>
          <ul>{problems.filter((p) => !(pack.steps.length === 0 && p.startsWith("steps:"))).map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      {editable && <NameCard draft={pack} isNew={s.draftIsNew} onChange={onChange} />}

      <div className="rail">
        <TriggerStation editable={editable} onChange={onChange} pack={pack} />

        {pack.steps.length === 0 && <p className="empty-steps">{t("steps.empty")}</p>}
        {pack.steps.map((step, i) => {
          const idx = s.executor?.step_index ?? -1;
          return (
            <StationCard
              active={runningThis && idx === i && !s.executor?.interrupt}
              count={pack.steps.length}
              done={(runningThis && idx > i) || (!draft && s.executor?.state === "done" && s.executor.behavior === pack.id)}
              editable={editable}
              index={i}
              key={i}
              onChange={(st) => onChange(replaceStep(pack, i, st))}
              onMove={(d) => onChange(moveStep(pack, i, d))}
              onRemove={() => onChange(removeStep(pack, i))}
              skills={skillMap}
              step={step}
            />
          );
        })}

        {editable && <AddStep onAdd={(st) => onChange(addStep(pack, st))} skills={s.skills} />}

        <AlwaysStation active={Boolean(runningThis && s.executor?.interrupt)} editable={editable} onChange={onChange} pack={pack} skills={skillMap} />
      </div>

      <details className="file">
        <summary>{t("yaml.title")}</summary>
        <pre>{draft ? stringify(tidy(draft)) : (s.yamlText ?? "…")}</pre>
      </details>
    </section>
  );
}

function Tabs() {
  const { behaviors, selectedBehaviorId, draft, draftIsNew, select, newDraft } = useStudio();
  return (
    <nav aria-label={t("tabs.title")} className="tabs">
      {behaviors.map((b) => (
        <button className={b.id === selectedBehaviorId && !draft ? "active" : ""} disabled={Boolean(draft)} key={b.id} onClick={() => select(b.id)} type="button">
          {b.name.de}
        </button>
      ))}
      {draft && draftIsNew && <button className="active" type="button">{draft.name.de || t("tabs.draft")}</button>}
      {!draft && <button className="new" onClick={newDraft} type="button">+ {t("tabs.new")}</button>}
    </nav>
  );
}

function RunToolbar({ pack, executor, connected, running, runningThis }: { pack: BehaviorPack; executor: ExecutorStatus | null; connected: boolean; running: boolean; runningThis: boolean }) {
  const { run, abortRun, editBehavior } = useStudio();
  const hasProblems = "problems" in pack && Array.isArray((pack as { problems?: string[] }).problems) && (pack as { problems: string[] }).problems.length > 0;
  return (
    <div className="toolbar">
      {runningThis ? (
        <button className="btn stop" onClick={() => void abortRun()} type="button">■ {t("run.stop")}</button>
      ) : (
        <button className="btn primary" disabled={!connected || running || hasProblems} onClick={() => void run(pack.id)} type="button">▶ {t("run.start")}</button>
      )}
      <span className={`hint${executor?.state === "failed" ? " warn" : ""}`}>{executorLabel(executor, pack.id)}</span>
      {!connected && <span className="hint">{t("run.needs_connection")}</span>}
      <span className="grow" />
      <button className="btn quiet" disabled={running} onClick={() => editBehavior(pack.id)} type="button">✎ {t("run.edit")}</button>
    </div>
  );
}

function EditToolbar({ canStart }: { canStart: boolean }) {
  const { draft, draftIsNew, draftDirty, saving, saveDraft, discardDraft, deleteBehavior } = useStudio();
  if (!draft) return null;
  return (
    <div className="toolbar">
      <button className="btn primary" disabled={saving || draft.steps.length === 0} onClick={() => void saveDraft(false)} type="button">{saving ? t("edit.saving") : t("edit.save")}</button>
      <button className="btn" disabled={saving || !canStart} onClick={() => void saveDraft(true)} type="button">▶ {t("edit.save_run")}</button>
      <button className="btn quiet" onClick={discardDraft} type="button">{t("edit.discard")}</button>
      {!draftIsNew && (
        <button
          className="btn danger"
          onClick={() => {
            if (window.confirm(t("edit.delete.confirm", { name: draft.name.de }))) void deleteBehavior(draft.id);
          }}
          type="button"
        >
          {t("edit.delete")}
        </button>
      )}
      <span className="grow" />
      {draftDirty && <span className="hint">{t("edit.unsaved")}</span>}
    </div>
  );
}

function SayRow({ pack, connected }: { pack: BehaviorPack; connected: boolean }) {
  const { say } = useStudio();
  const [phrase, setPhrase] = useState("");
  const submit = (text: string) => {
    const v = text.trim();
    if (!v) return;
    void say(v);
    setPhrase("");
  };
  const phrases = pack.trigger.kind === "speech" ? pack.trigger.phrases.de : [];
  return (
    <form
      className="sayrow"
      onSubmit={(e) => {
        e.preventDefault();
        submit(phrase);
      }}
    >
      <label htmlFor="say">{t("run.say")}</label>
      <input disabled={!connected} id="say" onChange={(e) => setPhrase(e.target.value)} placeholder={t("run.say.placeholder")} value={phrase} />
      <button className="btn small" disabled={!connected} type="submit">{t("run.say.button")}</button>
      <span className="phrases">
        {[...phrases, "Stopp"].map((p) => (
          <button className="phrase" disabled={!connected} key={p} onClick={() => submit(p)} type="button">„{p}“</button>
        ))}
      </span>
    </form>
  );
}

function NameCard({ draft, isNew, onChange }: { draft: BehaviorPack; isNew: boolean; onChange: (p: BehaviorPack) => void }) {
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="fields">
        <label className="field wide">
          <span>{t("edit.name")}</span>
          <input onChange={(e) => onChange(renameBehavior(draft, e.target.value, !isNew))} style={{ fontFamily: "var(--font-display)", fontSize: 20, fontWeight: 600 }} value={draft.name.de} />
        </label>
        <label className="field wide">
          <span>{t("edit.summary")}</span>
          <input onChange={(e) => onChange({ ...draft, summary: e.target.value ? { de: e.target.value } : undefined })} value={draft.summary?.de ?? ""} />
        </label>
        <label className="field inline wide">
          <input checked={Boolean(draft.vlm)} onChange={(e) => onChange(setVlm(draft, e.target.checked ? "anthropic" : null))} type="checkbox" />
          <span>{t("vlm.toggle")}</span>
          {draft.vlm && <input onChange={(e) => onChange(setVlm(draft, e.target.value || "anthropic"))} placeholder={t("vlm.provider")} value={draft.vlm.provider} />}
        </label>
      </div>
      {draft.vlm && <div className="vlm">{t("vlm.warning", { provider: draft.vlm.provider })}</div>}
      <div className="sub" style={{ marginTop: 8 }}>{t("edit.id")}: <code>{draft.id}.behavior.yaml</code></div>
    </div>
  );
}

function TriggerStation({ pack, editable, onChange }: { pack: BehaviorPack; editable: boolean; onChange: (p: BehaviorPack) => void }) {
  const [phrases, setPhrases] = useState(pack.trigger.kind === "speech" ? pack.trigger.phrases.de.join(", ") : "");
  useEffect(() => {
    if (pack.trigger.kind === "speech") setPhrases(pack.trigger.phrases.de.join(", "));
  }, [pack.id, pack.trigger]);
  return (
    <div className="station trigger">
      <div className="node">▶</div>
      <div className="card">
        {!editable ? (
          <>
            <div className="title">{t("trigger.title")}, {describeTrigger(pack.trigger)}</div>
            {pack.vlm && <div className="vlm">{t("vlm.badge", { provider: pack.vlm.provider })}</div>}
          </>
        ) : (
          <>
            <div className="title">{t("trigger.title")}</div>
            <div className="fields">
              <div className="field">
                <div className="seg">
                  <button className={pack.trigger.kind === "manual" ? "active" : ""} onClick={() => onChange(setTrigger(pack, { kind: "manual" }))} type="button">{t("trigger.choose.manual")}</button>
                  <button className={pack.trigger.kind === "speech" ? "active" : ""} onClick={() => onChange(setTrigger(pack, speechTrigger(phrases || "Los")))} type="button">{t("trigger.choose.speech")}</button>
                </div>
              </div>
              {pack.trigger.kind === "speech" && (
                <label className="field wide">
                  <span>{t("trigger.phrases")}</span>
                  <input onBlur={() => onChange(setTrigger(pack, speechTrigger(phrases)))} onChange={(e) => setPhrases(e.target.value)} value={phrases} />
                </label>
              )}
            </div>
            <div className="sub" style={{ marginTop: 8 }}>{describeTrigger(pack.trigger.kind === "speech" ? speechTrigger(phrases || "Los") : pack.trigger)}</div>
          </>
        )}
      </div>
    </div>
  );
}

function AlwaysStation({ pack, skills, editable, active, onChange }: { pack: BehaviorPack; skills: Map<string, SkillManifest>; editable: boolean; active: boolean; onChange: (p: BehaviorPack) => void }) {
  if (!editable && pack.always.length === 0) return null;
  const skillList = [...skills.values()];
  return (
    <div className={`station always${active ? " active" : ""}`}>
      <div className="node">!</div>
      <div className="card">
        <div className="title">{t("always.title")}</div>
        {!editable &&
          pack.always.map((rule, i) => (
            <div className="note" key={i}>
              {t("always.rule", { on: describeSignal(rule.on), do: rule.do.map((a) => actionLabel(a, skills)).join(", ") })}
            </div>
          ))}
        {editable && (
          <>
            {pack.always.length === 0 && <div className="sub">{t("always.none")}</div>}
            {pack.always.map((rule, i) => {
              const skill = rule.do.find((a) => skills.has(a)) ?? null;
              const after = rule.do.find((a) => (AFTER_ACTIONS as readonly string[]).includes(a)) ?? "resume";
              return (
                <div className="note" key={i}>
                  <div className="row">
                    <span>{t("always.on")}</span>
                    <select onChange={(e) => onChange(setAlwaysRule(pack, i, e.target.value, skill, after))} value={rule.on}>
                      {SIGNALS.map((sig) => <option key={sig} value={sig}>{tOr(`signal.${sig}`, sig)}</option>)}
                    </select>
                    <span>{t("always.do")}</span>
                    <select onChange={(e) => onChange(setAlwaysRule(pack, i, rule.on, e.target.value || null, after))} value={skill ?? ""}>
                      <option value="">–</option>
                      {skillList.map((sk) => <option key={sk.id} value={sk.id}>{sk.name.de}</option>)}
                    </select>
                    <span>{t("always.after")}</span>
                    <select onChange={(e) => onChange(setAlwaysRule(pack, i, rule.on, skill, e.target.value))} value={after}>
                      {AFTER_ACTIONS.map((a) => <option key={a} value={a}>{t(`action.${a}`)}</option>)}
                    </select>
                    <button className="iconbtn danger" onClick={() => onChange(removeAlwaysRule(pack, i))} title={t("step.remove")} type="button">✕</button>
                  </div>
                </div>
              );
            })}
            <div className="row" style={{ marginTop: 10 }}>
              <button className="chipbtn" onClick={() => onChange(addAlwaysRule(pack))} type="button">+ {t("always.add")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function executorLabel(executor: ExecutorStatus | null, behaviorId: string): string {
  if (!executor || executor.behavior !== behaviorId) return "";
  switch (executor.state) {
    case "running": {
      const base = t("run.state.running", { step: (executor.step_index ?? 0) + 1, count: executor.step_count });
      return executor.interrupt ? `${base} — ${t("run.interrupt", { on: describeSignal(executor.interrupt) })}` : base;
    }
    case "failed":
      return t("run.state.failed", { reason: executor.reason ?? "" });
    case "idle":
      return "";
    default:
      return t(`run.state.${executor.state}`);
  }
}

export { quoteAll };
