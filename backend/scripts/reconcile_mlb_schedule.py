#!/usr/bin/env python3
"""Reconcile our MLB event set against authoritative external schedules (#1779, #1796).

CENSUS ONLY. This script never writes. It is the measuring instrument for the
Aug 10-12 repair and the seed of the schedule-completeness sentinel (#1796).

Why it keys on the provider game id and not on (teams, commence_time):

    Every check we already have is a predicate over rows we hold, and the ones
    that do compare against the outside world compare NAMES and TIMES. That is
    exactly the comparison the #1779 defect survives. A row can carry the right
    two team names and a plausible time and still BE a different game -- because
    the row was created for Aug 11, then a higher-priority source dragged its
    commence_time forward onto Aug 12. Keyed on names+time that row reads as
    "the Aug 12 game, present and correct". Keyed on the id ESPN itself assigned,
    it reads as what it is: the Aug 11 game, misdated, with Aug 12's live score
    written over its own.

Ground truth comes from two independent sources, and they are used for different
things on purpose:

  * ESPN scoreboard  -> per-game IDENTITY (``espn_id``), because that is the id
    our ``events`` rows actually carry, so it is the only key on which "the same
    game" is decidable rather than inferable.
  * MLB Stats API    -> SCORES and STATUS, because it is the authoritative
    settlement source and is free/unauthenticated (gotcha: our own ``events``
    scores are NOT ground truth -- closed rows keep frozen mid-game scores).

Findings are classified, never scored. The Grid Sentinel's mlb-66 lesson applies:
a raw health number that cries wolf gets ignored, so each finding says what it is.

  MISSING        a game in truth that no row of ours holds the id for
  DUPLICATE_ID   one provider id carried by two or more of our rows
  MISDATED       we hold the id, but our commence_time is not that game's time
  WRONG_SCORE    settled in truth, our score disagrees
  STUCK_LIVE     truth says the game is final, our row is still ``live``
  TEAM_MISWIRED  home/away ``team_id`` dereferences to a club whose name
                 disagrees with the row's own ``*_team_name`` (#1798). Name-to-
                 name checks cannot see this; only dereferencing the id can.

Usage:
    python3 scripts/reconcile_mlb_schedule.py --start 2026-08-10 --end 2026-08-12
    python3 scripts/reconcile_mlb_schedule.py --start 2026-03-25 --end 2026-08-12 --summary

Requires BAINLUCK_API and ADMIN_TOKEN in the environment (``source ~/.claude/.env``).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={date}"
)
STATSAPI_SCHEDULE = (
    "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={start}&endDate={end}"
)

# Regular-season MLB sport_id and the duplicate preseason row that #1798 owns.
# Both are scanned: an event parked on the preseason sport_id during the regular
# season is itself a finding, not a row to skip.
MLB_SPORT_IDS = (53232, 33178)

# How far our commence_time may sit from the provider's for the same game id
# before we call it MISDATED. Generous enough to absorb a real start-time
# correction (rain delay, TV move); far tighter than the 24h that separates
# consecutive games of a series, which is the gap this must never call "fine".
MISDATE_TOLERANCE = timedelta(hours=6)

_FINAL_STATES = {"Final", "Game Over", "Completed Early"}


def _get_json(url: str, timeout: int = 30) -> dict:
    """GET JSON via ``requests``, with a urllib fallback.

    Deliberately sends NO custom headers. Measured 2026-08-12: ESPN's scoreboard
    serves ``requests``' default User-Agent but 403s both a plain urllib request
    and an explicit Chrome UA from this environment. Setting a "more realistic"
    header here makes it fail, so the absence of headers is load-bearing -- do not
    add a User-Agent back without re-measuring.
    """
    try:
        import requests  # noqa: PLC0415 -- optional, fallback below
    except ImportError:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_iso(value: str) -> datetime:
    """Parse the several ISO shapes these three sources emit into aware UTC."""
    text = value.strip().replace("Z", "+00:00")
    # ESPN emits '2026-08-11T23:07Z' (no seconds); Postgres emits a space separator.
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _daterange(start: datetime, end: datetime):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


# ── Ground truth ────────────────────────────────────────────────────


@dataclass
class TruthGame:
    espn_id: str
    away: str
    home: str
    commence: datetime
    game_pk: str | None = None
    status: str | None = None
    away_score: int | None = None
    home_score: int | None = None

    @property
    def is_final(self) -> bool:
        return (self.status or "") in _FINAL_STATES

    def label(self) -> str:
        return f"{self.away} @ {self.home} {self.commence:%Y-%m-%d %H:%M}Z"


def fetch_espn_truth(start: datetime, end: datetime) -> dict[str, TruthGame]:
    """ESPN scoreboard, one call per date -> {espn_id: TruthGame}."""
    truth: dict[str, TruthGame] = {}
    for day in _daterange(start, end):
        payload = _get_json(ESPN_SCOREBOARD.format(date=day.strftime("%Y%m%d")))
        for event in payload.get("events", []):
            comp = (event.get("competitions") or [{}])[0]
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            if "home" not in sides or "away" not in sides:
                continue
            truth[str(event["id"])] = TruthGame(
                espn_id=str(event["id"]),
                away=sides["away"]["team"]["displayName"],
                home=sides["home"]["team"]["displayName"],
                commence=_parse_iso(event["date"]),
            )
    return truth


def overlay_statsapi(truth: dict[str, TruthGame], start: datetime, end: datetime) -> int:
    """Fold MLB Stats API scores/status onto the ESPN identity set.

    Matched on (normalised team names, start time within an hour) because the two
    providers do not share an id. Returns the number of truth games left without
    a statsapi overlay -- reported rather than silently tolerated, since an
    un-overlaid game cannot be score-checked and must not read as "score fine".
    """
    payload = _get_json(
        STATSAPI_SCHEDULE.format(start=start.date().isoformat(), end=end.date().isoformat())
    )
    by_key: dict[tuple[str, str], list] = defaultdict(list)
    for date_block in payload.get("dates", []):
        for game in date_block.get("games", []):
            teams = game["teams"]
            by_key[(teams["away"]["team"]["name"], teams["home"]["team"]["name"])].append(game)

    unmatched = 0
    for game in truth.values():
        candidates = by_key.get((game.away, game.home), [])
        best = None
        for candidate in candidates:
            delta = abs((_parse_iso(candidate["gameDate"]) - game.commence).total_seconds())
            if delta <= 3600 and (best is None or delta < best[0]):
                best = (delta, candidate)
        if best is None:
            unmatched += 1
            continue
        candidate = best[1]
        game.game_pk = str(candidate["gamePk"])
        game.status = candidate["status"]["detailedState"]
        game.away_score = candidate["teams"]["away"].get("score")
        game.home_score = candidate["teams"]["home"].get("score")
    return unmatched


# ── Our rows ────────────────────────────────────────────────────────


@dataclass
class OurRow:
    id: int
    away_name: str
    home_name: str
    commence: datetime
    status: str
    espn_id: str | None
    away_score: int | None
    home_score: int | None
    away_team_id: int | None
    home_team_id: int | None
    sport_id: int


def _db_query(sql: str, limit: int = 1000) -> list:
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        sys.exit("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)")
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        f"{api}/api/admin/db-query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    # gotcha #40: this endpoint serialises JSONB as a Python repr, so json.loads
    # alone silently reads {}. Fall back to literal_eval rather than guessing.
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = ast.literal_eval(raw)
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if len(rows) >= limit:
        sys.exit(
            f"REFUSING TO REPORT: db-query returned {len(rows)} rows at the {limit} cap -- "
            "the result is truncated and any census over it would understate. Narrow the range."
        )
    return rows


def fetch_our_rows(start: datetime, end: datetime) -> list[OurRow]:
    sql = (
        "SELECT id, away_team_name, home_team_name, commence_time, status, espn_id, "
        "away_score, home_score, away_team_id, home_team_id, sport_id FROM events "
        f"WHERE sport_id IN ({','.join(str(s) for s in MLB_SPORT_IDS)}) "
        f"AND commence_time >= '{start.date()} 00:00:00+00' "
        f"AND commence_time < '{(end + timedelta(days=2)).date()} 00:00:00+00' "
        "ORDER BY commence_time"
    )
    return [
        OurRow(
            id=r[0], away_name=r[1], home_name=r[2], commence=_parse_iso(r[3]), status=r[4],
            espn_id=str(r[5]) if r[5] else None, away_score=r[6], home_score=r[7],
            away_team_id=r[8], home_team_id=r[9], sport_id=r[10],
        )
        for r in _db_query(sql)
    ]


def fetch_team_names(team_ids: set[int]) -> dict[int, tuple[str, int]]:
    """{team_id: (name, sport_id)} -- for dereferencing, never for name matching."""
    if not team_ids:
        return {}
    ids = ",".join(str(t) for t in sorted(team_ids))
    rows = _db_query(f"SELECT id, name, sport_id FROM teams WHERE id IN ({ids})")
    return {r[0]: (r[1], r[2]) for r in rows}


# ── Reconcile ───────────────────────────────────────────────────────


@dataclass
class Findings:
    missing: list = field(default_factory=list)
    missing_rekey: list = field(default_factory=list)
    duplicate_id: list = field(default_factory=list)
    misdated: list = field(default_factory=list)
    wrong_score: list = field(default_factory=list)
    stuck_live: list = field(default_factory=list)
    team_miswired: list = field(default_factory=list)
    unlinked: list = field(default_factory=list)
    statsapi_unmatched: int = 0

    def total(self) -> int:
        return sum(
            len(getattr(self, name))
            for name in (
                "missing", "missing_rekey", "duplicate_id", "misdated", "wrong_score",
                "stuck_live", "team_miswired", "unlinked",
            )
        )


def _norm(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def reconcile(truth: dict[str, TruthGame], rows: list[OurRow], teams: dict) -> Findings:
    found = Findings()

    by_espn: dict[str, list[OurRow]] = defaultdict(list)
    for row in rows:
        if row.espn_id:
            by_espn[row.espn_id].append(row)
        else:
            found.unlinked.append(row)

    for espn_id, game in sorted(truth.items(), key=lambda kv: kv[1].commence):
        held = by_espn.get(espn_id, [])
        if not held:
            # Split the absence. "No row holds this id" has two very different
            # repairs behind it, and conflating them is how a backfill creates
            # duplicates: either there is genuinely no row for this game (CREATE),
            # or a row for it exists and is wearing another game's id (RE-KEY).
            impostor = next(
                (
                    r for r in rows
                    if _norm(r.away_name) == _norm(game.away)
                    and _norm(r.home_name) == _norm(game.home)
                    and abs((r.commence - game.commence).total_seconds())
                    <= MISDATE_TOLERANCE.total_seconds()
                ),
                None,
            )
            if impostor is not None:
                found.missing_rekey.append((game, impostor))
            else:
                found.missing.append(game)
            continue
        if len(held) > 1:
            found.duplicate_id.append((game, held))
        for row in held:
            drift = abs((row.commence - game.commence).total_seconds())
            if drift > MISDATE_TOLERANCE.total_seconds():
                found.misdated.append((game, row, drift / 3600.0))
            if game.is_final:
                if row.status == "live":
                    found.stuck_live.append((game, row))
                if (
                    game.away_score is not None
                    and (row.away_score, row.home_score) != (game.away_score, game.home_score)
                ):
                    found.wrong_score.append((game, row))

    # #1798: dereference the id. Everything else in the codebase compares a name
    # to a name, which is precisely why rows with correct names and wrong ids
    # have gone unseen.
    for row in rows:
        for side, team_id, row_name in (
            ("away", row.away_team_id, row.away_name),
            ("home", row.home_team_id, row.home_name),
        ):
            if not team_id:
                continue
            entry = teams.get(team_id)
            if not entry:
                found.team_miswired.append((row, side, team_id, "<no such team row>", row_name))
                continue
            team_name, _team_sport = entry
            if _norm(team_name) != _norm(row_name):
                found.team_miswired.append((row, side, team_id, team_name, row_name))

    return found


def report(found: Findings, truth: dict, rows: list, summary_only: bool) -> None:
    print("=" * 78)
    print(f"TRUTH {len(truth)} games (ESPN identity)   OURS {len(rows)} rows in range")
    if found.statsapi_unmatched:
        print(
            f"  !! {found.statsapi_unmatched} truth games had NO statsapi overlay -- "
            "these are NOT score-checked; absence of a WRONG_SCORE finding on them means nothing"
        )
    print("-" * 78)
    print(f"  MISSING        {len(found.missing)}   (no row for this game at all -> CREATE)")
    print(f"  MISSING_REKEY  {len(found.missing_rekey)}   (a row exists wearing another game's id -> RE-KEY, do NOT create)")
    print(f"  DUPLICATE_ID   {len(found.duplicate_id)}")
    print(f"  MISDATED       {len(found.misdated)}")
    print(f"  WRONG_SCORE    {len(found.wrong_score)}")
    print(f"  STUCK_LIVE     {len(found.stuck_live)}")
    print(f"  TEAM_MISWIRED  {len(found.team_miswired)}")
    print(f"  (rows with no espn_id, not reconcilable: {len(found.unlinked)})")
    print("=" * 78)
    if summary_only:
        return

    if found.missing:
        print("\nMISSING -- in truth, no row of ours holds this id:")
        for g in found.missing:
            print(f"  espn={g.espn_id} pk={g.game_pk} {g.label()} [{g.status} "
                  f"{g.away_score}-{g.home_score}]")

    if found.missing_rekey:
        print("\nMISSING_REKEY -- the game has a row, but that row carries a different game's id:")
        for g, row in found.missing_rekey:
            print(f"  espn={g.espn_id} {g.label()} [{g.status} {g.away_score}-{g.home_score}]")
            print(f"      event {row.id} sits at {row.commence:%Y-%m-%d %H:%M}Z holding "
                  f"espn={row.espn_id}")

    if found.duplicate_id:
        print("\nDUPLICATE_ID -- one provider id on several rows:")
        for g, held in found.duplicate_id:
            print(f"  espn={g.espn_id} {g.label()}")
            for row in held:
                print(f"      event {row.id} commence={row.commence:%Y-%m-%d %H:%M}Z "
                      f"status={row.status} score={row.away_score}-{row.home_score}")

    if found.misdated:
        print("\nMISDATED -- we hold the id, our time is not that game's time:")
        for g, row, hours in sorted(found.misdated, key=lambda x: -x[2]):
            print(f"  event {row.id} espn={g.espn_id} {row.away_name} @ {row.home_name}")
            print(f"      ours={row.commence:%Y-%m-%d %H:%M}Z  truth={g.commence:%Y-%m-%d %H:%M}Z"
                  f"  drift={hours:.1f}h  status={row.status}")

    if found.wrong_score:
        print("\nWRONG_SCORE -- settled in truth, our score disagrees:")
        for g, row in found.wrong_score:
            print(f"  event {row.id} espn={g.espn_id} {g.label()}")
            print(f"      ours={row.away_score}-{row.home_score}  "
                  f"truth={g.away_score}-{g.home_score} ({g.status})")

    if found.stuck_live:
        print("\nSTUCK_LIVE -- final in truth, still live for us:")
        for g, row in found.stuck_live:
            print(f"  event {row.id} espn={g.espn_id} {g.label()} "
                  f"ours={row.away_score}-{row.home_score}")

    if found.team_miswired:
        print("\nTEAM_MISWIRED -- team_id dereferences to a different club (#1798):")
        for row, side, team_id, actual, expected in found.team_miswired:
            print(f"  event {row.id} {row.away_name} @ {row.home_name} "
                  f"({row.commence:%Y-%m-%d})")
            print(f"      {side}_team_id={team_id} -> '{actual}'   row says '{expected}'")


def emit_json(found: Findings, truth: dict, rows: list, start, end, path: str) -> None:
    """Write findings machine-readably, for the settlement-contamination census (339T item 3).

    The printed report is for a human; this is for the next script in the chain. It carries
    the SCORE PAIR on both sides deliberately -- a downstream re-grade adjudication needs the
    evidence, not the verdict, and re-reading it out of a text report is how a transcription
    error becomes a wrong is_winner.
    """
    payload = {
        "range": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "truth_games": len(truth),
        "our_rows": len(rows),
        "statsapi_unmatched": found.statsapi_unmatched,
        "wrong_score": [
            {
                "event_id": row.id, "espn_id": g.espn_id, "game_pk": g.game_pk,
                "label": g.label(), "commence_ours": row.commence.isoformat(),
                "commence_truth": g.commence.isoformat(), "status_ours": row.status,
                "status_truth": g.status,
                "ours": [row.away_score, row.home_score],
                "truth": [g.away_score, g.home_score],
            }
            for g, row in found.wrong_score
        ],
        "stuck_live": [
            {
                "event_id": row.id, "espn_id": g.espn_id, "label": g.label(),
                "ours": [row.away_score, row.home_score],
                "truth": [g.away_score, g.home_score], "status_truth": g.status,
            }
            for g, row in found.stuck_live
        ],
        "misdated": [
            {
                "event_id": row.id, "espn_id": g.espn_id, "drift_hours": round(hours, 2),
                "commence_ours": row.commence.isoformat(),
                "commence_truth": g.commence.isoformat(), "status_ours": row.status,
            }
            for g, row, hours in found.misdated
        ],
        "missing_rekey": [
            {
                "truth_espn_id": g.espn_id, "label": g.label(),
                "impostor_event_id": row.id, "impostor_holds_espn_id": row.espn_id,
                "impostor_commence": row.commence.isoformat(),
            }
            for g, row in found.missing_rekey
        ],
        "missing": [
            {"espn_id": g.espn_id, "game_pk": g.game_pk, "label": g.label(),
             "commence": g.commence.isoformat()}
            for g in found.missing
        ],
        "duplicate_id": [
            {"espn_id": g.espn_id, "label": g.label(),
             "event_ids": [r.id for r in held]}
            for g, held in found.duplicate_id
        ],
        "team_miswired": [
            {"event_id": row.id, "side": side, "team_id": team_id,
             "dereferences_to": actual, "row_says": expected,
             "commence": row.commence.isoformat()}
            for row, side, team_id, actual, expected in found.team_miswired
        ],
    }
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\n[emitted {path}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (UTC), inclusive")
    ap.add_argument("--summary", action="store_true", help="counts only, no per-finding detail")
    ap.add_argument("--json", dest="json_path", help="also write findings as JSON to this path")
    args = ap.parse_args()

    start = _parse_iso(f"{args.start}T00:00:00Z")
    end = _parse_iso(f"{args.end}T00:00:00Z")

    truth = fetch_espn_truth(start, end)
    unmatched = overlay_statsapi(truth, start, end)
    rows = fetch_our_rows(start, end)
    teams = fetch_team_names(
        {t for r in rows for t in (r.away_team_id, r.home_team_id) if t}
    )

    found = reconcile(truth, rows, teams)
    found.statsapi_unmatched = unmatched
    report(found, truth, rows, args.summary)
    if args.json_path:
        emit_json(found, truth, rows, start, end, args.json_path)
    return 1 if found.total() else 0


if __name__ == "__main__":
    sys.exit(main())
