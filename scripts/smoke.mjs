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
const editorOpen = () => page.locator(".editor").isVisible();
const editorGone = async () => !(await page.locator(".editor").isVisible());
const steps = () => page.locator(".steps > div > .step").count();
const nameField = () => page.locator(".editor .card input").first();
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
async function discard() {
  await page.getByRole("button", { name: /^(Verwerfen|Discard)$/ }).click();
  await until("Editor geschlossen", editorGone);
}

try {
  await fetch(`${API}/api/behaviors/${SMOKE_ID}`, { method: "DELETE" }).catch(() => {});
  await page.goto(STUDIO, { waitUntil: "domcontentloaded" });
  await until("geladene Abläufe", async () => (await behaviorCards()) >= 2, 30_000);
  console.log("Studio-Rauchtest\n");

  await check("Übersicht zeigt Abläufe und Bausteine", async () => {
    ok((await behaviorCards()) >= 2, "keine Ablauf-Karten");
    ok((await page.locator(".panel").first().locator(".card").count()) >= 8, "keine Bausteine");
    is(await page.locator(".status").innerText(), "Attrappe (Mock) · verbunden", "Status");
  });

  await check("Editor: Schritt hinzufügen, rückgängig, wiederholen", async () => {
    await openFirstForEditing();
    const before = await steps();
    await page.locator(".add-menu .chip", { hasText: "Quaken" }).first().click();
    await until("Schritt kam dazu", async () => (await steps()) === before + 1);
    await page.locator(".runbar .btn.icon-only").first().click();
    await until("rückgängig", async () => (await steps()) === before);
    await page.locator(".runbar .btn.icon-only").nth(1).click();
    await until("wiederholt", async () => (await steps()) === before + 1);
    await discard();
    await backToOverview(); // discarding an edit keeps that behavior open; the list is one click away
  });

  await check("Kopie anlegen", async () => {
    await page.locator(".behavior-card").first().locator("button[title='Kopie anlegen']").click();
    await until("Editor mit Kopie", async () => (await editorOpen()) && (await nameField().inputValue()).includes("(Kopie)"));
    ok((await page.locator(".editor .sub").first().innerText()).includes("-copy"), "Kennung ohne -copy");
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
    await until("Hinweis zur Umbenennung", () => page.locator(".editor .card.notice").isVisible());
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
    await page.locator(".add-menu .chip", { hasText: "Quaken" }).first().click();
    await until("Speichern wird klickbar", () => page.getByRole("button", { name: /^Speichern$/ }).isEnabled());
  });

  await check("Speichern & Starten: die Runtime führt aus", async () => {
    await page.getByRole("button", { name: /^Speichern & Starten$/ }).click();
    await until(`${SMOKE_ID} gespeichert`, async () => (await packs()).includes(SMOKE_ID));
    await until("Lauf beendet", async () => (await page.locator(".panel.live .doing").innerText()) === "fertig");
    ok((await page.locator(".panel.live .log li").count()) > 1, "kein Protokoll");
  });

  await check("Notstopp", async () => {
    await page.locator(".stop").click();
    await until("Notstopp im Protokoll", async () => /Notstopp|Stopp/i.test(await page.locator(".panel.live .log").innerText()));
  });

  await check("Sprache und Thema schalten", async () => {
    await page.locator(".switch.lang button", { hasText: "EN" }).click();
    await until("englische Panel-Titel", async () => (await page.locator(".panel").nth(1).locator("h2").innerText()) === "BEHAVIOR");
    await page.locator(".switch.theme button").nth(2).click();
    await until("dunkles Thema", async () => (await page.locator("html").getAttribute("data-theme")) === "dark");
    await page.locator(".switch.theme button").nth(1).click();
    await page.locator(".switch.lang button", { hasText: "DE" }).click();
    await until("wieder deutsch und hell", async () =>
      (await page.locator(".panel").nth(1).locator("h2").innerText()) === "ABLAUF" &&
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

  await check("keine Fehler in der Konsole", () => is(errors, [], "pageerror"));
} finally {
  await fetch(`${API}/api/behaviors/${SMOKE_ID}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
}

console.log(failures === 0 ? "\nalles grün" : `\n${failures} Prüfung(en) fehlgeschlagen`);
process.exit(failures === 0 ? 0 : 1);
