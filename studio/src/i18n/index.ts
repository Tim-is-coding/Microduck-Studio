import { useSyncExternalStore } from "react";

import de from "./de.json";
import en from "./en.json";

/**
 * German first, English beside it (CLAUDE.md §3.7). Two kinds of text meet here:
 *
 *   - the Studio's own words, from these dictionaries, keyed by `t("…")`;
 *   - the words in the data — skill and behavior names, questions, trigger phrases — which
 *     carry their own `de` and optional `en` (`text()` / `phrases()` below).
 *
 * A behavior somebody wrote in German stays German in an English Studio: nothing here
 * translates content, it only picks the language the content already offers.
 */
export const LANGUAGES = ["de", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

export const LANGUAGE_KEY = "duckstudio.language";

const dictionaries: Record<Language, Record<string, string>> = { de, en };
const listeners = new Set<() => void>();
let current: Language = initial();
if (typeof document !== "undefined") document.documentElement.lang = current;

export function isLanguage(value: unknown): value is Language {
  return value === "de" || value === "en";
}

/** Stored choice, else the browser's, else German. */
function initial(): Language {
  try {
    const stored = localStorage.getItem(LANGUAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    /* a locked-down browser is not a reason to fail */
  }
  return preferred(typeof navigator === "undefined" ? [] : navigator.languages);
}

export function preferred(tags: readonly string[]): Language {
  for (const tag of tags) {
    const lang = tag.slice(0, 2).toLowerCase();
    if (isLanguage(lang)) return lang;
  }
  return "de";
}

export function language(): Language {
  return current;
}

export function setLanguage(lang: Language): void {
  if (!dictionaries[lang] || lang === current) return;
  current = lang;
  if (typeof document !== "undefined") document.documentElement.lang = lang;
  try {
    localStorage.setItem(LANGUAGE_KEY, lang);
  } catch {
    /* ignore */
  }
  for (const listener of listeners) listener();
}

/** React re-renders the Studio when the language changes. */
export function useLanguage(): Language {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    language,
    () => "de" as Language,
  );
}

/** Translate `key`, substituting `{var}` placeholders. Unknown keys return the key itself. */
export function t(key: string, vars: Record<string, string | number> = {}): string {
  const template = dictionaries[current][key] ?? dictionaries.de[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

/** Translate with a fallback when the key is missing (for data-driven labels). */
export function tOr(key: string, fallback: string): string {
  return dictionaries[current][key] ?? dictionaries.de[key] ?? fallback;
}

/** Text that came with the data. German is always there; English only sometimes. */
export interface Localized {
  de: string;
  en?: string | null;
}

export function text(value: Localized | null | undefined, fallback = ""): string {
  if (!value) return fallback;
  return (current === "en" ? value.en : undefined) || value.de || fallback;
}

export interface LocalizedList {
  de: string[];
  en?: string[] | null;
}

export function phrases(value: LocalizedList | null | undefined): string[] {
  if (!value) return [];
  const chosen = current === "en" ? value.en : undefined;
  return chosen && chosen.length > 0 ? chosen : value.de;
}

const QUOTES: Record<Language, [string, string]> = { de: ["„", "“"], en: ["“", "”"] };

/** „so“ in German, “so” in English. */
export function quote(value: string): string {
  const [open, close] = QUOTES[current];
  return `${open}${value}${close}`;
}

export function quoteJoin(values: readonly string[], separator = " / "): string {
  return values.map(quote).join(separator);
}

/** 1.25 → "1,25" in German, "1.25" in English. */
export function number(value: number, digits = 1): string {
  return value.toLocaleString(current, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(current);
}

export function formatDuration(value: string): string {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(value);
  if (!m) return value;
  return t(`duration.${m[2]}`, { n: m[1]! });
}
