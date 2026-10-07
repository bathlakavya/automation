import unittest
from unittest.mock import patch

from campus_copilot import main


class AssistCommandTests(unittest.TestCase):
    @patch("campus_copilot.main.notify.broadcast")
    @patch("campus_copilot.main.llm.hermes", return_value="Try checking for a null value.")
    def test_sends_local_coding_answer_to_notification_channels(self, hermes, broadcast):
        broadcast.return_value = {"telegram": "sent"}

        main.main(["assist", "coding", "Why does this Java call return null?"])

        hermes.assert_called_once_with(
            main.llm.load_prompt("coder"),
            "Why does this Java call return null?",
        )
        broadcast.assert_called_once_with(
            "Campus Copilot — Coding help",
            "Try checking for a null value.",
        )


if __name__ == "__main__":
    unittest.main()
