/**
 * Anonymous usage counting — the no-login way to know if people are using it.
 *
 * What this does
 *   Sends exactly two things to the API, ever:
 *     install  — once per device, the first time the app is opened from the
 *                home screen
 *     open     — once per device, per day
 *   together with a random id that was created on this device and a version
 *   string. That is the whole payload. No prices, no email, no phone number, no
 *   advertising id, no fingerprint.
 *
 * What this is NOT
 *   Not login. Not accounts. Not cookies. Not cross-site tracking. The design
 *   goal is that the owner learns "40 people installed it, 12 came back
 *   yesterday" and learns nothing whatsoever about who those people are.
 *
 * The shopper is in control
 *   - Turning it off in the app footer stops it immediately and permanently.
 *   - Do Not Track / Global Privacy Control are honoured automatically: if the
 *     browser asks not to be tracked, nothing is ever sent.
 *   - Clearing site data forgets the device id, and the next visit looks brand
 *     new — indistinguishable from a first-time user.
 *
 * Enabled only when an endpoint is configured (see ANALYTICS.md). With no
 * endpoint, this file is inert: no request is made and no id is created.
 */

const ENDPOINT = (
  import.meta.env.VITE_ANALYTICS_ENDPOINT ||
  import.meta.env.VITE_API_BASE_URL ||
  ""
)
  .trim()
  .replace(/\/+$/, "");

const APP_VERSION = import.meta.env.VITE_APP_VERSION || "1.2.0";

/** The build-time switch: VITE_ANALYTICS=off turns counting off entirely. */
const MODE = String(import.meta.env.VITE_ANALYTICS || "").toLowerCase();
const FORCED_OFF = MODE === "off" || MODE === "false" || MODE === "0";
const FORCED_ON = MODE === "on" || MODE === "true" || MODE === "1";

export const analyticsConfigured = !FORCED_OFF && (FORCED_ON || Boolean(ENDPOINT));

const ID_KEY = "clear-price:device-id";
const OPT_OUT_KEY = "clear-price:no-stats";
const OPENED_KEY = "clear-price:last-open";
const INSTALLED_KEY = "clear-price:reported-install";

// ---------------------------------------------------------------- storage --- //

function read(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // private mode / storage disabled
  }
}

function write(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* nothing we can do, and nothing we need */
  }
}

/** A random id with no meaning: not a fingerprint, not derived from anything. */
function deviceId() {
  const existing = read(ID_KEY);
  if (existing) return existing;
  const fresh =
    globalThis.crypto?.randomUUID?.() ||
    Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  write(ID_KEY, fresh);
  return fresh;
}

// ------------------------------------------------------------- permission --- //

/** The shopper's own switch, set in the footer. */
export function statsEnabledByUser() {
  return read(OPT_OUT_KEY) !== "1";
}

/** Browsers and extensions sometimes ask on the user's behalf. We listen. */
export function browserAsksNotToTrack() {
  return navigator.doNotTrack === "1" || window.globalPrivacyControl === true;
}

export function statsAllowed() {
  return (
    analyticsConfigured && statsEnabledByUser() && !browserAsksNotToTrack()
  );
}

/** Flip the switch and remember the choice. Off is immediate and total. */
export function setStatsEnabled(enabled) {
  if (enabled) {
    try {
      window.localStorage.removeItem(OPT_OUT_KEY);
    } catch {
      /* ignore */
    }
  } else {
    write(OPT_OUT_KEY, "1");
  }
}

// ---------------------------------------------------------------- sending --- //

/**
 * Send one event. Fire-and-forget: a failure here must never affect the
 * shopper's calculation, so errors are swallowed by design.
 */
async function send(kind) {
  if (!statsAllowed()) return false;
  try {
    await fetch(`${ENDPOINT}/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId(), kind, app_version: APP_VERSION }),
      keepalive: true,
    });
    return true;
  } catch {
    return false; // offline, blocked, server down: nobody needs to know
  }
}

/** Is the app running as an installed app rather than a browser tab? */
export function isInstalled() {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.matchMedia?.("(display-mode: minimal-ui)").matches ||
    window.navigator.standalone === true
  );
}

/**
 * Count an app open — at most once per device per day.
 *
 * Also catches installs that never fired `appinstalled` (iOS never does): if we
 * are running installed and have never reported an install, this is it.
 */
export async function noteAppOpened() {
  if (!statsAllowed()) return;

  const today = new Date().toISOString().slice(0, 10);
  if (read(OPENED_KEY) === today) return;
  write(OPENED_KEY, today);

  if (isInstalled() && read(INSTALLED_KEY) !== "1") {
    write(INSTALLED_KEY, "1");
    await send("install");
  }
  await send("open");
}

/** Count an install. Called when the browser confirms one. */
export async function noteInstalled() {
  if (read(INSTALLED_KEY) === "1") return;
  write(INSTALLED_KEY, "1");
  await send("install");
}

export { APP_VERSION };
