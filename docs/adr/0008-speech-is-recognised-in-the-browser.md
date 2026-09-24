# ADR-0008: Speech is recognised in the browser, on the device where it can be

- Status: accepted
- Date: 2026-09-24

## Context

`CLAUDE.md` §9 left open where speech recognition runs: in the runtime, from the duck's
microphone, or in the browser. v1 had a stand-in — the Studio's „Ich sage: …“ row posts typed
or clicked phrases to `POST /api/say`, and the executor matches them against trigger phrases
and `until: speech` conditions.

What we know on 2026-09-24:

- The duck's microphone is not reachable yet. Upstream has no audio method on the sockets we
  use, the simulated duck has no microphone, and the real one arrives in December.
- Browsers ship `SpeechRecognition`. Chrome (and Edge) can recognise **on the device**
  (`processLocally`, with a language pack fetched once through `SpeechRecognition.install()`;
  `SpeechRecognition.available()` says which applies). Without that — and always in Safari,
  where we cannot tell — the audio goes to the browser maker's servers. Firefox has none.
- A local model in the runtime (Whisper and relatives) would be a heavy dependency for a
  runtime that runs on a laptop today and must stay light.

§7 already says camera frames leave the runtime only to the person's own Studio, and that a
VLM call is opt-in and visibly marked. A microphone deserves at least the same.

## Decision

1. **The Studio recognises, the runtime gets text.** A spoken phrase goes to the same
   `POST /api/say` as a typed one. Audio never reaches the runtime, the duck or the event log.
2. **On the device first.** Clicking the microphone asks the browser where it can recognise
   the Studio's language (`de-DE` / `en-US`):
   - on the device → listens at once, the line under the row says „wird auf diesem Gerät
     erkannt“;
   - after a language pack → offers the download (one click, never unasked), with the network
     as the other button;
   - only over the network → asks first, naming who receives the recording (Google, Microsoft,
     Apple from the user agent, else „den Hersteller deines Browsers“). The yes is kept per
     browser (`localStorage`), and for as long as it listens the line says „Aufnahme geht an
     Google“ in the warning colour;
   - not at all → the microphone button is disabled and says which browsers can.
3. **Only while visible and connected.** Listening starts with a click and ends with a click,
   when the row leaves the screen (another tab, the editor), when the runtime is lost, or when
   the language changes. The browser's own pauses are bridged; a session that keeps ending at
   once stops with a sentence instead of spinning.
4. **Phrases are found inside sentences.** The executor matches a phrase when its words appear
   in order, as whole words, in what was heard (`phrase_in`): „Okay, folge mir bitte“ starts
   „Folge mir“, „Stopp jetzt“ ends a step, „Stoppuhr“ does not. The longest matching trigger
   wins. Typed phrases go through the same rule.
5. **The Studio says what it heard** — „Gehört: „…“, „Folge mir“ startet.“ or „… das passt zu
   keinem Auslöser.“ — so speaking to a duck that does nothing is never a silent failure.

## Alternatives considered

- **Runtime, from the duck's microphone.** The right place for a duck that listens when you
  talk to *it*, and it is still where this goes (a speech backend behind the same
  `executor.say`). Not possible before the hardware and an upstream audio path exist.
- **Runtime, from the laptop's microphone, with a local model.** Works offline in every
  browser, but adds a large model and audio capture to a runtime that should stay a small
  client of the upstream API, and duplicates what Chrome now does on the device.
- **Browser, network recognition without asking.** Simplest, and what most sites do. Rejected:
  a person without a terminal cannot be expected to know Chrome sends their voice to Google;
  the Studio has to say it.
- **Exact phrase matching only.** Safe against accidental triggers, but recognisers hear
  whole sentences; a duck that only reacts to a bare „Folge mir“ would feel broken.

## Consequences

- „Folge mir“ can be said instead of clicked, on every desktop browser but Firefox.
- The smoke test drives the microphone with a stand-in recogniser (`scripts/smoke.mjs`), so CI
  checks the flow — on the device, the question before the network, stop on „Stopp“ — without
  audio. Real recognition quality is only checked by a person with a microphone.
- Word-in-sentence matching makes accidental triggers likelier („ich will nicht, dass du mir
  folgst“ does not match, „folge mir nicht“ does). Acceptable while a person watches the Studio;
  to revisit before the duck listens on its own.
- When the duck's microphone arrives, recognition there is a second source for the same call,
  and the question in point 2 is asked again for it.
