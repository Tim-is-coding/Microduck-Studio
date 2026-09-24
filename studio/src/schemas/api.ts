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
  /** Vendors with a key the runtime may use (ADR-0009); empty = only the local stand-in. */
  vendors: z.array(z.string()).default([]),
  model: z.string(),
  configured: z.boolean(),
  sends_frames: z.boolean(),
  hz: z.number(),
});
export type VlmInfo = z.infer<typeof VlmInfo>;

const Bilingual = z.object({ de: z.string(), en: z.string() });

/** One AI vendor a person can bring a key for (GET /api/ai, ADR-0009). Never the key itself. */
export const AiVendor = z.object({
  id: z.string(),
  label: z.string(),
  key_url: z.string(),
  docs_url: z.string(),
  pricing_url: z.string(),
  terms_url: z.string().nullish(),
  free_tier: z.boolean(),
  recommended: z.boolean(),
  note: Bilingual,
  env_var: z.string(),
  models: z.array(z.object({ id: z.string(), note: Bilingual })),
  model: z.string(),
  key: z.object({ source: z.enum(["studio", "environment"]), hint: z.string() }).nullable(),
});
export type AiVendor = z.infer<typeof AiVendor>;

export const AiInfo = z.object({
  checked: z.string(),
  hz: z.number(),
  max_calls: z.number(),
  vendors: z.array(AiVendor),
});
export type AiInfo = z.infer<typeof AiInfo>;

export const BackendKind = z.enum(["mock", "sim", "duck"]);
export type BackendKind = z.infer<typeof BackendKind>;

export const RuntimeHealth = z.object({
  version: z.string(),
  backend: BackendKind,
  /** What the Studio may switch to (ADR-0007). */
  backends: z.array(BackendKind).default(["sim", "mock", "duck"]),
  connected: z.boolean(),
  /** Why the last connection attempt failed, in the backend's words; null once connected. */
  backend_error: z.string().nullish(),
  /** The real duck's host name, only ever shown in the tunnel command. */
  duck_host: z.string().default(""),
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
  /** Why a run ended, in both languages — the runtime sends `{de, en}`, not a string. */
  reason: Text.nullable(),
  ticks: z.number(),
  intents_sent: z.number(),
  /** How many runs the runtime has recorded — a new number means the run list changed. */
  runs_recorded: z.number().default(0),
  stuck: z.boolean().default(false),
  camera: z.boolean().nullable(),
  person: PersonDetection.nullable(),
  target: TargetSighting.nullable(),
  tof_min_m: z.number().nullable(),
  /** 8x8 zones in metres, as the head sensor sees them (row 0 = up). */
  tof_rows: z.array(z.array(z.number())).nullish(),
  vlm: VlmActivity.nullish(),
});
export type ExecutorStatus = z.infer<typeof ExecutorStatus>;

/** One finished run, as `GET /api/runs` lists them (newest first). */
export const RunRecord = z.object({
  behavior: z.string(),
  name: Text,
  /** Seconds since the epoch, from the runtime's clock. */
  started_at: z.number(),
  duration_s: z.number(),
  state: ExecutorState,
  steps_done: z.number(),
  step_count: z.number(),
  reason: Text.nullable(),
});
export type RunRecord = z.infer<typeof RunRecord>;

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
