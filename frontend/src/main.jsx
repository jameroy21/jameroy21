import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Install the service worker so the app opens instantly and keeps working in
// stores with no signal. Production only: in dev it would serve stale modules
// and make hot reload confusing.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    // BASE_URL is "/" or "/clear-price/", so the worker registers inside the
    // project path and its scope matches the pages it may serve.
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {
      // No offline mode, no problem: the app still works normally online.
    });
  });
}
