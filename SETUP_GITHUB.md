# Setting up `clear-price` on GitHub — the exact steps

This is the delivery path for **Clear Price v1.2.0**: a new public repository
called `clear-price`, a release carrying the source zip, and GitHub Pages
serving the install address:

> **https://jameroy21.github.io/clear-price/**

Two of the steps can only be done by you, in the browser, because they are
account-level actions: **creating the repository** and **turning Pages on**.
Everything else is prepared and can be run for you.

---

## Step 1 — Create the repository (you, ~40 seconds)

1. Go to **https://github.com/new**
2. **Repository name:** `clear-price`
3. **Description:** `Clear Price — see what you really pay when discounts stack.`
4. **Public** (Pages is free on public repos; private repos need a paid plan)
5. **Do not** add a README, `.gitignore` or licence — the files arrive in the
   next step and an existing README would collide with them.
6. **Create repository**

## Step 2 — Give this agent access to the new repo (you, ~20 seconds)

The automation runs as a GitHub App installed on your account. It can currently
see `jameroy21/jameroy21` only, so the new repo needs to be added:

1. **https://github.com/settings/installations** → the **Arena** / agent app →
   **Configure**
2. Under **Repository access**, choose **All repositories** *or*
   **Only select repositories** → tick **`clear-price`**
3. **Save**

Without this, the push and the release are refused with a 403.

## Step 3 — Files, release and tag (me)

Once Steps 1–2 are done, this runs automatically:

```bash
# 1. the app itself, pushed straight into the new repo
git remote add clear-price https://github.com/jameroy21/clear-price.git
git push clear-price HEAD:main

# 2. that repo gets its own front page (this one's README is your GitHub
#    profile, which belongs on your profile repo, not in the app)
#    APP_README.md -> README.md, in a throwaway clone

# 3. a source zip, built from the exact commit that was tested
git archive --format=zip -o clear-price-v1.2.0.zip HEAD
shasum -a 256 clear-price-v1.2.0.zip > clear-price-v1.2.0.zip.sha256

# 4. the release, with the zip attached as a release asset
gh release create v1.2.0 \
  --repo jameroy21/clear-price \
  --target main \
  --title "Clear Price v1.2.0" \
  --notes-file .github/release-notes/v1.2.0.md \
  --latest \
  clear-price-v1.2.0.zip clear-price-v1.2.0.zip.sha256
```

The release notes are already written and committed at
`.github/release-notes/v1.2.0.md`, so the same text is in git next to the code
it describes.

That gives you **Releases → v1.2.0** with the zip downloadable from the same
page, plus a permanent archive GitHub generates for every tag.

## Step 4 — Turn Pages on (you, one dropdown)

The workflow `.github/workflows/pages.yml` is already in the repo. It builds the
site and publishes it on every push to `main`. All it needs is permission:

1. Repo → **Settings** → **Pages**
2. **Build and deployment → Source:** choose **GitHub Actions**
3. Repo → **Actions** tab → if prompted, **I understand my workflows, go ahead
   and enable them** (new repos ask once)
4. **Actions** → **Deploy to GitHub Pages** → **Run workflow** (or push any
   commit). It takes about a minute; the run prints the URL.
5. **Settings → Pages** now shows:
   **Your site is live at https://jameroy21.github.io/clear-price/**
6. Tick **Enforce HTTPS** if it is not already on.

### Why "GitHub Actions" and not "Deploy from a branch"

Your original note said *Settings → Pages → Deploy from a branch → `main` →
`/(root)`*. With that setting the address is identical, but the content is not:
this repository keeps **source** at the root (`backend/`, `frontend/`, `tools/`),
so a branch deploy would publish the source tree and the address would show a
file listing / 404 instead of the app. A branch deploy only works if the built
site is committed somewhere in the repo.

Two ways to get the exact URL either way — pick one and tell me:

| Option | What changes | Notes |
| --- | --- | --- |
| **A. GitHub Actions** *(already done)* | nothing | No build output in git. Pages rebuilds from source on every push. |
| **B. Commit the build to `/docs`** | a script copies `frontend/dist` to `docs/` before each release; Pages source becomes *Deploy from a branch → `main` → `/docs`* | Matches your branch-deploy wording exactly. Adds ~400 KB of generated files per release to git. |

Same address, same installed app, same behaviour. Option A is what a normal
project does; Option B commits the build output. Nothing else differs.

## Step 5 — Install it on your phone (you, ~20 seconds)

1. Open **https://jameroy21.github.io/clear-price/** on the phone.
2. **Android / Chrome:** menu **⋮** → **Install app** (or **Add to Home
   screen**). **iPhone / Safari:** **Share** → **Add to Home Screen**.
3. The icon that lands on the home screen is Clear Price's own green tag icon
   with the `%` — not a generic bookmark or "the default application".
4. Open it from the home screen: no browser bars, the splash screen matches your
   screen size, and the app calculates **on the phone** — flights, basements and
   dead zones included.

## What you get, and what is where

| Thing | Where |
| --- | --- |
| The app, installed | Home screen icon, opens full screen |
| The install address | https://jameroy21.github.io/clear-price/ |
| The source | https://github.com/jameroy21/clear-price |
| The signed-off version | Releases → `v1.2.0` → `clear-price-v1.2.0.zip` |
| Proof it works | Actions → green runs; `tools/pages_check.sh` locally |
| Your rights | `LICENSE`, `terms.html`, `privacy.html`, footer © 2026 Jame Roy |
| Counting installs | `GET /stats/summary` on the API host (see `ANALYTICS.md`) |

## About counting on the Pages build

The Pages site is static, so it cannot store counts itself — it ships with
counting switched **off** and every answer is worked out on the phone
(`VITE_CALC_MODE=local`). Nothing is sent anywhere from that build.
`privacy.html` says exactly that, so the promise on screen and the code agree.

If you want install counts on the Pages version, the API host from `DEPLOY.md`
(Render free tier) serves `POST /track` and `GET /stats/summary`; the Pages
build would then need `VITE_ANALYTICS_ENDPOINT` pointed at it. Say the word and
I will wire it — otherwise the Pages build stays fully offline, which is the
stronger privacy story.

## If something does not work

| Symptom | Cause | Fix |
| --- | --- | --- |
| Push refused, 403 | Step 2 not done | Add `clear-price` to the app's repository access |
| Pages shows the repo files or a 404 | Pages source set to *Deploy from a branch → root* | Switch to **GitHub Actions** (Step 4) |
| Address shows "404 File not found" | Wrong source, or the workflow has not run yet | Actions → **Deploy to GitHub Pages** → **Run workflow** |
| No **Install app** prompt on Android | Served over plain HTTP, manifest wrong, or already installed | Use the exact `https://` address; uninstall first if it is already there |
| iOS shows a white flash when opening | Launch image missing for that screen size | `python tools/check_splash.py` lists every size that must exist |
| Page loads unstyled, icons missing | A path began with `/` | `tools/check_urls.py` and `tools/pages_check.sh` catch this before deploy |
| Old version still shows after an update | Service worker cache | Close all tabs; the worker updates on the next load |
