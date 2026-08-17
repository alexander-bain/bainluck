# CAL-P064 — P-5 discharged, the instrument fixed, the PM zero-winner mass explained

Window: 2026-08-17 (PT). Queue: CAL-P064. Branch: `program/calibration-61`.
Scope: one code change (the sentinel instrument), everything else read-only.
**No market data was written.**

Every number below was measured DB-direct through the read-only `db-query` rail on
2026-08-17. **Nothing here is read off `/api/calibration`** — see §0, which is the
reason.

---

## 0. Gate 0 CANNOT BE DISCHARGED, and that changes how the wave is graded

CAL-P063's post-apply plan opens with *"Gate 0 — force a calibration recompute and
verify it."* Measured this window, that is not possible.

`GET /api/admin/task-metrics?task=precompute_calibration_main`:

| field | value |
|---|---|
| `last_success_at` | **`2026-08-14T00:16:08.240772+00:00`** |
| `successes_24h` | **0** |
| `failures_24h` / `incompletes_24h` / `starts_24h` | 14 / 3 / 11 |
| `consecutive_failures` | **88** |
| `last_verdict` / reason | `partial` / `StagedFuturesIncomplete` |
| `last_result_summary` | `futures generation incomplete — units banked, nothing published` |
| `last_error` | `QueryCanceledError: canceling statement due to statement timeout` on the `WITH market_info AS (...)` futures CTE |
| `health` | **critical** |

`GET /api/calibration` reports `generated_at: 2026-08-14T00:16:07.908709+00:00` — the
same instant as `last_success_at`, to the second. Producer ledger and served payload
agree.

**88 consecutive failures at an hourly beat is ~88 hours; last success to now is
~89.5 hours.** Those reconcile, so this is not intermittent — it is *every* beat since
2026-08-14. `worker-heavy` is confirmed **up** (`heroku ps`), so a forced recompute
would queue, run, and cancel like the preceding 88.

Two consequences, both binding on the attended wave:

1. **Grade the applies DB-direct.** Any post-apply number taken from the published
   snapshot is STALE-INSTRUMENT by construction and grades nothing. That is why this
   document contains no snapshot reads.
2. **`?bust=1` no longer exists on the public endpoint** and Gate 0's wording should
   stop naming it. It was retired in Queue 300B Item 0 as an unauthenticated recompute
   trigger (`routes/calibration.py:791-795`). The surviving rail is
   `GET /api/admin/calibration/mce?bust=true`, which *queues* the heavy task.

Filed as a comment on **#1680**, whose title still says "since 2026-08-02" — three
readings out of date. #1597 carries the same stale date.

---

## 1. P-5 IS DISCHARGED — the direction is DOWN, by 1.65pp

CAL-P063 registered P-5 as an obligation, not a claim: *"I attempted to measure the
ITF cohort's own curve and it timed out — NOT-RUN. I am explicitly declining to
predict the sign."* It is now measured.

### Why it kept timing out, and what fixed it

`EXPLAIN` (not a rerun — the plan, taken via `db-query`'s `explain:true`) shows the
planner drives **from a Seq Scan on `futures_outcomes` (1.97M–3.3M rows)** and probes
`futures_markets` by pkey. Every cohort filter in this queue lives on
`futures_markets`, so **none of them restrict the scan**. An `OFFSET 0` optimisation
fence does not help — it converts the nested loop to a Hash Join over the same seq
scan, and still hit `statement_timeout` at 10s (measured).

The fix is to shard: page the cohort's market ids out of `futures_markets` (small,
bounded), then aggregate `futures_outcomes` with an explicit `market_id IN (...)` list,
which forces `ix_futures_outcomes_market_id`. Each shard is milliseconds. **All
aggregation is server-side** so a shard returns ≤40 rows — the db-query 1000-row cap
truncates SILENTLY, and the first version of the reader tripped its own guard at
exactly 1000. Every call now asserts it came back under the cap.

This technique is reusable and is what produced every number in §1–§3.

### The two curves

| cohort | n | n-wtd MCE | max abs gap |
|---|---:|---:|---:|
| **HOST** — #1896 `tennis × binary` | 137,232 | **18.85pp** | 26.72pp |
| **ARRIVING** — ITF migrating (`KXITFMATCH-%`, category ≠ tennis), binary | 13,876 | **1.79pp** | 6.11pp |

**Reproduction is exact.** #1896 filed `MCE 18.9pp, n=137144`; measured 18.85pp at
n=137,232 (88 rows of drift over three days). Note the sentinel's "MCE" is
`_compute_horizon_mce(weighted=True)` — an n-weighted *mean* absolute gap, i.e. ECE by
the usual naming. The equal-weighted max is 26.72pp. Not a defect, but the label
misleads: **quote 18.85 as n-weighted, never as "the worst band".**

### The projection

Blending the arriving population into the host, band by band:

| band | n before | n after | gap before | gap after | Δ |
|---|---:|---:|---:|---:|---:|
| 0-10 | 11,760 | 15,542 | +3.17 | +2.08 | −1.09 |
| 10-20 | 2,255 | 2,550 | −3.13 | −3.22 | −0.09 |
| 20-30 | 4,254 | 4,647 | −5.99 | −6.00 | −0.01 |
| 30-40 | 8,617 | 9,061 | −11.18 | −10.81 | +0.37 |
| 40-50 | 13,840 | 16,099 | −17.12 | −15.05 | +2.07 |
| 50-60 | 67,146 | 68,928 | −26.00 | −25.43 | +0.57 |
| 60-70 | 8,851 | 9,218 | −26.72 | −25.75 | +0.97 |
| 70-80 | 4,339 | 4,754 | −22.13 | −19.99 | +2.14 |
| 80-90 | 2,303 | 2,638 | −19.69 | −17.33 | +2.36 |
| 90-100 | 13,867 | 17,671 | −4.29 | −3.36 | +0.93 |

> **n: 137,232 → 151,108 (+10.1%). n-weighted MCE: 18.85pp → 17.20pp (−1.65pp).**
> The cohort stays RED (17.20 ≫ 5.0). Every gap shrinks in magnitude except 10-20 and
> 20-30, which move −0.09 / −0.01 — nil.

### THE POINT, and it is a live hazard for the wave

**−1.65pp is larger than P-1's own refutation threshold of 1.0pp.**

P-1 predicts the attended applies move #1896 by **< 1.0pp**, and says any movement
≥1.0pp refutes it. If the #1109/#1888 ITF repair lands in the same wave, #1896 will
move about −1.65pp **from the migration alone**, and P-1 will read as REFUTED when
nothing about its mechanism was wrong. That is precisely the misattribution CAL-P063
warned about — now quantified instead of feared.

**So P-1 must be graded net of a declared −1.65pp subtraction, or the ITF repair must
be deployed on its own read (ruling 046: a stacked change is measured on its own
deploy).** Recommend the latter.

### P-4 is confirmed to the row, with one sub-claim corrected

Measured, versus what P-4 predicted:

| P-4 claim | predicted | measured | verdict |
|---|---:|---:|---|
| migrating cp-bearing outcomes | 14,407 | **14,407** | exact |
| donor: baseball | −8,003 | **−8,003** | exact |
| donor: football | −2,960 | **−2,960** | exact |
| donor: basketball | −3,282 | **−3,282** | exact |
| #1896 n after | ~151,500 (+10.5%) | 151,108 (+10.1%) | holds |

Two corrections, neither refuting:

* **"ITF is 2-outcome (13,807 outcomes / 6,946 markets ≈ 1.99)"** — 6,946 is the
  **baseball slice**, not all of ITF. There are **13,363** resolved ITF markets across
  18 categories. The migration counts were right anyway, so this only matters if
  someone reuses the denominator.
* **96.3% of the migrating rows land in `binary`; 531 (3.7%) land in `single`.** P-4
  said the cohort lands in `tennis × binary` outright. The 531 go to
  `tennis × single`, which is why n rises +10.1% and not +10.5%.

Also measured: of 7,521 ITF markets with cp-bearing outcomes, 92.9% are binary, **3.1%
(230) carry zero winners**, and **0.0% carry more than one**.

---

## 2. The instrument is fixed, and TWO red cells change verdict

`#1903`/`#1904`/`#1905`/`#1906` are fixed in this branch — commit
`CAL-P064 (#1903, #1904, #1905, #1906, #1544)`. They were fixed **before** any cell
work because a detector that drops dimensions hands you the wrong population: fixing
the instrument changes the red list itself.

Re-emitting the six calibration cells under the fixed coverage rule (exact SQL-counted
union rather than the max single class), measured DB-direct:

| cell | n | exact union | dominant class | CAL-P063 | **CAL-P064** |
|---|---:|---:|---|---|---|
| #1895 poly · mma | 4,470 | 34.8% | malformed_binary 30.2% | UNEXPLAINED | UNEXPLAINED → **AMBIGUOUS** (see below) |
| **#1896 tennis · binary** | 137,232 | **44.4%** | malformed_binary 39.6% | UNEXPLAINED | **EXPLAINED by malformed_binary** |
| #1142 kalshi · KXNHLGOAL | 14,315 | 24.1% | kalshi_prop_threshold 23.1% | UNEXPLAINED | UNEXPLAINED |
| #1143 kalshi · KXMLBTB | 41,047 | 36.4% | kalshi_prop_threshold 27.3% | UNEXPLAINED | UNEXPLAINED |
| **#1144 poly · politics** | 19,651 | **46.7%** | mex_normalization 36.9% | UNEXPLAINED | **EXPLAINED by mex_normalization** |
| #1145 hockey · binary | 5,272 | 17.0% | malformed_binary 12.8% | UNEXPLAINED | UNEXPLAINED |

**Two of six flip — and they are exactly the two CAL-P063 predicted would flip, by the
margins it predicted** (#1896 "filed by 0.4pp", #1144 "filed by 2.4pp"). That is an
independent confirmation of CAL-P063's read, arrived at from the fixed instrument
rather than from its arithmetic.

`#1895` is the interesting one. Its exact union is 34.8%, and `poly_placeholder` adds
~14.0% — but `poly_placeholder` is estimated from a **bounded snapshot sample** and so
cannot join the SQL-counted union. The honest answer is an interval, **[34.8%, 48.8%]**,
with the 40% threshold **inside** it. Neither "explained" nor "unexplained" is a true
statement about that cell, so the fix reports the interval and renders it AMBIGUOUS.
It still files — the automatic decision takes the lower bound, because a suppressed
real break ships miscalibration to users while an over-filed cell only makes noise.

### A FIFTH instrument defect, found while re-emitting

`#1142`'s union is 24.1% and its dominant class `kalshi_prop_threshold` is 23.1% — so
coverage can *never* explain it, yet its correct disposition is **CLOSE**. The
published MCE is 3.69pp, under threshold, because the shipped CAL-P013 exclusion drops
the offending rows.

**The sentinel flags on RAW MCE and has no view of the PUBLISHED curve at all.** Those
are different questions: coverage counts *excluded rows*, while the disposition depends
on what the *remaining* rows do. A cohort the shipped exclusion already fixes therefore
files at full raw severity — #1142 filed at 21.33pp raw against 3.69pp published.

No coverage-threshold tuning can fix this, because the two numbers are not related by a
fraction. Filed as a new issue; **not** fixed here (the four already in the branch are
the ones Fable scoped).

---

## 3. The PM zero-winner mass is a GRADER GAP — 100% recoverable, and the rail is green while writing nothing

Registered hypothesis (ruling 050), before measuring: *the PM winner pipeline itself —
C-UC-1 found `_backfill_polymarket_winners` is DEAD CODE and the live path is
`_from_api`.*

### The dead-code claim is CONFIRMED, and it is sharper than filed

`_backfill_polymarket_winners` (`backfill_winners.py:577`) has **zero live callers**.
The trap is the naming: the Celery task *named* `app.tasks.backfill_polymarket_winners`
(`tasks/__init__.py:909`) calls `_backfill_polymarket_winners_from_api`, and so does
the admin trigger. Anyone reading the beat schedule, the task name, or the admin route
would conclude the function at :577 is the live grader. It is not.

But the dead function is **not the cause** — see below. It is a decoy.

### The census — the split Fable asked for

PM tennis, resolved, cp-bearing markets (n = 66,786):

| | markets | share of zero-winner |
|---|---:|---:|
| exactly 1 winner (healthy) | 31,540 | |
| >1 winner | 6,157 | |
| **ZERO winners** | **29,089** | |
| → **never graded** (`resolution_source` NULL on *every* leg) | **25,264** | **86.9%** |
| → graded all-loser (a named source on every leg) | 3,824 | 13.1% |
| → partial (mixed) | 1 | 0.0% |

The discriminator is gotcha #53 turned on our own writer. "Zero winners" is a response
shape, not a fact, and it collapses two opposite bugs: `is_winner=false` with
`resolution_source` NULL is **the column default standing in for a grade that was never
written** — nothing ever decided the market — whereas a named source on every leg means
something ran, looked, and wrote "loser" on all sides. **86.9% of the mass is the
first.**

Graders responsible for the 3,824 that *were* actively graded all-loser:

| source | n | share |
|---|---:|---:|
| `pass2_loser` | 1,361 | 35.6% |
| `clean_resolution` | 1,343 | 35.1% |
| `api_settlement` | 597 | 15.6% |
| `all_losers` | 399 | 10.4% |
| `pass2_guess` | 112 | 2.9% |
| `pass3_threshold` / `clob_authoritative` / `clob_ordinal` | 12 | 0.3% |

Only **604** of 3,824 come from an authoritative rung; the rest is guess-family. And
`api_settlement` writing an all-loser verdict at the top authority rung is the **#1868
premature-grade shape**, now confirmed present on the Polymarket side too.

### Three-way split: there is no evidence-absent bucket

`scripts/probe_polymarket_retention.py` re-run this window: **exit 0**, boundary
`(2023-01-01, 2023-11-03]` holds, gamma offset cap ~1992.

Of the 25,264 never-graded markets, bucketed by resolution date against that cliff:

| | n | share |
|---|---:|---:|
| **inside retention** (venue still answerable) | **25,264** | **100.0%** |
| past the cliff (evidence-absent) | 0 | 0.0% |
| no date | 0 | 0.0% |

**Every one resolved in 2026.** Not a single row is past the retention cliff.
"Genuinely unresolved" is empty by construction — all are `status='resolved'` in our own
DB.

> **VERDICT: this is a grader gap, not an ingest gap and not real. 25,264 of 25,264 are
> recoverable, with zero retention loss.**

### The mechanism — an ownership hole between two rails, both reporting healthy

**Rail 1 — the Gamma grader** (`_backfill_polymarket_winners_from_api`). Its own last
run, from `task-metrics`:

```
markets_checked: 252,  winners_set: 1150,  losers_set: 2094,
unsupported_lookup: 9748,  api_miss: 0,  no_match: 0,  errors: []
```

It pulls ~10,000 markets and **discards 9,748 of them — 97.5%** — as
`unsupported_lookup`. That branch (`backfill_winners.py:4955-4957`) drops every market
whose `external_id` starts with `0x`, deliberately, with the comment *"They are the
CLOB rail's cohort — counted here, owned there."*

**Rail 2 — the CLOB drain** (`clob_resolve_drain`, scheduled every 6h, `limit=300`).
Its own last run:

```
checked: 300,  written: 0,  written_ordinal: 0,
resolved_direct: 0,  resolved_name_match: 0,  resolved_ordinal: 0,
resolved_score_based: 70,  void: 218,  integrity_skipped: 12,
next_cursor: 31189834
```

**Checked 300, wrote 0.** Everything landed in `resolved_score_based` (a tier not in
`write_tiers`), `void`, or `integrity_skipped`. At 300 checks every 6h — 1,200/day —
against 25,264 in tennis alone, with a 0% write rate on that sample, this does not
converge. `next_cursor` is at ~31.2M while market ids run past 58.7M.

So "counted here, owned there" is only true if someone owns it there. **Rail 1 hands
off 9,748 markets per run to a rail moving at 1,200 checks/day that wrote nothing on
its last pass.**

### And nothing is allowed to notice

Both tasks report `health: healthy`, `failures_24h: 0`. Both carry:

```
last_verdict: "unverified"
last_verdict_reason: "not_enforced(unknown:no_terminal_fields)"
```

The verdict rail — `app/utils/task_verdict.py`, whose stated purpose is that *"it
returned" is not "it worked"* — **is not enforced on either task.** A rail that writes
nothing is therefore indistinguishable from a rail with nothing to do.

This is gotcha #53's named specimen recurring on a different rail: the Kalshi trade
backfill recorded *"500 fetched, 500 empty, 0 created"* as a SUCCESS every 6h for ten
weeks while #683 sat open as a P0. `written: 0` and `unsupported_lookup: 9748` are the
same sentence in different words, and they are being logged right now, every six hours,
under a green health field.

**Making these two tasks fail their verdict on a zero-yield pass is the cheapest fix in
this document, and it is the one that stops the next ten weeks.**

---

## 4. Registered predictions (ruling 050)

Ruling 050 exists as a file — see the premise correction below. Graded from here.

| ID | Prediction | Refuted by |
|---|---|---|
| **P-7** | Applying the **#1109/#1888 ITF repair alone**, with no other apply in the same deploy, moves **#1896's n-weighted MCE from 18.85pp to 17.20pp ± 0.40** and its n from 137,232 to **151,108 ± 400**. | A move of the wrong SIGN, or |Δ| outside 1.25–2.05pp. Either means the arriving population is not the one measured here. |
| **P-8** | **P-1 as written will read REFUTED on #1896 if the ITF repair ships in the same wave**, for a reason that has nothing to do with #1852/#1868/#1870. Net of −1.65pp, P-1's own claim (<1.0pp from the three attended repairs) still holds. | #1896 moving ≥1.0pp *after* netting out the ITF migration — that would mean an attended repair really did reach a Polymarket-dominated cohort. |
| **P-9** | **Re-running the sentinel on the fixed instrument closes #1896 and #1144 as EXPLAINED and leaves #1895, #1142, #1143, #1145 filed.** Capture cells #1897, #1899, #1900 downgrade REAL→WATCH; #1898 (`basketball_wnba`, in-season, not in `_SEASON_LEAGUE_SLUG`) stays REAL. | Any other cell changing state, or #1898 downgrading — the latter would mean the season map silenced a league it has no bands for. |
| **P-10** | **Enforcing the task verdict on `clob_resolve_drain` and `polymarket_winners` turns both RED within 24h** without any change to what they do. | Either staying green — which would mean the zero-yield passes are not representative and the sampled runs above were unlucky. |

**Standing caveat:** Gate 0 is undischargeable (§0), so every one of these must be
graded DB-direct. A post-apply read off `/api/calibration` is STALE-INSTRUMENT and
grades nothing.

---

## 5. Premise correction, banked

CAL-P063's successor-note 4 — *"RULING 050 DOES NOT EXIST AS A FILE. `docs/rulings/`
and the index both stop at 047"* — is **WRONG**, and CAL-P061's identical claim with
it. Both were checked against the stack base rather than against `origin/master`.

Measured this window at `origin/master` = `160a7cdb`:

```
$ git ls-tree --name-only origin/master docs/rulings/ | wc -l
68                                    # 67 rulings + README
$ git ls-tree --name-only origin/master docs/rulings/ | grep 050
docs/rulings/050-a-control-that-cannot-fail-is-not-a-control.md
```

Rulings run to **071**. Nothing is owed by Fable on this front, and the two "rulings
stop at 047" claims are retracted.

**BANKED RULE: premise checks run against `origin/master`, always.** This is the second
stale-base ruling-count finding, and the shape is general — a program lane sits on a
stack whose base can be many merges behind, so *any* "X does not exist" claim taken
from the working tree is a claim about the lane's base, not about the repo.

---

## 6. Declared NOT-RUN (never reported as zero — gotcha #53)

| Measurement | Status |
|---|---|
| Gate 0 forced recompute | **CANNOT RUN** — 88 consecutive producer failures (§0) |
| Sentinel backtest re-emission via the live endpoint | **NOT-RUN** — production runs the unfixed code; §2's re-emission is the fixed classifier applied to DB-direct counts instead |
| Venue-level confirmation that the 25,264 have winners at Polymarket | **NOT-RUN** — vintage proves them *addressable* (100% inside retention), not *answered*. A bounded sample probe is the next step. |
| #1145's +41.5pp over-resolution mechanism | **NOT-RUN** — item 4, staged behind item 3 by directive. Its union is measured (17.0%, n=5,272). |
| `#1895`/`#1145` resolution_source × is_winner censuses | still NOT-RUN from CAL-P063 |

---

## 7. What this queue deliberately did not do

* **No market data written.** Every apply stays staged.
* **The fifth instrument defect (§2) is filed, not fixed.** Fable scoped four; adding a
  fifth behaviour change would put more merge risk in front of the applies.
* **No repair built for the 25,264.** The census says it is fixable and names the two
  rails; the fix is a queue of its own, and it is a WRITER, so it must be declared.
