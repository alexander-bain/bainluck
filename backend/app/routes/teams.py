"""Team detail page API."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from app.utils.event_rails import (
    live_first_order,
    recent_or_unreported_condition,
    upcoming_rail_condition,
)
from app.utils.aggregation import compute_aggregate_probability
from app.utils.lifecycle import served_event_status
from app.utils.season_variant_team import (
    choose_parent_league_row,
    wants_parent_league_row,
)
from app.utils.standings_shape import public_standings

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Team, Event, Sport, FuturesMarket, FuturesOutcome, TeamIdentityMapping
from app.services import get_db
from app.utils import season_windows
from app.utils.proven_duplicates import (
    FoldedBlendView,
    folded_probability_sources_batch,
    not_a_proven_duplicate,
)

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

    # #2498: A CLUB'S PAGE IS ITS LEAGUE'S ROW, NOT ITS SPRING ROW.
    #
    # `boston-red-sox` was the `baseball_mlb_preseason` row (853) — 13-15,
    # `standings_data` NULL, breadcrumb "MLB PRESEASON" — while the club playing
    # a pennant race sat one slug away at `boston-red-sox-mlb` (10709, 80-67,
    # division East). All 30 MLB preseason clubs held the clean slug that way.
    #
    # The swap is ID-ANCHORED and only that: the candidate query is keyed on a
    # shared `espn_id`, so this never matches on a name or a kickoff time and
    # ruling 048 is not in play. It writes nothing and merges nothing — both
    # rows survive; one of them stops being what a URL resolves to.
    #
    # NFL and NBA are untouched by construction: their variant rows carry no
    # `espn_id` at all, so the query below returns nothing for them.
    if wants_parent_league_row(getattr(team.sport, "key", None)) and getattr(team, "espn_id", None):
        siblings = (await db.execute(
            select(Team.id, Sport.key)
            .join(Sport, Sport.id == Team.sport_id)
            .where(Team.espn_id == team.espn_id, Team.id != team.id)
        )).all()
        parent_id = choose_parent_league_row(team.sport.key, siblings)
        if parent_id is not None:
            parent = (await db.execute(
                select(Team).options(selectinload(Team.sport)).where(Team.id == parent_id)
            )).scalars().first()
            # Only on a row we actually loaded. A `None` here would 404 a page
            # that was serving a moment ago — a worse page beats no page.
            if parent is not None:
                team = parent

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
            # The status × time half is `utils.event_rails` (#3211) — it was
            # these same two lines on the league page, and the pair of rails is
            # only correct as a pair. See that module for why `live` no longer
            # carries a `now - 2h` floor.
            upcoming_rail_condition(now),
            # #2263: one game, one card. A row the registry proved is a second
            # copy of another row is not a second fixture on this team's schedule.
            not_a_proven_duplicate(),
        )
        .order_by(
            # Q438: the same live-AND-started predicate the league rail uses —
            # the pair is only correct as a pair.
            live_first_order(now),
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
            #
            # 🔴 AND `suspended` — live/056, the same omission #1204 describes
            # one state later. `upcoming_q` above is live/scheduled gated on
            # `now - 2h`; a match is suspended precisely because hours have
            # passed. Between the two, a rain-delayed match was on NEITHER of
            # its two teams' pages. `RecentGameCard` was taught the state in the
            # same change — without that it would have graded the PARTIAL score
            # as a result ("L 1–2"), which is the false Final live/048 removed,
            # printed by a different component.
            #
            # 🔴 AND a `scheduled` row past its own kickoff — #3211, the third
            # state through the same hole and the one that cost 171 US Open
            # matches on the league pages. `RecentGameCard` needs no further
            # teaching: such a row has no score at all, so the state it renders
            # is the score-less arm of the one live/056 already gave it.
            #
            # The 30-day lookback is PASSED, not assumed — a team plays less
            # often than its league does, and that difference is this page's
            # decision rather than the shared module's.
            #
            # 🔴 ONE LIST HERE, THREE RAILS ON THE LEAGUE PAGE, and the asymmetry
            # is reasoned rather than inherited: that page's cap spans every
            # concurrent match in a league (hundreds, during a Grand Slam), so
            # result-less rows starved the Finals out of all eight slots. This
            # cap spans ONE team's own schedule, where a result-less game is one
            # fixture among the handful the rail was sized for. Comparable
            # populations, no starvation. `unreported_rail_condition` carries the
            # measurement and this call site is named in it.
            recent_or_unreported_condition(now, lookback=timedelta(days=30)),
            not_a_proven_duplicate(),  # #2263, as above
        )
        .order_by(Event.commence_time.desc())
        .limit(5)
    )

    _mark("resolve_team")
    upcoming_r, recent_r = await db.execute(upcoming_q), await db.execute(recent_q)
    upcoming_events, recent_events = await _folded_briefs(
        db, team, upcoming_r.scalars().all(), recent_r.scalars().all()
    )
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
    _ftime: dict = {}
    try:
        from app.routes.user import _query_team_futures
        futures_data = await _query_team_futures(
            [team.id], db, limit=30, timings=_ftime if debug_timing else None
        )
        futures_items = futures_data.get("items", [])
    except Exception:
        logger.exception("team page: futures section failed for team %s", team.id)
    _mark("futures")
    if debug_timing:
        _t["futures_detail"] = _ftime

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
        # `public_standings` drops write-dead keys (#4811): a pre-#4732
        # `conf_rank` is a division place wearing a conference label, and this
        # is the payload the team-page hero reads.
        "standings": public_standings(team.standings_data),
        "season_stats": team.season_stats,
        "roster": team.roster_players,
    }


async def _folded_briefs(db, team: Team, *rails) -> list[list[dict]]:
    """Each rail's rows as briefs, with ONE twin fold across ALL of them (#5382).

    🔴 THE HALF THE FIRST PRESENTATION MISSED. Reading the canonical blend
    instead of the never-existing ``aggregate`` key fixes every row that OWNS
    readings. It cannot fix a row that owns none — and the team rails are
    exactly where that row is common, because both queries above carry the
    proven-duplicate filter (#2263): the survivor is printed and its suppressed
    twin is not, so when the venue price landed on the twin the card had
    nothing to blend. The event page has folded that twin since #3810 and reads
    a number off it. Same fixture, two answers, one blank — which is the
    divergence the fold exists to close, arriving on a second surface.

    (That filter is named here without its parentheses on purpose:
    ``test_the_team_page_rails`` counts the literal call text in this file, so a
    mention in prose reads to it as a third rail and reddens CI on a comment.)

    ONE lookup for BOTH rails, not one per rail and certainly not one per row.
    The rails are capped at 5 each, so the N+1 here would be small — but the
    reason to batch is not this page's size, it is that
    ``folded_probability_sources_batch`` is the shared, measured form (#3937)
    and a second hand-rolled fold is how two implementations of one meaning
    start to drift. ``test_one_lookup_serves_both_rails`` pins the count.

    DEGRADES TO TODAY'S ANSWER, LOUDLY. The module's own rule is that fold
    errors are not swallowed, and its stated reason is a page that "silently
    loses its prices" (gotcha #53). Neither half applies to this call: the
    fallback is each row's OWN ``win_probability_sources``, so no price is
    lost — the card prints exactly what it printed before this repair — and
    ``logger.exception`` makes it the opposite of silent. What IS at stake is
    that these are the CORE rail of a Priority-#3 page (#1197 / #1239): the
    rows are already in hand, so a throw here would replace a working team page
    with a 500 for the sake of a number a reader would otherwise still see.
    """
    rows = [event for rail in rails for event in rail]
    folded: dict[int, dict] = {}
    try:
        folded = await folded_probability_sources_batch(db, rows)
    except Exception:
        logger.exception("team page: twin fold failed for team %s", team.id)

    return [
        [
            # The row's OWN sources are the default, never ``None``: the batch
            # promises an entry per event, but a miss must degrade to today's
            # unfolded answer rather than to a card whose number vanishes.
            _format_event_brief(
                FoldedBlendView(
                    event, folded.get(int(event.id), event.win_probability_sources)
                ),
                team,
            )
            for event in rail
        ]
        for rail in rails
    ]


def _format_event_brief(event: Event, team: Team) -> dict:
    """Compact event format for team page game lists."""
    sport = event.sport
    is_home = (event.home_team_id == team.id) or (event.home_team_name == team.name)
    opponent = event.away_team_name if is_home else event.home_team_name

    # #5382: this used to read `win_probability_sources["aggregate"]` — the same
    # read #1776 found and fixed in `league_futures.py::_event_probability`, left
    # unfixed in this second file. THAT KEY HAS NEVER EXISTED (measured: 0 of
    # 52,975 events with a non-null column carry it); the schema is
    # `{source: {value, updated_at, …}}` and the blend is COMPUTED, never stored.
    # So `wp` was None on every row of every team page, including a LIVE game
    # holding five sources whose own event-page hero read 99%.
    #
    # Calls the canonical blend rather than rolling a mean over the sources here:
    # one number per question, and `status` travels on the event, so a completed
    # game drops Kalshi/Polymarket inside `_tier1_readings` without this
    # formatter re-deriving a settled-language rule of its own.
    #
    # The isinstance guard is KEPT, for league_futures' reason: the blend does
    # `.items()` on the column, so a truthy NON-dict (a list, a bare string)
    # raises AttributeError — and in a per-item formatter a throw does not blank
    # one row, it empties the whole rail (gotcha #42).
    wp = None
    if isinstance(event.win_probability_sources, (dict, type(None))):
        wp = compute_aggregate_probability(event)
        # The blend states the HOME side's probability; this brief is
        # team-relative ("we had them at 72%"), so an away row is the
        # complement — the same orientation `pregame_win_probability` gets for
        # free by picking between two stored columns. Safe because our
        # probabilities are two-way normalised in every sport, draw leagues
        # included: measured 2026-09-11, `opening_home + opening_away` sums to
        # 1.0000 with 0 exceptions across all 60 sport keys, soccer among them.
        if wp is not None and not is_home:
            wp = 1.0 - wp

    # L2-174 Item 3e — the recents expectation grammar ("we had them at 72%",
    # L2-158) never fired because this brief never emitted the pre-game line or the
    # settled timestamp; the frontend render (TeamGameCards) is league-agnostic and
    # gates silently on the missing field. The team-relative OPENING probability is
    # exactly "what we had them at" before the game; completed_at dates the result.
    pre = event.opening_home_probability if is_home else event.opening_away_probability

    return {
        "id": event.id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_score": event.home_score,
        "away_score": event.away_score,
        # #1779 family: never render live before the row's own start time.
        "status": served_event_status(
            event.status, event.commence_time, datetime.now(timezone.utc)
        ),
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        "sport_key": sport.key if sport else None,
        "is_home": is_home,
        "opponent": opponent,
        "win_probability": round(wp, 3) if wp is not None else None,
        "pregame_win_probability": round(float(pre), 3) if pre is not None else None,
        "completed_at": event.completed_at.isoformat() if event.completed_at else None,
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
