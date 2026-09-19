import de from "./de.json";

// German first (CLAUDE.md §3.7). `en.json` lands later; the lookup already supports it.
const dictionaries: Record<string, Record<string, string>> = { de };
let current = "de";

export function setLanguage(lang: string): void {
  if (dictionaries[lang]) current = lang;
}

/** Translate `key`, substituting `{var}` placeholders. Unknown keys return the key itself. */
export function t(key: string, vars: Record<string, string | number> = {}): string {
  const template = dictionaries[current]?.[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

/** Translate with a fallback when the key is missing (for data-driven labels). */
export function tOr(key: string, fallback: string): string {
  return dictionaries[current]?.[key] ?? fallback;
}

export function formatDuration(text: string): string {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(text);
  if (!m) return text;
  return t(`duration.${m[2]}`, { n: m[1]! });
}
