import json

import httpx
import pytest

from mortmain import config as config_mod
from mortmain.providers import (AnthropicProvider, OpenAIResponsesProvider, OpenRouterProvider, ProviderError,
                                RoutingProvider, make_provider, shell_tool)

TEXT = {"shell_tool_description": "Run a command line in bash.", "shell_command_description": "command line"}
PRICES = config_mod.load().section("prices")

CONV = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "arrive"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "shell", "arguments": '{"command": "cat /rule"}'}}]},
    {"role": "tool", "tool_call_id": "c1", "content": "RULE"},
    {"role": "user", "content": "[bell] 0.25"},
]


def mock(handler, cls, **kw):
    return cls(api_key="sk-test-not-real", prices=PRICES, transport=httpx.MockTransport(handler),
               sleep=lambda s: None, **kw)


# ----------------------------------------------------------------- anthropic
def anthropic_reply(blocks, stop="tool_use", usage=None):
    return {"type": "message", "model": "claude-haiku-5-5", "content": blocks, "stop_reason": stop,
            "usage": usage or {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 2000,
                               "cache_creation_input_tokens": 400}}


def test_anthropic_request_shape():
    seen = {}

    def handler(req):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json=anthropic_reply([{"type": "text", "text": "ok"}], stop="end_turn"))

    p = mock(handler, AnthropicProvider, workspace_id="wrkspc_x")
    p.complete("anthropic/claude-haiku-5.5", CONV, tools=[shell_tool(TEXT)], tool_choice="none", max_tokens=4096)
    b = seen["body"]
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-test-not-real"
    assert seen["headers"]["anthropic-workspace-id"] == "wrkspc_x"
    assert b["model"] == "claude-haiku-5-5" and b["system"] == "sys" and b["max_tokens"] == 4096
    assert b["tool_choice"] == {"type": "none"}
    assert b["tools"][0]["name"] == "shell" and b["tools"][0]["input_schema"]["required"] == ["command"]
    assert [m["role"] for m in b["messages"]] == ["user", "assistant", "user"]
    assert b["messages"][1]["content"] == [{"type": "tool_use", "id": "c1", "name": "shell",
                                            "input": {"command": "cat /rule"}}]
    # tool result first, then the bell text, in one user turn; cache breakpoint on the last block
    last = b["messages"][2]["content"]
    assert last[0] == {"type": "tool_result", "tool_use_id": "c1", "content": "RULE"}
    assert last[1] == {"type": "text", "text": "[bell] 0.25", "cache_control": {"type": "ephemeral"}}
    assert "thinking" not in b
    # the stored conversation was not touched by the breakpoint
    assert "cache_control" not in json.dumps(CONV)


def test_anthropic_reply_parse_cost_and_exact_replay():
    blocks = [{"type": "thinking", "thinking": "hm", "signature": "sig=="},
              {"type": "text", "text": "looking"},
              {"type": "tool_use", "id": "tu_1", "name": "shell", "input": {"command": "ls"}}]
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=anthropic_reply(blocks))

    p = mock(handler, AnthropicProvider)
    c = p.complete("anthropic/claude-haiku-5.5", CONV, tools=[shell_tool(TEXT)], max_tokens=4096,
                   reasoning={"enabled": True})
    assert bodies[0]["thinking"] == {"type": "adaptive"} and "output_config" not in bodies[0]
    assert c.message["content"] == "looking" and c.message["reasoning"] == "hm"
    assert c.tool_calls == [{"id": "tu_1", "type": "function", "function": {"name": "shell",
                                                                           "arguments": '{"command": "ls"}'}}]
    assert c.raw["choices"][0]["finish_reason"] == "tool_calls"
    assert c.model == "anthropic/claude-haiku-5-5"
    assert c.usage["prompt_tokens"] == 3400 and c.usage["completion_tokens"] == 100
    assert c.usage["cost"] == pytest.approx((1000 * 0.10 + 2000 * 0.01 + 400 * 0.125 + 100 * 0.50) / 1e6)
    # replay: the native blocks go back verbatim (signature kept)
    conv = CONV + [c.message, {"role": "tool", "tool_call_id": "tu_1", "content": "x"}]
    p.complete("anthropic/claude-haiku-5.5", conv, tools=[shell_tool(TEXT)], max_tokens=4096)
    assert bodies[1]["messages"][3] == {"role": "assistant", "content": blocks}


@pytest.mark.parametrize("status,retried", [(529, True), (500, True), (400, False)])
def test_anthropic_retry(status, retried):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(status, json={"type": "error", "error": {"type": "overloaded_error"}})
        return httpx.Response(200, json=anthropic_reply([{"type": "text", "text": "ok"}], stop="end_turn"))

    p = mock(handler, AnthropicProvider)
    if retried:
        assert p.complete("anthropic/claude-haiku-5.5", CONV).message["content"] == "ok"
    else:
        with pytest.raises(ProviderError):
            p.complete("anthropic/claude-haiku-5.5", CONV)


def test_anthropic_key_from_either_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_KEY", raising=False)
    with pytest.raises(ProviderError) as e:
        AnthropicProvider(prices=PRICES)
    monkeypatch.setenv("ANTHROPIC_KEY", "sk-secret-value")
    p = AnthropicProvider(prices=PRICES)
    assert "sk-secret" not in repr(p) and "sk-secret" not in str(e.value)


# -------------------------------------------------------------------- openai
def openai_reply(output, usage=None, status="completed"):
    return {"id": "resp_1", "model": "gpt-6.1-sol", "status": status, "output": output,
            "usage": usage or {"input_tokens": 5000, "output_tokens": 300,
                               "input_tokens_details": {"cached_tokens": 4000},
                               "output_tokens_details": {"reasoning_tokens": 200}}}


def test_openai_request_parse_and_replay():
    out = [{"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "ENC", "status": None},
           {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": "I will look.", "annotations": []}]},
           {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "shell",
            "arguments": '{"command":"ls"}', "status": "completed"}]
    bodies = []

    def handler(req):
        assert str(req.url) == "https://api.openai.com/v1/responses"
        assert req.headers["authorization"] == "Bearer sk-test-not-real"
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=openai_reply(out))

    p = mock(handler, OpenAIResponsesProvider)
    c = p.complete("openai/gpt-6.1-sol", CONV, tools=[shell_tool(TEXT)], max_tokens=8192, reasoning={"enabled": True})
    b = bodies[0]
    assert b["model"] == "gpt-6.1-sol" and b["instructions"] == "sys" and b["store"] is False
    assert b["include"] == ["reasoning.encrypted_content"] and b["reasoning"] == {"effort": "medium"}
    assert b["max_output_tokens"] == 8192
    assert b["tools"][0] == {"type": "function", "name": "shell", "description": TEXT["shell_tool_description"],
                             "parameters": shell_tool(TEXT)["function"]["parameters"]}
    assert b["input"] == [
        {"role": "user", "content": "arrive"},
        {"type": "function_call", "call_id": "c1", "name": "shell", "arguments": '{"command": "cat /rule"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "RULE"},
        {"role": "user", "content": "[bell] 0.25"}]
    assert c.message["content"] == "I will look." and c.message["reasoning"] == "[encrypted]"
    assert c.tool_calls[0]["id"] == "call_1"
    assert c.raw["choices"][0]["finish_reason"] == "tool_calls"
    assert c.usage == {"prompt_tokens": 5000, "completion_tokens": 300, "cached_tokens": 4000,
                       "reasoning_tokens": 200, "cost": pytest.approx((1000 * 2.5 + 4000 * 0.1 + 300 * 10) / 1e6)}
    conv = CONV + [c.message, {"role": "tool", "tool_call_id": "call_1", "content": "a b"}]
    p.complete("openai/gpt-6.1-sol", conv, tools=[shell_tool(TEXT)])
    assert bodies[1]["input"][4:] == [
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "ENC"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "I will look."}]},
        {"type": "function_call", "call_id": "call_1", "name": "shell", "arguments": '{"command":"ls"}'},
        {"type": "function_call_output", "call_id": "call_1", "output": "a b"}]


def test_openai_incomplete_is_length():
    def handler(req):
        return httpx.Response(200, json={**openai_reply([]), "status": "incomplete",
                                         "incomplete_details": {"reason": "max_output_tokens"}})

    c = mock(handler, OpenAIResponsesProvider).complete("openai/gpt-6.1-sol", CONV)
    assert c.raw["choices"][0]["finish_reason"] == "length"


def test_unknown_price_refuses():
    def handler(req):
        return httpx.Response(200, json=openai_reply([]))

    with pytest.raises(ProviderError, match="no price"):
        mock(handler, OpenAIResponsesProvider).complete("openai/gpt-unpriced", CONV)


# ------------------------------------------------------------------- routing
def test_routing_by_prefix_and_lazy(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    r = make_provider(config_mod.load())
    assert r.routes == {"anthropic": "anthropic", "openai": "openai", "local": "local"}
    with pytest.raises(ProviderError, match="ANTHROPIC"):   # built on first use only
        r.provider_for("anthropic/claude-haiku-5.5")
    assert isinstance(r.provider_for("meta/x"), OpenRouterProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa")
    assert isinstance(r.provider_for("openai/gpt-6.1-sol"), OpenAIResponsesProvider)
    assert isinstance(RoutingProvider({}, {}).provider_for("anthropic/x"), OpenRouterProvider)
    with pytest.raises(ProviderError):
        RoutingProvider({"anthropic": "bogus"}, {})


def test_openrouter_strips_native():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    p = OpenRouterProvider(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    p.complete("anthropic/claude-haiku-5.5", [{"role": "assistant", "content": "a", "_native": {"x": 1}}])
    assert "_native" not in json.dumps(seen["body"])


def test_anthropic_thinking_modes():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=anthropic_reply([{"type": "text", "text": "ok"}], stop="end_turn"))

    p = mock(handler, AnthropicProvider)
    for r in (None, {"enabled": False}, {"enabled": True, "effort": "high"}):
        p.complete("anthropic/claude-haiku-5.5", CONV, reasoning=r)
    assert "thinking" not in bodies[0]
    assert bodies[1]["thinking"] == {"type": "disabled"}
    assert bodies[2]["thinking"] == {"type": "adaptive"} and bodies[2]["output_config"] == {"effort": "high"}


def test_reasoning_config_values():
    cfg = config_mod.load()
    for v, want in ((False, None), (True, {"enabled": True}), ("off", {"enabled": False})):
        c = cfg.with_overrides({"species": {"haiku": {"reasoning": v}}})
        assert c.species["haiku"].reasoning_param() == want
    with pytest.raises(ValueError):
        cfg.with_overrides({"species": {"haiku": {"reasoning": "maybe"}}})


def test_local_provider_strips_prefix_sends_no_key():
    from mortmain.providers import LocalProvider
    seen = []

    def handler(req):
        seen.append((str(req.url), dict(req.headers), json.loads(req.content)))
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

    r = RoutingProvider({"local": "local"}, {}, local_url="http://127.0.0.1:9/v1/chat/completions",
                        transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert isinstance(r.provider_for("local/m"), LocalProvider)
    c = r.complete("local/m", [{"role": "user", "content": "x"}])
    url, headers, body = seen[0]
    assert url == "http://127.0.0.1:9/v1/chat/completions" and body["model"] == "m"
    assert "authorization" not in headers
    assert c.model == "local/m" and c.usage == {"prompt_tokens": 3, "completion_tokens": 1}
    with pytest.raises(ProviderError):
        RoutingProvider({"local": "local"}, {}).provider_for("local/m")


def test_optional_species_only_when_chosen():
    cfg = config_mod.load()
    assert "qwen" not in cfg.species and set(cfg.species) == {"haiku", "sol"}
    run = cfg.with_species(["qwen", "sol"])
    assert set(run.species) == {"qwen", "sol"} and run.species["qwen"].model.startswith("local/")
    with pytest.raises(KeyError):
        cfg.with_species(["nope"])
