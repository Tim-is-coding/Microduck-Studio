# ADR-0009: AI vendors with keys from the Studio

- Status: accepted
- Date: 2026-09-24

## Context

ADR-0004 made the VLM a perception adapter: one question, one frame, a point back, 0.5–2 Hz,
never in the braking loop, opt-in per behavior by vendor name. It shipped Claude and a local
stub, switched on with `DUCKSTUDIO_VLM=anthropic` and a key in the environment. That is a
terminal step, and §3.1 says the Studio is for people without one.

Two things push beyond that. Finding real people: the local detectors only find the magenta
marker of the simulation, and neither upstream's `duck-detect` nor `pngwn/microduck-detector`
finds people (they find ducks, docs/upstream-notes.md). And Tim wants to host Duck Studio
later, keeping keys for the people who want that, or have them self-host with their own.

What the vendors offer (read from their pages on 2026-09-24):

- **Google Gemini**: `gemini-robotics-er-2-preview` points at things — `[y, x]` normalised to
  0–1000 — and has a free tier, as do the Flash and Flash-Lite models. On the free tier
  Google's terms allow human review of inputs and use them to improve its products, and
  "You may use only Paid Services when making API Clients available to users in the European
  Economic Area, Switzerland, or the United Kingdom."
- **Anthropic Claude**: vision and structured output, pay as you go, no free tier. Key at
  platform.claude.com.
- **OpenAI**: `gpt-6-luna` is cheap and takes images with structured output; no free tier
  for it. OpenAI's own vision guide says its models "struggle with tasks requiring precise
  spatial localization".
- Groq, Mistral and OpenRouter have free tiers, but their daily limits (50–1000 requests)
  cover minutes of looking at 0.5 Hz, and none documents pointing. Not offered.

## Decision

1. **Three vendors, one router.** Google, Anthropic and OpenAI are `VlmProvider`s
   (`perception/vlm.py`, `perception/vlm_rest.py`); a catalogue (`perception/vendors.py`)
   carries names, the page to get a key on, pricing, a dated note on what to know, and the
   models that make sense for pointing. `VlmRouter` answers each question with the vendor the
   behavior named, if there is a key for it — else the local stub, which the log names as a
   stand-in and which sends nothing anywhere. A key for one vendor is never consent for
   another.
2. **Keys are typed into the Studio**, on a „KI-Anbieter" page: one card per vendor, a link to
   get a key, the free-tier and privacy notes in plain words, a model choice, and „Prüfen und
   speichern". The runtime checks the key with the vendor first (one free GET on the chosen
   model) and keeps only keys that work.
3. **A key is stored to be used, never to be read back.** One JSON file outside the repo
   (`~/.config/duckstudio/keys.json`, or `$DUCKSTUDIO_KEYS`), created 0600 in a 0700 directory.
   The API returns whether there is a key and its last four characters; no key goes into an
   event, a log line, an error or a URL (Google's key goes in `x-goog-api-key`, not `?key=`).
   Tests point `DUCKSTUDIO_KEYS` at a temporary file, always.
4. **Self-hosting keeps the environment.** `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`,
   `OPENAI_API_KEY` count only for vendors named in `DUCKSTUDIO_VLM` (now a list), as in
   ADR-0004: a key lying around is not consent. The Studio shows such a key as coming from the
   environment and does not offer to remove it.
5. **Google is recommended, with its caveat on the card.** It is the one vendor that documents
   pointing, and it can be tried without paying. The card says in the same breath that on the
   free tier people at Google may look at the pictures, and that offering Duck Studio to others
   in the EU requires the paid service.
6. **Finding people is a behavior, not a new detector.** `behaviors/follow-with-ai.behavior.yaml`
   asks „Wo ist die nächste Person?" (`perceive: vlm.target`) and walks toward the target, with
   Google opted in. Without a key it runs on the practice duck and the stub; with one it finds
   real people. The fast local person detector stays the slot for tight following (§4).
7. **`anthropic` is a dependency**, no longer an extra: a person without a terminal cannot run
   `uv sync --extra vlm`. Google and OpenAI need no SDK — one `httpx` POST per question.

## Alternatives considered

- **A local person detector (YOLOX-nano, Apache-2.0) first.** Still the right tool for
  10–30 Hz following, and still open. Chosen against for now because a vendor key does more
  than people — scene questions, targets, later the planner — and Tim wants that path.
- **Keys in the repo's `.env` or in `DUCKSTUDIO_ROOT`.** One `git add -A` from a public commit.
- **The OS keychain.** Better at rest, but three platforms, a native dependency, and nothing a
  hosted Duck Studio could use; the file store is the interface a hosted key vault replaces.
- **Offering every free vision API.** Their daily limits make them demos, not eyes.
- **Recommending Google's free tier without the caveat.** It is the easiest start, and the one
  that sends pictures from someone's living room to human reviewers. The Studio says so.

## Consequences

- „Folge mir (mit KI)" and „Geh zu dem Ding" work with any of the three vendors once a key is
  in; the vendor select in the editor lists them and marks those without a key.
- The Gemini and OpenAI request shapes were read from their references, not run: no key was at
  hand. The key checks were run live against all three with a made-up key (all three said
  „rejected", nothing was stored). **The first real answer from each vendor still has to be
  checked by hand**, especially Gemini's point order and `responseSchema` dialect.
- Hosting, when it comes, needs per-person `KeyStore`s and an encrypted vault behind the same
  interface, plus the paid tier for EU users under Google's terms.
- The notes in the catalogue are dated (`CHECKED`); prices and model names move, and the
  Studio shows the date.
