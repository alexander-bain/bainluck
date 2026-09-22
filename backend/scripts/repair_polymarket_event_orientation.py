#!/usr/bin/env python3
"""#7739 — a Polymarket-minted US-sport game stops naming the away team as host.

WHAT A READER SEES TODAY. `/search?q=tempo` renders `Toronto Tempo 42% /
Connecticut Sun 58%` for event 15310072, and every card on the page puts the
HOST on top. ESPN's `homeAway` for that fixture (401857215) is home=Connecticut
Sun. The label and the price disagree with each other on one card.

WHERE IT COMES FROM. `_create_event_from_prediction_market` stamps
`home_team_name = team_a`, the club Polymarket names FIRST in "A vs. B".
Measured against ESPN on 2026-09-22 (artifacts-lane1-591), Polymarket mirrors
each sport's own listing habit rather than one convention:

    WNBA + NHL   87 fixtures   87 away-first    0 home-first
    soccer       34 fixtures    0 away-first   34 home-first

So `team_a` is right for world football and European club basketball and wrong
for the US leagues. See `POLYMARKET_AWAY_FIRST_LEAGUES` for the full note,
including why the mint path itself is NOT the place to fix this.

TWO SIGNALS, BOTH REQUIRED, AND WHY.
  1. ESPN's explicit `homeAway` for the same fixture, matched on both club
     names AND a kickoff inside `--kickoff-tolerance-min`.
  2. The measured venue convention for the league the clubs resolve to.

A row is rewritten only when both agree it is reversed. ESPN alone is not
enough: the WNBA and NHL slates both carry same-minute home-and-home pairs
(`nhl-ott-mon-2026-09-26` is two ESPN fixtures at 23:00Z with opposite
orientations), so a name-and-time join can land on the wrong leg of a pair and
"correct" a row that was already right. Requiring the convention to predict the
same flip means a wrong-leg match produces DISAGREE — which is reported and
skipped, never written.

SAFETY (D51(b) / notice 47(c)).
  * Dry run is the DEFAULT. `--apply` is the only thing that writes.
  * `--apply` refuses to start without `--backup`, which copies every row it is
    about to touch into `backup_event_orientation_7739` FIRST and prints the
    one-command restore before the first UPDATE.
  * Runtime DDL (`CREATE TABLE IF NOT EXISTS backup_*`), attended invocation
    only — this script is never run by a release or a beat.
  * Scheduled/live rows only. A completed game's orientation is load-bearing for
    scores already stored against it; swapping names there would silently
    reverse a final score, which is a worse defect than the one being fixed.

🔴 THE SWAP IS A TRANSPOSITION, NOT A RENAME, AND THIS IS THE WHOLE RISK.
`home_team_name` is not a label sitting on its own — every probability we store
for a game is HOME-ORIENTED. Event 15310072 carries
`win_probability_sources.polymarket.value = 0.585` with `hero_probability`
0.585 / `hero_probability_away` 0.415, and the card reads `Toronto Tempo 59%`.
Rename the two clubs and nothing else, and the page serves **Connecticut Sun
59%** — the market's price on the wrong club. That is a strictly worse defect
than the one being repaired: a wrong label becomes a wrong number.

So a swap moves, atomically:
    events.home_team_name  <-> away_team_name
    events.home_team_id    <-> away_team_id
    events.win_probability_sources.<source>.value  ->  1 - value
    win_prob_snapshots.home_win_probability <-> away_win_probability

and NOTHING ELSE IS ALLOWED TO BE PRESENT. `--apply` refuses any row carrying an
orientation-dependent field this script does not transpose (a score, an
opening/closing probability or spread, an odds snapshot). All 31 rows in the
2026-09-22 dry run are clean on every one of those, so the refusal is a guard
rather than a blocker — but it is what keeps this repair honest if the
population ever changes shape.

`yes_is_home` is deliberately NOT written: it is not a stored column.
`resolve_orientation` recomputes it from the current home/away names on every
pass, so the live writers produce the correctly-oriented value by themselves
once the names are right. Transposing the stored value is only there so the
page is never briefly wrong in the window before that pass.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.prediction_market_matching import (  # noqa: E402
    POLYMARKET_AWAY_FIRST_LEAGUES,
    polymarket_lists_away_first,
)

BACKUP_TABLE = "backup_event_orientation_7739"
PRODUCER_APP = "bainluck"

# Resolved league -> the ESPN scoreboard path that carries its fixtures. Only
# the leagues whose convention was actually measured; an unlisted league is
# skipped, never guessed at.
ESPN_PATHS = {
    "basketball_wnba": "basketball/wnba",
    "icehockey_nhl": "hockey/nhl",
    "icehockey_nhl_preseason": "hockey/nhl",
}

# The rows this defect can reach: minted by a Polymarket market (so the anchor
# channel knows only that source), never reconciled to the authority, and still
# ahead of or inside their own game.
CANDIDATE_SQL = """
WITH pm AS (
    SELECT DISTINCT event_id FROM event_provider_anchors WHERE source = 'polymarket'
), other AS (
    SELECT DISTINCT event_id FROM event_provider_anchors WHERE source <> 'polymarket'
)
SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name,
       e.commence_time, e.status
FROM events e
JOIN pm ON pm.event_id = e.id
LEFT JOIN other ON other.event_id = e.id
JOIN sports s ON s.id = e.sport_id
WHERE other.event_id IS NULL
  AND e.espn_id IS NULL
  AND e.status IN ('scheduled', 'live')
  AND e.commence_time BETWEEN now() - interval '1 day'
                          AND now() + interval :horizon_days * interval '1 day'
ORDER BY e.commence_time
"""

# Every club in the measured leagues, read ONCE. Resolution then happens in
# Python against `same_club`, which is the same rule the ESPN join uses.
#
# Exact-on-`teams` is not enough and the gap is not an edge case: run that way
# against production on 2026-09-22, 493 of 500 candidate rows came back
# UNRESOLVED and every NHL row was among them, because Polymarket titles them
# `Capitals vs. Hurricanes` while `teams` says `Washington Capitals`. An
# unresolved row is skipped, so exact matching quietly reduced this repair to
# its WNBA seventh while reporting a clean run.
CLUBS_SQL = """
SELECT s.key AS league, t.name
FROM teams t
JOIN sports s ON s.id = t.sport_id
WHERE s.key = ANY(:leagues)
"""


# Orientation-dependent data this script does NOT transpose. A row holding any
# of it is refused rather than half-swapped.
UNHANDLED_SQL = """
SELECT e.id,
       (e.home_score IS NOT NULL OR e.away_score IS NOT NULL) AS has_score,
       (e.opening_home_probability IS NOT NULL
        OR e.opening_away_probability IS NOT NULL
        OR e.opening_home_spread IS NOT NULL
        OR e.opening_favorite IS NOT NULL) AS has_opening,
       (e.closing_home_probability IS NOT NULL
        OR e.closing_away_probability IS NOT NULL
        OR e.closing_home_spread IS NOT NULL) AS has_closing,
       (SELECT count(*) FROM odds_snapshots o WHERE o.event_id = e.id)
           AS odds_snapshots
FROM events e
WHERE e.id = ANY(:ids)
"""

# The transposition itself. One statement per table, both inside one
# transaction: a half-applied swap is the wrong-price defect this guards.
SWAP_EVENT_SQL = """
UPDATE events SET
    home_team_name = away_team_name,
    away_team_name = home_team_name,
    home_team_id   = away_team_id,
    away_team_id   = home_team_id,
    win_probability_sources = (
        SELECT jsonb_object_agg(
                   key,
                   CASE WHEN jsonb_typeof(val -> 'value') = 'number'
                        THEN jsonb_set(val, '{value}',
                                 to_jsonb(round((1 - (val ->> 'value')::numeric), 4)))
                        ELSE val END)
        FROM jsonb_each(win_probability_sources) AS s(key, val)
    )
WHERE id = ANY(:ids)
"""

SWAP_SNAPSHOTS_SQL = """
UPDATE win_prob_snapshots SET
    home_win_probability = away_win_probability,
    away_win_probability = home_win_probability
WHERE event_id = ANY(:ids)
"""


def unhandled_reasons(row: dict) -> list[str]:
    """Named reasons a row may not be swapped, or an empty list."""
    reasons = []
    if row.get("has_score"):
        reasons.append("score")
    if row.get("has_opening"):
        reasons.append("opening-probability")
    if row.get("has_closing"):
        reasons.append("closing-probability")
    if row.get("odds_snapshots"):
        reasons.append(f"{row['odds_snapshots']} odds snapshots")
    return reasons


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def same_club(a: str | None, b: str | None) -> bool:
    """Containment either way, on a stem long enough to mean something.

    Polymarket titles an NHL club `Capitals` where ESPN says `Washington
    Capitals`. Exact equality matches none of those rows, and a miss here reads
    as "ESPN does not list this fixture" — the quietest possible wrong answer.
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if min(len(na), len(nb)) < 5:
        return False
    return na in nb or nb in na


def espn_slate(path: str, yyyymmdd: str) -> list[dict]:
    """One ESPN scoreboard day.

    curl, not urllib: ESPN 403s a bare urllib User-Agent, and an exception per
    fetch would have made an all-failing census print zero findings. The HTTP
    code is read, never inferred from a body that happens to parse.
    """
    url = (f"https://site.api.espn.com/apis/site/v2/sports/{path}"
           f"/scoreboard?dates={yyyymmdd}&limit=200")
    out = subprocess.run(
        ["curl", "-s", "--max-time", "30", "-w", "\n%{http_code}", url],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"curl exit {out.returncode}")
    body, _, code = out.stdout.rpartition("\n")
    if code.strip() != "200":
        raise RuntimeError(f"HTTP {code.strip()}")
    fixtures = []
    for ev in json.loads(body).get("events", []):
        comp = ev["competitions"][0]
        sides = {c["homeAway"]: c["team"].get("displayName")
                 for c in comp["competitors"]}
        fixtures.append({
            "espn_id": ev["id"],
            "kickoff": datetime.fromisoformat(ev["date"].replace("Z", "+00:00")),
            "home": sides.get("home"),
            "away": sides.get("away"),
            "neutral": bool(comp.get("neutralSite")),
        })
    return fixtures


def leagues_for_club(clubs: list[dict], name: str) -> set[str]:
    """Leagues whose club list contains exactly ONE match for ``name``.

    Uniqueness is the whole safeguard. `Kings` names one club inside the NHL and
    another inside the NBA; scoping the club list to the measured leagues keeps
    that apart, and requiring a single hit inside a league means an ambiguous
    nickname resolves to nothing rather than to whichever row sorted first.
    """
    out = set()
    for league in POLYMARKET_AWAY_FIRST_LEAGUES:
        hits = [c for c in clubs
                if c["league"] == league and same_club(name, c["name"])]
        if len(hits) == 1:
            out.add(league)
    return out


def resolve_league(clubs: list[dict], home: str, away: str) -> str | None:
    """The league this pair plays in, or None.

    NOT "exactly one shared league". Every NHL club is carried twice — once
    under `icehockey_nhl` and once under `icehockey_nhl_preseason` — so an
    exactly-one rule resolves every NHL pair to nothing, which is the whole
    hockey half of this defect silently skipped. Measured on production
    2026-09-22: `Pittsburgh Penguins` is team 60 and team 19703.

    What actually has to be unambiguous is the two things a verdict reads: the
    convention (every league in the set is away-first by construction) and the
    ESPN scoreboard to ask. Both NHL keys name `hockey/nhl`, so the tie is
    immaterial and resolving it is honest. A pair spanning two DIFFERENT
    scoreboards still returns None.
    """
    shared = leagues_for_club(clubs, home) & leagues_for_club(clubs, away)
    if not shared:
        return None
    paths = {ESPN_PATHS.get(lg) for lg in shared}
    if len(paths) != 1 or None in paths:
        return None
    return sorted(shared)[0]


def classify(row, fixtures, tolerance_min: int, league: str):
    """One of REVERSED / CORRECT / DISAGREE / NO-ESPN-FIXTURE / AMBIGUOUS."""
    window = timedelta(minutes=tolerance_min)
    hits = []
    for f in fixtures:
        if abs(f["kickoff"] - row["commence_time"]) > window:
            continue
        straight = (same_club(row["home_team_name"], f["home"])
                    and same_club(row["away_team_name"], f["away"]))
        flipped = (same_club(row["home_team_name"], f["away"])
                   and same_club(row["away_team_name"], f["home"]))
        # Written as two named booleans rather than one chained expression: the
        # `and`/`or` form of this test binds so that the time window silently
        # stops applying to one branch, which admits a fixture days away.
        if straight or flipped:
            hits.append(f)
    if not hits:
        return "NO-ESPN-FIXTURE", None
    if len(hits) > 1:
        # A same-minute home-and-home pair. Both legs carry the same two clubs,
        # so nothing here can say which one this row is; writing either way
        # would be a coin toss on a truth field.
        return "AMBIGUOUS", None
    hit = hits[0]
    if hit["neutral"]:
        return "NEUTRAL-SITE", hit
    espn_says_reversed = same_club(row["home_team_name"], hit["away"])
    convention_says_reversed = polymarket_lists_away_first(league)
    if espn_says_reversed and convention_says_reversed:
        return "REVERSED", hit
    if not espn_says_reversed:
        return "CORRECT", hit
    return "DISAGREE", hit


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the swaps (default is a dry run)")
    ap.add_argument("--backup", action="store_true",
                    help=f"copy touched rows into {BACKUP_TABLE} first; "
                         "required by --apply")
    ap.add_argument("--horizon-days", type=int, default=30)
    ap.add_argument("--kickoff-tolerance-min", type=int, default=90)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N rewrites (0 = no cap)")
    args = ap.parse_args()

    if args.apply and not args.backup:
        print("REFUSING: --apply requires --backup (D51(b)).", file=sys.stderr)
        return 2
    if args.apply and os.environ.get("HEROKU_APP_NAME") != PRODUCER_APP:
        seen = os.environ.get("HEROKU_APP_NAME")
        where = f"'{seen}'" if seen else "not a Heroku dyno (HEROKU_APP_NAME unset)"
        print(f"REFUSING --apply: this is {where}, not '{PRODUCER_APP}'.",
              file=sys.stderr)
        return 2

    # Imported here, not at module scope: the verdict logic below is pure and is
    # unit-tested by importing this file, and a module-level DB import would drag
    # the task layer into that test for no reason.
    from app.tasks.base import get_task_session

    verdicts = Counter()
    planned, slates = [], {}

    async with get_task_session() as session:
        rows = (await session.execute(
            text(CANDIDATE_SQL), {"horizon_days": args.horizon_days}
        )).mappings().all()
        clubs = [dict(r) for r in (await session.execute(
            text(CLUBS_SQL), {"leagues": list(POLYMARKET_AWAY_FIRST_LEAGUES)}
        )).mappings().all()]
        print(f"candidate rows (polymarket-only anchor, no espn_id, "
              f"scheduled/live, next {args.horizon_days}d): {len(rows)}")
        print(f"clubs in the {len(POLYMARKET_AWAY_FIRST_LEAGUES)} measured "
              f"leagues: {len(clubs)}")

        for row in rows:
            league = resolve_league(
                clubs, row["home_team_name"], row["away_team_name"]
            )
            if not league:
                verdicts["UNRESOLVED-LEAGUE"] += 1
                continue
            path = ESPN_PATHS.get(league)
            if not path:
                verdicts["NO-ESPN-PATH"] += 1
                continue
            # The authority's slate is a US-Eastern day, so a 02:00Z tip-off
            # sits on the PREVIOUS one. Read both and union.
            fixtures = []
            for delta in (0, -1):
                day = (row["commence_time"] + timedelta(days=delta)).strftime("%Y%m%d")
                key = (path, day)
                if key not in slates:
                    try:
                        slates[key] = espn_slate(path, day)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  espn {path} {day}: FAILED {exc}", file=sys.stderr)
                        slates[key] = []
                fixtures.extend(slates[key])

            verdict, hit = classify(
                row, fixtures, args.kickoff_tolerance_min, league
            )
            verdicts[verdict] += 1
            if verdict != "REVERSED":
                if verdict in ("DISAGREE", "AMBIGUOUS", "NEUTRAL-SITE"):
                    print(f"  {verdict}: {row['id']} "
                          f"{row['home_team_name']} / {row['away_team_name']}")
                continue
            print(f"  REVERSED: {row['id']} [{league}] "
                  f"stored home={row['home_team_name']} -> "
                  f"espn home={hit['home']} (espn {hit['espn_id']})")
            planned.append(row)
            if args.limit and len(planned) >= args.limit:
                break

        print()
        print("VERDICTS:", dict(verdicts))
        print(f"would rewrite: {len(planned)}")

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply --backup.")
            return 0
        if not planned:
            print("nothing to do.")
            return 0

        ids = [r["id"] for r in planned]

        # A rename is safe only where there is nothing else oriented to `home`.
        blocked = []
        for row in (await session.execute(
            text(UNHANDLED_SQL), {"ids": ids}
        )).mappings().all():
            reasons = unhandled_reasons(dict(row))
            if reasons:
                blocked.append((row["id"], reasons))
        if blocked:
            for event_id, reasons in blocked:
                print(f"  REFUSING {event_id}: carries {', '.join(reasons)} "
                      f"— this script does not transpose it", file=sys.stderr)
            print(f"\nREFUSING --apply: {len(blocked)} of {len(ids)} rows carry "
                  "orientation-dependent data this script does not transpose. "
                  "A half-swap serves the market's price on the wrong club.",
                  file=sys.stderr)
            return 2

        await session.execute(text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id bigint, home_team_name text, away_team_name text,"
            " home_team_id bigint, away_team_id bigint,"
            " win_probability_sources jsonb,"
            " backed_up_at timestamptz DEFAULT now())"
        ))
        await session.execute(text(
            f"INSERT INTO {BACKUP_TABLE} (event_id, home_team_name,"
            " away_team_name, home_team_id, away_team_id,"
            " win_probability_sources)"
            " SELECT id, home_team_name, away_team_name, home_team_id,"
            " away_team_id, win_probability_sources"
            " FROM events WHERE id = ANY(:ids)"
        ), {"ids": ids})
        await session.commit()
        print(f"\nbacked up {len(ids)} rows into {BACKUP_TABLE}")
        print("RESTORE (one command — re-swapping the snapshots is its own"
              " inverse, so it is included):")
        print(f"  UPDATE events e SET home_team_name = b.home_team_name,"
              f" away_team_name = b.away_team_name,"
              f" home_team_id = b.home_team_id, away_team_id = b.away_team_id,"
              f" win_probability_sources = b.win_probability_sources"
              f" FROM {BACKUP_TABLE} b WHERE b.event_id = e.id;"
              f" UPDATE win_prob_snapshots SET"
              f" home_win_probability = away_win_probability,"
              f" away_win_probability = home_win_probability"
              f" WHERE event_id IN (SELECT event_id FROM {BACKUP_TABLE});")

        # One transaction: a swap that moved the names but not the prices is
        # exactly the wrong-price defect the refusal above exists to prevent.
        events_done = (await session.execute(
            text(SWAP_EVENT_SQL), {"ids": ids})).rowcount
        snaps_done = (await session.execute(
            text(SWAP_SNAPSHOTS_SQL), {"ids": ids})).rowcount
        await session.commit()
        print(f"transposed {events_done} event rows and {snaps_done} "
              f"win-probability snapshots.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
