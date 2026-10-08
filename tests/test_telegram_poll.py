import os
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from campus_copilot import pipeline


class TelegramPollTests(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "42", "IMAP_USER": "", "IMAP_PASS": ""})
    @patch("campus_copilot.pipeline.store.due_reminders", return_value=[])
    @patch("campus_copilot.pipeline.store.get_state", return_value="0")
    @patch("campus_copilot.pipeline.notify.telegram_updates")
    @patch("campus_copilot.pipeline.notify.telegram_reply")
    @patch("campus_copilot.pipeline.store.set_state")
    @patch("campus_copilot.pipeline.personal.handle_message", return_value="Saved.")
    def test_processes_only_configured_chat_and_advances_offset(
            self, handle, set_state, reply, updates, _get_state, _due):
        updates.return_value = [
            {"update_id": 4, "message": {"chat": {"id": 42}, "text": "/help"}},
            {"update_id": 5, "message": {"chat": {"id": 99}, "text": "private message"}},
        ]

        result = pipeline.telegram_poll({"timezone": "Asia/Kolkata"})

        handle.assert_called_once_with(
            "/help", 4, ZoneInfo("Asia/Kolkata"), now=unittest.mock.ANY)
        reply.assert_called_once_with("42", "Saved.")
        set_state.assert_any_call("telegram_update_offset", 5)
        set_state.assert_any_call("telegram_update_offset", 6)
        self.assertEqual(result["telegram_messages"], 2)
        self.assertEqual(result["personal_reminders_sent"], 0)

    @patch.dict(os.environ, {"IMAP_USER": "student@example.edu", "IMAP_PASS": "private"})
    @patch("campus_copilot.pipeline.store.get_state", return_value=None)
    @patch("campus_copilot.pipeline.classroom.fetch_imap")
    @patch("campus_copilot.pipeline.store.mark_seen")
    @patch("campus_copilot.pipeline.store.set_state")
    def test_first_email_poll_baselines_existing_mail(
            self, set_state, mark_seen, fetch, _state):
        fetch.return_value = {"announcements": [{"email_id": "<old@example.edu>"}]}

        count = pipeline._poll_classroom_emails({"classroom": {"lookback_days": 7}}, "42")

        self.assertEqual(count, 0)
        mark_seen.assert_called_once_with(
            "classroom-email:<old@example.edu>", "classroom-email")
        set_state.assert_called_once_with("classroom_email_baselined", "1")

    @patch.dict(os.environ, {"IMAP_USER": "student@example.edu", "IMAP_PASS": "private"})
    @patch("campus_copilot.pipeline.store.get_state", return_value="1")
    @patch("campus_copilot.pipeline.classroom.fetch_imap")
    @patch("campus_copilot.pipeline.store.is_seen", return_value=False)
    @patch("campus_copilot.pipeline.notify.telegram_reply")
    @patch("campus_copilot.pipeline.store.mark_seen")
    def test_forwards_new_classroom_mail_once(
            self, mark_seen, reply, _is_seen, fetch, _state):
        fetch.return_value = {"announcements": [{
            "email_id": "<new@example.edu>",
            "text": "Assignment posted\nSubmit by Friday",
            "time": "2026-10-08T12:00:00+05:30",
        }]}

        count = pipeline._poll_classroom_emails({"classroom": {"lookback_days": 7}}, "42")

        self.assertEqual(count, 1)
        reply.assert_called_once()
        self.assertIn("Submit by Friday", reply.call_args.args[1])
        mark_seen.assert_called_once_with(
            "classroom-email:<new@example.edu>", "classroom-email")


if __name__ == "__main__":
    unittest.main()
