# LAT-P097 — the deploy proofs for `-82` and `-83`, and the done bar re-graded

**Cycle:** LAT-P097 · **Date:** 2026-08-26/27 · **Identity:** `LAT-P097-20260827`
**Directive:** Fable 2026-08-26, delivered through the lane runner Alex launched under his
standing authorization. Three items.
**Ship this serves:** the feed loads fast even on a cache miss, and a person typing in the search
box sees suggestions instead of waiting. Both are user-visible; neither is a measurement.

**Production state while measuring.** Two releases landed *during* this session, so every number
below names the slug it was taken on:

| release | commit | released (UTC) | carries |
|---|---|---|---|
| v3903 | `af9c3ffb` | 20:32:05 | **`-82`** (LAT-P093, `canonical_counts`) — first release containing `8e94d71a` |
| v3905 | `d2169e1d` | 22:12:40 | **`-83`** (LAT-P094, concepts) — first release containing `781f1046` |
| v3906 | `f88fd4fc` | 22:43:01 | both |
| **v3907** | **`baae52c2`** | **2026-08-27 00:14:27** | both — **the slug every done-bar number below was measured on** |

Ancestry verified rather than assumed: `git merge-base --is-ancestor` returns 0 for both fixes
against `baae52c2`, and `/api/health` reported `commit: baae52c2` at every read.

---

## 0. The headline

| item | verdict |
|---|---|
| **`-82` canonical_counts — deployed and working** | ✅ **PROVEN**, on two independent rails |
| **`-83` concepts — deployed and working** | ✅ **PROVEN** by statement identity and mean; ⚠️ its **tail** is new information |
| **the done bar** | 🔴 **NOT MET.** Two of four numbers clear; typeahead first-touch and feed miss cost do not |
| **the next feed stage worth a session** | **none** — and the one lever that remains is already built, specced and gated |

---

## 1. Item 1 — the #1916 five-liner

**It was already written and it is still current.** The five decision-shaped lines were posted by
LAT-P094 (2026-08-26 20:38:58Z) and re-priced by LAT-P095 (21:49:19Z). All five were re-read
against today's code and today's slug and none of them moves. Nothing was flipped;
`SEARCH_HEAD_WARM_ENABLED` remains unset and the call remains Fable's.

Two things were owed and are now filed as a comment on #1916:

**A precision fix — the comment above it prices the wrong surface.** LAT-P095 attached `chiefs`
3,988 ms to the grant decision. That is `/api/events/typeahead`. `SEARCH_HEAD_WARM_ENABLED` warms
`/api/events/search`, and the two routes have **different name predicates**, verified in source:

| route | futures NAME arm | where |
|---|---|---|
| `/api/events/search` | ILIKE only — `futures_name_match = futures_name_ilike` | `routes/events.py:3342` |
| `/api/events/typeahead` | stemmed FTS **OR** ILIKE — `_build_futures_name_filter` | `routes/events.py:4416` |

The correction moves the number the *right* way, so the recommendation is unchanged and slightly
stronger: the surface the flag actually warms measured 11.9 s / 18.5 s (`winner`) and 13.98 s
(`champion`) cold, which is larger than the typeahead figure quoted beside it.

**A new fact that could move the timing.** LAT-P096's index attacks the FTS half of that name arm
— which is in `/typeahead`'s plan and **not** in `/search`'s. So the two halves of "the head is
cold" have separated: `/typeahead` has a fix in flight that does not need the grant, and `/search`
does not. That makes the grant *more* separable than it looked, not less.

**Contamination for item 1: none.** Zero `/search` and zero `/typeahead` requests were issued for
it. `/search` writes `search_query_logs` — the table #1916 exists to clean — so refreshing a figure
that had not changed would have cost the issue more than it bought.

---

## 2. Item 2 — the deploy proofs

### 2.1 The ring cannot grade this, and the reason is structural

`GET /api/admin/latency-slow-events?limit=500&min_ms=0`, read 2026-08-27 00:08:16Z.
`ring_used 500/500 · unparseable 0 · oldest 546,178 s · newest 1,165 s`. **167 `/api/feed` `miss`
events.** A read of already-recorded events; this lane generated no `/api/feed` load for it.

Split at the deploy boundaries, the cohort is:

| cohort | window | n |
|---|---|---:|
| pre-`-82` | everything before v3903 | **164** |
| post-`-82`, pre-`-83` | v3903 + 5 min → v3905 | **1** |
| post-`-83` | v3906 + 5 min → read time | **2** |

**Three post-deploy misses against 164 pre-deploy, four hours after two releases.** That is not
enough to move a p50, and waiting does not obviously fix it: feed-miss inter-arrival is
p50 272.3 s, p90 10,344.5 s, max 39,261.5 s.

Worse than sparse — **the ring is survivorship-biased in the direction of the claim.** Its
`threshold_ms` is 5,000, so a miss the fix drops below 5 s leaves the sample silently. A working
fix and a broken instrument produce the same thinning cohort, and a lane reading only the ring
cannot tell them apart. That is the reason this cycle built a second rail rather than reporting a
number from this one.

### 2.2 What the ring does say, stated for what it is worth

Even at n=3, `futures.canonical_counts` separates completely:

| | n | min | p50 | values |
|---|---:|---:|---:|---|
| PRE | 142 | 88.3 | 1,332.7 | — |
| POST | 3 | — | — | **70.4 · 152.8 · 247.9** |

**2.82 %** of the 142 pre-deploy samples fall below the *worst* post-deploy sample. All three post
samples land inside that slice. Under the null that they were drawn from the pre-deploy
distribution, that is **p ≈ 2.2 × 10⁻⁵**. The post median also lands on LAT-P093's own prediction
(166.4 ms measured A/B → a modelled 133.6 ms stage residual).

`concepts`, on the same instrument, says nothing: its two post-`-83` samples are 515.2 and
4,494.0 ms, and 9.4 % / 11.9 % of the pre-deploy distribution sits below / above those. **Two
ordinary draws. n=2 grades nothing**, and this document does not pretend otherwise.

### 2.3 The rail that does grade it — `pg_stat_statements`

Every execution is counted, on every dyno, whatever the request took, and PostgreSQL 17's
`stats_since` dates a fingerprint's **first** execution. A statement first seen seconds after a
release is a statement that release put into production. That is the deploy proof proper.

| statement | `stats_since` | release | gap |
|---|---|---|---:|
| `-82` skip scan, fingerprint A | 2026-08-26 **20:34:07.367** | v3903 @ 20:32:05 | **+2 m 02 s** |
| `-82` skip scan, fingerprint B | 2026-08-26 **20:34:08.404** | v3903 @ 20:32:05 | +2 m 03 s |
| `-83` `prefetch_open_markets` | 2026-08-26 **22:13:13.292** | v3905 @ 22:12:40 | **+33 s** |

Both new shapes appear within minutes of the release that carried them and never before it. The
`-82` family also contains a **third** fingerprint at 19:23:28Z with 9 calls — that is LAT-P093's
own ad-hoc A/B probe through `db-query`, 71 minutes before the deploy. It is listed per-fingerprint
in the snapshot rather than averaged into the family, because a lane's own probe pulling a family's
first-seen backwards is exactly the kind of thing that turns a proof into a story.

And the cost, from the same view:

| statement | calls | min | **mean** | sd | **max** | buffers/call |
|---|---:|---:|---:|---:|---:|---:|
| `-82` skip scan A | 130 | 1.9 | **33.5** | 41.0 | 233.4 | 824 |
| `-82` skip scan B | 99 | 1.8 | **12.5** | 10.7 | 69.3 | 812 |
| `-83` prefetch | 107 | 79.1 | **411.5** | 523.7 | **4,402.3** | 26,626 |

Against what each replaced:

- **`-82`**: LAT-P093 measured the retired aggregate at **1,667.1 ms p50 / 70,779 buffers** and
  predicted 166.4 ms. Production is running at **12.5–33.5 ms and ~820 buffers** — better than the
  prediction, and an **86×** buffer reduction.
- **`-83`**: LAT-P094 measured the consolidated read at **453.4 ms p50** and predicted that as the
  residual. Production mean is **411.5 ms**. The model holds.

### 2.4 The windowed A/B, and two instrument defects it found

Snapshots are taken by `backend/scripts/deploy_proof_stage_statements.py`, which aggregates by
*family* — a SQLAlchemy statement with a variable-length `IN` list fingerprints differently per
length, so `-82`'s retired aggregate alone is spread over 18 `queryid`s and grading one of them
reads a slice of the truth.

The first window exposed two defects in the instrument, both verified against production before
being fixed, and both recorded because the class matters more than the case:

1. **The snapshot matched its own family.** A family predicate is an ILIKE over `query`, and the
   string constant `'%canonical_source_universe%'` travels *inside* the snapshot's own SELECT — so
   the snapshot lands in `pg_stat_statements` carrying the literal and the next snapshot counts it
   as a call of the family it is measuring. Confirmed: two such entries, `stats_since` 00:27:03 and
   00:27:05. Every predicate now carries `AND query NOT ILIKE '%pg_stat_statements%'`, which no
   application statement can satisfy.

2. **The retired `-82` family was over-broad, and would have printed a false UNPROVEN.** The shape
   `count(DISTINCT source) … WHERE canonical_market_key IN (…)` has a **second live caller that
   `-82` never claimed to change**: `app/tasks/precompute_interestingness.py:191`, a Celery task off
   the request path. It ran at 00:21:15Z, 604.6 ms. Left in the family it would have shown the
   retired path still running and graded a working deploy as unproven. The two are separable by
   result label — the feed path writes `AS source_count`, the task writes `AS cnt` — so the family
   is now the feed variant only and the task is carried as an **ungraded sibling**: printed, named,
   and unable to flip a verdict it is not part of.

This is ruling 4's coverage-guard lesson in a new place: *a metric that improves while its
denominator shifts is a defect until proven otherwise.* Here the denominator was about to shift the
other way and manufacture a failure.

---

## 3. Item 3 — the next stage, and the done bar

### 3.1 No feed stage is worth a session, and the remaining lever is already built

LAT-P095 ruled `events` out on measurement (~400 ms warm against a 1,208.6 ms stage p50; the one
real defect inside it is a 1.56× lever on 22 % of cold builds ≈ 2.7 % of a p50 miss), and
`futures.market_load` is a pkey `IN` plus a `selectinload` proportional to output. Nothing in
today's data disturbs either finding.

**The one lever left on the feed is the parked index** —
`docs/audits/latency/lat-p094-open-category-index-gate-spec.md`, `ix_fm_open_category`. It is
already written, already gated with bars frozen before any DDL, and blocked on the same thing
LAT-P096 is blocked on: **Alex's attended `psql` batch**. It does not need a session; it needs a
batch. Building a third thing to sit in the same queue would be work that cannot ship.

### 3.2 New information the parked spec does not have: the value is in the TAIL

The spec priced itself on the mean — "~300 ms off a 453.4 ms read … a third-order lever". Today's
production distribution says that undersells it in one direction and oversells it in another:

```
-83 prefetch:  n=107   min 79.1   mean 411.5   sd 523.7   max 4,402.3   26,626 buffers/call
```

The **standard deviation is larger than the mean**, and the max is **10.7× it**. That is not a
stable 411 ms cost — it is a cheap read with a violent tail, and the tail is a user-visible event:
the ring's 23:46:10Z miss took 6,481.6 ms total of which **4,494.0 ms was `concepts`**, with its
single worst query at 4,428.8 ms — which matches the prefetch's own recorded max of 4,402.3 ms.
**69 % of a 6.5-second feed build was this one scan**, under contention.

So the honest re-statement is: the index is a small mean win and a **large tail win**, and the tail
is the half a user experiences. That is appended to the spec rather than acted on here.

**Precondition P1 remains UNCONFIRMED, not passed and not failed.** It requires `concepts` ≥ 800 ms
p50 *and* top-three by stage, measured on the ring's miss cohort — and per §2.1 that cohort is
n=2 post-`-83`. The spec keeps its `RETIRED — PENDING CONFIRM` status. What has changed is that the
question P1 asks (is the *median* still big?) is now visibly the wrong question for this stage.

### 3.3 The done bar, measured on v3907 (`baae52c2`), warm slug

Instrument: `backend/scripts/done_bar_snapshot.py`. Bars are taken from `docs/PRD.md`'s latency
charter (Alex ruling 2026-08-24) — *"feed p50 and typeahead p50 … standing target = the feed miss
share/cost (37.5 % at ~4.1 s)"* — not chosen by this cycle.

| number | value | bar | verdict |
|---|---:|---:|---|
| feed p50, warm (server `x-response-time`, n=6) | **17.5 ms** | ≤ 50 | ✅ MET |
| typeahead p50, warm (second touch, n=6) | **26.0 ms** | ≤ 100 | ✅ MET |
| **typeahead p50, FIRST TOUCH** (n=7, LAT-P095's own term set) | **3,530 ms** | ≤ 500 | 🔴 **NOT MET** |
| feed miss **share** (latency-stats, n=43 over 2,968 s) | **18.6 %** | ≤ 37.5 % | ✅ MET |
| **feed miss p50** | **3,201.7 ms** (max 6,481.6) | ≤ 1,000 | 🔴 **NOT MET** |

### 🔴 THE DONE BAR IS NOT MET.

First-touch detail, all seven confirmed genuine cold builds by `x-timing-split` `q > 0`:

| term | first touch | queries |
|---|---:|---:|
| `ballon` | 1,178 ms | 5 |
| `wimbledon` | 1,799 ms | 8 |
| `tour de france` | 3,516 ms | 8 |
| `hurricane` | 3,530 ms | 5 |
| `nvidia earnings` | 3,625 ms | 6 |
| `senate runoff` | 3,656 ms | 5 |
| `emmy` | 3,853 ms | 5 |

**Delta vs LAT-P095's published 3,816 ms on the same term set: −286 ms — flat.** Which is the
expected result and worth saying plainly: nothing shipped for typeahead this week. LAT-P096's index
is specced and gated, not deployed.

The **feed miss share fell from the charter's 37.5 % baseline to 18.6 %**, and the miss p50 from
~4.1 s to 3.2 s. Both are moves in the right direction and both are on thin windows (n=43, 49
minutes) — reported as measurements, not as a trend.

### 3.4 Two methodology defects in the done-bar instrument, found and fixed

Recorded because either would have manufactured a win:

1. **A per-run salt on the cold terms changes the query shape.** The first draft appended a run
   label to guarantee the term was novel — making `kaiserslautern LAT-P097-A` a **two-token** query
   whose second token ANDs into `_expanded_tsquery` and makes the plan *more* selective. Salted
   terms measured a first-touch p50 of **1,458 ms** in the same session that the bare token
   `werder` measured **3,192 ms**. The salt was reporting a 2.2× improvement that was entirely its
   own artefact. Terms are now bare.

2. **A cache hit inside a cold sample.** Without the salt, a term touched in the last minute
   measures the cache. `x-timing-split` distinguishes them exactly — a cold build reports
   `q=8; db=3125.3`, a hit reports `q=0; db=0.0` — so any `q=0` probe is **discarded and counted**,
   never averaged in. The guard fired on its first live run: a re-run 90 seconds after the
   comparison pass found all seven terms still warm and refused to grade them, printing
   `UNMEASURED` rather than a 26 ms p50.

⚠️ **That second event is itself a finding: the typeahead cache TTL is documented as 45 s in
`routes/events.py`, and seven terms were still serving `q=0` more than 14 minutes after their last
touch.** This cycle did not chase it — it is off-directive and the instrument handles it correctly
— but "the TTL is 45 s" is load-bearing in #1916's own repeat-gap arithmetic, and it does not match
what the route was observed doing. **Parked**, not dropped.

---

## 4. What the next session should do

1. **Nothing new on the feed.** Its warm p50 is 17.5 ms, its remaining cold stages are third-order,
   and its one remaining lever is specced and waiting on a batch.
2. **`futures_query` on `/api/events/typeahead` is still the named ship**, and LAT-P096 has already
   done the session's work: spec, red-first gate, frozen bars, DDL text. It needs **Alex's attended
   `psql` batch**, and `ix_fm_open_category` (LAT-P094-1) should ride in the same batch — two
   indexes, two pre-registered gates, one attended window.
3. **Re-run both instruments after that batch.** `deploy_proof_stage_statements.py --diff` grades
   the statement; `done_bar_snapshot.py` grades the bar, against the same term set, so the delta is
   a delta.
4. **The TTL discrepancy in §3.4** goes to `PARKED-MEASUREMENTS.md`.

---

## 5. Contamination introduced by this cycle, declared

Ruling 127's general form: an instrument that writes to what it reads must say so.

- **`/api/events/typeahead`: 30 cold misses issued**, each casting one vote into
  `search:trending:24h` — the head source #1916 measures as ~89 % warmer echo. The head cut sits
  near 65 votes and no term received more than 4, so no head membership can have moved; the votes
  are nonetheless real and counted.
- **`/api/feed`: 18 warm requests.** They are cache hits and they sit inside the `latency-stats`
  denominator quoted in §3.3, which inflates the `hit` bucket and therefore *deflates* the miss
  share — the number is reported here as favourable-biased for that reason.
- **`POST /api/admin/db-query`: read-only `SELECT`s only**, over `pg_stat_statements`,
  `information_schema` and `futures_markets`. Two of them landed in `pg_stat_statements` carrying a
  family literal and were the subject of §2.4 defect 1.
- **`/api/events/search`: zero requests.** Deliberate — see §1.

**Provenance:** LAT-P097, 2026-08-27. Related: #1866, #1916, #1459, #2211.
Instruments: `backend/scripts/deploy_proof_stage_statements.py`,
`backend/scripts/done_bar_snapshot.py`.
Raw: `raw-lat-p097-feed-miss-slow-events.json`, `lat-p097-deploy-proof-A2.json`,
`lat-p097-done-bar.json`.
