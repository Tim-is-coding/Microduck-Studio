import { create } from "zustand";

import {
  AiInfo,
  AiVendor,
  LocalDetector,
  type AiInfo as AiInfoT,
  BehaviorPack,
  BehaviorPackFromApi,
  Event,
  ExecutorStatus,
  RobotState,
  RunRecord,
  RuntimeHealth,
  HubPolicy,
  SkillManifest,
  type BehaviorPack as PackT,
  type BehaviorPackFromApi as Pack,
  type Event as EventT,
  type ExecutorStatus as ExecutorStatusT,
  type RobotState as RobotStateT,
  type RunRecord as Run,
  type RuntimeHealth as RuntimeHealthT,
  type BackendKind as BackendKindT,
  type HubPolicy as Policy,
  type SkillManifest as Skill,
} from "../schemas";
import { z } from "zod";

import { newBehavior, tidy } from "../editor/model";
import { NO_HISTORY, record, redo, undo, type History } from "../editor/history";

export type RuntimeStatus = "loading" | "online" | "offline";

interface StudioState {
  runtime: RuntimeStatus;
  health: RuntimeHealthT | null;
  state: RobotStateT | null;
  executor: ExecutorStatusT | null;
  /** The last few runs, newest first — reloaded whenever one ends. */
  runs: Run[];
  skills: Skill[];
  behaviors: Pack[];
  selectedBehaviorId: string | null;
  events: EventT[];
  draft: PackT | null;
  draftIsNew: boolean;
  draftDirty: boolean;
  draftProblems: string[];
  /** Undo for the draft; reset whenever a different draft is opened (`editor/history.ts`). */
  history: History;
  /** One sentence about how this draft came to be — an imported file that had to be renamed. */
  draftNotice: string | null;
  saving: boolean;
  yamlText: string | null;
  catalogLoaded: boolean;
  refreshHealth: () => Promise<void>;
  refreshState: () => Promise<void>;
  refreshExecutor: () => Promise<void>;
  loadRuns: () => Promise<void>;
  run: (behaviorId: string) => Promise<void>;
  abortRun: () => Promise<void>;
  /** What the runtime made of a phrase: the behavior it started, if any; null if unreachable. */
  say: (text: string) => Promise<{ started: string | null } | null>;
  editBehavior: (id: string) => void;
  newDraft: (pack?: PackT, notice?: string) => void;
  updateDraft: (fn: (draft: PackT) => PackT) => void;
  undoDraft: () => void;
  redoDraft: () => void;
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
  /** Simulation, practice duck or the real one (ADR-0007). Resolves to an error sentence
   *  from the runtime, or null when it switched. */
  switchBackend: (kind: BackendKindT, host?: string) => Promise<string | null>;
  pushEvent: (e: EventT) => void;
  /** AI vendors and whether a key is there (ADR-0009). */
  ai: AiInfoT | null;
  loadAi: () => Promise<void>;
  /** Checks the key with the vendor and keeps it; null on success, else the runtime's reason. */
  saveAiKey: (vendor: string, key: string, model?: string) => Promise<string | null>;
  removeAiKey: (vendor: string) => Promise<void>;
  setAiModel: (vendor: string, model: string) => Promise<void>;
  /** Fetch the local person detector once (ADR-0010); null on success, else a reason. */
  downloadPersonModel: () => Promise<string | null>;
  setPersonMode: (mode: "auto" | "people") => Promise<void>;
}

/** FastAPI puts its sentence in `detail`; show that, not the JSON around it. */
function detail(body: string): string {
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed && typeof parsed.detail === "string") return parsed.detail;
  } catch {
    /* not JSON: the body is the message */
  }
  return body.slice(0, 300);
}

function replaceVendor(
  set: (partial: Partial<StudioState>) => void,
  get: () => StudioState,
  vendor: z.infer<typeof AiVendor>,
): void {
  const ai = get().ai;
  if (ai) set({ ai: { ...ai, vendors: ai.vendors.map((v) => (v.id === vendor.id ? vendor : v)) } });
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
  runs: [],
  skills: [],
  behaviors: [],
  selectedBehaviorId: null,
  events: [],
  draft: null,
  draftIsNew: false,
  draftDirty: false,
  draftProblems: [],
  history: NO_HISTORY,
  draftNotice: null,
  saving: false,
  yamlText: null,
  catalogLoaded: false,
  hubResults: null,
  hubBusy: false,
  hubError: null,
  ai: null,

  async loadAi() {
    try {
      set({ ai: await getJson("/api/ai", AiInfo) });
    } catch {
      /* the settings page says the runtime is not there */
    }
  },

  async saveAiKey(vendor, key, model) {
    let res: Response;
    try {
      res = await fetch(`/api/ai/${encodeURIComponent(vendor)}/key`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(model ? { key, model } : { key }),
      });
    } catch {
      return "unreachable";
    }
    if (!res.ok) {
      try {
        const reason = (await res.json())?.detail?.reason;
        return typeof reason === "string" ? reason : "failed";
      } catch {
        return "failed";
      }
    }
    replaceVendor(set, get, AiVendor.parse(await res.json()));
    void get().refreshHealth();
    return null;
  },

  async removeAiKey(vendor) {
    const res = await fetch(`/api/ai/${encodeURIComponent(vendor)}/key`, { method: "DELETE" });
    if (res.ok) replaceVendor(set, get, AiVendor.parse(await res.json()));
    void get().refreshHealth();
  },

  async setAiModel(vendor, model) {
    const res = await fetch(`/api/ai/${encodeURIComponent(vendor)}/model`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    if (res.ok) replaceVendor(set, get, AiVendor.parse(await res.json()));
  },

  async downloadPersonModel() {
    let res: Response;
    try {
      res = await fetch("/api/ai/local/download", { method: "POST" });
    } catch {
      return "unreachable";
    }
    if (!res.ok) return "download";
    const local = LocalDetector.parse(await res.json());
    const ai = get().ai;
    if (ai) set({ ai: { ...ai, local } });
    return null;
  },

  async setPersonMode(mode) {
    const res = await fetch("/api/ai/local/mode", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: mode }),
    });
    if (!res.ok) return;
    const local = LocalDetector.parse(await res.json());
    const ai = get().ai;
    if (ai) set({ ai: { ...ai, local } });
  },

  async refreshHealth() {
    const before = get().runtime;
    try {
      const health = await getJson("/api/health", RuntimeHealth);
      set({ runtime: "online", health });
      // A Studio opened before the runtime was up would otherwise stay empty forever: the
      // catalog is loaded once, and that one attempt failed. Load it when we can.
      if (before !== "online" || !get().catalogLoaded) {
        void get().loadCatalog();
        void get().loadRuns();
      }
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
    const before = get().executor;
    try {
      const executor = await getJson("/api/executor", ExecutorStatus);
      set({ executor });
      // A run ended. Comparing the runtime's own counter rather than the state catches a run
      // that started and finished between two polls, which a state change would miss.
      if (executor.runs_recorded !== before?.runs_recorded) void get().loadRuns();
    } catch {
      set({ executor: null });
    }
  },

  async loadRuns() {
    if (get().runtime !== "online") return;
    try {
      set({ runs: await getJson("/api/runs", z.array(RunRecord)) });
    } catch {
      /* the list is a convenience: keep the last one we had */
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
    if (!res.ok) return null;
    const { heard: _heard, started, ...status } = await res.json();
    set({ executor: ExecutorStatus.parse(status) });
    return { started: typeof started === "string" ? started : null };
  },

  editBehavior(id) {
    const pack = get().behaviors.find((b) => b.id === id);
    if (!pack) return;
    const { problems, ...rest } = pack;
    set({ draft: structuredClone(rest), draftIsNew: false, draftDirty: false, draftProblems: problems, history: NO_HISTORY, draftNotice: null });
  },

  newDraft(pack, notice) {
    set({
      draft: pack ?? newBehavior(),
      draftIsNew: true,
      draftDirty: true,
      draftProblems: [],
      history: NO_HISTORY,
      draftNotice: notice ?? null,
      selectedBehaviorId: null,
    });
  },

  updateDraft(fn) {
    const draft = get().draft;
    if (!draft) return;
    const next = fn(draft);
    set((s) => ({ draft: next, draftDirty: true, history: record(s.history, draft, next, Date.now()) }));
  },

  undoDraft() {
    const { draft, history } = get();
    const step = draft && undo(history, draft);
    if (step) set({ draft: step.draft, history: step.history, draftDirty: true });
  },

  redoDraft() {
    const { draft, history } = get();
    const step = draft && redo(history, draft);
    if (step) set({ draft: step.draft, history: step.history, draftDirty: true });
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
      set({ draft: null, draftDirty: false, draftIsNew: false, history: NO_HISTORY, draftNotice: null, selectedBehaviorId: draft.id, yamlText: null });
      if (thenRun) await get().run(draft.id);
      return true;
    } finally {
      set({ saving: false });
    }
  },

  discardDraft() {
    set((s) => ({ draft: null, draftDirty: false, draftIsNew: false, history: NO_HISTORY, draftNotice: null, selectedBehaviorId: s.selectedBehaviorId }));
  },

  async deleteBehavior(id) {
    const res = await fetch(`/api/behaviors/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok) {
      console.error(await res.text());
      return;
    }
    set({ draft: null, draftDirty: false, history: NO_HISTORY, draftNotice: null, selectedBehaviorId: null });
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

  async switchBackend(kind, host = "") {
    try {
      const res = await fetch("/api/backend", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, host }),
      });
      if (!res.ok) return detail(await res.text());
      // Nothing the old duck said is true of the new one.
      set({ health: RuntimeHealth.parse(await res.json()), state: null });
      void get().refreshExecutor();
      return null;
    } catch (err) {
      return String(err);
    }
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
