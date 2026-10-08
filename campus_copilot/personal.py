"""Personal reminders received through the Telegram bot."""
import re
from datetime import datetime, time, timedelta

from dateparser.search import search_dates

from . import store


def _parse_request(text, now, timezone):
    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now,
        "TIMEZONE": timezone.key,
        "RETURN_AS_TIMEZONE_AWARE": True,
    }
    matches = search_dates(text, settings=settings, languages=["en"])
    clock = re.search(
        r"\b(?:at\s+)?(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?\s*"
        r"(?P<ampm>a\.?m\.?|p\.?m\.?)\b",
        text,
        re.I,
    )
    if matches:
        phrase, due = matches[0]
        due = due.astimezone(timezone)
        has_time = bool(
            (clock and clock.group(0).strip().lower() in phrase.lower())
            or re.search(
                r"\b(?:in\s+)?(?:\d+|a|an)\s+(?:seconds?|minutes?|hours?)\b",
                phrase,
                re.I,
            )
        )
    elif clock:
        phrase = clock.group(0)
        hour = int(clock.group("hour")) % 12
        if clock.group("ampm").lower().startswith("p"):
            hour += 12
        due = datetime.combine(
            now.date(), time(hour, int(clock.group("minute") or 0)), tzinfo=timezone)
        if due <= now:
            due += timedelta(days=1)
        has_time = True
    else:
        return None

    if not has_time:
        due = due.replace(hour=9, minute=0, second=0, microsecond=0)
    if due <= now:
        return None

    title = text.replace(phrase, " ", 1)
    title = re.sub(r"(?i)^\s*(?:please\s+)?remind\s+me(?:\s+to)?\b", " ", title)
    title = re.sub(r"(?i)^\s*(?:please\s+)?reminder(?:\s+to)?\b", " ", title)
    title = re.sub(r"(?i)^\s*/?remind\b", " ", title)
    title = re.sub(r"(?i)^\s*(?:to|about|that|on|at|by)\b", " ", title)
    title = re.sub(r"[\s,;:.!?-]+", " ", title).strip()
    if not title:
        return None
    return title[:240], due, not has_time


def handle_message(text, update_id, timezone, now=None):
    """Save a one-time reminder, list reminders, or cancel one by its ID."""
    text = (text or "").strip()
    now = now or datetime.now(timezone)

    if text.lower() in ("/start", "/help", "help"):
        return ("Send a reminder like: “Remind me tomorrow at 5:30 PM to call Maya”. "
                "Use /list to see pending reminders or /cancel ID to cancel one. "
                "If you omit the time, I’ll use 9:00 AM.")

    if text.lower() in ("/list", "list reminders", "show reminders"):
        reminders = store.pending_reminders()
        if not reminders:
            return "You don’t have any pending personal reminders."
        return "Pending reminders:\n" + "\n".join(
            f"#{r['id']} — {r['title']} ({datetime.fromisoformat(r['due_at']).astimezone(timezone):%a %d %b, %I:%M %p})"
            for r in reminders[:20])

    cancel = re.fullmatch(r"/cancel\s+(\d+)", text, re.I)
    if cancel:
        reminder_id = int(cancel.group(1))
        return (f"Cancelled reminder #{reminder_id}."
                if store.cancel_reminder(reminder_id)
                else f"Reminder #{reminder_id} was not pending.")

    if not re.search(r"(?i)\bremind(?:er)?\b|^/remind\b", text):
        return "I can save personal reminders. Send /help for an example."

    parsed = _parse_request(text, now, timezone)
    if not parsed:
        return ("I couldn’t find a future date/time and reminder title. Try: "
                "“Remind me tomorrow at 5:30 PM to call Maya”.")
    title, due, defaulted_time = parsed
    reminder_id = store.add_reminder(title, due.isoformat(), update_id)
    suffix = " (using 9:00 AM because no time was given)" if defaulted_time else ""
    return f"Saved reminder #{reminder_id}: {title} — {due:%a %d %b, %I:%M %p}{suffix}."
