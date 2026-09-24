import { t } from "../i18n";
import type { RuntimeHealth } from "../schemas";
import { BackendMenu } from "./BackendMenu";
import { LanguageSwitch } from "./LanguageSwitch";
import { ThemeSwitch } from "./ThemeSwitch";

export function TopBar({ runtime, health }: { runtime: "loading" | "online" | "offline"; health: RuntimeHealth | null }) {
  return (
    <header className="topbar">
      <h1 className="wordmark">
        <svg aria-hidden="true" height="20" viewBox="0 0 32 32" width="20"><circle cx="14" cy="17" r="11" fill="currentColor" /><path d="M24 15.2 L30.5 17.5 L24 19.8 Z" fill="currentColor" /><circle cx="17.5" cy="13.5" r="1.9" fill="var(--bg)" /></svg>
        {t("app.title")}
      </h1>
      <span className="spacer" />
      <LanguageSwitch />
      <ThemeSwitch />
      <BackendMenu health={health} runtime={runtime} />
    </header>
  );
}
