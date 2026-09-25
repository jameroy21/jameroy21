/**
 * Talks to the Clear Price API, and keeps working when it cannot be reached.
 *
 * VITE_API_BASE_URL is set per environment:
 *   - Vercel / production : https://<your-render-service>.onrender.com  (no trailing slash)
 *   - local dev           : leave it empty — Vite proxies "/calculate" to
 *                           http://127.0.0.1:8000 (see vite.config.js)
 */
import { calculatePriceLocally } from "./calculate.js";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL || "";

export const API_BASE = RAW_BASE.trim().replace(/\/+$/, "");

const FRIENDLY = {
  413: "Those numbers were too long. Please type them again.",
  422: "Please check the numbers and try again.",
  429: "Too many tries at once. Wait a second and press again.",
};

/** Thrown for anything the shopper can act on; `message` is user-facing. */
export class ApiError extends Error {
  constructor(message, { offline = false } = {}) {
    super(message);
    this.name = "ApiError";
    /** true when the request never reached a server (no signal / airplane mode). */
    this.offline = offline;
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
    throw new ApiError(
      FRIENDLY[response.status] || "Something went wrong on our side. Please try again."
    );
  }
  return response.json();
}

/**
 * Ask the server, or calculate on the device when there is no connection.
 *
 * Server responses win — including error responses, which are passed straight
 * through so the shopper sees the real reason. Only a request that never
 * reached a server falls back to the identical local maths, flagged
 * `offline: true` so the screen can say so.
 */
export async function calculatePrice({ originalPrice, discount1Pct, discount2Pct }) {
  const body = { original_price: originalPrice, discount1_pct: discount1Pct };
  if (discount2Pct) body.discount2_pct = discount2Pct;

  try {
    const data = await postCalculate(body);
    return { ...data, source: "server", offline: false };
  } catch (error) {
    if (!(error instanceof ApiError) || !error.offline) throw error;

    const data = calculatePriceLocally(originalPrice, discount1Pct, discount2Pct);
    return { ...data, source: "offline", offline: true };
  }
}
