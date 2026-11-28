import json

import httpx
import pytest

from app.agents.llm import GroqClient, LLMError


def make_client(handler, key="test-key"):
    return GroqClient(
        api_key=key,
        model="test-model",
        base_url="https://example.test/v1",
        timeout_s=5,
        transport=httpx.MockTransport(handler),
        retry_delay_s=0.0,
    )


def ok():
    return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})


def test_request_shape_and_result():
    seen = []

    def handler(request):
        seen.append(request)
        return ok()

    result = make_client(handler).complete_json("SYS", "USER")
    assert result == '{"a": 1}'
    request = seen[0]
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_rate_limit_is_retried_once():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else ok()

    assert make_client(handler).complete_json("s", "u") == '{"a": 1}'
    assert len(calls) == 2


def test_gives_up_after_one_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429)

    with pytest.raises(LLMError):
        make_client(handler).complete_json("s", "u")
    assert len(calls) == 2


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with pytest.raises(LLMError):
        make_client(handler).complete_json("s", "u")
    assert len(calls) == 1


def test_missing_key_is_reported():
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        make_client(lambda request: ok(), key="").complete_json("s", "u")