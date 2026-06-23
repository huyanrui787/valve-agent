"""标书项目记录的 JSON 文件存储(沿用 FileSyncAdapter 的落盘思路)。

设计要点:
  - 一条记录一个 JSON 文件,落到 data_dir/projects/{id}.json,重启后仍在。
  - snapshot 是前端续编所需的整份状态(大纲/解析结果/引擎参数等),
    后端不解析其内部结构,只透传 —— 保持前后端低耦合,前端改字段不必动后端。
  - 顶层另存 project_name / word_count / status / 时间戳,供列表页展示与排序。
  - 生产可换关系库/对象存储:实现同样的 create/get/list/update 即可。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BidProject(BaseModel):
    """一条标书项目记录。"""

    id: str
    project_name: str = "未命名标书"
    status: str = "completed"          # 预留:completed / draft …
    word_count: int = 0
    spec: str = ""                     # 导出/再做所需的工况串
    created_at: str = ""
    updated_at: str = ""
    # 前端续编所需的整份状态;后端只透传不解析。
    snapshot: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_data_dir() -> Path:
    """优先读 VALVE_DATA_DIR;默认落到项目根的 ./data。"""
    env = os.environ.get("VALVE_DATA_DIR")
    if env:
        return Path(env)
    return Path("./data")


class BidProjectStore:
    """标书项目记录的文件仓库:create / get / list / update。"""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        root = Path(data_dir) if data_dir is not None else _default_data_dir()
        self.dir = root / "projects"

    def _path(self, project_id: str) -> Path:
        return self.dir / f"{project_id}.json"

    def _write(self, project: BidProject) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(project.id).write_text(
            project.model_dump_json(indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def create(
        self,
        *,
        project_name: str,
        word_count: int = 0,
        spec: str = "",
        status: str = "completed",
        snapshot: dict | None = None,
    ) -> BidProject:
        """新建一条记录(内容生成后调用),返回带 id 的项目。"""
        now = _now()
        project = BidProject(
            id=uuid.uuid4().hex,
            project_name=project_name or "未命名标书",
            status=status,
            word_count=word_count,
            spec=spec,
            created_at=now,
            updated_at=now,
            snapshot=snapshot or {},
        )
        self._write(project)
        return project

    def get(self, project_id: str) -> BidProject | None:
        path = self._path(project_id)
        if not path.is_file():
            return None
        try:
            return BidProject.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None

    def list(self) -> list[BidProject]:
        """列出全部记录,按 updated_at 倒序(最近更新在前)。"""
        if not self.dir.is_dir():
            return []
        items: list[BidProject] = []
        for path in self.dir.glob("*.json"):
            try:
                items.append(BidProject.model_validate_json(
                    path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue  # 跳过损坏文件,不影响整表
        items.sort(key=lambda p: p.updated_at, reverse=True)
        return items

    def update(
        self,
        project_id: str,
        *,
        project_name: str | None = None,
        word_count: int | None = None,
        spec: str | None = None,
        status: str | None = None,
        snapshot: dict | None = None,
    ) -> BidProject | None:
        """更新一条记录(编辑/导出后调用),刷新 updated_at。不存在返回 None。"""
        project = self.get(project_id)
        if project is None:
            return None
        if project_name is not None:
            project.project_name = project_name or project.project_name
        if word_count is not None:
            project.word_count = word_count
        if spec is not None:
            project.spec = spec
        if status is not None:
            project.status = status
        if snapshot is not None:
            project.snapshot = snapshot
        project.updated_at = _now()
        self._write(project)
        return project
