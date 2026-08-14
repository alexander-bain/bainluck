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

### `/search` adopts the scorer WITHIN each bucket (LAT-P049, 2026-08-13)

The design step is decided, and this is the record of the decision the previous
revision of this section demanded be written down rather than inferred from a
diff.

**`/search` uses the scorer as an ordering function INSIDE each bucket. It does
not impose a cross-bucket order.** The response contract is unchanged — same
keys, same caps, same sections — so no consumer migrates and no frontend change
is implied.

| bucket | wired | why |
|---|---|---|
| `event_concepts` | **yes** | unpaginated, caps at 5, and the surface where ruling 041's owned-evidence rule has teeth |
| `teams` | **yes** | unpaginated, caps at 5, and where the fragment-win family lives (`brito` for `british open`) |
| `results` | no | game events, ordered live → upcoming → completed. That order is a ruled product decision, not an unranked accident — and it is paginated |
| `futures`, `futures_families` | no | paginated. Reordering page *N* by relevance is coherent within the page and incoherent across pages, which is worse than the honest FTS order it replaces. Ranking a paginated bucket means ranking it in the SQL: different change, different risk |

A cross-bucket order was considered and rejected on the contract, not on taste:
`results` and `futures` are paginated, so a single merged ranking cannot be
computed from one page of each without lying about what page 2 contains.

Two evidence corrections travelled with the wiring, both of them the same
mistake this spec already records once:

- **`/search` now SELECTs `Team.alternate_names`.** It had always *filtered* on
  the column and never handed it to whatever ranked the rows — the identical
  floor-into-a-ceiling error typeahead had.
- **Concept provenance is computed per row, via `_query_names_concept`**, not
  set blanket-true the way typeahead sets it.

> ⚠️ **The two surfaces disagreed about provenance for exactly one cycle,
> deliberately, and the divergence is now CLOSED (#1846, LAT-P051).** Typeahead
> flagged every market-derived concept `_derived` unconditionally, which drops a
> concept whose OWN NAME IS THE QUERY — #1839's shape surviving in the general
> case after #1839's three named families were fixed.
>
> It was **filed as #1846, not fixed by LAT-P049**, because repairing it is a
> ranking change on the MEASURED surface and two ranking changes (`-43`, `-44`)
> were in flight with their reads untaken, which ruling 046 forbids compounding.
> `/search` took the correct rule immediately because it is unmeasured and the
> correct rule was what the wiring needed. Both reads have since been taken
> (v3806 → 38/44; v3807 → 38/44, no movement), so typeahead got the rule as its
> own single-change deploy with its own before/after — see §5.
>
> **What the blanket flag cost, measured rather than argued.** On the v3807 read
> the gold probe `us open` expects
> `concept:event:tennis:2026-women-s-us-open-winner-tennis`. Production minted
> that exact concept from its winner-field market, flagged it derived, dropped it,
> and answered with `market:114160` — the market whose name is byte-identical to
> the concept it had just deleted. That probe was also the +1 missing from `-43`'s
> projection, miscounted at the time as a #1839 casualty: it has no tennis
> resolver and therefore never had a query-derived twin for #1839's guard to
> upgrade (Alex ruling 2, 2026-08-13, which routed it here).
>
> **One rule, one implementation, two shapes.** `_query_names_concept_row` takes
> `key`/`name` as arguments; `_query_names_concept` (`/search`) and
> `_query_names_typeahead_concept` (`/typeahead`) are thin wrappers over it. The
> alternative — one rule living in two consumers — is gotcha #129, and #1846 is
> that gotcha's bill: the rule was correct on the surface someone had just read
> and wrong on the surface being graded.
>
> **A fragility this fix introduces, recorded rather than discovered later.** On
> `the open championship winner` the golf major and the now-rankable tennis
> `US Open` concepts produce an EXACT `rank_key` tie (same class, same kind, same
> absent prominence). The tennis rows previously lost that probe by being dropped,
> not by being ranked below. `rank()` is a stable sort, so rank 1 is now decided
> solely by `_upsert_query_derived_concept` inserting the golf major at the front.
> `TestGolfPrependProtectsTheTie` asserts both halves, including the
> counterfactual where the prepend is removed and the probe flips.

**AC#1 — the guard went with the scorer.** `/search` carried the same
first-writer-wins concept guard that produced #1839: `_detect_query_{golf_major,
world_cup,awards}` plus a **fourth** site, the `#206` team-bridge insertion, each
a bare `if key not in seen` skip sitting under a comment claiming the concept is
"prepended so it leads top-1". All four now route through
`_upsert_search_query_derived_concept`, which shares its six-line core with the
typeahead wrapper (`_upsert_query_derived_concept_row`) so the two surfaces
cannot drift into two verdicts of one rule.

The fourth site needed it most: on `france` the query does not name the concept
(`FIFA World Cup`), so that row owns no evidence against the query and would
score UNRANKABLE — **dropped, not demoted** — if left flagged derived. Its
rankability comes from being query-gated, and the upsert is how a row records
that.

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
| — | offline projection | 35/44 | 0.800 | — | **NOT a floor — see §6**; an estimate that can err in both directions |
| **v3800** | **`-41` scorer ALONE** (ruling 041) | **32/44** | 0.7391 | **+11±1 → 39–41** | **MISSED by 7** |
| **v3802** | **`-42` pool fix ALONE** (#1836) | **35/44** | **0.8043** | +2 → 34 | **HELD, exceeded** |
| v3804 / v3805 | no latency change (re-measured twice) | 35/44 | 0.8043 | — | corroborates the stack was unlanded |
| **v3806** | **`-43` concept dedup ALONE** (#1839) | **38/44** | **0.8696** | +4 → 39 | **MISSED by 1** |
| **v3807** | **`-44` outcome evidence** (#1843) | **38/44** | **0.8696** | none registered | **no movement** — see below |
| pending | **`-46` evidence echo** | — | — | none; a test asserts byte-identical ordering | owed |
| pending | **#1846 typeahead provenance** (LAT-P051) | — | — | **+1 → 39** (`us open` only) | owed |

Coverage 46/46, `fetch_ok` 46/46 throughout. Each deployed read was taken twice
with byte-identical dispositions across all 46 probes.

**`-43`'s missing +1 was a diagnosis error, not noise.** `grammys`, `oscars` and
`world cup` recovered exactly as projected; `us open` did not, and it had been
**miscounted** into #1839's casualty list. Its gold answer is a *tennis* concept,
there is no tennis resolver among the four `_detect_query_*` sites, so it never
had a query-derived twin for #1839's guard to upgrade. Alex routed it to #1846 as
a named sub-case (ruling 2, 2026-08-13); the LAT-P051 row above is that fix.

**`-44` is the first change this program shipped that moved nothing, and it is
recorded as a result rather than omitted.** It carried a real ranking change
(#1843: the scorer had been seeing only the 3 *display* outcomes, so a market
matching on a truncated-away outcome scored MC5 instead of MC4) and the 46 probes
produced **zero disposition differences** against v3806. Two readings are
available and they are not equivalent:

1. no gold probe exercises the truncated-outcome path, in which case the fix is
   real and the instrument is blind to it; or
2. the fix's effect is smaller than the probe set can resolve.

Either way the honest statement is **"unmeasured", not "ineffective"** — and it
is a coverage gap in the gold set, filed as such rather than settled here. It
also functioned as an **unarmed control** that came out clean, which is
corroboration for the attribution model the `-45` armed control (ruling 050) will
test deliberately.

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

## 6. The instrument — and why it is NOT a floor (LAT-P050, 2026-08-13)

Everything above was measured with `search_offline_rerank.py`, and the sentence
that used to close this document said it was a **projection biased low** — "quote
it as a floor". That was wrong, it was load-bearing, and it is the best available
explanation for how a `+11±1 → 39–41` band came to be ratified against an actual
**32/44**.

### The measurement that settles it

Production v3804, the same 46 probes, the same grader, the same day:

| what was graded | `entity_top_1` | MRR |
|---|---|---|
| **production, deployed** | **35/44** | 0.8043 |
| the harness re-ranking **production's own output** | **30/44** | 0.7207 |

Re-ranking a capture of the scorer's own output, with the same scorer, should be
approximately **idempotent**. Instead it destroyed five passes — `bruins`,
`celtics`, `patriots`, `red-sox`, `yankees`. Every one a **team**, and every one
for the same reason:

> `typeahead_search` ranks a team on its aliases (`alternate_names` +
> `abbreviation`) and then **strips them before responding**, because evidence is
> not payload. The harness re-ranked the response. So it re-ranked every team
> with its aliases withheld: **MC0 → MC1**, tie with a market, lost on
> `KIND_ORDER` (team 4, market 2).

The instrument committed the **withheld-evidence** defect — the same class the
route has now been repaired for three times (#1836, #1839, #1843) — against the
very fixes it was grading. An instrument cannot be trusted to measure a bug class
it contains.

### The bias is two-sided. Both directions, named.

* **Understates** — it can only reorder candidates the deployed assembly already
  admitted, so a correct answer that never reached the response is invisible and
  stays a failure in the projection. (Measured above: −5.)
* **Overstates** — it scores a **7-candidate** field where production scores the
  whole pool. Winning a seven-way contest is not winning a three-hundred-way one.
  (Consistent with the historical +7 overstatement; not separately measured.)

A quantity that can err in both directions is not a floor. It is an estimate, and
it must be quoted as one.

### What the fix actually required

Better field-mapping is **not** sufficient, and this was measured rather than
assumed. Re-capturing with adapter v2 — which preserves the wire suggestion
verbatim and rebuilds evidence through the endpoint's own `_typeahead_evidence` —
still scored **30/44**, the same five team probes. The deciding evidence
(`alternate_names`) is simply **not on the wire**, and no amount of care on the
harness side can reconstruct what the response does not contain.

So the endpoint now **echoes the evidence it ranked on**, behind
`GET /api/events/typeahead?debug_evidence=1`:

* the echo is taken from the same `Evidence` objects the scorer consumed, keyed
  by payload identity, and is built **after** the private-key strip so that a
  rebuild-from-suggestion cannot reproduce it — the provenance is structural, not
  a matter of care;
* it is **never cached in either direction** — a debug answer must not be served
  from a normal entry (it would arrive without the echo and be captured as low
  fidelity) and must never be written to one (a user typing that prefix would be
  served the eval payload for the full 45 s TTL);
* the default response is **byte-unchanged**: no new key, no ordering change.

One wire form, `evidence_to_wire`/`evidence_from_wire`, lives in the module that
owns `Evidence`. Both consumers import it, and a field added to `Evidence`
without a wire decision fails a test rather than silently not crossing.

### Fidelity is a property of the capture, and must be read

`metadata.evidence_fidelity` is `exact`, `partial` or `legacy`, and
`--require-fidelity exact` refuses in any pipeline whose number will be quoted.
An unlabelled capture resolves to `legacy`, never to the flattering reading. A
`legacy` run is a different experiment wearing the same filename.

### The armed control

`tests/test_offline_rerank_fidelity.py` asserts the idempotence property
directly: at `exact` fidelity, re-ranking the scorer's own output returns the
same order. That test is the instrument's own control, and it is the check that
would have caught this before a band was published.

**Still owed, and not claimable until the echo deploys:** the re-derived floor at
`exact` fidelity against production. Until then every projection in §5 stands as
recorded, with the two-sided caveat above attached to it — the old numbers are
not retracted, because they were honestly taken; only the claim that they were
floors is withdrawn.
