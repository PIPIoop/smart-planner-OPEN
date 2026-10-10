from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from finance_intent import detect_finance_query, extract_finance_intent


class FinanceIntentTest(unittest.TestCase):
    def test_extract_expense_and_category(self) -> None:
        intent = extract_finance_intent("Потратил 1450 рублей на продукты")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.kind, "expense")
        self.assertEqual(intent.amount_cents, 145_000)
        self.assertEqual(intent.category_hint, "food")

    def test_extract_transfer_with_thousands(self) -> None:
        intent = extract_finance_intent("Перевёл 20 тысяч на накопительный")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.kind, "transfer")
        self.assertEqual(intent.amount_cents, 2_000_000)
        self.assertEqual(intent.to_account_hint, "накопительный")

    def test_detect_queries(self) -> None:
        self.assertEqual(detect_finance_query("Сколько осталось денег?"), "balance")
        self.assertEqual(
            detect_finance_query("Сколько я потратил в этом месяце?"),
            "month_expense",
        )
        self.assertEqual(
            detect_finance_query("На что больше всего трачу?"),
            "top_categories",
        )

    def test_extract_expense_preserves_kopeks_exactly(self) -> None:
        intent = extract_finance_intent("Потратил 1250,75 рублей на продукты")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.amount_cents, 125_075)

    def test_task_command_time_is_not_a_finance_operation(self) -> None:
        self.assertIsNone(extract_finance_intent("Запиши встречу завтра в 10:00"))

    def test_calendar_date_is_not_used_as_money(self) -> None:
        self.assertIsNone(extract_finance_intent("Купил билеты, напомни 15 августа"))
        self.assertIsNone(extract_finance_intent("Оплатил подписку, проверить 2026-08-15"))

if __name__ == "__main__":
    unittest.main()