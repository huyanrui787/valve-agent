"""API 依赖:共享知识库与 Agent 单例。"""

from __future__ import annotations

from functools import lru_cache

from ..agents import BidAgent, QuoteAgent
from ..knowledge import KnowledgeBase, build_demo_kb
from ..projects import BidProjectStore
from ..rag import RagRetriever


@lru_cache
def get_kb() -> KnowledgeBase:
    return build_demo_kb()


@lru_cache
def get_quote_agent() -> QuoteAgent:
    return QuoteAgent(get_kb())


@lru_cache
def get_bid_agent() -> BidAgent:
    kb = get_kb()
    return BidAgent(kb, retriever=RagRetriever(kb))


@lru_cache
def get_project_store() -> BidProjectStore:
    return BidProjectStore()
