"""One verified tennis observation for the score-first headline (#12712).

The existing StatPal poll writes sets, games, points and their read time as one
snapshot. A reader never borrows points from another source or an older line.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.utils.authority_tennis_names import tennis_names_agree

# The poll runs every 30 seconds. Missing four passes must not leave a current
# point score on screen. Final sets/games remain readable without a live clock.
POINT_MAX_AGE_SECONDS = 120


def _moment(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        return parsed if isinstance(parsed, datetime) and parsed.tzinfo else None
    except ValueError:
        return None


def _sets(value: Any) -> list[list[int]] | None:
    if not isinstance(value, list) or not 1 <= len(value) <= 5:
        return None
    if any(
        not isinstance(pair, list)
        or len(pair) != 2
        or any(type(n) is not int or not 0 <= n <= 99 for n in pair)
        for pair in value
    ):
        return None
    return value


def _won_sets(sets: list[list[int]]) -> tuple[int, int]:
    def won(a: int, b: int) -> bool:
        return (a >= 6 and a - b >= 2) or (a == 7 and b == 6)

    return (sum(won(h, a) for h, a in sets), sum(won(a, h) for h, a in sets))


def _point(value: Any, tiebreak: bool | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if tiebreak is True:
        return (
            str(int(value))
            if value.isascii() and value.isdigit() and int(value) <= 99
            else None
        )
    if tiebreak is not False:
        return None
    return {
        "0": "0",
        "15": "15",
        "30": "30",
        "40": "40",
        "A": "Ad",
        "AD": "Ad",
        "Ad": "Ad",
    }.get(value)


def statpal_tennis_values(
    event: Any, fixtures: list[Any], read_at: datetime
) -> tuple[dict, str | None]:
    """An already anchored live fixture, with both sides verified, or a reason."""
    anchor = getattr(event, "statpal_fixture_id", None)
    if not anchor:
        return {}, "no-statpal-anchor"
    matches = [f for f in fixtures if str(f.fixture_id) == str(anchor)]
    if len(matches) != 1:
        return {}, "fixture-absent" if not matches else "fixture-ambiguous"
    fixture = matches[0]
    if event.status != "live" or fixture.status != "live":
        return {}, "not-live"
    direct = tennis_names_agree(
        event.home_team_name, fixture.home_team
    ) and tennis_names_agree(event.away_team_name, fixture.away_team)
    reverse = tennis_names_agree(
        event.home_team_name, fixture.away_team
    ) and tennis_names_agree(event.away_team_name, fixture.home_team)
    if direct == reverse:
        return {}, "orientation-unresolved"
    hp, ap = fixture.home_q_scores or {}, fixture.away_q_scores or {}
    keys = [f"s{i}" for i in range(1, len(hp) + 1)]
    if not keys or set(hp) != set(keys) or set(ap) != set(keys):
        return {}, "set-line-incomplete"
    sets = [[hp[k], ap[k]] for k in keys]
    if reverse:
        sets = [pair[::-1] for pair in sets]
    home, away = (
        (fixture.away_score, fixture.home_score)
        if reverse
        else (fixture.home_score, fixture.away_score)
    )
    if (
        _sets(sets) is None
        or type(home) is not int
        or type(away) is not int
        or _won_sets(sets) != (home, away)
    ):
        return {}, "set-score-disagrees"
    box = event.box_score_data if isinstance(event.box_score_data, dict) else {}
    old = box.get("tennis") or {}
    old_at = _moment(old.get("observed_at")) if isinstance(old, dict) else None
    if old_at is not None and old_at >= read_at:
        return {}, "newer-observation-held"
    score_at = _moment(getattr(event, "score_observed_at", None))
    if score_at is not None and score_at > read_at:
        return {}, "newer-observation-held"
    # A board still showing an earlier set must not undo a later score.
    if any(
        type(was) is int and now < was
        for now, was in ((home, event.home_score), (away, event.away_score))
    ):
        return {}, "set-score-behind"
    if isinstance(old, dict) and _sets(old.get("sets")) is not None:
        if sum(map(sum, sets)) < sum(map(sum, old["sets"])):
            return {}, "games-behind"
    points = [
        _point(fixture.home_game_score, fixture.tennis_tiebreak),
        _point(fixture.away_game_score, fixture.tennis_tiebreak),
    ]
    serves = [fixture.home_serving, fixture.away_serving]
    if reverse:
        points.reverse()
        serves.reverse()
    line = {
        "sets": sets,
        "home_games": sum(p[0] for p in sets),
        "away_games": sum(p[1] for p in sets),
        "home_sets": home,
        "away_sets": away,
        "source": "statpal",
        "fixture_id": str(anchor),
        "home_name": event.home_team_name,
        "away_name": event.away_team_name,
        "observed_at": read_at.isoformat(),
    }
    if all(p is not None for p in points) and points != ["Ad", "Ad"]:
        line.update(
            home_points=points[0],
            away_points=points[1],
            tiebreak=fixture.tennis_tiebreak,
        )
    if serves == [True, False] or serves == [False, True]:
        line["serving"] = "home" if serves[0] else "away"
    return {
        "home_score": home,
        "away_score": away,
        "box_score_data": {**box, "tennis": line},
        "score_source": "statpal",
        "score_observed_at": read_at,
    }, None


def served_tennis_line(event: Any, response: dict, now: datetime) -> dict | None:
    """Validate the whole line against the score being served; expire points."""
    sport = getattr(getattr(event, "sport", None), "key", "")
    if not isinstance(sport, str) or not sport.startswith("tennis"):
        return None
    box = event.box_score_data if isinstance(event.box_score_data, dict) else {}
    line = box.get("tennis")
    if not isinstance(line, dict) or _sets(line.get("sets")) is None:
        return None
    if _won_sets(line["sets"]) != (
        response.get("home_score"),
        response.get("away_score"),
    ):
        return None
    if line.get("source") not in {"espn", "statpal"}:
        return None
    if line["source"] == "statpal" and (
        line.get("fixture_id") != str(getattr(event, "statpal_fixture_id", None))
        or line.get("home_name") != event.home_team_name
        or line.get("away_name") != event.away_team_name
        or (line.get("home_sets"), line.get("away_sets"))
        != (response.get("home_score"), response.get("away_score"))
    ):
        return None
    result = deepcopy(line)
    stamp = _moment(result.get("observed_at"))
    current = (
        response.get("status") == "live"
        and stamp is not None
        and 0 <= (now - stamp).total_seconds() <= POINT_MAX_AGE_SECONDS
    )
    points = [
        _point(result.get(k), result.get("tiebreak"))
        for k in ("home_points", "away_points")
    ]
    if result["source"] != "statpal" or not current or any(p is None for p in points):
        for key in ("home_points", "away_points", "serving", "tiebreak"):
            result.pop(key, None)
    # Internal identity witnesses are not reader payload fields.
    for key in ("home_name", "away_name", "fixture_id"):
        result.pop(key, None)
    return result


def attach_tennis_score(event: Any, response: dict, now: datetime) -> None:
    sport = getattr(getattr(event, "sport", None), "key", "")
    if not isinstance(sport, str) or not sport.startswith("tennis"):
        return
    # The installed reader uses this historical key for points. A generic
    # period clock must never be mistaken for a tennis point score.
    if isinstance(response.get("espn"), dict):
        response["espn"].pop("game_clock", None)
    line = served_tennis_line(event, response, now)
    response.pop("linescore", None)
    if line is None:
        return
    response["linescore"] = line
    response.setdefault("box_score_data", {}).update(
        home_period_scores=[p[0] for p in line["sets"]],
        away_period_scores=[p[1] for p in line["sets"]],
    )
    # #12712's installed parser expects AWAY, HOME and ordinary game points.
    # Numeric tiebreak points stay explicit in linescore for the native owner.
    if "home_points" in line and line.get("tiebreak") is False:
        response.setdefault("espn", {})[
            "game_clock"
        ] = f"{line['away_points']}-{line['home_points']}"


def tennis_point_cache_expiry(payload: dict) -> float | None:
    line = payload.get("linescore")
    if not isinstance(line, dict) or "home_points" not in line:
        return None
    stamp = _moment(line.get("observed_at"))
    return stamp.timestamp() + POINT_MAX_AGE_SECONDS if stamp else 0.0
