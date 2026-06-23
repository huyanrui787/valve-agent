"""FastAPI 接口测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from valve_agent.api.app import create_app

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_tender.txt"


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """把项目记录落盘到临时目录,并清空 lru_cache 让其重新读取。"""
    from valve_agent.api import deps

    monkeypatch.setenv("VALVE_DATA_DIR", str(tmp_path))
    deps.get_project_store.cache_clear()
    yield tmp_path
    deps.get_project_store.cache_clear()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "llm" in data


def test_quote_line(client):
    r = client.post(
        "/api/quote/line",
        json={"spec": "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316", "quantity": 2},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["quote"] is not None
    assert data["quote"]["product_code"]


def test_select_bad_spec(client):
    r = client.post("/api/quote/select", json={"spec": "无效"})
    assert r.status_code == 400


def test_parse_tender_upload(client):
    with SAMPLE.open("rb") as f:
        r = client.post(
            "/api/tender/parse",
            files={"file": ("sample_tender.txt", f, "text/plain")},
        )
    assert r.status_code == 200
    assert len(r.json()["requirements"]) >= 1


def test_tender_bid_multipart(client):
    with SAMPLE.open("rb") as f:
        r = client.post(
            "/api/tender/bid",
            data={"spec": "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"},
            files={"file": ("sample_tender.txt", f, "text/plain")},
        )
    assert r.status_code == 200
    body = r.json()
    assert body.get("package") is not None


def test_rag_search(client):
    r = client.post("/api/rag/search", json={"query": "球阀 蒸汽", "top_k": 3})
    assert r.status_code == 200
    assert len(r.json()["hits"]) >= 1


# ---------------------------------------------------------------------------
# 标书项目记录
# ---------------------------------------------------------------------------
def test_projects_empty(client, isolated_store):
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


def test_project_create_list_get_update(client, isolated_store):
    # 创建(内容生成后)
    payload = {
        "project_name": "某水务集团阀门集采",
        "word_count": 18000,
        "spec": "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316",
        "snapshot": {"outline": [{"id": "dev-table", "content": "x"}], "step": "write"},
    }
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 200
    created = r.json()
    pid = created["id"]
    assert pid
    assert created["project_name"] == "某水务集团阀门集采"
    assert created["word_count"] == 18000
    assert created["created_at"] and created["updated_at"]

    # 列表(摘要不含 snapshot)
    r = client.get("/api/projects")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == pid
    assert "snapshot" not in body["items"][0]

    # 详情(带回 snapshot 供续编)
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["snapshot"]["step"] == "write"
    assert detail["spec"].startswith("球阀")

    # 更新(编辑后刷新字数与时间戳)
    upd = {**payload, "word_count": 25000,
           "snapshot": {"outline": [], "step": "write"}}
    r = client.put(f"/api/projects/{pid}", json=upd)
    assert r.status_code == 200
    assert r.json()["word_count"] == 25000

    r = client.get("/api/projects")
    assert r.json()["total"] == 1  # 更新不应新增记录


def test_project_get_missing(client, isolated_store):
    assert client.get("/api/projects/nope").status_code == 404
    assert client.put("/api/projects/nope", json={"project_name": "x"}).status_code == 404
