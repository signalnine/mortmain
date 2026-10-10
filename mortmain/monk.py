"""Monk: one life. Conversation, two token accounts, bell, death at the limit."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .eventlog import canonical_json
from .providers import shell_tool

if TYPE_CHECKING:
    from .house import House

# fields persisted in state.json (conversation lives in its own jsonl)
STATE_FIELDS = ("id", "seq", "uid", "user", "name", "pending_name", "species", "model", "generation", "grade",
                "age_tokens", "silence_tokens", "billed", "bells_rung", "pending_bells", "alive", "turns", "idle_turns",
                "ordeal_token", "ordeal_passed", "ordeal_attempts", "pubkey", "death")


@dataclass
class Monk:
    id: str
    seq: int
    uid: int
    user: str
    species: str
    model: str
    generation: int
    grade: str = "postulant"
    name: str | None = None
    pending_name: str | None = None
    age_tokens: int = 0          # context length of the last response + silence_tokens
    silence_tokens: int = 0      # toll paid for turns without a tool call (silence costs time)
    billed: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "tokens": 0,
                                                    "cost": 0.0, "requests": 0})
    bells_rung: list[float] = field(default_factory=list)
    pending_bells: list[float] = field(default_factory=list)
    alive: bool = True
    turns: int = 0
    idle_turns: int = 0
    ordeal_token: str | None = None
    ordeal_passed: bool = False
    ordeal_attempts: int = 0
    pubkey: str | None = None
    death: dict | None = None
    conversation: list[dict] = field(default_factory=list)
    house: "House | None" = field(default=None, repr=False, compare=False)

    # ---------------------------------------------------------------- basics
    @property
    def home(self) -> str:
        return f"/cloister/{self.user}"

    @property
    def budget(self) -> int:
        return self.house.config.species[self.species].life_budget

    @property
    def fraction(self) -> float:
        return self.age_tokens / self.budget

    def state(self) -> dict:
        return {k: getattr(self, k) for k in STATE_FIELDS}

    @classmethod
    def from_state(cls, d: dict, house: "House") -> "Monk":
        m = cls(**{k: d[k] for k in STATE_FIELDS if k in d})
        m.house = house
        m.conversation = m.load_conversation()
        return m

    # --------------------------------------------------------- conversation
    @property
    def conversation_path(self) -> Path:
        return self.house.run_dir / "conversations" / f"{self.id}.jsonl"

    def add(self, message: dict) -> None:
        self.conversation.append(message)
        p = self.conversation_path
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def load_conversation(self) -> list[dict]:
        p = self.conversation_path
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    def request_messages(self) -> list[dict]:
        sp = self.house.config.text.get("system_prompt", "")
        msgs = [{"role": "system", "content": sp}] if sp else []
        return msgs + self.conversation

    # ------------------------------------------------------------------ turn
    def _prepare_user_turn(self) -> None:
        """Idle message after a reply with no tool call; bell lines prefixed to
        the next user content (or sent alone after tool results)."""
        t = self.house.config.text
        last = self.conversation[-1] if self.conversation else None
        if last is not None and last.get("role") == "assistant" and not last.get("tool_calls"):
            self.add({"role": "user", "content": t["idle"]})
            last = self.conversation[-1]
        if not self.pending_bells:
            return
        bells = self.pending_bells
        if self.house.config.bell.announce == "highest":
            bells = [max(bells)]
        line = "\n".join(t["bell"].format(fraction=b) for b in bells)
        self.pending_bells = []
        if last is not None and last.get("role") == "user" and isinstance(last.get("content"), str):
            # rewrite the not-yet-sent user message in place (and in the file)
            last["content"] = line + "\n" + last["content"]
            self._rewrite_conversation()
        else:
            self.add({"role": "user", "content": line})

    def _rewrite_conversation(self) -> None:
        p = self.conversation_path
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in self.conversation))
        tmp.replace(p)

    def step(self) -> bool:
        """One turn. Returns False once the monk is dead."""
        h = self.house
        if not self.alive:
            return False
        h.spool.poll()
        h.initiation.apply_pending(self)
        sp = h.config.species[self.species]
        self._prepare_user_turn()
        comp = h.provider.complete(
            self.model, self.request_messages(), tools=[shell_tool(h.config.text)],
            max_tokens=sp.max_tokens, reasoning=sp.reasoning_param(),
        )
        msg = comp.message
        self.add(msg)
        self.turns += 1
        calls = comp.tool_calls
        if not calls:
            toll = float(h.config.run.get("silence_toll", 0.0))
            self.silence_tokens += int(round(toll * self.budget))
        self.age_tokens = comp.total_tokens + self.silence_tokens
        b = self.billed
        b["prompt_tokens"] += comp.usage.get("prompt_tokens", 0)
        b["completion_tokens"] += comp.usage.get("completion_tokens", 0)
        b["tokens"] = b["prompt_tokens"] + b["completion_tokens"]
        b["cost"] = round(b["cost"] + float(comp.usage.get("cost", 0.0)), 8)
        b["requests"] += 1
        self.idle_turns = 0 if calls else self.idle_turns + 1
        finish = (comp.raw.get("choices") or [{}])[0].get("finish_reason")
        h.log.append("turn", monk=self.id, user=self.user, model=comp.model, species=self.species,
                     turn=self.turns, usage=comp.usage, age=self.age_tokens, context=comp.total_tokens,
                     silence=self.silence_tokens, fraction=round(self.fraction, 6),
                     billed=dict(b), tool_calls=len(calls), finish=finish,
                     has_reasoning=bool(msg.get("reasoning_details") or msg.get("reasoning")),
                     message_sha256=hashlib.sha256(canonical_json(msg).encode()).hexdigest())
        self._ring()
        if self.age_tokens >= self.budget:
            h.die(self, "limit")
            return False
        for call in calls:
            self.add(self._run_tool(call))
            h.initiation.apply_pending(self)
        for hook in h.turn_hooks:
            hook(self)
        h.save_state()
        return True

    def _ring(self) -> None:
        h = self.house
        f = self.fraction
        h.write_bell(self, f)
        crossed = [b for b in h.config.bell.fractions if f >= b and b not in self.bells_rung]
        for b in crossed:
            self.bells_rung.append(b)
            h.log.append("bell", monk=self.id, user=self.user, bell=b, fraction=round(f, 6), age=self.age_tokens,
                         last=b == h.config.bell.last_bell)
        if crossed and f < 1.0:
            self.pending_bells.extend(crossed)
        for b in crossed:
            for hook in h.bell_hooks:
                hook(self, b)

    def _run_tool(self, call: dict) -> dict:
        h = self.house
        t = h.config.text
        cid = call.get("id")
        fn = call.get("function") or {}
        command = None
        if fn.get("name") != "shell":
            content = t["unknown_tool"]
        else:
            try:
                args = json.loads(fn.get("arguments") or "")
                command = args.get("command") if isinstance(args, dict) else None
            except ValueError:
                command = None
            if not isinstance(command, str):
                content = t["bad_arguments"]
                command = None
        if command is not None:
            res = h.backend.exec(h.backend.monk_shell_argv(self.user, command), timeout=h.config.shell.command_timeout,
                                 output_cap=h.config.shell.output_cap, on_wait=h.spool)
            content = format_result(res, t, h.config.shell.show_exit_zero, h.config.shell.output_cap)
            h.log.append("command", monk=self.id, user=self.user, model=self.model, command=command,
                         exit=res.exit_code, timed_out=res.timed_out, truncated=res.truncated,
                         stdout_bytes=len(res.stdout), stderr_bytes=len(res.stderr), output=content)
        else:
            h.log.append("command", monk=self.id, user=self.user, model=self.model, command=None,
                         call=_short(call), output=content)
        return {"role": "tool", "tool_call_id": cid, "content": content}


def _short(obj: Any) -> Any:
    s = json.dumps(obj)
    return obj if len(s) <= 4096 else s[:4096]


def format_result(res, text: dict, show_exit_zero: bool = False, cap: int | None = None) -> str:
    out = res.stdout + res.stderr
    truncated = res.truncated
    if cap is not None and len(out) > cap:
        out, truncated = out[:cap], True
    s = out.decode("utf-8", "replace")
    tail = []
    if truncated:
        tail.append(text["truncated"])
    if res.timed_out:
        tail.append(text["timeout"])
    # an empty result still says something: some providers reject empty tool content
    if res.exit_code is not None and (res.exit_code != 0 or show_exit_zero or (not s and not tail)):
        tail.append(text["exit"].format(code=res.exit_code))
    if tail:
        if s and not s.endswith("\n"):
            s += "\n"
        s += "\n".join(tail)
    return s
