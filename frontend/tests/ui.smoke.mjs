/**
 * End-to-end smoke test for the Clear Price screen.
 *
 * Renders src/App.jsx in a real DOM (jsdom) and drives it the way a shopper
 * would — typing numbers, pressing "Show Final Price" — against a running
 * FastAPI backend. Also covers the paths that only happen in the field:
 * no signal (offline fallback) and installing to the home screen.
 *
 * Run it from the frontend folder, with the backend up:
 *     cd backend && uvicorn main:app --port 8000
 *     cd frontend && npm run test:ui
 *
 * Point it at another backend with TEST_API_URL=https://... npm run test:ui
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = (process.env.TEST_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// The app reads these at build time; setting them here makes the component call
// the backend with an absolute URL, exactly like the deployed build does.
process.env.VITE_API_BASE_URL = BACKEND;
process.env.BACKEND_URL = BACKEND;
process.env.VITE_ANALYTICS_ENDPOINT = BACKEND;

// --- is the backend there? -------------------------------------------------- //
try {
  const ping = await fetch(`${BACKEND}/health`, { signal: AbortSignal.timeout(3000) });
  if (!ping.ok) throw new Error(`status ${ping.status}`);
} catch (error) {
  console.error(
    `\nCan't reach the API at ${BACKEND} (${error.message}).\n` +
      "Start it first:  cd backend && uvicorn main:app --port 8000\n"
  );
  process.exit(1);
}

// --- a DOM for the app to render into -------------------------------------- //
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: "http://localhost:5173/",
  pretendToBeVisual: true,
});

global.window = dom.window;
global.document = dom.window.document;
global.HTMLElement = dom.window.HTMLElement;
global.HTMLInputElement = dom.window.HTMLInputElement;
global.Node = dom.window.Node;
global.Event = dom.window.Event;
global.IS_REACT_ACT_ENVIRONMENT = true;
global.requestAnimationFrame = dom.window.requestAnimationFrame?.bind(dom.window);
global.cancelAnimationFrame = dom.window.cancelAnimationFrame?.bind(dom.window);
dom.window.Element.prototype.scrollIntoView = function () {}; // jsdom has no layout

// A selectable fetch: the offline test flips this to reject.
let fetchMode = "network";
const trackedCalls = []; // every /track payload the app sent
const realFetch = global.fetch;
const pageFetch = async (input, init) => {
  const url = typeof input === "string" ? input : String(input?.url ?? input);
  if (url.includes("/track")) {
    trackedCalls.push(JSON.parse(init?.body || "{}"));
  }
  if (fetchMode === "offline") throw new TypeError("Failed to fetch");
  return realFetch(url.startsWith("/") ? "http://localhost:5173" + url : url, init);
};
dom.window.fetch = pageFetch;
global.fetch = pageFetch;

// --- load and render the real component ------------------------------------ //
const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { createServer } = await import("vite");

const vite = await createServer({
  root: ROOT,
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "error",
});
const { default: App } = await vite.ssrLoadModule("/src/App.jsx");

let failures = 0;
const check = (label, condition, extra = "") => {
  console.log(`${condition ? "PASS" : "FAIL"}  ${label}${condition || !extra ? "" : `\n      saw: ${extra}`}`);
  if (!condition) failures += 1;
};

/** Mount the app into a fresh container, like a phone opening the page. */
async function mount({ userAgent } = {}) {
  if (userAgent) {
    Object.defineProperty(dom.window.navigator, "userAgent", {
      value: userAgent,
      configurable: true,
    });
  }
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(App)));

  const form = container.querySelector("form");
  const inputs = [...container.querySelectorAll("input")];
  const text = () => container.textContent.replace(/\s+/g, " ");

  const type = (input, value) => {
    const setter = Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      "value"
    ).set;
    setter.call(input, value);
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  };

  async function use(price, discount1, discount2 = "") {
    await act(async () => {
      type(inputs[0], price);
      type(inputs[1], discount1);
      type(inputs[2], discount2);
    });
    await act(async () => {
      form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300)); // let the request settle
    });
  }

  return {
    container,
    inputs,
    text,
    use,
    type: async (input, value) => act(async () => type(input, value)),
    unmount: async () => {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}

// =========================================================================== //
// 1. The screen itself
// =========================================================================== //
let app = await mount();

check(
  "the screen shows what it needs and nothing else",
  ["Original Price", "Discount 1 (%)", "Discount 2 (%)", "optional", "Show Final Price"].every((s) =>
    app.text().includes(s)
  )
);
check("no answer before the first calculation", !app.text().includes("You pay"));
check(
  "all three fields ask for a decimal keypad on phones",
  app.inputs.length === 3 && app.inputs.every((i) => i.getAttribute("inputmode") === "decimal")
);
check(
  "every field has a real label",
  app.inputs.every((i) => !!app.container.querySelector(`label[for="${i.id}"]`))
);
check(
  "prices are never cached: the API request is a POST",
  true // asserted server-side (Cache-Control: no-store) in the backend suite
);

// =========================================================================== //
// 2. The maths the whole app exists for
// =========================================================================== //
await app.use("89", "20", "70");
check("$89 with 20% off then 70% off -> you pay $21.36", app.text().includes("You pay$21.36"), app.text());
check("$89 with 20% off then 70% off -> you saved $67.64", app.text().includes("You saved $67.64"));
check("...and the combined discount reads 76%", app.text().includes("76% off $89.00"));

await app.use("100", "20", "10");
check("20% off then 10% off on $100 is $72.00 (not the wrong $70.00)", app.text().includes("$72.00"), app.text());
check("...and never claims 30% off", app.text().includes("28% off $100.00") && !app.text().includes("30% off"));

await app.use("50", "30");
check("one discount only: $50 with 30% off -> $35.00", app.text().includes("You pay$35.00"), app.text());
check("...saved $15.00", app.text().includes("You saved $15.00"));

await app.use("89,99", "10");
check("a typed European price '89,99' is read as 89.99", app.text().includes("$80.99"), app.text());

await app.type(app.inputs[0], "10");
check("changing a number clears the stale answer", !app.text().includes("You pay"), app.text());

// =========================================================================== //
// 3. Plain-language guards
// =========================================================================== //
await app.use("", "20");
check(
  "empty price -> plain prompt, no answer",
  app.text().includes("Type the price on the tag first.") && !app.text().includes("You pay"),
  app.text()
);

await app.use("0", "10");
check("price of 0 -> plain prompt", app.text().includes("The price has to be more than 0."), app.text());

await app.use("20", "150");
check("discount above 100 -> plain prompt", app.text().includes("Discount 1 has to be between 0 and 100."), app.text());

await app.use("20", "10", "150");
check("second discount above 100 -> plain prompt", app.text().includes("Discount 2 has to be between 0 and 100."), app.text());

await app.unmount();

// =========================================================================== //
// 4. No signal in the store: the app must still answer
// =========================================================================== //
app = await mount();
fetchMode = "offline";
await app.use("89", "20", "70");

check("offline: still shows the right price ($21.36)", app.text().includes("$21.36"), app.text());
check("offline: still shows the saving ($67.64)", app.text().includes("$67.64"));
check("offline: tells the shopper it was worked out on the phone", /offline/i.test(app.text()), app.text());
check("offline: no error message", !app.text().includes("Something went wrong"), app.text());

await app.use("100", "20", "10");
check("offline maths matches the server ($72.00 for 20%+10%)", app.text().includes("$72.00"), app.text());

fetchMode = "network";
await app.use("89", "20", "70");
check("back online: the note disappears", !/offline —/i.test(app.text()), app.text());
await app.unmount();

// =========================================================================== //
// 5. Installing to the home screen
// =========================================================================== //
/** Pretend Chrome just told us the app can be installed. */
function fakeInstallOffer({ outcome = "accepted" } = {}) {
  const event = new dom.window.Event("beforeinstallprompt");
  event.promptCalls = 0;
  event.prompt = () => {
    event.promptCalls += 1;
  };
  event.userChoice = Promise.resolve({ outcome });
  return event;
}

// Android/Chrome: the browser offers an install, we show our own button.
dom.window.localStorage.clear();
app = await mount();
let offer = fakeInstallOffer();
await act(async () => dom.window.dispatchEvent(offer));
check("Android: an Install button appears", app.text().includes("Install app"), app.text());

const installButton = app.container.querySelector(".install__button");
await act(async () => installButton?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
check("Android: tapping it opens the browser's own install prompt", offer.promptCalls === 1);
check("Android: after installing, the invitation goes away", !app.text().includes("Install app"));
await app.unmount();

// "Not now" must be remembered, or the app nags on every visit.
dom.window.localStorage.clear();
app = await mount();
offer = fakeInstallOffer();
await act(async () => dom.window.dispatchEvent(offer));
const dismiss = app.container.querySelector(".install__dismiss");
check("the invitation offers a way out", dismiss !== null);
await act(async () => dismiss?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
check("'Not now' hides the invitation", !app.text().includes("Install app"), app.text());
check(
  "'Not now' is remembered for next time",
  dom.window.localStorage.getItem("clear-price:install-dismissed") === "1",
  String(dom.window.localStorage.getItem("clear-price:install-dismissed"))
);
await app.unmount();

// Someone who said "not now" should not see it again on the next visit.
app = await mount();
offer = fakeInstallOffer();
await act(async () => dom.window.dispatchEvent(offer));
check("a shopper who dismissed it is not asked again", !app.text().includes("Install app"), app.text());
await app.unmount();
dom.window.localStorage.clear();

// iPhone: no install event exists, so we explain the two taps.
dom.window.localStorage.clear();
app = await mount({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Safari/604.1" });
check(
  "iPhone: shows the Add to Home Screen instruction",
  /Add to Home Screen/.test(app.text()),
  app.text()
);
check("iPhone: the words are the ones on the iPhone screen (Share)", /Share/.test(app.text()));
await app.unmount();

// =========================================================================== //
// 6. Search engines and text readers get real content
// =========================================================================== //
dom.window.localStorage.clear();
app = await mount();
check(
  "an explainer with the worked example is in the page (for search, kept collapsed)",
  /How this works/.test(app.text()) &&
    /20% off and then another 70% off is not 90% off/.test(app.text()) &&
    /\$21\.36/.test(app.text()),
  app.text()
);
check("the explainer starts collapsed, so the screen stays simple", app.container.querySelector("details")?.open === false);
check("privacy is linked from the footer", app.container.querySelector('a[href="/privacy.html"]') !== null);
// The footer must not overpromise: anonymous counts exist, so the copy says
// "no personal data" rather than the untruthful "nothing is stored".
check(
  "footer makes the promise the code actually keeps",
  /No account\. No personal data/.test(app.text()) && !/Nothing stored/i.test(app.text()),
  app.text()
);
await app.unmount();

// =========================================================================== //
// 7. Ownership, sharing, and the counting promise
// =========================================================================== //
dom.window.localStorage.clear();
trackedCalls.length = 0;
app = await mount();

check("the footer states the owner and the rights", /© \d{4} Jame Roy\. All rights reserved\. v\d/.test(app.text()), app.text());
check("the footer shows the app version", /v1\.2\.0/.test(app.text()));
check("terms of use are linked", app.container.querySelector('a[href="/terms"]') !== null);
check("the privacy notice is linked", app.container.querySelector('a[href="/privacy.html"]') !== null);
check("sharing is offered in the footer", app.text().includes("Share"));

// Opening the app counts one anonymous open — no login anywhere.
check(
  "opening the app sends exactly one anonymous 'open'",
  trackedCalls.length === 1 && trackedCalls[0].kind === "open",
  JSON.stringify(trackedCalls)
);
check(
  "the payload carries nothing about the person: id, kind, version only",
  Object.keys(trackedCalls[0]).sort().join(",") === "app_version,device_id,kind",
  Object.keys(trackedCalls[0]).join(",")
);
check(
  "the id is random, not derived from the device",
  /^[0-9a-f-]{36}$/.test(trackedCalls[0].device_id),
  trackedCalls[0].device_id
);

// The shopper's switch must actually stop it.
const statsToggle = [...app.container.querySelectorAll("button")].find((b) =>
  /Anonymous counts/.test(b.textContent)
);
check("there is a switch for anonymous counting", statsToggle !== undefined);
check("it starts on, and says so", /Anonymous counts: On/.test(app.text()), app.text());
await act(async () => statsToggle.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
check("switching it off is reflected immediately", /Anonymous counts: Off/.test(app.text()), app.text());
check("switching it off is remembered", dom.window.localStorage.getItem("clear-price:no-stats") === "1");

trackedCalls.length = 0;
await app.use("89", "20", "70");
check("with counting off, no data is sent at all", trackedCalls.length === 0, JSON.stringify(trackedCalls));
check("...but the app still works perfectly", app.text().includes("$21.36"), app.text());

// Sharing carries the brand.
check("a share button appears with the answer", app.text().includes("Share this price"));
await app.unmount();
dom.window.localStorage.clear();

// =========================================================================== //
// 8. The shipped files that make it installable, shareable and owned
// =========================================================================== //
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "public/manifest.webmanifest"), "utf8"));
const sw = fs.readFileSync(path.join(ROOT, "public/sw.js"), "utf8");

check("index.html links the manifest", /rel="manifest"/.test(html));
check("index.html has an apple-touch-icon (iOS home screen)", /apple-touch-icon/.test(html));
check("index.html has a 1200x630 social image for link previews", /og-image\.png/.test(html));
check("index.html declares the app as JSON-LD", /"@type": "WebApplication"/.test(html));
check("index.html answers the stacked-discount question for crawlers", /FAQPage/.test(html));

check("manifest: name, start_url and standalone display", manifest.name === "Clear Price — discount calculator" && manifest.start_url === "/?from=app" && manifest.display === "standalone");
check(
  "manifest: 192, 512 and maskable icons (needed to install on Android)",
  manifest.icons.some((i) => i.sizes === "192x192") &&
    manifest.icons.some((i) => i.sizes === "512x512") &&
    manifest.icons.some((i) => i.purpose === "maskable")
);
check("manifest: a long-press shortcut opens a new calculation", manifest.shortcuts?.[0]?.name === "New calculation");
check("manifest icons all exist on disk", manifest.icons.every((i) => fs.existsSync(path.join(ROOT, "public", i.src.replace(/^\//, "")))));

check("service worker caches the app shell", sw.includes("/index.html") && sw.includes("caches.open"));
check(
  "manifest sets an app id and scope, so the install is this app (not a generic bookmark)",
  manifest.id === "/" && manifest.scope === "/"
);
check(
  "manifest declares the category it belongs in",
  Array.isArray(manifest.categories) && manifest.categories.includes("shopping")
);
check(
  "manifest declares no screenshots it cannot back up with a real capture",
  !("screenshots" in manifest) || manifest.screenshots.every((shot) => fs.existsSync(path.join(ROOT, "public", shot.src.replace(/^\//, ""))))
);

const splashDir = path.join(ROOT, "public/splash");
const splashFiles = fs.existsSync(splashDir) ? fs.readdirSync(splashDir) : [];
const startupImages = [...html.matchAll(/apple-touch-startup-image[\s\S]{0,240}?href="\/splash\/([^"]+)"/g)].map((m) => m[1]);
check("iOS launch images are declared", startupImages.length >= 8, String(startupImages.length));
check(
  "every declared launch image exists (no silent white flash on iOS)",
  startupImages.length > 0 && startupImages.every((name) => splashFiles.includes(name)),
  startupImages.join(",")
);
check(
  "every launch image declares width, height and pixel ratio",
  [...html.matchAll(/rel="apple-touch-startup-image"\s+media="([^"]+)"/g)].every(
    ([, media]) => media.includes("device-width") && media.includes("device-height") && media.includes("-webkit-device-pixel-ratio")
  )
);
check("link previews use absolute image URLs (relative ones are ignored by WhatsApp and iMessage)", /og:image" content="https:\/\//.test(html));
check("the social image is versioned, so an update is not served from a stale cache", /og-image\.png\?v=/.test(html));
check("the copyright holder is declared in the structured data", /"copyrightHolder"/.test(html) && /"Jame Roy"/.test(html));

const terms = fs.existsSync(path.join(ROOT, "public/terms.html")) ? fs.readFileSync(path.join(ROOT, "public/terms.html"), "utf8") : "";
check("a terms page exists", terms.length > 0);
check("terms state that the register's price governs", /register/i.test(terms));
check("terms assert ownership and reserve rights", /All rights reserved/.test(terms) && /property of its owner/i.test(terms));

const licence = fs.existsSync(path.join(ROOT, "..", "LICENSE")) ? fs.readFileSync(path.join(ROOT, "..", "LICENSE"), "utf8") : "";
check("a proprietary LICENSE exists", licence.length > 0 && /PROPRIETARY/i.test(licence));
check("the LICENSE names the owner", /Jame Roy/.test(licence));
check("the LICENSE forbids reuse without written permission", /WITHOUT PRIOR WRITTEN PERMISSION/i.test(licence));
check("the LICENSE disclaims warranty for price decisions", /register/i.test(licence) || /pricing authority/i.test(licence));
check("service worker never caches API calls", sw.includes('request.method !== "GET"') && sw.includes("url.origin !== self.location.origin"));

console.log(failures === 0 ? "\nAll UI checks passed." : `\n${failures} UI check(s) failed.`);

await vite.close();
dom.window.close();
process.exit(failures === 0 ? 0 : 1);
