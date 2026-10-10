from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final, Iterable

from task_extractor import TaskExtraction


CONFIRM_ACTION: Final[str] = "task_confirm"
REJECT_ACTION: Final[str] = "task_reject"
EDIT_ACTION: Final[str] = "task_edit"
DURATION_ACTION: Final[str] = "task_duration"
SLOT_ACTION: Final[str] = "task_slot"
SAVE_UNTIMED_ACTION: Final[str] = "task_untimed"


@dataclass(frozen=True, slots=True)
class PendingTask:
    token: str
    user_id: int
    chat_id: int
    extraction: TaskExtraction
    created_at: datetime
    expires_at: datetime
    batch_id: str | None = None
    batch_index: int = 0
    batch_total: int = 1

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(slots=True)
class _PendingBatch:
    batch_id: str
    user_id: int
    chat_id: int
    extractions: list[TaskExtraction]
    created_at: datetime
    expires_at: datetime
    current_index: int = 0
    saved_count: int = 0
    skipped_count: int = 0

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class BatchSummary:
    total: int
    saved: int
    skipped: int


class ConfirmationStore:
    """Временное хранилище подтверждений и очередей нескольких задач."""

    def __init__(self, *, lifetime: timedelta = timedelta(minutes=15)) -> None:
        self._lifetime = lifetime
        self._items: dict[str, PendingTask] = {}
        self._batches: dict[str, _PendingBatch] = {}

    def create(
        self,
        *,
        user_id: int,
        chat_id: int,
        extraction: TaskExtraction,
        now: datetime,
    ) -> PendingTask:
        self.cleanup(now=now)
        return self._create_pending(
            user_id=user_id,
            chat_id=chat_id,
            extraction=extraction,
            now=now,
        )

    def create_batch(
        self,
        *,
        user_id: int,
        chat_id: int,
        extractions: Iterable[TaskExtraction],
        now: datetime,
    ) -> PendingTask:
        self.cleanup(now=now)
        values = list(extractions)
        if not values:
            raise ValueError("Batch must contain at least one task")
        if len(values) == 1:
            return self.create(
                user_id=user_id,
                chat_id=chat_id,
                extraction=values[0],
                now=now,
            )
        batch_id = secrets.token_urlsafe(8)
        batch = _PendingBatch(
            batch_id=batch_id,
            user_id=user_id,
            chat_id=chat_id,
            extractions=values,
            created_at=now,
            expires_at=now + self._lifetime,
        )
        self._batches[batch_id] = batch
        return self._create_pending(
            user_id=user_id,
            chat_id=chat_id,
            extraction=values[0],
            now=now,
            batch_id=batch_id,
            batch_index=0,
            batch_total=len(values),
        )

    def _create_pending(
        self,
        *,
        user_id: int,
        chat_id: int,
        extraction: TaskExtraction,
        now: datetime,
        batch_id: str | None = None,
        batch_index: int = 0,
        batch_total: int = 1,
    ) -> PendingTask:
        token = secrets.token_urlsafe(8)
        pending = PendingTask(
            token=token,
            user_id=user_id,
            chat_id=chat_id,
            extraction=extraction,
            created_at=now,
            expires_at=now + self._lifetime,
            batch_id=batch_id,
            batch_index=batch_index,
            batch_total=batch_total,
        )
        self._items[token] = pending
        return pending

    def get(
        self,
        *,
        token: str,
        user_id: int,
        chat_id: int,
        now: datetime,
    ) -> PendingTask | None:
        pending = self._items.get(token)
        if pending is None:
            return None
        if pending.is_expired(now):
            self._items.pop(token, None)
            return None
        if pending.user_id != user_id or pending.chat_id != chat_id:
            return None
        if pending.batch_id is not None:
            batch = self._batches.get(pending.batch_id)
            if batch is None or batch.is_expired(now):
                self._items.pop(token, None)
                return None
        return pending

    def replace_extraction(
        self,
        *,
        token: str,
        user_id: int,
        chat_id: int,
        extraction: TaskExtraction,
        now: datetime,
    ) -> PendingTask | None:
        pending = self.get(
            token=token,
            user_id=user_id,
            chat_id=chat_id,
            now=now,
        )
        if pending is None:
            return None
        updated = replace(pending, extraction=extraction, expires_at=now + self._lifetime)
        self._items[token] = updated
        if updated.batch_id is not None:
            batch = self._batches.get(updated.batch_id)
            if batch is not None and updated.batch_index < len(batch.extractions):
                batch.extractions[updated.batch_index] = extraction
                batch.expires_at = now + self._lifetime
        return updated

    def consume(
        self,
        *,
        token: str,
        user_id: int,
        chat_id: int,
        now: datetime,
    ) -> PendingTask | None:
        pending = self.get(
            token=token,
            user_id=user_id,
            chat_id=chat_id,
            now=now,
        )
        if pending is None:
            return None
        self._items.pop(token, None)
        return pending

    def advance_batch(
        self,
        *,
        pending: PendingTask,
        saved: bool,
        now: datetime,
    ) -> tuple[PendingTask | None, BatchSummary | None]:
        if pending.batch_id is None:
            return None, None
        batch = self._batches.get(pending.batch_id)
        if batch is None or batch.is_expired(now):
            return None, None
        if saved:
            batch.saved_count += 1
        else:
            batch.skipped_count += 1
        batch.current_index = pending.batch_index + 1
        batch.expires_at = now + self._lifetime
        if batch.current_index >= len(batch.extractions):
            summary = BatchSummary(
                total=len(batch.extractions),
                saved=batch.saved_count,
                skipped=batch.skipped_count,
            )
            self._batches.pop(batch.batch_id, None)
            return None, summary
        next_pending = self._create_pending(
            user_id=batch.user_id,
            chat_id=batch.chat_id,
            extraction=batch.extractions[batch.current_index],
            now=now,
            batch_id=batch.batch_id,
            batch_index=batch.current_index,
            batch_total=len(batch.extractions),
        )
        return next_pending, None

    def cleanup(self, *, now: datetime) -> None:
        expired_batches = {
            batch_id
            for batch_id, batch in self._batches.items()
            if batch.is_expired(now)
        }
        for batch_id in expired_batches:
            self._batches.pop(batch_id, None)
        expired_tokens = [
            token
            for token, pending in self._items.items()
            if pending.is_expired(now)
            or (pending.batch_id is not None and pending.batch_id not in self._batches)
        ]
        for token in expired_tokens:
            self._items.pop(token, None)
