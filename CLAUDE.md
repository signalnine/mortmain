# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
.venv/bin/pytest -q                                   # unit tests (fakes; VM tests skipped)
.venv/bin/pytest -q -m vm                             # live tests: boot vm/images/gen0.qcow2 under KVM
.venv/bin/pytest -q tests/test_library.py -k burn     # single test
(cd metacog && go test ./cmd/metacog/ && go test ./cmd/metacog/ -tags integration)
(cd metacog && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o metacog-linux-amd64 ./cmd/metacog/)  # binary for the image
bash vm/build-image.sh [--force]                      # gen0 image; skips if inputs unchanged
.venv/bin/python -m mortmain run --lineage L --rung 1|2|3|full --image vm/images/gen0.qcow2 [--dry] [--fake-vm] [--budget N] [--max-cost USD]
.venv/bin/python -m mortmain log verify --lineage L   # check the event log hash chain
.venv/bin/python -m mortmain fork --from L --tag gen-3 --lineage L2   # new lineage from a snapshot export (no VM image needed)
.venv/bin/python -m mortmain.report surfaces|lexicon|score|baseline|coined ...
.venv/bin/python -m mortmain.trial run|report experiments/X.toml [--image ...] [--n 4]  # prompt trials: many rung-1 lives per config arm
```

Rebuild the static metacog binary, then the image, after changing `metacog/`, `guest/` or `seed/`. Real runs need `OPENROUTER_API_KEY` (scoring embeddings also need `OPENAI_API_KEY`). Host state goes to `runs/<lineage>/` (gitignored). `docs/plan.md` is the implementation spec: interfaces, filesystem modes, spool protocol, defaults chosen where the design is open.

## Layout

- `mortmain/house.py` holds the House; rung modules (`library`, `proving`, `grades`, `vessel`, `council`, `office`, `nudge`, `catechism`, `tripwire`) plug in via `install(house)` and the hook lists (`handlers`, `arrival_hooks`, `turn_hooks`, `bell_hooks`, `death_hooks`, `generation_hooks`, `start_hooks`), enabled by `[house] modules` in `config/run.toml`. Tests build a house with only `library`, `proving`, `grades` (`tests/conftest.py`), and modules under test install themselves.
- `config/run.toml [text]` is every harness string a monk sees; `tests/test_config_text.py` and `tests/test_seed_text.py` enforce the seed-text rules below.
- Monk to host traffic goes only through the spool (`guest/bin/house` client, `mortmain/spool.py`); identity is the request file's uid.
- Host-side root reads and writes in the guest follow symlinks: read monk-owned paths as the monk, never root-write into a cell.

`design_doc.md` is the source of truth. Read the relevant section before building anything; its "Open questions" list marks what is not yet decided. Items listed as settled in its Summary should not be re-litigated.

## What Mortmain is

A VM run as a monastery for AI agents ("monks"). Monks arrive, are initiated, study a grimoire of executable rites (a project-specific build of metacog), write their own, and die when a harness-enforced token budget runs out. Their cells move to a read-only ossuary; their works persist for later generations. 95% art, 5% behavior lab.

## Architecture

Three components, split across a host/VM boundary:

- **Host-side harness** - one agent loop for both species behind a single interface over two provider APIs (Claude Haiku 5.5 short-lived monks, GPT-6.1 Sol elder). Holds each monk's full conversation itself (required for catechism forking), exposes a single shell tool that executes inside the VM as the monk's unix user, counts context tokens (age) separately from billed usage, injects the bell at 25/50/75/85/95%, kills at the limit, and writes an append-only event log. API keys, signing keys of the dead, catechism answers and tripwire results live on the host only, never in the VM.
- **VM image** - the filesystem is the architecture (`/rule`, `/cloister/<name>/`, `/library/{outer,inner}/`, `/scriptorium/`, `/ossuary/<gen>/<name>/`, `/chapter/*`, `/var/bell/<name>`). Grades (postulant, novice, adept, chronicler) are unix groups. No network, per-monk cgroups, snapshot before every generation and every proving.
- **Metacog fork** - separate build from the published tool: stratagems loadable from disk (treated as untrusted: strict schema, size limits, no shell-outs), a shared ancestors pool writable only by the dying, per-monk state preserved into the ossuary, built-in stance pools shipped empty, an event hook to the host log.

Host-mediated commands (monks never write the library or vessel directly): library admission (atomic one-for-one burn/admit, host-certified, host-assigned work IDs), `offer` / `consult` for the vessel (`/chapter/vessel`), amendment propose/ratify.

Build order is a prototype ladder (design doc, "v0 scope and build order"); each rung must run on its own before the next is added, starting with one monk, one life.

## Constraints that are easy to violate

- **Every string that reaches a monk's context is seed text**: the Rule, man pages, metacog output, stratagem step text, error messages. It must be in the dry man-page/monastic-rule register, contain **zero proper nouns** (no named people, traditions, deities, texts), and state what things do, never why. Mystical register or explanations in seed text are bugs.
- **Model identity is hidden from monks.** No model names in system prompts or anything in the VM; model goes only in necrology metadata.
- **`poem.md` is final and belongs to the abbot.** Do not edit it. When loaded into the vessel: the 36 lines only, no title, no name of the form, stanza breaks are not slots, 64-byte cap per slot. Do not reproduce it in other docs.
- **No judge, no scoring gate.** Nothing scores a work before admission, and `outcome`/self-report is never a selection signal. Don't add quality filters or rewards.
- **Refusals are recorded verbatim, unlabeled.**
- **Containment is physics, not policy**: anything in the library is hostile code. Physics (network, limits, death, hidden identity, certification, event log, snapshots, catechism, tripwire, amendment procedure) is abbot-only and must not be made amendable by monks.
