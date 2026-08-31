# DESIGN — a Polymarket game container is not a question, and the curve is scoring it as one

**Status: DESIGN ONLY. Nothing is built here and nothing in this file changes a
published row.** Written by the calibration lane (CAL-P155, #1978) because the
calibration lane is where the damage was measured. **The fix is an INGESTION
ship and it belongs to an ingestion queue with its own ship line** — ruling 134
and THE RIDER RULE both point the same way, and CAL-P151 said so when it found
the class.

**Pillar: TRUTH.** Ship, when it is built: *the accuracy page stops scoring a
Polymarket table-of-contents as though it were a prediction.*

🔴 **THIS IS OUR BUG.** It is an ingestion defect in `app/tasks/polymarket.py`.
The venue prices these questions fine — the toss market reads 0.4997 and three of
the four cricket families land within half a point (CAL-P151 §3). Nothing in this
document says or implies otherwise, and no "bad at cricket" label may be derived
from it.

---

## 1. The specimen, read rather than inferred

CAL-P151 found the shape and named the cause as *gotcha #18 unapplied*. It could
not say WHICH ingestion branch produced it, and said so. That read is now done —
one row, `futures_markets` 129934, 2026-08-31:

| column | value | what it means |
|---|---|---|
| `external_id` | `208556` | the numeric **Gamma EVENT id** — this is a PARENT row |
| `group_id` | `polymarket:208556` | matches, so `group_id = 'polymarket:' \|\| external_id` identifies the class |
| `group_type` | **NULL** | not `polymarket_event`; predates the stamping at `polymarket.py:824-830` |
| `market_metadata->>'neg_risk'` | **NULL** | predates the metadata write at `polymarket.py:833-841` |
| `mutually_exclusive` | **false** | so `event.neg_risk` was false: a GAME container |
| `market_type` | **`field`** | 🔴 classified as a single-winner partition |
| `shape.outcome_relation` | `unknown` | `shape.exhaustive` / `expected_winners` both NULL |
| sibling rows under that `group_id` | **1 — itself** | 🔴 **zero sub-markets were ever minted** |

The three outcomes named `…`, `… - Completed match`, `… - Who wins the toss` are
the three sibling QUESTIONS of that Gamma event, and they exist **nowhere else in
the database**. The container is not a duplicate view of decomposed rows; it is
the only representation there is.

## 2. The mechanism, end to end

1. **The parent's outcomes are its children's names.** `polymarket.py:1302-1331`
   — the loop commented *"Also keep parent market outcomes (for the moneyline
   matching task)"* — writes one outcome per sibling sub-market onto the parent,
   `external_id = market.condition_id`, `name = market.group_item_title or
   _extract_outcome_name(market.question, event.title)`. That name helper falls
   through to `question.rstrip("?")[:60]` (`polymarket.py:1956-1962`), which is
   the 60-character truncation the CAL-P123 specimen shows.
2. **Each child settles on its own, onto the parent's row.**
   `polymarket.py:2166-2202` writes `is_winner` by
   `external_id = ANY(:cids)` over the **bare** `condition_id`. The parent's
   outcomes are keyed on exactly that. So three sibling questions each resolving
   YES stamp **three winners on one market** — not a grading error, a direct
   consequence of two writers agreeing on a key.
3. **Nothing downstream can see it.** `mutually_exclusive` is set to
   `event.neg_risk` (`polymarket.py:909`), so for a game container it is FALSE,
   and every rung that could object is gated on it:
   * `malformed_binaries` — needs `mutually_exclusive = true AND n_outcomes = 2`.
     Blind: three outcomes, not exclusive.
   * `winner_field_coherence.field_is_incoherent` / `winners_are_incoherent` —
     both `return False` immediately when not mutually exclusive
     (`winner_field_coherence.py:53-54, 61-63`), and `INCOHERENT_FIELD_HAVING_SQL`
     is gated on `fm.mutually_exclusive` (70-73).
   * `no_winner_markets` — fires on `win_count = 0`. This is `win_count = 3`.
   * `mex_field_candidates` — needs `shape_exhaustive='true'` and
     `shape_expected_winners='1'`; both NULL here, so it is correctly not
     admitted, and that is the one rung the row does not fool.

   **There is no rung anywhere that asks "a non-exclusive market recorded more
   winners than it can have".** That is the hole, and it is why 68.6% of
   published cricket match-winner markets carry `win_count != 1` (CAL-P151 §4)
   while every guard reads green.
4. **A second, independent leak in the same loop.** The sub-market branch gates
   each child on `_resolve_market_probability_with_source` returning a price
   (`polymarket.py:974-978`: placeholder filter + the #151 evidence gate). The
   parent-outcome loop at 1303 applies **neither**, taking Gamma's precomputed
   `outcome_prices[0]` raw. So a child can be refused a market row of its own and
   still contribute an outcome to the parent. Even where decomposition DOES run,
   it can leave an outcome named after a market that does not exist.

## 3. What the fix has to be, and what it must not be

**Not a read-side calibration exclusion.** The curve could exclude these rows
tomorrow and the database would still hold three questions crammed into one
market, invisible to matching, to the event page, and to search. Excluding them
buys a number and ships nothing. (It is also the trap CLAUDE.md's opening section
is about.)

**Not a widening of `mutually_exclusive`.** A game container is genuinely not
mutually exclusive. Setting it true to wake the coherence rules would make the
guard fire for the wrong reason and would mis-describe every other container.

**The fix is to stop the container from being a market with outcomes.** Three
parts, in dependency order:

* **F1 — DECOMPOSE THE BACKLOG (the ship).** For every resolved Polymarket parent
  with no `polymarket_sub_market` sibling, mint the sub-markets its outcomes are
  already named after, keyed by `condition_id`, and move the grade to them.
  `backend/scripts/backfill_polymarket_submarkets.py:73-92` is the existing
  decomposer and its selection SQL is 90% of this — ⚠️ **it is scoped to
  `status='open'`, so the settled population this class lives in is entirely
  outside it.** Widening that scope is the smallest real change, and it is a
  WRITE to resolved rows, so it needs the resolution-authority ladder
  (`project_resolution_authority_ladder`) and gotcha #21 read on it before a line
  is written.
* **F2 — LABEL THE CONTAINER AT CAPTURE, so F1 never has a backlog again.**
  `group_type` is NULL on this row; current code stamps it. Whatever F2 lands on
  must be a POSITIVE label (a container says it is a container) rather than an
  inference from `win_count`, because inferring is what every blind rung above
  already tries to do.
* **F3 — CLOSE THE UNGATED PARENT LOOP.** `polymarket.py:1303` must apply the
  same placeholder and #151 evidence gates as `974-978`, or say in the code why
  it deliberately does not. Today the asymmetry is silent.

**F1 is the ship. F2 and F3 are the substrate and they ride it** — neither is
queueable on its own account (THE RIDER RULE).

## 4. The guard that is missing, and it is the cheap half

There is **no test anywhere** asserting that a non-negRisk multi-market event
produces N sub-market rows, or that a parent's outcomes are not sibling-market
names. The three tests that look like they cover this do not:
`test_polymarket_submarket_event_id.py` unit-tests `sub_market_metadata()` only;
`test_polymarket.py:915-937` are `inspect.getsource` substring assertions (the
vacuous-guard class this program has now caught four times, most recently in
CAL-P155's own suite); `test_polymarket.py:544-579` covers PARSING, not the write
branch.

Whoever takes F1 should write the behavioural guard first and watch it go red.

## 5. The census this needs, and why it is not in this file

**Sizing F1 needs one measurement and it belongs to the measurement lane**
(ruling 134; a build lane's only permitted measurement is its own gates). It is
staged, not dropped. The statement:

```sql
SELECT fm.mutually_exclusive, fm.market_type, (fm.group_type IS NULL) AS gt_null,
       COUNT(*) AS parents,
       COUNT(*) FILTER (WHERE sub.n > 0) AS with_submarkets
FROM futures_markets fm
LEFT JOIN LATERAL (
  SELECT COUNT(*) AS n FROM futures_markets s
  WHERE s.group_id = fm.group_id AND s.group_type = 'polymarket_sub_market'
) sub ON true
WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
  AND fm.group_id = 'polymarket:' || fm.external_id
  AND fm.id >= :lo AND fm.id < :hi          -- ⚠️ REQUIRED, see below
GROUP BY 1, 2, 3
```

⚠️ **Two rail facts measured this session, so the next reader does not pay for
them again.** Scoping by `llm_sport_category = 'cricket'` **times out** — every
index mentioning that column is PARTIAL on `status='open'` and the calibration
population is `status='resolved'` (CAL-P151 §5.2, re-confirmed here, correlation
`bc416d1ee39b`). And a modulus shard on a grouping key is **not** sargable on
this database, so it scans the whole table anyway. What works is the **primary
key**: `fm.id` windows drive `futures_markets_pkey` and return in ~1 s. Walk the
id space in windows and sum client-side; halve any window the rail refuses.

The number that decides F1's shape is `parents` where `with_submarkets = 0`, and
its split by `market_type` — a container classified `field` is the one that walks
past the most rungs.

## 6. Open questions a builder must answer, not assume

1. **Who consumes the parent's outcomes?** The loop's own comment says "for the
   moneyline matching task". F1 removes or re-homes those rows, so that consumer
   has to be found and read before anything is deleted. Deleting them blind
   trades a calibration defect for a matching one.
2. **How many containers are `group_type IS NULL`?** The specimen predates the
   stamping. If most of the backlog is unstamped, F2's positive label does not
   identify the historical rows and F1's selection must key on the structural
   fact (`group_id = 'polymarket:' || external_id`) instead.
3. **Is `market_type = 'field'` on a container written by ingest or by
   `backfill_market_shapes`?** It decides whether F2 is one writer or two.
4. **Does re-grading a resolved container's outcomes need a ruling?** Moving a
   grade from a container row to a new sub-market row is a write to settled data.
   `resolution_source` is the discriminator and the authority ladder is the rule.

## 7. What CAL-P155 did NOT do here

* Did not build any of F1/F2/F3, and did not touch `app/tasks/polymarket.py`.
* Did not run the census in §5 — it is the measurement lane's, and it is staged.
* Did not exclude anything from the calibration population on account of this.
  The freeze-lift batch is the only calibration population change in flight.
* Did not re-derive CAL-P151's cricket fold. It is done and it must not be re-run.
