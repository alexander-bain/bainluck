#!/usr/bin/env python3
"""CAL-P144 — the freeze window's own beats, each against the bound it ran under.

``census-window-margin.py`` measures the mechanism over ~7 days. This joins it to
the ONE population that has already been classified by hand: the CAL-P140 freeze
window log, whose 16 beats carry an independently-derived ``class`` (CLEAN /
B_DIAGNOSTICS_TRUTH_CENSUS / C_DEPLOY_KILL) attributed from
``task-metrics.last_error`` at the time.

That makes this a blind check rather than a fit: the classes were assigned from
error text before ``staged:window_left_ms`` was ever looked at, so agreement
between the two is evidence and not construction.

Usage:  source ~/.claude/.env && python3 artifacts/cal-p144/window-beat-margins.py
Exit 0 = the join ran. Disagreements are PRINTED, not raised — a beat the model
gets wrong is the most valuable row here and must not be hidden behind a
non-zero exit (gotcha #124).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

PHASE_DEADLINE_MS = 1_380_000
CENSUS_MS_OBSERVED = 88_284
WINDOW_LOG = "artifacts/cal-p140/window-log.jsonl"
HISTORY_IDENTITY = "calibration:beat_gauge_history"

SQL = (
    "SELECT o->>'generated_at' AS generated_at, "
    "o->'gauges'->>'staged:window_left_ms' AS window_left_ms, "
    "o->>'terminal' AS terminal "
    "FROM durable_state_snapshots s, "
    "jsonb_array_elements(s.payload->'observations') o "
    f"WHERE s.identity = '{HISTORY_IDENTITY}' ORDER BY 1 DESC"
)


def statement_timeout_for(remaining_ms: int) -> int:
    """``_statement_timeout_for`` from the phase ledger, reproduced exactly."""
    gap = max(1, min(30_000, remaining_ms // 10))
    return max(1, remaining_ms - gap)


def read_history() -> dict[str, str]:
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise SystemExit("source ~/.claude/.env first — BAINLUCK_API/ADMIN_TOKEN unset")
    req = urllib.request.Request(
        api.rstrip("/") + "/api/admin/db-query",
        data=json.dumps({"sql": SQL, "limit": 900}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    rows = payload.get("rows") or []
    if not rows:
        # gotcha #53 — an empty 200 is a shape, not an absence.
        raise SystemExit(f"{HISTORY_IDENTITY} returned NO observations — sampler down")
    return {r[0][:19]: r[1] for r in rows}


def main() -> int:
    if not os.path.exists(WINDOW_LOG):
        raise SystemExit(f"{WINDOW_LOG} not found — run from the repo root")
    hist = read_history()
    beats = [json.loads(line) for line in open(WINDOW_LOG)]

    print("=" * 88)
    print("CAL-P144 — CAL-P140 freeze-window beats vs the bound the census ran under")
    print("=" * 88)
    print(f"census cost (measured, 1 obs): {CENSUS_MS_OBSERVED} ms")
    print()
    print(f"{'n':>3}  {'generated_at':<20}{'hand class':<28}"
          f"{'window_left':>12}{'bound':>10}{'margin':>10}  predicted")

    agree = disagree = ungauged = 0
    for b in beats:
        key = b["generated_at"][:19]
        raw = hist.get(key)
        cls = b.get("class", "?")
        if raw is None:
            print(f"{b['n']:>3}  {key:<20}{cls:<28}{'(no gauge)':>12}")
            ungauged += 1
            continue
        w = int(raw)
        bd = statement_timeout_for(w)
        margin = bd - CENSUS_MS_OBSERVED
        pred_b = margin < 0
        was_b = cls.startswith("B_")
        ok = pred_b == was_b
        agree += ok
        disagree += (not ok)
        flag = "class B" if pred_b else "survives"
        mark = "" if ok else "   <== MODEL WRONG"
        print(f"{b['n']:>3}  {key:<20}{cls:<28}{w:>12}{bd:>10}{margin:>10}  {flag}{mark}")

    total = agree + disagree
    print()
    print(f"gauged beats {total}   model agrees {agree}   disagrees {disagree}"
          f"   ungauged {ungauged}")
    if disagree:
        print("A disagreement is the finding. Do not quote the agreement rate without it.")

    print()
    print("The CLEAN beats with the least room, in ms of margin:")
    slim = []
    for b in beats:
        raw = hist.get(b["generated_at"][:19])
        if raw is None or not b.get("class", "").startswith("CLEAN"):
            continue
        slim.append((statement_timeout_for(int(raw)) - CENSUS_MS_OBSERVED, b["n"]))
    for m, n in sorted(slim)[:3]:
        print(f"   beat {n:>2}: cleared by {m} ms ({m/1000:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
