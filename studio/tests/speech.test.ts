import { beforeEach, describe, expect, it } from "vitest";

import { Listener, listenError, vendor, whereItRuns, type Recognition, type RecognitionClass, type SpeechEnv } from "../src/speech/speech";

/** A browser recogniser we can drive: `said()` delivers results, `end()` is the browser pausing. */
class FakeRecognition implements Recognition {
  static made: FakeRecognition[] = [];
  static local: string = "available";
  static remote: string = "available";
  static async available(o: { processLocally?: boolean }) {
    return (o.processLocally ? FakeRecognition.local : FakeRecognition.remote) as "available";
  }
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  processLocally?: boolean;
  phrases?: unknown[];
  onresult: Recognition["onresult"] = null;
  onerror: Recognition["onerror"] = null;
  onend: Recognition["onend"] = null;
  onstart: Recognition["onstart"] = null;
  running = false;
  constructor() {
    FakeRecognition.made.push(this);
  }
  start() {
    this.running = true;
    this.onstart?.();
  }
  stop() {
    this.running = false;
  }
  abort() {
    this.running = false;
  }
  said(text: string, isFinal = true) {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
  }
  end() {
    this.running = false;
    this.onend?.();
  }
  fail(error: string) {
    this.onerror?.({ error });
  }
}

const env = (overrides: Partial<SpeechEnv> = {}): SpeechEnv => ({
  Recognition: FakeRecognition as unknown as RecognitionClass,
  Phrase: class {
    constructor(
      public phrase: string,
      public boost: number,
    ) {}
  },
  userAgent: "Mozilla/5.0 Chrome/140.0",
  ...overrides,
});

function recorder() {
  const log = { final: [] as string[], interim: [] as string[], errors: [] as string[], on: [] as boolean[] };
  return {
    log,
    options: (local: boolean) => ({
      lang: "de-DE",
      local,
      phrases: ["Folge mir", "Stopp"],
      onFinal: (t: string) => log.final.push(t),
      onInterim: (t: string) => log.interim.push(t),
      onError: (e: string) => log.errors.push(e),
      onListening: (on: boolean) => log.on.push(on),
    }),
  };
}

beforeEach(() => {
  FakeRecognition.made = [];
  FakeRecognition.local = "available";
  FakeRecognition.remote = "available";
});

describe("where recognition runs", () => {
  it("prefers the device, offers a download, and falls back to the network", async () => {
    expect(await whereItRuns(env(), "de-DE")).toBe("local");
    FakeRecognition.local = "downloadable";
    expect(await whereItRuns(env(), "de-DE")).toBe("download");
    FakeRecognition.local = "unavailable";
    expect(await whereItRuns(env(), "de-DE")).toBe("cloud");
    FakeRecognition.remote = "unavailable";
    expect(await whereItRuns(env(), "de-DE")).toBe("none");
  });

  it("assumes the network when the browser cannot say (Safari)", async () => {
    class NoAvailable extends FakeRecognition {}
    Object.defineProperty(NoAvailable, "available", { value: undefined });
    expect(await whereItRuns(env({ Recognition: NoAvailable as unknown as RecognitionClass }), "de-DE")).toBe("cloud");
  });

  it("knows no recognition at all (Firefox)", async () => {
    expect(await whereItRuns(env({ Recognition: null }), "de-DE")).toBe("none");
  });

  it("names whose servers hear the recording", () => {
    expect(vendor("Mozilla/5.0 Chrome/140.0 Safari/537.36")).toBe("Google");
    expect(vendor("Mozilla/5.0 Chrome/140.0 Safari/537.36 Edg/140.0")).toBe("Microsoft");
    expect(vendor("Mozilla/5.0 Version/19.0 Safari/605.1.15")).toBe("Apple");
    expect(vendor("Mozilla/5.0 Firefox/140.0")).toBeNull();
  });
});

describe("Listener", () => {
  it("hands over final results, shows interim ones, and asks for on-device recognition", () => {
    const { log, options } = recorder();
    const l = new Listener(env(), options(true));
    expect(l.start()).toBe(true);
    const rec = FakeRecognition.made[0]!;
    expect(rec.processLocally).toBe(true);
    expect(rec.continuous && rec.interimResults).toBe(true);
    expect(rec.phrases).toHaveLength(2);
    rec.said("folge", false);
    rec.said("Folge mir");
    expect(log.interim).toContain("folge");
    expect(log.final).toEqual(["Folge mir"]);
  });

  it("does not ask for the device, nor send the phrase hint, over the network", () => {
    const { options } = recorder();
    new Listener(env(), options(false)).start();
    const rec = FakeRecognition.made[0]!;
    expect(rec.processLocally).toBeUndefined();
    expect(rec.phrases).toBeUndefined();
  });

  it("keeps listening across the browser's pauses until stopped", () => {
    const { log, options } = recorder();
    const l = new Listener(env(), options(true));
    l.start();
    const rec = FakeRecognition.made[0]!;
    (l as unknown as { startedAt: number }).startedAt = Date.now() - 5000; // it listened a while
    rec.end();
    expect(rec.running).toBe(true); // started again
    l.stop();
    expect(rec.running).toBe(false);
    rec.end(); // a late end after stop() must not restart it
    expect(rec.running).toBe(false);
    expect(log.on.at(-1)).toBe(false);
  });

  it("gives up when the browser ends every session at once", () => {
    const { log, options } = recorder();
    const l = new Listener(env(), options(true));
    l.start();
    for (let i = 0; i < 10 && l.active; i++) FakeRecognition.made[0]!.end();
    expect(l.active).toBe(false);
    expect(log.errors).toEqual(["other"]);
  });

  it("stops on a refused microphone, and ignores silence", () => {
    const { log, options } = recorder();
    const l = new Listener(env(), options(true));
    l.start();
    FakeRecognition.made[0]!.fail("no-speech");
    expect(l.active).toBe(true);
    FakeRecognition.made[0]!.fail("not-allowed");
    expect(l.active).toBe(false);
    expect(log.errors).toEqual(["denied"]);
  });

  it("retries without the phrase hint when the browser will not take it", () => {
    const { log, options } = recorder();
    const l = new Listener(env(), options(true));
    l.start();
    FakeRecognition.made[0]!.fail("phrases-not-supported");
    FakeRecognition.made[0]!.end();
    const second = FakeRecognition.made[1]!;
    expect(second.running).toBe(true);
    expect(second.phrases).toBeUndefined();
    expect(log.errors).toEqual([]);
  });
});

describe("error codes", () => {
  it("maps the browser's words to ours", () => {
    expect(listenError("aborted")).toBeNull();
    expect(listenError("audio-capture")).toBe("no-mic");
    expect(listenError("network")).toBe("network");
    expect(listenError("whatever")).toBe("other");
  });
});
