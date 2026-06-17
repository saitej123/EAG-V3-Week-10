"""LLM env helpers use Gemini SDK defaults."""

from __future__ import annotations

import computer_use_agent.llm_env as llm_env


def test_try_embed_returns_none_without_gemini_client(monkeypatch) -> None:
    monkeypatch.setattr(llm_env, "shared_gemini_client", lambda: None)
    assert llm_env.try_embed_text("hello world") is None


def test_default_embed_model_is_v2(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_EMBED_MODEL", raising=False)
    assert llm_env.gemini_embed_model() == "gemini-embedding-2"


def test_format_embed_input_query() -> None:
    out = llm_env.format_embed_input("What is DPO?", task_type="retrieval_query")
    assert out == "task: search result | query: What is DPO?"


def test_format_embed_input_document() -> None:
    out = llm_env.format_embed_input("chunk body", task_type="retrieval_document", title="DPO paper")
    assert out == "title: DPO paper | text: chunk body"
