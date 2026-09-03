#!/usr/bin/env python3
"""Does each anchored row agree with its own anchor about kickoff? Read-only.

The dry-run twin of ``app/tasks/reconcile_anchor_schedule``, and the script
that module's docstring already names. It answers the same question against
production — *what game is this row's anchor?* — by dereferencing
``events.espn_id`` BY ID, one ``summary?event=`` call per row, rather than
looking for the row on today's scoreboard.

**It imports the shipped decider rather than restating it.** Every verdict here
comes from ``app.utils.anchor_schedule.schedule_decision`` and every
:class:`AuthorityRecord` from ``repair_authority_id_collisions.record_from_summary``,
so a plan printed here and a plan the rail applies cannot disagree. A census
that re-implements its rail's rule is a census of a copy.

Writes nothing, anywhere: the database is read through ``/api/admin/db-query``
(read-only SQL) and ESPN through its public site API.

    source ~/.claude/.env
    python3 scripts/audit_anchor_schedule.py
    python3 scripts/audit_anchor_schedule.py --sport americanfootball_nfl
    python3 scripts/audit_anchor_schedule.py --verdict teams_disagree --json

═══ WHAT IT MEASURED THE DAY IT WAS WRITTEN (2026-09-03) ═══

194 anchored, unfinished rows inside the 120-day horizon across NFL / MLB /
NCAAF / MLS: 160 ``agrees``, 10 ``authority_moves_us`` (#2792 §2, the two NFL
Week 1 ghosts among them) and 24 ``teams_disagree`` — of which 23 were team-name
*vocabulary* false positives, not real mis-anchors. That measurement is the
reason ``--verdict teams_disagree`` exists as a first-class view.

═══ EXIT CODES ═══

``0`` measured · ``2`` no ``ADMIN_TOKEN`` · ``3`` the authority answered for
nothing. A dark ESPN and a clean population produce the same empty verdict
list, so the dark case exits non-zero rather than printing a green census
(gotcha #53).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.espn_api import ESPN_API_BASE  # noqa: E402
from app.tasks.reconcile_anchor_schedule import (  # noqa: E402
    DEFAULT_HORIZON,
    DEFAULT_LIMIT,
    DEFAULT_LOOKBACK,
)
from app.tasks.repair_authority_id_collisions import record_from_summary  # noqa: E402
from app.utils.anchor_schedule import (  # noqa: E402
    AnchoredRow,
    NO_ANSWER,
    SCHEDULE_VERDICTS,
    schedule_decision,
    summarize_decisions,
)
from app.utils.espn_tennis_anchor import SETTLED_STATUSES  # noqa: E402
from app.utils.sport_keys import SPORT_LEAGUE_MAP  # noqa: E402

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
TOKEN = os.environ.get("ADMIN_TOKEN", "")

#: One ESPN call per row is the whole method, so this is an ESPN-politeness
#: pause, not a rate limit we have measured. Kept small enough that 200 rows
#: stay inside a couple of minutes.
ESPN_PAUSE_S = 0.12


def db_query(sql: str, limit: int = 1000) -> list[dict]:
    """Run a read-only SQL query via the admin endpoint; return list-of-dicts."""
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"db-query {exc.code}: {detail}\nSQL: {sql[:200]}") from None
    cols = payload["columns"]
    return [dict(zip(cols, row)) for row in payload["rows"]]


def _moment(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fetch_summary(sport_key: str, authority_id: str) -> dict | None:
    """ESPN's ``summary`` body for one id, or ``None`` when it did not answer.

    Deliberately does NOT distinguish 404 from a network failure the way the
    task's client does: both reach :func:`record_from_summary` as ``None`` and
    therefore reach the decider as :data:`NO_ANSWER`, which is the safe reading
    of either. The script's job is to report that count, not to act on it.
    """
    path = SPORT_LEAGUE_MAP.get(sport_key)
    if path is None:
        return None
    url = f"{ESPN_API_BASE}/{path[0]}/{path[1]}/summary?event={authority_id}"
    try:
        # NO custom User-Agent, and this is load-bearing. ESPN's edge 403s a
        # named agent — measured 2026-09-03 on this very script, whose first
        # run reported all 200 rows dark because it politely identified itself
        # as ``bainluck-audit``. It is the same finding ``espn_api``'s module
        # docstring already records for ``BainLuck/1.0``. urllib's own default
        # is accepted, so let it supply one.
        with urlopen(
            Request(url, headers={"Accept": "application/json"}), timeout=25
        ) as resp:
            return json.load(resp)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError):
        return None


def load_rows(
    sport: str | None, limit: int, lookback: timedelta, horizon: timedelta
) -> tuple[list[AnchoredRow], int]:
    """The same population ``reconcile_anchor_schedule._load_rows`` selects.

    Same predicates, same ``ORDER BY commence_time``, same limit. A census
    measured over a wider or narrower set than the rail it watches is a census
    of a different question.

    Returns the rows AND how many the window holds, because those two numbers
    are routinely different: 685 rows were eligible on 2026-09-03 against a
    default limit of 200. Printing only the first would make every run look
    complete.
    """
    now = datetime.now(timezone.utc)
    settled = ", ".join(f"'{s}'" for s in sorted(SETTLED_STATUSES))
    sport_clause = f"AND s.key = '{sport}'" if sport else ""
    where = f"""
        WHERE e.espn_id IS NOT NULL
          AND e.completed_at IS NULL
          AND e.status NOT IN ({settled})
          AND e.commence_time >= '{(now - lookback).isoformat()}'
          AND e.commence_time <  '{(now + horizon).isoformat()}'
          {sport_clause}
    """
    eligible = int(
        db_query(
            f"SELECT count(*) AS n FROM events e JOIN sports s ON s.id = e.sport_id {where}",
            limit=1,
        )[0]["n"]
    )
    rows = db_query(
        f"""
        SELECT e.id, e.espn_id, e.commence_time, e.home_team_name, e.away_team_name,
               e.status, e.completed_at, e.commence_time_source, s.key AS sport_key
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        {where}
        ORDER BY e.commence_time
        LIMIT {limit}
        """,
        limit=limit,
    )
    return [
        AnchoredRow(
            event_id=int(r["id"]),
            sport_key=r["sport_key"],
            home_team_name=r["home_team_name"] or "",
            away_team_name=r["away_team_name"] or "",
            espn_id=str(r["espn_id"]),
            commence_time=_moment(r["commence_time"]),
            status=r["status"],
            completed_at=_moment(r["completed_at"]),
            commence_time_source=r["commence_time_source"],
        )
        for r in rows
    ], eligible


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sport", default=None, help="Restrict to one sport key")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--horizon-days", type=int, default=int(DEFAULT_HORIZON.days))
    parser.add_argument(
        "--verdict",
        default=None,
        choices=SCHEDULE_VERDICTS,
        help="Print every row landing on one verdict, with both names and ESPN's label",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    rows, eligible = load_rows(
        args.sport, args.limit, DEFAULT_LOOKBACK, timedelta(days=args.horizon_days)
    )
    if not rows:
        print("no anchored, unfinished rows inside the window", file=sys.stderr)
        return 0

    decisions, labels = [], {}
    for row in rows:
        record = record_from_summary(
            row.espn_id, fetch_summary(row.sport_key, row.espn_id)
        )
        if record is not None and not record.usable:
            record = None
        decisions.append(schedule_decision(row, record))
        labels[row.event_id] = row
        time.sleep(ESPN_PAUSE_S)

    summary = summarize_decisions(decisions)
    if summary["by_verdict"][NO_ANSWER] == summary["examined"]:
        print(
            f"AUTHORITY DARK — ESPN answered for none of {summary['examined']} rows",
            file=sys.stderr,
        )
        return 3

    detail = [
        {
            "event_id": d.event_id,
            "espn_id": d.espn_id,
            "sport": labels[d.event_id].sport_key,
            "ours_away": labels[d.event_id].away_team_name,
            "ours_home": labels[d.event_id].home_team_name,
            "espn_label": d.authority_label,
            "ours_time": d.ours.isoformat() if d.ours else None,
            "espn_time": d.theirs.isoformat() if d.theirs else None,
            "delta_days": round((d.delta_seconds or 0) / 86400.0, 2),
            "verdict": d.verdict,
        }
        for d in decisions
        if args.verdict is None or d.verdict == args.verdict
    ]

    truncated = eligible > summary["examined"]
    if args.as_json:
        print(
            json.dumps(
                {
                    **summary,
                    "eligible": eligible,
                    "truncated": truncated,
                    "detail": detail,
                },
                indent=2,
                default=str,
            )
        )
        return 0

    scope = f" ({args.sport})" if args.sport else ""
    print(f"examined {summary['examined']} of {eligible} anchored rows{scope}")
    if truncated:
        print(
            f"  ** TRUNCATED — {eligible - summary['examined']} rows unseen; --limit {eligible}"
        )
    for verdict in SCHEDULE_VERDICTS:
        print(f"  {verdict:<20} {summary['by_verdict'][verdict]}")
    if summary["moves"]:
        print(f"\nMOVES ({len(summary['moves'])}) — the authority owns these dates:")
        for move in summary["moves"]:
            print(
                f"  E{move['event_id']:<10} espn {move['espn_id']:<12} "
                f"{move['ours']} -> {move['theirs']}  ({move['delta_days']}d)  {move['authority']}"
            )
    if args.verdict:
        print(f"\n{args.verdict.upper()} ({len(detail)}):")
        for row in detail:
            print(
                f"  E{row['event_id']:<10} {row['sport']:<24} "
                f"ours: {row['ours_away']} @ {row['ours_home']}\n"
                f"{'':<13} espn: {row['espn_label']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
