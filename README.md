# ParkingBot — EFFIA Valserhône subscription watcher

Emails you the moment a **subscription** parking spot opens in one of the 4 EFFIA
lots at the Bellegarde-sur-Valserine (Valserhône) train station. Monitoring +
email only (no automatic subscription). Runs unattended on GitHub Actions every
~5 minutes — your computer does not need to be on.

Preference order when several lots open at once: **P4 > P2 > P3 > P1**.

## How it works

The EFFIA search page renders each lot as `<li class="result-item">` cards. The
**subscription** signal is specific: EFFIA shows a `orderType=default` (hourly) card
always, and adds a SECOND `orderType=subscription` card with `data-available="1"` ONLY
when a subscription spot is free. So `parse.py` marks a lot available iff an
*`orderType=subscription`* card is available — the default card's `data-available` is
about hourly parking and is ignored. We GET that page, parse with BeautifulSoup, and email
only when a lot flips `0 → 1` (no spam while open; re-notifies on close→reopen). Last-seen
state is kept in `state.json`, committed back between scheduled runs.

```
src/parkingbot/
  config.py   lots, preference order, search URL, state path
  fetch.py    one HTTP GET with a browser User-Agent
  parse.py    HTML -> [LotStatus(code, label, available, url)]
  state.py    load/save state.json
  notify.py   Gmail SMTP email (opening alert + test email)
  main.py     fetch -> parse -> diff -> email -> save
```

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # fill in GMAIL_* and NOTIFY_TO
```

## Run

```bash
PYTHONPATH=src python -m parkingbot.main --dry-run     # check + log, no email/state
PYTHONPATH=src python -m parkingbot.main --once        # real check
PYTHONPATH=src python -m parkingbot.main --test-email  # verify SMTP wiring
```

## Test & lint

```bash
pytest          # parser tested against real captured EFFIA HTML
ruff check .
```

## Deployment (GitHub Actions)

`.github/workflows/watch.yml` runs `--once` and commits `state.json` back. Required repo
secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NOTIFY_TO`, `HEALTHCHECK_URL`.
Use the **Run workflow** button (with *test_email* checked) to send a test email.

### Trigger

GitHub's built-in `schedule:` cron proved unreliable for this repo (it ran 0 times in
hours). The **real trigger is external**: a free [cron-job.org](https://cron-job.org) job
calls the GitHub API every 5 minutes to dispatch `watch.yml`:

```
POST https://api.github.com/repos/ParkingBotEffia/ParkingBot/actions/workflows/watch.yml/dispatches
Authorization: Bearer <fine-grained PAT, this repo, Actions: read/write>
Accept: application/vnd.github+json
Body: {"ref":"main"}
```

The `schedule:` block is kept as a harmless backup (the `concurrency` group prevents
overlap). If the external trigger ever stops, the dead-man's-switch (above) emails you.

## SMS (free, Free Mobile)

Every notification email is **also sent as an SMS** to the owner's phone via Free Mobile's
free notification API — centralised in `notify.send()` (SMS text = the email subject), so
the spot alert, breakage alarm, recovered notice, weekly canary, and tests all buzz the
phone. Secrets `FREE_SMS_USER` / `FREE_SMS_PASS`; best-effort (never breaks the email/run)
and no-ops if unset. Verify with **Run workflow → test_sms**. The "bot is down"
dead-man's-switch (sent by healthchecks.io, not the bot) can also SMS by adding a Free
Mobile webhook URL as a healthchecks integration.

## Liveness (dead-man's-switch)

A bot that stops running can't email you — and GitHub only emails on *failed* runs, never
*missing* ones. So on every successful run the watcher pings an external
[healthchecks.io](https://healthchecks.io) check (`HEALTHCHECK_URL` secret, best-effort —
never breaks a run). If healthchecks.io gets no ping within ~45 min (period 5 min + grace
40 min), **it** emails you that ParkingBot is down. Being external, it catches even a total
GitHub-scheduler outage. Unset secret ⇒ the ping no-ops.

## Weekly system-test (canary)

`.github/workflows/canary.yml` runs every **Sunday 18:00 UTC** (and on demand). It runs
the **same** detection code against Marseille (which reliably has spots) and emails
**"✅ ParkingBot — test système OK"** when detection fires — proving the whole chain works
end-to-end, without any false "spot available" alert. If Marseille ever shows 0, it emails
a **"test système : anomalie"** instead. Fully separate from `watch.yml`: own workflow, own
config (`CANARY_*` in `config.py`), writes no state. Because it exercises the identical
`fetch`/`parse_lots`/`available_count` path, a passing test proves Bellegarde works too.

## Self-monitoring (breakage alarm)

If EFFIA changes their HTML and fewer than the 4 expected lots are recognised, the bot
emails a one-off **"⚠️ ParkingBot est peut-être cassé"** warning (deduped via a
`_degraded` flag in `state.json`) and a **"✅ refonctionne"** note when reading works
again. A hard fetch/HTTP error instead fails the CI run (GitHub emails you about failed
scheduled runs). Verify delivery anytime with **Run workflow → health_test**.

## Entry month — why we only watch the nearest month

Investigated and settled: EFFIA subscription availability is **capacity-based, not
month-specific**. A lot either has a free subscription slot or not; you pick your start
month at checkout. The server only renders that yes/no for the nearest month, and the
`entry=` URL param does **not** make it recompute for another month (per-month UI is
JavaScript-only). So a "free for a later month but not now" state does not meaningfully
exist — a freed slot appears immediately on the page we already watch. Watching later
months would need a headless browser and would find nothing extra, so we don't.
