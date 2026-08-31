# Does 12-CAL matter beyond rank 8? Yes — on three cells now, including the one RULE E2 was built on

**TL;DR.** The lone-claim defect is now measured on **three cells across two sources**, and
it changes two asks, not one:

* 🔴 **`polymarket/esports` is where RULE E2 came from — and E2's premise is false there.**
  CAL-P112 built E2 on that cell's *"453 markets, 453 outcomes, 453 winners — a win rate of
  1.000 … not a set of Yes/No claims being scored, it is one-sided capture."* Measured on
  the producer's own chain one predicate earlier: **141 eligible losers are being dropped**,
  and the class is **219/360 winners (60.8%), not 219/219.** The capture is two-sided at
  E2's own origin.
* 🔴 **The published direction is not one direction.** Two cells get worse, one gets better.

| cell | class today | class restored | cell today | cell restored | |
|---|---|---|---|---|---|
| `kalshi/entertainment` (CAL-P122) | 395, 100.0% W | 827, 47.8% W | ECE 5.21 | **6.30** | worse 1.09 |
| `polymarket/esports` (CAL-P143) | 219, 100.0% W | 360, 60.8% W | ECE 7.03 | **7.37** | worse 0.34 |
| `polymarket/economics` (CAL-P143) | 514, 99.6% W | 592, 86.5% W | ECE 3.90 | **3.68** | better 0.22 |
| `kalshi/economics` (CAL-P143) | 76, 100.0% W | 140, 54.3% W | ECE 5.39 | **5.34** | better 0.05 |

**Four cells, two sources, 715 dropped losers, and this is the shape of it:**

* **every** cell is two-sided in truth — 47.8%, 54.3%, 60.8%, 86.5% winners — while the page
  shows every one of them at 100% or 99.6%;
* the cell-level headline effect is **small and its sign disagrees**: −0.05, −0.22, +0.34,
  +1.09. Two better, two worse, and the largest move is 1.09 pp on one cell.

That second line is the one that should decide D13. The question was never "does this cost
us headline"; it costs between −0.22 and +1.09 pp on a cell, in both directions. The
question is whether a page that reports a class of forecasts as **100% correct** when it is
48–87% correct is one we are willing to keep publishing.

---

## The original two-cell framing, which the third cell did not overturn

Two things: 

1. ✅ **The mechanism is proved, not inferred.** CAL-P131 found 508 published outcomes on
   `polymarket/economics` that could not have lost, named `clean_vms` as the *candidate*
   clause, and marked it explicitly: *"Naming the clause is a lead for the lane that owns
   the fix, not a verdict."* Run on the producer's own chain one predicate earlier, the
   verdict is in: **78 eligible losers, uniquely dropped by the vm-level winner gate.**
2. 🔴 **"The fix makes the headline worse" is cell-dependent — and on this cell it makes it
   BETTER.** That sentence is the reason 12-CAL has sat since CAL-P122. It is true on
   `kalshi/entertainment` and false here.

**Three cells, two sources, and the signs disagree.** Nobody can say from three points which
way the board-wide headline moves, and this document does not extrapolate to the other 46
cells — a 134× spread on the phantom factor taught this lane not to pool cells that have not
been measured (`payload-basis-table.txt`). What can be said is that **"it makes our number
worse" is no longer a reason to leave 12-CAL unanswered**, because on one of the three it
does not, and because the two it worsens are worsened by 1.09 and 0.34 — not by amounts that
decide anything on their own.

---

## The measurement

```
polymarket/economics   (missing-loser census, width 1000000, 159s)
  curve generated 2026-08-30T12:25:52Z   population q268

  SELF-CHECK — the producer's own chain against the payload it produced
    exact replica    n=  12965  ECE=   3.9  gap=  -0.01
    payload          n=  13150  ECE=  3.87  gap=  -0.05
    delta            n=   -185 (-1.41%)  ECE=+0.03  gap=+0.04

  THE GATE'S SHADOW
    arm                                      n      ECE      gap  winrate
    A_also_no_winner (rung 1 owns these)    1754     5.31    +4.66    39.3%
    B_lone_claim (UNIQUELY dropped)           78    39.87   +39.87     0.0%

  THE LONE-CLAIM CLASS, published vs whole
    published today (winners only)           514    42.55   -42.55    99.6%
    with its losers restored                 592    31.71   -31.69    86.5%

  THE CELL
    published today                        12965      3.9    -0.01    41.3%
    with lone-claim losers restored        13043     3.68    +0.23    41.0%

  VERDICT  78 ELIGIBLE LOSERS ARE BEING DROPPED
```

The **1,754-row `A_also_no_winner` arm is 22× the defect** and is NOT part of it: those are
≥2-outcome virtual markets that graded nobody, which Queue 299 rung 1 removes on purpose as
UNKNOWN truth. Reporting one number here would have claimed 1,832. The split is the point,
and the repair's predicate (§2 of the rule design) restores the 78 and leaves the 1,754
exactly where rung 1 put them.

## 🔴 The correction this makes to CAL-P131

CAL-P131's raw-population census read:

```
  single-leg markets in polymarket/economics (raw)   3,844
    leg graded winner                                2,027  (52.7%)
    leg graded loser                                 1,817  (47.3%)
  rows this shape contributes to the published curve   508  — and 508 of 508 are winners
```

A reader could take "1,817 graded losers exist and 0 are published" as the size of the
repair. **It is not: 78 of them are recoverable, and the other ~1,739 fail some OTHER
published condition** — truth-eligible resolution source, opening price strictly inside
(0, 1), the liquidity-evidence predicate. The gate's shadow is measured *after* every
condition except the gate itself, which is exactly why the instrument reads `vm_stats`
rather than the raw table.

**The lesson, and it is the same shape as CAL-P141's:** a raw base rate is not a repair
size. 47.3% of the raw population being losers says the CAPTURE is two-sided (which was
CAL-P131's real point and stands). It says nothing about how many of those losers clear
every other bar the curve applies.

Note also that the published class is **99.6%** winners here, not 100.0%: two losers are
already on the curve, carried by a grouped sibling. A rule keyed on "this class is 100%
winners" — which is E2's premise — would not even match this cell cleanly.

## What this does to 13-CAL

13-CAL asks Alex to HOLD **RULE E2**, whose stated justification is *"a population that is
100% winners is not a set of Yes/No claims being scored, it is one-sided capture."* That
premise has now been tested on four cells and failed on all four:

* `polymarket/esports`: 100% winners published, **60.8%** restored — **and this is the cell
  E2 was written on**, the "453/453" claim;
* `kalshi/entertainment`: 100% winners published, **47.8%** restored;
* `kalshi/economics`: 100% winners published, **54.3%** restored;
* `polymarket/economics`: 99.6% winners published, **86.5%** restored.

In every cell the capture is two-sided and the **population filter** is the one-sided thing.
The esports result is the one that settles it: a rule may survive being wrong about a cell
it was generalised to, but not about the cell it was generalised FROM.

13-CAL blocks 143,495 excess outcomes — 18,763 in its own cell plus two banked designs
(`polymarket/esports` 59,902, `kalshi/economics` 64,830) whose own shipping clauses say E2
ships with them. **Both of those two are now measured and both carry the defect**, so E2
would ship onto two cells whose lone-claim class it mis-describes. **13-CAL cannot be
answered before 12-CAL, and 12-CAL now has four cells of evidence instead of one.**

## Coverage, stated rather than implied

Measured exactly and completely: `kalshi/entertainment` (CAL-P122), plus
`polymarket/economics`, `polymarket/esports` and `kalshi/economics` this session
(`missing-losers-*.json` + logs in this directory). **Both banked designs that cannot land
until 13-CAL are now measured, and both carry the defect** — esports 141, kalshi/economics
64. **The other 45 material cells are unmeasured** and are PARKED, not estimated —
CAL-P122-1 in `PARKED-MEASUREMENTS.md`, one command per cell.

Three properties worth carrying into the next cell, because all three held every time:

* the `A_also_no_winner` arm dwarfs the defect — 1,754 vs 78, **14,884 vs 141** (106×),
  1,494 vs 64. A census that reports one number here reports the wrong one by two orders of
  magnitude, which is why the instrument splits the arms and why the repair's predicate
  restores only the second;
* the self-check against the live payload holds every time, and on `kalshi/economics` it is
  **exact** — `delta n +0 (+0.00%), ECE +0.00, gap +0.00`. The counterfactual is being
  computed over the population the page actually publishes, not a lookalike;
* the restored class always lands between 47% and 87% winners. Nothing measured so far
  restores to something that looks like one-sided capture.
