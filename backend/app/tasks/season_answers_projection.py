"""T2-1 (#5058): project a league's two season answers into a tiny cache entry.

WHY A PROJECTION AND NOT A QUERY. ``/typeahead`` is the first surface a person
touches and it is measured against a 500 ms p50 (ruling 137). The two facts a
team card needs live in two expensive places — a 110 KB championship-grid
payload and a per-team ladder of seventeen outcomes — and neither is affordable
per keystroke. So the electing happens ONCE an hour, in the beat that already
built the grid, and the dropdown reads a few kilobytes of already-decided
answers.

WHAT MAKES THIS SAFE TO BE A SECOND COPY. ``grid_register``'s docstring is right
that a second copy of truth is a hazard, and the answer here is that this copy
is *derived in the same pass as the original and never recomputed*: the playoff
number is lifted verbatim out of the grid payload the beat just published, so
the dropdown and ``/api/playoffs/{slug}`` cannot print different numbers for the
same question — there is only one computation. The wins number has no original
to disagree with; the grid has no wins column.

WHAT IT COSTS WHEN IT FAILS. Nothing on the reader's path: a missing, stale or
unparseable key means the team row renders exactly as it did before this
existed. The write is wrapped by its caller so a projection failure can never
fail the grid warm it rides on — the grid is the load-bearing product, this is
the passenger.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.league_configs import LeagueConfig
from app.models.models import FuturesMarket, FuturesOutcome
from app.utils.season_answers import (
    build_playoff_answer,
    build_wins_answer,
    normalize_team_key,
    order_answers,
    parse_wins_rung,
    parse_wins_subject,
    parse_wins_ticker,
    pick_wins_rung,
    resolve_subject_to_team,
)

logger = logging.getLogger(__name__)

#: One key per SPORT KEY, not per league slug. The reader is the typeahead team
#: pool, whose rows carry `sports.key` and know nothing about grid slugs.
SEASON_ANSWERS_KEY_PREFIX = "bainluck:season_answers:"

#: Two hours against an hourly beat. Long enough that one missed warm leaves the
#: answers standing rather than blanking every team card in the product; short
#: enough that a league whose beat has stopped goes quiet within two cycles
#: instead of serving a dead season forever.
SEASON_ANSWERS_TTL_S = 7200

#: Schema stamp so a reader can refuse a shape it does not understand instead of
#: guessing at one. Bump when the answer wire shape changes.
SEASON_ANSWERS_SCHEMA = "season-answers/v1"


def season_answers_key(sport_key: str) -> str:
    return f"{SEASON_ANSWERS_KEY_PREFIX}{sport_key}"


def _make_playoffs_label(config: LeagueConfig) -> str | None:
    """The league's own word for the column, or ``None`` if it has no such column.

    Read from the grid config rather than written here: the grid page and the
    dropdown then say the same thing about the same question, and a league that
    calls it "Make Playoff" keeps calling it that on both surfaces.
    """
    for column in config.columns:
        if column.key == "make_playoffs":
            return column.label
    return None


async def _load_wins_ladders(
    db: AsyncSession,
    series: list[str],
) -> list[dict[str, Any]]:
    """Every open season-wins market in ``series``, with its priced rungs.

    One query for the whole league. Restricted to ``status='open'`` markets:
    a settled ladder is not an answer, and Kalshi leaves settled rows readable
    for a long time (gotcha #33's sibling), so the status filter is what keeps
    last season out of this season's card.
    """
    if not series:
        return []

    stmt = (
        select(
            FuturesMarket.id,
            FuturesMarket.external_id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesOutcome.id.label("outcome_id"),
            FuturesOutcome.name.label("outcome_name"),
            FuturesOutcome.current_probability,
            FuturesOutcome.price_changed_at,
        )
        .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.status == "open",
            FuturesOutcome.current_probability.isnot(None),
            or_(*[FuturesMarket.external_id.like(f"{s}-%") for s in series]),
        )
    )
    rows = (await db.execute(stmt)).all()

    markets: dict[int, dict[str, Any]] = {}
    for row in rows:
        entry = markets.get(row.id)
        if entry is None:
            entry = markets[row.id] = {
                "market_id": row.id,
                "external_id": row.external_id,
                "name": row.name,
                "source": row.source,
                "rungs": [],
            }
        threshold = parse_wins_rung(row.outcome_name)
        if threshold is None:
            continue
        entry["rungs"].append(
            {
                "threshold": threshold,
                "probability": float(row.current_probability),
                "outcome_id": row.outcome_id,
                "price_changed_at": row.price_changed_at,
            }
        )
    return list(markets.values())


def _wins_answers_by_team(
    ladders: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    season: str | None,
) -> dict[int, dict[str, Any]]:
    """Elect one wins answer per team, keyed by the index of the team in ``teams``.

    A team reached by two ladders keeps NEITHER. Two open season-wins markets
    for one club means the venue is carrying two seasons, or our subject
    resolution has folded two clubs together; in both cases the card would be
    printing a number whose question nobody can name.
    """
    index_of = {id(t): i for i, t in enumerate(teams)}

    # Resolve FIRST, elect second. Doing it the other way round makes the
    # two-ladder test depend on whether the first ladder happened to produce an
    # answer: a broken ladder followed by a good one for the same club would
    # look like a single uncontested claim and the good one would print.
    by_index: dict[int, list[dict[str, Any]]] = {}
    for ladder in ladders:
        if parse_wins_ticker(ladder["external_id"]) is None:
            continue
        team = resolve_subject_to_team(parse_wins_subject(ladder["name"]), teams)
        if team is None:
            continue
        by_index.setdefault(index_of[id(team)], []).append(ladder)

    picked: dict[int, dict[str, Any]] = {}
    for idx, claims in by_index.items():
        if len(claims) != 1:
            logger.warning(
                "Season wins for team index %d: %d open ladders claim it "
                "(%s) — showing none (#5058)",
                idx, len(claims), ", ".join(str(c["external_id"]) for c in claims),
            )
            continue
        ladder = claims[0]
        chosen = pick_wins_rung(
            [(r["threshold"], r["probability"]) for r in ladder["rungs"]]
        )
        if chosen is None:
            continue
        threshold, probability = chosen
        rung = next(
            r for r in ladder["rungs"]
            if r["threshold"] == threshold and r["probability"] == probability
        )
        observed = rung["price_changed_at"]
        picked[idx] = build_wins_answer(
            threshold=threshold,
            probability=probability,
            season=season,
            market_id=ladder["market_id"],
            outcome_id=rung["outcome_id"],
            source=ladder["source"],
            market_name=ladder["name"],
            observed_at=observed.isoformat() if observed is not None else None,
        )
    return picked


def build_projection(
    config: LeagueConfig,
    grid: dict[str, Any],
    ladders: list[dict[str, Any]],
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    """Compose the cache payload from a grid result and the league's ladders.

    Pure apart from the stamp it is handed, so the whole shape is testable
    without Redis, a database or a clock.
    """
    season = grid.get("season")
    playoff_label = _make_playoffs_label(config)
    teams = [t for t in (grid.get("teams") or []) if isinstance(t, dict)]
    wins_by_index = _wins_answers_by_team(ladders, teams, season)

    entries: list[dict[str, Any]] = []
    for idx, team in enumerate(teams):
        answers: list[dict[str, Any]] = []
        wins = wins_by_index.get(idx)
        if wins is not None:
            answers.append(wins)
        if playoff_label:
            playoff = build_playoff_answer(
                (team.get("cells") or {}).get("make_playoffs"),
                label=playoff_label,
                season=season,
            )
            if playoff is not None:
                answers.append(playoff)
        if not answers:
            continue
        entries.append(
            {
                "team_id": team.get("team_id"),
                "name": team.get("name"),
                "name_key": normalize_team_key(team.get("name")),
                "answers": order_answers(answers),
            }
        )

    return {
        "schema": SEASON_ANSWERS_SCHEMA,
        "league": config.slug,
        "season": season,
        "generated_at": generated_at.isoformat(),
        "teams": entries,
    }


async def write_season_answers_projection(
    rc: Any,
    config: LeagueConfig,
    grid: dict[str, Any],
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build and publish the projection for one league. Returns a run summary.

    ``rc`` is a SYNCHRONOUS Redis client, matching the grid warm's own client —
    the caller is a Celery task, not a request.

    🔴 Publishes nothing when the projection is empty. An empty write does not
    merely fail to help: it overwrites a good entry with a blank one and takes
    every team card in that league down with it, which is exactly the shape of
    failure the grid warm's own `_grid_payload_usable` gate exists to stop.
    """
    stamp = now or datetime.now(timezone.utc)
    ladders = await _load_wins_ladders(db, list(config.wins_series or []))
    projection = build_projection(config, grid, ladders, generated_at=stamp)

    entries = projection["teams"]
    if not entries:
        logger.warning(
            "Season answers for %s produced 0 teams — keeping any existing "
            "entry rather than publishing a blank one (#5058)",
            config.slug,
        )
        return {"outcome": "empty", "teams": 0, "keys": []}

    payload = json.dumps(projection, default=str)
    keys = [season_answers_key(sk) for sk in (config.sport_keys or [])]
    for key in keys:
        rc.setex(key, SEASON_ANSWERS_TTL_S, payload)

    wins = sum(
        1 for e in entries
        if any(a.get("key") == "season_wins" for a in e["answers"])
    )
    logger.info(
        "Season answers for %s: %d teams (%d with a wins ladder) -> %s",
        config.slug, len(entries), wins, ", ".join(keys) or "no sport key",
    )
    return {
        "outcome": "ok",
        "teams": len(entries),
        "wins_answers": wins,
        "keys": keys,
    }
