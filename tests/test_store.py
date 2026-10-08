import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from campus_copilot import store


class PersonalReminderStoreTests(unittest.TestCase):
    def test_reminder_lifecycle_and_update_deduplication(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(store, "DB", Path(temp_dir) / "test.db"):
                reminder_id = store.add_reminder(
                    "Call Maya", "2026-10-09T17:30:00+05:30", 123)

                self.assertEqual(
                    store.add_reminder("Duplicate", "2026-10-09T17:30:00+05:30", 123),
                    reminder_id,
                )
                self.assertEqual(
                    store.due_reminders("2026-10-09T17:30:00+05:30"),
                    [{"id": reminder_id, "title": "Call Maya",
                      "due_at": "2026-10-09T17:30:00+05:30"}],
                )

                store.mark_reminder_sent(reminder_id)

                self.assertEqual(store.pending_reminders(), [])

    def test_cancel_only_changes_pending_reminders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(store, "DB", Path(temp_dir) / "test.db"):
                reminder_id = store.add_reminder(
                    "Submit form", "2026-10-09T17:30:00+05:30", 456)

                self.assertTrue(store.cancel_reminder(reminder_id))
                self.assertFalse(store.cancel_reminder(reminder_id))
                self.assertEqual(store.pending_reminders(), [])

    @patch.dict(os.environ, {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "private-test-key",
    })
    @patch("campus_copilot.store.requests.request")
    def test_remote_reminder_insert_uses_service_role_and_conflict_deduplication(self, request):
        response = unittest.mock.Mock(
            status_code=201, content=b'[{"id": 27}]',
            json=lambda: [{"id": 27}],
        )
        request.return_value = response

        reminder_id = store.add_reminder(
            "Call Maya", "2026-10-09T17:30:00+05:30", 1234)

        self.assertEqual(reminder_id, 27)
        args, kwargs = request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "https://example.supabase.co/rest/v1/personal_reminders")
        self.assertEqual(kwargs["headers"]["apikey"], "private-test-key")
        self.assertEqual(kwargs["params"], {"on_conflict": "source_update_id"})
        self.assertEqual(kwargs["json"]["source_update_id"], 1234)
        self.assertEqual(kwargs["headers"]["Prefer"],
                         "resolution=ignore-duplicates,return=representation")


if __name__ == "__main__":
    unittest.main()
