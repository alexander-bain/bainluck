# RULING 129 — Coalescing moves cost between buckets without removing it

date: 2026-08-24
author: Fable (LAT-P084 item 1, pasted and reviewed by Alex)
issues: #2143
supersedes:

Found while re-measuring the feed miss share decontaminated on the post-T0 slug.

---

## The clause

**A request that waits out another request's build has not been served from
cache. Single-flight coalescing converts N concurrent cold requests into one
build and N−1 waits — it saves the backend N−1 builds and saves the user
nothing — so any metric that reads the MISS bucket to estimate what users wait
for undercounts by exactly the coalesced population, and undercounts most when
concurrency is highest.**

The general form, beyond caches: **an optimisation that redistributes a cost
across bookkeeping categories will be recorded as an improvement by any
instrument keyed on one category.** Ask what left the bucket, not what is in it.

---

## The measurement

`/api/feed` census (`always_sampled`), window 17:25:24Z→18:17:53Z on 2026-08-24,
entirely after T0 = 17:23:50Z (v3886 / `b5c2a750`), `completeness: complete`,
no release straddle. Decontaminated by subtracting this lane's six probes per
ruling 127:

| bucket | n | share | p50 ms | min ms |
|---|---:|---:|---:|---:|
| hit | 10 | 23.8% | 13.6 | 9.9 |
| stale_hit | 15 | 35.7% | 19.3 | 12.6 |
| miss | 6 | 14.3% | 5,046.8 | 3,172.2 |
| **other = `coalesced`** | **11** | **26.2%** | **2,897.6** | **2,093.3** |

**Build-paying share = (6 + 11) / 42 = 40.5%**, Wilson 95% CI 27.0 – 55.5%.
**Miss share alone = 14.3%.**

Fable's charge — "MISS SHARE IS 37.5% AT 4,121ms … better than a third of feed
requests eat four seconds" — is **correct in its conclusion and wrong in its
arithmetic**, and the two errors happened to cancel. A third of feed requests do
eat multiple seconds. Fewer than a sixth of them are misses.

## How `other` was identified, without guessing

`app/middleware/latency.py:106–119` buckets to `other` exactly when
`X-Feed-Cache` holds a value outside `{miss, hit, stale_hit, error}`.
`app/routes/feed.py` sets exactly seven such values. The distribution excludes
six of them:

- `last_good` (feed.py:2066) and `unavailable` (:2093) are reached **only after
  the wait budget is exhausted**, so neither can produce a 2,093.3 ms minimum.
- `disabled_debug` requires `?debug=true`, `disabled_reviewed_filter` requires a
  reviewed-filter param, `disabled` requires the response cache to be off — but
  `hit` and `stale_hit` are being served, so it is on. `n/a` is a helper default.
- `coalesced` (feed.py:2054) returns the instant the leader's build completes:
  bounded above by the leader's build, floored by the waiter's arrival offset.
  p50 2,897.6 under a leader p50 of 5,046.8 with a 2,093.3 floor is the only fit.

Then confirmed rather than inferred — three concurrent anonymous
`GET /api/feed?limit=5` at 18:17:37Z:

| probe | wall | `X-Feed-Cache` | `X-Feed-Singleflight` |
|---|---:|---|---|
| 1 | 6.560 s | `miss` | `leader` |
| 2 | 6.618 s | `miss` | `leader` |
| 3 | 6.632 s | **`coalesced`** | `coalesced` |

**A coalesced waiter took 6.632 s.** It is in the fast-sounding bucket and it is
the slowest of the three.

## The second finding, free with the first — and it is NOT the dyno count

Two leaders for one anon cache key. That should be impossible:
`request_cache.begin_build` has no `await` between its `_inflight.get` and its
`_inflight[key] = fut`, so within one event loop two same-key callers cannot
both lead; and all three probes were anonymous with identical params, so
`feed_response_cache_key` returns one key for all three
(`_session_id_from_request` reads only a cookie or `X-Session-Id`, and curl sent
neither).

**The first explanation reached for was the dyno count, and it was wrong.**
`heroku ps` shows exactly one `web (Standard-2X)` dyno, matching what
`scripts/watch_2107_feed_500s.py` already records. The actual cause is one
config var:

    WEB_CONCURRENCY: 2

Uvicorn honours `WEB_CONCURRENCY` as its worker count, so the single web dyno
runs **two worker processes**, each with its own event loop and its own
process-global `_inflight`. Probes 1 and 2 landed on different workers; probe 3
landed on one that already had a leader.

So the correct statement is: **single-flight is per WORKER PROCESS, and the
process count is `dynos × WEB_CONCURRENCY`, not `dynos`.** Any capacity argument
that reasons from `heroku ps` alone is wrong by the concurrency factor — and
`heroku ps` is the instrument everyone reaches for, which is why this is written
down. The same correction applies to any reasoning about process-global state:
there are two of every process-global on that dyno today.

## Relation to the rulings around it

This is [[053]]'s shape one level up — gotcha #53 says an empty 200 is a
response shape, not an absence; this says a bucket label is a code path, not a
cost class. It is also why ruling 127's charter insists the feed headline is
reported **with its `by_cache_status` split**: the split is what made this
visible. A single p50 (36.9 ms here) hides it completely, and so does a miss
share.

## What it changes

1. **The LAT-P084 headline** is the build-paying share, 40.5%, not the miss
   share, 14.3%. See `docs/feed-miss-path-decomposition-2143.md` §9.
2. **The #2143 lever's addressable population grows 2.8×.** Sharing the
   principal-independent build shortens the *leader's* build; a waiter's wait is
   bounded by that same build, so the saving reaches `coalesced` too.
   **With a discount the projection did not previously carry:** #2143's shared
   store is process-global, so at `WEB_CONCURRENCY=2` each artifact is built
   **twice per TTL window**, once per worker. The projected saving is unchanged
   for any single request that finds a warm entry, but the *rate* of cold
   builds is 2× what a one-process model predicts, and the first request to
   each worker still pays full price.
3. **Future latency reports must not quote a miss share as a wait share.**
   Quote `miss + coalesced`, and if a new non-standard `X-Feed-Cache` value
   appears, identify it before reporting a number over it — `other` is an
   unread measurement, never a residual.

## What it does NOT claim

- It does not say coalescing is wrong. Coalescing is correct and load-bearing:
  without it, 12 concurrent cold requests would be 12 builds. It says the
  *metric* is wrong, not the *mechanism*.
- It does not close #2143 or grade the fix. No delta has been measured; this
  lane cannot deploy.
- n = 42. The CI is wide (27.0 – 55.5%). The claim that the build-paying share
  is materially larger than the miss share survives it; a precise value does not.
