# Knowing people use it — without a login

**The question:** "How do I know people are using the app? Some people log in
with email or phone number, but many won't hand that over for security reasons.
Can we avoid that?"

**The answer:** don't build a login. There is nothing to log in *to* — the app
has no accounts, no saved work, no payments. A login would add friction, a
password database to protect, and a privacy promise to break, in exchange for
data nobody needs.

Instead the app counts **how many devices** installed it and **how many opened it
on a given day**, using a random number that lives only on that phone. The owner
learns whether the app is being used and whether it is growing. The owner cannot
learn who anyone is. That is the whole design.

---

## What is counted

| Event | When it is sent | How often |
| ----- | --------------- | --------- |
| `install` | The app is opened while installed to the home screen, or the browser confirms an install | **Once per device, ever** |
| `open` | The app is opened | **Once per device, per day** |

Sent with each event:

```json
{ "device_id": "3f9c…", "kind": "open", "app_version": "1.2.0" }
```

That is the entire payload. `device_id` is a random UUID the app generates on
first use. `app_version` exists so the owner can see adoption after an update.

---

## What is never collected

- No email address. No phone number. No name. No login. No password.
- No cookies, no advertising ID, no fingerprinting, no canvas or font probing.
- No IP addresses stored — the rate limiter uses them in memory to stop abuse,
  and never writes them to the database.
- No prices, no discounts, no calculations. The maths endpoint and the counting
  endpoint are completely separate.
- No cross-site tracking, no third-party analytics, no ad networks. The browser
  app loads nothing from any domain other than your own.

## How the privacy is enforced, not just promised

1. **The identifier is replaced on arrival.** The server computes
   `HMAC-SHA256(STATS_SECRET, device_id)` and stores only that. Without the
   secret, the stored value cannot be turned back into a device id — and it is
   meaningless on any other service.
2. **There is nowhere to store a person.** The table is exactly three columns:

   ```sql
   CREATE TABLE events (
       day TEXT, device TEXT, kind TEXT,   -- date, HMAC, 'install'|'open'
       PRIMARY KEY (day, device, kind)
   );
   ```

   No column for an email, a name, an IP, a price or a user agent. A test asserts
   this schema, so it cannot drift.
3. **The client cannot send extra data.** `POST /track` uses
   `extra="forbid"`, so a request carrying `email` or `price` fields is rejected
   with 422 rather than quietly stored.
4. **Counts, never lists.** Everything is `COUNT(DISTINCT device)`. There is no
   endpoint that returns an individual, because no individual is stored.
5. **Retention is enforced.** Events older than `STATS_RETENTION_DAYS` (default
   400) are deleted. A test proves the deletion actually happens.
6. **Rotating the secret resets everything.** Change `STATS_SECRET` and the old
   hashes can never be linked to new ones. A test asserts this.

If the owner ever deletes the database, nothing of value is lost — which is the
point.

---

## The shopper is in control

| Control | How it works |
| ------- | ------------ |
| **In-app switch** | "Anonymous counts: On / Off" in the footer. Off stops it immediately and permanently (stored on the device). |
| **Do Not Track / Global Privacy Control** | Honoured automatically — if the browser asks not to be tracked, nothing is sent, ever. |
| **Clearing site data** | Forgets the device id. The next visit looks exactly like a brand-new user. |
| **Build-time kill switch** | `VITE_ANALYTICS=off` removes counting from the frontend entirely; `STATS_DB=off` disables it server-side. Either one alone is enough. |

---

## Where the counts live (and when they reset)

The counts are a single SQLite file (`STATS_DB`, default `backend/stats.db`).
Honest caveats about hosting:

| Host | Behaviour |
| ---- | --------- |
| **Render free tier** | The filesystem is **ephemeral**: counts survive a sleep/wake, but are lost on a redeploy or restart. For a launch, that is usually acceptable — you lose the running total, not the trend. |
| **Render paid instance + disk** | Attach a disk (Dashboard → your service → **Disks**, mount at `/var/data`) and set `STATS_DB=/var/data/stats.db`. Counts then survive deploys. |
| **Local development** | `backend/stats.db`, created on first run and ignored by git. Delete it to start a clean count. |
| **Anywhere** | `STATS_DB=off` disables counting entirely and writes nothing at all. |

Two more things that reset counts by design, both intentional:

- **`STATS_SECRET` missing** → a random secret is generated per start, so every
  existing hash stops matching. The API prints a warning at boot. Set it.
- **Rotating `STATS_SECRET`** → old hashes can never be linked to new ones. That
  is the privacy guarantee working as intended, and it is a one-line way to wipe
  the ability to correlate anything.

If you would rather never think about this, set `STATS_DB=off` and the app simply
does not count. It works identically, and the privacy page is even simpler.

## Reading the numbers (owner only)

Set `STATS_TOKEN` on the host to a long random string, then:

```bash
curl -s https://your-api-host/stats/summary \
  -H "Authorization: Bearer $STATS_TOKEN" | python3 -m json.tool
```

```json
{
  "installs_total": 128,
  "devices_total": 143,
  "active_today": 22,
  "active_7d": 61,
  "active_30d": 118,
  "returning_devices": 54,
  "retention_pct": 37.8,
  "first_day": "2026-09-25",
  "last_day": "2026-10-24",
  "trend": [
    { "day": "2026-10-24", "installs": 6, "devices": 22 }
  ],
  "generated_at": "2026-10-24",
  "note": "Anonymous counts of distinct devices. No identities, no prices, no IP addresses are stored, by design."
}
```

What the rows mean, in plain terms:

| Field | The question it answers |
| ----- | ----------------------- |
| `installs_total` | How many people put it on their phone? |
| `active_today` | Is anyone using it right now? |
| `active_7d` / `active_30d` | Is usage growing or fading? |
| `returning_devices` | Did people come back after the first try? |
| `retention_pct` | Roughly what fraction came back on another day? |
| `trend` | The last 14 days, day by day — the shape of growth |

**Safety of the endpoint itself:** without a valid `Authorization: Bearer` token
it returns 401, and with no `STATS_TOKEN` configured at all it returns 404 —
so a deploy that forgets the variable exposes nothing. The comparison is
constant-time, and the response is sent with `Cache-Control: no-store`.

Because the report is authenticated by a bearer token, **serve it over HTTPS
only** (Render does by default) and treat the token like a password. Rotate it by
changing the environment variable; nothing else needs to change.

---

## Making the numbers useful

- **Before launch:** `installs_total` should be 0. Clear the database
  (`rm backend/stats.db` locally, or reset the Render disk) so early testing
  does not inflate your launch numbers.
- **Week 1 target:** 25 installs from friends and family — and look at
  `retention_pct`, not just the total. Anyone who installs it and never returns
  tells you the app was not useful *that day*.
- **Watch `trend` after any post.** A spike that decays within a day is a
  novelty. A plateau that holds is a product.
- **Pair it with the funnel you can see on the host:** Render and Vercel both
  report request counts and response times. If `installs` grows while the error
  rate grows too, something is broken for specific phones.

---

## Configuration reference

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `STATS_DB` | `stats.db` | SQLite file for counts. `off`, `none` or `disabled` turns counting off entirely and writes nothing. |
| `STATS_SECRET` | *(generated)* | HMAC secret for pseudonymising device ids. **Set this in production**, otherwise counts reset on every restart. A startup warning is printed when it is missing. |
| `STATS_TOKEN` | *(unset)* | Bearer token for `/stats/summary`. Unset means the report does not exist (404). |
| `STATS_RETENTION_DAYS` | `400` | How long anonymous counts are kept before deletion. |
| `RATE_LIMIT_TRACK` | `30` | `/track` requests per window per IP, in its own bucket so counting can never block a calculation. |
| `VITE_ANALYTICS` | *(auto)* | `off` disables counting in the frontend build. Any other value (or unset) enables it when an endpoint exists. |
| `VITE_ANALYTICS_ENDPOINT` | *(unset)* | Override the counting endpoint. Defaults to `VITE_API_BASE_URL`. With neither set, the frontend never sends anything. |

Generate a secret and a token:

```bash
python3 -c "import secrets; print('STATS_SECRET=' + secrets.token_hex(32)); print('STATS_TOKEN=' + secrets.token_urlsafe(32))"
```

---

## Adding more insight later, if you ever need it

The current numbers answer "how many, and do they come back". If you want to know
*which screens people struggle with*, the same privacy rules apply:

- **Anonymous, bucketed events only** — e.g. "validation error shown" or
  "second discount field used", never the values.
- **No session recording tools.** FullSession/Hotjar-style replay products
  capture everything a user types, which is exactly the guarantee this app makes
  and must keep.
- **Keep the switch working.** Any new counter must respect the same footer
  toggle, Do Not Track, and the retention rule.

If a future feature genuinely needs identity — saved calculations, price
history, a retailer account — that is the moment to add optional accounts, and to
update the privacy notice and the terms at the same time. Until then, no login is
the right login.
