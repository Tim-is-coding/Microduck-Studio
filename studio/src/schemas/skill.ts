import { z } from "zod";

import { ConditionStr, Identifier, InterruptStr, Text } from "./common";

export const SKILL_SCHEMA_ID = "duckstudio.skill/v0";

export const ParamSpec = z.strictObject({
  type: z.enum(["float", "int", "bool", "string"]).default("float"),
  min: z.number().nullish(),
  max: z.number().nullish(),
  unit: z.string().nullish(),
  default: z.union([z.number(), z.boolean(), z.string()]).nullish(),
});

export const Source = z
  .strictObject({
    kind: z.enum(["builtin", "hub"]),
    policy: z.string().nullish(),
    repo: z.string().nullish(),
    file: z.string().nullish(),
    version: z.union([z.number().int(), z.string()]).nullish(),
  })
  .superRefine((s, ctx) => {
    if (s.kind === "builtin" && !s.policy) ctx.addIssue({ code: "custom", message: "builtin source needs `policy`" });
    if (s.kind === "hub" && !s.repo) ctx.addIssue({ code: "custom", message: "hub source needs `repo`" });
  });

export const ChoiceControl = z
  .strictObject({
    control: z.literal("choice"),
    options: z.array(z.string()).min(2),
    maps_to: z.string().nullish(),
    values: z.array(z.number()).nullish(),
    default: z.string().nullish(),
  })
  .superRefine((c, ctx) => {
    if (c.values && c.values.length !== c.options.length)
      ctx.addIssue({ code: "custom", message: "`values` must have one entry per option" });
    if ((c.values == null) !== (c.maps_to == null))
      ctx.addIssue({ code: "custom", message: "`maps_to` and `values` go together" });
  });

export const SelectControl = z.strictObject({
  control: z.literal("select"),
  options: z.array(z.string()).min(1),
  default: z.string().nullish(),
});

export const RangeControl = z.strictObject({
  control: z.literal("range"),
  min: z.number(),
  max: z.number(),
  default: z.number().nullish(),
  step: z.number().nullish(),
  unit: z.string().nullish(),
  maps_to: z.string().nullish(),
});

export const ToggleControl = z.strictObject({
  control: z.literal("toggle"),
  default: z.boolean().default(false),
  maps_to: z.string().nullish(),
});

export const UiControl = z.discriminatedUnion("control", [
  ChoiceControl,
  SelectControl,
  RangeControl,
  ToggleControl,
]);
export type UiControl = z.infer<typeof UiControl>;

export const SkillManifest = z
  .strictObject({
    schema: z.literal(SKILL_SCHEMA_ID),
    id: Identifier,
    name: Text,
    summary: Text.nullish(),
    source: Source,
    intent: z.string().regex(/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/).nullish(),
    behavior: z.string().regex(/^[a-z][a-z0-9_]*$/).nullish(),
    params: z.record(z.string(), ParamSpec).default({}),
    ui: z.record(z.string(), UiControl).default({}),
    preconditions: z.array(ConditionStr).default([]),
    terminates_on: z.array(ConditionStr).default([]),
    interrupts: z.array(InterruptStr).default([]),
    rate_hz: z.number().int().min(1).max(50).default(10),
  })
  .superRefine((m, ctx) => {
    if ((m.intent == null) === (m.behavior == null))
      ctx.addIssue({ code: "custom", message: "exactly one of `intent` or `behavior` is required" });
    for (const [key, control] of Object.entries(m.ui)) {
      const target = "maps_to" in control ? control.maps_to : undefined;
      if (target && !(target in m.params))
        ctx.addIssue({ code: "custom", message: `ui.${key}.maps_to references unknown param ${target}` });
    }
  });
export type SkillManifest = z.infer<typeof SkillManifest>;
