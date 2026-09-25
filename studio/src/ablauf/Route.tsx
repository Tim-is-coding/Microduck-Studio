import { useCallback, useEffect, useRef, useState } from "react";
import { stringify } from "yaml";

import { language, phrases as phraseList, quote, t, text, tOr } from "../i18n";
import type { AiInfo, BehaviorPack, BehaviorPackFromApi, ExecutorStatus, SkillManifest, Step } from "../schemas";
import {
  DEFAULT_VLM_PROVIDER,
  AFTER_ACTIONS,
  SIGNALS,
  addAlwaysRule,
  addStep,
  asksVlm,
  moveStep,
  moveStepTo,
  removeAlwaysRule,
  removeStep,
  renameBehavior,
  replaceStep,
  setAlwaysRule,
  setSummary,
  setTrigger,
  setVlm,
  speechTrigger,
  tidy,
  withVlmIfNeeded,
} from "../editor/model";
import { BehaviorList } from "../editor/BehaviorList";
import { DraftWithAi } from "../editor/DraftWithAi";
import { templatesFor } from "../editor/templates";
import { AiVendors } from "../ai/AiVendors";
import { Blocks } from "../skills/Blocks";
import { useStudio } from "../store/useStudio";
import { Icon } from "../ui/Icon";
import { AddStepPicker } from "./AddStep";
import { SayRow } from "./SayRow";
import { StationCard } from "./StationCard";
import { actionLabel, describeSignal, describeTrigger } from "./describe";

/** The route: tabs, the run/edit toolbar and the rail of stations. Viewing and editing
 *  are the same cards; `editable` only turns the controls on. */
export function Route() {
  const s = useStudio();
  // A page beside the behaviors: the building blocks, or the AI vendors (ADR-0009).
  const [page, setPage] = useState<"blocks" | "ai" | null>(null);
  const blocksOpen = page !== null;
  const lang = language();
  const skillMap = new Map(s.skills.map((k) => [k.id, k]));
  const connected = s.health?.connected ?? false;
  const offline = s.runtime === "offline";
  const draft = s.draft;
  const saved: BehaviorPackFromApi | null = draft ? null : (s.behaviors.find((b) => b.id === s.selectedBehaviorId) ?? null);
  const pack: BehaviorPack | null = draft ?? saved;
  const running = s.executor?.state === "running";
  const runningThis = running && s.executor?.behavior === pack?.id && !draft;
  const editable = draft !== null;
  const hub = {
    hubResults: s.hubResults,
    hubBusy: s.hubBusy,
    hubError: s.hubError,
    onSearch: (q: string) => void s.searchHub(q),
    onClear: s.clearHub,
    onDetails: s.policyDetails,
    onImport: (repo: string, slot: string) => void s.importPolicy(repo, slot),
  };

  const open = (id: string | null) => {
    setPage(null);
    s.select(id);
  };

  return (
    <section className="route">
      <nav aria-label={t("list.overview")} className="tabs">
        <button className={!s.selectedBehaviorId && !draft && !blocksOpen ? "active" : ""} disabled={Boolean(draft)} onClick={() => open(null)} type="button">
          {t("list.overview")}
        </button>
        {s.behaviors.map((b) => (
          <button className={b.id === s.selectedBehaviorId && !draft && !blocksOpen ? "active" : ""} disabled={Boolean(draft)} key={b.id} onClick={() => open(b.id)} type="button">
            {text(b.name)}
          </button>
        ))}
        {draft && s.draftIsNew && <button className="active" type="button">{text(draft.name) || t("route.new")}</button>}

        {!draft && <button className="new" onClick={() => { setPage(null); s.newDraft(); }} type="button">+ {t("route.new")}</button>}

        <span className="spacer" />

        <button className={`tool${page === "blocks" && !draft ? " active" : ""}`} disabled={Boolean(draft)} onClick={() => { s.select(null); setPage("blocks"); }} type="button">

          {t("route.tab.blocks")}

        </button>

        <button className={`tool${page === "ai" && !draft ? " active" : ""}`} disabled={Boolean(draft)} onClick={() => { s.select(null); setPage("ai"); }} type="button">

          {t("route.tab.ai")}

        </button>
      </nav>

      {offline && <OfflineCard />}

      {!draft && page === "ai" && <AiVendors offline={offline} />}
      {!draft && page === "blocks" && !offline && (
        <Blocks offline={offline} onRemove={(id) => void s.removeSkill(id)} skills={s.skills} {...hub} />
      )}

      {!draft && !blocksOpen && !saved && !offline && (
        <BehaviorList
          behaviors={s.behaviors}
          connected={connected}
          onDraft={(p, notice) => s.newDraft(p, notice)}
          onNew={() => s.newDraft()}
          onOpen={open}
          onRun={(id) => void s.run(id)}
          running={running}
          skills={skillMap}
          templates={templatesFor(skillMap)}
        />
      )}
      {!draft && !blocksOpen && !saved && !offline && (
        <DraftWithAi onDraft={(p, notice) => s.newDraft(p, notice)} onSetUp={() => { s.select(null); setPage("ai"); }} />
      )}

      {pack && !blocksOpen && (
        <RouteView
          connected={connected}
          draft={draft}
          editable={editable}
          executor={s.executor}
          hub={hub}
          lang={lang}
          pack={pack}
          runningThis={runningThis}
          saved={saved}
          skillMap={skillMap}
          skills={s.skills}
        />
      )}
    </section>
  );
}

interface RouteViewProps {
  pack: BehaviorPack;
  saved: BehaviorPackFromApi | null;
  draft: BehaviorPack | null;
  editable: boolean;
  connected: boolean;
  executor: ExecutorStatus | null;
  runningThis: boolean;
  lang: ReturnType<typeof language>;
  skills: SkillManifest[];
  skillMap: Map<string, SkillManifest>;
  hub: Parameters<typeof AddStepPicker>[0] extends infer P ? Omit<P, "skills" | "onAdd" | "onClose"> : never;
}

function RouteView({ pack, saved, draft, editable, connected, executor, runningThis, lang, skills, skillMap, hub }: RouteViewProps) {
  const s = useStudio();
  const [insertAt, setInsertAt] = useState<number | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dropAt, setDropAt] = useState<number | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const dropRef = useRef<number | null>(null);
  const onChange = (next: BehaviorPack) => s.updateDraft(() => next);
  const running = executor?.state === "running";

  // A freshly started draft is unfinished, not broken: hide the schema's complaints about the
  // empty step list and the empty name until something has been typed.
  const named = text(pack.name).trim().length > 0;
  const rawProblems = draft ? s.draftProblems : (saved?.problems ?? []);
  const problems = editable
    ? rawProblems.filter((p) => !(pack.steps.length === 0 && p.startsWith("steps:")) && !(!named && (p.startsWith("name") || p.startsWith("id:"))))
    : rawProblems;
  const canSave = named && Boolean(pack.id) && pack.steps.length > 0;
  const canStart = connected && canSave && rawProblems.length === 0;

  /** Which gap is the pointer nearest? Gaps mark themselves with `data-gap`. */
  const gapNear = useCallback((clientY: number): number | null => {
    const root = railRef.current;
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

  // Dragging a station is pointer-based on purpose: it works with a finger and the drop line
  // is ours to draw.
  useEffect(() => {
    if (dragFrom === null || !draft) return;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragFrom, draft, gapNear]);

  // Ctrl/Cmd+Z and Shift for the draft; inside a text field the browser's own undo wins.
  useEffect(() => {
    if (!editable) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      e.preventDefault();
      if (e.shiftKey) s.redoDraft();
      else s.undoDraft();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editable, s]);

  const add = (step: Step, at: number) => {
    onChange(withVlmIfNeeded(addStep(pack, step, at)));
    setInsertAt(null);
  };

  const idx = executor?.step_index ?? -1;
  const allDone = !draft && executor?.state === "done" && executor.behavior === pack.id;

  return (
    <>
      {editable ? (
        <div className="toolbar">
          <button className="btn primary" disabled={s.saving || !canSave} onClick={() => void s.saveDraft(false)} type="button">{s.saving ? t("editor.saving") : t("editor.save")}</button>
          <button className="btn" disabled={s.saving || !canStart} onClick={() => void s.saveDraft(true)} type="button"><Icon name="play" /> {t("editor.save_run")}</button>
          <button className="iconbtn" disabled={s.history.past.length === 0} onClick={s.undoDraft} title={t("editor.undo")} type="button"><Icon name="undo" title={t("editor.undo")} /></button>
          <button className="iconbtn" disabled={s.history.future.length === 0} onClick={s.redoDraft} title={t("editor.redo")} type="button"><Icon name="redo" title={t("editor.redo")} /></button>
          <button className="btn quiet" onClick={s.discardDraft} type="button">{t("editor.discard")}</button>
          {!s.draftIsNew && (
            <button
              className="btn danger"
              onClick={() => {
                if (window.confirm(t("editor.delete.confirm", { name: text(pack.name) }))) void s.deleteBehavior(pack.id);
              }}
              type="button"
            >
              {t("editor.delete")}
            </button>
          )}
          <span className="grow" />
          {s.draftDirty && <span className="hint">{t("editor.unsaved")}</span>}
        </div>
      ) : (
        <div className="toolbar">
          {runningThis ? (
            <button className="btn stop" onClick={() => void s.abortRun()} type="button"><Icon name="stop" /> {t("run.abort")}</button>
          ) : (
            <button className="btn primary" disabled={!connected || running || rawProblems.length > 0} onClick={() => void s.run(pack.id)} type="button"><Icon name="play" /> {t("run.start")}</button>
          )}
          <span className={`hint${executor?.state === "failed" && executor.behavior === pack.id ? " warn" : ""}`}>{executorLabel(executor, pack.id)}</span>
          {!connected && <span className="hint">{t("run.needs_connection")}</span>}
          <span className="grow" />
          <button className="btn quiet" disabled={running} onClick={() => s.editBehavior(pack.id)} type="button"><Icon name="pencil" /> {t("editor.edit")}</button>
        </div>
      )}

      {!editable && <SayRow connected={connected} pack={pack} />}
      {editable && s.draftNotice && <div className="card notice">{s.draftNotice}</div>}
      {problems.length > 0 && (
        <div className="card problems">
          <div className="title">{t("editor.problems")}</div>
          <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      {editable && (
        <div className="card namecard">
          <label className="field wide">
            <span>{t("editor.name")}</span>
            <input
              autoFocus={s.draftIsNew && !named}
              className="name"
              onChange={(e) => onChange(renameBehavior(pack, e.target.value, !s.draftIsNew, lang, s.draftIsNew))}
              placeholder={t("editor.name.placeholder")}
              value={text(pack.name)}
            />
          </label>
          <label className="field wide">
            <span>{t("editor.summary")}</span>
            <input onChange={(e) => onChange(setSummary(pack, e.target.value, lang))} value={text(pack.summary)} />
          </label>
          <div className="sub">{pack.id ? <>{t("editor.id")}: <code>{pack.id}.behavior.yaml</code></> : t("editor.name.hint")}</div>
        </div>
      )}

      <div className={`rail${dragFrom !== null ? " dragging" : ""}`} ref={railRef}>
        <TriggerStation editable={editable} onChange={onChange} pack={pack} />

        {pack.steps.length === 0 && editable && <p className="empty-steps">{t("route.steps.empty")}</p>}
        {pack.steps.map((step, i) => (
          <div key={i}>
            {editable && <Gap at={i} dragging={dragFrom !== null} onOpen={() => setInsertAt(i)} open={insertAt === i} over={dropAt === i && dragFrom !== null}>
              {insertAt === i && <AddStepPicker onAdd={(st) => add(st, i)} onClose={() => setInsertAt(null)} skills={skills} {...hub} />}
            </Gap>}
            <StationCard
              active={runningThis && idx === i && !executor?.interrupt}
              count={pack.steps.length}
              done={(runningThis && idx > i) || allDone}
              dragging={dragFrom === i}
              editable={editable}
              index={i}
              lang={lang}
              onChange={(st) => onChange(withVlmIfNeeded(replaceStep(pack, i, st)))}
              onDragStart={(e) => {
                e.preventDefault();
                dropRef.current = null;
                setDragFrom(i);
              }}
              onMove={(d) => onChange(moveStep(pack, i, d))}
              onRemove={() => onChange(removeStep(pack, i))}
              skills={skillMap}
              step={step}
            />
          </div>
        ))}

        {editable && (
          <div className={`station add${dropAt === pack.steps.length && dragFrom !== null ? " over" : ""}`} data-gap={pack.steps.length}>
            {insertAt === pack.steps.length ? (
              <div className="card">
                <AddStepPicker onAdd={(st) => add(st, pack.steps.length)} onClose={() => setInsertAt(null)} skills={skills} {...hub} />
              </div>
            ) : (
              <button className="card addbtn" onClick={() => setInsertAt(pack.steps.length)} type="button">
                <Icon name="plus" /> {t("route.add")}
              </button>
            )}
          </div>
        )}

        <AlwaysStation active={Boolean(runningThis && executor?.interrupt)} editable={editable} onChange={onChange} pack={pack} skills={skillMap} />

        {editable && (
          <div className="station vlmstation">
            <div className="node">{t("route.node.ai")}</div>
            <div className={`card${pack.vlm ? " vlm-on" : ""}`}>
              <label className="field inline">
                <input checked={Boolean(pack.vlm)} disabled={asksVlm(pack)} onChange={(e) => onChange(setVlm(pack, e.target.checked ? preferredVendor(s.ai) : null))} type="checkbox" />
                <span>{t("editor.vlm.toggle")}</span>
              </label>
              {pack.vlm && <VendorSelect ai={s.ai} onPick={(id) => onChange(setVlm(pack, id))} value={pack.vlm.provider} />}
              {asksVlm(pack) && <div className="sub">{t("editor.vlm.required")}</div>}
              {pack.vlm && <div className="vlm">{t("editor.vlm", { provider: tOr(`vlm.provider.${pack.vlm.provider}`, pack.vlm.provider) })}</div>}
            </div>
          </div>
        )}
      </div>

      <details className="file">
        <summary>{t("route.file")}</summary>
        <pre>{draft ? stringify(tidy(draft)) : (s.yamlText ?? "…")}</pre>
      </details>
    </>
  );
}

/** The gap between two stations: drop a dragged station here, or open the picker to insert. */
function Gap({ at, open, over, dragging, onOpen, children }: { at: number; open: boolean; over: boolean; dragging: boolean; onOpen: () => void; children?: React.ReactNode }) {
  return (
    <div className={`gap${open ? " open" : ""}${dragging ? " dragging" : ""}${over ? " over" : ""}`} data-gap={at}>
      {open ? (
        <div className="card">{children}</div>
      ) : (
        <button className="gapbtn" onClick={onOpen} title={t("route.add.here")} type="button" aria-label={t("route.add.here")}>+</button>
      )}
    </div>
  );
}

function TriggerStation({ pack, editable, onChange }: { pack: BehaviorPack; editable: boolean; onChange: (p: BehaviorPack) => void }) {
  const [phrases, setPhrases] = useState(pack.trigger.kind === "speech" ? phraseList(pack.trigger.phrases).join(", ") : "");
  useEffect(() => {
    if (pack.trigger.kind === "speech") setPhrases(phraseList(pack.trigger.phrases).join(", "));
  }, [pack.id, pack.trigger]);
  return (
    <div className="station trigger">
      <div className="node">{t("route.node.start")}</div>
      <div className="card">
        {!editable ? (
          <>
            <div className="title">{t("route.trigger.title")}, {describeTrigger(pack.trigger)}</div>
            {pack.vlm && <div className="vlm">{t("route.vlm.badge", { provider: tOr(`vlm.provider.${pack.vlm.provider}`, pack.vlm.provider) })}</div>}
          </>
        ) : (
          <>
            <div className="title">{t("route.trigger.title")}</div>
            <div className="fields">
              <div className="field">
                <div className="seg">
                  <button className={pack.trigger.kind === "manual" ? "active" : ""} onClick={() => onChange(setTrigger(pack, { kind: "manual" }))} type="button">{t("route.trigger.choose.manual")}</button>
                  <button className={pack.trigger.kind === "speech" ? "active" : ""} onClick={() => onChange(setTrigger(pack, speechTrigger(phrases || "Los")))} type="button">{t("route.trigger.choose.speech")}</button>
                </div>
              </div>
              {pack.trigger.kind === "speech" && (
                <label className="field wide">
                  <span>{t("editor.trigger.phrases")}</span>
                  <input onBlur={() => onChange(setTrigger(pack, speechTrigger(phrases)))} onChange={(e) => setPhrases(e.target.value)} value={phrases} />
                </label>
              )}
            </div>
            <div className="sub">{describeTrigger(pack.trigger.kind === "speech" ? speechTrigger(phrases || "Los") : pack.trigger)}</div>
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
      <div className="node">{t("route.node.always")}</div>
      <div className="card">
        <div className="title">{t("route.always.title")}</div>
        {!editable &&
          pack.always.map((rule, i) => (
            <div className="note" key={i}>
              {t("route.always.rule", { on: describeSignal(rule.on), do: rule.do.map((a) => actionLabel(a, skills)).join(", ") })}
            </div>
          ))}
        {editable && (
          <>
            {pack.always.length === 0 && <div className="sub">{t("route.always.none")}</div>}
            {pack.always.map((rule, i) => {
              const skill = rule.do.find((a) => skills.has(a)) ?? null;
              const after = rule.do.find((a) => (AFTER_ACTIONS as readonly string[]).includes(a)) ?? "resume";
              return (
                <div className="note" key={i}>
                  <div className="row">
                    <span>{t("editor.always.on")}</span>
                    <select onChange={(e) => onChange(setAlwaysRule(pack, i, e.target.value, skill, after))} value={rule.on}>
                      {SIGNALS.map((sig) => <option key={sig} value={sig}>{tOr(`signal.${sig}`, sig)}</option>)}
                    </select>
                    <span>{t("editor.always.do")}</span>
                    <select onChange={(e) => onChange(setAlwaysRule(pack, i, rule.on, e.target.value || null, after))} value={skill ?? ""}>
                      <option value="">–</option>
                      {skillList.map((sk) => <option key={sk.id} value={sk.id}>{text(sk.name)}</option>)}
                    </select>
                    <span>{t("editor.always.after")}</span>
                    <select onChange={(e) => onChange(setAlwaysRule(pack, i, rule.on, skill, e.target.value))} value={after}>
                      {AFTER_ACTIONS.map((a) => <option key={a} value={a}>{t(`action.${a}`)}</option>)}
                    </select>
                    <button className="iconbtn danger" onClick={() => onChange(removeAlwaysRule(pack, i))} title={t("editor.always.remove")} type="button"><Icon name="close" title={t("editor.always.remove")} /></button>
                  </div>
                </div>
              );
            })}
            <div className="row">
              <button className="chipbtn" onClick={() => onChange(addAlwaysRule(pack))} type="button">+ {t("route.always.add")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function OfflineCard() {
  return (
    <div className="card offline">
      <div className="title">{t("offline.title")}</div>
      <p>{t("offline.body")}</p>
      <p className="sub">{t("offline.start")} <code>cd runtime &amp;&amp; uv run python -m duckstudio</code></p>
    </div>
  );
}

function executorLabel(executor: ExecutorStatus | null, behaviorId: string): string {
  if (!executor || executor.behavior !== behaviorId || executor.state === "idle") return "";
  if (executor.state === "running") {
    const base = t("route.running", { step: (executor.step_index ?? 0) + 1, count: executor.step_count });
    return executor.interrupt ? `${base} — ${t("run.interrupt", { on: describeSignal(executor.interrupt) })}` : base;
  }
  const label = t(`run.state.${executor.state}`);
  return executor.reason ? `${label}: ${text(executor.reason)}` : label;
}

/** The vendor a new opt-in names: one that has a key, else the recommended one (ADR-0009). */
function preferredVendor(ai: AiInfo | null): string {
  const vendors = ai?.vendors ?? [];
  return (vendors.find((v) => v.key) ?? vendors.find((v) => v.recommended) ?? vendors[0])?.id ?? DEFAULT_VLM_PROVIDER;
}

function VendorSelect({ ai, value, onPick }: { ai: AiInfo | null; value: string; onPick: (id: string) => void }) {
  const { loadAi } = useStudio();
  useEffect(() => {
    if (!ai) void loadAi();
  }, [ai, loadAi]);
  const vendors = ai?.vendors ?? [];
  const known = vendors.some((v) => v.id === value);
  return (
    <label className="field">
      <span>{t("editor.vlm.choose")}</span>
      <select className="provider" onChange={(e) => onPick(e.target.value)} value={value}>
        {vendors.map((v) => (
          <option key={v.id} value={v.id}>
            {v.label}
            {v.key ? "" : ` (${t("editor.vlm.nokey")})`}
          </option>
        ))}
        {!known && <option value={value}>{value}</option>}
      </select>
    </label>
  );
}
