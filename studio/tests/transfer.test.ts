import { describe, expect, it } from "vitest";

import { COPY_SUFFIX, duplicate, fileName, freeId, fromYaml, toYaml } from "../src/editor/transfer";
import { addStep, newBehavior } from "../src/editor/model";
import { readFileSync } from "node:fs";

const pack = addStep(newBehavior("Folge mir"), { skill: "quack", with: { style: "short" } });
const bilingual = { ...pack, name: { de: "Folge mir", en: "Follow me" } };

describe("freeId", () => {
  it("only moves out of the way when it has to", () => {
    expect(freeId("folge-mir", [])).toBe("folge-mir");
    expect(freeId("folge-mir", ["folge-mir"])).toBe("folge-mir-2");
    expect(freeId("folge-mir", ["folge-mir", "folge-mir-2", "folge-mir-3"])).toBe("folge-mir-4");
  });
});

describe("duplicate", () => {
  it("suffixes every language the pack carries and takes a free id", () => {
    const copy = duplicate(bilingual, ["folge-mir", "folge-mir-copy"]);
    expect(copy.id).toBe("folge-mir-copy-2");
    expect(copy.name).toEqual({ de: `Folge mir ${COPY_SUFFIX.de}`, en: `Follow me ${COPY_SUFFIX.en}` });
    expect(copy.steps).toEqual(bilingual.steps);
  });

  it("leaves a German-only pack German-only", () => {
    expect(duplicate(pack, []).name).toEqual({ de: `Folge mir ${COPY_SUFFIX.de}` });
  });

  it("drops what the API adds", () => {
    const fromApi = { ...pack, problems: ["something"] } as never;
    expect(duplicate(fromApi, [])).not.toHaveProperty("problems");
  });
});

describe("file round trip", () => {
  it("writes YAML the Studio reads back unchanged", () => {
    const result = fromYaml(toYaml(bilingual), []);
    expect(result.ok && result.pack).toEqual(bilingual);
    expect(fileName(bilingual)).toBe("folge-mir.behavior.yaml");
  });

  it("reads the behavior packs the repo ships", () => {
    for (const name of ["follow-me", "go-to-thing"]) {
      const text = readFileSync(new URL(`../../behaviors/${name}.behavior.yaml`, import.meta.url), "utf8");
      const result = fromYaml(text, []);
      expect(result.ok, `${name}: ${result.ok ? "" : result.detail}`).toBe(true);
    }
  });

  it("renames an id that is already taken instead of overwriting it", () => {
    const result = fromYaml(toYaml(pack), ["folge-mir"]);
    expect(result.ok && result.pack.id).toBe("folge-mir-2");
    expect(result.ok && result.renamedFrom).toBe("folge-mir");
  });

  it("says what is wrong with a file it cannot use", () => {
    expect(fromYaml("steps: [ unclosed", [])).toMatchObject({ ok: false, reason: "yaml" });
    expect(fromYaml("hallo: welt", [])).toMatchObject({ ok: false, reason: "schema" });
    expect(fromYaml(toYaml(pack).replace("duckstudio.behavior/v0", "something/else"), [])).toMatchObject({
      ok: false,
      reason: "schema",
    });
  });
});
