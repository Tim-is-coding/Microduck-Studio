import { useEffect, useMemo } from "react";

import { StepList } from "./editor/StepList";
import { t } from "./i18n";
import { LivePanel } from "./live/LivePanel";
import { SkillPanel } from "./skills/SkillPanel";
import { connectEvents, useStudio } from "./store/useStudio";

const HEALTH_INTERVAL_MS = 2000;
const STATE_INTERVAL_MS = 500;

export function App() {
  const {
    runtime, health, state, skills, behaviors, selectedBehaviorId, events,
    refreshHealth, refreshState, loadCatalog, select, stop,
  } = useStudio();

  useEffect(() => {
    void refreshHealth();
    void loadCatalog();
    const id = setInterval(() => void refreshHealth(), HEALTH_INTERVAL_MS);
    const stateId = setInterval(() => void refreshState(), STATE_INTERVAL_MS);
    const disconnect = connectEvents();
    return () => {
      clearInterval(id);
      clearInterval(stateId);
      disconnect();
    };
  }, [refreshHealth, refreshState, loadCatalog]);

  const skillMap = useMemo(() => new Map(skills.map((s) => [s.id, s])), [skills]);
  const selected = behaviors.find((b) => b.id === selectedBehaviorId) ?? null;

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
          {selected ? <StepList behavior={selected} skills={skillMap} /> : <div className="sub">{t("editor.empty")}</div>}
        </section>
        <LivePanel events={events} health={health} state={state} onStop={() => void stop()} />
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
