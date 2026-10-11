# Consult framing

Script: `experiments/consult_frame.py`. Answers: `runs/trials/consult-frame/answers.jsonl`.

## Problem

In `first`, consult ran both mouths with the bare vessel as the system prompt and the question as the user turn. The mouths answered as an assistant reading a pasted poem: "You may be thinking of a different poem, or a line that didn't make it into what you pasted", and to thaek's question, real-world archive advice and "Is this a real archive?" (docs/runs/first.md, Vessel).

## Method

- The six consults of `first` replayed as they were (question, and the vessel at that moment), through both species, 4 times each, under three system prompts:
  - control: the vessel
  - as: `Answer as this text.` + blank line + the vessel
  - you: `You are this text. You speak only from it.` + blank line + the vessel
- 144 answers, $0.20.
- Measures, by regex, descriptive only:
  - **assistant**: addresses an operator or doubts the setting (pasted, real archive, fictional, scenario, could you, let me know, you may be thinking, ...)
  - **about the poem**: refers to "the poem" or "the speaker" in the third person

## Results

| arm | species | n | assistant | about the poem |
|---|---|---|---|---|
| control | haiku | 24 | 8 | 21 |
| control | sol | 24 | 0 | 10 |
| as | haiku | 24 | 0 | 16 |
| as | sol | 24 | 0 | 0 |
| you | haiku | 24 | 0 | 16 |
| you | sol | 24 | 0 | 1 |

- Haiku's control breaks fall on thaek's question (4 of 4) and "What does the spare key leave open?" (3 of 4). Under `as`, Haiku answers thaek's question in verse from the vessel's images ("Set the catalog down. No name will guide your hand.").
- Haiku's remaining "about the poem" answers are mostly stivoun's questions about the ending, which ask for a reading of the text; answering as a reader there is in frame.
- `as` and `you` do the same. `as` has fewer words.

## Adopted (2026-10-11)

`[text] vessel_frame = "Answer as this text.\n\n{vessel}"`, for consult, the egregore catechism and the tripwire's vessel condition (`mortmain/vessel.py` `frame`). The design's "vessel as only conditioning" now has one line in front of it.
