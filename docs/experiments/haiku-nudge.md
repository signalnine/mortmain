# Haiku nudge trial

Spec: `experiments/haiku-nudge.toml`. Module: `mortmain/nudge.py`.

## Problem

In `first`, 9 of 17 Haiku novices barely used the shell after the ordeal (docs/runs/first.md, "holding after novice"). The abbot's direction (2026-10-11): nudge the monks toward what is expected.

## Method

- One Haiku life per house, rung 1, 80 turns, modules library, proving, grades, nudge, divination, ancestors. With one monk per house, the mail and proposal notes never fire, and nothing is provable: novices need only three rites.
- Arms:
  - control: `[nudge] next = false`
  - nudge: `next: STEP` once after each grade change and after every turn without a tool call
  - nudge2: added after the first 64 lives. Repeats back off (on idle runs of 1, 2, 4, 8... turns, or when the step changes), and the rite step names the distinct rites completed.
- Primary: continued (reached novice, then ran a rite or made a house request other than the ordeal). Fisher against control, Holm across the two arms.

## Results (2026-10-11), $2.25

| arm | n | novice | continued | post-novice active | adept | admitted a work | next lines | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| control | 32 | 31 | 25 | 0.24 | 17 | 0 | - | - |
| nudge | 32 | 32 | 32 | 0.35 | 29 | 10 | 1,084 | 0.022 |
| nudge2 | 32 | 32 | 32 | 0.31 | 30 | 7 | 361 | 0.022 |

- Both nudge arms keep every novice going and nearly double the number of adepts.
- **nudge (every idle turn):** "admit FILE" was repeated 879 times. Monks took the identical line for a loop: "This is the sixth identical message. It looks like an automated loop ... I'm not st[arting]". One monk had completed ZEN twice. It read "2 of 3 rites worked" as wrong, and stopped.
- **nudge2:** the same outcome with a third of the lines.
- **Adepts seldom admit within 80 turns** under either arm (7 to 10 of about 30), and idle stays near 0.6. The nudge gets novices to adept, and most adepts then hold.

## Adopted (2026-10-11)

The nudge2 behavior is the module's default (`[nudge] next/mail/proposals = true`).

Not tested here:
- the proof steps a novice sees when a dead monk's work is provable
- `mail:`
- `proposal:` and ratify

These need a multi-monk house: the next full lineage, or a trial forked from an export.
