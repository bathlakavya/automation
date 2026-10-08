import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
