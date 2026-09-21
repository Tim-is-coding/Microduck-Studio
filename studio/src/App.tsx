import { useEffect } from "react";

import { Route } from "./ablauf/Route";
import { t, useLanguage } from "./i18n";
import { LivePane } from "./live/LivePane";
import { connectEvents, useStudio } from "./store/useStudio";
import { TopBar } from "./ui/TopBar";

const HEALTH_INTERVAL_MS = 2000;
const STATE_INTERVAL_MS = 500;

export function App() {
  const { runtime, health, state, executor, events, draft, selectedBehaviorId, behaviors, refreshHealth, refreshState, refreshExecutor, stop, validateDraft, loadYaml } = useStudio();
  useLanguage(); // re-render the whole Studio when the language changes

  useEffect(() => {
    void refreshHealth(); // loads the catalog as soon as the runtime answers
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
  }, [refreshHealth, refreshState, refreshExecutor]);

  // live validation while editing, debounced
  useEffect(() => {
    if (!draft) return;
    const id = setTimeout(() => void validateDraft(), 300);
    return () => clearTimeout(id);
  }, [draft, validateDraft]);

  // developer view for the selected, saved behavior
  useEffect(() => {
    if (selectedBehaviorId && !draft) void loadYaml(selectedBehaviorId);
  }, [selectedBehaviorId, draft, behaviors, loadYaml]);

  return (
    <div className="app">
      <TopBar health={health} runtime={runtime} />
      <main className="workspace">
        <Route />
        <LivePane events={events} executor={executor} health={health} offline={runtime === "offline"} onStop={() => void stop()} state={state} />
      </main>
      <footer className="footer">{t("app.disclaimer")}</footer>
    </div>
  );
}
