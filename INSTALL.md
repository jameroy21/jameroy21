# Installing Clear Price (and putting it on your home screen)

Clear Price is a **website that installs like an app**. There is no App Store
download, no account, and nothing to pay. Installed, it opens full-screen from an
icon on your home screen, keeps working with no signal, and never asks for a
single permission.

Installed, it behaves like a proper app rather than a saved link: the icon has the
Clear Price name underneath it, the home screen and app switcher show the tag
logo, and launching it shows the brand rather than a white flash. Nothing about
the install is generic — that is the point of the manifest, the icon set and the
launch images in this repository.

The app shows its own **Install app** button when your browser allows it. If you
do not see it, the steps below always work.

---

## Steps for each device

### iPhone / iPad (Safari)

1. Open the site in **Safari** (Chrome on iOS cannot install apps).
2. Tap the **Share** button — the square with the arrow pointing up.
3. Scroll and tap **Add to Home Screen**.
4. Tap **Add**. The tag icon appears on your home screen.

### Android (Chrome, Edge, Samsung Internet, Firefox)

1. Open the site in your browser.
2. Tap **Install app** on the page, or open the **⋮** menu and choose
   **Install app** / **Add to Home screen**.
3. Confirm. Android may ask whether to add it to the home screen — say yes.
4. Long-press the icon afterwards for the **New calculation** shortcut.

### Desktop (Chrome, Edge, Brave)

1. Look for the **install** icon in the address bar (a small screen with a
   downward arrow), or open the **⋮** menu → **Install Clear Price…**
2. It opens in its own window, like a normal application.

### Desktop (Safari on macOS)

**File → Add to Dock**. That gives you an app icon in the Dock.

---

## Home screen widgets — what is actually possible

Honest answer first: **iOS and Android do not let a website create a home screen
widget.** A real widget needs native code. There is, however, a genuinely good
option on each platform, and one that takes about 30 seconds.

### iPhone: a one-tap widget via the Shortcuts app

This gives you a real widget tile that opens Clear Price, and lets you prefill a
price from your clipboard.

1. Open the **Shortcuts** app → **+** to make a new shortcut.
2. Add the action **Open URLs** and set the URL to your Clear Price address
   (e.g. `https://clear-price.vercel.app`).
3. Name it **Clear Price**, tap the icon to choose the tag logo.
4. Go to the home screen → long-press the background → **Edit** → **Add Widget**
   → choose **Shortcuts** → pick the size → **Add Widget**.
5. Long-press the new widget → **Edit Widget** → choose the **Clear Price**
   shortcut.

Now the tile opens the calculator in one tap — and because the app itself works
offline, it will answer even with no signal.

*Want it to prefill the price?* Add a **Get Clipboard** action before **Open
URLs** and use
`https://clear-price.vercel.app/?price=[Clipboard]` — the app reads a `price`
parameter on load. Set the shortcut as a **Lock Screen** widget too, and you can
tap it straight from the lock screen in a store.

### Android: the launcher shortcut, plus a real widget later

Android supports **long-press shortcuts** on a web app icon out of the box — the
manifest already ships one called **New calculation**, which jumps straight to
the price fields.

For a true home-screen widget on Android you need the app packaged (see below);
once it is a Trusted Web Activity, a small companion app or a
[Glance](https://developer.android.com/develop/ui/compose/glance) widget can be
added without touching the web code.

### Both platforms: lock screen / Quick Settings

- **iPhone:** Shortcuts can also be added to the **Lock Screen** (widget) and the
  **Action Button** on newer models.
- **Android:** add the site to a home screen folder or use
  **Chrome → Add to Home screen** for quick access; Quick Settings tiles require
  a packaged app.

---

## Publishing to the app stores (optional, later)

You do not need this to be useful, and you should not do it before people are
already using the web version. When you are ready, the same web code can be
wrapped:

### Google Play — Trusted Web Activity (recommended)

No new UI code; Play Store listing and reviews; keeps the same URL and updates.

```bash
npm install -g @bubblewrap/cli
bubblewrap init --manifest https://clear-price.vercel.app/manifest.webmanifest
bubblewrap build          # produces app-release-bundle.aab
# upload the .aab in the Play Console, then:
bubblewrap update         # to pick up future web changes
```

Requirements to know about: a Play Developer account (one-off US$25), a privacy
policy URL (already have one: `/privacy.html`), and the
[Digital Asset Links](https://developer.android.com/training/app-links/verify-android-applinks)
file so the installed app keeps the toolbar hidden. A TWA can also be a
foundation for a real Glance widget later.

### iOS App Store

Harder: you need a Mac, Xcode, an Apple Developer account (US$99/year), and a
native wrapper (Capacitor or a WKWebView shell). Apple also requires more than a
repackaged website — the widget and any offline extras would be what justify it.
Do this only if the web version has real usage.

---

## Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| No **Install app** button on iPhone | iOS never fires the install prompt; installing is manual | Share → Add to Home Screen |
| No button in Chrome | Site must be HTTPS, and the manifest must load | Check the padlock and that `/manifest.webmanifest` opens |
| Button appeared, then the app "isn't installed" | The prompt was dismissed twice | Clear site data for the site, or install from the ⋮ menu |
| "Offline — the same maths, done on your phone" | No signal; this is expected and correct | Nothing to do; the answer is identical to the server's |
| Stale version after a deploy | Service worker holding the old shell | Close all app windows and reopen; the new version installs on next visit |
| Opens to a white screen for a moment | Launch image missing for your device | Regenerate with `python tools/make_brand_assets.py`, then `python tools/check_splash.py` |
| Old prices visible on a shared phone | Browser never caches answers, but the page stays open | Reload — answers are cleared as soon as a field changes |
