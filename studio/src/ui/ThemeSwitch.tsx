import { useEffect, useState } from "react";

import { t } from "../i18n";
import {
  THEME_CHOICES,
  applyTheme,
  readThemeChoice,
  watchSystemTheme,
  writeThemeChoice,
  type ThemeChoice,
} from "../theme";
import { Icon, type IconName } from "./Icon";

const ICONS: Record<ThemeChoice, IconName> = { system: "system", light: "sun", dark: "moon" };

/** Hell, dunkel, oder was der Rechner sagt. Stays in this browser, never in a behavior. */
export function ThemeSwitch() {
  const [choice, setChoice] = useState<ThemeChoice>(() => readThemeChoice());

  useEffect(() => {
    applyTheme(choice);
    return watchSystemTheme(() => applyTheme(choice));
  }, [choice]);

  return (
    <div aria-label={t("theme")} className="switch theme" role="group">
      {THEME_CHOICES.map((option) => (
        <button
          aria-pressed={choice === option}
          key={option}
          onClick={() => {
            writeThemeChoice(option);
            setChoice(option);
          }}
          title={t(`theme.${option}`)}
          type="button"
        >
          <Icon name={ICONS[option]} title={t(`theme.${option}`)} />
        </button>
      ))}
    </div>
  );
}
