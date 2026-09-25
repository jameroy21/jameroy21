# Changelog

All notable changes to Clear Price. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

Copyright (c) 2026 Jame Roy. All rights reserved. See [LICENSE](LICENSE).

---

## [1.2.0] — 25 September 2026

Ownership, a branded install, and anonymous usage insight — no logins.

### Added — ownership and release surface

- **LICENSE** — proprietary, all rights reserved; no licence granted by
  publication. Explicitly prohibits copying, derivative works, redeployment and
  use of the name or logo.
- **Terms of use** (`/terms`) — plain-language terms covering the "it is a guide,
  the register governs" position, acceptable use, ownership, warranty and
  liability.
- **Copyright notice** in the API source, in the API metadata (`contact`,
  `license_info`), and in the app footer: `© 2026 Jame Roy. All rights
  reserved. v1.2.0`.
- **OWNER / COPYRIGHT_YEAR / APP_VERSION / OWNER_URL** as single sources of
  truth in `backend/main.py`, surfaced on `GET /`.

### Added — the app installs as *this* app, not a generic bookmark

- **iOS launch images** (`splash/`, 10 device sizes) wired with
  `apple-touch-startup-image`, so opening from the home screen shows the brand
  instead of a white flash.
- **Richer manifest**: `id`, `scope`, `display_override`, `launch_handler`,
  `prefer_related_applications`, and the short name and description people see
  under the icon.
- Regenerated brand assets: the tag mark is legible down to 32px, the `%` is a
  real glyph with no self-intersection, the tag's string hole is punched through,
  and the background is a seamless gradient. `tools/make_brand_assets.py`
  reproduces every icon, the splash set and the social card.

### Added — knowing people use it, without accounts

- **`POST /track`** — counts exactly two events, `install` (once per device) and
  `open` (once per device per day), using a random device id plus the app
  version. No email, no phone number, no login, no cookie, no IP address, no
  prices. `extra="forbid"` means a client cannot smuggle anything else in.
- **`GET /stats/summary`** — owner-only report (bearer `STATS_TOKEN`): installs,
  distinct devices, active today / 7 days / 30 days, returning devices,
  retention %, and a 14-day trend. Answering "is it growing, and do people come
  back?" without knowing a single person.
- **Privacy by construction** (`backend/stats.py`): device ids are replaced by
  `HMAC-SHA256(STATS_SECRET, id)` before anything is written; the table has
  exactly three columns (`day`, `device`, `kind`) so there is nowhere to put an
  identity; counting is distinct devices, never event totals; retention is
  enforced (`STATS_RETENTION_DAYS`, default 400).
- **Shopper control** (`frontend/src/analytics.js`): a footer switch
  ("Anonymous counts: On / Off") that stops collection immediately and
  permanently; Do Not Track and Global Privacy Control honoured automatically;
  clearing site data forgets the device id. Counting is disabled entirely with
  `STATS_DB=off` or `VITE_ANALYTICS=off`.
- **Separate rate-limit bucket** for `/track`, so counting traffic can never
  block someone from getting a price (and vice versa).
- **`ANALYTICS.md`** — what is counted, what is never counted, the privacy
  argument, and the commands to read the owner report.
- **25 tests** (`backend/tests/test_stats.py`) that assert the privacy claims
  rather than describing them: raw ids are absent from the database file, the
  schema has no identity column, rotating the secret breaks linkage, the report
  contains no hashes, and the endpoint is invisible without a token.
- **Sharing carries the brand** (`frontend/src/ShareButton.jsx`): the phone's
  share sheet opens with "Clear Price" as the title and the calculation in the
  message, with a clipboard fallback on desktop.

### Added — SEO for a product, not a page

- **Link previews that work**: `og:image` and `twitter:image` now use absolute,
  size-versioned URLs (WhatsApp, iMessage, X, Facebook and Slack only accept
  absolute URLs; the version query busts their caches after an update).
- **Terms page** at `/terms` (`cleanUrls`), linked from the footer, listed in the
  sitemap, and excluded from the SPA rewrite in `vercel.json`.
- Structured data gains the real page URL and the licence/ownership position.

### Fixed

- **Retention never pruned**: the cleanup compared a SQLite Julian day number
  with a Gregorian ordinal, so expired rows were never deleted. Now compares ISO
  day strings, which also uses the index. Caught by `test_old_events_are_deleted`.
- **`Cache-Control: no-store` only applied to POSTs**, leaving the owner report
  cacheable on a shared device. The header now follows the path, whatever the
  method.
- **Android install screenshots removed from the manifest.** Chrome validates
  that declared image sizes match the real PNG, and the sandbox had no browser to
  capture the app with. Shipping a wrong or overlapping image in the install
  dialog is worse than shipping none; `tools/make_screenshots.mjs` captures real
  ones locally and the header documents exactly how to add them back.

### Verification (v1.2.0)

| Check | Result |
| ----- | ------ |
| `cd backend && pytest -q` | 67 passed (21 maths + 21 security + 25 stats) |
| `cd frontend && npm run test:ui` | 47 checks passed, including offline and install flows |
| `python tools/check_parity.py` | 8,001 cases, on-device maths matches the server exactly |
| `npm run build` | clean, ~50 KB gzipped, CSP injected with `connect-src` scoped to the API |

---

## [1.1.0] — 25 September 2026

Hardened and installable, plus the launch playbook.

### Added

- **Security hardening** (`backend/security.py`, dependency-free): per-IP sliding
  window rate limiting on `/calculate` (60/min, `Retry-After` on 429), a 4 KB body
  cap enforced by buffering so a lying `Content-Length` cannot smuggle a large
  body, security headers on every response including errors, `Cache-Control:
  no-store` on results, optional `ALLOWED_HOSTS` allowlist, and `extra="forbid"`
  on request models. `X-Forwarded-For` is believed only when `TRUST_PROXY` is set.
- **Installable app**: web manifest, service worker (app shell only — API
  responses are never cached), maskable icon, an Install button on Android and
  Add-to-Home-Screen guidance on iOS, dismissable and remembered.
- **Offline mode**: with no signal the app calculates on the device and says so.
  A parity fuzzer (`tools/check_parity.py`, 8,001 cases) proves the on-device
  maths matches the server exactly.
- **Strict CSP** injected at build time, with `connect-src` scoped to the API
  origin; full security header set via `vercel.json` (HSTS preload,
  `nosniff`, `X-Frame-Options`, `Permissions-Policy`, COOP/CORP).
- **SEO foundations**: canonical, Open Graph and Twitter cards, `WebApplication`
  and `FAQPage` JSON-LD, `robots.txt`, `sitemap.xml`, `<noscript>` content, and a
  collapsed "How this works" explainer so the screen stays simple while crawlers
  get real text.
- **Documentation**: `SECURITY.md` (threat model, controls, go-live checklist),
  `DEPLOY.md` (Render + Vercel from scratch), `INSTALL.md` (per-platform install,
  widget options, Play Store and App Store paths), `LAUNCH.md` (CEO/SEO playbook).
- 21 security tests and 30 new UI checks.

### Fixed

- **One-cent divergence at half-cent boundaries** between the server and offline
  maths ($200.22 at 75% off rounded to $50.06 on the phone and $50.05 on the
  server). Python rounds the exact binary value with ties to even; the usual
  `Math.round(value * 100) / 100` shortcut re-rounds a value that lands exactly
  on a half cent. Replaced with an exact-decimal, ties-to-even implementation.

---

## [1.0.0] — 25 September 2026

First release.

### Added

- **FastAPI backend** with a single `POST /calculate` endpoint built on the
  specified `calculate_price()`: discounts apply sequentially, so $89 with 20%
  off then 70% off is $21.36, a 76% saving — not the $8.90 that adding the
  discounts together would suggest. Validation for price > 0 and 0–100
  discounts; `NaN`/`Infinity` rejected; CORS configurable via `ALLOWED_ORIGINS`.
- **React single-screen frontend**: three large fields, one button, one answer
  ("You pay $21.36" / "You saved $67.64" / "76% off $89.00"). No navigation, no
  jargon, no explanation text on screen.
- **Mobile-first accessibility**: 20px body text, 48px+ result, WCAG AAA
  contrast, `inputmode="decimal"` keypad on every field, real labels, `aria-live`
  announcements, plain-sentence errors, 68px inputs and a 72px button.
- **Forgiving input**: `89`, `89,99` and `$ 89.99` all parse; the answer clears
  the moment a number is edited, so the screen never contradicts itself.
- 21 backend tests and 17 UI checks driving the real component against the live
  API.
- `render.yaml` blueprint and copy-paste deployment steps in `CLEAR_PRICE.md`.

### Security notes

- No database, no accounts, no cookies, no third-party requests.
