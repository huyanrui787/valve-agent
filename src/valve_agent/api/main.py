"""启动 API 服务: uv run valve-api"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("VALVE_API_HOST", "0.0.0.0")
    port = int(os.environ.get("VALVE_API_PORT", "8000"))
    reload = os.environ.get("VALVE_API_RELOAD", "1") == "1"
    uvicorn.run(
        "valve_agent.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
