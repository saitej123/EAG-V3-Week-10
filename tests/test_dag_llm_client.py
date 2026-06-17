"""DAG LLM client uses direct Gemini dispatch."""

from __future__ import annotations

from computer_use_agent.llm_client import SkillLLMClient


def test_dag_client_stores_session_id():
    client = SkillLLMClient("test")
    assert client.session_id == "test"
    assert not hasattr(client, "base_url")


def test_parse_json_lenient():
    assert SkillLLMClient.parse_json('{"ok": true}') == {"ok": True}
