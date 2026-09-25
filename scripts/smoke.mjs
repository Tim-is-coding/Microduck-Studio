/**
 * The paths unit tests cannot see: a real browser, a real runtime, the whole Studio.
 * Vitest checks the pure pieces (`studio/tests/`), pytest the runtime — this walks the
 * clicks in between and says which of them still work.
 *
 *   cd runtime && DUCKSTUDIO_BACKEND=mock DUCKSTUDIO_ROOT=/tmp/ds-smoke uv run python -m duckstudio
 *   cd studio  && pnpm dev            # or: pnpm build && pnpm preview  (STUDIO=…:4173)
 *   node scripts/smoke.mjs
 *
 * Needs playwright (`pnpm dlx playwright@latest install chromium`, or point CHROMIUM at a
 * browser you already have). It creates one behavior and deletes it again; point
 * DUCKSTUDIO_ROOT at a scratch directory anyway, so a failed run cannot leave anything in
 * the repo's `behaviors/`.
 *
 * Every wait here waits for a *condition*, never for a duration: this runs on CI machines
 * that are slower than any laptop, and a test that fails by being early is worse than none.
 */
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

const API = process.env.API ?? "http://localhost:8000";
const STUDIO = process.env.STUDIO ?? "http://localhost:5173";
const TIMEOUT = Number(process.env.TIMEOUT ?? 20_000);
const SMOKE_ID = "rauchtest";

let failures = 0;
async function check(name, body) {
  try {
    await body();
    console.log(`  ok    ${name}`);
  } catch (e) {
    failures++;
    console.log(`  FAIL  ${name}\n        ${e.message.split("\n")[0]}`);
  }
}
function is(actual, expected, what) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${what}: ${a} ≠ ${b}`);
}
function ok(condition, what) {
  if (!condition) throw new Error(what);
}

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const page = await browser.newPage({ viewport: { width: 1500, height: 940 }, locale: "de-DE", acceptDownloads: true });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

// Speech recognition (ADR-0008) without a microphone: a stand-in for the browser's recogniser,
// installed before the Studio loads. `__speechMode` picks what the browser claims to offer;
// `__say(text)` is the person speaking. No audio, no network.
await page.addInitScript(() => {
  window.__recs = [];
  window.__speechMode = "local";
  class FakeRecognition {
    static async available(o) {
      return o.processLocally && window.__speechMode !== "local" ? "unavailable" : "available";
    }
    constructor() {
      window.__recs.push(this);
    }
    start() {
      this.running = true;
      setTimeout(() => this.onstart?.(), 0);
    }
    stop() {
      this.running = false;
    }
    abort() {
      this.running = false;
    }
  }
  window.SpeechRecognition = FakeRecognition;
  window.__say = (text) =>
    window.__recs.at(-1)?.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: text } }] });
});

/** Poll until the thing is true, then say what it was. */
async function until(what, fn, timeout = TIMEOUT) {
  const deadline = Date.now() + timeout;
  let last;
  for (;;) {
    try {
      last = await fn();
      if (last) return last;
    } catch (e) {
      last = e.message;
    }
    if (Date.now() > deadline) throw new Error(`wartete vergeblich auf: ${what} (zuletzt: ${JSON.stringify(last)})`);
    await page.waitForTimeout(100);
  }
}

/** Only saved behaviors have an `open` button; the dashed "new" card is a `.behavior-card` too,
 *  so counting cards alone would call an empty, still-loading Studio ready. */
const behaviorCards = () => page.locator(".behavior-card .open").count();
/** The name card exists only while a behavior is editable — that is what "the editor is open"
 *  means on the route: the same stations, with their controls switched on. */
const editorOpen = () => page.locator(".card.namecard").isVisible();
const editorGone = async () => !(await page.locator(".card.namecard").isVisible());
/** Steps are the stations the rail wraps in a div of their own; trigger, "add", the always
 *  rules and the VLM switch are direct children of `.rail` and must not be counted. */
const steps = () => page.locator(".rail > div > .station").count();
const nameField = () => page.locator(".card.namecard input.name");
const packs = async () => (await (await fetch(`${API}/api/behaviors`)).json()).map((b) => b.id);

async function backToOverview() {
  await page.getByRole("button", { name: /^(Übersicht|Overview)$/ }).click();
  await until("Übersicht", () => behaviorCards());
}
async function openFirstForEditing() {
  await page.locator(".behavior-card .btn", { hasText: "Öffnen" }).first().click();
  await until("Bearbeiten-Knopf", () => page.getByRole("button", { name: /Bearbeiten/ }).isVisible());
  await page.getByRole("button", { name: /Bearbeiten/ }).click();
  await until("Editor", editorOpen);
}
/** The picker opens in a gap of the route; every block in it is an `.option` with a name. */
async function addStep(name) {
  const before = await steps();
  await page.locator(".station.add .addbtn").click();
  await until("Bausteine-Auswahl", () => page.locator(".picker .option").first().isVisible());
  await page.locator(".picker .option", { has: page.locator(".name", { hasText: name }) }).first().click();
  await until(`${name} kam dazu`, async () => (await steps()) === before + 1);
  return before;
}
async function discard() {
  await page.getByRole("button", { name: /^(Verwerfen|Discard)$/ }).click();
  await until("Editor geschlossen", editorGone);
}

try {
  await fetch(`${API}/api/behaviors/${SMOKE_ID}`, { method: "DELETE" }).catch(() => {});
  await page.goto(STUDIO, { waitUntil: "domcontentloaded" });
  await until("geladene Abläufe", async () => (await behaviorCards()) >= 2, 30_000);
  console.log("Studio-Rauchtest\n");

  await check("Übersicht zeigt die Abläufe und die verbundene Ente", async () => {
    ok((await behaviorCards()) >= 2, "keine Ablauf-Karten");
    is(await page.locator(".duckstatus").innerText(), "Übungsente verbunden", "Status");
  });

  await check("Bausteine liegen hinter ihrem Tab", async () => {
    await page.getByRole("button", { name: /^(Bausteine|Building blocks)$/ }).click();
    const blocks = await until("Bausteine", async () => (await page.locator(".card.block").count()) || false);
    ok(blocks >= 8, `nur ${blocks} Bausteine`);
    await backToOverview();
  });

  await check("Editor: Schritt hinzufügen, rückgängig, wiederholen", async () => {
    await openFirstForEditing();
    const before = await addStep("Quaken");
    await page.locator(".toolbar .iconbtn").first().click();
    await until("rückgängig", async () => (await steps()) === before);
    await page.locator(".toolbar .iconbtn").nth(1).click();
    await until("wiederholt", async () => (await steps()) === before + 1);
    await discard();
    await backToOverview(); // discarding an edit keeps that behavior open; the list is one click away
  });

  await check("Kopie anlegen", async () => {
    await page.locator(".behavior-card").first().locator("button[title='Kopie anlegen']").click();
    await until("Editor mit Kopie", async () => (await editorOpen()) && (await nameField().inputValue()).includes("(Kopie)"));
    ok((await page.locator(".card.namecard .sub").innerText()).includes("-copy"), "Kennung ohne -copy");
    await discard();
    await backToOverview();
  });

  let exported = null;
  await check("Als Datei speichern", async () => {
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: TIMEOUT }),
      page.locator(".behavior-card").first().locator("button[title='Als Datei speichern']").click(),
    ]);
    exported = join(tmpdir(), download.suggestedFilename());
    await download.saveAs(exported);
    const yaml = readFileSync(exported, "utf8");
    ok(yaml.startsWith("schema: duckstudio.behavior/v0"), "Datei beginnt nicht mit dem Schema");
    ok(/\n {2}- skill:|\n {2}- perceive:|\n {2}- wait:/.test(yaml), "keine Schritte in der Datei");
  });

  await check("Aus Datei laden: belegte Kennung wird umbenannt", async () => {
    await page.locator(".starters input[type=file]").setInputFiles(exported);
    await until("Hinweis zur Umbenennung", () => page.locator(".route .card.notice").isVisible());
    await discard();
    await backToOverview();
  });

  await check("Aus Datei laden: unbrauchbare Datei erklärt sich", async () => {
    await page.locator(".starters input[type=file]").setInputFiles({ name: "junk.yaml", mimeType: "text/yaml", buffer: Buffer.from("hallo: welt\n") });
    const notice = await until("Fehlermeldung", async () => await page.locator(".starters .notice.error").innerText());
    ok(notice.includes("kein Ablauf"), `unerwartete Meldung: ${notice}`);
  });

  await check("Neuer Ablauf: namenlos, speichern erst mit Name und Schritt", async () => {
    await page.locator(".behavior-card.new").click();
    await until("leerer Entwurf", async () => (await editorOpen()) && (await nameField().inputValue()) === "");
    ok(!(await page.getByRole("button", { name: /^Speichern$/ }).isEnabled()), "Speichern war klickbar");
    await nameField().fill("Rauchtest");
    await addStep("Quaken");
    await until("Speichern wird klickbar", () => page.getByRole("button", { name: /^Speichern$/ }).isEnabled());
    // „Nur wenn …“ (ADR-0012): the practice duck measures 1 m, so this step must be skipped
    const check = page.locator(".station.editing .note.check").first();
    await check.locator("input[type=checkbox]").check();
    await check.locator("select").selectOption("obstacle");
    await check.locator("input[type=number]").fill("10");
    ok(/only_if:\s+signal: tof_distance < 0\.1/.test((await page.locator("details.file pre").textContent()) ?? ""), "only_if fehlt in der Datei");
  });

  await check("Speichern & Starten: die Runtime führt aus", async () => {
    await page.getByRole("button", { name: /^Speichern & Starten$/ }).click();
    await until(`${SMOKE_ID} gespeichert`, async () => (await packs()).includes(SMOKE_ID));
    await until("Lauf beendet", async () => (await page.locator(".route .toolbar .hint").first().innerText()) === "fertig");
    ok((await page.locator(".live .log li").count()) > 1, "kein Protokoll");
    await until("übersprungen, mit Grund", async () =>
      (await page.locator(".live .log").innerText()).includes("Schritt 1 übersprungen: nur wenn ein Hindernis näher als 10 cm ist."));
    ok(/übersprungen/.test(await page.locator(".station.skipped").first().innerText()), "Karte zeigt nicht „übersprungen“");
  });

  await check("Letzte Läufe zeigt den gerade beendeten Lauf", async () => {
    const first = await until("Eintrag in der Lauf-Liste", async () => await page.locator(".runs li").first().innerText());
    ok(first.includes("Rauchtest"), `unerwarteter Eintrag: ${first.replace(/\n/g, " · ")}`);
    ok(/FERTIG|GESTOPPT|ABGEBROCHEN/i.test(first), "kein Ergebnis im Eintrag");
  });

  await check("Notstopp", async () => {
    await page.locator(".live .estop").click();
    await until("Notstopp im Protokoll", async () => /Notstopp|Stopp/i.test(await page.locator(".live .log").innerText()));
  });

  await check("Zuhören: ein gesprochener Satz startet „Folge mir“, „Stopp“ wird gehört", async () => {
    await backToOverview();
    await page.getByRole("button", { name: "Folge mir", exact: true }).click();
    await page.getByRole("button", { name: "Zuhören" }).click();
    await until("hört auf dem Gerät zu", async () => /auf diesem Gerät/.test(await page.locator(".speechline").innerText()));
    await page.evaluate(() => window.__say("Okay, folge mir bitte"));
    await until("„Folge mir“ startet", async () => /startet/.test(await page.locator(".heard").innerText()));
    await page.evaluate(() => window.__say("Stopp"));
    await until("Stopp gehört", async () => /Gehört: „Stopp“/.test(await page.locator(".heard").innerText()));
    await page.getByRole("button", { name: "Nicht mehr zuhören" }).click();
    ok(!(await page.evaluate(() => window.__recs.some((r) => r.running))), "Mikrofon noch an");
    await fetch(`${API}/api/executor/abort`, { method: "POST" });
  });

  await check("Zuhören über das Netz nur nach Einwilligung", async () => {
    await page.evaluate(() => {
      window.__speechMode = "cloud";
      localStorage.removeItem("duckstudio.speech.cloud");
    });
    await backToOverview(); // the row asks the browser again when it mounts
    await page.getByRole("button", { name: "Folge mir", exact: true }).click();
    const before = await page.evaluate(() => window.__recs.length);
    await until("Mikrofon bereit", () => page.getByRole("button", { name: "Zuhören" }).isEnabled());
    await page.getByRole("button", { name: "Zuhören" }).click();
    const ask = await until("Frage nach Einwilligung", async () => await page.locator(".speechline.ask").innerText());
    ok(/Google/.test(ask), `Anbieter nicht genannt: ${ask}`);
    is(await page.evaluate(() => window.__recs.length), before, "vor der Einwilligung gestartet");
    await page.locator(".speechline.ask .btn", { hasText: "Abbrechen" }).click();
    await page.evaluate(() => {
      window.__speechMode = "local";
    });
  });

  await check("KI-Anbieter: drei Karten mit Links, falsches Format wird nicht gespeichert", async () => {
    await backToOverview();
    await page.getByRole("button", { name: "KI-Anbieter", exact: true }).click();
    await until("drei Anbieter und die lokale Erkennung", async () => (await page.locator(".aivendor").count()) === 4);
    // Never downloaded here (CI has no model, a laptop may): either the button or "geladen".
    const local = await page.locator(".aivendor.local").innerText();
    ok(/Personenerkennung laden|ist geladen/.test(local), `lokale Karte: ${local.slice(0, 80)}`);
    const google = page.locator(".aivendor:not(.local)").first();
    ok(/Google/.test(await google.locator("h3").innerText()), "Google nicht zuerst");
    is(await google.locator("a", { hasText: "Schlüssel holen" }).getAttribute("href"), "https://aistudio.google.com/apikey", "Link");
    // A key with a space is refused by the runtime before any vendor is asked: no network in CI.
    await google.locator("input[type=password]").fill("kein schlüssel");
    await google.getByRole("button", { name: "Prüfen und speichern" }).click();
    await until("Hinweis zum Format", async () => /nicht wie ein Schlüssel/.test(await google.locator(".error").innerText()));
    const ai = await (await fetch(`${API}/api/ai`)).json();
    ok(ai.vendors.every((v) => v.key === null), "ein Schlüssel wurde gespeichert");
  });

  await check("Mit KI entwerfen: ohne Schlüssel führt der Weg zu den KI-Anbietern", async () => {
    await backToOverview();
    const card = page.locator(".aidraft");
    await until("Karte „Mit KI entwerfen“", () => card.isVisible());
    const r = await fetch(`${API}/api/planner/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Quak einmal." }),
    });
    is(r.status, 409, "ohne Schlüssel");
    await card.getByRole("button", { name: "KI-Anbieter einrichten" }).click();
    await until("KI-Anbieter offen", async () => (await page.locator(".tabs button.active").innerText()) === "KI-Anbieter");
  });

  await check("Sprache und Thema schalten", async () => {
    const logHeading = () => page.locator(".live .logwrap h2").innerText();
    await page.locator(".switch.lang button", { hasText: "EN" }).click();
    await until("englische Überschrift", async () => (await logHeading()) === "What is happening");
    await page.locator(".switch.theme button").nth(2).click();
    await until("dunkles Thema", async () => (await page.locator("html").getAttribute("data-theme")) === "dark");
    await page.locator(".switch.theme button").nth(1).click();
    await page.locator(".switch.lang button", { hasText: "DE" }).click();
    await until("wieder deutsch und hell", async () =>
      (await logHeading()) === "Was passiert" &&
      (await page.locator("html").getAttribute("data-theme")) === "light");
  });

  await check("Löschen räumt auf", async () => {
    await backToOverview();
    page.once("dialog", (d) => void d.accept());
    await page.locator(".behavior-card", { hasText: "Rauchtest" }).locator(".btn", { hasText: "Öffnen" }).click();
    await until("Bearbeiten-Knopf", () => page.getByRole("button", { name: /Bearbeiten/ }).isVisible());
    await page.getByRole("button", { name: /Bearbeiten/ }).click();
    await until("Editor", editorOpen);
    await page.getByRole("button", { name: /^Löschen$/ }).click();
    await until(`${SMOKE_ID} ist weg`, async () => !(await packs()).includes(SMOKE_ID));
  });

  await check("Ente wechseln: echte Ente ohne Tunnel sagt, was fehlt, zurück zur Übungsente", async () => {
    const status = page.locator(".backendmenu > button");
    const pop = page.locator(".backendpop");
    await status.click();
    await pop.getByRole("radio", { name: /^Echte Ente/ }).click();
    await pop.getByPlaceholder("duck.local").fill("rauchente.local");
    is(await pop.locator(".command code").innerText(), "scripts/duck-tunnel.sh rauchente.local", "Tunnel-Befehl");
    await pop.getByRole("button", { name: "Mit der Ente verbinden" }).click();
    await until("Ente nicht verbunden", async () => (await status.innerText()) === "Ente nicht verbunden");
    await until("Satz zum Tunnel", () => pop.locator(".problem", { hasText: "Kein Tunnel zur Ente" }).isVisible());
    ok(await page.locator(".behavior-card .btn", { hasText: "Start" }).first().isDisabled(), "Start bleibt gesperrt");
    await pop.getByRole("radio", { name: /^Übungsente/ }).click();
    await until("Übungsente verbunden", async () => (await status.innerText()) === "Übungsente verbunden");
    await page.keyboard.press("Escape");
    await until("Menü zu", async () => !(await pop.isVisible()));
  });

  await check("keine Fehler in der Konsole", () => is(errors, [], "pageerror"));
} finally {
  await fetch(`${API}/api/behaviors/${SMOKE_ID}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
}

console.log(failures === 0 ? "\nalles grün" : `\n${failures} Prüfung(en) fehlgeschlagen`);
process.exit(failures === 0 ? 0 : 1);
