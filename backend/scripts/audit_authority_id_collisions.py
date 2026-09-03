#!/usr/bin/env python3
"""Measure the ``events.espn_id`` collisions against ESPN, without writing anything.

    python3 scripts/audit_authority_id_collisions.py --out /tmp/collisions.json
    python3 scripts/audit_authority_id_collisions.py --sport baseball_ncaa --verbose

Reads production through the admin ``db-query`` endpoint (so it runs from a
sandbox that cannot reach Postgres, gotcha: 5432 egress is blocked) and asks
ESPN who each contested id really is.  The verdicts come from
``app.utils.authority_id_collisions`` — the same module the repair job runs, so
the dry-run counts in a PR and the counts the job acts on cannot drift.

Needs ``BAINLUCK_API`` and ``ADMIN_TOKEN`` in the environment
(``source ~/.claude/.env``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.authority_id_collisions import (  # noqa: E402
    AuthorityRecord,
    CandidateRow,
    authority_names,
    decide_group,
    summarize,
)
from app.utils.sport_keys import SPORT_LEAGUE_MAP  # noqa: E402

ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={eid}"

COLLISION_SQL = """
SELECT e.espn_id, e.id, s.key, e.home_team_name, e.away_team_name,
       e.commence_time, e.status, e.external_id, ht.espn_id, at.espn_id
FROM events e
JOIN sports s ON s.id = e.sport_id
LEFT JOIN teams ht ON ht.id = e.home_team_id
LEFT JOIN teams at ON at.id = e.away_team_id
WHERE e.espn_id IN (
    SELECT espn_id FROM events
    WHERE espn_id IS NOT NULL
    GROUP BY espn_id HAVING count(*) > 1
)
ORDER BY e.espn_id, e.id
"""


def db_query(sql: str, limit: int = 1000) -> dict[str, Any]:
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        raise SystemExit("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)")
    body = json.dumps({"sql": " ".join(sql.split()), "limit": limit}).encode()
    request = urllib.request.Request(
        f"{base}/api/admin/db-query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace(" ", "T", 1).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fetch_authority(sport_key: str, authority_id: str) -> Optional[AuthorityRecord]:
    """ESPN's own record for one event id, or ``None`` — never a guess."""
    path = SPORT_LEAGUE_MAP.get(sport_key)
    if path is None:
        return None
    url = ESPN_SUMMARY.format(sport=path[0], league=path[1], eid=authority_id)
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            payload = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None

    competitions = ((payload.get("header") or {}).get("competitions") or [])
    if not competitions:
        return None
    competition = competitions[0]
    home: frozenset[str] = frozenset()
    away: frozenset[str] = frozenset()
    home_id: Optional[str] = None
    away_id: Optional[str] = None
    labels = {}
    for competitor in competition.get("competitors") or []:
        block = competitor.get("team") if isinstance(competitor.get("team"), dict) else competitor
        names = authority_names(competitor)
        team_id = block.get("id")
        side = competitor.get("homeAway")
        labels[side] = block.get("displayName") or (sorted(names)[0] if names else "?")
        if side == "home":
            home, home_id = names, (str(team_id) if team_id is not None else None)
        elif side == "away":
            away, away_id = names, (str(team_id) if team_id is not None else None)
    return AuthorityRecord(
        authority_id=str(authority_id),
        home_names=home,
        away_names=away,
        home_team_id=home_id,
        away_team_id=away_id,
        starts_at=parse_time(competition.get("date")),
        label=f"{labels.get('home', '?')} v {labels.get('away', '?')}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sport", help="restrict to one sport key")
    parser.add_argument("--out", help="write the full decision set as JSON")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.15, help="seconds between ESPN calls")
    args = parser.parse_args()

    result = db_query(COLLISION_SQL)
    if result.get("truncated"):
        print("WARNING: row cap hit — the population is larger than this run measured")

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in result["rows"]:
        groups.setdefault(str(row[0]), []).append({
            "event_id": int(row[1]),
            "sport": row[2],
            "home": row[3],
            "away": row[4],
            "commence_time": row[5],
            "status": row[6],
            "external_id": row[7],
            "home_team_espn_id": row[8],
            "away_team_espn_id": row[9],
        })

    if args.sport:
        groups = {
            k: v for k, v in groups.items() if any(r["sport"] == args.sport for r in v)
        }

    decisions = []
    records = []
    by_sport: Counter = Counter()
    for authority_id, raw in sorted(groups.items()):
        sport_keys = [r["sport"] for r in raw]
        record = None
        for sport_key in dict.fromkeys(sport_keys):
            record = fetch_authority(sport_key, authority_id)
            time.sleep(args.sleep)
            if record is not None and record.usable:
                break
        rows = [
            CandidateRow(
                event_id=r["event_id"],
                sport_key=r["sport"],
                home_team_name=r["home"] or "",
                away_team_name=r["away"] or "",
                commence_time=parse_time(r["commence_time"]),
                home_team_authority_id=r["home_team_espn_id"],
                away_team_authority_id=r["away_team_espn_id"],
                has_external_id=bool(r["external_id"]),
            )
            for r in raw
        ]
        decision = decide_group(record, rows, authority_id=authority_id)
        decisions.append(decision)
        by_sport[(sport_keys[0], decision.outcome)] += 1
        records.append({
            "authority_id": authority_id,
            "sport": sport_keys[0],
            "espn": record.label if record else None,
            "outcome": decision.outcome,
            "keep": decision.keep_event_id,
            "twins": list(decision.twin_event_ids),
            "unstamp": list(decision.unstamp_event_ids),
            "note": decision.note,
            "rows": [
                {
                    "event_id": v.event_id,
                    "verdict": v.verdict,
                    "channel": v.channel,
                    "inverted": v.inverted,
                    "delta_seconds": v.delta_seconds,
                    "home": next(r["home"] for r in raw if r["event_id"] == v.event_id),
                    "away": next(r["away"] for r in raw if r["event_id"] == v.event_id),
                }
                for v in decision.rows
            ],
        })
        if args.verbose and decision.outcome not in ("RESOLVED_ONE", "RESOLVED_MERGE"):
            print(f"{authority_id} {decision.outcome}: {decision.note}")
            for row in raw:
                print(f"    {row['event_id']} {row['home']} v {row['away']}")

    stats = summarize(decisions)
    print(json.dumps(stats, indent=2))
    print("\nBY SPORT")
    for (sport, outcome), n in sorted(by_sport.items()):
        print(f"  {sport:32s} {outcome:22s} {n}")

    if args.out:
        Path(args.out).write_text(json.dumps({"summary": stats, "groups": records}, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
