import { useEffect, useState } from "react";

/**
 * "Install this app" — the polite version.
 *
 * Android/Chrome fires `beforeinstallprompt`, which lets us show a real button
 * that installs the app in one tap. iOS has no such event, so iPhone users get
 * one short line telling them where the button is (Share -> Add to Home Screen).
 *
 * Nothing is ever shown when the app is already installed, and a dismissal is
 * remembered, so this never becomes nagging.
 */
const DISMISS_KEY = "clear-price:install-dismissed";

function isStandalone() {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    // Older iOS Safari
    window.navigator.standalone === true
  );
}

function isIos() {
  const ua = window.navigator.userAgent || "";
  const iOS = /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && "ontouchend" in document);
  return iOS;
}

export default function InstallPrompt() {
  const [deferredEvent, setDeferredEvent] = useState(null);
  const [showIosHelp, setShowIosHelp] = useState(false);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if (isStandalone()) return;

    let dismissed = false;
    try {
      dismissed = window.localStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      // Private mode: just show the prompt, nothing to remember.
    }
    if (dismissed) return;

    setHidden(false);

    const onBeforeInstall = (event) => {
      event.preventDefault(); // keep the mini-infobar away; we show our own button
      setDeferredEvent(event);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", () => setHidden(true));

    // iPhone: no install event exists, so offer the two-tap instructions.
    if (isIos()) setShowIosHelp(true);

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  function dismiss() {
    setHidden(true);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* nothing to remember */
    }
  }

  async function install() {
    if (!deferredEvent) return;
    deferredEvent.prompt();
    const { outcome } = await deferredEvent.userChoice;
    if (outcome === "accepted") setHidden(true);
    setDeferredEvent(null);
  }

  if (hidden) return null;
  if (!deferredEvent && !showIosHelp) return null;

  return (
    <aside className="install" aria-label="Install this app">
      {deferredEvent ? (
        <button type="button" className="install__button" onClick={install}>
          Install app
        </button>
      ) : null}

      {showIosHelp ? (
        <p className="install__hint">
          Add to Home Screen: tap <span className="install__key">Share</span> then{" "}
          <span className="install__key">Add to Home Screen</span>.
        </p>
      ) : null}

      <button type="button" className="install__dismiss" onClick={dismiss} aria-label="Not now">
        Not now
      </button>
    </aside>
  );
}
