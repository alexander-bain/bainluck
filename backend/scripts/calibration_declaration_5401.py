#!/usr/bin/env python3
"""#5401 — turn the two population arms into the DECLARATION, and judge it.

``CALIBRATION_POPULATION_DECLARATION`` states the move over the whole published
population and ``evaluate_publish`` refuses the rebuild if the realised move
misses it by more than ``tolerance_pct`` — and a refusal CLEARS THE CHECKPOINT,
binning every later rebuild until another deploy corrects it. So the number this
prints is the number that ships, and the arithmetic behind it is written down
here rather than done once in a shell.

THE DENOMINATOR IS THE WHOLE CURVE, NOT THE SOURCE. The bar is Kalshi-only
(``kalshi_writer_bar_met_sql`` is TRUE for every other source), so only Kalshi
rows move — but the declaration is a statement about the PUBLISHED POPULATION,
which at q269 is 782,077 observations of which Kalshi is 396,160. Quoting
Kalshi's own 8-9% as the expected drop would over-declare by a factor of two.

BOTH ARMS ARE MEASURED IN THE SAME WINDOW, and the drop is their difference —
never `published payload minus measured arm`. `futures_markets` grows while the
sweep runs, so an arm measured now against a bank published hours ago carries
that growth as if it were the repair's effect. The payload's Kalshi count is
used only as a CONTROL on the baseline arm, never as the baseline itself.

Usage::

    python3 backend/scripts/calibration_declaration_5401.py \\
        --baseline artifacts/cal-p1121/population-baseline.json \\
        --repaired artifacts/cal-p1121/population-repaired.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: The live q269 payload, read 2026-09-12T00:16:35Z. `by_source` sums to
#: `total_outcomes` exactly; `by_category` does NOT (it sums to 756,873, because
#: `min_category_outcomes = 1000` gates small cells out of that breakdown only),
#: so the control compares against by_source and never by_category.
PUBLISHED_TOTAL = 782_077
PUBLISHED_KALSHI = 396_160

#: `evaluate_publish`'s hard ceiling on `tolerance_pct`.
MAX_TOLERANCE_PCT = 5.0

#: A cell moving further from 1.0 than this is called out. A tenth of golf's own
#: miss — a threshold for ATTENTION, not a ruling.
CELL_DAMAGE_PCT = 0.02


def _ratio(won: float, implied: float) -> float | None:
    """Winners / implied winners: the accuracy page's own number, 1.0 perfect."""
    return (won / implied) if implied > 0 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--repaired", required=True)
    args = ap.parse_args()

    base = json.loads(Path(args.baseline).read_text())
    rep = json.loads(Path(args.repaired).read_text())

    for name, arm in (("baseline", base), ("repaired", rep)):
        if arm["irreducible"]:
            raise SystemExit(
                f"{name}: {len(arm['irreducible'])} chunk(s) never answered "
                f"({arm['irreducible'][:3]}...). Their rows are MISSING from "
                f"the count, so the difference below is not a population move. "
                f"Re-run with a smaller --target-outcomes."
            )

    b_n = base["kalshi_published_outcomes"]
    r_n = rep["kalshi_published_outcomes"]

    print("== CONTROL ==")
    drift = b_n - PUBLISHED_KALSHI
    print(f"baseline Kalshi (master semantics, measured) : {b_n:,}")
    print(f"live q269 payload by_source kalshi n         : {PUBLISHED_KALSHI:,}")
    print(
        f"difference                                   : {drift:+,} "
        f"({100.0 * drift / PUBLISHED_KALSHI:+.2f}%)"
    )
    print(
        "  The baseline arm reconstructs master's population from the branch "
        "by\n  neutralising one flag, chunked event-atomically over the full "
        "id range.\n  A large gap here means the RIG is wrong (a truncated "
        "key space, a split\n  event group, a per-source coupling) and the "
        "repaired arm means nothing.\n  A small one is live-table growth "
        "since the bank was built."
    )

    drop = b_n - r_n
    pct_of_all = 100.0 * drop / PUBLISHED_TOTAL
    pct_of_kalshi = 100.0 * drop / b_n if b_n else 0.0

    print("\n== THE MOVE ==")
    print(f"repaired Kalshi (writer bar applied)         : {r_n:,}")
    print(f"rows the writer bar removes                  : {drop:,}")
    print(f"  as a share of Kalshi                       : {pct_of_kalshi:.2f}%")
    print(
        f"  as a share of the PUBLISHED POPULATION     : {pct_of_all:.2f}%"
        "   <- expected_drop_pct"
    )

    print("\n== PER-CELL EFFECT (published rows, winners / implied) ==")
    bc = {r["category"]: r for r in base["by_category"]}
    rc = {r["category"]: r for r in rep["by_category"]}
    print(
        f"{'category':>18} {'n before':>9} {'n after':>8} {'cut%':>6} "
        f"{'before':>7} {'after':>7} {'move':>7}"
    )
    damaged = []
    for cat in sorted(bc, key=lambda c: -bc[c]["n"]):
        b, r = bc[cat], rc.get(cat, {"n": 0, "won": 0, "implied": 0.0})
        before, after = _ratio(b["won"], b["implied"]), _ratio(r["won"], r["implied"])
        cut = 100.0 * (b["n"] - r["n"]) / b["n"] if b["n"] else 0.0
        if before is None:
            continue
        flag = ""
        if after is not None and abs(after - 1.0) > abs(before - 1.0) + CELL_DAMAGE_PCT:
            flag = "  <- moves AWAY from 1.0"
            damaged.append(cat)
        a_txt = f"{after:7.3f}" if after is not None else "      -"
        m_txt = f"{after - before:+7.3f}" if after is not None else "      -"
        print(
            f"{cat:>18} {b['n']:>9,} {r['n']:>8,} {cut:>5.1f}% "
            f"{before:>7.3f} {a_txt} {m_txt}{flag}"
        )

    print("\n== WHAT TO WRITE INTO precompute_calibration.py ==")
    print('  CALIBRATION_POPULATION_VERSION = "q270"')
    print("  CALIBRATION_POPULATION_DECLARATION = dict(")
    print('      from_version="q269",')
    print(f"      expected_drop_pct={pct_of_all:.2f},")
    print(f"      tolerance_pct=<CHOOSE; hard max {MAX_TOLERANCE_PCT}>,")
    print("  )")
    if damaged:
        print(
            f"\n  WARNING: {len(damaged)} cell(s) move AWAY from 1.0: "
            f"{', '.join(damaged)}"
        )
        print(
            "  A source-wide predicate has to be judged on the cells it was "
            "not written\n  for. Read these before declaring."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
