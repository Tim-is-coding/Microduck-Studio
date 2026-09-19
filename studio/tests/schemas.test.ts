import { readdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import { parse } from "yaml";

import { BehaviorPack, SkillManifest, parseDuration } from "../src/schemas";

const root = fileURLToPath(new URL("../..", import.meta.url));

function yamlFiles(dir: string, suffix: string): string[] {
  return readdirSync(join(root, dir))
    .filter((f) => f.endsWith(suffix))
    .map((f) => join(root, dir, f));
}

describe("skill manifests (skills/*.skill.yaml) validate with the zod mirror", () => {
  const files = yamlFiles("skills", ".skill.yaml");
  it("finds manifests", () => expect(files.length).toBeGreaterThan(0));
  for (const file of files) {
    it(basename(file), () => {
      const result = SkillManifest.safeParse(parse(readFileSync(file, "utf8")));
      expect(result.success, JSON.stringify(result.error?.issues, null, 2)).toBe(true);
      expect(result.data!.id).toBe(basename(file, ".skill.yaml"));
    });
  }
});

describe("behavior packs (behaviors/*.behavior.yaml)", () => {
  for (const file of yamlFiles("behaviors", ".behavior.yaml")) {
    it(basename(file), () => {
      const result = BehaviorPack.safeParse(parse(readFileSync(file, "utf8")));
      expect(result.success, JSON.stringify(result.error?.issues, null, 2)).toBe(true);
    });
  }

  it("keeps `on:` a string (YAML 1.2), like the runtime loader", () => {
    expect(parse("on: fallen\nflag: true\n")).toEqual({ on: "fallen", flag: true });
  });

  it("reads the follow-me spec exactly as written in CLAUDE.md §6.2", () => {
    const pack = BehaviorPack.parse(parse(readFileSync(join(root, "behaviors/follow-me.behavior.yaml"), "utf8")));
    expect(pack.steps).toHaveLength(3);
    expect(pack.steps[1]).toMatchObject({ skill: "walk", with: { tempo: "easy", distance: 60 } });
    expect(pack.always[0]).toEqual({ on: "fallen", do: ["getup", "resume"] });
  });
});

describe("helpers", () => {
  it("parses durations", () => {
    expect(parseDuration("10m")).toBe(600);
    expect(parseDuration("500ms")).toBe(0.5);
    expect(() => parseDuration("soon")).toThrow();
  });
});
