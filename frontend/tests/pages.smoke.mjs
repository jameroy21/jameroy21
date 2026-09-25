/**
 * GitHub Pages smoke test for the *built* site, served from a subpath.
 *
 * Loads the deployed artefact over plain HTTP — exactly the way GitHub Pages
 * serves it: no rewrites, no API, just files under /clear-price/ — and checks
 * everything that a subpath deployment silently gets wrong:
 *
 *   - every asset the HTML references actually resolves and returns 200
 *   - no root-absolute paths, which 404 only once they are live
 *   - the manifest is scoped inside the subpath, so it is installable
 *   - the service worker precaches with relative paths
 *   - nothing calls a backend that Pages cannot run
 *
 * What this test cannot do: execute the app. The built bundle is an ES module
 * and jsdom does not implement module scripts, so behaviour is covered by
 * tests/ui.smoke.mjs (which runs the real components) and the maths by
 * tools/check_parity.py. This file is about paths, scope and delivery.
 *
 * Usage: tools/pages_check.sh   (builds, serves under /clear-price/, runs this)
 */
const BASE = (process.argv[2] || "http://127.0.0.1:8099/clear-price/").replace(/\/?$/, "/");

let failures = 0;
const check = (label, condition, extra = "") => {
  console.log(`${condition ? "PASS" : "FAIL"}  ${label}${condition || !extra ? "" : `\n      saw: ${extra}`}`);
  if (!condition) failures += 1;
};

const sameOrigin = (url) => url.startsWith("/") || url.startsWith(BASE) || url.startsWith("http://127.0.0.1") || url.startsWith("http://localhost");

/**
 * Fetch an app path the way a browser resolves it against the install address:
 * "icons/x.png" -> /clear-price/icons/x.png, and "/clear-price/assets/x.js"
 * stays as it is. (Getting this wrong made an earlier version of this test
 * request /clear-price/clear-price/... and fail for the wrong reason.)
 */
async function get(path) {
  const url = path.startsWith("http") ? path : new URL(path === "" ? "./" : path, BASE).href;
  const response = await fetch(url);
  return { status: response.status, type: response.headers.get("content-type") || "", body: await response.text() };
}

// -------------------------------------------------------------- the page ------
const index = await get("./");
check("the install address serves the app", index.status === 200 && index.type.includes("html"), `${index.status} ${index.type}`);

// Every asset reference in the HTML, in the form the browser will resolve it.
const refs = [...index.body.matchAll(/(?:href|src)="([^"]+)"/g)]
  .map((match) => match[1])
  .filter((url) => !url.startsWith("#") && !url.startsWith("mailto:") && !url.startsWith("http"));

check("the page references assets", refs.length > 5, String(refs.length));

const rootAbsolute = refs.filter((url) => url.startsWith("/") && !url.startsWith("/clear-price/"));
check(
  "no root-absolute asset paths (they 404 under /clear-price/)",
  rootAbsolute.length === 0,
  rootAbsolute.join(", ")
);

// Resolve each reference the way a browser on /clear-price/ would, and fetch it.
const missing = [];
for (const ref of refs) {
  const resolved = ref.startsWith("/") ? new URL(ref, BASE).href : new URL(ref, BASE).href;
  const response = await fetch(resolved);
  if (response.status !== 200) missing.push(`${ref} -> ${response.status}`);
}
check("every asset the page references resolves", missing.length === 0, missing.join(", "));

check(
  "the page is not framed-able and not sniffable from a static host points of view (CSP meta present)",
  /Content-Security-Policy/.test(index.body),
  ""
);
check("the copyright line is in the served page", /Jame Roy/.test(index.body));
check("the app name is in the title", /<title>Clear Price/.test(index.body), "");

// ------------------------------------------------------------- the manifest ---
const manifestResponse = await get("manifest.webmanifest");
let manifest = {};
try {
  manifest = JSON.parse(manifestResponse.body);
} catch {
  /* reported by the checks below */
}
check("the manifest is served as JSON", manifestResponse.status === 200 && /json/.test(manifestResponse.type), `${manifestResponse.status} ${manifestResponse.type}`);
check(
  "the manifest is scoped inside the subpath (otherwise it will not install)",
  manifest.scope === "./" && manifest.start_url === "./?from=app" && manifest.id === "./",
  JSON.stringify({ scope: manifest.scope, start_url: manifest.start_url, id: manifest.id })
);
check(
  "manifest icons are relative, so they land inside /clear-price/",
  Array.isArray(manifest.icons) && manifest.icons.every((icon) => !icon.src.startsWith("/")),
  JSON.stringify(manifest.icons?.map((icon) => icon.src))
);

// -------------------------------------------------------- the service worker --
const sw = await get("sw.js");
check("the service worker is served", sw.status === 200, String(sw.status));
check("the service worker version was bumped for this release", sw.body.includes("clear-price-v2"));
check(
  "the service worker precaches with relative paths",
  sw.body.includes('"./index.html"') && !/["']\/index\.html["']/.test(sw.body),
  ""
);

// ------------------------------------------------------------- no backend -----
const assetRefs = refs.filter((ref) => ref.includes("assets/"));
let bundle = "";
for (const ref of assetRefs) bundle += (await get(ref)).body;
check("a JavaScript bundle is present", bundle.length > 1000, String(bundle.length));
check(
  "no backend host is baked into the bundle",
  !bundle.includes("onrender.com") && !bundle.includes("clear-price-api"),
  ""
);
// The string "/calculate" is in the shared module either way (the server path is
// compiled out at runtime, not build time), so assert the mode instead: the
// local-answer copy only exists when this build can calculate without a server.
check(
  "the build can answer without a server",
  bundle.includes("Worked out on your phone"),
  ""
);

// Prove the graceful-degradation path this host produces. A Pages site answers
// 404 for /calculate, and the app treats 404 as "no API here" and calculates
// locally rather than showing the shopper an error.
const apiProbe = await get("calculate");
check(
  "this host has no calculation endpoint, and says so with 404 (what the app treats as 'no API')",
  apiProbe.status === 404,
  String(apiProbe.status)
);

// ------------------------------------------------------------- the pages ------
for (const path of [
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-maskable-512.png",
  "icons/apple-touch-icon.png",
  "icons/favicon-32.png",
  "splash/splash-1170x2532.png",
  "og-image.png",
  "terms.html",
  "privacy.html",
  "robots.txt",
  "sitemap.xml",
]) {
  const response = await get(path);
  const ok = response.status === 200;
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${path} is served (${response.status})`);
}

// The pages a phone can reach must not depend on SPA rewrites Pages does not have.
const terms = await get("terms.html");
check("terms links back to the app relatively", terms.body.includes('href="./"'));
check("terms mentions ownership", /All rights reserved/.test(terms.body));

const privacy = await get("privacy.html");
check("the privacy notice loads", privacy.status === 200 && /Privacy/.test(privacy.body));
check(
  "the privacy notice does not promise a counting switch that this deploy lacks",
  /Where anonymous counting is switched on/.test(privacy.body),
  ""
);

console.log(failures === 0 ? "\nAll Pages checks passed." : `\n${failures} Pages check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
