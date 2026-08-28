# RULING 145 — A template family renders as ONE combined card, and the SYSTEM finds the family

date: 2026-08-28
author: Alex, reviewing UX-P151 — relayed through the UX-P154 runner directive, executed by the
program-ux lane
issues: —

**Alex's words, quoted (ruling 144):**

> *"clearly looks better"* — on the combined second-major card — *"BUT: Was this a bespoke
> solution? I thought we'd built tools to identify groups and surface them as groups. Why didn't
> any of them trigger?"*

And the instruction: **GENERALIZE — template-family props render as one combined card BY THE
SYSTEM. FORMATTING pillar: bespoke solutions to systemic shapes are defects.**

**Binds:** every surface that renders a set of curated markets as cards.
**Generalises:** ruling 143 (two rivals asked one question are one card), which established the
SHAPE. This establishes who builds it.
**Does not weaken:** ruling 139 (a near-duplicate rule may never collapse across subjects). A
combine is not a collapse — every subject survives as a row.

---

## Why nothing triggered, answered from the code

The question deserves a mechanism, not an apology. Three parts, each measured:

**1. The tournament props pipeline had one family concept and it was a CAP, not a GROUPER.**
`frontend/lib/tournamentProps.ts::curatedProps` asked `propTemplateFamily` for a key and, on a
repeat, did `dropped.template += 1; continue`. There was no branch anywhere in that file where a
detected family produced a combined card. **The only two things the machinery could emit were TWO
CARDS or ONE CARD AND A DELETION.** UX-P138 got the deletion, UX-P147 rekeyed to stop the deletion
and got the repetition, and neither had a third option to reach for.

**2. That cap had been structurally unreachable since UX-P147.** It keys on the WHOLE register key,
and register keys are unique by construction — the population pass refuses duplicates. So
`dropped.template` could not be non-zero between UX-P147 and UX-P154. The rule everyone was
reasoning about was dead.

**3. The real grouper exists, is good, and was pointed elsewhere.**
`backend/app/utils/prop_families.py::group_prop_families` does exactly what Alex remembers: detects
a family and emits one family with one row per entity. Its only consumer is
`GET /api/teams/{...}/prop-families`; the tournament register pass never calls it. And it would not
have fired anyway — `family_key("Carlos Alcaraz: Grand Slam wins in 2026")` returns `None`, because
its pattern vocabulary was built for league props (Next Team, "... of the year", awards, "<entity>
to <verb> N <unit>", over/unders) and this is a season-total ladder with the subject in front of a
colon.

`market_grouping.py` groups on a different axis entirely — a provider's own event (`group_id`) —
and the two Kalshi series share no provider event.

**So the DETECTOR was blind to the shape and the RENDERER had no combined output.** Both halves
were missing, which is why a human wrote the legs by hand.

## The ruling

**Where two or more curated markets ask one question about different subjects, they render as ONE
card with one row per subject, and the system decides that — not a curator.**

Two layers, and both are required, because either alone leaves the guarantee conditional:

- **`backend/app/utils/prop_template_family.py`** detects families among the MARKETS, so the
  register is written with one composed card. Two markets are the same question about different
  subjects when their titles differ in **one contiguous run of tokens** and they **share at least
  one outcome name**.
- **`combinePropFamilies` in `lib/tournamentProps.ts`** merges same-topic/different-subject cards at
  RENDER, so the guarantee holds for a register the new pass did not write — including every
  register already committed.

## Four properties that come with it

1. **It combines or it renders both. It never deletes.** Where the members' own titles do not share
   enough to name the combined question, the cards render separately — visibly repetitive, which a
   person can see and fix, rather than invisibly halved, which they cannot. That is ruling 139
   satisfied in substance.

2. **The words stay curated; the composition stops being.** The detector never invents a question.
   The register's curation supplies the sentence, keyed on the detected skeleton, and the pass
   **REFUSES a detected family nobody has written a question for** rather than guessing one or
   shipping the repetition. A curated family the detector cannot find also refuses.

3. **Row labels are the SOURCE'S own words.** The subject tokens are printed as the row label with
   the source's own casing — "Carlos Alcaraz", not a curated "Alcaraz". Alex's item 4 in the same
   review: *"the market's own words are USED when they are the market's words."* A curated rename is
   a claim about a number that nothing downstream can check; the source's own subject is a fact.

4. **The test of "by the system" is a third subject.** A hand-written leg list notices nothing when
   the market opens a third player's ladder — the card keeps printing two men beside a question
   about all of them. `test_a_third_subject_joins_the_card_with_no_code_change` is the guard.

## Two bars, and the specimen that set each

**`MIN_SHARED_TOKENS = 2`** — a real family can have a short skeleton ("LeBron James Next Team" /
"Kevin Durant Next Team" share exactly two). One shared token is evidence of English, not of a
template.

**`MAX_SUBJECT_RATIO = 1.0`** — the differing run may be no longer than the shared part. The
specimen, which the first version of this rule got wrong on its first run:

    "Alcaraz to win the US Open in 2026"
    "Sinner to win the Australian Open in 2026"

One contiguous difference, three shared trailing tokens, and **two different tournaments**. The
difference had swallowed the question.

## And the condition the real data refused

The second half started as *"the same SET of outcomes"*, which reads better and is wrong. Measured
2026-08-28 on the two markets Alex's own card is built from:

    KXGRANDSLAM-CALC26  (Alcaraz)   2+ · 3+ · All 4
    KXGRANDSLAM-JSIN26  (Sinner)    1+ · 2+ · 3+

Two rungs each side the other does not have — a threshold ladder's rungs are per-market and they
move. **An identical-set rule would have failed to detect the one family we already know exists**,
which is the strongest possible evidence against it. So the family carries the INTERSECTION as its
`shared_outcomes`, and the comparison the card prints is required to come out of that intersection —
which is what makes "one column, same question, every member" true by construction rather than by
the curator having looked.

## General form

**A systemic shape gets a systemic solution, and a bespoke one is a defect even when it looks
right.** The hand-written card was correct on the day it was written and could not stay correct:
it had no way to notice a third subject, a renamed market, or a second family. The test of whether
a solution is systemic is not whether the output is right today — it is whether the output is still
right after the input changes in the ordinary way inputs change.
