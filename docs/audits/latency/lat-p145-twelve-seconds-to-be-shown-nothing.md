# LAT-P145 — twelve seconds to be shown nothing

**Pillar:** FORMATTING / DISCOVER (team pages — the surface one tap from search).
**Ship:** *An NFL team's page stops making you wait twelve seconds and then showing
you nothing.*

Issue: filed this cycle. Parent: **#1249**, which named this exact symptom and was
closed by LAT-P138 — while the symptom went on happening in production every day.

---

## 1. How it was found

The standing coldpath ranking, taken from `/api/admin/latency-slow-events?limit=500`
(the >5 s ring, 500/500 used, oldest 6.05 days) on production `944c466e`:

| n | p50 ms | max ms | Σ s | path | banked fix? |
|--:|-------:|-------:|----:|------|---|
| 118 | 6,953 | 30,607 | 1,106 | `/api/feed` | LAT-P141 (`-126`) |
| 58 | 14,553 | 25,807 | 892 | `/api/playoffs/{league_slug}` | — but `program/ux-131` holds +109/−30 in `routes/playoffs.py` |
| 60 | 8,807 | 36,272 | 881 | `/api/events/{event_id}/related-futures` | LAT-P144 (`-129`) |
| 99 | 6,640 | 10,260 | 730 | `/api/events/typeahead` | LAT-P143 (`-128`) |
| 25 | 14,517 | 28,164 | 405 | `/api/event/{key}` | — |
| **31** | **12,076** | **19,234** | **344** | **`/api/teams/{identifier}/prop-families`** | **— this queue** |

Ranked by 24-hour recency rather than by six-day total, prop-families is the top
un-banked, un-colliding path: **30 of its 31 slow requests are in the last 24 h**,
all of them AFTER LAT-P138 (merge `9af8700a`, 2026-08-29 21:05 PT) was live.

`/api/playoffs` is bigger and is deliberately NOT this queue's subject: `program/ux-131`
carries a live `ready` token with 109 added lines in `routes/playoffs.py`, and two
sessions on one route file is the Parallel Work Protocol's RED.

## 2. The signature, and what it is not

Two clusters in the prop-families population, and they are different events:

```
04:52:52   19,234 ms  db=19,193  app=41      q=5   maxq=11,901     <- a build that SUCCEEDED
04:49:00   12,124 ms  db=    56  app=12,067  q=3   maxq=30         <- a build that was CANCELLED
04:49:13   12,119 ms  db=    59  app=12,060  q=3   maxq=41
04:49:25   12,082 ms  db=    16  app=12,067  q=3   maxq=9
   ... 13 requests, 04:49:00 -> 04:53:04, every one 12,074-12,195 ms ...
```

`app_ms` ≈ the entire wall with `db_ms` in the tens is **not** slow Python, GIL
contention or pool starvation. `request_timing.py` builds `db_ms` from SQLAlchemy's
`after_cursor_execute`, and that event does not fire when the cursor raises — so a
statement killed by `SET LOCAL statement_timeout` contributes **zero** to `db_ms` and
its whole duration is billed to the application. The route's own header says so
outright, and this is the first cycle where it has: `unfinished=1`.

Reproduced live, three teams, first read and every read after it:

```
new-york-giants      12,638 ms  wall=12,376  db=281  app=12,096  q=3  unfinished=1  families 0  NO envelope
green-bay-packers    12,658 ms  wall=12,375  db=267  app=12,109  q=3  unfinished=1  families 0  NO envelope
pittsburgh-steelers  12,908 ms  wall=12,389  db=284  app=12,106  q=3  unfinished=1  families 0  NO envelope
```

Three warmed teams, for contrast, in the same minute: `nc-state-wolfpack` 178 ms,
`clemson-tigers` 49 ms, `kansas-city-chiefs` 29 ms — all `stale_ok`, all served from
the mirror LAT-P138 built.

## 3. `q=3` is the finding

`queries` counts statements that COMPLETED, and a cancelled one is not among them. So
the three that finished are the team lookup, the `SET LOCAL`, and **the `team_id`
branch** — which had already returned its rows when the outcome-name branch was
cancelled 12 seconds later. Counted on production in the same minute:

| team | roster | `team_id` branch rows |
|---|--:|--:|
| New York Giants | 80 | **27** |
| Green Bay Packers | 78 | **29** |
| Pittsburgh Steelers | 73 | **31** |

Postgres aborts a transaction whose statement is cancelled. All three branches ran
inside one transaction under one `SET LOCAL`, and the handler that caught the expiry
returned an empty payload. So one 12-second expiry did three things at once:

1. lost branch 2's rows (the ones it was actually waiting for);
2. made branch 3 **unrunnable** — the market-name branch never even executed;
3. **threw away branch 1's 27 rows**, which were already fetched and in memory.

And then, correctly, it cached nothing — `build_and_cache_prop_families` refuses to
put a timeout's empty page behind a 24 h mirror (gotcha #53). Which means the next
reader repeated all of it. That is the 13-request, four-minute, 12-seconds-each
cluster: a page that is permanently slow **because** it is permanently empty.

`backfill_winners.py` already has this lesson written down, about itself:

> *"A budget guard that takes down the parts AFTER it is not a budget guard, it is a
> new failure mode (gotcha #42 in another costume)."*

Here it took down the part BEFORE it as well.

## 4. Who is in the population

The warmer's reachable set is `roster IS NOT NULL AND a fixture within −1/+14 days`.
Measured on production, 2026-08-30:

```
9,625  teams
  367  have a non-empty roster        <- the only ones that can be slow
   82  ALSO have a fixture in ±14d    <- warmed, and demonstrably fast
  285  rostered, NOT warmed           <- pay the build themselves
```

In late August those 285 include most of the NFL — the Giants, Packers, Steelers,
Commanders, Broncos, Eagles, Cardinals and Panthers were all in it, because their
season was more than a fortnight out. Which team is fast is therefore an accident of
the schedule and not of anything a reader can see: the Chiefs (Week 1 inside the
window) served in 29 ms while the Giants served nothing in 12.6 seconds.

## 5. Why the branch is slow, measured rather than assumed

`EXPLAIN (ANALYZE, BUFFERS)` on the Giants' own 41 patterns, production, 25 s budget:

| branch | duration | rows | read blocks | of which I/O wait |
|---|--:|--:|--:|--:|
| outcome-name | **8,196 ms** | 103 | 11,959 | **7,387 ms (92 %)** |
| market-name | **1,771 ms** | 29 | 1,931 | 1,170 ms (66 %) |

The branch is not CPU-bound and it is not badly planned — it is a bitmap heap scan
that has to read twelve thousand blocks off disk. That is why it sits *on* the 12 s
cliff rather than safely under it: the same query measured 8.2 s here and 12.1 s
through the route minutes apart, which is buffer state, exactly as LAT-P144 saw on
the sibling tier (2,754 → 11,924 ms across three runs in one minute).

**This queue does not touch the query.** Making it cheaper needs an index, an index
needs a migration, and the branch's cost is not the defect — the defect is what the
route does when it expires.

## 6. What changed

Each branch now runs bounded, materialised and contained:

* **its own `SET LOCAL`, in its own transaction, at the same 12,000 ms.** The budget
  is deliberately unchanged in value and in meaning. A cheaper-looking fix would have
  been to shorten it, and that would have bought the win by making complete builds
  fail — so `_BRANCH_TIMEOUT_MS == 12000` is asserted by a guard AND attacked by a
  mutant.
* **rows copied to plain dicts before the next branch can roll back.** A rollback
  expires every ORM object in the session and `expire_on_commit=False` does not
  prevent it (gotcha #6); the team's own `id`/`name`/`slug` are read before the first
  branch runs, for the same reason.
* **an expiry recorded as `LOSS_PARTIAL` and the loop CONTINUED**, so branch 3 gets
  its turn.

The severity is the existing envelope contract's, not a new one: `LOSS_PARTIAL` is
defined as *"real content is missing, but the headline answer survived"*, which is
precisely a team that has its own futures but not its player props.

Three outcomes where there used to be two:

| build | stored | served |
|---|---|---|
| full | primary + 24 h mirror | `quality: full` |
| partial, has rows | primary; mirror only if the stored mirror is not `full` | `quality: partial`, `quality_reasons: ["branch_timeout:outcome_name"]` |
| nothing at all | **nothing** | empty, no envelope — unchanged |

The mirror guard is the module's own rule one notch out. `event_concept_cache` already
says an empty build never overwrites a good mirror; a partial is not empty, but it is
*less*, and freezing it for 24 hours on top of a complete answer would make this fix
cost warmed teams their content. `write_payload` grew one additive keyword,
`mirror=True` by default, so no existing customer changes behaviour.

Containment stays narrow. `is_statement_timeout` walks the `__cause__` chain, matches
the driver's class name first and its message second, and everything else is logged
at `exception` level — a real query defect must not be filed as "ran out of time"
(gotcha #45).

## 7. What a reader gets, stated honestly

For the Giants, per the measurements in §3 and §5:

| | before | after |
|---|---|---|
| first read | 12.4 s | **~14.2 s** (12 s expiry + the 1.8 s branch that can now run) |
| content | **0 families** | the `team_id` branch's 27 outcomes **+** the market-name branch's 29 |
| every read after the first | 12.4 s, forever | **~30 ms**, from cache |
| envelope | absent — indistinguishable from "no props" | `quality: partial`, naming the branch that expired |

The first read gets **slower**, and that is a real cost, not a rounding error: branch 3
now executes where before it was unreachable. It is the right trade — the reader waits
1.8 s longer once, in exchange for content instead of a blank section and for every
subsequent reader paying 30 ms instead of 12.4 s — but it is a trade and the READY
token says so where the Integrator will read it.

## 8. Ruled out, measured rather than assumed

* **Shorten the branch budget so the whole request is bounded.** Would cap the first
  read at 12.4 s *and* keep the content, if the cheap branch ran first. But the
  successful builds in the same ring run to 19.2 s of database time, and a 12 s total
  would turn those into partials — trading a real completeness regression for 1.8 s.
  Parked as **P145-1**, with the branch costs above already in hand.
* **Reorder the branches cheapest-first.** Saves nothing on its own: the 12 s expiry
  is paid whichever position it is in. Only pays off combined with P145-1.
* **Index the trigram branch.** An index is a migration; appended to the standing slot
  request as **P145-3**. Note LAT-P144's finding still binds — the collation is
  `en_US.UTF-8`, so the obvious prefix rewrite is 470× faster and returns the wrong
  rows.
* **Widen the warmer's reachable set to all 367 rostered teams.** The cleanest user
  outcome — nobody would ever pay a build. The coverage arithmetic does not close: at
  the pessimistic `SLOWEST_MEASURED_BUILD_SECONDS = 17`, a 180 s hourly pass clears 10
  teams, so 367 teams need 37 hours against a 24 h mirror. It needs either a bigger
  budget or a faster build, and both are their own measurement. Parked as **P145-4**.

## 9. Parked

* **P145-1** — bound the whole build, cheapest branch first. §8.
* **P145-2** — fold `backfill_winners._is_statement_timeout` into the new shared
  `app/utils/statement_timeout.py`. Ruling 005 says the second customer collapses the
  duplicate; `backfill_winners.py` is carried by the unmerged, cert-held
  `program/calibration-118`, and a two-line edit there would hand the Integrator a
  conflict in a 7,000-line file. Unblocks the moment that branch lands.
* **P145-3** — a trigram index for the name branches. Migration slot.
* **P145-4** — the warmer's reachable set vs the 24 h mirror. §8.
* **P145-5** — `/api/playoffs/{league_slug}`: 58 slow requests, p50 14.5 s, **zero
  caching of any kind**, 51 of them in the last 24 h. The biggest un-banked path on
  the board, held only by the `program/ux-131` collision. First in line once that
  branch merges.

## 10. Two findings the gates produced

**The residue scan caught three anchors this change had drifted.** Renaming
`branch_conds` to `branches` silently invalidated `prop_families_cache_mutations`
M1, M2 and M13 — LAT-P138's own battery. Pass A reported them as *harness drift, not
residue*: the mutants would have scored NOT-APPLIED, never a false kill, so the
battery would have gone on printing a clean line while pinning three fewer things
than it claimed. Re-targeted, and the re-target verified by re-running that battery
to 29/29 killed rather than by reading it.

**Three of this battery's own mutants survived the first run, and all three were
equivalent** — recorded in the harness header rather than deleted, because "the suite
has a hole" and "this mutation cannot change behaviour" are indistinguishable from the
exit code. The one worth repeating: dropping the cross-branch `_seen_oids` dedup is
**unobservable**, because `group_prop_families` collapses rows by entity and a
duplicate outcome id is the same database row collapsing onto itself — measured, same
fixture deduped and tripled, byte-identical output. That dedup bounds work, not
output; no assertion could have made it a correctness property.
