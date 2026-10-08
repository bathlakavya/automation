"""Google Classroom via API, with an IMAP (notification-email) fallback for locked-down college accounts."""
import os
import re
import html
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "secrets" / "credentials.json"
TOKEN = ROOT / "secrets" / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return creds


def _due(work, tz):
    d = work.get("dueDate")
    if not d:
        return None
    t = work.get("dueTime")
    if t is None:  # Classroom omits time => treat as end of day, local time
        return datetime(d["year"], d["month"], d["day"], 23, 59, tzinfo=tz)
    utc = datetime(d["year"], d["month"], d["day"], t.get("hours", 0), t.get("minutes", 0),
                   tzinfo=timezone.utc)
    return utc.astimezone(tz)


def fetch(cfg):
    from googleapiclient.discovery import build

    tz = ZoneInfo(cfg["timezone"])
    svc = build("classroom", "v1", credentials=get_creds(), cache_discovery=False)
    cutoff = datetime.now(tz) - timedelta(days=cfg["classroom"]["lookback_days"])
    courses = svc.courses().list(courseStates=["ACTIVE"], studentId="me").execute().get("courses", [])
    out = {"source": "api", "assignments": [], "announcements": [], "materials": []}
    for c in courses:
        cid, cname = c["id"], c["name"]
        subs = {}
        resp = svc.courses().courseWork().studentSubmissions().list(
            courseId=cid, courseWorkId="-", userId="me").execute()
        for s in resp.get("studentSubmissions", []):
            subs[s["courseWorkId"]] = s.get("state")
        for w in svc.courses().courseWork().list(courseId=cid, pageSize=50).execute().get("courseWork", []):
            state = subs.get(w["id"], "NEW")
            if state in ("TURNED_IN", "RETURNED"):
                continue
            due = _due(w, tz)
            if due and due < cutoff:
                continue
            out["assignments"].append({
                "id": w["id"], "course": cname, "title": w.get("title", ""),
                "description": (w.get("description") or "")[:500],
                "due_iso": due.isoformat() if due else None, "state": state,
                "link": w.get("alternateLink", ""),
            })
        for a in svc.courses().announcements().list(courseId=cid, pageSize=5).execute().get("announcements", []):
            out["announcements"].append({
                "course": cname, "text": (a.get("text") or "")[:600],
                "time": a.get("updateTime", ""), "link": a.get("alternateLink", "")})
        try:
            mats = svc.courses().courseWorkMaterials().list(courseId=cid, pageSize=5).execute()
            for m in mats.get("courseWorkMaterial", []):
                out["materials"].append({
                    "course": cname, "title": m.get("title", ""),
                    "description": (m.get("description") or "")[:500],
                    "link": m.get("alternateLink", "")})
        except Exception:  # noqa: BLE001  (materials are optional)
            pass
    return out


def fetch_imap(cfg):
    """Fallback: read Classroom notification emails (works even if your college blocks third-party OAuth)."""
    import email
    import imaplib
    from email.header import decode_header, make_header

    M = imaplib.IMAP4_SSL(os.getenv("IMAP_HOST", "imap.gmail.com"))
    M.login(os.environ["IMAP_USER"], os.environ["IMAP_PASS"])
    M.select("INBOX")
    since = (datetime.now() - timedelta(days=cfg["classroom"]["lookback_days"])).strftime("%d-%b-%Y")
    status, data = M.search(None, f'(FROM "classroom.google.com" SINCE {since})')
    if status != "OK":
        M.logout()
        raise RuntimeError("Could not search the Classroom notification mailbox.")
    items = []
    try:
        for num in data[0].split()[-40:]:
            result, msg_data = M.fetch(num, "(RFC822)")
            if result != "OK":
                raise RuntimeError("Could not read a Classroom notification email.")
            raw = next((part[1] for part in msg_data if isinstance(part, tuple)), None)
            if raw is None:
                raise RuntimeError("Classroom notification email had no message content.")
            msg = email.message_from_bytes(raw)
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            snippet = _plain_email_text(msg)
            email_id = msg.get("Message-ID") or num.decode("ascii", errors="replace")
            try:
                received = parsedate_to_datetime(msg.get("Date", "")).isoformat()
            except (TypeError, ValueError):
                received = msg.get("Date", "")
            items.append({
                "course": "(from email)",
                "text": subject + (f"\n{snippet}" if snippet else ""),
                "time": received,
                "link": "",
                "email_id": email_id,
            })
    finally:
        M.logout()
    return {"source": "imap", "assignments": [], "announcements": items, "materials": []}


def _plain_email_text(msg):
    """Return a short plain-text email excerpt without forwarding HTML markup."""
    parts = msg.walk() if msg.is_multipart() else (msg,)
    for part in parts:
        if part.get_content_type() != "text/plain" or part.get_content_disposition() == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        return re.sub(r"\s+", " ", html.unescape(text)).strip()[:700]
    return ""
