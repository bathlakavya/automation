import unittest
from unittest.mock import patch

import requests

from campus_copilot import notify


class GitHubDispatchTests(unittest.TestCase):
    @patch.dict("os.environ", {
        "GITHUB_ACTIONS_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "owner/repo",
    })
    @patch("campus_copilot.notify.requests.post")
    def test_dispatches_limited_telegram_task(self, post):
        post.return_value.status_code = 204

        self.assertTrue(notify.github_dispatch("telegram-pa", "Create a note"))
        self.assertEqual(post.call_args.args[0],
                         "https://api.github.com/repos/owner/repo/actions/workflows/"
                         "campus-copilot.yml/dispatches")
        self.assertEqual(post.call_args.kwargs["json"], {
            "ref": "main",
            "inputs": {
                "task": "telegram-pa", "request": "Create a note", "mode": "coding",
            },
        })
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    @patch.dict("os.environ", {
        "GITHUB_ACTIONS_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "owner/repo",
    })
    @patch("campus_copilot.notify.requests.post")
    def test_dispatches_hermes_assist_mode(self, post):
        post.return_value.status_code = 204

        notify.github_dispatch("assist", "Explain SQL joins", "study")

        self.assertEqual(post.call_args.kwargs["json"]["inputs"], {
            "task": "assist", "request": "Explain SQL joins", "mode": "study",
        })

    @patch.dict("os.environ", {
        "GITHUB_ACTIONS_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "owner/repo",
    })
    @patch("campus_copilot.notify.requests.post")
    def test_rejects_unexpected_github_response(self, post):
        post.return_value.status_code = 401

        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            notify.github_dispatch("telegram-pa", "Create a note")

    @patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"})
    def test_requires_dispatch_token(self):
        with self.assertRaisesRegex(RuntimeError, "GITHUB_ACTIONS_TOKEN"):
            notify.github_dispatch("telegram-pa", "Create a note")


if __name__ == "__main__":
    unittest.main()
