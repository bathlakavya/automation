import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from campus_copilot import personal


class PersonalReminderTests(unittest.TestCase):
    def setUp(self):
        self.tz = ZoneInfo("Asia/Kolkata")
        self.now = datetime(2026, 10, 8, 12, 0, tzinfo=self.tz)

    def test_parses_tomorrow_time_and_keeps_task_text(self):
        parsed = personal._parse_request(
            "Remind me tomorrow at 5:30 PM to go to class", self.now, self.tz)

        self.assertEqual(parsed[0], "go to class")
        self.assertEqual(parsed[1], datetime(2026, 10, 9, 17, 30, tzinfo=self.tz))
        self.assertFalse(parsed[2])

    def test_time_only_request_schedules_today_if_still_future(self):
        parsed = personal._parse_request("Remind me at 5:30 PM to call mom", self.now, self.tz)

        self.assertEqual(parsed[0], "call mom")
        self.assertEqual(parsed[1], datetime(2026, 10, 8, 17, 30, tzinfo=self.tz))

    def test_time_only_request_rolls_to_tomorrow_if_time_has_passed(self):
        parsed = personal._parse_request(
            "Remind me at 10:30 AM to call mom", self.now, self.tz)

        self.assertEqual(parsed[1], datetime(2026, 10, 9, 10, 30, tzinfo=self.tz))

    def test_relative_minutes_keeps_parsed_time(self):
        parsed = personal._parse_request(
            "Remind me in 20 minutes to test notifications", self.now, self.tz)

        self.assertEqual(parsed[0], "test notifications")
        self.assertEqual(parsed[1], datetime(2026, 10, 8, 12, 20, tzinfo=self.tz))
        self.assertFalse(parsed[2])

    def test_relative_hours_keeps_parsed_time(self):
        parsed = personal._parse_request(
            "Remind me in 2 hours to take a break", self.now, self.tz)

        self.assertEqual(parsed[0], "take a break")
        self.assertEqual(parsed[1], datetime(2026, 10, 8, 14, 0, tzinfo=self.tz))
        self.assertFalse(parsed[2])

    def test_date_without_time_defaults_to_nine_am(self):
        parsed = personal._parse_request(
            "Remind me tomorrow to submit the assignment", self.now, self.tz)

        self.assertEqual(parsed[1], datetime(2026, 10, 9, 9, 0, tzinfo=self.tz))
        self.assertTrue(parsed[2])

    def test_message_without_future_date_is_not_saved(self):
        with patch.object(personal.store, "add_reminder") as add:
            reply = personal.handle_message(
                "Remind me to call mom", 9, self.tz, now=self.now)

        self.assertIn("couldn’t find", reply)
        add.assert_not_called()

    @patch.object(personal.store, "add_reminder", return_value=12)
    def test_saves_and_confirms_reminder(self, add):
        reply = personal.handle_message(
            "Remind me tomorrow at 5:30 PM to call Maya", 42, self.tz, now=self.now)

        self.assertIn("Saved reminder #12: call Maya", reply)
        add.assert_called_once_with(
            "call Maya", "2026-10-09T17:30:00+05:30", 42)


if __name__ == "__main__":
    unittest.main()
