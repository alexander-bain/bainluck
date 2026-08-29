# CAL-P133 — the nested-ladder monotonicity instrument (CAL-P131-2), built and folded

**Published number at session start and end: 1.89 pp, FLAT** (nineteenth reading;
`q268` / `2026-08-29T00:36:47Z`, unmoved). Freeze gate at session start:
**3/24 clean, 21 misses, `NOT_MET`** — the freeze HOLDS.

## What this session did

Step 1 of the conveyor directive had no cell left to take (CAL-P132 folded the
last unworked one). So this session took **SUGGESTED ORDER item 1**: generalize
`app.utils.ladder_coherence` — which only knows the literal `O/U` token and a
fixed adjacency step of 1.0 — into a **monotonicity law over any nested ladder**.

Shipped, new files only, frozen file untouched:

| file | what |
|---|---|
| `backend/app/utils/ladder_monotonicity.py` | the law. Two rung grammars (threshold, `by <date>`), two sites (name, outcome), the family key, the violation list |
| `backend/tests/test_ladder_monotonicity.py` | **72 guards**, green |
| `backend/scripts/calibration_cell_exact.py` | `--by mono` registered as **rail dimension #18** (per-chunk, with `MONO_ROWS_SQL` + `mono_context` + `mono_dim`), plus `PER_CHUNK_CONTEXT` so the two per-chunk tables can no longer drift apart |
| `artifacts/cal-p133/ladder-monotonicity-census.py` | the producer of every number in the module docstring |

Sibling suites: `pytest -k calibration` → **2,609 passed**, unchanged
(the new file is not matched by `-k calibration`; it runs as its own 72).

## The law, and the three weakenings it carries vs the O/U rule

`P(above $255) >= P(above $260)`, `P(by June 5) <= P(by June 12)`. Containment,
so no model and no outcome is needed. Three differences from `ladder_coherence`,
each of which is a measurement and not a convenience — all three are in the
module docstring and each is pinned by a named guard:

1. **Adjacency is consecutive-in-sorted-order, not a fixed step.** Real ladders
   step irregularly (June 5, 12, 19, 26, 30, July 31; $1.0T … $172.5B).
2. **The law is NON-STRICT, so equality is not a violation.** O/U buys
   strictness from discrete totals and equality was its LARGEST condemned shape
   (250 of 631). Nothing licenses that here, so flat pairs are counted and
   reported (`flat_pairs`) and never condemned. **Anyone porting the O/U result
   here should expect to condemn less, and this is the reason — not a weaker search.**
3. **Direction is part of the family key.** Measured: 13 valuation families
   published a `(HIGH)` and a `(LOW)` leg whose names differ only inside the
   blanked span, so without direction in the key they merge and either sign
   manufactures violations across the whole merged family. This is the esports
   key-collapse failure of `ladder_coherence.read_ladders` in a new costume.

## Two parser defects the census found, both now guarded by name

* **`at least 2000 measles cases`** parsed the `m` of "measles" as a MEGA suffix,
  reading 2,000 as 2e9 *and* corrupting the family key to `<rung> easles cases`.
* **`...to the US government by April 30, 2026?`** matched `over` inside
  "g-**over**-nment" and bound it to the `30` of "April 30", inventing a
  threshold rung on a pure-date market.

Both were visible only because the ambiguity census **prints the families it
refuses** instead of dropping them silently (gotcha #53).

## The measured result — and the estimate it overturned

⚠️ **A convenience population gave the OPPOSITE answer and I nearly wrote it up.**
An offline ECE over *graded YES legs* (n=9,250 on economics, no eligibility
filter) read `drop` 7.60 vs `coherent` 8.42 — i.e. the rule condemning the
*better* arm. The exact rail, on the **published** population, inverts it. The
rail is the authority (lesson 1/9), and this is the cleanest instance of it the
lane has produced. Estimate and proof are kept in separate columns below
(lesson 10).

### PROOF — `polymarket/economics`, exact rail, `--by mono --holdout-at 32676761`

Self-check: exact replica n=12,959 ECE 3.92 vs payload n=12,882 ECE 3.9
(+0.60% rows). Cell bar **3.0**, cell excess 0.91, σ 2.07, established.

```
  class                    n   share     ECE      gap
  z_not_in_a_ladder    11972   92.4%    4.53    -0.15
  c_mono_coherent        511    3.9%    4.47    -0.71
  a_drop_reversed        476    3.7%   10.87    +4.63     <- 2.4x the arm it keeps

  HOLDOUT
    OLD   a_drop_reversed  118   18.24   |  c_mono_coherent  146   13.60
    NEW   a_drop_reversed  358    9.78   |  c_mono_coherent  365    5.93
```

**The separation reproduces in BOTH halves in sign** — condemned is worse in OLD
and in NEW — which is what makes it a finding rather than a fit. Two honest
caveats that must travel with it:

* **The kept arm is NOT clean.** OLD `c_mono_coherent` reads **13.60**. The rule
  separates a worse class from a bad one, not from a good one.
* **The two halves are not the same population** (lesson 14): `z_not_in_a_ladder`
  reads 3.44 OLD and 6.77 NEW.

### PROOF — `polymarket/tech`, exact rail, `--by mono --holdout-at 32127295`

**The mechanism does not reach the published curve here at all.**

```
  z_not_in_a_ladder     2740   99.6%    5.06
  a_drop_reversed          6    0.2%    41.5
  c_mono_coherent          4    0.1%    25.5
  b_ambiguous_kept         1    0.0%    86.0
```

The raw cell has **741 markets in a testable ladder**; the published population
has **11 rows**. Those ECEs are noise on single-digit n and must not be quoted.
🔴 **This is lesson 6 running the other way, and it is the transferable part:
a CELL census is not a PUBLISHED-POPULATION census, and a mechanism covering
25% of a cell's markets can cover 0.4% of its scored rows.** Check the published
n before designing against a raw-cell share.

## VERDICT: no design banked. Still five.

`mono` is **not** a compliance rule for `polymarket/economics`. Removing the
476-row condemned arm from a 12,959-row cell at 3.92 moves the cell to roughly
**3.66** (⚠️ ESTIMATE — ECE is a sum over buckets and does not decompose by arm;
the only proof would be a re-fold with the arm excluded). The bar is 3.0. It
does not get there, and on tech there is nothing to remove.

What it IS: a **leakage-free, holdout-stable, board-reusable dimension** that no
other instrument in this repo can express, which isolates a 476-row arm at 10.87
inside a cell publishing at 3.92 — and a **TRUTH-pillar product defect** (below)
that is worth more than the calibration delta.

## The product finding — we publish ladders that contradict themselves

Independent of any calibration verdict. Counted by the census:

| cell | multi-rung families | condemned | impossible published pairs |
|---|---|---|---|
| `polymarket/economics` | 1,597 | **747 (46.8%)** | **1,210** |
| `polymarket/tech` | 191 | 65 (34.0%) | 94 |

Plus the **outcome site** — a whole ladder inside ONE market's outcome list,
7 violating markets on tech. The worst is not close:

```
22737595  "Next Google Gemini Model: Arena Debut?"
  >=1460 0.780   >=1470 0.795   >=1480 0.800   >=1490 0.390
  >=1500 0.455   >=1510 0.030   >=1520 0.265
```

`P(>=1520) = 0.265` against `P(>=1510) = 0.030`: a strictly harder event priced
**nearly 9x higher**, in the same market, on the same screen. And on economics
the shape is the one the directive named — "Will Netflix (NFLX) finish week of
June 8 above \$X?" carries 6 reversals across 13 rungs.

Routed to Alex as `alex-inbox/calibration-905`. This is a LOOK, not a DECIDE.

## Re-running

```bash
# census (offline, needs a chunked outcome-row dump; see the script docstring)
python3 artifacts/cal-p133/ladder-monotonicity-census.py <rows.json> <label> [out.json]

# the rail (production; never run a fold and a census concurrently)
python3 backend/scripts/calibration_cell_exact.py \
    --source polymarket --category economics --by mono --holdout-at 32676761
```

⚠️ The mono pre-pass pulls **every market in the cell with a YES leg** and has
**no name filter**, deliberately: a Postgres rendering of the rung grammar would
be a second site for a predicate whose authority is the Python, which
`ladder_coherence` already books as an unproven cert obligation. Cost on
economics: 60 pre-pass chunks, ~185 s total fold.

## Artifacts

| file | what |
|---|---|
| `census-polymarket-economics.json` | full name-site + outcome-site census, incl. the `drop`/`ambiguous`/`coherent` id partition |
| `census-polymarket-tech.json` | same, tech |
| `fold-economics-mono.txt` | exact rail, pooled |
| `fold-economics-mono-holdout.txt` | exact rail, holdout split — **the load-bearing one** |
| `fold-tech-mono-holdout.txt` | exact rail, tech; the 11-row collapse |
