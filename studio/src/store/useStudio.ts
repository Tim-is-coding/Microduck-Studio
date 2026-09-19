import { create } from "zustand";

import {
  BehaviorPackFromApi,
  Event,
  RuntimeHealth,
  SkillManifest,
  type BehaviorPackFromApi as Pack,
  type Event as EventT,
  type RuntimeHealth as RuntimeHealthT,
  type SkillManifest as Skill,
} from "../schemas";
import { z } from "zod";

export type RuntimeStatus = "loading" | "online" | "offline";

interface StudioState {
  runtime: RuntimeStatus;
  health: RuntimeHealthT | null;
  skills: Skill[];
  behaviors: Pack[];
  selectedBehaviorId: string | null;
  events: EventT[];
  refreshHealth: () => Promise<void>;
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
