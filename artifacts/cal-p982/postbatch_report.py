"""CAL-P982 — the first honest post-batch number, q268 -> q269.

Runs the ratified scorecard against the freshly published curve and diffs it
against the banked q268 baseline (2026-08-31T04:37:36Z, 31/49, 1.86 pp).

Why the diff is not just "ECE went up/down": q269 REMOVES 21.66% of the
population on purpose (crypto 4,625 -> 0 is D12, the ruling). A cell that
vanishes is a mover — arguably the biggest kind — and a report that only
compares cells present in both silently drops exactly the cells the bump was
for. So cells are classified DROPPED / NEW / MOVED, and DROPPED is ranked by
the outcomes it took with it, not by an ECE delta it no longer has.

Usage:  python3 artifacts/cal-p982/postbatch_report.py           # scores live
        python3 artifacts/cal-p982/postbatch_report.py --payload FILE
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HISTORY = REPO / "artifacts/calibration-scorecard/history.jsonl"
BASELINE_AT = "2026-08-31T04:37:36.703361+00:00"


def load_baseline() -> dict:
    pts = [json.loads(x) for x in HISTORY.read_text().splitlines() if x.strip()]
    for p in pts:
        if p.get("generated_at") == BASELINE_AT and p["counts"].get("cells_at_bar") is not None:
            return p
    raise SystemExit(f"baseline {BASELINE_AT} not in {HISTORY}")


def score(payload: str | None) -> dict:
    """Run the ratified instrument. Never re-implement its fold (self_check is
    the warrant); shell out and read its JSON.

    Reads ``--out``, not stdout: stdout deliberately drops the ``cells`` key
    (``main`` filters it), and ``cells`` is the whole per-cell mover story.
    """
    out = Path(__file__).with_name("_scorecard-raw.json")
    cmd = [sys.executable, "scripts/calibration_scorecard.py", "--record", "--out", str(out)]
    cmd += ["--payload", payload] if payload else ["--live"]
    r = subprocess.run(cmd, cwd=REPO / "backend", capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"scorecard EXIT {r.returncode}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return json.loads(out.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload")
    args = ap.parse_args()

    base = load_baseline()
    new = score(args.payload)

    bc, nc = base["counts"], new["counts"]
    b_cells = base["material_cells"]
    n_cells = {
        c["cell"]: {"ece": c["ece"], "n": c["n"], "verdict": c["verdict"]}
        for c in new["cells"]
        if c["verdict"] != "EXEMPT_BELOW_MIN_N"
    }

    dropped = [(k, b_cells[k]) for k in b_cells if k not in n_cells]
    added = [(k, n_cells[k]) for k in n_cells if k not in b_cells]
    moved = []
    for k in b_cells:
        if k in n_cells and b_cells[k]["ece"] is not None and n_cells[k]["ece"] is not None:
            moved.append((k, b_cells[k], n_cells[k], n_cells[k]["ece"] - b_cells[k]["ece"]))

    dropped.sort(key=lambda x: -(x[1]["n"] or 0))
    added.sort(key=lambda x: -(x[1]["n"] or 0))
    moved.sort(key=lambda x: -abs(x[3]))

    out = {
        "baseline": {
            "generated_at": base["generated_at"],
            "population_version": base["population_version"],
            "cells_at_bar": bc["cells_at_bar"],
            "cells_material": bc["cells_material"],
            "headline_pp": base["headline_mce_closing_line"],
            "total_outcomes": base["total_outcomes"],
        },
        "new": {
            "generated_at": new["generated_at"],
            "population_version": new["population_version"],
            "cells_at_bar": nc["cells_at_bar"],
            "cells_material": nc["cells_material"],
            "headline_pp": new["headline_mce_closing_line"],
            "total_outcomes": new["total_outcomes"],
            "availability": new.get("availability"),
            "self_check": new.get("self_check"),
            "done": new.get("done"),
        },
        "delta": {
            "cells_at_bar": (nc["cells_at_bar"] or 0) - (bc["cells_at_bar"] or 0),
            "cells_material": nc["cells_material"] - bc["cells_material"],
            "headline_pp": round(
                (new["headline_mce_closing_line"] or 0)
                - (base["headline_mce_closing_line"] or 0),
                3,
            ),
            "total_outcomes": new["total_outcomes"] - base["total_outcomes"],
            "outcomes_removed_pct": round(
                100.0 * (base["total_outcomes"] - new["total_outcomes"]) / base["total_outcomes"], 2
            ),
        },
        "per_class": {"baseline": base["counts"], "new": new["counts"]},
        "movers": {
            "dropped": [{"cell": k, **v} for k, v in dropped],
            "new": [{"cell": k, **v} for k, v in added],
            "moved_top": [
                {"cell": k, "ece_before": b["ece"], "ece_after": n["ece"], "delta_pp": round(d, 2),
                 "n_before": b["n"], "n_after": n["n"],
                 "verdict_before": b["verdict"], "verdict_after": n["verdict"]}
                for k, b, n, d in moved[:12]
            ],
            "verdict_flips": [
                {"cell": k, "before": b["verdict"], "after": n["verdict"],
                 "ece_before": b["ece"], "ece_after": n["ece"]}
                for k, b, n, _ in moved
                if b["verdict"] != n["verdict"]
            ],
        },
        "per_class_new": new.get("per_class"),
        "measured_sigma_new": new.get("measured_sigma"),
        "needle": (
            f"NEEDLE: calibration {nc['cells_at_bar']}/{nc['cells_material']} "
            f"cells-at-bar @ {new['generated_at']}"
        ),
    }
    dest = Path(__file__).with_name("postbatch-q269.json")
    dest.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
