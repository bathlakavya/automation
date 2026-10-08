"""Fan-out delivery: Telegram, Email, WhatsApp (Twilio), Notion, Google Calendar. Missing keys => channel skipped."""
import logging
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

import requests

log = logging.getLogger("copilot")


def _chunks(text, n):
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def telegram(title, body):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return None
    for part in _chunks(f"{title}\n\n{body}", 3900):
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              json={"chat_id": chat, "text": part, "disable_web_page_preview": True},
                              timeout=30)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Telegram delivery failed ({type(exc).__name__})") from None
    return True


def telegram_reply(chat_id, text):
    """Reply in the configured Telegram chat."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if not tok:
        raise RuntimeError("Telegram replies require TELEGRAM_BOT_TOKEN.")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Telegram reply failed ({type(exc).__name__}).") from None
    if not payload.get("ok"):
        raise RuntimeError("Telegram did not accept the reply.")
    return True


def telegram_set_webhook(webhook_url, secret_token):
    """Register Telegram's webhook, rejecting malformed configuration without exposing secrets."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Telegram webhook requires TELEGRAM_BOT_TOKEN.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret_token or ""):
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET must be 1–256 letters, numbers, underscores, or hyphens.")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "secret_token": secret_token,
                  "allowed_updates": ["message"], "drop_pending_updates": False},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Telegram webhook setup failed ({type(exc).__name__}).") from None
    if not payload.get("ok"):
        raise RuntimeError("Telegram did not accept the webhook configuration.")
    return True


def email(title, body):
    user, pwd, to = os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"), os.getenv("EMAIL_TO")
    if not (user and pwd and to):
        return None
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = title, user, to
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), 465, timeout=30) as s:
        s.login(user, pwd)
        s.send_message(msg)
    return True


def whatsapp(title, body):
    sid, tok = os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN")
    frm, to = os.getenv("TWILIO_WA_FROM"), os.getenv("TWILIO_WA_TO")
    if not (sid and tok and frm and to):
        return None
    for part in _chunks(f"{title}\n\n{body}", 1500)[:3]:  # WhatsApp body limit ~1600 chars
        r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                          auth=(sid, tok), data={"From": frm, "To": to, "Body": part}, timeout=30)
        r.raise_for_status()
    return True


def notion(title, body):
    tok, db = os.getenv("NOTION_TOKEN"), os.getenv("NOTION_DATABASE_ID")
    if not (tok and db):
        return None
    blocks = [{"object": "block", "type": "paragraph",
               "paragraph": {"rich_text": [{"type": "text", "text": {"content": p}}]}}
              for p in _chunks(body, 1900)][:90]
    r = requests.post("https://api.notion.com/v1/pages",
                      headers={"Authorization": f"Bearer {tok}", "Notion-Version": "2022-06-28"},
                      json={"parent": {"database_id": db},
                            "properties": {"Name": {"title": [{"text": {"content": title[:200]}}]}},
                            "children": blocks}, timeout=30)
    r.raise_for_status()
    return True


def calendar_event(title, start_dt, minutes=30, description="", tz="Asia/Kolkata"):
    """Create an event. start_dt must be a timezone-aware datetime."""
    from googleapiclient.discovery import build

    from .classroom import get_creds

    svc = build("calendar", "v3", credentials=get_creds(), cache_discovery=False)
    end = start_dt + timedelta(minutes=minutes)
    svc.events().insert(calendarId="primary", body={
        "summary": title, "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "reminders": {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": 60}, {"method": "popup", "minutes": 1440}]},
    }).execute()
    return True


CHANNELS = {"telegram": telegram, "email": email, "whatsapp": whatsapp, "notion": notion}


def broadcast(title, body):
    results = {}
    for name, fn in CHANNELS.items():
        try:
            r = fn(title, body)
            results[name] = "sent" if r else "skipped (not configured)"
        except Exception as e:  # noqa: BLE001  one dead channel must not block the rest
            log.warning("%s failed: %s", name, e)
            results[name] = f"failed: {e}"
    return results


def parse_dt(iso):
    return datetime.fromisoformat(iso)
