"""ParkingBot entry point: check EFFIA, email on a newly-opened subscription spot.

Flow: fetch -> parse -> diff against saved state -> email lots that went 0->1
(sorted by preference) -> save the new state.

CLI:
    python -m parkingbot.main            # one check (default)
    python -m parkingbot.main --once     # explicit single check
    python -m parkingbot.main --dry-run  # check + log, but never send email/save
    python -m parkingbot.main --test-email   # send one test email and exit
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Dict, List

from dotenv import load_dotenv

from . import config, fetch, notify, state
from .parse import LotStatus, available_count, parse_lots

log = logging.getLogger("parkingbot")


def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


def compute_newly_open(
    lots: List[LotStatus], previous: Dict[str, bool]
) -> List[LotStatus]:
    """Lots that are available now but were NOT available last run (0->1).

    Returned sorted by preference (config.PREFERENCE_RANK), most-wanted first.
    A lot missing from ``previous`` is treated as previously False, so the very
    first run will alert on anything already open.
    """
    transitioned = [
        lot
        for lot in lots
        if lot.available and not previous.get(lot.code, False)
    ]
    transitioned.sort(key=lambda lot: config.PREFERENCE_RANK.get(lot.code, 99))
    return transitioned


def next_state(lots: List[LotStatus]) -> Dict[str, bool]:
    """The availability map to persist for next run."""
    return {lot.code: lot.available for lot in lots}


def run_once(dry_run: bool = False) -> int:
    """Perform a single check. Returns the number of lots newly opened."""
    html = fetch.fetch_search_html()
    lots = parse_lots(html)
    previous = state.load_state()

    summary = ", ".join(f"{lot.code}={'1' if lot.available else '0'}" for lot in lots)
    log.info("Parsed %d lots [%s]; %d available.",
             len(lots), summary, available_count(lots))

    newly_open = compute_newly_open(lots, previous)

    if newly_open:
        codes = ", ".join(lot.code for lot in newly_open)
        log.info("NEWLY OPEN (preference order): %s", codes)
        if dry_run:
            log.info("[dry-run] would email %s and save state; doing neither.", codes)
        else:
            notify.send(notify.build_opening_email(newly_open))
            log.info("Email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))
    else:
        log.info("No new openings. No email.")

    if not dry_run:
        state.save_state(next_state(lots))

    return len(newly_open)


def main() -> None:
    load_dotenv()
    _configure_logging()

    parser = argparse.ArgumentParser(description="EFFIA Valserhône spot watcher")
    parser.add_argument("--once", action="store_true",
                        help="run a single check (this is also the default)")
    parser.add_argument("--dry-run", action="store_true",
                        help="check and log, but never send email or write state")
    parser.add_argument("--test-email", action="store_true",
                        help="send one test email to verify SMTP setup, then exit")
    args = parser.parse_args()

    if args.test_email:
        notify.send(notify.build_test_email())
        log.info("Test email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))
        return

    run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
