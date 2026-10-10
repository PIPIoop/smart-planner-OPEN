from __future__ import annotations

import hashlib
import sqlite3
from calendar import monthrange
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .models import (
    FinanceAccountBalance,
    FinanceAccountRecord,
    FinanceCategoryRecord,
    FinanceCategorySpend,
    FinanceDailySpend,
    FinanceDebtDirection,
    FinanceDebtRecord,
    FinanceDebtStatus,
    FinancePaymentRecord,
    FinancePeriodReport,
    FinanceRecurrence,
    FinanceSummaryResponse,
    FinanceTransactionRecord,
    FinanceTransactionType,
    FinancialGoalRecord,
)


class FinanceNotFoundError(LookupError):
    pass


class FinanceConflictError(RuntimeError):
    pass


class FinanceValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PaymentSettlementResult:
    transaction: FinanceTransactionRecord
    payment: FinancePaymentRecord
    previous_payment: FinancePaymentRecord
    created: bool

_DEFAULT_CATEGORIES: tuple[tuple[str, str, str, str], ...] = (
    ("food", "Продукты", "#5B8FF9", "shopping_basket"),
    ("transport", "Транспорт", "#61DDAA", "directions_car"),
    ("housing", "Жильё", "#65789B", "home"),
    ("entertainment", "Развлечения", "#F6BD16", "movie"),
    ("subscriptions", "Подписки", "#7262FD", "subscriptions"),
    ("health", "Здоровье", "#E8684A", "health"),
    ("education", "Образование", "#78D3F8", "school"),
    ("shopping", "Покупки", "#9661BC", "shopping_bag"),
    ("other", "Другое", "#A0A7B8", "wallet"),
)


class SqliteFinanceRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = Path(database_path).resolve()
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS finance_accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    opening_balance_cents INTEGER NOT NULL DEFAULT 0,
                    color_hex TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (is_default IN (0, 1)),
                    CHECK (is_archived IN (0, 1))
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS finance_categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    color_hex TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    is_system INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (is_system IN (0, 1))
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS finance_transactions (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    account_id TEXT NOT NULL,
                    to_account_id TEXT,
                    category_id TEXT,
                    note TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CHECK (type IN ('expense', 'income', 'transfer')),
                    CHECK (amount_cents > 0)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS financial_goals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    target_cents INTEGER NOT NULL,
                    saved_cents INTEGER NOT NULL DEFAULT 0,
                    due_date TEXT,
                    linked_account_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (target_cents > 0),
                    CHECK (saved_cents >= 0)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS finance_payments (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    due_date TEXT NOT NULL,
                    recurrence TEXT NOT NULL,
                    recurrence_day INTEGER,
                    account_id TEXT,
                    category_id TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    create_calendar_task INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (amount_cents > 0),
                    CHECK (recurrence IN ('once', 'monthly')),
                    CHECK (is_active IN (0, 1)),
                    CHECK (create_calendar_task IN (0, 1))
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS finance_debts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    person TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    due_date TEXT,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (direction IN ('owed_to_me', 'i_owe')),
                    CHECK (status IN ('open', 'settled')),
                    CHECK (amount_cents > 0)
                )
            """)
            payment_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(finance_payments)")
            }
            if "recurrence_day" not in payment_columns:
                connection.execute("ALTER TABLE finance_payments ADD COLUMN recurrence_day INTEGER")
            connection.execute(
                """UPDATE finance_payments
                   SET recurrence_day=CAST(strftime('%d', due_date) AS INTEGER)
                   WHERE recurrence_day IS NULL"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_finance_transactions_occurred ON finance_transactions(occurred_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_finance_transactions_account ON finance_transactions(account_id, occurred_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_finance_transactions_category ON finance_transactions(category_id, occurred_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_finance_payments_due ON finance_payments(is_active, due_date)")
            now = datetime.now(timezone.utc).isoformat()
            for category_id, name, color, icon in _DEFAULT_CATEGORIES:
                connection.execute(
                    """INSERT OR IGNORE INTO finance_categories
                       (id, name, color_hex, icon, is_system, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (category_id, name, color, icon, now, now),
                )

    def list_accounts(self, *, include_archived: bool = False) -> list[FinanceAccountRecord]:
        where = "" if include_archived else " WHERE is_archived=0"
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM finance_accounts{where} ORDER BY is_default DESC, created_at").fetchall()
        return [self._row_to_account(row) for row in rows]

    def get_account(self, account_id: str) -> FinanceAccountRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM finance_accounts WHERE id=?", (account_id,)).fetchone()
        return None if row is None else self._row_to_account(row)

    def create_account(self, account: FinanceAccountRecord) -> FinanceAccountRecord:
        try:
            with self._connect() as connection:
                if account.is_default:
                    connection.execute("UPDATE finance_accounts SET is_default=0")
                elif connection.execute("SELECT 1 FROM finance_accounts WHERE is_archived=0 LIMIT 1").fetchone() is None:
                    account = account.model_copy(update={"is_default": True})
                connection.execute(
                    """INSERT INTO finance_accounts
                       (id,name,opening_balance_cents,color_hex,is_default,is_archived,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    self._account_params(account),
                )
        except sqlite3.IntegrityError as error:
            raise FinanceConflictError(f"Account {account.id!r} already exists") from error
        return account

    def update_account(self, account: FinanceAccountRecord) -> FinanceAccountRecord:
        with self._connect() as connection:
            if account.is_default:
                connection.execute("UPDATE finance_accounts SET is_default=0 WHERE id<>?", (account.id,))
            cursor = connection.execute(
                """UPDATE finance_accounts SET name=?,opening_balance_cents=?,color_hex=?,is_default=?,is_archived=?,created_at=?,updated_at=? WHERE id=?""",
                (account.name, account.opening_balance_cents, account.color_hex, int(account.is_default), int(account.is_archived), account.created_at.isoformat(), account.updated_at.isoformat(), account.id),
            )
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(account.id)
        return account

    def delete_account(self, account_id: str) -> None:
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM finance_accounts WHERE id=?", (account_id,)).fetchone() is None:
                raise FinanceNotFoundError(account_id)
            if connection.execute("SELECT 1 FROM finance_transactions WHERE account_id=? OR to_account_id=? LIMIT 1", (account_id, account_id)).fetchone() is not None:
                raise FinanceValidationError("Account with transactions cannot be deleted; archive it instead")
            connection.execute("DELETE FROM finance_accounts WHERE id=?", (account_id,))

    def list_categories(self) -> list[FinanceCategoryRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM finance_categories ORDER BY is_system DESC, name COLLATE NOCASE").fetchall()
        return [self._row_to_category(row) for row in rows]

    def get_category(self, category_id: str) -> FinanceCategoryRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM finance_categories WHERE id=?", (category_id,)).fetchone()
        return None if row is None else self._row_to_category(row)

    def create_category(self, category: FinanceCategoryRecord) -> FinanceCategoryRecord:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO finance_categories (id,name,color_hex,icon,is_system,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (category.id, category.name, category.color_hex, category.icon, int(category.is_system), category.created_at.isoformat(), category.updated_at.isoformat()),
                )
        except sqlite3.IntegrityError as error:
            raise FinanceConflictError(f"Category {category.id!r} already exists") from error
        return category

    def list_transactions(self, *, limit: int = 200) -> list[FinanceTransactionRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM finance_transactions ORDER BY occurred_at DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def get_transaction(self, transaction_id: str) -> FinanceTransactionRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM finance_transactions WHERE id=?", (transaction_id,)).fetchone()
        return None if row is None else self._row_to_transaction(row)

    def create_transaction(self, transaction: FinanceTransactionRecord) -> FinanceTransactionRecord:
        if transaction.id.startswith("finance-settle-"):
            raise FinanceValidationError("Transaction ID prefix is reserved for payment settlement")
        self._validate_transaction_refs(transaction)
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO finance_transactions
                       (id,type,amount_cents,account_id,to_account_id,category_id,note,occurred_at,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (transaction.id, transaction.type.value, transaction.amount_cents, transaction.account_id, transaction.to_account_id, transaction.category_id, transaction.note, transaction.occurred_at.isoformat(), transaction.created_at.isoformat()),
                )
        except sqlite3.IntegrityError as error:
            raise FinanceConflictError(f"Transaction {transaction.id!r} already exists") from error
        return transaction

    def delete_transaction(self, transaction_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM finance_transactions WHERE id=?", (transaction_id,))
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(transaction_id)

    def list_goals(self) -> list[FinancialGoalRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM financial_goals ORDER BY due_date IS NULL, due_date, created_at").fetchall()
        return [self._row_to_goal(row) for row in rows]

    def create_goal(self, goal: FinancialGoalRecord) -> FinancialGoalRecord:
        if goal.linked_account_id is not None and self.get_account(goal.linked_account_id) is None:
            raise FinanceValidationError("Linked account does not exist")
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO financial_goals (id,title,target_cents,saved_cents,due_date,linked_account_id,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (goal.id, goal.title, goal.target_cents, goal.saved_cents, goal.due_date.isoformat() if goal.due_date else None, goal.linked_account_id, goal.created_at.isoformat(), goal.updated_at.isoformat()),
                )
        except sqlite3.IntegrityError as error:
            raise FinanceConflictError(f"Goal {goal.id!r} already exists") from error
        return goal

    def update_goal(self, goal: FinancialGoalRecord) -> FinancialGoalRecord:
        if goal.linked_account_id is not None and self.get_account(goal.linked_account_id) is None:
            raise FinanceValidationError("Linked account does not exist")
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE financial_goals SET title=?,target_cents=?,saved_cents=?,due_date=?,linked_account_id=?,created_at=?,updated_at=? WHERE id=?""",
                (goal.title, goal.target_cents, goal.saved_cents, goal.due_date.isoformat() if goal.due_date else None, goal.linked_account_id, goal.created_at.isoformat(), goal.updated_at.isoformat(), goal.id),
            )
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(goal.id)
        return goal

    def delete_goal(self, goal_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM financial_goals WHERE id=?", (goal_id,))
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(goal_id)

    def list_payments(self) -> list[FinancePaymentRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM finance_payments ORDER BY is_active DESC, due_date, created_at").fetchall()
        return [self._row_to_payment(row) for row in rows]

    def create_payment(self, payment: FinancePaymentRecord) -> FinancePaymentRecord:
        self._validate_optional_refs(payment.account_id, payment.category_id)
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO finance_payments (id,title,amount_cents,due_date,recurrence,recurrence_day,account_id,category_id,is_active,create_calendar_task,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    self._payment_params(payment),
                )
        except sqlite3.IntegrityError as error:
            raise FinanceConflictError(f"Payment {payment.id!r} already exists") from error
        return payment

    def update_payment(self, payment: FinancePaymentRecord) -> FinancePaymentRecord:
        self._validate_optional_refs(payment.account_id, payment.category_id)
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE finance_payments SET title=?,amount_cents=?,due_date=?,recurrence=?,recurrence_day=?,account_id=?,category_id=?,is_active=?,create_calendar_task=?,created_at=?,updated_at=? WHERE id=?""",
                (payment.title, payment.amount_cents, payment.due_date.isoformat(), payment.recurrence.value, payment.recurrence_day, payment.account_id, payment.category_id, int(payment.is_active), int(payment.create_calendar_task), payment.created_at.isoformat(), payment.updated_at.isoformat(), payment.id),
            )
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(payment.id)
        return payment

    def delete_payment(self, payment_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM finance_payments WHERE id=?", (payment_id,))
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(payment_id)

    @staticmethod
    def settlement_transaction_id(payment_id: str, expected_due_date: date) -> str:
        digest = hashlib.sha256(
            f"{payment_id}\0{expected_due_date.isoformat()}".encode("utf-8")
        ).hexdigest()[:40]
        return f"finance-settle-{digest}"

    def payment_settlement_exists(self, payment_id: str, expected_due_date: date) -> bool:
        transaction_id = self.settlement_transaction_id(payment_id, expected_due_date)
        return self.get_transaction(transaction_id) is not None

    def settle_payment(
        self,
        payment_id: str,
        expected_due_date: date,
        paid_at: datetime,
    ) -> PaymentSettlementResult:
        transaction_id = self.settlement_transaction_id(payment_id, expected_due_date)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM finance_payments WHERE id=?", (payment_id,)
            ).fetchone()
            if row is None:
                raise FinanceNotFoundError(payment_id)
            previous = self._row_to_payment(row)
            existing = connection.execute(
                "SELECT * FROM finance_transactions WHERE id=?", (transaction_id,)
            ).fetchone()
            if existing is not None:
                stored_transaction = self._row_to_transaction(existing)
                marker = _settlement_marker(payment_id, expected_due_date)
                if marker not in stored_transaction.note:
                    raise FinanceConflictError(
                        "Reserved payment settlement transaction ID is already occupied"
                    )
                return PaymentSettlementResult(
                    transaction=stored_transaction,
                    payment=previous,
                    previous_payment=previous,
                    created=False,
                )
            if not previous.is_active or previous.due_date != expected_due_date:
                raise FinanceConflictError(
                    "Payment due date has changed; refresh finance data before confirming"
                )

            account_id = previous.account_id
            if account_id is None:
                account = connection.execute(
                    """SELECT id FROM finance_accounts
                       WHERE is_archived=0 ORDER BY is_default DESC, created_at LIMIT 1"""
                ).fetchone()
                if account is None:
                    raise FinanceValidationError("Create an account before paying")
                account_id = str(account["id"])
            elif connection.execute(
                "SELECT 1 FROM finance_accounts WHERE id=? AND is_archived=0", (account_id,)
            ).fetchone() is None:
                raise FinanceValidationError("Payment account does not exist or is archived")

            transaction = FinanceTransactionRecord(
                id=transaction_id,
                type=FinanceTransactionType.expense,
                amountCents=previous.amount_cents,
                accountId=account_id,
                toAccountId=None,
                categoryId=previous.category_id,
                note=f"Оплата: {previous.title}\n{_settlement_marker(payment_id, expected_due_date)}",
                occurredAt=paid_at,
                createdAt=paid_at,
            )
            if previous.recurrence is FinanceRecurrence.once:
                updated = previous.model_copy(
                    update={"is_active": False, "updated_at": paid_at}
                )
            else:
                updated = previous.model_copy(
                    update={
                        "due_date": _next_month_same_day(
                            previous.due_date, previous.recurrence_day or previous.due_date.day
                        ),
                        "updated_at": paid_at,
                    }
                )
            connection.execute(
                """INSERT INTO finance_transactions
                   (id,type,amount_cents,account_id,to_account_id,category_id,note,occurred_at,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    transaction.id, transaction.type.value, transaction.amount_cents,
                    transaction.account_id, transaction.to_account_id, transaction.category_id,
                    transaction.note, transaction.occurred_at.isoformat(),
                    transaction.created_at.isoformat(),
                ),
            )
            connection.execute(
                """UPDATE finance_payments SET
                   title=?,amount_cents=?,due_date=?,recurrence=?,recurrence_day=?,
                   account_id=?,category_id=?,is_active=?,create_calendar_task=?,
                   created_at=?,updated_at=? WHERE id=?""",
                (
                    updated.title, updated.amount_cents, updated.due_date.isoformat(),
                    updated.recurrence.value, updated.recurrence_day, updated.account_id,
                    updated.category_id, int(updated.is_active),
                    int(updated.create_calendar_task), updated.created_at.isoformat(),
                    updated.updated_at.isoformat(), updated.id,
                ),
            )
        return PaymentSettlementResult(
            transaction=transaction,
            payment=updated,
            previous_payment=previous,
            created=True,
        )

    def rollback_payment_settlement(self, result: PaymentSettlementResult) -> None:
        if not result.created:
            return
        previous = result.previous_payment
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM finance_transactions WHERE id=?", (result.transaction.id,)
            )
            connection.execute(
                """UPDATE finance_payments SET
                   title=?,amount_cents=?,due_date=?,recurrence=?,recurrence_day=?,
                   account_id=?,category_id=?,is_active=?,create_calendar_task=?,
                   created_at=?,updated_at=? WHERE id=?""",
                (
                    previous.title, previous.amount_cents, previous.due_date.isoformat(),
                    previous.recurrence.value, previous.recurrence_day, previous.account_id,
                    previous.category_id, int(previous.is_active),
                    int(previous.create_calendar_task), previous.created_at.isoformat(),
                    previous.updated_at.isoformat(), previous.id,
                ),
            )
    def list_debts(self) -> list[FinanceDebtRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM finance_debts ORDER BY status, due_date IS NULL, due_date, created_at").fetchall()
        return [self._row_to_debt(row) for row in rows]

    def create_debt(self, debt: FinanceDebtRecord) -> FinanceDebtRecord:
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO finance_debts (id,title,person,direction,amount_cents,due_date,status,note,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    self._debt_params(debt),
                )
        except sqlite3.IntegrityError as error:
            raise FinanceConflictError(f"Debt {debt.id!r} already exists") from error
        return debt

    def update_debt(self, debt: FinanceDebtRecord) -> FinanceDebtRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE finance_debts SET title=?,person=?,direction=?,amount_cents=?,due_date=?,status=?,note=?,created_at=?,updated_at=? WHERE id=?""",
                (debt.title, debt.person, debt.direction.value, debt.amount_cents, debt.due_date.isoformat() if debt.due_date else None, debt.status.value, debt.note, debt.created_at.isoformat(), debt.updated_at.isoformat(), debt.id),
            )
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(debt.id)
        return debt

    def delete_debt(self, debt_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM finance_debts WHERE id=?", (debt_id,))
            if cursor.rowcount != 1:
                raise FinanceNotFoundError(debt_id)

    def account_balance_cents(self, account_id: str) -> int:
        account = self.get_account(account_id)
        if account is None:
            raise FinanceNotFoundError(account_id)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT
                    COALESCE(SUM(CASE
                        WHEN type='income' AND account_id=? THEN amount_cents
                        WHEN type='expense' AND account_id=? THEN -amount_cents
                        WHEN type='transfer' AND account_id=? THEN -amount_cents
                        WHEN type='transfer' AND to_account_id=? THEN amount_cents
                        ELSE 0 END), 0) AS delta
                    FROM finance_transactions""",
                (account_id, account_id, account_id, account_id),
            ).fetchone()
        return account.opening_balance_cents + int(row["delta"] or 0)

    def summary(self, *, today: date | None = None) -> FinanceSummaryResponse:
        today = today or datetime.now(timezone.utc).date()
        month_start = today.replace(day=1)
        if month_start.month == 1:
            prev_start = month_start.replace(year=month_start.year - 1, month=12)
        else:
            prev_start = month_start.replace(month=month_start.month - 1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        accounts = self.list_accounts()
        account_balances = [FinanceAccountBalance(account=a, balanceCents=self.account_balance_cents(a.id)) for a in accounts]
        total_balance = sum(item.balance_cents for item in account_balances)
        with self._connect() as connection:
            expense_rows = connection.execute(
                """SELECT date(occurred_at) AS day, category_id, SUM(amount_cents) AS amount
                   FROM finance_transactions
                   WHERE type='expense' AND date(occurred_at)>=? AND date(occurred_at)<?
                   GROUP BY day, category_id ORDER BY day""",
                (month_start.isoformat(), next_month.isoformat()),
            ).fetchall()
            previous = connection.execute(
                """SELECT COALESCE(SUM(amount_cents),0) AS amount FROM finance_transactions
                   WHERE type='expense' AND date(occurred_at)>=? AND date(occurred_at)<?""",
                (prev_start.isoformat(), month_start.isoformat()),
            ).fetchone()
        categories = {category.id: category for category in self.list_categories()}
        by_day: dict[date, int] = {}
        by_category: dict[str | None, int] = {}
        for row in expense_rows:
            day = date.fromisoformat(row["day"])
            amount = int(row["amount"] or 0)
            by_day[day] = by_day.get(day, 0) + amount
            category_id = row["category_id"]
            by_category[category_id] = by_category.get(category_id, 0) + amount
        month_expense = sum(by_day.values())
        today_expense = by_day.get(today, 0)
        average = month_expense // max(1, today.day)
        category_spend = []
        for category_id, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True):
            category = categories.get(category_id) if category_id is not None else None
            category_spend.append(FinanceCategorySpend(
                categoryId=category_id,
                name=category.name if category else "Без категории",
                colorHex=category.color_hex if category else "#A0A7B8",
                amountCents=amount,
            ))
        goals = []
        for goal in self.list_goals():
            if goal.linked_account_id is not None:
                try:
                    linked_balance = max(0, self.account_balance_cents(goal.linked_account_id))
                    goal = goal.model_copy(update={"saved_cents": linked_balance})
                except FinanceNotFoundError:
                    pass
            goals.append(goal)
        return FinanceSummaryResponse(
            totalBalanceCents=total_balance,
            monthExpenseCents=month_expense,
            previousMonthExpenseCents=int(previous["amount"] or 0),
            todayExpenseCents=today_expense,
            averageDailyExpenseCents=average,
            accounts=account_balances,
            categorySpend=category_spend,
            dailySpend=[FinanceDailySpend(date=day, amountCents=by_day[day]) for day in sorted(by_day)],
            goals=goals,
            payments=[p for p in self.list_payments() if p.is_active],
            debts=[d for d in self.list_debts() if d.status is FinanceDebtStatus.open],
            recentTransactions=self.list_transactions(limit=12),
        )

    def period_report(self, *, start: date, end: date, period: str) -> FinancePeriodReport:
        if end < start:
            raise FinanceValidationError("Report end date cannot be before start date")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT date(occurred_at) AS day, category_id, SUM(amount_cents) AS amount
                   FROM finance_transactions
                   WHERE type='expense' AND date(occurred_at)>=? AND date(occurred_at)<=?
                   GROUP BY day, category_id ORDER BY day""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        categories = {category.id: category for category in self.list_categories()}
        by_day: dict[date, int] = {}
        by_category: dict[str | None, int] = {}
        for row in rows:
            day = date.fromisoformat(row["day"])
            amount = int(row["amount"] or 0)
            by_day[day] = by_day.get(day, 0) + amount
            category_id = row["category_id"]
            by_category[category_id] = by_category.get(category_id, 0) + amount
        category_spend: list[FinanceCategorySpend] = []
        for category_id, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True):
            category = categories.get(category_id) if category_id is not None else None
            category_spend.append(FinanceCategorySpend(
                categoryId=category_id,
                name=category.name if category else "Без категории",
                colorHex=category.color_hex if category else "#A0A7B8",
                amountCents=amount,
            ))
        expense = sum(by_day.values())
        days = max(1, (end - start).days + 1)
        return FinancePeriodReport(
            period=period,
            startDate=start,
            endDate=end,
            totalBalanceCents=sum(self.account_balance_cents(account.id) for account in self.list_accounts()),
            expenseCents=expense,
            averageDailyExpenseCents=expense // days,
            categorySpend=category_spend,
            dailySpend=[FinanceDailySpend(date=day, amountCents=by_day[day]) for day in sorted(by_day)],
        )

    def _validate_transaction_refs(self, transaction: FinanceTransactionRecord) -> None:
        if self.get_account(transaction.account_id) is None:
            raise FinanceValidationError("Source account does not exist")
        if transaction.to_account_id is not None and self.get_account(transaction.to_account_id) is None:
            raise FinanceValidationError("Destination account does not exist")
        if transaction.category_id is not None and self.get_category(transaction.category_id) is None:
            raise FinanceValidationError("Category does not exist")

    def _validate_optional_refs(self, account_id: str | None, category_id: str | None) -> None:
        if account_id is not None and self.get_account(account_id) is None:
            raise FinanceValidationError("Account does not exist")
        if category_id is not None and self.get_category(category_id) is None:
            raise FinanceValidationError("Category does not exist")

    @staticmethod
    def _account_params(account: FinanceAccountRecord) -> tuple[object, ...]:
        return (account.id, account.name, account.opening_balance_cents, account.color_hex, int(account.is_default), int(account.is_archived), account.created_at.isoformat(), account.updated_at.isoformat())

    @staticmethod
    def _payment_params(payment: FinancePaymentRecord) -> tuple[object, ...]:
        return (payment.id, payment.title, payment.amount_cents, payment.due_date.isoformat(), payment.recurrence.value, payment.recurrence_day, payment.account_id, payment.category_id, int(payment.is_active), int(payment.create_calendar_task), payment.created_at.isoformat(), payment.updated_at.isoformat())

    @staticmethod
    def _debt_params(debt: FinanceDebtRecord) -> tuple[object, ...]:
        return (debt.id, debt.title, debt.person, debt.direction.value, debt.amount_cents, debt.due_date.isoformat() if debt.due_date else None, debt.status.value, debt.note, debt.created_at.isoformat(), debt.updated_at.isoformat())

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> FinanceAccountRecord:
        return FinanceAccountRecord(id=row["id"], name=row["name"], openingBalanceCents=row["opening_balance_cents"], colorHex=row["color_hex"], isDefault=bool(row["is_default"]), isArchived=bool(row["is_archived"]), createdAt=row["created_at"], updatedAt=row["updated_at"])

    @staticmethod
    def _row_to_category(row: sqlite3.Row) -> FinanceCategoryRecord:
        return FinanceCategoryRecord(id=row["id"], name=row["name"], colorHex=row["color_hex"], icon=row["icon"], isSystem=bool(row["is_system"]), createdAt=row["created_at"], updatedAt=row["updated_at"])

    @staticmethod
    def _row_to_transaction(row: sqlite3.Row) -> FinanceTransactionRecord:
        return FinanceTransactionRecord(id=row["id"], type=FinanceTransactionType(row["type"]), amountCents=row["amount_cents"], accountId=row["account_id"], toAccountId=row["to_account_id"], categoryId=row["category_id"], note=row["note"], occurredAt=row["occurred_at"], createdAt=row["created_at"])

    @staticmethod
    def _row_to_goal(row: sqlite3.Row) -> FinancialGoalRecord:
        return FinancialGoalRecord(id=row["id"], title=row["title"], targetCents=row["target_cents"], savedCents=row["saved_cents"], dueDate=row["due_date"], linkedAccountId=row["linked_account_id"], createdAt=row["created_at"], updatedAt=row["updated_at"])

    @staticmethod
    def _row_to_payment(row: sqlite3.Row) -> FinancePaymentRecord:
        return FinancePaymentRecord(id=row["id"], title=row["title"], amountCents=row["amount_cents"], dueDate=row["due_date"], recurrence=FinanceRecurrence(row["recurrence"]), recurrenceDay=row["recurrence_day"], accountId=row["account_id"], categoryId=row["category_id"], isActive=bool(row["is_active"]), createCalendarTask=bool(row["create_calendar_task"]), createdAt=row["created_at"], updatedAt=row["updated_at"])

    @staticmethod
    def _row_to_debt(row: sqlite3.Row) -> FinanceDebtRecord:
        return FinanceDebtRecord(id=row["id"], title=row["title"], person=row["person"], direction=FinanceDebtDirection(row["direction"]), amountCents=row["amount_cents"], dueDate=row["due_date"], status=FinanceDebtStatus(row["status"]), note=row["note"], createdAt=row["created_at"], updatedAt=row["updated_at"])


def _next_month_same_day(value: date, preferred_day: int) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return date(year, month, min(preferred_day, monthrange(year, month)[1]))

def _settlement_marker(payment_id: str, expected_due_date: date) -> str:
    return f"[finance-settlement:{payment_id}:{expected_due_date.isoformat()}]"