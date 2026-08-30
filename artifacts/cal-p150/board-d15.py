#!/usr/bin/env python3
"""CAL-P150 — the repair board, rebuilt under the 2026-08-30 rulings batch.

WHAT CHANGED, AND WHY A SCRIPT RATHER THAN A DOCUMENT. Three of the day's
rulings move cells on and off the work list, and one of them (D15) changes the
ORDERING RULE rather than any single cell:

  D15, verbatim Alex — *"If there are 80 predictions in a golf tournament, one
  for each player, then I want to know the accuracy of each of them. That's not
  one thing, that's 80."*  NEW DOCTRINE: every published prediction is
  individually accountable; clustering arguments may inform CONFIDENCE
  reporting but do not remove a category from repair work.

  SIX CELLS — the six categories removed last week under the clustering
  argument are RE-LISTED.

  D16 — basketball is PARKED until the D5 dedup lands, then re-measured.

  D14 — cricket's "the venue is bad at cricket" conclusion is REJECTED. The
  cell returns to the board under the presumption that the defect is OURS.

Six of the seven cells this restores were refused with the words "not
established", which is the SIGMA_GATE 2.0 test — and the sigma gate IS the
clustering argument, wearing a number. So the doctrine does not merely re-list
six cells: it retires the reason nine cells were taken off, and it says what to
do instead, which is to rank them below the established ones rather than delete
them. That is an ordering rule, and an ordering rule belongs in code.

WHAT THIS IS NOT. It does not change what /api/calibration publishes, it does
not touch a threshold, and it does not re-measure anything: every number is read
out of a banked scorecard render. `calibration_scorecard.py` still renders the
board its own way and will until Alex rules on the display.

EXIT CODES (gotcha #124 — read the value, not the fact that it ran):
  0  the board reproduced and every ruled cell is present and correctly placed
  4  a cell the rulings batch names is MISSING from the live board
  5  a banked render could not be read

Usage, from the repo root::

    python3 artifacts/cal-p150/board-d15.py [--render <path>]
"""

from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RENDERS = os.path.join(os.path.dirname(HERE), "cal-p147-renders")

#: SIGMA_GATE, read off the render's own thresholds rather than restated. A
#: constant copied out of a payload is a constant that drifts from it.
SIGMA_GATE_KEY = "sigma_gate"

#: The cells the 2026-08-30 batch puts BACK on the board, with the refusal each
#: one is being restored over. Every entry must appear in the rebuilt board or
#: this script exits 4 — a ruling that silently fails to reach the work list is
#: the failure mode the refusal register was built to catch (CAL-P145).
RESTORED = {
    "kalshi/golf": (
        "D15 — 17-CAL is ANSWERED NO. CAL-P127 measured sigma 1.42 against a "
        "2.0 gate and recommended taking it OFF the board; the golf ruling is "
        "the direct answer to that recommendation and it declines it. "
        "~80 players, ~80 predictions, each individually accountable."
    ),
    "odds_api_bookmaker/basketball_nba": (
        "SIX CELLS — CAL-P120 refused it 'not established' at game grain "
        "(measured sigma 0.62-1.72 across the six). Re-listed."
    ),
    "odds_api_bookmaker/baseball_mlb_preseason": ("SIX CELLS — as above."),
    "odds_api_bookmaker/icehockey_nhl": ("SIX CELLS — as above."),
    "odds_api_bookmaker/basketball_wncaab": ("SIX CELLS — as above."),
    "odds_api_bookmaker/basketball_wnba": ("SIX CELLS — as above."),
    "odds_api_bookmaker/basketball_euroleague": ("SIX CELLS — as above."),
    "polymarket/cricket": (
        "D14 — OVERRULED, verbatim Alex: 'I refuse to believe that well traded "
        "markets for any sport are fundamentally inaccurate. Markets aren't "
        "wrong; calculations are.' The cell is not refused for being "
        "unfixable; it is under re-investigation as OUR defect. No "
        "known-bad label ships."
    ),
}

#: 🔴 MEASURED SIGMA THE BOARD'S LEDGER DOES NOT CARRY, and without this table
#: this script ranks six cells on a number CAL-P120 disproved.
#:
#: The board's per-cell `sigma` is a binomial estimate over BOOK ROWS. For
#: `odds_api_bookmaker` that unit is wrong by construction: 10-18 bookmakers
#: quote one game, so one game is counted 10-18 times and sigma is inflated by
#: roughly the square root of the replication. CAL-P120 re-folded all six at
#: GAME grain and none of them clears 2.0.
#:
#: `sigma_measured` is a ledger OVERLAY, not census output — it is populated for
#: twelve cells and absent for these six, so reading the render alone silently
#: substitutes the binomial number and prints "established" for every one of
#: them. That is the same class of mistake as the D5 comment: an instrument
#: reporting a different quantity than the reader assumes, with nothing in the
#: output saying so.
#:
#: Source: artifacts/cal-p120/RULE-DESIGN-odds-api-bookmaker-six-cells.md §2,
#: the "σ per game" column. Transcribed with the replication factor beside it so
#: a reader can see why the two numbers differ rather than having to trust one.
CAL_P120_GAME_GRAIN_SIGMA = {
    # cell: (sigma_per_game, games, replication_vs_book_rows)
    "odds_api_bookmaker/basketball_nba": (1.28, 573, 17.8),
    "odds_api_bookmaker/baseball_mlb_preseason": (1.69, 217, 15.0),
    "odds_api_bookmaker/icehockey_nhl": (0.62, 495, 17.5),
    "odds_api_bookmaker/basketball_wncaab": (1.72, 583, 5.8),
    "odds_api_bookmaker/basketball_wnba": (0.80, 300, 10.4),
    "odds_api_bookmaker/basketball_euroleague": (0.74, 162, 10.9),
}

#: Cells whose work is explicitly SUSPENDED rather than refused, with the event
#: that resumes them. Parked is a real state (CLAUDE.md), and it is not the same
#: as refused: a refused cell needs a new argument, a parked one needs a date.
PARKED = {
    "polymarket/basketball": (
        "D16 — parked until the D5 dedup lands, then re-measure and finish. "
        "The cell is scored over 43.44% duplicate rows, so every number about "
        "it today describes a population that is about to change."
    ),
    "polymarket/hockey": (
        "20-CAL, same mechanism as basketball (26.79% duplicate rows). Parked "
        "with it — D16 names basketball, and folding hockey in is the ledger's "
        "own CAL-P141 finding that the two are one question."
    ),
}


def _newest_render() -> str:
    hits = sorted(glob.glob(os.path.join(RENDERS, "scorecard-*.txt")))
    if not hits:
        print("🔴 no banked scorecard render found", file=sys.stderr)
        raise SystemExit(5)
    return hits[-1]


def build(render_path: str) -> dict:
    with open(render_path) as fh:
        board = json.load(fh)

    gate = board["thresholds"][SIGMA_GATE_KEY]
    cells = board["cells"]

    over = [c for c in cells if str(c.get("verdict", "")).startswith("OVER_BAR")]

    # THE D15 ORDERING. Established first, thin-miss below — not removed, and
    # not interleaved. `sigma` is the board's own binomial estimate; where a
    # measured (cluster-bootstrap) sigma exists it OVERRIDES, because that is
    # the number the clustering argument was made on and the doctrine is about
    # exactly that argument.
    # THE PRECEDENCE, and the order matters more than any one entry:
    #   1. CAL-P120's game-grain fold, where it exists — the number the
    #      clustering argument was actually made on;
    #   2. the render's `sigma_measured` ledger overlay;
    #   3. the render's binomial row estimate, LAST and labelled, because for a
    #      multi-bookmaker cell it is a fact about rows and not about games.
    def _sigma(c):
        name = c["cell"]
        if name in CAL_P120_GAME_GRAIN_SIGMA:
            return CAL_P120_GAME_GRAIN_SIGMA[name][0], "measured_game_grain_p120"
        if c.get("sigma_measured") is not None:
            return c["sigma_measured"], "measured"
        return c.get("sigma"), c.get("sigma_basis")

    def established(c) -> bool:
        s, _ = _sigma(c)
        return s is not None and s >= gate

    def sigma_used(c):
        return _sigma(c)[0]

    ranked = sorted(
        over,
        key=lambda c: (0 if established(c) else 1, -c.get("excess_outcomes", 0)),
    )

    rows = []
    for i, c in enumerate(ranked, 1):
        name = c["cell"]
        rows.append(
            {
                "rank": i,
                "cell": name,
                "tier": "established" if established(c) else "thin-miss",
                "ece": c.get("ece"),
                "bar_pp": c.get("bar_pp"),
                "n": c.get("n"),
                "excess_outcomes": c.get("excess_outcomes"),
                "sigma_used": sigma_used(c),
                "sigma_basis": _sigma(c)[1],
                "sigma_board_binomial": c.get("sigma"),
                "state": (
                    "PARKED" if name in PARKED
                    else "RESTORED" if name in RESTORED
                    else "on-board"
                ),
                "note": PARKED.get(name) or RESTORED.get(name),
            }
        )

    present = {r["cell"] for r in rows}
    missing = sorted(set(RESTORED) - present)

    return {
        "render": os.path.basename(render_path),
        "generated_at": board.get("generated_at"),
        "population_version": board.get("population_version"),
        "headline_mce_closing_line": board.get("headline_mce_closing_line"),
        "sigma_gate": gate,
        "counts": {
            "over_bar_total": len(rows),
            "established": sum(1 for r in rows if r["tier"] == "established"),
            "thin_miss": sum(1 for r in rows if r["tier"] == "thin-miss"),
            "restored_by_this_batch": sum(1 for r in rows if r["state"] == "RESTORED"),
            "parked": sum(1 for r in rows if r["state"] == "PARKED"),
        },
        "missing_ruled_cells": missing,
        "board": rows,
    }


def main() -> int:
    args = sys.argv[1:]
    render = _newest_render()
    if "--render" in args:
        render = args[args.index("--render") + 1]

    out = build(render)
    with open(os.path.join(HERE, "board-d15.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    c = out["counts"]
    print(f"CAL-P150 BOARD — D15 ordering, on {out['render']}")
    print(f"  population {out['population_version']}   headline "
          f"{out['headline_mce_closing_line']} pp   sigma_gate {out['sigma_gate']}")
    print(f"  {c['over_bar_total']} cells over bar: {c['established']} established, "
          f"{c['thin_miss']} thin-miss (ranked below, NOT removed)")
    print(f"  {c['restored_by_this_batch']} restored by the 2026-08-30 batch, "
          f"{c['parked']} parked")
    print()
    print(f"  {'#':>3}  {'cell':<44} {'ece':>6} {'bar':>5} {'excess':>8} "
          f"{'sigma':>7} {'basis':<26} {'tier':<12} state")
    for r in out["board"]:
        sig = r["sigma_used"]
        print(f"  {r['rank']:>3}  {r['cell']:<44} {r['ece']:>6} {r['bar_pp']:>5} "
              f"{r['excess_outcomes']:>8} {sig if sig is None else round(sig,2):>7} "
              f"{str(r['sigma_basis']):<26} {r['tier']:<12} {r['state']}")

    shadowed = [
        r for r in out["board"]
        if r["sigma_basis"] == "measured_game_grain_p120"
        and r["sigma_board_binomial"] is not None
        and r["sigma_board_binomial"] >= out["sigma_gate"] > r["sigma_used"]
    ]
    if shadowed:
        print()
        print("  ⚠️ THE LIVE BOARD WOULD RANK THESE AS ESTABLISHED AND IT IS READING")
        print("     A DIFFERENT QUANTITY. Its sigma is binomial over BOOK ROWS; one")
        print("     game is quoted by 10-18 bookmakers, so the unit is wrong and the")
        print("     number is inflated by roughly sqrt(replication). The board's own")
        print("     `sigma_measured` overlay is ABSENT for all of these, so nothing in")
        print("     the render says so. CAL-P120 §2 re-folded them at game grain:")
        for r in shadowed:
            games, repl = CAL_P120_GAME_GRAIN_SIGMA[r["cell"]][1:]
            print(f"       {r['cell']:<44} board {r['sigma_board_binomial']:>5} -> "
                  f"per-game {r['sigma_used']:>5}  ({games} games, {repl}x rows)")
        print("     They stay ON the board under D15 — the clustering argument informs")
        print("     confidence, it does not remove a category from repair work — and")
        print("     they are ranked BELOW the established cells, which is what the")
        print("     doctrine asks for instead of deletion.")

    if out["missing_ruled_cells"]:
        print()
        print("🔴 RULED CELLS ABSENT FROM THE LIVE BOARD — a ruling that does not")
        print("   reach the work list is the failure the refusal register exists")
        print("   to catch. These are not resolved; they are unfindable:")
        for name in out["missing_ruled_cells"]:
            print(f"     {name}")
            print(f"       {RESTORED[name]}")
        return 4

    print()
    print("  every cell named by the 2026-08-30 batch is present and placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
