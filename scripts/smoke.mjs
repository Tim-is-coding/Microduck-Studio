/**
 * The paths unit tests cannot see: a real browser, a real runtime, the whole Studio.
 * Vitest checks the pure pieces (`studio/tests/`), pytest the runtime — this walks the
 * clicks in between and says which of them still work.
 *
 *   cd runtime && DUCKSTUDIO_BACKEND=mock DUCKSTUDIO_ROOT=/tmp/ds-smoke uv run python -m duckstudio
 *   cd studio  && pnpm dev
 *   node scripts/smoke.mjs
 *
 * Needs playwright (`pnpm dlx playwright@latest install chromium`, or point CHROMIUM at a
 * browser you already have). It creates one behavior and deletes it again; point
 * DUCKSTUDIO_ROOT at a scratch directory anyway, so a failed run cannot leave anything in
 * the repo's `behaviors/`.
 */
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

const API = process.env.API ?? "http://localhost:8000";
const STUDIO = process.env.STUDIO ?? "http://localhost:5173";
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

const overview = () => page.getByRole("button", { name: /^(Übersicht|Overview)$/ }).click();
const discard = () => page.getByRole("button", { name: /^(Verwerfen|Discard)$/ }).click();
const steps = () => page.locator(".steps > div > .step").count();
const settle = (ms = 500) => page.waitForTimeout(ms);

try {
  await fetch(`${API}/api/behaviors/${SMOKE_ID}`, { method: "DELETE" }).catch(() => {});
  await page.goto(STUDIO, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".behavior-card", { timeout: 15_000 });
  console.log("Studio-Rauchtest\n");

  await check("Übersicht zeigt Abläufe und Bausteine", async () => {
    ok((await page.locator(".behavior-card").count()) >= 2, "keine Ablauf-Karten");
    ok((await page.locator(".panel").first().locator(".card").count()) >= 8, "keine Bausteine");
    is(await page.locator(".status").innerText(), "Attrappe (Mock) · verbunden", "Status");
  });

  await check("Editor: Schritt hinzufügen, rückgängig, wiederholen", async () => {
    await page.locator(".behavior-card .btn", { hasText: "Öffnen" }).first().click();
    await settle(400);
    await page.getByRole("button", { name: /Bearbeiten/ }).click();
    await settle();
    const before = await steps();
    await page.locator(".add-menu .chip", { hasText: "Quaken" }).first().click();
    await settle(400);
    is(await steps(), before + 1, "nach Hinzufügen");
    await page.locator(".runbar .btn.icon-only").first().click();
    await settle(400);
    is(await steps(), before, "nach Rückgängig");
    await page.locator(".runbar .btn.icon-only").nth(1).click();
    await settle(400);
    is(await steps(), before + 1, "nach Wiederholen");
    await discard();
    await settle(400);
    await overview(); // discarding an edit keeps that behavior open; the list is one click away
    await settle(400);
  });

  await check("Kopie anlegen", async () => {
    await page.locator(".behavior-card").first().locator("button[title='Kopie anlegen']").click();
    await settle(600);
    ok((await page.locator(".card input").first().inputValue()).includes("(Kopie)"), "Name ohne (Kopie)");
    ok((await page.locator(".editor .sub").first().innerText()).includes("-copy"), "Kennung ohne -copy");
    await discard();
    await settle(400);
    await overview();
    await settle(400);
  });

  let exported = null;
  await check("Als Datei speichern", async () => {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
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
    await settle(800);
    ok((await page.locator(".editor .card.notice").innerText()).length > 0, "kein Hinweis zur Umbenennung");
    await discard();
    await settle(400);
    await overview();
    await settle(400);
  });

  await check("Aus Datei laden: unbrauchbare Datei erklärt sich", async () => {
    await page.locator(".starters input[type=file]").setInputFiles({ name: "junk.yaml", mimeType: "text/yaml", buffer: Buffer.from("hallo: welt\n") });
    await settle(600);
    ok((await page.locator(".starters .notice.error").innerText()).includes("kein Ablauf"), "keine Fehlermeldung");
  });

  await check("Neuer Ablauf: namenlos, speichern erst mit Name und Schritt", async () => {
    await page.locator(".behavior-card.new").click();
    await settle(600);
    is(await page.locator(".card input").first().inputValue(), "", "Name eines neuen Entwurfs");
    ok(!(await page.getByRole("button", { name: /^Speichern$/ }).isEnabled()), "Speichern war klickbar");
    await page.locator(".card input").first().fill("Rauchtest");
    await page.locator(".add-menu .chip", { hasText: "Quaken" }).first().click();
    await settle(600);
    ok(await page.getByRole("button", { name: /^Speichern$/ }).isEnabled(), "Speichern blieb gesperrt");
  });

  await check("Speichern & Starten: die Runtime führt aus", async () => {
    await page.getByRole("button", { name: /^Speichern & Starten$/ }).click();
    await settle(2000);
    const packs = await (await fetch(`${API}/api/behaviors`)).json();
    ok(packs.some((b) => b.id === SMOKE_ID), `${SMOKE_ID} nicht gespeichert`);
    ok((await page.locator(".panel.live .log li").count()) > 1, "kein Protokoll");
    is(await page.locator(".panel.live .doing").innerText(), "fertig", "Live-Zeile");
  });

  await check("Notstopp", async () => {
    await page.locator(".stop").click();
    await settle(800);
    const log = await page.locator(".panel.live .log").innerText();
    ok(/Notstopp|Stopp/i.test(log), "kein Notstopp im Protokoll");
  });

  await check("Sprache und Thema schalten", async () => {
    await page.locator(".switch.lang button", { hasText: "EN" }).click();
    await settle(400);
    is(await page.locator(".panel").nth(1).locator("h2").innerText(), "BEHAVIOR", "Panel-Titel auf Englisch");
    await page.locator(".switch.theme button").nth(2).click();
    await settle(300);
    is(await page.locator("html").getAttribute("data-theme"), "dark", "data-theme");
    await page.locator(".switch.theme button").nth(1).click();
    await page.locator(".switch.lang button", { hasText: "DE" }).click();
    await settle(400);
  });

  await check("Löschen räumt auf", async () => {
    await overview();
    await settle(400);
    page.once("dialog", (d) => void d.accept());
    await page.locator(".behavior-card", { hasText: "Rauchtest" }).locator(".btn", { hasText: "Öffnen" }).click();
    await settle(400);
    await page.getByRole("button", { name: /Bearbeiten/ }).click();
    await settle(500);
    await page.getByRole("button", { name: /^Löschen$/ }).click();
    await settle(1000);
    const packs = await (await fetch(`${API}/api/behaviors`)).json();
    ok(!packs.some((b) => b.id === SMOKE_ID), `${SMOKE_ID} liegt noch da`);
  });

  await check("keine Fehler in der Konsole", () => is(errors, [], "pageerror"));
} finally {
  await fetch(`${API}/api/behaviors/${SMOKE_ID}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
}

console.log(failures === 0 ? "\nalles grün" : `\n${failures} Prüfung(en) fehlgeschlagen`);
process.exit(failures === 0 ? 0 : 1);
