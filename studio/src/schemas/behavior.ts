import { z } from "zod";

import { ConditionStr, DurationStr, Identifier, Phrases, Scalar, Text } from "./common";

export const BEHAVIOR_SCHEMA_ID = "duckstudio.behavior/v0";
export const RESERVED_ACTIONS = new Set(["resume", "abort", "stop", "retry", "continue"]);

export const SpeechTrigger = z.strictObject({ kind: z.literal("speech"), phrases: Phrases });
export const ManualTrigger = z.strictObject({ kind: z.literal("manual") });
export const Trigger = z.discriminatedUnion("kind", [SpeechTrigger, ManualTrigger]);
export type Trigger = z.infer<typeof Trigger>;

export const SpeechCondition = z.strictObject({ speech: Phrases });
export const ElapsedCondition = z.strictObject({ elapsed: DurationStr });
export const SignalCondition = z.strictObject({ signal: ConditionStr });
export const StopCondition = z.union([SpeechCondition, ElapsedCondition, SignalCondition]);
export type StopCondition = z.infer<typeof StopCondition>;

export const Until = z
  .strictObject({
    any: z.array(StopCondition).min(1).nullish(),
    all: z.array(StopCondition).min(1).nullish(),
  })
  .superRefine((u, ctx) => {
    if ((u.any == null) === (u.all == null))
      ctx.addIssue({ code: "custom", message: "`until` needs exactly one of `any` or `all`" });
  });

export const OnNone = z.strictObject({
  do: Identifier,
  seconds: z.number().gt(0).lte(600),
  then: z.enum(["retry", "abort", "continue"]).default("retry"),
});

export const PerceiveStep = z.strictObject({
  perceive: z.string().regex(/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/),
  on_none: OnNone.nullish(),
});
export const SkillStep = z.strictObject({
  skill: Identifier,
  with: z.record(z.string(), Scalar).default({}),
  until: Until.nullish(),
});
export const WaitStep = z.strictObject({ wait: DurationStr });
export const Step = z.union([PerceiveStep, SkillStep, WaitStep]);
export type Step = z.infer<typeof Step>;
export type PerceiveStep = z.infer<typeof PerceiveStep>;
export type SkillStep = z.infer<typeof SkillStep>;
export type WaitStep = z.infer<typeof WaitStep>;

export const AlwaysRule = z.strictObject({ on: ConditionStr, do: z.array(Identifier).min(1) });
export const VlmOptIn = z.strictObject({ provider: z.string().min(1), purpose: Text.nullish() });

export const BehaviorPack = z.strictObject({
  schema: z.literal(BEHAVIOR_SCHEMA_ID),
  id: Identifier,
  name: Text,
  summary: Text.nullish(),
  trigger: Trigger,
  steps: z.array(Step).min(1),
  always: z.array(AlwaysRule).default([]),
  vlm: VlmOptIn.nullish(),
});
export type BehaviorPack = z.infer<typeof BehaviorPack>;

/** What GET /api/behaviors returns: the pack plus the runtime's cross-validation result. */
export const BehaviorPackFromApi = BehaviorPack.extend({ problems: z.array(z.string()).default([]) });
export type BehaviorPackFromApi = z.infer<typeof BehaviorPackFromApi>;

export function isPerceive(s: Step): s is PerceiveStep { return "perceive" in s; }
export function isSkill(s: Step): s is SkillStep { return "skill" in s; }
export function isWait(s: Step): s is WaitStep { return "wait" in s; }
