"""A small Groq client (OpenAI-compatible chat API) that returns JSON text.

Behind the LLMClient protocol so the provider can change without touching any agent.
"""

import time
from typing import Protocol

import httpx

from app.agents.settings import agent_settings

RETRYABLE = (429, 500, 502, 503, 504)


class LLMError(Exception):
    """The LLM could not be reached or returned something unusable."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> str:
        """Returns the model's reply, which must be a JSON object, as text."""
        ...


class GroqClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_s: float | None = None,
        transport: httpx.BaseTransport | None = None,
        retry_delay_s: float = 3.0,
    ) -> None:
        self._api_key = agent_settings.groq_api_key if api_key is None else api_key
        self._model = model or agent_settings.groq_model
        self._base_url = (base_url or agent_settings.groq_base_url).rstrip("/")
        self._timeout_s = timeout_s or agent_settings.llm_timeout_s
        self._transport = transport
        self._retry_delay_s = retry_delay_s

    def complete_json(self, system: str, user: str) -> str:
        if not self._api_key:
            raise LLMError("GROQ_API_KEY is not set (add it to the .env file in the repo root)")
        body = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last = "unknown problem"
        for attempt in range(2):  # one retry for rate limits and temporary errors
            try:
                with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                    response = client.post(
                        f"{self._base_url}/chat/completions", headers=headers, json=body
                    )
            except httpx.HTTPError as exc:
                last = f"network error: {exc}"
            else:
                if response.status_code == 200:
                    try:
                        return response.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, TypeError, ValueError) as exc:
                        raise LLMError("unexpected response shape from the LLM API") from exc
                if response.status_code not in RETRYABLE:
                    raise LLMError(f"LLM API returned HTTP {response.status_code}: {response.text[:300]}")
                last = f"HTTP {response.status_code}"
            if attempt == 0:
                time.sleep(self._retry_delay_s)
        raise LLMError(f"LLM request failed after one retry ({last})")