/**
 * The M3 acceptance measurement (CLAUDE.md §8, docs/m3-acceptance.md): a first-time user,
 * an empty Studio, one behavior saved and started — twice, once from the empty card and
 * once from a starter template.
 *
 * The robot clicks, but it waits like a person: THINK where somebody meets a new screen and
 * has to decide, READ for a glance at something familiar, and the name is typed letter by
 * letter. Those pauses are the honest part of the number.
 *
 *   cd runtime && DUCKSTUDIO_BACKEND=mock DUCKSTUDIO_ROOT=/tmp/ds-firstrun uv run python -m duckstudio
 *   cd studio  && pnpm dev
 *   node scripts/firstrun.mjs
 *
 * Needs playwright (`pnpm dlx playwright@latest install chromium`, or point CHROMIUM at a
 * browser you already have). It deletes every behavior in the runtime's workspace before and
 * after each path, so point DUCKSTUDIO_ROOT somewhere disposable.
 */
import { chromium } from "playwright";

const THINK = Number(process.env.THINK ?? 2500); // meeting a new screen
const READ = Number(process.env.READ ?? 1200);   // a glance at something familiar
const API = process.env.API ?? "http://localhost:8000";
const STUDIO = process.env.STUDIO ?? "http://localhost:5173";
const SHOTS = process.env.SHOTS ?? null;         // directory for screenshots, or none

async function emptyTheStudio() {
  const packs = await (await fetch(`${API}/api/behaviors`)).json();
  for (const p of packs) await fetch(`${API}/api/behaviors/${p.id}`, { method: "DELETE" });
}

async function run(kind, browser) {
  await emptyTheStudio();
  const marks = [];
  const t0 = Date.now();
  const at = () => ((Date.now() - t0) / 1000).toFixed(1);
  const mark = (what) => { marks.push(what); console.log(`  ${at().padStart(5)}s  ${what}`); };
  const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/fr-${kind}-${name}.png` }); };

  const page = await browser.newPage({ viewport: { width: 1500, height: 940 }, deviceScaleFactor: 2, locale: "de-DE" });
  page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
  await page.goto(STUDIO, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  mark("Studio offen");
  await shot(page, "1-empty");

  await page.waitForTimeout(THINK);                       // "was mache ich hier?"
  if (kind === "template") {
    await page.locator(".starters .chip", { hasText: "Begrüßung" }).first().click();
    await page.waitForTimeout(600);
    mark("Beispiel Begrüßung geöffnet");
  } else {
    await page.locator(".behavior-card.new").click();
    await page.waitForTimeout(600);
    mark("Neuer Ablauf geklickt");
    await shot(page, "2-editor");

    await page.waitForTimeout(THINK);                     // Name?
    await page.locator(".card input").first().pressSequentially("Begrüßung", { delay: 70 });
    await page.waitForTimeout(READ);
    mark("Name getippt");

    await page.waitForTimeout(THINK);                     // welcher Baustein?
    await page.locator(".add-menu .chip", { hasText: "Quaken" }).first().click();
    await page.waitForTimeout(READ);
    mark("Baustein Quaken hinzugefügt");

    await page.waitForTimeout(READ);
    await page.locator(".add-menu .chip", { hasText: "Hinsetzen" }).first().click();
    await page.waitForTimeout(READ);
    mark("Baustein Hinsetzen hinzugefügt");
  }
  await shot(page, "3-ready");

  await page.waitForTimeout(THINK);                       // und jetzt?
  const save = page.getByRole("button", { name: /^Speichern & Starten$/ });
  const ready = await save.isEnabled();
  console.log(`    „Speichern & Starten" klickbar: ${ready}`);
  await (ready ? save : page.getByRole("button", { name: /^Speichern$/ })).click();
  await page.waitForTimeout(2000);
  mark("gespeichert und gestartet");
  await shot(page, "4-saved");

  console.log("    Live: " + (await page.locator(".panel.live .doing").innerText()).replace(/\n/g, " / "));
  const packs = await (await fetch(`${API}/api/behaviors`)).json();
  console.log("    Runtime kennt: " + (packs.map((b) => `${b.id} (${b.steps.length} Schritte, ${b.problems.length} Probleme)`).join(", ") || "(nichts)"));
  const total = (Date.now() - t0) / 1000;
  console.log(`  GESAMT ${kind}: ${total.toFixed(1)} s, ${marks.length} Interaktionen\n`);
  await page.close();
  return total;
}

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
console.log(`Leeres Studio → erster Ablauf (THINK=${THINK}ms, READ=${READ}ms)\n`);
console.log("A) von der leeren Karte:");
const blank = await run("blank", browser);
console.log("B) vom Beispiel:");
const template = await run("template", browser);
console.log(`Ergebnis: leere Karte ${blank.toFixed(1)} s · Beispiel ${template.toFixed(1)} s · Ziel < 120 s`);
await emptyTheStudio();
await browser.close();
