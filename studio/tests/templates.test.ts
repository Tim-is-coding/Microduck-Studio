import { describe, expect, it } from "vitest";

import { templatesFor } from "../src/editor/templates";
import { BehaviorPack, SkillManifest } from "../src/schemas";
import { readdirSync, readFileSync } from "node:fs";
import { parse } from "yaml";

/** The manifests the repo ships: a template may only name skills that exist. */
function builtinSkills(): Map<string, SkillManifest> {
  const dir = new URL("../../skills/", import.meta.url);
  const skills = readdirSync(dir)
    .filter((f) => f.endsWith(".skill.yaml"))
    .map((f) => SkillManifest.parse(parse(readFileSync(new URL(f, dir), "utf8"))));
  return new Map(skills.map((s) => [s.id, s]));
}

describe("starter templates", () => {
  const skills = builtinSkills();

  it("are offered with the builtin skills and are valid packs", () => {
    const templates = templatesFor(skills);
    expect(templates.length).toBeGreaterThan(0);
    for (const tpl of templates) {
      expect(() => BehaviorPack.parse(tpl.pack)).not.toThrow();
      for (const id of tpl.needs) expect(skills.has(id)).toBe(true);
    }
  });

  it("fill every skill card from its manifest", () => {
    for (const tpl of templatesFor(skills)) {
      for (const step of tpl.pack.steps) {
        if (!("skill" in step)) continue;
        const manifest = skills.get(step.skill)!;
        for (const [key, control] of Object.entries(manifest.ui)) {
          if (control.default !== undefined && control.default !== null) expect(step.with).toHaveProperty(key);
        }
      }
    }
  });

  it("offer nothing when the registry is empty", () => {
    expect(templatesFor(new Map())).toEqual([]);
  });
});
