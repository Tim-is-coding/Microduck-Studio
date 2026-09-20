import { useEffect, useMemo, useState } from "react";

import { BehaviorEditor } from "./editor/BehaviorEditor";
import { BehaviorList } from "./editor/BehaviorList";
import { templatesFor } from "./editor/templates";
import { StepList } from "./editor/StepList";
import { language, phrases as phraseList, quote, t, text, useLanguage } from "./i18n";
import { LivePanel } from "./live/LivePanel";
import { SkillPanel } from "./skills/SkillPanel";
import { Icon } from "./ui/Icon";
import { LanguageSwitch } from "./ui/LanguageSwitch";
import { ThemeSwitch } from "./ui/ThemeSwitch";
import { connectEvents, useStudio } from "./store/useStudio";

const HEALTH_INTERVAL_MS = 2000;
const STATE_INTERVAL_MS = 500;

export function App() {
  const {
    runtime, health, state, executor, skills, behaviors, selectedBehaviorId, events,
    draft, draftIsNew, draftDirty, draftProblems, saving, yamlText, hubResults, hubBusy, hubError,
    refreshHealth, refreshState, refreshExecutor, loadCatalog, select, stop, run, abortRun, say,
    editBehavior, newDraft, updateDraft, validateDraft, saveDraft, discardDraft, deleteBehavior, loadYaml,
    searchHub, clearHub, policyDetails, importPolicy, removeSkill,
  } = useStudio();
  const [phrase, setPhrase] = useState("");
  useLanguage(); // re-render the whole Studio when the language changes

  // live validation while editing, debounced
  useEffect(() => {
    if (!draft) return;
    const id = setTimeout(() => void validateDraft(), 300);
    return () => clearTimeout(id);
  }, [draft, validateDraft]);

  // developer view for the selected (saved) behavior
  useEffect(() => {
    if (selectedBehaviorId && !draft) void loadYaml(selectedBehaviorId);
  }, [selectedBehaviorId, draft, behaviors, loadYaml]);

  useEffect(() => {
    void refreshHealth();
    void loadCatalog();
    const id = setInterval(() => void refreshHealth(), HEALTH_INTERVAL_MS);
    const stateId = setInterval(() => {
      void refreshState();
      void refreshExecutor();
    }, STATE_INTERVAL_MS);
    const disconnect = connectEvents();
    return () => {
      clearInterval(id);
      clearInterval(stateId);
      disconnect();
    };
  }, [refreshHealth, refreshState, refreshExecutor, loadCatalog]);

  const skillMap = useMemo(() => new Map(skills.map((s) => [s.id, s])), [skills]);
  const selected = draft ? null : (behaviors.find((b) => b.id === selectedBehaviorId) ?? null);
  const connected = health?.connected ?? false;
  const running = executor?.state === "running";
  const runningSelected = running && executor?.behavior === selected?.id;
  const triggerPhrases = selected?.trigger.kind === "speech" ? phraseList(selected.trigger.phrases) : [];
  const submitPhrase = (text: string) => {
    const t = text.trim();
    if (!t) return;
    void say(t);
    setPhrase("");
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>{t("app.title")}</h1>
        <div className="spacer" />
        <LanguageSwitch />
        <ThemeSwitch />
        <div className={`status ${runtime}`}>
          <span className="dot" />
          {statusLabel(runtime, health)}
        </div>
      </header>

      <main className="columns">
        <SkillPanel
          hubBusy={hubBusy}
          hubError={hubError}
          hubResults={hubResults}
          onClear={clearHub}
          onDetails={policyDetails}
          onImport={(repo, slot) => void importPolicy(repo, slot)}
          onRemove={(id) => void removeSkill(id)}
          onSearch={(q) => void searchHub(q)}
          skills={skills}
        />
        <section className="panel">
          <h2>{t("panel.editor")}</h2>
          <div className="behavior-tabs">
            <button
              className={!selectedBehaviorId && !draft ? "active" : ""}
              disabled={Boolean(draft)}
              onClick={() => select(null)}
              type="button"
            >
              {t("list.overview")}
            </button>
            {behaviors.map((b) => (
              <button
                className={b.id === selectedBehaviorId && !draft ? "active" : ""}
                disabled={Boolean(draft)}
                key={b.id}
                onClick={() => select(b.id)}
                type="button"
              >
                {text(b.name)}
              </button>
            ))}
            {draft && draftIsNew && <button className="active" type="button">{text(draft.name) || t("editor.new")}</button>}
            {!draft && selectedBehaviorId && <button className="new" onClick={() => newDraft()} type="button">+ {t("editor.new")}</button>}
          </div>
          {draft && (
            <BehaviorEditor
              connected={connected}
              dirty={draftDirty}
              draft={draft}
              isNew={draftIsNew}
              lang={language()}
              onChange={(pack) => updateDraft(() => pack)}
              onDelete={() => {
                if (window.confirm(t("editor.delete.confirm", { name: text(draft.name) }))) void deleteBehavior(draft.id);
              }}
              onDiscard={discardDraft}
              onSave={() => void saveDraft(false)}
              onSaveAndRun={() => void saveDraft(true)}
              problems={draftProblems}
              saving={saving}
              skills={skillMap}
            />
          )}
          {selected && (
            <div className="runbar">
              {runningSelected ? (
                <button className="btn danger" onClick={() => void abortRun()} type="button"><Icon name="stop" /> {t("run.abort")}</button>
              ) : (
                <button className="btn primary" disabled={!connected || running} onClick={() => void run(selected.id)} type="button">
                  <Icon name="play" /> {t("run.start")}
                </button>
              )}
              <span className="runstate">{executorLabel(executor)}</span>
              {!connected && <span className="sub">{t("run.needs_connection")}</span>}
              <span className="spacer" />
              <button className="btn" disabled={running} onClick={() => editBehavior(selected.id)} type="button"><Icon name="pencil" /> {t("editor.edit")}</button>
            </div>
          )}
          {selected && (
            <form
              className="sayrow"
              onSubmit={(e) => {
                e.preventDefault();
                submitPhrase(phrase);
              }}
            >
              <label htmlFor="say">{t("run.say.label")}</label>
              <input id="say" onChange={(e) => setPhrase(e.target.value)} placeholder={t("run.say.placeholder")} value={phrase} />
              <button className="btn" disabled={!connected} type="submit">{t("run.say.button")}</button>
              <div className="chips">
                {[...triggerPhrases, t("run.say.stop")].map((p) => (
                  <button className="chip clickable" disabled={!connected} key={p} onClick={() => submitPhrase(p)} type="button">{quote(p)}</button>
                ))}
              </div>
            </form>
          )}
          {selected && (
            <>
              <StepList
                activeStep={runningSelected ? executor?.step_index ?? null : null}
                behavior={selected}
                interrupt={runningSelected ? executor?.interrupt ?? null : null}
                skills={skillMap}
              />
              <details className="yaml">
                <summary>{t("editor.yaml")}</summary>
                <pre>{yamlText ?? "…"}</pre>
              </details>
            </>
          )}
          {!selected && !draft && (
            <BehaviorList
              behaviors={behaviors}
              connected={connected}
              onNew={() => newDraft()}
              onOpen={select}
              onRun={(id) => void run(id)}
              onTemplate={(pack) => newDraft(structuredClone(pack))}
              running={running}
              templates={templatesFor(skillMap)}
            />
          )}
        </section>
        <LivePanel events={events} executor={executor} health={health} state={state} onStop={() => void stop()} />
      </main>

      <footer className="footer">{t("app.disclaimer")}</footer>
    </div>
  );
}

function statusLabel(runtime: "loading" | "online" | "offline", health: ReturnType<typeof useStudio.getState>["health"]): string {
  if (runtime === "loading") return t("status.runtime.loading");
  if (runtime === "offline" || !health) return t("status.runtime.offline");
  if (health.backend === "duck") return t(health.connected ? "status.duck.connected" : "status.duck.disconnected");
  return t(health.connected ? `status.${health.backend}.connected` : `status.${health.backend}`);
}

function executorLabel(executor: ReturnType<typeof useStudio.getState>["executor"]): string {
  if (!executor) return "";
  if (executor.state === "running") {
    const base = t("run.state.running", { step: (executor.step_index ?? 0) + 1, count: executor.step_count });
    return executor.interrupt ? `${base} · ${t("run.interrupt", { on: executor.interrupt })}` : base;
  }
  const label = t(`run.state.${executor.state}`);
  return executor.reason && executor.state !== "idle" ? `${label}: ${executor.reason}` : label;
}
