import { useCallback, useState } from "react";

import { language, phrases as phraseList, quote, t, text } from "../i18n";
import type { BehaviorPack } from "../schemas";
import { useSpeech, type Speech } from "../speech/useSpeech";
import { useStudio } from "../store/useStudio";
import { Icon } from "../ui/Icon";
import { packPhrases } from "./phrases";

interface Heard {
  said: string;
  started: string | null;
  running: boolean;
}

/**
 * „Ich sage: …“ — a phrase typed, clicked or spoken (ADR-0008) goes to the runtime as text; the
 * line below says what it made of it. The microphone is off until clicked, and says where the
 * recording goes for as long as it is on.
 */
export function SayRow({ pack, connected }: { pack: BehaviorPack; connected: boolean }) {
  const { say, behaviors, executor } = useStudio();
  const [phrase, setPhrase] = useState("");
  const [heard, setHeard] = useState<Heard | null>(null);
  const running = executor?.state === "running";

  const submit = useCallback(
    (value: string) => {
      const v = value.trim();
      if (!v) return;
      setPhrase("");
      void say(v).then((r) => r && setHeard({ said: v, started: r.started, running }));
    },
    [say, running],
  );
  const phrases = packPhrases(pack);
  const speech = useSpeech(submit, [...phrases, t("run.say.stop")], connected);
  const listening = speech.status === "listening";
  const startedName = heard?.started ? behaviors.find((b) => b.id === heard.started)?.name : undefined;

  return (
    <div className="sayblock">
      <form
        className="sayrow"
        onSubmit={(e) => {
          e.preventDefault();
          submit(phrase);
        }}
      >
        <label htmlFor="say">{t("run.say.label")}</label>
        <MicButton connected={connected} speech={speech} />
        <input
          disabled={!connected}
          id="say"
          onChange={(e) => setPhrase(e.target.value)}
          placeholder={listening ? t("speech.speak") : t("run.say.placeholder")}
          value={listening && speech.interim ? speech.interim : phrase}
        />
        <button className="btn small" disabled={!connected} type="submit">{t("run.say.button")}</button>
        <span className="phrases">
          {[...(pack.trigger.kind === "speech" ? phraseList(pack.trigger.phrases) : []), t("run.say.stop")].map((p) => (
            <button className="phrase" disabled={!connected} key={p} onClick={() => submit(p)} type="button">{quote(p)}</button>
          ))}
        </span>
      </form>
      <SpeechLine speech={speech} />
      {heard && (
        <div aria-live="polite" className="heard">
          {heard.started
            ? t("run.heard.started", { said: quote(heard.said), behavior: quote(startedName ? text(startedName) : heard.started) })
            : heard.running
              ? t("run.heard.running", { said: quote(heard.said) })
              : t("run.heard.none", { said: quote(heard.said) })}
        </div>
      )}
    </div>
  );
}

function MicButton({ speech, connected }: { speech: Speech; connected: boolean }) {
  const listening = speech.status === "listening";
  const none = !speech.supported;
  const label = none ? t("speech.none") : listening ? t("speech.stop") : t("speech.listen");
  return (
    <button
      aria-label={label}
      aria-pressed={listening}
      className={`mic${listening ? " on" : ""}`}
      disabled={!connected || none || speech.status === "checking" || speech.status === "installing"}
      onClick={speech.toggle}
      title={label}
      type="button"
    >
      <Icon name="mic" />
    </button>
  );
}

function SpeechLine({ speech }: { speech: Speech }) {
  const who = speech.vendor ?? t("speech.vendor.unknown");
  const lang = language() === "de" ? "Deutsch" : "English";
  if (speech.status === "listening") {
    return (
      <div aria-live="polite" className={`speechline ${speech.local ? "local" : "cloud"}`}>
        <span className="dot" /> {t("speech.listening")} · {speech.local ? t("speech.where.local") : t("speech.where.cloud", { vendor: who })}
      </div>
    );
  }
  if (speech.status === "ask-cloud") {
    return (
      <div className="speechline ask" role="dialog">
        <p>{t("speech.ask.cloud", { vendor: who })}</p>
        <div className="actions">
          <button className="btn small primary" onClick={speech.agreeCloud} type="button">{t("speech.ask.cloud.yes")}</button>
          <button className="btn small" onClick={speech.cancel} type="button">{t("speech.cancel")}</button>
        </div>
      </div>
    );
  }
  if (speech.status === "ask-download" || speech.status === "installing") {
    const busy = speech.status === "installing";
    return (
      <div className="speechline ask" role="dialog">
        <p>{busy ? t("speech.installing") : t("speech.ask.download", { lang })}</p>
        {!busy && (
          <div className="actions">
            <button className="btn small primary" onClick={speech.download} type="button">{t("speech.ask.download.yes")}</button>
            <button className="btn small" onClick={speech.agreeCloud} type="button">{t("speech.ask.download.cloud", { vendor: who })}</button>
            <button className="btn small" onClick={speech.cancel} type="button">{t("speech.cancel")}</button>
          </div>
        )}
      </div>
    );
  }
  if (speech.error) return <div className="speechline error" role="status">{t(`speech.error.${speech.error}`)}</div>;
  return null;
}
