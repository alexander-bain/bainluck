# LAT-P097 — the code-only lever for the typeahead name arm, tested and REJECTED

**Cycle:** LAT-P097 · **Date:** 2026-08-26 (PT) / 2026-08-27 (UTC)
**Production state while measuring:** `baae52c2` = Heroku **v3907**, released 17:14:27 PDT,
warm at read time. Everything below is a measurement against that slug, never a projection.

⚠️ **Lane collision, declared first because it bounds what this file may claim.** A sibling
session on this same lane committed `2d3e1d83` (LAT-P097 deploy proofs + done bar) at 17:37 PDT
while this work was in flight, and was still writing the shared worktree afterwards. **This file
covers only the half that commit does not: the name-arm lever.** The deploy-proof and done-bar
numbers are theirs and are not restated here.

---

## What was tested, and why it was tested rather than asserted

LAT-P096 ended with "the fix is an FTS expression index — DDL, not code", and left a
`CREATE INDEX CONCURRENTLY` awaiting Alex's attended batch. That is a *conclusion*, and it was
load-bearing enough to be worth attacking: if a code-only lever existed, the ship would not be
waiting on a hand-run DDL at all.

**The candidate.** Delete the FTS half of the futures NAME arm and replace it with a second
ILIKE over the query term's **Postgres stem**, computed in SQL rather than in Python:

```sql
name ILIKE '%champions%' OR name ILIKE '%' || btrim(strip(to_tsvector('english','champions'))::text, '''') || '%'
```

Computing the stem in SQL is the whole trick. It needs no new dependency, and — more importantly
— the stemmer is *the same one the FTS half used*, so recall equivalence would be exact by
construction rather than approximate. A Python Snowball port would only be equivalent until the
two implementations diverged, silently.

## It is fast, and the index does the work

`ix_futures_name_trgm` already exists and already serves substring matching. The open question
was whether the planner can use it when the LIKE pattern is a runtime expression rather than a
literal. **It can** — the two plans are identical, node for node:

```
computed stem (expression pattern)     literal stem
Aggregate cost=1948.29                 Aggregate cost=1948.29
  Bitmap Heap Scan cost=1948.28          Bitmap Heap Scan cost=1948.28
    BitmapOr cost=1619.61                  BitmapOr cost=1619.61
      Bitmap Index Scan ix_futures_name_trgm    Bitmap Index Scan ix_futures_name_trgm
      Bitmap Index Scan ix_futures_name_trgm    Bitmap Index Scan ix_futures_name_trgm
```

Three interleaved rounds, `EXPLAIN (ANALYZE)` on production, open markets only. Interleaved and
reported as a ratio for the reason `gate_futures_name_fts_index.py` already established: this
predicate's cost is per-row `to_tsvector` CPU and the host's contention moves it several fold
within minutes.

| shape | p50 ms | min | max | buffers p50 |
|---|---:|---:|---:|---:|
| `werder` OLD — `ILIKE OR FTS` | 3,423.7 | 2,385.8 | 6,564.3 | 26,106 |
| `werder` NEW — ILIKE only | **24.8** | 14.8 | 103.7 | **632** |
| `champions` OLD — `ILIKE OR FTS` | 6,293.9 | 2,398.3 | 6,522.9 | 26,106 |
| `champions` NEW — `ILIKE OR stem-ILIKE` | **259.0** | 227.1 | 401.1 | **4,315** |
| control — FTS over `external_id` (unindexed, not touched by any lever) | 1,852.6 | 593.9 | 2,100.7 | 26,106 |

**24.3× on `champions`, 137.8× on `werder`.** The control moved 594 → 2,101 ms across the same
three rounds, which is the host getting busier under all six shapes at once — it is why the
ratios are the finding and the absolute milliseconds are not.

## Then it fails its own census, on a head query

The ten-term LAT-P096 census — the one that justified *keeping* the FTS half — passes perfectly.
Zero rows lost on all ten, and `election` gains 11:

```
champions 742→742   relegation 116→116   chiefs 30→30    election 2402→2413 (+11)
werder     28→28    schalke     34→34    winner 3593→3593  trump  812→812
fed       270→270   mvp         31→31
```

That is exactly the trap LAT-P096 documented in the other direction, and it caught this lever
too: **a ten-term census is a spot check.** Widened to 36 terms — the 30-day `/search` head plus
deliberate stemming hazards — four terms lose recall, and one of them is head rank 7:

| term | OLD | NEW | lost | stem | note |
|---|---:|---:|---:|---|---|
| `grammys` | 15 | 5 | **−10** | `grammi` | **head rank 7** (75 queries/30d) |
| `cities` | 744 | 4 | **−740** | `citi` | |
| `qualifying` | 1,074 | 237 | **−837** | `qualifi` | also **+473** rows FTS never admitted |
| `trophies` | 15 | 8 | −7 | `trophi` | |

**One cause, and it is structural.** Porter maps a trailing `y` to `i`. `grammys` stems to
`grammi`, which is not a substring of "Grammy" — FTS matches it because FTS stems *both sides*,
and a substring predicate only ever sees one. Every `-y`/`-ies` word in English is in this class,
so this is not four unlucky terms; it is a category.

The obvious repair — also try the stem with its trailing `i` truncated (`grammi` → `gramm`) —
restores the recall and spends precision on a list that is `ORDER BY market_tier, volume LIMIT
20`. `qualifying` already admits 473 rows the FTS half rejects; `citi` → `cit` would admit
"citizen", `studi` → `stud` admits "student". That trades a **measured** loss for an
**unmeasured** one on a ranked, truncated, user-facing dropdown, which is not a trade this lane
can make on its own numbers.

**VERDICT: REJECTED on measurement.** The value is not the rejection, it is what the rejection
proves: the DDL is not merely the *convenient* lever, it is the only one that preserves the
recall the census pins. LAT-P096's spec is strengthened, not replaced, and the attended
`CREATE INDEX CONCURRENTLY` is still the ship.

## Two incidental findings, parked not dropped

Both belong to `.claude/handoff/PARKED-MEASUREMENTS.md`, not to a queue of their own.

1. **`revs` and `pats` — head ranks 11 and 13 — match ZERO open markets on the futures name
   arm**, in both the old and new shapes. Whatever those users see comes from the team or
   outcome arms, or they see nothing from futures at all. Not a latency finding; a recall one.
2. **`fed rate decision` and `penalties` also return 0** on both shapes.

## What was shipped, and what was not

**Shipped:** the finding, as a guard. `_build_futures_name_filter`'s docstring carries the census
so the next reader does not re-derive it over 40 minutes, and
`tests/test_futures_name_filter_arms.py` gains `TestStemSubstringIsNotASubstituteForFTS`.

**Not shipped:** any change to the predicate. No code path moved, no plan changed, no config var
touched, no DDL run.

### The guards are red-first, and the plant compiles

A green gate is evidence only if you can say what would turn it red (GO 2026-08-19, STANDING).
The rejected lever was **planted into `_build_futures_name_filter` and the suite re-run**:

```
plant   9 failed, 9 passed     0 CompileErrors
clean  18 passed
```

All six new tests fail against the plant, on their own assertions — the first plant attempt
failed all 18 on a `CompileError`, which is red for the wrong reason and was thrown away and
rewritten until the plant rendered real SQL (memory: *a plant must hit the render*).

**The nine that PASS against the plant are why the new class had to exist.** The lever emits the
token `to_tsvector` (it uses it to compute the stem) and it emits `ILIKE`, so
`test_no_conditional_wrapping_of_the_fts_arm` (counts `TO_TSVECTOR == 1` — the plant has exactly
one) and all four `test_recall_terms_keep_both_halves` cases stay green while 740 rows go
missing. The new assertions are the ones that can tell "we search stemmed names" from "we
stemmed the search box":

- the `@@` operator's left side must vectorise `futures_markets.name`;
- no tsvector may be built over a string literal;
- the four census-loss terms must not be matched by their stem substrings, parametrised so the
  failure names the term that broke.

## Contamination declared

This work issued **zero** `/api/events/typeahead` and **zero** `/api/events/search` requests, so
it cast no votes into `search:trending:24h` (#1916's head source) and wrote no rows to
`search_query_logs`. Every number above came through `POST /api/admin/db-query`. It did spend
real production database time: ~36 census queries and ~20 `EXPLAIN ANALYZE` runs, each scanning
open markets, of which the old-shape halves cost 2–6.5 s apiece.

The 30-day head used to pick census terms was read from `search_query_logs`, which #1916
measures as 23.6 % gold-sentinel. That biases *which terms were tested*, not the recall counts
themselves — and the head's contamination pushes toward sentinel phrasings, so if anything it
under-samples the organic `-y`/`-ies` words that break this lever.
