import { useState } from "react";

import { APP_VERSION } from "./analytics.js";

/**
 * Sharing, with the app's own name attached.
 *
 * Without this, sharing means pasting a bare URL and hoping the preview appears.
 * With the Web Share API, the phone's share sheet opens with a proper title and
 * message — "Clear Price — what do I really pay?" plus the numbers if there is a
 * result on screen — so whoever receives it knows what it is before they tap.
 *
 * On a browser without Web Share (most desktops), it copies the same message to
 * the clipboard and says so.
 */
const SITE_URL = import.meta.env.VITE_SITE_URL || "https://clear-price.vercel.app";

export default function ShareButton({ result, formatMoney, variant = "button" }) {
  const [note, setNote] = useState("");

  const url = `${SITE_URL.replace(/\/+$/, "")}/`;

  function message() {
    if (result) {
      const numbers =
        `${formatMoney(result.final_price)} after ` +
        `${Number(Number(result.total_discount_pct).toFixed(1))}% off — ` +
        `saved ${formatMoney(result.amount_saved)}.`;
      return `Clear Price says: ${numbers} Work out your own: ${url}`;
    }
    return `Clear Price — type a tag price and the discounts, see what you really pay. Works offline. ${url}`;
  }

  async function share() {
    const text = message();
    try {
      if (navigator.share) {
        await navigator.share({ title: "Clear Price", text, url });
        return;
      }
      await navigator.clipboard.writeText(text);
      setNote("Copied — paste it anywhere.");
    } catch (error) {
      // The shopper cancelled the share sheet, or the clipboard is blocked.
      if (error?.name !== "AbortError") setNote("Long-press to copy the address instead.");
    }
    setTimeout(() => setNote(""), 4000);
  }

  return (
    <span className="share">
      <button
        type="button"
        className={variant === "link" ? "share__link" : "share__button"}
        onClick={share}
        data-app-version={APP_VERSION}
      >
        {result ? "Share this price" : "Share"}
      </button>
      <span className="share__note" role="status" aria-live="polite">
        {note}
      </span>
    </span>
  );
}
