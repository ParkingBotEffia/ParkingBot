"""Parse the EFFIA search HTML into per-lot availability.

The page renders each lot as a single ``<li class="result-item">`` element that
carries everything we need as attributes on that one tag:

    <li class="result-item" data-available="0|1"
        data-link="https://www.effia.com/parking/...-p4-...?entry=...&...">

We therefore parse the DOM (not regex — the href and the flag sit far apart in
the markup) with BeautifulSoup, read ``data-available`` and identify the lot from
the ``data-link`` slug. ``data-available="1"`` is the real signal; it matches the
visible "X parking(s) disponible(s)" counter, which is just JS counting these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup

from . import config


@dataclass
class LotStatus:
    """Availability of one monitored lot."""

    code: str            # "P4", "P2", ...
    label: str           # human-friendly label from config
    available: bool      # True when a subscription spot is open
    url: str             # the lot's parking page (from data-link, query stripped)


def _lot_for_slug(slug_or_link: str, lots) -> Optional[tuple]:
    """Return the matching (code, slug, label) tuple for a data-link, or None."""
    for entry in lots:
        _code, slug_token, _label = entry
        if slug_token in slug_or_link:
            return entry
    return None


def parse_lots(html: str, lots=None) -> List[LotStatus]:
    """Extract subscription availability for every monitored lot in the page.

    ``lots`` is a list of (code, slug-token, label) tuples and defaults to
    ``config.LOTS`` (Bellegarde); the canary passes ``config.CANARY_LOTS``.

    IMPORTANT — EFFIA renders up to TWO ``<li class="result-item">`` cards per
    parking: a ``orderType=default`` (hourly) card, and — ONLY when a subscription
    spot is free — an extra ``orderType=subscription`` card with
    ``data-available="1"``. The subscription signal is therefore *a subscription
    card that is available*; the default card's ``data-available`` is about hourly
    parking and must NOT be treated as a subscription opening. We aggregate all
    cards matching a lot and mark it available iff one such subscription card is
    available. Returned in ``lots`` order; each lot at most once.
    """
    if lots is None:
        lots = config.LOTS
    soup = BeautifulSoup(html, "html.parser")

    # code -> {"available": bool, "url": str}
    found = {}
    for li in soup.select("li.result-item"):
        link = li.get("data-link", "") or ""
        entry = _lot_for_slug(link, lots)
        if entry is None:
            continue  # a parking we don't monitor
        code, _slug, _label = entry
        is_subscription = "orderType=subscription" in link
        available = (li.get("data-available", "0") or "0").strip() == "1"
        clean_url = link.split("?", 1)[0] if link else ""

        rec = found.setdefault(code, {"available": False, "url": ""})
        # Subscription availability = an available subscription card exists.
        if is_subscription and available:
            rec["available"] = True
        # Prefer the subscription card's URL; otherwise keep the first seen.
        if is_subscription or not rec["url"]:
            rec["url"] = clean_url

    results: List[LotStatus] = []
    for code, _slug, label in lots:
        if code in found:
            results.append(LotStatus(code=code, label=label,
                                     available=found[code]["available"],
                                     url=found[code]["url"]))
    return results


def available_count(lots: List[LotStatus]) -> int:
    """How many monitored lots are currently free (reproduces EFFIA's counter)."""
    return sum(1 for lot in lots if lot.available)
