# LAT-P184 — the cold Discover waterfall, before side

Measured 2026-09-01 ~09:4x–10:0x PT from the lane sandbox against **production**
(`www.bainluck.com` / `api.bainluck.com`), deployed frontend build serving
document sha-stamped by `<meta name="x-bainluck-frontend-build">`.

Everything here is the BEFORE side of the boot-fetch ship. The AFTER side is
PC-1 in `READY-latency-LAT-P184.md`.

---

## 1. What the document already does well — do not re-rank this

    curl -s -o doc.html -w 'ttfb=%{time_starttransfer} total=%{time_total} size=%{size_download}\n' \
      https://www.bainluck.com/

    ttfb=0.470119s total=1.722027s size=32350   (first, cold DNS/TLS)
    ttfb=0.053103s total=0.058237s size=32350
    ttfb=0.050026s total=0.055515s size=32350

`x-vercel-cache: HIT`. The 32,350-byte document is server-rendered and already
contains, as HTML with no JavaScript required:

* the site header, the desktop nav and the footer — every link a real `<a href>`;
* the Discover page header;
* **nine skeleton cards** (`data-testid="discover-skeleton"`).

So the *interactive shell* half of D-C is already shipped. The gap is DATA.

## 2. The entry graph — 22 chunks

    grep -oE 'src="/_next/static/[^"]*"' doc.html | sed 's/src="//;s/"//' | sort -u

22 chunks, measured with `curl --compressed -o /dev/null -w '%{size_download}'`:

| bytes (compressed) | chunk |
|---|---|
| 54,463 | `fd9d1056-*.js` |
| 39,797 | `polyfills-*.js` — **`noModule`, never fetched by a modern browser** |
| 33,234 | `7537-*.js` |
| 22,705 | `1442-*.js` |
| 14,203 | `app/layout-*.js` |
| … | 17 more |
| **241,150** | total |
| **201,353** | total excluding the `noModule` polyfill |

⚠️ `grep -c nomodule` returns 0 — Next writes it camelCase. Use `-i`.

**Every one of the 21 real chunks is `async=""`.** The single parser-blocking
`<script src>` in the document is the `noModule` polyfill, which a modern browser
skips without downloading. That is what makes an inline script in the page body
runnable within milliseconds of TTFB.

## 3. The feed the first screen is waiting for

    curl -s --compressed -D - -o /dev/null \
      'https://api.bainluck.com/api/feed?limit=20&event_pct=0.15'

    x-feed-cache: hit
    x-feed-elapsed-ms: 7.06 / 7.08 / 6.96
    size_download: 65,143
    ttfb 0.242–0.268 s   total 0.382–0.402 s

The shared anonymous key is **warm** — the server spends 7 ms. The reader waits
~390 ms of wire, and does not start waiting until hydration runs.

## 4. The two orderings, measured

`/tmp/lat-p184/waterfall.sh`. Arm A is today: document, then all 22 chunks, then
the feed. Arm B is the ship: document, then the chunks and the feed together.
Both arms fetch the identical byte set; only the ordering differs.

| rep | A `chunks_end` | A `feed_ready` | B `chunks_end` = `feed_ready` |
|---|---|---|---|
| 1 | 356 | **866** | **573** |
| 2 | 366 | **853** | **580** |
| 3 | 452 | **875** | 1844 † |
| 4 | 311 | **843** | **563** |
| 5 | 293 | **800** | 8442 † |
| 6 | 334 | **798** | **599** |
| 7 | 384 | **884** | **611** |
| 8 | 3647 | 4111 † | 5684 † |

† sandbox network outliers, excluded from the medians below and reported rather
than dropped.

    A feed_ready  median 853 ms   (n=7, range 798–884)
    B feed_ready  median 580 ms   (n=5, range 563–611)
    ------------------------------------------------------
    −273 ms, −32.0% on the served wait to a renderable first screen

**AND THE COST, MEASURED, NOT WAVED AWAY.** Arm B's chunks finish *later* —
median 580 ms vs arm A's 334 ms, **+246 ms** — because the 65 KB feed body
competes with the 201 KB of JavaScript for the same pipe. The win is what is left
after paying that: arm A's feed leg alone is 853 − 334 = **519 ms**, of which
273 ms survives contention.

🔴 **WHAT THIS WATERFALL CANNOT SEE, AND IT IS THE LARGER HALF.** It measures
transfer only. It does not include parse, execute or hydrate, and that CPU is
**additive to arm A alone** — in arm A the feed request cannot be issued until it
has all happened. LAT-P179's browser trace put `load` at 983 ms and content
complete at 4,425 ms on the same page, so the real gap between "chunks
downloaded" and "SWR's effect runs" is not small. The number above is therefore a
**LOWER BOUND on a desktop-class connection**, not an estimate of the win.

Grading it properly needs the browser run this lane has owed for eleven cycles
(`alex-inbox/latency-018` §2, now `latency-020`).
