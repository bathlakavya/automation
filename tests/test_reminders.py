import unittest
import os
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from campus_copilot import pipeline


class DeadlineReminderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 8, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        self.cfg = {"timezone": "Asia/Kolkata"}

    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "42"})
    @patch("campus_copilot.pipeline.store.mark_seen")
    @patch("campus_copilot.pipeline.store.is_seen", return_value=False)
    @patch("campus_copilot.pipeline.notify.telegram_reply")
    @patch("campus_copilot.pipeline.get_classroom")
    @patch("campus_copilot.pipeline._now")
    def test_sends_only_important_deadline_milestones_once(
            self, now, classroom, reply, _is_seen, mark_seen):
        now.return_value = self.now
        classroom.return_value = {"assignments": [
            {"id": "dbms-1", "title": "Six hour item", "course": "DBMS",
             "due_iso": "2026-10-08T17:00:00+05:30", "link": ""},
            {"id": "os-1", "title": "Urgent item", "course": "OS",
             "due_iso": "2026-10-08T12:30:00+05:30", "link": "https://example.test/os"},
            {"id": "java-1", "title": "Overdue item", "course": "Java",
             "due_iso": "2026-10-08T11:00:00+05:30", "link": ""},
            {"id": "math-1", "title": "Not urgent", "course": "Math",
             "due_iso": "2026-10-08T20:00:00+05:30", "link": ""},
            {"id": "old-1", "title": "Too old", "course": "Old class",
             "due_iso": "2026-10-07T11:00:00+05:30", "link": ""},
        ]}

        result = pipeline.remind(self.cfg)

        self.assertEqual(result, {"telegram": "sent"})
        reply.assert_called_once()
        self.assertEqual(reply.call_args.args[0], "42")
        body = reply.call_args.args[1]
        self.assertLess(body.index("OVERDUE — Overdue item"), body.index("DUE WITHIN 1 HOUR — Urgent item"))
        self.assertLess(body.index("DUE WITHIN 1 HOUR — Urgent item"),
                        body.index("DUE WITHIN 6 HOURS — Six hour item"))
        self.assertNotIn("Not urgent", body)
        self.assertNotIn("Too old", body)
        self.assertIn("https://example.test/os", body)
        self.assertEqual(mark_seen.call_count, 3)

    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "42"})
    @patch("campus_copilot.pipeline.store.is_seen", return_value=True)
    @patch("campus_copilot.pipeline.notify.telegram_reply")
    @patch("campus_copilot.pipeline.get_classroom", return_value={"assignments": []})
    @patch("campus_copilot.pipeline._now")
    def test_sends_nothing_when_no_new_important_deadlines(self, now, _classroom, reply, _seen):
        now.return_value = self.now
        _classroom.return_value = {"assignments": [{
            "id": "os-1", "title": "Urgent item", "course": "OS",
            "due_iso": "2026-10-08T12:30:00+05:30", "link": "",
        }]}

        result = pipeline.remind(self.cfg)

        self.assertIsNone(result)
        reply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
