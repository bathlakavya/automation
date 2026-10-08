"""Orchestration: Ollama drafts and audits, then notifications fan out."""
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import classroom, jobs, llm, notify, personal, store

log = logging.getLogger("copilot")


def _now(cfg):
    return datetime.now(ZoneInfo(cfg["timezone"]))


def _harvest_skill(text):
    """Save reusable-skill suggestions for the student to review."""
    for line in text.splitlines():
        if line.startswith("SKILL_PROPOSAL:"):
            with open(store.ROOT / "data" / "skill_proposals.md", "a", encoding="utf-8") as f:
                f.write(line + "\n")
    return "\n".join(l for l in text.splitlines() if not l.startswith("SKILL_PROPOSAL:"))


def get_classroom(cfg):
    try:
        return classroom.fetch(cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("Classroom API failed (%s); trying email fallback", e)
        return classroom.fetch_imap(cfg)


def sync_calendar(cfg, data):
    if os.getenv("CALENDAR_SYNC", "1") != "1" or data.get("source") != "api":
        return 0
    horizon = _now(cfg) + timedelta(days=cfg["classroom"]["calendar_horizon_days"])
    n = 0
    for a in data["assignments"]:
        if not a["due_iso"]:
            continue
        due = notify.parse_dt(a["due_iso"])
        key = f"cal:{a['id']}:{a['due_iso']}"
        if due < _now(cfg) or due > horizon or store.is_seen(key):
            continue
        try:
            notify.calendar_event(f"DUE: {a['title']} ({a['course']})", due - timedelta(minutes=30),
                                  description=a["link"], tz=cfg["timezone"])
            store.mark_seen(key, "cal")
            n += 1
        except Exception as e:  # noqa: BLE001
            log.warning("Calendar sync failed: %s", e)
            break
    return n


def classroom_section(cfg):
    try:
        data = get_classroom(cfg)
    except Exception as e:  # noqa: BLE001
        return f"## Classroom\nUnavailable today: {e}"
    data["assignments"].sort(key=lambda a: a["due_iso"] or "9999")
    synced = sync_calendar(cfg, data)
    raw = json.dumps({"now": _now(cfg).isoformat(), **data}, ensure_ascii=False)
    task = ("TASK: Build today's Classroom brief as Markdown with sections: 'Deadlines' (urgency-sorted), "
            "'New announcements' (one line each), 'New materials' (title + 1-line gist), "
            "'Today's focus' (max 3 bullets). Data:\n" + raw)
    draft = _harvest_skill(llm.execute(task))
    final = llm.audit(draft, raw, "classroom")
    return "## Classroom\n" + final + (f"\n\n📅 {synced} deadline(s) added to Google Calendar." if synced else "")


def score_job(job, cfg):
    fb = store.recent_feedback()
    task = (
        "TASK: Score this job 0-100 for fit with the profile. Return JSON "
        '{"score": int, "type": "internship"|"full-time"|"other", "reason": str, "emphasise": [str, str]}.\n'
        f"PROFILE: {json.dumps(cfg['profile'])}\nPAST FEEDBACK (liked=true means user wanted more like this): "
        f"{json.dumps(fb)}\nJOB: {json.dumps({k: job[k] for k in ('title', 'company', 'location', 'desc')})}"
    )
    try:
        res = llm.parse_json(llm.execute(task, json_mode=True))
        return {**job, "score": int(res.get("score", 0)), "type": res.get("type", "other"),
                "reason": res.get("reason", ""), "emphasise": res.get("emphasise", [])}
    except Exception as e:  # noqa: BLE001
        log.warning("Scoring failed for %s: %s", job["title"], e)
        return {**job, "score": 0, "type": "other", "reason": "unscored", "emphasise": []}


def jobs_section(cfg):
    new = jobs.fetch_new(cfg)
    if not new:
        return "## Jobs & internships\nNothing new today."
    scored = sorted((score_job(j, cfg) for j in new), key=lambda j: j["score"], reverse=True)
    top = scored[: cfg["jobs"]["top_n"]]
    for j in top:
        store.remember_job(j["key"], j["title"], j["company"])
    slim = [{"id": j["key"][:8], "title": j["title"], "company": j["company"], "location": j["location"],
             "url": j["url"], "score": j["score"], "type": j["type"], "reason": j["reason"],
             "emphasise": j["emphasise"]} for j in top]
    raw = json.dumps({"profile": cfg["profile"], "candidates": slim}, ensure_ascii=False)
    draft = "\n".join(
        f"- [{j['id']}] {j['title']} @ {j['company']} ({j['location']}) score {j['score']} | {j['type']} | "
        f"{j['reason']} | {j['url']}" for j in slim)
    final = llm.audit(draft, raw, "jobs")
    for j in scored:  # dedupe everything we looked at, even low scorers
        store.mark_seen(j["key"], "job")
    return ("## Jobs & internships\n" + final +
            "\n\nRate with: python -m campus_copilot feedback <id> up|down")


def run_daily(cfg):
    stamp = _now(cfg).strftime("%a %d %b")
    body = classroom_section(cfg) + "\n\n" + jobs_section(cfg)
    return notify.broadcast(f"Campus Copilot, {stamp}", body), body


def remind(cfg):
    """Send an urgency-ranked reminder for overdue or next-24-hour deadlines."""
    try:
        data = get_classroom(cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("remind failed: %s", e)
        return None
    now = _now(cfg)
    due_soon = []
    for a in data["assignments"]:
        if a["due_iso"]:
            d = notify.parse_dt(a["due_iso"])
            if now - timedelta(days=1) <= d <= now + timedelta(hours=24):
                due_soon.append((d, a))
    if not due_soon:
        return None
    lines = []
    for due, assignment in sorted(due_soon, key=lambda item: item[0]):
        remaining = due - now
        if remaining.total_seconds() <= 0:
            urgency = "🔴 OVERDUE"
        elif remaining <= timedelta(hours=3):
            urgency = "🔴 URGENT"
        elif remaining <= timedelta(hours=6):
            urgency = "🟠 HIGH"
        else:
            urgency = "🟡 DUE SOON"
        line = (f"{urgency} — {assignment['title']} ({assignment['course']})\n"
                f"Due: {due.strftime('%a %d %b, %I:%M %p')}")
        if assignment["link"]:
            line += f"\n{assignment['link']}"
        lines.append(line)
    return notify.broadcast("Deadline check — act on the highest urgency first", "\n\n".join(lines))


def telegram_poll(cfg):
    """Read bot messages, send due personal reminders, and forward new Classroom emails."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("Telegram polling requires TELEGRAM_CHAT_ID.")

    updates = notify.telegram_updates(int(store.get_state("telegram_update_offset") or 0))
    for update in updates:
        update_id = int(update["update_id"])
        message = update.get("message", {})
        chat = message.get("chat", {})
        if str(chat.get("id", "")) == str(chat_id) and message.get("text"):
            reply = personal.handle_message(
                message["text"], update_id, ZoneInfo(cfg["timezone"]), now=_now(cfg))
            notify.telegram_reply(chat_id, reply)
        store.set_state("telegram_update_offset", update_id + 1)

    now = _now(cfg)
    due = store.due_reminders(now.isoformat())
    for reminder in due:
        notify.telegram_reply(
            chat_id,
            f"⏰ Reminder: {reminder['title']}\n"
            f"Scheduled for {notify.parse_dt(reminder['due_at']).astimezone(ZoneInfo(cfg['timezone'])):%a %d %b, %I:%M %p}.",
        )
        store.mark_reminder_sent(reminder["id"])

    email_count = _poll_classroom_emails(cfg, chat_id)
    return {"telegram_messages": len(updates), "personal_reminders_sent": len(due),
            "classroom_emails_sent": email_count}


def _poll_classroom_emails(cfg, chat_id):
    """Forward new Classroom notification emails, baselining existing mail on first setup."""
    if not (os.getenv("IMAP_USER") and os.getenv("IMAP_PASS")):
        log.info("Classroom email polling skipped; IMAP_USER/IMAP_PASS are not configured.")
        return 0
    data = classroom.fetch_imap(cfg)
    items = data["announcements"]
    if store.get_state("classroom_email_baselined") is None:
        for item in items:
            store.mark_seen(f"classroom-email:{item['email_id']}", "classroom-email")
        store.set_state("classroom_email_baselined", "1")
        log.info("Classroom email polling initialized; existing messages were not forwarded.")
        return 0

    sent = 0
    for item in items:
        key = f"classroom-email:{item['email_id']}"
        if store.is_seen(key):
            continue
        notify.telegram_reply(
            chat_id,
            f"📚 Classroom email\n{item['text']}\n"
            + (f"Received: {item['time']}" if item["time"] else ""),
        )
        store.mark_seen(key, "classroom-email")
        sent += 1
    return sent
