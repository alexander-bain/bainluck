# LAT-P106 — the latency needle exists, and here is its first reading

**NEEDLE: latency 711 ms @ 2026-08-28T17:51:51+00:00**

Production slug `bddb5f3f`, uptime 2,468 s (warm — a slug younger than five
minutes reads as a regression and this one is not). Pooled cold p50 over 22 cold
samples across 6 of 7 member paths, max 2,782 ms. Instrument
`backend/scripts/needle_latency.py`, committed with this report so the reading
reproduces identically.

This is the **first** point in the series, so there is no delta to report. It is
also, deliberately, not a claim that anything got faster today: nothing shipped
this cycle. The number exists so that the next five merges have something to
move.

## What the number is

`.claude/handoff/NEEDLE-SPEC.md` (Alex, 2026-08-28) gives this lane exactly one
glanceable number:

> latency: p50 cold load in ms across the three graded surfaces (Discover open,
> tab loads, cold search) — one pooled p50, cold only.

The pool is declared by path key, frozen in a literal, and pinned by
`backend/tests/test_needle_latency.py` so it cannot re-base without a visible
commit:

| surface | path key | endpoint |
|---|---|---|
| Discover open | `discover_native` | `/api/feed?limit=50&offset=0&event_pct=0.15` |
| | `discover_web` | `/api/feed?limit=20&offset=0&event_pct=0.15` |
| tab loads | `sports_native` | `/api/feed?limit=50&offset=0&mode=sports` |
| | `sports_web` | `/api/feed?limit=20&offset=0&mode=sports` |
| | `search_trending` | `/api/events/search/trending` |
| | `my_stuff_stats` | `/api/predictions/stats` |
| cold search | `search_cold` | `/api/events/search?q=` |

Only the request that **gates first paint** is in the pool. The siblings a tab
also issues — `/api/predictions/resolutions`, the 200-row event backfill,
`/api/futures/grouped-feed`, the `requires_auth` my-teams feed — are measured by
`cold_path_snapshot.py` and printed there, but nobody waits on them and a needle
that averaged them would be describing traffic rather than a wait.

Browse contributes nothing on purpose: it issues zero requests on appear
(`Views/LeaguesView.swift:55-78`). Printing 0 ms for a request that is never
issued would flatter the pool with something that is not a measurement.

Typeahead is out. It is a keystroke, not a load; it carries its own 500 ms bar;
and the non-voting `debug_timing` mode this program must use to sample it
without stuffing the trending head reads ~2.2x low.

The instrument is a wrapper over `cold_path_snapshot.py` (ruling 137) rather
than a new prober, so every discipline that queue paid for — a fresh principal
per sample, the cache state read from the route's own `X-Feed-Cache` rather than
assumed, server time rather than this sandbox's ~250–330 ms transport floor,
round-robin sampling — carries over unforked. It adds exactly two things: the
pool, and the line.

## The reading

```
surface        path key          graded  cold  cold%  p50 cold
Discover open  discover_native        5     5   100%   1,739.0
               discover_web           5     1    20%   2,190.0
tab loads      sports_native          5     4    80%     707.0
               sports_web             5     1    20%   1,057.0
               search_trending        5     0     0%         —
               my_stuff_stats         5     5   100%      15.0
cold search    search_cold            6     6   100%     563.0
               Browse                 —     —      —         —   (no request)

composition cross-check: balanced p50 (each member weighted equally) = 882.0 ms
POOLED COLD p50 = 711.0 ms   (n=22, 6/7 member paths, max 2,782.0 ms)
```

Organic `/api/admin/latency-stats` read taken **before** the run (ruling 127's
organic-first protocol, enforced mechanically via `--stats-before`): `/api/feed`
n=75, p50 1,211.9 ms, p95 2,729.8 ms, split hit 9 / stale_hit 12 / miss 53 /
other 1. That window's miss p50 of 1,265.2 ms is the organic corroboration for
the two Discover rows above.

**Contamination declared:** 30 `/api/feed` requests (all land in the
always-sampled `latency-stats` window — subtract before quoting it as organic),
20 other read-only tab requests, 6 `search_query_logs` rows from cold search
(#1916; cold search is a graded surface, so it is not optional here), 6
non-voting typeahead requests, 4 `/api/health`.

## The hazard, measured rather than feared

**You cannot take two readings back to back.** The four graded feed shapes are
pre-warmed on a schedule (`FEED_PREWARM_SHAPES`), and this instrument's own
anonymous-principal samples publish to the shared key on a miss, refreshing its
TTL every round-robin pass. A read taken about a minute after the one above came
back with **zero cold samples on six of seven member paths** and a single 11 ms
sample on the seventh. The sample-count floor (`MIN_POOL_N = 8`) refused it:

```
🔴 POOL TOO THIN TO PUBLISH — n=5 cold samples, floor is 8.
   A null is not a fast number. Re-run.
```

That refusal is the only reason an 11 ms "needle" was not published, and it is
now a test (`test_a_thin_pool_refuses_instead_of_publishing`). Two consequences
are written into the convention rather than left to be rediscovered:

1. Leave a real gap between runs.
2. A collapse in cold share is a statement about the cache, not about the
   product. Every run therefore prints the per-path cold n and a **balanced**
   cross-check — the median of the per-path cold medians, weighting each surface
   equally regardless of how often it happened to miss. The headline stays the
   raw pool because that is what the spec ratified; the cross-check is there so
   a move can be attributed rather than assumed.

## 🔴 The raw pool is ±25 % composition noise. The cross-check is not.

A third read was taken after a real cooldown (>10 minutes, same slug `bddb5f3f`,
same code, nothing deployed in between). It is not a stability confirmation — it
is the opposite, and it is the most important finding of this queue:

| | reading 1 (17:51:51Z) | reading 3 (18:01:48Z) | move |
|---|---:|---:|---:|
| **raw pooled cold p50 — THE NEEDLE** | **711.0 ms** | **536.0 ms** | **−24.6 %** |
| balanced cross-check | 882.0 ms | 873.0 ms | −1.0 % |
| cold samples in pool | 22 | 11 | −50 % |
| `discover_native` cold p50 | 1,739.0 ms | 3,566.5 ms | **+105 %** |
| pool max | 2,782 ms | 5,802 ms | +109 % |

**Nothing got faster between those two reads. Discover's cold open got twice as
slow, and the needle went down 25 %.** The mechanism is arithmetic, not mystery:
the feed paths' cold share collapsed from 11 cold samples to 5, so
`my_stuff_stats` — genuinely uncached, genuinely ~12 ms, genuinely what a
signed-out person waits for on that tab — went from 5/22 of the pool to 5/11 and
dragged the median through the fast mode. The balanced statistic, which weights
each surface once, moved 1 %.

This is ruling 137's own finding arriving one level up. 137 established that a
p50 over mixed cache states is a statement about the hit rate; cold-only fixes
that, but a *pool* over surfaces with different cold shares is a statement about
which surfaces missed. Same error, different axis.

The practical consequence for the ship: **the raw pool's run-to-run noise is
larger than any single merge in the READY stack is expected to buy.** LAT-P105's
win is ~383 ms on one surface; the needle moved 175 ms between two reads of
identical code. As specified, it cannot yet answer "did the day's work move the
dial" at the resolution the day's work operates at.

It is reported, not fixed. The metric changes only by Alex ruling
(`NEEDLE-SPEC.md`), so this queue publishes the ratified statistic, prints the
alternative beside it every run, and puts the choice in front of Alex. The
smallest change that would fix it — publish the balanced median instead of the
raw pool — is one line and one test edit.

Also worth Alex's eye independently of the metric question: reading 3's pool max
was **5,802 ms**, against `DiscoverViewModel.retryBudget = 6,000 ms`. That is a
cold Discover open ~200 ms from the point where the native client gives up and
paints disk last-good.

## What this number does NOT reflect

Production is on `bddb5f3f`, and `origin/master` is `bddb5f3f` — master is fully
deployed, so there is no merged-but-undeployed work. What there **is** is a
five-deep stack of finished, gated, `ready_for_integration` branches that are
neither merged nor deployed. Every one of them is a cold-path win aimed at
exactly the surfaces this needle pools, and none of it is in the 711 ms:

| branch | queue | head | ship, in one line |
|---|---|---|---|
| `program/latency-87` | LAT-P101 (#2236) | `ffea1ff9` | the Sports tab stops going cold once every ~90 s while a game is live (2.6–4.6 s, at random) |
| `program/latency-88` | LAT-P102 (#2211, #1916) | `9e36bb60` | the search head warmer is enabled and elected by real askers — `red sox`, measured 1.73 s cold |
| `program/latency-89` | LAT-P103 (#2143, #2203) | `c42bd538` | the shared feed stage survives a cold worker — built once per fleet, not once per process |
| `program/latency-90` | LAT-P104 (#2143) | `ea54da79` | the shared concept stage stops being discarded while still fresh (865–1,249 ms rebuild, twice a minute) |
| `program/latency-91` | LAT-P105 (#1459, #1090) | `05f1dda4` | the futures pool stops being scored twice on a cold Discover open (~383 ms of a ~1,594 ms build, 24 %) |

Verified this session, not copied from the tokens:
`git merge-base --is-ancestor <head> origin/master` returns **NO** for all five.
Merge order is load-bearing: `-87 → -88 → -89 → -90 → -91`.

**The needle moves when those merges deploy, which is the point.** Three of the
five (LAT-P103, LAT-P104, LAT-P105) also carry pre-registered post-deploy checks
that are owed on the same release and are still unrun.

## Convention

`docs/audits/latency/README.md` now carries the lane's report convention in the
directory the reports live in, so a session writing one cannot miss it: reports
**open** with ruling 137's cold-path rows and **end** with the NEEDLE line,
produced by `needle_latency.py` rather than hand-computed. If the number did not
move, print it unmoved; if the run refuses, say the needle was not obtainable
and why — a null does not license republishing the previous cycle's value.

## Gates

- `backend/tests/test_needle_latency.py` — **10 passed**, exit 0.
- **RED-FIRST, four mutations, each applied alone from a `cp` backup with the
  restore verified by `cmp` before the next** (gotcha #51); the harness refuses
  a mutation whose pattern matches nothing, so a no-op cannot read as a pass.
  Final `shasum -c` against the pristine manifest: OK.

  | | mutation | result |
  |---|---|---:|
  | M1 | a non-blocking sibling joins the pool | **4 fail** |
  | M2 | the NEEDLE line changes shape | **1 fail** |
  | M3 | the thin-pool floor is removed | **1 fail** |
  | M4 | warm samples leak into the pool | **3 fail** |

- ruff: clean on both new files. black 26.5.1: clean on both new files.
- No migration, no beat change, no config var, no route, no frontend, no iOS.
  Two new files under `backend/`, two new docs.

## What is NOT claimed

- **No delta.** This is the first point in the series.
- **No win.** Nothing shipped this cycle; the queue's deliverable is the
  instrument and the reading.
- **The pool's composition is not under the lane's control**, and this is now
  measured rather than suspected: two reads of identical code ten minutes apart
  gave 711 ms and 536 ms. The balanced cross-check is printed to make that
  attributable; it is not a second headline, and changing the headline would
  need an Alex ruling.
- **`my_stuff_stats` is a real member and a heavy influence.** It is genuinely
  what a signed-out person waits for on that tab, it is genuinely uncached, and
  at ~12–15 ms it pulls the raw median down hard whenever the feed paths happen
  to be warm. That is the spec's pool, faithfully applied — flagged here so a
  future reader does not mistake it for a bug.
- **Reading 3 is not evidence that Discover got slower.** Two cold samples are
  two cold samples. It is evidence that the pool is thin enough for that to
  matter, which is the point being made.

## Alex-ask

Filed to `YOUR-TURN.md`: the needle is live and reading 711 ms, but as ratified
it carries ±25 % composition noise — larger than any single win in the READY
stack. One-line question: keep the raw pooled p50, or switch the published
statistic to the balanced median (each graded surface weighted once)? Both are
computed and printed every run today, so the switch costs one line and one test
edit, and no re-baselining beyond publishing both for one overlapping cycle
(ruling 127).
