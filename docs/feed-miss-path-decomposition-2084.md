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
| window does not straddle a release | INT-112 is running under **ZERO PUSHES**; `origin/master` unmoved at `81380151` for the whole window |
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

- Baseline under challenge: `PROGRAM-LATENCY-REPORT.md` §LAT-P083, line 17307.
- Decontaminated read: `/api/admin/latency-stats` 16:33:34Z and 17:01:17Z, 2026-08-24.
- Decomposition probes: 16:36:05–16:36:09Z, 2026-08-24, four requests, recorded
  in the LAT-P084 report section.
- Production release at read time: v3885 / `81380151`, deployed 2026-08-23 14:48 PDT.
