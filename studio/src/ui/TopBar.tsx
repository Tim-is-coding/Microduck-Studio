import { t } from "../i18n";
import type { RuntimeHealth } from "../schemas";
import { LanguageSwitch } from "./LanguageSwitch";
import { ThemeSwitch } from "./ThemeSwitch";

export function TopBar({ runtime, health }: { runtime: "loading" | "online" | "offline"; health: RuntimeHealth | null }) {
  const cls = runtime === "offline" ? "offline" : health?.connected ? "online" : "waiting";
  return (
    <header className="topbar">
      <h1>{t("app.title")}</h1>
      <span className="spacer" />
      <LanguageSwitch />
      <ThemeSwitch />
      <span className={`duckstatus ${cls}`}>
        <span className="dot" />
        {statusLabel(runtime, health)}
      </span>
    </header>
  );
}

function statusLabel(runtime: "loading" | "online" | "offline", health: RuntimeHealth | null): string {
  if (runtime === "loading") return t("duck.status.loading");
  if (runtime === "offline" || !health) return t("duck.status.offline");
  return t(`duck.status.${health.backend}.${health.connected ? "connected" : "disconnected"}`);
}
