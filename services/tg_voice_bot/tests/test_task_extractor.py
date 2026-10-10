from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from task_extractor import TaskExtractor


class TaskExtractorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.timezone = ZoneInfo("Asia/Yekaterinburg")
        self.extractor = TaskExtractor(timezone=self.timezone)
        self.reference = datetime(2026, 8, 3, 10, 15, tzinfo=self.timezone)

    def test_relative_hours_preserve_calculated_time(self) -> None:
        result = self.extractor.extract(
            "Через два часа проверить документы",
            reference_datetime=self.reference,
        )

        self.assertEqual(result.scheduled_date.isoformat(), "2026-08-03")
        self.assertEqual(result.scheduled_time.strftime("%H:%M"), "12:15")
        self.assertEqual(result.title, "Проверить документы")
        self.assertNotIn("time_not_found", result.warnings)

    def test_explicit_date_and_time(self) -> None:
        result = self.extractor.extract(
            "Добавь завтра в 18:30 тренировку",
            reference_datetime=self.reference,
        )

        self.assertEqual(result.scheduled_date.isoformat(), "2026-08-04")
        self.assertEqual(result.scheduled_time.strftime("%H:%M"), "18:30")
        self.assertEqual(result.title, "Тренировку")


    def test_numeric_time_range_produces_duration(self) -> None:
        result = self.extractor.extract(
            "завтра с 10:00 до 12:00 я буду на работе",
            reference_datetime=self.reference,
        )

        self.assertEqual(result.schema_version, "1.2")
        self.assertEqual(result.scheduled_date.isoformat(), "2026-08-04")
        self.assertEqual(result.scheduled_time.strftime("%H:%M"), "10:00")
        self.assertEqual(result.scheduled_end_time.strftime("%H:%M"), "12:00")
        self.assertEqual(result.duration_minutes, 120)
        self.assertEqual(result.title, "Я буду на работе")

    def test_spoken_time_range_produces_duration(self) -> None:
        result = self.extractor.extract(
            "завтра с десяти ноль ноль до двенадцати ноль ноль я буду на работе",
            reference_datetime=self.reference,
        )

        self.assertEqual(result.scheduled_time.strftime("%H:%M"), "10:00")
        self.assertEqual(result.scheduled_end_time.strftime("%H:%M"), "12:00")
        self.assertEqual(result.duration_minutes, 120)
        self.assertEqual(result.title, "Я буду на работе")

    def test_reversed_time_range_requires_clarification(self) -> None:
        result = self.extractor.extract(
            "завтра с 12:00 до 10:00 работа",
            reference_datetime=self.reference,
        )

        self.assertEqual(result.intent, "unknown")
        self.assertIn("invalid_time_range", result.warnings)
        self.assertIn("позже", result.clarification_question or "")

    def test_extracts_multiple_tasks_with_shared_date_and_deadline(self) -> None:
        results = self.extractor.extract_many(
            "завтра в 10 стоматолог, после него заехать в магазин, вечером час английского и не забыть отправить отчёт до 18",
            reference_datetime=self.reference,
        )

        self.assertEqual(len(results), 4)
        self.assertEqual(results[0].scheduled_time.strftime("%H:%M"), "10:00")
        self.assertTrue(all(item.scheduled_date.isoformat() == "2026-08-04" for item in results))
        self.assertEqual(results[2].duration_minutes, 60)
        self.assertTrue(results[2].time_is_flexible)
        self.assertEqual(results[3].title, "Отправить отчёт")
        self.assertEqual(results[3].deadline_time.strftime("%H:%M"), "18:00")

    def test_extracts_common_compound_durations(self) -> None:
        one_half = self.extractor.extract(
            "Завтра полтора часа тренировка",
            reference_datetime=self.reference,
        )
        compound = self.extractor.extract(
            "Завтра поработать 1 час 30 минут",
            reference_datetime=self.reference,
        )

        self.assertEqual(one_half.duration_minutes, 90)
        self.assertEqual(compound.duration_minutes, 90)

    def test_deadline_clock_is_not_mistaken_for_start_time(self) -> None:
        result = self.extractor.extract(
            "Срочно отправить отчёт до пятницы до 18:00",
            reference_datetime=self.reference,
        )

        self.assertEqual(result.priority, "high")
        self.assertEqual(result.deadline_date, date(2026, 8, 7))
        self.assertEqual(result.deadline_time, time(18, 0))
        self.assertIsNone(result.scheduled_time)

    def test_extracts_priority_deadline_and_flexible_duration(self) -> None:
        deadline = self.extractor.extract(
            "до пятницы срочно отправить отчёт",
            reference_datetime=self.reference,
        )
        self.assertEqual(deadline.priority, "high")
        self.assertEqual(deadline.deadline_date.isoformat(), "2026-08-07")
        self.assertEqual(deadline.scheduled_date, deadline.deadline_date)

        flexible = self.extractor.extract(
            "завтра поработать над проектом 2 часа",
            reference_datetime=self.reference,
        )
        self.assertIsNone(flexible.scheduled_time)
        self.assertEqual(flexible.duration_minutes, 120)
        self.assertEqual(flexible.title, "Поработать над проектом")

if __name__ == "__main__":
    unittest.main()