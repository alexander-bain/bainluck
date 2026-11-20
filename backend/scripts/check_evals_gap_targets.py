#!/usr/bin/env python3
"""Daily /evals gap-targets vs launch-board Target check (#12467).

Compares every entry in ``frontend/lib/evals/data/gap-targets.json`` against
live GitHub issue state and the issue's ``Target`` field on the launch board
(``PVT_kwHOC0ai9c4Bp5gq`` — "Nov 2026 launch"). Exits 0 on GREEN (all gap
issues open and all printed targets match the board), 1 on RED (any drift or
closed issue), and 2 on UNKNOWN (GitHub read failed).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _resolve_github_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if tok:
        return tok.strip()
    try:
        return subprocess.check_output(
            ["gh", "auth", "token"], text=True, timeout=10
        ).strip()
    except Exception:
        return ""


def _fetch_issue_states(token: str, issue_nums: list[int]) -> dict[int, str] | None:
    import httpx
    from app.tasks.bug_report_github import REPO

    owner, name = REPO.split("/", 1)
    fields = "\n".join(
        f"i{n}: issue(number: {n}) {{ number state title }}"
        for n in sorted(set(issue_nums))
    )
    query = f"""
    query($owner: String!, $name: String!) {{
      repository(owner: $owner, name: $name) {{
        {fields}
      }}
    }}
    """
    try:
        resp = httpx.post(
            "https://api.github.com/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={"query": query, "variables": {"owner": owner, "name": name}},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or data.get("errors"):
            return None
        repo = (data.get("data") or {}).get("repository") or {}
        out: dict[int, str] = {}
        for k, val in repo.items():
            if isinstance(val, dict) and val.get("number") is not None:
                out[int(val["number"])] = str(val.get("state") or "")
        return out
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    import app.tasks.bug_report_github as gh
    from app.tasks.board_sentinel import (
        _fetch_launch_board_targets,
        _iter_gap_target_entries,
        _load_evals_gap_targets,
        check_evals_gap_targets,
    )

    gap_targets = _load_evals_gap_targets()
    if not gap_targets:
        print("UNKNOWN: could not load frontend/lib/evals/data/gap-targets.json", file=sys.stderr)
        return 2

    token = _resolve_github_token()
    if not token:
        print("UNKNOWN: GITHUB_TOKEN / gh auth token unavailable", file=sys.stderr)
        return 2
    gh.GITHUB_TOKEN = token

    project_id = str(gap_targets.get("project_id") or "")
    launch_targets = _fetch_launch_board_targets(project_id)
    if launch_targets is None:
        print("UNKNOWN: failed to read launch board Targets via GraphQL", file=sys.stderr)
        return 2

    entries = _iter_gap_target_entries(gap_targets)
    issue_nums = [
        int(str(g.get("issue") or "").lstrip("#"))
        for g in entries
        if str(g.get("issue") or "").lstrip("#").isdigit()
    ]
    states = _fetch_issue_states(token, issue_nums)
    if states is None or len(states) < len(set(issue_nums)):
        print("UNKNOWN: failed to read complete issue states via GraphQL", file=sys.stderr)
        return 2

    from datetime import datetime, timezone

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    open_issues = [
        {"number": num, "state": st}
        for num, st in states.items()
        if st.upper() == "OPEN"
    ]
    findings = check_evals_gap_targets(
        gap_targets,
        open_issues,
        launch_targets,
        today=today_iso,
        population_complete=True,
    )
    rows = []
    for g in entries:
        num = int(str(g.get("issue") or "").lstrip("#"))
        printed = g.get("target")
        board = launch_targets.get(num)
        state = states.get(num, "MISSING")
        ok = state.upper() == "OPEN" and printed == board
        rows.append({
            "id": g.get("id"),
            "issue": f"#{num}",
            "state": state,
            "printed_target": printed,
            "board_target": board,
            "match": ok,
        })

    verdict = "red" if findings else "green"
    report = {
        "verdict": verdict,
        "project_id": project_id,
        "checked_gaps": len(rows),
        "mismatches": len(findings),
        "rows": rows,
        "findings": findings,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"verdict: {verdict.upper()} ({len(rows)} gaps checked, {len(findings)} mismatch(es))")
        print(f"{'Gap ID':24s} | {'Issue':7s} | {'State':6s} | {'Printed (/evals)':16s} | {'Board Target':16s} | Status")
        print("-" * 88)
        for r in rows:
            p_str = r["printed_target"] or "Not scheduled"
            b_str = r["board_target"] or "Not scheduled"
            st_str = "OK" if r["match"] else "DRIFT"
            print(f"{r['id']:24s} | {r['issue']:7s} | {r['state']:6s} | {p_str:16s} | {b_str:16s} | {st_str}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
