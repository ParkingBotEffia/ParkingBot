"""Fetch retries + graceful EFFIA-outage handling (no crash, no ping)."""

import os
import sys

import pytest
import requests

import parkingbot.main as main
from parkingbot import config, fetch

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class _Resp:
    def __init__(self, status=200, text="OK"):
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")


def test_fetch_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("transient")
        return _Resp(200, "<html>ok</html>")

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda *_: None)
    assert fetch.fetch_search_html("http://x") == "<html>ok</html>"
    assert calls["n"] == 3  # failed twice, succeeded on the third


def test_fetch_raises_effia_unavailable_after_all_attempts(monkeypatch):
    monkeypatch.setattr(fetch.requests, "get", lambda url, **kw: _Resp(503, "busy"))
    monkeypatch.setattr(fetch.time, "sleep", lambda *_: None)
    with pytest.raises(fetch.EffiaUnavailable):
        fetch.fetch_search_html("http://x")


def _raise_unavailable(*a, **k):
    raise fetch.EffiaUnavailable("EFFIA down")


def test_main_skips_cleanly_and_does_not_ping_on_outage(monkeypatch, tmp_path):
    # An EFFIA outage must NOT crash main() (so GitHub sends no failure email)
    # and must NOT ping (so healthchecks reports a single down/up).
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(sys, "argv", ["parkingbot", "--once"])
    monkeypatch.setattr(fetch, "fetch_search_html", _raise_unavailable)
    pinged = []
    monkeypatch.setattr(main, "ping_liveness", lambda: pinged.append(1))
    main.main()  # must return normally (exit 0)
    assert pinged == []


def test_main_pings_on_healthy_run(monkeypatch, tmp_path):
    good = open(os.path.join(FIXTURES, "valserhone_all_unavailable.html"),
                encoding="utf-8").read()
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(sys, "argv", ["parkingbot", "--once"])
    monkeypatch.setattr(fetch, "fetch_search_html", lambda *a, **k: good)
    pinged = []
    monkeypatch.setattr(main, "ping_liveness", lambda: pinged.append(1))
    main.main()
    assert pinged == [1]  # healthy run still pings
