import { z } from "zod";

import { Text } from "./common";

export const Health = z.strictObject({
  battery: z.number().min(0).max(1),
  temperatures_c: z.record(z.string(), z.number()).default({}),
  ok: z.boolean(),
  warnings: z.array(z.string()).default([]),
});

/** Which model would see the camera, and whether a frame would leave the machine at all. */
export const VlmInfo = z.object({
  provider: z.string(),
  model: z.string(),
  configured: z.boolean(),
  sends_frames: z.boolean(),
  hz: z.number(),
});
export type VlmInfo = z.infer<typeof VlmInfo>;

export const RuntimeHealth = z.object({
  version: z.string(),
  backend: z.enum(["mock", "sim", "duck"]),
  connected: z.boolean(),
  health: Health.nullable(),
  unverified_upstream_methods: z.array(z.string()).default([]),
  vlm: VlmInfo.nullish(),
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
  frame_width: z.number(),
  frame_height: z.number(),
  area_px: z.number(),
  confidence: z.number(),
});
export type PersonDetection = z.infer<typeof PersonDetection>;

/** The same geometry, seen by a VLM instead of the local detector. */
export const TargetSighting = PersonDetection.extend({ label: Text, source: z.string() });
export type TargetSighting = z.infer<typeof TargetSighting>;

export const VlmAnswer = z.object({
  timestamp: z.number(),
  question: z.string(),
  found: z.boolean(),
  answer: z.string().default(""),
  provider: z.string(),
  model: z.string(),
  latency_s: z.number(),
});
export type VlmAnswer = z.infer<typeof VlmAnswer>;

export const VlmActivity = z.object({
  provider: z.string(),
  sends_frames: z.boolean(),
  question: Text.nullable(),
  asked: z.number(),
  answer: VlmAnswer.nullable(),
});
export type VlmActivity = z.infer<typeof VlmActivity>;

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
  target: TargetSighting.nullable(),
  tof_min_m: z.number().nullable(),
  /** 8x8 zones in metres, as the head sensor sees them (row 0 = up). */
  tof_rows: z.array(z.array(z.number())).nullish(),
  vlm: VlmActivity.nullish(),
});
export type ExecutorStatus = z.infer<typeof ExecutorStatus>;

/** A policy repo on the Hugging Face Hub, as the runtime relays it. Text from the Hub is
 *  data: it is shown, never followed (CLAUDE.md §10). */
export const HubPolicy = z.object({
  repo: z.string(),
  name: z.string(),
  author: z.string(),
  summary: z.string().default(""),
  tags: z.array(z.string()).default([]),
  downloads: z.number().default(0),
  likes: z.number().default(0),
  updated: z.string().nullish(),
  url: z.string(),
  preview: z.string().nullish(),
  status: z.string().nullish(),
  hardware_tested: z.boolean().nullish(),
  commands: z.string().nullish(),
  control_hz: z.number().nullish(),
  policy_file: z.string().nullish(),
  revision: z.string().nullish(),
  slot_guess: z.string().nullish(),
});
export type HubPolicy = z.infer<typeof HubPolicy>;

export const Event = z.object({
  ts: z.number(),
  level: z.enum(["info", "warn", "error"]).default("info"),
  kind: z.string(),
  text: Text,
  data: z.record(z.string(), z.unknown()).default({}),
});
export type Event = z.infer<typeof Event>;
