import { z } from "zod";

// Mirrors runtime/duckstudio/common.py. The pydantic models are the source of truth
// (docs/schemas/*.json); tests validate the example YAML files against both.

export const Text = z.strictObject({
  de: z.string().min(1),
  en: z.string().nullish(),
});
export type Text = z.infer<typeof Text>;

export const Phrases = z.strictObject({
  de: z.array(z.string()).min(1),
  en: z.array(z.string()).nullish(),
});
export type Phrases = z.infer<typeof Phrases>;

export const ID_PATTERN = /^[a-z][a-z0-9_-]*$/;
export const CONDITION_PATTERN = /^[a-z][a-z0-9_.]*(\s*(<=|>=|==|!=|<|>)\s*-?\d+(\.\d+)?)?$/;
export const INTERRUPT_PATTERN = /^[a-z][a-z0-9_.]*(\s*->\s*[a-z][a-z0-9_-]*)+$/;
export const DURATION_PATTERN = /^\d+(\.\d+)?(ms|s|m|h)$/;

export const Identifier = z.string().max(64).regex(ID_PATTERN);
export const ConditionStr = z.string().regex(CONDITION_PATTERN);
export const InterruptStr = z.string().regex(INTERRUPT_PATTERN);
export const DurationStr = z.string().regex(DURATION_PATTERN);

export const Scalar = z.union([z.string(), z.number(), z.boolean()]);
export type Scalar = z.infer<typeof Scalar>;

export function parseCondition(text: string): { signal: string; op?: string; value?: number } {
  const m = /^([a-z][a-z0-9_.]*)(?:\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?))?$/.exec(text.trim());
  if (!m) throw new Error(`invalid condition: ${text}`);
  const [, signal, op, value] = m;
  return op ? { signal: signal!, op, value: Number(value) } : { signal: signal! };
}

const DURATION_FACTORS: Record<string, number> = { ms: 0.001, s: 1, m: 60, h: 3600 };
export function parseDuration(text: string): number {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(text.trim());
  if (!m) throw new Error(`invalid duration: ${text}`);
  return Number(m[1]) * DURATION_FACTORS[m[2]!]!;
}
