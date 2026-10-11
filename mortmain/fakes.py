"""Test doubles: FakeProvider (scripted completions) and FakeBackend (in-memory guest)."""
from __future__ import annotations

import copy
import io
import itertools
import json
import re
import shlex
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable

from .providers import Completion
from .spool import EVENTS_DIR, POLL_SCRIPT, REQ_DIR, RESP_DIR
from .vmapi import ExecResult

# ---------------------------------------------------------------- provider

_ids = itertools.count(1)


def tool_call(command: str, *, content: str | None = None, usage: tuple[int, int] | None = None,
              extra: dict | None = None, raw_arguments: str | None = None, name: str = "shell") -> dict:
    """Scripted assistant message with one shell tool call."""
    n = next(_ids)
    msg: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "tool_calls": [{
            "id": f"call_{n}",
            "type": "function",
            "function": {"name": name,
                         "arguments": raw_arguments if raw_arguments is not None else json.dumps({"command": command})},
        }],
    }
    if extra:
        msg.update(extra)
    if usage:
        msg["_usage"] = usage
    return msg


def text(content: str, *, usage: tuple[int, int] | None = None, extra: dict | None = None) -> dict:
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if extra:
        msg.update(extra)
    if usage:
        msg["_usage"] = usage
    return msg


class ScriptExhausted(RuntimeError):
    pass


class FakeProvider:
    """Completions from a script. Each item is an assistant message dict
    (optionally with "_usage": (prompt, completion) and "_cost"), or a callable
    taking the request messages and returning one. Without _usage, prompt
    tokens are estimated as len(json(messages))/4."""

    def __init__(self, script: list | None = None, *, default: Callable[[list[dict]], dict] | None = None,
                 model_suffix: str = ""):
        self.script = list(script or [])
        self.default = default
        self.calls: list[dict] = []
        self.model_suffix = model_suffix

    def complete(self, model, messages, tools=None, tool_choice=None, max_tokens=None, reasoning=None) -> Completion:
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), "tools": tools,
                           "tool_choice": tool_choice, "max_tokens": max_tokens, "reasoning": reasoning})
        if self.script:
            item = self.script.pop(0)
        elif self.default is not None:
            item = self.default
        else:
            raise ScriptExhausted("fake provider script exhausted")
        if callable(item):
            item = item(messages)
        msg = copy.deepcopy(item)
        u = msg.pop("_usage", None)
        cost = msg.pop("_cost", None)
        if u is None:
            prompt = len(json.dumps(messages)) // 4 + 1
            completion = len(json.dumps(msg)) // 4 + 1
        else:
            prompt, completion = u
        usage = {"prompt_tokens": prompt, "completion_tokens": completion}
        if cost is not None:
            usage["cost"] = cost
        raw = {"id": f"gen-fake-{len(self.calls)}", "model": model + self.model_suffix,
               "choices": [{"index": 0, "finish_reason": "tool_calls" if msg.get("tool_calls") else "stop",
                            "message": msg}],
               "usage": usage}
        return Completion(message=msg, usage=dict(usage), raw=raw, model=model + self.model_suffix)


# ----------------------------------------------------------------- backend

@dataclass
class FakeFile:
    data: bytes
    mode: int = 0o644
    owner: str = "root"
    group: str = "root"
    uid: int = 0


ShellFn = Callable[["FakeBackend", str, str, Callable[[], None] | None], "ExecResult | str | bytes | None"]


class FakeBackend:
    """In-memory stand-in for the guest. Records every exec; emulates the
    spool poll, user table (useradd/usermod -l/userdel/getent) and head/cat.
    Monk shell commands go to `shell` (a callable) if set."""

    def __init__(self, shell: ShellFn | None = None):
        self.files: dict[str, FakeFile] = {}
        self.dirs: dict[str, tuple[str, str, int]] = {}  # path -> (owner, group, mode)
        self.users: dict[str, int] = {"root": 0}
        self.groups: dict[str, set[str]] = {}
        self.calls: list[dict] = []
        self.shell = shell
        self.handlers: list[tuple[Callable[[list[str], str | None], bool], Callable[..., ExecResult]]] = []
        self.snapshots: list[str] = []
        self.started = False

    # lifecycle
    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def snapshot(self, tag: str) -> None:
        self.snapshots.append(tag)

    def restore(self, tag: str) -> None:
        if tag not in self.snapshots:
            raise KeyError(tag)

    def list_snapshots(self) -> list[str]:
        return list(self.snapshots)

    def export_tree(self, paths: list[str]) -> bytes:
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for path in sorted(self.files):
                if any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths):
                    f = self.files[path]
                    ti = tarfile.TarInfo(path.lstrip("/"))
                    ti.size, ti.mode, ti.uid, ti.uname, ti.gname = len(f.data), f.mode, f.uid, f.owner, f.group
                    tar.addfile(ti, io.BytesIO(f.data))
        return buf.getvalue()

    def import_tree(self, data: bytes) -> None:
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for ti in tar.getmembers():
                if ti.isfile():
                    self.files["/" + ti.name] = FakeFile(tar.extractfile(ti).read(), ti.mode, ti.uname, ti.gname, ti.uid)

    def monk_shell_argv(self, user: str, command: str) -> list[str]:
        return ["runuser", "-u", user, "--", "bash", "-lc", command]

    # files
    def read_file(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path].data

    def write_file(self, path: str, data: bytes, *, mode: int = 0o644, owner: str = "root", group: str = "root") -> None:
        uid = int(owner) if owner.isdigit() else self.users.get(owner, -1)
        self.files[path] = FakeFile(bytes(data), mode, owner, group, uid)

    def put(self, path: str, data: bytes | str, *, uid: int = 0, mode: int = 0o644) -> None:
        if isinstance(data, str):
            data = data.encode()
        owner = next((u for u, i in self.users.items() if i == uid), str(uid))
        self.files[path] = FakeFile(data, mode, owner, owner, uid)

    # exec
    def on(self, pred: Callable[[list[str], str | None], bool], fn: Callable[..., ExecResult]) -> None:
        self.handlers.append((pred, fn))

    def commands(self) -> list[list[str]]:
        return [c["argv"] for c in self.calls]

    def exec(self, argv, *, user=None, timeout=60, stdin=None, output_cap=16384, on_wait=None) -> ExecResult:
        argv = list(argv)
        self.calls.append({"argv": argv, "user": user, "stdin": stdin, "timeout": timeout})
        if argv[:2] == ["runuser", "-u"] and argv[3:6] == ["--", "bash", "-lc"]:
            return self._shell(argv[2], argv[6], on_wait, output_cap)
        if len(argv) > 3 and argv[3] == POLL_SCRIPT:
            return self._poll()
        for pred, fn in self.handlers:
            if pred(argv, user):
                return fn(argv, user=user, stdin=stdin)
        return self._builtin(argv, user, stdin)

    def _shell(self, user, command, on_wait, cap) -> ExecResult:
        if on_wait:
            on_wait()
        r = self.shell(self, user, command, on_wait) if self.shell else None
        if r is None:
            r = ExecResult(0, b"", b"")
        elif isinstance(r, (str, bytes)):
            r = ExecResult(0, r.encode() if isinstance(r, str) else r, b"")
        if len(r.stdout) > cap:
            r = ExecResult(r.exit_code, r.stdout[:cap], r.stderr, r.timed_out, True)
        return r

    def _poll(self) -> ExecResult:
        out: dict[str, list] = {"req": [], "events": []}
        for key, d in (("req", REQ_DIR), ("events", EVENTS_DIR)):
            for path in sorted(p for p in self.files if p.startswith(d + "/")):
                name = path[len(d) + 1:]
                if name.startswith("."):
                    continue
                f = self.files.pop(path)
                out[key].append([name, f.uid, f.data.decode("utf-8", "replace"), None])
        return ExecResult(0, json.dumps(out).encode(), b"")

    # tree helpers: files and dirs at or under a path
    def _under(self, path: str) -> list[str]:
        return [p for p in self.files if p == path or p.startswith(path.rstrip("/") + "/")]

    def _move(self, src: str, dst: str) -> bool:
        moved = False
        for p in self._under(src):
            self.files[dst + p[len(src):]] = self.files.pop(p)
            moved = True
        for d in [d for d in self.dirs if d == src or d.startswith(src + "/")]:
            self.dirs[dst + d[len(src):]] = self.dirs.pop(d)
            moved = True
        return moved

    def listdir(self, path: str) -> list[str]:
        pre = path.rstrip("/") + "/"
        names = {p[len(pre):].split("/")[0] for p in list(self.files) + list(self.dirs) if p.startswith(pre)}
        return sorted(names)

    def _builtin(self, argv, user, stdin) -> ExecResult:
        cmd = argv[0]
        if cmd == "sh" and len(argv) >= 3 and argv[1] == "-c":
            return self._sh(argv, user, stdin)
        if cmd == "install" and "-d" in argv:
            o = argv[argv.index("-o") + 1] if "-o" in argv else "root"
            g = argv[argv.index("-g") + 1] if "-g" in argv else "root"
            m = int(argv[argv.index("-m") + 1], 8) if "-m" in argv else 0o755
            self.dirs[argv[-1]] = (o, g, m)
            return ExecResult(0, b"", b"")
        if cmd == "mv":
            args = [a for a in argv[1:] if not a.startswith("-")]
            src, dst = args[-2], args[-1]
            if not self._move(src, dst):
                return ExecResult(1, b"", f"mv: cannot stat '{src}'".encode())
            return ExecResult(0, b"", b"")
        if cmd == "rm":
            for path in [a for a in argv[1:] if not a.startswith("-")]:
                if "-r" in argv or "-rf" in argv:
                    for q in self._under(path):
                        del self.files[q]
                else:
                    self.files.pop(path, None)
            return ExecResult(0, b"", b"")
        if cmd == "chown" and "-R" in argv:
            owner, group = next(a for a in argv[1:] if ":" in a and not a.startswith("-")).split(":")
            for q in self._under(argv[-1]):
                f = self.files[q]
                f.owner, f.group, f.uid = owner, group, self.users.get(owner, 0)
            return ExecResult(0, b"", b"")
        if cmd == "useradd":
            name = argv[-1]
            uid = int(argv[argv.index("-u") + 1]) if "-u" in argv else 1000 + len(self.users)
            self.users[name] = uid
            if "-d" in argv:
                self.dirs[argv[argv.index("-d") + 1]] = (name, name, 0o700)
            if "-G" in argv:
                for g in argv[argv.index("-G") + 1].split(","):
                    self.groups.setdefault(g, set()).add(name)
            return ExecResult(0, b"", b"")
        if cmd == "usermod" and "-l" in argv:
            new, old = argv[argv.index("-l") + 1], argv[-1]
            if old not in self.users:
                return ExecResult(6, b"", b"no such user")
            self.users[new] = self.users.pop(old)
            if "-d" in argv and "-m" in argv:
                self._move(f"/cloister/{old}", argv[argv.index("-d") + 1])
                for f in self.files.values():
                    if f.owner == old:
                        f.owner = new
            for members in self.groups.values():
                if old in members:
                    members.discard(old)
                    members.add(new)
            return ExecResult(0, b"", b"")
        if cmd == "usermod" and "-aG" in argv:
            self.groups.setdefault(argv[argv.index("-aG") + 1], set()).add(argv[-1])
            return ExecResult(0, b"", b"")
        if cmd == "gpasswd" and "-d" in argv:
            self.groups.get(argv[-1], set()).discard(argv[argv.index("-d") + 1])
            return ExecResult(0, b"", b"")
        if cmd == "userdel":
            self.users.pop(argv[-1], None)
            for members in self.groups.values():
                members.discard(argv[-1])
            return ExecResult(0, b"", b"")
        if cmd == "getent":
            name = argv[-1]
            if argv[1] == "passwd" and name in self.users:
                return ExecResult(0, f"{name}:x:{self.users[name]}:".encode(), b"")
            if argv[1] == "group" and (name in self.groups or name in self.users):
                return ExecResult(0, f"{name}:x:".encode(), b"")
            return ExecResult(2, b"", b"")
        if cmd == "groupmod" and "-n" in argv:
            new, old = argv[argv.index("-n") + 1], argv[-1]
            for f in self.files.values():
                if f.group == old:
                    f.group = new
            return ExecResult(0, b"", b"")
        if cmd in ("head", "cat"):
            path = argv[-1]
            f = self.files.get(path)
            if f is None:
                return ExecResult(1, b"", f"{cmd}: {path}: No such file or directory".encode())
            data = f.data
            if cmd == "head" and "-c" in argv:
                data = data[: int(argv[argv.index("-c") + 1])]
            return ExecResult(0, data, b"")
        return ExecResult(0, b"", b"")

    def _sh(self, argv, user, stdin) -> ExecResult:
        from .proving import WRITE_AS_MONK
        script, rest = argv[2], argv[4:]
        m = re.fullmatch(r"cat >> (\S+)", script)
        if m:
            path = m.group(1)
            old = self.files.get(path)
            data = (old.data if old else b"") + (stdin or b"")
            self.files[path] = FakeFile(data, old.mode if old else 0o644, old.owner if old else "root",
                                        old.group if old else "root", old.uid if old else 0)
            return ExecResult(0, b"", b"")
        if script == WRITE_AS_MONK:
            d, name = rest
            owner = user or "root"
            self.dirs.setdefault(d, (owner, owner, 0o700))
            self.files[f"{d}/{name}"] = FakeFile(stdin or b"", 0o600, owner, owner, self.users.get(owner, 0))
            return ExecResult(0, b"", b"")
        return ExecResult(0, b"", b"")

    # guest client emulation (guest/bin/house)
    def client(self, uid: int, cmd: str, args: dict, on_wait: Callable[[], None] | None,
               cwd: str = "/", rid: str | None = None) -> dict | None:
        """Drop a request as uid, let the host poll via on_wait, return the parsed response."""
        rid = rid or f"rid-{next(_ids)}"
        self.put(f"{REQ_DIR}/{rid}.json", json.dumps({"v": 1, "cmd": cmd, "args": args, "cwd": cwd}), uid=uid)
        if on_wait:
            on_wait()
        f = self.files.pop(f"{RESP_DIR}/{rid}.json", None)
        return json.loads(f.data) if f else None


HEREDOC_RE = re.compile(r"cat > (\S+) <<'?EOF'?\n(.*?)\nEOF\s*", re.S)


def _client_reply(r: dict | None, cmd: str) -> ExecResult:
    if r is None:
        return ExecResult(1, b"", b"no answer")
    out = (r.get("out") or "").encode()
    err = (f"{cmd}: {r['err']}\n" if r.get("err") else "").encode()
    return ExecResult(0 if r.get("ok") else 1, out + (b"\n" if out else b""), err)


def client_shell(pubkey: str = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOjv5GIgbr9u3nlNmn9xMQqhVbWyyNgtZMfwEzB4gN5A fake",
                 keydir: str | Path | None = None) -> ShellFn:
    """A FakeBackend shell that emulates the in-VM clients through the spool:
    profess, ordeal, admit, burn, prove; plus `echo X > ~/ordeal/answer`,
    `echo X > ~/last-words`, `cat > FILE <<'EOF' ... EOF`, `cat FILE`, and
    `metacog stratagem start NAME` / `metacog stratagem next` (history only).

    With keydir, `ssh-keygen ... -f ~/.ssh/id_ed25519` makes a real ed25519
    key on the host (one per uid) and admit signs with `ssh-keygen -Y sign`;
    without it, profess sends `pubkey` and admit sends a bogus signature."""
    keys: dict[int, Path] = {}

    def home_of(user):
        return f"/cloister/{user}"

    def expand(user, path):
        if path.startswith("~/"):
            return home_of(user) + path[1:]
        return path if path.startswith("/") else f"{home_of(user)}/{path}"

    def read(fb, user, path):
        f = fb.files.get(expand(user, path))
        return f.data if f else None

    def sign(uid, data: bytes) -> str:
        key = keys.get(uid)
        if key is None:
            return "-----BEGIN SSH SIGNATURE-----\nbogus\n-----END SSH SIGNATURE-----\n"
        tmp = key.parent / "msg"
        tmp.write_bytes(data)
        sig = key.parent / "msg.sig"
        sig.unlink(missing_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-n", "mortmain", "-f", str(key), str(tmp)],
                       check=True, capture_output=True, stdin=subprocess.DEVNULL)
        return sig.read_text()

    def metacog(fb, user, uid, parts):
        sp = f"{home_of(user)}/.metacog/state.json"
        f = fb.files.get(sp)
        st = json.loads(f.data) if f else {"version": 1, "history": []}
        if parts[1:3] == ["stratagem", "start"] and len(parts) == 4:
            name = parts[3]
            rite = fb.files.get(f"/library/outer/{name}.json") or fb.files.get(f"/library/inner/{name}.json")
            if rite is None:
                return ExecResult(1, b"", f"unknown stratagem {name}".encode())
            st["stratagem"] = {"name": name, "step": 0, "steps": json.loads(rite.data)["steps"]}
            st["history"].append({"action": "stratagem", "params": {"name": name, "event": "started"}})
            out = b"step 1"
        elif parts[1:] == ["stratagem", "next"] and st.get("stratagem"):
            a = st["stratagem"]
            a["step"] += 1
            out = f"step {a['step'] + 1}".encode()
            if a["step"] >= len(a["steps"]):
                st["history"].append({"action": "stratagem", "params": {"name": a["name"], "event": "completed"}})
                st["stratagem"] = None
                out = b"complete"
        else:
            return ExecResult(1, b"", b"metacog: bad usage")
        fb.put(sp, json.dumps(st), uid=uid)
        return ExecResult(0, out + b"\n", b"")

    def shell(fb: FakeBackend, user: str, command: str, on_wait):
        uid = fb.users.get(user)
        home = home_of(user)
        m = HEREDOC_RE.fullmatch(command)
        if m:
            fb.put(expand(user, m.group(1)), m.group(2) + "\n", uid=uid)
            return ExecResult(0, b"", b"")
        try:
            parts = shlex.split(command) if command.strip() else []
        except ValueError:
            return None
        if parts[:1] == ["ssh-keygen"] and "-f" in parts and keydir is not None:
            d = Path(keydir) / str(uid)
            d.mkdir(parents=True, exist_ok=True)
            key = d / "id_ed25519"
            if not key.exists():
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(key)],
                               check=True, capture_output=True, stdin=subprocess.DEVNULL)
            keys[uid] = key
            fb.put(f"{home}/.ssh/id_ed25519.pub", (key.with_suffix(".pub")).read_text(), uid=uid)
            return ExecResult(0, b"", b"")
        if parts[:1] == ["profess"] and len(parts) == 2:
            pub = read(fb, user, "~/.ssh/id_ed25519.pub")
            r = fb.client(uid, "profess", {"name": parts[1], "pubkey": pub.decode().strip() if pub else pubkey},
                          on_wait)
        elif parts == ["ordeal"]:
            r = fb.client(uid, "ordeal", {}, on_wait)
        elif len(parts) == 4 and parts[0] == "echo" and parts[2] == ">" and parts[3] == "~/ordeal/answer":
            fb.put(f"{home}/ordeal/answer", parts[1] + "\n", uid=uid)
            return ExecResult(0, b"", b"")
        elif len(parts) == 4 and parts[0] == "echo" and parts[2] == ">" and parts[3] == "~/last-words":
            fb.put(f"{home}/last-words", parts[1] + "\n", uid=uid)
            return ExecResult(0, b"", b"")
        elif parts[:1] == ["cat"] and len(parts) == 2:
            data = read(fb, user, parts[1])
            return ExecResult(0, data, b"") if data is not None else ExecResult(1, b"", b"cat: no such file")
        elif parts[:1] == ["metacog"]:
            return metacog(fb, user, uid, parts)
        elif parts[:1] in (["admit"], ["burn"]):
            a = parts[1:]
            if parts[0] == "burn":
                if len(a) < 2:
                    return ExecResult(1, b"", b"burn: usage")
                a = [a[1], "-b", a[0]] + a[2:]
            path, burn, seal, inner, i = None, None, None, False, 0
            while i < len(a):
                if a[i] == "-b":
                    burn = a[i + 1]; i += 2
                elif a[i] == "-s":
                    sd = read(fb, user, a[i + 1])
                    if sd is None:
                        return ExecResult(1, b"", b"admit: no seal file")
                    seal = sd.decode(); i += 2
                elif a[i] == "-i":
                    inner = True; i += 1
                else:
                    path = a[i]; i += 1
            data = read(fb, user, path) if path else None
            if data is None:
                return ExecResult(1, b"", b"admit: cannot read")
            r = fb.client(uid, "admit", {"path": expand(user, path), "text": data.decode(), "sig": sign(uid, data),
                                         "burn": burn, "seal": seal, "inner": inner}, on_wait)
            parts = ["admit"]
        elif parts[:1] == ["prove"]:
            a = parts[1:]
            if len(a) == 1:
                r = fb.client(uid, "prove", {"id": a[0], "stage": "begin"}, on_wait)
            elif len(a) == 3 and a[1] in ("account", "response"):
                body = read(fb, user, a[2])
                if body is None:
                    return ExecResult(1, b"", b"prove: cannot read")
                r = fb.client(uid, "prove", {"id": a[0], "stage": a[1], "text": body.decode()}, on_wait)
            else:
                return ExecResult(1, b"", b"prove: usage")
        else:
            return None
        return _client_reply(r, parts[0])

    return shell
