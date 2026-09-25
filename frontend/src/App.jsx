import { useEffect, useId, useRef, useState } from "react";

import {
  APP_VERSION,
  analyticsConfigured,
  noteAppOpened,
  noteInstalled,
  setStatsEnabled,
  statsEnabledByUser,
} from "./analytics.js";
import { ApiError, calculatePrice } from "./api.js";
import InstallPrompt from "./InstallPrompt.jsx";
import ShareButton from "./ShareButton.jsx";

/** © 2026 Jame Roy — all rights reserved. See LICENSE. */
const OWNER = "Jame Roy";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function formatPercent(value) {
  // 76.0 -> "76%", 27.5 -> "27.5%"
  return `${Number(Number(value).toFixed(1))}%`;
}

/**
 * Read a number out of whatever the shopper typed:
 * "89", "89.99", "89,99", "$ 89.99", "1,234" all work.
 * Returns null when there is no usable number.
 */
function parseNumber(raw) {
  let text = String(raw).replace(/[^\d.,]/g, "");
  if (!text) return null;

  const hasComma = text.includes(",");
  const hasDot = text.includes(".");

  if (hasComma && hasDot) {
    // Both separators: the last one is the decimal point.
    text =
      text.lastIndexOf(",") > text.lastIndexOf(".")
        ? text.replace(/\./g, "").replace(",", ".")
        : text.replace(/,/g, "");
  } else if (hasComma) {
    const commas = text.split(",");
    if (commas.length > 2) {
      text = text.replace(/,/g, ""); // 1,234,567 -> grouping
    } else {
      const [head, tail] = commas;
      // "1,234" reads as one thousand; "9,99" reads as 9.99.
      text = tail.length === 3 && head.length <= 3 ? head + tail : `${head}.${tail}`;
    }
  }

  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

export default function App() {
  const [priceText, setPriceText] = useState("");
  const [firstText, setFirstText] = useState("");
  const [secondText, setSecondText] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [statsOn, setStatsOn] = useState(statsEnabledByUser);

  const ids = {
    price: useId(),
    first: useId(),
    second: useId(),
    error: useId(),
  };
  const resultRef = useRef(null);

  /**
   * Count this visit (anonymous, once per day — see analytics.js) and listen for
   * the browser confirming an install. Nothing here ever affects the maths, and
   * nothing is sent when the shopper has opted out or their browser asks not to
   * be tracked.
   */
  useEffect(() => {
    noteAppOpened();
    const onInstalled = () => noteInstalled();
    window.addEventListener("appinstalled", onInstalled);
    return () => window.removeEventListener("appinstalled", onInstalled);
  }, []);

  function toggleStats() {
    const next = !statsOn;
    setStatsOn(next);
    setStatsEnabled(next);
    if (next) noteAppOpened();
  }

  /**
   * Any change to a number clears the previous answer, so what is on screen can
   * never contradict the numbers on screen.
   */
  function update(setter) {
    return (event) => {
      setter(event.target.value);
      setResult(null);
      setError("");
    };
  }

  function reject(message) {
    setResult(null);
    setError(message);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    const price = parseNumber(priceText);
    const first = firstText.trim() === "" ? null : parseNumber(firstText);
    const second = secondText.trim() === "" ? null : parseNumber(secondText);

    if (priceText.trim() === "") {
      reject("Type the price on the tag first.");
      return;
    }
    if (price === null || price <= 0) {
      reject("The price has to be more than 0.");
      return;
    }
    if (firstText.trim() !== "" && (first === null || first < 0 || first > 100)) {
      reject("Discount 1 has to be between 0 and 100.");
      return;
    }
    if (secondText.trim() !== "" && (second === null || second < 0 || second > 100)) {
      reject("Discount 2 has to be between 0 and 100.");
      return;
    }

    setBusy(true);
    try {
      const data = await calculatePrice({
        originalPrice: price,
        discount1Pct: first ?? 0,
        discount2Pct: second ?? 0,
      });
      setResult(data);
      // Bring the answer into view on a small screen. Guarded so an unusual
      // browser (or a test DOM) without these APIs never hides the answer.
      const reduceMotion = window.matchMedia?.(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      const schedule = window.requestAnimationFrame
        ? window.requestAnimationFrame.bind(window)
        : (callback) => setTimeout(callback, 0);
      schedule(() => {
        resultRef.current?.scrollIntoView?.({
          behavior: reduceMotion ? "auto" : "smooth",
          block: "center",
        });
      });
    } catch (err) {
      setResult(null);
      setError(
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <header className="masthead">
        <h1 className="masthead__title">Clear Price</h1>
        <p className="masthead__tagline">What will I really pay?</p>
      </header>

      <form className="card" onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label className="field__label" htmlFor={ids.price}>
            Original Price
          </label>
          <div className="field__control">
            <span className="field__prefix" aria-hidden="true">
              $
            </span>
            <input
              id={ids.price}
              className="field__input field__input--money"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              enterKeyHint="next"
              placeholder="89"
              value={priceText}
              onChange={update(setPriceText)}
              autoFocus
            />
          </div>
        </div>

        <div className="field">
          <label className="field__label" htmlFor={ids.first}>
            Discount 1 (%)
          </label>
          <div className="field__control">
            <input
              id={ids.first}
              className="field__input field__input--percent"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              enterKeyHint="next"
              placeholder="20"
              value={firstText}
              onChange={update(setFirstText)}
            />
            <span className="field__suffix" aria-hidden="true">
              %
            </span>
          </div>
        </div>

        <div className="field">
          <label className="field__label" htmlFor={ids.second}>
            Discount 2 (%) <span className="chip">optional</span>
          </label>
          <div className="field__control">
            <input
              id={ids.second}
              className="field__input field__input--percent"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              enterKeyHint="done"
              placeholder="70"
              value={secondText}
              onChange={update(setSecondText)}
            />
            <span className="field__suffix" aria-hidden="true">
              %
            </span>
          </div>
        </div>

        <button className="button" type="submit" disabled={busy}>
          {busy ? "Checking…" : "Show Final Price"}
        </button>
      </form>

      <div id={ids.error} role="alert" aria-live="assertive">
        {error ? <p className="alert">{error}</p> : null}
      </div>

      <section
        className="result"
        ref={resultRef}
        aria-live="polite"
        aria-atomic="true"
      >
        {result ? (
          <>
            <p className="result__label">You pay</p>
            <p className="result__price">{money.format(result.final_price)}</p>
            <p className="result__saved">
              You saved {money.format(result.amount_saved)}
            </p>
            <p className="result__detail">
              {formatPercent(result.total_discount_pct)} off{" "}
              {money.format(result.original_price)}
            </p>
            {result.offline ? (
              <p className="result__note">
                Offline — the same maths, done on your phone.
              </p>
            ) : null}
            <ShareButton result={result} formatMoney={money.format} />
          </>
        ) : null}
      </section>

      <InstallPrompt />

      {/*
        Kept closed by default: the screen stays simple, but search engines and
        anyone who does read it get real, useful words instead of an empty page.
      */}
      <details className="explainer">
        <summary className="explainer__summary">How this works</summary>
        <div className="explainer__body">
          <p>
            A second discount comes off the already-discounted price, not the
            original price. So 20% off and then another 70% off is not 90% off —
            it is 76% off.
          </p>
          <p className="explainer__example">
            $89, then 20% off: $71.20. Then 70% off that: $21.36. You save $67.64.
          </p>
        </div>
      </details>

      <footer className="footer">
        <p className="footer__promise">
          Free. No account. No personal data — ever.
        </p>
        <p className="footer__actions">
          <ShareButton variant="link" />
          {analyticsConfigured ? (
            <button
              type="button"
              className="footer__link"
              onClick={toggleStats}
              aria-pressed={statsOn}
            >
              Anonymous counts: {statsOn ? "On" : "Off"}
            </button>
          ) : null}
          <a className="footer__link" href="/terms">
            Terms
          </a>
          <a className="footer__link" href="/privacy.html">
            Privacy
          </a>
        </p>
        <p className="footer__legal">
          © {new Date().getFullYear()} {OWNER}. All rights reserved. v{APP_VERSION}
        </p>
      </footer>
    </main>
  );
}
