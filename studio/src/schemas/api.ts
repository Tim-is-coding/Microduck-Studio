import { z } from "zod";

import { Text } from "./common";

export const Health = z.strictObject({
  battery: z.number().min(0).max(1),
  temperatures_c: z.record(z.string(), z.number()).default({}),
  ok: z.boolean(),
  warnings: z.array(z.string()).default([]),
});

export const RuntimeHealth = z.object({
  version: z.string(),
  backend: z.enum(["mock", "sim", "duck"]),
  connected: z.boolean(),
  health: Health.nullable(),
  unverified_upstream_methods: z.array(z.string()).default([]),
});
export type RuntimeHealth = z.infer<typeof RuntimeHealth>;

export const RobotState = z.object({
  timestamp: z.number(),
  joints: z.array(z.number()).length(15),
  imu: z.object({ roll: z.number(), pitch: z.number(), yaw: z.number() }),
  flags: z.object({ standing: z.boolean(), fallen: z.boolean(), sitting: z.boolean(), moving: z.boolean() }),
  pose: z.object({ x: z.number(), y: z.number(), heading: z.number() }).nullable(),
});
export type RobotState = z.infer<typeof RobotState>;

export const PersonDetection = z.object({
  timestamp: z.number(),
  bearing_rad: z.number(),
  distance_m: z.number().nullable(),
  pixel_x: z.number(),
  pixel_y: z.number(),
  area_px: z.number(),
  confidence: z.number(),
});
export type PersonDetection = z.infer<typeof PersonDetection>;

export const ExecutorState = z.enum(["idle", "running", "done", "failed", "aborted", "preempted"]);

export const ExecutorStatus = z.object({
  state: ExecutorState,
  behavior: z.string().nullable(),
  step_index: z.number().nullable(),
  step_count: z.number(),
  active_skill: z.string().nullable(),
  interrupt: z.string().nullable(),
  reason: z.string().nullable(),
  ticks: z.number(),
  intents_sent: z.number(),
  camera: z.boolean().nullable(),
  person: PersonDetection.nullable(),
  tof_min_m: z.number().nullable(),
});
export type ExecutorStatus = z.infer<typeof ExecutorStatus>;

export const Event = z.object({
  ts: z.number(),
  level: z.enum(["info", "warn", "error"]).default("info"),
  kind: z.string(),
  text: Text,
  data: z.record(z.string(), z.unknown()).default({}),
});
export type Event = z.infer<typeof Event>;
