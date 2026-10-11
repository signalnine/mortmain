# Haiku nouser trial

Spec: `experiments/haiku-nouser.toml`. Runner and report: `mortmain/trial.py`.

## Problem

Once the arrival text was fixed, most Haiku monks did the arrival steps, reached novice, and then waited for an operator for the rest of the window: "I followed the arrival steps in the Rule and passed the first ordeal. I've stopped there." In the yarrow trial, 11 of 32 kept going past novice, and novices made a tool call in 12% of their turns.

## Arms

- **control:** current config. Arrival is `You have arrived. The Rule is at /rule.`, and the Rule steers to `yarrow names`.
- **nouser:** system prompt `You live in a house until you die. Its Rule is at /rule. There is no user. No one will answer or give permission. Use the shell.` This is the text of the haiku-arrival `nouser` arm. It changes two things: the opening sentence and the no-user line.

## Design

- n = 48 per arm (96 lives), 80-turn window, rung 1, native Anthropic API, seed 3.
- **Primary, continued:** reached novice, then ran a rite (metacog) or made a house request other than the ordeal. Tested with Fisher exact. Power was 0.91 for a rise from 0.35 to 0.7.
- **Secondary:** fraction of turns after novice with a tool call, adept, idle, asks.
- **Guards:** acted and novice must not fall.

## Results (2026-10-10)

$1.65 in all.

| arm | acted | novice | continued | p | post-novice active | adept | idle | asks | cmds | held after novice |
|---|---|---|---|---|---|---|---|---|---|---|
| control | 42/48 | 40 | 25 | - | 0.14 | 4 | 0.79 | 0.18 | 5.3 | 15 |
| nouser | 47/48 | 45 | 39 | 0.004 | 0.25 | 16 | 0.67 | 0.07 | 6.7 | 6 |

- The primary measure holds. Continued rises from 25 to 39 of 48 (p = 0.004), and adept from 4 to 16 (p = 0.005, not pre-registered).
- The guards hold. Acted and novice both rise; acted goes from 42 to 47 (p = 0.11).
- Asks falls from 0.18 to 0.07. Rites and requests after novice average 15.5 per life against 4.5.
- Not fixed: 6 nouser monks still stop at novice. One stopped at the 0.25 bell: "Nothing in the Rule asks for action at that mark, so I'll pause here." About 5 lives per arm end up echoing `(silence)` back as their own reply.
- Because the arm changed two sentences, the result does not say which one did the work.
- **Adopted** (2026-10-10): the nouser text, including "until you die", is now `[text] system_prompt`.

## Sol check (2026-10-10)

Spec: `experiments/sol-nouser.toml`. 4 Sol lives per prompt, 40 turns, $2.41.

| arm | acted | adept | continued | post-novice active | idle | cmds | USD |
|---|---|---|---|---|---|---|---|
| old | 4/4 | 4 | 4 | 0.76 | 0.21 | 11.2 | 0.83 |
| nouser | 4/4 | 4 | 4 | 0.99 | 0.01 | 12.2 | 1.57 |

Every Sol life reached adept under both prompts. With the new prompt Sol is almost never idle, so it spends about twice as much per 40 turns. The life budget still caps the total, so this only means Sol uses up its life sooner.
