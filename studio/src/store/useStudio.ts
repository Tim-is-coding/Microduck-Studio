import { create } from "zustand";

import {
  BehaviorPackFromApi,
  Event,
  ExecutorStatus,
  RobotState,
  RuntimeHealth,
  SkillManifest,
  type BehaviorPackFromApi as Pack,
  type Event as EventT,
  type ExecutorStatus as ExecutorStatusT,
  type RobotState as RobotStateT,
  type RuntimeHealth as RuntimeHealthT,
  type SkillManifest as Skill,
} from "../schemas";
import { z } from "zod";

export type RuntimeStatus = "loading" | "online" | "offline";

interface StudioState {
  runtime: RuntimeStatus;
  health: RuntimeHealthT | null;
  state: RobotStateT | null;
  executor: ExecutorStatusT | null;
  skills: Skill[];
  behaviors: Pack[];
  selectedBehaviorId: string | null;
  events: EventT[];
  refreshHealth: () => Promise<void>;
  refreshState: () => Promise<void>;
  refreshExecutor: () => Promise<void>;
  run: (behaviorId: string) => Promise<void>;
  abortRun: () => Promise<void>;
  say: (text: string) => Promise<void>;
  loadCatalog: () => Promise<void>;
  select: (id: string) => void;
  stop: () => Promise<void>;
  pushEvent: (e: EventT) => void;
}

async function getJson<T>(url: string, schema: z.ZodType<T>): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return schema.parse(await res.json());
}

export const useStudio = create<StudioState>((set, get) => ({
  runtime: "loading",
  health: null,
  state: null,
  executor: null,
  skills: [],
  behaviors: [],
  selectedBehaviorId: null,
  events: [],

  async refreshHealth() {
    try {
      const health = await getJson("/api/health", RuntimeHealth);
      set({ runtime: "online", health });
    } catch {
      set({ runtime: "offline", health: null });
    }
  },

  async refreshState() {
    if (!get().health?.connected) {
      if (get().state) set({ state: null });
      return;
    }
    try {
      set({ state: await getJson("/api/state", RobotState) });
    } catch {
      set({ state: null });
    }
  },

  async refreshExecutor() {
    if (get().runtime !== "online") return;
    try {
      set({ executor: await getJson("/api/executor", ExecutorStatus) });
    } catch {
      set({ executor: null });
    }
  },

  async run(behaviorId) {
    const res = await fetch(`/api/behaviors/${encodeURIComponent(behaviorId)}/run`, { method: "POST" });
    if (res.ok) set({ executor: ExecutorStatus.parse(await res.json()) });
    else console.error(await res.text());
  },

  async abortRun() {
    const res = await fetch("/api/executor/abort", { method: "POST" });
    if (res.ok) set({ executor: ExecutorStatus.parse(await res.json()) });
  },

  async say(text) {
    const res = await fetch("/api/say", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (res.ok) {
      const { heard: _heard, started: _started, ...status } = await res.json();
      set({ executor: ExecutorStatus.parse(status) });
    }
  },

  async loadCatalog() {
    try {
      const [skills, behaviors] = await Promise.all([
        getJson("/api/skills", z.array(SkillManifest)),
        getJson("/api/behaviors", z.array(BehaviorPackFromApi)),
      ]);
      set((s) => ({
        skills,
        behaviors,
        selectedBehaviorId: s.selectedBehaviorId ?? behaviors[0]?.id ?? null,
      }));
    } catch (err) {
      console.error(err);
    }
  },

  select(id) {
    set({ selectedBehaviorId: id });
  },

  async stop() {
    // Never gated on the client either: fire, then let the runtime's event tell the story.
    await fetch("/api/stop", { method: "POST" }).catch((err) => console.error(err));
    void get().refreshHealth();
  },

  pushEvent(e) {
    set((s) => ({ events: [...s.events.slice(-199), e] }));
  },
}));

/** Subscribe to the runtime's event stream; reconnects with a small backoff. */
export function connectEvents(): () => void {
  let socket: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const open = () => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${proto}//${location.host}/ws/events`);
    socket.onmessage = (msg) => {
      const parsed = Event.safeParse(JSON.parse(String(msg.data)));
      if (parsed.success) useStudio.getState().pushEvent(parsed.data);
    };
    socket.onclose = () => {
      if (!closed) timer = setTimeout(open, 2000);
    };
  };
  open();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    socket?.close();
  };
}
