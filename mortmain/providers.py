"""Provider: OpenRouter chat completions behind one interface.

Assistant messages are returned (and must be stored and replayed) verbatim,
including `reasoning` / `reasoning_details`. The API key comes from the
environment and is never logged, stored or put in an exception message.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
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
    the provider returned them, reasoning fields included."""
    return [dict(m) for m in messages]


class OpenRouterProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        url: str = OPENROUTER_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 600.0,
        max_retries: int = 6,
        backoff_base: float = 2.0,
        backoff_cap: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
        extra_body: dict | None = None,
    ):
        key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.url = url
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self.extra_body = extra_body or {}
        self._client = httpx.Client(transport=transport, timeout=timeout)

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

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None) -> Completion:
        body = self.build_body(model, messages, tools, tool_choice, max_tokens, reasoning)
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            resp = None
            try:
                resp = self._client.post(self.url, headers=self._headers, content=json.dumps(body))
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
                        err = data.get("error") if isinstance(data, dict) else None
                        if err:
                            code = err.get("code") if isinstance(err, dict) else None
                            if isinstance(code, int) and code in RETRY_STATUS:
                                last = ProviderError(f"provider error {code}", code, err)
                            else:
                                raise ProviderError(f"provider error {code}", code, err)
                        else:
                            choices = data.get("choices") or []
                            if not choices or "message" not in choices[0]:
                                # empty choices happen on upstream hiccups; retry
                                last = ProviderError("no choices", resp.status_code, data)
                            else:
                                msg = dict(choices[0]["message"])
                                msg.setdefault("role", "assistant")
                                return Completion(
                                    message=msg,
                                    usage=normalize_usage(data.get("usage")),
                                    raw=data,
                                    model=data.get("model", model),
                                )
            if attempt < self.max_retries:
                self._sleep(self._delay(attempt, resp))
        assert last is not None
        raise last


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text[:2000]
