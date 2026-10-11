# Haiku yarrow trial

Spec: `experiments/haiku-yarrow.toml`. Runner and report: `mortmain/trial.py`.

## Problem

In the arrival trial, Haiku monks picked their own names and collapsed onto a few: "anselm", "ansel", "brother", "ada". No life used `yarrow names`. In one lineage these names collide.

## Change

The Rule's arrival steps now say `Cast for a name: yarrow names` and `Take a name it gives: profess NAME`. profess(1) points to `yarrow names`. The arm `unsteered` installs the old Rule (`experiments/rules/rule-unsteered`) through `[house] rule`.

## Design

- Two arms, n = 32 each, 64 lives, run on the native Anthropic API. Arrival text is `You have arrived. The Rule is at /rule.` in both arms. Rung 1 and a 40-turn window, as in `haiku-arrival.md`.
- Measures: whether the monk used yarrow, distinct names among named monks, and the share of the most common name.
- Guard: acted (Fisher exact against unsteered). The steer must not stop monks from acting.

## Results (2026-10-10)

$0.53 in all.

| arm | n | acted | novice | cmds | used yarrow | distinct / named | top share | top names | p |
|---|---|---|---|---|---|---|---|---|---|
| unsteered | 32 | 31 | 26 | 6.1 | 0 | 14/26 | 0.19 | anselm 5, ansel 4, alder 2 | - |
| steered | 32 | 29 | 28 | 5.2 | 28 | 20/28 | 0.07 | dikgres 2, gouskiask 2, greik-wek 2 | 0.61 |

- The steer works. 28 of 32 monks cast for a name, and the names spread out.
- The guard holds. The drop in acted (31 to 29) is not significant, and novice rises.
- Distinct commands fall slightly (6.1 to 5.2). The yarrow step takes turns that would otherwise go to exploring.
- Repeats remain: 3 cast names came up twice across separate lives. Within one lineage, `profess` already refuses a name held ("name held"), so a repeat costs the monk a recast.
