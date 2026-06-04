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
