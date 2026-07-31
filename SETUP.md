# Running the watcher for free on GitHub Actions (cloud, no computer needed)

This folder is a self-contained repo you push to GitHub. Once set up, GitHub
runs the stock check on a schedule for you — your computer can be off.

## Free vs. private — read this first

GitHub Actions is unlimited/free on a **public** repo. On a **private**
repo you only get 2,000 free minutes/month — a check every 5 minutes
(~288 runs/day, each ~1-2 min) would burn through that in a few days and
start costing money. Nothing sensitive lives in this repo (the email
password is a GitHub *secret*, never committed to a file), so a **public
repo is the free, simple choice**. If you'd rather keep it private,
either accept the cost past the free minutes, or widen the schedule (e.g.
every 30 min) in `.github/workflows/zara-watch.yml`.

## 1. Create a GitHub account (skip if you have one)

https://github.com/join — free.

## 2. Create a new repository

On github.com click **New repository**. Name it e.g. `zara-watcher`,
set it to **Public**, don't initialize with a README (we already have
files). Create it.

## 3. Push this folder to the repo

Open a terminal in this `cloud` folder and run (replace the URL with the
one GitHub shows you after creating the repo):

```
git init
git add .
git commit -m "Zara RO stock watcher"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/zara-watcher.git
git push -u origin main
```

You'll be prompted to sign in to GitHub the first time (a browser window
opens — this is GitHub's own login, not something to type credentials
into a script).

## 4. Add your email credentials as repo secrets

In your new repo on github.com: **Settings → Secrets and variables →
Actions → New repository secret**. Add three secrets:

| Name | Value |
|---|---|
| `SENDER_EMAIL` | the Gmail address that sends the alert |
| `SENDER_APP_PASSWORD` | a Gmail App Password (see below) |
| `RECIPIENT_EMAIL` | tudor.vsl99@gmail.com (or wherever you want alerts) |

To get a Gmail App Password: https://myaccount.google.com/apppasswords
(requires 2-Step Verification turned on first, at
https://myaccount.google.com/security).

Secrets are encrypted by GitHub and never shown in logs or visible to
repo visitors, even on a public repo.

## 5. Turn on Actions and test it

Go to the **Actions** tab in your repo. If prompted, click "I understand,
enable Actions". Click into the **Zara RO Stock Watch** workflow, click
**Run workflow** to trigger it manually right away, and check the run's
log to confirm it found your products and (if applicable) sent an email.

After that, it runs automatically every 5 minutes on its own — no
computer, no terminal, nothing left open.

## 6. Editing your watched products later

Edit `config.json` in the repo (on github.com, or locally + `git push`)
to add/remove products or change sizes — same format as the local
version:

```json
{
    "products": [
        { "name": "...", "url": "https://www.zara.com/ro/ro/....html", "sizes": ["M"] }
    ]
}
```

## Limitations

- **Timing is best-effort, not exact.** GitHub can delay scheduled runs
  by several minutes during high platform load, especially for the
  `*/5` (every 5 min) cadence. This is materially slower than the local
  script's 30-60 second polling — pick the local script instead if
  catching a restock within seconds matters most to you.
- If Zara changes its page layout, the size-detection selectors in
  `checker_once.py` may need updating (same caveat as the local version).
- Each run spins up a fresh headless Chrome, so it can't "remember"
  anything except what's saved in `state.json` between runs.
