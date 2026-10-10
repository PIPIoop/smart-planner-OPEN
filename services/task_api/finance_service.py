from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from .finance_repository import FinanceNotFoundError, SqliteFinanceRepository
from .models import (
    FinanceAccountRecord,
    FinanceCategoryRecord,
    FinanceDebtRecord,
    FinancePaymentRecord,
    FinancePaymentSettlementResponse,
    FinancePeriodReport,
    FinanceRecurrence,
    FinanceSummaryResponse,
    FinanceTransactionRecord,
    FinancialGoalRecord,
    TaskPriority,
    TaskRecord,
)
from .repository import TaskConflictError, TaskRepository


def _format_rubles(cents: int) -> str:
    negative = cents < 0
    absolute = abs(cents)
    rubles, kopeks = divmod(absolute, 100)
    grouped = f"{rubles:,}".replace(",", " ")
    fraction = "" if kopeks == 0 else f",{kopeks:02d}"
    return f"{'−' if negative else ''}{grouped}{fraction} ₽"


_PAYMENT_LOCKS: dict[Path, RLock] = {}
_PAYMENT_LOCKS_GUARD = RLock()


def _payment_lock(database_path: Path) -> RLock:
    with _PAYMENT_LOCKS_GUARD:
        return _PAYMENT_LOCKS.setdefault(database_path.resolve(), RLock())

class FinanceService:
    def __init__(self, task_repository: TaskRepository) -> None:
        database_path = getattr(task_repository, "database_path", None)
        if database_path is None:
            raise RuntimeError("Finance requires a SQLite-backed task repository")
        self._task_repository = task_repository
        resolved_path = Path(database_path).resolve()
        self._repository = SqliteFinanceRepository(resolved_path)
        self._payment_operation_lock = _payment_lock(resolved_path)

    def summary(self) -> FinanceSummaryResponse:
        return self._repository.summary()

    def period_report(self, period: str) -> FinancePeriodReport:
        today = datetime.now(timezone.utc).date()
        if period == "day":
            start = today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
        elif period == "month":
            start = today.replace(day=1)
        elif period == "year":
            start = today.replace(month=1, day=1)
        else:
            raise ValueError("Unsupported finance report period")
        return self._repository.period_report(start=start, end=today, period=period)

    def list_accounts(self) -> list[FinanceAccountRecord]:
        return self._repository.list_accounts()

    def create_account(self, account: FinanceAccountRecord) -> FinanceAccountRecord:
        return self._repository.create_account(account)

    def update_account(self, account: FinanceAccountRecord) -> FinanceAccountRecord:
        return self._repository.update_account(account)

    def delete_account(self, account_id: str) -> None:
        self._repository.delete_account(account_id)

    def list_categories(self) -> list[FinanceCategoryRecord]:
        return self._repository.list_categories()

    def create_category(self, category: FinanceCategoryRecord) -> FinanceCategoryRecord:
        return self._repository.create_category(category)

    def list_transactions(self, limit: int = 200) -> list[FinanceTransactionRecord]:
        return self._repository.list_transactions(limit=limit)

    def create_transaction(self, transaction: FinanceTransactionRecord) -> FinanceTransactionRecord:
        return self._repository.create_transaction(transaction)

    def delete_transaction(self, transaction_id: str) -> None:
        self._repository.delete_transaction(transaction_id)

    def list_goals(self) -> list[FinancialGoalRecord]:
        return self._repository.list_goals()

    def create_goal(self, goal: FinancialGoalRecord) -> FinancialGoalRecord:
        return self._repository.create_goal(goal)

    def update_goal(self, goal: FinancialGoalRecord) -> FinancialGoalRecord:
        return self._repository.update_goal(goal)

    def delete_goal(self, goal_id: str) -> None:
        self._repository.delete_goal(goal_id)

    def list_payments(self) -> list[FinancePaymentRecord]:
        return self._repository.list_payments()

    def create_payment(self, payment: FinancePaymentRecord) -> FinancePaymentRecord:
        with self._payment_operation_lock:
            result = self._repository.create_payment(payment)
            try:
                self._sync_payment_tasks(result)
            except Exception:
                self._repository.delete_payment(result.id)
                raise
            return result

    def update_payment(self, payment: FinancePaymentRecord) -> FinancePaymentRecord:
        with self._payment_operation_lock:
            previous = self._payment(payment.id)
            result = self._repository.update_payment(payment)
            try:
                self._sync_payment_tasks(result)
            except Exception:
                self._repository.update_payment(previous)
                raise
            return result

    def payment_settlement_exists(self, payment_id: str, expected_due_date: date) -> bool:
        return self._repository.payment_settlement_exists(payment_id, expected_due_date)

    def settle_payment(
        self,
        payment_id: str,
        expected_due_date: date,
        paid_at: datetime,
    ) -> FinancePaymentSettlementResponse:
        with self._payment_operation_lock:
            result = self._repository.settle_payment(
                payment_id, expected_due_date, paid_at
            )
            if result.created:
                try:
                    self._sync_payment_tasks(result.payment)
                except Exception:
                    self._repository.rollback_payment_settlement(result)
                    raise
            return FinancePaymentSettlementResponse(
                transaction=result.transaction,
                payment=result.payment,
                created=result.created,
            )

    def delete_payment(self, payment_id: str) -> None:
        with self._payment_operation_lock:
            self._payment(payment_id)
            marker = self._payment_marker(payment_id)
            prefix = self._payment_task_prefix(payment_id)
            previous_tasks = [
                task
                for task in self._task_repository.list_all()
                if self._is_payment_task(task, payment_id)
            ]
            self._task_repository.replace_generated_tasks(
                id_prefix=prefix,
                note_marker=marker,
                tasks=[],
            )
            try:
                self._repository.delete_payment(payment_id)
            except Exception:
                self._task_repository.replace_generated_tasks(
                    id_prefix=prefix,
                    note_marker=marker,
                    tasks=previous_tasks,
                )
                raise

    def list_debts(self) -> list[FinanceDebtRecord]:
        return self._repository.list_debts()

    def create_debt(self, debt: FinanceDebtRecord) -> FinanceDebtRecord:
        return self._repository.create_debt(debt)

    def update_debt(self, debt: FinanceDebtRecord) -> FinanceDebtRecord:
        return self._repository.update_debt(debt)

    def delete_debt(self, debt_id: str) -> None:
        self._repository.delete_debt(debt_id)

    def _payment(self, payment_id: str) -> FinancePaymentRecord:
        for payment in self._repository.list_payments():
            if payment.id == payment_id:
                return payment
        raise FinanceNotFoundError(payment_id)

    @staticmethod
    def _payment_task_prefix(payment_id: str) -> str:
        return f"finance-payment-{payment_id}-"
    @staticmethod
    def _payment_marker(payment_id: str) -> str:
        return f"[finance-payment:{payment_id}]"

    @classmethod
    def _is_payment_task(cls, task: TaskRecord, payment_id: str) -> bool:
        return (
            task.id.startswith(cls._payment_task_prefix(payment_id))
            and cls._payment_marker(payment_id) in task.note
        )

    def _sync_payment_tasks(self, payment: FinancePaymentRecord) -> None:
        self._task_repository.replace_generated_tasks(
            id_prefix=self._payment_task_prefix(payment.id),
            note_marker=self._payment_marker(payment.id),
            tasks=self._build_payment_tasks(payment),
        )

    def _build_payment_tasks(self, payment: FinancePaymentRecord) -> list[TaskRecord]:
        if not payment.is_active or not payment.create_calendar_task:
            return []
        dates = [payment.due_date]
        if payment.recurrence is FinanceRecurrence.monthly:
            cursor = payment.due_date
            for _ in range(11):
                cursor = _next_month_same_day(cursor, payment.recurrence_day or payment.due_date.day)
                dates.append(cursor)
        now = datetime.now(timezone.utc)
        marker = self._payment_marker(payment.id)
        return [
            TaskRecord(
                id=f"finance-payment-{payment.id}-{due.isoformat()}",
                title=f"Оплатить: {payment.title}",
                note=(
                    "Создано автоматически из раздела «Финансы».\n"
                    f"Сумма: {_format_rubles(payment.amount_cents)}\n"
                    f"{marker}"
                ),
                date=due,
                startMinute=None,
                durationMinutes=None,
                deadlineDate=due,
                deadlineMinute=None,
                priority=TaskPriority.normal,
                isCompleted=False,
                goalId=None,
                goalOccurrenceDate=None,
                completedAt=None,
                groupId=None,
                createdAt=now,
                updatedAt=now,
            )
            for due in dates
        ]


def _next_month_same_day(value: date, preferred_day: int) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(preferred_day, monthrange(year, month)[1])
    return date(year, month, day)