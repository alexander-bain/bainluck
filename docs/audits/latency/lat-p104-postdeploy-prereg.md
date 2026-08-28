# LAT-P104 — pre-registered post-deploy check

Written **before** the branch was deployed and before any post-deploy read was taken.
Committed with the code, in the same commit, so the bar cannot move after the number arrives.

## What is being pre-registered, and what is not

This queue inherited a built tree. The prior latency window was killed mid-run by an API infra
error and left `feed.py`, `principal_independent_cache.py` and an untracked gate file in the
worktree; the re-staging directive says to treat that work as **untrusted**. So:

- **NOT pre-registered:** the build. It already existed when this window opened. Pretending
  otherwise would be a pre-registration written after the fact, which is the thing
  pre-registration exists to prevent.
- **Pre-registered here:** the production check. Nothing has been deployed, so this bar is
  genuinely ahead of its measurement.
- **Independently re-run in this window, from scratch:** the red-first battery (five mutations)
  and every gate. Those are in the main audit doc with the counts pytest actually printed. An
  inherited diff that nobody re-reddened is an assertion, not a gate.

## The prediction

The change widens the shared concept stage's clock bucket from a **30 s literal** to
`clock_bucket_s()` (**3600 s**, clamped never to be finer than the live TTL). The TTL is
**60 s** and is unchanged.

LAT-P103's BEFORE instrument (production, slug `ba3be25f`, 2026-08-27, ten cold builds / ten
principals / ten unwarmed shapes) measured:

| | n | `x-feed-shared` | median `x-feed-elapsed-ms` |
|---|---:|---|---:|
| REBUILT the concept stage | 4 | `canonical_counts` | 2,481.99 ms |
| REUSED the concept stage | 6 | `canonical_counts,concepts` | 1,295.07 ms |

`concepts` was reused **6/10**; `canonical_counts`, whose key carries no clock component at all,
was reused **10/10**. One instrument, two artifacts, one difference between their keys.

## The bar — graded, not narrated

Same shape as LAT-P103's own post-deploy check so the two are comparable. **Ten cold builds, ten
distinct principals, ten unwarmed shapes (`limit=31..41`), server-side `x-feed-elapsed-ms`.**

1. **PRIMARY — `concepts` present in `x-feed-shared` on ≥ 9 of 10.** Baseline 6/10.
   This is the whole ship. It is a header state, which no buffer-cache or warm-path condition
   can fake.
2. **`x-feed-cache: miss` on 10 of 10.** The precondition. If this fails the run is void and
   says nothing — a response-cache hit never reaches the stage at all.
3. **GUARD — the rebuild is still bounded by the TTL, not by the bucket.** Two requests on ONE
   unwarmed shape **> 90 s apart** must show the second NOT naming `concepts`, or must show a
   second build in the stage timings. If an hour-wide key ever serves past its 60 s TTL, this
   change widened staleness and must be rolled back. `FEED_SHARED_BUILD_CROSS_WORKER=0` is the
   no-deploy rollback.
4. **No new `x-feed-shared-tier` regression:** the first of two back-to-back requests may be
   `cross_worker`; the second must be `local`. The L1 hit path must not have started going to
   Redis (this is LAT-P103's invariant and this change must not disturb it).

### What a FAIL means, written down now

- 1 fails but 2 holds → the bucket widened and reuse did not follow. Most likely cause: the two
  worker processes are not sharing at all and LAT-P103's Redis tier is not live in this release.
  **Check `x-feed-shared-tier` before blaming this change** — that is a `-89` problem, not a
  `-90` one.
- 3 fails → **roll back**, via the config var, no deploy. This is the only outcome that is a
  correctness defect rather than a missed win.

## Honest ceiling, stated before the read

The fleet is **1 web dyno × `WEB_CONCURRENCY=2` = 2 worker processes** (LAT-P103's measured
figure). Rebuild rate for a bucket `B` and TTL `T`, with `B >= T`, is `1/T + 1/B`. So:

    before   B=30, T=60   ->  one rebuild every 30 s  (the bucket binds)
    after    B=3600, T=60 ->  one rebuild every ~59 s (the TTL binds)

That is a **2× reduction in concept-stage rebuild frequency, not more**. Anyone reading a
larger number out of this has read it wrong. The 6/10 → ≥9/10 bar is the reuse-rate consequence
of that halving, at the observed request arrival rate; it is not an independent claim.

**Not claimed, and must not be quoted as the improvement:** any p50 latency delta. The 2,482 ms
vs 1,295 ms split above is a real cost of the rebuild, but a paired before/after wall-clock read
on this endpoint is confounded by Postgres buffer sharing — LAT-P100 measured the same shape at
383.5 ms interleaved and 1,034.5 ms paired, a 2.7× swing from nothing but read order. The graded
claim is the header state.
