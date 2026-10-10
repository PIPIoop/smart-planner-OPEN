from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .repository import SqliteTaskRepository, TaskRepository
from .subscriptions import (
    BillingPeriod, EntitlementSnapshot, SubscriptionPlan, SubscriptionStatus, SubscriptionStore,
)

LEGACY_USER_ID = "__legacy__"


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class UserStatus(str, Enum):
    pending = "pending"
    active = "active"
    blocked = "blocked"
    deactivated = "deactivated"
    rejected = "rejected"


class UserRegistrationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    telegram_user_id: str = Field(alias="telegramUserId", min_length=1, max_length=32)
    username: str | None = Field(default=None, max_length=64)
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)

    @field_validator("telegram_user_id", "display_name")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Value cannot be empty")
        return normalized

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lstrip("@")
        return normalized or None


class PlannerUserRecord(UserRegistrationRequest):
    role: UserRole
    status: UserStatus
    registered_at: datetime = Field(alias="registeredAt")
    last_activity_at: datetime = Field(alias="lastActivityAt")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")
    task_count: int = Field(default=0, alias="taskCount")
    goal_count: int = Field(default=0, alias="goalCount")
    group_count: int = Field(default=0, alias="groupCount")
    subscription_plan: SubscriptionPlan = Field(default=SubscriptionPlan.free, alias="subscriptionPlan")
    subscription_status: SubscriptionStatus = Field(default=SubscriptionStatus.active, alias="subscriptionStatus")
    billing_period: BillingPeriod = Field(default=BillingPeriod.manual, alias="billingPeriod")
    subscription_expires_at: datetime | None = Field(default=None, alias="subscriptionExpiresAt")
    trial_ends_at: datetime | None = Field(default=None, alias="trialEndsAt")


class UserRegistrationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user: PlannerUserRecord
    created: bool


class UserAccessError(PermissionError):
    pass


class UserNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class UserActionResult:
    user: PlannerUserRecord


class MultiTenantStore:
    """Реестр Telegram-пользователей и маршрутизатор их SQLite-календарей."""

    def __init__(self, admin_database_path: Path) -> None:
        self._admin_database_path = admin_database_path.resolve()
        self._admin_database_path.parent.mkdir(parents=True, exist_ok=True)
        self._tenant_directory = self._admin_database_path.parent / "tenants"
        self._tenant_directory.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._admin_database_path.parent / "users.sqlite3"
        self._repositories: dict[str, SqliteTaskRepository] = {}
        self._lock = RLock()
        self._initialize_registry()
        self.subscriptions = SubscriptionStore(self._connect)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._registry_path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_registry(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS planner_users (
                    telegram_user_id TEXT PRIMARY KEY,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL,
                    approved_at TEXT,
                    CHECK (role IN ('admin', 'user')),
                    CHECK (status IN ('pending', 'active', 'blocked', 'deactivated', 'rejected'))
                )
            """)
            connection.commit()

    def bootstrap_admin(self, request: UserRegistrationRequest) -> PlannerUserRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            existing_admin = connection.execute(
                "SELECT telegram_user_id FROM planner_users WHERE role='admin'"
            ).fetchone()
            if existing_admin is not None and existing_admin["telegram_user_id"] != request.telegram_user_id:
                raise UserAccessError("Another administrator is already configured")
            existing = connection.execute(
                "SELECT 1 FROM planner_users WHERE telegram_user_id=?",
                (request.telegram_user_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO planner_users (
                        telegram_user_id, username, display_name, role, status,
                        registered_at, last_activity_at, approved_at
                    ) VALUES (?, ?, ?, 'admin', 'active', ?, ?, ?)""",
                    (
                        request.telegram_user_id,
                        request.username,
                        request.display_name,
                        now,
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """UPDATE planner_users SET username=?, display_name=?, role='admin',
                        status='active', last_activity_at=?, approved_at=COALESCE(approved_at, ?)
                        WHERE telegram_user_id=?""",
                    (request.username, request.display_name, now, now, request.telegram_user_id),
                )
            connection.commit()
        self.subscriptions.ensure_subscription(request.telegram_user_id, admin=True)
        return self.get_user(request.telegram_user_id, include_stats=True)

    def admin_user_id(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT telegram_user_id FROM planner_users WHERE role='admin' AND status='active'"
            ).fetchone()
        if row is None:
            raise UserNotFoundError("Active administrator is not configured")
        return str(row["telegram_user_id"])
    def register(self, request: UserRegistrationRequest) -> UserRegistrationResponse:
        now = datetime.now(timezone.utc).isoformat()
        created = False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM planner_users WHERE telegram_user_id=?",
                (request.telegram_user_id,),
            ).fetchone()
            if row is None:
                created = True
                connection.execute(
                    """INSERT INTO planner_users (
                        telegram_user_id, username, display_name, role, status,
                        registered_at, last_activity_at, approved_at
                    ) VALUES (?, ?, ?, 'user', 'pending', ?, ?, NULL)""",
                    (
                        request.telegram_user_id,
                        request.username,
                        request.display_name,
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """UPDATE planner_users SET username=?, display_name=?, last_activity_at=?
                        WHERE telegram_user_id=?""",
                    (request.username, request.display_name, now, request.telegram_user_id),
                )
            connection.commit()
        self.subscriptions.ensure_subscription(request.telegram_user_id, admin=False)
        return UserRegistrationResponse(
            user=self.get_user(request.telegram_user_id, include_stats=True),
            created=created,
        )

    def touch(self, user_id: str) -> PlannerUserRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE planner_users SET last_activity_at=? WHERE telegram_user_id=?",
                (now, user_id),
            )
            if cursor.rowcount != 1:
                raise UserNotFoundError(user_id)
            connection.commit()
        return self.get_user(user_id)

    def get_user(self, user_id: str, *, include_stats: bool = False) -> PlannerUserRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM planner_users WHERE telegram_user_id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise UserNotFoundError(user_id)
        return self._row_to_user(row, include_stats=include_stats)

    def list_users(self, actor_id: str) -> list[PlannerUserRecord]:
        self._require_admin(actor_id)
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM planner_users
                    ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                    registered_at DESC"""
            ).fetchall()
        return [self._row_to_user(row, include_stats=True) for row in rows]

    def set_status(self, actor_id: str, user_id: str, status: UserStatus) -> PlannerUserRecord:
        self._require_admin(actor_id)
        target = self.get_user(user_id)
        if target.role is UserRole.admin:
            raise UserAccessError("Administrator status cannot be changed")
        approved_at = datetime.now(timezone.utc).isoformat() if status is UserStatus.active else None
        with self._connect() as connection:
            connection.execute(
                """UPDATE planner_users SET status=?, approved_at=CASE
                    WHEN ?='active' THEN COALESCE(approved_at, ?) ELSE approved_at END
                    WHERE telegram_user_id=?""",
                (status.value, status.value, approved_at, user_id),
            )
            connection.commit()
        return self.get_user(user_id, include_stats=True)

    def delete_user(self, actor_id: str, user_id: str) -> None:
        self._require_admin(actor_id)
        target = self.get_user(user_id)
        if target.role is UserRole.admin:
            raise UserAccessError("Administrator cannot be deleted")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM planner_users WHERE telegram_user_id=?",
                (user_id,),
            )
            connection.commit()
        self.subscriptions.delete_user_data(user_id)
        with self._lock:
            self._repositories.pop(user_id, None)
        tenant_path = self._tenant_path(user_id)
        for path in (
            tenant_path,
            Path(f"{tenant_path}-wal"),
            Path(f"{tenant_path}-shm"),
        ):
            if path.exists():
                path.unlink()

    def repository_for(self, user_id: str) -> TaskRepository:
        if user_id == LEGACY_USER_ID:
            key = LEGACY_USER_ID
            path = self._admin_database_path
        else:
            user = self.get_user(user_id)
            if user.status is not UserStatus.active:
                raise UserAccessError(f"User status is {user.status.value}")
            key = user_id
            path = self._admin_database_path if user.role is UserRole.admin else self._tenant_path(user_id)
        with self._lock:
            repository = self._repositories.get(key)
            if repository is None:
                repository = SqliteTaskRepository(path)
                self._repositories[key] = repository
            return repository

    def authorize_calendar(self, actor_id: str, owner_id: str) -> None:
        actor = self.get_user(actor_id)
        if actor.status is not UserStatus.active:
            raise UserAccessError(f"Actor status is {actor.status.value}")
        if actor_id != owner_id and actor.role is not UserRole.admin:
            raise UserAccessError("Access to another user calendar is forbidden")
        owner = self.get_user(owner_id)
        if owner.status is not UserStatus.active:
            raise UserAccessError(f"Calendar owner status is {owner.status.value}")

    def authorize_write(self, actor_id: str, owner_id: str) -> None:
        self.authorize_calendar(actor_id, owner_id)
        if actor_id != owner_id:
            raise UserAccessError("Administrator access to another user is read-only")

    def is_admin(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        return user.role is UserRole.admin and user.status is UserStatus.active

    def entitlements_for(self, user_id: str) -> EntitlementSnapshot:
        return self.subscriptions.snapshot(user_id, admin=self.is_admin(user_id))
    def _tenant_path(self, user_id: str) -> Path:
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
        return self._tenant_directory / f"user_{digest}.sqlite3"

    def _require_admin(self, actor_id: str) -> PlannerUserRecord:
        actor = self.get_user(actor_id)
        if actor.role is not UserRole.admin or actor.status is not UserStatus.active:
            raise UserAccessError("Administrator access required")
        return actor

    def _row_to_user(self, row: sqlite3.Row, *, include_stats: bool) -> PlannerUserRecord:
        task_count = goal_count = group_count = 0
        if include_stats and row["status"] == UserStatus.active.value:
            repository = self.repository_for(row["telegram_user_id"])
            task_count = len(repository.list_all())
            goal_count = len(repository.list_goals())
            group_count = len(repository.list_groups())
        role = UserRole(row["role"])
        subscription = self.subscriptions.ensure_subscription(
            row["telegram_user_id"], admin=role is UserRole.admin
        )
        return PlannerUserRecord(
            telegram_user_id=row["telegram_user_id"],
            username=row["username"],
            display_name=row["display_name"],
            role=role,
            status=UserStatus(row["status"]),
            registered_at=row["registered_at"],
            last_activity_at=row["last_activity_at"],
            approved_at=row["approved_at"],
            task_count=task_count,
            goal_count=goal_count,
            group_count=group_count,
            subscription_plan=subscription.plan,
            subscription_status=subscription.status,
            billing_period=subscription.billing_period,
            subscription_expires_at=subscription.expires_at,
            trial_ends_at=subscription.trial_ends_at,
        )
