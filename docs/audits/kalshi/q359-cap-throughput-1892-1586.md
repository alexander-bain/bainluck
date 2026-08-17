# Two caps, two files, one shape — #1892 and #1586

Queue 359 Batch 1 item 3, 2026-08-17. Measured against production; every number
below carries its source, and the ones inherited from the issue bodies are
marked INHERITED.

The two issues were held by one designer because they are the same defect
twice: **a bounded run whose bound sits below its inflow never converges**
(gotcha #41), plus **every instrument on both of them measured liveness rather
than convergence**, which is why both read healthy for weeks.

---

## 1. What was measured, and what it overturned

All figures from `POST /api/admin/db-query` and
`GET /api/admin/task-metrics` / `GET /api/admin/kalshi/scan-report`,
2026-08-17 15:20–16:10 UTC (08:20–09:10 PT).

### 1a. The cliff clock is NOT running (#1892 §3 disproven)

Uncovered = resolved Kalshi outcomes with `external_id` and **zero** rows in
`futures_odds_snapshots` — i.e. exactly the drain's own cohort predicate.

| age band | total | uncovered | uncovered % |
|---|---|---|---|
| 5–10d | 45,625 | 25,964 | 57% |
| 10–15d | 51,115 | 32,663 | 64% |
| 15–20d | 59,717 | 24,031 | 40% |
| 20–25d | 53,361 | 13,713 | 26% |
| 25–30d | 48,860 | 4,548 | 9.3% |
| 35–40d | 47,138 | 2,216 | 4.7% |
| 45–50d | 43,168 | 798 | 1.8% |
| 55–60d | 37,220 | 43 | 0.1% |
| 65–70d | 35,405 | **0** | 0% |
| 75–80d | 42,021 | **0** | 0% |
| **74–86d (the at-risk band)** | — | **0** | **0%** |
| 60–86d (whole tail) | — | 1,608 | — |

**The at-risk band contains zero unexamined outcomes.** Loss to the retention
cliff is ~0/day today, not the ~1,100/day the issues are framed on (INHERITED,
and historical — it predates the #1884 unblock). Coverage reaches ~0% uncovered
by ~60 days entirely inside the window, so the population dies covered.

This overturns #1892 §3's headline ("the watermark has already passed the
at-risk band … the expiring edge is already behind the drain"). The premise is
right; the consequence is not, because there is nothing left in the band to
lose. What §3 identified correctly is the **residue**, below.

### 1b. The residue behind the watermark, sized exactly

Uncovered rows inside the window but **behind** the main watermark
(`2026-07-24T17:00Z`): **15,712**.

The drain's own cumulative counters: `empty_present` 12,232 + `empty_unprobed`
3,560 = **15,792**.

Those match to within 80 rows, which settles what the residue *is*: it is
entirely the drain's own empty answers, and by construction nothing revisits
them. They will age to 86 days and die. Whether that costs anything depends on
whether `empty_present` is a true fact — see §4, open question 1.

### 1c. #1586's named mechanism is built on a counter that cannot mean it

`GET /api/admin/kalshi/scan-report`, 24-beat ring, 2026-08-17 14:45Z beat:

```
events_fetched  13,513   main_scan 5,000   supplementary 8,513
events_new       7,198   events_existing   6,315
events_processed   356   events_unreached  13,157
unreached_existing 6,315  loop_deadline_hit FALSE   duration 296.6s
```

`unreached_existing` is derived in `app/tasks/kalshi.py:1104-1127` as
`max(0, n_existing - max(0, processed - n_new))`. That treats
`events_processed` as a **position** in the fetched list. It is not one:
`events_processed` is incremented only after a market upsert succeeds
(`kalshi.py:863`), and the loop's first statement is
`if not event.markets: continue` (`kalshi.py:641`). Because `processed` (356)
is always far below `n_new` (7,198), the inner clamp is always 0 and
`unreached_existing ≡ events_existing` — which is what all 24 beats show, to
the row. Its "growth" 5,075 → 8,597 is the growth of `events_existing`.

And `loop_deadline_hit` is **False on all 24 beats**. The loop reached every
event. It did not run out of budget.

**The real mechanism: 13,157 of 13,513 fetched events (97.4%) carry zero
markets and are dropped.** Confirmed independently — `poll_kalshi`'s
`by_category` histogram sums to exactly 356, and `crypto_skipped` is 0.

Two causes, both in `app/services/kalshi_api.py`:

1. `_HEAVY_TOKENS = ("GAME","SPREAD","TOTAL","1H","2H","WINNER","SERIES")`
   supplementary series are fetched with `with_nested_markets=False`
   (`:1021`, `:1058`) on the stated promise (`:1005-1006`) that "the
   empty-events backfill below fetches their markets per-event, lazily +
   bounded".
2. **The promise is not kept.** That backfill (`:1085+`) is structurally LAST
   in the fetch budget with no reserve, and gated on `not _past_deadline()`.
   Production reports `fetch_deadline_hit: True` — the 240s fetch deadline is
   already spent by the time control reaches it, so it is skipped entirely. It
   also filters to `"sport" in category`, so a market-less non-sport event was
   never a candidate at all.

This is the same failure as `_RESCUE_RESERVE_S`: the supplementary loop got a
guaranteed reserve carved out of the main scan precisely because a step at the
end of a budget never runs. The backfill needed the same and never got it.

**Raising `max_pages` therefore cannot help — it is aimed at the wrong stage,
and it would make this worse** (more fetched events competing for the same
zero-reserve backfill). Alex's constraint was right for a reason nobody had
measured yet.

---

## 2. The arithmetic

### Recovery vs inflow — the cliff drain (#1892)

Sources: `remaining` from `task-metrics.last_result_summary` at four points
(runs 23 / 25 / 44 / 65 — the first three INHERITED from the issue thread, the
fourth measured today at 15:21Z); run durations from `recent_durations_ms`
(n=50); `starts_24h=17` measured; beat is `crontab(minute=20)` = 24 scheduled.

| quantity | value | source |
|---|---|---|
| per-run cap | 400 outcomes | `limit=400` beat kwarg |
| runs/day, scheduled | 24 | beat |
| runs/day, actual | **17** | `starts_24h` |
| **recovery, actual** | **6,800 outcomes/day** | 400 × 17 |
| run duration | 62–150 s (median ~76 s) | `recent_durations_ms` n=50 |
| task budget | 780 s deadline / 900 s soft limit | `tasks/__init__.py:922-938` |
| **budget utilisation** | **~10%** | 76 s of 780 s |
| uncovered inflow | **~5,200–6,500/day** | 10–15d and 15–20d bands ÷ 5 |
| cliff loss today | **~0/day** | at-risk band = 0 uncovered |
| `remaining`, runs 25→44 | −5,821 (−306/run) | INHERITED |
| `remaining`, runs 44→65 | −6,167 (−294/run) | measured today |
| `remaining`, runs 65→66 | −278 | measured today, 16:23Z |
| **net convergence** | **−300/run ≈ −6,000/day** | 41-run span |
| watermark lag | 24 days (cursor 2026-07-24) | measured |

**Verdict: it out-runs inflow, but only just, and only because #1586 is
broken.** Throughput 6,800/day vs inflow 5,200–6,500/day is a margin of
300–1,600/day — inside the noise of a single missed beat. The reason the
margin exists at all is that `poll_kalshi` is currently capturing 356 events
per beat instead of ~7,500; **closing #1586 raises the inflow this rail has to
absorb, and at that point the drain flips to losing.** The two issues are
coupled in that direction and only that direction.

Note the two rates are NOT the same denominator, and this is where the issue's
framing goes wrong: `remaining` counts rows *ahead of the watermark*, so the
drain reduces it by 400/run **whether or not a single snapshot is written**.
`remaining` falling proves the cursor is advancing; it does not prove the
uncovered population is shrinking. Only 172 of 400 (43%) yield history.

### Under the shipped design

| quantity | before | after | note |
|---|---|---|---|
| main pass | 400/run | 400/run | unchanged |
| at-risk pass | 0 | +100/run (`limit // 4`) | new, taken FIRST |
| total examined | 400/run | 500/run | +25% |
| est. duration | ~76 s | ~95 s | +100 × 0.19 s/outcome |
| budget utilisation | 10% | 12% | of 780 s |
| at-risk capacity | — | **1,700/day** | 100 × 17 |
| at-risk inflow | — | **~655/day** | 15,712 residue ÷ 24d lag |
| **at-risk margin** | — | **2.6×** | 1,700 vs 655 |

**Verdict on the at-risk pass: it out-runs its inflow with 2.6× headroom.**
That is the honest claim and the whole claim — it does not improve the main
drain's thin margin at all.

### Under the DESIGNED-ONLY cap raise (§3.1)

| `limit` | outcomes/day @17 runs | est. duration | vs 780 s budget | vs inflow 6,500/day |
|---|---|---|---|---|
| 400 (today) | 6,800 | 76 s | 10% | +300 … +1,600 |
| 1,200 | 20,400 | ~230 s | 29% | **+13,900** |
| 2,000 | 34,000 | ~380 s | 49% | +27,500 |
| 3,500 | 59,500 | ~665 s | 85% | — at the wall |

At `limit=1,200` the 24-day watermark lag closes in **~4 days** instead of
~13, and the rail keeps a 3× margin over inflow even if #1586's capture gap
closes completely. **This is not raising a cap into a wall** — the wall is 780 s
and the rail is using 76 s of it. The binding constraint at 400 is the cap
itself and nothing else.

Recommended: **`limit=1,200`**. Leaves 3.4× duration headroom, is one line, and
is reversible.

---

## 3. Designed, NOT implemented

Nothing here was shipped this window: each item touches a file outside this
item's blast radius (`app/tasks/__init__.py`, `app/tasks/kalshi.py`,
`app/utils/kalshi_scan_report.py`) or needs live proof this window could not
produce.

### 3.1 Raise the drain's cap to 1,200 — `app/tasks/__init__.py`

```python
# beat "kalshi-cliff-drain", ~:3230
"kwargs": {"limit": 1200},
```

`run_cliff_drain`'s signature default stays 400 (a manual/admin trigger should
stay small). The at-risk share is `limit // 4`, so this also takes the at-risk
pass to 300/run — cap it explicitly if that is more than wanted:
`{"limit": 1200, "at_risk_limit": 150}`.

**Gate before shipping:** the run duration must stay under ~400 s. Read
`recent_durations_ms` from `task-metrics?task=kalshi_cliff_drain` for 3 beats
after deploy. If p95 exceeds 400 s, step back to 800.

**Do NOT ship this in the same window as 3.3.** 3.3 raises inflow; shipping
both at once makes an unhealthy duration un-attributable.

### 3.2 Fix `unreached_existing`, or delete it — `app/tasks/kalshi.py:1104-1127`

It is not a measurement (§1c). Replace the derivation with counters the loop
actually keeps:

```python
# in the upsert loop, alongside events_processed:
stats["events_visited"] += 1                    # every iteration, first line
stats["events_no_markets"] += 1                 # at the `continue`
# then:
_reached_existing = max(0, stats["events_visited"] - _n_new)
```

`events_visited` IS a position, so `unreached_existing` becomes true. And add
`events_no_markets` to `KalshiScanReport`
(`app/utils/kalshi_scan_report.py`) — it is the number that explains the
capture curve and there is no field for it. The verdict logic at
`kalshi_scan_report.py:213` currently keys `frozen` off `unreached_existing >
0`, which under the artifact means **every beat is frozen forever**; rekey it
off `events_no_markets` once the counter exists.

The service-side half of this landed today: `events_without_markets`,
`market_backfill_candidates`, `market_backfill_skipped_past_deadline`,
`market_backfill_filled` are now written into `_tel` by
`_fetch_all_events_unfiltered`. They will not appear in `/kalshi/scan-report`
until `KalshiScanReport` carries the fields, which is this item.

### 3.3 Give the empty-event market backfill a reserved budget — `kalshi_api.py`

The actual capture fix, and the highest-value item in either issue. Mirror
`_RESCUE_RESERVE_S`:

```python
_RESCUE_RESERVE_S       = 60.0   # existing: main scan stops here
_BACKFILL_RESERVE_S     = 45.0   # new: supplementary loop stops here
_main_scan_deadline     = deadline - _RESCUE_RESERVE_S - _BACKFILL_RESERVE_S
_supplementary_deadline = deadline - _BACKFILL_RESERVE_S
```

with `_past_supplementary_deadline()` replacing `_past_deadline()` inside the
supplementary series loop only, and the backfill gated on the full `deadline`.

Then three changes to the backfill itself:

1. **Drop the `"sport" in category` filter.** Non-sport market-less events are
   dropped by the upsert loop identically and were never candidates.
2. **Prioritise `_HEAVY_TOKENS` events.** They are market-less *by our own
   choice* and the backfill is the promise that redeems it. Sort them first.
3. **Persist a rotation cursor** — `bainluck:kalshi:market_backfill_offset`,
   the same shape as `_MAIN_CURSOR_KEY`. 45 s at 0.3 s/event is ~120 events per
   beat against ~13,000 candidates; without a cursor, every beat backfills the
   same first 120 and the other 12,880 are never reached. **Ordering is never
   the whole answer — ask what the ordering starts on** (gotcha #41). This is
   that gotcha's third instance in these two issues.

**Convergence check, not liveness:** the acceptance test is
`events_without_markets` **falling** across beats, not "the backfill ran".

**Sequence gate:** `poll_kalshi` is the task behind #995's month-long creation
freeze. Ship 3.3 alone, watch `events_processed`, `markets_processed` and
`total_api_events` for 3 beats, and only then consider 3.1.

### 3.4 Give the drain's `partial` terminal somewhere to go

`kalshi_cliff_drain` reports `health=critical`, `successes_24h=0`,
`consecutive_failures=5` — permanently, because `terminal` is `partial` on
every run that moved the watermark and `complete` is only reachable when the
cohort is exhausted, which will not happen while markets keep resolving. A
signal that cannot change carries no information; that is the crying-wolf shape
the grid health score was retired for.

`convergence` is now the honest input to that verdict: a run that made its
quota, banked its watermark, has no errors and sits on a `converging` ring is a
run that did its job. Options, in preference order:

1. Teach `task_verdict._classify` to read `convergence.verdict` for enrolled
   sweep tasks (`app/utils/task_verdict.py` — owned elsewhere; needs a ruling,
   because it widens what `COMPLETE` means).
2. Add a `sweep_ok` terminal to `_TERMINAL_COMPLETE` for resumable sweeps that
   met quota AND are converging.
3. Leave it and read `convergence` directly in `/health`.

Not shipped: it needs a decision about verdict semantics, not code.

---

## 4. Open questions the next queue should settle

1. **Is `empty_present` a true fact?** 12,232 outcomes came back
   HTTP-200-with-no-candles while their market lookup returned 200. If that is
   real, the 15,712-row residue costs nothing and §1b is closed. If it is an
   artifact of *our request shape* (`period_interval=60`, the
   `settlement−120d … settlement+1d` window, or a swallowed rate limit), it is
   12,232 recoverable price histories walking off the cliff at ~655/day.
   **Cheap to settle:** sample 50 `empty_present` tickers still inside the
   window, re-probe at `period_interval=1` and at a widened window, and run a
   positive control (a known-good ticker of the same age) beside it — *a
   negative result about upstream is only believable next to a positive
   control*, this module's own rule.
2. **Why do 5,000 main-scan events fetched WITH nested markets still yield
   ~356 processed?** The `_HEAVY_TOKENS` supplementary events explain the 8,513
   half. The main-scan half is unexplained and is the larger prize.
3. **Which rail actually covers the 25–60d cohort?** Coverage climbs from 9.3%
   uncovered at 25–30d to 0.1% at 55–60d, and the cliff drain's cursor has
   never been past 24d. Something else is doing that work
   (`backfill_kalshi_history`, `backfill_kalshi_candlestick`); knowing which
   tells us whether the cliff drain is needed at its current size at all.
4. **Re-measure `remaining` on a 6-point ring.** The convergence block now
   records one automatically per run; read it at
   `GET /api/admin/kalshi/cliff-drain` (which should also stop H12-ing now) or
   in `task-metrics.last_result_summary.convergence`.
