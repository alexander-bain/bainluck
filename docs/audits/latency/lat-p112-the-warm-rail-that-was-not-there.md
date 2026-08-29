# LAT-P112 — the warm rail that was not there

**Ship:** opening Discover stops randomly costing 3.7 seconds.
**Pillar:** DISCOVER.
**Branch:** `program/latency-97`, cut from `origin/master` @ `f0b512b8`.
**Measured on:** production slug `f0b512b8`, 2026-08-29 ~01:20–02:0x UTC
(2026-08-28 ~18:20–19:0x PT).

---

## 1. The number

Production's own always-sampled `/api/feed` window, one hour, read from
`GET /api/admin/latency-stats` — not from this session's instrumentation:

| cache status | n | p50 | max |
|---|---:|---:|---:|
| `hit` | 13 | **10.8 ms** | 21.3 ms |
| `stale_hit` | 6 | 14.4 ms | 20.3 ms |
| `other` (shared_hit / shared_stale_hit) | 41 | 43.5 ms | 299.3 ms |
| **`miss`** | **1** | — | **3,722.7 ms** |

One request in that hour cost **345× the hit p50**. `/api/feed` is four of the
seven needle member paths and the request that gates first paint on both
Discover surfaces and both Sports surfaces. A `miss` is not a slow cache read —
it is the absence of a cache entry, and the person who finds the absence is the
one who pays to fill it.

## 2. Why the entry is ever absent

Three facts, and the third is the one nobody had written down.

**(a) The stale mirror dies at 300 s.** `FEED_RESPONSE_STALE_TTL_SECONDS = 300`.
`routes/feed.py::_read_shared_feed_cache` reads the head, then `<key>:stale`.
Past 300 s from the last publication there is nothing to fall back to.

**(b) The warm rail is declared at 120 s.** `precompute-discover-candidate-base`
is `crontab(minute="*/2")` and hosts `_prewarm_discover_feed_responses`, which
warms all five first-paint shapes. 120 < 300, so on paper the mirror can never
expire. `#2236` proved its own invariant against exactly this declared number,
and `test_the_120s_host_beat_is_recorded_as_insufficient_for_live_shapes` still
asserts it.

**(c) 120 s is not what the queue delivers.** That beat is routed to
`background`. Measured over a 12,375 s window (49 consecutive fires, read twice
25 minutes apart so it is not one bad hour):

| | declared | p50 gap | p90 gap | max gap | gaps > 300 s |
|---|---:|---:|---:|---:|---:|
| `precompute-discover-candidate-base` (`background`) | 120 s | **152 s** | **517 s** | **2,511 s** | **10 / 49** |
| `prewarm-live-feed-shapes` (`realtime`) — the control | 40 s | **40 s** | 43 s | 54 s | 0 / 49 |

Summing `max(0, gap − 300)` across the window: **4,687 s of 12,375 s — 37.9 % of
wall-clock time the warm rail left the anonymous Discover entry uncovered.**

The control is what makes this a statement about the QUEUE rather than about
the beat scheduler. Same scheduler, same 24 hours, same process family, same
kind of work — and a beat on `realtime` held its declared period to the second
while the beat on `background` drifted by a factor of 21 at the tail.
`background` queue depth at the time of the reading: **25**. `realtime`: **0**.
`heavy`: 0.

**37.9 % is the exposure the warm rail leaves, not the fraction of time the
cache was empty**, and the distinction is deliberate: organic traffic
republishes on a miss, and when a shape is live the 40 s republish rail covers
it too. But every one of those covering events is *somebody paying the build*.
The hole is quietest-hours-shaped — it opens widest exactly when the live rail
has nothing to republish and there is no traffic to accidentally repair it,
which is when a brand-new install is most likely to be the first arrival.

## 3. The last-good rail does not cross the gap

`routes/feed.py` calls `_rc.remember_last_good(...)`, and the beat's own comment
says "the bounded last-good key + request-path publish keep cold pages covered
between beats." `request_cache.remember_last_good` is documented in its own
docstring as **in-process**. `WEB_CONCURRENCY=2` across multiple dynos means a
request landing on any worker that has not itself served that key during the
hole has no last-good to recall. It is a per-worker warm-up, not a rail.

## 4. The fix

The net rides the rail that is punctual and asks the only question it was not
asking: **is anything simply gone?**

`_prewarm_live_feed_shapes` — 40 s, `realtime`, p50 exactly 40 s over the
measured window — now selects `live_labels ∪ absent_labels`, where
`_absent_prewarm_labels` is the set of first-paint shapes whose `<key>:stale`
mirror does not exist.

Three properties it was built to have, each of which is a mutant in
`scripts/evals/feed_prewarm_absent_shape_net_mutations.py`:

* **It cannot invent work.** A label whose key is not known is SKIPPED, never
  built (M4). After a deploy the hash is empty and the net does nothing at all;
  it arms itself per shape as the host rail warms each one and records its key.
* **It probes the mirror, not the head** (M3). The head dies at 60 s under a
  120 s beat, so it is legitimately absent most of the time and a reader served
  from the mirror waits ~14 ms. Probing the head would rebuild every shape every
  40 s — the cost `#2236`'s docstring explicitly refused.
* **It never competes with the invariant** (M5). Live labels are ordered FIRST
  and take their budget slices first; absent labels get the remainder. Neither
  `FEED_LIVE_REPUBLISH_PERIOD_S` nor `FEED_LIVE_REPUBLISH_BUDGET_S` changes, so
  `live_republish_headroom_s()` is untouched and `40 + 20 == 60` still holds.

**The key is the route's own answer, carried forward, never re-derived.** The
comment above `FEED_PREWARM_LIVE_SHAPES_KEY` forbids a per-key marker precisely
because it would have to rebuild the response cache key outside the route — the
LAT-P001 two-writers trap. `_record_shape_cache_key` is called from inside
`_prewarm_feed_shape`, two statements after the scope readback, with the same
value that was just published to. A source guard
(`test_the_net_never_derives_a_cache_key_of_its_own`) keeps it that way, because
no behavioural test can tell a correct re-derivation from a carried-forward one
until the key builder changes.

**Cost when healthy — which is every ordinary pass.** One `HGETALL`, five
`EXISTS`, zero builds. The idle-pass affordability argument that made a 40 s
beat acceptable is preserved: the net's cost scales with the number of shapes
that are actually GONE.

**Named as out of scope:** `GROUPED_FEED_PREWARM_SHAPES`. Same exposure, but
`/api/futures/grouped-feed` is the Sports tab's third request and does not gate
first paint (`cold_path_snapshot.py` marks it `blocking=False`). Widening the
net to it would buy realtime slot time for a wait nobody is doing.

**Not taken, and it is the permanent form:** moving
`precompute-discover-candidate-base` off `background`, or unstarving that queue.
The net removes the user-visible consequence; it does not remove the cause. That
is a beat-schedule change with a blast radius across ~57 beats and it belongs to
whoever owns the queue, not to a latency cycle — **parked P112-1** and filed.

## 5. What did NOT get fixed, and was measured on the way

* **P112-2 — the personalization stage costs a brand-new install 200 ms on a
  cold worker.** Eight fresh-`x-session-id` Discover opens at the native shape:
  `personalization` = 203, 111, 17, 58, 17, 22, 16, 19 ms. The steady state is
  ~17 ms and the tail is a per-worker warm-up. `_load_personalization_context`
  issues seven sequential round trips for a principal the database has never
  seen — three of them are `select(...).where(False)`, which can return nothing
  by construction — and the result is then discarded by the LAT-P089 inert-
  principal share. Real, bounded, and an order of magnitude below the hole
  above; parked rather than bundled.
* **P112-3 — `precompute_category_pages` is being hard-killed.**
  `successes_24h: 2`, `starts_24h: 11`, `hard_kills_24h: 8`, durations
  84–147 s against `soft_time_limit=300`. Not the feed warm rail (that is the
  candidate-base beat) and not this lane's ship, but it is the same
  `background`-queue contention wearing a different symptom, and it is the
  strongest available corroboration of P112-1's cause.

## 6. Post-deploy bar, pre-registered

Registered here **before** the branch is merged, so it cannot be chosen after
the fact.

* **PRIMARY.** Read `GET /api/admin/task-metrics?task=prewarm_live_feed_shapes`
  after the release and confirm the pass still holds its 40 s p50 — the net must
  not have made the punctual rail late. Then read the live-republish status key
  and confirm `absent_labels` is PRESENT in the payload (that is the deploy
  check: the field's existence proves the code is live) and empty on healthy
  passes.
* **THE SHIP.** `/api/admin/latency-stats`, `/api/feed`, `by_cache_status`:
  `miss` must fall to **n = 0** over a full quiet-hours window. A non-zero
  `miss` n after deploy means the net did not arm — check whether the shape-key
  hash is populated before concluding anything about the gaps.
* **GUARD.** `X-Feed-Counts` on an anonymous Discover open must not move
  (`total` 102–104, `type_futures` 32 at the time of writing). The net publishes
  through `_prewarm_feed_shape`, which is the same builder with the same
  degraded/empty refusals, so a card-count change would mean the net is
  publishing something the route would not — and that rolls back.
* **The cause, unchanged.** P112-1 stays open regardless of the above. A green
  bar here means the consequence is covered, not that `background` is healthy.
