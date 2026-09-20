import { LANGUAGES, setLanguage, t, useLanguage } from "../i18n";

/** Deutsch or English, remembered per browser (§3.7). It changes the Studio's own words;
 *  what a behavior says stays in the language it was written in. */
export function LanguageSwitch() {
  const current = useLanguage();
  return (
    <div aria-label={t("language")} className="theme-switch lang" role="group">
      {LANGUAGES.map((lang) => (
        <button
          aria-pressed={current === lang}
          key={lang}
          onClick={() => setLanguage(lang)}
          title={t(`language.${lang}`)}
          type="button"
        >
          {lang.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
