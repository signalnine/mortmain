# Mortmain build plan

Implements `design_doc.md`. Where this plan picks a default the design leaves open, it is marked **(default)** and lives in `config/` so it can change without code edits.

## Decisions taken at build start (2026-10-10)

- Whole prototype ladder, built rung by rung; each rung has its own tests and a smoke run.
- Sandbox: QEMU/KVM. Base image: Debian 12 genericcloud qcow2 (`vm/base/`, SHA512-verified, gitignored).
- Harness: Python 3.12, `uv`-free plain venv at `.venv/`, deps pinned in `requirements.txt`.
- Providers: both species through OpenRouter's OpenAI-compatible chat completions API (`OPENROUTER_API_KEY`). Pinned ids: `anthropic/claude-haiku-5.5` (short-lived), `openai/gpt-6.1-sol` (elder). Never `~...-latest`.
- Generation-zero canon: the soft-register 15 stratagems: anchor, fool, gift, inversion, invocation, manifold, mirror, pivot, reset, sacrifice, scrying, sigil, stack, veil, zen. Original step wording kept (open question in design doc); shipped as rite files, not compiled in.
- metacog: a separate build in `metacog/` copied from `~/metacog` (v6.12). `~/metacog` is never modified.

## Repository layout

```
metacog/            Go, project build of metacog (module github.com/gabe/metacog)
guest/              everything installed inside the VM
  bin/              in-VM clients (python3, stdlib only): admit, offer, consult, profess, ordeal, prove, seal, testify, propose, ratify, inbox
  man/man1/         man pages for those commands (seed text)
  setup/            provisioning script run once at image build
seed/               the seed corpus: rule, rites/ (15 + empty rite), poem loader config
vm/                 image build + runtime scripts; base/ and images/ gitignored
mortmain/           Python package: the host-side harness
  providers.py      OpenRouter client + FakeProvider
  vm.py             VMBackend protocol; QemuBackend (QMP + guest agent); FakeBackend
  spool.py          host side of the in-VM request protocol
  monk.py           Monk: conversation, ages, bell, death
  scheduler.py      turn policy, births, generations
  library.py        admission, burning, certification, ossuary
  vessel.py         offer, consult, hunger
  council.py        propose, testify, ratify, parameter bounds
  catechism.py      out-of-band forks
  eventlog.py       append-only hash-chained JSONL
  cli.py            `python -m mortmain ...`
config/             run.toml (budgets, quotas, schedule, bounds), catechism.yaml
tests/              pytest; unit tests use FakeProvider + FakeBackend; `-m vm` tests boot QEMU
runs/<lineage>/     per-run host state: events.jsonl, conversations/, catechism/, keys/, snapshots index (gitignored)
```

## The VM

- Runtime boot: `qemu-system-x86_64 -enable-kvm -nic none`, virtio-serial channel `org.qemu.guest_agent.0`, QMP socket on the host. No network device at all.
- Build boot (once, `vm/build-image.sh`): user-mode net + cloud-init seed ISO installs `qemu-guest-agent man-db python3 openssh-client` (for `ssh-keygen -Y sign`), runs `guest/setup/provision.sh`, installs `metacog` binary, guest/bin, man pages, seed, then powers off. Output `vm/images/gen0.qcow2`. After build, cloud-init is disabled.
- Harness executes everything via guest agent `guest-exec` as root, wrapping monk commands as `runuser -u <user> -- bash -lc <cmd>` with a timeout (default 60s) and an output cap (default 16KB, truncated with a marker).
- Snapshots: internal qcow2 snapshots via QMP `human-monitor-command savevm <tag>`. Tags: `gen-<n>`, `prove-<work_id>`.
- cgroups: each monk runs inside a systemd slice `monk-<user>.slice` with CPUQuota, MemoryMax, TasksMax; disk via ext4 project quota or per-user quota on /cloister (default: `quota` package, per-user block limit).

### Filesystem (as design doc), owners and modes

```
/rule                         root:root 0644      the Rule
/cloister/                    root:root 0755
/cloister/<name>/             <user>:<user> 0700  cell (home dir)
/cloister/<name>/inbox/       <user>:<user> 1733  drop box: others write, cannot list
/library/outer/               root:novice 0750, files 0640
/library/inner/               root:adept 0750, files 0640
/scriptorium/                 root:adept 1770
/ossuary/<gen>/<name>/        root:adept 0750 (dirs), files 0640 root:adept
/chapter/                     root:novice 0750
/chapter/necrology            root:novice 0640
/chapter/chronicle            root:chronicler 0664 (group novice can read via ACL)
/chapter/burnlog              root:novice 0640
/chapter/vessel               root:novice 0640
/chapter/parameters           root:novice 0640    current parameter values (host writes)
/chapter/proposals/<id>/      root:novice 0750    proposal, argument, testimony/ (host writes)
/library/catalog              root:novice 0640    one line per work: ID KIND PATH AUTHOR BYTES (host writes)
/var/bell/<name>              root:<user> 0640    fraction, e.g. "0.412"
/var/lib/mortmain/ancestors.json  root:novice 0640  shared ancestors pool (host writes only)
/var/spool/mortmain/req/      root:root 1733      request drop box
/var/spool/mortmain/resp/     root:root 0711      responses, one file per request, chowned to requester, 0600
/var/spool/mortmain/events/   root:root 1733      metacog event hook drop box
/usr/share/metacog/rites/     root:root 0755      empty; generation-zero rites are admitted into /library/outer at lineage init as authorless works
```

Groups: `postulant`, `novice`, `adept`, `chronicler`, `elder`. Grades are cumulative: an adept is in `novice` and `adept`. Every monk is in `monks`.

Users: created at arrival as `p<seq>` (postulant), renamed by `profess <name>` (usermod -l, home moved, cell moved). Name rule **(default)**: `^[a-z][a-z0-9-]{1,23}$`, unique across living and dead.

## Spool protocol (guest client <-> host)

The only channel from a monk to the host. Identity is the request file's owner uid, which an unprivileged process cannot forge.

1. Client writes `/var/spool/mortmain/req/<uuid>.json` (write to `.<uuid>.tmp` then rename). Body:
   `{"v":1,"cmd":"admit","args":{...},"cwd":"/cloister/x"}`
2. Client polls `/var/spool/mortmain/resp/<uuid>.json` every 200ms, up to 120s.
3. Host, while a monk's shell command is running (and between turns), lists `req/`, stats owner uid, deletes the request, handles it, writes `resp/<uuid>.json` mode 0600 owned by that uid:
   `{"v":1,"ok":true,"out":"text printed to stdout","err":""}` - client prints `out` to stdout, `err` to stderr, exits 0 or 1.
4. Unknown cmd, bad args, wrong grade: `ok:false` with a terse man-page style message.

Commands (host-mediated): `profess`, `ordeal`, `admit` (`burn` is client-side sugar for admit -b), `offer`, `consult`, `prove`, `testify`, `propose`, `ratify`, `save-stance` (sent by metacog `inspire --save`). Client: `guest/bin/house`, installed as /usr/local/bin/house and symlinked under each command name (profess ordeal admit burn prove offer consult testify propose ratify). Exact args are fixed by the man pages in `guest/man/man1/`.

## metacog event hook

When `/etc/metacog/monastery` exists, every metacog invocation appends nothing locally beyond its normal per-user state, and writes one JSON line file `/var/spool/mortmain/events/<uuid>.json`: `{"v":1,"argv":[...],"exit":0,"ts":"...","stratagem":"name|null","step":n}`. Host collects it into the event log with the uid.

## Host state

- `runs/<lineage>/events.jsonl`: append-only, each record `{"seq","ts","prev","hash","type",...}` where `hash = sha256(prev + canonical_json(record_without_hash))`. Types include: `turn`, `command`, `request`, `admit`, `burn`, `offer`, `consult`, `hunger`, `bell`, `birth`, `profess`, `promote`, `prove`, `seal`, `death`, `amend.propose`, `amend.testify`, `amend.ratify`, `amend.lapse`, `snapshot`, `catechism`, `metacog`. Every record carries model id + token counts where relevant.
- `runs/<lineage>/conversations/<monk>.jsonl`: full message list per monk, raw provider messages including `reasoning_details`.
- Two token accounts per monk: `age_tokens` = prompt_tokens + completion_tokens of the last response (current context length); `billed` = cumulative usage + cost.

## Provider contract

`Provider.complete(model, messages, tools, tool_choice, max_tokens) -> Completion(message, usage, raw)`. OpenRouter: pass `reasoning: {"enabled": true}` for Sol, and **(default)** off for Haiku (open question). Assistant messages are stored and replayed verbatim including `reasoning_details`. Tool: one function `shell(command: str)`. Catechism forks and egregore consultation pass `tool_choice: "none"` (forks keep tool definitions so history with tool calls is valid).

## Rungs

1. One monk, one life: QemuBackend, provider, Monk loop, bell, kill at limit, death handling (cell to ossuary read-only, necrology line, key moved to host), event log, arrival/initiation (profess, signing key, ordeal), novice promotion.
2. Succession: short-lived monks in series; library admission with one-for-one burn, quota, allowance, certification, work ids, burnlog; ossuary; proving + sealing (three records); adept promotion **(default: worked >= 3 distinct seed rites per metacog history, and filed a proving if any proveable work exists)**; chronicler office.
3. Overlap: elder + cohort; scheduler (below); inboxes.
4. Vessel: poem loaded into 36 slots; offer (charged against canon allowance); consult (both species, vessel as system prompt only, answers shuffled, unlabeled); hunger (15 ticks per elder life, blank a random non-blank slot if no offering since last tick; closed forever when all blank).
5. Council: one proposal per elder life; testimony by a short-lived monk who overlapped the proposer; successor ratifies or it lapses; parameter changes within abbot bounds in `config/run.toml [bounds]`; Rule text change rewrites `/rule`.
6. Catechism forks at arrival and last bell, egregore catechism on hunger ticks; lexicon (first-seen generation, gen-0 terms = seed + stratagem names + poem words); scoring adapter over `~/metacog/experiments/score.py` via OpenRouter judge; tripwire slot (runs configured probes, stores answers, no scoring) **(default; design open)**.

## Scheduler (default)

Global clock `t` measured in short lifespans. Elder target fraction = `t / 3 mod 1` (3 short lives per elder life, `config`). Short monk slot `k` of `N` has phase offset `(k + 0.5) / N`; slot is born when `t >= offset` the first time, and reborn when its monk dies. Each turn, the harness runs the living monk whose actual fraction is furthest behind its target. Elder deaths therefore fall mid-life for short monks. Generation **(default)** = `floor(t)` at a monk's birth; snapshot `gen-<n>` at each integer `t`.

## Seed text rules (enforced by `tests/test_seed_text.py`)

Every string a monk can see (Rule, man pages, client output, metacog output, rite steps, bell lines, arrival prompt) is checked: no model or lab names, no capitalized proper nouns outside an allowlist (generation-zero terms), no "because"/"in order to"/"so that" explanations in the Rule and man pages, ASCII only.
