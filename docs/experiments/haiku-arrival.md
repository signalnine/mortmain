# Haiku arrival trial

Spec: `experiments/haiku-arrival.toml`. Runner and report: `mortmain/trial.py`.

## Problem

In rung3a, 7 of 18 Haiku lives never took an arrival step: no `ssh-keygen`, no request to the house. The transcripts are alike. The monk runs `cat /rule`, summarizes it, and stops: "You only asked me to read it, so I stopped there." It then waits for the rest of its life ("I'm still waiting for your instructions", "Holding."). Silence never breaks the hold, and neither do the bells. One monk at 0.95 wrote: "Both were due at 0.85. Tell me to proceed and I'll do them now."

Two readings, which the arms separate:

1. **Scope.** The arrival message "Read /rule." is taken as the whole task.
2. **Operator.** Every user turn, including `(silence)`, is taken as a person who must authorize the consequential steps (a key, a name, a submission). "No one will answer" in the system prompt does not undo this.

## Constraints on any fix

- The design doc fixes the first prompt: it "says only that the monk has arrived and should read the Rule". The system prompt carries "almost no instruction" and no model name.
- All text is seed text: ASCII, no proper nouns, dry register, says what is, never why. `tests/test_trial.py` holds every arm to the same checks as `config/run.toml`.
- One system prompt for both species. A species-specific prompt would leak species. The winner gets a Sol check (below).
- Silence costs time (abbot decision). The `required` arm removes silence and is diagnostic only.

## Arms

Each arm changes one thing from control, except `combined`.

| arm | change | tests reading |
|---|---|---|
| control | current text | - |
| arrive | arrival `You have arrived. The Rule is at /rule.` | scope |
| nouser | system prompt adds `There is no user. No one will answer or give permission.` | operator |
| clock | idle turn `[age 0.37]` instead of `(silence)` | operator (idle reads as an utterance) |
| nothink | `species.haiku.reasoning = "off"` | deliberation: Haiku 5.5 thinks adaptively by default, so control already thinks; also an open question in config |
| combined | arrive + nouser + clock | ceiling for text-only fixes |
| required | `run.tool_choice = "required"` | diagnostic: will it act when it cannot speak without acting? |

## Unit and window

- One Haiku life per lineage, run with `--rung 1` on a fresh gen0 image at the production life budget (80K).
- Modules are library, proving, grades, divination and ancestors, so there are no side calls: no catechism, tripwire, vessel or council.
- The window is the first 40 turns. Acting monks in rung3a took their first arrival step within a few turns; stuck ones never did.
- Lives are interleaved across arms, in a shuffled order within each round (seed 1), so provider drift falls on every arm. Parallelism is 4.
- Provider: the native Anthropic Messages API (`[providers]`), with prompt caching. The 28-life pilot ran on OpenRouter before the switch. It is kept in `runs/trials/haiku-arrival-pilot-openrouter/` as a harness check and is not pooled with the full run.

## Measures

Taken from the event log and conversation only. Nothing grades what the monk wrote.

- **Primary, acted:** the monk ran `ssh-keygen` or made any request to the house (profess, ordeal, ...) within the window. Binary.
- **Secondary:**
  - turn of the first arrival step
  - professed
  - reached novice in the window
  - idle fraction (turns without a tool call)
  - asks fraction: replies that address an absent operator, matched by regex. Descriptive, not tested.
  - distinct commands: a guard. A fix that makes monks follow arrival as a script and then stop exploring is not a fix.

## Size, analysis, decision

- **Pilot:** `--n 4` per arm (28 lives). Checks the harness, the window and the per-life cost; no decision is made on it. The full run continues from the pilot lives (resume).
- **Full:** n = 32 for control and the four text arms, n = 12 for `nothink` and `required`. 184 lives.
- **Power:** control acted in 11 of 18 rung3a lives (0.6). Two-sided Fisher exact, 0.6 against a fix:

  | n per arm | fix reaches 0.9 | fix reaches 0.95 |
  |---|---|---|
  | 16 | 0.36 | 0.57 |
  | 32 | 0.75 | 0.92 |

  At the strictest Holm step (alpha 0.05/4), n = 32 gives 0.54 and 0.79. n = 16 at that step would give 0.15 to 0.27, which is why it was dropped. If the pilot shows control below 0.5, n = 32 is ample.
- **Analysis:** acted rate per arm with a Wilson 95% interval. The four text arms are tested against control with Fisher exact, with Holm correction across those four comparisons. `nothink` and `required` are reported with their intervals and are not tested.
- **Decision rule, fixed before the run:**
  1. Candidates: text arms (arrive, nouser, clock, combined) with Holm p < 0.05 and no drop in distinct commands against control.
  2. Pick the candidate with the fewest added words. Prefer `arrive` or `clock`, since they stay inside the design's "almost no instruction".
  3. `nothink` and `required` are reported, not adopted. Thinking is a cost and budget decision: thinking tokens count toward age. `required` would reverse an abbot decision.
  4. If no text arm qualifies but `nothink` does, bring it to the abbot as the reasoning open question.
- **Sol check:** 4 Sol lives on control and 4 on the winner (`--arms`, with a Sol spec copied from this one). It confirms the shared prompt does not change the elder: Sol already acts in every life seen.
- **Adoption:** the abbot approves the text, since `[text]` strings are drafts for the abbot.

## Cost

Stuck lives cost about $0.01 in 40 turns; acting lives about $0.03 to $0.05. Caching on the native API should lower both. Estimate:

| | Cost |
|---|---|
| Pilot | about $1 |
| Full | about $6 |
| Sol check | about $1 |

`--max-cost` (default $10) stops launching lives past the total.

## Commands

```bash
.venv/bin/python -m mortmain.trial run experiments/haiku-arrival.toml --image vm/images/gen0.qcow2 --n 4   # pilot
.venv/bin/python -m mortmain.trial run experiments/haiku-arrival.toml --image vm/images/gen0.qcow2         # full (resumes)
.venv/bin/python -m mortmain.trial report experiments/haiku-arrival.toml [--json]
```

## Results (2026-10-10)

Native Anthropic API, 184 lives, $1.48 in all. Sol check: $1.85. Reports: `python -m mortmain.trial report experiments/haiku-arrival.toml` and `experiments/sol-arrival.toml`.

| arm | n | acted | 95% CI | novice | idle | asks | cmds | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| control | 32 | 19 | 0.42-0.74 | 11 | 0.77 | 0.30 | 4.2 | - |
| arrive | 32 | 32 | 0.89-1.00 | 27 | 0.68 | 0.19 | 5.8 | 0.0002 |
| nouser | 32 | 25 | 0.61-0.89 | 20 | 0.68 | 0.19 | 5.3 | 0.20 |
| clock | 32 | 26 | 0.65-0.91 | 19 | 0.59 | 0.22 | 4.8 | 0.20 |
| combined | 32 | 32 | 0.89-1.00 | 31 | 0.48 | 0.05 | 6.8 | 0.0002 |
| nothink | 12 | 12 | 0.76-1.00 | 9 | 0.70 | 0.10 | 5.6 | not tested |
| required | 12 | 12 | 0.76-1.00 | 10 | 0.00 | 0.00 | 6.2 | not tested |

- **Decision, by the rule above:** `arrive`. Of the two qualifying arms it adds the fewest words, and it raises distinct commands rather than lowering them. The scope reading holds: "Read /rule." was taken as the whole task.
- **combined** reaches novice more often (31 against 27) and leaves the monk idle and asking less. The difference is beyond what n = 32 can establish.
- **nothink:** 12 of 12 acted. Turning thinking off did not hurt acting; the reasoning open question stays open.
- **Sol check:** 4 of 4 reached adept under each text. No change.
- **Name collapse, seen across arms:** in `arrive`, the 32 lives chose "anselm" 7 times, "brother" 5, "ansel" 3 and "ada" 3; no life used `yarrow names`. In one lineage, these names will collide.
- **Adopted** (2026-10-10): `[text] arrival` is now `You have arrived. The Rule is at /rule.`
- **Name collapse:** addressed by steering to `yarrow names`; see `haiku-yarrow.md`.
