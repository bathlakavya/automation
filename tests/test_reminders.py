import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from campus_copilot import pipeline


class DeadlineReminderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 8, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        self.cfg = {"timezone": "Asia/Kolkata"}

    @patch("campus_copilot.pipeline.notify.broadcast")
    @patch("campus_copilot.pipeline.get_classroom")
    @patch("campus_copilot.pipeline._now")
    def test_sends_deadlines_with_urgency_and_in_due_order(self, now, classroom, broadcast):
        now.return_value = self.now
        broadcast.return_value = {"telegram": "sent"}
        classroom.return_value = {"assignments": [
            {"title": "Tomorrow item", "course": "DBMS", "due_iso": "2026-10-09T11:00:00+05:30", "link": ""},
            {"title": "Urgent item", "course": "OS", "due_iso": "2026-10-08T14:00:00+05:30", "link": "https://example.test/os"},
            {"title": "Overdue item", "course": "Java", "due_iso": "2026-10-08T11:00:00+05:30", "link": ""},
            {"title": "Outside window", "course": "Math", "due_iso": "2026-10-10T13:00:00+05:30", "link": ""},
        ]}

        result = pipeline.remind(self.cfg)

        self.assertEqual(result, {"telegram": "sent"})
        body = broadcast.call_args.args[1]
        self.assertLess(body.index("OVERDUE — Overdue item"), body.index("URGENT — Urgent item"))
        self.assertLess(body.index("URGENT — Urgent item"), body.index("DUE SOON — Tomorrow item"))
        self.assertNotIn("Outside window", body)
        self.assertIn("https://example.test/os", body)

    @patch("campus_copilot.pipeline.notify.broadcast")
    @patch("campus_copilot.pipeline.get_classroom", return_value={"assignments": []})
    @patch("campus_copilot.pipeline._now")
    def test_sends_nothing_when_no_deadlines_are_in_window(self, now, _classroom, broadcast):
        now.return_value = self.now

        result = pipeline.remind(self.cfg)

        self.assertIsNone(result)
        broadcast.assert_not_called()


if __name__ == "__main__":
    unittest.main()
