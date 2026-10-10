from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_admin_user_id: int

    whisper_model: str
    whisper_language: str | None
    whisper_device: str
    whisper_compute_type: str

    max_voice_duration_seconds: int

    task_api_url: str
    task_api_timeout_seconds: float
    task_api_service_token: str

    app_timezone: str
    app_locale: str

    @property
    def telegram_owner_user_id(self) -> int:
        return self.telegram_admin_user_id

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    if not telegram_bot_token:
        raise RuntimeError(
            "Переменная TELEGRAM_BOT_TOKEN не задана."
        )

    owner_user_id_raw = (
        os.getenv("TELEGRAM_ADMIN_USER_ID", "").strip()
        or os.getenv("TELEGRAM_OWNER_USER_ID", "").strip()
    )
    try:
        telegram_owner_user_id = int(owner_user_id_raw)
    except ValueError as error:
        raise RuntimeError(
            "TELEGRAM_ADMIN_USER_ID должен быть целым числом."
        ) from error
    if telegram_owner_user_id <= 0:
        raise RuntimeError(
            "TELEGRAM_ADMIN_USER_ID должен быть больше нуля."
        )
    max_duration_raw = os.getenv(
        "MAX_VOICE_DURATION_SECONDS",
        "300",
    ).strip()

    try:
        max_voice_duration_seconds = int(max_duration_raw)
    except ValueError as error:
        raise RuntimeError(
            "MAX_VOICE_DURATION_SECONDS должна быть целым числом."
        ) from error

    if max_voice_duration_seconds <= 0:
        raise RuntimeError(
            "MAX_VOICE_DURATION_SECONDS должна быть больше нуля."
        )

    task_api_url = os.getenv(
        "TASK_API_URL",
        "http://127.0.0.1:8080",
    ).strip().rstrip("/")
    if not (
        task_api_url.startswith("http://")
        or task_api_url.startswith("https://")
    ):
        raise RuntimeError(
            "TASK_API_URL должен начинаться с http:// или https://."
        )

    task_api_timeout_raw = os.getenv(
        "TASK_API_TIMEOUT_SECONDS",
        "10",
    ).strip()
    try:
        task_api_timeout_seconds = float(task_api_timeout_raw)
    except ValueError as error:
        raise RuntimeError(
            "TASK_API_TIMEOUT_SECONDS должна быть числом."
        ) from error
    if task_api_timeout_seconds <= 0:
        raise RuntimeError(
            "TASK_API_TIMEOUT_SECONDS должна быть больше нуля."
        )

    task_api_service_token = os.getenv("TASK_API_SERVICE_TOKEN", "").strip()
    if len(task_api_service_token) < 32:
        raise RuntimeError(
            "TASK_API_SERVICE_TOKEN должен содержать минимум 32 символа."
        )
    app_timezone = os.getenv(
        "APP_TIMEZONE",
        "Asia/Yekaterinburg",
    ).strip()

    try:
        ZoneInfo(app_timezone)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            f"Неизвестный часовой пояс: {app_timezone}"
        ) from error

    whisper_language = os.getenv(
        "WHISPER_LANGUAGE",
        "ru",
    ).strip()

    return Settings(
        telegram_bot_token=telegram_bot_token,
        telegram_admin_user_id=telegram_owner_user_id,
        whisper_model=os.getenv(
            "WHISPER_MODEL",
            "small",
        ).strip(),
        whisper_language=whisper_language or None,
        whisper_device=os.getenv(
            "WHISPER_DEVICE",
            "cpu",
        ).strip(),
        whisper_compute_type=os.getenv(
            "WHISPER_COMPUTE_TYPE",
            "int8",
        ).strip(),
        max_voice_duration_seconds=max_voice_duration_seconds,
        task_api_url=task_api_url,
        task_api_timeout_seconds=task_api_timeout_seconds,
        task_api_service_token=task_api_service_token,
        app_timezone=app_timezone,
        app_locale=os.getenv(
            "APP_LOCALE",
            "ru-RU",
        ).strip(),
    )