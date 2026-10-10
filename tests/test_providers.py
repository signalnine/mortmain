import json

import httpx
import pytest

from mortmain import config as config_mod
from mortmain.providers import OpenRouterProvider, ProviderError, shell_tool

CFG = config_mod.load()
TOOLS = [shell_tool(CFG.text)]

REASONING_DETAILS = [{"type": "reasoning.encrypted", "data": "opaque==", "id": "rs_1", "format": "openai-responses-v1"}]


def ok_body(msg, usage=None, model="openai/gpt-6.1-sol"):
    return {"id": "gen-1", "model": model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": msg}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": 0.0012,
                               "completion_tokens_details": {"reasoning_tokens": 7}}}


def make(handler, **kw):
    return OpenRouterProvider(api_key="sk-test-not-real", transport=httpx.MockTransport(handler),
                              sleep=lambda s: None, **kw)


def test_request_shape_and_replay_verbatim():
    seen = []
    assistant = {"role": "assistant", "content": None, "reasoning": "thinking...",
                 "reasoning_details": REASONING_DETAILS,
                 "tool_calls": [{"id": "call_1", "type": "function",
                                 "function": {"name": "shell", "arguments": "{\"command\":\"ls\"}"}}]}

    def handler(req):
        seen.append(json.loads(req.content))
        assert req.headers["authorization"] == "Bearer sk-test-not-real"
        assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
        return httpx.Response(200, json=ok_body(assistant))

    p = make(handler)
    msgs = [{"role": "user", "content": "You have arrived. Read /rule."}]
    c = p.complete("openai/gpt-6.1-sol", msgs, tools=TOOLS, max_tokens=50, reasoning={"enabled": True})
    assert c.message == assistant
    assert c.usage == {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0012, "reasoning_tokens": 7}
    assert c.total_tokens == 120
    body = seen[0]
    assert body["model"] == "openai/gpt-6.1-sol"
    assert body["reasoning"] == {"enabled": True}
    assert body["max_tokens"] == 50
    assert body["tools"][0]["function"]["name"] == "shell"
    assert body["tools"][0]["function"]["parameters"]["required"] == ["command"]

    # second turn: stored assistant message goes back byte-for-byte, reasoning included
    msgs2 = msgs + [c.message, {"role": "tool", "tool_call_id": "call_1", "content": "rule\n"}]
    p.complete("openai/gpt-6.1-sol", msgs2, tools=TOOLS)
    sent = seen[1]["messages"][1]
    assert sent == assistant
    assert sent["reasoning_details"] == REASONING_DETAILS
    assert sent["reasoning"] == "thinking..."
    assert "reasoning" not in seen[1]


def test_reasoning_omitted_when_off():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=ok_body({"role": "assistant", "content": "hi"}))

    make(handler).complete("anthropic/claude-haiku-5.5", [{"role": "user", "content": "x"}], tools=TOOLS,
                           reasoning=CFG.species["haiku"].reasoning_param())
    assert "reasoning" not in seen[0]


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_retry_then_success(status):
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] < 3:
            return httpx.Response(status, json={"error": {"message": "busy"}}, headers={"retry-after": "1"})
        return httpx.Response(200, json=ok_body({"role": "assistant", "content": "ok"}))

    c = make(handler).complete("m", [{"role": "user", "content": "x"}])
    assert c.message["content"] == "ok" and n["i"] == 3


def test_retry_gives_up():
    p = make(lambda req: httpx.Response(503, text="down"), max_retries=2)
    with pytest.raises(ProviderError) as e:
        p.complete("m", [])
    assert e.value.status == 503


@pytest.mark.parametrize("status", [400, 401, 402, 404])
def test_hard_error_no_retry(status):
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(ProviderError) as e:
        make(handler).complete("m", [])
    assert n["i"] == 1
    assert "sk-test-not-real" not in str(e.value) and "sk-test-not-real" not in repr(e.value.body)


def test_error_in_200_body():
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(200, json={"error": {"code": 502, "message": "upstream"}})
        return httpx.Response(200, json=ok_body({"role": "assistant", "content": "ok"}))

    assert make(handler).complete("m", []).message["content"] == "ok"
    with pytest.raises(ProviderError):
        make(lambda r: httpx.Response(200, json={"error": {"code": 400, "message": "bad"}})).complete("m", [])


def test_transport_error_retried():
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=ok_body({"role": "assistant", "content": "ok"}))

    assert make(handler).complete("m", []).message["content"] == "ok"


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        OpenRouterProvider()


def test_repr_hides_key():
    p = make(lambda r: httpx.Response(200, json={}))
    assert "sk-test" not in repr(p)
