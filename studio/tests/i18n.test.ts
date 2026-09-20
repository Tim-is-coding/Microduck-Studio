import { describe, expect, it } from "vitest";

import de from "../src/i18n/de.json";
import en from "../src/i18n/en.json";
import { isLanguage, preferred, setLanguage, t, text, phrases } from "../src/i18n";
import { newBehavior, renameBehavior, setLocalized } from "../src/editor/model";

describe("the two dictionaries stay in step", () => {
  it("has the same keys on both sides", () => {
    const missingEn = Object.keys(de).filter((k) => !(k in en));
    const missingDe = Object.keys(en).filter((k) => !(k in de));
    expect(missingEn, "keys without an English text").toEqual([]);
    expect(missingDe, "English keys nobody asks for in German").toEqual([]);
  });

  it("keeps the same placeholders in both languages", () => {
    const vars = (s: string) => (s.match(/\{(\w+)\}/g) ?? []).sort();
    const wrong = Object.keys(de).filter(
      (k) => vars((de as Record<string, string>)[k]!).join() !== vars((en as Record<string, string>)[k]!).join(),
    );
    expect(wrong, "placeholders differ between de and en").toEqual([]);
  });

  it("has no empty texts", () => {
    expect(Object.entries(en).filter(([, v]) => !v.trim())).toEqual([]);
  });
});

describe("picking a language", () => {
  it("takes the first one it has a dictionary for", () => {
    expect(preferred(["en-GB", "de"])).toBe("en");
    expect(preferred(["de-AT"])).toBe("de");
    expect(preferred(["fr", "es"])).toBe("de"); // German first (§3.7)
    expect(preferred([])).toBe("de");
    expect(isLanguage("en")).toBe(true);
    expect(isLanguage("fr")).toBe(false);
  });

  it("translates with placeholders in whichever language is on", () => {
    setLanguage("de");
    expect(t("live.doing.step", { step: 2, count: 3 })).toBe("Schritt 2 von 3");
    setLanguage("en");
    expect(t("live.doing.step", { step: 2, count: 3 })).toBe("Step 2 of 3");
    expect(t("nope.not.here")).toBe("nope.not.here");
  });
});

describe("text that came with the data", () => {
  it("follows the Studio's language when the data offers one", () => {
    setLanguage("de");
    expect(text({ de: "Gehen", en: "Walk" })).toBe("Gehen");
    expect(phrases({ de: ["Folge mir"], en: ["Follow me"] })).toEqual(["Folge mir"]);
    setLanguage("en");
    expect(text({ de: "Gehen", en: "Walk" })).toBe("Walk");
    expect(phrases({ de: ["Folge mir"], en: ["Follow me"] })).toEqual(["Follow me"]);
  });

  it("falls back to German — a behavior written in German stays readable", () => {
    setLanguage("en");
    expect(text({ de: "Tanzen" })).toBe("Tanzen");
    expect(phrases({ de: ["Tanz"] })).toEqual(["Tanz"]);
    expect(text(null, "–")).toBe("–");
    setLanguage("de");
  });
});

describe("editing writes the language you type in", () => {
  it("fills German when German is the editing language", () => {
    expect(setLocalized(undefined, "Tanzen", "de")).toEqual({ de: "Tanzen" });
    expect(setLocalized({ de: "Gehen", en: "Walk" }, "Laufen", "de")).toEqual({ de: "Laufen", en: "Walk" });
  });

  it("fills both when English is typed into something that has no German yet", () => {
    expect(setLocalized(undefined, "Dance", "en")).toEqual({ de: "Dance", en: "Dance" });
  });

  it("leaves the German alone when a bilingual text is edited in English", () => {
    expect(setLocalized({ de: "Gehen", en: "Walk" }, "Stroll", "en")).toEqual({ de: "Gehen", en: "Stroll" });
  });

  it("drops the field when the text is cleared", () => {
    expect(setLocalized({ de: "Gehen" }, "", "de")).toBeUndefined();
  });
});

describe("a behavior born in an English Studio", () => {
  it("takes the typed name as its name, not the placeholder it started with", () => {
    const fresh = newBehavior("New behavior");
    const named = renameBehavior(fresh, "Greeting", false, "en", true);
    expect(named.name).toEqual({ de: "Greeting", en: "Greeting" });
    expect(named.id).toBe("greeting");
  });

  it("protects an existing German name once the behavior is saved", () => {
    const saved = { ...newBehavior("Folge mir"), name: { de: "Folge mir", en: "Follow me" } };
    const renamed = renameBehavior(saved, "Follow the person", true, "en", false);
    expect(renamed.name).toEqual({ de: "Folge mir", en: "Follow the person" });
  });
});
