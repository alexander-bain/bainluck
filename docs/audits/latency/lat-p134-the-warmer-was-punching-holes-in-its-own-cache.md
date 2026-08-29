# LAT-P134 — the warmer was punching holes in its own cache

**Cycle:** LAT-P134 · **Date:** 2026-08-29 · **Branch:** `program/latency-120`
**Base:** `origin/master` `8ca1e2ed` · **Issue:** **#2304** (split out of #1866, which stays open —
this is the code-only half; #1866's own 90–95 % cause is DDL and is still blocked)
**Pillar: DISCOVER. Ships: typing a popular search stops randomly taking three seconds.**

---

## 0. The one-sentence version

`typeahead_warmer` kept the head warm by **DELETING** each cached answer and letting the route
rebuild it on the miss path — and measured on production, that delete-shaped hole cost a real
user **2.0–3.7 s on 8.6 % of requests to terms the warmer was actively keeping warm.** The
module docstring had priced the same hole at "~20 ms". It now rebuilds *over* the entry
instead, so the old answer is served continuously until the new one replaces it.

---

## 1. How this cycle picked its target, before it picked a fix

The lane's frozen instrument (`backend/scripts/cold_path_snapshot.py`, LAT-P099, bars committed
before the first number) was run against production `8ca1e2ed`, `uptime 1637 s`, `warm_slug=True`,
`n=6` round-robin, organic `latency-stats` read taken first (`/tmp/stats_before_p134.json`).

```
tab        surface    n   p50 all  p50 cold  cold%       max  bar      verdict
Discover   native     6      61.0         —     0%     182.0  1000     MET
Discover   web        6      22.0         —     0%      25.0  1000     MET
Sports     native     6      40.5         —     0%     218.0  1000     MET
Sports     web        6      16.5   5,776.0    17%   5,776.0  1000     MET
Browse     —          —         0         0      —         0  n/a      NO SERVER DEPENDENCY
Search     native     6      21.0         —     0%      23.0  1000     MET
My Stuff   native     6      11.5      11.5   100%      24.0  1000     MET

typeahead COLD BUILD (debug_timing, non-voting): n=6 p50 3,251.0 ms  bar 500  NOT MET
VERDICT: THE COLD-PATH BAR IS NOT MET          exit 1
```

**Every tab meets its bar. Exactly one row fails.** So the target was not chosen; it was the
only thing left.

That row is #1866, and its 90–95 % cause — `futures_markets.name` matched with an un-indexed
`FTS(...) OR ILIKE`, LAT-P095/P096 — is **DDL, blocked on Alex's attended `psql` batch**. I
verified against production `pg_indexes` today: neither `ix_futures_name_fts_open` nor
`ix_fm_open_category` exists, three days after both were specced and gated. Re-staged as
`alex-inbox/latency-003`.

🔴 **The code-only substitute is closed and it is closed by measurement, not by taste.** LAT-P097
censused a stem-substring replacement over 36 terms: `grammys` 15→5 (a head query), `cities`
744→4, `qualifying` 1074→237, because Porter maps a trailing `y` to `i` and `grammi` is not a
substring of "Grammy". A third code-side approximation was not built.

**So this cycle asked a different question: not "why is a cold build slow", but "why are terms
the warmer is warming cold at all".**

---

## 2. The finding

### 2.1 The mechanism

`/api/events/typeahead` writes its Redis entry **only on the miss path** (`events.py`, the
`setex(_cache_key, 65, ...)` at the end of the build). So when `typeahead_warmer` wanted to
extend a head term's life, the only lever it had was to make the route miss:

```python
dropped = False if ttl_before == _TTL_NO_KEY else _drop_cached(q)   # a Redis DELETE
...
await asyncio.wait_for(typeahead_search(q=q, ...), timeout=PER_QUERY_TIMEOUT_SECONDS)
```

From the `DELETE` until that route call's `setex`, **the key is absent**. Any real user typing
that term in the window misses too — and pays their own full, independent build, because there
is no single-flight on this path.

### 2.2 What LAT-P060 predicted

Verbatim from `typeahead_warmer.py`'s module docstring, as shipped:

> "between the drop and the route's write there is a window in which a user typing that prefix
> pays a database read. It is bounded by ONE recompute, and because the warmer keeps the pages
> resident that recompute is the HOT cost (5-27ms), not the 1.4s cold cost. **It replaces a
> 30-50s cold window per cycle with a ~20ms one**, and it only ever fires on an entry that was
> seconds from expiring anyway."

### 2.3 What it actually costs

Production `8ca1e2ed`. Two terms confirmed warm (`celtics`, `lakers` — both returned ~30 ms on
an earlier touch, i.e. genuinely in the warmer's head). Polled alternately every 4 s for 5½
minutes through the **real cache path** with `X-Bainluck-Origin: harness`, which suppresses the
trending vote without bypassing the cache (`_request_is_automation`, LAT-P118). Server time
(`x-response-time`), never wall.

| term | n | p50 | max | samples > 300 ms |
|---|---:|---:|---:|---|
| `celtics` | 35 | **19 ms** | 3,689 ms | **4 (11 %)** — 20:10:40, 20:11:54, 20:12:43, 20:14:37 |
| `lakers` | 35 | **18 ms** | 3,144 ms | **2 (6 %)** — 20:10:55, 20:12:10 |
| **both** | **70** | — | **3,689 ms** | **6 (8.6 %)** at **2,000–3,689 ms** |

The spikes are 60–115 s apart and the two terms are staggered by ~15 s — the signature of a
round-robin pass, not of database noise.

> **The hole was ~150× its estimate, and it landed on precisely the terms the warmer exists to
> keep fast.** A person typing `celtics` had roughly a one-in-twelve chance of waiting three
> seconds *because* the warmer was working.

### 2.4 Why the estimate was wrong — and it was refutable from inside this repo

"The warmer keeps the pages resident, so the recompute is the HOT cost." True, and irrelevant in
the same breath. LAT-P096 later measured the dominant stage: the FTS half of the futures name arm
reads **27,483 buffers — all HITS, i.e. already resident — and still takes 742.7 ms**, because it
computes one `to_tsvector` per open market. **The cost is CPU. Page residency was never going to
buy it back.**

That measurement lives in `routes/events.py`. The estimate lives in `tasks/typeahead_warmer.py`.
Nobody carried one to the other for three cycles.

**The general clause:** *a cost estimate written in one module is not reviewed by the measurement
that refutes it in another. A prediction that a later cycle could falsify needs to be findable
from where that cycle will be standing — or it survives on the strength of never being re-read.*

---

## 3. The fix

`_force_cache_rebuild`, a ContextVar in `routes/events.py`: it makes the route **skip the cache
READ and keep the cache WRITE**. `_warm_one` sets it and no longer deletes anything.
`_drop_cached` is removed, not left unused.

```
before:  DELETE ──[1–6 s HOLE, users pay a full build]── setex
after:   (old answer served throughout) ────────────────── setex
```

Four properties, stated so each can be checked:

1. **Max staleness is UNCHANGED.** The 65 s response TTL governs both shapes, and the new entry
   is written at the same instant it would have been. **This buys latency, not freshness, and
   must not be read as buying freshness** — the payload carries live probabilities.
2. **Failure now degrades to last-good.** A rebuild that times out or errors leaves the previous
   answer alive to its natural expiry instead of leaving a hole. Same principle LAT-P133 shipped
   on the playoff grid a day earlier.
3. **One Redis round trip fewer** per rebuilt term (no DELETE), and one more (the verification
   below). Net zero.
4. **Not load-bearing.** A cold miss still builds inline in the route; turning the warmer off
   makes `/typeahead` slow again, never broken. That was true before and stays true.

### 🔴 3.1 The load-bearing half is the refusal, again

`debug_evidence` and `debug_timing` bypass the cache in **both** directions. This flag bypasses
**one**. If it ever joined the WRITE condition, the warmer would run the full query path, write
nothing, and report success — a green pass that warmed nothing. That is gotcha #53, and it is the
same trap the existing `Query(False)` comment in `_warm_one` already describes; the fix for one
hole must not dig the other.

So the route is **read-only** with respect to this flag (a route that could set it would force
its own misses on every user), and the flag is **set-and-reset with a token in a `finally`** —
per-task context copies already make a leak unreachable, and the reset makes it unreachable
*without depending on that argument*. An argument is what the previous mispricing was made of.

### 3.2 "It returned" is not "it wrote"

`_warm_one` now re-reads the TTL after the route call and grades it:

| after | reason | `ok` |
|---|---|---|
| moved up | `warmed` | ✅ |
| unchanged | **`no_write`** | ❌ — and it forces the pass to `partial` |
| unreadable (`None`) | `warmed_unverified` | ✅ |

The middle row is the exact signature of the flag failing to reach the route. The third row is
kept **distinct on purpose**: collapsing an unreadable Redis into `no_write` would manufacture a
warmer defect out of a network blink — the mirror of the conflation that produced this file's
subject (gotcha #53). The pass summary carries `no_writes` (the queries) and `unverified` (a
count), and both are present-and-empty on the skip shape so no consumer branches on `terminal`
to learn whether a field exists.

---

## 4. Guards

`backend/tests/test_typeahead_warmer_overwrites_not_deletes.py` — **21 tests**, in both
directions: the DELETE must not come back, the flag must be set, the route must honour it on the
read, the route must **not** honour it on the write, a silent no-write must be counted, an
unreadable Redis must not read as that defect, and the flag must not leak.

`backend/scripts/gate_typeahead_overwrite_mutations.py` — **12 mutants, 12 killed, exit 0**,
restore verified byte-identical by SHA-256 on both files. The mutants pull both ways: back toward
the DELETE (M1, M2, M9) and onward past it to a flag that also suppresses the write (M10, M11).
Only exit code `1` is counted as a kill; any other code is recorded as a survivor, because it is
a story about the harness (gotcha #124).

### 🔴 4.1 Two guards were wrong before they were right, and both are recorded

**`M3-NO-RESET` SURVIVED the first battery pass, and the mutant was right.** The test read
`_force_cache_rebuild.get()` from the test body after `run_until_complete` — which wraps the
coroutine in a Task and therefore **copies the context**, so the `set(True)` inside `_warm_one`
was never visible there. The assertion was true with the reset deleted. Repaired to `await`
`_warm_one` from a caller that shares its context (the only arrangement in which the leak could
hurt anyone), plus a second test for the success path. Then 12/12.

**A summary test was passing for the wrong reason.** The first draft of the pass-summary tests
used one-character probe terms `"a"`/`"b"`. `_warm_typeahead` filters the head to
`_MIN_QUERY_CHARS..._MAX_QUERY_CHARS`, so the head emptied and the pass reported `partial` for a
reason with nothing to do with writes — the `no_write` assertion would have gone green with the
feature deleted. Now the helper asserts `total > 0` before returning, and a `complete` control
sits next to the `partial` case.

Recorded, not quietly re-run.

### 🔴 4.2 Three mutation needles were broken BY THIS CYCLE, and the scanner caught them

`scan_mutation_residue` PASS A, run on the branch, reported four drifted needles. Checked against
`origin/master` rather than assumed — **three of the four are mine**:

| needle | points at | on master | on branch |
|---|---|---|---|
| `offline_rerank_fidelity:M3` | the `/typeahead` cache-READ guard | present | **absent** |
| `offline_rerank_fidelity:M14` | same line | present | **absent** |
| `typeahead_warmer:M3` | the `terminal` expression | present | **absent** |
| `typeahead_warmer:M4` | `_warm_one`'s `except Exception` | absent | absent (pre-existing, #2113) |

A drifted needle scores **NOT-APPLIED**, printed in the same column as a kill, next to nine of them.
Nothing goes red. **Three guards would have been switched off by this ship and the only thing that
said so was a scanner nobody had to run.**

All four re-targeted. M14's **replacement** was updated too, not just its needle — it drops the
`debug_timing` conjunct and must keep dropping exactly that one, so it now reads
`if not debug_evidence and not _force_cache_rebuild.get()`. *A re-targeted needle with a stale
replacement is a mutant testing a different defect under the old name.*

`typeahead_warmer:M4` is pre-existing but was taken anyway: it is the **per-item-guard mutant
(gotcha #42) for the exact block this cycle rewrote**, and shipping a rewrite of a guard with that
guard's battery switched off is not a defensible trade. `typeahead_warmer:M6` (drifted since
LAT-P078 made `resolve_head` blend, renaming the local to `log_head`) is also taken, because
#2113/#2154 name exactly M4 and M6 as "now unguarded" and the fix is one identifier.

Result: `typeahead_warmer_mutations` **7/10 → 10/10 killed, 0 not-applied**;
`offline_rerank_fidelity_mutations` **12/14 → 14/14, 0 not-applied**; and the residue scan reports
**zero harness drift, which `origin/master` does not**.

**The general clause:** *a mutation needle is source text, so any refactor can silently retire the
mutant that guards it — and the retirement is reported as NOT-APPLIED, which sits in the kill column
and reads like coverage. The cycle that moves the line is the only one that still knows what the
mutant was for.*

### 4.3 The existing suite was updated, not deleted

`tests/test_typeahead_warmer.py` pinned the DELETE mechanism in six tests. Each one's *intent*
survives, re-pointed at the new mechanism — e.g.
`test_a_near_expiry_entry_is_DROPPED_BEFORE_the_route_is_called` (which pinned drop-then-call
ordering) becomes `..._is_REBUILT_OVER_AND_NEVER_DROPPED`, and now asserts the stronger property:
no delete at all, and the flag visible *inside* the route.

🔴 **`_ok_route()` had to start writing.** It was a stub that returned without touching Redis —
a stand-in for a route that does not write, which is a broken route. With the TTL verification in
place every cadence test using it reported `no_write`. Ruling 072 again: a fake that agrees with
the code instead of with the real thing proves only that the code agrees with itself. `_FakeRedis`
grew a real `setex`, and `delete` now clears the TTL too.

---

---

## 4.9 Gates, every exit code read by value

| gate | result |
|---|---|
| full backend suite | **22,380 passed / 0 failed / 124 skipped / 61 xfailed, `PYTEST_EXIT_CODE: 0`**, 934.76 s |
| collect reconciliation | 22,380+124+61 = **22,565 = branch collect exactly**; **+22** vs master = the new file's exact count (`test_typeahead_warmer.py` measured 61 on BOTH sides) |
| `gate_typeahead_overwrite_mutations.py` | **12/12 killed, 0 survived, exit 0**, restore SHA-256 identical |
| `typeahead_warmer_mutations` | **10/10, 0 not-applied, exit 0** (was 7/10) |
| `offline_rerank_fidelity_mutations` | **14/14, 0 not-applied, exit 0** (was 12/14) |
| `scan_mutation_residue` | **exit 0, CLEAN**, 289 needles / 1055 broad checks, **zero drift** |
| smoke | exit 0 |
| ruff | **net 0** (`events.py` 41→41, `typeahead_warmer.py` 0→0, `test_typeahead_warmer.py` 0→0; both new files clean) |
| frontend build / typecheck | exit 0 / exit 0, **70 = baseline 70** |
| `merge-tree` vs `origin/master` | **exit 0**, tree `7f6d4482` |

⚠️ **REBASED MID-CYCLE, EVERY GATE RE-RUN.** Cut from `8ca1e2ed`; master advanced to `0eb74bd8`
while the first suite was in flight. **That run was killed, not quoted** — the move is disjoint from
my files at the file level, and INT-151's worked example is that disjoint text still collides
semantically.

⚠️ **A SECOND RUN IS ALSO DISCARDED, AND ITS ONE FAILURE WAS MINE TO CAUSE.** The rebased run
reported `1 failed` on `test_the_warmer_passes_every_marker_defaulted_route_parameter`, which passes
in isolation: **I ran a mutation harness — which rewrites `typeahead_warmer.py` in place — while
that suite was reading it.** The quoted 22,380/0 is a clean re-run on the identical tree. The
background launcher had also reported its own `exit 0` over that failure, which is the
missing-verdict-line trap; the file's `PYTEST_EXIT_CODE` is what was read.

---

## 5. What this does NOT fix, said plainly

**A never-asked term still costs 2.8–6.4 s on first touch.** That is the un-indexed `to_tsvector`
scan, it is 90–95 % of a cold build, and it is DDL waiting on Alex. This cycle removes the holes
in the *warm* head; it does not make the cold build cheap, and the charter's cold-typeahead row
will still read NOT MET after this deploys.

Measured today for the record, first touch, server time: `nvidia` 6,351 ms · `taylor swift`
5,698 ms · `us open` 5,149 ms · `super bowl` 3,830 ms · `yankees` 3,718 ms · `premier league`
3,019 ms · `vuelta` 2,856 ms. Second touch on the same terms: 28–49 ms.

**Nothing post-deploy is claimed.** This lane does not deploy.

**Owed after deploy:** re-run the `celtics`/`lakers` hole probe (same header, same cadence) and
expect the >300 ms fraction to go to zero; read the pass summary's new `no_writes` field on
`/api/admin/...` task metrics — **a non-empty `no_writes` is the fix failing, and it is designed
to be loud rather than to be a slow regression.**

---

## 6. Contamination declared

Five bare typeahead probes were issued **before** I established that
`X-Bainluck-Origin: harness` suppresses the vote on this route, and they voted into
`search:trending:24h`: `us open` (3), `yankees`, `world cup`, `taylor swift`, `nvidia` (2 each).
On this site's organic volume single-digit votes buy warmer head slots (LAT-P097). They age out
of the 24 h window unaided. Every probe after that point carried the header; the 70-sample hole
probe and the charter snapshot both did.

The charter snapshot's own contamination block: 36 `/api/feed`, 24 other tab endpoints, 6
typeahead (`debug_timing` + origin, 0 votes), 0 `/api/events/search`, 4 `/api/health`.

---

## 7. Parked

* **P134-1** — the four requests the charter's typeahead row can't see: `teams_query`,
  `events_query` and both fuzzy-fallback queries run with **no statement timeout at all**
  (`_apply_search_statement_timeout` is called once, immediately before the futures stage). A
  slow teams query can eat the whole 10 s deadline with no cancellation, and because
  `_ta_degraded` stays False the slow-but-complete answer is then **cached**. Exactly LAT-P133's
  "bounded against one clock" shape, on the other surface. MEASUREMENT lane first — nobody has
  read how often it fires.
* **P134-2** — `typeahead_beat_budget.WALL_MAX_EXCEEDS_RESPONSE_TTL` is `True` (worst pass
  66.365 s vs a 65 s TTL), so **no beat interval can keep the head resident**. This cycle removes
  the warmer-made holes; it does not remove that one. The module names
  `worker-background --concurrency=2` as the cause, which is a capacity decision, not a latency fix.
* **P134-3** — the fuzzy team fallback still uses the non-indexable `similarity() > 0.25`
  function form; `/search`'s twin replaced it with the `%` operator years of cycles ago
  (`events.py:3400-3409`). Small, and it only fires when everything else found nothing.
* **P127-1 — DISCHARGED, and by someone else.** Measured today: `/api/futures/browse` is
  **113–424 ms server-side** (`x-response-time`), not the 408–514 ms the park recorded. LAT-P123's
  single-scan rewrite (`count(*) OVER ()`) did it. It is under the 1,000 ms bar and is no longer
  the strongest next candidate. The uncategorised call is still 1,560–1,805 ms — **and no client
  issues it**; `CategoryBrowser.tsx` always passes a category.
* **P127-5** — the two dead `lib/api.ts` exports, so the next census stops re-nominating them.
* Carried unchanged: **P133-1** · **P133-2** · **P133-3** · **P132-1**–**P132-5** · **P131-3** ·
  **P131-4** · **P130-1**–**P130-3** · **P129-1** · **P129-2** · **P129-3** · **P129-5** ·
  **P128-1** · **P127-3** (**NEEDS ALEX**) · **P127-4** · **P126-1** · **P125-A** · **P125-1** ·
  **P125-2** · **P124-1**–**P124-5** · **P110-4** · **P122-5** (option b/c, **TWENTIETH**
  consecutive cycle).
