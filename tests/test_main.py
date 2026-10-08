import unittest
from unittest.mock import patch

from campus_copilot.main import cmd_pa


class PersonalAssistantActionTests(unittest.TestCase):
    @patch("campus_copilot.main.llm.execute", return_value=(
        '{"action":"unsupported","title":"","start_iso":null,'
        '"duration_min":30,"body":""}'))
    def test_unsupported_request_does_not_create_an_action(self, _execute):
        with patch("campus_copilot.main.notify.calendar_event") as calendar_event, \
                patch("campus_copilot.main.notify.notion") as notion:
            reply = cmd_pa({"timezone": "Asia/Kolkata"}, "What is a database?")

        self.assertIn("create Google Calendar events", reply)
        calendar_event.assert_not_called()
        notion.assert_not_called()

    @patch("campus_copilot.main.llm.execute", return_value=(
        '{"action":"note","title":"Exam plan","start_iso":null,'
        '"duration_min":30,"body":"Revise SQL"}'))
    @patch("campus_copilot.main.notify.notion", return_value=None)
    def test_missing_notion_configuration_is_not_reported_as_saved(self, notion, _execute):
        reply = cmd_pa({"timezone": "Asia/Kolkata"}, "Save an exam plan")

        self.assertIn("after Notion is configured", reply)
        notion.assert_called_once_with("Exam plan", "Revise SQL")


if __name__ == "__main__":
    unittest.main()
