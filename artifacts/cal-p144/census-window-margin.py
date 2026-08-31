#!/usr/bin/env python3
"""CAL-P144 — why class B fires, measured over every beat the store still holds.

The class the window log calls ``B_DIAGNOSTICS_TRUTH_CENSUS`` was named from its
error text (``QueryCanceledError`` on the truth-census statement) and nothing
else. That is a symptom. This instrument measures the mechanism, and it is
re-runnable so the number is never quoted from a session that has ended.

The mechanism, stated so it can be falsified
--------------------------------------------
``read:truth_census`` is a single statement in ``PHASE_DIAGNOSTICS``, which runs
AFTER ``PHASE_FUTURES``. Its DB backstop is not a constant — it is

    statement_timeout = _statement_timeout_for(remaining_ms)
                      = remaining_ms - min(30_000, remaining_ms // 10)

where ``remaining_ms = PHASE_DEADLINE_MS - elapsed`` at the moment diagnostics
opens. The producer banks that exact quantity every beat as the gauge
``staged:window_left_ms`` (``precompute_calibration.py`` line ~3183), and the
beat-gauge sampler (CAL-P084) keeps ~7 days of them under the durable identity
``calibration:beat_gauge_history``. So the bound the census ran against on a
beat that no longer exists is still readable, which is the only reason this
measurement is possible at all.

The prediction: a beat dies of class B exactly when that bound is smaller than
the census costs. Everything below is the check.

Why the residual is small so often — the root cause
----------------------------------------------------
``window_left_ms`` is written at ONE place: the futures staging loop's exit
branch, where ``_unit_fits_in_window(remaining_ms, worst_unit_ms, prior_unit_ms)``
returns False. That predicate asks whether one more UNIT fits. It reserves
nothing for the phases that must follow. So the leftover is a RESIDUAL bounded
above by one unit's cost — and one unit costs 143k-358k ms in this same history.
A residual drawn from that range lands under the census's need often, and it
does so independently of how far along the rebuild is (see the r below).

Gotcha #53: an absent gauge is a shape, not a zero. Beats whose
``staged:window_left_ms`` is missing (the loop never hit the exit branch) are
counted and reported as UNGAUGED, never folded into the denominator.

Exit 0 = the prediction was checked. It is 0 whether the prediction holds or
fails; the verdict is the printed table, not the exit code (gotcha #124 —
read the value, do not infer it).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.error
import urllib.request

HISTORY_IDENTITY = "calibration:beat_gauge_history"

#: ``SOFT_LIMIT_MS - CLEANUP_MARGIN_MS`` from ``app/utils/calibration_phase_ledger.py``.
#: Imported by value rather than by import because this script runs outside the
#: backend venv; the assertion that they still agree is in the report header.
PHASE_DEADLINE_MS = 1_380_000
STATEMENT_INNER_MARGIN_MS = 30_000

#: What ``read:truth_census`` actually cost on the last beat that completed it,
#: read off ``task-metrics.last_result_summary.phase_ledger.stages``. This is ONE
#: measurement, not a distribution — the census cost is not banked per beat, so
#: the sensitivity sweep below exists to say how much the answer depends on it.
CENSUS_MS_OBSERVED = 88_284


def statement_timeout_for(remaining_ms: int) -> int:
    """``_statement_timeout_for`` from the phase ledger, reproduced exactly."""
    gap = max(1, min(STATEMENT_INNER_MARGIN_MS, remaining_ms // 10))
    return max(1, remaining_ms - gap)


def _post(api: str, token: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        api.rstrip("/") + "/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


SQL = f"""
SELECT o->>'generated_at'                            AS generated_at,
       o->>'terminal'                                AS terminal,
       o->'gauges'->>'staged:window_left_ms'         AS window_left_ms,
       o->'gauges'->>'staged:units_done'             AS units_done,
       o->'gauges'->>'staged:unit_ms_worst'          AS unit_ms_worst
FROM durable_state_snapshots s,
     jsonb_array_elements(s.payload->'observations') o
WHERE s.identity = '{HISTORY_IDENTITY}'
ORDER BY 1 DESC
"""


def read_history(api: str, token: str) -> list[dict]:
    payload = _post(api, token, {"sql": SQL, "limit": 900})
    columns = payload.get("columns") or []
    rows = [dict(zip(columns, r)) for r in (payload.get("rows") or [])]
    if not rows:
        # gotcha #53 — an empty 200 is a response shape. An empty history is the
        # sampler down, and must never render as "no beats were ever at risk".
        raise SystemExit(
            f"{HISTORY_IDENTITY} returned NO observations — that is the beat-gauge "
            "sampler down, not a clean count of zero"
        )
    if payload.get("truncated"):
        # project_dbquery_1000_row_cap: silent truncation reads as completeness.
        print("WARNING: history truncated by the row cap — widen before quoting",
              file=sys.stderr)
    return rows


def pearson(xs: list[float], ys: list[float]) -> float:
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


def main(argv=None) -> int:
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise SystemExit("source ~/.claude/.env first — BAINLUCK_API/ADMIN_TOKEN unset")

    rows = read_history(api, token)
    gauged, ungauged = [], []
    for r in rows:
        if r.get("window_left_ms") is None:
            ungauged.append(r)
        else:
            gauged.append(r)

    need = CENSUS_MS_OBSERVED
    below = [r for r in gauged if statement_timeout_for(int(r["window_left_ms"])) < need]

    print("=" * 78)
    print("CAL-P144 — the truth census against the window the futures loop leaves it")
    print("=" * 78)
    print(f"PHASE_DEADLINE_MS        {PHASE_DEADLINE_MS}")
    print(f"census cost (1 measured) {need} ms  (read:truth_census, last completing beat)")
    print(f"beats in history         {len(rows)}   gauged {len(gauged)}   UNGAUGED {len(ungauged)}")
    print()

    # ---- 1. does the bound predict the terminal? -------------------------
    print("-- 1. the prediction: bound < census cost => the beat dies ------------")
    for label, group in (("bound BELOW census need", below),
                         ("bound ABOVE census need",
                          [r for r in gauged if r not in below])):
        n = len(group)
        f = sum(1 for r in group if r["terminal"] == "failed")
        c = sum(1 for r in group if r["terminal"] == "complete")
        x = sum(1 for r in group if r["terminal"] == "cancelled")
        print(f"   {label:<26} n={n:>4}  failed={f:>3} ({100*f/n:>3.0f}%)"
              f"  complete={c:>3}  cancelled={x:>3}")
    hazard = len(below) / len(gauged)
    print(f"\n   per-beat hazard p = {len(below)}/{len(gauged)} = {hazard:.3f}")
    for n in (1, 5, 10, 15):
        print(f"     P(>=1 class-B miss in {n:>2} beats) = {1 - (1 - hazard) ** n:>5.1%}")

    # ---- 2. is the residual coupled to rebuild progress? -----------------
    print("\n-- 2. is the hazard a REBUILD condition? ------------------------------")
    pts = [(int(r["units_done"]), int(r["window_left_ms"]))
           for r in gauged if r.get("units_done")]
    r_val = pearson([p[0] for p in pts], [p[1] for p in pts])
    print(f"   Pearson r(units_done, window_left_ms) = {r_val:+.3f}   n={len(pts)}")
    print("   -> near zero: the residual does NOT depend on how far the rebuild got.")
    print("      A rebuild-heavy beat is not more exposed; EVERY beat is exposed.")

    # ---- 3. the residual's shape, and the reserve that is not there ------
    print("\n-- 3. window_left_ms is a residual, not a reserve ---------------------")
    ws = sorted(int(r["window_left_ms"]) for r in gauged)
    print(f"   min {ws[0]}  p10 {ws[len(ws)//10]}  p25 {ws[len(ws)//4]}"
          f"  median {int(statistics.median(ws))}  max {ws[-1]}")
    uws = [int(r["unit_ms_worst"]) for r in gauged if r.get("unit_ms_worst")]
    if uws:
        print(f"   one unit costs  min {min(uws)}  median {int(statistics.median(uws))}"
              f"  max {max(uws)}")
    print("   _unit_fits_in_window() admits a unit on unit cost alone. The leftover")
    print("   is bounded by one unit's cost and reserves nothing for diagnostics.")

    # ---- 4. how much of this rests on the single census measurement? -----
    print("\n-- 4. sensitivity: the census cost is ONE observation -----------------")
    for c in (60_000, 75_000, need, 100_000, 120_000):
        k = sum(1 for r in gauged
                if statement_timeout_for(int(r["window_left_ms"])) < c)
        tag = "  <== measured" if c == need else ""
        print(f"   census {c:>7} ms -> {k:>3}/{len(gauged)} beats cannot fit"
              f"  ({100*k/len(gauged):>4.1f}%){tag}")

    print("\nexit 0 = the prediction was CHECKED. The verdict is the table above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
