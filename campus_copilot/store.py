"""SQLite memory for deduplication and job feedback."""
import sqlite3
import time
import os
from contextlib import contextmanager
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "copilot.db"


def _supabase_config():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if bool(url) != bool(key):
        raise RuntimeError("Set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    return (url.rstrip("/"), key) if url and key else None


def _supabase_request(table, method, *, params=None, payload=None, prefer=None):
    config = _supabase_config()
    if config is None:
        raise RuntimeError("Supabase is not configured; set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    url, key = config
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(
            method, f"{url}/rest/v1/{table}", headers=headers,
            params=params, json=payload, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else "unavailable"
        raise RuntimeError(
            f"Supabase {table} request failed (HTTP {status}); check database URL, key, and schema.") from None
    if response.status_code == 204 or not response.content:
        return []
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(f"Supabase {table} returned an invalid response.") from None
    if not isinstance(result, list):
        raise RuntimeError(f"Supabase {table} returned an unexpected response.")
    return result


def _remote_enabled():
    return _supabase_config() is not None


@contextmanager
def conn():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen(key TEXT PRIMARY KEY, kind TEXT, ts REAL);
            CREATE TABLE IF NOT EXISTS feedback(
                job_key TEXT PRIMARY KEY, title TEXT, company TEXT, label INTEGER, ts REAL);
            CREATE TABLE IF NOT EXISTS app_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS personal_reminders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL,
                source_update_id INTEGER UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL);
            """
        )
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def is_seen(key):
    if _remote_enabled():
        return bool(_supabase_request("seen", "GET", params={
            "select": "key", "key": f"eq.{key}", "limit": "1",
        }))
    with conn() as c:
        return c.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone() is not None


def mark_seen(key, kind):
    if _remote_enabled():
        _supabase_request("seen", "POST", params={"on_conflict": "key"},
                          payload={"key": key, "kind": kind, "ts": time.time()},
                          prefer="resolution=ignore-duplicates,return=minimal")
        return
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO seen VALUES (?,?,?)", (key, kind, time.time()))


def save_feedback(job_key, title, company, label):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO feedback VALUES (?,?,?,?,?)",
                  (job_key, title, company, label, time.time()))


def find_job_key(prefix):
    with conn() as c:
        row = c.execute("SELECT key FROM seen WHERE kind='job' AND key LIKE ? LIMIT 1",
                        (prefix + "%",)).fetchone()
    return row[0] if row else None


def job_meta(key):
    with conn() as c:
        row = c.execute("SELECT title, company FROM job_meta WHERE key=?", (key,)).fetchone() \
            if _has_table(c, "job_meta") else None
    return row or ("", "")


def _has_table(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def remember_job(key, title, company):
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS job_meta(key TEXT PRIMARY KEY, title TEXT, company TEXT)")
        c.execute("INSERT OR REPLACE INTO job_meta VALUES (?,?,?)", (key, title, company))


def recent_feedback(limit=6):
    with conn() as c:
        rows = c.execute(
            "SELECT title, company, label FROM feedback ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [{"title": t, "company": co, "liked": bool(l)} for t, co, l in rows]


def get_state(key):
    if _remote_enabled():
        rows = _supabase_request("app_state", "GET", params={
            "select": "value", "key": f"eq.{key}", "limit": "1",
        })
        return rows[0]["value"] if rows else None
    with conn() as c:
        row = c.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_state(key, value):
    if _remote_enabled():
        _supabase_request("app_state", "POST", params={"on_conflict": "key"},
                          payload={"key": key, "value": str(value)},
                          prefer="resolution=merge-duplicates,return=minimal")
        return
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO app_state VALUES (?,?)", (key, str(value)))


def add_reminder(title, due_at, source_update_id):
    if _remote_enabled():
        rows = _supabase_request(
            "personal_reminders", "POST", params={"on_conflict": "source_update_id"},
            payload={"title": title, "due_at": due_at, "source_update_id": source_update_id},
            prefer="resolution=ignore-duplicates,return=representation")
        if rows:
            return rows[0]["id"]
        existing = _supabase_request("personal_reminders", "GET", params={
            "select": "id", "source_update_id": f"eq.{source_update_id}", "limit": "1",
        })
        if not existing:
            raise RuntimeError("Could not confirm the saved Telegram reminder.")
        return existing[0]["id"]
    with conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO personal_reminders
               (title, due_at, source_update_id, created_at) VALUES (?,?,?,?)""",
            (title, due_at, source_update_id, time.time()))
        if cur.rowcount:
            return cur.lastrowid
        row = c.execute("SELECT id FROM personal_reminders WHERE source_update_id=?",
                        (source_update_id,)).fetchone()
    return row[0]


def pending_reminders():
    if _remote_enabled():
        return _supabase_request("personal_reminders", "GET", params={
            "select": "id,title,due_at", "status": "eq.pending",
            "order": "due_at.asc", "limit": "100",
        })
    with conn() as c:
        rows = c.execute(
            "SELECT id, title, due_at FROM personal_reminders "
            "WHERE status='pending' ORDER BY due_at, id").fetchall()
    return [{"id": i, "title": title, "due_at": due_at} for i, title, due_at in rows]


def due_reminders(now_iso):
    if _remote_enabled():
        return _supabase_request("personal_reminders", "GET", params={
            "select": "id,title,due_at", "status": "eq.pending",
            "due_at": f"lte.{now_iso}", "order": "due_at.asc", "limit": "100",
        })
    with conn() as c:
        rows = c.execute(
            "SELECT id, title, due_at FROM personal_reminders "
            "WHERE status='pending' AND due_at<=? ORDER BY due_at, id",
            (now_iso,)).fetchall()
    return [{"id": i, "title": title, "due_at": due_at} for i, title, due_at in rows]


def mark_reminder_sent(reminder_id):
    if _remote_enabled():
        _supabase_request("personal_reminders", "PATCH", params={
            "id": f"eq.{reminder_id}", "status": "eq.pending",
        }, payload={"status": "sent"}, prefer="return=minimal")
        return
    with conn() as c:
        c.execute("UPDATE personal_reminders SET status='sent' WHERE id=? AND status='pending'",
                  (reminder_id,))


def cancel_reminder(reminder_id):
    if _remote_enabled():
        rows = _supabase_request("personal_reminders", "PATCH", params={
            "id": f"eq.{reminder_id}", "status": "eq.pending",
        }, payload={"status": "cancelled"}, prefer="return=representation")
        return bool(rows)
    with conn() as c:
        cur = c.execute("UPDATE personal_reminders SET status='cancelled' "
                        "WHERE id=? AND status='pending'", (reminder_id,))
    return cur.rowcount > 0
