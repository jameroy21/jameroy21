# Clear Price

**See what you really pay.** Type the tag price, type the discount(s), press one
button. Built for a phone in a store aisle — big text, high contrast, no jargon.

Installable on any phone, and **works with no signal** once installed, which is
the situation inside most big stores. No accounts, no cookies, no tracking, no
database.

> Your price is $89, the tag says **20% off**, and the clearance rack says **an
> extra 70% off**. The register will not charge you $8.90 — it charges **$21.36**.

---

## The one rule this app exists for

Discounts stack **one after the other**, never added together. The second
discount lands on the price that is *already* reduced.

```
$89.00   ── 20% off ──▶   $71.20   ── 70% off ──▶   $21.36
                          89 x 0.80              71.20 x 0.30

You pay:      $21.36
You saved:    $67.64
Combined:     76% off   (not 90% off)
```

The backend function that does this (verbatim the one in the spec):

```python
def calculate_price(original_price: float, discount1_pct: float, discount2_pct: float = 0) -> dict:
    price_after_first = original_price * (1 - discount1_pct / 100)
    final_price = price_after_first * (1 - discount2_pct / 100) if discount2_pct else price_after_first
    saved = original_price - final_price
    return {
        "original_price": round(original_price, 2),
        "final_price": round(final_price, 2),
        "amount_saved": round(saved, 2),
        "total_discount_pct": round((saved / original_price) * 100, 1),
    }
```

---

## Where to start

| I want to… | Read |
| ---------- | ---- |
| Put it live (Render + Vercel, from scratch) | [DEPLOY.md](DEPLOY.md) |
| Understand the security posture | [SECURITY.md](SECURITY.md) |
| Get people using it / launch it | [LAUNCH.md](LAUNCH.md) |
| Install it on a phone, or add a widget | [INSTALL.md](INSTALL.md) |

---

## Layout

```
backend/
  main.py                  FastAPI app: the maths + POST /calculate, config
  security.py              rate limiting, body cap, security headers (no deps)
  requirements.txt         runtime deps (fastapi, uvicorn, pydantic)
  requirements-dev.txt     + pytest, httpx
  tests/test_calculate.py  21 tests: the maths, validation, CORS
  tests/test_security.py   21 tests: headers, limits, spoofing, memory bounds
frontend/
  src/App.jsx              the whole screen (one component, no navigation)
  src/api.js               talks to the API, falls back to on-device maths
  src/calculate.js         the offline maths, parity-tested against Python
  src/InstallPrompt.jsx    "Install app" (Android) / "Add to Home Screen" (iOS)
  src/styles.css           mobile-first, big-type styles
  public/manifest.webmanifest   installable app metadata + shortcuts
  public/sw.js             service worker: instant opens, offline app shell
  public/privacy.html      plain-language privacy page
  public/robots.txt|sitemap.xml|og-image.png   SEO + link previews
  tests/ui.smoke.mjs       47 checks: UI, offline mode, install, SEO assets
  vite.config.js           dev proxy, preview hosts, build-time CSP
  vercel.json              SPA routing + security headers for Vercel
tools/
  make_brand_assets.py     regenerates the icons and the social card
  check_parity.py          fuzzes server maths vs on-device maths (8001 cases)
render.yaml                Render blueprint for the backend
```

---

## Run it locally

Two terminals, no database, no build step needed for development.

```bash
# 1. backend  →  http://127.0.0.1:8000   (docs at /docs)
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate   # first time only
pip install -r requirements-dev.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 2. frontend →  http://localhost:5173
cd frontend
npm install
npm run dev
```

In development the browser calls `/calculate` on the dev server, and Vite proxies
it to FastAPI (`vite.config.js`), so there is nothing to configure.

### Tests

```bash
cd backend  && pytest -q                     # 42 tests
cd frontend && npm run test:ui               # 47 checks (backend must be running)

# The offline maths must equal the server maths, exactly, on 8001 fuzz cases:
.venv/bin/python tools/check_parity.py
```

---

## API

### `POST /calculate`

```json
{
  "original_price": 89,
  "discount1_pct": 20,
  "discount2_pct": 70
}
```

`discount2_pct` is optional — leave it out (or send `0`, or `null`) when there is
only one discount.

```json
{
  "original_price": 89.0,
  "final_price": 21.36,
  "amount_saved": 67.64,
  "total_discount_pct": 76.0
}
```

Validation — bad input returns **422** with FastAPI's standard error body:

| Field             | Rule                                                    |
| ----------------- | ------------------------------------------------------- |
| `original_price`  | required, must be greater than 0                         |
| `discount1_pct`   | required, 0–100                                          |
| `discount2_pct`   | optional (default 0), 0–100                              |

`NaN`, `Infinity` and `-Infinity` are rejected. `GET /health` returns
`{"status": "ok"}` for uptime checks; `GET /docs` is the interactive API docs.

### CORS

The API sends `Access-Control-Allow-Origin: *` by default so any preview or
Vercel URL works out of the box. To lock it down, set an environment variable on
the host:

```
ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:5173
```

---

## Deploy

### Backend → Render

1. Render dashboard → **New + → Web Service** → connect this GitHub repo.
2. Settings:
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
3. Environment variable (optional but recommended):
   `ALLOWED_ORIGINS` = `https://<your-vercel-app>.vercel.app`
4. Deploy, then copy the service URL, e.g. `https://clear-price-api.onrender.com`.

`render.yaml` in the repo root does steps 2–3 for you: **New + → Blueprint**.

> Free instances sleep after ~15 minutes idle. The first request after that takes
> ~30–60 seconds to wake up; the app shows "Can't reach the server. Check your
> connection and try again." if it gives up. For a demo, ping `/health` first.

### Frontend → Vercel

1. Vercel dashboard → **Add New → Project** → import this repo.
2. Settings:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Vite (auto-detected; build `npm run build`, output `dist`)
3. Environment variable (Production and Preview):

   ```
   VITE_API_BASE_URL = https://clear-price-api.onrender.com     ← no trailing slash
   ```

4. Deploy. If you set `ALLOWED_ORIGINS` on Render, add the final Vercel URL there.

Locally, leave `VITE_API_BASE_URL` empty and the dev proxy handles it (copy
`frontend/.env.example` to `frontend/.env` if you want to override it).

---

## Security & privacy

Hardened by default, with nothing extra to install or audit: per-IP rate
limiting, a 4 KB request cap enforced even on lying `Content-Length` headers,
security headers on every response (including errors), strict CSP with
`connect-src` limited to your API origin, `Cache-Control: no-store` on results,
optional Host allowlist, and no third-party requests at all. Full detail,
threat model, and a go-live checklist: [SECURITY.md](SECURITY.md).

## Accessibility choices

- Body text is 20px, the answer is 48px+ (`clamp(3rem, 16vw, 4.5rem)`), inputs 32px.
- Contrast: near-black on white (~18:1), white on the result panel (~18:1),
  green saved amount on the dark panel (>10:1) — comfortably past WCAG AAA.
- All three fields use `inputmode="decimal"` so phones show the number keypad.
- Every field has a real `<label>`; the answer and any error are announced
  (`aria-live`), and errors are plain sentences, not codes.
- Tap targets are 68px inputs and a 72px button; zooming is left enabled.
- The screen never contradicts itself: the answer disappears the moment a number
  is edited, and validation errors replace it.
- No explanation text on screen — three fields, one button, one answer.

## Not in v1 (noted for later)

Third stacked discount · currency selector · share the result as an image ·
"what % off was that?" reverse mode · camera/OCR price-tag scanning · price-per-unit
comparison · a real Android widget via a Play Store wrapper. Priorities, effort
sizing and the reasoning are in [LAUNCH.md](LAUNCH.md) (Part 5).
