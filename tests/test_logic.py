"""Transition + preference-ordering + email tests (no network, no SMTP)."""

from parkingbot.main import compute_newly_open, next_state
from parkingbot.notify import build_opening_email
from parkingbot.parse import LotStatus


def _lot(code, available):
    return LotStatus(code=code, label=f"{code} label", available=available,
                     url=f"https://www.effia.com/parking/x-{code.lower()}-effia")


def test_only_zero_to_one_transitions_notify():
    lots = [_lot("P4", True), _lot("P2", True), _lot("P3", False)]
    # P2 was already open last run -> not a new opening; P4 is newly open.
    previous = {"P4": False, "P2": True, "P3": False}
    newly = compute_newly_open(lots, previous)
    assert [lot.code for lot in newly] == ["P4"]


def test_no_state_first_run_alerts_on_open():
    lots = [_lot("P3", True)]
    assert [lot.code for lot in compute_newly_open(lots, {})] == ["P3"]


def test_preference_order_p4_p2_p3_p1():
    # All four open at once, deliberately out of order in the input.
    lots = [_lot("P1", True), _lot("P3", True), _lot("P2", True), _lot("P4", True)]
    newly = compute_newly_open(lots, {})
    assert [lot.code for lot in newly] == ["P4", "P2", "P3", "P1"]


def test_next_state_maps_all_lots():
    lots = [_lot("P4", True), _lot("P1", False)]
    assert next_state(lots) == {"P4": True, "P1": False}


def test_email_lists_lots_in_given_order():
    newly = [_lot("P4", True), _lot("P2", True)]
    msg = build_opening_email(newly)
    assert "P4" in msg["Subject"] and "P2" in msg["Subject"]
    body = msg.get_content()
    # P4 must appear before P2 in the body (preference order preserved).
    assert body.index("P4 label") < body.index("P2 label")
