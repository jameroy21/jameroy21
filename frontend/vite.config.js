import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend address used by the dev-server proxy (server side only — the browser
// always talks to the dev server itself, so this also works behind a proxy).
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
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
});
