import { t } from "../i18n";
import type { RuntimeHealth } from "../schemas";

export function TopBar({ runtime, health }: { runtime: "loading" | "online" | "offline"; health: RuntimeHealth | null }) {
  const cls = runtime === "offline" ? "offline" : health?.connected ? "online" : "waiting";
  return (
    <header className="topbar">
      <h1>{t("app.title")}</h1>
      <span className="spacer" />
      <span className={`duckstatus ${cls}`}>
        <span className="dot" />
        {statusLabel(runtime, health)}
      </span>
    </header>
  );
}

function statusLabel(runtime: "loading" | "online" | "offline", health: RuntimeHealth | null): string {
  if (runtime === "loading") return t("status.loading");
  if (runtime === "offline" || !health) return t("status.offline");
  return t(`status.${health.backend}.${health.connected ? "connected" : "disconnected"}`);
}
