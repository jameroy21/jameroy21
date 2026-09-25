/**
 * Capture real screenshots of the running app.
 *
 * These go into frontend/public/screenshots/ and are referenced by the web app
 * manifest, where Android shows them in the install dialog — so people see a
 * branded app, with a real calculation on screen, instead of a generic bookmark.
 *
 * Uses @sparticuz/chromium (a headless Chromium that ships as an npm package,
 * so no browser download is needed).
 *
 * Prerequisites — on a normal machine this is two commands:
 *   cd tools && npm install                 # puppeteer-core + chromium
 *   sudo apt-get install -y libnss3 libatk-bridge2.0-0 libgbm1   # Chromium's libs (Linux)
 *
 * Then, with the dev server running on 5173:
 *   node tools/make_screenshots.mjs
 *
 * Then add the captured files back to the manifest:
 *   "screenshots": [
 *     { "src": "/screenshots/phone.png", "sizes": "1080x1920",
 *       "type": "image/png", "form_factor": "narrow",
 *       "label": "$89 with 20% off then 70% off: you pay $21.36" },
 *     { "src": "/screenshots/desktop.png", "sizes": "1920x1080",
 *       "type": "image/png", "form_factor": "wide",
 *       "label": "The same one-screen calculator on a desktop" }
 *   ]
 *
 * They are deliberately NOT shipped until they are real captures of the running
 * app: an install dialog showing a wrong or overlapping image is worse than one
 * showing none, and the manifest works fine without them. Chrome also verifies
 * that declared sizes match the actual PNG, so generated stand-ins can be
 * rejected outright.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "frontend", "public", "screenshots");
const URL = process.env.SCREENSHOT_URL || "http://127.0.0.1:5173/";

/** Do the calculation on screen, so the images show the app doing its job. */
async function showResult(page) {
  const type = async (selector, value) => {
    await page.click(selector, { clickCount: 3 });
    await page.type(selector, value, { delay: 20 });
  };
  const inputs = await page.$$("input");
  await type(`#${await inputs[0].evaluate((el) => el.id)}`, "89");
  await type(`#${await inputs[1].evaluate((el) => el.id)}`, "20");
  await type(`#${await inputs[2].evaluate((el) => el.id)}`, "70");
  await page.click('button[type="submit"]');
  await page.waitForFunction(
    () => document.body.innerText.includes("$21.36"),
    { timeout: 15000 }
  );
  await new Promise((resolve) => setTimeout(resolve, 700)); // let the smooth scroll settle
}

const browser = await puppeteer.launch({
  args: [...chromium.args, "--font-render-hinting=none", "--force-color-profile=srgb"],
  executablePath: await chromium.executablePath(),
  headless: true,
});

try {
  await mkdir(OUT, { recursive: true });

  for (const [name, width, height, mobile] of [
    ["phone", 1080, 1920, true],
    ["desktop", 1920, 1080, false],
  ]) {
    const page = await browser.newPage();
    await page.setViewport({ width, height, deviceScaleFactor: 1, isMobile: mobile });
    await page.goto(URL, { waitUntil: "networkidle0" });
    await showResult(page);

    const target = path.join(OUT, `${name}.png`);
    await page.screenshot({ path: target, type: "png" });
    console.log(`captured ${path.relative(ROOT, target)} (${width}x${height})`);
    await page.close();
  }
} finally {
  await browser.close();
}
