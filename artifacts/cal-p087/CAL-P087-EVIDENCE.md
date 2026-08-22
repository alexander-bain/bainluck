# CAL-P087 — evidence index

Fable directive 2026-08-22 (Alex-pasted, Alex-reviewed), executed read-only during the drain.
**No file on `program/calibration-53` / `-82` / `-83` / `-84` was touched.** Everything in this
queue is a new file on `program/calibration-85`, which stacks on `-84`.

| artifact | what it pins |
|---|---|
| `ARTIFACT-CAL-P087-GATE0-SPLIT-PRE-READ.json` | Gate 0's colour under CAL-P086B's split, over today's real inputs |
| `ARTIFACT-CAL-P087-APPLY-BEFORES-PINNED.json` | the apply's two BEFORE pairs, frozen with timestamps |
| `ARTIFACT-CAL-P087-2098-CROSS-SUPPRESSION.json` | #2098's "not measured" turned into a number |

Regenerate any of them:

```bash
source ~/.claude/.env
cd backend
python3 scripts/gate0_split_pre_read.py            --out ../artifacts/cal-p087/ARTIFACT-CAL-P087-GATE0-SPLIT-PRE-READ.json
python3 scripts/pin_apply_befores.py               --out ../artifacts/cal-p087/ARTIFACT-CAL-P087-APPLY-BEFORES-PINNED.json
python3 scripts/measure_2098_mode_price_collision.py --out ../artifacts/cal-p087/ARTIFACT-CAL-P087-2098-CROSS-SUPPRESSION.json
python3 scripts/measure_2098_mode_price_collision.py --chain-plan   # plan-only, does not execute
```

---

## 1. Gate 0 is **RED** under the new rule — and **GREEN** under the old one, over the same inputs

This is the question the directive wanted answered before the drain lands it, and it has a
clean answer rather than a conditional.

**Inputs, both real and both from today.** The served payload
(`generated_at 2026-08-22T11:38:22Z`, `population_version q268`) and the twin's own last run
(`artifact_generated_at 2026-08-21T19:24:23Z`). That run is a failure:

```
  fold_duration_s   = 1351.95     against timeout_ms = 1,350,000
  db_rows           = 0
  db_cells          = 0
  terminal          = failed
  payload_error     = published_read_failed: redis call did not complete
```

Two things worth naming. The fold **still does not fit**, now at the raised 1,350 s ceiling —
#2076 is not one ceiling away from done. And there is a **second, independent blocker** that has
nothing to do with the fold: the worker could not read the published payload at all
(`redis call did not complete`). Even a fold that finished would have had nothing to compare
against on that run.

**The verdict, over those inputs, from the split `reconcile` on `-84`:**

| rule | verdict |
|---|---|
| **new (CAL-P086B split)** | **`disagrees`** |
| old (pre-split) | `agrees` |

```
  tolerance_pp                 = 100.0        (staged measured, 128/128 drifted)
  compared                     = 0
  outside                      = 0            <- why the OLD rule says agrees
  published_only               = 1,482
  published_only_in_scope      = 608          <- why the NEW rule says disagrees
  published_only_out_of_scope  = 874
  cells_db                     = 0
  cells_published              = 286
```

So the split does exactly what CAL-P086B claimed and the colour change is not hypothetical: **a
fold that produced nothing used to read as agreement.** With `units_drifted 128/128` the bound is
pinned at 100 pp, `outside` can never populate, and the old rule had no other way to fail. Gate 5
could have been "met" by a fold that timed out.

**The part that is a NEW constraint on the apply, not just a repair.**
`published_only_in_scope` is **not tolerance-scaled**. Every other way Gate 0 can go red passes
through the drift bound, which the sawtooth in §2 of the apply spec is all about timing around.
This one does not: a single in-scope published bucket with no twin row forces `disagrees` at any
bound. Today's payload carries **608 in-scope bucket keys across 83 in-scope cells**, and **159 of
those keys have `n <= 2`** — one row from vanishing between the payload's build and the fold's
read. Gate 5 is therefore not only "run the fold inside the trough"; it is "run the fold against a
payload whose in-scope cell set the DB still produces". That is a stricter ask than the trough
timing, and it should be costed before the attended window, not during it.

**The scope census, re-measured today** (CAL-P086B measured 203/285 yesterday):

| | value |
|---|---|
| cells in scope (kalshi / polymarket / datagolf) | 83 |
| cells out of scope (the four `odds_api*` sources) | 203 |
| **out-of-scope share** | **70.98%** (203 of 286) |
| in-scope bucket keys | 608 |
| in-scope bucket keys with `n <= 2` | 159 |

**And one thing found on the way, filed as #2111.** `reconcile` keys without `price_moved` while
the payload carries it as a dimension, so **455 of 1,937 payload rows are overwritten** rather
than merged — including their `n`. Its scope census therefore counts **526,462** published
outcomes where the payload says **869,978**, a 39.5% shortfall, and every percentage in that block
is over the short denominator. It is not producing a wrong verdict today only because the fold has
never produced a row.

---

## 2. #2098 — **the collision fires: 35 rows on 2 vm_ids**

Whole `event_id` domain swept, **0 unswept ranges**, 559 chunks, 1,788 s. Full write-up posted to
the issue; artifact `ARTIFACT-CAL-P087-2098-CROSS-SUPPRESSION.json`.

| | |
|---|---|
| shared `e:` vm_ids **after group precedence** | **314** (not 1,271 — see below) |
| …carrying a source-blind mode price | 28 |
| in-band rows suppressed by it | 127 |
| **…suppressed by a mode price their own source did not earn** | **35** |
| distinct vm_ids affected | 2 |

The mechanism, on `e:14887630`: polymarket has `eligible 4` and 4 legs at `p = 0.01`, so it clears
`GREATEST(eligible*0.5, 2) = 2` and emits a mode price. Kalshi has `eligible 120` and 23 legs at
0.01, threshold 60 — it could never form one. `deduped` joins on `(vm_id, mode_price)` with no
source predicate, so **a 4-leg Polymarket market deletes 23 Kalshi legs from the published curve**.
`0.01` is inside the band, so the band does not already remove them. `e:14942135` is the same
shape, 12 rows. The asymmetry is what makes it bite: the threshold's floor of `2` lets a *tiny*
field mint a mode price that then suppresses a *large* one.

**A correction to the issue's own number.** 1,271 counts `event_sizes` alone, but
`virtual_market`'s `CASE` tries the **group arm first** — a market whose group has >= 3 members
becomes `'g:'||group_id` and never reaches the `'e:'` arm. Polymarket groups its event markets, so
most polymarket sides leave the `e:` pool. Reachable shared `e:` vm_ids: **314**.

**It is an UPPER BOUND**, by construction (omits `is_liquid`, `is_field_incomplete`,
`is_poly_placeholder`, `has_winner >= 1`; omitting an exclusion can only add candidates). 35 rows
against ~870K published outcomes is 0.004% — real, reproducible, named, and small. What it settles
is that a source-chunked fold is **not row-identical** to the whole fold, so #2076's option 2/3 is
now closed on correctness as well as on cost. What it does not settle is whether today's unchunked
behaviour is the *right* one; that is a separate call and this queue does not make it.

The faithful instrument — two runs of the real chain differing only in three substitutions
(`mode_prices` gains `source`; `deduped`'s join gains `AND mp.source = ro.source`) — **cannot be
run**, and that is itself measured:

```
  unscoped fold                       total_cost = 12,719,996
  scoped to the 1,288 shared events   total_cost = 10,235,054   (0.80x)
  same, with source-scoped mode       total_cost = 10,234,964   (0.80x)
```

Scoping the base scan to the only events that can collide removes **20%** of the planner's cost;
`ranked_outcomes` still estimates 1,077,901 rows. So the scoped fold inherits #2076's wall against
a 25 s ceiling on the only read rail the freeze allows. Planner cost is not runtime (CAL-P085
measured this fold's model understating by >= 2.35x), so the usable signal is the **ratio**, and
the ratio says event-scoping is not the lever.

What ran instead is a direct, chunked **upper bound**, partitioned by `event_id` range — exact for
this question, because an `e:` vm_id is `'e:'||event_id` and every row that can collide on it
lives in one chunk. Group sizes are still resolved globally inside each chunk, so a `g:` market is
never mistaken for an `e:` one. It omits the expensive per-outcome exclusions (`is_liquid`,
`is_field_incomplete`, `is_poly_placeholder`, `clean_vms`'s `has_winner >= 1`), and omitting an
exclusion can only ADD candidates — hence a bound, in the safe direction.

---

## 3. The apply's befores, frozen

`ARTIFACT-CAL-P087-APPLY-BEFORES-PINNED.json`, pinned **2026-08-22T13:22Z**.

| | before | after | kind |
|---|---|---|---|
| **Full population** | **3.7226 pp** (n = 372,293) | **~1.7422 pp** | **re-anchored**, not re-measured |
| **Rendered cohort** | **1.3615 pp** (`cohortN` 526,138) | expected to move little | **re-measured live** |

**The rendered number in the apply spec's §5b table has already moved.** §5b records 1.3509 pp at
`cohortN 525,601` (CAL-P086B, 2026-08-21); the same code path today gives **1.3615 pp at 526,138**,
and the payload's `mce_opening_price` reads **1.66** where §5b recorded 1.61. Nothing is wrong —
~19 hours of a live curve is exactly the drift that makes a remembered before useless, which is
why the directive asked for a frozen one. Re-run `pin_apply_befores.py` immediately before the
apply so the closing report's before is hours old rather than days.

The full-population pair is **re-anchored, not re-measured**, and the artifact says so in the
record: CAL-P085's whole-market fold ran 411.15 s over the population #2076 has never got through
in 1,350 s. It is pinned to `artifacts/cal-p085/price-provenance-whole-market.json` at commit
`b29edb44`, with 49/49 cells measured and 0 unmeasured, so the closing report quotes a file rather
than a memory.

The rendered metric is ported field-for-field from `frontend/lib/calibrationParity.ts` +
`calibrationMath.ts`, **including `aggregateBuckets`'s rounding of `error` to one decimal in pp**
before ECE weights it — computing ECE from unrounded errors gives a different number than the page
renders, and the before must be the rendered one. The port is validated by reproduction, not
inspection: 1.3615 sits between CAL-P086B's 1.3509 and `C-CALPAGE-SKEPTIC-1`'s 1.37, at a
`cohortN` 537 above theirs.

---

## 4. `MINIMUM_BANKED_RULINGS` — the resolution is at the conflict site

Counted on the trees, not read off a handoff:

```
  origin/master            docs/rulings/NNN-*.md = 113
  program/calibration-53   = 116   (constant raised to 116)
  program/calibration-84   = 114   (constant raised to 114)
  both land                = 113 + 3 + 1 = 117
```

`-84`'s `backend/tests/test_product_brain_integrity.py` carries the DECLARED COLLISION block
immediately above the constant, naming 117 as the merged value and neither branch's own. `-53`
does not carry it. Since the two sides differ on the comment as well as the value, `-84`'s
declaration appears inside the conflict hunk whichever order they merge in — which is where the
Integrator will be standing.
