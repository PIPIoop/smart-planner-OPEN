from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from telegram.error import TimedOut

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from bot import global_error_handler


class GlobalErrorHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_network_timeout_is_logged_without_secondary_telegram_request(self) -> None:
        context = SimpleNamespace(error=TimedOut("Timed out"))

        with self.assertLogs("bot", level="WARNING") as captured:
            await global_error_handler(object(), context)

        self.assertTrue(any("Telegram network error" in line for line in captured.output))

    async def test_unexpected_exception_is_logged(self) -> None:
        context = SimpleNamespace(error=ValueError("boom"))

        with self.assertLogs("bot", level="ERROR") as captured:
            await global_error_handler(object(), context)

        self.assertTrue(any("Unhandled exception" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
