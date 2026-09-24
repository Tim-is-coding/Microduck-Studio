import { useCallback, useEffect, useRef, useState } from "react";

import { useLanguage } from "../i18n";
import {
  browserEnv,
  hasCloudConsent,
  installLocal,
  Listener,
  RECOGNITION_LANG,
  setCloudConsent,
  vendor,
  whereItRuns,
  type ListenError,
  type Where,
} from "./speech";

/**
 * - `off`: not listening.
 * - `ask-cloud`: the browser can only recognise over the network; waiting for a yes.
 * - `ask-download`: a language pack would let it recognise on the device; waiting for a click.
 * - `checking`: asking the browser where it can recognise (after the click, never before).
 * - `installing`: that pack is downloading.
 * - `listening`: the microphone is on.
 */
export type SpeechStatus = "off" | "checking" | "ask-cloud" | "ask-download" | "installing" | "listening";

export interface Speech {
  /** The browser has speech recognition at all (not Firefox). */
  supported: boolean;
  where: Where | null; // null until the first click asked the browser; "none" known at once
  vendor: string | null;
  status: SpeechStatus;
  /** Recognised on the device (true) or sent to `vendor` (false), while listening. */
  local: boolean;
  interim: string;
  error: ListenError | "download" | null;
  toggle(): void;
  agreeCloud(): void;
  download(): void;
  cancel(): void;
}

export function useSpeech(onHeard: (text: string) => void, phrases: string[], enabled: boolean): Speech {
  const language = useLanguage();
  const lang = RECOGNITION_LANG[language];
  const env = useRef(browserEnv()).current;
  const who = vendor(env.userAgent);
  const [where, setWhere] = useState<Where | null>(env.Recognition ? null : "none");
  const [status, setStatus] = useState<SpeechStatus>("off");
  const [local, setLocal] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<Speech["error"]>(null);
  const listener = useRef<Listener | null>(null);
  const heard = useRef(onHeard);
  heard.current = onHeard;
  const phraseKey = phrases.join("\n");

  const stop = useCallback(() => {
    listener.current?.stop();
    listener.current = null;
    setStatus("off");
  }, []);

  // Asked on the click, not on mount: opening a behavior must never depend on the browser's
  // speech stack (headless Chromium's shell crashes the tab on `available({processLocally})`).
  useEffect(() => setWhere(env.Recognition ? null : "none"), [env, lang]);

  // A new language, a new pack or a lost runtime ends the session; so does leaving the row.
  useEffect(() => stop, [stop, lang, phraseKey]);
  useEffect(() => {
    if (!enabled) stop();
  }, [enabled, stop]);

  const listen = useCallback(
    (onDevice: boolean) => {
      listener.current?.stop();
      setError(null);
      setLocal(onDevice);
      const l = new Listener(env, {
        lang,
        local: onDevice,
        phrases: phraseKey ? phraseKey.split("\n") : [],
        onInterim: setInterim,
        onFinal: (text) => heard.current(text),
        onError: (e) => setError(e),
        onListening: (on) => {
          if (!on && listener.current === l) setStatus("off");
        },
      });
      listener.current = l;
      if (l.start()) setStatus("listening");
    },
    [env, lang, phraseKey],
  );

  const toggle = useCallback(() => {
    if (status === "listening") return stop();
    if (status !== "off") return setStatus("off");
    const go = (w: Where) => {
      if (w === "local") listen(true);
      else if (w === "download") setStatus("ask-download");
      else if (w === "cloud") {
        if (hasCloudConsent(who)) listen(false);
        else setStatus("ask-cloud");
      } else {
        setError("language");
        setStatus("off");
      }
    };
    if (where !== null) return go(where);
    setStatus("checking");
    void whereItRuns(env, lang).then((w) => {
      setWhere(w);
      go(w);
    });
  }, [status, where, who, env, lang, listen, stop]);

  const agreeCloud = useCallback(() => {
    setCloudConsent(who, true);
    listen(false);
  }, [who, listen]);

  const download = useCallback(() => {
    setStatus("installing");
    setError(null);
    void installLocal(env, lang).then((ok) => {
      if (ok) {
        setWhere("local");
        listen(true);
      } else {
        setError("download");
        setStatus("off");
      }
    });
  }, [env, lang, listen]);

  return { supported: env.Recognition !== null, where, vendor: who, status, local, interim, error, toggle, agreeCloud, download, cancel: () => setStatus("off") };
}
