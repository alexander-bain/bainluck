#!/usr/bin/env python3
"""CAL-P145 — the refusal register, extended from four refusals to every one on disk,
and made unable to go stale silently.

WHAT THIS IS (inherited from CAL-P143/144, unchanged)
-----------------------------------------------------
`artifacts/cal-p140/hold-ledger.py` groups the board's queued cells by the question
each one waits on. It is the right instrument for a HOLD and the wrong one for a
REFUSAL, for two reasons that show up in its own output:

1.  Its refusals cite the string ``"refused with measurement"`` — a disposition
    wearing a citation's clothes. The documents exist; nothing pointed at them.
2.  The ledger reads the LIVE board, so a cell that leaves the board leaves the
    ledger. A hold that leaves the board is resolved. A refusal that leaves the
    board is still a refusal: a durable finding about a cell, and the next session
    to reach it needs to know the search was already run exhaustively.

So the register is keyed on the REFUSAL, not the board; the board is joined in as a
status column rather than used as the row source. That inversion is the design.

🔴 WHAT CAL-P145 CHANGES, AND WHY
---------------------------------
CAL-P143/144's register carried **four** refusals — CAL-P129/130/131/132, one
contiguous run of sessions. Reconciled against disk on 2026-08-30 there are
**eight refusal documents covering thirteen cells**, and the four missing documents
are not marginal:

* `CAL-P118` refused `polymarket/soccer` — **live rank 4**. Its own text says the
  document "exists so that nobody spends another cycle building it." That is this
  register's purpose, stated by a document the register could not see.
* `CAL-P120` refused all six `odds_api_bookmaker` cells as **not established** —
  **live ranks 5, 8, 13, 14, 18, 20**, including the board's rank 5.
* `CAL-P123` refused `polymarket/cricket` exhaustively — **live rank 10**.
* `CAL-P127` ruled `kalshi/golf` **not established** and recommended it off the
  board — **live rank 7**.

An instrument scoped to one run of sessions is a session note, not a register. The
same lesson CAL-P144 wrote about `refusal-register.py`'s live path applies to its
row source: an instrument that cannot notice what it is missing reports its own
scope as the world.

So this version adds a **reconciliation**: every `artifacts/*/RULE-DESIGN-*.md` on
disk must be registered here, as a refusal or with a named non-refusal disposition.
A new rule-design document that nobody registers makes this exit 4. The register can
now go stale, but it can no longer go stale *quietly*.

Two other things are carried forward verbatim because they are still true:
CAL-P144's fix to the live path (the scorecard REQUIRES ``--live``; invoked bare it
exits 2 with empty stdout, and the old code read neither returncode nor stderr —
gotcha #124, #53), and its correction that `polymarket/tech` is back on the board.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not re-litigate a refusal, re-measure a cell, or infer a disposition. Every
rank, excess and refuting number below is quoted from the document it cites. Where a
document does not state a figure, the field is ``None`` and prints as ``-`` — never
a reconstruction. (`polymarket/tech`'s excess at refusal is the one such gap.)

Exit codes: 0 register clean; 4 a cited document is missing from disk, a refusal is
off the board with no recorded reason, or a rule-design document on disk is not
registered here.

    source ~/.claude/.env && python3 artifacts/cal-p145/refusal-register.py
    python3 artifacts/cal-p145/refusal-register.py --scorecard PATH [--json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]

#: One entry per refusal DOCUMENT (not per cell) — CAL-P120 refuses six cells in
#: one document, and two documents touch `kalshi/entertainment`, so the document is
#: the only key that is one-to-one with a search having been run.
#:
#: ``disposition`` is load-bearing and the taxonomy is deliberate: "no rule exists"
#: (a search was run and came back empty) and "not established" (the cell's excess
#: does not survive the right unit of observation) are different findings with
#: different consequences, and collapsing them into "refused" loses the difference.
#:
#: ``refused_at`` is ``{cell: (rank, excess)}`` AS THE DOCUMENT STATES IT, so the
#: live join below reads as drift rather than as a second opinion.
REFUSALS: list[dict] = [
    {
        "session": "CAL-P118",
        "doc": "artifacts/cal-p118/RULE-DESIGN-polymarket-soccer.md",
        "cells": ["polymarket/soccer"],
        "disposition": "no rule exists",
        "mode": "named mechanism, folded",
        "searched": "the cell's own named mechanism (incoherent ladders) plus every "
                    "variant tried, holdout-split",
        "refuting_number": "the shipped rule makes the cell WORSE on BOTH halves — "
                           "OLD 4.86 -> 4.99, NEW 2.01 -> 2.22; rank 4 keeps its "
                           "44,857 excess-outcomes and loses its check",
        "refused_at": {"polymarket/soccer": (4, 44_857)},
        "board_note": None,
        "still_open_question": None,
        "sharpened_by": None,
    },
    {
        "session": "CAL-P120",
        "doc": "artifacts/cal-p120/RULE-DESIGN-odds-api-bookmaker-six-cells.md",
        "cells": [
            "odds_api_bookmaker/basketball_nba",
            "odds_api_bookmaker/baseball_mlb_preseason",
            "odds_api_bookmaker/icehockey_nhl",
            "odds_api_bookmaker/basketball_wncaab",
            "odds_api_bookmaker/basketball_wnba",
            "odds_api_bookmaker/basketball_euroleague",
        ],
        "disposition": "not established",
        "mode": "unit-of-observation correction",
        "searched": "all six cells re-folded at game grain instead of "
                    "bookmaker-row grain",
        "refuting_number": "every one of the six falls below the board's own "
                           "SIGMA_GATE = 2.0 once the unit is a game (measured "
                           "sigma 0.62-1.72); 82,345 of 478,677 excess-outcomes "
                           "(17.2%) are an artifact of counting one game 10-18x",
        "refused_at": {
            # CAL-P120 states the six as a block (82,345 of 478,677) and does not
            # publish a per-cell rank/excess table, so per-cell figures are absent
            # rather than back-computed.
        },
        "board_note": "🔴 refused as NOT ESTABLISHED and still seated: six of the "
                      "twenty live seats, including rank 5. A refusal that the "
                      "board never acted on is the loudest thing this register "
                      "can show — the conveyor still ranks these cells above "
                      "cells nobody has searched",
        "still_open_question": None,
        "sharpened_by": None,
    },
    {
        "session": "CAL-P123",
        "doc": "artifacts/cal-p123/RULE-DESIGN-polymarket-cricket.md",
        "cells": ["polymarket/cricket"],
        "disposition": "no rule exists",
        "mode": "two-partition enumeration",
        "searched": "1,971 candidate rules — all 127 non-empty name-family subsets "
                    "and all 1,844 shape x price-sum subsets retaining >=300 rows, "
                    "exhaustive",
        "refuting_number": "not one of the 1,971 brings the cell under 3.0; the "
                           "best lands at 4.96 while deleting 29% of the cell, and "
                           "the best family rule at 5.45 while deleting 76%",
        "refused_at": {"polymarket/cricket": (10, 16_618)},
        "board_note": None,
        "still_open_question": "D14 (whether the VENUE is wrong rather than us)",
        "sharpened_by": None,
    },
    {
        "session": "CAL-P127",
        "doc": "artifacts/cal-p127/RULE-DESIGN-kalshi-golf.md",
        "cells": ["kalshi/golf"],
        "disposition": "not established",
        "mode": "eight partitions + sigma correction",
        "searched": "eight partitions exhaustively, NO RULE BANKED",
        "refuting_number": "measured sigma 1.42 (cluster bootstrap) against "
                           "SIGMA_GATE 2.0 — the cell is not established and the "
                           "document recommends taking it OFF the board (17-CAL)",
        "refused_at": {"kalshi/golf": (9, 18_040)},
        "board_note": "🔴 recommended OFF the board by its own refusal and still "
                      "seated at rank 7 — the recommendation is 17-CAL and is "
                      "unanswered",
        "still_open_question": "17-CAL",
        "sharpened_by": None,
    },
    {
        "session": "CAL-P129",
        "doc": "artifacts/cal-p129/RULE-DESIGN-kalshi-entertainment.md",
        "cells": ["kalshi/entertainment"],
        "disposition": "no rule exists",
        "mode": "holdout",
        "searched": "12 partitions, no retention floor",
        "refuting_number": "sumband's 33 pooled passes go to 0 of 1023 under the "
                           "holdout; best worst-half 3.09 vs a 3.0 bar",
        "refused_at": {"kalshi/entertainment": (8, 18_465)},
        "board_note": None,
        "still_open_question": "13-CAL",
        "sharpened_by": (
            "CAL-P143 measured the lost-loss class here: 395 published at 100.0% "
            "winners is really 827 at 47.8%, and the cell headline moves "
            "5.21 -> 6.30, i.e. WORSE. This is the cell D13's 'the fix makes the "
            "number worse' framing was written on — and it is one of two that go "
            "the wrong way out of four measured. "
            "artifacts/cal-p143/GENERALITY-12CAL.md"
        ),
    },
    {
        "session": "CAL-P130",
        "doc": "artifacts/cal-p130/RULE-DESIGN-polymarket-golf.md",
        "cells": ["polymarket/golf"],
        "disposition": "no rule exists",
        "mode": "retention",
        "searched": "15 partitions (14 inherited + 1 built), exhaustive",
        "refuting_number": "no subset clears the bar at any retention; the cell "
                           "shows ~100 golfers each priced ~48% to finish top five",
        "refused_at": {"polymarket/golf": (12, 15_834)},
        "board_note": None,
        "still_open_question": None,
        "sharpened_by": None,
    },
    {
        "session": "CAL-P131",
        "doc": "artifacts/cal-p131/RULE-DESIGN-polymarket-economics.md",
        "cells": ["polymarket/economics"],
        "disposition": "no rule exists",
        "mode": "no structural dimension",
        "searched": "16 partitions (15 inherited + 1 built), exhaustive",
        "refuting_number": "508 outcomes the curve admits only because they won; "
                           "an 11-band S&P market prices both tails at 40%",
        "refused_at": {"polymarket/economics": (15, 11_594)},
        "board_note": None,
        "still_open_question": None,
        # CAL-P144: the refusal stands, but its headline number has since been
        # re-measured one predicate earlier and is 6.5x smaller. Carried here
        # because the next session to reach this cell will otherwise size the
        # repair off 508 — which is the raw base rate, not the repair size.
        "sharpened_by": (
            "CAL-P143 ran CAL-P131's lead on the producer's own chain: 78 eligible "
            "losers UNIQUELY dropped (not 508), ECE 39.87, winrate 0.0%; the cell "
            "moves 3.90 -> 3.68, i.e. BETTER. "
            "artifacts/cal-p143/GENERALITY-12CAL.md"
        ),
    },
    {
        "session": "CAL-P132",
        "doc": "artifacts/cal-p132/RULE-DESIGN-polymarket-tech.md",
        "cells": ["polymarket/tech"],
        "disposition": "no rule exists",
        "mode": "exhaustive lattice",
        "searched": "17 partitions, whole 2^k lattice at --min-rows 1 --min-share 0",
        "refuting_number": "zero subsets clear 3.0 on the worst half at ANY "
                           "retention, including retentions that delete 99% of the "
                           "cell; best leakage-free 3.12 / 4.66",
        # The document states the rank and not the excess; the excess is left
        # absent rather than reconstructed from a later render.
        "refused_at": {"polymarket/tech": (19, None)},
        "board_note": "was rank 19 when refused (CAL-P132) and CAL-P143 recorded it "
                      "as having LEFT the board; the live board has it back at rank "
                      "19. Board membership oscillates — do not treat one render's "
                      "absence as a resolution",
        "still_open_question": None,
        "sharpened_by": None,
    },
]

#: Every OTHER `RULE-DESIGN-*.md` on disk, with the disposition its own header
#: declares. This exists so the reconciliation below can tell "not a refusal" from
#: "a refusal nobody registered" — without it, the scan would have to guess, and a
#: register that guesses is worse than one that is merely incomplete.
NON_REFUSALS: dict[str, str] = {
    "artifacts/cal-p112/RULE-DESIGN-kalshi-tech.md":
        "BANKED — designed, benched, holdout-validated; NOT built",
    "artifacts/cal-p112/RULE-DESIGN-polymarket-esports.md":
        "BANKED — designed, benched, holdout-validated; NOT built",
    "artifacts/cal-p114/RULE-DESIGN-kalshi-economics.md":
        "RULED BY ALEX 2026-08-28, option (b) APPROVED WITH DISCLOSURE; landable, "
        "NOT built — ships when ruling 009's amended freeze lifts",
    "artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md":
        "BANKED — designed, benched, holdout-validated; NOT built",
    "artifacts/cal-p121/RULE-DESIGN-kalshi-crypto.md":
        "BANKED — designed, benched, holdout-split; NOT built",
    "artifacts/cal-p122/RULE-DESIGN-kalshi-entertainment.md":
        "DIAGNOSIS, no rule banked — SUPERSEDED as the refusal of record by "
        "CAL-P129, which searched the same cell exhaustively",
    "artifacts/cal-p124/RULE-DESIGN-polymarket-basketball.md":
        "BLOCKED on the instrument (rail reached 64% of the cell) — SUPERSEDED by "
        "CAL-P125, which fixed the rail and measured it",
    "artifacts/cal-p125/RULE-DESIGN-polymarket-basketball.md":
        "CANDIDATE, not banked — a one-arm rule at 2.60 pp benched on a population "
        "16-CAL says double-counts 43.44% of its rows; needs one re-bench",
    "artifacts/cal-p143/RULE-DESIGN-12CAL-lost-losses.md":
        "BUILT, verified, NOT applied — the D13 pre-build; ruling 009's freeze holds",
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


def reconcile_docs() -> tuple[list[str], list[str]]:
    """Every rule-design document on disk must be registered, one way or the other.

    Returns (problems, unregistered). The scan is over the filesystem rather than
    over this file's own tables, which is the entire point: a table can only report
    what someone remembered to put in it.
    """
    registered = {r["doc"] for r in REFUSALS} | set(NON_REFUSALS)
    on_disk = sorted(
        str(p.relative_to(REPO))
        for p in REPO.glob("artifacts/*/RULE-DESIGN-*.md")
    )
    unregistered = [d for d in on_disk if d not in registered]
    problems = [
        f"{d}: a rule-design document on disk that this register does not classify "
        f"— add it to REFUSALS or NON_REFUSALS with a citation"
        for d in unregistered
    ]
    # The mirror direction: a registered non-refusal whose file has gone away.
    for d in sorted(NON_REFUSALS):
        if not (REPO / d).exists():
            problems.append(f"{d}: registered as a non-refusal but not on disk")
    return problems, unregistered


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorecard", help="read a banked scorecard render instead "
                                        "of going live")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.scorecard:
        text = pathlib.Path(args.scorecard).read_text()
    else:
        # CAL-P144 🔴 — this path had never run. The scorecard REQUIRES ``--live``;
        # invoked bare it exits 2 with empty stdout, and the old code read neither
        # the return code nor stderr. ``read_board`` then parsed "" into {}, every
        # refusal rendered OFF THE BOARD, and the register invented three holes and
        # exited 4 — a fail-open instrument reporting a maximally alarming result
        # from a total absence of data. Gotcha #124: read the exit code's VALUE.
        # Gotcha #53: an empty read is a shape, not an absence.
        proc = subprocess.run([sys.executable, SCORECARD, "--live"], cwd=REPO,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(
                f"scorecard exited {proc.returncode}; the board was NOT read. "
                "Refusing to render — an unread board is not an empty board.\n"
                f"  {(proc.stderr or '').strip().splitlines()[-1:] or ['(no stderr)']}"
            )
        text = proc.stdout
    board = read_board(text)
    if not board:
        # The same refusal one layer down: a parse that yields zero cells means the
        # scorecard's rendering moved, not that the queue emptied.
        raise SystemExit(
            "board parsed to ZERO queued cells — that is the scorecard's format "
            "having moved, not an empty queue. Refusing to report every refusal "
            "as OFF THE BOARD on no evidence."
        )

    problems, _ = reconcile_docs()
    rows = []
    for r in REFUSALS:
        doc_exists = (REPO / r["doc"]).exists()
        if not doc_exists:
            problems.append(f"{r['session']}: cited document {r['doc']} is not on disk")
        for cell in r["cells"]:
            seat = board.get(cell)
            if seat is None and not r["board_note"]:
                problems.append(f"{cell}: refused, off the board, and no reason "
                                f"recorded for why it left")
            was = r["refused_at"].get(cell)
            rows.append({**{k: v for k, v in r.items() if k != "cells"},
                         "cell": cell,
                         "on_board": seat is not None,
                         "rank": seat["rank"] if seat else None,
                         "excess_outcomes": seat["excess_outcomes"] if seat else None,
                         "rank_at_refusal": was[0] if was else None,
                         "excess_at_refusal": was[1] if was else None,
                         "doc_exists": doc_exists})

    refused_seats = [r for r in rows if r["on_board"]]
    refused_excess = sum(r["excess_outcomes"] for r in refused_seats)
    board_excess = sum(c["excess_outcomes"] for c in board.values())

    if args.json:
        print(json.dumps({"refusals": rows, "problems": problems,
                          "board_cells": len(board),
                          "refused_seats": len(refused_seats),
                          "refused_excess": refused_excess,
                          "board_excess": board_excess}, indent=1))
        return 4 if problems else 0

    print("CAL-P145 REFUSAL REGISTER (live board) — every documented refusal, and "
          "where each cell now sits")
    print(f"  board read: {len(board)} queued cells   "
          f"refusal documents: {len(REFUSALS)}   cells refused: {len(rows)}\n")
    print(f"  {'cell':<42} {'session':<9} {'disposition':<16} "
          f"{'refused at':<14} {'board now':<14} excess now")
    for row in sorted(rows, key=lambda r: (r["rank"] is None, r["rank"] or 0)):
        seat = f"rank {row['rank']}" if row["on_board"] else "OFF THE BOARD"
        was = (f"rank {row['rank_at_refusal']}" if row["rank_at_refusal"]
               else "-")
        excess = f"{row['excess_outcomes']:,}" if row["excess_outcomes"] else "-"
        print(f"  {row['cell']:<42} {row['session']:<9} {row['disposition']:<16} "
              f"{was:<14} {seat:<14} {excess:>10}")
    print()

    for r in REFUSALS:
        cells = ", ".join(r["cells"]) if len(r["cells"]) <= 2 else (
            f"{r['cells'][0]} + {len(r['cells']) - 1} more")
        print(f"  {r['session']} — {cells}  [{r['disposition']}]")
        print(f"      searched: {r['searched']}")
        print(f"      {r['refuting_number']}")
        print(f"      {r['doc']}")
        if r["board_note"]:
            print(f"      {r['board_note']}")
        if r["still_open_question"]:
            print(f"      waits on {r['still_open_question']}")
        if r.get("sharpened_by"):
            # A refusal is durable; the NUMBER it was refused on may not be. When a
            # later session re-measures the same cell, the register carries both —
            # never the old number alone, and never the new one without saying the
            # refusal itself still stands.
            print(f"      SHARPENED (refusal stands): {r['sharpened_by']}")
    print()

    off = [r for r in rows if not r["on_board"]]
    pct = 100.0 * refused_excess / board_excess if board_excess else 0.0
    print(f"  ON the board: {len(refused_seats)} of {len(board)} live seats   "
          f"OFF the board: {len(off)} of {len(rows)} refused cells")
    print(f"  Excess-outcomes under a documented refusal: "
          f"{refused_excess:,} of {board_excess:,} ({pct:.1f}%)")
    print("  🔴 A seat under a documented refusal is a seat the conveyor's step 1 "
          "will select and then decline. That is the empty-set selection in "
          "alex-inbox/calibration-908, shown as a number rather than asserted.")
    if off:
        print(f"  🔴 hold-ledger.py reads the board, so it cannot show the "
              f"{len(off)} refused cell(s) that are off it. A hold that leaves the "
              "board is resolved; a refusal that leaves the board is still a "
              "refusal.")
    for p in problems:
        print(f"  🔴 {p}")
    print("\n  EXIT " + ("4 — the register has a hole" if problems else "0"))
    return 4 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
