"""ParkingBot entry point: check EFFIA, email on a newly-opened subscription spot.

Flow: fetch -> parse -> diff against saved state -> email lots that went 0->1
(sorted by preference) -> save the new state.

CLI:
    python -m parkingbot.main            # one check (default)
    python -m parkingbot.main --once     # explicit single check
    python -m parkingbot.main --loop     # check every 5 min for 28 min, then exit
                                         # (what CI runs — see run_loop)
    python -m parkingbot.main --dry-run  # check + log, but never send email/save
    python -m parkingbot.main --test-email   # send one test email and exit
    python -m parkingbot.main --self-test    # run the REAL alert path on a captured
                                             # "P4 available" page and email it (proves
                                             # detection -> opening email -> SMTP)
    python -m parkingbot.main --health-test  # send a real (marked) breakage-alarm email
    python -m parkingbot.main --canary       # weekly end-to-end self-check (Marseille)
    python -m parkingbot.main --test-sms     # send a test SMS via Free Mobile
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Dict, List

import requests
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


DEGRADED_KEY = "_degraded"  # state flag: are we currently failing to read EFFIA?
EFFIA_DOWN_KEY = "_effia_down"  # state flag: is EFFIA's site itself unreachable?


def run_once(dry_run: bool = False) -> int:
    """Perform a single check. Returns the number of lots newly opened.

    Health guard: if we recognise fewer than all expected lots, EFFIA has likely
    changed their HTML and detection may be silently broken. We email a one-off
    warning (deduped via the ``_degraded`` state flag) and a "recovered" note when
    reading works again — so a breakage pings Léo instead of failing silently.
    (A hard fetch/HTTP error instead raises, turning the CI run red — GitHub emails
    you about your own failed scheduled runs.)
    """
    html = fetch.fetch_search_html()
    lots = parse_lots(html)
    previous = state.load_state()
    was_degraded = previous.get(DEGRADED_KEY, False)

    expected = len(config.LOTS)
    if len(lots) < expected:
        log.warning("DEGRADED: recognised %d of %d lots — EFFIA structure may have "
                    "changed; detection may be broken.", len(lots), expected)
        if dry_run:
            log.info("[dry-run] would send a health alert; doing nothing.")
            return 0
        if not was_degraded:
            notify.send(notify.build_health_alert_email(len(lots), expected))
            log.info("Health-alert email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))
        else:
            log.info("Still degraded; alert already sent — staying silent.")
        # Preserve the previous per-lot memory; only flip the degraded flag.
        carried = dict(previous)
        carried[DEGRADED_KEY] = True
        state.save_state(carried)
        return 0

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
        if was_degraded:
            notify.send(notify.build_recovered_email())
            log.info("Recovered: reading EFFIA works again; recovery email sent.")
        new_state = next_state(lots)
        new_state[DEGRADED_KEY] = False
        # next_state() rebuilds the map from the parsed lots, so any non-lot flag
        # would be dropped here. _effia_down is owned by the loop, not by us.
        new_state[EFFIA_DOWN_KEY] = previous.get(EFFIA_DOWN_KEY, False)
        state.save_state(new_state)

    return len(newly_open)


def ping_liveness() -> None:
    """Best-effort dead-man's-switch ping after a successful run.

    GETs config.HEALTHCHECK_URL so healthchecks.io knows the watcher ran. If the
    URL is unset it no-ops; any network error is swallowed — the ping must NEVER
    affect the run's outcome. A *missing* ping (because the scheduler didn't fire,
    or the check itself crashed) is what triggers healthchecks.io's external alert.

    Note we DO ping when EFFIA is unreachable: the bot ran and behaved correctly,
    so staying silent would report *us* as dead for *their* outage. A sustained
    EFFIA outage is reported separately by the _effia_down alarm.
    """
    url = config.HEALTHCHECK_URL
    if not url:
        return
    try:
        requests.get(url, timeout=10)
        log.info("Liveness ping sent.")
    except Exception as exc:  # noqa: BLE001 - never let the ping break the run
        log.warning("Liveness ping failed (ignored): %s", exc)


def _flag_effia_down(consecutive: int, dry_run: bool = False) -> None:
    """Email once when EFFIA has been unreachable long enough to be a real outage.

    Deduped across runs via the ``_effia_down`` state flag, exactly like
    ``_degraded`` — a multi-hour EFFIA outage must cost one email, not one per
    check. Below the threshold we stay silent: short blips are already absorbed
    by fetch's retries and aren't worth a notification.
    """
    if dry_run or consecutive < config.EFFIA_DOWN_THRESHOLD:
        return
    current = state.load_state()
    if current.get(EFFIA_DOWN_KEY, False):
        return  # already reported; stay quiet until it recovers
    notify.send(notify.build_effia_down_email(consecutive))
    current[EFFIA_DOWN_KEY] = True
    state.save_state(current)
    log.info("EFFIA-outage email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))


def _clear_effia_down(dry_run: bool = False) -> None:
    """Confirm EFFIA is reachable again — but only if we said it wasn't."""
    if dry_run:
        return
    current = state.load_state()
    if not current.get(EFFIA_DOWN_KEY, False):
        return
    notify.send(notify.build_effia_recovered_email())
    current[EFFIA_DOWN_KEY] = False
    state.save_state(current)
    log.info("EFFIA reachable again; recovery email sent.")


def run_loop(duration: int, interval: int, dry_run: bool = False) -> None:
    """Check every ``interval`` seconds for ``duration`` seconds, then exit.

    Batching many checks into one long-lived CI run is what keeps GitHub from
    emailing about this bot: a run per check meant ~288 runner acquisitions a
    day, and when GitHub can't hand out a runner the run fails without executing
    a single step — nothing inside the workflow can catch that. Six checks per
    run cuts the exposure ~6x while keeping the 5-min detection cadence.

    Nothing here may raise. Ending the run early would leave us blind until the
    next dispatch, so a failing check is logged and skipped; it simply doesn't
    ping, and healthchecks.io raises the alarm if that persists.
    """
    started = time.monotonic()
    deadline = started + duration
    next_check = started
    consecutive_outages = 0
    checks = 0

    while True:
        checks += 1
        log.info("Check %d (t+%ds of %ds).", checks,
                 int(time.monotonic() - started), duration)

        pingable = True
        try:
            run_once(dry_run=dry_run)
        except fetch.EffiaUnavailable as exc:
            # Their site, not ours: still a healthy run (see ping_liveness).
            consecutive_outages += 1
            log.warning("EFFIA unreachable (%d in a row): %s", consecutive_outages, exc)
            _flag_effia_down(consecutive_outages, dry_run=dry_run)
        except Exception:  # noqa: BLE001 - one bad check must not end the run
            pingable = False
            log.exception("Check failed; skipping this check's ping and continuing.")
        else:
            consecutive_outages = 0
            _clear_effia_down(dry_run=dry_run)

        if pingable and not dry_run:
            ping_liveness()

        next_check += interval
        if next_check >= deadline:
            log.info("Loop done: %d checks in %ds; exiting before the next dispatch.",
                     checks, int(time.monotonic() - started))
            return
        time.sleep(max(0.0, next_check - time.monotonic()))


def run_canary() -> None:
    """Weekly end-to-end self-check against an always-available parking (Marseille).

    Runs the EXACT same code path as Bellegarde — fetch_search_html -> parse_lots ->
    available_count — only the URL and lot list differ. Sends a clearly-labelled
    "test système" email (never a false spot alert). Touches no state.
    """
    html = fetch.fetch_search_html(config.CANARY_URL)
    lots = parse_lots(html, config.CANARY_LOTS)
    n = available_count(lots)
    log.info("Canary: %s detected %d/%d configured lots available.",
             config.CANARY_STATION, n, len(config.CANARY_LOTS))
    notify.send(notify.build_systemtest_email(detected=n >= 1, station=config.CANARY_STATION, n=n))
    log.info("System-test email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))


def run_health_test() -> None:
    """Send a real (clearly-marked) health-alert email to prove the breakage alarm
    actually reaches your inbox. Does not touch state.json."""
    msg = notify.build_health_alert_email(0, len(config.LOTS))
    msg.replace_header("Subject", "[TEST] " + msg["Subject"])
    notify.send(msg)
    log.info("Health-test email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))


def run_self_test() -> None:
    """Exercise the full alert path against a captured 'P4 available' page.

    Loads the real test fixture, parses it, runs the same transition + email-build
    + send code production uses, and sends a real (clearly marked) email. This is
    the only way to prove detection -> opening email -> SMTP end to end without
    waiting for an actual spot to open. It does NOT touch state.json.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    fixture = os.path.join(
        repo_root, "tests", "fixtures", "valserhone_p4_available.html"
    )
    with open(fixture, encoding="utf-8") as fh:
        html = fh.read()

    lots = parse_lots(html)
    newly_open = compute_newly_open(lots, previous={})  # empty state -> all open count
    log.info("Self-test parsed %d lots; newly open: %s",
             len(lots), ", ".join(lot.code for lot in newly_open) or "none")
    if not newly_open:
        raise RuntimeError("Self-test fixture parsed no available lot — parser broken!")

    msg = notify.build_opening_email(newly_open)
    # Prefix the subject so you know this is a drill, not a real opening.
    # (EmailMessage forbids re-assigning a header, so replace it.)
    msg.replace_header("Subject", "[SELF-TEST] " + msg["Subject"])
    notify.send(msg)
    log.info("Self-test alert email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))


def main() -> None:
    load_dotenv()
    _configure_logging()

    parser = argparse.ArgumentParser(description="EFFIA Valserhône spot watcher")
    parser.add_argument("--once", action="store_true",
                        help="run a single check (this is also the default)")
    parser.add_argument("--loop", action="store_true",
                        help="keep checking every 5 min until --duration elapses, "
                             "then exit (what CI runs)")
    parser.add_argument("--duration", type=int, default=config.LOOP_DURATION,
                        help="seconds --loop keeps checking "
                             f"(default {config.LOOP_DURATION})")
    parser.add_argument("--dry-run", action="store_true",
                        help="check and log, but never send email or write state")
    parser.add_argument("--test-email", action="store_true",
                        help="send one test email to verify SMTP setup, then exit")
    parser.add_argument("--self-test", action="store_true",
                        help="run the full alert path on a captured 'available' page "
                             "and email it, then exit")
    parser.add_argument("--health-test", action="store_true",
                        help="send a real (marked) breakage-alarm email, then exit")
    parser.add_argument("--canary", action="store_true",
                        help="weekly end-to-end self-check against Marseille, then exit")
    parser.add_argument("--test-sms", action="store_true",
                        help="send a test SMS via Free Mobile to verify setup, then exit")
    args = parser.parse_args()

    if args.test_email:
        notify.send(notify.build_test_email())
        log.info("Test email sent to %s.", os.environ.get("NOTIFY_TO", "<unset>"))
        return

    if args.self_test:
        run_self_test()
        return

    if args.health_test:
        run_health_test()
        return

    if args.canary:
        try:
            run_canary()
        except fetch.EffiaUnavailable as exc:
            # EFFIA down at canary time — skip cleanly (no GitHub failure email).
            log.warning("Canary skipped: %s", exc)
        return

    if args.test_sms:
        notify.send_sms("ParkingBot — test SMS OK")
        log.info("Test SMS attempted (check your phone).")
        return

    if args.loop:
        run_loop(args.duration, config.LOOP_INTERVAL, dry_run=args.dry_run)
        return

    try:
        run_once(dry_run=args.dry_run)
    except fetch.EffiaUnavailable as exc:
        # Transient EFFIA outage: skip this cycle without failing the run. We still
        # ping below — the bot ran correctly, and starving healthchecks here would
        # report *us* as down for *their* outage. Any other error still raises.
        log.warning("Skipping cycle — EFFIA unreachable (their site): %s", exc)
    # Liveness ping only on a real (non-dry-run) check.
    if not args.dry_run:
        ping_liveness()


if __name__ == "__main__":
    main()
