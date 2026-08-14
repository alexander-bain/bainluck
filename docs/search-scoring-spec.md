# Search scoring spec — the tier-lexicographic scorer

**Ruling:** [041](rulings/041-search-ranks-by-match-class-on-owned-evidence.md) ·
**Queue:** Q325 (LAT-P044) · **Code:** `backend/app/utils/search_match_class.py` ·
**Property suite:** `backend/tests/test_search_match_class_properties.py` ·
**Instrument:** `backend/scripts/evals/search_results_producer.py` →
`search_gold_eval.py --mode entity_top_1`

> ## Why this file exists, before anything else
>
> **The ratified spec was delivered untracked and vanished.** It was never
> committed; a bridge write lost it, before the verification rule that would
> have caught that. Its twelve property invariants went with it. The decisions
> below were ratified by Alex MC on **2026-08-11** and are reconstructed here
> from that ratification — they are **not** re-litigated, and no reader should
> re-ask them.
>
> The lesson is the reason this document is in the repo and not in a handoff
> file: **a spec that governs committed code lives with the committed code.**
> This file ships in the same commit as the scorer it specifies.
>
> Everything the reconstruction had to *decide* rather than *recall* is marked
> **[RECONSTRUCTION]** below. Nothing is smoothed over.

---

## 1. The structure

Rank by **match class** first. Knobs tune ordering only *within* a class.

| class | meaning |
|---|---|
| **MC0** | exact full-alias equality, **UNFOLDED** — no stemming, no accent strip, no punctuation strip |
| **MC1** | every query token present in the entity's OWN name (folding allowed from MC1 down) |
| **MC2** | prefix match on the last query token (the user is still typing it) |
| **MC3** | partial token match — some, not all, query tokens present |
| **MC4** | outcome-only evidence: a market matching on its OWN outcomes |
| **MC5** | fragment / fuzzy (trigram) |
| — | **derived-only evidence → UNRANKABLE, excluded entirely** |

**Tier order is inviolable.** No knob setting may lift a lower class above a
higher one. This is property 1 of the suite, and it is what makes the knobs safe
to tune: you can argue about ordering *within* a class without ever reopening
the ordering *between* classes.

### Owned-evidence-only

An entity ranks **only on evidence it owns**: its own name, its own aliases, its
own outcomes. Never on member or derived content.

This is the rule that kills the Emmys black hole. An event concept assembled
from a member market used to inherit that market's match; `super bowl`,
`world series`, `wwe` and `stranger things` therefore all answered
`concept:event:awards:emmys`. The concept matched none of them.

Exclusion, not demotion — and the distinction is load-bearing. A wrong answer
that merely sorts late still wins whenever the right answers happen to be
absent, which is exactly the situation a bad query is in.

**Only derived-only evidence is UNRANKABLE.** A weak-but-owned candidate sinks
to MC5 and stays in the answer. Recall was decided by the SQL that built the
candidate set; a scorer that also filters can empty a result set while reporting
that it ordered one. *(An early draft dropped no-match candidates too. The
property suite's own specimen check caught it — that check exists for this.)*

### Kind order

Ties inside a class break by kind. **RATIFIED: market > event > team.** No
intent classifier:

- `hurricane` → the weather **market**, because a market outranks a team at
  equal class (`Carolina Hurricanes` is an honest MC1 match — "Hurricanes" folds
  to "hurricane" — and no tier can or should separate them).
- `celtics` → the **team**, because the team matches *better*: its alias is
  exactly what was typed, so it is MC0 and the markets are MC1. That is what
  **"team floor"** means — teams sit at the bottom of kind order and win by
  matching better, never by being handed a slot.

**[RECONSTRUCTION]** `concept` and `hub` are not covered by the ratified text.
They are placed **above** market:

```
event_concept(0) · hub(1) · market(2) · event(3) · team(4)
```

The ratified `market > event > team` relation is preserved exactly. The
aggregate placement was **measured, not chosen**: the first draft put a concept
*below* the market it aggregates, which reads plausibly and cost seven gold
probes — `grammys` answered "Grammy Winner: Best New Artist" instead of The
Grammys, `world cup` answered "2030 FIFA World Cup Champion" instead of the 2026
tournament, and `us open` answered a market whose name is **byte-identical** to
the concept it displaced. When an aggregate matches as well as its members, the
aggregate is the page the user asked for. One dict to flip if Alex rules
otherwise.

**[RECONSTRUCTION]** MC0 casefolds. "Unfolded" is read as *no stemming, no
accent stripping, no punctuation stripping* — `São Paulo` and `sao paulo` meet
at MC1, not MC0 — but case is not a semantic distinction and a typeahead query
is typed lowercase by convention. This is the single judgment inside MC0.

## 2. The knobs

Five, against a ratified ceiling of eight. **Every default is provisional until
a measured run.**

| knob | default | governs |
|---|---|---|
| `TRIGRAM_FLOOR` | 0.30 | fragment ordering *within* MC5 (not an admission gate) |
| `MIN_FRAGMENT_LEN` | 3 | below this query length, fragment similarity earns no credit |
| `PREFIX_MIN_LEN` | 2 | minimum last-token length to carry MC2 |
| `PARTIAL_MIN_COVERAGE` | 0.5 | fraction of query tokens MC3 requires |
| `PROMINENT_SPORT_KEYS` | major pro leagues | same-class, same-kind ties (`Boston Bruins` vs `Belmont Bruins`) |

**The acceptance rule for a knob move, ratified:** net flips **≥ 2·√f** on the
test split, at most **two moves per cycle**, **one ranking change in flight at a
time**. A knob is never moved to make a unit test pass — when a synthetic
specimen fell just under `TRIGRAM_FLOOR` during this build, the specimen was
swapped, not the floor.

## 3. Surfaces

**Typeahead is the measured surface.** The scorer wires into the assembly at the
end of `typeahead_search` in `backend/app/routes/events.py`, which previously
merged fixed slots — 1 hub, 1 team, 2 events, 1 concept, 2 markets — with **no
relevance signal anywhere in the merge**. The slot guarantees are removed
deliberately: a guaranteed slot is a promise to show something irrelevant
whenever nothing relevant matched.

`/search` follows the same order. **[P7, ratified]** query-class vocabularies are
scoped per registry.

> **`/search` does NOT yet adopt the scorer — still true as of 2026-08-13, and
> now with a diagnosis attached.** It is scheduled as its own measured change
> (Alex, 2026-08-13: *same scorer, second surface, one change in flight, its own
> before/after*), so it is not a gap to close opportunistically inside another
> queue.
>
> Two things are known about it in advance, both worth having before the design
> step:
>
> 1. **It is a design step, not a copy.** `/search` answers in parallel buckets
>    and asserts no cross-bucket order. Whoever wires it must decide and write
>    down which is being built: the scorer WITHIN each bucket, or a cross-bucket
>    order that changes the bucket contract.
> 2. **It carries the same first-writer-wins concept guard** that produced #1839
>    on typeahead — three call sites, `_detect_query_{golf_major,world_cup,awards}`
>    at `events.py`, each skipping when a member-derived row already claimed the
>    key. The consequence is milder here *only because there is no scorer yet*:
>    the concept still displays, it just fails to lead, which contradicts the
>    call sites' own "prepended so it leads top-1" comments. **Wiring the scorer
>    into `/search` without also routing these through
>    `_upsert_query_derived_concept` would convert a mild ordering miss into
>    #1839's disappearing-concept bug on a second surface.**

Two evidence changes were required to make the ruling operable:

- **Teams now SELECT `alternate_names`.** The recall arms had always *filtered*
  on it; the column never reached the scorer. Without the short name, `Boston
  Red Sox` is only MC1 for `red sox` and loses the kind tie to any market
  mentioning the Red Sox — measured, `red sox` and `yankees` both regressed to a
  player-props market. Withholding the evidence a team would win on turns the
  floor into a ceiling.
- **Concepts carry their provenance.** Concepts built inside the loop over
  ranked futures are marked derived; those built by `_detect_query_*(q)` matched
  the query itself and are not.

## 4. The property suite

**[RECONSTRUCTION]** The ratified spec carried **twelve** property invariants
and their enumeration was lost with the document. The suite rebuilds twelve from
the tier semantics. Five are named verbatim in the reconstruction brief — tier
order is inviolable, owned-evidence exclusion holds for every concept, MC0 is
exactly-equal-unfolded, kind-order breaks ties deterministically, adding
evidence never demotes. The other seven are derived. **They are not claimed to
be the original twelve.**

A thirteenth check, `P0`, guards the suite itself: it asserts every specimen
really is in the class it claims. Without it a drifted specimen makes the
ordering properties pass while comparing the wrong things — and it caught a real
defect on first run.

Nothing in the suite reads the clock (gotcha #44) and nothing is randomised: the
space is small and enumerated, so it cannot flake and cannot depend on a seed.

## 5. The measurement

Same 46 probes, same instrument, every number written down and **attributed to
the change that caused it** (ruling 046).

| deploy | change | `entity_top_1` | MRR | prediction | verdict |
|---|---|---|---|---|---|
| v3792 / v3795 / v3798 | **BEFORE** — measured three times, identical | **30/44** | 0.7572 | — | — |
| — | offline projection, biased low | 35/44 | 0.800 | — | a floor, not a read |
| **v3800** | **`-41` scorer ALONE** (ruling 041) | **32/44** | 0.7391 | **+11±1 → 39–41** | **MISSED by 7** |
| **v3802** | **`-42` pool fix ALONE** (#1836) | **35/44** | **0.8043** | +2 → 34 | **HELD, exceeded** |
| pending | **`-43` concept dedup ALONE** (#1839) | **OWED** | — | +4 → 39 | — |

Coverage 46/46, `fetch_ok` 46/46 throughout. Each deployed read was taken twice
with byte-identical dispositions across all 46 probes.

### How this table must be read — and how it must not

**Recorded by Alex, 2026-08-13, as this ledger's standing text.**

If `-43` lands its projected +4, the program reaches **39/44** — a number that
sits inside the originally ratified 39–41 band. **That is not the prediction
holding, and this ledger must never be read as though it were.**

> The band was a claim about **`-41` alone**, and `-41` missed it by 7. Three
> changes reaching a number that was predicted for one is **not** the prediction
> holding.

The arithmetic that makes this unambiguous: the ratified claim was `+11±1` from
the scorer. The scorer delivered **`+2`**. The remaining movement was bought by a
recall fix and a dedup repair that were not part of the claim — and the dedup
repair exists only because the scorer's own miss exposed the defect.

So the record shows **a missed prediction and a working measurement system**,
and that is worth more than a prediction that appeared to hold. A number
assembled from three changes and compared against a band drawn for one is the
exact confusion ruling 046 was written to prevent; reproducing it here, in the
ledger, would undo the discipline that produced the numbers.

Expected misses that **do not** count against the prediction: `celtics`,
`march-madness`, `422` — data/identity riders on queue 322, which was trimmed to
exactly that scope. (`celtics` remains an undiagnosed pool miss, recorded when
#1836 closed.)

`search_offline_rerank.py` re-ranks captured producer output with the same
scorer and grades it with the unmodified grader. It is a **projection biased
low**, for two structural reasons stated in its own docstring: it can only
reorder candidates the old slot assembly already admitted, and the capture
carries no aliases, outcomes or derived flags — so MC0-by-alias, MC4 and the
owned-evidence exclusion are all invisible to it. Quote it as a floor. Replace
it with the deployed measurement when the branch lands.
