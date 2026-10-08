import os
import unittest
from unittest.mock import patch

from campus_copilot import web


class TelegramWebhookTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "private-test-token",
        "TELEGRAM_CHAT_ID": "42",
        "TELEGRAM_WEBHOOK_SECRET": "webhook-secret",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "private-test-key",
        "RENDER_EXTERNAL_URL": "https://campus-copilot.onrender.com",
    })
    @patch("campus_copilot.web.notify.telegram_set_webhook")
    @patch("campus_copilot.web.store.get_state")
    @patch("campus_copilot.web._webhook_ready", False)
    def test_health_check_registers_telegram_webhook(self, _state, set_webhook):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        set_webhook.assert_called_once_with(
            "https://campus-copilot.onrender.com/telegram/webhook", "webhook-secret")

    @patch.dict(os.environ, {
        "TELEGRAM_WEBHOOK_SECRET": "test-secret",
        "TELEGRAM_CHAT_ID": "42",
    })
    @patch("campus_copilot.web.notify.telegram_reply")
    @patch("campus_copilot.web.personal.handle_message", return_value="Saved reminder.")
    @patch("campus_copilot.web._ensure_webhook")
    def test_valid_text_update_gets_immediate_reply(self, _setup, handle, reply):
        response = self.client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            json={"update_id": 15, "message": {
                "chat": {"id": 42}, "text": "Remind me tomorrow at 5 PM to call Maya",
            }},
        )

        self.assertEqual(response.status_code, 200)
        handle.assert_called_once()
        self.assertEqual(handle.call_args.args[:2], (
            "Remind me tomorrow at 5 PM to call Maya", 15))
        self.assertEqual(handle.call_args.args[2].key, "Asia/Kolkata")
        self.assertEqual(handle.call_args.kwargs["now"].tzinfo.key, "Asia/Kolkata")
        reply.assert_called_once_with("42", "Saved reminder.")

    @patch.dict(os.environ, {
        "TELEGRAM_WEBHOOK_SECRET": "test-secret",
        "TELEGRAM_CHAT_ID": "42",
    })
    @patch("campus_copilot.web._ensure_webhook")
    def test_rejects_webhook_without_correct_secret(self, _setup):
        response = self.client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            json={"update_id": 15, "message": {"chat": {"id": 42}, "text": "/help"}},
        )

        self.assertEqual(response.status_code, 403)

    @patch.dict(os.environ, {
        "TELEGRAM_WEBHOOK_SECRET": "test-secret",
        "TELEGRAM_CHAT_ID": "42",
    })
    @patch("campus_copilot.web.notify.telegram_reply")
    @patch("campus_copilot.web._ensure_webhook")
    def test_explains_that_voice_messages_are_not_supported(self, _setup, reply):
        response = self.client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            json={"update_id": 16, "message": {
                "chat": {"id": 42}, "voice": {"file_id": "private-file-id"},
            }},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("as text", reply.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
