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
| **v3812** | **`-45` `/search` scorer wiring ALONE** — the **ARMED CONTROL** | **38/44** | **0.8696** | **NO movement, with a HALT attached** (ruling 050) | ✅ **HELD — the control fired clean; no HALT** |
| **v3813** | **`-46` evidence echo ALONE** | **38/44** | **0.8696** | none; a test asserts byte-identical ordering | ✅ **HELD — no movement** (LAT-P054) |
| **v3814** | **`-47` #1846 typeahead provenance ALONE** (LAT-P051) | **39/44** | **0.8913** | **+1 → 39** (`us open` only) | ✅ **HELD — exactly, and on the named probe** |

Coverage 46/46, `fetch_ok` 46/46 throughout. Each deployed read was taken twice
with byte-identical dispositions across all 46 probes.

**Cache state, and it is now a structural claim rather than an observation.**
Every read in this table was taken with `debug_evidence=1`, and
`typeahead_search` skips the cache **in both directions** when that flag is set
(`events.py:4021-4034`). So every gold read is **100% cache-MISS by
construction** — not "predominantly misses", which is how LAT-P053 could only
put it. This is also why #1866's miss cost is the cost of every number above.

### The `-45` ARMED CONTROL fired, and it came out clean (LAT-P053, 2026-08-14)

Ruling 050 armed this one in advance: `-45` wires the scorer into `/search`, a
surface `entity_top_1` does **not** grade (the producer reads `/typeahead`), so
it was predicted to move **nothing** — with an explicit HALT on further ranking
merges if it moved anyway.

`-45` merged **alone** into `6d3fba9e` and deployed as **v3812**, exactly as
ruling 046 requires. Read taken twice, ~2.5 min apart, beginning ~15 min after
the release (outside the ~5 min post-deploy artifact window):

| read | `entity_top_1` | MRR | coverage | dispositions differing |
|---|---|---|---|---|
| r1 (18:22 UTC) | **38/44** | 0.8695652 | 46/46 | — |
| r2 (18:25 UTC) | **38/44** | 0.8695652 | 46/46 | **0 of 46 vs r1** |

`regression: 0` on both. Identical to v3806 and v3807 to seven decimal places.

**The prediction HELD. The HALT does not fire, and ranking merges continue.**
Three windows kept this armed rather than skipping it as a foregone conclusion;
what it bought is that the attribution model behind every row above is now
corroborated by a change deliberately chosen to be invisible to it. Under ruling
056's corollary, a clean unarmed control (`-44`) *raised* the value of firing
this one — that reasoning is now paid off rather than merely asserted.

`search-gold-us-open-001` is still `ENTITY_NOT_TOP`, which is the expected state:
its fix is `-47`, which has not deployed.

**CACHE STATE, recorded for the first time** (the new standing requirement from
§8 / #1866): **both reads are cache MISSES.** LAT-P053 could only say
"predominantly", reasoning from the 45s TTL and a 150s gap between reads;
LAT-P054 upgraded that to a **structural** claim by reading the route —
`debug_evidence=1` skips the cache in **both** directions
(`events.py:4021-4034`), so an evidence-bearing read can never be served warm
and never warms anything. Read 2's wall clock was **113s for 46 probes —
2.46s/probe**, which independently corroborates #1866's 1.16–2.29s miss p50 plus
the ~0.24s sandbox connection tax, on a measurement taken for a different reason.

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

**RESOLVED, LAT-P052 (2026-08-14): it was reading 1, and the mechanism is now
measured.** Alex adopted the distinction as this ledger's standing reading law
(**ruling 056**) and required a fix rather than a filing. Both landed; the answer
is more specific than either reading above.

#1843's lift is **conditionally uniform**, and the rival set decides, not the
change. Measured with the real scorer over a frozen production capture — 7 Oscar
markets, 155 outcomes, v3808 —
`backend/tests/test_search_outcome_evidence_discrimination.py`:

* **When every candidate owns the queried outcome below its own display cut**,
  they all move MC5 → MC4 *together*. `entity_top_1` reads relative order only,
  so the lift is **invisible**. Four of five new specimens behave this way, and
  this is why 46 probes produced byte-identical dispositions on v3807.
* **When the lift is unequal, top-1 moves.** `club kid` is the specimen:
  "Oscars 2027: Best Original Screenplay Winner" displays it at outcome rank
  **3 of 17**, inside its cut, so it already scored MC4 and did not move while
  the others did.
* **The substring accident is the shape #1843 named.** Query `fjord`: the Best
  Picture market owns the film at outcome rank 7, while "FH Hafnarfjordur vs.
  Vikingur Reykjavik" merely contains the letters and sits on the MC5 floor.
  Pre-#1843 the accident won on input order; post-#1843 it cannot. Both rows are
  real production data.

So `-44`'s row stays **"no movement"**, and it now carries a mechanism instead of
a shrug: *the change was real, and the 46-probe set could not see it because the
class it lifts, it lifts uniformly.*

### `-46`'s read, and the EXACT-FIDELITY RE-DERIVATION (LAT-P054, 2026-08-14)

`-46` merged alone into `7ffc2911` and deployed as **v3813** at 11:40 PDT. Its
prediction was a **declared null** — the echo is additive and a test asserts
byte-identical default ordering — so ruling 050's HALT was attached to it, and
the read was taken rather than assumed.

| read | `entity_top_1` | MRR | coverage | dispositions differing |
|---|---|---|---|---|
| r1 | **38/44** | 0.8695652173913043 | 46/46 | — |
| r2 | **38/44** | 0.8695652173913043 | 46/46 | **0 of 46 vs r1** |

`regression: 0` on both. **The prediction HELD; the HALT does not fire.**

#### The re-derivation: the harness and the server now agree exactly

This debt was owed for **four windows** and was payable the hour `-46` went
live. The producer's `evidence_fidelity` flipped `legacy` → **`exact`** on the
first capture, 46/46 evidence probes.

**The acceptance was the idempotence property, not a number:** at `exact`
fidelity against a **same-deploy** capture, a rerank must reproduce the
deployed grade. It does, on both captures independently:

| graded object (all v3813, same hour, same 46 probes) | `entity_top_1` | MRR |
|---|---|---|
| production, deployed (capture r1) | **38/44** | 0.8696 |
| production, deployed (capture r2) | **38/44** | 0.8696 |
| harness rerank @ **exact** (r1) | **38/44** | 0.8696 |
| harness rerank @ **exact** (r2) | **38/44** | 0.8696 |
| harness rerank @ **legacy** (same deploy) | **33/44** | 0.7859 |

**0 probes differ** in code, disposition *or* top entity across every pairwise
comparison of the first four rows. The instrument no longer models a different
server.

#### The size of the old instrument's error, measured on ONE deploy

The `−5` was previously known only as a cross-deploy comparison (v3804: 35
deployed vs 30 reranked). LAT-P054 measured both fidelities against the **same**
deploy, an hour apart, and the error reproduces **exactly**:

> **38/44 deployed → 33/44 at legacy fidelity: −5, and the five casualties are
> the same five team probes as the original diagnosis** — `bruins`, `celtics`,
> `patriots`, `red-sox`, `yankees`. Every one `team → market`: `MC0 → MC1` on
> aliases the wire never carried, losing the tie on `KIND_ORDER`.

Nine deploys and a different baseline later (35/44 → 38/44), the defect is the
same size and hits the same five probes. It was never a noisy offset; it was a
structural blindness to exactly one class, and the echo closes it to **zero**.

**A control fell out of this for free.** The `legacy` capture is a *plain*
capture — no `debug_evidence` — and it graded **38/44**, identical to the two
evidence-bearing captures. So the echo does not perturb ranking: the spec's
"the default response is byte-unchanged" claim is now verified end-to-end on the
graded cohort, not just asserted by a unit test.

The fidelity gate also demonstrated it refuses: `--require-fidelity exact`
against the legacy capture **exits 2** rather than producing a number.

### `-47`'s read: the first projection this program has hit EXACTLY (LAT-P054)

`-47` merged **alone** into `92f66962` and deployed as **v3814** at 12:01 PDT —
ruling 046 honoured by the Integrator without being asked. The projection on
record was **+1 → 39/44, `us open` only**.

| read | `entity_top_1` | MRR | coverage | dispositions differing |
|---|---|---|---|---|
| r1 | **39/44** | 0.8913043478260869 | 46/46 | — |
| r2 | **39/44** | 0.8913043478260869 | 46/46 | **0 of 46 vs r1** |

`regression: 0`. Against v3813, **exactly one probe moved**, and it is the named
one:

```
search-gold-us-open-001   ENTITY_NOT_TOP/fail  market:114160
                       →  PASS/pass            concept:event:tennis:2026-women-s-us-open-winner-tennis
```

**+1 predicted, +1 delivered, on the predicted probe.** The prior record was
`-41` missed by 7, `-42` held and exceeded, `-43` missed by 1, `-44` no movement,
`-45` and `-46` declared nulls that held. This is the first row where the
mechanism, the magnitude *and* the specific probe were all called in advance.

Idempotence was re-asserted on this deploy too, so the instrument's agreement is
not a one-deploy accident: rerank @ `exact` = **39/44**, MRR identical to 16
decimals, **0 probes differing** from the deployed grade.

**The standing honesty note, which still applies and is Alex's text:** 39/44 sits
inside the originally ratified **39–41** band — but that band was a claim about
`-41` **alone**, and `-41` missed it by 7. Several changes summing to a number
predicted for one is **not** the prediction holding. What holds here is `-47`'s
own `+1`, nothing wider.

**The stack's read debt is now fully discharged.** Every ranking change from
`-41` to `-47` has a number attributed to its own deploy.

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

---

## 7. What the probe set can and cannot DISCRIMINATE (LAT-P052, ruling 056, #1861)

The 46-probe gold set was assembled for **coverage** of Alex's approved query
set. Nothing has ever asked the separate question — *which classes of ranking
change can it tell apart?* — and the two are not the same property. A set can
cover the query space perfectly and still be blind to a whole tier.

`-44` is what forced the question: a real ranking change, deployed alone under
ruling 046, that moved zero probes. This section is the answer, and it is
maintained rather than one-off — a change class that lands here as "cannot"
is a queue item, not a footnote.

| match class | what a change to it looks like | can `entity_top_1` grade it? | evidence |
|---|---|---|---|
| **MC0** exact alias | a team's alias is withheld or restored | **YES** | `-42` (#1836) moved **+3**; five team probes turn on aliases the response strips |
| **MC1** all tokens in own name | the name pool widens or narrows | **YES** | the majority of the 46 probes resolve here |
| **MC2** last-token prefix | typeahead prefix behaviour | **partially** | no probe is *specifically* a prefix probe; the class is exercised only incidentally |
| **MC3** partial tokens | coverage-threshold tuning | **NO probe isolates it** | untested class — the nearest is `full_question`, which conflates it with scaffolding-strip |
| **MC4** outcome-only | #1843's widening | **ONLY when the lift is unequal** | see below — this is the #1861 finding |
| **MC5** fragment / fuzzy | the trigram floor | **indirectly** | graded only as the thing better classes must beat |
| **UNRANKABLE** derived-only | #1846's provenance fix | **YES** | `us open`; projection **+1 → 39** registered pre-deploy |

### The MC4 rule, stated once so it is not re-derived

> An outcome-evidence change moves `entity_top_1` **only when the candidates do
> not all gain the class together.**

Because `entity_top_1` is a function of *relative* order, and #1843 lifts every
market that owns the queried outcome at the same instant. Three regimes, all
measured against a frozen production capture in
`backend/tests/test_search_outcome_evidence_discrimination.py`:

| regime | pre-#1843 winner | post | graded? |
|---|---|---|---|
| all candidates own the outcome below their cut | the same market | unchanged | **no** — uniform lift |
| a rival displays the outcome inside its top 3 | that rival (already MC4) | **moves** | **yes** — `club kid` |
| the winner never owns the outcome (substring accident) | the accident, on input order | **moves** | **yes** — `fjord` |

### Consequences worth acting on

1. **MC3 is genuinely ungraded.** Nothing in the set isolates partial-token
   coverage, so `PARTIAL_MIN_COVERAGE` could be retuned in either direction and
   every published number would be unchanged. That is the largest remaining
   blind spot. **Filed as #1867** (LAT-P053) — a table cell reading "NO" is a
   spec note, not a queue, which is why the filing was owed.
2. **MC2 is graded only by accident.** Typeahead's defining behaviour — the user
   is still typing — has no dedicated probe. **Also #1867.**
3. **A null read is now interpretable.** Under ruling 056, "no movement" on a
   class marked **NO** or **partially** above is a statement about the
   instrument. On a class marked **YES** it is a statement about the change.
   That distinction is the whole point of keeping this table.

### The class lives in `canary`, deliberately

The outcome-evidence probes are `--split canary`, not `test`. The §5 ledger is
written against a 46-probe cohort graded 44-wide; growing `test` would move the
denominator and silently make every prior read incomparable — a measurement
defect committed while fixing one.
`test_the_canary_split_never_grows_the_ledger_cohort` asserts the separation, so
the ledger cannot be invalidated by a well-meant registry edit.

---

## 8. The recall/latency trade, priced (#1855, LAT-P052, 2026-08-14)

#1855 asked whether **+3 `entity_top_1` was worth ~170ms of warm `/search` p50**
(0.48s → 0.65s), and routed it here for a measured verdict rather than a
recovery. Measured on **v3808 (`d4b7309c`)**, ~1h after release so no post-deploy
artifact (gotcha: a read inside ~5 min of a release scans as a regression).

### First: ~0.24s of every number ever quoted here is the measuring instrument

`GET /api/health` — an endpoint that does no work — costs **p50 0.239s** (n=8)
from an agent sandbox, of which **~0.148s is the TLS handshake**. Every `curl`
opens a fresh connection, so that tax is paid per reading.

On a **reused** connection the same endpoint costs **p50 0.086s** (n=9). The
difference is not the server.

| surface | fresh conn | keep-alive | server work |
|---|---|---|---|
| `/api/health` (floor) | 0.239s | 0.086s | ~0 |
| `/api/events/search?q=chiefs` warm | **0.476s** (n=12) | **0.213s** (n=9) | **~0.127s** |
| `/api/feed` (control, untouched by this program) | 0.368s (n=8) | — | — |

Server-side, from `?debug_timing=1` (n=11): **total p50 163ms**, of which
`teams` **p50 60ms** and `futures` **p50 35ms**.

### The 170ms is the cold/warm boundary, not a code cost

Same deploy, no code change between the two readings:

| `/api/events/search`, novel queries | p50 |
|---|---|
| **cold** (first touch, n=6) | **0.692s** |
| **warm** (second touch, n=5) | **0.468s** |

The gap is **0.224s** — and #1855's claimed regression is **0.17s**. Its two
numbers are a warm read (v3800, 0.48s) compared against reads that were
effectively cold, at n=1–4, over a distribution whose server-side total spans
**105ms to 399ms across eleven consecutive reads of the same query**. A
four-sample median cannot resolve 170ms on that distribution.

Today's warm `/search?q=chiefs` p50 is **0.476s** — the v3800 baseline number.

### The verdict, as two numbers and a recommendation

* **Cost of the recall: ≤ 60ms of server time.** That is the *entire* `teams`
  stage, which is an **upper bound** — there is no pre-`-42` stage measurement to
  subtract, so this deliberately charges the widening for work the stage was
  always doing.
* **Benefit: +3 `entity_top_1`** (`-42`, #1836, v3802: 32 → 35/44).

**Recommendation: keep the recall, and close #1855 as premise-not-supported.**
There is no trade to make. 60ms is 3% of the 2s bar and ~37% of a stage that is
itself 13% of a warm request's wall clock; the 170ms it was weighed against is a
cache-state artifact reproducible today with no code change at all.

### `_search_owned_outcome_names` is not the suspect — stop suspecting it

The queue asked whether #1843's deliberately-unbounded outcome walk is free.
**It is not on `/search` at all.** Its only call site is `typeahead_search`
(`events.py:4400`); `/search` never invokes it. It cannot be any part of #1855.
On typeahead it walks a list already `selectinload`ed into memory — 38 strings
for the largest specimen in §7.

### The finding that is bigger than #1855: typeahead's cache miss

`/api/events/typeahead` is Redis-fronted at `bainluck:typeahead:{q}` with a
**45s TTL**. That changes what every measurement of this surface means — and
typeahead is **the surface `entity_top_1` grades**.

| typeahead | p50 |
|---|---|
| cache **hit** (n=10) | **0.235s** — *at the 0.239s network floor; server ≈ 0* |
| cache **miss**, novel queries (n=6) | **1.158s** |
| cache **miss**, same batch ~25 min later (n=8) | **2.289s**, max **7.67s** |

The code states a **`<150ms p50` budget** for this endpoint. A cache miss is
7–15× that. The second row is not query-specific: re-reading the *first* batch's
queries after their TTL expired moved `packers` 1.072s → 1.797s and `nvidia`
1.126s → 2.164s, and three never-used controls all landed at ~2.1s — so the
surface drifts with load, and it drifts across the **2s investigate bar** in
`CLAUDE.md`.

Two consequences this lane owns:

1. **Every gold-set read this program has taken is a read of a cache-fronted
   surface.** That does not invalidate any ranking number — ordering is cached
   along with the payload — but it means the lane has never once measured
   typeahead's true cost, and `<150ms p50` has never been verified against a
   miss.
2. The `-45`/`-46`/`-47` reads should record cache state, because a 45s TTL and a
   46-probe sequential producer run interact.

**Dispositions, LAT-P053 (2026-08-14).** Alex closed #1855 on the decomposition
above — *accepted trade, ≤60ms server time for +3 recall* — and the closing
comment carries the TLS and cold/warm arithmetic **so nobody re-discovers the
sandbox tax as a regression**. The miss-cost finding is now **#1866, p1**, framed
as Alex required: *no ranking number invalidated, the COST was simply never
measured.* Consequence 2 is promoted from "should" to an acceptance criterion —
every read from LAT-P053 onward **records cache state**.

### #1866 measured: the assembly hypothesis dies, and the drift is MONOTONE (LAT-P054, 2026-08-14)

All numbers below are production **v3813**, taken between ~12:15 and ~13:05 PDT
with no release in the window.

#### Cache state is now a STRUCTURAL claim, not an inference

`debug_evidence=1` skips the cache in **both** directions
(`events.py:4021-4034`), so an evidence-bearing read can never be served warm
and never warms anything. **Every gold read in §5 is 100% cache-MISS by
construction.** LAT-P053 reasoned to "predominantly" from the 45s TTL and a 150s
gap; it did not have to. This also gives #1866 a free instrument: `debug_evidence=1`
is a *repeatable* miss that needs no TTL wrangling to reproduce.

#### Step 2 — per-result assembly is REFUTED as the dominant term

`_search_owned_outcome_names` was cleared for #1855 on the grounds that it is not
on `/search` at all. That is not a conviction *or* an acquittal for `/typeahead`,
where it genuinely does run. So it was measured, with a **discriminating**
experiment rather than a plausible one:

> If per-result assembly drives the miss cost, a query returning **zero**
> suggestions must be cheap — it does zero assembly.

| arm (both guaranteed misses) | p50 | mean | min | max | n |
|---|---|---|---|---|---|
| **zero-result** novel tokens (0 assembly) | **1.778s** | 1.783s | 1.366s | 2.455s | 8 |
| **result-bearing** gold queries | **1.297s** | 1.324s | 1.124s | 1.708s | 8 |

**Zero-result queries are 1.37× SLOWER**, and the zero arm's *minimum* (1.366s)
sits above the result arm's *median* (1.297s) — the distributions barely overlap
in the wrong direction. Assembly is not the cost. **The cost is in the match/scan
phase**, which is where `?debug_timing=1`'s marks are now placed.

#### The miss cost, paired against its own network floor

Pairing miss and hit **on the same query** removes the ~0.26s sandbox connection
tax that §8 opens with, so this is server work rather than a difference of two
population medians:

| | p50 | min | max | n |
|---|---|---|---|---|
| warm **hit** | **0.262s** | 0.258s | 0.269s | 16 |
| cold **miss** (novel) | 1.309s | 1.166s | 13.701s | 16 |
| **paired miss cost** (miss − hit, same query) | **1.049s** | 0.903s | 13.433s | 16 |

**1.049s against a stated `<150ms p50` budget is 7.0×.** The warm-hit arm's
spread is 11ms across 16 calls, which is what a network floor looks like and is
why the paired subtraction is trustworthy.

#### Step 3 — the drift is REAL and LARGE, but its direction is NOT stable

The issue reported 1.16 → 2.29s inside one window and could not say whether that
was noise, query mix, or a trend. LAT-P054 ran an **identical 8-query arm** (same
queries, same flag, round-opening warmup discarded) five times. All five landed
after the **v3814** release at **12:01:33 PDT**, so the series starts on freshly
restarted dynos:

| minutes after the v3814 restart | +1.7 | +3.8 | +8.1 | +12.5 | +17.0 |
|---|---|---|---|---|---|
| **p50** | **1.297s** | **1.808s** | **2.006s** | **2.781s** | **3.098s** |

Within that series: **monotonically increasing, 2.39× end to end**, same deploy,
same queries. Round 4's *minimum* is 2.654s — by then **every** query is over
`CLAUDE.md`'s 2s investigate bar, and the p50 is **20.7×** the stated budget.
Two round-opening warmup calls exceeded **10s**.

**Two confounds were chased. One is cleared; the other kills the tidy story.**

**Cleared — it is not this machine.** The mutation harness and then the full
13,916-test suite were running locally during rounds 2–4, at load average ~12,
so client CPU contention was the obvious alternative explanation. The warm-**hit**
arm is the control that settles it: a hit does ~0 server work, so its wall clock
is network plus local cost. Measured under load average 11.9 it was **p50 0.264s
(min 0.259, max 0.274, n=8)** against a low-load baseline of **p50 0.262s (min
0.258, max 0.269, n=16)** — an inflation factor of **1.01×**. The client is not
the cause.

**Not cleared — the climb did NOT replicate.** `v3815` restarted the dynos again
at 12:20:51, which is a free second trial, and two independent 46-probe captures
across that window trend the *other* way. Per-probe fetch cost, derived from
capture wall clocks (46 probes, 45 × 1.1s of deliberate spacing removed):

| capture | window | per-probe |
|---|---|---|
| v3813 r1 | 11:48–11:51 | 2.10s |
| v3813 r2 | 11:53–11:56 | 1.78s |
| v3813 legacy | 11:56–11:58 | 1.56s |
| v3814 r1 | ~12:27–12:29 (+6 min from restart) | 1.91s |
| v3814 r2 | ~12:31–12:33 (+10.5 min) | 1.71s |

Both series **decline**. So the honest verdict is narrower than the one this
section first drafted:

> **The miss cost is real, is 7–20× its stated budget, and swings between roughly
> 1.3s and 3.1s within a single hour on identical queries. It is NOT established
> that it climbs monotonically, and the accumulating-resource reading is NOT
> supported** — one identical-arm series climbed, two capture series over
> comparable windows fell. The variance itself is the SLO defect; the direction
> is not yet a finding.

**What would settle it:** stage attribution, not more black-box timing. Four
independent black-box series have now produced three different shapes. That is
the signature of a measurement that cannot resolve its own subject, which is
precisely why step 1 was step 1. `?debug_timing=1` is built and **not deployed**;
the next window's first #1866 act is to re-run these arms against per-stage
numbers and name the stage that moves.

**Sequencing owed to ruling 046:** `debug_timing` is production code on the very
endpoint `entity_top_1` grades. `-47` (#1846) still owes its own read on its own
deploy. **`-47` must land, deploy and be read BEFORE `-50` lands**, or `-47`'s
`+1 → 39/44` projection is measured on a server that also changed underneath it.

---

## 9. The miss path, decomposed — and it was never compute (#1866, LAT-P056, 2026-08-14)

§8's tail asked for stage attribution and said four black-box series had produced
three shapes. This section closes that. The answer needed neither `?debug_timing=1`
nor a deploy, because the segment that owns the cost is visible from outside —
and once located, `EXPLAIN ANALYZE` named the mechanism exactly.

Measured against **`da5e7992` / Heroku v3816**, confirmed via `/api/health`.

### 9.1 The segments, on one instrument

`backend/scripts/probe_typeahead_segments.py`. Per query a MISS leg then an
immediate HIT leg, both on fresh connections, so the difference per segment IS
the miss cost with the network floor subtracted rather than estimated. The 45s
cache TTL makes the first touch of a round a miss by construction; a "miss" whose
server segment lands under 150ms is disclosed as pre-warmed and excluded.

**Capture A, 8-query arm × 3 rounds, n=24 usable pairs, 0 pre-warmed, 0 errors:**

| segment | miss p50 | hit p50 | **miss cost p50** | share of miss cost |
|---|---|---|---|---|
| dns | 0.011ms | 0.011ms | 0.000ms | 0.00% |
| connect | 0.165ms | 0.157ms | 0.010ms | 0.00% |
| tls | 157.644ms | 157.934ms | 3.449ms | 0.25% |
| **server** | **1455.496ms** | 86.041ms | **1369.777ms** | **99.74%** |
| transfer | 0.516ms | 0.299ms | 0.078ms | 0.01% |

Total miss cost p50 **1384.6ms** (min 949.8, max 5195.4); miss wall p50 1627.3ms.
Response body 1875 bytes.

**Two things this settles immediately.**

*Serialization is not a suspect.* FastAPI's `JSONResponse` serializes fully
before the first byte, so serialization sits inside `server` — but `transfer`
measures the wire for that same 1875-byte body at **0.5ms**. A 2 KB payload whose
transfer is sub-millisecond is not hiding a large serialization cost.

*The TLS tax is real but is a FLOOR, not the miss cost.* 157.6ms on every fresh
connection — which alone exceeds the `<150ms` budget this endpoint states twice —
yet only **0.25%** of the miss cost. The connection-reuse control priced it
directly: leg 2 down the same connection pays **0ms** TLS, and a warm hit drops
from 251ms to 108ms wall. So connection reuse is worth ~154ms of *floor* and
~3ms of *miss*. It is a real improvement to the wrong number.

### 9.2 Inside `server`: it is I/O, not compute

`EXPLAIN (ANALYZE, BUFFERS)` on production, on the outcome-name arm
(`futures_outcomes.name ILIKE '%q%'` — the 3.2M-row / 3 GB table the route's own
comment flags), same query run twice:

| query | cold | hot | ratio | cold `Shared I/O Read Time` | cold `Shared Read Blocks` | hot read blocks |
|---|---|---|---|---|---|---|
| `red sox` | 1094.5ms | **27.1ms** | 40× | 1067.2ms (97.5%) | 710 | **0** |
| `yankees` | 426.5ms | **5.5ms** | 78× | 380.3ms (89.2%) | 350 | **0** |
| `bruins` | 219.9ms | **5.0ms** | 44× | 173.8ms (79.0%) | 289 | **0** |

Same plan, same index, same rows, every time. The planner was never wrong and the
query was never expensive: **the pg_trgm GIN pages simply were not resident**, and
on every cold run 79–98% of the node's time is `Shared I/O Read Time`.

### 9.3 Why it swings by the hour — and why "accumulating resource" was right to be withdrawn

| object | size |
|---|---|
| `ix_futures_outcomes_name_trgm` | **406 MB** |
| `ix_futures_name_trgm` | **172 MB** |
| `futures_outcomes` / `futures_markets` | 1141 MB / 977 MB |
| **`shared_buffers`** | **1024 MB** |

Those two indexes alone want **56% of the entire buffer pool**, and they compete
with scheduled work that sweeps it: `pg_stat_statements` shows the prediction-market
matcher's `futures_markets` scans at **13–21s mean** over a 977 MB table, running
every 15 minutes.

Residency is therefore a **shared resource under periodic eviction pressure**.
That is not monotone, does not accumulate, and does not survive a restart in any
particular direction — which is exactly why LAT-P054's one climbing series failed
to replicate and why withdrawing the accumulating-resource reading was correct.
The variance was never a leak; it is who last touched the buffer pool.

### 9.4 The three candidate fixes, premise-checked against master before believing

| candidate | verdict | evidence |
|---|---|---|
| single-flight on concurrent identical misses (#1767) | **does not address the named segment** | it dedupes N concurrent identical misses into one query; the surviving one still pays the cold read in full, so p50 miss cost is unchanged. Master already has single-flight in `main.py`, `feed.py`, `hub.py`, `league_futures.py` — the utility is not the blocker, the mechanism is |
| connection reuse | **refuted as the miss-cost fix** | 3.4ms of a 1384.6ms miss cost (0.25%). Worth ~154ms of the warm-hit floor; not this |
| **warm the head of the query distribution** | **taken** | it moves who pays the cold read. And the mechanism upgrades it: page residency is SHARED, so warming the head also speeds tail queries that touch the same index pages — a bigger effect than the 45s response cache it superficially resembles |

The head is **measured, not guessed** — `search_query_logs`, 30 days, 2026-08-14:
3,423 rows / 210 distinct, **top-20 = 36.0% of volume, top-50 = 68.7%**. The live
`/typeahead` distribution is better still and already exists: the route writes
`search:trending:24h` on every call, so the warmer reads that first and falls back
to the log, then to a five-entry static floor. Which source produced the head
travels in the run summary, because it changes what the run means.

### 9.5 The fix, and what is deliberately NOT claimed

`app/tasks/typeahead_warmer.py`, beat `warm-typeahead` every 2 min, background
queue. It calls **the route function itself** — one implementation, no second
copy to drift — so the route's own `setex` does the writing and **no ranking code
is touched**.

The cadence deliberately does not chase the 45s response TTL: with pages resident
a genuine miss measured 5–27ms in the arm above, so residency is the thing worth
holding, and a sub-45s cadence would buy a little hit-rate for a lot more load
against the segment that is not the problem.

**Not load-bearing.** A cold miss still builds inline in the route, so turning the
task off makes `/typeahead` slow again — never broken.

**The trap it is written against.** `debug_evidence` and `debug_timing` default to
`Query(False)`, a marker object that is **truthy**. A caller that omits them makes
the route skip its cache write, so the warmer would run every query, warm nothing,
and report success — indistinguishable from a healthy run (gotcha #53). The flags
are passed as literal `False`, two separate mutants cover the conjunction, and
`scripts/evals/typeahead_warmer_mutations.py` scores **6/6 killed**.

### 9.6 Pre-registered read (ruling 050) — declared BEFORE the deploy

`-51` ships no ranking code, so the no-regression control and the target are
independent claims and are graded separately.

* **Target — the floor:** `server` miss-cost p50 **< 600ms**, down from
  **1369.777ms**. Stretch: budget-adjacent (<150ms).
* **Prediction pinned to the named segment:** the movement appears in `server`
  and **only** in `server`. `tls` stays ~157ms, `connect`/`dns`/`transfer` stay
  sub-millisecond. A fix that moved `tls` would mean something other than this
  change moved.
* **No-regression control:** gold set **39/44, MRR 0.8913043478260869, 0
  regressions, 46/46 measured, fidelity `exact`** — measured on `da5e7992` in the
  same window. **0 of 46 dispositions may differ.**
* **HALT:** if `server` miss-cost p50 does not fall, or any of the 46 dispositions
  change, HALT further ranking merges until explained.
* **Method:** same instrument, `probe_typeahead_segments.py`, same 8-query arm,
  same hour-class, read twice.
