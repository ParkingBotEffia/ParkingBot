"""Static configuration for the EFFIA Valserhône subscription watcher.

Everything that might need tweaking later (the lots, their preference order, the
search URL, file locations) lives here so the rest of the code stays generic.
"""

from __future__ import annotations

import os

# --- The lots we monitor -----------------------------------------------------
# EFFIA identifies each lot by the slug in its parking URL. We detect a lot by
# the "-pN-effia" token in that slug, which is stable regardless of the card's
# position in the page. Order here is also our NOTIFICATION PREFERENCE order
# (P4 first, P1 last): when several lots open at once, the email lists them in
# this order so the most-wanted spot is on top.
#
# Each entry: (lot code, slug token used to recognise it, human label).
LOTS = [
    ("P4", "-p4-effia", "P4 — parking gare P4"),
    ("P2", "-p2-effia", "P2 — parking gare P2"),
    ("P3", "-p3-effia", "P3 — parking gare P3"),
    ("P1", "-p1-effia", "P1 — arrêt minute"),
]

# Preference rank: lower number = higher priority. Built from LOTS order above.
PREFERENCE_RANK = {code: i for i, (code, _slug, _label) in enumerate(LOTS)}

# --- The signal page ---------------------------------------------------------
# The search page in SUBSCRIPTION mode. As long as no subscription spot is free
# it server-renders all 4 lots as <li class="result-item"> with data-available="0".
# When a spot opens, that lot's card flips to data-available="1". No date param
# is passed: EFFIA evaluates the nearest bookable month by default, which is
# exactly what we want ("first slot available, nearest preferred").
SEARCH_URL = os.environ.get(
    "EFFIA_SEARCH_URL",
    "https://www.effia.com/search"
    "?lat=46.1076&lng=5.82618&q=valserh%C3%B4ne&orderType=subscription",
)

# A real browser User-Agent — the plain default urllib/requests UA can be blocked.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

HTTP_TIMEOUT = 30  # seconds

# --- SMS (free, Free Mobile) -------------------------------------------------
# Free Mobile's built-in "Notifications par SMS" API sends a free SMS to the
# subscriber's OWN number. Every notification email is mirrored to SMS (text =
# the email subject) when these are set; unset => SMS is a no-op (safe).
#   user = Free Mobile identifiant, pass = generated API key (Mes Options).
FREE_SMS_USER = os.environ.get("FREE_SMS_USER", "")
FREE_SMS_PASS = os.environ.get("FREE_SMS_PASS", "")
FREE_SMS_URL = "https://smsapi.free-mobile.fr/sendmsg"

# --- Liveness / dead-man's-switch -------------------------------------------
# Optional healthchecks.io (or compatible) ping URL. The watcher GETs this URL
# after every check; if healthchecks.io receives no ping within its period+grace
# (period 5 min + grace 3 h) it emails Léo that the bot stopped running. This is
# the ONLY way to detect "the scheduler isn't firing" — the bot can't email that
# itself. Unset => ping is a no-op (safe before setup).
#
# The 3 h grace is deliberate: GitHub-hosted-runner capacity incidents routinely
# stall dispatches for 1-2 h (2026-08-06 saw gaps of 110, 80 and 65 min), and a
# tighter grace turns every one of those into a false "ParkingBot is DOWN" alert.
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")

# --- Batched runs (--loop) ---------------------------------------------------
# One GitHub Actions run per check meant ~288 runner acquisitions a day, and
# every one is a chance for GitHub to fail to hand us a runner — which fails the
# run and emails Léo, without a single step ever executing. So a run now stays
# alive and checks repeatedly: same 5-min cadence, ~6x fewer acquisitions.
#
# LOOP_DURATION must stay comfortably under the external dispatch interval
# (30 min) so a run always exits before its successor is dispatched and the
# `concurrency` group in watch.yml never has to queue.
LOOP_INTERVAL = 300    # seconds between checks within a run (5 min)
LOOP_DURATION = 1680   # seconds a single run keeps checking (28 min)

# How many consecutive unreachable-EFFIA checks before we conclude it's a real
# outage worth emailing about, rather than a blip the retries already absorb.
# 12 x 5 min = 1 h.
EFFIA_DOWN_THRESHOLD = 12

# --- Canary / weekly system-test --------------------------------------------
# A parking that reliably HAS subscription availability, used once a week to
# prove the whole chain (fetch -> parse -> detect -> email) still works without
# sending false "spot available" alerts. Marseille currently shows 5 free lots.
# The canary runs the SAME fetch/parse/detect code as Bellegarde, only the URL
# and lot list differ — so a passing Marseille test proves Bellegarde detection
# works too. "Detected" = at least one of these lots is available, so it won't
# false-alarm unless they all fill simultaneously (very unlikely).
CANARY_STATION = "Marseille"
CANARY_URL = os.environ.get(
    "EFFIA_CANARY_URL",
    "https://www.effia.com/search"
    "?lat=43.3026&lng=5.36907&q=marseille&orderType=subscription",
)
CANARY_LOTS = [
    ("GAMBETTA", "-gambetta-effia", "Marseille Gambetta"),
    ("CORDERIE", "-corderie-effia", "Marseille Corderie"),
    ("ST-CHARLES-P3", "-marseille-saint-charles-p3-effia", "Marseille Saint-Charles P3"),
    ("COURS-JULIEN", "-cours-julien-effia", "Marseille Cours Julien"),
    ("BARET", "-baret-effia", "Marseille Baret"),
]

# --- State file --------------------------------------------------------------
# Tiny JSON remembering each lot's last-seen availability, so we email only on a
# 0->1 transition and never re-spam while a spot stays open. In CI this file is
# committed back to the repo between runs to persist state across scheduled runs.
STATE_PATH = os.environ.get(
    "PARKINGBOT_STATE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "state.json"),
)
