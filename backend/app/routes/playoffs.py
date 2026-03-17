"""
Championship progression grid endpoint.

GET /api/playoffs/{league_slug} returns a grid of teams × playoff stages,
with multi-source probability merging, 24h movers, and trend chart data.
"""

import logging
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.league_configs import LeagueConfig, get_league_config, get_all_league_slugs
from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Team
from app.services import get_db
from app.utils.tournament_stages import classify_market_stage, get_stages_for_sport

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Market filters — reject non-playoff markets
# ---------------------------------------------------------------------------

# Markets that should never appear in a playoff grid (win totals, props, etc.)
_NON_PLAYOFF_MARKET_RE = re.compile(
    r"""
    \bover\s*\(           |   # Win totals: "Over (41.5)"
    \bunder\s*\(          |   # "Under (41.5)"
    \bover/under\b        |   # "Over/Under"
    \b\d+\+\s*wins\b      |   # "15+ wins", "20+ wins"
    \bwin\s+total\b       |   # "Win Total"
    \bseason\s+wins\b     |   # "Season Wins"
    \bbefore\s+\w+\s+\d   |   # "Before March 7th, 2026" (date markets)
    \bexact\s+wins\b      |   # "Exact Wins"
    \bpoints\b            |   # Player stat props
    \brebounds\b          |   # Player stat props
    \bassists\b           |   # Player stat props
    \bmvp\b               |   # MVP markets
    \brookie\b            |   # Rookie of the year
    \bdefensive\b         |   # DPOY
    \bmost\s+improved\b   |   # MIP
    \bscoring\s+leader\b  |   # Scoring leader
    \b6th\s+man\b         |   # 6th man
    \bcoach\b             |   # Coach of the year
    \bvs\.?\s              |   # Game-level "Team A vs Team B"
    \bat\b.*:             |   # "Team A at Team B: Points"
    \bdraft\b             |   # Draft markets
    \bdrafted\b           |   # "freshmen drafted"
    \bfreshmen\b          |   # Draft props
    \bupset\b             |   # "1+ upsets" props
    \bseed\s+margin\b     |   # "Biggest Upset Seed Margin"
    \bpick\b              |   # Draft pick markets
    \ball[- ]star\b       |   # All-Star markets
    \bhome[- ]?court\b    |   # Home court advantage
    \bregular\s+season\b  |   # Regular season awards
    \bseries\s+price\b    |   # Series pricing markets
    \bexact\s+score\b     |   # Exact score props
    \btotal\s+(?:goals|runs|points|games)\b |  # Totals
    \bper\s+game\s+leader\b |  # Stat leaders: "Blocks Per Game Leader"
    \bleader\b            |   # Stat leaders
    \bexpansion\b         |   # Expansion draft/team markets
    \bmost\s+valuable\b   |   # "Most Valuable Player"
    \bplayer\s+of\b       |   # "Player of the Year"
    \bgolden\s+glove\b    |   # Baseball awards
    \bcy\s+young\b        |   # Baseball awards
    \bheisman\b           |   # College football awards
    \b(?:steals|blocks|assists|rebounds|scoring)\s+(?:leader|per\s+game)\b |  # Stat categories
    \bwhich\s+teams\s+will\s+play\b |  # "Which teams will play in..." matchup markets
    \bwhich\s+cities\b    |   # Expansion city markets
    \bcover\s+of\b        |   # "Cover of NBA 2K27"
    \b2k\d+\b             |   # Video game markets (NBA 2K27, etc.)
    \b\d+\+\s+(?:golf|major|championship)\b |  # "1+ golf major championship wins"
    \b(?:and|&)\b(?=.*\b(?:cup|champion|final))  |
    \besports?\b          |   # Esports markets
    \b(?:LOL|LoL)\b       |   # League of Legends
    \bvalorant\b          |   # Valorant esports
    \bcounter[- ]?strike\b |  # CS2/CSGO
    \b(?:LCK|LPL|LEC|LCS|VCT|MSI)\b |  # Esports league codes
    \bhalftime\b          |   # Super Bowl Halftime Show
    \banthem\b            |   # National anthem markets
    \bcoin\s*toss\b       |   # Coin toss props
    \bgatorade\b          |   # Gatorade color markets
    \bdarts\b             |   # Premier League Darts (not football)
    \bsnooker\b           |   # Snooker (not football)
    \bcricket\b           |   # Cricket markets
    \brunning\b.*\bback\b |   # "Running back to win MVP" player props
    \bballon\s+d.or\b     |   # Ballon d'Or award
    \bgolden\s+boot\b     |   # Golden Boot award
    \bgolden\s+ball\b         # Golden Ball award
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Country names that should never appear as outcomes in club competitions
# (EPL, La Liga, Champions League, Bundesliga, MLS)
_COUNTRY_NAMES = {
    "Argentina", "Australia", "Austria", "Belgium", "Brazil", "Cameroon",
    "Canada", "Chile", "China", "Colombia", "Costa Rica", "Croatia",
    "Czech Republic", "Denmark", "Ecuador", "Egypt", "England", "Finland",
    "France", "Germany", "Ghana", "Greece", "Hungary", "Iceland", "India",
    "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica",
    "Japan", "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria",
    "North Korea", "Norway", "Panama", "Paraguay", "Peru", "Poland",
    "Portugal", "Qatar", "Romania", "Russia", "Saudi Arabia", "Scotland",
    "Senegal", "Serbia", "Slovakia", "Slovenia", "South Africa",
    "South Korea", "Spain", "Sweden", "Switzerland", "Tunisia", "Turkey",
    "Ukraine", "United States", "Uruguay", "Venezuela", "Wales",
    "USA", "US", "UK",
}


def _is_playoff_relevant_market(market_name: str) -> bool:
    """Check if a market name is relevant to playoff progression grids.

    Rejects win totals, player props, awards, game-level markets, and
    date-based threshold markets.
    """
    return not _NON_PLAYOFF_MARKET_RE.search(market_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_diacritics(s: str) -> str:
    """Remove diacritics for cross-source name dedup."""
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _normalize_team_name(name: str) -> str:
    """Normalize a team/outcome name for dedup across sources."""
    n = _strip_diacritics(name).lower().strip()
    # Strip common suffixes
    n = re.sub(r"\s*\(.*\)$", "", n)
    # Strip trailing periods (e.g. "Michigan St." → "Michigan St")
    n = n.rstrip(".")
    return n


def _match_market_to_column(
    market: FuturesMarket,
    config: LeagueConfig,
) -> str | None:
    """Determine which grid column a market belongs to.

    Uses matching_rules from the league config (name patterns + market_tier),
    then falls back to tournament_stages.py classify_market_stage.
    """
    name = market.name or ""
    name_lower = name.lower()

    # 0. Reject non-playoff markets (win totals, props, awards, etc.)
    if not _is_playoff_relevant_market(name):
        return None

    # 1. Try league config matching rules (most specific)
    for rule in config.matching_rules:
        # Tier match
        if rule.tier is not None and market.market_tier == rule.tier:
            # Verify the column key exists in config columns
            if any(c.key == rule.column for c in config.columns):
                # For tier matches, also check name patterns if available
                # to prevent false positives (e.g., tier 2 could be conference OR award)
                if rule.name_patterns:
                    for pat in rule.name_patterns:
                        if re.search(pat, name, re.IGNORECASE):
                            return rule.column
                else:
                    return rule.column

        # Name pattern match
        for pat in rule.name_patterns:
            if re.search(pat, name, re.IGNORECASE):
                return rule.column

    # 2. Fall back to tournament_stages.py classify_market_stage
    # NOTE: Do NOT pass market_tier to the fallback — our config matching rules
    # already handle tiers with name-pattern gating. The fallback's tier→stage
    # mapping has no name validation, which causes false positives like
    # "NBA 2K27 Cover" (tier=1) → championship.
    stages = get_stages_for_sport(config.sport_category, league=None)
    if stages:
        stage_key = classify_market_stage(
            market_name=name,
            external_id=market.external_id,
            market_tier=None,  # Intentionally None — see note above
            stages=stages,
        )
        if stage_key and any(c.key == stage_key for c in config.columns):
            return stage_key

    return None


def _merge_probabilities(probs: list[float]) -> float:
    """Merge probabilities from multiple sources using median."""
    if not probs:
        return 0.0
    return statistics.median(probs)


async def _compute_movers(
    session: AsyncSession,
    outcome_ids: list[int],
    hours: int = 24,
) -> dict[int, float]:
    """Compute probability change over the last N hours for a set of outcomes.

    Returns {outcome_id: change_24h}.
    """
    if not outcome_ids:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get earliest snapshot after cutoff for each outcome
    stmt = (
        select(
            FuturesOddsSnapshot.outcome_id,
            sqlfunc.min(FuturesOddsSnapshot.captured_at).label("earliest_time"),
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .group_by(FuturesOddsSnapshot.outcome_id)
    )
    result = await session.execute(stmt)
    earliest_times = {row.outcome_id: row.earliest_time for row in result}

    if not earliest_times:
        return {}

    # Get probabilities at those earliest times
    old_probs: dict[int, float] = {}
    for oid, t in earliest_times.items():
        snap_stmt = (
            select(FuturesOddsSnapshot.probability)
            .where(
                FuturesOddsSnapshot.outcome_id == oid,
                FuturesOddsSnapshot.captured_at == t,
            )
            .limit(1)
        )
        snap_result = await session.execute(snap_stmt)
        row = snap_result.first()
        if row and row.probability is not None:
            old_probs[oid] = float(row.probability)

    return old_probs


async def _build_trend_chart(
    session: AsyncSession,
    outcome_ids: list[int],
    outcome_names: dict[int, str],
    hours: int = 168,
    top_n: int = 10,
    bucket_seconds: int = 3600,
) -> dict:
    """Build trend chart data for top N outcomes.

    Returns probability timeline in the same format as the futures
    probability-timeline endpoint.
    """
    if not outcome_ids:
        return {"timeline": [], "outcomes": []}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    stmt = (
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.captured_at,
            FuturesOddsSnapshot.probability,
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
            FuturesOddsSnapshot.probability.isnot(None),
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"timeline": [], "outcomes": []}

    # Bucket by time
    buckets: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        ts = int(row.captured_at.timestamp())
        bucket_ts = (ts // bucket_seconds) * bucket_seconds
        if row.probability is not None:
            buckets[bucket_ts][row.outcome_id].append(float(row.probability))

    # Build timeline
    timeline = []
    for bucket_ts in sorted(buckets.keys()):
        entry = {
            "timestamp": datetime.fromtimestamp(bucket_ts, tz=timezone.utc).isoformat(),
            "outcomes": {},
        }
        for oid, probs in buckets[bucket_ts].items():
            name = outcome_names.get(oid, str(oid))
            entry["outcomes"][name] = statistics.median(probs)
        timeline.append(entry)

    return {
        "hours": hours,
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
    }


async def _get_team_metadata(
    session: AsyncSession,
    team_names: set[str],
) -> dict[str, dict]:
    """Look up team metadata (logo, colors, record, conference) by name.

    Returns {normalized_name: metadata_dict}.
    """
    if not team_names:
        return {}

    # Build ILIKE conditions for each name
    conditions = []
    for name in team_names:
        escaped = name.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Team.name.ilike(f"%{escaped}%"))

    stmt = select(Team).where(*[] if not conditions else [conditions[0]])
    if len(conditions) > 1:
        from sqlalchemy import or_
        stmt = select(Team).where(or_(*conditions))
    elif conditions:
        stmt = select(Team).where(conditions[0])

    result = await session.execute(stmt)
    teams = result.scalars().all()

    # Build lookup by normalized name
    team_lookup: dict[str, dict] = {}
    for team in teams:
        meta = {
            "team_id": team.id,
            "name": team.name,
            "short_name": team.abbreviation or team.name.split()[-1] if team.name else None,
            "abbreviation": getattr(team, "abbreviation", None),
            "logo_url": team.logo_url_small or team.logo_url_large,
            "primary_color": team.primary_color,
            "secondary_color": team.secondary_color,
            "record": team.current_record,
            "conference": None,
            "division": None,
            "seed": None,
        }

        # Extract standings info if available
        standings = team.standings_data or {}
        if isinstance(standings, dict):
            meta["conference"] = standings.get("conference")
            meta["division"] = standings.get("division")
            meta["seed"] = standings.get("position") or standings.get("seed")

        norm = _normalize_team_name(team.name)
        team_lookup[norm] = meta

        # Also index by abbreviation if available
        if team.abbreviation:
            team_lookup[_normalize_team_name(team.abbreviation)] = meta

        # And alternate names
        alt_names = team.alternate_names or []
        for alt in alt_names:
            team_lookup[_normalize_team_name(alt)] = meta

    return team_lookup


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{league_slug}")
async def get_playoff_grid(
    league_slug: str,
    hours: int = Query(default=None, description="Trend chart window in hours"),
    top: int = Query(default=10, ge=1, le=50, description="Top N teams for trend chart"),
    db: AsyncSession = Depends(get_db),
):
    """Return championship progression grid for a league.

    Each team row shows probabilities of reaching each playoff stage,
    sourced from Odds API, Kalshi, and Polymarket.
    """
    config = get_league_config(league_slug)
    if not config:
        available = get_all_league_slugs()
        raise HTTPException(
            status_code=404,
            detail=f"League '{league_slug}' not found. Available: {available}",
        )

    trend_hours = hours or config.trend_hours

    # -----------------------------------------------------------------------
    # 1. Query futures markets that match this league
    # -----------------------------------------------------------------------

    from sqlalchemy import or_

    # Path A: Match by external_id sport key prefix (Odds API markets)
    sport_conditions = []
    for sk in config.sport_keys:
        sport_conditions.append(FuturesMarket.external_id.ilike(f"{sk}%"))

    # Path B: Match by llm_sport_category (Kalshi/Polymarket markets)
    # These sources use non-sport-key external IDs (tickers, numeric IDs).
    # We filter by category, then use league_name_patterns in Python to
    # separate leagues that share a category (NBA vs NCAAB both = "basketball").
    category_condition = FuturesMarket.llm_sport_category == config.sport_category

    market_filter = or_(*sport_conditions, category_condition)

    stmt = (
        select(FuturesMarket)
        .where(
            market_filter,
            FuturesMarket.status != "resolved",
        )
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    all_markets = result.scalars().unique().all()

    # Filter by league name patterns (Python-side) to separate e.g. NBA from NCAAB
    league_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.league_name_patterns
    ] if config.league_name_patterns else []

    markets = []
    for market in all_markets:
        eid = market.external_id or ""
        # Path A markets (sport key prefix) always pass
        if any(eid.lower().startswith(sk.lower()) for sk in config.sport_keys):
            markets.append(market)
            continue
        # Path B markets must match a league name pattern
        if league_patterns:
            name = market.name or ""
            if any(pat.search(name) for pat in league_patterns):
                markets.append(market)
        # If no league_name_patterns configured, all category matches pass
        elif not league_patterns:
            markets.append(market)

    logger.info(
        "Playoff grid %s: found %d markets for sport_keys=%s, category=%s",
        league_slug,
        len(markets),
        config.sport_keys,
        config.sport_category,
    )

    # -----------------------------------------------------------------------
    # 2. Match each market to a grid column
    # -----------------------------------------------------------------------

    # column_key -> list of (market, outcome) tuples
    column_data: dict[str, list[tuple]] = defaultdict(list)

    for market in markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue

        for outcome in market.outcomes:
            if outcome.current_probability is None:
                continue
            prob = float(outcome.current_probability)
            if prob <= 0:
                continue
            # Skip non-team outcome names (thresholds, dates, generic)
            oname = outcome.name or ""
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            # Skip generic yes/no, over/under outcomes
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            # Skip matchup pair outcomes like "Tampa Bay and Colorado"
            if re.search(r"\band\b", oname, re.IGNORECASE) and \
               not re.search(r"\bTrail\s+Blazers\b", oname, re.IGNORECASE):
                # Allow "Trail Blazers" which is a real team (Portland Trail Blazers)
                # but block "Tampa Bay and Colorado" matchup pairs
                if re.match(r"^[\w\s.]+ and [\w\s.]+$", oname.strip()):
                    continue
            # Skip generic/seeded outcomes like "#1 seed", "1+ wins"
            if re.match(r"^#?\d+", oname.strip()):
                continue
            # Skip country/national team names in club competitions
            # (catches World Cup outcomes leaking into Champions League, EPL, etc.)
            if config.sport_category == "soccer" and oname.strip() in _COUNTRY_NAMES:
                continue
            # Filter prediction market 0.5 noise — binary markets near 50%
            # are illiquid defaults, not real predictions.  Applies to both
            # Kalshi and Polymarket.
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                continue

            column_data[col_key].append((market, outcome))

    # Log column coverage
    for col in config.columns:
        count = len(column_data.get(col.key, []))
        logger.info("  Column %s (%s): %d outcome entries", col.key, col.label, count)

    # -----------------------------------------------------------------------
    # 3. Aggregate by team × column with cross-source merging
    # -----------------------------------------------------------------------

    # team_norm_name -> {col_key -> {source -> {probability, bookmaker, market_id, outcome_id, last_updated}}}
    grid_raw: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    # Track outcome IDs for trend/mover queries
    all_outcome_ids: list[int] = []
    outcome_id_to_team: dict[int, str] = {}
    outcome_id_to_name: dict[int, str] = {}

    for col_key, entries in column_data.items():
        for market, outcome in entries:
            team_name = outcome.name
            norm = _normalize_team_name(team_name)

            source_entry = {
                "source": market.source,
                "probability": float(outcome.current_probability),
                "market_id": market.id,
                "outcome_id": outcome.id,
            }

            grid_raw[norm][col_key].append(source_entry)
            all_outcome_ids.append(outcome.id)
            outcome_id_to_team[outcome.id] = norm
            # Store display name (first occurrence wins)
            if norm not in outcome_id_to_name:
                outcome_id_to_name[outcome.id] = team_name

    # Deduplicate within same source per team+column: when a source has
    # multiple entries (e.g., both "NCAAB Championship" and "Make Championship
    # Game" matched to the championship column), keep the LOWEST probability.
    # The genuine championship market always has lower probability than
    # round-advancement markets.
    for norm_name in grid_raw:
        for col_key in grid_raw[norm_name]:
            entries = grid_raw[norm_name][col_key]
            if len(entries) <= 1:
                continue
            # Group by source
            by_source: dict[str, list[dict]] = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            # Keep lowest prob per source
            deduped = []
            for source, source_entries in by_source.items():
                best = min(source_entries, key=lambda e: e["probability"])
                deduped.append(best)
            grid_raw[norm_name][col_key] = deduped

    # -----------------------------------------------------------------------
    # 3b. Merge duplicate teams (short name → full name dedup)
    # -----------------------------------------------------------------------
    # Kalshi uses "Oklahoma City", Odds API uses "Oklahoma City Thunder".
    # Merge entries where one normalized name is a prefix of another.

    norm_names = sorted(grid_raw.keys(), key=len, reverse=True)  # longest first
    merge_map: dict[str, str] = {}  # short_name → long_name

    for i, long_name in enumerate(norm_names):
        for short_name in norm_names[i + 1:]:
            if short_name in merge_map:
                continue
            # Check if short_name is a prefix of long_name
            if long_name.startswith(short_name + " ") or long_name.startswith(short_name + "-"):
                merge_map[short_name] = long_name
            # Check single-letter abbreviation suffix
            # e.g., "los angeles l" → "los angeles lakers"
            elif (
                len(short_name) >= 3
                and short_name[-2] == " "
                and short_name[-1].isalpha()
                and long_name.startswith(short_name[:-1])
                and len(long_name) > len(short_name)
                and long_name[len(short_name) - 1] == short_name[-1]
            ):
                merge_map[short_name] = long_name
            # Check if short_name words are a subset of long_name words
            # (e.g., "michigan state" vs "michigan st spartans")
            elif len(short_name.split()) >= 2:
                short_words = set(short_name.split())
                long_words = set(long_name.split())
                # Normalize common abbreviations for comparison
                def _expand_abbrevs(words):
                    expanded = set()
                    for w in words:
                        expanded.add(w)
                        if w == "st":
                            expanded.add("state")
                        elif w == "state":
                            expanded.add("st")
                    return expanded
                short_expanded = _expand_abbrevs(short_words)
                if short_expanded.issubset(_expand_abbrevs(long_words)):
                    merge_map[short_name] = long_name

    # Apply merges
    for short_name, long_name in merge_map.items():
        if short_name in grid_raw and long_name in grid_raw:
            for col_key, entries in grid_raw[short_name].items():
                grid_raw[long_name][col_key].extend(entries)
            del grid_raw[short_name]
            logger.debug("Merged team '%s' into '%s'", short_name, long_name)

    # -----------------------------------------------------------------------
    # 4. Build team rows with merged probabilities
    # -----------------------------------------------------------------------

    # Get team metadata
    team_names_raw = set()
    for norm_name in grid_raw:
        # Find any display name for lookup
        for col_entries in grid_raw[norm_name].values():
            for entry in col_entries:
                oid = entry["outcome_id"]
                if oid in outcome_id_to_name:
                    team_names_raw.add(outcome_id_to_name[oid])
                    break
            break

    team_meta = await _get_team_metadata(db, team_names_raw)

    # Second merge pass: use team metadata to identify teams that share
    # the same team_id but have different normalized names
    # (e.g., "Connecticut" vs "UConn Huskies")
    team_id_to_norm: dict[int, str] = {}
    meta_merge_map: dict[str, str] = {}
    for norm_name in list(grid_raw.keys()):
        meta = team_meta.get(norm_name, {})
        tid = meta.get("team_id")
        if tid is None:
            continue
        if tid in team_id_to_norm:
            # Same team_id, different norm name — merge shorter into longer
            existing = team_id_to_norm[tid]
            if len(norm_name) > len(existing):
                meta_merge_map[existing] = norm_name
                team_id_to_norm[tid] = norm_name
            else:
                meta_merge_map[norm_name] = existing
        else:
            team_id_to_norm[tid] = norm_name

    for short_name, long_name in meta_merge_map.items():
        if short_name in grid_raw and long_name in grid_raw:
            for col_key, entries in grid_raw[short_name].items():
                grid_raw[long_name][col_key].extend(entries)
            del grid_raw[short_name]
            logger.debug("Merged team '%s' into '%s' (same team_id)", short_name, long_name)

    # Compute 24h changes
    old_probs = await _compute_movers(db, all_outcome_ids, hours=24)

    teams = []
    championship_col = config.columns[-1].key  # Last column is typically championship

    for norm_name, col_map in grid_raw.items():
        # Find display name
        display_name = norm_name
        for col_entries in col_map.values():
            for entry in col_entries:
                oid = entry["outcome_id"]
                if oid in outcome_id_to_name:
                    display_name = outcome_id_to_name[oid]
                    break
            break

        # Look up team metadata
        meta = team_meta.get(norm_name, {})

        cells = {}
        for col in config.columns:
            entries = col_map.get(col.key, [])
            if not entries:
                continue

            probs = [e["probability"] for e in entries]
            merged = _merge_probabilities(probs)

            sources = []
            for e in entries:
                src = {
                    "source": e["source"],
                    "probability": round(e["probability"], 4),
                }
                sources.append(src)

            # Compute 24h trend from the championship outcome
            trend_24h = None
            if entries:
                # Use the first outcome's old probability
                oid = entries[0]["outcome_id"]
                old_p = old_probs.get(oid)
                if old_p is not None:
                    trend_24h = round(merged - old_p, 4)

            cells[col.key] = {
                "merged_probability": round(merged, 4),
                "sources": sources,
                "trend_24h": trend_24h,
            }

        if not cells:
            continue

        team_row = {
            "name": display_name,
            "short_name": meta.get("short_name") or display_name,
            "team_id": meta.get("team_id"),
            "logo_url": meta.get("logo_url"),
            "primary_color": meta.get("primary_color"),
            "secondary_color": meta.get("secondary_color"),
            "record": meta.get("record"),
            "conference": meta.get("conference"),
            "division": meta.get("division"),
            "seed": meta.get("seed"),
            "cells": cells,
        }
        teams.append(team_row)

    # -----------------------------------------------------------------------
    # 5. Sort teams
    # -----------------------------------------------------------------------

    def _sort_key(team_row):
        champ_prob = (
            team_row["cells"]
            .get(championship_col, {})
            .get("merged_probability", 0)
        )
        return -champ_prob  # descending

    teams.sort(key=_sort_key)

    # Cap at max_teams
    teams = teams[: config.max_teams]

    # -----------------------------------------------------------------------
    # 6. Compute biggest movers (top 5 up, top 5 down)
    # -----------------------------------------------------------------------

    movers = []
    for team_row in teams:
        champ_cell = team_row["cells"].get(championship_col)
        if champ_cell and champ_cell.get("trend_24h") is not None:
            movers.append({
                "name": team_row["name"],
                "short_name": team_row["short_name"],
                "team_id": team_row["team_id"],
                "column": championship_col,
                "change_24h": champ_cell["trend_24h"],
                "direction": "up" if champ_cell["trend_24h"] > 0 else "down",
                "logo_url": team_row.get("logo_url"),
                "primary_color": team_row.get("primary_color"),
            })

    movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
    movers = movers[:10]

    # -----------------------------------------------------------------------
    # 7. Build trend chart for top N teams
    # -----------------------------------------------------------------------

    # Collect championship outcome IDs for top N teams
    top_team_norms = [_normalize_team_name(t["name"]) for t in teams[:top]]
    trend_outcome_ids = []
    trend_outcome_names: dict[int, str] = {}

    for norm_name in top_team_norms:
        entries = grid_raw.get(norm_name, {}).get(championship_col, [])
        for e in entries:
            oid = e["outcome_id"]
            trend_outcome_ids.append(oid)
            trend_outcome_names[oid] = outcome_id_to_name.get(oid, norm_name)
            break  # one outcome per team for the chart

    trend_chart = await _build_trend_chart(
        db,
        trend_outcome_ids,
        trend_outcome_names,
        hours=trend_hours,
        top_n=top,
    )
    trend_chart["column"] = championship_col
    trend_chart["top"] = top

    # -----------------------------------------------------------------------
    # 8. Determine available sources
    # -----------------------------------------------------------------------

    sources_seen = set()
    for col_entries in column_data.values():
        for market, _ in col_entries:
            sources_seen.add(market.source)

    # -----------------------------------------------------------------------
    # 9. Build response
    # -----------------------------------------------------------------------

    # Only include columns that have data
    active_columns = []
    for col in config.columns:
        if col.key in column_data:
            active_columns.append({
                "key": col.key,
                "label": col.label,
                "order": col.order,
                "sequential": col.sequential,
            })

    # Group teams by conference if configured
    grouped_teams = None
    if config.conference_split:
        groups: dict[str, list] = defaultdict(list)
        ungrouped = []
        for team_row in teams:
            conf = team_row.get("conference")
            if conf:
                groups[conf].append(team_row)
            else:
                ungrouped.append(team_row)
        if groups:
            grouped_teams = {
                conf: rows for conf, rows in sorted(groups.items())
            }
            if ungrouped:
                grouped_teams["Other"] = ungrouped
    elif config.region_split:
        groups: dict[str, list] = defaultdict(list)
        ungrouped = []
        for team_row in teams:
            region = team_row.get("region")
            if region:
                groups[region].append(team_row)
            else:
                ungrouped.append(team_row)
        if groups:
            grouped_teams = {
                region: rows for region, rows in sorted(groups.items())
            }
            if ungrouped:
                grouped_teams["Other"] = ungrouped

    return {
        "league": config.slug,
        "name": config.name,
        "season": config.season_pattern,
        "columns": active_columns,
        "trend_chart": trend_chart,
        "teams": teams,
        "grouped_teams": grouped_teams,
        "movers": movers,
        "team_count": len(teams),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "sources_available": sorted(sources_seen),
    }


@router.get("/")
async def list_leagues():
    """List all available playoff grid leagues."""
    leagues = []
    for slug in get_all_league_slugs():
        config = get_league_config(slug)
        if config:
            leagues.append({
                "slug": config.slug,
                "name": config.name,
                "sport_category": config.sport_category,
                "column_count": len(config.columns),
            })
    return {"leagues": leagues}
