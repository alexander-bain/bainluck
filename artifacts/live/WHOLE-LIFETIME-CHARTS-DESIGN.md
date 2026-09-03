# A finished match draws its whole life — design (live/035)

PILLAR: TRUTH · SHIP: **a settled match page draws the full curve — pre-match drift, the in-match
swings, the settlement — instead of a single dot written after the final point.**

Alex, 2026-09-01 ~10pm PT, on `/events/15300759` (Vallejo v Monfils, US Open): "the win-prob chart
is a single dot at 7:59pm, written after the match ended; no pre-match drift, no live swings."
Ruled to outrank the SSE-to-phone half of live/034: *a chart with one point is the defect to fix
first.*

Status: **BUILT.** Backend rail + live cadence floor + the read-side window fix, with guards.

---

## 1. The diagnosis, measured — and it is not a cadence bug

Production, 2026-09-02:

| Fact | Value |
|---|---|
| `events.id 15300759` `created_at` | **2026-09-01 22:05 UTC** |
| `events.status` / `commence_time` / `completed_at` | `scheduled` / 2026-08-30 00:00 UTC / `NULL` |
| `futures_markets 59693708` (`KXATPMATCH-26AUG30VALMON`) `created_at` | 2026-08-28 18:49 UTC, `resolved` |
| Its two outcomes' `futures_odds_snapshots` | **53 rows, 2026-08-28 → 2026-09-02**, opening 0.535 → 0.01 |
| `win_prob_snapshots` for the event | **1 row**, `captured_at` 2026-09-02 02:59 UTC, `reading_count` 7 |
| Kalshi `open_time` / `close_time` for `…-MON` | 2026-08-27 17:16 → 2026-09-02 01:40, `result: yes` |
| Kalshi candlesticks for that ticker, 1-minute | **2,081 points, 0.495 → 1.0**, 2026-08-27 17:17 → 2026-09-02 01:43 |

**The event row is younger than the match it describes.** Kalshi listed the market on 08-27, we
minted the market on 08-28, the match played on 09-01 — and the `events` row the chart hangs off
did not exist until 09-01 22:05. Every win-prob writer we have is a *sampler*: it records what it
sees while it is looking. None of them can record what happened before the row existed.

Two corollaries that decide the whole design:

* **No amount of live-cadence work fixes this.** A faster sampler still has nothing to sample
  before 22:05 on the last day. Item 2 below is still worth building — it is a real defect on its
  own — but it is not what draws this chart.
* **This is the steady state for prediction-market-native events**, not an outlier. Tennis, combat
  and anything with no sportsbook get their `events` row created by the market matcher, which runs
  on markets, not on schedules. The 53 `futures_odds_snapshots` prove we *were* watching the price
  the whole time — into a different table, one the event chart does not read.

The missing history still exists at the venue, and both venues publish it:

    Kalshi      GET /markets/candlesticks?market_tickers=…      per MARKET ticker (= our outcome)
    Polymarket  GET /prices-history?market={clob_token_id}      per CLOB token

---

## 2. Three measured traps in the Kalshi endpoint

All found by probing the specimen's own ticker on 2026-09-02, all encoded as constants + guards
rather than as prose:

* **A 7-day window at `period_interval=1` is refused.** 10,080 periods → HTTP 400; 10,000 → served
  (2,080 candles). So the specimen's own lifetime cannot be fetched in one request, and a naive
  fetch records the exception as "no history". `candle_windows()` chunks at
  `KALSHI_MAX_PERIODS_PER_REQUEST = 5000`, half the observed ceiling.
* **`period_interval` 5 and 15 are not errors — they are nonsense.** They return **4** candles for
  a window that yields 1,134 at 1-minute. An answer shaped like data is worse than a refusal, so
  `choose_period_interval()` can only ever emit a value from `KALSHI_PERIOD_INTERVALS = (1, 60,
  1440)`, and a test asserts that across six lifetimes.
* **The shared normalizer reports a settled LOSER at 1.0.** Caught by the first live dry-run of
  this rail, before anything was written. `KalshiAPIService.get_market_candlesticks` reduces a
  candle to the bid/ask mid and falls back to the **ask** when there is no bid — and at settlement
  a losing market's book is the shell `bid 0.0000 / ask 1.0000`. The raw final candle of
  `KXATPMATCH-26AUG30VALMON-VAL` (Vallejo, who LOST) carries exactly that, with
  `price.previous_dollars = 0.0100`. Priced off the ask, the dry run ended Vallejo's curve at
  **1.0** — a chart whose last act is to declare the loser certain.

  The fix is a chart-specific normalizer, `normalize_candle()`, over a new
  `get_market_candlesticks_raw()`: trust the mid only while the spread is tight enough for a mid to
  mean anything (`WIDE_SPREAD_DOLLARS = 0.10`), else take the last TRADE, else a single real quote,
  else no price at all. This is gotcha #19's rule — "wide spread → lastTradePrice" — already
  learned at Polymarket and now applied at Kalshi.

  The shared method is deliberately **left broken**: its two consumers (`kalshi_cliff`,
  `_backfill_kalshi_price_history`) fill calibration buckets, and changing their inputs is not this
  queue's to do. It now carries a note naming the flaw and pointing chart callers at the raw
  method, and a control test asserts the old reduction still answers 1.0 — so if it is ever fixed,
  that test fails and the note comes out.

### The backstop, because this is the failure that matters most

Orientation is borrowed so a mirrored curve cannot happen — but "cannot happen" deserves an
assertion. `contradicts_known_winner()` refuses to write any settled series whose last point sits
confidently (>10pts) on the wrong side of the venue's own settlement. Nothing is written on a
contradiction: **a missing chart is a gap, a mirrored one is a legible lie.**

It only acts when exactly one outcome is positively marked `is_winner` — that column is a Boolean
defaulting to False, so absence is not a loss (the trap #195 hit grading ungraded props as misses).
And the margin is stark on purpose: it catches an inverted AXIS, not a surprising RESULT. A genuine
upset ends with the loser high and is a true story about the market; a test asserts a 0.85 finish
by the loser passes untouched.

---

## 3. What was built

### Item 1 — `app/tasks/event_chart_backfill.py`, the recovery rail

Writes `win_prob_snapshots` — the table `/api/events/{id}/history` reads into `win_prob_history`
and the chart draws. Four decisions carry the weight:

**Orientation is borrowed, never re-derived.** A backfilled curve that is flipped is worse than no
curve: it is a confident lie about who was winning. `resolve_orientation()` runs the exact chain
the 120s poll and the WS fast lane use — `select_primary_market` →
`extract_matchup_with_ticker_fallback` → `find_moneyline_outcome` — so a backfilled point and a
live point sit on the same axis by construction. A test asserts the two agree on the same market.

The one concession: `find_moneyline_outcome` discards outcomes priced at exactly 0 or 1, which is
right for a live read and fatal here, because **1.0/0.0 is the steady state of the settled cohort
this rail exists for**. `_ClampedOutcome` re-runs the same selector over nudged copies; it changes
only which outcome is *selected*, never a probability that reaches the chart. Its control test
asserts the unclamped selector really would have declined.

**Compression that keeps every move.** 2,081 rows per source per event does not survive as a
nightly policy. `compress_series()` keeps every value change, both endpoints, and a heartbeat while
flat — for the specimen, ~266 changes + heartbeats ≈ 600 points. A chart is ~1,000px wide; the
discarded points were never going to be pixels. The endpoints are kept *independently* because the
opening opinion and the settlement are the two points a finished chart is read for.

**Idempotent by minute, not by constraint.** `win_prob_snapshots` has no unique index on
`(event_id, source, captured_at)`, and adding one means a non-CONCURRENT unique build over a very
large table inside an Alembic release — gotcha #31, the shape that took the site down in May.
Instead the existing minute-truncated stamps are read once and used as a skip set; candle
timestamps are period-aligned, so a re-run is a no-op. Guarded both ways: a second run writes
nothing, and an already-present live point is skipped around rather than duplicated.

**`game_state` carries no in-game state.** `app/utils/game_window.py` (#1828) deletes state-bearing
win-prob rows from outside the game window on read — and on this cohort `commence_time` is exactly
the field that is wrong, so those rows would be deleted as they were drawn. A candlestick asserts a
price, not an inning, so the stamped `game_state` carries market provenance and
`poll_type: "history_backfill"` and no `period`/`inning`/`clock` key. A test runs the real filter
over the real output and asserts `dropped == 0`.

**Selection, for the nightly sweep.** `is_thin_chart(points, lifetime)` — fewer than one point per
hour of market life, capped at 120 — decides. Bounded at BOTH ends per gotcha #41: a floor at
`PROVABLY_PURGED_AGE_DAYS` keeps the sweep off markets Kalshi has already deleted, and inside that
floor it works **oldest-first**, so the at-risk edge is reached before it expires. Newest-first
would starve exactly the rows that die.

The selection query is the *second* shape it was written in. The obvious one — one `GROUP BY` with
`LEFT JOIN win_prob_snapshots` and `COUNT(DISTINCT w.id)` — hit **`statement_timeout` on
production**, because it counts points for every candidate before the LIMIT can discard any.
Bounding the candidate set first and counting only the survivors with a correlated subquery
measured **1.9s for 360 candidates**. A nightly task whose selection query times out is a nightly
task that never runs, and it would report cleanly while doing nothing (gotcha #53). A test asserts
the timing-out shape cannot come back.

**Cohort size, measured 2026-09-02:** of 360 oldest candidates inside the retention floor, **355
are thin**. The specimen is the steady state, not an outlier.

Surfaces: `app.tasks.backfill_event_chart_history` (targeted), `app.tasks.backfill_thin_event_charts`
(nightly 08:40 UTC = 01:40 PDT, after the morning sentinels), and
`POST /api/admin/backfill-event-chart` which runs **inline by default** and returns the per-source
verdict — a repair whose result you cannot read is a repair you cannot certify.

### Item 2 — the live cadence floor

`_create_or_update_win_prob_snapshot` appends only on a value CHANGE. That is why a live game with
a settled price draws one straight segment between two distant points. It now takes
`max_gap_seconds`: unchanged **and** older than the floor is a new observation and gets its own row.

The arithmetic matters and is its own tested function. A deadline equal to the sampling period is
first observed breached one whole period LATE, so `heartbeat_deadline(target, period) = target −
period`. With the shipped constants a flat live market's worst-case gap is **45s**, under Alex's
one-per-minute bar; the test simulates the sampler and fails if it is not.

Both writers pass it and nobody else does, so growth is one row/minute/source on games actually in
progress and **zero** everywhere else. It is explicitly not applied when `is_completed` — a
heartbeat there would rebuild the post-final stale tail #922 exists to prevent, and there is a test
for that.

### Item 1b — the read-side window, without which item 1 is invisible

`GET /api/events/{id}/history?hours=N` windows a non-finished event at `now − N`. The web page asks
for `hours=48`. That would clip four of the five days the backfill just recovered — and this event
is not finished, because nothing ever settles a Kalshi-native tennis event.

`_event_started_long_ago_unsettled()` fires only when `commence_time < now − hours`: an event that
started before its own whole window and never reached a terminal status is not being *focused* by
that window, it is being *chorded*. Such an event is served whole and cached for an hour like a
finished one. The end is deliberately left **open** rather than capped at `commence_time +
max_duration`, because on this cohort `commence_time` is the untrustworthy field (a Kalshi
ticker-derived midnight, gotcha #14 — here wrong by two days); capping there would clip the real
match out in the name of trimming a stale tail. The 3,000-row LIMIT bounds the response.

The `time_domain` (#240) is widened — never narrowed — to contain the earliest point served, for
the same reason: an axis anchored on a wrong `commence_time` can open *after* the data it is the
axis for.

A live game keeps its window. The control test drives the real route with a stub that honours the
compiled bind parameters, so "the window was lifted" and "the window was ignored" cannot pass as
each other.

---

## 4. What this does not do

* **It does not settle the specimen.** `events.id 15300759` is still `status='scheduled'` with no
  scores for a match that finished on 09-02. That is a settlement-authority defect
  (`resolution_engine`, the authority ladder), not a chart defect, and fixing it here would be
  scope creep into another lane. The chart is correct without it — which is the point of leaving
  the window open rather than trusting `commence_time`.
* **It does not correct `commence_time`.** Same reason: gotcha #14's ticker-derived stand-in is a
  matching-layer fact. This design routes *around* it rather than depending on it.
* **It does not devig the backfilled series.** The live writers devig only when a source published
  exactly two markets for the game; Kalshi tennis publishes one market with two outcomes, so there
  is nothing to average and the single reading stands — identical to what the live path does.
