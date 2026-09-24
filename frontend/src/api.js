/**
 * Talks to the Clear Price API.
 *
 * VITE_API_BASE_URL is set per environment:
 *   - Vercel / production : https://<your-render-service>.onrender.com  (no trailing slash)
 *   - local dev           : leave it empty — Vite proxies "/calculate" to
 *                           http://127.0.0.1:8000 (see vite.config.js)
 */
const RAW_BASE = import.meta.env.VITE_API_BASE_URL || "";

export const API_BASE = RAW_BASE.trim().replace(/\/+$/, "");

/** Thrown for anything the shopper can act on; `message` is user-facing. */
export class ApiError extends Error {
  constructor(message, { retryable = true } = {}) {
    super(message);
    this.name = "ApiError";
    this.retryable = retryable;
  }
}

export async function calculatePrice({
  originalPrice,
  discount1Pct,
  discount2Pct,
}) {
  const body = {
    original_price: originalPrice,
    discount1_pct: discount1Pct,
  };
  if (discount2Pct) body.discount2_pct = discount2Pct;

  let response;
  try {
    response = await fetch(`${API_BASE}/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    // Offline, DNS failure, timeout, CORS blocked...
    throw new ApiError("Can't reach the server. Check your connection and try again.");
  }

  if (!response.ok) {
    if (response.status === 422 || response.status === 400) {
      // The backend says the numbers are out of range — should be rare, since
      // the form checks first.
      throw new ApiError("Please check the numbers and try again.", {
        retryable: false,
      });
    }
    throw new ApiError("Something went wrong on our side. Please try again.");
  }

  return response.json();
}
