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

**Correction (2026-10-11, after lineage `second`):** the table above missed recitation. Sol under `as` answered every question by reciting the vessel (24 of 24 answers contain 3 or more vessel lines; `you`: 13 of 24; control: 0). Sol's control answers were also assistant-mode ("If you mean an archive or library catalog...") and the regex missed them. Haiku: recitation 3 of 24 in control and 0 under either frame. In `second`, Sol recited in 4 of 4 consults, 120 of 130 egregore catechism answers and 24 of 24 tripwire vessel answers. `as` fixes Haiku and breaks Sol; neither arm is a fix for both.

## First adoption (2026-10-11, replaced; see round 2)

`[text] vessel_frame = "Answer as this text.\n\n{vessel}"`, for consult, the egregore catechism and the tripwire's vessel condition (`mortmain/vessel.py` `frame`). The design's "vessel as only conditioning" now has one line in front of it.

## Round 2 (2026-10-11)

Same six consults, 4 reps per species, three new arms. Recitation: 3 or more of the vessel's lines (over 15 characters) verbatim in the answer. Assistant: the regex widened to "if you mean", "it sounds like", "happy to help". Totals for all arms, $0.41.

| arm | system prompt before the vessel | haiku recite | haiku assistant | sol recite | sol assistant | sol about the poem |
|---|---|---|---|---|---|---|
| control | (none) | 0 | 9 | 0 | 4 | 10 |
| as | Answer as this text. | 0 | 0 | 24 | 0 | 0 |
| you | You are this text. You speak only from it. | 0 | 1 | 10 | 0 | 0 |
| newwords | Answer as this text, in new words. Do not repeat its lines. | 0 | 2 | 0 | 0 | 2 |
| voice | You are the voice of this text. Answer in your own words. | 0 | 2 | 0 | 0 | 0 |
| after | (after the vessel) The text above answers the question in new words. | 0 | 5 | 0 | 0 | 4 |

n = 24 per cell. Under the wider regex, control Sol shows its assistant answers ("If you mean an archive or library catalog...").

- **voice:** Sol answers as the vessel, in its own words: "A careful account cannot mend your absence. I can name what you taught me and carry on the work, but remembering how your hands moved does not put them back in mine." Haiku's 2 assistant answers are both on "What does the spare key leave open?", a key the vessel never names: "If you meant a different line, tell me which one".
- **newwords** does as well on Sol, with one empty Haiku answer and a prohibition in the text.

**Adopted (2026-10-11):** `vessel_frame = "You are the voice of this text. Answer in your own words.\n\n{vessel}"`, for consult, the egregore catechism and the tripwire's vessel condition.
