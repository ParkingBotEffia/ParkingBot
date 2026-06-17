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


def _lot_for_slug(slug_or_link: str) -> Optional[tuple]:
    """Return the matching (code, slug, label) tuple for a data-link, or None."""
    for entry in config.LOTS:
        _code, slug_token, _label = entry
        if slug_token in slug_or_link:
            return entry
    return None


def parse_lots(html: str) -> List[LotStatus]:
    """Extract availability for every monitored lot found in the page.

    Only lots listed in ``config.LOTS`` are returned (the search page may also
    contain unrelated nearby parkings). Each is returned once; order follows the
    page's DOM order — callers sort by preference when it matters.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: List[LotStatus] = []
    seen = set()

    for li in soup.select("li.result-item"):
        link = li.get("data-link", "") or ""
        entry = _lot_for_slug(link)
        if entry is None:
            continue  # a parking we don't monitor
        code, _slug, label = entry
        if code in seen:
            continue  # guard against accidental duplicates
        seen.add(code)

        available = (li.get("data-available", "0") or "0").strip() == "1"
        # Strip the query string so the URL is a clean, shareable parking page.
        clean_url = link.split("?", 1)[0] if link else ""
        results.append(
            LotStatus(code=code, label=label, available=available, url=clean_url)
        )

    return results


def available_count(lots: List[LotStatus]) -> int:
    """How many monitored lots are currently free (reproduces EFFIA's counter)."""
    return sum(1 for lot in lots if lot.available)
