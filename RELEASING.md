# Releasing Clear Price

Repeatable, in about five minutes. The rules that matter:

1. **The version is one string.** It lives in eight files — the checker enforces
   that they agree, because drift is silent and a release with two version
   numbers is worse than no release.
2. **Never tag a red build.** `tools/check_versions.py` and the test suites run in
   CI (`.github/workflows/ci.yml`) on every push and pull request.
3. **The changelog entry comes first.** The release notes are written from it, so
   the tag describes work that was already documented.
4. **A tag points at a commit, not at a branch.** Releases are cut from the commit
   that passed. If that commit later lands on `main`, the tag stays valid.

---

## 1. Decide the version

[Semantic Versioning](https://semver.org/), for a user-facing app:

| Change | Bump | Example |
| ------ | ---- | ------- |
| New feature people will notice (currency selector, share-as-image) | **minor** | 1.2.0 → 1.3.0 |
| Fix only (a wrong cent, a broken install) | **patch** | 1.2.0 → 1.2.1 |
| Breaking change (renamed endpoint, new required setting) | **major** | 1.2.0 → 2.0.0 |

Anything that changes a price calculation is at least a **minor** release, even if
it is one line: it is the one thing this app must get right.

## 2. Write the changelog entry

Add to the top of [CHANGELOG.md](CHANGELOG.md), under a `## [x.y.z] — <date>`
heading, using the shape already there:

- **Added** — what is new
- **Changed** — what behaves differently
- **Fixed** — what was broken, and how it was noticed
- **Security notes** — anything a careful reader would want to know
- **Verification** — a table of the checks that passed, with numbers

Write it for the person installing the app, not for the author. "Installs as its
own branded app (name, icon, iOS launch screens)" beats "updated manifest".

## 3. Bump the version everywhere

Run the checker to see every source, then update them together:

```bash
.venv/bin/python tools/check_versions.py     # lists all eight sources
```

| File | What to change |
| ---- | -------------- |
| `frontend/package.json` | `"version"` |
| `frontend/package-lock.json` | root `"version"` **and** `packages[""].version` (or run `npm install` in `frontend/` to sync it) |
| `backend/main.py` | `APP_VERSION` |
| `frontend/index.html` | `"softwareVersion"` in the JSON-LD |
| `frontend/src/analytics.js` | the `VITE_APP_VERSION \|\| "x.y.z"` fallback |
| `CHANGELOG.md` | the new `## [x.y.z]` heading |
| `SECURITY.md` | `**Version:**` |
| `frontend/public/privacy.html` | `Last updated: … · vx.y.z` |

If you changed anything users will see, also bump `?v=` on the social image in
`frontend/index.html` — WhatsApp and Facebook cache previews hard.

## 4. Run everything locally

```bash
cd backend  && pytest -q                       # maths, hardening, privacy
cd frontend && npm run test:ui                 # 80 checks (start the API first)
.venv/bin/python tools/check_parity.py         # server maths == device maths
.venv/bin/python tools/check_versions.py       # all sources agree
.venv/bin/python tools/check_urls.py           # every URL on the canonical host
.venv/bin/python tools/check_splash.py         # every iOS launch image exists
tools/pages_check.sh                           # the GitHub Pages build works
cd frontend && npm run build                   # production build is clean
```

Then confirm the built app by hand — the things tests cannot judge:

```bash
cd frontend && npm run preview -- --host 0.0.0.0 --port 4173
```

- Type 89 / 20 / 70 → **$21.36**, "You saved $67.64", "76% off $89.00".
- Install it on a real phone from that URL, open it from the icon, check the
  branded launch screen and that airplane mode still gives $21.36.

## 5. Commit, push, tag

```bash
git add -A
git commit -m "Release v1.2.0"          # or a descriptive title + the notes
git push
```

## 6. Cut the GitHub release

Releases are cut in **`jameroy21/clear-price`** — the repository the install
address is served from — not in the development mirror.

```bash
# the zip that becomes the release asset, taken from the tested commit
git archive --format=zip -o /tmp/clear-price-v1.2.0.zip HEAD
shasum -a 256 /tmp/clear-price-v1.2.0.zip > /tmp/clear-price-v1.2.0.zip.sha256

gh release create v1.2.0 \
  --repo jameroy21/clear-price \
  --target "$(git rev-parse HEAD)" \
  --title "Clear Price v1.2.0 — <short promise>" \
  --notes-file .github/release-notes/v1.2.0.md \
  --latest \
  /tmp/clear-price-v1.2.0.zip /tmp/clear-price-v1.2.0.zip.sha256
```

**Always pass `--target`.** Without it, `gh` creates the tag from the repository's
default branch, which may not contain the code you just tested — the release would
point at the wrong commit.

**Always attach the zip.** It is the copy people can keep, and it is the only
artefact that still exists if the host ever disappears. The `.sha256` beside it
lets anyone check the file survived the download intact. GitHub's own
`Source code (zip)` links are generated, not attached — both should be present.

Release notes live in `.github/release-notes/<version>.md`, so the exact text
that shipped is reviewable in git next to the code it describes.

Good release notes answer four things:

1. **What is this?** One sentence, plus the worked example (it is the whole pitch).
2. **How do I get it?** The two install lines — iPhone: Share → Add to Home
   Screen; Android: Install app.
3. **What changed?** The changelog highlights, not the commit log.
4. **How do I know it works, and what should I be wary of?** The verification
   table plus the honest limitations (free-tier sleep, ephemeral usage counts).

End with the licence line: © 2026 Jame Roy, all rights reserved.

## 7. Afterwards

- [ ] Check the release renders: `gh release view v1.2.0 --json tagName,targetCommitish,isLatest,url`
- [ ] Confirm the tag points at the commit you tested:
      `git rev-parse v1.2.0` should equal `git rev-parse HEAD` at tag time.
- [ ] Confirm the install address is live and is serving the new build:
      `tools/pages_check.sh` locally, then
      <https://jameroy21.github.io/clear-price/> on a phone. Pages deploys from
      `main` on push (`.github/workflows/pages.yml`), so a release normally
      needs nothing extra; run the workflow by hand if a run was skipped.
- [ ] Confirm the release has its asset:
      `gh release view v1.2.0 --repo jameroy21/clear-price --json tagName,assets`
- [ ] Installed apps pick up the new version on the next visit; the service worker
      checks the network for the page itself, so nobody is stuck on an old build.
- [ ] If the release revealed a problem, do not delete the tag — publish a patch
      release. The tag is the record of what shipped.

---

## Rolling a release back

You cannot un-ship a tag people may have fetched, and deleting it breaks anyone
who pinned it. Instead:

1. Fix the problem on the branch.
2. Cut a patch release (`v1.2.1`) with the fix at the top of the notes.
3. If the broken build is still live on a host, redeploy the previous commit there
   immediately — the releases list stays untouched, so the history remains honest.

## Where the version is visible to users

| Surface | What they see |
| ------- | ------------- |
| App footer | `© 2026 Jame Roy. All rights reserved. v1.2.0` |
| `GET /` | `version`, `owner`, `copyright`, `license` |
| `/docs` | API version and licence in the header |
| Anonymous counts | `app_version` travels with each event, so update adoption is visible |
| Installed app | Version shown in the footer; the icon title is the manifest `short_name` |
