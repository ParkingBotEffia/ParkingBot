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
