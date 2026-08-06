"""Batched --loop runs: cadence, crash tolerance, and the EFFIA-outage alarm.

The loop is what keeps GitHub quiet (one runner acquisition per ~6 checks), so
the properties that matter most here are "it always exits before the next
dispatch" and "nothing can end it early".
"""

import os

import pytest

import parkingbot.main as main
from parkingbot import config, fetch, state

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class _Clock:
    """Virtual clock: sleep() advances time instead of blocking the test."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(main, "time", c)
    return c


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Point state at tmp and make emails/pings observable instead of real."""
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    sent, pinged = [], []
    monkeypatch.setattr(main.notify, "send", lambda msg: sent.append(msg["Subject"]))
    monkeypatch.setattr(main, "ping_liveness", lambda: pinged.append(1))
    return sent, pinged


def _outage(*a, **k):
    raise fetch.EffiaUnavailable("EFFIA down")


def test_loop_runs_expected_checks_and_exits_before_duration(clock, isolated, monkeypatch):
    # 28 min / 5 min = 6 checks, and the loop must stop rather than start a 7th
    # that would overrun into the next dispatch.
    calls = []
    monkeypatch.setattr(main, "run_once", lambda dry_run=False: calls.append(1))
    main.run_loop(duration=1680, interval=300)
    assert len(calls) == 6
    assert clock.now == 1500  # exited with time to spare before 1680


def test_loop_pings_once_per_check(clock, isolated, monkeypatch):
    _, pinged = isolated
    monkeypatch.setattr(main, "run_once", lambda dry_run=False: None)
    main.run_loop(duration=1680, interval=300)
    assert pinged == [1] * 6


def test_crash_does_not_end_the_loop_and_skips_only_that_ping(clock, isolated, monkeypatch):
    # A single bad check (SMTP down, parser crash) used to end the process and
    # fail the run. Now it costs exactly one ping and the loop carries on.
    _, pinged = isolated
    calls = {"n": 0}

    def flaky(dry_run=False):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")

    monkeypatch.setattr(main, "run_once", flaky)
    main.run_loop(duration=1680, interval=300)
    assert calls["n"] == 6        # loop survived the crash
    assert len(pinged) == 5       # every check but the broken one pinged


def test_effia_outage_still_pings(clock, isolated, monkeypatch):
    # EFFIA being down is not ParkingBot being down.
    _, pinged = isolated
    monkeypatch.setattr(main, "run_once", _outage)
    main.run_loop(duration=1680, interval=300)
    assert len(pinged) == 6


def test_effia_outage_emails_once_at_threshold(clock, isolated, monkeypatch):
    sent, _ = isolated
    monkeypatch.setattr(config, "EFFIA_DOWN_THRESHOLD", 3)
    monkeypatch.setattr(main, "run_once", _outage)
    main.run_loop(duration=1680, interval=300)
    # Threshold hit on check 3; checks 4-6 must stay silent.
    assert sent == ["⚠️ Site EFFIA injoignable"]
    assert state.load_state()[main.EFFIA_DOWN_KEY] is True


def test_effia_outage_stays_silent_below_threshold(clock, isolated, monkeypatch):
    sent, _ = isolated
    monkeypatch.setattr(config, "EFFIA_DOWN_THRESHOLD", 12)
    monkeypatch.setattr(main, "run_once", _outage)
    main.run_loop(duration=1680, interval=300)
    assert sent == []  # 6 outages < 12: absorbed silently


def test_effia_recovery_emails_once(clock, isolated, monkeypatch):
    sent, _ = isolated
    state.save_state({"P1": False, main.EFFIA_DOWN_KEY: True})
    monkeypatch.setattr(main, "run_once", lambda dry_run=False: None)
    main.run_loop(duration=1680, interval=300)
    assert sent == ["✅ Site EFFIA de nouveau accessible"]
    assert state.load_state()[main.EFFIA_DOWN_KEY] is False


def test_run_once_preserves_effia_down_flag(monkeypatch, tmp_path):
    # next_state() rebuilds the map from parsed lots, so without an explicit
    # carry-over the flag would vanish and the recovery email would never fire.
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(main.notify, "send", lambda msg: None)
    good = open(os.path.join(FIXTURES, "valserhone_all_unavailable.html"),
                encoding="utf-8").read()
    monkeypatch.setattr(fetch, "fetch_search_html", lambda *a, **k: good)
    state.save_state({main.EFFIA_DOWN_KEY: True})
    main.run_once()
    assert state.load_state()[main.EFFIA_DOWN_KEY] is True


def test_dry_run_never_pings_or_emails(clock, isolated, monkeypatch):
    sent, pinged = isolated
    monkeypatch.setattr(config, "EFFIA_DOWN_THRESHOLD", 1)
    monkeypatch.setattr(main, "run_once", _outage)
    main.run_loop(duration=1680, interval=300, dry_run=True)
    assert pinged == []
    assert sent == []
