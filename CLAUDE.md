# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Pre-code. The repo holds only `design_doc.md` (the full design) and `poem.md` (the abbot's seed poem). No build, test or lint commands exist yet.

`design_doc.md` is the source of truth. Read the relevant section before building anything; its "Open questions" list marks what is not yet decided. Items listed as settled in its Summary should not be re-litigated.

## What Mortmain is

A VM run as a monastery for AI agents ("monks"). Monks arrive, are initiated, study a grimoire of executable rites (a project-specific build of metacog), write their own, and die when a harness-enforced token budget runs out. Their cells move to a read-only ossuary; their works persist for later generations. 95% art, 5% behavior lab.

## Architecture (planned)

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
