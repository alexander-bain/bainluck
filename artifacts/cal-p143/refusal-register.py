#!/usr/bin/env python3
"""CAL-P143 — the refusal register: four cells were refused, and the instrument
that is supposed to make refusals legible can only see three of them.

WHY THIS EXISTS
---------------
`artifacts/cal-p140/hold-ledger.py` groups the board's queued cells by the
question each one waits on. It is the right instrument for a HOLD. It is the
wrong one for a REFUSAL, and the gap shows up in two places in its own output:

1.  Two of its three refusals cite the string ``"refused with measurement"`` --
    a disposition wearing a citation's clothes. The documents exist
    (`cal-p130`, `cal-p131`); nothing pointed at them.
2.  The ledger reads the LIVE board, so a cell that leaves the board leaves the
    ledger. **`polymarket/tech` -- CAL-P132's refusal, and the fourth of the
    four consecutive ones -- is not on the board any more, so the ledger cannot
    show it at all.** A hold that leaves the board is resolved. A refusal that
    leaves the board is still a refusal: it is a durable finding about a cell,
    and the next session to reach that cell needs to know the search was already
    run exhaustively.

So the register is keyed on the REFUSAL, not on the board, and the board is
joined in as a status column rather than used as the row source. That inversion
is the whole design.

Exit codes: 0 register clean; 4 a refusal cites a document that is not on disk,
or a refusal is off the board with no recorded reason.

    python3 artifacts/cal-p143/refusal-register.py [--scorecard PATH] [--json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]

#: cell -> the refusal, as its own document states it. ``mode`` is what the
#: refusal turned on, and the four are deliberately different: reading them as
#: one "no rule found" loses the fact that four unrelated search strategies were
#: each exhausted.
REFUSALS: dict[str, dict] = {
    "kalshi/entertainment": {
        "session": "CAL-P129",
        "doc": "artifacts/cal-p129/RULE-DESIGN-kalshi-entertainment.md",
        "mode": "holdout",
        "searched": "12 partitions, no retention floor",
        "refuting_number": "sumband's 33 pooled passes go to 0 of 1023 under "
                           "the holdout; best worst-half 3.09 vs a 3.0 bar",
        "board_note": None,
        "still_open_question": "13-CAL",
    },
    "polymarket/golf": {
        "session": "CAL-P130",
        "doc": "artifacts/cal-p130/RULE-DESIGN-polymarket-golf.md",
        "mode": "retention",
        "searched": "15 partitions (14 inherited + 1 built), exhaustive",
        "refuting_number": "no subset clears the bar at any retention; the cell "
                           "shows ~100 golfers each priced ~48% to finish top five",
        "board_note": None,
        "still_open_question": None,
    },
    "polymarket/economics": {
        "session": "CAL-P131",
        "doc": "artifacts/cal-p131/RULE-DESIGN-polymarket-economics.md",
        "mode": "no structural dimension",
        "searched": "16 partitions (15 inherited + 1 built), exhaustive",
        "refuting_number": "508 outcomes the curve admits only because they won; "
                           "an 11-band S&P market prices both tails at 40%",
        "board_note": None,
        "still_open_question": None,
    },
    "polymarket/tech": {
        "session": "CAL-P132",
        "doc": "artifacts/cal-p132/RULE-DESIGN-polymarket-tech.md",
        "mode": "exhaustive lattice",
        "searched": "17 partitions, whole 2^k lattice at --min-rows 1 "
                    "--min-share 0",
        "refuting_number": "zero subsets clear 3.0 on the worst half at ANY "
                           "retention, including retentions that delete 99% of "
                           "the cell; best leakage-free 3.12 / 4.66",
        "board_note": "was board rank 19 when refused; the board has since moved "
                      "and it is no longer in the queued 19, so hold-ledger.py "
                      "cannot see it",
        "still_open_question": None,
    },
}

SCORECARD = "backend/scripts/calibration_scorecard.py"


def read_board(scorecard_text: str) -> dict[str, dict]:
    """Rank + excess for every queued cell, off the scorecard's own rendering.

    Same parse as ``hold-ledger.py`` and for the same reason: the ranking this
    joins against must be the one the conveyor reads, not a second opinion.
    """
    board, started = {}, False
    for line in scorecard_text.splitlines():
        if line.startswith("QUEUED CELLS"):
            started = True
            continue
        if not started:
            continue
        stripped = line.strip()
        if not stripped:
            if board:
                break
            continue
        if "excess-outcomes=" not in stripped:
            break
        head, _, tail = stripped.partition(".")
        try:
            rank = int(head.strip())
        except ValueError:
            break
        name = tail.strip().split()[0]
        board[name] = {
            "rank": rank,
            "excess_outcomes": int(
                tail.split("excess-outcomes=")[1].strip().replace(",", "")),
        }
    return board


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorecard", help="read a banked scorecard render instead "
                                        "of going live")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.scorecard:
        text = pathlib.Path(args.scorecard).read_text()
    else:
        text = subprocess.run([sys.executable, SCORECARD], cwd=REPO,
                              capture_output=True, text=True).stdout
    board = read_board(text)

    rows, problems = [], []
    for cell, r in REFUSALS.items():
        doc = REPO / r["doc"]
        if not doc.exists():
            problems.append(f"{cell}: cited document {r['doc']} is not on disk")
        seat = board.get(cell)
        if seat is None and not r["board_note"]:
            problems.append(f"{cell}: refused, off the board, and no reason "
                            f"recorded for why it left")
        rows.append({**r, "cell": cell,
                     "on_board": seat is not None,
                     "rank": seat["rank"] if seat else None,
                     "excess_outcomes": seat["excess_outcomes"] if seat else None,
                     "doc_exists": doc.exists()})

    if args.json:
        print(json.dumps({"refusals": rows, "problems": problems,
                          "board_cells": len(board)}, indent=1))
        return 4 if problems else 0

    print("CAL-P143 REFUSAL REGISTER — the four consecutive refusals, and where "
          "each one now sits")
    print(f"  board read: {len(board)} queued cells\n")
    print(f"  {'cell':<26} {'session':<9} {'mode':<24} {'board':<16} excess")
    for row in sorted(rows, key=lambda r: (r["rank"] is None, r["rank"] or 0)):
        seat = f"rank {row['rank']}" if row["on_board"] else "OFF THE BOARD"
        excess = f"{row['excess_outcomes']:,}" if row["excess_outcomes"] else "-"
        print(f"  {row['cell']:<26} {row['session']:<9} {row['mode']:<24} "
              f"{seat:<16} {excess:>8}")
    print()
    for row in rows:
        print(f"  {row['cell']} — {row['searched']}")
        print(f"      {row['refuting_number']}")
        print(f"      {row['doc']}")
        if row["board_note"]:
            print(f"      🔴 {row['board_note']}")
        if row["still_open_question"]:
            print(f"      waits on {row['still_open_question']}")
    print()
    off = [r for r in rows if not r["on_board"]]
    print(f"  ON the board: {len(rows) - len(off)} of {len(rows)}   "
          f"OFF the board: {len(off)}")
    if off:
        print("  🔴 hold-ledger.py reads the board, so it cannot show the "
              f"{len(off)} refusal(s) above. A hold that leaves the board is "
              "resolved; a refusal that leaves the board is still a refusal.")
    for p in problems:
        print(f"  🔴 {p}")
    print("\n  EXIT " + ("4 — the register has a hole" if problems else "0"))
    return 4 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
