# LAT-P087 item 1 — the #2143 delta, measured: **1,652 / 1,745 ms**, inside the projection

LAT-P086 left an explicit IOU:

> **Projected:** ~1.55–1.95 s off a ~4.0–4.4 s cold build (**~35–48 %**) for the second and later
> principals in a TTL window, applying to **40.5 %** of requests.
> **Measured: OWED.** This lane cannot deploy. The measured half arrives the cycle after #2143 ships.

It shipped. This is the measured half. **The projection is confirmed** — but not by the instrument
the directive named, and the reason that matters is the rest of this document.

## 0. The gate, and a correction to its premise

The directive gates on *"the 56b71ac6 release going live (it carries latency-76)"*. It does not.
`git merge-base --is-ancestor 56b71ac6 b3b56f25` puts 56b71ac6 **before** the latency-76 merge:

| release | SHA | UTC | carries |
|---|---|---|---|
| v3889 | `56b71ac6` | 21:11:33Z | *not* latency-76 |
| **v3890** | **`ea07f81e`** | **21:40:47Z** | **latency-76, incl. `50fb21b7` = #2143** |
| v3891 | `642c28a6` | 22:21:13Z | the LAT-P086 merge + a sibling lane |

Re-based the gate on **v3890**. Per INT-106's standing instruction the artefact wins and the
disagreement is the headline, so it is here rather than in a footnote.

A second release then landed **mid-cycle**: v3891 at 22:21:13Z, which is **1 min 27 s before my
first probe run started**. That run is discarded as a headline (see §2) and everything reported
below is either ≥35 min clear of v3891 or explicitly labelled.

## 1. 🔢 THE CHARTER HEADLINE — before / after

| surface | banked before | after | delta |
|---|---|---|---|
| `/api/feed?limit=20` wall p50 | **372.0 ms** (n=14) | **371.4 ms** / **465.5 ms** (n=14 each) | **NOT MOVED** — see §2 |
| `/api/typeahead` p50 | **231.3 ms** (n=25) | **242.5 ms** (n=25) | +11.2 ms — inside the floor |
| `/api/events/search` wall p50 | **821.7 ms** (n=40) | **761.3 ms** (n=40) | **−60.4 ms (−7.3 %)** |
| census `/api/feed` `miss` p50 | **5,046.8 ms** (n=6) | **4,578.2 ms** (n=5) | −468.6 ms, **n too small to read** |
| **#2143 amortized build saving** | **0** (not deployed) | **1,652 ms** / **1,745 ms** | **CONFIRMED**, inside 1,550–1,950 |

Two of those five rows are honest non-results and one is the answer. Taking them in order.

## 2. The feed wall p50 cannot measure this, and my own two runs prove it

Same instrument as the banked before — 14 sequential anonymous `GET /api/feed?limit=20`, nothing
else in flight — run twice on **the same slug** (v3891), 65 minutes apart:

```
15:22 PDT   p50 371.4 ms   p90 380.1   max 4825.2   X-Feed-Shared on 1/14
16:27 PDT   p50 465.5 ms   p90 635.3   max  709.1   X-Feed-Shared on 0/14
```

**94.1 ms of spread between two runs of one instrument against one slug.** Any before/after delta
this row could report is smaller than its own reproducibility, so `372.0 → 371.4` is not a −0.6 ms
win and `372.0 → 465.5` is not a +93.5 ms regression. Both are the same reading of a number that
moves on its own. (Note the *warmer* slug measured **slower**, so this is load, not deploy warmth.)

There is also a structural reason this row is the wrong place to look: `X-Feed-Shared` appears on
**1 of 28** anonymous samples. A repeated anonymous principal is the warm response-cache path — it
never builds, so it never reuses a build artifact. **The headline surface does not exercise #2143
and never did.** A row that cannot move is not evidence that nothing moved.

## 3. The census `miss` bucket is un-straddled, clean — and n=5

Read at 23:26:52Z, `completeness: complete`, `unbucketed_samples: 0`, oldest sample **+35.0 min
relative to v3891** ⇒ ruling 130 **CLEAR**, and after this lane's own probes had aged out of the
rolling hour:

| bucket | n | share | p50 ms | min | max |
|---|---:|---:|---:|---:|---:|
| hit | 2 | 16.7 % | 35.7 | 35.7 | 42.0 |
| stale_hit | 4 | 33.3 % | 37.4 | 28.0 | 43.9 |
| **miss** | **5** | 41.7 % | **4,578.2** | 3,068.9 | 25,416.7 |
| other = `coalesced` | 1 | 8.3 % | — | 4,385.9 | 4,385.9 |

Against the banked before (hit 13.6 / stale_hit 19.3 / **miss 5,046.8** / coalesced 2,897.6), the
miss bucket moved **−468.6 ms (−9.3 %)**. **Do not report that as the delta.** It is a p50 over
**five** samples containing a 25.4-second outlier, against a before of six. The endpoint's own
`min_samples` rule already refuses to print a p95 at this n; the p50 it does print is a nearest-rank
pick of one sample. Build-paying share (ruling 129: coalesced counts) is 6/12 = 50.0 % against a
banked 40.5 %, on twelve samples total.

A thin window is why the projection needed a different instrument, not a reason to quote the thin
number with a confident sign.

## 4. 🎯 THE MEASUREMENT THAT WORKS — stage presence, not stage duration

`X-Feed-Stages` names each stage that **ran**. A stage absent from the header did not execute. Before
#2143 every build-paying principal necessarily built `concepts` and `canonical_counts` itself — that
is the premise of the fix. So the saving is directly readable as *the rate at which those stages
stopped appearing*, and it needs no pre-fix slug to subtract against.

`backend/scripts/probe_feed_shared_build.py` fires bursts of **distinct** `x-session-id` principals
(bursts of three, not pairs: the cache is process-local and production is one dyno at
`WEB_CONCURRENCY=2`, so a pair would report ~50 % sharing under *perfect* sharing and a reader could
not tell that from a half-broken cache).

| run | n | `concepts` paid | p50 when paid | `canonical_counts` paid | p50 when paid | **amortized saving** |
|---|---:|---|---:|---|---:|---:|
| 15:22 PDT | 24 | 5/24 (20.8 %) | 280.9 ms | 1/24 (4.2 %) | 1,588.3 ms | **1,745 ms** |
| 16:27 PDT | 42 | 11/42 (26.2 %) | 1,330.3 ms | 5/42 (11.9 %) | 760.8 ms | **1,652 ms** |

**Projected 1,550–1,950 ms. Measured 1,652 and 1,745 ms. Confirmed.**

Note what the two runs did and did not agree on. The wall p50 moved **1,570.2 → 1,964.8 ms (+25 %)**
between them, and the per-stage costs moved violently in *opposite* directions (`concepts`
280.9 → 1,330.3; `canonical_counts` 1,588.3 → 760.8). The **amortized saving agreed within 5.6 %.**
Two independent runs, 65 minutes apart, different load, and the derived quantity is stable while
every raw quantity feeding it is not. That is the signature of the right unit.

The same discipline shows up once more in the same data: the build path costs

```
15:22   1570.2 / 371.4 = 4.23 x the cached path
16:27   1964.8 / 465.5 = 4.22 x
```

**4.23 and 4.22** across a 25 % absolute swing. Bank the ratio, not the milliseconds — it is the
same lesson the teams-FTS gate correction learned independently today
(`lat-p086-teams-fts-index-spec.md` §7), from a different endpoint and a different database.

## 5. Sharing is at 100 %, which is both the confirmation and why there is no control

**66 of 66 distinct principals** (24 + 42) carried `X-Feed-Shared: canonical_counts,concepts`. All 42
of the second run were `X-Feed-Singleflight: leader` — genuine independent builds, not coalesced
waiters riding one build.

That is the fix working, and it removes the in-batch control. With `DEFAULT_TTL_S = 60` over a 30 s
`time_bucket`, there are ~2 build slots per bucket per worker, and organic traffic takes them before
a probe can arrive. **The unshared counterfactual no longer occurs in production.** Producing one
would mean setting `FEED_SHARED_BUILD_TTL_S=0` on production — a config change on a live user-facing
surface, which is Alex's call and not something I did unilaterally.

This is exactly why §4's method matters: stage presence measures the saving *from inside a single
post-fix batch*, with no cross-release subtraction at all. It is the only number here that does not
have to trust that nothing else changed between v3886 and v3891 — and something did (v3891 alone
touches `feed.py`, `league_futures.py`, `golf.py`, `outcome_display.py`, and removes an endpoint).

## 6. What the fix did NOT buy, stated plainly

The lever removed what it claimed. The miss path is still **~4.5 s**. Where it now lives, from the
42-sample decomposition:

| stage | n/42 | p50 | share of server total |
|---|---:|---:|---:|
| `futures` | 42 | 1,152 ms | **44.8 %** |
| ↳ `futures.market_load` | 42 | 531 ms | 18.2 % |
| ↳ `futures.scoring_loop` | 42 | 242 ms | 9.1 % |
| `concepts` | **11** | 1,330 ms | 11.1 % |
| `events` | 42 | 238 ms | 9.4 % |
| `futures.canonical_counts` | **5** | 761 ms | 3.1 % |
| `golf` | 41 | 52 ms | 1.9 % |
| `personalization` | 41 | 16 ms | 1.1 % |

**`futures` is now the feed's dominant cost at 44.8 %, paid by 42/42 requests, and it is not
shareable by #2143's mechanism** — `market_load` and `scoring_loop` run on every principal. This is
the same conclusion the search decomposition reached from the other side today
(`lat-p085-search-decomposition.md` had teams at 40.4 % and futures at 30.4 %; the LAT-P087
re-measure inverts it to teams 12.7 %, futures **59.3 %**).

**Two independent endpoints, measured independently, now both name `futures` as the top cost.** That
is the next lever, and it is a bigger one than either surface's runner-up.

## 7. Reproducing this

```bash
source ~/.claude/.env
python3 backend/scripts/probe_feed_shared_build.py --label <label> \
  --bursts 14 --burst-size 3 --burst-gap 4 --out <path>.json
echo "EXIT CODE: $?"
```

Artifacts: `lat-p087-feed-2143.json` (run 1), `lat-p087-feed-2143-v3891.json` (run 2),
`lat-p087-census-clean.json` (the un-straddled census), `lat-p087-census-contaminated.json` (the
earlier read, kept dated and labelled rather than deleted), `lat-p087-search-after.jsonl`,
`lat-p087-typeahead-after.jsonl`.

**Caveat on the two non-feed rows**: the search and typeahead after-runs were taken on **v3890**,
before v3891 landed. v3891 does not touch `app/routes/events.py`, so neither surface's code path
changed under them — but they are v3890 readings and are labelled as such rather than silently
folded into a v3891 report.
