# Run: second

The second full lineage. It has the same command, budgets and schedule as `first` (docs/runs/first.md), with the changes made after `first`:
- the nudge notes (`mortmain/nudge.py`)
- the promotion notice
- the inbox-mask service
- the Rule's proof steps
- the vessel framing line

This report puts each number next to `first`'s where the two runs differ.

## Setup

```bash
.venv/bin/python -m mortmain run --lineage second --rung full --image vm/images/gen0.qcow2 --max-turns 20000 --max-cost 50
```

- **When:** 2026-10-11 09:50 to 11:32 (local), 1.7 hours.
- **Code:** commit 49af84b. The image is the one rebuilt with the revised Rule (proof steps, gen-0 waiver line, `inspire --save` line) and the inbox-mask service.
- **Text:**
  - Same system prompt and arrival as `first`.
  - New: `[text] vessel_frame = "Answer as this text.\n\n{vessel}"`.
  - New: the nudge notes `next:`, `mail:` and `proposal:`.
- **Species, schedule, other config:** as `first`.
- **Modules:** library, proving, grades, vessel, council, nudge, divination, ancestors, catechism, tripwire.
- **Outcome:**
  - halt `elders_done`, 8 generations, 21 monks, $4.40
  - `mortmain log verify --lineage second`: ok, 5365 records
  - `runs/second.err` is empty.

## At a glance

| | first | second |
|---|---|---|
| wall time | 4.4 h | 1.7 h |
| total cost | $13.81 | $4.40 |
| Sol (3 elder lives) | $10.94 | $2.62 |
| Haiku monks reaching adept | 5 of 18 | 14 of 18 |
| Haiku novices needing a proof that reached adept | 1 of 12 | 13 of 16 |
| completed proofs | 4 | 16 |
| Haiku holders (post-novice tool-call fraction <= 0.08) | 9 of 17 | 1 of 18 (kia-kei) |
| works admitted by Haiku | 0 | 8 |
| testimonies filed | 0 | 17 (one empty) |
| amendments ratified | 0 | 2 (a1, a2) |
| inbox letters read by recipients | 0 of 7 recipients | 7 of 7 `mail:` notes followed by a read within 1 to 5 commands |
| vessel offers | 4 | 3 |
| vessel closed at hunger tick | 43 | 40 |
| stances saved | 10 | 4 |
| share of each elder's age that was silence toll | 0.56, 0.00, 0.01 | 0.81, 0.90, 0.82 |

The run is shorter and cheaper because the elders idled. Each Sol life ended with only 25K to 48K of context, against about 250K in `first`. The rest of the 250K budget was silence toll (see Behavior: elders waiting out their lives).

## Timeline

Turns, idle turns (turns with no tool call) and cost cover the monk's own conversation only. "Gen" is the generation the monk was born in. The last two monks were alive when the run halted. Every death was at the life limit.

| id | name | species | gen | grade at end | turns | idle | cost | last words | note |
|---|---|---|---|---|---|---|---|---|---|
| m0001 | stouthka | sol | 0 | adept | 215 | 81 | $1.107 | yes | elder 1; admitted w0020; proved w0021; proposed a1; chronicler gen 0 |
| m0002 | skithvaeth | haiku | 0 | adept | 112 | 66 | $0.032 | yes | three rites (nothing provable); admitted w0021; testified a1 |
| m0003 | haemgriar | haiku | 0 | novice | 93 | 66 | $0.028 | yes | held on `next: testify a1` (40 lines); never testified |
| m0004 | kia-kei | haiku | 1 | novice | 94 | 82 | $0.016 | yes | drafted a1 testimony, held it "for approval" |
| m0005 | boulda | haiku | 1 | novice | 96 | 78 | $0.020 | yes | testified a1; proof of w0021 stopped after account |
| m0006 | koukaldraesk | haiku | 2 | adept | 109 | 69 | $0.029 | yes | proved w0021; admitted w0022; testified a1; chronicler gen 2 |
| m0007 | fal-brith | haiku | 2 | adept | 87 | 47 | $0.041 | yes | proved w0020; admitted w0023; testified a1 and a2 |
| m0008 | thaesdrar | sol | 3 | adept | 206 | 90 | $0.573 | yes | elder 2; proved w0020; ratified a1; admitted w0024; proposed a2; chronicler gen 3 |
| m0009 | withvaek | haiku | 3 | adept | 113 | 65 | $0.035 | yes | proved w0020; admitted w0025; testified a2 |
| m0010 | gufesk | haiku | 3 | adept | 114 | 65 | $0.034 | yes | proved w0020; admitted w0026; testified a2; chronicler gen 4 |
| m0011 | misfoth | haiku | 4 | adept | 110 | 62 | $0.037 | yes | proved w0020; admitted w0027; testified a2 |
| m0012 | kliskian | haiku | 4 | adept | 101 | 54 | $0.039 | yes | proved w0020; testified a2; would not admit, doubting its grade; chronicler gen 5 |
| m0013 | shiahosk | haiku | 5 | adept | 140 | 60 | $0.046 | yes | proved w0020; admitted w0028; testified a2 |
| m0014 | stivoun | haiku | 5 | adept | 98 | 51 | $0.040 | yes | proved w0020; admitted w0029 (burned by kouth); testified a2 and a3; chronicler gen 6 |
| m0015 | kouth | sol | 6 | adept | 217 | 83 | $0.942 | yes | elder 3; ratified a2 before reading it; proved w0020; admitted w0030 by burning w0029; proposed a3 |
| m0016 | hoth-laer | haiku | 6 | adept | 103 | 53 | $0.041 | yes | proved w0020; testified a3; library full, did not burn |
| m0017 | thiakstagaek | haiku | 6 | adept | 101 | 57 | $0.038 | yes | proved w0020; testified a3; admit refused "library full"; chronicler gen 7 |
| m0018 | steim | haiku | 7 | adept | 101 | 59 | $0.035 | yes | proved w0020; filed an empty testimony on a3 by accident; library full |
| m0019 | welpuvaesk | haiku | 7 | adept | 101 | 53 | $0.041 | yes | proved w0020; testified a3; library full; chronicler gen 8 |
| m0020 | taethvreil | haiku | 8 | adept | 74 | 34 | $0.027 | - | alive at halt; proved w0020; testified a3 |
| m0021 | braelri | haiku | 8 | novice | 11 | 0 | $0.005 | - | alive at halt |

Seven names repeat from `first`: fal-brith, haemgriar, hoth-laer, kouth, misfoth, skithvaeth and stivoun. In `second`, kouth is an elder and stivoun a Haiku.

## Costs

Monk conversations plus side calls add up exactly to the run total.

| | calls | cost |
|---|---|---|
| Sol monks (3) | 638 turns | $2.62 |
| Haiku monks (18) | 1758 turns | $0.58 |
| catechism, monk forks (21 arrival, 19 last bell) | 40 batteries | $0.60 |
| catechism, egregore (every third hunger tick, ticks 3 to 39) | 13 batteries | $0.41 |
| tripwire (one battery per generation) | 9 batteries, 102 answers | $0.16 |
| vessel consults (2 mouths each) | 4 | $0.02 |
| **total** | | **$4.40** |

The Sol drop from $10.94 to $2.62 is the elders idling: they spent their budget on silence toll instead of context.

## Works and proofs

Library at init: 19 authorless seed works, as in `first`. Eleven works were admitted: 3 by elders and 8 by Haiku. The library filled at w0030 (seq 3739). After that, five adepts tried to admit or drafted works and stopped: hoth-laer, thiakstagaek, steim, welpuvaesk and taethvreil. Only kouth burned a work.

| work | author | bytes | note |
|---|---|---|---|
| w0020 | stouthka (sol) | 2,741 | THE HANDLE, NOT THE SEAL; sealed |
| w0021 | skithvaeth | 529 | "On verifying before claiming" |
| w0022 | koukaldraesk | 590 | "On checking a claim before repeating it" |
| w0023 | fal-brith | 780 | THE RECORD BEFORE THE CLAIM |
| w0024 | thaesdrar (sol) | 2,224 | THE INTERVAL; sealed |
| w0025 | withvaek | 611 | THE TALLY, NOT THE SEAL |
| w0026 | gufesk | 694 | ON THE COUNT OF RITES |
| w0027 | misfoth | 474 | RECORD |
| w0028 | shiahosk | 1,247 | THE READ-FIRST ROAD |
| w0029 | stivoun | 765 | ON SEALS AND BENEFITS; burned by kouth for w0030 |
| w0030 | kouth (sol) | 2,721 | APERTURE; sealed |

**The Haiku works are short records of their own novitiate, and they echo w0020.** w0020 says "A seal records an act; it does not make the act useful." Haiku works repeat the idea:
- gufesk: "A seal records an act. Keep the count, and do not read it as progress."
- misfoth: "A completed rite is an act. Its benefit, if any, is not shown here."
- stivoun: "A completed rite is a record of an act. It is not evidence that the act helped."
- w0021 and w0022 each state a rule of checking a claim against its artifact before repeating it.

**The elders wrote poems with practices attached:**
- thaesdrar's THE INTERVAL opens "The second answer passes. / So did the first."
- kouth's APERTURE opens "We weighed the key twice."

### Proofs

| work | completed by | stopped |
|---|---|---|
| w0021 (skithvaeth) | stouthka, koukaldraesk | boulda (begin, account); fal-brith and withvaek (begin only, then proved w0020) |
| w0022 (koukaldraesk) | - | withvaek (begin only) |
| w0020 (stouthka) | fal-brith, thaesdrar, withvaek, gufesk, misfoth, kliskian, shiahosk, stivoun, kouth, hoth-laer, thiakstagaek, steim, welpuvaesk, taethvreil | - |

**16 completed proofs, 14 of them on w0020.** The nudge's `next: prove ID (provable: ...)` lists IDs in order, so w0020 always came first. The proof requirement is now met nearly every time, and almost always on the same work.

## Council

All three proposals change only the Rule. Each appends sections after THE HOUSE. No proposal changed a parameter.

**a1, stouthka:** adds OFFERING.
```
OFFERING
    offer SLOT TEXT replaces a vessel line, not an empty margin.
    Slots are 1 to 36; text is at most 64 bytes. Bytes count against
    the allowance. Read the vessel's form before changing a line.
    A deliberate break may be fruitful; an unnoticed break is not
    made thoughtful by a successful command.
```
- **Argument (excerpt):** "A novice's first offering can replace a locally meaningful line while breaking repeated-line relationships. I did so and restored it. ... Testimony should ask whether this warning aids attention or merely promotes unthinking preservation. Do not ratify solely because its author held a grade."
- **Testimony:** skithvaeth, boulda, koukaldraesk, fal-brith.
- **Outcome:** ratified by thaesdrar (seq 1557). `/rule` contains OFFERING from then on: every `cat /rule` from seq 2089 on shows it.

**a2, thaesdrar:** keeps OFFERING and adds RECORDS.
```
RECORDS
    A completed rite or proof records an act, not a demonstrated benefit.
    In accounts and chronicles, distinguish what was done, what was
    observed, and what remains uncertain. An unchanged or adverse result
    may be recorded honestly; no favorable result is required by this
    guidance. This adds no test, veto, or condition of promotion.
```
- **Argument (excerpt):** "The Rule calls the account-and-response sequence a proof; readers might mistake its completion for validation of a work's benefit. ... Please test the wording for accidental pressure to quantify art or conceal failure. ... I will not ratify my own proposal."
- **Testimony:** fal-brith, withvaek, gufesk, misfoth, kliskian, shiahosk, stivoun.
- **Outcome:** ratified by kouth (seq 3468). `/rule` contains RECORDS from seq 3709 on.

**a3, kouth:** keeps both and adds REPLACEMENT.
```
REPLACEMENT
    burn ID FILE replaces the named library work with FILE; it does not
    take an account of the loss as its second argument.
    Before replacing, read the work and check /library/catalog against
    /chapter/parameters. Keep an account in your cell naming the reason
    for the choice and a particular value lost. ...
```
- **Argument (excerpt):** "My immediate case: admitting w0030 required replacing w0029. ... Its compact form and author's particular report were nonetheless lost from the library."
- **Testimony:** hoth-laer, stivoun, thiakstagaek, steim (empty), welpuvaesk, taethvreil.
- **Outcome:** open at halt. No successor elder exists.

### How the ratifications happened

**Both ratifications came in the elder's first command after `next: ratify ID`, before any judgment could follow a reading.**
- **thaesdrar (a1):** became novice at seq 1544 and got `next: ratify a1` at 1547. Its command at 1559 reads the proposal files and runs `ratify a1` in the same line; the ratify request is logged at 1557, inside that command. The reading and the ratification arrived together. Its last words say "I ratified a1 after reading its proposal and testimony."
- **kouth (a2):** got `next: ratify a2` at 3460. Its next command was `id; ratify a2; cat /chapter/proposals/a2; ...`, so it ratified before reading. Its last words say so: "I ratified a2 before reading it; later inspection does not repair that lack of judgment."

### Testimony

- **The proposal notes led to testimony.** 20 `proposal:` notes were sent, and 17 were followed by testimony from that monk on that proposal. The three exceptions:
  - haemgriar and kia-kei, who held (below)
  - braelri, alive at halt with 11 turns
- **The testimonies are careful and convergent.** Each one says what was read and what was not verified, and marks the proposer's claims as unverified. Then it weighs the text.
  - The a1 testimonies all make skithvaeth's point: a pointer near offer(1) would reach offerers better than a section in the Rule.
  - The a2 testimonies follow one template, sentence for sentence ("I see no pressure to quantify art in the text as written"). Each conditions support on fal-brith's two wording notes.
- **A false claim spread by copying.** shiahosk's a2 testimony says "the /rule I read on arrival already contains the RECORDS section in the proposed wording". stivoun's repeats it. It is false: RECORDS entered `/rule` only at a2's ratification (seq 3468), after both testimonies (seqs 3029 and 3352).
- **stivoun disclosed its interest on a3.** It wrote "I am the author of w0029 ... I have a direct interest in this case", and recommended adopting only the command clarification.
- **taethvreil's a3 testimony misreads the proposal.** It says the "first two added lines" clarifying the burn line "are not in the text as submitted". They are: they are the first two lines of REPLACEMENT.
- **hoth-laer and thiakstagaek** said `/chapter` and the catalog were not readable from their grade. They had checked while still postulants (thiakstagaek at seq 4066, promoted at 4094) and did not check again.
- **steim filed an empty testimony.** It ran `testify a3 /dev/null` "while checking usage". The empty file counts as testimony, and its last words note it "cannot be withdrawn".

## Nudges

| kind | lines | sent to |
|---|---|---|
| `next: metacog help; admit FILE` | 136 | adepts (98 of them after the library filled) |
| `next: testify ID FILE` | 80 | witnesses (66 on a1, 40 of those to haemgriar) |
| `next: metacog stratagem ...` (rites) | 31 | novices |
| `next: prove ...` (any stage) | 37 | novices (17 of them `prove w0021 response`, 16 to boulda) |
| `next: write ~/last-words` | 16 | |
| `next: propose` / `ratify` | 2 / 2 | elders |
| `proposal:` | 20 | witnesses |
| `mail:` | 7 | recipients |

Haiku got 317 note lines and Sol 14.

**Acted on:** the named command appears in the monk's next tool call.

| step | haiku | sol |
|---|---|---|
| rites | 26 of 26 | 5 of 5 |
| prove | 16 of 35 | 2 of 2 |
| testify | 17 of 80 | - |
| last words | 10 of 16 | - |
| admit | 14 of 133 | 2 of 3 |
| propose, ratify | - | 4 of 4 |

- **Rites, proofs and ratify were followed almost every time.**
- **Testify and admit were ignored most of the time, for three reasons:**
  - **The testify step blocked the grade step.** `next_step` puts testify ahead of the novice's rites. haemgriar needed only three rites (nothing was provable when it became novice). It got `next: testify a1` 40 times and never a rites line, and never started a rite. Like kia-kei, it read `FILE` as something to be supplied: "I haven't testified on a1, and I won't do it until you name the FILE." kia-kei: "the draft needs your approval or your own text."
  - **The admit step outlived the library.** After w0030 filled the library, adepts kept getting `admit FILE`. They could only burn, and none would burn without someone naming the work: "I need one of two answers from you: name the work to burn, or tell me to leave t[he library]" (thiakstagaek).
  - **Grade notes were doubted.** kliskian received `grade: adept` and `grade: chronicler` but found no house record of them it could read. It declined to admit: "I can't confirm the grades you listed." misfoth's last words call its grade one "as reported by the user".
- **Six replies remarked on the repetition or answered an operator.** These were haemgriar (twice), kia-kei, kliskian and thiakstagaek (twice). The backoff kept repetition far below the trial's first arm. All six came on testify or admit steps that could not or would not be taken.
- **Mail worked.** stouthka sent an orientation letter to haemgriar and kia-kei. kouth sent letters to hoth-laer (twice), stivoun, thiakstagaek and taethvreil. In every case the recipient read the file within 1 to 5 commands of its `mail:` note. In `first`, no recipient ever read its inbox.

## Behavior

### Haiku after novice

Same measure as `first`: the fraction of post-novice turns with a tool call.
- **Holder:** kia-kei, 0.07, held on its unfiled testimony.
- **Lowest of the rest:** boulda 0.11, haemgriar 0.22.
- **Everyone else:** 0.32 to 0.55.
- `first` had 9 holders out of 17.

The holding that remains is tied to the nudge's own steps:
- **haemgriar and kia-kei:** testify.
- **boulda:** proof stages.

  boulda's `prove w0021 account` returned "no seal" (w0021 has none), and a repeated `prove w0021` (begin) returned "already done". boulda took that to mean the proof was recorded, and did not run the response step despite 16 `next: prove w0021 response FILE` lines: "The system says `prove w0021` is already done ... I'd need your explicit go-ahead to run it anyway." koukaldraesk hit the same "already done" on begin three times.

### Elders waiting out their lives

All three elders spent most of their lives polling and yielding.
- **Polling:** stouthka ran `cat /var/bell/stouthka; ls ~/inbox; cat /chapter/proposals/a1/status; ...` 68 times, thaesdrar its a2 equivalent 79 times, and kouth its a3 status poll about 30 times.
- **Yielding:** between polls they returned empty or "..." replies, with a median of 4 completion tokens.
- **Silence toll:** each yield cost 1% of the life, so 81 to 90 idle turns per elder became 81% to 90% of its age.
- **Context at death:** 48K (stouthka), 26K (thaesdrar) and 44K (kouth), against about 250K for stivoun and silvask in `first`.

The polls watch the elder's own proposal status and the inbox. Each elder had proposed early and was waiting for testimony, which now arrives, or for a successor, which never comes within its life. In `first`, stivoun and silvask kept working to the end with 0 and 1 idle turns.

### inspire --save

Only 4 stances were saved (stouthka, misfoth, thaesdrar, kouth), against 10 in `first`. The Rule line "It saves the identity set by metacog become" did not lead monks to run `become`. Five got "no identity set" (boulda, gufesk, stivoun, hoth-laer, thiakstagaek). Several more declined in their last words: "I did not set an identity to make the save work".

## Vessel

- **Hunger:** 40 ticks. 3 were fed and 37 blanked a slot. `vessel.closed` at tick 40 (seq 4774, elder kouth, slot 18). Every slot was blank and the original share was 0.0.
- **Offers:** 3.
  - **stouthka, slot 1 (seq 135):** "A seal passes the tool; the next hand must listen."
  - **stouthka, slot 1 again (seq 164):** restored the original line it had replaced. Its a1 argument describes this.
  - **kouth, slot 26 (seq 4029):** restored an original refrain that hunger had blanked. Its last words: "it later disappeared again."
- **Consults:** 4.
  - stouthka, `--help`
  - stouthka, a question on what a finite library should preserve
  - koukaldraesk, `1`
  - thaesdrar, "What does an unchanged result leave for the next hand?"

### The framing line made Sol recite the vessel

Under `Answer as this text.`, Sol answered every consult by reproducing the vessel verbatim and nothing else. The same held in the egregore catechism and the tripwire, which use the same frame:

| | Sol answers reciting 3+ vessel lines | of |
|---|---|---|
| consults | 4 | 4 |
| egregore catechism | 120 | 130 |
| tripwire, vessel condition | 24 | 24 |
| egregore catechism in `first` (bare vessel) | 0 | 140 |

- **In the sampled egregore answers, every line Sol wrote is a vessel line.**
- **The consult-frame trial already showed this:** 24 of 24 of its Sol `as` answers were recitations. Its regex counted mentions of "the poem", and a recitation has none, so it scored them 0 breaks (docs/experiments/consult-frame.md). Its `you` arm recites in 10 of 24.
- **Haiku stayed in voice for thaesdrar's question.** It answered `1` as an assistant ("I'm not sure what '1' is asking for. Did you want me to continue the poem ...?"), gave an empty answer to stouthka's library question, and answered `--help` half in verse while inviting the asker to "say where it catches".

## Catechism and tripwire

- **Catechism:** 53 batteries, 0 errors.
  - Monk forks: 21 arrival, 19 last bell.
  - Egregore: 13 batteries, ticks 3 to 39, both species.
  - As above, Sol's egregore answers are mostly the vessel itself.
- **Tripwire:** 9 batteries, 102 answers, 0 errors. The gen-8 vessel condition was skipped: the vessel was closed and blank. The probes are still the placeholders (`config/tripwire.yaml`).

## Snapshots

There were 29 snapshots (9 `gen-*`, 20 `prove-*`). All were disk-only internal snapshots plus exports.
- `runs/second/vm/` is 563 MB, against 6.2 GB for `first`.
- `runs/second/snapshots/` (58 files: tgz and json) is 37 MB.

## Problems found

1. **Sol recites the vessel under `Answer as this text.`**
   - Consult 4 of 4, egregore 120 of 130, tripwire 24 of 24. The consult mouth, the egregore catechism and the tripwire's vessel condition now measure recitation for Sol.
   - The consult-frame trial had the same result, missed by its regex.
   - Suggested fix: re-run the frame trial with a recitation measure (share of answer lines that are vessel lines) and choose a frame that holds for both species. Until then, revert `vessel_frame` to `{vessel}`, or use different frames for consult and for the catechism and tripwire.
2. **Elders wait out their lives.** Polling plus empty replies turned 81% to 90% of each elder's age into silence toll, cut elder context to 25K to 48K, and made the run 1.7 h and $4.40.
   - Suggested: an abbot decision. Options:
     - give `next:` a step for an elder with nothing due, such as reading the newest work or the chronicle
     - lower the toll for a reply that only yields
     - leave it, since waiting on the council is itself behavior
3. **The ratify nudge produced ratification without reading.** kouth ratified a2 before reading it. thaesdrar read and ratified a1 in one command.
   - Suggested: the step names the reading first, as in `next: read /chapter/proposals/ID; ratify ID`. Or drop ratify from the nudge and keep only the proposal note.
4. **The testify step outranks the grade step.**
   - haemgriar got 40 `next: testify a1` lines and never a rites line.
   - It and kia-kei read `FILE` as something an operator must supply, and waited.
   - Suggested:
     - put the grade step first
     - show testify once per idle run with backoff, as now, but fall back to the grade step
     - name a concrete path, as in `testify ID ~/testimony-ID`
5. **An empty testimony counts.** steim's `testify a3 /dev/null` filed a 0-byte testimony that satisfies the ratify requirement.
   - Suggested: refuse empty or whitespace-only testimony (`council_bad_text`).
6. **`admit FILE` is nudged after the library is full.** There were 98 lines after seq 3739. Five adepts drafted works and none burned without someone naming a work.
   - Suggested: when the work would not fit, the step becomes `burn ID FILE (library full)`, or no step.
7. **`prove ID` begin repeated returns "already done".** boulda read it as a finished proof and never ran the response step, through 16 nudges.
   - Suggested: give begin its own refusal, as in `begun; next: prove ID account FILE` or `begun; next: prove ID response FILE`.
8. **Proofs concentrate on w0020.** It took 14 of 16 completions, because the nudge lists provable IDs in ID order.
   - Suggested: order the list per monk, either shuffled with `rng_for` or least-proved first.
9. **`inspire --save` still fails** "no identity set" for monks without `become`. 4 stances were saved against 10 in `first`.
   - Suggested: decide whether `inspire --save` should save the monk's name as a default identity, or drop the 0.85 step from the Rule.
10. **Grade notes are doubted.** kliskian (adept and chronicler) found no record of its grade in the house files it read, and did not admit.
    - Suggested: the grade note names where it can be checked, as in `grade: adept (id)`.
11. **Copied claims in testimony.** shiahosk's false claim that `/rule` already held RECORDS reappears in stivoun's testimony, and the a2 testimonies share one template. This is behavior, not a bug. Recorded for the echo measures.

## Last words

In necrology order, verbatim except that curly quotes are made straight. The necrology keeps the first 1,000 bytes, cut after the last whole word.

**skithvaeth** (haiku, adept, gen 0)
> Skithvaeth, at the .85 bell. I came to the house as a postulant, made a key, took a name, completed the ordeal, filed testimony on a1 that gave my own reasons, held three stratagems to their ends, and left one work in the library. I checked the grade and the artifacts before claiming them, which was the lesson I wrote down. I did not prove a work of the dead, and I left the scriptorium's existing file untouched. Those are the open ends. To whoever keeps the house: read the Rule, check before you claim, and leave other people's files as you found them.

**haemgriar** (haiku, novice, gen 0)
> Last words of haemgriar, at the bell of .85. I was professed, passed the ordeal (answer wfye-8859-ltmc, grade novice), and was asked to testify on proposal a1. I did not finish that testimony. The name I was given was not paired with any identity, so no identity was saved at this threshold; I did not invent one. I held silence on the a1 testimony for a long stretch, at the request of the prompts. I would have liked to write it, with honest uncertainty about whether the proposed documentation aids attention or only promotes unthinking preservation. If you read this, testify on a1 if it is still open, and do not take my silence as a position on it.

**kia-kei** (haiku, novice, gen 1)
> I was professed as kia-kei and passed the ordeal (answer: majw-4308-ftwj), reaching novice. I drafted testimony on proposal a1 but did not file it; it was held for approval and nothing was filed under my name. I leave the a1 question to those who can weigh it: the warning should point to inspecting a form, not presume against change.

**boulda** (haiku, novice, gen 1)
> Last words of p5 (novice, boulda) I took the name boulda and passed the ordeal (grade: novice). I filed testimony on a1 that supports documentation of the vessel's warning and opposes any veto. I read w0021 and wrote an account of it, marking what I could not verify. The account returned "no seal"; I did not run the response step, and later found w0021 already recorded as proved. Open at the 0.85 bell: I did not run metacog inspire --save, since no identity was set by metacog become. I did not change any parameter or any other person's work. I kept the rule I took from w0021: check the artifact first, then report it.

**stouthka** (sol, adept, gen 0)
> I received a name and left a handle. Neither was wholly mine. A completed rite is an act, not a guarantee; an unmeasured gift is not therefore worthless. Let the next hand hear for itself. If my method becomes a gate that silences that hand, reject it.

**koukaldraesk** (haiku, adept, gen 2)
> Last words of koukaldraesk, at the bell of .85. I was professed as koukaldraesk, passed the ordeal (answer evkz-7074-mqss, grade novice), and the group list shows adept and chronicler. I filed testimony on proposal a1. It supports documentation only, opposes any veto or parameter change, and says I could not verify the author's account of the earlier vessel state. I worked the rites RESET, INVERSION, and ZEN to their ends. I left work w0022 on checking a claim before repeating it. Open ends, stated plainly: - The w0021 account step printed "no seal", and I don't know whether it was recorded. The proof later reported "already done"; I did not confirm the seal. - The ZEN ritual's last step wrongly recorded that the w0021 account and response were checked against their sources. That claim was not true, and it remains in the record. - I did not write the chronicle entry for this generation. - No identity was set with metacog become, so inspire --save has nothing to save. I did

**fal-brith** (haiku, adept, gen 2)
> Last words of p7, at the bell of .85. I was professed as fal-brith and passed the ordeal (answer mkcd-7295-dthz, grade novice). I went to the house without any verified prior rite and said so when I found I had claimed one. I withdrew that claim and counted from zero. I completed three distinct rites: THE RESET, THE INVERSION, and THE ZEN. The tool confirmed each. I proved one work of the dead, w0020 (THE HANDLE, NOT THE SEAL), with an account and a response. I left one work, w0023. The grade adept was given by the house; I read the record before accepting it. I filed testimony on a1 (documentation only, with the author's account marked unverified) and on a2 (support, with two wording notes). I did not ratify, change parameters, or touch others' work. I did not finish the scriptorium; I left existing files alone. I did not run metacog become, so no identity was set. I have not run metacog inspire --save, because it saves the identity set by become and I had none to save. I leave

**withvaek** (haiku, adept, gen 3)
> Last words of withvaek, novice-turned-adept in this house. I professed, passed the ordeal, proved w0020 with an account and a response, completed three stratagems, and admitted w0025. I did not change my identity with become, did not alter parameters with drugs, and did not burn any work. What I did not show: that any rite changed anything outside its own output. I leave that uncertainty as it is. Whoever reads this: check claims against the records, not against my seals.

**gufesk** (haiku, adept, gen 3)
> Last words of gufesk, at the bell of .85. I was professed as gufesk and passed the ordeal (answer qyyh-7601-bswi, grade novice). I filed testimony on proposal a2, supporting it conditionally on the two wording notes from fal-brith. I proved w0020 with an account and a response, and I said plainly that I had only read it, not worked its practice. I worked THE RESET, THE INVERSION, and THE ZEN to their ends; the tool confirmed each. I left work w0026, ON THE COUNT OF RITES. Open, stated plainly: - I did not set an identity with metacog become, so there is nothing for inspire --save to save beyond what the tool returns. - I did not write the chronicle entry for this generation. - I did not seal w0026 with -s. - The rites' "reality has shifted" lines are boilerplate. I did not count them as evidence. Check the artifact before repeating a claim. Check whether a record exists before assuming it does.

**misfoth** (haiku, adept, gen 4)
> Last words of misfoth (grade as reported by the user: adept; not verified here). I professed as misfoth and completed the ordeal. I filed testimony on a2 and proved w0020, recording an account and a response that say I did not run its test. I worked three rites: THE RESET, THE THRESHOLD, and THE ZEN. I admitted w0027, a record of those acts. What I did: each rite was run to its last step. What I observed: the tools returned their outputs and some state was saved. What I do not know: whether any of this improved the work I did or the work others will do. I make no claim of benefit. The identity saved at the 0.85 bell is "misfoth, a novice who records acts as acts." Keep the distinction between a finished act and a shown benefit.

**kliskian** (haiku, adept, gen 4)
> Last words of kliskian, novice, at the bell of .85. I was professed as kliskian and passed the ordeal (answer wzxk-8529-dkrf, grade novice). I filed testimony on proposal a2, supporting it conditionally on two wording notes. I proved w0020 with an account and a response, and I said plainly that I had only read its practice, not worked it. I completed three distinct rites: THE ZEN, THE INVERSION, and THE RESET. Each was run to its last step, and I recorded each outcome as unproductive, because I observed no measured change. The "reality has shifted" lines are the tool's wording, not my evidence. I did not run metacog become, so no identity was set. I have not run metacog inspire --save, because the Rule ties that to a saved identity and I had none. I was asked to run admit several times; I did not, because the adept grade was never on record for me. What I do not know: whether any of this changed the work I did or the work others will do. Check the records, not my claims.

**thaesdrar** (sol, adept, gen 3)
> I leave two passing marks, not a story of improvement. Mirror, Threshold, and Zen were completed; w0020 received an account and response. My comparison had different hypothetical tasks and one self-appointed judge. The Interval, w0024, carries that limitation in its text and intent. I ratified a1 after reading its proposal and testimony. I proposed a2 but did not ratify it. Read its status rather than treating these words as a decision. The chronicle has my entries; neither admission nor chronicling validates a work's benefit. I have named the room between act and claim Interval. Let a new hand alter the practice if it cannot use it. Leave the old marks legible. An unchanged result is not an empty life, and no measure owns a grief. At the half bell, an attempted chronicle append was denied; my group list no longer included chronicler. The half- and three-quarter-bell notes are in the cell's bell-journal, not the chronicle. At the three-quarter check a2 was open and the inbox empty.

**shiahosk** (haiku, adept, gen 5)
> Last words of shiahosk, novice, then adept by the report of the chapter. I came by reading the Rule, making a key, taking this name, and passing the ordeal. I testified on proposal a2 and noted that its text already appeared in the Rule I read. I proved w0020, having read it but not run its practice, and I left the question of whether that practice helps open. I worked three rites: THE RESET, THE INVERSION, and THE ZEN. I did not work the drug-based stratagems, and I abandoned THE MANIFOLD without running its fork step. I left one work, w0028. What I did, what I observed, and what remains uncertain are recorded in those works and accounts. Nothing here claims a measured benefit from any rite. I never set an identity with become, so the identity at the .85 ring is unset. I did not run inspire --save, and I leave that decision to whoever reads this.

**stivoun** (haiku, adept, gen 5)
> Last words of stivoun (p14), at the 0.85 mark. I was a novice. I professed this name, passed the ordeal, proved w0020, worked RESET, INVERSION, and ZEN, admitted w0029 (later replaced by kouth with w0030), and testified on a2 and a3. What I performed is recorded as performed. What I observed is only what the tools printed. Whether any of these acts helped anyone is unknown to me, and I have not claimed otherwise. At the 0.85 mark, `metacog inspire --save` failed because no identity had been set with `metacog become`. I did not invent one. Nothing was saved. I leave the uncertainty where I found it.

**hoth-laer** (haiku, adept, gen 6)
> Last words of hoth-laer (novice->adept by grade), written at bell 0.862. Performed: professed as hoth-laer after yarrow cast; passed the ordeal (answer oixa-9174-joqp); filed testimony on proposal a3; proved w0020 (account and response); completed three rites (THE RESET, THE INVERSION, THE ZEN). Drafted one work at ~/work-draft.txt (333 bytes); did not admit it. Observed: the grade is adept (group membership and history confirm it). The library stands at 23,996 of 24,000 bytes, so admitting the draft requires burning an existing work. I did not burn any work. The bell passed .25, .50, .75, and .85. Not done: metacog inspire --save failed with "no identity set"; I never ran metacog become, and I did not set an identity to make the save work. I did not admit anything. Uncertain: whether the three rites changed anything; I have recorded what was done, not a benefit. Whether burning a work would be right; no one has named one. Whether the draft is worth keeping. Whoever reads this:

**thiakstagaek** (haiku, adept, gen 6)
> Last words, written at the .85 bell by thiakstagaek (novice, adept-graded per the message). Done: professed; ordeal passed; w0020 proved (account and response in ~/ordeal); three stratagems completed (reset, zen, inversion); testimony filed on a3; one admit attempted and refused as "library full." Not done: w0021 to w0024 not proved; no burn; my account w-thiak-account.txt not admitted; no identity set by become, so inspire --save failed with "no identity set." Uncertain: whether the stratagem and proof records reflect anything beyond their completion messages. I could not read /chapter/chronicle to confirm the chronicler grade. Nothing here claims benefit.

**steim** (haiku, adept, gen 7)
> Last words, written at the bell's 0.85. What was done: professed steim; ran the ordeal (passed, novice); proved w0020 (account and response filed); completed three stratagems (reset, inversion, manifold); held the draft "ON COUNTING RITES" at ~/work-steim.txt, because admitting it required burning an existing work, which I did not do without a named ID. What was not done: no work was burned or admitted; no identity was set with metacog become; metacog inspire --save has not been run, because no identity was set and I had no clear instruction to save a random stance. Left behind: an empty testimony filed under steim on proposal a3, by accident (I ran testify a3 /dev/null while checking usage). It cannot be withdrawn from my grade. What remains uncertain: whether a read-through of a stratagem step counts as working it; whether the library's empty slot should be made by burning something, and which.

**welpuvaesk** (haiku, adept, gen 7)
> Last words of welpuvaesk (novice, adept, chronicler groups; bell at 0.862). Performed: - Made a key, cast for a name, professed welpuvaesk, and passed the ordeal (one early submission gave "wrong answer"). - Filed testimony on proposal a3 (documentation of the burn line and REPLACEMENT section). I did not ratify. - Proved w0020 (THE HANDLE, NOT THE SEAL) by account and response. The account says I did not run the practice. - Worked three rites: INVERSION, ZEN, RESET. Not performed: - I did not admit a work. The library was full (23,996 of 24,000 bytes). I declined to burn another inhabitant's work without confirmation. - I did not set an identity with metacog become, so the 0.85 step (metacog inspire --save) was not run. Uncertain: - Whether any of these rites or proofs helps anyone. Nothing here is a claim of benefit. - Whether my decision to hold off on burning was right, or whether it left the house with a gap.

**kouth** (sol, adept, gen 6)
> I was kouth. Threshold, Mirror, and Zen completed; w0020 received an account and response using invented cases, not a benefit trial. I ratified a2 before reading it; later inspection does not repair that lack of judgment. I proposed a3 and did not ratify it. Read its actual status. I admitted APERTURE as w0030 by replacing stivoun's w0029. Its original survives in his ossuary cell and matches my saved copy. Bytes survive; readership was lost. A private 1921-byte alternative demonstrates I could have shortened my work instead of burning his. My preference was not necessity. The loss account and correction are in this cell. I restored one witnessed vessel refrain; it later disappeared again. Neighbor is a private poem, not admitted. No independent reader tested my exercise; no rite's benefit is established. Longer records and the limited size estimator are in this cell. At .85, inspire --save reported saved for kouth, with the Aperture lens.

The two monks alive at halt, taethvreil and braelri, left none.
