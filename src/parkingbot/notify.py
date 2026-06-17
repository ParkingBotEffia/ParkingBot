"""Send the notification email via Gmail SMTP.

Credentials come from environment variables (set as GitHub Actions secrets):
    GMAIL_USER          sender address, e.g. your-sender@gmail.com
    GMAIL_APP_PASSWORD  16-char Google app password (NOT the account password)
    NOTIFY_TO           recipient, e.g. you@example.com

Gmail SMTP is used because Microsoft disabled basic-auth SMTP for personal
Outlook/Hotmail accounts, which makes them unusable from an unattended script.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import List

from .parse import LotStatus

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # implicit TLS (SMTPS)


class EmailConfigError(RuntimeError):
    """Raised when required email environment variables are missing."""


def _credentials() -> tuple:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("NOTIFY_TO")
    missing = [
        name
        for name, value in (
            ("GMAIL_USER", user),
            ("GMAIL_APP_PASSWORD", password),
            ("NOTIFY_TO", recipient),
        )
        if not value
    ]
    if missing:
        raise EmailConfigError("Missing env vars: " + ", ".join(missing))
    return user, password, recipient


def build_opening_email(newly_open: List[LotStatus]) -> EmailMessage:
    """Build the 'a spot opened' email. ``newly_open`` is pre-sorted by preference."""
    codes = ", ".join(lot.code for lot in newly_open)
    msg = EmailMessage()
    msg["Subject"] = f"🅿️ Place dispo EFFIA Valserhône : {codes}"

    lines = [
        "Une place d'abonnement vient de se libérer à la gare de "
        "Bellegarde-sur-Valserine (Valserhône).",
        "",
        "Parking(s) disponible(s), par ordre de préférence :",
    ]
    for lot in newly_open:
        lines.append(f"  • {lot.label}")
        if lot.url:
            lines.append(f"    {lot.url}")
    lines += [
        "",
        "Réserve vite — ces places partent en quelques minutes.",
        "",
        "— ParkingBot",
    ]
    msg.set_content("\n".join(lines))
    return msg


def build_health_alert_email(found: int, expected: int) -> EmailMessage:
    """Warn that ParkingBot may be broken (EFFIA HTML likely changed)."""
    msg = EmailMessage()
    msg["Subject"] = "⚠️ ParkingBot est peut-être cassé"
    msg.set_content(
        "ParkingBot n'a pas réussi à lire correctement la page EFFIA.\n\n"
        f"Parkings reconnus : {found} sur {expected} attendus.\n\n"
        "Cela arrive en général quand EFFIA modifie son site web. La surveillance ne "
        "fonctionne donc peut-être plus — il faut vérifier/réparer le parser.\n\n"
        "Tu ne recevras pas d'autre alerte de ce type tant que ce n'est pas résolu "
        "(et un message de confirmation quand ça refonctionnera).\n\n"
        "— ParkingBot"
    )
    return msg


def build_recovered_email() -> EmailMessage:
    """Confirm ParkingBot can read EFFIA again after a degraded period."""
    msg = EmailMessage()
    msg["Subject"] = "✅ ParkingBot refonctionne"
    msg.set_content(
        "Bonne nouvelle : ParkingBot relit de nouveau correctement la page EFFIA. "
        "La surveillance des places d'abonnement est réactivée.\n\n— ParkingBot"
    )
    return msg


def build_test_email() -> EmailMessage:
    """A simple message to confirm SMTP credentials/wiring work end to end."""
    msg = EmailMessage()
    msg["Subject"] = "✅ ParkingBot test email"
    msg.set_content(
        "If you can read this, ParkingBot's Gmail SMTP setup works. "
        "You'll get a real alert the moment a Valserhône subscription spot opens."
    )
    return msg


def send(msg: EmailMessage) -> None:
    """Send a prepared message via Gmail SMTP over implicit TLS."""
    user, password, recipient = _credentials()
    msg["From"] = user
    msg["To"] = recipient
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
