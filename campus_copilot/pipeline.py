"""Orchestration: Ollama drafts and audits, then notifications fan out."""
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import classroom, jobs, llm, notify, store

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
    """Cheap evening nudge: no LLM calls, just deadlines inside 24h."""
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
    lines = [f"⏰ {a['title']} ({a['course']}) due {d.strftime('%a %d %b, %I:%M %p')}\n{a['link']}"
             for d, a in sorted(due_soon, key=lambda x: x[0])]
    return notify.broadcast("Due in the next 24h", "\n\n".join(lines))
