"""Read-only census of open/live duplicate event rows across every league (#13238).

Usage (ONLY after Alex's explicit go for one read-only run on production):
    heroku run --app bainluck --no-tty -- python3 scripts/audit_open_duplicate_events_13238.py

Guarantees:
- Read-only session (`conn.set_session(readonly=True)` + `SET TRANSACTION READ ONLY`).
- Writes nothing to Postgres, Redis, or disk.
- Excludes rows already suppressed with `provenance:duplicate-of:<id>`.
- Lists every pair of upcoming (`scheduled`) or `live` event rows in the same
  league that represent the same game, together with the recommended keeper row
  and why the two rows matched.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.event_twin_fold import _squash_for_league  # noqa: E402
from app.utils.name_normalization import names_match  # noqa: E402
from app.utils.prediction_market_matching import _fuzzy_team_match  # noqa: E402
from app.utils.proven_duplicates import canonical_id_from_tags  # noqa: E402
from app.utils.soccer_team_matching import soccer_pair_matches  # noqa: E402
from app.utils.sport_keys import league_identity  # noqa: E402

#: Normal kickoff separation window for two rows of the same game (4 hours).
#: Back-to-back games in a series sit >= 18 hours apart.
NORMAL_GAP_SECONDS = 4 * 3600
#: Wider window (16 hours, strictly below 18h) ONLY when one row carries a
#: midnight/date-only placeholder or Kalshi ticker expiration stamp.
PLACEHOLDER_GAP_SECONDS = 16 * 3600


@dataclass(frozen=True)
class OpenEventRow:
    event_id: int
    sport_id: int
    sport_key: str
    status: str
    commence_time: datetime
    commence_time_source: str | None
    home_team_name: str
    away_team_name: str
    external_id: str | None
    espn_id: str | None
    statpal_fixture_id: str | None
    home_score: int | None
    away_score: int | None
    event_tags: tuple[str, ...]
    win_prob_sources: tuple[str, ...]
    linked_market_count: int = 0
    odds_snapshot_count: int = 0


def _is_sportsbook_row(row: OpenEventRow) -> bool:
    ext = (row.external_id or "").strip()
    return bool(ext) and not ext.startswith("pm_")


def _is_placeholder_or_ticker_time(row: OpenEventRow) -> bool:
    if any("placeholder" in t.lower() for t in row.event_tags):
        return True
    src = (row.commence_time_source or "").strip().lower()
    if src in ("kalshi_ticker", "kalshi_ticker_time", "kalshi_occurrence"):
        return True
    t = row.commence_time
    return t.hour == 0 and t.minute == 0 and t.second == 0


def keeper_rank(row: OpenEventRow) -> tuple[int, int, int, int, int, int, int, int]:
    """Higher tuple wins as the canonical row to keep when folding a pair."""
    has_score = int(row.home_score is not None or row.away_score is not None)
    return (
        int(_is_sportsbook_row(row)),
        int(bool(row.espn_id)),
        int(bool(row.statpal_fixture_id)),
        has_score,
        int(row.odds_snapshot_count > 0),
        row.linked_market_count,
        len(row.win_prob_sources),
        -row.event_id,  # tie-break: older (lower) id
    )


def choose_keeper(a: OpenEventRow, b: OpenEventRow) -> tuple[OpenEventRow, OpenEventRow]:
    """Return `(keeper, duplicate)` using deterministic authority ranking."""
    return (a, b) if keeper_rank(a) >= keeper_rank(b) else (b, a)


def _pair_match_reason(a: OpenEventRow, b: OpenEventRow, league: str) -> str | None:
    """Return match reason string if two same-league rows are the same matchup."""
    # Never fold two rows carrying two DIFFERENT real IDs from the same authority.
    if a.espn_id and b.espn_id and a.espn_id != b.espn_id:
        return None
    if (
        _is_sportsbook_row(a)
        and _is_sportsbook_row(b)
        and a.external_id != b.external_id
    ):
        return None
    if (
        a.statpal_fixture_id
        and b.statpal_fixture_id
        and a.statpal_fixture_id != b.statpal_fixture_id
    ):
        return None

    # 1. Strict canonical fold key (includes VENUE_CLUB_SPELLINGS + LEAGUE_CLUB_SPELLINGS + NCAA)
    ah, aa = _squash_for_league(a.home_team_name, league), _squash_for_league(
        a.away_team_name, league
    )
    bh, ba = _squash_for_league(b.home_team_name, league), _squash_for_league(
        b.away_team_name, league
    )
    if ah and aa and bh and ba:
        if (ah == bh and aa == ba) or (ah == ba and aa == bh):
            return "canonical_fold_key"

    # 2. Soccer exonym / token-subset matcher (for soccer leagues)
    if a.sport_key.startswith("soccer_") or b.sport_key.startswith("soccer_"):
        if soccer_pair_matches(
            (a.home_team_name, a.away_team_name),
            (b.home_team_name, b.away_team_name),
        ) or soccer_pair_matches(
            (a.home_team_name, a.away_team_name),
            (b.away_team_name, b.home_team_name),
        ):
            return "soccer_pair_matches"

    # 3. Registry names_match (both teams normal or swapped)
    if (
        names_match(a.home_team_name, b.home_team_name)
        and names_match(a.away_team_name, b.away_team_name)
    ) or (
        names_match(a.home_team_name, b.away_team_name)
        and names_match(a.away_team_name, b.home_team_name)
    ):
        return "names_match"

    # 4. Prediction-market fuzzy matcher (both teams normal or swapped)
    if (
        _fuzzy_team_match(a.home_team_name, b.home_team_name)
        and _fuzzy_team_match(a.away_team_name, b.away_team_name)
    ) or (
        _fuzzy_team_match(a.home_team_name, b.away_team_name)
        and _fuzzy_team_match(a.away_team_name, b.home_team_name)
    ):
        return "pm_fuzzy_match"

    return None


def find_open_duplicate_pairs(rows: Sequence[OpenEventRow]) -> list[dict[str, Any]]:
    """Find every same-game duplicate pair among unsuppressed open/live events."""
    active = [
        r
        for r in rows
        if r.status in ("scheduled", "live")
        and canonical_id_from_tags(r.event_tags) is None
    ]
    by_league: dict[str, list[OpenEventRow]] = defaultdict(list)
    for row in active:
        league = league_identity(row.sport_key) or row.sport_key
        by_league[league].append(row)

    pairs: list[dict[str, Any]] = []
    for league, bucket in sorted(by_league.items()):
        bucket.sort(key=lambda r: (r.commence_time, r.event_id))
        n = len(bucket)
        for i in range(n):
            a = bucket[i]
            for j in range(i + 1, n):
                b = bucket[j]
                gap_s = abs((b.commence_time - a.commence_time).total_seconds())
                if gap_s > PLACEHOLDER_GAP_SECONDS:
                    break
                max_gap = (
                    PLACEHOLDER_GAP_SECONDS
                    if (_is_placeholder_or_ticker_time(a) or _is_placeholder_or_ticker_time(b))
                    else NORMAL_GAP_SECONDS
                )
                if gap_s > max_gap:
                    continue
                reason = _pair_match_reason(a, b, league)
                if reason is None:
                    continue
                keeper, dup = choose_keeper(a, b)
                pairs.append(
                    {
                        "league": league,
                        "sport_key": keeper.sport_key,
                        "match_reason": reason,
                        "time_gap_minutes": round(gap_s / 60.0, 1),
                        "keeper": {
                            "id": keeper.event_id,
                            "status": keeper.status,
                            "commence_time": keeper.commence_time.isoformat(),
                            "away": keeper.away_team_name,
                            "home": keeper.home_team_name,
                            "external_id": keeper.external_id,
                            "espn_id": keeper.espn_id,
                            "statpal_fixture_id": keeper.statpal_fixture_id,
                            "score": (
                                f"{keeper.away_score}-{keeper.home_score}"
                                if keeper.home_score is not None or keeper.away_score is not None
                                else None
                            ),
                            "sources": list(keeper.win_prob_sources),
                            "linked_markets": keeper.linked_market_count,
                            "odds_snapshots": keeper.odds_snapshot_count,
                        },
                        "duplicate": {
                            "id": dup.event_id,
                            "status": dup.status,
                            "commence_time": dup.commence_time.isoformat(),
                            "away": dup.away_team_name,
                            "home": dup.home_team_name,
                            "external_id": dup.external_id,
                            "espn_id": dup.espn_id,
                            "statpal_fixture_id": dup.statpal_fixture_id,
                            "score": (
                                f"{dup.away_score}-{dup.home_score}"
                                if dup.home_score is not None or dup.away_score is not None
                                else None
                            ),
                            "sources": list(dup.win_prob_sources),
                            "linked_markets": dup.linked_market_count,
                            "odds_snapshots": dup.odds_snapshot_count,
                        },
                    }
                )
    return pairs


def _fetch_open_events_readonly(hours_back: int, days_ahead: int) -> list[OpenEventRow]:
    import psycopg2

    db_url = (os.getenv("DATABASE_URL") or "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://") :]

    conn = psycopg2.connect(db_url)
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """
                WITH open_events AS (
                    SELECT
                        e.id,
                        e.sport_id,
                        s.key AS sport_key,
                        e.status,
                        e.commence_time,
                        e.commence_time_source,
                        e.home_team_name,
                        e.away_team_name,
                        e.external_id,
                        e.espn_id,
                        e.statpal_fixture_id,
                        e.home_score,
                        e.away_score,
                        e.event_tags,
                        e.win_probability_sources
                    FROM events e
                    JOIN sports s ON s.id = e.sport_id
                    WHERE e.status IN ('scheduled', 'live')
                      AND e.commence_time >= NOW() - (%s || ' hours')::interval
                      AND e.commence_time <= NOW() + (%s || ' days')::interval
                ),
                fm AS (
                    SELECT event_id, COUNT(*) AS cnt
                    FROM futures_markets
                    WHERE event_id IN (SELECT id FROM open_events)
                    GROUP BY event_id
                ),
                osnap AS (
                    SELECT event_id, COUNT(*) AS cnt
                    FROM odds_snapshots
                    WHERE event_id IN (SELECT id FROM open_events)
                    GROUP BY event_id
                )
                SELECT
                    oe.id,
                    oe.sport_id,
                    oe.sport_key,
                    oe.status,
                    oe.commence_time,
                    oe.commence_time_source,
                    oe.home_team_name,
                    oe.away_team_name,
                    oe.external_id,
                    oe.espn_id,
                    oe.statpal_fixture_id,
                    oe.home_score,
                    oe.away_score,
                    oe.event_tags,
                    oe.win_probability_sources,
                    COALESCE(fm.cnt, 0) AS linked_market_count,
                    COALESCE(osnap.cnt, 0) AS odds_snapshot_count
                FROM open_events oe
                LEFT JOIN fm ON fm.event_id = oe.id
                LEFT JOIN osnap ON osnap.event_id = oe.id
                ORDER BY oe.sport_key, oe.commence_time, oe.id
                """,
                (int(hours_back), int(days_ahead)),
            )
            fetched = cur.fetchall()
        conn.rollback()
    finally:
        conn.close()

    rows: list[OpenEventRow] = []
    for rec in fetched:
        (
            eid,
            sport_id,
            sport_key,
            status,
            commence_time,
            commence_time_source,
            home_team_name,
            away_team_name,
            external_id,
            espn_id,
            statpal_fixture_id,
            home_score,
            away_score,
            event_tags,
            wps,
            linked_cnt,
            odds_cnt,
        ) = rec
        if commence_time is None:
            continue
        if commence_time.tzinfo is None:
            commence_time = commence_time.replace(tzinfo=timezone.utc)
        tags = tuple(str(t) for t in (event_tags or []) if isinstance(t, str))
        sources = tuple(sorted(wps.keys())) if isinstance(wps, dict) else ()
        rows.append(
            OpenEventRow(
                event_id=int(eid),
                sport_id=int(sport_id),
                sport_key=str(sport_key or ""),
                status=str(status or ""),
                commence_time=commence_time,
                commence_time_source=str(commence_time_source) if commence_time_source else None,
                home_team_name=str(home_team_name or ""),
                away_team_name=str(away_team_name or ""),
                external_id=str(external_id) if external_id else None,
                espn_id=str(espn_id) if espn_id else None,
                statpal_fixture_id=str(statpal_fixture_id) if statpal_fixture_id else None,
                home_score=int(home_score) if home_score is not None else None,
                away_score=int(away_score) if away_score is not None else None,
                event_tags=tags,
                win_prob_sources=sources,
                linked_market_count=int(linked_cnt or 0),
                odds_snapshot_count=int(odds_cnt or 0),
            )
        )
    return rows


def format_report(
    rows: Sequence[OpenEventRow], pairs: Sequence[dict[str, Any]]
) -> str:
    by_sport = Counter(p["sport_key"] for p in pairs)
    lines = [
        f"Open/live duplicate event census (#13238, READ-ONLY): "
        f"scanned={len(rows)} active_rows pairs={len(pairs)} leagues_affected={len(by_sport)}"
    ]
    if by_sport:
        lines.append("By league:")
        for sp, cnt in sorted(by_sport.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  - {sp}: {cnt} pair(s)")
    if pairs:
        lines.append("Pairs (keeper <- duplicate):")
        for idx, p in enumerate(pairs, 1):
            k = p["keeper"]
            d = p["duplicate"]
            lines.append(
                f"  {idx}. [{p['sport_key']}] ({p['match_reason']}, gap={p['time_gap_minutes']}m) "
                f"KEEP {k['id']} ({k['status']}, ext={bool(k['external_id'])}, espn={bool(k['espn_id'])}, "
                f"mkts={k['linked_markets']}, odds={k['odds_snapshots']}, src={k['sources']}) "
                f"'{k['away']} @ {k['home']}' [{k['commence_time']}]  <--  "
                f"DUP {d['id']} ({d['status']}, ext={bool(d['external_id'])}, espn={bool(d['espn_id'])}, "
                f"mkts={d['linked_markets']}, odds={d['odds_snapshots']}, src={d['sources']}) "
                f"'{d['away']} @ {d['home']}' [{d['commence_time']}]"
            )
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only census of open/live duplicate event rows across every league (#13238)."
    )
    parser.add_argument("--hours-back", type=int, default=12)
    parser.add_argument("--days-ahead", type=int, default=14)
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    rows = _fetch_open_events_readonly(args.hours_back, args.days_ahead)
    pairs = find_open_duplicate_pairs(rows)
    if args.json:
        print(
            json.dumps(
                {
                    "scanned_rows": len(rows),
                    "pair_count": len(pairs),
                    "pairs": pairs,
                },
                indent=2,
            )
        )
    else:
        print(format_report(rows, pairs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
