"""
Celery task for syncing NCAA Tournament bracket data from ESPN.

Fetches seeds, regions, and bracket placement from ESPN scoreboard
after Selection Sunday. Matches ESPN games to our Event records.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, and_

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

# ESPN API base
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports"

# Tournament type → ESPN path mapping
_ESPN_PATHS = {
    "mens": "basketball/mens-college-basketball",
    "womens": "basketball/womens-college-basketball",
}

# Sport keys for DB queries
_SPORT_KEYS = {
    "mens": "basketball_ncaab",
    "womens": "basketball_wncaab",
}

# Date range for 2026 tournament
_TOURNAMENT_START = datetime(2026, 3, 15, tzinfo=timezone.utc)
_TOURNAMENT_END = datetime(2026, 4, 8, tzinfo=timezone.utc)

# Round detection patterns (applied to ESPN event name or notes)
_ROUND_PATTERNS = [
    (re.compile(r"championship|title\s*game|national\s*championship", re.I), "Championship"),
    (re.compile(r"final\s*four|semifinals|national\s*semi", re.I), "Final Four"),
    (re.compile(r"elite\s*eight|regional\s*final", re.I), "Elite Eight"),
    (re.compile(r"sweet\s*(sixteen|16)|regional\s*semi", re.I), "Sweet 16"),
    (re.compile(r"(second|2nd)\s*round|round\s*of\s*32", re.I), "Round of 32"),
    (re.compile(r"(first|1st)\s*round|round\s*of\s*64", re.I), "Round of 64"),
    (re.compile(r"first\s*four|play.in", re.I), "First Four"),
]

# Region detection patterns
_REGION_PATTERNS = re.compile(r"\b(East|West|South|Midwest)\b(?:\s*Region)?", re.I)


def _detect_round(event_name: str, notes: list[str]) -> str | None:
    """Detect tournament round from ESPN event name and notes."""
    all_text = " ".join([event_name] + notes)
    for pattern, round_name in _ROUND_PATTERNS:
        if pattern.search(all_text):
            return round_name
    return None


def _detect_region(notes: list[str]) -> str | None:
    """Detect tournament region from ESPN notes/headlines."""
    all_text = " ".join(notes)
    match = _REGION_PATTERNS.search(all_text)
    if match:
        region = match.group(1).capitalize()
        return region
    return None


def _parse_seed(competitor: dict) -> int | None:
    """Extract seed from ESPN competitor data (multiple formats)."""
    # Direct seed field
    seed = competitor.get("seed")
    if seed is not None:
        try:
            return int(seed)
        except (ValueError, TypeError):
            pass

    # curatedRank format
    curated = competitor.get("curatedRank", {})
    if curated:
        current = curated.get("current")
        if current is not None:
            try:
                return int(current)
            except (ValueError, TypeError):
                pass

    # Sometimes in the team record or rank
    rank = competitor.get("rank")
    if rank is not None:
        try:
            val = int(rank)
            if 1 <= val <= 16:
                return val
        except (ValueError, TypeError):
            pass

    return None


def _normalize_name(name: str) -> str:
    """Normalize team name for matching."""
    import unicodedata
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return name.lower().strip()


def _names_overlap(espn_name: str, db_name: str) -> bool:
    """Check if ESPN team name matches our DB team name."""
    a = set(_normalize_name(espn_name).split())
    b = set(_normalize_name(db_name).split())
    # Remove common stopwords
    stopwords = {"the", "of", "fc", "sc", "cf", "at", "st", "st."}
    a -= stopwords
    b -= stopwords
    if not a or not b:
        return False
    overlap = a & b
    score = min(len(overlap) / len(a), len(overlap) / len(b))
    return score > 0.5


async def _sync_march_madness_bracket() -> dict:
    """
    Sync NCAA tournament bracket data from ESPN.

    For each tournament type (mens/womens):
    1. Fetch ESPN scoreboard for tournament date range
    2. Parse seeds, regions, rounds from ESPN data
    3. Match to our Event records
    4. Update tournament fields
    5. Cache bracket in Redis
    """
    from app.models.models import Event

    stats = {
        "mens": {"fetched": 0, "matched": 0, "updated": 0},
        "womens": {"fetched": 0, "matched": 0, "updated": 0},
    }

    async with get_task_session() as session:
        for tournament_type, espn_path in _ESPN_PATHS.items():
            sport_key = _SPORT_KEYS[tournament_type]
            type_stats = stats[tournament_type]

            # Fetch ESPN scoreboard for each day of the tournament
            espn_games = []
            async with httpx.AsyncClient(timeout=15.0) as client:
                current_date = _TOURNAMENT_START
                while current_date <= _TOURNAMENT_END:
                    date_str = current_date.strftime("%Y%m%d")
                    url = f"{ESPN_API}/{espn_path}/scoreboard?dates={date_str}"

                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            data = resp.json()
                            for event_data in data.get("events", []):
                                espn_games.append(event_data)
                    except Exception as e:
                        logger.warning(
                            f"ESPN fetch error for {tournament_type} {date_str}: {e}"
                        )

                    current_date += timedelta(days=1)

            type_stats["fetched"] = len(espn_games)
            logger.info(f"Fetched {len(espn_games)} ESPN {tournament_type} games")

            if not espn_games:
                continue

            # Load our events for the tournament period
            result = await session.execute(
                select(Event).where(
                    and_(
                        Event.sport_key.like(f"%ncaa%")
                        | Event.sport_key.like(f"%{sport_key}%"),
                        Event.commence_time
                        >= _TOURNAMENT_START - timedelta(days=1),
                        Event.commence_time <= _TOURNAMENT_END + timedelta(days=1),
                    )
                )
            )
            our_events = result.scalars().all()
            logger.info(
                f"Found {len(our_events)} DB events for {tournament_type} matching"
            )

            # Build bracket data for Redis cache
            bracket_games = []

            for espn_game in espn_games:
                competition = espn_game.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])

                if len(competitors) < 2:
                    continue

                # Parse ESPN data
                event_name = espn_game.get("name", "")
                notes = []
                for note in competition.get("notes", []):
                    headline = note.get("headline", "")
                    if headline:
                        notes.append(headline)
                # Also check event-level notes
                for note in espn_game.get("notes", []):
                    headline = note.get("headline", "")
                    if headline:
                        notes.append(headline)

                round_name = _detect_round(event_name, notes)
                region = _detect_region(notes)

                # Parse teams + seeds
                home_comp = None
                away_comp = None
                for comp in competitors:
                    if comp.get("homeAway") == "home":
                        home_comp = comp
                    else:
                        away_comp = comp

                if not home_comp or not away_comp:
                    continue

                home_name = home_comp.get("team", {}).get("displayName", "")
                away_name = away_comp.get("team", {}).get("displayName", "")
                home_seed = _parse_seed(home_comp)
                away_seed = _parse_seed(away_comp)

                # Only process if we have at least one seed (tournament game indicator)
                if home_seed is None and away_seed is None:
                    # Check if it looks like a tournament game from round detection
                    if round_name is None:
                        continue

                # Parse game time
                game_date_str = espn_game.get("date", "")
                try:
                    game_time = datetime.fromisoformat(
                        game_date_str.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    continue

                type_stats["matched"] += 1

                # Find matching Event in our DB
                best_match = None
                best_score = 0

                for event in our_events:
                    # Check time proximity (±3 hours)
                    if event.commence_time:
                        time_diff = abs(
                            (event.commence_time - game_time).total_seconds()
                        )
                        if time_diff > 10800:  # 3 hours
                            continue
                    else:
                        continue

                    # Check team name match
                    home_match = _names_overlap(
                        home_name, event.home_team_name or ""
                    ) or _names_overlap(away_name, event.home_team_name or "")
                    away_match = _names_overlap(
                        away_name, event.away_team_name or ""
                    ) or _names_overlap(home_name, event.away_team_name or "")

                    if home_match and away_match:
                        # Both teams match — great
                        score = 2 - (time_diff / 10800)  # Prefer closer time
                        if score > best_score:
                            best_score = score
                            best_match = event
                    elif home_match or away_match:
                        # One team matches
                        score = 1 - (time_diff / 10800)
                        if score > best_score:
                            best_score = score
                            best_match = event

                # Update the matching event
                if best_match:
                    updated = False

                    if home_seed is not None and best_match.tournament_seed_home != home_seed:
                        # Figure out which ESPN team maps to home vs away in our DB
                        if _names_overlap(home_name, best_match.home_team_name or ""):
                            best_match.tournament_seed_home = home_seed
                            best_match.tournament_seed_away = away_seed
                        else:
                            # Teams are swapped
                            best_match.tournament_seed_home = away_seed
                            best_match.tournament_seed_away = home_seed
                        updated = True

                    if region and best_match.tournament_region != region:
                        best_match.tournament_region = region
                        updated = True

                    if round_name and best_match.tournament_round != round_name:
                        best_match.tournament_round = round_name
                        updated = True

                    if not best_match.tournament_type:
                        best_match.tournament_type = tournament_type
                        updated = True

                    if not best_match.is_tournament_game:
                        best_match.is_tournament_game = True
                        updated = True

                    if updated:
                        type_stats["updated"] += 1

                # Build bracket cache entry
                espn_status = (
                    espn_game.get("status", {})
                    .get("type", {})
                    .get("name", "")
                )
                home_score = home_comp.get("score")
                away_score = away_comp.get("score")

                bracket_games.append(
                    {
                        "espn_id": espn_game.get("id"),
                        "event_id": best_match.id if best_match else None,
                        "round": round_name,
                        "region": region,
                        "home_team": home_name,
                        "away_team": away_name,
                        "seed_home": home_seed,
                        "seed_away": away_seed,
                        "score_home": int(home_score) if home_score else None,
                        "score_away": int(away_score) if away_score else None,
                        "status": espn_status.lower().replace("status_", ""),
                        "commence_time": game_time.isoformat(),
                    }
                )

            # Cache bracket in Redis
            try:
                from app.tasks.redis_state import get_redis_client

                r = get_redis_client()
                cache_key = f"bainluck:mm:{tournament_type}:bracket"
                r.setex(
                    cache_key, 10800, json.dumps(bracket_games)
                )  # 3h TTL
                logger.info(
                    f"Cached {len(bracket_games)} {tournament_type} bracket games in Redis"
                )
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

            await session.commit()

    logger.info(f"March Madness bracket sync complete: {stats}")
    return stats
