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
PYTHONPATH=src python -m parkingbot.main --loop        # what CI runs: check every
                                                       # 5 min for 28 min, then exit
PYTHONPATH=src python -m parkingbot.main --test-email  # verify SMTP wiring
```

## Test & lint

```bash
pytest          # parser tested against real captured EFFIA HTML
ruff check .
```

## Deployment (GitHub Actions)

`.github/workflows/watch.yml` runs `--loop --duration 1680` and commits `state.json` back.
Required repo secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NOTIFY_TO`, `HEALTHCHECK_URL`.
Use the **Run workflow** button (with *test_email* checked) to send a test email.

### Trigger

GitHub's built-in `schedule:` cron proved unreliable for this repo (it ran 0 times in
hours). The **real trigger is external**: a free [cron-job.org](https://cron-job.org) job
calls the GitHub API **every 30 minutes** to dispatch `watch.yml`:

```
POST https://api.github.com/repos/ParkingBotEffia/ParkingBot/actions/workflows/watch.yml/dispatches
Authorization: Bearer <fine-grained PAT, this repo, Actions: read/write>
Accept: application/vnd.github+json
Body: {"ref":"main"}
```

Each run then checks **every 5 minutes for 28 minutes** and exits (`--loop`), so detection
stays on a 5-min cadence while GitHub is asked for a runner only ~48 times a day instead
of 288. That ratio is the point: on 2026-08-06 a GitHub hosted-runner capacity incident
could not assign runners for ~6 h, and because every check was its own run it produced
**24 "Run failed" emails in a day** — from jobs that never executed a single step, so
nothing inside the workflow could have caught them. Fewer, longer runs shrink that
exposure ~6x; the rest is handled by turning off Actions email (see below).

There is deliberately **no `schedule:` block** any more: it was a second trigger firing
into the same `concurrency` group as cron-job.org, so during that incident its runs piled
up and were cancelled or failed. cron-job.org is the single trigger; if it ever stops, the
dead-man's-switch below emails you.

### Notifications

GitHub Actions failure emails are **turned off** for the ParkingBotEffia account
(Settings → Notifications → Actions → Email unchecked; Web left on). They cannot be
suppressed from inside a workflow — a run that fails because no runner was available
never executes a step, so `continue-on-error`/`timeout-minutes` don't apply. Nothing is
lost: healthchecks.io catches a dead bot and the breakage alarm catches a broken parser,
which between them cover every real failure. **healthchecks.io is now the only alerting
channel**, so `--loop` deliberately never dies on an exception — it just stops pinging.

## SMS (free, Free Mobile)

Every notification email is **also sent as an SMS** to the owner's phone via Free Mobile's
free notification API — centralised in `notify.send()` (SMS text = the email subject), so
the spot alert, breakage alarm, recovered notice, weekly canary, and tests all buzz the
phone. Secrets `FREE_SMS_USER` / `FREE_SMS_PASS`; best-effort (never breaks the email/run)
and no-ops if unset. Verify with **Run workflow → test_sms**. The "bot is down"
dead-man's-switch (sent by healthchecks.io, not the bot) can also SMS by adding a Free
Mobile webhook URL as a healthchecks integration.

## Liveness (dead-man's-switch)

A bot that stops running can't email you — and GitHub never emails about *missing* runs.
So after **every check** the watcher pings an external
[healthchecks.io](https://healthchecks.io) check (`HEALTHCHECK_URL` secret, best-effort —
never breaks a run). If healthchecks.io gets no ping within ~3 h (period 5 min + grace
3 h), **it** emails you that ParkingBot is down. Being external, it catches even a total
GitHub outage. Unset secret ⇒ the ping no-ops.

The 3 h grace is deliberate. It was 40 min, and GitHub runner-capacity incidents routinely
stall dispatches for longer than that — 2026-08-06 saw gaps of 110, 80 and 65 min, each of
which fired a false "ParkingBot is DOWN" email *and* SMS for a bot that was perfectly
healthy. 3 h absorbs those while still reporting a genuinely dead bot the same morning.

Two things deliberately do **not** withhold the ping, because neither means ParkingBot is
broken: **EFFIA being unreachable** (their outage, not ours — reported separately, below)
and any single failed check inside a `--loop` run (logged and skipped). What does stop the
pings is the bot being genuinely dead or wedged — which is exactly what this detects.

## Weekly system-test (canary)

`.github/workflows/canary.yml` runs every **Sunday 18:00 UTC** (and on demand). It runs
the **same** detection code against Marseille (which reliably has spots) and emails
**"✅ ParkingBot — test système OK"** when detection fires — proving the whole chain works
end-to-end, without any false "spot available" alert. If Marseille ever shows 0, it emails
a **"test système : anomalie"** instead. Fully separate from `watch.yml`: own workflow, own
config (`CANARY_*` in `config.py`), writes no state. Because it exercises the identical
`fetch`/`parse_lots`/`available_count` path, a passing test proves Bellegarde works too.

## Self-monitoring (breakage alarm)

Two distinct failures, two distinct alarms — both one-off, both deduped by a flag in
`state.json`, both with a matching "recovered" note:

| What broke | Symptom | Email | Flag |
|---|---|---|---|
| **We can't read EFFIA** — they changed their HTML, our parser is stale | page loads, fewer than the 4 expected lots recognised | ⚠️ ParkingBot est peut-être cassé | `_degraded` |
| **EFFIA is down** — their site, nothing to fix here | page doesn't load at all, for 12 checks in a row (~1 h) | ⚠️ Site EFFIA injoignable | `_effia_down` |

A short EFFIA blip is absorbed silently by `fetch.py`'s retries and never emails. Neither
case fails the CI run, and neither withholds the healthchecks ping — the bot is running
correctly in both. Verify delivery anytime with **Run workflow → health_test**.

## Entry month — why we only watch the nearest month

Investigated and settled: EFFIA subscription availability is **capacity-based, not
month-specific**. A lot either has a free subscription slot or not; you pick your start
month at checkout. The server only renders that yes/no for the nearest month, and the
`entry=` URL param does **not** make it recompute for another month (per-month UI is
JavaScript-only). So a "free for a later month but not now" state does not meaningfully
exist — a freed slot appears immediately on the page we already watch. Watching later
months would need a headless browser and would find nothing extra, so we don't.
