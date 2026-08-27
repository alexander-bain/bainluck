# LAT-P099 — the cold-path baseline, and the Sports tab's missing line

**Cycle:** LAT-P099 · **Date:** 2026-08-27 · **Identity:** `LAT-P099-20260827`
**Directive:** Alex 2026-08-26, authored in Alex's Fable session and delivered through the lane
runner Alex launched under his standing authorization. Three items.
**Ship this serves:** a person opening the Sports tab sees the board instead of a spinner — the
first time, without having been lucky enough to arrive while a cache was warm.

**Ruling banked:** `docs/rulings/137-the-headline-is-the-cold-path-a-user-walks.md`.
**Pre-registration:** `docs/audits/latency/lat-p099-cold-path-charter.md`, committed in
`bf7e0aa1` **before** the first number was taken.
**Instrument:** `backend/scripts/cold_path_snapshot.py`.
**Guard suites:** `backend/tests/test_cold_path_charter.py` (12 pass) and
`backend/tests/test_feed_prewarm.py` (29 pass). Both RED-proven against deliberate mutations,
with the script restored and shasum-verified each time
(`838cabb62794fbf67345c99ce6d58677e66dea95b78e9772518b139b1dd4e70d`):

| mutation | red |
|---|---|
| the `sports_native` shape removed entirely | **3 of 39 fail** — `test_warm_shapes_match_the_first_paint_requests`, `test_every_native_first_paint_shape_is_warmed`, `test_native_sports_warm_shape_tracks_the_ios_client` |
| the shape present but `event_pct` set to `0.15` instead of `None` | **3 of 29 fail**, including `test_the_warmed_anon_key_is_the_key_the_inert_share_reads[sports_native]` — the silent-failure case, where the warmer runs, succeeds, publishes, and warms a key nobody reads |

**Production state while measuring.** No release landed during this session.
`origin/master` = `06fdad74` = the live slug, `/api/health` reporting `commit: 06fdad74` with
`uptime 8,642 s` (2.4 h) — well clear of the post-deploy window that reads as a false regression.
Every number below is server-side `x-response-time`; the sandbox's transport floor to Heroku
measured **244.7 ms** wall this session and would otherwise swamp the table.

---

## 0. THE HEADLINE — the new metric set, measured

The first table under ruling 137. Fresh `x-session-id` per sample; cache state read from
`X-Feed-Cache`, never assumed.

| tab | surface | n | **p50** | p50 cold | cold share | max | bar | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **Discover** | native | 3 | **57.0 ms** | — | 0 % | 220.0 | 1,000 | ✅ MET |
| **Discover** | web | 3 | **21.0 ms** | — | 0 % | 27.0 | 1,000 | ✅ MET |
| **Sports** | native | 3 | **872.0 ms** | 872.0 | **100 %** | 1,184.0 | 1,000 | ⚠️ MET, but see below |
| **Sports** | web | 3 | **18.0 ms** | — | 0 % | 19.0 | 1,000 | ✅ MET |
| **Browse** | both | — | **no server dependency** | | | | n/a | ✅ |
| **Search** | native | 3 | **19.0 ms** | — | 0 % | 20.0 | 1,000 | ✅ MET |
| **My Stuff** | native (signed out) | 3 | **17.0 ms** | 17.0 | 100 % | 17.0 | 1,000 | ✅ MET |
| **cold search** — `/api/events/search` | 6 terms | 6 | **469.0 ms** | | | 792.0 | 1,000 | ✅ MET |
| **cold search** — `/api/events/typeahead` | 6 terms | 6 | **2,968.5 ms** | | | 3,380.0 | 500 | 🔴 **NOT MET** |

### 🔴 THE COLD-PATH BAR IS NOT MET, and the failure is typeahead — again.

But the number that **moved this cycle** is Sports, and it is the one worth reading first.

---

## 1. Item 2 — the baseline, and the one row that does not belong

Six of the eight measured surfaces clear comfortably. One row is 48× its sibling:

```
Discover native  limit=50 event_pct=0.15    57 ms   shared_hit  3/3
Sports   native  limit=50 mode=sports      872 ms   MISS        3/3
Sports   web     limit=20 mode=sports       18 ms   hit         3/3
```

Same client, same release, same session, three requests apart in a round-robin. **The native
Sports tab pays a full cold build on every single open**, and the two rows bracketing it do not.

Per-sample, so nobody reads a median as a trend: `1,184 · 609 · 872 ms`, `X-Feed-Cache: miss` on
all three, 79,836 bytes and 50 items each time. The build's own stage header on the slowest:

```
wall=1166.0; db=687.9; app=478.0; q=20; maxq=366.2
events=444.7  futures=323.8  concepts=187.3  team_enrichment=69.1  golf=63.2
```

20 queries and 687.9 ms of database time, per open, per person.

### Why — and it is one missing line, not a slow query

The feed response cache is keyed per principal *and per shape*
(`feed_cache.feed_response_cache_key`). The native client sends a persistent `x-session-id`
(`APIClient.swift:162`), so its key is `s:<uuid>` at a 5 s TTL — useless as a first-open cache.
What saves the Discover tab is LAT-P089's **inert-principal share** (`routes/feed.py:2224`): when
the personalization context equals a default-constructed one, the request reads the **anonymous**
entry of the same shape instead of building.

That share can only hit an anonymous entry that something published. `FEED_PREWARM_SHAPES`
published three:

| warmed shape | limit | mode | serves |
|---|---:|---|---|
| `discover` | 20 | — | web Discover |
| `sports` | 20 | `sports` | web Sports |
| `discover_native` | 50 | — | **native Discover** |

Native Sports asks `mode=sports` at `APIClient.fetchFeed`'s **default limit of 50**
(`FeedViewModel.swift:499` → `APIClient.swift:606`). The warmed sports shape is the *web's* 20.
**A different limit is a different cache key**, so the share looked up an anonymous entry nothing
had ever published, found nothing, and fell through to the build. Three times out of three.

### The part worth recording is that this is LAT-P089's own lesson, arriving twice

LAT-P089 diagnosed exactly this mechanism, wrote it out at length in the comment above the
constant — *"the NATIVE shape is a different limit, so it is a different key, and nothing warmed
it"* — and enrolled `discover_native`. Its comment even names the sibling: the warmer exists to
keep *"the anonymous Discover + Sports first-paint responses"* warm. The Sports line was one row
below the line being edited, was reasoned about in the same paragraph, and was left warming the
wrong key.

**A fix scoped to the surface that surfaced the bug is how a class survives its own repair.** The
guard test that existed asserted each shape it *knew about*, which is precisely why it stayed
green: nobody had written the missing member down, so nothing could notice it was missing.

---

## 2. Item 3 — the build

`FEED_PREWARM_SHAPES` gains a fourth entry, `sports_native`: `limit 50, offset 0, event_pct None,
mode "sports"`. `event_pct` is `None` and not `0.15` deliberately — the Discover-default guard at
`routes/feed.py:1822` skips `mode=sports`, so the request path keeps `None`, and a warmer
supplying `0.15` would key differently and warm nothing.

**Code-only. No DDL, no migration, no beat-schedule edit, no `feed_cache.py` change** (#2216 owns
keying and TTL and was not touched).

### The mechanism is proven offline, not merely predicted

A prediction has to wait for a deploy. The key arithmetic does not.
`test_the_warmed_anon_key_is_the_key_the_inert_share_reads`, parametrised over every declared
native shape, asserts that the anonymous key the warmer publishes is **byte-identical** to the
anonymous key the inert-principal share re-derives for that client's request. That equality is
the entire fix: a native client is the `s:<uuid>` principal and can never read the warmer's key
directly, so the warm is worth exactly nothing unless the share lands on the same string.

It is a real gate, not a restatement. Setting the new shape's `event_pct` to `0.15` — the
plausible mistake, copied from the Discover row directly above it — turns it red, and that is
precisely the case with no other symptom: the warmer would still run, still succeed, still
publish, still report `outcome: ok`, and the tab would still pay 872 ms. **A broken warmer and a
working one produce identical logs**, which is why this had to be an assertion rather than a
post-deploy observation.

### One thing the fourth shape broke, and it is a better finding than the fix

`test_prewarm_is_bounded` computes the warm pass's worst case as
`20 (base deadline) + FEED_PREWARM_DEADLINE_S × len(FEED_PREWARM_SHAPES)` against the task's
`soft_time_limit=120`. At three shapes that was `20 + 25×3 = 95`. The fourth made it
**`20 + 25×4 = 120` — exactly the limit**, and the guard went red.

`FEED_PREWARM_DEADLINE_S` moves **25.0 → 20.0**. That is not headroom arithmetic; it is what the
deadline is *for*. It bounds the beat, and it is not a licence for a slow build — **the native
client gives up at 6 s** (`DiscoverViewModel.retryBudget`), so a shape still building at 20 s is
warming a payload no user would have waited for. Against measurement it is not close: the whole
beat, base and every shape, runs at **p50 9.8 s / p95 14.2 s** across 233 runs in 24 h, and the
shape being added measured 872 ms.

**The general form, written into the test rather than into a report nobody re-reads:** a per-item
deadline multiplied by an item count is a budget that silently tightens every time someone adds
an item, and it fires at the moment of the *addition* rather than at the moment of the *mistake*.
A fifth shape will need more than another constant nudge — the pass needs one wall budget instead
of a per-shape one, and whoever builds that should read gotcha #34 first, because a shared budget
consumed in loop order starves whatever is last.

### `beat_cost` (doctrine, MECHANICAL SPEC — declared, with the arithmetic shown)

    beat_cost: none
      precompute_discover_candidate_base  BEFORE p50 9.8s · p95 14.2s · 233 runs/24h
                                          · slot_s/day 2272 · %soft — (no soft limit hit)
      measured 2026-08-27 (UTC) via backend/scripts/measure_beat_cost.py --task
               precompute_discover_candidate_base

`none` is the declaration, and here is the check a reader can redo. The added shape's build cost
is the 872 ms this cycle measured on the request path, so the modelled after is ~10.7 s:
**1.09× and +0.9 s** against gates of ≥ 1.25× **and** ≥ 60 s — neither met. `p95/soft` ≈ 15.1/120
= **0.13**, well under 0.80. `slot_s/day` ≈ 233 × 10.7 = **2,493**, under 3,600. The lowered
per-shape deadline only reduces the worst case. ⚠️ The **after** is modelled, not measured, for
the reason every pre-merge beat_cost is: the change is not deployed. It is owed as a post-deploy
re-read (§5).

---

## 3. What the rest of the table says, so nothing is quietly dropped

**Typeahead is still the largest cold number and is still not this session's to fix.**
2,968.5 ms p50 in non-voting debug mode, which LAT-P097 measured as reading **~2.2× low** against
a true first touch — so the user-felt figure is in the same ~6.5 s band the program has been
reporting. LAT-P096 already did this session's work on it: index spec, red-first gate, frozen
bars, DDL text. It is blocked on **Alex's attended `psql` batch** (ruling 131), together with
`ix_fm_open_category` (LAT-P094-1). Building a third thing to sit in the same queue is work that
cannot ship. This cycle did not touch it.

**Cold `/api/events/search` clears at 469 ms** (max 792 ms) on the same six obscure terms that
cost `/typeahead` 2,968 ms. That is not a contradiction and it is worth stating: the two routes
have different name predicates — `/search` is ILIKE-only (`events.py:3342`), `/typeahead` adds a
stemmed FTS arm (`events.py:4416`), and the FTS arm is what LAT-P096's index attacks. The same
terms through the two routes separate 6.3×, on the same slug, in the same minute. ⚠️ Six obscure
club names are not the whole distribution — LAT-P097 measured `/search` at 11.9–18.5 s on
`winner` / `champion`. **The 469 ms is this term set's number, not the route's.**

**The Sports tab's non-blocking sibling is cold too, and it is named rather than shipped.**
`/api/feed?limit=200&include_futures=false` — the events backfill that fills Live Now / Just
Happened / Upcoming — measured **543 ms p50 (150 · 543 · 800), `miss` 3/3**. Nothing warms it
either. It does **not** gate first paint (`FeedViewModel.swift:114`, a 10 s optional sibling), so
it is not a headline number and it is not this cycle's ship. Enrolling it needs
`_prewarm_feed_shape` to carry `include_events` / `include_futures` per shape rather than
hardcoding both `True` — a wider change to a warmer that Discover depends on, and it lands
against the same worst-case budget §2 just tightened. **Named, sized, and left for a session that
can do it with the budget rework rather than beside it.**

**Everything else clears with room.** `/api/predictions/resolutions` 18 ms,
`/api/predictions/stats` 17 ms, `/api/futures/grouped-feed` 206 ms, `/api/events/search/trending`
19 ms — all uncached, all cheap.

**Browse costs nothing, and that is a source fact, not a measurement.** Zero network requests on
appear (`Views/LeaguesView.swift:55-78`); the web Browse is a link dropdown with no route
(`components/BottomNav.tsx:56`). Reported as NO SERVER DEPENDENCY and pinned by a test that fails
if the view ever grows an `APIClient` reference — because a request that is never issued has no
latency, and a printed zero reads as a measured pass.

**My Stuff's authenticated feed is the one hole in the table.** `my_teams_only=true` without a
user returns an empty `requires_auth` body with no cache header (`routes/feed.py:2049-2069`) — a
different code path that exits before the work starts, so the anonymous probe is not a floor and
is not reported as one. This sandbox holds an admin secret, not a user JWT. What is known
structurally: the key is `u:<id>`, TTL 30 s, and **nothing pre-warms it and nothing can** — the
content depends on which teams that person follows. That tab's signed-in first load is
unmeasured, and it is the only headline row this instrument cannot reach.

---

## 4. Registered prediction, before the deploy

Frozen here so the post-deploy read grades a claim rather than describes an outcome.

**Prediction.** Once `06fdad74 + this change` is live and one `precompute_discover_candidate_base`
pass has run (≤ 2 min after boot), a re-run of `cold_path_snapshot.py --label LAT-P099-after`
returns, for `sports_native`:

1. `X-Feed-Cache` in `{shared_hit, shared_stale_hit}` on **≥ 2 of 3** samples — the mechanical
   claim, and the one that fails loudly if the key arithmetic is wrong;
2. **p50 ≤ 150 ms**, against 872 ms. The band is derived, not hoped: a shared hit is serialization
   plus transfer, and the two measured comparators are `discover_web` at 19–27 ms for 59.5 KB and
   `discover_native` at 53–220 ms for 126.9 KB. The sports payload is 79.8 KB, between them.

**What refutes it.** A `miss` on any sample after a warm pass means the warmer's published key and
the share's computed key differ, and the fix is inert — the LAT-P089 failure mode repeating a
third time. A `shared_hit` with a p50 above 150 ms means the cost was never the build, and §1's
whole attribution is wrong.

**What it does NOT claim.** Nothing about `sports_web`, `discover_*` (already warm), the events
backfill (not enrolled), or typeahead. A move in any of those is somebody else's change or noise.

---

## 5. What the next session should do

1. **Re-run `cold_path_snapshot.py` against the deployed slug** and grade §4's prediction. Same
   instrument, same term set, so the delta is a delta.
2. **`futures_query` on `/api/events/typeahead` (#1866) is still the named ship**, and still needs
   **Alex's attended `psql` batch** — LAT-P096's index and `ix_fm_open_category` (LAT-P094-1) ride
   together, two pre-registered gates, one attended window.
3. **The Sports events backfill** (§3), if and when the warm pass gets a single wall budget.
4. **My Stuff signed-in** is the unmeasured headline row. Measuring it needs a user JWT this lane
   cannot mint — that is a measurement-lane request with a named ship, not a build-lane task.

---

## 6. Contamination introduced by this cycle, declared

Ruling 127's protocol, enforced by the instrument rather than by memory (`--stats-before`).

- 🔴 **The organic `/api/feed` census was read FIRST**, before any probe:
  `lat-p099-latency-stats-T0.json`, 02:55:17Z, 1-hour window, **n=57, p50 20.7 ms, hit 28 /
  stale_hit 29, and ZERO misses**. That zero is worth its own line — LAT-P097 measured an 18.6 %
  organic miss share and the PRD's first honest measurement was 37.5 %. ⚠️ It is one hour of
  overnight traffic (n=57) and is reported as a measurement, not a trend.
- **`/api/feed`: 18 requests issued by this run.** All of them land in the always-sampled
  `latency-stats` window and must be subtracted before that window is quoted as organic. Twelve
  were warm hits (inflating the hit bucket, deflating any later-quoted miss share) and six were
  genuine cold builds this lane caused — three `sports_native`, three `sports_event_backfill` —
  costing production roughly 4.1 s of database time in total.
- **`/api/events/typeahead`: 6 requests, `debug_timing=1`, ZERO votes** into
  `search:trending:24h`. LAT-P097's contamination finding is discharged, not re-incurred.
- **`/api/events/search`: 6 requests**, each writing one `search_query_logs` row — the table #1916
  exists to clean. Declared, and the reason it is opt-in.
- **12 read-only requests** to `/api/predictions/*`, `/api/futures/grouped-feed` and
  `/api/events/search/trending`; 4 to `/api/health`.
- **`POST /api/admin/db-query`: zero.** Nothing this cycle needed one.

**Provenance:** LAT-P099, 2026-08-27. Related: #1545, #1866, #2216, LAT-P089, LAT-P096.
Raw: `lat-p099-latency-stats-T0.json`, `lat-p099-baseline.json`.
