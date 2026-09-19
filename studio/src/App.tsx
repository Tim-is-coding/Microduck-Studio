import { useEffect, useMemo, useState } from "react";

import { StepList } from "./editor/StepList";
import { t } from "./i18n";
import { LivePanel } from "./live/LivePanel";
import { SkillPanel } from "./skills/SkillPanel";
import { connectEvents, useStudio } from "./store/useStudio";

const HEALTH_INTERVAL_MS = 2000;
const STATE_INTERVAL_MS = 500;

export function App() {
  const {
    runtime, health, state, executor, skills, behaviors, selectedBehaviorId, events,
    refreshHealth, refreshState, refreshExecutor, loadCatalog, select, stop, run, abortRun, say,
  } = useStudio();
  const [phrase, setPhrase] = useState("");

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
  const selected = behaviors.find((b) => b.id === selectedBehaviorId) ?? null;
  const connected = health?.connected ?? false;
  const running = executor?.state === "running";
  const runningSelected = running && executor?.behavior === selected?.id;
  const triggerPhrases = selected?.trigger.kind === "speech" ? selected.trigger.phrases.de : [];
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
        <div className={`status ${runtime}`}>
          <span className="dot" />
          {statusLabel(runtime, health)}
        </div>
      </header>

      <main className="columns">
        <SkillPanel skills={skills} />
        <section className="panel">
          <h2>{t("panel.editor")}</h2>
          <div className="behavior-tabs">
            {behaviors.map((b) => (
              <button className={b.id === selectedBehaviorId ? "active" : ""} key={b.id} onClick={() => select(b.id)} type="button">
                {b.name.de}
              </button>
            ))}
          </div>
          {selected && (
            <div className="runbar">
              {runningSelected ? (
                <button className="btn danger" onClick={() => void abortRun()} type="button">■ {t("run.abort")}</button>
              ) : (
                <button className="btn primary" disabled={!connected || running} onClick={() => void run(selected.id)} type="button">
                  ▶ {t("run.start")}
                </button>
              )}
              <span className="runstate">{executorLabel(executor)}</span>
              {!connected && <span className="sub">{t("run.needs_connection")}</span>}
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
                {[...triggerPhrases, "Stopp"].map((p) => (
                  <button className="chip clickable" disabled={!connected} key={p} onClick={() => submitPhrase(p)} type="button">„{p}“</button>
                ))}
              </div>
            </form>
          )}
          {selected ? (
            <StepList
              activeStep={runningSelected ? executor?.step_index ?? null : null}
              behavior={selected}
              interrupt={runningSelected ? executor?.interrupt ?? null : null}
              skills={skillMap}
            />
          ) : (
            <div className="sub">{t("editor.empty")}</div>
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
