from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from report_renderer import build_report, format_report_html, render_report_png


class ReportRendererTest(unittest.TestCase):
    def test_week_report_counts_statuses_groups_and_renders_png(self) -> None:
        tasks = [
            {"date": "2026-08-03", "isCompleted": True, "completedAt": "2026-08-03T10:00:00+00:00", "groupId": "work"},
            {"date": "2026-08-04", "isCompleted": True, "completedAt": "2026-08-06T10:00:00+00:00", "groupId": "work"},
            {"date": "2026-08-05", "isCompleted": False, "completedAt": None, "groupId": None},
            {"date": "2026-08-09", "isCompleted": False, "completedAt": None, "groupId": None},
            {"date": "2026-07-31", "isCompleted": True, "completedAt": "2026-07-31T10:00:00+00:00", "groupId": "work"},
        ]
        tasks.extend([
            {
                "date": "2026-08-03",
                "isCompleted": True,
                "completedAt": "2026-08-03T08:30:00+05:00",
                "startMinute": 480,
                "durationMinutes": 90,
                "goalId": "reading",
                "goalOccurrenceDate": "2026-08-03",
            },
            {
                "date": "2026-08-05",
                "isCompleted": False,
                "completedAt": None,
                "goalId": "reading",
                "goalOccurrenceDate": "2026-08-05",
            },
        ])
        groups = [{"id": "work", "name": "Работа", "colorHex": "#3B82F6"}]
        goals = [{
            "id": "reading",
            "title": "Читать 30 минут",
            "startDate": "2026-08-03",
            "endDate": "2026-08-09",
            "intervalDays": 2,
        }]
        report = build_report(
            tasks=tasks,
            groups=groups,
            goals=goals,
            period="week",
            now=datetime(2026, 8, 6, 12, tzinfo=ZoneInfo("Asia/Yekaterinburg")),
        )
        self.assertEqual((report.total, report.completed, report.on_time, report.late, report.missed, report.pending), (6, 3, 2, 1, 2, 1))
        self.assertEqual(len(report.habits), 1)
        self.assertEqual(report.habits[0].states[:4], ("completed", "none", "missed", "none"))
        self.assertGreater(max(value for row in report.focus_matrix for value in row), 0.0)
        self.assertIn("Работа: 2/2", format_report_html(report))
        image = render_report_png(report)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(image), 10_000)

    def test_month_report_supports_empty_period(self) -> None:
        report = build_report(tasks=[], groups=[], period="month", now=datetime(2026, 8, 3))
        self.assertEqual(report.total, 0)
        self.assertEqual(report.completion_rate, 0.0)
        self.assertIn("0%", format_report_html(report))


if __name__ == "__main__":
    unittest.main()