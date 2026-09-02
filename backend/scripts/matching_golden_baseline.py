#!/usr/bin/env python3
"""Record which golden pairs the matcher gets right today (#2706).

The golden set is a RATCHET, not a bar: only 39 of its 709 pairs pass today, so
the CI gate asserts "no pair that passes stops passing" rather than "all pairs
pass". This script writes the floor that gate compares against.

    python3 scripts/matching_golden_baseline.py            # show the diff
    python3 scripts/matching_golden_baseline.py --write     # record it

Run ``--write`` when a matching change makes pairs go GREEN. Never run it to
make a red CI go green: the whole point of the fail-on-improvement arm is that
an unrecorded improvement silently raises the floor, and the next regression
back down to it then goes unnoticed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.test_matching_golden_set_2706 import (  # noqa: E402
    BASELINE_PATH,
    GOLDEN_AS_OF,
    evaluate_all,
    load_inputs,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--reset",
        metavar="REASON",
        help=(
            "Re-record from scratch, accepting regressions. ONLY for a change "
            "to the REPLAY HARNESS itself (the fixture, the clock rule, the "
            "status derivation) — never for a change to the matcher. The "
            "reason is written into the baseline so the next reader can see "
            "why the floor moved."
        ),
    )
    args = ap.parse_args()

    inputs = load_inputs()
    actual = evaluate_all()
    by_market = {str(p["market_id"]): p for p in inputs["pairs"]}

    old = {}
    if BASELINE_PATH.exists():
        old = json.loads(BASELINE_PATH.read_text()).get("pairs", {})

    regressions = [m for m in old if old[m] and m in actual and not actual[m]]
    improvements = [m for m in old if not old[m] and m in actual and actual[m]]
    passing = sorted(m for m, ok in actual.items() if ok)

    print(f"pairs: {len(actual)}   passing: {len(passing)}")
    for label, ids in (("REGRESSED", regressions), ("IMPROVED", improvements)):
        if not ids:
            continue
        print(f"\n{label} ({len(ids)}):")
        for m in ids[:40]:
            p = by_market[m]
            print(f"  {m} [{p['failure_class']}] {p['title']!r} → {p['correct_event_id']}")

    if not args.write:
        print("\n(dry run — pass --write to record)")
        return 0

    if regressions and not args.reset:
        print(
            f"\nREFUSING to write: {len(regressions)} pair(s) regressed. "
            "Recording a regression as the new floor is how a ratchet stops "
            "being one. Fix the regression — or, if the REPLAY HARNESS changed "
            "rather than the matcher, re-record with --reset '<reason>'."
        )
        return 1

    BASELINE_PATH.write_text(json.dumps({
        "note": (
            "Which MATCHING-GOLDEN pairs the matcher gets right. A RATCHET "
            "floor, not a target: most pairs are the audit's open failure "
            "classes. Regenerate with scripts/matching_golden_baseline.py "
            "--write, and only ever upward."
        ),
        "source_file": inputs["source_file"],
        "reset_reason": args.reset,
        "anchor": "per-pair decision clock (see pair_as_of)",
        "fallback_as_of": GOLDEN_AS_OF.isoformat(),
        "pair_count": len(actual),
        "passing_count": len(passing),
        "pairs": dict(sorted(actual.items(), key=lambda kv: int(kv[0]))),
    }, indent=1) + "\n")
    print(f"\nwrote {BASELINE_PATH} — {len(passing)}/{len(actual)} passing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
