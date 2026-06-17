"""Free Mobile SMS: best-effort, mirrors every email, never breaks the run."""

from email.message import EmailMessage

from parkingbot import config, notify


def test_sms_noop_when_creds_unset(monkeypatch):
    monkeypatch.setattr(config, "FREE_SMS_USER", "")
    monkeypatch.setattr(config, "FREE_SMS_PASS", "")
    called = []
    monkeypatch.setattr(notify.requests, "get", lambda *a, **k: called.append(a))
    notify.send_sms("hello")
    assert called == []  # not configured -> no network call


def test_sms_calls_free_mobile_api_when_set(monkeypatch):
    monkeypatch.setattr(config, "FREE_SMS_USER", "12345678")
    monkeypatch.setattr(config, "FREE_SMS_PASS", "secretkey")
    seen = {}

    class _Resp:
        status_code = 200

    def fake_get(url, **kw):
        seen["url"] = url
        seen["params"] = kw.get("params")
        return _Resp()

    monkeypatch.setattr(notify.requests, "get", fake_get)
    notify.send_sms("🅿️ Place dispo : P4")
    assert seen["url"] == "https://smsapi.free-mobile.fr/sendmsg"
    assert seen["params"]["user"] == "12345678"
    assert seen["params"]["pass"] == "secretkey"
    assert seen["params"]["msg"] == "🅿️ Place dispo : P4"


def test_sms_caps_length_to_160(monkeypatch):
    monkeypatch.setattr(config, "FREE_SMS_USER", "u")
    monkeypatch.setattr(config, "FREE_SMS_PASS", "p")
    seen = {}

    class _Resp:
        status_code = 200

    monkeypatch.setattr(notify.requests, "get",
                        lambda url, **kw: seen.update(kw["params"]) or _Resp())
    notify.send_sms("x" * 500)
    assert len(seen["msg"]) == 160


def test_sms_never_raises_on_error(monkeypatch):
    monkeypatch.setattr(config, "FREE_SMS_USER", "u")
    monkeypatch.setattr(config, "FREE_SMS_PASS", "p")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify.requests, "get", boom)
    notify.send_sms("hi")  # must not raise

    # And a non-200 (e.g. 403 bad creds) must also be swallowed.
    class _Resp:
        status_code = 403
    monkeypatch.setattr(notify.requests, "get", lambda *a, **k: _Resp())
    notify.send_sms("hi")


def test_send_mirrors_subject_to_sms(monkeypatch):
    # send() must SMS the email's subject after a successful SMTP send.
    monkeypatch.setattr(notify, "_credentials", lambda: ("u", "p", "to@x"))

    class _SMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def send_message(self, *a): pass

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", _SMTP)
    sms = []
    monkeypatch.setattr(notify, "send_sms", lambda text: sms.append(text))

    msg = EmailMessage()
    msg["Subject"] = "⚠️ ParkingBot est peut-être cassé"
    msg.set_content("body")
    notify.send(msg)
    assert sms == ["⚠️ ParkingBot est peut-être cassé"]
