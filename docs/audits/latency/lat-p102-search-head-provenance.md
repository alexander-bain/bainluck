# LAT-P102 — the `/search` head warmer is enabled, and the head is elected by people

**Ship:** the one question two different people actually searched this month is answered before it
is asked. Today that is one query (`red sox`, 1.73 s cold → cache hit); the day a second question
earns two askers, it joins it with no config change, no re-tuning and no new decision.

**Queue:** LAT-P102 · **branch** `program/latency-88` · **issues** #2211 (the warmer), #1916 (the
block) · **migration_slot** none · **beat_schedule_change** false · **config vars** none changed.

---

## 1. What was blocked, and what unblocked it

LAT-P090 built the `/search` response cache and its head warmer, and **shipped the warmer
disabled**. The reason was #1916, which measured `search_query_logs` as 23.6 % gold-sentinel
traffic and says in bold: *do not tune, re-rank, resize or re-source a warmer head until a clean
distribution exists.* LAT-P090 respected that rather than stepping over it, and wrote down the
argument for flipping it while explicitly declining to flip it.

This queue went to resolve the block. The resolution is that **the clean distribution #1916 asks
for can already be read, and needs no column and no migration.**

`search_query_logs.session_id` is written from the `x-session-id` header. Both shipping clients
attach it to **every** search — `frontend/lib/api.ts:332` and
`ios/Bain Luck/.../APIClient.swift` — and **no probe, sentinel or warmer in this repo sends it.**
So a row carrying a session was written on behalf of a real client. That is a *write-time-recorded
attribute*, which is exactly the discriminator #1916's acceptance criteria demand and exactly what
its "not by timestamp heuristic" clause rules out the alternative to.

## 2. The census — #1916's own number was a four-fold undercount

`search_query_logs`, 30 days to 2026-08-27, via `/api/admin/db-query`:

| slice | rows | share |
|---|---:|---:|
| total | 3,851 | 100 % |
| **carrying no `session_id` and no `user_id`** | **3,838** | **99.66 %** |
| in the 07:09–07:12 UTC sentinel minute | 922 | 23.9 % |
| in a *burst* minute (≥ 8 distinct queries in one clock minute) | 2,858 | 74.2 % |

#1916 measured the sentinel and reported 23.6 %. That was correct and incomplete: **135 burst
minutes carrying 2,858 rows** are ad-hoc probe sweeps from this lane's own measurement rounds
(25–50 distinct queries inside a single minute — not a shape a human produces). The 07:10 sentinel
is the *visible* quarter of the contamination, not the whole of it.

The top of the raw 30-day head, with the sentinel minute split out:

| query | total | in sentinel minute | outside | days seen |
|---|---:|---:|---:|---:|
| masters winner | 116 | 56 | 60 | 30 |
| stanley cup | 110 | 28 | 82 | 30 |
| world cup | 103 | 28 | 75 | 30 |
| nba champion | 101 | 28 | 73 | 30 |
| world series | 99 | 28 | 71 | 30 |
| red sox | 95 | 0 | 95 | 10 |
| grammys | 75 | 28 | 47 | 30 |
| yankees | 74 | 0 | 74 | 7 |

**Every one of the eight terms the warmer would have warmed is a sentinel or probe term.** Note
also that excluding the sentinel *minute* would not have saved it: `stanley cup` has 82 rows
**outside** that minute, and they are probe rows too. A read-time timestamp filter was never going
to work, which is why #1916 forbade one.

## 3. The clean distribution, published

#1916's final acceptance criterion asks for a user-traffic-only re-measure to be published,
*"and the overlap with the current head reported whether it moved or not."* Here it is — the whole
of it, ranked by distinct sessions:

| query | distinct sessions | rows |
|---|---:|---:|
| **red sox** | **2** | 2 |
| patriots | 1 | 5 |
| orenburg | 1 | 2 |
| bridesmaid | 1 | 1 |
| masters | 1 | 1 |
| pregnancy | 1 | 1 |
| world cup | 1 | 1 |

**13 rows. 12 sessions. 7 distinct queries. 30 days.** Overlap with the raw head: `world cup`
(1 session) and `red sox`. Overlap with the *warmable* head: **one term.**

Two things in that table are worth naming rather than averaging away:

- **`patriots`: five rows, one session, nine seconds.** One person submitted the same word four
  times in a row. Row-ranked, that single person's frustration would lead the head — more rows
  than any genuinely shared query has in total. This is the artifact `MIN_HEAD_SESSIONS = 2` exists
  to refuse, and it is not hypothetical: it is the largest single entry in the real data.
- **Those four submissions returned `25, 0, 0, 25` results.** Same query, same session, same nine
  seconds. That is a user-visible reliability defect on a graded surface and it is filed in §7 —
  it is not this queue's scope, but it is the most important thing this census turned up.

## 4. What shipped

`backend/app/tasks/search_head_warmer.py`

- **`_head_from_user_rows` + `_USER_HEAD_SQL`** — a new head query that filters to
  `session_id IS NOT NULL OR user_id IS NOT NULL`, ranks by
  `count(DISTINCT COALESCE(session_id, 'u:' || user_id))`, and floors on `MIN_HEAD_SESSIONS = 2`.
  Deliberately **not** shared with `typeahead_warmer._head_from_query_log`: that surface still reads
  the table whole on purpose, and sharing one query would have silently re-sourced the `/typeahead`
  head as well — the other half of what #1916 forbids.
- **`resolve_head` has no fallback**, and the absence is load-bearing. "If the attested head is
  empty, use the whole table so the warmer has something to do" reinstates the block in the one
  state where it bites hardest, because the attested head is empty precisely when all the traffic
  is ours. Empty is the correct answer to *what do users want warmed* when nobody has asked twice,
  and `_summarize` renders it `partial`, never `complete`.
- **`head_warm_enabled()` now fails OPEN** — unset means ON, restoring the family convention, with
  `_WARM_OFF_VALUES` byte-identical to `search_cache._CACHE_OFF_VALUES` so the two neighbouring kill
  switches cannot disagree about what "off" spells.

The guarantee moved from the env var into the head query, and that is strictly stronger: **an
operator can flip a default without having read #1916; a filter cannot elect a probe term at all.**

## 5. The measured before

Ten cold arrivals, each after 65 s of idle (past the 60 s `SEARCH_RESPONSE_TTL_SECONDS`), against
production with the warmer still disabled. `world series` is the control — a probe term the new
head can never elect, so it must NOT improve after deploy.

| round | `red sox` (head) | `world series` (control) |
|---|---:|---:|
| 1 | 2.720 s | 1.510 s |
| 2 | 1.346 s | 0.593 s |
| 3 | 0.760 s | 0.448 s |
| 4 | 1.731 s | 0.520 s |
| 5 | 2.062 s | 0.580 s |
| **median** | **1.731 s** | **0.580 s** |

`x-search-cache: miss` on **10 of 10**, HTTP 200 on 10 of 10. That number is the finding underneath
the ship: **with the cache alone, a real user's first search of any minute is always a miss.** The
response cache LAT-P090 shipped serves within-session repeats (which is what `patriots` ×4 and
`orenburg` ×2 are) and nothing else. Only a warmer closes the cold arrival, and only for terms it
knows to warm.

Raw: `lat-p102-before.txt` beside this file (CSV; the extension dodges `.gitignore:74`).

## 6. The post-deploy grade — pre-registered

Re-run the §5 probe unchanged. **PASS requires all three:**

1. `red sox` returns `x-search-cache: hit` on **≥ 4 of 5** cold arrivals (the warmer's 45 s pass
   floor against a 60 s TTL leaves no gap; a miss means the duty-cycle relation is broken).
2. `red sox` median **≤ 0.30 s**, down from 1.731 s.
3. **The control does not move.** `world series` median stays within ±40 % of 0.580 s and keeps
   returning `miss`. A control that improves means something other than the warmer changed and the
   result is not attributable.

Plus, from `/api/admin/task-metrics?task=warm_search_head`: `terminal: complete`, `total: 1`,
`head_source: db:user_attested:30d:min2sess`, `warmed: 1`. **`total: 8` would be a failure** — it
would mean the attestation filter is not applied.

⚠️ Take the reading **≥ 10 minutes after the release**, warm second pass, per the standing
post-deploy-latency rule.

**Rollback:** `heroku config:set SEARCH_HEAD_WARM_ENABLED=0 -a bainluck`. No deploy, no revert. The
response cache is on a separate switch and is unaffected.

## 7. For Fable — three findings, none of them this queue's scope

1. 🔴 **`/api/events/search` returns 0 results intermittently for a query that has 25.** Session
   `DABC07D4…`, 2026-08-14 22:16:02–22:16:10 UTC, query `patriots`, five submissions,
   `result_count` = **25, 0, 0, 0, 25**. A real person retyped the same word four times because
   search kept coming back empty. This is Alex's #1 priority class (reliability) on a graded
   surface, it is in the *organic* traffic rather than a probe, and it is invisible to the Flow
   Sentinel because the gold set asks each query once. Suspect the LAT-P007 `degraded` path
   returning an empty body under the 20 s budget. **Worth a queue on its own.**
2. **This lane's own probe traffic is 74 % of `search_query_logs`** and has been silently
   corrupting every head-selection question asked of that table, including #1916's. The attestation
   filter fixes the *read*; it does not stop the *writes*. #1916's `X-Bainluck-Origin` header (its
   design item 1) is still owed, and is now the cheaper half of that issue — the sentinel and the
   probe scripts declaring themselves is a small change, and it would let the automation rows be
   counted rather than merely excluded.
3. **#1916 can be narrowed.** Its `search_query_logs` half is answerable today by
   `session_id IS NOT NULL` and this queue publishes the re-measure it asks for. What remains
   genuinely open is the `search:trending:24h` half — the ~89 % warmer echo, and the unidentified
   reset mechanism that a warmer head must not inherit. Those are untouched here.

## 8. What this queue did NOT do

- **No migration.** No `origin` column. `session_id` answers the question this ship needed
  answered; the column remains the better instrument for the questions it does not.
- **No change to the `/typeahead` head**, asserted by a test rather than left to care.
- **No re-tuning of the three constants.** 45 / 60 / 25 are untouched and their relation test
  still passes.
- **No claim that the warmer is now valuable at scale.** It warms one term. The honest reading is
  that `/search` has almost no organic repeat demand *yet*, and the value of this queue is that the
  warmer is now correct and self-gating, so it converts demand into speed automatically instead of
  waiting on somebody to re-litigate #1916.
