import { describe, expect, it } from "vitest";

import { THEME_KEY, isThemeChoice, readThemeChoice, resolveTheme } from "../src/theme";

const storage = (value: string | null) => ({ getItem: (key: string) => (key === THEME_KEY ? value : null) });

describe("theme choice", () => {
  it("follows the machine when nothing was chosen", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("wins over the machine once someone chose", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("reads what was stored and ignores nonsense", () => {
    expect(readThemeChoice(storage("dark"))).toBe("dark");
    expect(readThemeChoice(storage("purple"))).toBe("system");
    expect(readThemeChoice(storage(null))).toBe("system");
    expect(readThemeChoice(null)).toBe("system"); // storage blocked entirely
  });

  it("knows a choice when it sees one", () => {
    expect(isThemeChoice("system")).toBe(true);
    expect(isThemeChoice("")).toBe(false);
  });
});
