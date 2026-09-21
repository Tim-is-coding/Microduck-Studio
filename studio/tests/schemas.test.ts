import { readdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import { parse } from "yaml";

import { BehaviorPack, ExecutorStatus, RunRecord, SkillManifest, parseDuration } from "../src/schemas";

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

describe("what the runtime sends about a run", () => {
  // Mirrors duckstudio/executor/tree.py: `reason` is bilingual, never a bare string — the
  // Studio dropped the whole status when it was parsed as one, so an aborted run lost its
  // sentence.
  const status = {
    state: "aborted",
    behavior: "follow-me",
    step_index: null,
    step_count: 3,
    active_skill: null,
    interrupt: null,
    reason: { de: "vom Studio gestoppt", en: "stopped from the Studio" },
    ticks: 12,
    intents_sent: 4,
    camera: true,
    person: null,
    target: null,
    tof_min_m: null,
  };

  it("parses an aborted run's status", () => {
    const result = ExecutorStatus.safeParse(status);
    expect(result.success, JSON.stringify(result.error?.issues)).toBe(true);
    expect(result.data!.reason!.de).toBe("vom Studio gestoppt");
  });

  it("parses a run record", () => {
    const result = RunRecord.safeParse({
      behavior: "follow-me",
      name: { de: "Folge mir", en: "Follow me" },
      started_at: 1_789_000_000.5,
      duration_s: 12.25,
      state: "done",
      steps_done: 3,
      step_count: 3,
      reason: null,
    });
    expect(result.success, JSON.stringify(result.error?.issues)).toBe(true);
  });
});
