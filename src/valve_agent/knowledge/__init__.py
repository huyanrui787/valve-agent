"""企业知识底座导出。"""

from __future__ import annotations

from .repository import KnowledgeBase
from .seed import build_demo_kb

__all__ = ["KnowledgeBase", "build_demo_kb"]
