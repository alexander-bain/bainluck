"""Replay the twin fold over a captured production population, master vs HEAD.

#6007. Reads the rows exactly as `/api/admin/db-query` returned them, hydrates
doubles that carry only the attributes the fold reads, and drives the REAL
`fold_twin_events` — never a re-implementation of it. Run it once on
`origin/master` and once on the branch and diff the two reports:

    python3 tools/replay_6007_date_only_fold.py /tmp/pop_leagues.json /tmp/pop_other.json

Prints, per sport key: rows in, rows served, rows folded, and every folded
group with its survivor and its losers, so a reviewer can see WHICH card a
reader stops seeing twice and which row is the one that survives.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from types import SimpleNamespace


class Sport(SimpleNamespace):
    pass


def load(paths: list[str]) -> list:
    rows = []
    for path in paths:
        payload = json.load(open(path))
        cols = payload["columns"]
        for raw in payload["rows"]:
            r = dict(zip(cols, raw))
            sources = r["win_probability_sources"]
            if isinstance(sources, str):
                try:
                    sources = json.loads(sources)
                except Exception:
                    import ast

                    sources = ast.literal_eval(sources)  # gotcha #40
            rows.append(
                SimpleNamespace(
                    id=r["id"],
                    sport_id=r["sport_id"],
                    sport=Sport(key=r["sport_key"]),
                    home_team_name=r["home_team_name"],
                    away_team_name=r["away_team_name"],
                    commence_time=datetime.fromisoformat(r["commence_time"]),
                    commence_time_source=r["commence_time_source"],
                    espn_id=r["espn_id"],
                    external_id=r["external_id"],
                    home_score=r["home_score"],
                    away_score=r["away_score"],
                    status=r["status"],
                    win_probability_sources=sources or {},
                )
            )
    return rows


def main() -> int:
    sys.path.insert(0, "backend")
    from app.utils import event_twin_fold as fold_module
    from app.utils.event_twin_fold import fold_twin_events

    # Record what `_elect` was handed, so the report can show WHICH card
    # absorbed which, and so the two false-fold audits below have groups to
    # run over. Wrapping rather than re-deriving: the groups audited are the
    # groups the real function elected from.
    elected_groups: list[list] = []
    real_elect = fold_module._elect

    def recording_elect(members, keep, result):
        elected_groups.append(list(members))
        return real_elect(members, keep, result)

    fold_module._elect = recording_elect

    rows = load(sys.argv[1:])
    by_sport: dict[str, list] = {}
    for row in rows:
        by_sport.setdefault(row.sport.key, []).append(row)

    total_in = total_out = 0
    for key in sorted(by_sport):
        population = by_sport[key]
        result = fold_twin_events(population)
        total_in += len(population)
        total_out += len(result.events)
        if not result.dropped_ids:
            print(f"{key}: {len(population)} in, 0 folded")
            continue
        print(
            f"{key}: {len(population)} in -> {len(result.events)} served, "
            f"{result.folded_count} folded"
        )
        by_id = {row.id: row for row in population}
        for dropped_id in sorted(result.dropped_ids):
            row = by_id[dropped_id]
            print(
                f"   DROPPED {row.id} {row.home_team_name} v {row.away_team_name} "
                f"{row.commence_time} src={row.commence_time_source} "
                f"status={row.status} score={row.home_score}-{row.away_score} "
                f"espn={bool(row.espn_id)} srcs={sorted(row.win_probability_sources)}"
            )
        for survivor_id in sorted(result.merged_sources):
            row = by_id[survivor_id]
            print(
                f"   GAINED  {row.id} {row.home_team_name} v {row.away_team_name} "
                f"{row.commence_time} status={row.status} "
                f"score={row.home_score}-{row.away_score} espn={bool(row.espn_id)} "
                f"srcs_after={sorted(result.merged_sources[survivor_id])}"
            )
    print(f"TOTAL {total_in} in -> {total_out} served, {total_in - total_out} folded")

    # The two objective false-fold tests #5964 used, re-run because #6007 is the
    # first change that folds a pair the clock alone would have refused. Either
    # failure means two real games were merged into one card.
    bad_ids = bad_scores = 0
    for members in elected_groups:
        espn = {m.espn_id for m in members if m.espn_id}
        if len(espn) > 1:
            bad_ids += 1
            print(f"FALSE FOLD: two espn_ids in one group {sorted(espn)}")
        lines = {
            (m.home_score, m.away_score)
            for m in members
            if m.home_score is not None or m.away_score is not None
        }
        if len(lines) > 1:
            bad_scores += 1
            print(
                f"FALSE FOLD: two scorelines in one group {sorted(lines)} "
                f"{[m.id for m in members]}"
            )
    print(
        f"AUDIT groups={len(elected_groups)} two_espn_ids={bad_ids} "
        f"two_scorelines={bad_scores}"
    )

    # And the election itself, for every group that folded a date-only row: the
    # survivor must be the row with the real kick-off, never the placeholder.
    from app.utils.event_twin_fold import is_kalshi_date_only, twin_identity_rank

    survived_dateless = 0
    for members in elected_groups:
        if not any(is_kalshi_date_only(m) for m in members):
            continue
        survivor = max(members, key=twin_identity_rank)
        losers = [m for m in members if m is not survivor]
        flag = "PLACEHOLDER SURVIVED" if is_kalshi_date_only(survivor) else "ok"
        if flag != "ok":
            survived_dateless += 1
        print(
            f"ELECTION {flag}: survivor {survivor.id} {survivor.home_team_name} v "
            f"{survivor.away_team_name} {survivor.commence_time} "
            f"status={survivor.status} score={survivor.home_score}-"
            f"{survivor.away_score} espn={bool(survivor.espn_id)} <- absorbed "
            f"{[(m.id, m.commence_time_source) for m in losers]}"
        )
    print(f"AUDIT date_only_groups_where_placeholder_won={survived_dateless}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
