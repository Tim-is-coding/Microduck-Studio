/**
 * Speech recognition in the browser (ADR-0008): what the person says to the Studio becomes the
 * same `POST /api/say` as a typed phrase. The runtime only ever gets text, never audio.
 *
 * Where the recognition runs matters more than anything else here. Chrome and Edge can do it on
 * the device (`processLocally`, with a one-off language pack); without that, and in Safari, the
 * recording goes to the browser maker's servers. So:
 *
 *   - on the device if the browser can, and it is always asked first;
 *   - a missing language pack is offered as a download, never fetched unasked;
 *   - over the network only after the person agreed to it, and the listening line says where
 *     the recording goes for as long as it listens (§7's rule for camera frames, applied to the
 *     microphone).
 *
 * Nothing here listens without a click, and nothing keeps listening once the row that started
 * it is gone (`Listener.stop()` on unmount).
 */

/** The part of `SpeechRecognition` we use; `lib.dom` does not carry it everywhere yet. */
export interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  processLocally?: boolean;
  phrases?: unknown[];
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export interface RecognitionResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

type Availability = "available" | "downloadable" | "downloading" | "unavailable";

export interface RecognitionClass {
  new (): Recognition;
  available?: (options: { langs: string[]; processLocally?: boolean }) => Promise<Availability>;
  install?: (options: { langs: string[]; processLocally?: boolean }) => Promise<boolean>;
}

export interface SpeechEnv {
  Recognition: RecognitionClass | null;
  Phrase: (new (phrase: string, boost: number) => unknown) | null;
  userAgent: string;
}

/** What the browser offers. Everything below takes it as an argument, so tests can fake it. */
export function browserEnv(): SpeechEnv {
  if (typeof window === "undefined") return { Recognition: null, Phrase: null, userAgent: "" };
  const w = window as unknown as Record<string, unknown>;
  const Recognition = (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as RecognitionClass | null;
  const Phrase = (w.SpeechRecognitionPhrase ?? null) as SpeechEnv["Phrase"];
  return { Recognition, Phrase, userAgent: navigator.userAgent };
}

/**
 * - `local`: recognised on this device.
 * - `download`: could be, after a one-off language pack.
 * - `cloud`: only by sending the recording to `vendor`.
 * - `none`: this browser cannot (Firefox), or not in this language.
 */
export type Where = "local" | "download" | "cloud" | "none";

export const RECOGNITION_LANG = { de: "de-DE", en: "en-US" } as const;

export async function whereItRuns(env: SpeechEnv, lang: string): Promise<Where> {
  const R = env.Recognition;
  if (!R) return "none";
  if (typeof R.available !== "function") return "cloud"; // Safari, older Chrome: cannot tell, so assume the worst
  try {
    const local = await R.available({ langs: [lang], processLocally: true });
    if (local === "available") return "local";
    if (local === "downloadable" || local === "downloading") return "download";
    const remote = await R.available({ langs: [lang], processLocally: false });
    return remote === "unavailable" ? "none" : "cloud";
  } catch {
    return "cloud";
  }
}

/** Download the language pack for on-device recognition. Call from a click. */
export async function installLocal(env: SpeechEnv, lang: string): Promise<boolean> {
  const R = env.Recognition;
  if (!R || typeof R.install !== "function") return false;
  try {
    return await R.install({ langs: [lang], processLocally: true });
  } catch {
    return false;
  }
}

/** Whose servers hear the recording when it is not recognised on the device. */
export function vendor(userAgent: string): string | null {
  if (/Edg\//.test(userAgent)) return "Microsoft";
  if (/(Chrome|Chromium|CriOS)\//.test(userAgent)) return "Google";
  if (/Safari\//.test(userAgent)) return "Apple";
  return null;
}

export type ListenError = "denied" | "no-mic" | "network" | "language" | "other";

export function listenError(code: string): ListenError | null {
  switch (code) {
    case "no-speech":
    case "aborted":
      return null; // silence, or our own stop(): not a problem to report
    case "not-allowed":
    case "service-not-allowed":
      return "denied";
    case "audio-capture":
      return "no-mic";
    case "network":
      return "network";
    case "language-not-supported":
      return "language";
    default:
      return "other";
  }
}

export interface ListenOptions {
  lang: string;
  local: boolean;
  /** Phrases to listen out for (trigger and stop words); a hint where the browser takes one. */
  phrases?: string[];
  onInterim(text: string): void;
  onFinal(text: string): void;
  onError(error: ListenError): void;
  onListening(on: boolean): void;
}

/**
 * One microphone session, kept alive across the browser's own pauses: Chrome ends a
 * continuous recognition after some seconds of silence, so `onend` starts it again for as long
 * as `stop()` has not been called. An error that will not go away by retrying ends it.
 */
export class Listener {
  private rec: Recognition | null = null;
  private wanted = false;
  private restarts = 0; // sessions in a row that ended within a second of starting
  private startedAt = 0;

  constructor(
    private readonly env: SpeechEnv,
    private readonly options: ListenOptions,
  ) {}

  get active(): boolean {
    return this.wanted;
  }

  start(): boolean {
    const R = this.env.Recognition;
    if (!R || this.wanted) return false;
    this.wanted = true;
    this.restarts = 0;
    this.rec = this.make(R, true);
    return this.begin();
  }

  stop(): void {
    this.wanted = false;
    const rec = this.rec;
    this.rec = null;
    if (!rec) return;
    rec.onend = null;
    rec.onresult = null;
    rec.onerror = null;
    try {
      rec.abort();
    } catch {
      /* already stopped */
    }
    this.options.onInterim("");
    this.options.onListening(false);
  }

  private make(R: RecognitionClass, withPhrases: boolean): Recognition {
    const rec = new R();
    rec.lang = this.options.lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    if (this.options.local) rec.processLocally = true;
    // A hint, and only on the device. A browser that will not take it says so with
    // `phrases-not-supported`, and the next session goes without.
    if (withPhrases && this.options.local && this.env.Phrase && this.options.phrases?.length) {
      try {
        rec.phrases = this.options.phrases.map((p) => new this.env.Phrase!(p, 5));
      } catch {
        /* a browser that has the class but not the attribute */
      }
    }
    rec.onstart = () => {
      this.startedAt = Date.now();
      this.options.onListening(true);
    };
    rec.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const said = result?.[0]?.transcript.trim();
        if (!said) continue;
        if (result!.isFinal) this.options.onFinal(said);
        else interim += (interim ? " " : "") + said;
      }
      this.options.onInterim(interim);
    };
    rec.onerror = (event) => {
      if (event.error === "phrases-not-supported" && this.wanted) {
        this.rec = this.make(R, false); // try once more, without the hint
        return;
      }
      const error = listenError(event.error);
      if (error === null) return;
      this.options.onError(error);
      this.stop();
    };
    rec.onend = () => {
      this.options.onInterim("");
      if (!this.wanted) return;
      // A pause after real listening is normal; ending again and again at once is not.
      this.restarts = Date.now() - this.startedAt < 1000 ? this.restarts + 1 : 0;
      if (this.restarts > 5) {
        this.options.onError("other");
        this.stop();
        return;
      }
      if (this.rec) this.begin();
    };
    return rec;
  }

  private begin(): boolean {
    try {
      this.rec?.start();
      return true;
    } catch {
      this.options.onError("other");
      this.stop();
      return false;
    }
  }
}

/** Stored per browser: the person agreed once that recordings may go to this vendor. */
export const CLOUD_CONSENT_KEY = "duckstudio.speech.cloud";

export function hasCloudConsent(who: string | null): boolean {
  try {
    return localStorage.getItem(CLOUD_CONSENT_KEY) === (who ?? "unknown");
  } catch {
    return false;
  }
}

export function setCloudConsent(who: string | null, agreed: boolean): void {
  try {
    if (agreed) localStorage.setItem(CLOUD_CONSENT_KEY, who ?? "unknown");
    else localStorage.removeItem(CLOUD_CONSENT_KEY);
  } catch {
    /* without storage we simply ask again next time */
  }
}
