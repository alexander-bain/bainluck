"""Assert every branch of `verdict-2060.py`, including the unreachable ones.

## Why this exists

`proof-2060-defect-routes.sh` runs against a corpus with **zero post-deploy
rows**, and will keep doing so until Alex labels a card. Every routing assertion
in the verdict is therefore dead code from production's point of view, and dead
code that nobody executes is code that silently stops working. The push-verdict
rail hit this exactly: two of its six branches produced identical counters, and
only a synthetic run separated them.

So the decision logic is driven here over fixtures instead — no network, no
database, no admin token. Ten cases: four that mutate the half production CAN
reach (so the passing half is proved non-vacuous), five that mutate the half it
cannot, and one healthy state that must come out PASS. A suite where nothing
can fail is the failure this file exists to prevent, so the control case is
asserted too: unmutated live-shaped input must be UNKNOWN, not PASS.

Run: `tools/postdeploy/checks/proof-2060-defect-routes.sh --self-test`
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VERDICT = os.path.join(HERE, "verdict-2060.py")

PASS, FAIL, UNKNOWN = 0, 1, 3

ROW_COLS = [
    "post_rows",
    "post_eligible",
    "post_routed",
    "post_derived_ok",
    "post_auto_candidate",
    "post_stale_spelling",
    "all_rows",
    "all_with_fi",
]

#: The live shape as measured 2026-08-23: 88 rows, none of them post-deploy.
LIVE_ROWS = dict(
    post_rows=0,
    post_eligible=0,
    post_routed=0,
    post_derived_ok=0,
    post_auto_candidate=0,
    post_stale_spelling=0,
    all_rows=88,
    all_with_fi=0,
)
#: Pacific and UTC genuinely disagree today, which is what makes the meter's
#: day-bucket claim discriminable at all. A fixture where they agreed would
#: quietly convert the strongest assertion here into a no-op.
LIVE_DAYS = dict(pt_days=7, utc_days=6, total=88)
LIVE_PROGRESS = {
    "total": 88,
    "total_target": 250,
    "total_met": False,
    "today": 0,
    "daily_target": 20,
    "daily_met": False,
    "distinct_days": 7,
    "spread_target": 13,
    "spread_met": False,
    "streak": 0,
    "first_day": "2026-05-24",
    "last_day": "2026-08-20",
    "timezone": "America/Los_Angeles",
    "reviewer": None,
}


def clusters(total: int) -> dict:
    return {"status": "open", "total": total, "clusters": [{}] * total}


def routed_rows(**over) -> dict:
    """A corpus in which three eligible rows were written and all three routed."""
    base = dict(
        post_rows=5,
        post_eligible=3,
        post_routed=3,
        post_derived_ok=3,
        post_auto_candidate=0,
        post_stale_spelling=0,
        all_rows=91,
        all_with_fi=3,
    )
    base.update(over)
    return base


def run(rows: dict, days: dict, progress: dict, clus: dict) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        paths = []
        rows_doc = {"columns": ROW_COLS, "rows": [[rows[c] for c in ROW_COLS]]}
        days_doc = {"columns": list(days), "rows": [list(days.values())]}
        for name, doc in (
            ("rows", rows_doc),
            ("days", days_doc),
            ("progress", progress),
            ("clusters", clus),
            ("repair", {"total": clus["total"], "clusters": clus["clusters"]}),
        ):
            p = os.path.join(d, f"{name}.json")
            with open(p, "w") as fh:
                json.dump(doc, fh)
            paths.append(p)
        proc = subprocess.run(
            [sys.executable, VERDICT, *paths],
            capture_output=True,
            text=True,
            env={**os.environ, "CUTOFF": "2026-08-22T22:11:51-07:00"},
        )
        return proc.returncode, proc.stdout + proc.stderr


CASES: list[tuple[str, dict, dict, dict, dict, int, str]] = [
    # ── the control. If this is not UNKNOWN, every FAIL below proves nothing. ──
    (
        "M0 control — live shape, nothing mutated",
        LIVE_ROWS, LIVE_DAYS, LIVE_PROGRESS, clusters(0),
        UNKNOWN, "has had no input",
    ),
    # ── the half production CAN reach ─────────────────────────────────────────
    (
        "M1 /progress reports the UTC day bucket",
        LIVE_ROWS, LIVE_DAYS, {**LIVE_PROGRESS, "distinct_days": 6}, clusters(0),
        FAIL, "is the UTC bucket",
    ),
    (
        "M2 /progress declares the wrong timezone",
        LIVE_ROWS, LIVE_DAYS, {**LIVE_PROGRESS, "timezone": "UTC"}, clusters(0),
        FAIL, "not America/Los_Angeles",
    ),
    (
        "M3 /progress total drifts from the table",
        LIVE_ROWS, LIVE_DAYS, {**LIVE_PROGRESS, "total": 87}, clusters(0),
        FAIL, "!= 88 rows in the table",
    ),
    (
        "M4 a meter leg is deleted",
        LIVE_ROWS, LIVE_DAYS,
        {k: v for k, v in LIVE_PROGRESS.items() if k != "spread_target"}, clusters(0),
        FAIL, "missing the meter leg",
    ),
    (
        "M5 the two day buckets agree, so the claim is UNDISCRIMINABLE",
        LIVE_ROWS, dict(pt_days=7, utc_days=7, total=88), LIVE_PROGRESS, clusters(0),
        UNKNOWN, "cannot be discriminated",
    ),
    # ── the half production CANNOT currently reach ────────────────────────────
    (
        "R1 rows routed but the cluster rail is still empty",
        routed_rows(), LIVE_DAYS, LIVE_PROGRESS, clusters(0),
        FAIL, "still not filling",
    ),
    (
        "R2 only some eligible rows routed",
        routed_rows(post_routed=2, post_derived_ok=2, all_with_fi=2),
        LIVE_DAYS, LIVE_PROGRESS, clusters(1),
        FAIL, "only 2 of 3 eligible",
    ),
    (
        "R3 provenance drifts from the route",
        routed_rows(post_derived_ok=1), LIVE_DAYS, LIVE_PROGRESS, clusters(1),
        FAIL, "derived_from='reason_tags'",
    ),
    (
        "R4 create_issue_candidate inferred from a tap",
        routed_rows(post_auto_candidate=1), LIVE_DAYS, LIVE_PROGRESS, clusters(1),
        FAIL, "cried-wolf",
    ),
    (
        "R5 a fresh row stores an un-folded alias",
        routed_rows(post_stale_spelling=1), LIVE_DAYS, LIVE_PROGRESS, clusters(1),
        FAIL, "un-folded alias",
    ),
    (
        "R6 the healthy shipped state",
        routed_rows(), LIVE_DAYS, LIVE_PROGRESS, clusters(2),
        PASS, "#2060: PASS",
    ),
]


def main() -> int:
    name = {PASS: "PASS", FAIL: "FAIL", UNKNOWN: "UNKNOWN"}
    failures = 0
    print(f"verdict-2060 self-test — {len(CASES)} cases, no network, no database")
    for title, rows, days, progress, clus, want_rc, want_text in CASES:
        rc, out = run(rows, days, progress, clus)
        ok = rc == want_rc and want_text in out
        if not ok:
            failures += 1
        mark = "ok  " if ok else "FAIL"
        print(f"  {mark} {title}")
        print(f"        want {name.get(want_rc, want_rc)} containing {want_text!r}")
        print(f"        got  {name.get(rc, rc)}")
        if not ok:
            for line in out.strip().splitlines()[-8:]:
                print("        | " + line)
    print("")
    if failures:
        print(f"SELF-TEST FAIL: {failures} of {len(CASES)} cases")
        return 1
    print(f"SELF-TEST PASS: {len(CASES)}/{len(CASES)} branches asserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
