"""SQLite memory for deduplication and job feedback."""
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "copilot.db"


def conn():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS seen(key TEXT PRIMARY KEY, kind TEXT, ts REAL);
        CREATE TABLE IF NOT EXISTS feedback(
            job_key TEXT PRIMARY KEY, title TEXT, company TEXT, label INTEGER, ts REAL);
        """
    )
    return c


def is_seen(key):
    with conn() as c:
        return c.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone() is not None


def mark_seen(key, kind):
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
