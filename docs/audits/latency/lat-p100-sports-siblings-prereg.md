# LAT-P100 — the Sports tab's fill-in requests, PRE-REGISTERED

**Cycle:** LAT-P100 · **Date:** 2026-08-27 · **Identity:** `LAT-P100-20260827-w77883`
**Directive:** Fable 2026-08-27, staged under Alex's standing authorization for this lane.
**Charter it runs under:** `docs/rulings/137-the-headline-is-the-cold-path-a-user-walks.md` and
`docs/audits/latency/lat-p099-cold-path-charter.md`. Nothing in this file amends either. The bars
below are **inherited**; none is invented by this cycle.

**Status of this file: FROZEN BEFORE THE FIX EXISTS.** It is committed before a line of the build
is written and before any *after* number is taken. The baseline numbers in §1 were taken first and
are recorded here so the comparison cannot be re-based later.

---

## 0. The ship, in the user's words

**A person opens the Sports tab and the board fills in — Live Now, Upcoming, and the player-prop
and playoff cards — without waiting for the server to rebuild all of it from scratch, again, for
them.**

LAT-P099 fixed the request that gates the tab's *first paint* (`mode=sports`, `limit=50`) and named
this one in its own handoff as **not shipped, with its number**. The tab issues three requests. One
was warmed. Two rebuild on every open, for every person, forever.

---

## 1. The baseline, measured BEFORE the build

Production slug `7833da68`, `/api/health` uptime 3,212 s at first read — clear of the post-deploy
window that reads as a false regression (memory: post-deploy latency isn't evidence). Server time
(`x-response-time`), never wall; the sandbox transport floor measured **246.7 ms** this session.

### 1a. The full native Sports request set, round-robin, fresh `x-session-id` per round (n=8)

| request | p50 | min | max | cache |
|---|---:|---:|---:|---|
| `sports_main` `/api/feed?limit=50&offset=0&mode=sports` | **656.0 ms** | 364.0 | 1,397.0 | `miss` 8/8 |
| `sports_backfill` `/api/feed?limit=200&offset=0&include_futures=false` | **151.5 ms** | 137.0 | 721.0 | `miss` 8/8 |
| `sports_grouped` `/api/futures/grouped-feed?limit=20` | **383.5 ms** | 190.0 | 1,010.0 | **no cache header at all** |

`sports_main` is LAT-P099's fix, which is **not deployed** (`62b67ee1` is not an ancestor of
`origin/master` `7833da68`). It is not this cycle's subject and no claim is made about it.

### 1b. Both grouped-feed shapes, measured alone and paired (n=6 each)

| shape | consumer | p50 | min | max |
|---|---|---:|---:|---:|
| `?limit=20` | **native Sports tab** (`APIClient.swift:743`) | **1,034.5 ms** | 916.0 | 1,308.0 |
| `?limit=20&sports_only=true` | **web Sports page** (`app/sports/page.tsx:109`) | **683.0 ms** | 597.0 | 915.0 |

⚠️ **The two reads of the same shape disagree by 2.7× and the report will say so rather than quote
the bigger one.** `sports_grouped` reads 383.5 ms interleaved among three other requests and
1,034.5 ms when only the two grouped shapes alternate. The interleaved run shares Postgres buffer
cache with the `/api/feed` builds running beside it; the paired run does not. **Both are honest
reads of different conditions, the true organic cost sits between them, and the claim this cycle
makes does not depend on which is right** — the fix takes the whole build out either way. The
`before` half of the A/B in §3 is re-measured with the *same* harness as the `after` half, and only
that pair is quoted as a delta.

### 1c. Why neither sibling can be cached today, from source

- **The backfill is a `/api/feed` shape that no warm entry can express.** `_prewarm_feed_shape`
  (`precompute_category_pages.py:449`) calls `get_feed(...)` with `include_events=True,
  include_futures=True` **hardcoded**. `include_futures` is part of the response-cache key
  (`feed_cache.feed_response_cache_key:65,93`), so the shape the client asks for
  (`include_futures=false`) is a key the warmer is structurally incapable of publishing. The
  LAT-P089 inert-principal share (`routes/feed.py:2221-2231`) then looks up an anonymous entry that
  has never existed and falls through to the build — the exact mechanism LAT-P099 fixed for
  `mode=sports`, one indirection deeper.
- **`/api/futures/grouped-feed` has no server cache of any kind.** `routes/futures.py:1531-1739`
  reads `limit*5` markets with `selectinload(outcomes)` and runs three pure grouping functions on
  every request. It takes **no principal** — no user, no session, no personalization — so its
  response is a function of `(category, sport, sports_only, limit)` alone. It is the cheapest thing
  on this board to cache correctly and it is the most expensive one uncached.

### 1d. Why a fifth warm target cannot just be appended

`test_prewarm_is_bounded` computes the pass's worst case as `20 (base) + FEED_PREWARM_DEADLINE_S ×
len(SHAPES)` against `soft_time_limit=120`. LAT-P099's fourth shape put that at exactly 120 and was
paid for by cutting the per-shape deadline 25 → 20. A fifth at 20 s would be 120 again. **A
per-item deadline multiplied by an item count is a budget that silently tightens every time
someone adds an item** — LAT-P099 wrote that sentence into the source and left the general fix for
the session that needed it. This is that session.

---

## 2. What will be built, stated before it exists

1. **Per-shape `include_events` / `include_futures` in `FEED_PREWARM_SHAPES`**, replacing the
   hardcoded `True`/`True` in `_prewarm_feed_shape`; every shape declares both explicitly and a
   guard asserts the declaration rather than trusting a default.
2. **A fifth feed shape, `sports_native_events`** — `limit 200, offset 0, include_futures False`.
3. **One wall budget for the whole pre-warm pass**, replacing the per-item deadline, allocated so
   that **no target can be starved by the ones ahead of it in loop order** (gotcha #34).
4. **A shared response cache on `/api/futures/grouped-feed`**, plus both of its real shapes
   (native `limit=20`, web `limit=20&sports_only=true`) enrolled as warm targets in the same pass.

**Boundaries, unchanged and explicit:** `backend/app/utils/feed_cache.py` is **NOT** edited — #2216
(lane1) owns feed keying and TTL. **No beat-schedule change** — the warmer stays inside the
existing every-2-minute `precompute_discover_candidate_base`. **No DDL, no migration, no index,
no config var.** Zero frontend, zero iOS.

---

## 3. The bars, frozen — every one inherited

| # | bar | value | derivation |
|---|---|---:|---|
| **B1** | grouped-feed native, post-deploy p50 | **≤ 150 ms** | LAT-P099's own registered prediction for a warmed shape, verbatim. Same unit, same claim shape: a warmed read is a Redis fetch, not a build. |
| **B2** | grouped-feed native, cache state | **`hit` on ≥ 2 of 3 samples** | LAT-P099's mechanical clause, verbatim (`shared_hit` there, `hit` here — this route has one shared key and no principal). A `miss` means the warmed key is not the key the route reads, and the fix is **inert**. |
| **B3** | sports events backfill p50 | **≤ 150 ms** | Same LAT-P099 prediction, same reason. Note the baseline (151.5 ms interleaved) is already **at** this bar: **B3 is therefore graded on the cache STATE (B4), and its p50 clause can only fail, never flatter.** Recorded so nobody later reads a met p50 as this fix working. |
| **B4** | sports events backfill, cache state | **`shared_hit` or `shared_stale_hit` on ≥ 2 of 3** | LAT-P099's clause verbatim. This is the load-bearing grade for the backfill. |
| **B5** | tab first-load p50 | **≤ 1,000 ms** | Charter §3, unchanged. No regression permitted on any headline row. |
| **B6** | hard ceiling, per sample | **≤ 6,000 ms** | `DiscoverViewModel.retryBudget = 6`. Charter §3, unchanged. |
| **B7** | pass worst case | **`20 + PASS_BUDGET` ≤ `soft_time_limit` (120 s)** | `test_prewarm_is_bounded`'s existing arithmetic, unchanged. |
| **B8** | per-target starvation floor | **every target's deadline ≥ `PASS_BUDGET / len(targets)`, for every target, in every loop order** | Gotcha #34, stated as an invariant a test can execute rather than a caution a reader can skip. |
| **B9** | beat cost | **< 1.25× AND < +60 s** on `precompute_discover_candidate_base` | The lane's standing `beat_cost` gate, unchanged from LAT-P099's declaration. |

**`PASS_BUDGET` is inherited, not chosen: 80.0 s**, which is exactly today's effective worst case
(`FEED_PREWARM_DEADLINE_S 20.0 × 4 shapes`). The pass therefore gains three targets **at no
increase in its own worst-case bound** — that is the point of replacing the multiplication.

**Correctness bars, which are not latency bars and outrank them:**

- **C1** — the warmed grouped-feed key must be **byte-identical** to the key the route reads,
  asserted by a test that derives both, not by an eyeball. LAT-P099's silent-failure case (a warmer
  that runs, succeeds, publishes and reports `outcome: ok` while warming a key nobody reads) is the
  failure mode with no other symptom, and it must be **red-provable**.
- **C2** — a cached grouped-feed response must equal the uncached one for the same params.
- **C3** — every prewarm shape must declare `include_events` and `include_futures` explicitly; a
  shape that omits either fails the suite rather than silently warming `True`.

---

## 4. The else branch, named in advance

If the build lands and the post-deploy read shows `miss` on the grouped shape, **the fix is inert
and the report says INERT in its first line** — not "improved". If the p50 clears but the cache
state does not, the win is buffer-cache luck and is reported as unproven. A bar that is missed is
reported with its margin; it is not moved.
