# LAT-P100 — the Sports tab's other two requests, and the route with no cache at all

**Cycle:** LAT-P100 · **Date:** 2026-08-27 · **Identity:** `LAT-P100-20260827-w77883`
**Directive:** Fable 2026-08-27, staged under Alex's standing authorization for this lane.
**Ship this serves:** a person opens the Sports tab and the board fills in — Live Now, Upcoming,
and the player-prop and playoff cards — without waiting for the server to rebuild all of it from
scratch, again, for them.

**Pre-registration:** `docs/audits/latency/lat-p100-sports-siblings-prereg.md`, committed in
`437f950a` **before** a line of the build was written.
**Charter:** ruling 137 + `lat-p099-cold-path-charter.md`. Unamended. Every bar inherited.
**Branch:** `program/latency-86`, stacked on `program/latency-85` @ `06b6f57f` (LAT-P099, unmerged).

---

## 0. THE HEADLINE — ruling 137's metric set, measured before the build

Production slug `7833da68`, uptime 3,235 s. Server time (`x-response-time`); the sandbox transport
floor measured **246.7 ms** wall this session and would otherwise swamp the table.

| tab | surface | n | p50 | p50 cold | cold % | max | bar | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Discover | native | 3 | **67.0 ms** | — | 0 % | 210.0 | 1,000 | ✅ MET |
| Discover | web | 3 | **21.0 ms** | — | 0 % | 23.0 | 1,000 | ✅ MET |
| Sports | native | 3 | **1,282.0 ms** | 1,282.0 | 100 % | 1,296.0 | 1,000 | 🔴 NOT MET |
| Sports | web | 3 | **15.0 ms** | — | 0 % | 15.0 | 1,000 | ✅ MET |
| Browse | both | — | **no server dependency** | | | | n/a | ✅ |
| Search | native | 3 | **16.0 ms** | — | 0 % | 38.0 | 1,000 | ✅ MET |
| My Stuff | native (signed out) | 3 | **16.0 ms** | 16.0 | 100 % | 17.0 | 1,000 | ✅ MET |
| cold search — `/api/events/search` | 6 terms | 6 | not run | | | | 1,000 | — |
| cold search — `/api/events/typeahead` | 6 terms | 6 | **3,176.0 ms** | | | 3,755.0 | 500 | 🔴 **NOT MET** |

**🔴 THE COLD-PATH BAR IS NOT MET, and neither failing row is this cycle's to fix.**

- **Sports native at 1,282 ms is LAT-P099's subject and LAT-P099's fix is not deployed** — `62b67ee1`
  is not an ancestor of `origin/master`. The row is reported, not claimed and not re-fixed.
- **Typeahead at 3,176 ms is #1866, and it is blocked on Alex's attended `psql` batch, not on a
  session.** LAT-P096 proved the cost is `FTS(name) OR name ILIKE` with no FTS expression index;
  LAT-P097 built the code-only alternative, measured it at 24–138× faster, and then **rejected it on
  its own census** (four of 36 terms lose recall; `grammys` → stem `grammi`, which is not a
  substring of "Grammy"). Two prior cycles established that the DDL is the only lever that preserves
  the recall. This cycle did not re-litigate that and did not build a third thing for the same
  queue.

**What this cycle took instead is the largest number on the board that a lane can actually build**:
the two Sports-tab requests LAT-P099 named in its own handoff as not shipped.

---

## 1. The finding — one of the three requests has never had a cache

The Sports tab issues three requests (`FeedViewModel.swift:272-296`): the `mode=sports` feed that
gates first paint, and two owned, cancellable, deadline-bounded siblings that fill the board in
behind it. Measured round-robin with a fresh `x-session-id` per round, n=8:

| request | p50 | min | max | cache |
|---|---:|---:|---:|---|
| `sports_main` `/api/feed?limit=50&mode=sports` | 656.0 ms | 364.0 | 1,397.0 | `miss` 8/8 |
| `sports_backfill` `/api/feed?limit=200&include_futures=false` | **151.5 ms** | 137.0 | 721.0 | `miss` 8/8 |
| `sports_grouped` `/api/futures/grouped-feed?limit=20` | **383.5 ms** | 190.0 | 1,010.0 | **no cache header at all** |

and the grouped shapes measured alone, n=6 each:

| shape | consumer | p50 | min | max |
|---|---|---:|---:|---:|
| `?limit=20` | native Sports tab | **1,034.5 ms** | 916.0 | 1,308.0 |
| `?limit=20&sports_only=true` | web Sports page | **683.0 ms** | 597.0 | 915.0 |

### ⚠️ The same shape reads 383.5 ms and 1,034.5 ms, and the report says so rather than quoting the bigger one

A 2.7× spread between two honest reads taken forty minutes apart. The interleaved run shares
Postgres buffer cache with the `/api/feed` builds running beside it; the paired run does not. The
true organic cost sits between them.

**The claim does not depend on which is right.** The fix does not make the build faster — it stops
the build happening on the request path at all, so the win is whatever the build costs. Quoting
1,034.5 ms as "the improvement" would be picking the flattering read of a number I measured twice
and got two answers for. Both are in the pre-registration; the graded comparison is the post-deploy
`X-Grouped-Cache` state, which no buffer-cache condition can fake.

### Why neither sibling could be cached, from source

**The backfill was not un-warmed. It was UNWARMABLE.** `_prewarm_feed_shape` called `get_feed` with
`include_events=True, include_futures=True` **hardcoded**, and `include_futures` is part of the
response-cache key (`feed_cache.feed_response_cache_key:65,93`). No entry in `FEED_PREWARM_SHAPES`
could have expressed `include_futures=false`, whatever anyone wrote in it. The LAT-P089
inert-principal share then looked up an anonymous entry that had never existed and fell through to
the build — the LAT-P099 mechanism exactly, one indirection deeper, and hidden behind two literals
rather than behind a missing row.

**`/api/futures/grouped-feed` had no server cache of any kind.** It reads `limit * 5` markets with
`selectinload(outcomes)` and runs three grouping passes on every request. It also takes **no
principal** — no user, no session, no personalization context — so its response is a pure function
of four query params. It is simultaneously the most expensive uncached thing on the tab and the
cheapest thing on the board to cache correctly.

---

## 2. The build

### 2a. The include flags become per-shape, and REQUIRED

Every shape declares `include_events` and `include_futures`; `_prewarm_feed_shape` reads them.

They are required rather than defaulted, and that is the whole design decision. A
`shape.get("include_futures", True)` would have been the natural fix and would have rebuilt the
identical trap one indirection down: the next author to add a shape and forget the key warms `True`
in silence, and the symptom is again a tab paying a cold build behind a green suite.
`test_every_shape_declares_its_include_flags_explicitly` asserts both the declaration and — via
AST, because an assertion about the shapes cannot see a literal in the call — that the warmer has
not re-hardcoded them.

### 2b. The fifth feed shape

`sports_native_events`: `limit 200, offset 0, include_events True, include_futures False`, no mode,
no `event_pct`. The absent mode is deliberate and is the subtle row in the table: the
Discover-default guard (`routes/feed.py:1822`) requires `include_futures` to be **true**, so it
skips this request and rewrites nothing — unlike `discover_native`, where the same absent mode *is*
rewritten to `"discover"`. Both then key through `{mode or 'discover'}`, which is why the two rows
look inconsistent in the shape table and are not.

### 2c. `/api/futures/grouped-feed` gets a response cache, and the route is the only writer

`app/utils/grouped_feed_cache.py` holds the key, the TTLs, the scope marker and the header — the
same single-source-of-truth arrangement `feed_cache.py` exists to provide, created **before** the
second writer rather than after the bug.

The route is the sole writer. The warmer calls it with a scope-only marker that suppresses the
**read**; the route publishes on its way out. Two properties fall out of that rather than being
maintained:

- the warmed key cannot drift from the read key, because there is only one derivation;
- a plain request-path miss populates the cache, so the endpoint is fast even if the beat is broken.

TTLs are set against the warm cadence, not by taste. **180 s fresh** must exceed the 2-minute beat
interval or the entry is missing for part of every cycle and whoever arrives in the gap pays the
build — the failure that reads as "the cache does not seem to help". **600 s stale** covers a beat
that fails or is skipped outright. `test_the_fresh_ttl_outlives_the_warm_cadence` asserts the
relationship against the beat schedule, not the numbers, so re-timing the beat fails the test
instead of quietly reintroducing the gap.

Both real shapes are warmed. **The native tab does not send `sports_only`; the web page does** —
a different key, a different entry, and precisely the "one row below the line being edited"
difference that cost the Sports tab 872 ms for two days in LAT-P099.

### 2d. The per-item deadline is gone — the general fix LAT-P099 asked for

`test_prewarm_is_bounded` computed the worst case as `20 + DEADLINE × len(SHAPES)`. LAT-P099's
fourth shape landed it exactly on `soft_time_limit` (20 + 25×4 = 120) and had to buy room by cutting
everyone's deadline to 20. A fifth would have done it again. **A per-item deadline multiplied by an
item count is a budget that silently tightens every time someone adds an item, and it fails at the
moment of the addition rather than at the moment of the mistake.**

The pass now has one wall budget. `FEED_PREWARM_PASS_BUDGET_S = 80.0` is not a new number: it is
exactly the old `20.0 × 4`. The worst case is **20 + 80 = 100 s against a 120 s soft limit —
identical before and after**, while the pass goes from four targets to seven.

**Gotcha #34 says a shared budget consumed in loop order starves whatever is last**, and a starved
warmer logs exactly what a healthy one logs. So the allocator divides the *remaining* budget by the
*remaining* targets, which makes the floor arithmetic rather than aspirational:

> `deadline_i ≥ PASS_BUDGET / N` for every *i*, in every order.

The induction is in the docstring and is **executed** by
`test_no_target_can_be_starved_by_the_ones_ahead_of_it` under the adversarial case where every
target burns its entire allowance. The upside is free and is the reason to divide the remainder
rather than hand out fixed slices: a target that finishes early returns its unspent time to
everyone behind it, so the normal case (seven fast targets) leaves the last one with nearly the
whole budget while the pathological case still cannot push any target below its floor.

---

## 3. RED-PROVEN SEVEN WAYS

Each mutation applied **independently** — the first attempt at this battery restored with
`git -C <repo-root> checkout -- <backend-relative-path>`, which silently matched no pathspec, so the
mutations stacked and the results were meaningless. That is gotcha #51's "`-C` pins the DIRECTORY"
arriving in a new costume, and it is written down here because the failure mode was *plausible
output*, not an error anyone would notice. The battery was re-run with `cp` backups and **every
restore verified by `cmp` and by shasum** (`d576d1cbd9dd0f8e` / `e82cda71a566029d`).

| mutation | red | which guard caught it |
|---|---|---|
| **M1** the backfill shape removed | **2 fail** | shape set; key equality `[sports_native_events]` |
| **M2** the shape present, `include_futures` **True** | **2 fail** | same two — **the silent case**: the warmer runs, succeeds, publishes a live key, and the tab still pays |
| **M3** the warmer re-hardcodes the flags | **1 fail** | `test_every_shape_declares_its_include_flags_explicitly` (AST) |
| **M4** naive shared budget (each target may take everything left) | **1 fail** | `test_no_target_can_be_starved_by_the_ones_ahead_of_it` |
| **M5** `grouped_native` copies the web's `sports_only` | **3 fail** | key equality, the iOS pin, and the route-level key test |
| **M6** the route stops reading its own cache | **6 fail** | incl. `test_a_warm_entry_is_served_without_touching_the_database` |
| **M7** an empty feed is published | **3 fail** | the empty-truth guards on both the route and the warmer |

**M6 is the one worth naming.** It kills the only assertion that can distinguish a cache on the hot
path from a cache that returns the right body *after* running the query it was added to avoid. Every
pure-helper guard in the unit suite stays green through M6. That is the "a plant must hit the
render" lesson applied to a backend route, and it is why the route-level suite exists alongside the
unit one.

---

## 4. The registered prediction — frozen here, graded after the deploy

From the pre-registration §3, unchanged:

| bar | claim |
|---|---|
| **B1** | grouped-feed native p50 **≤ 150 ms** (baseline 383.5–1,034.5 ms) |
| **B2** | `X-Grouped-Cache: hit` on **≥ 2 of 3** samples — a `miss` means the fix is **INERT** |
| **B3** | backfill p50 ≤ 150 ms — **already at bar; can only fail, never flatter** |
| **B4** | backfill `X-Feed-Cache ∈ {shared_hit, shared_stale_hit}` on ≥ 2 of 3 — **the load-bearing grade** |
| **B5/B6** | no headline row regresses past 1,000 ms p50 / 6,000 ms per sample |

**The else branch is named in advance and is not negotiable after the fact:** if the post-deploy read
shows `miss` on the grouped shape, the report's first word is **INERT**, not "improved". If the p50
clears while the cache state does not, the win is buffer-cache luck and is reported as unproven.

---

## 5. `beat_cost` — measured before, modelled after

`precompute_discover_candidate_base`, measured 2026-08-27 with
`backend/scripts/measure_beat_cost.py`:

```
beat                                    p50_s    p95_s  runs/24h  slot_s/day   %soft
precompute_discover_candidate_base       11.9     18.9         7          83       —
```

⚠️ **The `runs/24h` column is not a day.** `successes_window_s` is **672 s** — the counters were
reset by a recent release, so 7 is 7 runs in 11.2 minutes. The duration ring is the sounder basis:
**n=50, saturated, over 6,701 s** → p50 **11.9 s**, p95 **21.0 s**, max **26.4 s**, and 50 runs in
6,701 s is one per 134 s, which independently confirms the 2-minute beat is firing on cadence.
`last_result_summary` reads `{'candidate_base': 631, 'feed_prewarm': 3}` — 3 of the deployed slug's
3 feed shapes warming, i.e. healthy.

**Modelled after: +3 targets at their measured cold cost** (0.15 + 1.03 + 0.68 s) ≈ **+1.9 s** ⇒
p50 ≈ **13.8 s = 1.16×, +1.9 s**. Gates are ≥ **1.25×** **AND** ≥ **60 s** — **neither met**.
p95/soft ≈ 22.9/120 = **0.19** (bar 0.80). Worst-case bound **100 s**, unchanged.

⚠️ **`slot_s/day` cannot be graded from this window and is not claimed.** The script computes it as
`runs × p50` over whatever counter window it has, and this one is 672 s. Parked as **LAT-P100-1**
for the measurement lane: reconcile the beat's true daily run count (LAT-P099 recorded 233/24 h;
a 2-minute cadence implies ~720) before anyone grades a `slot_s/day` bar on this beat. The **ratio**
gate is the binding one here and it is met with margin.

⚠️ Also observed, not diagnosed: `incompletes_24h: 2` against `starts_24h: 7` in the same 672 s
window, `hard_kills_24h: 0`, `health: healthy`. Parked as **LAT-P100-2** — it is not a timeout
(p95 21 s against a 120 s soft limit), and it predates this branch.

---

## 6. What is NOT claimed

- **No after-number exists.** The branch is not deployed. Every latency claim in §1 is a baseline;
  §4 is a prediction with a frozen bar and a named inert branch.
- **The Sports first-paint row is LAT-P099's**, whose fix is still unmerged. This cycle changed
  nothing about it.
- **Typeahead is untouched**, deliberately. It is the biggest number on the board and it is blocked
  on a DDL, not on a session. Building a third thing for the same queue is work that cannot ship.
- **`feed_cache.py` was not edited.** #2216 (lane1) owns feed keying and TTL, and it merged into
  master mid-session (`b71e2c0d`); the boundary is why that merge does not conflict with this branch.

## 7. Named and NOT shipped, with its number

`/api/predictions/resolutions` (Discover sibling, 11.0 ms) and `/api/predictions/stats` (My Stuff,
16.0 ms) are both uncached and both under 20 ms. They are named so a later reader can see they were
measured and dismissed on arithmetic, not overlooked: at ~15 ms there is no session's worth of win
in either, and caching them would add two warm targets to a budget for no user-visible change.
