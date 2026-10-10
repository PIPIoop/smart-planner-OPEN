from __future__ import annotations

import sys
import unittest
from datetime import date, time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from bot import _format_confirmed_task, _format_extraction_preview
from task_extractor import TaskExtraction


class BotFormattingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.extraction = TaskExtraction(
            intent="create_task",
            source_text="завтра с 10:00 до 12:00 я буду на работе",
            title="Я буду на работе",
            scheduled_date=date(2026, 8, 4),
            scheduled_time=time(10, 0),
            scheduled_end_time=time(12, 0),
            duration_minutes=120,
            confidence=1.0,
        )

    def test_preview_shows_range_and_duration(self) -> None:
        text = _format_extraction_preview(
            transcription=self.extraction.source_text,
            extraction=self.extraction,
        )
        self.assertIn("10:00–12:00", text)
        self.assertIn("Длительность:</b> 2 ч", text)

    def test_confirmation_shows_range_and_duration(self) -> None:
        text = _format_confirmed_task(self.extraction, task_id="task-1")
        self.assertIn("10:00–12:00", text)
        self.assertIn("Длительность:</b> 2 ч", text)


if __name__ == "__main__":
    unittest.main()