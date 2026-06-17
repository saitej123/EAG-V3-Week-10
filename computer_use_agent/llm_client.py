"""Direct Gemini LLM dispatch for DAG skills."""

from __future__ import annotations

from typing import Any

from .llm_env import gemini_models_with_fallbacks, shared_gemini_client
from .llm_retry import generate_content_with_retry, loads_json_lenient


class SkillLLMClient:
    """Call Gemini directly for all DAG skills."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def chat(
        self,
        *,
        agent: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_schema: type | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        del tools
        client = shared_gemini_client()
        models = gemini_models_with_fallbacks()
        if client is None or not models:
            raise RuntimeError("Gemini not configured - set GEMINI_API_KEY in .env")

        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system:
            config_kwargs["system_instruction"] = system
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
        config = types.GenerateContentConfig(**config_kwargs)
        response = generate_content_with_retry(
            model=models[0],
            contents=prompt,
            config=config,
            label=f"dag:{agent}",
        )
        return (response.text or "").strip()

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        return loads_json_lenient(text)
