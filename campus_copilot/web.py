"""Telegram webhook application for the Render-hosted personal assistant."""
import hmac
import logging
import os
import re
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, request

from . import notify, personal, store

log = logging.getLogger("copilot")
app = Flask(__name__)
_setup_lock = threading.Lock()
_webhook_ready = False


def _ensure_webhook():
    global _webhook_ready
    if _webhook_ready:
        return
    with _setup_lock:
        if _webhook_ready:
            return
        base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not base_url.startswith("https://"):
            raise RuntimeError("Render must provide an HTTPS RENDER_EXTERNAL_URL.")
        if not chat_id:
            raise RuntimeError("Set TELEGRAM_CHAT_ID in the Render environment.")
        if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
            raise RuntimeError("Set Supabase URL and service-role key in the Render environment.")
        store.get_state("telegram_webhook_ready")
        notify.telegram_set_webhook(f"{base_url}/telegram/webhook", secret)
        _webhook_ready = True
        log.info("Telegram webhook registered.")


@app.before_request
def initialize_service():
    try:
        _ensure_webhook()
    except RuntimeError as exc:
        log.error("Telegram service initialization failed: %s", exc)
        abort(503, description="The Telegram assistant is not configured yet.")


@app.get("/healthz")
def health():
    return jsonify(status="ok")


@app.post("/telegram/webhook")
def telegram_webhook():
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    actual = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or not hmac.compare_digest(actual, expected):
        abort(403)

    update = request.get_json(silent=True)
    if not isinstance(update, dict) or "update_id" not in update:
        abort(400)
    message = update.get("message")
    if not isinstance(message, dict):
        return jsonify(ok=True)

    configured_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if chat_id != str(configured_chat):
        log.warning("Ignored Telegram update from an unconfigured chat.")
        return jsonify(ok=True)

    timezone = ZoneInfo("Asia/Kolkata")
    try:
        import yaml

        with open(store.ROOT / "config.yaml", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
        timezone = ZoneInfo(config["timezone"])
    except (OSError, KeyError, TypeError, ValueError) as exc:
        log.error("Could not load assistant timezone (%s).", type(exc).__name__)
        abort(503, description="The Telegram assistant configuration is unavailable.")

    text = message.get("text")
    if not text:
        reply = "Please send tasks and reminders as text. Voice messages aren’t supported yet."
    else:
        text = text.strip()
        lower_text = text.lower()
        update_id = int(update["update_id"])
        reminder_command = re.search(
            r"(?i)\bremind(?:er)?\b|^/(?:start|help|list|cancel)(?:\s|$)", text)
        assistant_request = re.match(r"^/(?:do|pa|ask|code|study)\b\s*(.*)$", text, re.I)

        if reminder_command and not assistant_request:
            reply = personal.handle_message(
                text, update_id, timezone, now=datetime.now(timezone))
        elif lower_text in {"help", "/help", "/start"}:
            reply = personal.handle_message(
                "/help", update_id, timezone, now=datetime.now(timezone))
        else:
            task_text = assistant_request.group(1).strip() if assistant_request else text
            command = assistant_request.group(0).split()[0].lower() if assistant_request else ""
            if not task_text:
                reply = "Please include what you want me to do after the command."
            elif len(task_text) > 2000:
                reply = "That request is too long. Please keep it under 2,000 characters."
            else:
                task = "assist" if command in {"/ask", "/code", "/study"} else "telegram-pa"
                mode = "study" if command == "/study" else "coding"
                try:
                    marker = f"telegram-task-update:{update_id}"
                    if store.is_seen(marker):
                        reply = "I’ve already received that task and it is queued."
                    else:
                        notify.github_dispatch(task, task_text, mode)
                        if task == "assist":
                            reply = ("I’ve started your request. Hermes will send the answer here "
                                     "when it finishes; the first run can take several minutes.")
                        else:
                            reply = ("I’ve started your task. I can create a Google Calendar event "
                                     "or save a Notion note; I’ll send the result here. "
                                     "This can take several minutes.")
                        try:
                            store.mark_seen(marker, "telegram-task")
                        except RuntimeError as exc:
                            log.error("Task started, but update deduplication failed: %s", exc)
                            reply = ("The task has started, but I couldn’t save its duplicate "
                                     "protection. Please don’t resend it.")
                except RuntimeError as exc:
                    log.error("Could not dispatch Telegram task: %s", exc)
                    reply = ("I couldn’t start that task. Check that Render has a valid "
                             "GITHUB_ACTIONS_TOKEN with Actions write access, then try again.")
    try:
        notify.telegram_reply(configured_chat, reply)
    except RuntimeError as exc:
        log.error("Could not reply to Telegram update: %s", exc)
        abort(503, description="The Telegram assistant could not send its reply.")
    return jsonify(ok=True)
