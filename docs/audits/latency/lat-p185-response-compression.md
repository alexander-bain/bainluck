# LAT-P185 — response compression: the measurement, and why the placement is right

PILLAR: **TRUTH** (the platform answers the question you asked, at the speed you
asked it). SHIP: **`CERT-630` / `program/latency-178-response-compression`** —
which was already built by LAT-P178 and is not re-built here.

Measured 2026-09-01 ~10:2x–11:1x PT from the lane sandbox against **production**
(`api.bainluck.com`), instrument
`backend/scripts/measure_response_compression.py`.

> ⚠️ **Read this first.** LAT-P185 was directed to build API response
> compression and did so before discovering that **LAT-P178 had already built
> it** on 2026-08-31 and staged it as `CERT-630`. That branch was never graded —
> its cert bus session died holding it. **The duplicate was discarded**; this
> document keeps only what is additive: the reusable instrument, the level
> pricing, and an answer to an adversarial hand-off `CERT-630` left open.

---

## 1. The finding, re-confirmed a day later

Fifteen samples across the five heaviest public JSON endpoints, every request
sent with `Accept-Encoding: gzip, br`:

    endpoint               bytes enc         ttfb_ms  total_ms      srv  cache
    ---------------------------------------------------------------------------
    calibration          449,182 (none)          323       673     94ms
    calibration          449,182 (none)          305       638     87ms
    calibration          449,182 (none)          326       677     96ms
    golf-tournament      172,091 (none)         1906      2116   1682ms
    golf-tournament      172,091 (none)         2565     11343   2248ms
    golf-tournament      172,091 (none)         2448      2656   2234ms
    feed                  65,245 (none)          247       386     27ms    hit
    feed                  65,245 (none)          259       410     26ms    hit
    feed                  65,245 (none)          254       393     23ms    hit
    search                27,607 (none)          728       796    506ms
    search                27,607 (none)          248       318     21ms
    search                27,607 (none)          252       324     21ms
    futures               10,810 (none)          270       338     29ms
    futures               10,810 (none)          259       261     28ms
    futures               10,810 (none)          282       285     44ms
    ---------------------------------------------------------------------------
    TOTAL              2,174,805 bytes over 15 responses

`content-encoding: (none)` on all fifteen. The client asked for compression on
every request and the server never once offered it. There is no CDN to have done
it instead — the only intermediary is `via: 2.0 heroku-router`, which passes
`Content-Encoding` through untouched.

**The clearest single reading is `/api/calibration`.** The server's own
`x-response-time` says 94 ms; the client measures 673 ms; TTFB is 323 ms. So
roughly **350 ms of that request is the body crossing the wire** — nearly four
times the server time.

## 2. `/api/feed` is now a pure bytes problem — which is the answer to "attack the feed"

The lane's standing framing is *"the platform got fast and only the feed is
left."* Measured today, the feed is no longer a compute problem at all:

| feed request | server time | wire bytes | client total |
|---|---:|---:|---:|
| warm shared-anon (`x-feed-cache: hit`) | **6.6–8.3 ms** | 65,244 | ~390 ms |
| brand-new session id (new-install profile) | **20–27 ms** | 65,284 | ~390 ms |

A brand-new `x-session-id` does not even cold-build: it falls back to the shared
anonymous payload and re-personalises (`x-feed-stages:
personalization=13-20,cache_shared_hit=6`). **The server spends 7–27 ms and the
reader waits ~390 ms.** Essentially the entire remaining cost of the feed is
moving 65 KB, and `CERT-630` takes that to 8,924 bytes.

So the third directive item does not need a separate ship. **Compression *is*
the feed ship**, and the number to report for it is 65,244 → 8,924 bytes.

## 3. Pricing the level (why 6, not Starlette's 9)

`measure_response_compression.py --offline-levels`, run on the real bodies. gzip
is a synchronous C call that holds the GIL and blocks the asyncio event loop for
its whole duration, so on a `WEB_CONCURRENCY=2` dyno the CPU is paid by every
request queued behind it:

    calibration  (/api/calibration)  raw 449,182 bytes
        gzip -1:    89,718 (20.0%)   cpu   4.08 ms
        gzip -4:    75,718 (16.9%)   cpu   4.66 ms
        gzip -5:    69,758 (15.5%)   cpu   4.82 ms
        gzip -6:    67,888 (15.1%)   cpu   5.38 ms
        gzip -9:    64,564 (14.4%)   cpu  10.52 ms

    Totals across all five endpoints (raw 724,935 bytes):
        gzip -1:   129,197 (17.8%)   total cpu   4.49 ms
        gzip -4:   110,426 (15.2%)   total cpu   5.53 ms
        gzip -5:   102,800 (14.2%)   total cpu   5.80 ms
        gzip -6:    99,930 (13.8%)   total cpu   6.61 ms   <- what CERT-630 ships
        gzip -9:    95,521 (13.2%)   total cpu  12.78 ms

The DEFLATE ratio curve is flat above 6 and the CPU curve is not: level 9 buys
**0.6 more percentage points for roughly double the CPU**. This reproduces
LAT-P178's independent benchmark (it measured 3.99 ms vs 9.73 ms on
`/api/calibration`; absolute numbers differ with the machine, the ratio does
not) and lands on the same choice.

**On `minimum_size`, LAT-P178's 1000 is better than the 500 LAT-P185 had
picked**, and the duplicate deferred to it: #1636 explicitly asked that the
~844 B scheduled-game payloads stay raw, and 500 would have compressed them.

## 4. The ship, in bytes

| endpoint | before | after (gzip -6) | saved |
|---|---:|---:|---:|
| `/api/calibration` | 449,182 | 67,888 | **−84.9%** |
| `/api/golf/tournaments/us-open` | 172,091 | 16,508 | **−90.4%** |
| `/api/feed?limit=20` | 65,245 | 8,924 | **−86.3%** |
| `/api/events/search?q=lakers` | 27,607 | 4,348 | **−84.2%** |
| `/api/futures/1` | 10,810 | 2,262 | **−79.1%** |
| **total** | **724,935** | **99,930** | **−86.2%** |

## 5. The additive finding: why innermost placement is load-bearing

`CERT-630`'s block carries an adversarial hand-off from its author: mutation M5
(gzip moved outermost) killed the compression-ratio test and *"I did not chase
down why."* An independent 7-mutation battery run today chased it down, and the
answer is stronger than the comment in `main.py` claims.

Moving `GZipMiddleware` outside the `BaseHTTPMiddleware` layers does not merely
relocate its CPU cost. **It changes the response shape.** Outside, gzip sees the
`_StreamingResponse` those layers emit, so it takes Starlette's *streaming*
branch, which:

* **deletes `Content-Length`** and sends the body chunked, and
* **never consults `minimum_size`** — so small responses get compressed too.

Reproduced as two separate mutations, each caught:

| mutation | tests failed | includes |
|---|---:|---|
| gzip moved outside the timing middleware | 3 | "small responses stay uncompressed", the wire-ratio test |
| gzip moved outside CORS | 4 | both of the above, plus the ordering assertion |

So innermost is not only where the cost is *measured* honestly. It is the only
placement that keeps `Content-Length` on the wire. The existing rationale
understates its own case, and this is worth carrying forward into the comment as
a follow-up.

Full battery (run in an rsync copy, control green at both ends, **7/7 caught**):
compression removed entirely (11 tests fail), level inherited as 9 (1),
`compresslevel` kwarg dropped (1), `minimum_size` kwarg dropped (1),
`minimum_size` raised past every body (7), moved outside timing (3), moved
outside CORS (4).

## 6. Not brotli, yet

Brotli would buy an estimated further ~15% over gzip, but it needs a dependency
that is not installed and cannot be exercised in this sandbox. **Parked with a
measured headroom** rather than shipped as an untested import in the request
path: gzip captures 86% of the available win with zero new dependencies.

## 7. Owed after deploy

The production AFTER measurement is **owed, not claimed**. Re-run the identical
instrument once the dyno is up:

    cd backend && python3 scripts/measure_response_compression.py --repeats 3

Expected: `enc` reads `gzip` on all five, and the 15-sample total falls from
2,174,805 bytes to roughly 300,000.

## 8. Parked measurement (not a ship, filed per CLAUDE.md)

`/api/feed` carries a **`debug_bundles`** object on every bundle card — 1,513 B
of 65,245 (2.3%) across 6 of 20 items — with **zero frontend consumers**
(`grep -rn debug_bundles frontend/` is empty). It duplicates the sibling
`member_ids` and adds `member_names`.

**Deliberately NOT removed.** Ruling 072 names this exact field as the reason
`DiscoverFeedProdFixture` keeps unread keys — *"never trim what you do not
understand"* — and `tests/test_discover_bundles.py` pins its shape in four
places. After compression it is a fraction of a fraction. Appended to
`PARKED-MEASUREMENTS.md` rather than acted on.
