# 🏷️ Clear Price

**Two discounts, one honest answer.** A shopper-facing calculator that shows what
you really pay when discounts stack.

**[▶ Open the app →](https://jameroy21.github.io/clear-price/)**

[![CI](https://github.com/jameroy21/clear-price/actions/workflows/ci.yml/badge.svg)](https://github.com/jameroy21/clear-price/actions/workflows/ci.yml)
[![Pages](https://github.com/jameroy21/clear-price/actions/workflows/pages.yml/badge.svg)](https://jameroy21.github.io/clear-price/)
[![Release](https://img.shields.io/github/v/release/jameroy21/clear-price?label=release)](https://github.com/jameroy21/clear-price/releases)
[![Licence: proprietary](https://img.shields.io/badge/licence-proprietary-red)](LICENSE)

---

## The problem it solves

A shelf says **20% off**. A sign says **take another 70% off**. Shops apply the
second discount to the *already-reduced* price, so you do not get 90% off — you
get **76% off**:

| Step | Amount |
| --- | --- |
| Price on the tag | **$89.00** |
| − 20% | $71.20 |
| − 70% | **$21.36** |
| You saved | **$67.64** (76%) |

Everything else you find adds the two percentages together and is wrong by
$12.46 on this one. Clear Price gets this right, on a big-type screen you can
read while holding a phone in one hand in a shop.

## Install it on your phone

Open **https://jameroy21.github.io/clear-price/** and add it to your home screen:

- **iPhone / Safari** — **Share** → **Add to Home Screen**
- **Android / Chrome** — menu **⋮** → **Install app** (or **Add to Home screen**)

It installs as its own app: name, green tag icon, and a launch screen sized to
your phone — not a browser bookmark. After the first visit it **works with no
signal**, and it answers on the phone itself, so nothing is sent anywhere.

## What it does

- Two discounts, applied sequentially the way shops actually do it, using
  half-even rounding (the same rule the server uses — verified on 8,001 cases).
- Shows the final price, the amount saved and the true total percentage off.
- 18 px minimum text, a 32 px result, a decimal keypad on phones, high contrast,
  full keyboard and screen-reader support, and a dark-mode theme.
- Works offline; installs to the home screen; shares a link with one tap.
- No accounts, no email, no phone number, no cookies on the Pages build.

## Run it locally

```bash
# API
cd backend
python -m venv ../.venv && ../.venv/bin/pip install -r requirements-dev.txt
../.venv/bin/python -m uvicorn main:app --reload --port 8000

# App
cd frontend
npm install
npm run dev            # http://localhost:5173
```

`POST /calculate` `{original_price, discount1_pct, discount2_pct?}` →
`{original_price, final_price, amount_saved, total_discount_pct}`.
Validation is strict (`extra="forbid"`, price > 0, percentages 0–100) and every
response carries the security header set. The frontend talks to that API when it
is reachable and falls back to identical on-device maths when it is not.

## Checks

```bash
cd backend && ../.venv/bin/python -m pytest -q   # 67 backend tests
cd frontend && npm run test:ui                    # UI, offline and install checks
.venv/bin/python tools/check_parity.py            # 8,001 server-vs-device cases
.venv/bin/python tools/check_versions.py          # every version string agrees
.venv/bin/python tools/check_urls.py              # no bad absolute paths
.venv/bin/python tools/check_splash.py            # every iOS launch image exists
tools/pages_check.sh                              # the Pages build, as served
```

All of these run in CI on every push (`.github/workflows/ci.yml`).

## Documentation

| Document | For |
| --- | --- |
| [SETUP_GITHUB.md](SETUP_GITHUB.md) | Repository, release and Pages setup, click by click |
| [INSTALL.md](INSTALL.md) | Installing and adding to the home screen, on both phones |
| [DEPLOY.md](DEPLOY.md) | Hosting: GitHub Pages, Render, Vercel, custom domains |
| [LAUNCH.md](LAUNCH.md) | Getting it to people: launch order, SEO, growth |
| [SECURITY.md](SECURITY.md) | Threat model, hardening, reporting a problem |
| [ANALYTICS.md](ANALYTICS.md) | Counting installs without logins or personal data |
| [RELEASING.md](RELEASING.md) | How a version is cut, verified and published |
| [CHANGELOG.md](CHANGELOG.md) | What changed, release by release |
| [CLEAR_PRICE.md](CLEAR_PRICE.md) | The product one-pager: scope and decisions |

## Ownership

© 2026 **Jame Roy**. All rights reserved.

The idea, the name, the design and the code are proprietary — see
[LICENSE](LICENSE), and [terms.html](frontend/public/terms.html) /
[privacy.html](frontend/public/privacy.html) for what users are told in the app
itself.

---

<sub>Built with FastAPI, React and Vite. No database, no accounts: the API holds
one calculator and an anonymous, opted-out-by-default install counter.</sub>
