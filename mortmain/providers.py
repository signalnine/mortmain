"""Providers behind one interface: OpenRouter chat completions, and the native
Anthropic Messages and OpenAI Responses APIs.

The stored conversation is in chat-completions form (system / user /
assistant with tool_calls / tool). OpenRouter takes it as is; assistant
messages are stored and replayed verbatim, `reasoning` / `reasoning_details`
included. The native providers translate it on the way out, and store each
reply's own blocks under `_native` so a replay to the same provider is exact
(thinking blocks with signatures, encrypted reasoning items). A message without
`_native` for that provider is rebuilt from its chat fields.

Native APIs report no cost; it is computed from `[prices]` (USD per million
tokens, by native model id). RoutingProvider picks a provider by the model's
prefix (`anthropic/`, `openai/`, `local/`) from `[providers]`; `local` is a
chat-completions server on this machine at `[local] url`, billed at nothing.

API keys come from the environment and are never logged, stored or put in an
exception message.
"""
from __future__ import annotations

import copy
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_SEEDS = random.SystemRandom()
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class Completion:
    message: dict
    usage: dict
    raw: dict
    model: str

    @property
    def tool_calls(self) -> list[dict]:
        return list(self.message.get("tool_calls") or [])

    @property
    def total_tokens(self) -> int:
        return int(self.usage.get("prompt_tokens", 0)) + int(self.usage.get("completion_tokens", 0))


def shell_tool(text: dict[str, str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "shell",
            "description": text["shell_tool_description"],
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": text["shell_command_description"]}},
                "required": ["command"],
            },
        },
    }


class Provider(Protocol):
    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        max_tokens: int | None = None,
        reasoning: dict | None = None,
        seed: int | None = None,
    ) -> Completion: ...


def normalize_usage(u: dict | None) -> dict:
    u = u or {}
    out = {
        "prompt_tokens": int(u.get("prompt_tokens") or 0),
        "completion_tokens": int(u.get("completion_tokens") or 0),
    }
    if u.get("cost") is not None:
        out["cost"] = float(u["cost"])
    ctd = u.get("completion_tokens_details") or {}
    if ctd.get("reasoning_tokens") is not None:
        out["reasoning_tokens"] = int(ctd["reasoning_tokens"])
    ptd = u.get("prompt_tokens_details") or {}
    if ptd.get("cached_tokens") is not None:
        out["cached_tokens"] = int(ptd["cached_tokens"])
    return out


def wire_messages(messages: list[dict]) -> list[dict]:
    """Messages as sent: exactly as stored. Assistant messages are replayed as
    the provider returned them, reasoning fields included. `_native` blocks
    are for the native providers only."""
    return [{k: v for k, v in m.items() if k != "_native"} for m in messages]


class _Retry(Exception):
    def __init__(self, err: ProviderError):
        self.err = err


class _HttpProvider:
    """POST with retries on transport errors, retryable statuses and bodies a
    parser marks retryable (_Retry)."""

    def __init__(self, *, transport=None, timeout: float = 600.0, max_retries: int = 6, backoff_base: float = 2.0,
                 backoff_cap: float = 120.0, sleep: Callable[[float], None] = time.sleep):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def _delay(self, attempt: int, resp: httpx.Response | None) -> float:
        if resp is not None:
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    return min(float(ra), self.backoff_cap)
                except ValueError:
                    pass
        d = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return d * (0.5 + random.random() / 2)

    def _post(self, url: str, headers: dict, body: dict, parse: Callable[[dict, int], Completion]) -> Completion:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            resp = None
            try:
                resp = self._client.post(url, headers=headers, content=json.dumps(body))
            except (httpx.TransportError,) as e:
                last = ProviderError(f"transport: {type(e).__name__}")
            else:
                if resp.status_code in RETRY_STATUS:
                    last = ProviderError(f"http {resp.status_code}", resp.status_code, _safe_body(resp))
                elif resp.status_code >= 400:
                    raise ProviderError(f"http {resp.status_code}", resp.status_code, _safe_body(resp))
                else:
                    try:
                        data = resp.json()
                    except ValueError:
                        last = ProviderError("bad json from provider", resp.status_code)
                    else:
                        try:
                            return parse(data, resp.status_code)
                        except _Retry as r:
                            last = r.err
            if attempt < self.max_retries:
                self._sleep(self._delay(attempt, resp))
        assert last is not None
        raise last


class OpenRouterProvider(_HttpProvider):
    send_seed = False
    def __init__(self, *, api_key: str | None = None, url: str = OPENROUTER_URL, extra_body: dict | None = None,
                 **kw):
        key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if not key and api_key != "":
            raise ProviderError("OPENROUTER_API_KEY is not set")
        super().__init__(**kw)
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.url = url
        self.extra_body = extra_body or {}

    def __repr__(self) -> str:  # never show the key
        return f"OpenRouterProvider(url={self.url!r})"

    def build_body(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None) -> dict:
        body: dict[str, Any] = {"model": model, "messages": wire_messages(messages), "usage": {"include": True}}
        if tools:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if reasoning is not None:
            body["reasoning"] = reasoning
        body.update(self.extra_body)
        return body

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None,
                 seed=None) -> Completion:
        body = self.build_body(model, messages, tools, tool_choice, max_tokens, reasoning)
        if self.send_seed:
            body["seed"] = seed if seed is not None else _SEEDS.getrandbits(62)

        def parse(data, status):
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                code = err.get("code") if isinstance(err, dict) else None
                if isinstance(code, int) and code in RETRY_STATUS:
                    raise _Retry(ProviderError(f"provider error {code}", code, err))
                raise ProviderError(f"provider error {code}", code, err)
            choices = data.get("choices") or []
            if not choices or "message" not in choices[0]:
                # empty choices happen on upstream hiccups; retry
                raise _Retry(ProviderError("no choices", status, data))
            msg = dict(choices[0]["message"])
            msg.setdefault("role", "assistant")
            return Completion(message=msg, usage=normalize_usage(data.get("usage")), raw=data,
                              model=data.get("model", model))

        return self._post(self.url, self._headers, body, parse)


class LocalProvider(OpenRouterProvider):
    """A chat-completions server on this machine (`[local] url`), no key, no
    cost. The model prefix is stripped: `local/NAME` is sent as `NAME`.

    Every request carries a `seed`: q27 samples with seed 0 when none is sent,
    so the same prompt gave the same output (lineage qwen1: identical first
    turns for every monk). The caller's seed when given (a monk's turn), else
    a fresh one. Other providers ignore `seed`."""

    send_seed = True

    def __init__(self, *, url: str | None = None, **kw):
        if not url:
            raise ProviderError("[local] url is not set")
        super().__init__(api_key="", url=url, **kw)
        self._headers = {"Content-Type": "application/json"}

    def __repr__(self) -> str:
        return f"LocalProvider(url={self.url!r})"

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None,
                 seed=None) -> Completion:
        comp = super().complete(_split_model(model)[1], messages, tools, tool_choice, max_tokens, reasoning, seed)
        comp.model = model
        return comp


# ------------------------------------------------------------------ native
def price_cost(prices: dict, native_model: str, *, uncached: int, output: int, cache_read: int = 0,
               cache_write: int = 0) -> float:
    p = prices.get(native_model)
    if p is None:
        raise ProviderError(f"no price for {native_model}")
    return (uncached * p["input"] + output * p["output"] + cache_read * p.get("cache_read", p["input"])
            + cache_write * p.get("cache_write", p["input"])) / 1e6


def _split_model(model: str) -> tuple[str, str]:
    prefix, _, name = model.partition("/")
    return (prefix, name) if name else ("", prefix)


def _system_text(messages: list[dict]) -> str:
    return "\n\n".join(_plain(m.get("content")) for m in messages if m.get("role") == "system")


def _plain(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def _args(call: dict) -> dict:
    try:
        v = json.loads((call.get("function") or {}).get("arguments") or "{}")
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def _chat_finish(native: str | None) -> str | None:
    return {"end_turn": "stop", "stop_sequence": "stop", "tool_use": "tool_calls", "max_tokens": "length",
            "pause_turn": "stop"}.get(native, native)


class AnthropicProvider(_HttpProvider):
    """Messages API. Model `anthropic/claude-haiku-5.5` -> `claude-haiku-5-5`.
    The last block of each request carries a cache breakpoint."""

    URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"

    def __init__(self, *, prices: dict, api_key: str | None = None, workspace_id: str | None = None,
                 url: str = URL, **kw):
        key = api_key if api_key is not None else (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_KEY"))
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY (or ANTHROPIC_KEY) is not set")
        super().__init__(**kw)
        ws = workspace_id if workspace_id is not None else os.environ.get("ANTHROPIC_WORKSPACE_ID")
        self._headers = {"x-api-key": key, "anthropic-version": self.VERSION, "content-type": "application/json"}
        if ws:
            self._headers["anthropic-workspace-id"] = ws
        self.url = url
        self.prices = prices

    def __repr__(self) -> str:
        return f"AnthropicProvider(url={self.url!r})"

    @staticmethod
    def native_model(model: str) -> str:
        return _split_model(model)[1].replace(".", "-")

    @staticmethod
    def wire(messages: list[dict]) -> list[dict]:
        out: list[dict] = []

        def push(role, blocks):
            if not blocks:
                return
            if out and out[-1]["role"] == role:
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": role, "content": list(blocks)})

        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "user":
                text = _plain(m.get("content"))
                push("user", [{"type": "text", "text": text}] if text else [])
            elif role == "tool":
                push("user", [{"type": "tool_result", "tool_use_id": m.get("tool_call_id"),
                               "content": _plain(m.get("content")) or "(empty)"}])
            elif role == "assistant":
                nat = m.get("_native") or {}
                if nat.get("provider") == "anthropic":
                    blocks = copy.deepcopy(nat["content"])
                else:
                    text = _plain(m.get("content"))
                    blocks = [{"type": "text", "text": text}] if text else []
                    blocks += [{"type": "tool_use", "id": c.get("id"), "name": (c.get("function") or {}).get("name"),
                                "input": _args(c)} for c in m.get("tool_calls") or []]
                push("assistant", blocks)
        return out

    def build_body(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None) -> dict:
        wire = self.wire(messages)
        if wire and wire[-1]["content"]:
            last = wire[-1]["content"][-1]
            if last.get("type") in ("text", "tool_result"):
                last["cache_control"] = {"type": "ephemeral"}
        body: dict[str, Any] = {"model": self.native_model(model), "max_tokens": max_tokens or 4096,
                                "messages": wire}
        system = _system_text(messages)
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                              "input_schema": t["function"]["parameters"]} for t in tools]
        if tool_choice is not None:
            body["tool_choice"] = {"none": {"type": "none"}, "required": {"type": "any"},
                                   "auto": {"type": "auto"}}.get(tool_choice, tool_choice)
        if reasoning is not None and reasoning.get("enabled") is False:
            body["thinking"] = {"type": "disabled"}
        elif reasoning:
            # Haiku 5.5 takes only adaptive thinking; effort sets how much
            body["thinking"] = {"type": "adaptive"}
            if reasoning.get("effort"):
                body["output_config"] = {"effort": reasoning["effort"]}
        return body

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None,
                 seed=None) -> Completion:
        body = self.build_body(model, messages, tools, tool_choice, max_tokens, reasoning)

        def parse(data, status):
            if data.get("type") == "error":
                err = data.get("error") or {}
                if err.get("type") in ("overloaded_error", "api_error", "rate_limit_error"):
                    raise _Retry(ProviderError(f"provider error {err.get('type')}", status, err))
                raise ProviderError(f"provider error {err.get('type')}", status, err)
            blocks = data.get("content") or []
            msg: dict[str, Any] = {"role": "assistant",
                                   "content": "".join(b.get("text", "") for b in blocks if b.get("type") == "text")}
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                     for b in blocks if b.get("type") == "tool_use"]
            if calls:
                msg["tool_calls"] = calls
            thinking = [b for b in blocks if b.get("type") in ("thinking", "redacted_thinking")]
            if thinking:
                msg["reasoning"] = "\n".join(b.get("thinking", "") for b in thinking) or "[redacted]"
            msg["_native"] = {"provider": "anthropic", "content": blocks}
            u = data.get("usage") or {}
            unc, out = int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
            cr, cw = int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)
            native = data.get("model") or body["model"]
            usage = {"prompt_tokens": unc + cr + cw, "completion_tokens": out, "cached_tokens": cr,
                     "cache_write_tokens": cw,
                     "cost": round(price_cost(self.prices, body["model"], uncached=unc, output=out, cache_read=cr,
                                              cache_write=cw), 10)}
            raw = {"choices": [{"finish_reason": _chat_finish(data.get("stop_reason"))}], "native": data}
            return Completion(message=msg, usage=usage, raw=raw, model=f"anthropic/{native}")

        return self._post(self.url, self._headers, body, parse)


class OpenAIResponsesProvider(_HttpProvider):
    """Responses API, stateless (store false), encrypted reasoning carried in
    the conversation. Model `openai/gpt-6.1-sol` -> `gpt-6.1-sol`."""

    URL = "https://api.openai.com/v1/responses"

    def __init__(self, *, prices: dict, api_key: str | None = None, url: str = URL, effort: str = "medium", **kw):
        key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not set")
        super().__init__(**kw)
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.url = url
        self.prices = prices
        self.effort = effort

    def __repr__(self) -> str:
        return f"OpenAIResponsesProvider(url={self.url!r})"

    @staticmethod
    def native_model(model: str) -> str:
        return _split_model(model)[1]

    @staticmethod
    def _replay(item: dict) -> dict | None:
        t = item.get("type")
        if t == "reasoning":
            return {k: item[k] for k in ("type", "id", "summary", "encrypted_content") if k in item}
        if t == "message":
            parts = [{"type": "output_text", "text": c.get("text", "")} for c in item.get("content") or []
                     if c.get("type") == "output_text"]
            return {"type": "message", "role": "assistant", "content": parts} if parts else None
        if t == "function_call":
            return {"type": "function_call", "call_id": item["call_id"], "name": item["name"],
                    "arguments": item.get("arguments", "")}
        return None

    @classmethod
    def wire(cls, messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role == "user":
                out.append({"role": "user", "content": _plain(m.get("content"))})
            elif role == "tool":
                out.append({"type": "function_call_output", "call_id": m.get("tool_call_id"),
                            "output": _plain(m.get("content"))})
            elif role == "assistant":
                nat = m.get("_native") or {}
                if nat.get("provider") == "openai":
                    out += [r for r in (cls._replay(i) for i in nat["output"]) if r]
                else:
                    text = _plain(m.get("content"))
                    if text:
                        out.append({"type": "message", "role": "assistant",
                                    "content": [{"type": "output_text", "text": text}]})
                    out += [{"type": "function_call", "call_id": c.get("id"),
                             "name": (c.get("function") or {}).get("name"),
                             "arguments": (c.get("function") or {}).get("arguments") or "{}"}
                            for c in m.get("tool_calls") or []]
        return out

    def build_body(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None) -> dict:
        body: dict[str, Any] = {"model": self.native_model(model), "input": self.wire(messages), "store": False,
                                "include": ["reasoning.encrypted_content"]}
        system = _system_text(messages)
        if system:
            body["instructions"] = system
        if tools:
            body["tools"] = [{"type": "function", "name": t["function"]["name"],
                              "description": t["function"].get("description", ""),
                              "parameters": t["function"]["parameters"]} for t in tools]
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if max_tokens is not None:
            body["max_output_tokens"] = max_tokens
        if reasoning is not None and reasoning.get("enabled") is False:
            body["reasoning"] = {"effort": "none"}
        elif reasoning:
            body["reasoning"] = {"effort": reasoning.get("effort") or self.effort}
        return body

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None,
                 seed=None) -> Completion:
        body = self.build_body(model, messages, tools, tool_choice, max_tokens, reasoning)

        def parse(data, status):
            if data.get("error"):
                raise ProviderError("provider error", status, data["error"])
            if data.get("status") == "failed":
                raise _Retry(ProviderError("response failed", status, data.get("error")))
            items = data.get("output") or []
            text, calls, summaries, has_reasoning = [], [], [], False
            for it in items:
                t = it.get("type")
                if t == "message":
                    text += [c.get("text", "") for c in it.get("content") or [] if c.get("type") == "output_text"]
                elif t == "function_call":
                    calls.append({"id": it["call_id"], "type": "function",
                                  "function": {"name": it["name"], "arguments": it.get("arguments", "")}})
                elif t == "reasoning":
                    has_reasoning = True
                    summaries += [s.get("text", "") for s in it.get("summary") or []]
            msg: dict[str, Any] = {"role": "assistant", "content": "".join(text)}
            if calls:
                msg["tool_calls"] = calls
            if has_reasoning:
                msg["reasoning"] = "\n".join(summaries) or "[encrypted]"
            msg["_native"] = {"provider": "openai", "output": items}
            u = data.get("usage") or {}
            inp, out = int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
            cached = int((u.get("input_tokens_details") or {}).get("cached_tokens") or 0)
            rt = (u.get("output_tokens_details") or {}).get("reasoning_tokens")
            native = body["model"]
            usage = {"prompt_tokens": inp, "completion_tokens": out, "cached_tokens": cached,
                     "cost": round(price_cost(self.prices, native, uncached=inp - cached, output=out,
                                              cache_read=cached), 10)}
            if rt is not None:
                usage["reasoning_tokens"] = int(rt)
            inc = (data.get("incomplete_details") or {}).get("reason")
            finish = "length" if inc == "max_output_tokens" else "tool_calls" if calls else "stop"
            raw = {"choices": [{"finish_reason": finish}], "native": data}
            return Completion(message=msg, usage=usage, raw=raw, model=f"openai/{data.get('model') or native}")

        return self._post(self.url, self._headers, body, parse)


class RoutingProvider:
    """Picks a provider by model prefix. Providers are built on first use, so a
    missing key matters only for a species that is actually run."""

    KINDS = {"openrouter": OpenRouterProvider, "anthropic": AnthropicProvider, "openai": OpenAIResponsesProvider,
             "local": LocalProvider}

    def __init__(self, routes: dict[str, str], prices: dict, local_url: str | None = None, **kw):
        for k in routes.values():
            if k not in self.KINDS:
                raise ProviderError(f"unknown provider {k}")
        self.routes = routes
        self.prices = prices
        self.local_url = local_url
        self.kw = kw
        self._made: dict[str, Any] = {}
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"RoutingProvider({self.routes!r})"

    def provider_for(self, model: str):
        kind = self.routes.get(_split_model(model)[0], "openrouter")
        with self._lock:
            if kind not in self._made:
                cls = self.KINDS[kind]
                if cls is OpenRouterProvider:
                    self._made[kind] = cls(**self.kw)
                elif cls is LocalProvider:
                    self._made[kind] = cls(url=self.local_url, **self.kw)
                else:
                    self._made[kind] = cls(prices=self.prices, **self.kw)
            return self._made[kind]

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None,
                 seed=None) -> Completion:
        return self.provider_for(model).complete(model, messages, tools=tools, tool_choice=tool_choice,
                                                 max_tokens=max_tokens, reasoning=reasoning, seed=seed)


def make_provider(cfg) -> RoutingProvider:
    """The provider for a run, from `[providers]` and `[prices]` in run.toml."""
    routes = dict(cfg.section("providers"))
    return RoutingProvider(routes, dict(cfg.section("prices")), local_url=cfg.section("local").get("url"))


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text[:2000]
