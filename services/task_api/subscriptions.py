from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubscriptionPlan(str, Enum):
    free = "free"
    plus = "plus"
    full = "full"


class SubscriptionStatus(str, Enum):
    trial = "trial"
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"
    expired = "expired"


class BillingPeriod(str, Enum):
    monthly = "monthly"
    yearly = "yearly"
    manual = "manual"
    trial = "trial"


# Stable entitlement keys. Pricing/marketing names can change without touching API clients.
ENTITLEMENT_CALENDAR = "calendar"
ENTITLEMENT_GOOGLE_CALENDAR = "google_calendar"
ENTITLEMENT_TELEGRAM_BASIC = "telegram_basic"
ENTITLEMENT_MULTI_TASK = "multi_task_recognition"
ENTITLEMENT_SMART_SCHEDULING = "smart_scheduling"
ENTITLEMENT_ADVANCED_REPORTS = "advanced_reports"
ENTITLEMENT_FINANCE = "finance"
ENTITLEMENT_FINANCE_TELEGRAM = "finance_telegram"

LIMIT_AI_ACTIONS = "ai_actions_monthly"
LIMIT_VOICE_MESSAGES = "voice_messages_monthly"
LIMIT_GROUPS = "groups"
LIMIT_GOALS = "goals"
LIMIT_ANALYTICS_DAYS = "analytics_history_days"
LIMIT_FINANCE_ACCOUNTS = "finance_accounts"
LIMIT_FINANCE_TRANSACTIONS = "finance_transactions_monthly"


PLAN_ENTITLEMENTS: dict[SubscriptionPlan, dict[str, bool]] = {
    SubscriptionPlan.free: {
        ENTITLEMENT_CALENDAR: True,
        ENTITLEMENT_GOOGLE_CALENDAR: True,
        ENTITLEMENT_TELEGRAM_BASIC: True,
        ENTITLEMENT_MULTI_TASK: False,
        ENTITLEMENT_SMART_SCHEDULING: False,
        ENTITLEMENT_ADVANCED_REPORTS: False,
        ENTITLEMENT_FINANCE: False,
        ENTITLEMENT_FINANCE_TELEGRAM: False,
    },
    SubscriptionPlan.plus: {
        ENTITLEMENT_CALENDAR: True,
        ENTITLEMENT_GOOGLE_CALENDAR: True,
        ENTITLEMENT_TELEGRAM_BASIC: True,
        ENTITLEMENT_MULTI_TASK: True,
        ENTITLEMENT_SMART_SCHEDULING: True,
        ENTITLEMENT_ADVANCED_REPORTS: True,
        ENTITLEMENT_FINANCE: False,
        ENTITLEMENT_FINANCE_TELEGRAM: False,
    },
    SubscriptionPlan.full: {
        ENTITLEMENT_CALENDAR: True,
        ENTITLEMENT_GOOGLE_CALENDAR: True,
        ENTITLEMENT_TELEGRAM_BASIC: True,
        ENTITLEMENT_MULTI_TASK: True,
        ENTITLEMENT_SMART_SCHEDULING: True,
        ENTITLEMENT_ADVANCED_REPORTS: True,
        ENTITLEMENT_FINANCE: True,
        ENTITLEMENT_FINANCE_TELEGRAM: True,
    },
}

# These are protective limits. Plus/Full are intentionally presented in UI as unlimited.
PLAN_LIMITS: dict[SubscriptionPlan, dict[str, int]] = {
    SubscriptionPlan.free: {
        LIMIT_AI_ACTIONS: 20,
        LIMIT_VOICE_MESSAGES: 10,
        LIMIT_GROUPS: 3,
        LIMIT_GOALS: 2,
        LIMIT_ANALYTICS_DAYS: 30,
        LIMIT_FINANCE_ACCOUNTS: 0,
        LIMIT_FINANCE_TRANSACTIONS: 0,
    },
    SubscriptionPlan.plus: {
        LIMIT_AI_ACTIONS: 1_000,
        LIMIT_VOICE_MESSAGES: 500,
        LIMIT_GROUPS: 100,
        LIMIT_GOALS: 100,
        LIMIT_ANALYTICS_DAYS: 365,
        LIMIT_FINANCE_ACCOUNTS: 0,
        LIMIT_FINANCE_TRANSACTIONS: 0,
    },
    SubscriptionPlan.full: {
        LIMIT_AI_ACTIONS: 2_000,
        LIMIT_VOICE_MESSAGES: 1_000,
        LIMIT_GROUPS: 100,
        LIMIT_GOALS: 100,
        LIMIT_ANALYTICS_DAYS: -1,
        LIMIT_FINANCE_ACCOUNTS: 100,
        LIMIT_FINANCE_TRANSACTIONS: 20_000,
    },
}

PUBLIC_UNLIMITED_LIMITS = {
    SubscriptionPlan.plus: {LIMIT_AI_ACTIONS, LIMIT_VOICE_MESSAGES, LIMIT_GROUPS, LIMIT_GOALS},
    SubscriptionPlan.full: {
        LIMIT_AI_ACTIONS,
        LIMIT_VOICE_MESSAGES,
        LIMIT_GROUPS,
        LIMIT_GOALS,
        LIMIT_FINANCE_ACCOUNTS,
        LIMIT_FINANCE_TRANSACTIONS,
    },
}

KNOWN_ENTITLEMENTS = frozenset(PLAN_ENTITLEMENTS[SubscriptionPlan.full].keys())
KNOWN_LIMITS = frozenset(PLAN_LIMITS[SubscriptionPlan.full].keys())


class SubscriptionRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    plan: SubscriptionPlan
    status: SubscriptionStatus
    billing_period: BillingPeriod = Field(alias="billingPeriod")
    starts_at: datetime = Field(alias="startsAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    trial_ends_at: datetime | None = Field(default=None, alias="trialEndsAt")
    grace_ends_at: datetime | None = Field(default=None, alias="graceEndsAt")
    updated_at: datetime = Field(alias="updatedAt")


class SubscriptionUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    plan: SubscriptionPlan
    status: SubscriptionStatus = SubscriptionStatus.active
    billing_period: BillingPeriod = Field(default=BillingPeriod.manual, alias="billingPeriod")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    @field_validator("expires_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expiresAt must contain a timezone")
        return value.astimezone(timezone.utc) if value is not None else None


class TrialGrantRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    days: int = Field(ge=1, le=365)


class OverrideKind(str, Enum):
    entitlement = "entitlement"
    limit_bonus = "limit_bonus"


class AccountOverrideRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    user_id: str = Field(alias="userId")
    key: str
    kind: OverrideKind
    bool_value: bool | None = Field(default=None, alias="boolValue")
    int_value: int | None = Field(default=None, alias="intValue")
    expires_at: datetime = Field(alias="expiresAt")
    reason: str = ""
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")


class OverrideCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    key: str = Field(min_length=1, max_length=80)
    kind: OverrideKind
    bool_value: bool | None = Field(default=None, alias="boolValue")
    int_value: int | None = Field(default=None, alias="intValue", ge=1, le=1_000_000)
    expires_at: datetime = Field(alias="expiresAt")
    reason: str = Field(default="", max_length=300)

    @field_validator("expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expiresAt must contain a timezone")
        return value.astimezone(timezone.utc)


class EntitlementSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(alias="userId")
    plan: SubscriptionPlan
    status: SubscriptionStatus
    billing_period: BillingPeriod = Field(alias="billingPeriod")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    trial_ends_at: datetime | None = Field(default=None, alias="trialEndsAt")
    grace_ends_at: datetime | None = Field(default=None, alias="graceEndsAt")
    entitlements: dict[str, bool]
    limits: dict[str, int]
    public_unlimited: list[str] = Field(alias="publicUnlimited")
    usage: dict[str, int]
    overrides: list[AccountOverrideRecord]
    finance_read_only: bool = Field(alias="financeReadOnly")


class AuditLogRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: int
    actor_id: str = Field(alias="actorId")
    user_id: str = Field(alias="userId")
    action: str
    before_json: dict[str, Any] | None = Field(default=None, alias="before")
    after_json: dict[str, Any] | None = Field(default=None, alias="after")
    created_at: datetime = Field(alias="createdAt")


class UserNotificationRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: int
    user_id: str = Field(alias="userId")
    title: str
    message: str
    created_at: datetime = Field(alias="createdAt")
    delivered_at: datetime | None = Field(default=None, alias="deliveredAt")


class SubscriptionLimitError(PermissionError):
    def __init__(self, key: str, limit: int) -> None:
        self.key = key
        self.limit = limit
        super().__init__(f"Subscription limit reached: {key} ({limit})")


class SubscriptionAccessError(PermissionError):
    pass


@dataclass(frozen=True)
class _EffectiveSubscription:
    subscription: SubscriptionRecord
    entitlements: dict[str, bool]
    limits: dict[str, int]
    overrides: list[AccountOverrideRecord]


class SubscriptionStore:
    """Subscription/entitlement storage backed by the shared user registry SQLite database."""

    def __init__(self, connection_factory, *, default_trial_days: int = 14, grace_days: int = 3) -> None:
        self._connect = connection_factory
        self.default_trial_days = default_trial_days
        self.grace_days = grace_days
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    user_id TEXT PRIMARY KEY,
                    plan TEXT NOT NULL,
                    status TEXT NOT NULL,
                    billing_period TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    expires_at TEXT,
                    trial_ends_at TEXT,
                    grace_ends_at TEXT,
                    updated_at TEXT NOT NULL,
                    CHECK (plan IN ('free','plus','full')),
                    CHECK (status IN ('trial','active','past_due','cancelled','expired')),
                    CHECK (billing_period IN ('monthly','yearly','manual','trial'))
                );
                CREATE TABLE IF NOT EXISTS user_subscription_overrides (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    bool_value INTEGER,
                    int_value INTEGER,
                    expires_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CHECK (kind IN ('entitlement','limit_bonus'))
                );
                CREATE INDEX IF NOT EXISTS idx_subscription_overrides_user
                    ON user_subscription_overrides(user_id, expires_at);
                CREATE TABLE IF NOT EXISTS user_usage_monthly (
                    user_id TEXT NOT NULL,
                    usage_key TEXT NOT NULL,
                    period TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, usage_key, period)
                );
                CREATE TABLE IF NOT EXISTS user_subscription_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    before_json TEXT,
                    after_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    delivered_at TEXT
                );
            """)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.astimezone(timezone.utc).isoformat() if value is not None else None

    def ensure_subscription(self, user_id: str, *, admin: bool = False) -> SubscriptionRecord:
        existing = self._raw_subscription(user_id)
        if existing is not None:
            return self._normalize_status(existing)
        now = self._now()
        if admin:
            record = SubscriptionRecord(
                userId=user_id,
                plan=SubscriptionPlan.full,
                status=SubscriptionStatus.active,
                billingPeriod=BillingPeriod.manual,
                startsAt=now,
                expiresAt=None,
                trialEndsAt=None,
                graceEndsAt=None,
                updatedAt=now,
            )
        else:
            trial_end = now + timedelta(days=self.default_trial_days)
            record = SubscriptionRecord(
                userId=user_id,
                plan=SubscriptionPlan.full,
                status=SubscriptionStatus.trial,
                billingPeriod=BillingPeriod.trial,
                startsAt=now,
                expiresAt=trial_end,
                trialEndsAt=trial_end,
                graceEndsAt=None,
                updatedAt=now,
            )
        self._save(record)
        return record

    def _raw_subscription(self, user_id: str) -> SubscriptionRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM user_subscriptions WHERE user_id=?", (user_id,)).fetchone()
        return self._row_to_subscription(row) if row is not None else None

    def _normalize_status(self, record: SubscriptionRecord) -> SubscriptionRecord:
        now = self._now()
        changed = False
        downgrade_reason: str | None = None
        status = record.status
        plan = record.plan
        billing = record.billing_period
        expires = record.expires_at
        grace = record.grace_ends_at
        trial_ends = record.trial_ends_at

        if status is SubscriptionStatus.trial and trial_ends is not None and trial_ends <= now:
            plan = SubscriptionPlan.free
            status = SubscriptionStatus.active
            billing = BillingPeriod.manual
            expires = None
            trial_ends = None
            grace = None
            downgrade_reason = "trial_expired"
            changed = True
        elif status is SubscriptionStatus.active and expires is not None and expires <= now:
            plan = SubscriptionPlan.free
            status = SubscriptionStatus.active
            billing = BillingPeriod.manual
            expires = None
            grace = None
            downgrade_reason = "subscription_expired"
            changed = True
        elif status is SubscriptionStatus.cancelled and expires is not None and expires <= now:
            plan = SubscriptionPlan.free
            status = SubscriptionStatus.active
            billing = BillingPeriod.manual
            expires = None
            grace = None
            downgrade_reason = "cancelled_period_ended"
            changed = True
        elif status is SubscriptionStatus.past_due:
            if grace is None and expires is not None:
                grace = expires + timedelta(days=self.grace_days)
                changed = True
            if grace is not None and grace <= now:
                plan = SubscriptionPlan.free
                status = SubscriptionStatus.active
                billing = BillingPeriod.manual
                expires = None
                grace = None
                downgrade_reason = "grace_period_ended"
                changed = True
        elif status is SubscriptionStatus.expired:
            plan = SubscriptionPlan.free
            status = SubscriptionStatus.active
            billing = BillingPeriod.manual
            expires = None
            grace = None
            downgrade_reason = "subscription_expired"
            changed = True

        if not changed:
            return record
        before = record.model_dump(mode="json", by_alias=True)
        normalized = record.model_copy(update={
            "plan": plan,
            "status": status,
            "billing_period": billing,
            "expires_at": expires,
            "trial_ends_at": trial_ends,
            "grace_ends_at": grace,
            "updated_at": now,
        })
        self._save(normalized)
        if downgrade_reason is not None:
            after = normalized.model_dump(mode="json", by_alias=True)
            self._audit("system", record.user_id, f"subscription.{downgrade_reason}", before, after)
            self._notify(
                record.user_id,
                "Подписка изменена",
                "Платный доступ завершён. Ваши данные сохранены; недоступные функции переведены в режим только для чтения.",
            )
        return normalized

    def get_subscription(self, user_id: str, *, admin: bool = False) -> SubscriptionRecord:
        return self.ensure_subscription(user_id, admin=admin)

    def effective(self, user_id: str, *, admin: bool = False) -> _EffectiveSubscription:
        subscription = self.ensure_subscription(user_id, admin=admin)
        entitlements = dict(PLAN_ENTITLEMENTS[subscription.plan])
        limits = dict(PLAN_LIMITS[subscription.plan])
        overrides = self.list_overrides(user_id)
        for override in overrides:
            if override.kind is OverrideKind.entitlement and override.bool_value is not None:
                entitlements[override.key] = override.bool_value
            elif override.kind is OverrideKind.limit_bonus and override.int_value is not None:
                base = limits.get(override.key, 0)
                if base >= 0:
                    limits[override.key] = base + override.int_value

        # Telegram-запись финансов подразумевает доступ к самому финансовому модулю.
        if entitlements.get(ENTITLEMENT_FINANCE_TELEGRAM, False):
            entitlements[ENTITLEMENT_FINANCE] = True

        # Временный доступ к финансам должен быть реально пригоден к использованию.
        # На Free/Plus базовые финансовые safety-лимиты равны нулю, поэтому
        # entitlement override автоматически получает технические лимиты Full.
        if entitlements.get(ENTITLEMENT_FINANCE, False):
            if limits.get(LIMIT_FINANCE_ACCOUNTS, 0) == 0:
                limits[LIMIT_FINANCE_ACCOUNTS] = PLAN_LIMITS[SubscriptionPlan.full][LIMIT_FINANCE_ACCOUNTS]
            if limits.get(LIMIT_FINANCE_TRANSACTIONS, 0) == 0:
                limits[LIMIT_FINANCE_TRANSACTIONS] = PLAN_LIMITS[SubscriptionPlan.full][LIMIT_FINANCE_TRANSACTIONS]
        return _EffectiveSubscription(subscription, entitlements, limits, overrides)

    def snapshot(self, user_id: str, *, admin: bool = False) -> EntitlementSnapshot:
        effective = self.effective(user_id, admin=admin)
        subscription = effective.subscription
        # Admin is an authorization role, not a paid plan. It bypasses feature gates.
        entitlements = {key: True for key in effective.entitlements} if admin else effective.entitlements
        limits = dict(effective.limits)
        if admin:
            limits = {key: -1 for key in limits}
        usage = self.usage_snapshot(user_id)
        finance_write = admin or effective.entitlements.get(ENTITLEMENT_FINANCE, False)
        public_unlimited = sorted(PUBLIC_UNLIMITED_LIMITS.get(subscription.plan, set()))
        return EntitlementSnapshot(
            userId=user_id,
            plan=subscription.plan,
            status=subscription.status,
            billingPeriod=subscription.billing_period,
            expiresAt=subscription.expires_at,
            trialEndsAt=subscription.trial_ends_at,
            graceEndsAt=subscription.grace_ends_at,
            entitlements=entitlements,
            limits=limits,
            publicUnlimited=public_unlimited,
            usage=usage,
            overrides=effective.overrides,
            financeReadOnly=not finance_write,
        )

    def has_entitlement(self, user_id: str, key: str, *, admin: bool = False) -> bool:
        if admin:
            return True
        return self.effective(user_id).entitlements.get(key, False)

    def limit(self, user_id: str, key: str, *, admin: bool = False) -> int:
        if admin:
            return -1
        return self.effective(user_id).limits.get(key, 0)

    def enforce_count_limit(self, user_id: str, key: str, current_count: int, *, admin: bool = False) -> None:
        limit = self.limit(user_id, key, admin=admin)
        if limit >= 0 and current_count >= limit:
            raise SubscriptionLimitError(key, limit)

    def consume_usage(self, user_id: str, key: str, amount: int = 1, *, admin: bool = False) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        limit = self.limit(user_id, key, admin=admin)
        period = self._now().strftime("%Y-%m")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT amount FROM user_usage_monthly WHERE user_id=? AND usage_key=? AND period=?",
                (user_id, key, period),
            ).fetchone()
            current = int(row["amount"]) if row is not None else 0
            if limit >= 0 and current + amount > limit:
                raise SubscriptionLimitError(key, limit)
            new_value = current + amount
            connection.execute(
                """INSERT INTO user_usage_monthly(user_id, usage_key, period, amount)
                   VALUES(?,?,?,?)
                   ON CONFLICT(user_id,usage_key,period) DO UPDATE SET amount=excluded.amount""",
                (user_id, key, period, new_value),
            )
        return new_value

    def refund_usage(self, user_id: str, key: str, amount: int = 1) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        period = self._now().strftime("%Y-%m")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT amount FROM user_usage_monthly WHERE user_id=? AND usage_key=? AND period=?",
                (user_id, key, period),
            ).fetchone()
            current = int(row["amount"]) if row is not None else 0
            new_value = max(0, current - amount)
            if new_value == 0:
                connection.execute(
                    "DELETE FROM user_usage_monthly WHERE user_id=? AND usage_key=? AND period=?",
                    (user_id, key, period),
                )
            else:
                connection.execute(
                    "UPDATE user_usage_monthly SET amount=? WHERE user_id=? AND usage_key=? AND period=?",
                    (new_value, user_id, key, period),
                )
        return new_value
    def usage_snapshot(self, user_id: str) -> dict[str, int]:
        period = self._now().strftime("%Y-%m")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT usage_key, amount FROM user_usage_monthly WHERE user_id=? AND period=?",
                (user_id, period),
            ).fetchall()
        return {str(row["usage_key"]): int(row["amount"]) for row in rows}

    def update_subscription(self, actor_id: str, user_id: str, request: SubscriptionUpdateRequest) -> SubscriptionRecord:
        before = self.ensure_subscription(user_id).model_dump(mode="json", by_alias=True)
        now = self._now()
        grace = None
        if request.status is SubscriptionStatus.past_due:
            grace_start = request.expires_at or now
            grace = grace_start + timedelta(days=self.grace_days)
        record = SubscriptionRecord(
            userId=user_id,
            plan=request.plan,
            status=request.status,
            billingPeriod=request.billing_period,
            startsAt=now,
            expiresAt=request.expires_at,
            trialEndsAt=None,
            graceEndsAt=grace,
            updatedAt=now,
        )
        self._save(record)
        self._audit(actor_id, user_id, "subscription.updated", before, record.model_dump(mode="json", by_alias=True))
        self._notify(user_id, "Подписка обновлена", f"Ваш тариф Smart Planner изменён на {record.plan.value.upper()}.")
        return record

    def reset_to_free(self, actor_id: str, user_id: str) -> SubscriptionRecord:
        before = self.ensure_subscription(user_id).model_dump(mode="json", by_alias=True)
        now = self._now()
        record = SubscriptionRecord(
            userId=user_id,
            plan=SubscriptionPlan.free,
            status=SubscriptionStatus.active,
            billingPeriod=BillingPeriod.manual,
            startsAt=now,
            expiresAt=None,
            trialEndsAt=None,
            graceEndsAt=None,
            updatedAt=now,
        )
        self._save(record)
        self._audit(actor_id, user_id, "subscription.reset_to_free", before, record.model_dump(mode="json", by_alias=True))
        self._notify(user_id, "Подписка изменена", "Платная подписка завершена. Ваши данные сохранены; финансовый раздел доступен только для чтения.")
        return record

    def grant_trial(self, actor_id: str, user_id: str, days: int) -> SubscriptionRecord:
        before = self.ensure_subscription(user_id).model_dump(mode="json", by_alias=True)
        now = self._now()
        trial_end = now + timedelta(days=days)
        record = SubscriptionRecord(
            userId=user_id,
            plan=SubscriptionPlan.full,
            status=SubscriptionStatus.trial,
            billingPeriod=BillingPeriod.trial,
            startsAt=now,
            expiresAt=trial_end,
            trialEndsAt=trial_end,
            graceEndsAt=None,
            updatedAt=now,
        )
        self._save(record)
        self._audit(actor_id, user_id, "trial.granted", before, record.model_dump(mode="json", by_alias=True))
        self._notify(user_id, "Выдан пробный Full", f"Вам открыт Full на {days} дн. До {trial_end.date().isoformat()} доступны все функции, включая финансы.")
        return record

    def add_override(self, actor_id: str, user_id: str, request: OverrideCreateRequest) -> AccountOverrideRecord:
        now = self._now()
        if request.expires_at <= now:
            raise ValueError("Override expiration must be in the future")
        if request.kind is OverrideKind.entitlement:
            if request.key not in KNOWN_ENTITLEMENTS:
                raise ValueError("Unknown entitlement override key")
            if request.bool_value is None:
                raise ValueError("boolValue is required for entitlement override")
        if request.kind is OverrideKind.limit_bonus:
            if request.key not in KNOWN_LIMITS:
                raise ValueError("Unknown limit override key")
            if request.int_value is None:
                raise ValueError("intValue is required for limit bonus override")
        record = AccountOverrideRecord(
            id=uuid.uuid4().hex,
            userId=user_id,
            key=request.key,
            kind=request.kind,
            boolValue=request.bool_value,
            intValue=request.int_value,
            expiresAt=request.expires_at,
            reason=request.reason.strip(),
            createdBy=actor_id,
            createdAt=now,
        )
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO user_subscription_overrides
                   (id,user_id,key,kind,bool_value,int_value,expires_at,reason,created_by,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, user_id, record.key, record.kind.value,
                    None if record.bool_value is None else int(record.bool_value), record.int_value,
                    self._iso(record.expires_at), record.reason, actor_id, self._iso(now),
                ),
            )
        self._audit(actor_id, user_id, "override.granted", None, record.model_dump(mode="json", by_alias=True))
        label = self._override_label(record.key)
        self._notify(user_id, "Вам выдан дополнительный доступ", f"Администратор выдал «{label}» до {record.expires_at.date().isoformat()}.")
        return record

    def delete_override(self, actor_id: str, user_id: str, override_id: str) -> None:
        records = {item.id: item for item in self.list_overrides(user_id, include_expired=True)}
        before = records.get(override_id)
        if before is None:
            raise LookupError(override_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM user_subscription_overrides WHERE id=? AND user_id=?", (override_id, user_id))
        self._audit(actor_id, user_id, "override.removed", before.model_dump(mode="json", by_alias=True), None)
        self._notify(user_id, "Дополнительный доступ завершён", f"Дополнительная возможность «{self._override_label(before.key)}» была отключена.")

    def list_overrides(self, user_id: str, *, include_expired: bool = False) -> list[AccountOverrideRecord]:
        self._expire_overrides(user_id)
        query = "SELECT * FROM user_subscription_overrides WHERE user_id=?"
        params: list[Any] = [user_id]
        if not include_expired:
            query += " AND expires_at>?"
            params.append(self._iso(self._now()))
        query += " ORDER BY expires_at ASC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_override(row) for row in rows]

    def _expire_overrides(self, user_id: str) -> None:
        now = self._now()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM user_subscription_overrides WHERE user_id=? AND expires_at<=?",
                (user_id, self._iso(now)),
            ).fetchall()
            if rows:
                connection.executemany(
                    "DELETE FROM user_subscription_overrides WHERE id=? AND user_id=?",
                    [(row["id"], user_id) for row in rows],
                )
        for row in rows:
            expired = self._row_to_override(row)
            before = expired.model_dump(mode="json", by_alias=True)
            self._audit("system", user_id, "override.expired", before, None)
            self._notify(
                user_id,
                "Дополнительный доступ завершён",
                f"Срок дополнительной возможности «{self._override_label(expired.key)}» закончился.",
            )

    def audit_log(self, user_id: str, *, limit: int = 100) -> list[AuditLogRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM user_subscription_audit WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        result: list[AuditLogRecord] = []
        for row in rows:
            result.append(AuditLogRecord(
                id=row["id"], actorId=row["actor_id"], userId=row["user_id"], action=row["action"],
                before=json.loads(row["before_json"]) if row["before_json"] else None,
                after=json.loads(row["after_json"]) if row["after_json"] else None,
                createdAt=row["created_at"],
            ))
        return result

    def pending_notifications(self, user_id: str) -> list[UserNotificationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM user_notifications WHERE user_id=? AND delivered_at IS NULL ORDER BY id ASC LIMIT 20",
                (user_id,),
            ).fetchall()
        return [self._row_to_notification(row) for row in rows]

    def mark_notification_delivered(self, user_id: str, notification_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE user_notifications SET delivered_at=? WHERE id=? AND user_id=?",
                (self._iso(self._now()), notification_id, user_id),
            )

    def delete_user_data(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM user_subscriptions WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM user_subscription_overrides WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM user_usage_monthly WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM user_subscription_audit WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM user_notifications WHERE user_id=?", (user_id,))

    @staticmethod
    def _override_label(key: str) -> str:
        labels = {
            ENTITLEMENT_FINANCE: "Финансы",
            ENTITLEMENT_FINANCE_TELEGRAM: "Финансы в Telegram",
            ENTITLEMENT_SMART_SCHEDULING: "Умное планирование",
            ENTITLEMENT_MULTI_TASK: "Несколько задач в одном сообщении",
            ENTITLEMENT_ADVANCED_REPORTS: "Расширенные отчёты",
            LIMIT_AI_ACTIONS: "дополнительные AI-действия",
            LIMIT_VOICE_MESSAGES: "дополнительные голосовые сообщения",
            LIMIT_GROUPS: "дополнительные группы",
            LIMIT_GOALS: "дополнительные цели",
        }
        return labels.get(key, key.replace("_", " "))

    def _save(self, record: SubscriptionRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO user_subscriptions
                   (user_id,plan,status,billing_period,starts_at,expires_at,trial_ends_at,grace_ends_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     plan=excluded.plan,status=excluded.status,billing_period=excluded.billing_period,
                     starts_at=excluded.starts_at,expires_at=excluded.expires_at,trial_ends_at=excluded.trial_ends_at,
                     grace_ends_at=excluded.grace_ends_at,updated_at=excluded.updated_at""",
                (
                    record.user_id, record.plan.value, record.status.value, record.billing_period.value,
                    self._iso(record.starts_at), self._iso(record.expires_at), self._iso(record.trial_ends_at),
                    self._iso(record.grace_ends_at), self._iso(record.updated_at),
                ),
            )

    def _audit(self, actor_id: str, user_id: str, action: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO user_subscription_audit(actor_id,user_id,action,before_json,after_json,created_at) VALUES(?,?,?,?,?,?)",
                (actor_id, user_id, action, json.dumps(before, ensure_ascii=False) if before is not None else None,
                 json.dumps(after, ensure_ascii=False) if after is not None else None, self._iso(self._now())),
            )

    def _notify(self, user_id: str, title: str, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO user_notifications(user_id,title,message,created_at,delivered_at) VALUES(?,?,?,?,NULL)",
                (user_id, title, message, self._iso(self._now())),
            )

    @staticmethod
    def _row_to_subscription(row: sqlite3.Row) -> SubscriptionRecord:
        return SubscriptionRecord(
            userId=row["user_id"], plan=row["plan"], status=row["status"], billingPeriod=row["billing_period"],
            startsAt=row["starts_at"], expiresAt=row["expires_at"], trialEndsAt=row["trial_ends_at"],
            graceEndsAt=row["grace_ends_at"], updatedAt=row["updated_at"],
        )

    @staticmethod
    def _row_to_override(row: sqlite3.Row) -> AccountOverrideRecord:
        return AccountOverrideRecord(
            id=row["id"], userId=row["user_id"], key=row["key"], kind=row["kind"],
            boolValue=None if row["bool_value"] is None else bool(row["bool_value"]), intValue=row["int_value"],
            expiresAt=row["expires_at"], reason=row["reason"], createdBy=row["created_by"], createdAt=row["created_at"],
        )

    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> UserNotificationRecord:
        return UserNotificationRecord(
            id=row["id"], userId=row["user_id"], title=row["title"], message=row["message"],
            createdAt=row["created_at"], deliveredAt=row["delivered_at"],
        )
