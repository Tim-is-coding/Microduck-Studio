/**
 * The screenshots in the README (`CLAUDE.md` §5), taken from a real Studio against a real
 * runtime so they can never drift into wishful thinking. Nothing here saves a behavior: it
 * opens, runs and aborts, so the workspace is the same afterwards.
 *
 *   cd runtime && DUCKSTUDIO_BACKEND=mock uv run python -m duckstudio
 *   cd studio  && pnpm dev
 *   node scripts/screenshots.mjs            # writes docs/images/*.png
 *
 * Needs playwright (`pnpm dlx playwright@latest install chromium`, or point CHROMIUM at a
 * browser you already have).
 */
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const API = process.env.API ?? "http://localhost:8000";
const STUDIO = process.env.STUDIO ?? "http://localhost:5173";
const OUT = process.env.OUT ?? new URL("../docs/images/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const page = await browser.newPage({ viewport: { width: 1480, height: 940 }, locale: "de-DE" });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));

const shot = async (name) => {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log(`  ${name}.png`);
};
const theme = async (which) => {
  await page.locator(".switch.theme button").nth(which === "dark" ? 2 : 1).click();
  await page.waitForTimeout(300);
};
const lang = async (which) => {
  await page.locator(".switch.lang button", { hasText: which.toUpperCase() }).click();
  await page.waitForTimeout(300);
};

await page.goto(STUDIO, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);
await theme("light");
await shot("overview");

await page.locator(".behavior-card .btn", { hasText: "Öffnen" }).first().click();
await page.waitForTimeout(400);
await page.getByRole("button", { name: /Bearbeiten/ }).click();
await page.waitForTimeout(600);
await shot("editor");
await page.getByRole("button", { name: /^Verwerfen$/ }).click();
await page.waitForTimeout(400);

await theme("dark");
await page.getByRole("button", { name: /^Übersicht$/ }).click();
await page.waitForTimeout(400);
await page.locator(".behavior-card .btn.primary").first().click();
await page.waitForTimeout(600);
await page.getByRole("button", { name: /^Folge mir$/ }).click(); // the route, with the running station lit
await page.waitForTimeout(1900);
await shot("running");
await fetch(`${API}/api/executor/abort`, { method: "POST" });
await page.waitForTimeout(800);

await lang("en");
await page.getByRole("button", { name: /^Overview$/ }).click();
await page.waitForTimeout(500);
await shot("english-dark");

await theme("light");
await lang("de");
await browser.close();
console.log(`fertig → ${OUT}`);
