import os
import unittest
from unittest.mock import patch

from campus_copilot import pipeline


class ScheduledTickTests(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "42", "IMAP_USER": "", "IMAP_PASS": ""})
    @patch("campus_copilot.pipeline.store.due_reminders", return_value=[])
    @patch("campus_copilot.pipeline.notify.telegram_reply")
    @patch("campus_copilot.pipeline.store.mark_reminder_sent")
    def test_sends_due_reminders_without_polling_updates(self, mark_sent, reply, due):
        due.return_value = [
            {"id": 7, "title": "Call Maya", "due_at": "2026-10-09T17:30:00+05:30"},
            {"id": 8, "title": "Submit DBMS", "due_at": "2026-10-09T17:30:00+05:30"},
        ]

        result = pipeline.scheduled_tick({"timezone": "Asia/Kolkata"})

        reply.assert_called_once()
        self.assertIn("Call Maya", reply.call_args.args[1])
        self.assertIn("Submit DBMS", reply.call_args.args[1])
        self.assertIn("Fri 09 Oct, 05:30 PM", reply.call_args.args[1])
        self.assertEqual(mark_sent.call_count, 2)
        mark_sent.assert_any_call(7)
        mark_sent.assert_any_call(8)
        self.assertEqual(result["personal_reminders_sent"], 2)
        self.assertEqual(result["classroom_emails_sent"], 0)

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

    @patch.dict(os.environ, {"IMAP_USER": "student@example.edu", "IMAP_PASS": "private"})
    @patch("campus_copilot.pipeline.store.get_state", return_value="1")
    @patch("campus_copilot.pipeline.classroom.fetch_imap")
    @patch("campus_copilot.pipeline.store.is_seen", return_value=False)
    @patch("campus_copilot.pipeline.notify.telegram_reply")
    @patch("campus_copilot.pipeline.store.mark_seen")
    def test_suppresses_routine_mail_and_batches_actionable_updates(
            self, mark_seen, reply, _is_seen, fetch, _state):
        fetch.return_value = {"announcements": [
            {"email_id": "<routine@example.edu>", "text": "New material posted", "time": ""},
            {"email_id": "<assignment@example.edu>",
             "text": "Assignment deadline Friday; submit your work", "time": ""},
            {"email_id": "<exam@example.edu>",
             "text": "Quiz scheduled for tomorrow", "time": ""},
        ]}

        count = pipeline._poll_classroom_emails(
            {"classroom": {"lookback_days": 7}}, "42")

        self.assertEqual(count, 1)
        reply.assert_called_once()
        body = reply.call_args.args[1]
        self.assertIn("Assignment deadline Friday", body)
        self.assertIn("Quiz scheduled for tomorrow", body)
        self.assertNotIn("New material posted", body)
        self.assertEqual(mark_seen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
