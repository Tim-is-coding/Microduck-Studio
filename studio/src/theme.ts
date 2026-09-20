import { useEffect, useState } from "react";

/**
 * Light, dark or whatever the machine says. The choice is a per-browser convenience, so it
 * lives in localStorage and nowhere near the runtime; the resolution is a pure function so
 * it can be tested without a DOM.
 */
export const THEME_KEY = "duckstudio.theme";

export type ThemeChoice = "system" | "light" | "dark";
export type Resolved = "light" | "dark";

export const THEME_CHOICES: ThemeChoice[] = ["system", "light", "dark"];

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === "system" || value === "light" || value === "dark";
}

/** What the page should actually show. */
export function resolveTheme(choice: ThemeChoice, systemPrefersDark: boolean): Resolved {
  if (choice === "system") return systemPrefersDark ? "dark" : "light";
  return choice;
}

export function readThemeChoice(storage: Pick<Storage, "getItem"> | null = safeStorage()): ThemeChoice {
  try {
    const stored = storage?.getItem(THEME_KEY);
    return isThemeChoice(stored) ? stored : "system";
  } catch {
    return "system"; // a locked-down browser is not a reason to fail
  }
}

export function writeThemeChoice(choice: ThemeChoice, storage = safeStorage()): void {
  try {
    storage?.setItem(THEME_KEY, choice);
  } catch {
    /* ignore */
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function prefersDark(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Put the resolved theme on <html> so the stylesheet can switch tokens. */
export function applyTheme(choice: ThemeChoice): Resolved {
  const resolved = resolveTheme(choice, prefersDark());
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeChoice = choice;
  return resolved;
}

/** Run `onChange` when the machine's preference changes while "system" is chosen. */
export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof matchMedia !== "function") return () => {};
  const query = matchMedia("(prefers-color-scheme: dark)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** React hook: is the page dark right now? Follows the switch and the machine. */
export function useIsDark(): boolean {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark");
  useEffect(() => {
    const read = () => setDark(document.documentElement.dataset.theme === "dark");
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}
