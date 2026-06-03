"""共享 fixtures。"""

from __future__ import annotations

from datetime import date

import pytest

from valve_agent.knowledge import build_demo_kb


@pytest.fixture
def kb():
    return build_demo_kb()


@pytest.fixture
def basis():
    return date(2026, 6, 4)
