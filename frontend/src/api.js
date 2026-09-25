/**
 * Talks to the Clear Price API, or calculates on the device when there is none.
 *
 * Three ways this app can run, chosen at build time:
 *
 *   server + offline fallback (default)
 *     Posts to the API. If the phone has no signal, or the host returns 404
 *     because there is no API behind it at all (GitHub Pages, a file on a USB
 *     stick, an intranet mirror), the identical maths runs locally instead of
 *     showing an error.
 *
 *   local only (`VITE_CALC_MODE=local`, used by the GitHub Pages build)
 *     Never touches the network. The whole app is ~50 KB and the maths is
 *     already parity-tested against the server, so a static host gives an
 *     instant answer that works offline from the very first launch.
 *
 *   API base configured (`VITE_API_BASE_URL`, used by the Vercel build)
 *     Calls the FastAPI service, which is the primary path there.
 *
 * Whichever way it runs, the number is the same: tools/check_parity.py fuzzes
 * both implementations against each other on 8,001 cases.
 */
import { calculatePriceLocally } from "./calculate.js";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL || "";

export const API_BASE = RAW_BASE.trim().replace(/\/+$/, "");

const MODE = String(import.meta.env.VITE_CALC_MODE || "auto").toLowerCase();

/** true when this build must never call the network for a calculation. */
export const LOCAL_ONLY = MODE === "local" || MODE === "offline";

const FRIENDLY = {
  413: "Those numbers were too long. Please type them again.",
  422: "Please check the numbers and try again.",
  429: "Too many tries at once. Wait a second and press again.",
};

/** Statuses that mean "this host has no API here", not "something broke". */
const NO_API = new Set([404, 405, 501]);

/** Thrown for anything the shopper can act on; `message` is user-facing. */
export class ApiError extends Error {
  constructor(message, { offline = false, noApi = false } = {}) {
    super(message);
    this.name = "ApiError";
    /** true when the request never reached a server (no signal / airplane mode). */
    this.offline = offline;
    /** true when the host answered, but has no calculation endpoint. */
    this.noApi = noApi;
  }
}

async function postCalculate(body) {
  let response;
  try {
    response = await fetch(`${API_BASE}/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    // fetch only rejects on network-level failure: offline, DNS, timeout, CORS.
    throw new ApiError("Can't reach the server.", { offline: true });
  }

  if (!response.ok) {
    if (NO_API.has(response.status)) {
      // A static host answering for a path it does not serve. Not our fault,
      // and not the shopper's problem — calculate locally instead.
      throw new ApiError("No calculation service here.", { noApi: true });
    }
    throw new ApiError(
      FRIENDLY[response.status] || "Something went wrong on our side. Please try again."
    );
  }
  return response.json();
}

/**
 * Work out the price, using the server when there is one.
 *
 * Server responses win — including error responses, which are passed straight
 * through so the shopper sees the real reason (bad numbers, too many tries).
 * Only a request that never reached a calculation service falls back.
 */
export async function calculatePrice({ originalPrice, discount1Pct, discount2Pct }) {
  const locally = (source) => ({
    ...calculatePriceLocally(originalPrice, discount1Pct, discount2Pct),
    source,
    offline: source === "offline",
  });

  if (LOCAL_ONLY) return locally("local");

  const body = { original_price: originalPrice, discount1_pct: discount1Pct };
  if (discount2Pct) body.discount2_pct = discount2Pct;

  try {
    const data = await postCalculate(body);
    return { ...data, source: "server", offline: false };
  } catch (error) {
    if (!(error instanceof ApiError) || !(error.offline || error.noApi)) throw error;
    return locally(error.offline ? "offline" : "local");
  }
}
