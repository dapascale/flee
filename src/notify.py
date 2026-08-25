"""
Two notification channels: ntfy (push) and email (SMTP).
Both read their settings from environment variables so no secrets
live in code or in the searches.json config file.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

import httpx


def send_ntfy(title: str, message: str, priority: str = "default", url: str | None = None) -> None:
    """
    Posts to ntfy (self-hosted or the free public ntfy.sh instance).

    Env vars:
      NTFY_SERVER  - e.g. https://ntfy.sh  or  https://ntfy.yourdomain.com
      NTFY_TOPIC   - your private topic name (treat it like a password --
                     anyone who knows it can read/publish to it on a public server)
    """
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic = os.environ["NTFY_TOPIC"]
    if url is None:
        url = f"{server}/{topic}"

    # httpx encodes str header values as ASCII by default, which breaks
    # on titles containing emoji/non-ASCII (e.g. "✈ ..."). ntfy expects
    # raw UTF-8 bytes in the Title header, so encode it ourselves --
    # passing bytes skips httpx's ASCII-only encoding path.
    headers = {"Title": title.encode("utf-8"), "Priority": priority.encode("utf-8")}
    resp = httpx.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
    resp.raise_for_status()


def send_email(subject: str, body: str) -> None:
    """
    Sends a plain-text email via SMTP.

    Env vars:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
      EMAIL_TO   - where alerts should land (can be same as SMTP_USER)

    For Gmail: use an "App Password" (myaccount.google.com/apppasswords),
    not your normal password -- Gmail blocks plain SMTP logins otherwise.
    """
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_addr = os.environ.get("EMAIL_TO", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context) as server:
        server.login(user, password)
        server.send_message(msg)


def notify_all(channels: list[str], title: str, message: str) -> None:
    errors = []
    if "ntfy" in channels:
        try:
            send_ntfy(title, message)
        except Exception as e:  # noqa: BLE001
            errors.append(f"ntfy failed: {e}")
    if "email" in channels:
        try:
            send_email(title, message)
        except Exception as e:  # noqa: BLE001
            errors.append(f"email failed: {e}")
    if errors:
        raise RuntimeError("; ".join(errors))
