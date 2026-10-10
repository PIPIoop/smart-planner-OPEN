from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from confirmation_store import ConfirmationStore
from task_extractor import TaskExtraction


class ConfirmationStoreTest(unittest.TestCase):
    def extraction(self, title: str) -> TaskExtraction:
        return TaskExtraction(
            intent="create_task",
            source_text=title,
            title=title,
            scheduled_date=date(2026, 8, 9),
            confidence=0.9,
        )

    def test_batch_advances_one_task_at_a_time_and_summarizes(self) -> None:
        store = ConfirmationStore(lifetime=timedelta(minutes=15))
        now = datetime(2026, 8, 8, 12, 0)
        first = store.create_batch(
            user_id=7,
            chat_id=11,
            extractions=[self.extraction("Первая"), self.extraction("Вторая")],
            now=now,
        )
        self.assertEqual((first.batch_index, first.batch_total), (0, 2))

        consumed = store.consume(token=first.token, user_id=7, chat_id=11, now=now)
        self.assertIsNotNone(consumed)
        second, summary = store.advance_batch(pending=consumed, saved=True, now=now)
        self.assertIsNone(summary)
        self.assertIsNotNone(second)
        self.assertEqual(second.batch_index, 1)

        consumed_second = store.consume(token=second.token, user_id=7, chat_id=11, now=now)
        _, summary = store.advance_batch(pending=consumed_second, saved=False, now=now)
        self.assertEqual(summary.saved, 1)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.total, 2)

    def test_replaces_current_extraction_without_losing_batch_position(self) -> None:
        store = ConfirmationStore()
        now = datetime(2026, 8, 8, 12, 0)
        pending = store.create_batch(
            user_id=7,
            chat_id=11,
            extractions=[self.extraction("Первая"), self.extraction("Вторая")],
            now=now,
        )
        updated = store.replace_extraction(
            token=pending.token,
            user_id=7,
            chat_id=11,
            extraction=self.extraction("Исправленная"),
            now=now,
        )
        self.assertEqual(updated.extraction.title, "Исправленная")
        self.assertEqual((updated.batch_index, updated.batch_total), (0, 2))


if __name__ == "__main__":
    unittest.main()
