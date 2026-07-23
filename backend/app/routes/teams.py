"""Team detail page API."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Team, Event, Sport, FuturesMarket, FuturesOutcome, TeamIdentityMapping
from app.services import get_db
from app.utils import season_windows

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{identifier}")
async def get_team(identifier: str, debug_timing: bool = False, db: AsyncSession = Depends(get_db)):
    """Get a team page with upcoming/recent games, futures, and championship path."""
    _t = {}
    _t0 = time.perf_counter()

    def _mark(label):
        nonlocal _t0
        _t[label] = round((time.perf_counter() - _t0) * 1000)
        _t0 = time.perf_counter()

    # Try integer ID first, then slug
    team_filter = Team.slug == identifier
    try:
        team_id = int(identifier)
        team_filter = or_(Team.id == team_id, Team.slug == identifier)
    except ValueError:
        pass

    result = await db.execute(
        select(Team).options(selectinload(Team.sport)).where(team_filter)
    )
    team = result.scalars().first()
    if not team:
        # #1204: legacy-slug redirect. A slug retired by a team-identity merge is
        # registered in team_identity_mapping (source='legacy_slug') pointing at the
        # canonical franchise, so a bookmarked old slug (e.g. /teams/boston) resolves
        # to the live row instead of 404-ing (redirect, not 404).
        legacy_id = (await db.execute(
            select(TeamIdentityMapping.team_id).where(
                TeamIdentityMapping.source == "legacy_slug",
                TeamIdentityMapping.source_id == identifier,
            ).limit(1)
        )).scalar_one_or_none()
        if legacy_id is not None:
            team = (await db.execute(
                select(Team).options(selectinload(Team.sport)).where(Team.id == legacy_id)
            )).scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    now = datetime.now(timezone.utc)

    # --- Events: upcoming + recent ---
    base_event_filter = or_(
        Event.home_team_id == team.id,
        Event.away_team_id == team.id,
        Event.home_team_name == team.name,
        Event.away_team_name == team.name,
    )

    upcoming_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            base_event_filter,
            Event.status.in_(["live", "scheduled"]),
            Event.commence_time >= now - timedelta(hours=2),
        )
        .order_by(
            case((Event.status == "live", 0), else_=1),
            Event.commence_time.asc(),
        )
        .limit(5)
    )

    recent_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            base_event_filter,
            # #1204: include 'closed'-settled, not just 'completed' — a settled
            # doubleheader game (and every source that closes rather than completes)
            # was orphaned from recent games (only 1 of 2 surfaced).
            Event.status.in_(["completed", "closed"]),
            Event.commence_time >= now - timedelta(days=30),
        )
        .order_by(Event.commence_time.desc())
        .limit(5)
    )

    _mark("resolve_team")
    upcoming_r, recent_r = await db.execute(upcoming_q), await db.execute(recent_q)
    upcoming_events = [_format_event_brief(e, team) for e in upcoming_r.scalars().all()]
    recent_events = [_format_event_brief(e, team) for e in recent_r.scalars().all()]
    _mark("events")

    # #1197 / #1239: the team page is Priority #3 and must NEVER hard-500 on a
    # failure in an optional enrichment section (a slow/failing futures query, a
    # season-descriptor edge case, a championship-path exception). Each optional
    # section degrades to its empty value and the core page (identity + games)
    # always renders. A cache/DB blip on a sub-section is not allowed to take the
    # whole page down.
    sport_key = team.sport.key if team.sport else None
    league_slug = _league_slug_for_sport_key(sport_key)

    # --- Team futures (championship, conference, division, awards) ---
    futures_items: list = []
    try:
        from app.routes.user import _query_team_futures
        futures_data = await _query_team_futures([team.id], db, limit=30)
        futures_items = futures_data.get("items", [])
    except Exception:
        logger.exception("team page: futures section failed for team %s", team.id)
    _mark("futures")

    # --- Season context (every team-page number declares its season) ---
    season_ctx = None
    try:
        season_ctx = (
            season_windows.season_descriptor(league_slug, now) if league_slug else None
        )
    except Exception:
        logger.exception("team page: season descriptor failed for team %s", team.id)
    _mark("season")

    # --- Championship path (tier 1/2/4 probabilities) ---
    champ_path: list = []
    try:
        champ_path = await _get_championship_path(
            team.id, db, league_slug=league_slug, now=now
        )
    except Exception:
        logger.exception("team page: championship path failed for team %s", team.id)
    _mark("championship")

    resp = {
        "team": _format_team(team),
        "season": season_ctx,
        "upcoming_events": upcoming_events,
        "recent_events": recent_events,
        "futures": futures_items,
        "championship_path": champ_path,
    }
    if debug_timing:
        resp["_timings_ms"] = _t
    return resp


# Map an Odds-API sport_key ("basketball_nba") to the season_windows league slug
# ("nba"). Only the four leagues season_windows models have a season string;
# everything else returns None (no year-based season filtering, graded-winner
# exclusion still applies).
_SPORT_KEY_TO_LEAGUE = {
    "basketball_nba": "nba",
    "baseball_mlb": "mlb",
    "americanfootball_nfl": "nfl",
    "icehockey_nhl": "nhl",
}


def _league_slug_for_sport_key(sport_key: str | None) -> str | None:
    return _SPORT_KEY_TO_LEAGUE.get((sport_key or "").strip().lower())


def _format_team(team: Team) -> dict:
    sport = team.sport
    return {
        "id": team.id,
        "slug": team.slug,
        "name": team.name,
        "abbreviation": team.abbreviation,
        "sport_key": sport.key if sport else None,
        "sport_name": sport.name if sport else None,
        "location": team.location,
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_small": team.logo_url_small,
        "logo_large": team.logo_url_large,
        "record": team.current_record,
        "standings": team.standings_data,
        "season_stats": team.season_stats,
        "roster": team.roster_players,
    }


def _format_event_brief(event: Event, team: Team) -> dict:
    """Compact event format for team page game lists."""
    sport = event.sport
    is_home = (event.home_team_id == team.id) or (event.home_team_name == team.name)
    opponent = event.away_team_name if is_home else event.home_team_name

    wp = None
    if event.win_probability_sources and isinstance(event.win_probability_sources, dict):
        agg = event.win_probability_sources.get("aggregate", {})
        wp = agg.get("home") if is_home else agg.get("away")

    return {
        "id": event.id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "status": event.status,
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        "sport_key": sport.key if sport else None,
        "is_home": is_home,
        "opponent": opponent,
        "win_probability": round(wp, 3) if wp is not None else None,
    }


_CHAMP_YEAR_RE = re.compile(r"\b(202[4-9]|2030)\b")
_CHAMP_SEASON_HYPHEN_RE = re.compile(r"\b(202[4-9])-(2[4-9]|30)\b")


def _is_future_season(market_name: str, max_year: int) -> bool:
    """Return True if the market name references a season beyond max_year.

    Markets without any year reference pass through (return False).
    """
    years: set[int] = set()
    for match in _CHAMP_SEASON_HYPHEN_RE.finditer(market_name or ""):
        base = int(match.group(1))
        suffix = int(match.group(2))
        years.add(base)
        years.add(base // 100 * 100 + suffix)
    for match in _CHAMP_YEAR_RE.finditer(market_name or ""):
        years.add(int(match.group(1)))
    if not years:
        return False
    return any(y > max_year for y in years)


def _extract_championship_season(market) -> str | None:
    """Season string for a futures market: prefer canonical_market_key
    ({sport}:{league}:{category}:{season}), fall back to a year in the name."""
    key = getattr(market, "canonical_market_key", None)
    if key:
        parts = key.split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
    name = market.name or ""
    m = _CHAMP_SEASON_HYPHEN_RE.search(name)
    if m:
        return m.group(0)
    m2 = _CHAMP_YEAR_RE.search(name)
    if m2:
        return m2.group(0)
    return None


def _season_base_year(season: str | None) -> int | None:
    """First 4-digit year in a season string ("2025-26" → 2025, "2026" → 2026)."""
    if not season:
        return None
    m = _CHAMP_YEAR_RE.search(season)
    return int(m.group(0)) if m else None


async def _get_championship_path(
    team_id: int,
    db: AsyncSession,
    league_slug: str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Get championship/conference/division probabilities for a team.

    The championship path is FORWARD-looking, so it must exclude:
      1. Settled markets — a graded winner exists even while Kalshi keeps the
         market ``status='open'`` (gotcha #33). A settled prior-season market
         with a graded outcome near 100% was leaking into next season's path as
         a bogus "99.5% Division" number (Queue #242 Item 1).
      2. Prior-season markets — the market's season is numerically before the
         league's current season.
      3. Future-season markets (e.g. "2027 Champion" when it is 2025-26).

    Averages probabilities when multiple sources provide markets at the same
    tier, and stamps each entry with the season it describes.
    """
    now = now or datetime.now(timezone.utc)

    # Markets with a graded winner are settled (gotcha #33: status stays 'open').
    graded = (
        select(FuturesOutcome.id)
        .where(
            FuturesOutcome.market_id == FuturesMarket.id,
            FuturesOutcome.is_winner.is_(True),
        )
    )

    result = await db.execute(
        select(FuturesOutcome, FuturesMarket)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesOutcome.team_id == team_id,
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            FuturesMarket.market_tier.in_([1, 2, 4]),
            ~graded.exists(),
        )
        .order_by(FuturesMarket.market_tier.asc())
    )

    # Current-season cutoff: the maximum year that counts as "this season".
    # For a 2025-26 season the cutoff is 2026; a market referencing 2027 is
    # future-season and should be excluded.
    max_year = now.year

    # Current-season base year for prior-season exclusion (e.g. a settled 2025-26
    # market must not show up once the 2026-27 season's markets are the truth).
    current_season = (
        season_windows.season_string(league_slug, now) if league_slug else None
    )
    current_base = _season_base_year(current_season)

    tier_labels = {1: "Championship", 2: "Conference", 4: "Division"}

    # Collect all valid outcomes per tier, then pick the best per tier.
    # dict: tier → list of (probability, outcome, market) tuples
    tier_candidates: dict[int, list[tuple[float, object, object]]] = {}

    for outcome, market in result.all():
        # Skip future-season markets (same fix as #471 for championship grid)
        if _is_future_season(market.name or "", max_year):
            continue

        # Skip prior-season markets: the market's own season predates the current
        # league season. Markets with no year in their name pass through.
        if current_base is not None:
            mkt_season = _extract_championship_season(market)
            mkt_base = _season_base_year(mkt_season)
            if mkt_base is not None and mkt_base < current_base:
                continue

        prob = float(outcome.current_probability) if outcome.current_probability else None
        if prob is None:
            continue

        tier = market.market_tier
        tier_candidates.setdefault(tier, []).append((prob, outcome, market))

    path = []
    for tier in sorted(tier_candidates.keys()):
        candidates = tier_candidates[tier]

        # Deduplicate by group_id: if multiple outcomes share the same
        # group_id, keep only the one with the highest probability (they
        # are from the same underlying market, just different sub-markets).
        seen_groups: set[str] = set()
        deduped: list[tuple[float, object, object]] = []
        for prob, outcome, market in candidates:
            gid = market.group_id
            if gid and gid in seen_groups:
                continue
            if gid:
                seen_groups.add(gid)
            deduped.append((prob, outcome, market))

        if not deduped:
            continue

        # Average probability across sources for robustness; use the
        # market with the highest probability for display metadata.
        avg_prob = sum(p for p, _, _ in deduped) / len(deduped)
        best_prob, best_outcome, best_market = max(deduped, key=lambda x: x[0])

        # Sanity check: if the averaged probability exceeds 1.0, log a warning
        if avg_prob > 1.0:
            logger.warning(
                "Championship path tier %d for team %d has probability %.3f > 1.0 "
                "(from %d candidates); clamping to 1.0",
                tier, team_id, avg_prob, len(deduped),
            )
            avg_prob = 1.0

        path.append({
            "tier": tier,
            "label": tier_labels.get(tier, "Other"),
            "market_name": best_market.name,
            "market_id": best_market.id,
            "probability": round(avg_prob, 4),
            "rank": best_outcome.rank,
            "movement": float(best_outcome.probability_change_24h) if best_outcome.probability_change_24h else None,
            # Season this number describes (Queue #242 Item 1) — prefer the
            # market's own season, fall back to the league's current season.
            "season": _extract_championship_season(best_market) or current_season,
        })

    return path
