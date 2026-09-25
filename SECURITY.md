# Security & privacy — Clear Price

A calculator that helps you read a sale tag. It holds no accounts, no payments
and no personal data, which removes most of the risk that security work usually
chases. What follows is what is actually enforced, how to verify it, and what
still needs doing before you call a launch "done".

**Last reviewed:** 25 September 2026 · **Version:** 1.1.0

---

## 1. Threat model — what we are actually defending against

| # | Threat | Why it applies here | Control |
| - | ------ | ------------------- | ------- |
| 1 | **Abuse of the free tier** — a script hammering the endpoint until Render throttles or bills you | Public, unauthenticated POST endpoint | Per-IP sliding-window rate limit (60/min default), 4 KB body cap, `Retry-After` on 429 |
| 2 | **Cross-site scripting** — a dependency or a bad input injecting script into the page | React escapes by default, but a stray `innerHTML` or a compromised CDN would undo that | Strict CSP (`script-src 'self'`, no CDNs, no `unsafe-inline`), no third-party scripts at all, `nosniff`, no `innerHTML` in the codebase |
| 3 | **Clickjacking** — the calculator framed inside a scam page to look like part of it | Trivially possible without headers | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `Cross-Origin-Opener-Policy: same-origin` |
| 4 | **Data exfiltration** — a compromised dependency posting typed prices somewhere | The app handles nothing sensitive, but users deserve the guarantee | `connect-src` limited to the API origin; no analytics, no fonts, no third-party origins in the policy |
| 5 | **Injection / parser abuse** — oversized or malformed bodies aimed at the JSON parser | FastAPI + Pydantic parse attacker input on every request | 4 KB cap enforced before parsing (even on chunked bodies that lie about length), `extra="forbid"`, typed numbers, range checks, `NaN`/`Infinity` rejected |
| 6 | **Rate-limit evasion** via a forged `X-Forwarded-For` | Header is attacker-controlled when there is no proxy | Header is believed **only** when `TRUST_PROXY=1` (default on Render); otherwise the socket peer is used. Tested both ways. |
| 7 | **Host header / DNS rebinding** | Forgery can poison absolute URLs and caches | Optional `ALLOWED_HOSTS` allowlist → real 400s (tested) |
| 8 | **Transport interception** — someone on the store Wi-Fi altering the answer | Public Wi-Fi is the normal case | HTTPS enforced everywhere; `Strict-Transport-Security` with `preload`; `upgrade-insecure-requests` in the CSP |
| 9 | **Cache leakage** — a shared/kiosk browser showing the last shopper's price | Shared phones and tablets are common | `Cache-Control: no-store` on `/calculate`; the answer is cleared the moment any field changes; the service worker never caches API responses |
| 10 | **Supply chain** — a malicious npm/pip package | Two dependency trees | Two runtime Python deps and four frontend deps; no post-install scripts added by us; lockfile committed and installs use it; `npm audit` / `pip-audit` in the checklist below |
| 11 | **PII exposure** | The strongest thing we can say is that we hold nothing | No database, no cookies, no accounts, no analytics, no request-body logging; prices are used for one request and discarded — see [privacy.html](frontend/public/privacy.html) |

**Explicitly out of scope:** a targeted attacker with control of the platform
account, physical device access, or the shopper's own browser. For an app with no
data and no money, those are not worth trading usability for.

---

## 2. What is implemented

### Backend (`backend/main.py`, `backend/security.py`)

- **Rate limiting** — sliding window, per client IP, `/calculate` only.
  60 requests/min by default; `RATE_LIMIT` and `RATE_WINDOW_SECONDS` to tune.
  Returns `429` with `Retry-After` and a plain-language message. Stale windows
  are reclaimed periodically and the key table is hard-capped at 10,000 entries,
  so a flood of unique IPs cannot exhaust memory.
- **Body size cap** — 4 KB, enforced by buffering the body ourselves, so a
  chunked request with no `Content-Length`, or a lying one, is still stopped
  before the JSON parser sees it. Returns `413`.
- **Security headers on every response**, including error responses:
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy` denying camera,
  microphone, geolocation and payment, `Cross-Origin-Resource-Policy: same-site`.
- **No caching of results** — `Cache-Control: no-store` on `/calculate`.
- **Input validation** — Pydantic models with `gt=0`, `ge=0`, `le=100`,
  `allow_inf_nan=False` and `extra="forbid"`; the endpoint re-validates at the
  boundary and returns 422 with no internal detail.
- **CORS** — `ALLOWED_ORIGINS` allowlist, `allow_credentials=False` (there are no
  cookies to send), methods and headers limited to what the app needs. The
  default `*` is safe here precisely because no credentials and no user data are
  involved; lock it down once your Vercel URL is fixed.
- **Middleware ordering is deliberate**: security headers wrap CORS, which wraps
  the limiters — so even a 429 or 413 is readable by the browser and carries the
  full header set. Tested.
- **No secrets in the repo**, no `.env` committed, config is environment-only.

### Frontend (`frontend/`)

- **Strict CSP injected at build time** (`vite.config.js`), with `connect-src`
  listing only `'self'` plus your API origin. No CDNs, no inline scripts, no
  `eval`. Also shipped as real headers by `vercel.json` on Vercel.
- **`vercel.json` headers**: HSTS (2 years, `includeSubDomains`, `preload`),
  `nosniff`, `DENY` framing, `Referrer-Policy`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, long-lived
  immutable caching for fingerprinted assets, `no-store` for `sw.js`.
- **No third-party requests at all** — no analytics, no fonts, no CDNs. What
  loads is what you shipped.
- **No `innerHTML`, no `eval`, no dynamic script insertion**; React escapes all
  rendered values.
- **The installed app stores only its own files** (service worker), never prices
  or answers. Offline mode computes on the device rather than sending anything.
- **Input parsing is deliberately permissive but bounded** — `parseNumber()`
  handles `89`, `89,99`, `$89.99`, `1,234` and rejects anything that is not a
  finite number, before it ever reaches the network.

### Privacy by design

No accounts, no cookies, no database, no analytics, no ad pixels. The price you
type is used to compute one answer and is never stored or logged. That is not a
policy promise bolted on at the end; it is why the architecture has no database
in the first place.

---

## 3. Verify it yourself

```bash
# Backend: 42 tests, covering the hardening layer specifically
cd backend && pytest -q

# Frontend: 47 checks, including offline mode and the install flow
cd frontend && npm run test:ui

# Server and browser maths agree on 8001 cases, including half-cent boundaries
.venv/bin/python tools/check_parity.py

# Live header and limit check against a running API
curl -sI http://127.0.0.1:8000/health | grep -iE 'x-content|x-frame|referrer|permissions'
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8000/calculate \
  -H 'Content-Type: application/json' \
  -d '{"original_price":89,"discount1_pct":20,"discount2_pct":70}'   # 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8000/calculate \
  -H 'Content-Type: application/json' \
  -d '{"original_price":-1,"discount1_pct":20}'                      # 422
```

Security tests worth reading: `backend/tests/test_security.py` — forged
`X-Forwarded-For` against the rate limit (both trust settings), lying
`Content-Length`, oversized chunked body, CORS headers surviving a 429/413, and
the memory bounds on the rate-limit table.

---

## 4. Before you call a launch "done" — go-live checklist

- [ ] `ALLOWED_ORIGINS` set to your real Vercel URL (not `*`) on Render.
- [ ] `ALLOWED_HOSTS` set to your Render hostname, and uncommented in `render.yaml`.
- [ ] `TRUST_PROXY=1` on Render (already in `render.yaml`); **never** set it on a
      host without a proxy, or the rate limit becomes spoofable.
- [ ] Custom domain on both sides, HTTPS on, and the Vercel domain added to
      Render's `ALLOWED_ORIGINS`.
- [ ] `VITE_API_BASE_URL` set in Vercel for **Production and Preview**.
- [ ] Replace `clear-price.vercel.app` in `index.html` (canonical, OG URLs),
      `robots.txt` and `sitemap.xml` with the real domain.
- [ ] Confirm the CSP on the deployed site matches your API origin (view source).
- [ ] `npm audit --omit=dev` and `pip-audit -r backend/requirements.txt` clean.
- [ ] GitHub: enable Dependabot alerts + secret scanning, branch protection on
      `main`, and 2FA on both the GitHub and Render accounts.
- [ ] Vercel/Render: 2FA on, deploy protection on preview URLs if the repo is
      public.
- [ ] Check the deployed site on an SSL Labs test and at
      [securityheaders.com](https://securityheaders.com) — expect A/A+.
- [ ] Re-run `pytest`, `npm run test:ui` and `check_parity.py` after any math or
      dependency change.

---

## 5. Reporting a problem

Found something? Please open a GitHub issue with the `security` label, or email
the address on the project profile. Please do not post a working exploit
publicly before there has been a chance to fix it. There is no bug bounty — this
is a free tool with no revenue — but credit will be given in the release notes
if you want it.

**Known, accepted limitations** (documented rather than hidden):

- Rate limiting is in-memory and per instance. On a single free-tier instance
  that is exact; if the service is ever scaled to several instances, each gets
  its own budget — move to Redis or an edge rate limiter at that point.
- `/docs` (Swagger UI) is public. Turn it off by setting `docs_url=None` in
  `create_app()` if you would rather not advertise the schema.
- The service worker caches the app shell. On a shared device, clear site data
  to remove it. It never holds prices or answers.
