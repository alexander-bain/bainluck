# CAL-P1118 — #5401 sized on the PUBLISHED population, and what that refutes

Measured 2026-09-11 22:35Z–23:10Z (Fri 3:35–4:10PM PT) by calibration/1118.
Instrument: `backend/scripts/calibration_fold_opening_source.py`, which calls
`_calibration_population_ctes()` from the producer, so the population is the
curve's own and cannot drift from it.

Raw JSON beside this file: `opening-source-kalshi-golf.json`,
`opening-source-kalshi-entertainment.json`.

## The fold reconciles to the served cells, so the numbers below are quotable

| cell | implied | won | fold ratio | served cell |
|---|---:|---:|---:|---:|
| `kalshi/golf` | 4,455.6 | 3,395 | **0.762** | 0.762 |
| `kalshi/entertainment` | 1,062.6 | 880 | **0.828** | 0.831 |

`kalshi/golf` kept `n` = 22,141 against the published waterfall's 22,074 (+0.3%),
which is the documented `fm.id`-chunking approximation, not a different population.

## kalshi/golf, published (kept) rows only

| basis | band | n | won | implied | realised | mean price |
|---|---|---:|---:|---:|---:|---:|
| *(untagged)* | ≥0.80 | 418 | 101 | 388.2 | **24.2%** | 0.929 |
| *(untagged)* | <0.80 | 12,513 | 1,422 | 2,263.6 | **11.4%** | 0.181 |
| `bid_ask_midpoint` | ≥0.80 | 289 | 273 | 272.3 | 94.5% | 0.942 |
| `bid_ask_midpoint` | <0.80 | 7,399 | 1,341 | 1,260.9 | 18.1% | 0.170 |
| `first_snapshot` | ≥0.80 | 6 | 6 | 5.3 | 100.0% | 0.887 |
| `first_snapshot` | <0.80 | 1,516 | 252 | 265.3 | 16.6% | 0.175 |

Deficit (implied − won) by cohort: **untagged +1,128.8**, `bid_ask_midpoint`
−80.8 (mildly UNDER-priced), `first_snapshot` +12.6. Net **1,060.6**.

## kalshi/entertainment, published (kept) rows only

| basis | band | n | won | implied | realised |
|---|---|---:|---:|---:|---:|
| *(untagged)* | ≥0.80 | 368 | 203 | 352.8 | **55.2%** |
| *(untagged)* | <0.80 | 2,341 | 383 | 381.2 | 16.4% |
| `bid_ask_midpoint` | ≥0.80 | 54 | 51 | 49.8 | 94.4% |
| `bid_ask_midpoint` | <0.80 | 335 | 69 | 62.7 | 20.6% |
| `first_snapshot` | ≥0.80 | 56 | 49 | 52.2 | 87.5% |
| `first_snapshot` | <0.80 | 693 | 125 | 163.9 | 18.0% |

Net deficit **182.6**, of which the untagged ≥0.80 cohort alone is **149.8 (82%)**.

## F1 — the untagged cohort IS the miss, in both cells

A leg carrying a basis is priced almost exactly right in both bands and in both
cells. A leg carrying none is not. In golf the untagged cohort's 1,128.8 is
*more* than the cell's whole net miss, because the tagged cohort offsets it.

## F2 — `first_snapshot` is already gone, so #4745's predicate is not the lever

Six legs in the published golf ≥0.80 band; 56 in entertainment. The existing
filters remove the rest. Extending `is_lone_ask_on_empty_book` — CAL-P1118's
preferred repair (a) and #5401's — would therefore recover **almost nothing**.

## F3 — the band-keyed cut is wrong for golf, and the two cells are NOT one repair

#5401's option (b) cuts at ≥0.80. In golf that reaches 287.2 of 1,060.6 = **27%**;
**79% of golf's deficit sits BELOW 0.80** (12,513 legs at 0.181 realising 0.114).
In entertainment the opposite holds — 82% is ≥0.80, and the untagged low band is
near-perfect (16.4% vs 16.3% implied).

This refutes CAL-P1118 ARM B's "entertainment is probably the same repair".
Same *cohort*, different *shape*; one cut cannot serve both.

## F4 — "untagged = no book" is refuted; the book shape does not discriminate

Raw kalshi/golf resolved legs, `opening_source` × the earliest snapshot's book:

| basis | earliest book | legs | mean open | realised |
|---|---|---:|---:|---:|
| `bid_ask_midpoint` | **no book recorded** | 3,041 | 0.324 | **37.7%** |
| `bid_ask_midpoint` | two-sided | 4,365 | 0.203 | 21.2% |
| `bid_ask_midpoint` | zero bid | 2,476 | 0.050 | 5.0% |
| *(untagged)* | **no book recorded** | 9,011 | 0.617 | **7.2%** |
| *(untagged)* | two-sided | 7,543 | 0.313 | **22.4%** |
| *(untagged)* | zero bid | 6,471 | 0.234 | 5.1% |

A tagged leg with **no book at all** is well calibrated (37.7% at 0.324). An
untagged leg **with a two-sided book** is not (22.4% at 0.313). So a predicate
keyed on the recorded book — the natural sibling of `is_lone_ask_on_empty_book`
— cannot separate these rows. Whatever the tag is standing in for, it is not the
book.

## F5 — mechanism: the basis is missing because the INSERT arm never wrote it

`app/tasks/kalshi.py`: the upsert's CONFLICT arm sets `opening_source`
(`update_set`, under `if has_real_trading`), and the INSERT arm's `.values()`
did not name the column at all. A leg whose opening was captured the first time
the poller saw it — the common case in a 150-runner field — was born with a real
opening and no provenance. Same defect as CAL-P1004R, same `pg_insert`, one
column over. **Fixed on this branch, with a guard.**

## F6 — the curve's liquidity bar is weaker than the writer's own

`KALSHI_LIQUIDITY_EXISTS` admits a leg that ever showed `yes_bid > 0` OR
`last_price > 0`. The poller will only WRITE an opening when
`yes_bid > 0 AND (yes_ask − yes_bid) < 0.50`. So the curve publishes openings
the writer itself would have refused. Measured, golf resolved legs with **no**
snapshot meeting the writer's own bar: 2,048 untagged legs, mean opening 0.296,
realised **3.2%**.

Those 2,048 cannot have come from today's poller path (its own guard implies at
least one qualifying snapshot), so they are historical or another writer's rows.
**This gap — not the book shape, not the band — is the honest discriminator, and
it is nameable as a rule rather than as a provenance artifact.**

### F6b — and it is the better cut, measured

Same instrument, same published `kalshi/golf` cell, splitting on whether the leg
has any snapshot meeting the WRITER's own bar instead of on the provenance tag:

| cohort | band | n | won | implied | realised |
|---|---|---:|---:|---:|---:|
| below writer bar | ≥0.80 | 304 | 9 | 285.4 | **3.0%** |
| below writer bar | <0.80 | 5,558 | 125 | 752.2 | **2.2%** |
| meets writer bar | ≥0.80 | 409 | 371 | 380.4 | 90.7% |
| meets writer bar | <0.80 | 15,871 | 2,890 | 3,037.9 | 18.2% |

(Totals reconcile: 22,142 legs, implied 4,455.9, won 3,395 — the same cell.)

| cut | population removed | deficit captured | cell after |
|---|---:|---:|---:|
| provenance (`opening_source` untagged) | **58.4%** | 1,128.8 (106%) | 1.038 — overshoots |
| **writer bar** | **26.5%** | **903.6 (85%)** | **0.954** |

The writer-bar rule removes **less than half as much population**, captures 85% of
the miss, and lands the cell at 0.954 against a board control of 0.982 — where the
provenance cut overshoots to 1.038. **This is the repair to build.** It still
exceeds the gate's ±5% band, so it still needs q270.

## F7 — BLOCKER: any curve-side exclusion here needs q270

The untagged cohort is 12,931 of 22,141 published `kalshi/golf` legs (**58.4%**).
Removing it is a deliberate methodology shrink, which the publish gate refuses as
`population_shrink` unless the population version is bumped — and a refusal
CLEARS THE CHECKPOINT, so every subsequent rebuild is binned for the same reason.
`q269 → q270` is currently **STOPPED** (Fable's condition spent; CAL-P1118 ARM E).

So #5401 cannot land its repair until q270 is released. That is a new cost on the
q270 stop and has been put to Fable.

## Shipped on this branch (neither moves the population)

1. `backend/app/tasks/kalshi.py` — the insert arm now records the basis.
2. `backend/tests/test_opening_source_named_5401.py` — guard; the class scan
   discovers its own population and pins the three venues still writing untagged
   openings (`polymarket.py`, `futures.py`, `datagolf.py`).
3. `backend/scripts/calibration_fold_opening_source.py` — the instrument.

## Traps paid for here

* **A `*_source` column can be an ARTIFACT of write-path bookkeeping.** Splitting
  a bad metric by provenance found the cohort in one query — but the tag's
  *meaning* was not what its name says, and two plausible readings ("no book",
  "never traded") were both refuted by measurement before the repair was written.
  Split by provenance to FIND the cohort; read the writer before keying a rule on it.
* **A class scan that reads one construction shape under-counts silently.** The
  first version of the guard read only `pg_insert(...).values()` and reported
  three untagged venues; `datagolf.py` writes openings through the ORM
  constructor. The tripwire caught it only because the population is discovered
  rather than typed.
