import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend address used by the dev-server proxy (server side only — the browser
// always talks to the dev server itself, so this also works behind a proxy).
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const API_BASE_URL = (process.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");

/**
 * Inject a strict Content-Security-Policy into the **built** HTML only.
 *
 * Dev is left alone on purpose: Vite injects inline scripts for hot reload, and
 * a policy strict enough to be worth having would block them.
 *
 * connect-src lists the API origin explicitly, so a compromised dependency
 * cannot quietly post the shopper's prices somewhere else. Vercel also sends
 * these headers (see vercel.json) — this is the belt-and-braces version that
 * travels with the HTML, and applies even on hosts that do not send headers.
 */
function contentSecurityPolicy() {
  const connect = ["'self'", ...(API_BASE_URL ? [API_BASE_URL] : [])];
  const policy = [
    "default-src 'self'",
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    `connect-src ${connect.join(" ")}`,
    "upgrade-insecure-requests",
  ].join("; ");

  return {
    name: "clear-price-csp",
    apply: "build",
    transformIndexHtml(html) {
      return html.replace(
        "</title>",
        `</title>\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), contentSecurityPolicy()],
  server: {
    host: true, // listen on 0.0.0.0 so the preview URL can reach it
    port: 5173,
    strictPort: false,
    // Accept whatever host the preview/proxy uses (localhost, *.e2b.app, ngrok...).
    allowedHosts: true,
    proxy: {
      // In development the app calls "/calculate" and Vite forwards it to FastAPI.
      "/calculate": { target: BACKEND_URL, changeOrigin: true },
      "/health": { target: BACKEND_URL, changeOrigin: true },
    },
  },
  preview: {
    host: true,
    port: 4173,
    allowedHosts: true,
  },
  build: {
    // The service worker is shipped from public/ untouched; make sure nothing
    // ever inlines a sourcemap with server paths into the bundle.
    sourcemap: false,
  },
});
