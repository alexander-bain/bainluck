#!/usr/bin/env python3
"""Inverted completed_at audit — the 439 cross-merged-events class (#189/#190).

Enforces the invariant `completed_at >= commence_time`: a game cannot be recorded
as finishing before it starts. Violations are the cross-merged-events class
(gotcha #32): ESPN's finished-game handling folded an EARLIER same-matchup game's
terminal state (completed_at + final win prob, sometimes the score + snapshots)
onto a LATER sibling event, via the time-loose 28h structured match / no-time-guard
name match. Root cause of the "disgrace page": empty settled charts + impossible
My-Stuff dates.

Read-only. Uses the admin db-query endpoint (same rail as the other audits).

Sections:
  A. Count + per-league breakdown of the inverted class (total, >6h to exclude
     any timezone-rounding noise).
  B. A 20-row forensic ledger: for each of the newest inverted events, its
     commence/completed times and its actual win_prob_snapshot window per source,
     so re-point-vs-null can be decided per event before any bulk pass.
  C. The recommended, REVIEW-GATED repair SQL (null the poisoned completed_at
     where re-pointing snapshots is unsafe). This script never mutates.

Usage:
    source ~/.claude/.env
    python3 scripts/audit_inverted_completed_at.py
    python3 scripts/audit_inverted_completed_at.py --ledger 20
"""

import argparse
import json
import os
import subprocess
import sys


def _api() -> str:
    api = os.getenv("BAINLUCK_API")
    if not api:
        print("ERROR: set BAINLUCK_API (source ~/.claude/.env)", file=sys.stderr)
        sys.exit(2)
    return api.rstrip("/")


def _dbq(sql: str, limit: int = 500, timeout: int = 60):
    """Run a read-only query via the admin db-query endpoint. Returns rows list."""
    token = os.getenv("ADMIN_TOKEN", "")
    body = json.dumps({"sql": sql, "limit": limit})
    cmd = [
        "curl", "-s", "-X", "POST", f"{_api()}/api/admin/db-query",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", body,
    ]
    try:
        out = subprocess.check_output(cmd, timeout=timeout)
        d = json.loads(out)
        if "rows" not in d:
            print(f"  db-query error: {str(d)[:300]}", file=sys.stderr)
            return []
        return d.get("rows") or []
    except Exception as exc:  # noqa: BLE001
        print(f"  db-query failed: {exc}", file=sys.stderr)
        return []


def section_a():
    print("=" * 72)
    print("A. Inverted completed_at class (completed_at < commence_time)")
    print("=" * 72)
    rows = _dbq(
        "SELECT count(*) AS total, "
        "count(*) FILTER (WHERE completed_at < commence_time - interval '6 hours') AS inverted_6h "
        "FROM events WHERE completed_at IS NOT NULL AND completed_at < commence_time"
    )
    if rows:
        total, inv6h = rows[0]
        print(f"  total inverted:      {total}")
        print(f"  inverted by > 6h:    {inv6h}   (excludes tz-rounding noise)")
    print()
    print("  By league:")
    for r in _dbq(
        "SELECT COALESCE(llm_league,'(null)') AS league, count(*) AS n, "
        "min(commence_time - completed_at) AS min_gap, "
        "max(commence_time - completed_at) AS max_gap "
        "FROM events WHERE completed_at < commence_time "
        "GROUP BY llm_league ORDER BY n DESC"
    ):
        print(f"    {str(r[0]):<16} {str(r[1]):>5}   gap {str(r[2])[:16]} .. {str(r[3])[:20]}")
    print()


def section_b(n: int):
    print("=" * 72)
    print(f"B. Forensic ledger — newest {n} inverted events (snapshot windows)")
    print("=" * 72)
    ids_rows = _dbq(
        "SELECT id, llm_league, commence_time, completed_at, status, home_score, away_score "
        "FROM events WHERE completed_at < commence_time - interval '6 hours' "
        f"ORDER BY completed_at DESC LIMIT {int(n)}"
    )
    if not ids_rows:
        print("  (no rows)")
        return
    ids = [r[0] for r in ids_rows]
    # Snapshot windows for just these ids (WHERE event_id IN — avoids full scan).
    snap_rows = _dbq(
        "SELECT event_id, source, min(captured_at) AS first, max(captured_at) AS last, count(*) AS n "
        f"FROM win_prob_snapshots WHERE event_id IN ({','.join(str(i) for i in ids)}) "
        "GROUP BY event_id, source ORDER BY event_id, source",
        limit=1000,
    )
    snaps: dict = {}
    for eid, src, first, last, cnt in snap_rows:
        snaps.setdefault(eid, []).append((src, str(first)[:19], str(last)[:19], cnt))
    for r in ids_rows:
        eid, league, commence, completed, status, hs, as_ = r
        print(f"\n  event {eid} [{league}] {status}  score {hs}-{as_}")
        print(f"    commence  {str(commence)[:19]}")
        print(f"    completed {str(completed)[:19]}   <-- precedes commence (inverted)")
        for src, first, last, cnt in snaps.get(eid, []):
            print(f"      snap {src:<11} {first} .. {last}  (n={cnt})")
        # Sub-class hint: do the non-polymarket snapshots align with commence day?
        non_pm = [s for s in snaps.get(eid, []) if s[0] != "polymarket"]
        if non_pm:
            hint = ("A: snapshots look on-time (only completed_at poisoned)"
                    if all(s[1][:10] == str(commence)[:10] for s in non_pm)
                    else "B: snapshots ALSO from a different game (re-point unsafe → null)")
            print(f"    sub-class: {hint}")
    print()


def section_c():
    print("=" * 72)
    print("C. Recommended repair (REVIEW-GATED — this script does NOT mutate)")
    print("=" * 72)
    print("""
  The write-side guards (app/utils/espn_helpers.py) + the flow-sentinel
  inverted_completed_events detector prevent NEW inversions. For the existing
  backlog, re-pointing mis-attributed snapshots is unsafe (sub-class B carries a
  wrong score too), so the safe repair is to null the impossible completed_at and
  let the read-side heal (#189) render correctly:

      -- 20-row ledger reviewed first (section B), then, as a reviewed one-off:
      UPDATE events
      SET    completed_at = NULL
      WHERE  completed_at < commence_time;

  Gotcha #21: this is resolved data — run it as a deliberate, reviewed one-off
  (heroku run / admin path), NOT an unattended bulk pass. Re-run this audit after
  to confirm total inverted == 0.
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=int, default=20, help="rows in the forensic ledger")
    args = ap.parse_args()
    section_a()
    section_b(args.ledger)
    section_c()


if __name__ == "__main__":
    main()
