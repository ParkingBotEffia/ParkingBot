# ParkingBot — EFFIA Valserhône subscription watcher

Emails you the moment a **subscription** parking spot opens in one of the 4 EFFIA
lots at the Bellegarde-sur-Valserine (Valserhône) train station. Monitoring +
email only (no automatic subscription). Runs unattended on GitHub Actions every
~5 minutes — your computer does not need to be on.

Preference order when several lots open at once: **P4 > P2 > P3 > P1**.

## How it works

The EFFIA search page in subscription mode server-renders each lot as
`<li class="result-item" data-available="0|1" data-link=".../parking/...-p4-...">`.
`data-available="1"` means a spot is free. We GET that page, parse the four cards
with BeautifulSoup, and email only when a lot flips `0 → 1` (so no spam while it
stays open; re-notifies if it closes then reopens). Last-seen state is kept in
`state.json`, committed back to the repo between scheduled runs.

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

`.github/workflows/watch.yml` runs `--once` on `cron: */5` and commits `state.json`
back. Required repo secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NOTIFY_TO`.
Use the **Run workflow** button (with *test_email* checked) to send a test email.

## Entry month

v1 watches EFFIA's nearest bookable month (the default search URL). The `data-link`
exposes `entry=`/`exit=` params, so sweeping additional months is a future option.
