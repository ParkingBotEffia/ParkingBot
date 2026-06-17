"""Parser-health alert: degraded <-> healthy transitions (no network, no SMTP)."""

import os

import parkingbot.main as main
from parkingbot import config, fetch, notify, state

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
GOOD = open(os.path.join(FIXTURES, "valserhone_all_unavailable.html"), encoding="utf-8").read()
BAD = "<html><body>EFFIA redesigned the page — no result-item here.</body></html>"


def _wire(monkeypatch, tmp_path):
    """Point state at a temp file and capture sent-email subjects."""
    statefile = str(tmp_path / "state.json")
    monkeypatch.setattr(config, "STATE_PATH", statefile)
    sent = []
    monkeypatch.setattr(notify, "send", lambda msg: sent.append(msg["Subject"]))
    return statefile, sent


def _set_html(monkeypatch, html):
    monkeypatch.setattr(fetch, "fetch_search_html", lambda *a, **k: html)


def test_degraded_then_recovered_cycle(tmp_path, monkeypatch):
    statefile, sent = _wire(monkeypatch, tmp_path)

    # 1) Healthy run: no email; state saved healthy.
    _set_html(monkeypatch, GOOD)
    main.run_once()
    assert sent == []
    assert state.load_state(statefile).get("_degraded") is False
    assert state.load_state(statefile).get("P4") is False

    # 2) EFFIA "changes" -> degraded: exactly one health-alert email.
    _set_html(monkeypatch, BAD)
    main.run_once()
    assert len(sent) == 1 and "cassé" in sent[0]
    st = state.load_state(statefile)
    assert st.get("_degraded") is True
    assert st.get("P4") is False  # previous lot memory preserved, not clobbered

    # 3) Still broken: deduped, no new email.
    main.run_once()
    assert len(sent) == 1

    # 4) Fixed: recovery email sent, flag cleared.
    _set_html(monkeypatch, GOOD)
    main.run_once()
    assert len(sent) == 2 and "refonctionne" in sent[1]
    assert state.load_state(statefile).get("_degraded") is False


def test_health_email_builders():
    assert "cassé" in notify.build_health_alert_email(0, 4)["Subject"]
    assert "3 sur 4" in notify.build_health_alert_email(3, 4).get_content()
    assert "refonctionne" in notify.build_recovered_email()["Subject"]


def test_compute_newly_open_ignores_degraded_key():
    from parkingbot.main import compute_newly_open
    from parkingbot.parse import LotStatus
    lots = [LotStatus("P4", "P4", True, "u")]
    # A stray _degraded key in previous state must not break transition logic.
    assert [x.code for x in compute_newly_open(lots, {"_degraded": True})] == ["P4"]
