import os
import unittest
from unittest.mock import patch

import requests

from campus_copilot import notify


class TelegramTests(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "private-test-token", "TELEGRAM_CHAT_ID": "123"})
    @patch("campus_copilot.notify.requests.post")
    def test_sends_message_to_configured_bot(self, post):
        post.return_value.raise_for_status.return_value = None

        result = notify.telegram("Title", "Body")

        self.assertTrue(result)
        self.assertIn("/botprivate-test-token/sendMessage", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["json"]["chat_id"], "123")

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "private-test-token", "TELEGRAM_CHAT_ID": "123"})
    @patch("campus_copilot.notify.requests.post", side_effect=requests.ConnectionError(
        "failed URL https://api.telegram.org/botprivate-test-token/sendMessage"
    ))
    def test_does_not_expose_bot_token_in_delivery_error(self, _post):
        with self.assertRaises(RuntimeError) as error:
            notify.telegram("Title", "Body")

        self.assertNotIn("private-test-token", str(error.exception))


if __name__ == "__main__":
    unittest.main()
