# The `/api/feed` miss path — decomposition and the single biggest lever

**LAT-P084 item 1** (Fable directive 2026-08-24, pasted and reviewed by Alex).
Measurement artifact. **No code is proposed as shipped here** — the directive
said *"Measurement before code; code only with a red-first gate"*, and the
proposal at the end is costed, not built.

---

## 0. The charge

> your own baseline says feed p50 is 16.2ms but MISS SHARE IS 37.5% AT 4,121ms,
> p95 5.5s. That means better than a third of feed requests eat four seconds.
> This is the headline-metric mover. First: re-measure DECONTAMINATED (post
> wave-2 deploy, probe samples excluded, window not straddling a release). If
> the miss share holds anywhere near 37%, decompose the miss path — what builds,
> what blocks, what's cacheable — and bring the single biggest lever as a costed
> proposal.

---

## 1. Decontamination — all three conditions verified, and the read taken FIRST

Ruling 127 ("take the feed read FIRST — a census that samples every request
counts the observer") governs the order of operations here, and it was honoured:
`/api/admin/latency-stats` was read at **16:33:34Z**, before this lane's session
issued a single request to `/api/feed`.

| condition | verified |
|---|---|
| post wave-2 deploy | v3885 (`81380151`) deployed 2026-08-23 14:48 PDT — **~18.7 h** before the window opened |
| window does not straddle a release | **holds for the headline read, NOT for the whole session.** v3885 (`81380151`) was current from 16:30Z until **17:23:50Z**, when the wave-2 deploy landed as **v3886** (`b5c2a750`). The headline population in §2b is bounded at 17:06:13Z and is entirely v3885. Reads after 17:23:50Z straddle the release and are partitioned rather than pooled — see the correction at the head of §2b |
| probe samples excluded | window opened with **zero** samples from this lane; contamination is separable by subtraction (§2) |

`/api/feed` is on `always_sampled_endpoints`, i.e. it is a **census, not a 1/10
sample**. That is what makes ruling 127 binding and what makes the subtraction
in §2 exact rather than statistical.

---

## 2. The decontaminated headline — the miss share HOLDS, and it may be worse

**First read, 16:33:34Z, n=3.** 1 hit (64.0 ms), 1 **miss (4,358.4 ms)**, 1
stale_hit (37.9 ms). Miss share 1/3; miss p50 4,358 ms against the 4,121 ms
baseline.

That denominator cannot resolve 33% from 37.5% and is reported as such. **It is
itself the first finding:** the 37.5% baseline rested on n=24, of which 7 were
the previous lane's own probes — organic n was ~17. Organic `/api/feed` traffic
is running at **~3 requests/hour**, so every figure in this section is a
small-sample figure and no percentile below p50 is answerable at all
(`min_samples` requires n≥20 for p95).

**Passive sampler, 60 s cadence, 30 minutes later (17:01:17Z), n=20:**

| bucket | n | p50 | min | max |
|---|---|---|---|---|
| hit | 3 | 28.4 ms | 22.7 ms | 64.0 ms |
| stale_hit | 7 | 16.4 ms | 7.1 ms | 37.9 ms |
| **miss** | **10** | **2,629.2 ms** | **1,888.5 ms** | **7,531.6 ms** |
| all | 20 | 64.0 ms | 7.1 ms | 7,531.6 ms (p95 6,089.1 ms) |

Four of those 20 are this lane's decomposition probes (§3), and they are
attributable one-for-one: the accumulator moved 3→7 with buckets matching
A/B/C/D exactly. Subtracting them leaves **organic n=16: 2 hit, 6 stale_hit, 8
miss — a 50% miss share.**

> **The honest reading.** The miss share is **not** refuted and is if anything
> understated by the baseline. But at organic n=16 the 95% binomial interval on
> 8/16 runs roughly 25–75%, so "37.5%" and "50%" are the same measurement. What
> IS resolved, and does not depend on the denominator, is the **cost**: every
> single miss in every window measured has landed between 1.9 s and 7.5 s, and
> the buckets are bimodal with nothing in between — 7–64 ms or 1,888+ ms. There
> is no middle. A user either pays ~20 ms or ~2.5 s.

p95 (6,089.1 ms) became answerable only at n=20 and is consistent with the
5.5 s baseline.

### 2b. The PROBE-FREE read — the ring evicted this lane's probes on its own

The n=16 organic figure above rests on a **subtraction**, and a subtraction is an
argument. The ring settled the question without one.

`oldest_sample_age_s` grew 1:1 with the wall clock from the first read onward —
the ring had **not yet rolled** and was accumulating from a fixed floor at
16:30:54Z. It began evicting at 17:31, and at **17:36:32Z the eviction boundary
crossed this lane's probe burst**: `oldest_sample_age_s` jumped 3,566 s → 2,859 s
in one 60 s tick (all four probes fired inside four seconds, so they leave
together), and the accumulator moved

    n 59 → 55    hit 16 → 15    stale_hit 13 → 12    miss 30 → 28

— i.e. it dropped **exactly 1 hit, 1 stale_hit and 2 miss**, which is probe
C / A / B+D one for one. The subtraction in §2 is therefore not merely
defensible; it was independently reproduced by the instrument's own retention.

🔴 **CORRECTION, same day, before this document left the lane.** The 17:38:33Z
read was first written up here as "no release inside it." **That was wrong.**
Heroku **v3886** (`b5c2a750`) deployed at **17:23:50Z**, seventeen minutes before
that read and squarely inside its 49.7-minute window — the wave-2 deploy this
lane had been waiting on for item 3, which landed while the sampler was running.
Decontamination condition 3 was therefore violated for the *probe-free* read, in
the one direction the §1 table asserts it is not. It is corrected rather than
quietly restated, and the correction turns out to make the finding **stronger**,
which is exactly why it must not be the lane that decides whether to mention it.

The two contaminants are separable, and — usefully — they contaminate **different
reads**, because the ring evicts by age while the release arrives by clock:

- reads **before 17:23:50Z** are release-free but still hold this lane's 4 probes;
- reads **after 17:36:32Z** are probe-free but straddle the release.

The release-side contamination is exactly attributable. The ring was silent from
17:06:13Z to 17:25:27Z (`newest_sample_age_s` climbed 782 → 1,089 s across six
consecutive reads with `n` frozen at 56), and then took **6 samples**: +2 at
17:25:29 (1 hit, 1 miss) and +4 at 17:26:29 (4 hits). Those six, and only those
six, are post-v3886.

🟢 **THE DECONTAMINATED HEADLINE — probe-free AND release-free, from the
17:24:22Z read (`n`=56) with this lane's four probes removed. Window 16:30:48Z →
17:06:13Z, slug v3885 / `81380151` throughout:**

| bucket | n | p50 | p95 | min | max |
|---|---|---|---|---|---|
| hit | 11 | — | — | 9.4 ms | 77.6 ms |
| stale_hit | 13 | — | — | 7.1 ms | 37.9 ms |
| **miss** | **28** | **2,433.6 ms** | **6,089.1 ms** | **958.6 ms** | **7,531.6 ms** |
| **all** | **52** | — | — | 7.1 ms | 7,531.6 ms |

**MISS SHARE = 28/52 = 53.8%** (95% CI 40.3–67.4%). `unbucketed_samples = 0`, so
the three buckets are the whole census.

**It survives every partition of the contamination, and the point estimate rises
as the contamination is removed:**

| population | n | miss | share |
|---|---:|---:|---:|
| raw ring @ 17:38:33Z (probes evicted, release straddled) | 55 | 28 | 50.9% |
| **pre-release organic @ 17:24:22Z — the headline** | **52** | **28** | **53.8%** |
| pre-release organic surviving in the 17:38:33Z ring | 49 | 27 | 55.1% |
| post-v3886 only | 6 | 1 | *(16.7% — n=6, nothing concludable)* |

The post-release cell is reported because it is the only cut that could be read
as an improvement, and at n=6 it is not one: it is five hits and one miss taken
within three minutes of a dyno restart, which is the window in which post-deploy
readings are least trustworthy in *either* direction. No claim is made from it.

**The directive's question is answered: the miss share does not merely hold near
37.5% — 37.5% is at the very bottom of the interval, and the point estimate is
better than half.** Across all 65 reads spanning 16:34→17:38 it never once fell
below 42.9% after the first three samples, and it sat between 50.0% and 53.6%
for the last 38 minutes. Series artifact:
`docs/audits/latency/lat-p084-feed-cache-series-2026-08-24.jsonl` (65 reads,
60 s cadence, passive — the sampler touches `/api/admin/latency-stats` only and
never `/api/feed`, which is how ruling 127's observer problem was avoided rather
than corrected for).

⚠️ **Report the overall p50 with its split or not at all.** It reads **958.6 ms**
here against **16.2 ms** in the previous cycle's baseline. Almost none of that is
a latency change: the hit-side p50s are 13.8 ms and 14.1 ms, indistinguishable
from the 12.8 / 15.3 ms ruling 127 recorded. What moved is the **hit rate**, and
the bimodality means the overall p50 is a step function of it — it crosses three
orders of magnitude the moment the miss share passes 50%, which is precisely what
happened between the two cycles. This is ruling 127's warning arriving in the
first cycle after it was written, and it is the reason the headline number is
useless unbucketed.

⚠️ **Traffic is sparse and that bounds everything here.** `newest_sample_age_s`
was **776 s** at the final read — 13 minutes since the last organic request to
`/api/feed`. n=55 over 50 minutes is ~66 requests/hour, and a single burst
(17:05–17:06 added 23 samples, 13 of them misses) is a large fraction of the
window. The miss share is robust across the series; the *absolute* volume of
users affected is not established by this measurement and is not claimed.

---

## 3. The decomposition — four probes, two of them cold builds

Fired 16:36:05–16:36:09Z. A = anonymous (control, expected to hit the pre-warmed
key). B, D = two **distinct fresh session ids** (the identified path). C = B's
session re-fired 3 s later (inside the 5 s fresh TTL).

| probe | principal | `x-feed-cache` | elapsed | singleflight |
|---|---|---|---|---|
| A | anonymous | `stale_hit` | **6.06 ms** | none |
| B | session S1 | **`miss`** | **2,243.7 ms** | leader |
| C | session S1, +3 s | `hit` | 12.19 ms | none |
| D | session S2 | **`miss`** | **2,033.4 ms** | leader |

🔴 **All four returned a bit-identical counts vector** —
`returned=20, total=104, type_bundle=5, type_concept=1, type_event=1,
type_futures=13`. Two independent principals paid ~2.1 s each to build what the
anonymous key was already serving in 6 ms, and the shape of what they built was
indistinguishable from it.

### Server-side stage budget (`X-Feed-Stages`, top-8)

| stage | B (ms) | D (ms) | principal-dependent? |
|---|---:|---:|---|
| `futures` (top-level) | 1,439.7 | 1,406.9 | mostly **no** |
| ├ `futures.market_load` | 430.5 | 432.5 | **no** |
| ├ `futures.scoring_loop` | 246.9 | 310.6 | **partly** (multiplier only) |
| ├ `futures.canonical_counts` | 170.3 | 162.5 | **no** |
| └ (below the top-8 cut) | ~592 | ~501 | *unattributed* |
| `concepts` | 324.8 | 316.9 | **no** |
| `events` | 233.6 | 134.5 | **no** |
| `personalization` | 108.7 | 84.7 | **yes** |
| `team_enrichment` | 55.7 | — | **no** |
| `golf` | — | 64.8 | **no** |
| **top-level sum** | **2,162.5** | **2,007.8** | |
| elapsed | 2,243.7 | 2,033.4 | |
| unattributed setup/serialization | 81.2 | 25.6 | |

**Only ~109 ms — 4.8% — of a cold build is principal-dependent.** The other
~95% is work whose inputs do not include the user, the session, or their
history.

The ~500–590 ms inside `futures` below the top-8 header cut is **unattributed,
not estimated**. Both probes logged the full stages dict server-side, but
`heroku logs` is EPERM in this sandbox (gotcha, memory
`reference_heroku_logs_eperm_sandbox`), so it could not be retrieved. It is
reported as a gap rather than apportioned.

---

## 4. What blocks — the mechanism, read out of the code

`backend/app/utils/feed_cache.py`:

```python
FEED_RESPONSE_TTL_ANON_SECONDS        = 60
FEED_RESPONSE_TTL_IDENTIFIED_SECONDS  =  5     # <-- the identified path
FEED_RESPONSE_TTL_MY_TEAMS_SECONDS    = 30
FEED_RESPONSE_STALE_TTL_SECONDS       = 300
```

and the key includes `user_part` (`u:<id>` / `s:<uuid>` / `anon`) **and
`offset`**. `backend/app/tasks/precompute_category_pages.py` pre-warms exactly
two shapes, both anonymous, both `offset=0`.

So the miss population is not random. It is, exhaustively:

1. **Returning readers.** Every signed-in user and every returning session gets
   its own key with a **5 s** fresh window and a 300 s stale slot. Arrive 301 s
   after your own last request and you pay a full cold build. Nobody pre-warms
   your key and nobody can — the key space is unbounded.
2. **Pagination.** `offset` is in the key and only `offset=0` is warmed, so
   **every scroll to page 2 is a guaranteed cold build**, for every principal,
   always. This is the one that is latency-critical as UX: it happens mid-scroll
   with the reader watching.

`stale_hit` **returns immediately and does not trigger a background refresh**
(`feed.py` ~1863–1890). So the 300 s stale slot is a grace period, not a
self-healing one: it expires into a cold build rather than into a warm rebuild.

The `X-Feed-Cache: hit` on probe C at 12.19 ms confirms the fresh window works
exactly as designed — it is simply 5 seconds wide.

---

## 5. What is already cached, and why the obvious lever is the wrong one

**The shared candidate base already exists and is healthy.** Queue 285 /
`app.utils.candidate_base` publishes a user-independent ordered candidate-ID
union. `GET /api/admin/candidate-base-state` at read time: **enabled, fresh,
19.8 s old, 628 IDs, healthy.** No `futures.pool_*` stage appeared on either
cold probe, confirming both builds consumed the shared base and skipped the
candidate pools entirely.

> So the lever is **not** "build a shared candidate base". It is that the shared
> artifact **stops at the ID list**. Everything downstream — the `market_load`
> SELECT that hydrates those same 628 rows, `canonical_counts` over those same
> keys, the base scoring pass, `concepts`, `events`, `team_enrichment` — is
> principal-independent by construction and is rebuilt from scratch for every
> principal anyway. That is ~2,050 of the ~2,140 ms.

`feed.py:6372` already knows this. Queue 305 (#1475) added `preloaded_base` so
the #1090 broaden re-score could reuse the hydrated rows "instead of re-paying
the ~494 ms `market_load` SELECT". The mechanism exists; **its lifetime is one
request.**

---

## 6. THE PROPOSAL — extend the shared artifact past the ID list

**Shape.** A per-process hydrated-base cache keyed on the candidate base's own
version stamp, holding what `preloaded_base` already holds plus the two
principal-independent derived maps:

- the ordered hydrated candidate rows (today: `market_load`, 430 ms)
- `canonical_source_counts` for those rows (today: `canonical_counts`, 170 ms)
- the base score per candidate, *before* the personalization multiplier

Per-principal work then reduces to the ~109 ms personalization context load plus
an in-memory re-rank of 628 candidates and the existing diversity/cap pass.

**Expected effect.** Removes ~600 ms of measured SQL immediately, and up to
~2,050 ms if `concepts`/`events`/`team_enrichment` are folded in on the same
key. A 2.0–2.5 s miss becomes roughly **150–250 ms**. Applied to the measured
organic mix (8 misses of 16), the endpoint's own p50 barely moves — it is
already 64 ms — but the **miss bucket p50 falls from 2,629 ms to the low
hundreds**, which is the number the charge is actually about.

**🔴 The named hazard, and it is not hypothetical.** Caching hydrated ORM rows
across requests is **exactly #2107** — the defect this program shipped a fix for
nine commits ago. A `rollback()` on the populating session expires every object
the cache holds and every later request 500s on `DetachedInstanceError`. The
answer is the one already proven in this codebase: a frozen detached snapshot
(`TeamSnapshot` / `_snapshot_team` in `routes/events.py`), with deep-copied
JSONB, and the `test_team_cache_detachment.py` suite as the template — including
its ARM-1 discipline of asserting the hazard is *still real* so the guard cannot
evaporate. LAT-P084 item 4 closed a leak in exactly that pattern
(`season_stats` handed out by reference), which is a fair estimate of the care
this needs: the pattern works, and it is easy to implement 90% of it.

**Cost.** A `FuturesMarketSnapshot` over the fields the scoring loop reads, the
version-stamped process-local cache, invalidation on base-version change, and a
detachment suite modelled on `test_team_cache_detachment.py`. One queue. It is
**not** a two-line change, and anything that claims to be one is skipping the
snapshot.

### Rejected alternatives, with the reason

| lever | why not |
|---|---|
| Pre-warm the identified shapes | The key space is `s:<uuid>` — unbounded. Not warmable, at any budget. |
| Raise `FEED_RESPONSE_TTL_IDENTIFIED_SECONDS` from 5 s | Shrinks the miss population only for readers who return within the new window. Does nothing for pagination (different key) and nothing for the 300 s+ returner. Serves staler data for a fraction of the benefit. |
| Extend `FEED_RESPONSE_STALE_TTL_SECONDS` past 300 s | A stale_hit does **not** refresh in the background, so this serves arbitrarily old data with no repair path. Would be reasonable *paired with* a background refresh — that is a separate, smaller proposal worth taking on its own merits. |
| Key the response cache on a personalization fingerprint | A zero-state session is already routed to the anon key by `frontend/lib/api.ts` (it omits `x-session-id` on the proven-first request of a fresh signed-out visitor). This mostly re-implements that. |

---

## 7. The one split this could not measure, and the instrument it needs

The miss population is dominated by two sub-populations with **very different**
product weight:

- returning readers at `offset=0` — annoying, once per visit;
- **pagination at `offset>0`** — mid-scroll, every page, latency-critical.

Nothing in `/api/admin/latency-stats` carries `offset`, and the per-request
observability that does (`feed_stage_observability`) is only reachable through
`heroku logs`, which is EPERM here. **The split is unmeasured and is not
guessed at in this document.**

If the split matters to how the proposal is scoped — and it should, because a
pagination-dominated miss population argues for warming `offset=20` on the anon
shape as a cheap partial fix before the snapshot work — the instrument is one
field: an `offset` bucket (`0` vs `>0`) on the `by_cache_status` breakdown in
`latency-stats`. That is small enough to be its own red-first gate and is the
recommended next measurement.

---

## 8. Provenance

- Tracking issue: **#2143**. (This file was first written as
  `feed-miss-path-decomposition-2084.md` before the issue existed; #2084 is an
  unrelated Discover rounding bug and was never cited in the body. Renamed with
  `git mv` in the commit that filed #2143.)
- Baseline under challenge: `PROGRAM-LATENCY-REPORT.md` §LAT-P083, line 17307.
- Decontaminated reads: `/api/admin/latency-stats` 16:33:34Z, 17:01:17Z and the
  probe-free **17:38:33Z** (§2b), 2026-08-24.
- Full series, 65 passive reads at 60 s cadence 16:34:09Z–17:38:32Z:
  `docs/audits/latency/lat-p084-feed-cache-series-2026-08-24.jsonl`.
- Decomposition probes: 16:36:05–16:36:09Z, 2026-08-24, four requests, recorded
  in the LAT-P084 report section; independently confirmed by their eviction from
  the ring at 17:36:32Z (§2b).
- Production release for the whole measurement: v3885 / `81380151`, deployed
  2026-08-23 14:48 PDT and still current at 17:38Z.

---

## 9. POST-T0 CORRECTION — the miss bucket was UNDERCOUNTING, and `other` is why

Everything above §8 was measured on v3885. The wave-2 deploy landed at
**T0 = 2026-08-24T17:23:50Z (v3886 / `b5c2a750`)**, so this section re-reads the
census on the new slug. It changes the headline number and, more importantly,
changes what the number means.

### 9.1 A bucket appeared that was not there before

The v3885 series had four cache-status buckets: `hit`, `stale_hit`, `miss`,
`error`. The post-T0 read has a fifth, `other`, and it is not small:

| bucket | n | p50 ms | min ms | max ms |
|---|---:|---:|---:|---:|
| hit | 10 | 13.6 | 9.9 | 36.9 |
| stale_hit | 15 | 19.3 | 12.6 | 41.1 |
| **miss** | **11** | **5,046.8** | 3,172.2 | 7,979.0 |
| **other** | **12** | **2,897.6** | **2,093.3** | 6,313.4 |

Read at 18:17:53Z; window 17:25:24Z→18:17:53Z, entirely post-T0, no release
straddle, `completeness: complete`, `unbucketed_samples: 1`.

`other` is not a residual. `app/middleware/latency.py:106–119` buckets to
`other` **exactly when** `X-Feed-Cache` carries a value outside
`{miss, hit, stale_hit, error}`, and `app/routes/feed.py` sets exactly seven
such values: `disabled`, `disabled_debug`, `disabled_reviewed_filter`,
`last_good`, `coalesced`, `unavailable`, `n/a`. The distribution identifies
which one without guessing:

- `last_good` and `unavailable` are reached **only after the wait budget is
  exhausted** (feed.py:2066 / :2093), so they cannot produce a 2,093 ms minimum.
- `disabled_debug` needs `?debug=true`; `disabled_reviewed_filter` needs a
  reviewed-filter param; `disabled` needs the response cache off — but `hit` and
  `stale_hit` are being served, so it is on.
- `coalesced` (feed.py:2054) returns **the instant the leader's build finishes**.
  Its support is bounded above by the leader's build and floored by how late the
  waiter arrived. p50 2,897.6 against a leader p50 of 5,046.8, floor 2,093.3:
  the only shape that fits.

**Confirmed directly, not inferred.** Three concurrent anonymous
`GET /api/feed?limit=5` at 18:17:37Z:

| probe | time | `X-Feed-Cache` | `X-Feed-Singleflight` |
|---|---:|---|---|
| 1 | 6.560 s | `miss` | `leader` |
| 2 | 6.618 s | `miss` | `leader` |
| 3 | 6.632 s | **`coalesced`** | `coalesced` |

Two leaders for one anon cache key is itself a finding: `begin_build` is a
**process-local** single-flight, so N web dynos give N leaders per key. Only the
third request landed on a process that already had one.

### 9.2 The corrected headline

Subtracting this lane's six probes from the census (ruling 127 — 17:44:0x
liveness ×1 `miss`; ~17:53 decomposition ×2 `miss`; 18:17:37 ×3 = 2 `miss` +
1 `coalesced`):

| | n | share |
|---|---:|---:|
| hit | 10 | 23.8% |
| stale_hit | 15 | 35.7% |
| miss | 6 | 14.3% |
| **other (`coalesced`)** | **11** | **26.2%** |
| **build-paying (miss + coalesced)** | **17 / 42** | **40.5%** |

95% CI (Wilson) on the build-paying share: **27.0% – 55.5%**.

**Fable's 37.5% headline is vindicated — for the wrong reason.** Miss share
alone is 14.3%, well under it. The build-paying share is 40.5%, just over it.
The gap between those two numbers is the entire content of this section.

### 9.3 Why this matters more than the number

**A coalesced waiter is not a cache hit. It pays the leader's build wall-clock
and it is not in the miss bucket.** Single-flight moves cost between buckets
without removing it: N concurrent cold requests become 1 build + (N−1) waits,
which genuinely saves the *backend* N−1 builds, and changes the *user's* wait
by nothing at all. Any dashboard reading miss-share therefore records an
improvement the user cannot feel, and the improvement gets larger the more
concurrent the traffic is — worst exactly when it matters most.

Banked as **ruling 129**.

### 9.4 What it does to the #2143 proposal — nothing but strengthen it

The lever in §6 shortens the **leader's** build. A waiter's wait is bounded by
that same build, so the projected saving applies to `other` as well as to `miss`
— i.e. to **40.5% of requests, not 14.3%**. No change to the design, a 2.8×
larger population.

### 9.5 Provenance for this section

- Read: `/api/admin/latency-stats` at 2026-08-24T18:17:53Z, slug v3886.
- Header confirmation: 3 concurrent probes at 18:17:37Z, recorded above and
  owed as a subtraction to any later read whose window contains them.
- T0 record: `docs/audits/latency/2107-watch-T0.md`.
