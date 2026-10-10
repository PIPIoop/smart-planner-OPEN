from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class _TaskFields(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=1000)
    date: date
    start_minute: int | None = Field(default=None, alias="startMinute", ge=0, le=1439)
    duration_minutes: int | None = Field(default=None, alias="durationMinutes", ge=15, le=1440)
    deadline_date: date | None = Field(default=None, alias="deadlineDate")
    deadline_minute: int | None = Field(default=None, alias="deadlineMinute", ge=0, le=1439)
    priority: TaskPriority = TaskPriority.normal
    is_completed: bool = Field(default=False, alias="isCompleted")
    goal_id: str | None = Field(default=None, alias="goalId", max_length=128)
    goal_occurrence_date: date | None = Field(default=None, alias="goalOccurrenceDate")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    group_id: str | None = Field(default=None, alias="groupId", max_length=128)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Task title cannot be empty")
        return normalized

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("completedAt must contain a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def completion_is_consistent(self) -> "_TaskFields":
        if self.start_minute is None and self.duration_minutes is not None:
            raise ValueError("durationMinutes requires startMinute")
        if self.deadline_minute is not None and self.deadline_date is None:
            raise ValueError("deadlineMinute requires deadlineDate")
        if self.start_minute is not None and self.duration_minutes is None:
            self.duration_minutes = 60
        if self.duration_minutes is not None:
            if self.duration_minutes % 15 != 0:
                raise ValueError("durationMinutes must use 15-minute steps")
            if self.start_minute is not None and self.start_minute + self.duration_minutes > 1440:
                raise ValueError("Task duration must end within the same day")
        if (self.goal_id is None) != (self.goal_occurrence_date is None):
            raise ValueError("goalId and goalOccurrenceDate must be specified together")
        if self.is_completed != (self.completed_at is not None):
            raise ValueError("isCompleted and completedAt must be consistent")
        return self


class TaskCreateRequest(_TaskFields):
    id: str | None = Field(default=None, min_length=1, max_length=128)
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Task timestamps must contain a timezone")
        return value.astimezone(timezone.utc)


class TaskRecord(_TaskFields):
    id: str = Field(min_length=1, max_length=128)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Task timestamps must contain a timezone")
        return value.astimezone(timezone.utc)


class GoalRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=1000)
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    interval_days: int = Field(alias="intervalDays", ge=1, le=365)
    task_title: str = Field(alias="taskTitle", min_length=1, max_length=120)
    task_note: str = Field(default="", alias="taskNote", max_length=1000)
    task_start_minute: int | None = Field(default=None, alias="taskStartMinute", ge=0, le=1439)
    task_duration_minutes: int | None = Field(default=None, alias="taskDurationMinutes", ge=15, le=1440)
    task_priority: TaskPriority = Field(default=TaskPriority.normal, alias="taskPriority")
    task_group_id: str | None = Field(default=None, alias="taskGroupId", max_length=128)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("title", "task_title")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Goal titles must not be blank")
        return normalized

    @field_validator("note", "task_note")
    @classmethod
    def normalize_notes(cls, value: str) -> str:
        return value.strip()

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_goal_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Goal timestamps must contain a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_period(self) -> "GoalRecord":
        if self.end_date < self.start_date:
            raise ValueError("endDate must not be before startDate")
        if self.task_start_minute is None and self.task_duration_minutes is not None:
            raise ValueError("taskDurationMinutes requires taskStartMinute")
        if self.task_start_minute is not None and self.task_duration_minutes is None:
            self.task_duration_minutes = 60
        if self.task_duration_minutes is not None:
            if self.task_duration_minutes % 15 != 0:
                raise ValueError("taskDurationMinutes must use 15-minute steps")
            if self.task_start_minute is not None and self.task_start_minute + self.task_duration_minutes > 1440:
                raise ValueError("Goal task duration must end within the same day")
        return self


class TaskGroupRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=60)
    color_hex: str = Field(alias="colorHex", pattern=r"^#[0-9A-Fa-f]{6}$")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Group name cannot be empty")
        return normalized

    @field_validator("color_hex")
    @classmethod
    def normalize_color(cls, value: str) -> str:
        return value.upper()

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_group_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Group timestamps must contain a timezone")
        return value.astimezone(timezone.utc)

class GoalCreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: GoalRecord
    tasks: list[TaskRecord] = Field(min_length=1, max_length=1000)


class GoalCreationResponse(GoalCreationRequest):
    pass


class TaskReplacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[TaskRecord]


class PlannerDataReplacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[TaskRecord]
    goals: list[GoalRecord]
    groups: list[TaskGroupRecord]


class HealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    status: str
    schema_version: int = Field(alias="schemaVersion")
class FinanceTransactionType(str, Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"


class FinanceRecurrence(str, Enum):
    once = "once"
    monthly = "monthly"


class FinanceDebtDirection(str, Enum):
    owed_to_me = "owed_to_me"
    i_owe = "i_owe"


class FinanceDebtStatus(str, Enum):
    open = "open"
    settled = "settled"


class FinanceAccountRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    opening_balance_cents: int = Field(default=0, alias="openingBalanceCents")
    color_hex: str = Field(default="#5B47F7", alias="colorHex", pattern=r"^#[0-9A-Fa-f]{6}$")
    is_default: bool = Field(default=False, alias="isDefault")
    is_archived: bool = Field(default=False, alias="isArchived")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("name")
    @classmethod
    def normalize_account_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Account name cannot be empty")
        return normalized

    @field_validator("color_hex")
    @classmethod
    def normalize_account_color(cls, value: str) -> str:
        return value.upper()

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_account_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Finance account timestamps must contain a timezone")
        return value.astimezone(timezone.utc)


class FinanceCategoryRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=60)
    color_hex: str = Field(alias="colorHex", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str = Field(default="wallet", min_length=1, max_length=40)
    is_system: bool = Field(default=False, alias="isSystem")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("name")
    @classmethod
    def normalize_category_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Category name cannot be empty")
        return normalized

    @field_validator("color_hex")
    @classmethod
    def normalize_category_color(cls, value: str) -> str:
        return value.upper()

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_category_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Finance category timestamps must contain a timezone")
        return value.astimezone(timezone.utc)


class FinanceTransactionRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: FinanceTransactionType
    amount_cents: int = Field(alias="amountCents", gt=0)
    account_id: str = Field(alias="accountId", min_length=1, max_length=128)
    to_account_id: str | None = Field(default=None, alias="toAccountId", max_length=128)
    category_id: str | None = Field(default=None, alias="categoryId", max_length=128)
    note: str = Field(default="", max_length=500)
    occurred_at: datetime = Field(alias="occurredAt")
    created_at: datetime = Field(alias="createdAt")

    @field_validator("note")
    @classmethod
    def normalize_transaction_note(cls, value: str) -> str:
        return value.strip()

    @field_validator("occurred_at", "created_at")
    @classmethod
    def normalize_transaction_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Finance transaction timestamps must contain a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_transaction_shape(self) -> "FinanceTransactionRecord":
        if self.type is FinanceTransactionType.transfer:
            if self.to_account_id is None:
                raise ValueError("Transfer requires toAccountId")
            if self.to_account_id == self.account_id:
                raise ValueError("Transfer accounts must be different")
            if self.category_id is not None:
                raise ValueError("Transfer cannot have a category")
        elif self.to_account_id is not None:
            raise ValueError("toAccountId is only valid for transfers")
        return self


class FinancialGoalRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    target_cents: int = Field(alias="targetCents", gt=0)
    saved_cents: int = Field(default=0, alias="savedCents", ge=0)
    due_date: date | None = Field(default=None, alias="dueDate")
    linked_account_id: str | None = Field(default=None, alias="linkedAccountId", max_length=128)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("title")
    @classmethod
    def normalize_financial_goal_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Financial goal title must not be blank")
        return normalized

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_financial_goal_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Financial goal timestamps must contain a timezone")
        return value.astimezone(timezone.utc)


class FinancePaymentRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    amount_cents: int = Field(alias="amountCents", gt=0)
    due_date: date = Field(alias="dueDate")
    recurrence: FinanceRecurrence = FinanceRecurrence.monthly
    recurrence_day: int | None = Field(default=None, alias="recurrenceDay", ge=1, le=31)
    account_id: str | None = Field(default=None, alias="accountId", max_length=128)
    category_id: str | None = Field(default=None, alias="categoryId", max_length=128)
    is_active: bool = Field(default=True, alias="isActive")
    create_calendar_task: bool = Field(default=True, alias="createCalendarTask")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("title")
    @classmethod
    def normalize_payment_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Finance payment title must not be blank")
        return normalized

    @model_validator(mode="after")
    def default_recurrence_day(self) -> "FinancePaymentRecord":
        if self.recurrence_day is None:
            self.recurrence_day = self.due_date.day
        return self

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_payment_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Finance payment timestamps must contain a timezone")
        return value.astimezone(timezone.utc)

class FinancePaymentSettlementRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    expected_due_date: date = Field(alias="expectedDueDate")
    paid_at: datetime = Field(alias="paidAt")

    @field_validator("paid_at")
    @classmethod
    def normalize_paid_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("paidAt must contain a timezone")
        return value.astimezone(timezone.utc)


class FinancePaymentSettlementResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    transaction: FinanceTransactionRecord
    payment: FinancePaymentRecord
    created: bool

class FinanceDebtRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    person: str = Field(default="", max_length=120)
    direction: FinanceDebtDirection
    amount_cents: int = Field(alias="amountCents", gt=0)
    due_date: date | None = Field(default=None, alias="dueDate")
    status: FinanceDebtStatus = FinanceDebtStatus.open
    note: str = Field(default="", max_length=500)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("title", "person")
    @classmethod
    def normalize_debt_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("title")
    @classmethod
    def validate_debt_title(cls, value: str) -> str:
        if not value:
            raise ValueError("Finance debt title must not be blank")
        return value

    @field_validator("note")
    @classmethod
    def normalize_debt_note(cls, value: str) -> str:
        return value.strip()

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_debt_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Finance debt timestamps must contain a timezone")
        return value.astimezone(timezone.utc)


class FinanceAccountBalance(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    account: FinanceAccountRecord
    balance_cents: int = Field(alias="balanceCents")


class FinanceCategorySpend(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    category_id: str | None = Field(alias="categoryId")
    name: str
    color_hex: str = Field(alias="colorHex")
    amount_cents: int = Field(alias="amountCents")


class FinanceDailySpend(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    date: date
    amount_cents: int = Field(alias="amountCents")


class FinanceSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    currency: str = "RUB"
    total_balance_cents: int = Field(alias="totalBalanceCents")
    month_expense_cents: int = Field(alias="monthExpenseCents")
    previous_month_expense_cents: int = Field(alias="previousMonthExpenseCents")
    today_expense_cents: int = Field(alias="todayExpenseCents")
    average_daily_expense_cents: int = Field(alias="averageDailyExpenseCents")
    accounts: list[FinanceAccountBalance]
    category_spend: list[FinanceCategorySpend] = Field(alias="categorySpend")
    daily_spend: list[FinanceDailySpend] = Field(alias="dailySpend")
    goals: list[FinancialGoalRecord]
    payments: list[FinancePaymentRecord]
    debts: list[FinanceDebtRecord]
    recent_transactions: list[FinanceTransactionRecord] = Field(alias="recentTransactions")


class FinancePeriodReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    period: str
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    currency: str = "RUB"
    total_balance_cents: int = Field(alias="totalBalanceCents")
    expense_cents: int = Field(alias="expenseCents")
    average_daily_expense_cents: int = Field(alias="averageDailyExpenseCents")
    category_spend: list[FinanceCategorySpend] = Field(alias="categorySpend")
    daily_spend: list[FinanceDailySpend] = Field(alias="dailySpend")
