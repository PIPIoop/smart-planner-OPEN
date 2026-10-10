from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from config import load_settings


class ConfigTest(unittest.TestCase):
    def test_loads_shared_api_defaults_and_new_admin_name(self) -> None:
        environment = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ADMIN_USER_ID": "123456789",
            "TASK_API_SERVICE_TOKEN": "x" * 32,
            "APP_TIMEZONE": "Asia/Yekaterinburg",
        }
        with patch("config.load_dotenv"), patch.dict(os.environ, environment, clear=True):
            settings = load_settings()

        self.assertEqual(settings.task_api_url, "http://127.0.0.1:8080")
        self.assertEqual(settings.task_api_timeout_seconds, 10.0)
        self.assertEqual(settings.telegram_admin_user_id, 123456789)
        self.assertEqual(settings.telegram_owner_user_id, 123456789)
        self.assertEqual(settings.task_api_service_token, "x" * 32)

    def test_supports_legacy_owner_variable(self) -> None:
        environment = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_OWNER_USER_ID": "123456789",
            "TASK_API_SERVICE_TOKEN": "x" * 32,
        }
        with patch("config.load_dotenv"), patch.dict(os.environ, environment, clear=True):
            settings = load_settings()
        self.assertEqual(settings.telegram_admin_user_id, 123456789)

    def test_requires_positive_admin_user_id(self) -> None:
        environment = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ADMIN_USER_ID": "0",
            "TASK_API_SERVICE_TOKEN": "x" * 32,
        }
        with (
            patch("config.load_dotenv"),
            patch.dict(os.environ, environment, clear=True),
            self.assertRaisesRegex(RuntimeError, "TELEGRAM_ADMIN_USER_ID"),
        ):
            load_settings()


if __name__ == "__main__":
    unittest.main()