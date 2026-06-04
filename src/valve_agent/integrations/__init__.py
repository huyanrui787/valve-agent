"""外部系统集成。"""

from __future__ import annotations

from .base import CRMClient, ERPClient, SyncResult
from .file_adapter import FileSyncAdapter

__all__ = ["CRMClient", "ERPClient", "SyncResult", "FileSyncAdapter"]
