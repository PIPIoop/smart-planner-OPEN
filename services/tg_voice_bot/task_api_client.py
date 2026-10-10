from __future__ import annotations

import hashlib
import hmac
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from task_extractor import TaskExtraction


class TaskApiError(RuntimeError):
    """Ошибка защищённого общего Task API."""


class TaskApiSubscriptionError(TaskApiError):
    """Ожидаемый отказ subscription/entitlement API с HTTP-кодом."""

    def __init__(self, message: str, *, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class TaskApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        service_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._service_token = service_token
        self._transport = transport

    def _user_headers(self, user_id: int | str) -> dict[str, str]:
        if self._service_token is None:
            return {}
        normalized = str(user_id)
        token = hmac.new(
            self._service_token.encode("utf-8"),
            f"smart-planner-user:{normalized}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {"Authorization": f"Bearer {token}", "X-User-Id": normalized}

    def _service_headers(self) -> dict[str, str]:
        if self._service_token is None:
            return {}
        return {"Authorization": f"Bearer {self._service_token}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    async def bootstrap_admin(self, *, user_id: int, username: str | None, display_name: str) -> dict[str, Any]:
        return await self._post_user_payload(
            "/api/v1/users/bootstrap-admin",
            user_id=user_id,
            username=username,
            display_name=display_name,
        )

    async def register_user(self, *, user_id: int, username: str | None, display_name: str) -> dict[str, Any]:
        return await self._post_user_payload(
            "/api/v1/users/requests",
            user_id=user_id,
            username=username,
            display_name=display_name,
        )

    async def _post_user_payload(self, path: str, *, user_id: int, username: str | None, display_name: str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.post(
                    path,
                    headers=self._service_headers(),
                    json={
                        "telegramUserId": str(user_id),
                        "username": username,
                        "displayName": display_name,
                    },
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось обновить реестр пользователей.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректного пользователя.")
        return data

    async def get_current_user(self, user_id: int | str) -> dict[str, Any] | None:
        try:
            async with self._client() as client:
                response = await client.get(
                    "/api/v1/users/me",
                    headers=self._user_headers(user_id),
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось проверить доступ пользователя.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректного пользователя.")
        return data

    async def get_subscription(self, user_id: int | str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.get(
                    "/api/v1/subscription/me",
                    headers=self._user_headers(user_id),
                )
            if response.status_code != 200:
                raise self._subscription_error(response, "Не удалось получить подписку.")
            data = response.json()
        except TaskApiSubscriptionError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось получить подписку пользователя.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректную подписку.")
        return data

    async def consume_subscription_usage(
        self,
        user_id: int | str,
        usage_key: str,
        *,
        amount: int = 1,
    ) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.post(
                    f"/api/v1/subscription/usage/{usage_key}/consume",
                    headers=self._user_headers(user_id),
                    params={"amount": amount},
                )
            if response.status_code != 200:
                raise self._subscription_error(response, "Лимит подписки не позволяет выполнить действие.")
            data = response.json()
        except TaskApiSubscriptionError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось проверить лимит подписки.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректный лимит подписки.")
        return data

    async def pending_notifications(self, user_id: int | str) -> list[dict[str, Any]]:
        return await self._get_list(
            "/api/v1/users/me/notifications",
            "уведомления подписки",
            user_id,
        )

    async def mark_notification_delivered(self, user_id: int | str, notification_id: int) -> None:
        try:
            async with self._client() as client:
                response = await client.post(
                    f"/api/v1/users/me/notifications/{notification_id}/delivered",
                    headers=self._user_headers(user_id),
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось отметить уведомление подписки доставленным.") from error

    @staticmethod
    def _subscription_error(response: httpx.Response, fallback: str) -> TaskApiSubscriptionError:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                raw = payload.get("detail")
                if isinstance(raw, str):
                    detail = raw
                elif raw is not None:
                    detail = str(raw)
        except ValueError:
            detail = response.text[:500]
        return TaskApiSubscriptionError(
            detail or fallback,
            status_code=response.status_code,
            detail=detail,
        )

    async def list_users(self, admin_user_id: int | str) -> list[dict[str, Any]]:
        return await self._get_list("/api/v1/users", "пользователей", admin_user_id)

    async def set_user_status(self, *, admin_user_id: int | str, user_id: int | str, status: str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.post(
                    f"/api/v1/users/{user_id}/status/{status}",
                    headers=self._user_headers(admin_user_id),
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось изменить статус пользователя.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректного пользователя.")
        return data

    async def delete_user(self, *, admin_user_id: int | str, user_id: int | str) -> None:
        try:
            async with self._client() as client:
                response = await client.delete(
                    f"/api/v1/users/{user_id}",
                    headers=self._user_headers(admin_user_id),
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось удалить пользователя.") from error

    async def list_tasks(self, user_id: int | str | None = None) -> list[dict[str, Any]]:
        return await self._get_list("/api/v1/tasks", "задачи", user_id)

    async def list_groups(self, user_id: int | str | None = None) -> list[dict[str, Any]]:
        return await self._get_list("/api/v1/groups", "группы", user_id)

    async def list_goals(self, user_id: int | str | None = None) -> list[dict[str, Any]]:
        return await self._get_list("/api/v1/goals", "цели", user_id)

    async def _get_list(self, path: str, entity_name: str, user_id: int | str | None) -> list[dict[str, Any]]:
        try:
            async with self._client() as client:
                response = await client.get(
                    path,
                    headers=self._user_headers(user_id) if user_id is not None else {},
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError(f"Не удалось получить {entity_name} через общий Task API.") from error
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise TaskApiError("Task API вернул некорректный список.")
        return data

    async def update_task(self, task: dict[str, Any], user_id: int | str | None = None) -> dict[str, Any]:
        task_id = str(task.get("id", ""))
        if not task_id:
            raise ValueError("Task ID is required")
        try:
            async with self._client() as client:
                response = await client.put(
                    f"/api/v1/tasks/{task_id}",
                    headers=self._user_headers(user_id) if user_id is not None else {},
                    json=task,
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось изменить задачу через общий Task API.") from error
        if not isinstance(data, dict) or str(data.get("id")) != task_id:
            raise TaskApiError("Task API вернул некорректную задачу.")
        return data

    async def delete_task(self, task_id: str, user_id: int | str | None = None) -> None:
        try:
            async with self._client() as client:
                response = await client.delete(
                    f"/api/v1/tasks/{task_id}",
                    headers=self._user_headers(user_id) if user_id is not None else {},
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось удалить задачу через общий Task API.") from error

    async def create_task(
        self,
        *,
        extraction: TaskExtraction,
        user_id: int,
        chat_id: int,
        confirmation_token: str,
    ) -> dict[str, Any]:
        if extraction.title is None or extraction.scheduled_date is None:
            raise ValueError("Cannot persist an incomplete task extraction")
        task_id = uuid5(
            NAMESPACE_URL,
            f"smart-planner:telegram:{chat_id}:{user_id}:{confirmation_token}",
        ).hex
        start_minute = None
        if extraction.scheduled_time is not None:
            start_minute = extraction.scheduled_time.hour * 60 + extraction.scheduled_time.minute
        deadline_minute = None
        if extraction.deadline_time is not None:
            deadline_minute = extraction.deadline_time.hour * 60 + extraction.deadline_time.minute
        payload = {
            "id": task_id,
            "title": extraction.title,
            "note": "Создано из Telegram.\n" f"Исходный текст: {extraction.source_text}",
            "date": extraction.scheduled_date.isoformat(),
            "startMinute": start_minute,
            "durationMinutes": (extraction.duration_minutes or 60) if start_minute is not None else None,
            "deadlineDate": extraction.deadline_date.isoformat() if extraction.deadline_date is not None else None,
            "deadlineMinute": deadline_minute,
            "priority": extraction.priority,
            "isCompleted": False,
        }
        try:
            async with self._client() as client:
                response = await client.post(
                    "/api/v1/tasks",
                    headers=self._user_headers(user_id),
                    json=payload,
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось сохранить задачу через общий Task API.") from error
        if not isinstance(data, dict) or data.get("id") != task_id:
            raise TaskApiError("Task API вернул некорректный ответ.")
        return data
    async def finance_summary(self, user_id: int | str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.get(
                    "/api/v1/finance/summary",
                    headers=self._user_headers(user_id),
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось получить финансовую сводку.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректную финансовую сводку.")
        return data

    async def finance_report(self, user_id: int | str, period: str) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.get(
                    "/api/v1/finance/report",
                    headers=self._user_headers(user_id),
                    params={"period": period},
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось получить финансовый отчёт.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректный финансовый отчёт.")
        return data

    async def list_finance_accounts(self, user_id: int | str) -> list[dict[str, Any]]:
        return await self._get_list("/api/v1/finance/accounts", "финансовые счета", user_id)

    async def list_finance_categories(self, user_id: int | str) -> list[dict[str, Any]]:
        return await self._get_list("/api/v1/finance/categories", "финансовые категории", user_id)

    async def create_finance_transaction(
        self,
        *,
        payload: dict[str, Any],
        user_id: int | str,
    ) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.post(
                    "/api/v1/finance/transactions",
                    headers=self._user_headers(user_id),
                    json=payload,
                )
                response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TaskApiError("Не удалось записать финансовую операцию.") from error
        if not isinstance(data, dict):
            raise TaskApiError("Task API вернул некорректную финансовую операцию.")
        return data

