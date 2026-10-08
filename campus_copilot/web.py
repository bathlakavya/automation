"""Telegram webhook application for the Render-hosted personal assistant."""
import hmac
import logging
import os
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
        reply = "Please send reminders as text, for example: “Remind me tomorrow at 5 PM to call Maya”."
    else:
        reply = personal.handle_message(
            text, int(update["update_id"]), timezone, now=datetime.now(timezone))
    try:
        notify.telegram_reply(configured_chat, reply)
    except RuntimeError as exc:
        log.error("Could not reply to Telegram update: %s", exc)
        abort(503, description="The Telegram assistant could not send its reply.")
    return jsonify(ok=True)
