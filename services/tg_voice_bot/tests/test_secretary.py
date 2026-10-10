from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from secretary import (
    SecretarySettings,
    best_free_slots,
    conflict_warning_for_candidate,
    detect_conflicts,
    format_agenda_html,
    free_slots,
    recommendations,
)


class SecretaryTest(unittest.TestCase):
    def task(self, task_id: str, start: int | None, duration: int | None = 60, *, completed: bool = False, task_date: str = "2026-08-03") -> dict[str, object]:
        return {
            "id": task_id,
            "title": f"Задача {task_id}",
            "date": task_date,
            "startMinute": start,
            "durationMinutes": duration if start is not None else None,
            "isCompleted": completed,
        }

    def test_detects_real_overlap_and_ignores_completed_task(self) -> None:
        tasks = [self.task("a", 9 * 60, 90), self.task("b", 10 * 60, 60), self.task("done", 9 * 60, 180, completed=True)]
        conflicts = detect_conflicts(tasks)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual({conflicts[0].first["id"], conflicts[0].second["id"]}, {"a", "b"})

    def test_free_slots_respect_workday_and_fifteen_minute_breaks(self) -> None:
        slots = free_slots([self.task("meeting", 10 * 60, 60)], date(2026, 8, 3))
        self.assertEqual((slots[0].start_minute, slots[0].end_minute), (9 * 60, 9 * 60 + 45))
        self.assertEqual((slots[1].start_minute, slots[1].end_minute), (11 * 60 + 15, 18 * 60))

    def test_recommends_fixing_conflicts_overload_and_outside_hours(self) -> None:
        tasks = [self.task("early", 8 * 60, 240), self.task("overlap", 9 * 60, 300), self.task("late", 15 * 60, 240)]
        advice = " ".join(recommendations(tasks, settings=SecretarySettings()))
        self.assertIn("пересеч", advice)
        self.assertIn("больше рекомендуемых 8 часов", advice)
        self.assertIn("вне рабочего времени", advice)
        self.assertIn("разбить", advice)

    def test_weekly_advice_applies_daily_not_weekly_overload_limit(self) -> None:
        tasks = [
            self.task(
                f"day-{offset}",
                10 * 60,
                120,
                task_date=f"2026-08-{3 + offset:02d}",
            )
            for offset in range(5)
        ]

        advice = " ".join(recommendations(tasks))

        self.assertNotIn("больше рекомендуемых 8 часов", advice)
        self.assertIn("реалистично", advice)
    def test_candidate_warning_and_agenda_are_calendar_grounded(self) -> None:
        existing = [self.task("busy", 10 * 60, 60)]
        candidate = self.task("candidate", 10 * 60 + 30, 60)
        warning = conflict_warning_for_candidate(existing, candidate)
        self.assertIn("Задача busy", warning or "")
        agenda = format_agenda_html(existing, title="Сегодня", groups=[])
        self.assertIn("10:00–11:00", agenda)
        self.assertIn("Рекомендации", agenda)


    def test_best_free_slots_avoid_busy_time_and_respect_deadline(self) -> None:
        tasks = [self.task("busy", 9 * 60, 60)]
        slots = best_free_slots(
            tasks,
            start_date=date(2026, 8, 3),
            end_date=date(2026, 8, 3),
            duration_minutes=120,
            deadline_date=date(2026, 8, 3),
            deadline_minute=13 * 60,
            planning_start_minute=9 * 60,
            planning_end_minute=18 * 60,
        )
        self.assertTrue(slots)
        self.assertTrue(all(slot.start_minute >= 10 * 60 for slot in slots))
        self.assertTrue(all(slot.end_minute <= 13 * 60 for slot in slots))

if __name__ == "__main__":
    unittest.main()