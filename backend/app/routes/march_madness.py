"""
March Madness landing page endpoints.

Aggregates championship futures from Polymarket, Kalshi, and The Odds API for
the 2026 NCAA Men's and Women's Basketball Tournaments. Provides bracket data,
live game tracking, upset detection, cinderella watch, and historical seed
matchup context.

Two endpoints sharing one implementation:
  GET /api/march-madness/mens
  GET /api/march-madness/womens
"""

import logging
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_optional_user
from app.models.models import (
    Event,
    FuturesMarket,
    FuturesOddsSnapshot,
    User,
    UserFavorite,
)
from app.services.database import get_db
from app.utils.odds_math import probability_to_american
from app.data.seed_history import SEED_HISTORY, NOTABLE_UPSETS
from app.utils.seed_matchups import (
    get_first_round_seed_history,
    get_historical_upset_rate,
    get_seed_context_text,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Key dates — 2026 NCAA Tournament
# ============================================================================

_SELECTION_SUNDAY = datetime(2026, 3, 15, 23, 0, 0, tzinfo=timezone.utc)  # ~6PM ET
_FIRST_FOUR_START = datetime(2026, 3, 17, 23, 0, 0, tzinfo=timezone.utc)
_CHAMPIONSHIP_DATE = datetime(2026, 4, 7, 4, 0, 0, tzinfo=timezone.utc)

# Sport key prefixes for NCAA basketball
_SPORT_FILTERS = {
    "mens": {
        "sport_prefix": "basketball_ncaab",
        "llm_category": "basketball",
        "display_name": "NCAA Men's Basketball Tournament",
    },
    "womens": {
        "sport_prefix": "basketball_wncaab",
        "llm_category": "basketball",
        "display_name": "NCAA Women's Basketball Tournament",
    },
}

# Market name patterns that indicate NCAA championship futures
_NCAAB_CHAMPIONSHIP_PATTERNS = [
    "ncaa", "march madness", "final four", "sweet sixteen", "elite eight",
    "college basketball", "national champion", "ncaab",
]

_WOMENS_PATTERNS = [
    "women", "wncaab", "ncaaw",
]

# Round display order
ROUND_ORDER = [
    "First Four", "Round of 64", "Round of 32",
    "Sweet 16", "Elite Eight", "Final Four", "Championship",
]


# ============================================================================
# Helpers
# ============================================================================

_EXTRA_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})


def _strip_diacritics(s: str) -> str:
    """Remove accent marks and transliterate special letters."""
    s = s.translate(_EXTRA_TRANSLITERATIONS)
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _team_match_key(name: str) -> str:
    """Create a matching key for cross-source team dedup."""
    clean = _strip_diacritics(name.strip()).lower()
    # Remove common suffixes that vary across sources
    for suffix in [" bulldogs", " wildcats", " tigers", " bears", " eagles",
                   " cardinals", " huskies", " cavaliers", " tar heels",
                   " blue devils", " jayhawks", " boilermakers"]:
        if clean.endswith(suffix):
            # Keep school name, remove mascot only if the school name is long enough
            prefix = clean[: -len(suffix)]
            if len(prefix) >= 3:
                clean = prefix
            break
    # Normalize whitespace
    return " ".join(clean.split())


def _get_tournament_state() -> str:
    """Determine tournament state based on current time."""
    now = datetime.now(timezone.utc)
    if now < _SELECTION_SUNDAY:
        return "pre_selection"
    elif now < _FIRST_FOUR_START:
        return "pre_tournament"
    elif now < _CHAMPIONSHIP_DATE:
        return "in_progress"
    else:
        return "completed"


def _is_ncaab_championship_market(market_name: str, tournament_type: str) -> bool:
    """Check if a market name is an NCAAB championship futures market."""
    name_lower = market_name.lower()

    # Must match at least one NCAA basketball pattern
    has_ncaab = any(p in name_lower for p in _NCAAB_CHAMPIONSHIP_PATTERNS)
    if not has_ncaab:
        return False

    # Distinguish men's vs women's
    has_womens_signal = any(p in name_lower for p in _WOMENS_PATTERNS)

    if tournament_type == "womens":
        return has_womens_signal
    else:
        # Men's: accept if no women's signal present
        return not has_womens_signal


# ============================================================================
# Main endpoint implementation
# ============================================================================

async def _get_march_madness_data(
    tournament_type: str,
    db: AsyncSession,
    user: Optional[User],
) -> dict:
    """Build the full March Madness response for a tournament type."""
    now = datetime.now(timezone.utc)
    config = _SPORT_FILTERS[tournament_type]
    tournament_state = _get_tournament_state()

    # ==================================================================
    # 1. Championship futures — cross-source aggregation
    # ==================================================================
    futures_query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.external_id.ilike(f"{config['sport_prefix']}%"),
                FuturesMarket.llm_sport_category == config["llm_category"],
            ),
        )
    )
    result = await db.execute(futures_query)
    all_markets = result.scalars().unique().all()

    # Filter to championship markets for the right tournament type
    championship_markets = [
        m for m in all_markets
        if _is_ncaab_championship_market(m.name, tournament_type)
    ]

    logger.info(
        "March Madness %s: %d championship markets from %d total",
        tournament_type, len(championship_markets), len(all_markets),
    )

    # Merge teams across sources (same pattern as Oscars)
    team_data: dict[str, dict] = {}  # match_key -> aggregated data

    for market in championship_markets:
        source = market.source or "unknown"

        for outcome in market.outcomes:
            if outcome.current_probability is None:
                continue

            prob = float(outcome.current_probability)

            # Skip Kalshi 0.5 noise
            if source == "kalshi" and prob == 0.5:
                continue

            display_name = outcome.name.strip()
            key = _team_match_key(display_name)
            if not key:
                continue

            if key not in team_data:
                team_data[key] = {
                    "team_name": display_name,
                    "sources": {},
                    "probabilities": [],
                    "movement_24h": None,
                    "opening_probability": None,
                    "seed": None,
                    "region": None,
                    "is_eliminated": False,
                    "is_alma_mater": False,
                }

            team_data[key]["sources"][source] = round(prob, 3)
            team_data[key]["probabilities"].append(prob)

            # 24h movement
            if outcome.probability_change_24h is not None:
                existing = team_data[key]["movement_24h"]
                change = float(outcome.probability_change_24h)
                if existing is None or abs(change) > abs(existing):
                    team_data[key]["movement_24h"] = round(change, 4)

            # Opening probability
            if outcome.opening_probability is not None and team_data[key]["opening_probability"] is None:
                team_data[key]["opening_probability"] = round(float(outcome.opening_probability), 3)

    # Compute average probability and build response
    championship_odds = []
    for data in team_data.values():
        avg_prob = sum(data["probabilities"]) / len(data["probabilities"])
        championship_odds.append({
            "team_name": data["team_name"],
            "probability": round(avg_prob, 4),
            "movement_24h": data["movement_24h"],
            "opening_probability": data["opening_probability"],
            "sources": data["sources"],
            "seed": data["seed"],
            "region": data["region"],
            "is_eliminated": data["is_eliminated"],
            "is_alma_mater": data["is_alma_mater"],
            "american_odds": probability_to_american(avg_prob),
        })

    # Sort by probability descending
    championship_odds.sort(key=lambda t: t["probability"], reverse=True)

    # Normalize top teams' probabilities
    total_prob = sum(t["probability"] for t in championship_odds)
    if total_prob > 0:
        for team in championship_odds:
            team["probability"] = round(team["probability"] / total_prob, 4)
            team["american_odds"] = probability_to_american(team["probability"])

    # ==================================================================
    # 2. 24h Biggest movers (from FuturesOddsSnapshot)
    # ==================================================================
    all_outcome_ids = []
    outcome_id_to_team: dict[int, str] = {}
    for market in championship_markets:
        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                all_outcome_ids.append(outcome.id)
                outcome_id_to_team[outcome.id] = outcome.name.strip()

    prob_24h_ago: dict[int, float] = {}
    if all_outcome_ids:
        snapshot_subq = (
            select(
                FuturesOddsSnapshot.outcome_id,
                FuturesOddsSnapshot.probability,
                sqlfunc.row_number().over(
                    partition_by=FuturesOddsSnapshot.outcome_id,
                    order_by=FuturesOddsSnapshot.captured_at.desc(),
                ).label("rn"),
            )
            .where(
                FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
                FuturesOddsSnapshot.captured_at.between(
                    now - timedelta(hours=25),
                    now - timedelta(hours=23),
                ),
            )
            .subquery()
        )

        snap_result = await db.execute(
            select(snapshot_subq.c.outcome_id, snapshot_subq.c.probability)
            .where(snapshot_subq.c.rn == 1)
        )
        prob_24h_ago = {row.outcome_id: float(row.probability) for row in snap_result}

    # Build movers list
    biggest_movers = []
    for market in championship_markets:
        for outcome in market.outcomes:
            if outcome.current_probability is None:
                continue
            current = float(outcome.current_probability)
            past = prob_24h_ago.get(outcome.id)
            if past is not None:
                movement = current - past
                if abs(movement) >= 0.005:  # At least 0.5% change
                    biggest_movers.append({
                        "team_name": outcome.name.strip(),
                        "movement_24h": round(movement, 4),
                        "probability": round(current, 4),
                        "seed": None,
                    })

    # Sort by absolute movement descending, take top 10
    biggest_movers.sort(key=lambda m: abs(m["movement_24h"]), reverse=True)
    biggest_movers = biggest_movers[:10]

    # ==================================================================
    # 3. Tournament bracket games
    # ==================================================================
    bracket_games = []
    live_games = []
    upsets = []
    cinderellas = []

    if tournament_state in ("pre_tournament", "in_progress", "completed"):
        # Query tournament-tagged events
        bracket_query = (
            select(Event)
            .where(
                Event.is_tournament_game.is_(True),
                Event.tournament_type == tournament_type,
            )
            .order_by(Event.commence_time)
        )
        bracket_result = await db.execute(bracket_query)
        tournament_events = bracket_result.scalars().all()

        # Also enrich championship_odds with seed/region from bracket data
        team_seed_map: dict[str, int] = {}
        team_region_map: dict[str, str] = {}

        for event in tournament_events:
            game = {
                "event_id": event.id,
                "round": event.tournament_round,
                "region": event.tournament_region,
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "seed_home": event.tournament_seed_home,
                "seed_away": event.tournament_seed_away,
                "score_home": event.score_home,
                "score_away": event.score_away,
                "status": event.status,
                "commence_time": event.commence_time.isoformat() if event.commence_time else None,
            }

            # Add current odds if available
            if event.current_odds:
                home_prob = event.current_odds.get("home")
                away_prob = event.current_odds.get("away")
                game["prob_home"] = round(home_prob, 3) if home_prob else None
                game["prob_away"] = round(away_prob, 3) if away_prob else None
            else:
                game["prob_home"] = None
                game["prob_away"] = None

            # Historical upset rate for this seed matchup
            if event.tournament_seed_home and event.tournament_seed_away:
                hist = get_historical_upset_rate(
                    tournament_type,
                    event.tournament_seed_home,
                    event.tournament_seed_away,
                )
                game["historical_upset_rate"] = hist["upset_pct"] if hist else None
                game["seed_context"] = get_seed_context_text(
                    tournament_type,
                    min(event.tournament_seed_home, event.tournament_seed_away),
                    max(event.tournament_seed_home, event.tournament_seed_away),
                )
            else:
                game["historical_upset_rate"] = None
                game["seed_context"] = None

            # EI if available
            if event.raw_ei:
                game["ei"] = round(event.raw_ei * 100)
            else:
                game["ei"] = None

            bracket_games.append(game)

            # Track seeds/regions for championship odds enrichment
            if event.tournament_seed_home and event.home_team_name:
                team_seed_map[_team_match_key(event.home_team_name)] = event.tournament_seed_home
                if event.tournament_region:
                    team_region_map[_team_match_key(event.home_team_name)] = event.tournament_region
            if event.tournament_seed_away and event.away_team_name:
                team_seed_map[_team_match_key(event.away_team_name)] = event.tournament_seed_away
                if event.tournament_region:
                    team_region_map[_team_match_key(event.away_team_name)] = event.tournament_region

            # Live games (currently playing or starting within 6h)
            if event.status == "live":
                live_games.append(game)
            elif (event.status == "scheduled" and event.commence_time
                  and event.commence_time <= now + timedelta(hours=6)):
                live_games.append(game)

            # Upset detection (completed games where lower seed won)
            if event.status in ("completed", "closed") and event.score_home is not None and event.score_away is not None:
                seed_h = event.tournament_seed_home
                seed_a = event.tournament_seed_away
                if seed_h and seed_a and seed_h != seed_a:
                    home_won = event.score_home > event.score_away
                    # Upset = higher-numbered seed won
                    if (home_won and seed_h > seed_a) or (not home_won and seed_a > seed_h):
                        winner = event.home_team_name if home_won else event.away_team_name
                        loser = event.away_team_name if home_won else event.home_team_name
                        seed_winner = seed_h if home_won else seed_a
                        seed_loser = seed_a if home_won else seed_h

                        hist = get_historical_upset_rate(tournament_type, seed_winner, seed_loser)

                        upsets.append({
                            "event_id": event.id,
                            "winner": winner,
                            "loser": loser,
                            "seed_winner": seed_winner,
                            "seed_loser": seed_loser,
                            "score": f"{event.score_home}-{event.score_away}" if home_won else f"{event.score_away}-{event.score_home}",
                            "winner_pre_game_prob": game.get("prob_home") if home_won else game.get("prob_away"),
                            "historical_upset_rate": hist["upset_pct"] if hist else None,
                            "round": event.tournament_round,
                        })

        # Enrich championship odds with seed/region data
        for team in championship_odds:
            key = _team_match_key(team["team_name"])
            if key in team_seed_map:
                team["seed"] = team_seed_map[key]
            if key in team_region_map:
                team["region"] = team_region_map[key]

        # Cinderella watch: seeds 9+ still alive with title odds
        # Find teams still alive by looking at which teams haven't lost
        eliminated_teams: set[str] = set()
        for event in tournament_events:
            if event.status in ("completed", "closed") and event.score_home is not None and event.score_away is not None:
                if event.score_home > event.score_away:
                    eliminated_teams.add(_team_match_key(event.away_team_name))
                else:
                    eliminated_teams.add(_team_match_key(event.home_team_name))

        # Mark eliminated teams in championship odds
        for team in championship_odds:
            key = _team_match_key(team["team_name"])
            if key in eliminated_teams:
                team["is_eliminated"] = True

        # Build cinderella list
        for team in championship_odds:
            seed = team.get("seed")
            if seed and seed >= 9 and not team["is_eliminated"] and team["probability"] > 0:
                games_won = 0
                games_played = 0
                for event in tournament_events:
                    tk_home = _team_match_key(event.home_team_name) if event.home_team_name else ""
                    tk_away = _team_match_key(event.away_team_name) if event.away_team_name else ""
                    team_key = _team_match_key(team["team_name"])
                    if team_key in (tk_home, tk_away) and event.status in ("completed", "closed"):
                        games_played += 1
                        if event.score_home is not None and event.score_away is not None:
                            if (team_key == tk_home and event.score_home > event.score_away) or \
                               (team_key == tk_away and event.score_away > event.score_home):
                                games_won += 1

                cinderellas.append({
                    "team_name": team["team_name"],
                    "seed": seed,
                    "region": team.get("region"),
                    "title_odds": team["probability"],
                    "games_won": games_won,
                    "games_played": games_played,
                })

        # Sort cinderellas by games won then title odds
        cinderellas.sort(key=lambda c: (c["games_won"], c["title_odds"]), reverse=True)

    # Sort upsets by seed differential
    upsets.sort(key=lambda u: u["seed_winner"] - u["seed_loser"], reverse=True)

    # ==================================================================
    # 4. Alma mater personalization
    # ==================================================================
    alma_mater_teams: list[str] = []
    if user:
        fav_result = await db.execute(
            select(UserFavorite)
            .where(
                UserFavorite.user_id == user.id,
                UserFavorite.relation_type == "alma_mater",
            )
        )
        favorites = fav_result.scalars().all()
        for fav in favorites:
            if fav.team and fav.team.name:
                alma_mater_teams.append(fav.team.name)

        # Mark alma mater teams in championship odds
        alma_keys = {_team_match_key(name) for name in alma_mater_teams}
        for team in championship_odds:
            if _team_match_key(team["team_name"]) in alma_keys:
                team["is_alma_mater"] = True

    # ==================================================================
    # 5. Seed history (static reference data)
    # ==================================================================
    seed_history = get_first_round_seed_history(tournament_type)
    notable_upsets = NOTABLE_UPSETS.get(tournament_type, [])

    # ==================================================================
    # Build bracket structure
    # ==================================================================
    bracket = None
    if bracket_games:
        regions = sorted(set(
            g["region"] for g in bracket_games if g.get("region")
        ))
        bracket = {
            "regions": regions if regions else ["East", "West", "South", "Midwest"],
            "games": bracket_games,
        }

    return {
        "tournament_type": tournament_type,
        "tournament_state": tournament_state,
        "display_name": config["display_name"],
        "selection_sunday": _SELECTION_SUNDAY.isoformat(),
        "championship_date": _CHAMPIONSHIP_DATE.isoformat(),
        "championship_odds": championship_odds,
        "bracket": bracket,
        "live_games": live_games,
        "upsets": upsets,
        "cinderellas": cinderellas,
        "biggest_movers": biggest_movers,
        "seed_history": seed_history,
        "notable_upsets": notable_upsets,
        "alma_mater_teams": alma_mater_teams if user else None,
    }


# ============================================================================
# Route handlers
# ============================================================================

@router.get("/mens")
async def get_mens_tournament(
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """Get Men's NCAA Tournament data with championship odds, bracket, and live games."""
    return await _get_march_madness_data("mens", db, user)


@router.get("/womens")
async def get_womens_tournament(
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """Get Women's NCAA Tournament data with championship odds, bracket, and live games."""
    return await _get_march_madness_data("womens", db, user)
