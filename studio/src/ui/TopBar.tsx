import { t } from "../i18n";
import type { RuntimeHealth } from "../schemas";
import { BackendMenu } from "./BackendMenu";
import { LanguageSwitch } from "./LanguageSwitch";
import { ThemeSwitch } from "./ThemeSwitch";

export function TopBar({ runtime, health }: { runtime: "loading" | "online" | "offline"; health: RuntimeHealth | null }) {
  return (
    <header className="topbar">
      <h1>{t("app.title")}</h1>
      <span className="spacer" />
      <LanguageSwitch />
      <ThemeSwitch />
      <BackendMenu health={health} runtime={runtime} />
    </header>
  );
}
