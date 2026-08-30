#!/usr/bin/env python3
"""CAL-P140 — the hold ledger: which unanswered question is blocking how much, and
has the conveyor's step 1 got a legal answer yet?

WHAT THIS IS FOR
----------------
The conveyor directive's step 1 is *"take the highest-excess cell that has no
banked ready-to-land rule design yet"*. It has selected the empty set for seven
sessions, because every cell in the top 19 is banked, refused, held or switched
off. `alex-inbox/calibration-908` says so in prose. Prose is why each session
pays to rediscover it.

This is that prose as an instrument, and it does two things prose cannot:

1. **It ranks the holds by what they cost.** Each held cell carries an excess-
   outcome count that moves every time the board is rebuilt. Grouping the live
   counts by the question each cell waits on turns "five cells are held" into
   "answering X unblocks N outcomes" — which is the form the question has to be
   in before it is worth Alex's attention.

2. 🔴 **It is a SENSOR, not a report.** The moment a cell appears in the live
   top-19 with no disposition on file, step 1 has a legal answer again and the
   conveyor can move. Nothing watches for that today; a session notices by
   reading the scorecard and remembering. `EXIT 3` is that signal, so a caller
   can act on it without parsing anything.

WHY THE DISPOSITIONS ARE A LITERAL IN THIS FILE
------------------------------------------------
They are judgments recorded across a dozen artifacts and rulings, not a column in
any table, and there is no honest way to derive them at runtime. So they are
declared here, each with the document that establishes it, and the map is
verified against the live board on every run rather than trusted:

* a cell on the board with no entry -> `UNDISPOSED` (the sensor above);
* an entry naming a cell no longer on the board -> `STALE`, reported, never
  silently dropped, because a cell that left the top 19 is either fixed or the
  board moved under the ledger and both are worth knowing.

Neither condition is an error in the data. Both are findings about the ledger.

USAGE
-----
    source ~/.claude/.env && python3 artifacts/cal-p140/hold-ledger.py
    python3 artifacts/cal-p140/hold-ledger.py --json

Exit codes: 0 every queued cell disposed · 3 at least one UNDISPOSED cell (step 1
has a legal answer) · 2 could not measure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

BANKED = "banked"
REFUSED = "refused_with_measurement"
HELD = "held_on_alex"
OFF = "off_by_ruling"

#: cell -> (disposition, question or None, the document that establishes it).
#:
#: "Question" is the open Alex item the cell waits on. `None` means the cell is
#: not waiting on anybody — a banked design waits on the freeze, and a refused
#: cell waits on nothing at all because the refusal IS the finding.
DISPOSITIONS: dict[str, tuple[str, str | None, str]] = {
    "polymarket/baseball": (BANKED, None, "banked rule design; CAL-P139 §4 flags its outcome double-count"),
    "kalshi/economics": (BANKED, None, "banked rule design (also refused at the outcome site)"),
    "polymarket/esports": (BANKED, None, "banked rule design; E2's origin, the 453/453 claim"),
    "kalshi/crypto": (BANKED, None, "banked rule design (also refused at the outcome site)"),
    "kalshi/tech": (BANKED, None, "CAL-P132 — banked; a third of the category is podcast word bingo"),

    "kalshi/entertainment": (REFUSED, "13-CAL", "CAL-P122 §6i — every passing policy deletes the filtered class; 13-CAL HOLDs RULE E2 behind 12-CAL"),
    "polymarket/golf": (REFUSED, None, "refused with measurement"),
    "polymarket/economics": (REFUSED, None, "refused with measurement"),

    "polymarket/soccer": (HELD, "19-CAL", "CAL-P128 FINDING-sigma-sweep — NOT ESTABLISHED, recommend off the board"),
    "kalshi/golf": (HELD, "17-CAL", "CAL-P127 RULE-DESIGN §17-CAL — not established, measured sigma 1.42; CAL-P128 confirms independently at 1.48"),
    "polymarket/cricket": (HELD, "14-CAL", "CAL-P123 — all 1,971 candidate rules searched, none reaches bar"),
    # CAL-P141 measured both of these. The divergence that held them is a
    # duplicate-ROW count, not missing data: in both cells the replica sees every
    # outcome the payload publishes (outcome coverage 1.0009 and 1.0042) and
    # simply does not reproduce the payload's duplicate rows. So neither cell is
    # waiting to be EXPLAINED any more — both are waiting on the same phantom
    # REPAIR, which is the outcome-grain dedup on alex-inbox/calibration-911.
    "polymarket/basketball": (HELD, "20-CAL", "CAL-P128 FINDING-sigma-sweep — 43.44% phantom; CAL-P141 measured rowcov 0.6424 / outcov 1.0009, so the hold is the dedup, not an explanation"),
    "polymarket/hockey": (HELD, "20-CAL", "CAL-P128 filed this as 21-CAL; CAL-P141 measured it at 26.79% phantom, rowcov 0.7799 / outcov 1.0042 — the same mechanism as basketball, so it folds into 20-CAL"),

    "odds_api_bookmaker/basketball_nba": (OFF, None, "CAL-P120 §6g"),
    "odds_api_bookmaker/baseball_mlb_preseason": (OFF, None, "CAL-P120 §6g"),
    "odds_api_bookmaker/icehockey_nhl": (OFF, None, "CAL-P120 §6g"),
    "odds_api_bookmaker/basketball_wncaab": (OFF, None, "CAL-P120 §6g"),
    "odds_api_bookmaker/basketball_wnba": (OFF, None, "CAL-P120 §6g"),
    "odds_api_bookmaker/basketball_euroleague": (OFF, None, "CAL-P120 §6g"),
}

#: Banked designs whose rule text says a HELD rule ships WITH them, so the hold
#: blocks their LANDING even though the cell itself is not held. This is the
#: leverage that a disposition-only view misses entirely: a banked design that
#: cannot land is worth the same as a held cell on the day the freeze lifts.
#:
#: Both entries are verified against the design's own shipping clause, not
#: inferred from the rule being mentioned. `polymarket/basketball` mentions E2
#: only as a cross-cell check and is deliberately absent.
LANDING_BLOCKED: dict[str, list[tuple[str, str]]] = {
    "13-CAL": [
        ("polymarket/esports",
         "artifacts/cal-p112/RULE-DESIGN-polymarket-esports.md:170 — "
         "'E, E2 and E3 ship together or the cell is worked twice'"),
        ("kalshi/economics",
         "artifacts/cal-p114/RULE-DESIGN-kalshi-economics.md:381 — "
         "'E, E2, E3 and the (source, category) keying ship together'"),
    ],
}

#: Question -> what answering it releases, and what it depends on. Recorded so
#: the ranking below is not read as a pure excess-outcome sort: a question with
#: an unmet prerequisite cannot be answered first however much it blocks.
QUESTIONS: dict[str, dict] = {
    "12-CAL": {
        "summary": "the curve publishes winners and drops losers for lone claims — "
                   "clean_vms' `has_winner >= 1` drops 432 authoritative graded losses "
                   "and keeps 395 winners",
        "blocks": "13-CAL, and the true value of every cell whose population it filters",
        "depends_on": None,
        "note": "a producer change under freeze, so it is a ruling and not a lane's call; "
                "the recommended option makes the headline WORSE",
        "source": "CALIBRATION-SCORECARD.md — 'Owed to Alex', item 1",
    },
    "13-CAL": {
        "summary": "HOLD RULE E2 — its stated justification ('100% winners is one-sided "
                   "capture') is measured false: the capture is two-sided, the filter is not",
        "blocks": "kalshi/entertainment",
        "depends_on": "12-CAL",
        "note": "must not land before 12-CAL is decided",
        "source": "CALIBRATION-SCORECARD.md — 'Owed to Alex', item 2",
    },
    "14-CAL": {"summary": "polymarket/cricket admits no rule at all — 1,971 candidates searched exhaustively",
               "blocks": "polymarket/cricket", "depends_on": None, "note": None,
               "source": "artifacts/cal-p123/RULE-DESIGN-polymarket-cricket.md"},
    "17-CAL": {"summary": "kalshi/golf is not established (sigma 1.42, confirmed 1.48) — take it off the board",
               "blocks": "kalshi/golf", "depends_on": None, "note": None,
               "source": "artifacts/cal-p127/RULE-DESIGN-kalshi-golf.md"},
    "19-CAL": {"summary": "polymarket/soccer is not established — same precedent as the six CAL-P120 removed",
               "blocks": "polymarket/soccer", "depends_on": None, "note": None,
               "source": "artifacts/cal-p128/FINDING-sigma-sweep.md"},
    "20-CAL": {"summary": "polymarket/basketball AND polymarket/hockey are scored over "
                          "43.44%- and 26.79%-duplicate rows — both need the outcome-grain "
                          "dedup, neither needs a further explanation",
               "blocks": "polymarket/basketball, polymarket/hockey",
               "depends_on": None,
               "note": "CAL-P141 absorbed 21-CAL into this. It is the same mechanism in both "
                       "cells and the repair is the dedup on alex-inbox/calibration-911, so "
                       "answering it twice would double-count the question, not the outcomes",
               "source": "artifacts/cal-p128/FINDING-sigma-sweep.md + "
                         "artifacts/cal-p141/reconcile-duplication.json"},
    # 21-CAL is deliberately absent, not deleted-and-forgotten: CAL-P128 filed it
    # as "routing note, no decision" pending exactly the measurement CAL-P141 ran
    # (`cell-polymarket-hockey.json`). It asked whether hockey's 0.780 was
    # basketball's cause or a second one; it is basketball's cause. A routing note
    # discharges on its measurement, so there is nothing left for Alex to answer —
    # and leaving it on the board would show a hold nobody can clear.
}

SCORECARD = "backend/scripts/calibration_scorecard.py"


def read_queued_cells(scorecard_text: str) -> list[dict]:
    """Parse the QUEUED CELLS block off the scorecard's own rendered output.

    Parsed rather than recomputed on purpose: the ranking this ledger is about
    is the one the conveyor reads, so it must come from the same renderer. A
    second implementation could disagree with the board and be right, and being
    right about a different board is exactly the failure this avoids.
    """
    cells, started = [], False
    for line in scorecard_text.splitlines():
        if line.startswith("QUEUED CELLS"):
            started = True
            continue
        if not started:
            continue
        stripped = line.strip()
        if not stripped:
            if cells:
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
        excess = int(tail.split("excess-outcomes=")[1].strip().replace(",", ""))
        ece = float(tail.split("ece=")[1].split()[0])
        n = int(tail.split("n=")[1].split()[0].replace(",", ""))
        cells.append({"rank": rank, "cell": name, "excess_outcomes": excess,
                      "ece": ece, "n": n})
    return cells


def build(cells: list[dict]) -> dict:
    rows, undisposed = [], []
    for cell in cells:
        entry = DISPOSITIONS.get(cell["cell"])
        if entry is None:
            undisposed.append(cell["cell"])
            rows.append({**cell, "disposition": "UNDISPOSED", "question": None,
                         "source": None})
            continue
        disposition, question, source = entry
        rows.append({**cell, "disposition": disposition, "question": question,
                     "source": source})

    on_board = {c["cell"] for c in cells}
    stale = sorted(name for name in DISPOSITIONS if name not in on_board)

    by_question: dict[str, dict] = {}
    for row in rows:
        q = row["question"]
        if q is None:
            continue
        slot = by_question.setdefault(
            q, {"question": q, "cells": [], "excess_outcomes": 0, **QUESTIONS.get(q, {})}
        )
        slot["cells"].append(row["cell"])
        slot["excess_outcomes"] += row["excess_outcomes"]

    # Banked designs a hold prevents from LANDING. Counted separately from the
    # cells the hold blocks outright, because they are different states of the
    # world — one is work not yet done, the other is work done and stuck — and
    # summing them into one figure would hide which is which.
    excess_by_cell = {c["cell"]: c["excess_outcomes"] for c in cells}
    for question, entries in LANDING_BLOCKED.items():
        slot = by_question.setdefault(
            question, {"question": question, "cells": [], "excess_outcomes": 0,
                       **QUESTIONS.get(question, {})}
        )
        landing = [
            {"cell": cell, "excess_outcomes": excess_by_cell[cell], "source": source}
            for cell, source in entries
            if cell in excess_by_cell
        ]
        slot["landing_blocked"] = landing
        slot["excess_outcomes_landing"] = sum(e["excess_outcomes"] for e in landing)

    def weight(slot):
        return (slot.get("excess_outcomes", 0)
                + slot.get("excess_outcomes_landing", 0)
                + slot.get("excess_outcomes_transitive", 0))

    # 12-CAL blocks nothing on the board DIRECTLY — it blocks 13-CAL, which
    # blocks both a cell and two banked designs. Credit it with everything its
    # dependents carry, flagged as transitive so it is never read as a direct
    # block. It is the root of the biggest branch and it must not rank last
    # merely because nothing points at it by name.
    transitive = sum(
        weight(slot) for slot in by_question.values()
        if slot.get("depends_on") == "12-CAL"
    )
    if transitive:
        by_question.setdefault(
            "12-CAL", {"question": "12-CAL", "cells": [], "excess_outcomes": 0,
                       **QUESTIONS["12-CAL"]}
        )
        by_question["12-CAL"]["excess_outcomes_transitive"] = transitive

    ranked = sorted(by_question.values(), key=lambda s: -weight(s))

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1

    return {
        "instrument": "CAL-P140 hold ledger",
        "queued_cells": len(cells),
        "disposition_counts": counts,
        "undisposed_cells": undisposed,
        "step1_has_a_legal_answer": bool(undisposed),
        "stale_dispositions": stale,
        "questions_ranked": ranked,
        "cells": rows,
    }


def render(result: dict) -> str:
    lines = [
        "CAL-P140 HOLD LEDGER — the conveyor's step 1, as a number",
        f"  {result['queued_cells']} queued cells: "
        + ", ".join(f"{n} {k}" for k, n in sorted(result["disposition_counts"].items())),
        "",
        "  STEP 1 — 'the highest-excess cell with no banked design yet':",
    ]
    if result["step1_has_a_legal_answer"]:
        lines += [
            "  🟢 IT HAS A LEGAL ANSWER AGAIN: " + ", ".join(result["undisposed_cells"]),
            "     The conveyor can move. Work the highest-ranked one.",
        ]
    else:
        lines += [
            "  🔴 SELECTS THE EMPTY SET. Every queued cell is banked, refused, held or off.",
            "     This is calibration-908's finding, re-measured against the live board.",
        ]
    if result["stale_dispositions"]:
        lines += [
            "",
            "  ⚠️  dispositions on file for cells no longer on the board (fixed, or the "
            "board moved):",
            "      " + ", ".join(result["stale_dispositions"]),
        ]
    lines += ["", "  WHAT EACH UNANSWERED QUESTION IS BLOCKING, biggest first:"]
    for slot in result["questions_ranked"]:
        direct = slot["excess_outcomes"]
        landing = slot.get("excess_outcomes_landing", 0)
        trans = slot.get("excess_outcomes_transitive", 0)
        total = direct + landing + trans
        lines.append(f"    {slot['question']:<8} {total:>10,} total   "
                     f"{', '.join(slot['cells']) or '(no cell directly)'}")
        if slot.get("summary"):
            lines.append(f"             {slot['summary'][:110]}")
        if direct:
            lines.append(f"             {direct:>10,}  cell blocked outright")
        for entry in slot.get("landing_blocked", []):
            lines.append(f"             {entry['excess_outcomes']:>10,}  banked design cannot LAND: "
                         f"{entry['cell']}")
        if trans:
            lines.append(f"             {trans:>10,}  transitive, via its dependents")
        if slot.get("depends_on"):
            lines.append(f"             ⛔ cannot be answered before {slot['depends_on']}")
    lines += ["", "  the board, by disposition:"]
    for row in result["cells"]:
        q = f"  [{row['question']}]" if row["question"] else ""
        lines.append(
            f"    {row['rank']:>2}. {row['cell']:<42} {row['excess_outcomes']:>8,}  "
            f"{row['disposition']}{q}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--scorecard", help="read a banked scorecard instead of going live")
    args = ap.parse_args(argv)

    if args.scorecard:
        with open(args.scorecard) as fh:
            text = fh.read()
    else:
        if not os.environ.get("BAINLUCK_API") or not os.environ.get("ADMIN_TOKEN"):
            print("BAINLUCK_API and ADMIN_TOKEN required (source ~/.claude/.env)",
                  file=sys.stderr)
            return 2
        proc = subprocess.run([sys.executable, SCORECARD, "--live"],
                              capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            print(f"scorecard failed ({proc.returncode}): {proc.stderr[:400]}",
                  file=sys.stderr)
            return 2
        text = proc.stdout

    cells = read_queued_cells(text)
    if not cells:
        # gotcha #53 again: no QUEUED CELLS block is a parse failure or a board
        # with nothing queued, and those mean opposite things. Refuse to guess.
        print("no QUEUED CELLS block found in the scorecard output — that is a parse "
              "failure or an empty board, and this cannot tell which", file=sys.stderr)
        return 2

    result = build(cells)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 3 if result["step1_has_a_legal_answer"] else 0


if __name__ == "__main__":
    sys.exit(main())
