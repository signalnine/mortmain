"""Host side of the spool protocol (docs/plan.md "Spool protocol").

Identity is the owner uid of the request file. One root exec of POLL_SCRIPT in
the guest lists, reads and unlinks every pending request and metacog event,
printing JSON. The host dispatches each request by cmd and writes the response
0600, owned by the requester.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

SPOOL = "/var/spool/mortmain"
REQ_DIR = SPOOL + "/req"
RESP_DIR = SPOOL + "/resp"
EVENTS_DIR = SPOOL + "/events"
MAX_REQUEST_BYTES = 65536 + 16384  # client caps file payloads at 64KB
RID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")

# Runs in the guest as root: python3 -c POLL_SCRIPT REQ_DIR EVENTS_DIR MAXBYTES
# Never follows symlinks, reads only regular single-link files, unlinks
# everything it looks at except in-progress dotfiles.
POLL_SCRIPT = r"""
import json, os, stat, sys
def take(d, cap):
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if n.startswith('.'):
            continue
        p = os.path.join(d, n)
        uid, body, why = None, None, None
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as e:
            try:
                st = os.lstat(p); uid = st.st_uid
            except OSError:
                pass
            why = 'open'
        else:
            try:
                st = os.fstat(fd); uid = st.st_uid
                if not stat.S_ISREG(st.st_mode):
                    why = 'type'
                elif st.st_nlink != 1:
                    why = 'links'
                elif st.st_size > cap:
                    why = 'size'
                else:
                    body = os.read(fd, cap + 1).decode('utf-8', 'replace')
            finally:
                os.close(fd)
        try:
            os.unlink(p)
        except OSError:
            pass
        out.append([n, uid, body, why])
    return out
cap = int(sys.argv[3])
print(json.dumps({'req': take(sys.argv[1], cap), 'events': take(sys.argv[2], cap)}))
"""


def poll_argv() -> list[str]:
    return ["python3", "-I", "-c", POLL_SCRIPT, REQ_DIR, EVENTS_DIR, str(MAX_REQUEST_BYTES)]


@dataclass
class Reply:
    ok: bool
    out: str = ""
    err: str = ""

    def to_json(self) -> bytes:
        return (json.dumps({"v": 1, "ok": self.ok, "out": self.out, "err": self.err}) + "\n").encode()


class Registry(Protocol):
    def by_uid(self, uid: int) -> Any: ...


Handler = Callable[[Any, dict, str | None], Reply]


class SpoolService:
    def __init__(self, backend, registry: Registry, handlers: dict[str, Handler], log, text: dict[str, str],
                 *, min_interval: float = 0.5, clock: Callable[[], float] = time.monotonic):
        self.backend = backend
        self.registry = registry
        self.handlers = handlers
        self.log = log
        self.text = text
        self.min_interval = min_interval
        self._clock = clock
        self._last = float("-inf")
        self._busy = False

    def __call__(self) -> None:
        """on_wait hook: poll at most every min_interval seconds."""
        now = self._clock()
        if now - self._last >= self.min_interval:
            self.poll()

    def poll(self) -> int:
        if self._busy:  # handlers exec in the guest; never re-enter
            return 0
        self._busy = True
        try:
            self._last = self._clock()
            res = self.backend.exec(poll_argv(), timeout=30, output_cap=1 << 24)
            if res.exit_code != 0:
                self.log.append("spool.error", stage="poll", exit=res.exit_code,
                                stderr=res.stderr[-2000:].decode("utf-8", "replace"))
                return 0
            try:
                data = json.loads(res.stdout)
            except ValueError:
                self.log.append("spool.error", stage="poll", error="bad listing")
                return 0
            for entry in data.get("events", []):
                self._event(*entry)
            n = 0
            for entry in data.get("req", []):
                self._request(*entry)
                n += 1
            return n
        finally:
            self._busy = False

    # -- metacog event hook drop box
    def _event(self, name, uid, body, why) -> None:
        monk = self.registry.by_uid(uid) if uid is not None else None
        rec: dict[str, Any] = {"uid": uid, "file": name, "monk": getattr(monk, "id", None)}
        if body is None:
            rec["rejected"] = why
        else:
            try:
                rec["data"] = json.loads(body)
            except ValueError:
                rec["raw"] = body[:4096]
        self.log.append("metacog", **rec)

    # -- requests
    def _request(self, name, uid, body, why) -> None:
        monk = self.registry.by_uid(uid) if uid is not None else None
        rid = name[:-5] if name.endswith(".json") else None
        if monk is None:
            self.log.append("spool.unknown", uid=uid, file=name, rejected=why)
            return
        if rid is None or not RID_RE.match(rid):
            self.log.append("request", monk=monk.id, user=monk.user, file=name, error="bad name")
            return
        cmd, args, cwd = None, None, None
        if body is None:
            reply = Reply(False, err=self.text["bad_request"])
            err = f"rejected: {why}"
        else:
            err = None
            try:
                req = json.loads(body)
                if not isinstance(req, dict) or req.get("v") != 1 or not isinstance(req.get("cmd"), str) \
                        or not isinstance(req.get("args", {}), dict):
                    raise ValueError
                cmd, args, cwd = req["cmd"], req.get("args", {}), req.get("cwd")
            except ValueError:
                reply = Reply(False, err=self.text["bad_request"])
                err = "bad json"
            else:
                handler = self.handlers.get(cmd)
                if handler is None:
                    reply = Reply(False, err=self.text["unknown_command"])
                else:
                    try:
                        reply = handler(monk, args, cwd if isinstance(cwd, str) else None)
                    except Exception as e:  # handler bug: the monk sees a terse failure
                        reply = Reply(False, err=self.text["failed"])
                        err = f"handler: {type(e).__name__}: {e}"
        self.log.append("request", monk=monk.id, user=monk.user, uid=uid, rid=rid, cmd=cmd, args=args,
                        cwd=cwd, ok=reply.ok, out=reply.out, err=reply.err, error=err)
        # owner resolved after the handler, in case the user was renamed
        owner = self.registry.by_uid(uid)
        if owner is not None:
            self.backend.write_file(f"{RESP_DIR}/{rid}.json", reply.to_json(), mode=0o600,
                                    owner=owner.user, group="root")
