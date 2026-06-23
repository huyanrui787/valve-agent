"""标书项目记录:把内存草稿升级为可留存、可重新打开续编的项目。

一条记录在标书引擎跑完(偏离表/废标体检/技术方案生成)那一刻创建,
落盘为 JSON 文件,刷新或重启后仍可在「我的标书」列表里继续编辑。
"""

from __future__ import annotations

from .store import BidProject, BidProjectStore

__all__ = ["BidProject", "BidProjectStore"]
