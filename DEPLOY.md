# Deploying Clear Price — from scratch to a live URL

Two free hosts, about 20 minutes, no credit card. Backend on **Render**
(FastAPI). The frontend ships two ways: a **static GitHub Pages** build that
answers on the phone with no server at all, and the same React app on
**Vercel** wired to the API for the full counting setup. Both come from this
GitHub repo so every push deploys itself.

Order matters: the backend first, because the frontend needs its URL, and then
the frontend URL goes back into the backend's CORS settings.

```
GitHub repo ──┬──▶ Pages   (frontend, static)   https://jameroy21.github.io/clear-price/
              │      └─ the install address: works offline, no server needed
              ├──▶ Render  (backend, FastAPI)   https://clear-price-api.onrender.com
              └──▶ Vercel  (frontend, React)    https://clear-price.vercel.app
                     └─ optional: the API-backed version with install counting

Vercel needs: VITE_API_BASE_URL = the Render URL
Render needs: ALLOWED_ORIGINS   = the Vercel URL
```

**If all you want is the app on your phone, deploy §2 and stop** — GitHub Pages
needs no account beyond the one you already have and no backend at all. Render
and Vercel are for the version that counts installs and answers from the server.

---

## 0. Five minutes before you start

- [ ] Code pushed to GitHub (the repo this file lives in).
- [ ] A [Render](https://render.com) account (GitHub sign-in is fine).
- [ ] A [Vercel](https://vercel.com) account (GitHub sign-in is fine).
- [ ] **2FA switched on** on GitHub, Render and Vercel.
- [ ] Optionally, a domain you own (see step 5).

---

## 1. Backend → Render

### Option A — the blueprint (fastest, uses `render.yaml`)

1. Render dashboard → **New +** → **Blueprint**.
2. Pick this repository → **Apply**.
   Render reads `render.yaml` and creates the `clear-price-api` service with the
   build command, start command, health check and environment variables already
   set.
3. Wait for the first deploy (2–3 minutes), then copy the service URL.

### Option B — by hand

1. **New +** → **Web Service** → connect this repository.
2. Fill in **exactly** these settings:

   | Field | Value |
   | ----- | ----- |
   | Name | `clear-price-api` |
   | Language / Runtime | Python 3 |
   | Root Directory | `backend` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
   | Health Check Path | `/health` |
   | Instance Type | Free |

3. Add environment variables (Render → your service → **Environment**):

   | Key | Value | Why |
   | --- | ----- | --- |
   | `PYTHON_VERSION` | `3.11.9` | Pins the interpreter |
   | `ALLOWED_ORIGINS` | `https://your-app.vercel.app` | CORS. Put a placeholder now, fix it in step 4 |
   | `TRUST_PROXY` | `1` | Render is behind a proxy; without this the rate limit counts the proxy, not shoppers. **Never set this where there is no proxy.** |
   | `RATE_LIMIT` | `60` | Calculations per minute per IP |
   | `MAX_BODY_BYTES` | `4096` | Request size cap |
   | `ALLOWED_HOSTS` | `clear-price-api.onrender.com` | Optional: rejects forged Host headers. Leave unset until you know the hostname |
   | `STATS_SECRET` | a 64-character random hex string | **Set this.** It pseudonymises device ids for the anonymous counts. Without it, counts reset on every restart |
   | `STATS_TOKEN` | a long random string | Your key to read the owner report at `/stats/summary`. Unset means the report does not exist |
   | `STATS_DB` | `stats.db` | Where counts are stored. `off` disables counting entirely |
   | `STATS_RETENTION_DAYS` | `400` | How long anonymous counts are kept |
   | `RATE_LIMIT_TRACK` | `30` | `/track` requests per minute per IP, separate from the calculator |

4. **Create Web Service** and wait for **Live**.

### Check it

Generate the two secrets first (see ANALYTICS.md for what they do):

```bash
python3 -c "import secrets; print('STATS_SECRET=' + secrets.token_hex(32)); print('STATS_TOKEN=' + secrets.token_urlsafe(32))"
```

```bash
curl https://clear-price-api.onrender.com/health
# {"status":"ok"}

curl -X POST https://clear-price-api.onrender.com/calculate \
  -H 'Content-Type: application/json' \
  -d '{"original_price":89,"discount1_pct":20,"discount2_pct":70}'
# {"original_price":89.0,"final_price":21.36,"amount_saved":67.64,"total_discount_pct":76.0}
```

> **Free-tier note:** the instance sleeps after ~15 minutes idle. The first
> request afterwards can take 30–60 seconds. The app shows *"Can't reach the
> server"* if it gives up — that is the free plan, not a bug. Options: accept it,
> ping `/health` from a free uptime monitor (e.g. UptimeRobot) every 10 minutes,
> or move to a paid instance ($7/month) for an always-on service.

---

## 2. Frontend → GitHub Pages (the install address)

Nothing to sign up for, no build output in git, and it deploys itself on every
push to `main`. The whole thing is `.github/workflows/pages.yml` plus four
clicks — the full walkthrough is in [SETUP_GITHUB.md](SETUP_GITHUB.md).

1. Repo → **Settings** → **Pages** → **Build and deployment → Source:**
   **GitHub Actions**.
2. Repo → **Actions** → **Deploy to GitHub Pages** → **Run workflow**.
3. Wait for the green tick, then open
   **https://jameroy21.github.io/clear-price/**.

What the workflow does: `npm ci`, `npm run build:pages`, which is

```bash
VITE_BASE=/clear-price/ \
VITE_CALC_MODE=local \
VITE_ANALYTICS=off \
VITE_SITE_URL=https://jameroy21.github.io/clear-price/ \
vite build
```

`VITE_BASE` makes every asset path relative so the site works from the
`/clear-price/` subpath; `VITE_CALC_MODE=local` makes the app answer with
on-device maths, because a static host has no Python. Before uploading, the
workflow fails the build if any path is root-absolute or any backend URL got
baked in — the two mistakes that produce a live 404. `tools/pages_check.sh`
runs the same test locally against a real static server.

## 3. Frontend → Vercel (optional, for the API-backed version)

1. Vercel dashboard → **Add New…** → **Project** → import this repository.
2. Configure:

   | Field | Value |
   | ----- | ----- |
   | Root Directory | `frontend` (**Edit** → select `frontend`) |
   | Framework Preset | Vite (auto-detected) |
   | Build Command | `npm run build` (default) |
   | Output Directory | `dist` (default) |
   | Install Command | `npm install` (default) |

3. **Environment Variables** (add to Production **and** Preview):

   ```
   VITE_API_BASE_URL = https://clear-price-api.onrender.com
   ```

   Optional but worth it while you are here:

   ```
   VITE_SITE_URL        = https://your-app.vercel.app   # used when sharing from the app
   VITE_ANALYTICS       = on                            # off = never count anything
   VITE_APP_VERSION     = 1.2.0                         # shown in the footer and sent with counts
   ```

   No trailing slash. Vite inlines this at build time, so changing it requires a
   redeploy — that is normal.

4. **Deploy**. Note the URL Vercel gives you, e.g.
   `https://clear-price.vercel.app`.

The repo already ships `frontend/vercel.json`, which configures the SPA routing
and all the security headers (HSTS, CSP carried in the HTML, `nosniff`,
`X-Frame-Options`, `Permissions-Policy`, cache policy).

---

## 4. Complete the loop — CORS

Go back to Render → **Environment** and set:

```
ALLOWED_ORIGINS = https://clear-price.vercel.app
```

Save; Render redeploys automatically. Then confirm from your own machine:

```bash
curl -i -X POST https://clear-price-api.onrender.com/calculate \
  -H 'Origin: https://clear-price.vercel.app' \
  -H 'Content-Type: application/json' \
  -d '{"original_price":89,"discount1_pct":20,"discount2_pct":70}' | grep -i access-control
# access-control-allow-origin: https://clear-price.vercel.app
```

If you use Vercel **preview** deployments as well, add those origins too
(comma-separated), or keep `*` while you are still evaluating — the API holds no
user data, so an open origin policy leaks nothing.

---

## 5. Smoke-test the live site

1. Open the Vercel URL on your phone.
2. Type `89`, `20`, `70` → tap **Show Final Price** → **$21.36**.
3. Turn on **airplane mode** and repeat → the same answer, with
   *"Offline — the same maths, done on your phone."*
4. Tap **Install app** (Android) or Share → Add to Home Screen (iPhone), then
   open it from the icon — it should run full-screen with no browser toolbar.
5. Install it (Android: **Install app**; iPhone: Share → Add to Home Screen) and
   confirm it opens full-screen with a brand splash, not a white flash.
6. Check your own numbers:

   ```bash
   curl -s https://clear-price-api.onrender.com/stats/summary \
     -H "Authorization: Bearer $STATS_TOKEN" | python3 -m json.tool
   ```

   A fresh deploy should read `installs_total: 0` — so install it once yourself
   and watch it become 1. If it stays at 0, `STATS_SECRET` is missing or the
   request never reached the API.
7. Check the headers: [securityheaders.com](https://securityheaders.com) should
   give A/A+, and an SSL Labs scan should give an A.

---

## 6. Custom domain (recommended, ~US$10–15/year)

1. Buy a short, memorable domain (see `LAUNCH.md` for naming advice) — e.g.
   `clearpriced.com`, `stackeddiscount.com`.
2. Add it to whichever host serves the app:
   - **GitHub Pages** → repo → **Settings** → **Pages** → **Custom domain**,
     then create a `CNAME` record at your registrar pointing at
     `jameroy21.github.io`. Tick **Enforce HTTPS** once the certificate is
     issued (minutes, sometimes an hour).
   - **Vercel** → project → **Settings** → **Domains** → add it and follow the
     DNS instructions (an `A`/`CNAME` record).
   - **Render** (API) → optional: front it with `api.clearpriced.com`.
3. **Rebuild for the new address.** The Pages build bakes its own path in
   (`VITE_BASE=/clear-price/`), so an address change is a config change, not a
   DNS-only move:

   ```jsonc
   // frontend/package.json -> scripts
   "build:pages": "VITE_BASE=/ VITE_CALC_MODE=local VITE_ANALYTICS=off \
                   VITE_SITE_URL=https://clearpriced.com vite build"
   ```

   With a custom domain the site is served from the root, so the base becomes
   `/`. If instead you keep the github.io address, change nothing.
4. Update the canonical and social URLs everywhere at once — `frontend/index.html`
   (canonical, `og:url`), `frontend/public/robots.txt`,
   `frontend/public/sitemap.xml`, `APP_README.md`, `SETUP_GITHUB.md` — then run
   `.venv/bin/python tools/check_urls.py`, which fails if any of them disagree
   or if an asset path stops being safe for a subpath. Commit and push.
5. Add the custom domain to Render's `ALLOWED_ORIGINS` (comma-separated with the
   Vercel URL), then update `VITE_API_BASE_URL` in Vercel and redeploy.
6. Set up the redirect so `www` and the apex both work (Vercel handles this by
   default once both are added; on Pages, redirect the `www` CNAME in DNS or
   with a Cloudflare rule).

---

## 7. Shipping updates after launch

The whole point of connecting the repo: `git push` is the deploy.

```bash
cd /path/to/repo
# backend change?
cd backend && pytest -q && cd ..
# frontend change?
cd frontend && npm run test:ui && cd ..      # needs the backend running
.venv/bin/python tools/check_parity.py       # only if you touched the maths
git add -A && git commit -m "..." && git push
```

- Render redeploys the backend on pushes to the connected branch.
- Vercel redeploys the frontend, and gives every pull request its own preview
  URL.
- Users' installed apps pick up the new version on their next visit; the service
  worker caches the app shell but always checks the network for the page itself,
  so no one gets stuck on an old build.

---

## 8. Cost summary

| Item | Free tier | When you would pay |
| ---- | --------- | ------------------ |
| GitHub Pages (the install address) | 100 GB bandwidth/month, free forever on public repos | Never, unless you outgrow it — and even then a CDN sits in front for free |
| Render web service (optional API) | Sleeps when idle | $7/month for always-on |
| Vercel hosting (optional API build) | 100 GB bandwidth/month | Rarely, at this size |
| Domain | — | ~$10–15/year, worth it |
| HTTPS | Included both hosts | — |
| Database | Not used | — |
| **Total to launch** | **$0** (or ~$12/year with a domain) | |

GitHub Pages is the part that costs nothing and needs no account: the app is
static files, and the calculation happens on the phone.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| "Can't reach the server" after a quiet period | Render free tier asleep | Wait ~30–60s and press again; add an uptime ping |
| CORS error in the console | `ALLOWED_ORIGINS` missing your exact origin (scheme, no trailing slash) | Copy the origin from the browser's address bar into Render's env var |
| Frontend still calls `localhost` | `VITE_API_BASE_URL` not set, or set after the build | Set it in Vercel, then **Redeploy** |
| Blank page on Vercel | Wrong Root Directory | Must be `frontend` |
| `422` for valid-looking input | Values outside 0–100, a negative price, or an extra field | `extra="forbid"` is on by design |
| `429 Too many requests` while testing | You are the script | Raise `RATE_LIMIT` temporarily or wait a minute |
| Installs always read 0 | `STATS_SECRET` unset (counts reset each restart), or `STATS_DB=off` | Set both, then redeploy — see ANALYTICS.md |
| `/stats/summary` returns 404 | No `STATS_TOKEN` configured (by design) | Set it, redeploy |
| Counts reset after a deploy | Free tier has an ephemeral disk | Attach a Render disk at `/var/data` and set `STATS_DB=/var/data/stats.db` |
| `413` on a normal request | Body over 4 KB | Only three numbers are needed; a proxy is inflating the request |
