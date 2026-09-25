/**
 * Clear Price service worker.
 *
 * Makes the installed app open instantly and work with no signal — which is the
 * normal situation in the middle of a store. Strategy:
 *
 *   navigation (the page itself)  -> network first, cached shell as fallback
 *   same-origin assets            -> cache first (Vite fingerprints them, so a
 *                                    cached file is always the right file)
 *   anything else (API, analytics) -> not touched, never cached
 *
 * No prices or answers are ever stored: only the app's own files.
 */

const CACHE = "clear-price-v2";

// Relative on purpose. A service worker's scope is its own directory, so these
// resolve to /clear-price/... on a GitHub Pages project site and to / on a
// custom domain — the same file, no build-time rewriting, no broken precache.
// (Bump CACHE whenever the shell changes, or clients keep the old files.)
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
  "./icons/favicon-32.png",
];

/** Absolute URL for a shell entry, resolved against this script's location. */
const absolute = (relative) => new URL(relative, self.location).href;

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      // Individual puts: one missing file must not fail the whole install.
      await Promise.all(
        SHELL.map((url) =>
          cache.add(new Request(absolute(url), { cache: "reload" })).catch(() => {})
        )
      );
      await self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Never interfere with API calls or anything that is not a plain GET.
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(request);
          const cache = await caches.open(CACHE);
          cache.put(absolute("./index.html"), fresh.clone());
          return fresh;
        } catch {
          const cache = await caches.open(CACHE);
          return (
            (await cache.match(absolute("./index.html"))) ||
            (await cache.match(absolute("./"))) ||
            new Response("Clear Price is offline.", {
              status: 503,
              headers: { "Content-Type": "text/plain" },
            })
          );
        }
      })()
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(request);
      if (hit) return hit;
      try {
        const fresh = await fetch(request);
        if (fresh.ok && fresh.type === "basic") cache.put(request, fresh.clone());
        return fresh;
      } catch {
        return new Response("", { status: 504 });
      }
    })()
  );
});

// Let the page apply a new version immediately instead of on the next visit.
self.addEventListener("message", (event) => {
  if (event.data === "skip-waiting") self.skipWaiting();
});
