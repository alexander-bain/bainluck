# CAL-P124 — `polymarket/basketball` (rank 11): UNMEASURED, and the rail is why

**Verdict: NO RULE DESIGNED, and this time the blocker is the instrument rather than the cell.**
The exact rail — the producer's own CTE chain — reaches only **8,426 of the cell's 13,135 published
rows (−35.85%)**. That is six times the worst shortfall this rail has ever recorded and it is not a
sampling wobble: the mechanism is named, measured, and it predicts the shortfall on four cells out
of four.

A rule benched on 64% of a cell, where the missing 36% is removed by a mechanism that also
**re-assigns markets between the very classes a rule would name**, is a rule designed on a
different population. CAL-P112 declared `polymarket/tech` UNMEASURED for less than this.

**Nothing about this cell's error is disproved here.** The cell may well admit a rule. It cannot be
*shown* to, on this rail, today.

---

## 1. The three cheap checks, and the one that failed

| | n | ECE | gap |
|---|--:|--:|--:|
| exact replica (producer's own chain) | 8,426 | 4.14 | +3.51 |
| published payload | 13,135 | 4.24 | +2.96 |
| **delta** | **−4,709 (−35.85%)** | **−0.10** | **+0.55** |

Curve `q268`, generated `2026-08-29T00:36:47Z`.

**Lesson 3 bit, and the amendment written last session is what made it visible.** CAL-P123 amended
the standing "Polymarket is 5–6% short" budget to *"measure it per cell; the shortfall is a
property of particular CELLS, not of the source."* That amendment is now paid for twice over —
cricket was **−0.18%** and basketball is **−35.85%**, on the same rail, same source, same week.

`--by age` returned **100% `z_no_snapshot`** — the dimension is dead on this cell and named nothing.

---

## 2. `--edge-check` said "5 rows", and it was answering a different question

```
exact replica    n = 8,426     (chunk width 1,000,000)
edge check       n = 8,421     (chunk width   500,000)
                              ⚠️  DIFFERENT — chunking is affecting virtual_market grouping
```

The instrument flagged the warning **and understated the effect by three orders of magnitude.**
It is not broken. `--edge-check` is a **marginal** test — it moves the chunk width and asks whether
the answer moves — and marginal sensitivity is near zero when a cluster's members span 31,000,000
ids, because 1,000,000 and 500,000 shatter that cluster equally thoroughly. Add the rail's
`_split()` recursion (a chunk that times out is halved until it fits), and the *effective* partition
is data-dependent rather than width-dependent, so the two runs are not as independent as the flag
implies.

**Record this as a standing limitation of `--edge-check`, not as a bug:** a 5-row disagreement is
evidence about the DERIVATIVE, and it is compatible with a 4,709-row error in the level.

---

## 3. The mechanism, in the producer's own words

`precompute_calibration.py::_virtual_market_ctes` documents the hazard exactly, because the producer
had to solve it to chunk its own build:

> ... an event with 4 eligible markets where one sits in a >=3 group has three markets in
> `e:<event_id>` and one in `g:<group_id>`. Chunk by virtual question and re-derive, and the `e:`
> chunk now sees only 3 of the event's 4 markets... and **a chunk holding fewer than 3 would see the
> event collapse below the gate entirely, silently re-assigning every one of its markets to `m:`** —
> a different question identity, a different representative, a different bucket.

A market re-assigned to `m:` is its own virtual question. It takes the non-multi `rn = 1` branch and
publishes **one** row where the grouped market published many. So a shattered cluster does not
corrupt rows — **it deletes them.**

The producer's fix is a **frozen VM roster**: derive the assignment once over the whole population
(`_futures_generation_sql`), then inject it per chunk so each chunk is a *replay* of the global
derivation rather than a re-derivation over a subset. `calibration_cell_exact.py` does not do this.
It re-derives `virtual_market` inside every id-range chunk, which its own docstring discloses as
"the one approximation, measured rather than asserted" — the disclosure is honest, the measurement
(`--edge-check`) is the one that cannot see this case.

### Why the loss is invisible in a bucket-shape check

| bucket | payload n | replica n | delta | payload win% | replica win% |
|---|--:|--:|--:|--:|--:|
| 0 | 1,941 | 1,546 | −20.4% | 3.6% | 3.3% |
| 1 | 704 | 461 | −34.5% | 15.2% | 13.7% |
| 2 | 695 | 459 | −34.0% | 22.2% | 22.4% |
| 3 | 1,271 | 750 | −41.0% | 38.1% | 36.1% |
| 4 | 2,772 | 1,656 | −40.3% | 37.1% | 36.1% |
| 5 | 3,267 | 1,937 | −40.7% | 48.7% | 47.9% |
| 6 | 636 | 427 | −32.9% | 65.6% | 63.7% |
| 7 | 490 | 329 | −32.9% | 75.9% | 76.3% |
| 8 | 493 | 306 | −37.9% | 75.5% | 75.5% |
| 9 | 866 | 555 | −35.9% | 93.8% | 94.2% |

**Near-uniform loss, matching win rates in every bucket.** The rail loses whole markets, not a
price-selected slice — which is why the pooled ECE barely moved and why nothing in the fold's own
output looks wrong. `--by price_moved` says the same thing: replica 67.8% moved vs payload 69.97%.

---

## 4. The predictor — eight seconds, no fold required

New instrument `backend/scripts/calibration_cluster_spread.py` (31 guards,
`tests/test_calibration_cluster_spread_p124.py`). It measures, per cell, the share of clustered
markets living in a cluster whose **market-id spread exceeds one chunk width** — i.e. the share the
fold's chunking is guaranteed to shatter.

| cell | % markets in wide clusters | measured reproduction shortfall |
|---|--:|--:|
| `polymarket/cricket` | 7.0% | −0.18% |
| `polymarket/soccer` | 14.2% | −5.06% |
| `polymarket/baseball` | 32.2% | −5.70% |
| **`polymarket/basketball`** | **93.1%** | **−35.85%** |

**Monotone on four of four.** The "5–6% Polymarket budget" was never a source constant; it was two
cells that happen to sit at 14.2% and 32.2% on this axis. `polymarket/basketball` has a **maximum
cluster spread of 31.0M ids against a 1M chunk**, and 19,824 of its 21,288 clustered markets sit in
a cluster the chunker cannot keep whole.

`n = 4` is a correlation, not a calibration, and `risk_band()` deliberately returns a qualitative
band rather than an interpolated percentage — an n=4 curve that prints "predicted −18.4%" will be
believed.

### Board-wide pre-flight (run this BEFORE trusting any fold)

| cell | group_id | event_id | band |
|---|--:|--:|---|
| `polymarket/golf` | 1.6% | — | LOW |
| `polymarket/economics` | 11.2% | — | MODERATE |
| `polymarket/soccer` | 14.2% | — | MODERATE |
| `polymarket/esports` | 18.6% | 12.3% | MODERATE |
| `polymarket/entertainment` | 26.3% | — | MODERATE |
| `polymarket/tech` | 26.6% | — | MODERATE |
| `polymarket/baseball` | 32.2% | — | MODERATE |
| `polymarket/politics` | 39.1% | — | HIGH |
| **`polymarket/basketball`** | **93.1%** | **96.8%** | **SEVERE** |
| **`polymarket/hockey`** | **93.0%** | **98.5%** | **SEVERE** |
| `kalshi/football` | — | 31.8% | MODERATE |
| `kalshi/{economics,crypto,entertainment,tech,golf}` | — | — | NO_CLUSTERS |

🔴 **`polymarket/hockey` is the handoff's own "next cell with no design" (rank 15/16, 9,945
excess-outcomes) and it is SEVERE.** Two of the three cells the conveyor was pointed at cannot be
measured on the current rail. **Do not spend a session folding it before the rail is fixed.**

🟢 **Kalshi is essentially cluster-free on `group_id`.** Every Kalshi cell measured returns
NO_CLUSTERS, which is the structural reason this rail has reproduced Kalshi cells well and is why
the eleven Kalshi-cell folds on this board are not in question.

---

## 5. What this does and does NOT do to the five banked designs

**It does not invalidate any of them.** Two things bound the exposure, and both are measured:

1. **Pooled ECE is robust to this shortfall.** On the worst cell on the board, losing 35.85% of rows
   moved the pooled ECE by **−0.10 pp** and the gap by +0.55. The chunker deletes rows nearly
   uniformly in price, so the headline-shaped number survives even when coverage does not.
2. **Class-level numbers are not robust**, and that is what a rule is made of. A shattered cluster's
   markets are re-assigned to `m:`, which changes their `shape`, `market_type` and `pairtype`
   classification — the fold re-partitions the very axes a rule names.

So the exposure is per-design, and it is only material where a rule's margin is thin:

| banked design | cell | band | margin | exposure |
|---|---|---|--:|---|
| rank 1 — K′ | `polymarket/baseball` | MODERATE (32.2%) | **2.71 vs 3.0 = 0.29 pp** | 🟠 thinnest on the board; the pooled drift measured on basketball alone was 0.10 pp, a third of this margin |
| rank 3 — E | `polymarket/esports` | MODERATE (18.6%) | 3.29, over bar | 🟢 does not pass either way |
| rank 2 — E+E2+E3 | `kalshi/economics` | NO_CLUSTERS | 2.61 vs 3.0 | 🟢 unaffected — Kalshi has no clusters |
| rank 6 — RULE C | `kalshi/crypto` | NO_CLUSTERS | deletes the cell | 🟢 unaffected |
| rank 17 — T | `kalshi/tech` | NO_CLUSTERS | 3.80 | 🟢 unaffected |

**Only rank 1 carries real exposure**, and it is the design queued to land FIRST when the freeze
lifts. The recommendation is not to un-bank it: it is to **re-bench K′ on the repaired rail before
it lands**, which the rail rebuild makes cheap, and to state the 0.29 pp margin in its cert.

---

## 6. What is owed

**15-CAL (NEW, Alex — instrument, not a curve decision, so it may not need him at all):**
`calibration_cell_exact.py` cannot measure a Polymarket cell whose groups are id-scattered, and two
board cells (`basketball`, `hockey`, 26,232 excess-outcomes between them) are behind that blocker.
The fix is a **whole-virtual-market chunker** that replays the producer's frozen roster instead of
re-deriving `virtual_market` per id range. Both halves are probed and viable (§7). This is
new-file, read-only tooling and rides the existing ship; it is a build-lane job, not a measurement.

**Amendment to lesson 3 (supersedes CAL-P123's):** do not measure the shortfall per cell by running
the fold and reading the SELF-CHECK. **Predict it first with `calibration_cluster_spread.py`** — it
costs eight seconds against the fold's four minutes, and on a SEVERE cell it tells you not to spend
the four minutes at all.

**Amendment to `--edge-check`:** it is a marginal test and cannot see a uniformly-shattered cell.
A "DIFFERENT" flag with a tiny delta is **not** an all-clear. Read it alongside the spread band.

---

## 7. The rail rebuild — designed and probed, NOT built

Staged as the next conveyor queue. Both risky halves were probed live this session so the next
queue does not re-discover them:

**Stage A (roster) — VIABLE, measured.** The global generation cannot be driven from db-query: the
unscoped chain blew the Heroku router timeout (`Application Error` at 103s). The working variant
scopes the CTEs to the cell — which leaves `group_sizes`/`event_sizes` correct *within* the cell,
because both are already `GROUP BY ..., source` — and chunks the **read** by `abs(hashtext(vm_id)) %
N`, a filter on the OUTER select that does not touch `market_info`. Measured on basketball:
**22,645+ roster rows in 97s at N=24**, with 15 of 24 chunks truncating at the 1,000-row cap, so
ship it at **N=128 with adaptive split on the `truncated` flag** (never on a row-count heuristic —
gotcha #53).

**Stage B (replay) — designed, not probed.** Per unit, call
`_calibration_population_ctes(frozen_vm_roster=True, market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA)`
and inline the three roster arrays as literals (db-query is a text endpoint and takes no binds).
Chunk with the producer's **own** planner, `app.utils.calibration_staged_futures.plan_units`, which
guarantees a `vm_id` is never split. Budget ~15 KB of SQL per 400-market unit against the rail's
`MAX_SQL_CHARS = 60_000`.

**The one residual, and it must be measured rather than asserted:** scoping Stage A to a category
mis-sizes any cluster that spans categories. Measure that directly (count clusters in the cell whose
markets carry more than one `llm_sport_category`) and state the bound. Do not assume it is zero.

---

## 8. Reproduce

```bash
source ~/.claude/.env
python3 backend/scripts/calibration_cluster_spread.py --source polymarket --category basketball
python3 backend/scripts/calibration_cell_exact.py --source polymarket --category basketball \
        --by none --edge-check
python3 backend/scripts/calibration_cell_exact.py --source polymarket --category basketball \
        --by price_moved --out artifacts/cal-p124/fold-price_moved.json
```

The spread run is ~8 s. Each fold is ~225 s; `--edge-check` doubles it. Guards:
`backend/tests/test_calibration_cluster_spread_p124.py`, 31 tests.
