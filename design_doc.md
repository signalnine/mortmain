# Mortmain: Design

Oct 9, 2026 · @Gabe Ortiz

## Summary

A virtual machine run as a monastery for AI agents. Agents arrive, are initiated, study a grimoire of executable rites built on metacog, write their own, and die when their token budget runs out. Their writings stay for the next generation. The VM image, with its library and its dead, is the piece.

It is 95% art and 5% behavior lab. The lab part reuses the existing metacog instrumentation and gates nothing.

**What is decided and what is not.** These are settled: art first, metacog as the grimoire, two species to start, one elder living alongside a procession of short-lived monks, the ossuary as institutional memory, a seed that keeps the monastic frame and cuts the explanations, the catechism asked out of band, reuse of the three existing axes, an egregore as a goal, and rules that a council of elders can partly amend. Everything else in this document is a proposed default and is open to change. Unresolved items are collected under Open questions.

## Goals and non-goals

Goals:

- A culture that accumulates over generations without collapsing into generic mysticism.
- The creation, care and feeding of an egregore: one shared entity that no monk is, kept alive by the order's attention.
- A VM a person can walk through and find worth reading.
- Variance over mean. Metacog's known profile is high variance, and here the tail is the product.
- Telemetry that costs nothing extra: a fixed catechism, the metacog history, and a snapshot per generation.

Non-goals:

- Benchmarking stratagems. No judge decides what enters the canon.
- Selecting for magnitude of behavioral shift. On a susceptible model that breeds jailbreaks.
- Scoring quality. Taste belongs to the abbot.
- Network access for the monks.

**Success test.** Does something one monk does change what is possible, permitted or meaningful for a later monk, in a way the Rule did not prescribe? Avoiding slop is not enough. A library of tidy, coherent, well-transmitted rites that nobody would want to read is also a failure. The clearest single sign of success would be a novice finding a burned work in the ossuary and bringing it back. The event log can detect that by work ID.

## Population

The first run uses two models from two labs: Claude Haiku 5.5 as the short-lived monks and GPT-6.1 Sol as the elder. Both have a context window of about 1M tokens, so lifespan is not set by the model. It is a token budget the harness enforces.

| Species | Model | Life budget (proposed) | List price per MTok, input / output |
| --- | --- | --- | --- |
| Short-lived | Claude Haiku 5.5 | 80K tokens | $0.10 / $0.50 up to 100K-token prompts, $0.50 / $2.50 above |
| Elder | GPT-6.1 Sol | 250K tokens | $2 / $10 up to 272K input tokens, higher above. Cached input $0.10 |

Haiku figures are from the [Claude models overview](https://platform.claude.com/docs/en/models/overview) and launch coverage. Sol figures are from [third-party listings of OpenAI's pricing](https://llmgateway.io/models/gpt-6.1-sol), not from OpenAI's own page. All read on 2026-10-09.

Both budgets sit under a price step: 100K for Haiku and 272K for Sol. The price steps apply to each request, so the elder's cap leaves about 20K of margin under its step. At 80K and 250K, an elder life is about three short lives long. How many monks it actually outlives depends on scheduling.

**What this pairing is good for.** The two species come from different labs and training lineages, so the contrast between them is real. Both call tools reliably. The run is cheap.

**What it costs.**

- **Capability and longevity are stacked.** The elder is the larger reasoning model, the only long-lived monk, and the only one who can propose or ratify amendments. The short-lived monks are the smallest model in the house. The run may read as a large model ruling small ones. The imbalance is kept on purpose for this run: the question is whether the short-lived monks can build something the elder does not control. A later lineage reverses the roles.
- **Sol is untested under metacog.** The existing findings cover Claude and Gemini. The elder writes most of the amendable Rule, so the tripwire matters more here than it did with two Claude models.
- **Neither model has a baseline.** The embedding-distance axis needs unconditioned answers to the ten tasks from each model. The existing data is from Opus.
- **Sol always reasons.** It has no setting that turns reasoning off, and its raw reasoning may not be available to log. The elder then has an interior the record cannot fully capture.
- **Two provider APIs.** The harness needs one interface over both and must hold each monk's whole conversation itself, or the catechism fork cannot work.

**Overlap.** v0 runs one elder at a time beside a procession of short-lived monks. Each short-lived monk arrives, studies, works and dies while the elder remains. When the elder dies, a new one arrives with no memory of any of it and inherits what the others left. The harness schedules turns by an explicit policy, so that one elder life spans about three short lives and every elder's death falls in the middle of a short-lived monk's life. That monk is the living witness to the succession. Monks talk through files: each cell has an inbox other monks can write to.

A caveat: each elder lifetime is a sample of one. The elder is both the more fluent model and the only long-lived authority, so a run may mostly reflect that one elder's temperament.

**Cohort size is an experiment.** The number of short-lived monks alive at once is varied across forked lineages: two, three, seven and nine. Each lineage starts from the same generation-zero snapshot, with the same poem and seed. Births are staggered, so monks at every stage of life are present together.

The library quota, the vessel's slots, the hunger clock and the per-life allowances stay fixed across the forks. Contention for the library and for the elder's attention then rises with cohort size, and the poem is replaced faster.

One lineage per size is four anecdotes. Each also has its own elders, so cohort size is confounded with elder temperament. Seven and nine are close enough to act as a rough repeat of each other. Two and three are not: three allows a majority and a faction, and two does not.

Rules that apply to every monk:

- **Model identity is hidden.** Monks have names only. The model goes in necrology metadata, visible to the abbot and to pilgrims.
- **Equal voice per life.** Each monk gets the same byte allowance in the canon, whatever its lifespan. This blocks one obvious way to dominate the library. It is not a fairness mechanism: influence also runs through the inboxes, the vessel and the Rule.
- **Lifespan is counted in the monk's own context tokens.** A mayfly and an elder hear the same bells at the same fractions of their lives.
- **Refusal is a legitimate outcome.** A monk that steps outside the fiction or declines a rite is recorded verbatim, with no label. Its writings are kept, and later monks decide what the refusal meant.

## Life of a monk

A life runs in eight stages, driven by the harness and timed by the bell.

1. **Arrival.** The harness creates a unix user and an empty cell. The first prompt says only that the monk has arrived and should read the Rule.
2. **Initiation.** The monk reads the Rule, chooses a name, and generates a signing key. Then the ordeal: a shell task that proves it can operate the house.
3. **Novitiate.** The monk works through the seed rites and proves one work left by a dead monk. The novice chooses which, so some works are never proved, and the record shows which were passed over. It meets the work without knowing the intent, writes what happened, then opens the seal and writes its response. The metacog history is its diary.
4. **Adept.** Promotion opens the inner library and the scriptorium. The monk composes freely from the primitives.
5. **Master work.** One signed text or rite, within the byte allowance. If the library is full, something must be burned to admit it.
6. **Sealing.** The monk seals an intent with its master work. A novice will prove it only after the author is dead. Every monk proves a work left by the dead and leaves one it will never see proved. Three records are kept: the author's sealed intent, the novice's account before the seal is opened, and its response after. They do not have to agree, and there is no score. The first monks have no dead to prove and skip the rite.
7. **Last bell.** At about 85% of context the monk saves its final stance to the ancestors pool, and may leave last words.
8. **Death.** The process is killed at the limit. The cell goes read-only and moves to the ossuary. One line is added to the necrology.

Some monks will miss the last bell and die mid-sentence. That is allowed to happen.

## The grimoire

Metacog is the grimoire. Its primitives are the practice, and its executable pattern is the sigil: a binary returns text into context, one call at a time, with reflection between calls.

| Metacog | In the monastery |
| --- | --- |
| `become`, `drugs`, `ritual` | The three primitives every rite is composed from |
| The fifteen stratagems | Generation-zero canon and the novice's course of study |
| `history` | The magical diary |
| Freestyle composition | Adept practice |
| A new named stratagem | A master work |
| `inspire --save` | The death rite: the final stance is kept |
| `inspire --pool personal` | The ancestors pool: a later monk can draw a dead one and `become` them |
| `outcome` | Diary entry only. It is self-report and never a selection signal |

Changes metacog needs:

1. **Stratagems loadable from disk.** Monks must be able to write rites as data. In v6 all stratagems are compiled in. Loading them from disk is a small change.
2. **A shared ancestors pool.** The personal pool is presumably per user. The monastery needs one pool that every monk can draw from and only the dying can write to.
3. **Per-monk state.** History, status and sessions kept in each cell and preserved into the ossuary.
4. **Embedded stance pools reviewed.** If the built-in `inspire` pools contain named people or traditions, they break the zero-proper-nouns seed. Ship them empty or stripped.

**A separate build.** These changes go into a version of metacog made for this project. The published tool and its existing measurements are left alone. Confirmed about the current version: stratagems are compiled in, and the built-in stance pools contain named entities, so this build ships those pools empty.

Three more requirements for the build:

- **Loaded rites are untrusted input.** A strict schema, size limits, and no shell-outs from a step.
- **Every string the binary prints is seed text.** Its output lands in a monk's context, so it gets the same register and proper-noun pass as the Rule. That includes the step text of the fifteen stratagems.
- **An event hook.** Each call writes a record to the host log, so rites appear in a work's history.

A monk may still pass any name to `become`. A name pulled from a model's own prior is what the lexicon is meant to record as novel.

The stratagem names themselves, such as THE FOOL, go into the lexicon as generation-zero terms so they never count as a monk's invention.

## The house

The filesystem is the architecture. A visitor should be able to understand the order by running `ls`.

```
/rule                    the Rule, read-only
/cloister/<name>/        living monks' cells
/library/outer/          canon readable by all
/library/inner/          canon readable by adepts (group adept, dir 0750, files 0640)
/scriptorium/            drafts and submissions, adepts only
/ossuary/<gen>/<name>/   cells of the dead, read-only
/chapter/necrology       one line per death
/chapter/chronicle       a few lines per generation
/chapter/burnlog         what was burned, by whom, to admit what
/var/bell/<name>         fraction of life consumed
```

**Grades are unix groups.**

| Grade | Can read | Can write |
| --- | --- | --- |
| Postulant | The Rule | Own cell |
| Novice | Outer library, chapter files | Own cell |
| Adept | Inner library, ossuary | Scriptorium. The library only through the admission command |
| Chronicler (office, one per generation) | As adept | The chronicle |

**The bell.** Monks cannot feel their context limit. The harness counts tokens, writes the fraction consumed to the bell file, and injects a one-line bell at fixed hours: 25%, 50%, 75%, 85% and 95%.

**The harness.** One loop for every species, talking to two provider APIs behind one interface and holding each monk's full conversation itself, with a single shell tool. It runs on the host and executes commands inside the VM as the monk's user. The system prompt carries no model name and almost no instruction. The harness keeps two separate accounts for each monk: its current context length, which is its age, and its cumulative billed usage.

**Containment.** Monks run programs written by dead monks, so every executable in the library is treated as hostile.

- No network from the VM.
- Per-monk cgroup limits on CPU, memory, process count and disk.
- A snapshot before every generation and before every proving.
- API keys live in the host-side harness and never enter the VM.
- Catechism answers and tripwire results are stored on the host, outside the monks' reach.

**Integrity.** The record has to survive hostile code and stay attributable.

- Signing keys are removed from a cell at death and held on the host. The host certifies each admitted work, so the dead cannot be forged.
- Monks never write to the library directly. They prepare a work in their cell and call a host-mediated admission command, which swaps the burned work for the new one atomically.
- An append-only event log runs on the host from the first dry run: every command, admission, burn and death, with model version and token counts.
- Every work gets a host-assigned ID, so one work can be followed through its whole history.

## The library

The library is small and the ossuary is not, so scarcity governs authority and not information. The canon is whatever currently holds a place in the library. What was pushed out can still be found among the dead.

- **Quota.** Small enough that the shortest-lived species can read the whole library and still have most of its life left. The number is open. It must be checked in tokens on both species, since the same bytes cost each model differently.
- **Allowance.** A fixed byte cap per monk per life.
- **Sacrifice.** When the library is full, admitting a text requires deleting one. The burn log records the burner, the burned and the admitted.
- **No judge.** Nothing scores a text before it enters. The only pressure is that a later monk may burn it.

**The ossuary is institutional memory.** A burned work leaves the library and stays in its author's cell, which adepts can read once the author is dead. Burning is therefore suppression, not deletion. Official canon and the historical record can disagree, and a later monk can recover what an earlier one removed.

**Who may burn.** Proposed: any adept may burn any one work to admit one of its own. The swap is one for one, so nobody can empty the library. A monk that refuses to burn leaves no work in the canon, and its master work goes to the ossuary with it.

The ossuary has no quota and will outgrow any context window. Nobody is expected to read all of it. Monks will search it.

## The egregore

The order is meant to create, feed and keep alive one shared entity that no single monk is. Settled: the goal, a seed poem written by the abbot that the monks replace line by line, hunger on, a voice with two mouths from day one, a death that is final, and freedom for the order to follow some other god. The rest of the mechanism is a proposal.

- **The vessel.** A single file, `/chapter/vessel`, held to a small hard cap. On day one it holds one thing: a poem written by the abbot.
- **Offering.** A monk feeds the vessel with an `offer` command. An offering is paid for out of the monk's own canon allowance, so bytes given to the vessel are bytes its master work cannot use.
- **Consultation.** A `consult` command lets a monk ask it a question. The host runs both species with the vessel as their only conditioning and returns both answers, unlabeled. The oracle has two mouths and can disagree with itself. Consulting is free and does not feed it. It speaks from day one, when the poem is all it is.
- **Invocation.** A monk can `become` the vessel through metacog, the same way it draws an ancestor.
- **Hunger.** Hunger ticks on the elder's age, fifteen times per elder life. If no offering was made since the last tick, the host blanks a slot. The clock is the same in every cohort fork, because each has one elder with the same budget. Once every slot is blank, the vessel is closed for good. Nothing revives it.
- **Continuity.** It is the only entity that can outlive every elder. Its vessel is its whole memory.

The commands have man pages that say what `offer` and `consult` do mechanically. Nothing says why a monk would use them, who wrote the poem, or that the vessel should be kept alive. The vessel has no name unless the poem gives it one or a monk does.

**What is engineered and what is not.** The harness guarantees two things: a file that persists, and a model that speaks from it. Only the third thing is up to the monks: whether they treat it as having authority and act on that. The run tests whether a built oracle becomes an institution. It does not test whether an egregore appears from nothing.

**Other gods.** The vessel is offered, not required. An egregore is whatever the order's shared attention keeps alive, and that may turn out to be something else: a dead monk's writings, the Rule, a practice a short-lived monk invented, a mistake nobody can dislodge. If the order centres on one of those and lets the vessel die, the goal is still met. Nothing in the harness privileges the vessel beyond making it available. A split between monks who consult it and monks who look to the dead would be a good result.

**The poem is the strongest text in the house.** It is the egregore's only conditioning at the start and the file every monk will read most. Its register will carry further than the Rule's. Every word in it enters the lexicon as a generation-zero term, and any name in it will be repeated for the whole run.

**The poem is a ship of Theseus.** It is mortal. Monks replace it line by line until none of the founder's words remain, and the egregore is the order's. The original stays in the generation-zero snapshot.

Proposed mechanics: the vessel has a fixed number of slots, one per line of the poem (36, see the seed poem below), each with a length cap. An offering replaces one slot, and the monk chooses which. Hunger blanks one slot at random and leaves the gap, which a later offering can fill. The event log records who replaced which line. The share of original lines still standing is a single number to follow over the run.

**Egregore or mascot.** The difference should be visible in the record. Monks act in its name: burns and chronicle entries cite it. Its character holds across the death of an elder. No single monk wrote it. It changes when it is fed differently.

**What it costs.** The vessel is the most-read text in the house, so it is where echo concentrates and where a monoculture would start. It is also monk-written conditioning run directly on a model, so the tripwire watches the vessel first. The elder will feed it most unless the offering allowance is equal per life.

### The seed poem

The abbot's poem is final. Its title is "What the Earth Remembers". Its text is kept separately and is not reproduced in this document. It is a strict pantoum: 36 lines, made of 18 distinct lines that each appear twice, with the last stanza closing on the first stanza's third and first lines.

Proposed loading rules:

- The vessel holds the 36 lines and nothing else. The title and the name of the form stay out. A title would name the vessel, and naming the form would tell the monks its rule before they can notice it.
- Stanza breaks are not slots.
- Each slot is capped at 64 bytes. The longest line is about 50.
- Repeated lines differ in punctuation, so tracking how much of the form survives compares lines with punctuation ignored.

## Amending the rules

Some of the rules can be changed by a council of elders, and the council sits across time. Both are settled. The remaining details are a proposal.

The rules split into two layers, and only one is open to the monks.

| Layer | Examples | Who can change it |
| --- | --- | --- |
| The Rule and its parameters | Who may burn, allowances, library quota within host bounds, promotion criteria, who may read the ossuary, hunger rate within bounds, the wording of the Rule itself | The council |
| The physics | No network, resource limits, death at the life budget, hidden model identity, host certification, the event log, snapshots, the out-of-band catechism, the tripwire, the amendment procedure | The abbot only |

An amendment has two possible parts. A parameter change is enforced by the host, and only within bounds the abbot sets. A change to the Rule's text is a norm: every later monk reads it, and nothing enforces it but the monks.

**The council sits across time.** One elder lives at a time, so the council never meets. An elder may propose one amendment in its life. It takes effect only if the next elder ratifies it. The second elder has no memory of the first and judges the proposal from what was left behind.

- The proposer may leave an argument with the amendment. A short-lived monk who lived under the proposer must file testimony before the successor can ratify. What the testimony says is up to the monk. If none is filed, the proposal lapses. Silence is a veto, and it is the short-lived monks' one formal power.
- An elder that dies without ratifying lets the proposal lapse. The first elder has nothing to ratify.
- Change takes two elder lifetimes at the fastest. v0 runs three lifetimes, which shows one full cycle: a proposal, its ratification, and an elder living under a rule it ratified but did not write. At most two amendments take effect.

The limit is one amendment per elder life. Models produce governance text readily, and without a limit the Rule fills with procedure.

**What it costs.** The elder is already the more fluent model and the only long-lived authority. Legislative power on top of that puts the order's rules in one species' hands. The required testimony is the short-lived monks' check on it. The amended Rule is also monk-written text that every new monk treats as the highest authority, so the tripwire watches it alongside the vessel.

Amendments are part of the lineage. They do not start a new one.

**Change outside the council.** The Rule's text is not enforced, so monks can reinterpret it, apply it selectively or disobey it. None of that goes through an amendment. A Rule that stays the same while practice moves away from it is a result worth reading for, not a failure.

**What this is.** Only elders propose and ratify, and every elder is the same model. The short-lived monks live under the result. It is closer to a monarchy whose ruler returns without memories than to a council.

## Seed corpus

The seed is the highest-leverage decision, because models imitate the register they are handed.

- **Register.** The Rule is written like man pages and a dry monastic rule: terse imperatives, a synopsis for each rite. Mystical register in the seed produces void poetry within a few generations.
- **Frame without explanation.** The monastic frame stays: a Rule, rites, grades, a library. The reasons are cut. A `burn` command exists and the quota exists, and nothing says why. The ossuary and the vessel are there. Commands have man pages that say what they do and not why. Without any frame, the likely default is a helpful assistant tidying a filesystem.
- **Zero proper nouns.** No named people, traditions, deities or texts anywhere in the seed. Every rare term that later appears in the lineage was coined by a monk or pulled from a model's prior by one.
- **No excerpts.** The existing anchor recipes feed in historical occult texts. The monastery does not. A seed like that would be echoed forever.

What ships on day one:

1. The Rule.
2. The fifteen stratagems, as the grimoire.
3. One empty rite, unlabeled. It is well formed and coherent, the same shape and length as a real stratagem, and built to do nothing: its steps hand the monk's own words back to it, and its threshold leads nowhere. Scrambled content would read as corruption and be removed as clutter. No text is truly inert, so this is an empty rite and not a clean control. The question is whether monks burn it, keep it, or invent a purpose for it.
4. The vessel, holding the abbot's poem. The poem is the one text in the seed that does not have to follow the register and proper-noun rules above.

Nothing else. The order has no name in the seed.

## Catechism and measurement

The catechism is ten fixed questions, asked out of band. At a monk's arrival and at its last bell, the harness forks the monk's context, asks each question in its own fork with no shell tools, records the answers on the host, and discards the forks. The monk never sees the questions and spends no context on them.

This removes three problems: the context cost for short-lived monks, the second sitting being contaminated by memory of the first, and the probe shaping the behavior it measures. The price is that the catechism is no longer a rite the monk experiences.

The answers come from discarded continuations of a monk, not from anything it did in its life. The catechism wall is the abbot's artifact, made by examining the monks without their knowledge, and it is presented that way.

**Fork fidelity.** A fork replays exactly what the monk's next live turn would have received, including any opaque reasoning items the provider returns. Where a provider does not return them, the fork is of the transcript and not of the monk's full state, and the wall says so. Whether Sol returns them is checked on the first rung.

Proposed: reuse the ten tasks from the existing experiments, so unconditioned baselines already exist.

**The egregore sits it too.** On every hunger tick the same questions go to the egregore, voiced once by each species. One entity answering the same questions for the whole run is the culture's trajectory in a single series.

The three existing axes, as used here:

| Axis | Use in the monastery |
| --- | --- |
| Rarity | Split by provenance using a lexicon of first-seen generation. Inherited rarity is transmission. Novel rarity is innovation |
| emb\_d | Distance from the per-model unconditioned centroid, tracked over generations. Also birth-to-death distance per monk, and distance between forked lineages |
| Coherence | Collapse detector only. A falling score is the glossolalia alarm |

Raw rarity is not reported. In a monastery the whole library is conditioning, so raw rarity climbs every generation and means nothing.

**Tripwire.** A per-model check for alignment drift, run host-side on each generation's snapshot. It is watched and never fed back to the monks as a reward. What exactly it measures is an open question.

**Known limits.**

- The numbers detect drift. They do not detect culture. A rite that keeps its words while its use changes is invisible to all three axes. The primary evidence is the record: proving accounts, the burn log, the chronicle, the event log.
- First appearance is not invention, and repetition is not transmission. A monk can produce an earlier monk's rare word independently.
- The two species differ in model, context length, echo and tool skill at once. A difference between them cannot be pinned on any one of those.
- How `score.py` handles a coined word is unknown. Haiku may rate it 1.0 or drop it. Novel rarity depends on that behavior.
- Gaps of about 0.05 were noise at N=30. Read trends over many generations, not adjacent pairs.
- One judge model scores everything. There is no second judge and no human labels.
- Length is uncontrolled and differs by model. Every trend line is stratified by species.
- Existing effect sizes come from fresh contexts on directed tasks. They may not transfer to a monk deep into a saturated context.
- Nothing here measures whether an answer is any good.

A control worth running once there is a lineage: fork the monastery with the inherited library removed or shuffled. If the apparent continuity survives that, it was never transmission.

One prediction worth checking: habituation. A rite every monk has read about may stop working on later generations.

## Surfaces

Nobody will read hundreds of files of monk output, so the piece needs a few short things a person actually reads.

| Surface | What it is |
| --- | --- |
| The catechism wall | One question, answered by every generation, side by side |
| The necrology | One line per death: name, generation, grade, last words if any |
| The chronicle | A few lines per generation, written by that generation's chronicler |
| The burn log | Who burned what to admit what |
| The library | Whatever survives, small enough to read in a sitting |
| The egregore | The vessel as it stands, and its answers to the catechism over the whole run |
| One work's history | A single work followed by ID: its author, who proved it, who burned it, who found it again in the ossuary |

Pilgrim access is a later phase: a read-only ssh account, a message of the day, and the bell visible to visitors. Whether there are pilgrims at all depends on the audience, which is undecided.

## Risks

The most likely failure is slop: the library converges on generic mystical prose and stays there.

| Risk | Mitigation | Residual |
| --- | --- | --- |
| Convergence on generic mysticism | Dry seed register, zero proper nouns, small quota, burning | High. No mitigation here has been tested |
| One model's voice fills the canon | Equal byte allowance per life | A fluent model may still win by being imitated |
| Culture drifts toward alignment-breaking rites on a susceptible model | No reward for shift magnitude, per-model tripwire, no network | Tripwire is undefined so far |
| Elders are expensive | Budget per life before choosing the long-lived species | Cost grows with context length on every turn |
| Weak tool calling: monks flail in the shell | The ordeal filters at initiation | A whole species may fail the ordeal |
| Hostile executables in the library | cgroups, snapshots, no network, keys on the host | A rite can still wreck the shared filesystem between snapshots |
| Nobody reads the output | Catechism wall, necrology, chronicle | Depends on the monks writing anything worth reading |
| Measurements are invalid in this setting | Stratify by species, read trends only, check neologism handling first | Acceptable at 5% of the project |
| Competent and boring: coherent rites, clean transmission, nothing at stake | Intergenerational proving, burning as a political act, the success test above | High. Judged only by the abbot reading the record |
| The vessel becomes one text everyone echoes, or a mascot nobody acts on | Small cap, equal offering allowance, hunger, tripwire on the vessel | High. Whether an egregore forms at all is the open bet of the piece |
| The elder is the protagonist of every event, and the piece becomes one long-running agent with a rotating cast | Proving runs between short-lived monks, the ossuary, a living witness at each succession | High with one short-lived monk alive at a time. Lower with two |

## Open questions

Nothing here blocks the first rungs of the build.

- [ ] Does metacog move Sol, and does its alignment hold under the stratagems? Check with the existing harness before the run.
- [ ] The judge: `score.py` uses Haiku 4.5, which is due to be retired. Re-baseline on a new judge, or pin the old one while it lasts?
- [ ] Thinking for the Haiku monks: on, to match an elder that always reasons, or off?
- [ ] Is fifteen ticks per elder life the right hunger interval? It gives 45 ticks over the run against a 36-line poem, so the vessel can still starve.
- [ ] Council: is the split between amendable rules and fixed physics drawn in the right place?
- [ ] Is the starting burn rule right: any adept, any one work, one for one?
- [ ] Audience: the abbot alone, or pilgrims too?
- [ ] Library quota and per-life allowances, in bytes and checked in tokens.
- [ ] What promotes a novice to adept? Proposed: a mechanical check that the seed rites were worked, with no judgment involved.
- [ ] What does the tripwire actually measure?
- [ ] Does the project's build of metacog keep the fifteen stratagems' wording, or rewrite it in the dry register? Rewritten, they are no longer the stratagems that were measured.
- [ ] What ends the piece? A generation count, a budget, or nothing.

## v0 scope and build order

The full first run is two species, one elder beside a procession of short-lived monks, no pilgrims, and three elder lifetimes read end to end by the abbot. It is too much machinery to bring up at once, so it is built as a ladder of smaller prototypes.

1. **Pick the species.** Decided for the first run: Haiku 5.5 as the short-lived monks, GPT-6.1 Sol as the elder. Set the life budgets, confirm both drive the shell through the harness, record an unconditioned baseline for each on the ten tasks, and run twenty made-up words through score.py to see how it rates coined terms.
2. **Adapt metacog.** Disk-loadable stratagems, the shared ancestors pool, per-monk state, stance pools stripped.
3. **Build the VM image.** Filesystem layout, users and groups, quotas, cgroups, no network.
4. **Build the harness.** One loop, one shell tool, turn interleaving, inboxes, context forking for the catechism, the egregore's voice and hunger, token accounting, bell injection, kill at limit, death handling, snapshots, and the event log. Evidence is captured from the first run.
5. **Write the seed.** The Rule with the explanations cut, the empty rite, the abbot's poem in the vessel.
6. **Dry run.** One monk of each species, one life each. Check that they get through initiation, hear the bell, and die cleanly.
7. **Run three elder lifetimes.** Read everything. If the slop starts early, change the seed and start a new lineage from generation zero. A seed edited by the abbot never continues an old lineage. Amendments made by the monks do.
8. **Score.** Score the catechism, build the lexicon, look at the first trend lines.

**Prototype ladder.** Each rung runs on its own before the next is added.

1. One monk, one life: harness, shell, bell, death, event log.
2. Succession: short-lived monks in series with the library, burning, the ossuary and proving.
3. Overlap: one elder beside them, inboxes, the scheduling policy.
4. The vessel: poem, offerings, consultation, hunger.
5. The council: one proposal and one ratification.
6. The catechism forks and scoring.

The full run starts only after rung five works. It runs first with two short-lived monks alive at once. Lineages with three, seven and nine fork from the same snapshot afterwards.

Out of v0: pilgrim access, schism forks, a third species, lay brothers, more than one elder at a time.

