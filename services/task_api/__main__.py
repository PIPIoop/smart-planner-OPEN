from __future__ import annotations

import uvicorn

from .config import load_task_api_settings


def main() -> None:
    settings = load_task_api_settings()
    uvicorn.run(
        "services.task_api.app:create_default_app",
        host=settings.host,
        port=settings.port,
        factory=True,
        reload=False,
    )


if __name__ == "__main__":
    main()

