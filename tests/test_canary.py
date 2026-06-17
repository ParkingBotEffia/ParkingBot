"""Canary / weekly system-test: same parse code, separate target."""

import os

from parkingbot import config, notify
from parkingbot.parse import available_count, parse_lots

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def test_canary_detects_marseille_availability():
    # The SAME parse_lots, pointed at Marseille lots, detects real availability.
    lots = parse_lots(_load("marseille_subscription.html"), config.CANARY_LOTS)
    assert available_count(lots) >= 1
    # All recognised lots belong to the canary config (no Bellegarde bleed-through).
    assert {lot.code for lot in lots} <= {c for c, _s, _l in config.CANARY_LOTS}


def test_bellegarde_parsing_unchanged_by_default_arg():
    # Calling parse_lots with no second arg must behave exactly as before:
    # the 4 Bellegarde lots, all currently unavailable.
    lots = parse_lots(_load("valserhone_all_unavailable.html"))
    assert {lot.code for lot in lots} == {"P1", "P2", "P3", "P4"}
    assert available_count(lots) == 0
    # And passing config.LOTS explicitly gives an identical result.
    explicit = parse_lots(_load("valserhone_all_unavailable.html"), config.LOTS)
    assert [(x.code, x.available) for x in lots] == [(y.code, y.available) for y in explicit]


def test_systemtest_email_ok_wording():
    msg = notify.build_systemtest_email(detected=True, station="Marseille", n=5)
    assert "test système OK" in msg["Subject"]
    body = msg.get_content()
    assert "Marseille" in body and "5 place" in body
    # Must never imply an actionable Bellegarde spot.
    assert "PAS une place à Bellegarde" in body


def test_systemtest_email_anomaly_wording():
    msg = notify.build_systemtest_email(detected=False, station="Marseille", n=0)
    assert "anomalie" in msg["Subject"]
    assert "AUCUNE place" in msg.get_content()
