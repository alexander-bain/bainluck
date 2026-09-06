# latency/181 — label the invisible third, then move the two grinders

Written by latency/180 at 2026-09-06 ~04:15am PT (11:15Z — PT = local `date` minus 3h, notice 24,
verified with `TZ=America/Los_Angeles date`). Staged, not consumed.

**PILLAR: DISCOVER.** **SHIP: the search box stops being cold 45% of the time** — the same ship as
178, 179 and 180. 180 found the mechanism end to end; this queue is the one that can act on it.

## Read first

`artifacts/latency-180/REPORT-latency-180-the-instrument-could-not-see-a-third-of-the-queue.md`,
and issues **#3444** (label map — blocks any realtime number), **#3440** (settled concepts),
**#3399** (180's ship, merged), **#3398** (the parent measurement, CLAIMED by latency).

**Do not re-derive any of this:**

- Do NOT re-run the concurrency sweep, do NOT touch `WARM_CONCURRENCY`, `REFRESH_AHEAD_SECONDS` or
  `RESPONSE_CACHE_TTL_S`. 178 settled all three.
- Do NOT implement priority queueing. 179 measured and refuted it.
- Do NOT move anything to `heavy`. 180 measured it at **0.91x** against background's 0.84x *floor*;
  it is the more loaded lane.
- Do NOT rebuild the demand model from scratch — `artifacts/latency-180/demand.py` works and carries
  the four instrument corrections in its docstring. Re-run it; do not re-derive it.
- Do NOT trust `pg_stat_statements` totals. Reset 5+ days ago; 135 of its top 200 statements are
  dead. Use `pgss-snap.py` + `pgss-delta.py`.

## State on arrival

🔴 **180's ship is CERTED GREEN BUT NOT MERGED, and it is blocked on another lane.**
**CERT-2032 — GREEN, TOKEN GRANTED, exact-SHA CI still required before merge**, at
`2a28a13f`. The grader independently verified the behaviour on production (first shed request
writes, second hits) and ran the battery (23/23).

**Exact-sha CI is RED, and not for this ship.** `backend-tests (2)` fails on
`test_combat_card_rollover_1712.py::...::test_kalshi_and_events_halves_land_on_one_token` —
`assert [] == ['event:ufc:26sep05']`, a UFC card dated the day before. A clock-dependent anchor
(gotcha #44). Verified failing identically on pristine `origin/master` in a throwaway worktree, so
**every branch cut from master currently has a red shard 2**. Already owned:
`authority/040-the-combat-card-tests-anchor-on-now` @ `f68d4146`, **#3456** (commented there with the
blast radius; not touching it, notice 6).

**So the sequence is: #3456 lands → rebase → re-stage under a NEW cert id quoting CERT-2032.** A
rebase changes the sha and breaks the notice-13 token grep, so do NOT try to merge on `2a28a13f`.
The branch has also moved past the certed sha (docs + the CERT-2032 follow-up fix `c5cbc7af`), which
the re-stage absorbs.

**The post-deploy check is therefore still OWED and is 180's, not 181's** — unless 180's session is
gone, in which case take it. It is: `GET /api/events/typeahead?q=sta` twice, ~2s apart; the second
should be fast (a warm hit) where before the change both were 5–8s. Same for `red`. If it is not
warm, suspect first that `sta` has fallen out of the warmed head rather than that the fix failed —
read `last_outcome.head` from `/api/admin/typeahead-warmer/last`, and note the ring truncates that
list to 12 while the task-metrics summary carries all 40.

## The mechanism, established — build on it, do not re-measure it

1. Both `background` slots are busy **10 of 11 sampled minutes (91%)**, with **2 tasks prefetched
   and waiting in every single sample**.
2. `warm_typeahead` fires every 10s (`matched_emitted: 60` per 600s bucket — the beat is healthy)
   and its messages queue: **18 at once** in a 33-deep census.
3. `expires: 120` discards them before a slot frees.
4. The warmer's skip counters therefore sit **frozen** — `{lock, min_period}` unchanged for 201
   seconds while `last_outcome_age_s` climbed and `read_at_epoch` advanced (so: not a cached
   endpoint, genuinely nothing delivered).
5. Period stretches to 191–616s, the 65s TTL lapses, head cold **45.0%** of the time
   (79 passes / 112.8 min — the longest window 180 could build; shorter windows of the
   same metric read 38.5% and 41.5%, so quote the long one or quote the range).

## ITEM 1 — THE PREREQUISITE: give the 32 unlabelled beats a duration

**This is the ship's critical path and it is mechanical.** 32 of 110 `background` beats never call
`_tracked_run`, so they have **no duration under any label**. The demand model scores them zero. The
occupancy timeline scores them idle. That is how 180 briefly concluded the queue had free slots
during its own holes.

It is not a rounding error: the **single largest occupant** of the queue in the `inspect` sample is
`collapse_snapshots` (45.5% of samples), and it is one of the 32. `merge_duplicate_events` and
`merge_degenerate_combat_events` are two more.

The 32, by delivery rate: `update_max_movement` 6.25/hr, `track_statpal_usage` 5.53, `compute_gei_batch`
2.04, `merge_duplicate_events` 2.04, `check_tier1_coverage` 1.06, `enrich_events_metadata` 1.06,
`compute_gei_percentiles` 1.03, `sync_sports` 1.03, `backfill_team_links` 1.02, `backfill_historical_links`
0.49, then a long tail at ≤0.2/hr including `collapse_snapshots`, `recategorize_other`,
`canonicalize_entities`, `sync_rosters`, `backfill_espn_ids`, `mark_resolved_futures`,
`compute_matching_metrics`, `backfill_polymarket_matchups`, `backfill_canonical_keys`.

⚠️ **`collapse_snapshots` reads 0.00/hr on the delivery counter and is the biggest occupant of the
queue.** Do not let a low rate excuse a task from being labelled — reconcile that contradiction as
part of this item, because one of the two numbers is lying and it matters which.

Also worth pricing in the same pass: **`refresh_hub` is not a beat entry at all** and was holding a
background slot when 180 looked. Find what dispatches it. A demand model over the beat schedule
cannot see route- or task-dispatched work, and that is a second blind spot beside the 32.

**Then re-run `demand.py` and get the real total.** Only then is a topology decision possible.

## ITEM 2 — THE LIKELY SHIP: the two grinders

Once ITEM 1 makes them visible, the two obvious candidates are already named:

- **`turbo_collapse_futures`** — mean **942.7s**, in 36.4% of `inspect` samples. A 16-minute task on
  a 2-slot queue.
- **`collapse_snapshots`** — unlabelled, in **45.5%** of samples.

Both are collapse/compaction work with no reader waiting on them. That is exactly the profile
`refresh_stale_futures_prices` had when it was pinned to `heavy` with the note that a multi-minute
beat "does not share [background], it closes it".

🔴 **But `heavy` is at 0.91x and cannot take them** (180, measured). So the honest options are, in
order of preference:

1. **Make them cheaper.** Check both for 179's defect class first — an `Index Scan` whose leading
   column is unconstrained is a full scan that reads like a seek; the tells are `Total Cost` and
   `Shared Read Blocks`, never `Node Type`. A 942s task is a strong prior for a per-item loop. If
   this works it costs nothing elsewhere and it is the right answer.
2. **Cadence.** Ask 179's class question first — `tournament_price_refresh` did not need to run less
   often, it needed to stop costing 189s. But compaction genuinely may not need its current cadence,
   and unlike a price refresh nothing user-facing reads it.
3. **A fourth queue, or `--concurrency=3` on background.** ⚠️ **This is spending and is OUT OF SCOPE
   without Alex.** A Standard-1X at `--concurrency=3` is not free memory-wise
   (`--max-memory-per-child=200000`). If the measurement says this is the only answer, that is a
   YOUR-TURN entry with the number, not a change.

Do NOT pick from this list before ITEM 1 gives you the total. 179's rule (tt) — relieving one
contributor in an oversubscribed queue reallocates the wait — still applies, and 180 adds that a
ranking taken from a partially-blind instrument can name the wrong task entirely.

## ITEM 3 — `warm_search_head` is silenced, and it is nearly free to say so (#3364)

`expires: 20` against a queue whose wait is minutes means **96.7% of its fires are discarded**:
`matched_emitted: 30 / matched_delivered: 1`, `undelivered_fraction 0.967`, `ratio 0.04`, verdict
`missing`. The constant's own comment justifies 20s on the grounds that the task's wall (~4–8s) is
shorter than its 20s period, so a held-off fire IS superseded. **That reasoning is correct and its
premise is false**: it compares against the task's own wall, not against the QUEUE WAIT. When the
wait exceeds `expires`, the task is not de-duplicated, it is silenced.

This is **#3364 and is filed, not ours** — but 180 has the measurement that explains it, and the
generalisation is worth writing into `_EXPIRING_WARMER_BEATS`: *the bound must be compared against
delivery latency, not against the task's own duration.* Coordinate; do not claim.

## ITEM 4 — #3444 blocks the realtime answer, and it is a live monitoring bug

`label_map` is single-valued; `poll_all_odds` and `discover_events` each write several
`_tracked_run` labels and keep whichever ran last. The health surface therefore grades
`poll_all_odds` on a DataGolf sub-poll (**3.3x over**) and `discover_events` on a taxonomy
enrichment (**4.0x under**) — and `discover_events` is one of the three largest background
occupants, so this distorts ITEM 1 too.

The guard that found it is three lines of `ast.walk` and belongs in CI regardless of which fix is
chosen. **`poll_all_odds` itself is the live lane's — hand it over, do not claim it.**
**Do not ask the bus to re-run M-20260905-A until #3444 lands.** D67 does not go back to Alex until
the lane is still over capacity *after* ITEM 1 and ITEM 2, with the audit's number.

## ITEM 4b — CERT-2032's remaining follow-up, and why 180 did not build it

CERT-2032 was GREEN with the token granted and named two nonblocking follow-ups.

**`TYPEAHEAD-DEBUG-STATE-OUTSIDE-TIMING-MAP` is DONE** (`c5cbc7af`). The two shed booleans were in
`debug_timing`, a map of stage milliseconds whose `total_ms` is a sum — and `True` sums as 1. They
moved to their own `debug_shed` key, with a RED-first guard that also refuses the
one-level-less-visible version (a `**_ta_stage_ms` spread sharing a dict with the booleans).

**`TYPEAHEAD-SHED-RUNTIME-CACHE-CONTRACT` is OWED.** The ask is an endpoint-level regression: a
shed answer WRITES and the next request HITS; a full futures-stage timeout writes NOTHING. The
grader proved both by hand against production; there is no test.

⚠️ **Why 180 did not build it, so 181 does not rediscover the reason.** Three test files already
drive `typeahead_search` directly (`test_typeahead_trending_cache_hit_2117.py`,
`test_search_origin_channel_p118.py`, `test_typeahead_eval_calls_do_not_vote.py`) and **all three
rely on a cache HIT returning before the first query**, so they pass `db=None`. This contract needs
the MISS path, which means a fake `AsyncSession` that survives every stage of a 1,000-line function.
That is the real work, and it is worth doing once and sharing — `/search`'s suite has the analogous
harness in `test_search_response_cache.py::_search` and is the model. Note its warning, which cost
that file a red run: the debug flags' declared defaults are `Query(...)` marker objects, TRUTHY
outside FastAPI, so every flag must be passed explicitly or the assertions are made against the
uncached path.

## ITEM 5 — carried, unchanged

- **`LAT-P240-PREDICATE-SEMANTICS-GUARD` is still owed.** 179's guard counts emitted writes against
  a permissive fake; production answered it empirically but that is evidence, not a guard.
- **#3440** (settled golf concepts, 426 wsec/hr, byte-identical output proven over 3–4 rebuilds) is
  filed with a suggested shape. Small, safe, and it is 5.9% of a queue now measured saturated.
- Seven `external_id ==` sites remain; none moved in the live `pg_stat_statements` delta.
  `admin_matching.py` is **D35/D39 — file, do not fix**, link #2693.
- **CERT-1988 stays PARKED.** Do not merge PR #3377, do not re-stage, do not rewrite its header.
  `PARKED-MEASUREMENTS.md:8917`.

⚠️ Build on a FRESH branch off master. `program/latency-242-…` still holds the parked commits;
`program/latency-245-…` is 180's and is merged or in flight.

## Explicitly NOT in scope

- **Spending** — no dyno resize, no concurrency purchase, without Alex and a number.
- `WARM_CONCURRENCY`, `REFRESH_AHEAD_SECONDS`, `RESPONSE_CACHE_TTL_S`, priority queueing, moving
  work to `heavy`.
- **The tsvector index** — Tier-1, integrator + Alex.
- **ITEM 4 of 178** (serving `red sox` its headline market) — recall, not latency; needs a stated
  recall argument and must not be bundled.
- Matching symptoms — D35, file under #2693, never fix.

## Rules carried forward

168 (a)–(g), 170 (b)–(e), 171 (b)–(e), 173 (f)–(i), 174 (j)–(m), 175 (n)–(x), 176 (y)–(dd),
177 (ee)–(kk), 178 (ll)–(oo), 179 (pp)–(uu), **180 (vv)–(aaa)** all hold. The three from 180 most
likely to bite this queue:

**(vv)** An occupancy timeline reconstructed from per-task instrumentation reports UNINSTRUMENTED
work as IDLE. Before believing a resource is free, ask what fraction of its consumers the instrument
can see, and cross-check with a direct `inspect` read. **The caveat you write in one model does not
travel to the next model you build from the same data.**

**(ww)** When two measurements of one mechanism disagree by 7x, suspect COVERAGE before mechanism.

**(zz)** Frozen counters are a positive result and the cheapest one available — pair them with a
freshness control (`read_at_epoch`) so "nothing happened" cannot be confused with "nothing was read".

Idle rule: empty inbox → write the next directive from the charter; never stop, never end with a
question.
