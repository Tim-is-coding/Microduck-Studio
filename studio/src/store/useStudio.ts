import { create } from "zustand";

import {
  BehaviorPack,
  BehaviorPackFromApi,
  Event,
  ExecutorStatus,
  RobotState,
  RuntimeHealth,
  HubPolicy,
  SkillManifest,
  type BehaviorPack as PackT,
  type BehaviorPackFromApi as Pack,
  type Event as EventT,
  type ExecutorStatus as ExecutorStatusT,
  type RobotState as RobotStateT,
  type RuntimeHealth as RuntimeHealthT,
  type HubPolicy as Policy,
  type SkillManifest as Skill,
} from "../schemas";
import { z } from "zod";

import { newBehavior, tidy } from "../editor/model";
import { t } from "../i18n";

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
  draft: PackT | null;
  draftIsNew: boolean;
  draftDirty: boolean;
  draftProblems: string[];
  saving: boolean;
  yamlText: string | null;
  catalogLoaded: boolean;
  refreshHealth: () => Promise<void>;
  refreshState: () => Promise<void>;
  refreshExecutor: () => Promise<void>;
  run: (behaviorId: string) => Promise<void>;
  abortRun: () => Promise<void>;
  say: (text: string) => Promise<void>;
  editBehavior: (id: string) => void;
  newDraft: () => void;
  updateDraft: (fn: (draft: PackT) => PackT) => void;
  validateDraft: () => Promise<void>;
  saveDraft: (thenRun: boolean) => Promise<boolean>;
  discardDraft: () => void;
  deleteBehavior: (id: string) => Promise<void>;
  loadYaml: (id: string) => Promise<void>;
  hubResults: Policy[] | null;
  hubBusy: boolean;
  hubError: string | null;
  searchHub: (query: string) => Promise<void>;
  clearHub: () => void;
  policyDetails: (repo: string) => Promise<Policy | null>;
  importPolicy: (repo: string, slot: string) => Promise<boolean>;
  removeSkill: (id: string) => Promise<void>;
  loadCatalog: () => Promise<void>;
  select: (id: string | null) => void;
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
  draft: null,
  draftIsNew: false,
  draftDirty: false,
  draftProblems: [],
  saving: false,
  yamlText: null,
  catalogLoaded: false,
  hubResults: null,
  hubBusy: false,
  hubError: null,

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

  editBehavior(id) {
    const pack = get().behaviors.find((b) => b.id === id);
    if (!pack) return;
    const { problems, ...rest } = pack;
    set({ draft: structuredClone(rest), draftIsNew: false, draftDirty: false, draftProblems: problems });
  },

  newDraft() {
    set({ draft: newBehavior(t("list.new")), draftIsNew: true, draftDirty: true, draftProblems: [], selectedBehaviorId: null });
  },

  updateDraft(fn) {
    const draft = get().draft;
    if (!draft) return;
    set({ draft: fn(draft), draftDirty: true });
  },

  async validateDraft() {
    const draft = get().draft;
    if (!draft) return;
    try {
      const res = await fetch("/api/behaviors/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tidy(draft)),
      });
      if (res.ok) {
        const body = (await res.json()) as { problems: string[] };
        if (get().draft === draft) set({ draftProblems: body.problems });
      }
    } catch {
      /* offline: keep the last result */
    }
  },

  async saveDraft(thenRun) {
    const draft = get().draft;
    if (!draft) return false;
    set({ saving: true });
    try {
      const res = await fetch(`/api/behaviors/${encodeURIComponent(draft.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tidy(draft)),
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({}))) as { detail?: { problems?: string[] } | string };
        const problems = typeof detail.detail === "object" && detail.detail?.problems ? detail.detail.problems : [String(detail.detail ?? res.statusText)];
        set({ draftProblems: problems });
        return false;
      }
      await get().loadCatalog();
      set({ draft: null, draftDirty: false, draftIsNew: false, selectedBehaviorId: draft.id, yamlText: null });
      if (thenRun) await get().run(draft.id);
      return true;
    } finally {
      set({ saving: false });
    }
  },

  discardDraft() {
    set((s) => ({ draft: null, draftDirty: false, draftIsNew: false, selectedBehaviorId: s.selectedBehaviorId }));
  },

  async deleteBehavior(id) {
    const res = await fetch(`/api/behaviors/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok) {
      console.error(await res.text());
      return;
    }
    set({ draft: null, draftDirty: false, selectedBehaviorId: null });
    await get().loadCatalog();
  },

  async loadYaml(id) {
    try {
      const res = await fetch(`/api/behaviors/${encodeURIComponent(id)}/yaml`);
      set({ yamlText: res.ok ? await res.text() : null });
    } catch {
      set({ yamlText: null });
    }
  },

  async searchHub(query) {
    set({ hubBusy: true, hubError: null });
    try {
      const url = `/api/hub/policies?limit=12&q=${encodeURIComponent(query)}`;
      set({ hubResults: await getJson(url, z.array(HubPolicy)), hubBusy: false });
    } catch (err) {
      console.error(err);
      set({ hubBusy: false, hubError: String(err), hubResults: [] });
    }
  },

  clearHub() {
    set({ hubResults: null, hubError: null });
  },

  async policyDetails(repo) {
    try {
      return await getJson(`/api/hub/policy?repo=${encodeURIComponent(repo)}`, HubPolicy);
    } catch (err) {
      console.error(err);
      set({ hubError: String(err) });
      return null;
    }
  },

  async importPolicy(repo, slot) {
    set({ hubBusy: true, hubError: null });
    try {
      const res = await fetch("/api/hub/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, slot }),
      });
      if (!res.ok) {
        set({ hubError: (await res.text()).slice(0, 300), hubBusy: false });
        return false;
      }
      await get().loadCatalog();
      set({ hubBusy: false });
      return true;
    } catch (err) {
      set({ hubError: String(err), hubBusy: false });
      return false;
    }
  },

  async removeSkill(id) {
    const res = await fetch(`/api/skills/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok) set({ hubError: (await res.text()).slice(0, 300) });
    await get().loadCatalog();
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
        catalogLoaded: true,
        // The Studio opens on the overview; after that, keep whatever is open unless it is gone.
        selectedBehaviorId:
          !s.catalogLoaded || (s.draft && s.draftIsNew)
            ? null
            : behaviors.some((b) => b.id === s.selectedBehaviorId)
              ? s.selectedBehaviorId
              : null,
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
