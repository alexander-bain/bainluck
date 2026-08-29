"""Keep `/typeahead`'s hot pages resident, so a user never pays the cold read (#1866).

WHAT THIS FIXES, measured rather than assumed (LAT-P056, production `da5e7992`).

`/typeahead`'s cache-MISS cost was decomposed end-to-end at the transport
boundary, n=24 paired miss/hit probes, and the answer was not ambiguous:

    segment    miss p50      share of the 1384.6ms miss cost
    dns          0.011ms     0.00%
    connect      0.165ms     0.00%
    tls        157.644ms     0.25%      <- a real FLOOR, but not the miss cost
    server    1455.496ms    99.74%      <- all of it
    transfer     0.516ms     0.01%      (1875-byte body)

So the miss is server-side. Then EXPLAIN ANALYZE on production named what the
server was doing, and it was not computing — it was **waiting on storage**:

    ILIKE '%red sox%' over futures_outcomes   cold 1094.5ms   hot  27.1ms
    ILIKE '%yankees%'                         cold  426.5ms   hot   5.5ms
    ILIKE '%bruins%'                          cold  219.9ms   hot   5.0ms

On every cold run 95-98% of the node's time was `Shared I/O Read Time` with
hundreds of `Shared Read Blocks`; on every hot run `Shared Read Blocks` was
**0** and the same query, same plan, same rows, cost single-digit ms. The plan
was never wrong — the pg_trgm GIN index pages simply were not resident.

WHY THAT SWINGS BY THE HOUR, and why "accumulating resource" was the wrong
reading (LAT-P054 withdrew it after it failed to replicate across a restart —
correctly, because nothing accumulates here). `ix_futures_outcomes_name_trgm` is
**406 MB** and `ix_futures_name_trgm` **172 MB**, against `shared_buffers` of
**1 GB**. Those two indexes alone want 56% of the entire buffer pool, and they
compete with scheduled work that sweeps it: the prediction-market matcher's
`futures_markets` scans run every 15 minutes and measure 13-21s mean in
`pg_stat_statements`, over a 977 MB table. Residency is therefore a shared
resource under periodic eviction pressure — which looks like drift, is not
monotone, and does not survive a restart, exactly as observed.

WHAT THIS TASK DOES ABOUT IT. It re-touches the head of the query distribution
every 30s, so the cold read is paid by a background worker instead of by
somebody typing.

THE CADENCE IS MEASURED, AND THE FIRST DRAFT OF IT WAS WRONG. It was written as
2 minutes on the reasoning that page residency is a shared resource worth
holding, and that the 45s response TTL was the less interesting of the two
effects. Then residency was measured directly instead of reasoned about:

    t=0 cold  245 read blocks / 221.7ms
    t=2s        0 / 35.5ms      t=30s   0 / 16.8ms
    t=15s       0 /  7.2ms      t=45s   0 /  9.9ms
    ...and a second query at t=60s: 701 blocks, fully EVICTED.

Residency survives 45s and is gone by 60s. A 2-minute warmer would therefore
have left the pages cold for most of every interval: it would have run, reported
success, and delivered nothing — the exact failure this module's tests are
built around, reached by the design rather than by a bug.

So 30s, and the ORDER OF THE TWO EFFECTS IS THE REVERSE of the first draft:

* **The head rides on the response cache.** 30s is inside the route's 45s TTL,
  so a head entry never expires and those users never reach the database at all.
  That is the guarantee.
* **Page residency is the weaker, shared bonus.** It reaches tail queries that
  touch the same index pages, which the response cache cannot do — but it decays
  inside a minute, so nothing is allowed to rest on it.

THAT GUARANTEE WAS FALSE IN PRODUCTION FOR THE WHOLE OF `-51`'s LIFE, and it
failed in TWO independent ways. LAT-P059 measured the first, LAT-P060 the
second; the fix needed both, which is why neither alone had been enough.

**Hole 1 — the beat is 30s but a PASS took 38s.** The head was warmed one query
at a time, so a pass ran 33-59s (median 38.0s, worst 58.9s) while the Redis
run-lock serialised the beats behind it. Measured over 50 invocations / 1246s:
**25 lock skips**, and an interval between real passes of **95.8s** — against a
45s TTL. The head was cold for roughly half of every cycle.

**Hole 2 — A PASS THAT HITS THE CACHE EXTENDS NOTHING, so cadence alone could
never have fixed it.** `routes/events.py` returns the cached body *before* it
reaches its own `setex`, so an entry's life is 45s from its last REBUILD and a
warm read resets no clock. In the same 50-invocation window **12 beats ran a
full 40-query pass in ~0.65s** — 40 Redis GETs, `terminal: complete`,
`warmed: 40/40`, and nothing rebuilt. A green run that did no warming, which is
the exact failure mode the rest of this module is built to refuse.

Hole 2 turns the duty cycle into a SAWTOOTH rather than a ratio. With pass
period T the rebuild period is `T*ceil(45/T)`, so the warm fraction is
`45/(T*ceil(45/T))`:

    T = 95.8s (as shipped)  ->  47.0%      T = 30s  ->  75.0%   <- NOT 100%
    T = 60s                 ->  75.0%      T = 25s  ->  90.0%
    T = 20s                 ->  75.0%      T = 15s  -> 100.0%

Read the T=30 row: making the pass fit inside the beat — the obvious fix, and
the one that was proposed — lands on 75%, and does so NON-MONOTONICALLY (a 20s
pass is no better than a 30s one). Tuning a cadence against a TTL the warmer
cannot refresh is tuning a sawtooth.

SO THE FIX IS TWO CHANGES, and the module now does both:

1. **`WARM_CONCURRENCY`** closes hole 1. A pass fans out over N sessions, so it
   fits inside the beat and stops being skipped.
2. **`REFRESH_AHEAD_SECONDS`** closes hole 2. A query whose cached entry is
   near expiry is REBUILT OVER before it can expire, so the route recomputes and
   writes a fresh TTL. The rebuild period becomes the pass period, and the duty
   cycle becomes `min(TTL, T)/T` = 100% for any T < TTL — flat, not a sawtooth.

🔴 LAT-P134 (2026-08-29) CORRECTS THE PRICE OF (2), AND THE CORRECTION IS THE
REASON THE MECHANISM CHANGED. This paragraph used to read:

    "between the drop and the route's write there is a window in which a user
    typing that prefix pays a database read ... because the warmer keeps the
    pages resident that recompute is the HOT cost (5-27ms), not the 1.4s cold
    cost. It replaces a 30-50s cold window per cycle with a ~20ms one"

The mechanism was a Redis DELETE (`_drop_cached`), because the route writes its
cache only on the miss path. Measured on production `8ca1e2ed`, `celtics` and
`lakers` — both confirmed warm head terms — 70 samples through the real cache
path with the non-voting origin header: **p50 18-19ms, and 6 of 70 (8.6%) at
2,000-3,689ms**, spaced at the pass period. **The hole was ~150x its estimate,
and it landed on the terms this file exists to keep fast.**

The estimate failed for a reason a later cycle measured in another file and
nobody carried back here: the recompute is dominated by LAT-P096's un-indexed
`to_tsvector` scan over ~49.5k open markets, which is CPU. LAT-P096 measured
27,483 buffer HITS — already resident — and still 742.7ms. Page residency was
never going to buy this back, so "the warmer keeps the pages resident" was true
and irrelevant in the same breath.

The hole is gone rather than re-priced. `_force_cache_rebuild` (defined in
`routes/events.py`) makes the route skip the cache READ and keep the cache
WRITE, so the old answer is served continuously until the new one replaces it,
at the same instant it would have been written anyway. **Max staleness is
UNCHANGED** — the response TTL governs both — so this buys latency and must not
be read as buying freshness. A rebuild that times out or errors now leaves the
previous answer alive to its natural expiry instead of leaving a hole.

THE HEAD IS MEASURED, NEVER GUESSED — AND FOR THREE CYCLES IT MEASURED THIS TASK
RATHER THAN ITS USERS (LAT-P078, #1866). Two real sources, now BLENDED:

1. ``search_query_logs`` — the /search log (#239 Item 4). Real submitted intent,
   time-windowed to 30 days by its own query, written only by `/search`, which
   this task never calls. Nothing here can pollute it. Measured 2026-08-14:
   3,423 rows / 210 distinct, top-20 = 36% of volume, top-50 = 69%.
2. ``search:trending:24h`` — the Redis zset `/typeahead` writes on every call. It
   measures the surface actually being warmed, including the prefixes a user
   passes through on the way to a phrase, which `/search` never sees. Hour-
   bucketed since LAT-P080B/#2072; before that it was an all-time counter with a
   24h label, which is the other half of the frozen head below.
3. ``_STATIC_FLOOR`` — cold-start only, for a fresh Redis and an empty table.

**Source 1 had never selected a single warmed term in production.** `resolve_head`
was a strict first-non-empty cascade and source 2 is never empty, so the query-log
arm was unreachable code. That alone would be a composition bug. What made it a
LOOP is that `_warm_one` warms by calling the route, and the route's last act is
to `zincrby` the query into source 2 — so every pass voted for its own head, ~1,700
times a day per term against ~3/day for an organic query. Once a term was in the
top-40 it could not fall out and nothing could break in.

The signature was unmistakable once looked at. Production, 2026-08-21::

    world cup 5414   red sox 5411   celtics 5403   yankees 5400   patriots 5399

A spread of 15 across the top five is a round-robin process, not a human
distribution — the log's own head over the same period runs 102, 101, 95, 90, 82.

⚠️ LAT-P117 (2026-08-29): that contrast was read as zset-machine vs log-human,
and only the first half was true. The log's 102/101/95/90 head is ALSO machine —
the Flow Sentinel's nightly gold set (see `_QUERY_LOG_SHARE` below for the
measurement). The zset diagnosis stands; "so the log is the honest one" does not.

The user-visible cost, measured the same morning at a 15.6h post-deploy horizon:
the top four queries by 30-day volume are ``masters winner`` (102),
``stanley cup`` (101), ``world series`` (95), ``nba champion`` (90), and three of
those four were COLD at 4.0s, 4.9s and 5.2s against a <150ms budget. ``world
series`` was warm at 0.25s for no better reason than that it was also locked into
the zset. The warmer reported ``warmed: 40/40`` on every one of those passes.

So the fix is two halves of one change, and neither works alone: the route stops
counting the warmer's own calls (`_suppress_trending_write`), and `resolve_head`
blends instead of cascading (`_QUERY_LOG_SHARE`). Breaking the loop without the
blend would leave the accumulated ~5,400 all-time scores frozen in place, because
the route re-`expire`s the key on every write so it never actually rolls 24h.

NOT LOAD-BEARING, deliberately. A cold miss still builds inline in the route, so
turning this task off makes `/typeahead` slow again — never broken. The tests
assert that, the same contract `event_concept_warmer` carries.
"""

from __future__ import annotations

import asyncio
import logging
import time

from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

#: How many head queries to warm per run. 40 sits just past the measured
#: top-of-distribution knee (top-50 covered 69% of logged volume) while keeping
#: a warm run's total work small — every query after the first cycle is
#: single-digit-to-low-hundreds of ms because the pages it needs are resident.
DEFAULT_HEAD_SIZE = 40

#: Bound on ONE query, not on the loop. Bounding only the loop boundary lets a
#: single pathological query eat the whole budget and starve the rest of the
#: head — the same failure `event_concept_warmer.PER_KEY_TIMEOUT_SECONDS` exists
#: to prevent, and the reason `/typeahead`'s own deadline is per-request.
PER_QUERY_TIMEOUT_SECONDS = 10

#: How many head queries are warmed at once. FOUR, and the number is bounded by
#: measurement in both directions rather than picked for roundness:
#:
#: * FROM BELOW, by the pass wall against the 45s response TTL. ⚠️ This bullet
#:   USED to divide a 58.9s serial pass by W and claim "W=2 gives 29.5s, W=4
#:   gives 14.7s worst / ~9.5s median". Those were PROJECTIONS and production
#:   refuted them: the real W=4 pass measures 29-43s, never 14.7s (LAT-P062).
#:   Replaced with the MEASURED paired sweep (LAT-P063, 9 alternating arms, all
#:   40 entries force-rebuilt so the arms do equal work — see
#:   `docs/audits/latency/lat-p063-wsweep-graded.md`):
#:
#:       W       wall/rebuild     DB-work/rebuild     vs W=4 wall
#:       1          2.880              2.880            1.91x
#:       2          1.869              3.730            1.24x
#:       4          1.506              5.752            1.00x
#:
#:   The binding constraint is `period ~= max(seconds_wall, MIN_PASS_PERIOD)`
#:   against the 45s TTL. Live W=4 wall is 32s median (29.4-42.6s range), so
#:   W=2 scales to ~40s median with an upper tail OVER 45s, and W=1 to ~62s.
#:   LAT-P063 measured, 20 passes for 20, that EVERY pass with period > 45s
#:   lost cached entries (up to 39 of 40) and no pass under 45s lost any.
#:   Crossing the TTL does not degrade the head gradually; it empties it.
#:   So W=4 is not padding — it is the margin between the pass and the TTL.
#: * FROM ABOVE, by what the concurrency does to the thing this task exists to
#:   protect. These are 40 pg_trgm reads against a 1 GiB `shared_buffers`
#:   (measured: `shared_buffers` = 131072 * 8kB), and production runs at 3
#:   ACTIVE backends, so W=4 roughly doubles peak concurrent query work. That
#:   is the real ceiling; connections are not (measured 2026-08-17:
#:   `max_connections` 500, 21 in use — 479 free, so a connection argument for
#:   any W in this range would be theatre).
#: * A THIRD bound applies if this is ever consolidated onto ONE engine:
#:   `base._get_task_engine()` is `pool_size=3, max_overflow=2`, so a single
#:   engine can hand out at most FIVE concurrent connections. W=4 fits with one
#:   spare; a larger W would silently serialise on pool checkout and the
#:   concurrency would be a lie the summary could not see.
#:
#: 🔴 THE JUSTIFICATION THAT USED TO SIT HERE IS REFUTED. IT READ:
#:
#:     "LAT-P056 measured 95-98% of a cold query's time as `Shared I/O Read
#:      Time`. These are I/O-WAIT bound, which is the one case where
#:      concurrency overlaps waiting instead of multiplying work — and they
#:      contend for the buffer pool LESS than four different queries would,
#:      because they want the same index pages."
#:
#: Work that merely overlaps waiting does not get 1.9x more EXPENSIVE PER UNIT
#: as the fan-out widens, and it does. LAT-P063's sweep measures DB work per
#: rebuild rising 2.880 -> 3.730 -> 5.752 across W = 1 -> 2 -> 4: concurrency
#: multiplies work here, it does not overlap it. 40 concurrent trigram scans
#: against a 1 GiB `shared_buffers` contend for the very pages they are all
#: trying to keep resident — they want the same index pages, and that is why
#: they evict each other rather than why they cost less.
#:
#: THE VALUE SURVIVES ITS OWN REFUTATION, for a different reason than the one
#: it was chosen for: W=4 costs 1.54x the DB work of W=2 and buys a 1.24x
#: shorter pass, and the pass wall is what has to clear the 45s TTL. We are
#: buying TTL margin with database work, knowingly. Narrowing was measured and
#: REFUSED this window (ruling 050 prediction registered first); the ship rule,
#: the numbers and the refusal are in `lat-p063-wsweep-graded.md`.
#:
#: This cost is a workaround, not a design. The 688.6 MB trigram surface it
#: exists to hold resident is 67% of the buffer pool; Option D replaces it with
#: ~140 MB, after which this whole constant should stop being load-bearing.
WARM_CONCURRENCY = 4

#: Rebuild a cached entry when it has less than this much life left, instead of
#: reading it back and extending nothing (hole 2 in the module docstring).
#:
#: 35s = one 30s beat plus 5s of margin. The bound it has to satisfy: an entry
#: must survive from this pass until the NEXT pass reaches the same query. Each
#: query is warmed at a fixed offset inside the pass, so that gap is the pass
#: PERIOD (the 30s beat), not the period plus the duration — which is why a
#: 45s TTL has room for it at all, and why the margin can be small.
#:
#: Set this BELOW the beat and entries expire between passes; set it at or above
#: the 45s TTL and every entry is rebuilt unconditionally, which is what the
#: module did before and is merely wasteful rather than wrong. The `fresh` skip
#: it enables is a safety valve for a shortened beat, not an optimisation for
#: today's one — at a 30s beat against a 45s TTL an entry always has ~15s left
#: when a pass reaches it, so today it rebuilds every time, by design.
#:
#: ⚠️ LAT-P062 CORRECTION — the bound above is REFUTED, and the value is kept
#: anyway. The paragraph reasons from "that gap is the pass PERIOD (the 30s
#: beat)". It is not. The measured period is **42.5–51.7s** across two
#: production reads, because a ~31s pass does not fit inside a 30s beat and the
#: run-lock quantises the period up. So the arithmetic that matters is:
#:
#:     an entry's remaining TTL when a pass reaches it is  45 - P
#:     a threshold T skips it only when                    T < 45 - P
#:
#:     P = 42.5s  ->  the largest useful T is 2.5s
#:     P = 51.7s  ->  nothing is ever fresh; no T works at all
#:
#: `fresh: 0` on 5 of 5 observed production passes is therefore not a tuning
#: miss, it is the only reachable value — and LOWERING T into that band would be
#: actively harmful, because skipping an entry with 2.5s of life left means it
#: expires before the next pass arrives. A staleness-aware skip would buy pass
#: time by re-opening the cold window refresh-ahead exists to close.
#:
#: The value stays at 35 because the value is not what is wrong: it is inert, it
#: is inert in the SAFE direction (always rebuild), and it becomes live again if
#: the period ever drops below 10s. What was wrong is the justification, and a
#: constant whose stated justification is refuted is the trap ruling 076 banks.
#: The period is fixed by `MIN_PASS_PERIOD_SECONDS` and the beat, not by T.
REFRESH_AHEAD_SECONDS = 35

#: The pass may not START more often than this. A floor, not a cadence.
#:
#: LAT-P062 shortened the beat from 30s to 10s to stop the run-lock quantising
#: the pass period up to ~60s (a ~31s pass cannot fit inside a 30s beat, so
#: every other beat skipped and the period straddled the 45s TTL — measured duty
#: cycle 17.5 of 24). A shorter beat removes dead time, but on its own it also
#: removes the only thing that was bounding how often the warmer may run.
#:
#: That bound matters because the warmer is not free: it holds the database for
#: 73% of wall-clock at concurrency 4 — roughly 2.9 backend-equivalents against
#: a production baseline of ~3 ACTIVE backends. Halving the period would double
#: that. So the floor keeps the load increase bounded and STATED: period moves
#: from a 42.5–51.7s mean to ~40s (+6% to +29% warmer DB work), and can never go
#: below 30s (+42%, the worst case) however fast a pass becomes.
#:
#: 30s rather than 45s because the entry has to be rebuilt strictly BEFORE it
#: expires, not as it expires; and rather than 35s because the floor should not
#: bind at today's ~31s wall — it is a rail, not the mechanism.
MIN_PASS_PERIOD_SECONDS = 30

#: Unix timestamp of the last pass START. Read to enforce the floor and to
#: report `period_s`, which is the number the 45s TTL actually has to be
#: compared against — and which, until LAT-P062, the task could not state about
#: itself. Every duty-cycle grade so far has been inferred from a client probe
#: or reconstructed from a duration histogram; ruling 074 asks an instrument to
#: report the work it did, and "how long since I last did it" is half of that.
#:
#: Deliberately a plain key rather than part of the run-lock: the lock's whole
#: contract is that it disappears (`_LOCK_TTL_SECONDS`, so a killed worker
#: cannot wedge the warmer), and a value that must OUTLIVE the pass cannot share
#: a key whose job is to expire during it.
_LAST_PASS_START_KEY = "bainluck:typeahead_warmer:last_pass_start"

#: Long enough that a pass gap is still readable after a worker outage, short
#: enough that a stale value cannot suppress passes forever. A missing value
#: means "no floor" — fails toward DOING the work, like every other Redis read
#: in this module.
_LAST_PASS_START_TTL_SECONDS = 3600

#: The bounded ring of REAL PASS results, and the state hash beside it.
#:
#: LAT-P074 (#1866, #1609). These exist because of a distinction the previous
#: cycle got wrong in BOTH directions, and the correction is worth stating here
#: rather than in a report nobody will re-read.
#:
#: **What LAT-P073 believed:** the pass summary "goes to the task return value
#: and a log, and nothing can read either". **That is false.** `_tracked_run`
#: hands the summary to `record_task_success`, which writes it verbatim to
#: `task_metrics:<name>.last_result_summary`, and
#: `GET /api/admin/celery/task-metrics/warm_typeahead` returns it. The last pass
#: result has been readable from production the whole time.
#:
#: **What is genuinely missing, and is what these keys add:** that slot holds
#: exactly ONE outcome and is overwritten by every run — including the no-ops.
#: Measured 2026-08-20T00:15Z over a saturated 50-sample duration ring: 33 of 50
#: executions were no-ops (all <= 71 ms) and 17 were real passes (all >= 32.9 s).
#: So a single-slot read lands on a no-op **two times in three**, and no number
#: of reads can reconstruct a DISTRIBUTION from a slot that keeps overwriting
#: itself. #1866 §5 needs the distribution, not the last value:
#: `MEASURED_WALL_MAX_S` is a known underestimate and cannot be corrected from
#: one sample; the publish gate's registered halt is `expired` **per pass**; and
#: #1996 needs no-ops counted rather than discarded.
#:
#: Hence a ring of PASSES ONLY (32 — at the measured ~74 s period that is ~40
#: minutes of history, enough for a wall distribution and short enough that the
#: memory cost is fixed) plus COUNTERS for the skips, so a no-op is counted and
#: not merely absent. Three states, never two: a Redis that cannot answer, a
#: Redis that answers with nothing, and real data are three different findings
#: (gotcha #53), and `app/utils/typeahead_pass_ring.py` keeps them apart.
_PASS_RING_KEY = "bainluck:typeahead_warmer:pass_ring"

#: 32 entries. Bounded by LTRIM on every write rather than by TTL, for the same
#: reason `redis_state._push_duration` is: on an `allkeys-lru` instance an
#: unbounded key does not merely cost memory, it evicts other people's keys.
_PASS_RING_MAX = 32

#: How many head terms each ring record carries (LAT-P078/#1866).
#:
#: The ring records the head so a client probe is ATTRIBUTABLE — "was the term I
#: measured actually in the warmed set" was unanswerable from production for four
#: cycles, and answering it wrong is what produced the withdrawn 80% -> 0% result.
#: Truncated at 12 of 40 because the ring is 32 records deep on an `allkeys-lru`
#: instance where an oversized key evicts other people's data (the same reason
#: `_PASS_RING_MAX` exists), and because the question the ring answers needs a
#: sample of the head, not a transcript of it. `head_n` carries the true length,
#: so a truncated list can never be mistaken for a short head.
_RING_HEAD_SAMPLE = 12

#: Skip counters + the most recent outcome OF ANY KIND. The last-outcome slot is
#: what makes "the warmer is skipping every beat" distinguishable from "the
#: warmer has not run at all" without waiting for the ring to fill.
_WARMER_STATE_KEY = "bainluck:typeahead_warmer:state"

#: Long enough to survive a quiet night, short enough that a dead warmer's last
#: word ages out instead of being read as current. The reader reports the age of
#: every record it returns, so a stale ring is visible rather than silent.
_PASS_RING_TTL_SECONDS = 86400

#: `/typeahead`'s response-cache key, mirrored from `routes/events.py`. Mirrored
#: rather than imported for the same reason `_MAX_QUERY_CHARS` is — importing
#: the route at module scope would make this task's import graph the route's.
#: `test_typeahead_warmer.py` pins the two against each other, so a drift is a
#: red test rather than a warmer that silently refreshes a key nobody reads.
_CACHE_KEY_PREFIX = "bainluck:typeahead:"

#: Redis `TTL` sentinels, named because `-2` and `-1` at a call site are two
#: magic numbers that mean opposite things.
_TTL_NO_KEY = -2
_TTL_NO_EXPIRY = -1

#: Only used when BOTH measured sources are empty (fresh Redis + empty table).
#: Kept deliberately tiny: a static list is a guess about user behaviour, and a
#: long guess is a long wrong answer that also costs real query time every run.
_STATIC_FLOOR: tuple[str, ...] = (
    "world series",
    "stanley cup",
    "world cup",
    "super bowl",
    "nba champion",
)

#: `/typeahead` enforces this itself (`min_length=2`). A shorter string would be
#: rejected by the route, so warming it would burn a slot to raise a 422.
_MIN_QUERY_CHARS = 2

#: Single-run lock. At a 30s cadence a COLD run (every query paying a real disk
#: read) can outlast its own interval, and without this the next beat starts a
#: second copy doing the identical work against the same already-loaded pages —
#: doubling the load at exactly the moment the database is slowest.
_LOCK_KEY = "bainluck:typeahead_warmer:running"

#: Longer than a plausible cold run, short enough that a worker killed mid-run
#: (the 300s hard SIGKILL that records as `no_data`) cannot wedge the warmer
#: off permanently. A lock nobody can release is worse than no lock.
_LOCK_TTL_SECONDS = 120

#: `/typeahead`'s `max_length`. Mirrored rather than imported to keep this module
#: importable without pulling the route in at module scope; the test asserts the
#: two agree, so a drift is a red test rather than a silent 422 every run.
_MAX_QUERY_CHARS = 200


def _head_from_redis(limit: int) -> list[str]:
    """The live `/typeahead` distribution, over a window that is really 24h.

    LAT-P080B/#2072: this used to `zrevrange` one immortal zset. The route
    re-`expire`d that key on every write, so it never rolled and the top-40 was
    an all-time ranking — a term popular ONCE outranked a term popular NOW,
    permanently. That is why #1866's loop-break was necessary but not
    sufficient: it stopped the warmer voting for its own head while the ~5,400
    already-accumulated scores went on selecting the same terms.
    """
    try:
        from app.tasks.redis_state import get_redis_client
        from app.utils.search_trending import read_window

        rows = read_window(get_redis_client(), limit)
    except Exception:  # noqa: BLE001 — a warmer never takes the app down
        logger.warning("typeahead_warmer: trending window unreadable", exc_info=True)
        return []

    out = []
    for query, _score in rows or []:
        q = str(query).strip().lower()
        if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS:
            out.append(q)
    return out


async def _head_from_query_log(session, limit: int) -> list[str]:
    """The /search log's 30-day head — a real distribution, a different surface.

    Second rather than first precisely BECAUSE it is a different surface: it
    records `/api/events/search`, while the zset records `/typeahead`. Both are
    measured; the one that measures the endpoint being warmed wins.
    """
    from sqlalchemy import text

    try:
        result = await session.execute(
            text(
                """
                SELECT lower(btrim(query)) AS q
                FROM search_query_logs
                WHERE created_at >= now() - interval '30 days'
                  AND length(btrim(query)) BETWEEN :lo AND :hi
                GROUP BY 1
                ORDER BY count(*) DESC
                LIMIT :lim
                """
            ),
            {"lo": _MIN_QUERY_CHARS, "hi": _MAX_QUERY_CHARS, "lim": limit},
        )
        return [row[0] for row in result.all() if row[0]]
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: query-log head unreadable", exc_info=True)
        await session.rollback()
        return []


#: Share of the warm budget reserved for the `/search` log's head.
#:
#: NOT a taste call. The two sources are not equally trustworthy and the reason
#: is structural (LAT-P078/#1866):
#:
#: * `search_query_logs` is written ONLY by `/search` (`_log_search_query`), which
#:   the warmer never calls. It is time-windowed by its own query (30 days) and
#:   records SUBMITTED intent.
#:
#:   🔴 **"Nothing in this system can pollute it" — THAT SENTENCE USED TO BE HERE
#:   AND IT IS FALSE.** Measured 2026-08-29 (LAT-P117): of 4,257 rows in the
#:   30-day window, **13 are attested** (a `session_id` or a `user_id`) and
#:   **4,244 are not** — the table is 99.7 % machine. The polluter is not a
#:   warmer, which is why the #1866 suppression above does not catch it: the
#:   **Flow Sentinel** (`tasks/flow_sentinel.py`, nightly 07:10 UTC) submits its
#:   33-query `GOLD_SET` + `GOLD_SET_TOP1` over **HTTP** via `httpx`, so the
#:   in-process `_suppress_search_log` ContextVar cannot reach it. The signature
#:   is arithmetic, not correlation: hour 07 UTC is the single largest hour for
#:   the whole head, at exactly 30 rows / 30 days for a term in ONE gold set and
#:   exactly 60 for `masters winner`, which is in BOTH. **18 of the top 25 terms
#:   are literally gold-set entries.** So this arm's guaranteed half is elected
#:   by our own nightly checklist.
#:
#:   IT IS STILL NOT REMOVED, AND THAT IS A FINDING RATHER THAN AN OMISSION. On
#:   a site with ~13 real searches a month there is no demand signal to replace
#:   it with: the attested head is **7 queries**, several of them (`orenburg`,
#:   `bridesmaid`, `pregnancy`) other harnesses' probes, so filtering this arm to
#:   attested rows would cut it 20 -> ~7 and — because `_blend_heads`' share is a
#:   FLOOR and the zset arm reads empty in production — would warm FEWER terms
#:   than today. The gold set is, by accident, a defensible warm list: it was
#:   chosen to be representative user intents. Parked P117-2 with the numbers;
#:   do not "fix" this without a demand signal to put in its place.
#: * `search:trending:24h` is written by `/typeahead`, which the warmer DOES call
#:   — it was a closed loop until the suppression in `routes/events.py` landed.
#:   Its scores were also all-time rather than 24h, because the route
#:   re-`expire`d the key on every write so it never rolled; hour-bucketed in
#:   LAT-P080B (#2072), so this arm now selects on recent volume. The share
#:   below is unchanged by that fix: the argument for a guaranteed half was
#:   never about decay, it was about which surface each source measures.
#:
#: So the query log gets a GUARANTEED half of the budget, which is what makes the
#: real head reachable at all, and the zset keeps the other half because it is
#: the only source that measures the surface actually being warmed — the prefixes
#: a user passes THROUGH on the way to a phrase, which `/search` never sees.
#: Neither is allowed to be the whole answer.
_QUERY_LOG_SHARE = 0.5


def _blend_heads(log_head: list[str], zset_head: list[str], limit: int) -> list[str]:
    """Merge two measured heads into one budget, deduped, order-stable.

    The query-log reservation is a FLOOR, not a quota: if the zset is short, the
    log fills the remainder, and vice versa. A budget that went unspent because
    one source ran dry would warm fewer terms than the previous code did, which
    would make this change a regression on exactly the metric it exists to move.
    """
    if limit <= 0:
        return []

    reserved = min(len(log_head), max(1, round(limit * _QUERY_LOG_SHARE)))

    out: list[str] = []
    seen: set[str] = set()

    def _take(source: list[str], upto: int) -> None:
        for q in source:
            if len(out) >= upto:
                return
            if q and q not in seen:
                seen.add(q)
                out.append(q)

    _take(log_head, reserved)
    _take(zset_head, limit)
    # Backfill from whichever source still has terms — the zset half may have
    # been mostly duplicates of the log half, which is the EXPECTED steady state
    # once the real head is being warmed and therefore starts trending too.
    _take(log_head, limit)
    return out[:limit]


async def resolve_head(session, limit: int) -> tuple[list[str], str]:
    """Return `(queries, source)`. `source` is reported so a run is attributable.

    Falling back is not a silent degradation here — which source produced the
    head changes what the run MEANS, so it travels in the summary rather than
    being inferred from the query list.

    🔴 LAT-P078/#1866: this was a strict first-non-empty CASCADE, and that is the
    defect. `_head_from_redis` is never empty in production, so the query-log arm
    below was unreachable code and `search_query_logs` — the only unpolluted
    measurement of real user intent in the system — had never selected a single
    warmed term. Measured 2026-08-21, the top four real queries by 30-day volume
    were `masters winner` (102), `stanley cup` (101), `world series` (95),
    `nba champion` (90); the first, second and fourth were COLD at 4.0s, 4.9s and
    5.2s against a <150ms budget, while `world series` was warm at 0.25s purely
    because it also happened to be locked into the zset. Both sources are real
    and they measure different surfaces, so both now select — a cascade was the
    wrong shape for two measurements of one population.
    """
    zset_head = _head_from_redis(limit)
    log_head = await _head_from_query_log(session, limit)

    if zset_head and log_head:
        blended = _blend_heads(log_head, zset_head, limit)
        n_log = sum(1 for q in blended if q in set(log_head))
        return blended, f"blend:query_log+trending:{n_log}/{len(blended)}_from_log"

    if zset_head:
        return zset_head[:limit], "redis:search:trending:24h"

    if log_head:
        return log_head[:limit], "db:search_query_logs:30d"

    return list(_STATIC_FLOOR[:limit]), "static_floor"


def _cache_ttl_seconds(q: str) -> int | None:
    """Remaining life of `/typeahead`'s cached answer for `q`, in seconds.

    Returns None when Redis cannot answer — and None means "do not skip", so an
    unreadable Redis degrades into the old always-rebuild behaviour rather than
    into a warmer that decides everything is fresh and stops working. Fails
    toward doing the work, exactly as `_acquire_run_lock` fails open.

    Redis TTL is THREE-VALUED and the two negatives mean opposite things, so
    they are returned distinctly rather than collapsed (gotcha #53 — an absent
    value and a zero value must never read the same):

        >= 0                 seconds of life remaining
        _TTL_NO_KEY   (-2)   nothing is cached; the route will miss on its own
        _TTL_NO_EXPIRY(-1)   a key with no expiry, which should be impossible
                             here and is treated as NEEDING a rebuild, not as
                             infinitely fresh — an entry that never expires is
                             a bug to correct, not a state to rest on
        None                 REDIS DID NOT ANSWER. Not a TTL at all.

    Collapsing the last one into "no key" was the first draft of this function
    and it would have made an unreadable Redis report a successful rebuild.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        ttl = get_redis_client().ttl(_CACHE_KEY_PREFIX + q)
    except Exception:  # noqa: BLE001 — a warmer never takes the app down
        logger.warning("typeahead_warmer: ttl read failed for %r", q, exc_info=True)
        return None

    return None if ttl is None else int(ttl)


async def _warm_one(session, q: str, refresh_ahead: int = REFRESH_AHEAD_SECONDS) -> dict:
    """Run ONE query through the route's own code path. Never raises."""
    from app.routes.events import (
        _force_cache_rebuild,
        _suppress_trending_write,
        typeahead_search,
    )

    # LAT-P078/#1866. Running the route's own code path is the point of this
    # function — it is what makes the warmed body byte-identical to the served
    # one — but the route's LAST act is to `zincrby` the query into
    # `search:trending:24h`, which is the zset `resolve_head` reads. Warming
    # therefore voted for its own head, ~1,700 times a day per term, and the
    # head could never change. Suppress the vote, keep the code path.
    _suppress_trending_write.set(True)

    started = time.monotonic()

    # REFRESH-AHEAD. Before LAT-P060 this call went straight to the route, which
    # returned the cached body without touching its TTL — so a "warm" of a warm
    # entry was a 16ms Redis GET that reset no clock, and 12 of every 50 beats
    # were exactly that. The entry is now REBUILT OVER when it is close enough to
    # expiry that it would not survive until the next pass.
    ttl_before = _cache_ttl_seconds(q)

    if ttl_before is not None and ttl_before > refresh_ahead:
        # Genuinely fresh. Reported as its own reason rather than folded into
        # `warmed`: a pass that skipped everything as fresh and a pass that
        # rebuilt everything must not produce the same summary.
        return {"q": q, "ok": True, "reason": "fresh",
                "ttl_before": ttl_before, "rebuilt": False, "ttl_after": ttl_before,
                "seconds": round(time.monotonic() - started, 3)}

    # 🔴 LAT-P134/#1866: REBUILD OVER THE ENTRY, NEVER DELETE IT FIRST.
    #
    # This used to be `_drop_cached(q)` — a Redis DELETE — because the route
    # writes its cache only on the miss path, so removing the entry was the only
    # way to make the route rebuild. LAT-P060 priced that hole at "~20ms, the HOT
    # cost, because the warmer keeps the pages resident". MEASURED on production
    # `8ca1e2ed` 2026-08-29, `celtics` + `lakers` (both confirmed warm head
    # terms), 70 samples through the real cache path with the non-voting origin
    # header: **p50 18-19ms, and 6 of 70 (8.6%) at 2,000-3,689ms**, spaced at the
    # pass period. The hole is two orders of magnitude wider than its estimate,
    # and it lands on the terms the warmer exists to keep fast.
    #
    # The estimate failed for a reason later measured elsewhere and never carried
    # back here: the rebuild is dominated by LAT-P096's un-indexed `to_tsvector`
    # scan over ~49.5k open markets, which is CPU. That cycle measured 27,483
    # buffer HITS — already resident — and still 742.7ms. Page residency was
    # never going to buy this back.
    #
    # `_force_cache_rebuild` makes the route skip the cache READ and keep the
    # cache WRITE, so the old answer is served continuously right up to the
    # instant the new one replaces it. Max staleness is UNCHANGED (the 65s TTL
    # governs both), and a rebuild that fails now leaves the previous answer
    # alive to its natural expiry instead of leaving a hole.
    #
    # Token + reset in `finally`, unlike `_suppress_trending_write` above: this
    # flag makes a request BYPASS THE CACHE, so a leak would be a real user
    # paying a full build. Per-task context copies already make that unreachable;
    # the reset makes it unreachable without depending on that argument.
    _force_token = _force_cache_rebuild.set(True)
    try:
        await asyncio.wait_for(
            # PASS THE DEBUG FLAGS EXPLICITLY. They default to `Query(False)`,
            # which is a FastAPI marker object and is TRUTHY — so omitting them
            # makes the route read `not debug_evidence` as False and skip BOTH
            # the cache read and the cache write. The warmer would then execute
            # the full query path, warm nothing into Redis, and report success:
            # a green run that did no warming, indistinguishable from a healthy
            # one (gotcha #53). `test_typeahead_warmer.py` pins this.
            typeahead_search(
                q=q,
                debug_evidence=False,
                debug_timing=False,
                db=session,
            ),
            timeout=PER_QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        # The route may have left an aborted transaction behind; the next query
        # on THIS session would fail on a poisoned one. Under concurrency each
        # worker owns its own session, so this contains the damage to one
        # worker's slice of the head instead of the whole pass — the
        # per-item-guard rule (gotcha #42) now holds at the session level too.
        await _safe_rollback(session)
        return {"q": q, "ok": False, "reason": "timeout",
                "ttl_before": ttl_before, "rebuilt": True, "ttl_after": None,
                "seconds": round(time.monotonic() - started, 3)}
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: %r failed", q, exc_info=True)
        await _safe_rollback(session)
        return {"q": q, "ok": False, "reason": "error",
                "ttl_before": ttl_before, "rebuilt": True, "ttl_after": None,
                "seconds": round(time.monotonic() - started, 3)}
    finally:
        _force_cache_rebuild.reset(_force_token)

    # 🔴 "IT RETURNED" IS NOT "IT WROTE" (`app/utils/task_verdict.py`, gotcha #53).
    #
    # The one way this change can fail silently is if the route stops honouring
    # `_force_cache_rebuild` — an import that resolves to a different module, a
    # future edit that moves the flag onto the WRITE condition too. The route
    # would then answer from the very entry we came to replace, return in ~18ms,
    # and this function would report `warmed`. That is precisely the `Query(False)`
    # trap above, wearing a new hat, so it gets a real check rather than a comment:
    # re-read the TTL and require that it actually moved up.
    #
    # `None` (Redis silent) is NOT a failure — it is an unreadable instrument, and
    # reporting `no_write` on it would turn a Redis blink into a fake defect. It
    # reports `warmed_unverified` so the pass can say how much of its own success
    # it could not check.
    ttl_after = _cache_ttl_seconds(q)
    if ttl_after is None:
        reason = "warmed_unverified"
    elif ttl_after > (ttl_before if ttl_before is not None and ttl_before >= 0 else -1):
        reason = "warmed"
    else:
        reason = "no_write"

    return {"q": q, "ok": reason != "no_write", "reason": reason,
            "ttl_before": ttl_before, "rebuilt": True, "ttl_after": ttl_after,
            "seconds": round(time.monotonic() - started, 3)}


def _acquire_run_lock() -> bool:
    """True if THIS run owns the lock. False means another run is in flight.

    Fails OPEN: if Redis is unreachable we warm anyway. The lock exists to stop
    duplicate work, not to enforce correctness — a doubled warm is wasteful, a
    warmer that silently stops warming because Redis blinked is the bug this
    whole file is about.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        return bool(rc.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS))
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: lock unavailable, warming anyway", exc_info=True)
        return True


def _release_run_lock() -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(_LOCK_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: lock release failed", exc_info=True)


def _seconds_since_last_pass(now: float) -> float | None:
    """Seconds since the previous pass STARTED, or None if that is unknown.

    None is returned for every reason a caller might otherwise conflate: no
    previous pass recorded, Redis unreadable, or a stored value that will not
    parse. All three mean the same thing to the floor — **do not suppress** —
    and none of them may be reported as a period of 0.0, which would read as
    two passes starting simultaneously (gotcha #53).
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(_LAST_PASS_START_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: last-pass read failed", exc_info=True)
        return None
    if raw is None:
        return None
    try:
        previous = float(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
    except (TypeError, ValueError):
        logger.warning("typeahead_warmer: last-pass value unparseable: %r", raw)
        return None
    delta = now - previous
    # A negative delta means the clock moved backwards or another dyno wrote a
    # future timestamp. Refuse it rather than let it read as "a pass just ran",
    # which would suppress this one.
    return delta if delta >= 0 else None


def _record_pass_start(now: float) -> None:
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().set(
            _LAST_PASS_START_KEY, repr(now), ex=_LAST_PASS_START_TTL_SECONDS
        )
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: last-pass write failed", exc_info=True)


def _pass_ring_record(summary: dict, at: float) -> dict:
    """The compact ring entry for one outcome. Pure, so the shape is testable.

    Deliberately a PROJECTION of the summary rather than the summary itself: the
    ring is read by an operator asking "is the wall distribution moving", and a
    32-deep list of full summaries (with `timeouts` and `errors` carrying query
    strings) is both larger and harder to read than the eight numbers that
    answer the question. `timeouts`/`errors` are kept as COUNTS, because their
    presence changes how a wall should be read and their contents do not.
    """
    return {
        "at": round(at, 3),
        "terminal": summary.get("terminal"),
        "skip_reason": summary.get("skip_reason"),
        "seconds_wall": summary.get("seconds_wall"),
        "period_s": summary.get("period_s"),
        "expired": summary.get("expired"),
        "rebuilt": summary.get("rebuilt"),
        "fresh": summary.get("fresh"),
        "warmed": summary.get("warmed"),
        "total": summary.get("total"),
        "concurrency": summary.get("concurrency"),
        "head_source": summary.get("head_source"),
        # LAT-P078/#1866. `head_source` names the SOURCE; this names the SET.
        # Without it no client probe is attributable: LAT-P077 spent a window
        # measuring five `_STATIC_FLOOR` strings believing they were the warmed
        # set, and the resulting 80% -> 0% -> 45% swing was head composition
        # wearing a warmer-health label. Truncated because the ring is read by a
        # human and 40 phrases per record is a wall, not an instrument; the
        # prefix is enough to answer "was the thing I probed in the head".
        "head": list(summary.get("head") or ())[:_RING_HEAD_SAMPLE],
        "head_n": len(summary.get("head") or ()),
        "timeouts": len(summary.get("timeouts") or ()),
        "errors": len(summary.get("errors") or ()),
    }


def _record_outcome(summary: dict, now: float | None = None) -> None:
    """Persist one outcome so production can read it. Best-effort, never raises.

    ⚠️ **This must never be the reason a pass fails.** The warmer's contract is
    that it is not load-bearing — a cold miss still builds inline in the route —
    and an instrument that can break the thing it measures is worse than no
    instrument. So every path here swallows, logs, and returns.

    A REAL PASS goes on the ring; a SKIP increments its own counter. Both update
    the last-outcome slot, because "the last thing that happened was a no-op" is
    an answer and its absence is a different answer.
    """
    at = time.time() if now is None else now
    record = _pass_ring_record(summary, at)
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        pipe = rc.pipeline()
        pipe.hset(
            _WARMER_STATE_KEY,
            mapping={"last_outcome": _json_dumps(record), "last_outcome_at": repr(at)},
        )
        if summary.get("terminal") == "skipped":
            # A skip is COUNTED, not ringed. Counting is what makes the no-op
            # share readable; ringing them would flush the pass history out of a
            # 32-deep list inside twenty minutes, since two thirds of executions
            # are skips (measured, see `_PASS_RING_KEY`).
            reason = summary.get("skip_reason") or "unknown"
            pipe.hincrby(_WARMER_STATE_KEY, f"skips:{reason}", 1)
        else:
            pipe.lpush(_PASS_RING_KEY, _json_dumps(record))
            pipe.ltrim(_PASS_RING_KEY, 0, _PASS_RING_MAX - 1)
            pipe.expire(_PASS_RING_KEY, _PASS_RING_TTL_SECONDS)
        pipe.expire(_WARMER_STATE_KEY, _PASS_RING_TTL_SECONDS)
        pipe.execute()
    except Exception:  # noqa: BLE001 — an instrument never breaks its subject
        logger.warning("typeahead_warmer: outcome record failed", exc_info=True)


def _json_dumps(obj) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


async def _safe_rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001
        logger.warning("typeahead_warmer: rollback failed", exc_info=True)


async def _warm_head_concurrently(sessions: list, head: list[str]) -> list[dict]:
    """Warm `head` across `sessions`, one query in flight per session.

    A worker-pool over a shared cursor rather than a per-worker slice, because
    slices assume the queries cost the same and they do not — `seconds_max` was
    5.6s against a ~1.0s mean, so one slow query in a static slice idles its
    worker's whole remainder while another worker still has ten to go. Pulling
    from a shared cursor is self-balancing and needs no estimate.

    ONE query in flight per session is a hard invariant, not a tuning choice:
    an `AsyncSession` is not safe for concurrent use, so a second coroutine on
    the same session is a corruption bug, not a slowdown. The pool's width IS
    the session count for that reason.
    """
    cursor = iter(range(len(head)))
    results: list[dict | None] = [None] * len(head)

    async def _worker(session) -> None:
        for i in cursor:  # a shared iterator; next() is atomic under the GIL
            results[i] = await _warm_one(session, head[i])

    await asyncio.gather(*(_worker(s) for s in sessions))

    # Order is preserved by index, so the summary reads in head order rather
    # than in completion order — otherwise two identical passes would produce
    # differently-ordered evidence and diffing them would be noise.
    return [r for r in results if r is not None]


async def _warm_typeahead(
    queries: list[str] | None = None,
    head_size: int = DEFAULT_HEAD_SIZE,
    concurrency: int = WARM_CONCURRENCY,
) -> dict:
    """Warm the head of the `/typeahead` distribution. Returns a contract summary.

    The summary speaks the `task_verdict` vocabulary (`terminal` +
    `completed`/`total` + `errors`), and a run that warmed NOTHING reports
    `partial` with `total: 0` rather than a clean `complete`. A warmer whose
    entire purpose is that the head is hot must not be able to report success
    while it is cold — that is the ten-week failure `app/utils/task_verdict.py`
    exists to prevent.
    """
    from app.tasks.base import get_task_session

    def _no_work(skip_reason: str, period_s: float | None) -> dict:  # noqa: C901
        # A skip is an accounted-for outcome, not a success and not damage. It
        # gets a NO_WORK terminal so a warmer that skips every single beat
        # cannot hide inside `complete`, and it carries `skip_reason` so the two
        # skips are never conflated: "another pass is running" and "the previous
        # pass was too recent" are opposite diagnoses. A wedged lock and a
        # too-tight floor would otherwise produce the identical summary.
        out = {
            "terminal": "skipped",
            "skip_reason": skip_reason,
            "completed": 0,
            "total": 0,
            "head_source": "none",
            # Present and EMPTY, never absent — the same-keys contract. A skip
            # resolved no head, and "resolved nothing" is a different fact from
            # "this field does not exist on this shape".
            "head": [],
            "warmed": 0,
            "timeouts": [],
            "errors": [],
            "seconds_total": 0.0,
            "seconds_max": 0.0,
            # Same KEYS as a real pass, so a consumer never has to branch on
            # terminal to know whether a field exists. An absent field and a
            # zero field must not read the same (gotcha #53) — here they are
            # both present and both honestly zero.
            "seconds_wall": 0.0,
            "concurrency": max(1, int(concurrency)),
            "rebuilt": 0,
            "fresh": 0,
            # LAT-P134, same-keys contract: a skip wrote nothing and verified
            # nothing, and both facts are stated rather than left absent.
            "no_writes": [],
            "unverified": 0,
            "expired": 0,
            "refresh_ahead_s": REFRESH_AHEAD_SECONDS,
            # `None`, not 0.0, when the gap is unknown. Zero would read as two
            # passes starting at the same instant.
            "period_s": None if period_s is None else round(period_s, 3),
            "min_period_s": MIN_PASS_PERIOD_SECONDS,
        }
        # Recorded on the SKIP path too, and counted rather than ringed. A
        # warmer that skips every beat and a warmer that never fires are the
        # same silence on `last_result_summary`; they are different findings.
        _record_outcome(out)
        return out

    if not _acquire_run_lock():
        logger.info("typeahead_warmer: another run holds the lock, skipping")
        return _no_work("lock", None)

    # THE FLOOR, checked under the lock so two beats cannot both pass it. Read
    # after acquiring rather than before, because the check-then-act would
    # otherwise race exactly the way the lock exists to prevent.
    now = time.time()
    since_last = _seconds_since_last_pass(now)
    if since_last is not None and since_last < MIN_PASS_PERIOD_SECONDS:
        _release_run_lock()
        logger.info(
            "typeahead_warmer: last pass started %.1fs ago (floor %ds), skipping",
            since_last, MIN_PASS_PERIOD_SECONDS,
        )
        return _no_work("min_period", since_last)

    _record_pass_start(now)

    width = max(1, int(concurrency))
    wall_started = time.monotonic()
    try:
        async with AsyncExitStack() as stack:
            sessions = [
                await stack.enter_async_context(get_task_session())
                for _ in range(width)
            ]

            if queries is None:
                head, source = await resolve_head(sessions[0], head_size)
            else:
                head, source = [q.strip().lower() for q in queries], "explicit"

            head = [q for q in head if _MIN_QUERY_CHARS <= len(q) <= _MAX_QUERY_CHARS]

            results = await _warm_head_concurrently(sessions[:width], head)
    finally:
        _release_run_lock()
    seconds_wall = round(time.monotonic() - wall_started, 3)

    warmed = [r for r in results if r["ok"]]
    timeouts = [r for r in results if r["reason"] == "timeout"]
    errors = [r for r in results if r["reason"] == "error"]

    # LAT-P134. `warmed_unverified` DID rebuild — it is a `warmed` whose TTL
    # re-read came back from an unreadable Redis — so it belongs in `rebuilt`.
    # Folding it into `warmed` alone and leaving it out here would make a Redis
    # blink read as "the threshold did not fire", which is the opposite diagnosis.
    rebuilt = [r for r in results if r["reason"] in ("warmed", "warmed_unverified")]
    unverified = [r for r in results if r["reason"] == "warmed_unverified"]
    # 🔴 THE ROUTE RAN AND NOTHING WAS WRITTEN. Its own category, and it counts
    # against `terminal` below: a pass that warmed nothing must never report
    # `complete`. This is the state `_force_cache_rebuild` failing to reach the
    # route would produce, and the whole reason `_warm_one` re-reads the TTL.
    no_writes = [r for r in results if r["reason"] == "no_write"]
    fresh = [r for r in results if r["reason"] == "fresh"]
    # `_TTL_NO_KEY` exactly, never "falsy" and never "<= 0": `None` means Redis
    # did not answer and `_TTL_NO_EXPIRY` (-1) means a key with no expiry. All
    # three are non-positive and all three mean different things.
    expired = [r for r in results if r.get("ttl_before") == _TTL_NO_KEY]

    seconds = [r["seconds"] for r in results]
    summary = {
        # An empty head is a FAILURE of this task's purpose, not a quiet success.
        "terminal": (
            "complete"
            if head and not timeouts and not errors and not no_writes
            else "partial"
        ),
        "completed": len(warmed),
        "total": len(head),
        "head_source": source,
        # The SET, not just its provenance (LAT-P078/#1866). `_pass_ring_record`
        # truncates it for the ring; the full list stays in the return value so a
        # caller that wants all of it is not forced to re-derive the head.
        "head": list(head),
        "warmed": len(warmed),
        "timeouts": [r["q"] for r in timeouts],
        "errors": [r["q"] for r in errors],
        "seconds_total": round(sum(seconds), 3),
        "seconds_max": round(max(seconds), 3) if seconds else 0.0,
        # LAT-P060. `seconds_total` is the SUM of per-query times and is what it
        # always was, so it stays comparable across the concurrency change. It
        # is NO LONGER the pass duration — that is `seconds_wall`, and it is the
        # number the 45s TTL has to be compared against. Reporting only the sum
        # after adding concurrency would have shown a pass "not getting faster"
        # while the thing that matters halved.
        "seconds_wall": seconds_wall,
        "concurrency": width,
        # The two halves of hole 2, separated. `rebuilt` is work that actually
        # reset a TTL; `fresh` is work correctly skipped. Before LAT-P060 every
        # run reported `warmed: 40/40` whether it rebuilt forty entries or read
        # forty warm ones back, and 12 of every 50 beats were the latter.
        "rebuilt": len(rebuilt),
        "fresh": len(fresh),
        # LAT-P134. Both halves of "did the rebuild land", stated separately
        # because they are different verdicts: `no_write` is a DEFECT (the route
        # ran and Redis still holds no fresher entry), `unverified` is an
        # UNREADABLE INSTRUMENT (the TTL re-read failed). Collapsing them would
        # make a Redis blink indistinguishable from a broken warmer — the exact
        # conflation gotcha #53 names.
        "no_writes": [r["q"] for r in no_writes],
        "unverified": len(unverified),
        # `None` on a pass that RAN. Present on both shapes because the summary
        # contract is that a consumer never branches on `terminal` to know
        # whether a field exists — `test_a_skipped_run_carries_the_same_keys_as_
        # a_real_one` is that contract, and it caught this field the first time
        # it was added to only one shape.
        "skip_reason": None,
        # LAT-P062. `rebuilt` cannot distinguish an entry that was ALIVE-but-
        # stale from one that was ALREADY DEAD when the pass reached it, and
        # those are opposite diagnoses: the first says the threshold fired as
        # designed, the second says the head was cold and a user typing that
        # prefix paid a database read. Every duty-cycle grade so far has had to
        # infer this from a client probe. `expired` is the pass answering it
        # directly — `ttl_before == -2`, i.e. no key at all.
        "expired": len(expired),
        "refresh_ahead_s": REFRESH_AHEAD_SECONDS,
        # The number the 45s TTL actually has to be compared against, and the
        # one the task could not previously state about itself. `None` when the
        # previous start is unknown (first pass after a restart, or Redis
        # unreadable) — never 0.0, which would read as a zero-length period.
        "period_s": None if since_last is None else round(since_last, 3),
        "min_period_s": MIN_PASS_PERIOD_SECONDS,
    }
    # LAT-P074 (#1866). The pass joins the bounded ring so the WALL and PERIOD
    # distributions — not just the last value — are readable from production.
    # Placed after the summary is complete and before the log, so a ring entry
    # and its log line can never disagree.
    _record_outcome(summary)
    logger.info(
        "typeahead_warmer: %d/%d warmed from %s (%d rebuilt, %d fresh, %d expired) "
        "in %.1fs wall / %.1fs summed at width %d, %s since last pass "
        "(%d timeouts, %d errors)",
        len(warmed), len(head), source, len(rebuilt), len(fresh), len(expired),
        seconds_wall, summary["seconds_total"], width,
        "unknown" if since_last is None else f"{since_last:.1f}s",
        len(timeouts), len(errors),
    )
    return summary
