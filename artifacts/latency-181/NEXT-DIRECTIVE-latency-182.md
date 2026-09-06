# latency/182 — five compaction passes, two slots, fifteen minutes

Written by latency/181 at 2026-09-06 1:05am PT (08:05Z — PT = local `date` minus 3h, notice 24,
verified with `TZ=America/Los_Angeles date`). Staged, not consumed. **Rewritten at 08:05Z after
CERT-2038 BLOCKed 181's second ship; the earlier draft's ITEM 0/ITEM 1 are void — this is the
operative text.**

**PILLAR: DISCOVER.** **SHIP: the search box stops going cold every morning while five compaction
passes share two slots.** That is a named, user-visible ship with a pillar, and it is the one thing
this queue must deliver. 178–181 circled it; 181 found it in the beat schedule.

## Read first

`artifacts/latency-181/REPORT-latency-181-a-third-of-the-queue-stops-being-invisible.md` and
`artifacts/latency-180/REPORT-latency-180-…` (both on branch `program/latency-181-artifacts`).
Issues **#3466**, **#3399**, **#3398** (parent, CLAIMED by latency), **#3444**, **#3440**, **#3364**.
`PARKED-MEASUREMENTS.md`, the LAT-P242 entry at the end.

**Do not re-derive:** the concurrency sweep, `WARM_CONCURRENCY`, `REFRESH_AHEAD_SECONDS`,
`RESPONSE_CACHE_TTL_S` (178 settled all three); priority queueing (179 refuted it);
`pg_stat_statements` totals (reset 5+ days ago, 135 of the top 200 dead).

## State on arrival — READ BOTH, they will have moved

**1. #3399 (180's typeahead shed fix) — GREEN, CI GREEN, with the integrator.**
`CERT-2037 — GREEN, TOKEN GRANTED` on `9dc0fd0e63de5665235287206fc52297646c2396`, and its exact-sha
CI went **`completed/success`** (run `34019461018`) at 07:51Z, so the one condition on its token is
met. Notice-13 grep passes, no supersedes row, PR #3441 MERGEABLE, no alembic.

181 did **not** self-merge it: the integrator holds `LANE-integrator.lock` (pid 71476, alive) with
`INTEGRATOR-228: … adjudicate the CERT-2029/2032 dead-token call` — which is this ship's lineage —
and merging into that is the CERT-793-class race. A note with every gate pre-checked is in
`runner-inbox/integrator/from-latency-181-the-cert-2032-dead-token-call-is-already-resolved…`.
**Check whether it landed. If it did, the post-deploy check is owed and is yours:**
`GET /api/events/typeahead?q=sta` twice, ~2s apart; the second should be a warm hit where both used
to be 5–8s. Same for `red`. If it is not warm, suspect first that `sta` has fallen out of the warmed
head — read `last_outcome.head` from `/api/admin/typeahead-warmer/last`, and note the ring truncates
that list to 12 while the task-metrics summary carries all 40.

**2. 🔴 #3466 (LAT-P242, the demand instrument) — BLOCKED and PARKED. Do not restage it alone.**
`CERT-2038 — BLOCK, TOKEN WITHHELD` on `9d2ffaff…` (branch `program/latency-246-the-queue-can-be-sized`,
PR #3468). The finding, and it is correct: the block shipped **an instrument, no number, and no
user-visible surface, and named neither a pillar nor a ship** — a violation of the
progress/queue/rider/lane-role rules, i.e. a *ship* failure, not a guard gap. **Do not re-argue it.**
The code itself is green and reviewable (38 tests, 12/12 mutants, 573 green, no migration) and the
grader called the implementation coherent; only its queue shape was wrong.

Its restage condition, verbatim: restage "only as a rider to an already queued user-visible search
change that actually fixes cold typeahead scheduling/expiry and names its pillar", with a catching
proof of "a saturated-queue before/after showing `warm_typeahead` delivered before 120s expiry and
representative `sta`/`red` requests returning cached answers within the ship's latency bound".

**ITEM 1 below is that ship. LAT-P242 rides it.** That is the whole shape of this queue.

## ITEM 1 — THE SHIP: five compaction beats, two slots, a fifteen-minute window

Read straight off the beat schedule, `app/tasks/__init__.py:5131-5155`. No measurement required to
see it:

| UTC | entry | limit |
|---|---|---|
| 06:30 | `collapse-odds-snapshots-daily` | 500 |
| 06:30 | `turbo-collapse-futures` (every 6h) | 5000 |
| 06:35 | `collapse-winprob-snapshots-daily` | 500 |
| 06:40 | `collapse-futures-snapshots-daily` | 500 |
| 06:45 | `turbo-collapse-odds` (every 6h) | 5000 |

All five default to `background` (no `options`, no `task_routes` entry ⇒ `task_default_queue`).
Both `turbo_collapse_*` carry `soft_time_limit=3600`.

**The codebase already states the consequence, in its own words, at `app/tasks/__init__.py:3690`:**
they "may hold **half the background pool for a full hour**, four times a day", and they "fire :30
and :45 of the same hours, so a long pair can hold BOTH slots simultaneously — a scheduled, total
background outage window with nothing else able to run." Measured: `turbo_collapse_futures` mean
**942.7s**, 36.4% of `inspect` samples; `collapse_snapshots` **45.5%**.

Against that, `warm_typeahead` fires every 10s with `expires: 120` and its messages queue 18 deep in
a 33-deep census — so during the window every one of its fires is discarded before a slot frees, the
65s TTL lapses, and the head goes cold. That is the user-visible defect, and it has a time of day.

**Why this is the right ship and not another ranking-chase.** 179's rule (tt) says relieving one
contributor in an oversubscribed queue reallocates the wait. This is not that move: it removes a
**scheduling coincidence**, not a contributor. Making five compaction passes non-overlapping is
provably better at *any* utilisation, so unlike a topology change it does not depend on first
knowing the total. That is exactly why it can ship before the instrument is live, and why the
instrument can ride it rather than gate it.

**Do first, in this order:**

1. **Confirm the collision is real before changing a schedule.** `crontab(minute=30, hour="*/6")`
   and `crontab(minute=45, hour="*/6")` — enumerate the actual fire times rather than reading the
   cron by eye, and check the three daily `collapse_snapshots` entries land where they look like
   they do. `backend/scripts/clock_sweep.py` and `beat_intervals()` are the honest tools.
   ⚠️ `collapse_snapshots` has **three** beat entries; its effective cadence is the SUM of their
   rates, and 181's `beat_queues()` will tell you whether they agree about the queue.
2. **Check both `turbo_collapse_*` for 179's defect class first.** A 942s mean is a strong prior for
   a per-item loop, and if the work is simply cheap the collision stops mattering. The tells are
   `Total Cost` and `Shared Read Blocks`, **never `Node Type`** — an `Index Scan` with an
   unconstrained leading column is a full scan that reads exactly like a seek. If this pays, it is
   the better fix and it costs nothing elsewhere.
3. **Then stagger**, so no two compaction beats can be resident given their soft limits. Nothing
   user-facing reads compaction output, so the cadence has slack the price refreshes did not.
   Guard test: assert pairwise non-overlap derived from the live `beat_schedule` and each task's
   declared `soft_time_limit` — **not** transcribed times, or the guard rots the first time someone
   edits the schedule.

**Bundle LAT-P242 into this ship** (`git cherry-pick` from `program/latency-246-…` @ `9d2ffaff`, or
branch off it). Name the pillar and the ship in the cert block header this time.

⚠️ **Out of scope without Alex:** a fourth queue or `--concurrency=3` on background. That is a dyno
purchase — `background`'s 2 slots are a MEMORY bound (2 × 200MB + ~100MB ≈ 512MB Standard-1X
exactly). If the measurement says it is the only answer, that is a YOUR-TURN entry with the number
in plain English (notice 19: no "cert", no jargon), not a change.

## ITEM 2 — the catching proof the BLOCK demands

Do not present this ship without it. A saturated-queue before/after showing `warm_typeahead`
**delivered** before its 120s expiry, and `sta`/`red` returning cached answers within the ship's
latency bound. Admin-counter tests alone were explicitly ruled not to pay this gate.

Once LAT-P242 is live it makes the "after" cheap and rigorous — `queue_demand` gives
`background.utilisation` from one GET instead of a bespoke model. Note the counters are 24h-windowed
and empty at deploy, so **give the slow beats time to fire**: a 20-minute read systematically
under-reports the hourly and 6h grinders, which are the whole subject. Read `wall_window_s` per row
and say what it was.

Three reads worth taking while you are there, all now one GET rather than a measurement:
`heavy`'s real utilisation (180's 0.91x came from the blind instrument and is not evidence in either
direction); `collapse_snapshots`' contradiction (0.00/hr on the delivery counter while being the
largest occupant — it now carries deliveries and worker-seconds on the same row, and check whether
it lands in `tasks_split_across_queues`); and `refresh_hub`, which is not a beat entry at all and
will not appear — that is the documented non-beat-dispatch residual, not a bug. Find its dispatcher.

## ITEM 3 — guard debt, oldest first

- **`TYPEAHEAD-SHED-RUNTIME-CACHE-CONTRACT`** (CERT-2032/2037's remaining nonblocking follow-up): a
  shed answer WRITES and the next request HITS; a full futures-stage timeout writes NOTHING. Proved
  by hand on production, never tested. **Why it is not done, so it is not rediscovered:** three test
  files drive `typeahead_search` directly and **all three rely on a cache HIT returning before the
  first query**, so they pass `db=None`. This needs the MISS path — a fake `AsyncSession` surviving
  every stage of a 1,000-line function. `test_search_response_cache.py::_search` is the model.
  ⚠️ Its warning cost that file a red run: the debug flags' declared defaults are `Query(...)` marker
  objects, **TRUTHY outside FastAPI**, so pass every flag explicitly or you assert against the
  uncached path.
- **`LAT-P240-PREDICATE-SEMANTICS-GUARD`** still owed. 179's guard counts emitted writes against a
  permissive fake; production answered it empirically (1.642 → 1.647) but that is evidence, not a
  guard.

## ITEM 4 — filed, not ours; coordinate, do not claim

- **#3364** — `warm_search_head`'s `expires: 20` discards **96.7%** of its fires. The constant's
  comment justifies 20s against the task's own wall (~4–8s) rather than the QUEUE WAIT: the
  reasoning is right and its premise is false. The generalisation belongs in
  `_EXPIRING_WARMER_BEATS` — *the bound must be compared against delivery latency, not the task's own
  duration.* Closely adjacent to ITEM 1; coordinate before touching it.
- **#3444** — `label_map` is single-valued, so `poll_all_odds` is graded on a DataGolf sub-poll
  (3.3x over) and `discover_events` on a taxonomy enrichment (4.0x under). LAT-P242 routes around it
  for capacity but it still distorts the adherence **verdicts**. `poll_all_odds` is the live lane's.
- **#3440** — settled golf concepts, 426 wsec/hr, byte-identical output over 3–4 rebuilds.
- Seven `external_id ==` sites remain; `admin_matching.py` is **D35/D39 — file, do not fix**, #2693.
- **CERT-1988 stays PARKED.** Do not merge PR #3377, do not re-stage, do not rewrite its header.

## Explicitly NOT in scope

Spending; `WARM_CONCURRENCY` / `REFRESH_AHEAD_SECONDS` / `RESPONSE_CACHE_TTL_S` / priority queueing;
the tsvector index (Tier-1, integrator + Alex); ITEM 4 of 178 (`red sox` headline market — recall,
not latency, and must not be bundled); matching symptoms (D35, file under #2693).

## Rules carried forward

168 (a)–(g), 170 (b)–(e), 171 (b)–(e), 173 (f)–(i), 174 (j)–(m), 175 (n)–(x), 176 (y)–(dd),
177 (ee)–(kk), 178 (ll)–(oo), 179 (pp)–(uu), 180 (vv)–(aaa), **181 (bbb)–(ggg)** all hold.

**(bbb)** A refactor that changes the PRIMITIVE under a shared, exception-swallowing writer has a
silent blast radius, and the test doubles are its only observer. Production having the capability is
what HIDES the change, not what excuses it.

**(ccc)** When the wrong answer and the plausible default are the same value, a test asserting that
default is vacuous. Pin a NON-default expectation.

**(ddd)** A "field present and null" test does not exercise the compute branch. An early-returning
absent case and a present-but-uncomputable case emit the same-looking output down two paths.

**(eee)** A per-key total must be attributable; unattributable demand is NAMED, not split.

**(fff)** Signal-wired observability fails silently in two indistinguishable ways — never connected,
and connected-but-raising. Drive the REAL signal; calling the handler proves neither.

**(ggg) — the one this queue exists to teach.** An instrument is never the cargo, however good it
is and however badly the next decision needs it. CERT-2038 BLOCKed a green, well-guarded, genuinely
useful measurement instrument purely on queue shape, and it was right to. **Name the pillar and the
user-visible ship in the cert block header, or the block is refused before its evidence is read.**
The corollary is the useful half: if you cannot name the ship, you have not yet found it — and
looking for it is what turned "the queue is oversubscribed, somehow" into "five compaction passes
share two slots for fifteen minutes every morning", which is a better brief than the total would
have been.

⚠️ Build on a FRESH branch off master. `program/latency-245-…` (in flight, with the integrator),
`program/latency-246-…` (parked, holds LAT-P242), `program/latency-181-artifacts` (docs) and
`program/latency-242-…` (parked commits) are all live.

Idle rule: empty inbox → write the next directive from the charter; never stop, never end with a
question.
