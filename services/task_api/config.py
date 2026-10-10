from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class TaskApiSettings:
    database_path: Path
    host: str
    port: int
    service_token: str
    web_admin_password: str


def load_task_api_settings() -> TaskApiSettings:
    load_dotenv(Path(__file__).parents[1] / "tg_voice_bot" / ".env")
    default_database = Path(__file__).parent / "data" / "tasks.sqlite3"
    database_path = Path(
        os.getenv("TASK_DB_PATH", str(default_database))
    ).expanduser()

    port_raw = os.getenv("TASK_API_PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError as error:
        raise RuntimeError("TASK_API_PORT must be an integer") from error

    if not 1 <= port <= 65535:
        raise RuntimeError("TASK_API_PORT must be between 1 and 65535")

    service_token = os.getenv("TASK_API_SERVICE_TOKEN", "").strip()
    if len(service_token) < 32:
        raise RuntimeError(
            "TASK_API_SERVICE_TOKEN must contain at least 32 characters"
        )
    web_admin_password = os.getenv("TASK_API_WEB_ADMIN_PASSWORD", "").strip()
    if len(web_admin_password) < 16:
        raise RuntimeError(
            "TASK_API_WEB_ADMIN_PASSWORD must contain at least 16 characters"
        )
    return TaskApiSettings(
        database_path=database_path,
        host=os.getenv("TASK_API_HOST", "127.0.0.1").strip(),
        port=port,
        service_token=service_token,
        web_admin_password=web_admin_password,
    )

