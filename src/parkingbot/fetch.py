"""Fetch the EFFIA search page HTML.

Deliberately tiny: one GET with a browser-like User-Agent. The availability
signal is in the server-rendered HTML, so there is no JavaScript to execute and
no headless browser to manage.

EFFIA's site occasionally returns 5xx for hours at a time. We retry a few times
to ride out brief blips, and raise ``EffiaUnavailable`` if it stays unreachable —
the caller treats that as "skip this cycle" (a clean exit) rather than a crash,
so a transient EFFIA outage doesn't spam GitHub "run failed" emails.
"""

from __future__ import annotations

import logging
import time

import requests

from . import config

log = logging.getLogger("parkingbot")

# Retry a handful of times on transient network/5xx errors before giving up.
FETCH_ATTEMPTS = 3
FETCH_BACKOFF = 2  # seconds between attempts


class EffiaUnavailable(RuntimeError):
    """EFFIA's site was unreachable (network error / 5xx) after retries.

    Signals a transient *external* outage, not a bug in our code — the caller
    skips the cycle and exits cleanly instead of failing the run.
    """


def fetch_search_html(url: str | None = None) -> str:
    """Return the raw HTML of the subscription search page.

    Retries transient failures; raises ``EffiaUnavailable`` if EFFIA stays
    unreachable after ``FETCH_ATTEMPTS`` tries.
    """
    url = url or config.SEARCH_URL
    last_exc = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.HTTP_TIMEOUT,
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("EFFIA fetch attempt %d/%d failed: %s",
                        attempt, FETCH_ATTEMPTS, exc)
            if attempt < FETCH_ATTEMPTS:
                time.sleep(FETCH_BACKOFF)
    raise EffiaUnavailable(f"EFFIA unreachable after {FETCH_ATTEMPTS} attempts: {last_exc}")
