# live/042 — CERT-753 repair: an error is not an absence

**PILLAR:** TRUTH. **SHIP:** the 30-day chart drain stops reporting `drained`
over US Open match pages it never managed to fetch — an event the venue refused
is retried by id, and the pages fill.

**Branch:** `live/035-whole-lifetime-charts` @ `25771922`, rebased onto master
`da6eebfa`. **Subject of the repair:** `28468003` (CERT-753 BLOCK).

---

## Queue item 1 — already delivered, by another lane

The queue asked to fold live/041's Polymarket prefix fix out as a separate small
ship first, so PM attach was not held by this repair. It was already done:
`cd4ec4e8` is **byte-identical** to `86261a94`'s parser hunk (same blob
`fa469153`) and merged to master at `a1fe4212` under **CERT-759**. The rebase
dropped the duplicate — this branch's diff against master contains no parser
change and no `test_us_open_draw_qualifier_prefix.py`.

**Confirmed live, LOOK pass 2026-09-02 ~11:35am PT.** `/events/15299858`
(Shelton v Hurkacz — the exact specimen CERT-730 and CERT-753 both named as the
curve that could never draw) now renders a full live win-probability curve,
"+2 sources", 10:15am–11:35am. Production DB: **72 Polymarket win-prob points**
on that event where it had none. Three more from the same cohort: Kostyuk v
Stephens 94, Jodar v Bu 104, Etcheverry v Fearnley 88.

---

## The two defects, and the third thing the repair needed

### 1. `get_prices_history()` swallowed every failure into `[]`

```python
except Exception as e:
    logger.warning(...)
    return []
```

A `ConnectTimeout`, a 429, a 502 and a token that genuinely has no series all
returned the same value. `fetch_polymarket_series` counted it `api_empty`,
`_tally` folded that into "genuinely empty", the tier's **permanent** Redis
checkpoint advanced past the event, and the verdict said `drained`.

Now raises `PolymarketHistoryUnavailable`. The distinction is kept where the
counts are:

| situation | before | after |
|---|---|---|
| transport / HTTP failure, every fidelity | `api_empty` | `fetch_failed` (retryable) |
| fidelity 1 errors, fidelity 60 returns data | data | data (unchanged) |
| fidelity 1 errors, fidelity 60 returns `[]` | `api_empty` | `api_empty` — the venue **answered** |
| both fidelities return `[]` | `api_empty` | `api_empty` (unchanged) |
| 200 with a non-list `history` | `api_empty` | `fetch_failed` |
| Kalshi: every candle window errored | `api_empty` (after an existence check) | `fetch_failed`, and `get_market` is **not consulted** |
| Kalshi: 404 on the market lookup | `purged` | `purged` (unchanged) |

Other two call sites: `tasks/polymarket.py:1877` already had its own `except`
and now separates the outage from `api_empty` for free;
`_backfill_polymarket_win_prob_history` had none and gets an explicit one that
records "price history unavailable", not "empty price history".

### 2. Exhaustion was inferred from the SQL, not from the loop

```python
return DrainPage(fillable, cursor, len(rows) < scan, len(rows))
```

`len(rows) < scan` says the **query** ran out. The Python loop above it breaks
early the moment `limit` fillable events are collected. The cert's exact
reproduction — 250 thin rows, limit 200, scan 800 — returned `exhausted=True`
over 50 rows the loop never judged, and the tier was marked permanently done.

Exhaustion now requires **both** halves: the query ran out **and** every row it
returned was consumed. `scanned` reports rows JUDGED, which is what the cursor
actually covers.

### 3. A FAILED event is retried, not marked done — by id

The census is three outcomes where it was two: `filled`,
`empty_with_no_history`, `failed`. `_tally` returns the third, `_drain_events`
returns the failed ids, and they land in a per-tier Redis HASH of
`event_id -> attempts`. The next trigger drains that hash **before** it scans new
ground, and a tier cannot be marked done while the hash is non-empty.

**Per EVENT, and that is the second draft.** The first retried by clearing the
tier cursor and re-scanning from the top. Correct and terminating, but wasteful
past the point of being acceptable: the selection query returns everything still
thin, and **14,240 of these events hold nothing at all and will stay thin
forever**, so one failure at the tail of the remainder tier would re-ask ~13,591
events per lap. Holding the ids makes the retry O(failures).

Bounded at `MAX_EVENT_RETRIES=3`. An event that can never be fetched drops out
of the hash and increments a per-tier give-up counter; a non-zero counter makes
the tier end `drained_with_failures` — terminal, and deliberately not spelled
`drained`.

Tier statuses: `in_progress` · `awaiting_retries` (scan finished, retries owed —
**not** terminal) · `drained` · `drained_with_failures`.

Backward compatible: `_read_checkpoint` reads the old bare `"1"` done-marker as
the clean verdict it meant, `_verdict` maps a legacy `already_drained` tier
status to `drained`, and `reset_checkpoints` clears the new keys.


### 3b. Two holes the repair opened, closed before staging

**A deleted event row held its tier open forever.** An id in the retry hash
whose `events` row has since been deleted is never *attempted*, so
`_record_attempts` never saw it and never dropped it — and its tier would sit at
`awaiting_retries` permanently, unable to finish. That is the false-`drained`
defect wearing its opposite face, and it would have been mine, not inherited.
`DrainPass` now reports `missing` separately and the caller settles those ids
too. Guarded.

**The retry hash can be evicted, and that is stated rather than hidden.** Redis
here is one shared 100MB LRU. If `chart_backfill_30d:retry:{tier}` is evicted the
owed retries are forgotten and the next exhausted scan marks the tier `drained`
— the same false-`drained` shape, arriving by eviction instead of by logic. It is
**not** defended with new durable state, deliberately: the events remain thin and
therefore remain findable (both steady-state rails still reach them, and
`reset=true` re-scans the window). What is not acceptable is leaving it unsaid,
so it is said in the module docstring beside the key and here.

---

## Gates

| gate | result |
|---|---|
| new guard file `test_chart_backfill_failure_is_not_absence.py` | **35 passed** |
| both arms (rsync copy, 6 source files reverted to `28468003`, guard file held constant) | **without: 29 failed / 6 passed · with: 35 passed** |
| focused: thirty_day + event_chart_backfill + reader scope + startup + wiring | **206 passed** |
| polymarket / matching / prediction-market (`-k`) | **1,560 passed** |
| full backend suite, run on the FINAL tree after the last edit | **26,691 passed, 160 skipped, 61 xfailed, 0 failed** (21:20) |
| ruff on every file this touches | clean (the 14 pre-existing findings in `prediction_market_matching.py` are unchanged in count, measured both arms) |
| frontend / iOS | no file in the diff — those gates cannot move and were not run |

**The 6 controls green in BOTH arms**, and they are the point: an empty
`history` list is still an empty list; a real series still comes back; a token
that answers empty on both fidelities is still `api_empty`; the cursor still
stops on the last judged row; a short page the loop FINISHED is still exhausted;
a break on the very last row is still exhaustion. Without the last two the
repair could answer `exhausted=False` forever and the drain could never finish.

New symbols are resolved **lazily inside each test**. A module-level import of
`_settle_tier` or `PolymarketHistoryUnavailable` collapses the whole file into
one collection error against the pre-fix tree, which is red for the wrong reason
and proves nothing about any individual guard.

---

## Not run

The drain's admin endpoints still 404 on production because live/035, 036 and
039 remain unmerged. No production write, no merge, no push.

## Filed / observed, not built

The LOOK pass over `/tournaments/us-open` reproduced **#2690** (open, Alex's own,
filed 18:36Z today): the hub renders Rafael Jodar v Bu Yunchaokete as "Nobody is
quoting this match yet" while event 15300190 is LIVE with 10 linked markets,
`betting 0.2846` + `polymarket 0.30`, and a snapshot 30 seconds before render.
Already owned — corroborated, not re-filed.
