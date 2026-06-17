"""Dead-man's-switch liveness ping: best-effort, never breaks a run."""

import parkingbot.main as main
from parkingbot import config


def test_ping_noop_when_url_unset(monkeypatch):
    monkeypatch.setattr(config, "HEALTHCHECK_URL", "")
    called = []
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: called.append(a))
    main.ping_liveness()
    assert called == []  # no URL -> no network call


def test_ping_gets_url_when_set(monkeypatch):
    monkeypatch.setattr(config, "HEALTHCHECK_URL", "https://hc-ping.com/abc")
    seen = {}
    monkeypatch.setattr(main.requests, "get",
                        lambda url, **k: seen.update(url=url, kw=k))
    main.ping_liveness()
    assert seen["url"] == "https://hc-ping.com/abc"
    assert "timeout" in seen["kw"]


def test_ping_swallows_errors(monkeypatch):
    monkeypatch.setattr(config, "HEALTHCHECK_URL", "https://hc-ping.com/abc")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(main.requests, "get", boom)
    main.ping_liveness()  # must not raise
