"""League-scoped futures endpoint.

Returns all open futures markets for a specific league, grouped by section
(series, awards, props, season_stats, more_markets). Powers the league
page's below-the-grid sections.

Phase 3 generalizes the sectioned layout to all major sports (NBA, NHL, MLB, NFL)
with sport-aware keyword classification for awards, series, and props.
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Path
from sqlalchemy import select, and_, or_, func, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models import Event, FuturesMarket, FuturesOutcome, Sport
from app.routes.events import (
    _build_team_lookup,
    _format_team_data,
    _normalize_futures_dedup_key,
)
from app.services import get_db
from app.utils.aggregation import compute_aggregate_probability
from app.utils.event_rails import (
    live_first_order,
    settled_rail_condition,
    unreported_rail_condition,
    upcoming_rail_condition,
)
from app.utils.game_state import normalize_live_game_state
from app.utils.matchup_sides import sided_yes_no_labels
from app.utils.lifecycle import event_is_playable, served_event_status
from app.utils.entity_page_tiers import (
    AVAILABILITY_DEGRADED,
    AVAILABILITY_EMPTY,
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
    resolve_entity_tier,
)
from app.utils.event_concept_cache import (
    ConceptCacheKeys,
    acquire_refresh_lock,
    cache_keys,
    release_refresh_lock,
)
from app.utils.proven_duplicates import not_a_proven_duplicate
from app.utils.sport_keys import SPORT_HIERARCHY

logger = logging.getLogger(__name__)

#: The league tier's Redis namespace. These are the keys that have been live since
#: #777, and `cache_keys()` reproduces them EXACTLY (`<prefix><sport_key>` and
#: `…:stale`) — so adopting the shared four-key layout here is a drop-in that adds
#: a `:refreshing` lock without moving or orphaning a single existing entry.
LEAGUE_CACHE_PREFIX = "bainluck:league:"

#: How fresh a *live* hit is. Unchanged from the value this route has always used;
#: the defect #1767 fixes was never this number (see `_schedule_league_refresh`).
LEAGUE_PRIMARY_TTL = 300

#: How long the mirror outlives an outage. Also unchanged, and deliberately so:
#: shortening it would have traded a 24-hour lie for a shorter one while leaving
#: the missing revalidation — the actual defect — in place.
LEAGUE_STALE_TTL = 86400

#: How old a mirror carrying GAME ROWS may be and still be served (#3389).
#:
#: #1767 restored revalidation but left it entirely reader-driven, and the 24h
#: mirror is unbounded in the one dimension that matters for a game: a snapshot
#: describes a moving object. Measured on production `0247b0ed`, Sat 2026-09-05
#: 02:26Z, with eight MLS matches in play: the league payload had last been built
#: at ~00:36Z — 1h50m earlier — because nobody had opened the page since. It
#: served Charlotte–Houston as `live`, 0–0, ESPN clock `66'`; `GET
#: /api/events/15291063` said `completed` at 01:40Z, 0–0, FT. Same row, same
#: producer, two hours apart. It also carried Inter Miami's kickoff as 23:30Z
#: against the event row's 01:05Z, because the mirror predated the re-key.
#:
#: So a mirror with games on it gets an age bound and the reader waits for a real
#: build past it. A page with NO game rows — a futures-only league, an off-season
#: board — keeps the full 24h outage mirror, which is what that mirror is for.
#: The bound sits above `LEAGUE_PRIMARY_TTL` plus the measured revalidation
#: delivery latency (167s that night: the rebuild queues on `background` behind
#: the typeahead warmers), so a page under continuous traffic never trips it —
#: only a genuine quiet gap does, and then exactly one reader pays the build.
LEAGUE_GAMES_MIRROR_MAX_AGE = 600

#: Revalidate a games payload while its primary slot is STILL VALID (#3389).
#:
#: The rebuild is only *started* once the primary has expired, and delivery
#: measured 167s against a 300s TTL — so a continuously-read league page spends
#: roughly a third of its life serving the mirror. Timeline from the same night,
#: `soccer_usa_mls`, one read every ten seconds: `fresh` 02:35:52 → 02:40:49
#: (300s exactly), `stale` 02:41:00 → 02:43:39, `fresh` again 02:43:47.
#:
#: 120 leaves 180s of headroom against that measured 167s, which is the whole
#: constraint: a replacement dispatched with less headroom than the delivery takes
#: arrives after the slot it replaces has already expired, and the early dispatch
#: buys nothing at all. `test_the_headroom_covers_the_measured_delivery_latency`
#: pins it — an earlier draft of this said "half the TTL" and shipped 150, which
#: is 17s short of the number in the sentence justifying it.
#:
#: What it costs, stated plainly: the cycle is `LEAGUE_EARLY_REVALIDATE_AFTER +
#: delivery`, so a league whose rebuild is delivered promptly rebuilds every ~130s
#: rather than every ~300s — roughly 2.3x the builds, at ~4s of database each, and
#: only for leagues that BOTH carry games and are being read right now. A congested
#: queue converges back on the old rate (120 + 167 = 287s). That is the right side
#: to be wrong on for a page showing a match in progress, and the ceiling on how
#: far behind that page can be drops with it.
LEAGUE_EARLY_REVALIDATE_AFTER = 120

router = APIRouter()

# Sport key → league name patterns for filtering (case-insensitive SQL ILIKE).
# Markets matching ANY pattern are included for that league.
LEAGUE_NAME_PATTERNS: dict[str, list[str]] = {
    "basketball_nba": ["NBA%", "%National Basketball%"],
    "basketball_wnba": ["WNBA%", "%Women_s National Basketball%"],
    "basketball_ncaab": ["%NCAA%Basketball%", "%March Madness%", "%College Basketball%"],
    "icehockey_nhl": ["NHL%", "%National Hockey%", "%Stanley Cup%"],
    "baseball_mlb": ["MLB%", "%Major League Baseball%", "%World Series%"],
    "americanfootball_nfl": ["NFL%", "%National Football%", "%Super Bowl%"],
    "americanfootball_ncaaf": ["%NCAA%Football%", "%College Football%", "%CFP%"],
    "soccer_epl": ["%Premier League%", "%EPL%"],
    "soccer_usa_mls": ["%MLS%", "%Major League Soccer%"],
    "soccer_spain_la_liga": ["%La Liga%", "%LaLiga%"],
    "soccer_germany_bundesliga": ["%Bundesliga%"],
    "soccer_uefa_champs_league": ["%Champions League%", "%UCL%"],
    "mma_mixed_martial_arts": ["%UFC%", "%Mixed Martial Arts%"],
    "tennis_atp": ["%ATP%", "%Roland Garros ATP%", "%Wimbledon%Men%", "%US Open%Men%", "%Australian Open%Men%"],
    "tennis_wta": ["%WTA%", "%Roland Garros WTA%", "%Wimbledon%Women%", "%US Open%Women%", "%Australian Open%Women%"],
    "boxing_boxing": ["%Boxing%", "%WBC%", "%WBA%", "%IBF%", "%WBO%"],
    "motorsport_f1": ["%Formula 1%", "%F1 %", "%Grand Prix%"],
    "motorsport_nascar": ["%NASCAR%"],
    "esports_lol": ["%League of Legends%", "%LoL %"],
    "esports_cs2": ["%Counter-Strike%", "%CS2%"],
    "esports_valorant": ["%Valorant%"],
}

# Sport key → Kalshi external_id prefix for precise filtering
LEAGUE_TICKER_PREFIXES: dict[str, list[str]] = {
    "basketball_nba": ["KXNBA"],
    "basketball_wnba": ["KXWNBA"],
    "basketball_ncaab": ["KXNCAAB", "KXMM"],
    "icehockey_nhl": ["KXNHL"],
    "baseball_mlb": ["KXMLB"],
    "americanfootball_nfl": ["KXNFL"],
    "americanfootball_ncaaf": ["KXNCAAF", "KXCFP"],
    "soccer_epl": ["KXEPL"],
    "soccer_usa_mls": ["KXMLS"],
    "mma_mixed_martial_arts": ["KXUFC"],
    "tennis_atp": ["KXATP"],
    "tennis_wta": ["KXWTA"],
    "boxing_boxing": ["KXBOXING", "KXWBC"],
    "motorsport_f1": ["KXF1"],
    "motorsport_nascar": ["KXNASCAR"],
    "esports_lol": ["KXLOL"],
    "esports_cs2": ["KXCS2"],
    "esports_valorant": ["KXVALORANT", "KXVAL"],
}

# ---------------------------------------------------------------------------
# Section assignment: sport-aware classification
# ---------------------------------------------------------------------------
# Target sections (matching frontend expectations):
#   series       — Playoff series matchups (Team A vs Team B, total games O/U)
#   awards       — MVP, ROY, Cy Young, Vezina, Selke, etc.
#   props        — Team-level props (win totals, div winners, playoff quals,
#                  trades, no-hitters, draft, Madden cover, etc.)
#   season_stats — Player stat-based markets (scoring leader, HR leader, etc.)
#   more_markets — Everything else
# ---------------------------------------------------------------------------

# Sport-specific award name fragments (matched case-insensitively).
# Generic awards ("MVP", "Rookie of the Year") are caught by tier == 3.
_AWARD_KEYWORDS: list[str] = [
    # NBA
    "defensive player of the year", "sixth man", "most improved",
    "clutch player", "finals mvp",
    # NHL
    "vezina", "selke", "norris", "conn smythe", "hart", "calder",
    "richard trophy", "art ross", "jack adams", "lady byng",
    # MLB
    "cy young", "hank aaron", "gold glove", "silver slugger",
    "reliever of the year", "manager of the year", "rookie of the year",
    # NFL
    "comeback player", "offensive player of the year",
    "defensive player of the year", "walter payton",
    "offensive rookie", "defensive rookie", "coach of the year",
    # MMA / UFC
    "fight of the year", "fighter of the year", "knockout of the year",
    "performance of the night",
]

# Keywords that identify a market as a playoff series matchup.
_SERIES_KEYWORDS: list[str] = [
    "series", "total games o/u", "total games over",
]

# Keywords for team/season-level props (not player stats).
_PROPS_KEYWORDS: list[str] = [
    "win total", "win more than", "win 100", "win 90", "win 80",
    "division winner", "make playoff", "clinch",
    "postseason", "wild card",
    "traded", "be traded", "trade",
    "no-hitter", "perfect game",
    "draft", "lottery",
    "cover of madden", "madden nfl",
    "debut date", "free agent",
    "sweep", "game 7", "playoff win total", "elimination",
    "fired", "general manager", "head coach",
    # Soccer
    "relegation", "promotion", "golden boot", "top scorer",
    # MMA / UFC
    "method of", "distance", "total rounds", "finish",
]

# Sports where "vs" indicates an individual match/fight, not a playoff series.
# Markets in these sports should go to "matches" section, not "series".
_INDIVIDUAL_MATCH_SPORTS: frozenset[str] = frozenset({
    "tennis", "mma", "boxing", "esports",
})

# Categories surfaced as a single, futures-ONLY hub: no per-game league split and
# no per-tournament event grouping yet, so head-to-head matchup markets are pure
# noise. Esports has thousands of per-map "Team A vs Team B" rows that would bury
# the genuine tournament outrights (MSI/LCK/Worlds/EWC winners), and there is no
# championship GRID for these — so we match the whole category, drop matchups, and
# surface title/winner markets in a "futures" section rather than hiding them.
# (#159-era lesson: esports data is messy — build only what honestly stands.)
_CATEGORY_WIDE_FUTURES_ONLY: frozenset[str] = frozenset({"esports"})

# Keywords for player-stat markets (season stats section).
_SEASON_STAT_KEYWORDS: list[str] = [
    "leader", "scoring title", "assists title", "rebounds title",
    "home run leader", "batting average", "era leader", "strikeout leader",
    "rushing leader", "passing leader", "receiving leader",
    "goal leader", "points leader", "save leader",
    "regular season record", "regular season wins",
    # Soccer
    "clean sheets", "assist leader", "top assists",
]


# ---------------------------------------------------------------------------
# UX-P062 (#1743, epic #1741): league identity, from the register
# ---------------------------------------------------------------------------

#: Every sport key that `SPORT_HIERARCHY` navigates to. This is what makes a
#: league a REAL entity for the tier resolver (spec §2): a registered league with
#: zero answers is a legitimate T0 page, while an unrecognised key is not a page at
#: all — that distinction is the generation gate, and it needs an identity source.
#: Derived from the register rather than re-listed, so adding a league to the nav
#: cannot leave a second list behind (the C23 constant-scatter lesson).
_REGISTERED_SPORT_KEYS: frozenset[str] = frozenset(
    key
    for sport in SPORT_HIERARCHY.values()
    for league in (sport.get("leagues") or [])
    for key in (league.get("sport_keys") or [])
)


#: How far back a settled game still counts as a RESULT worth showing. Long enough
#: that a league playing weekly still has receipts, short enough that "recent"
#: stays true.
RESULTS_LOOKBACK_DAYS = 14

#: Rail sizes. Both are counted caps (spec §4) — the payload carries the totals, so
#: a cap is never a silent truncation.
UPCOMING_GAMES_LIMIT = 8
RESULTS_LIMIT = 8

#: The NO RESULT REPORTED rail's cap (#3211). Its OWN constant, not a share of
#: `RESULTS_LIMIT`: the rail exists precisely because one cap over two
#: populations of very different size starved the smaller one out of existence,
#: and two rails governed by one number can never be tuned apart again.
#:
#: Smaller than the other two on purpose. This is the page's least informative
#: content — every card says the same thing, which is that we do not know — so
#: it earns fewer slots than the games a reader can still watch or the results
#: they came for. The cap is DECLARED like the others, so the rest is a number
#: the payload states rather than a truncation it hides.
UNREPORTED_LIMIT = 6


def upcoming_games_query(sport_key: str, now: datetime):
    """The UPCOMING GAMES rail, scoped to one league.

    `events` has no `sport_key` column, so the league scope is a join through
    `sports` (memory: project_events_no_sport_key).

    🔴 **Deliberately NOT fenced** — see `recent_results_query`. This ORDER BY
    leads with a CASE expression, so no index can serve the ordering and the
    planner already has to collect every match and sort. There is no LIMIT
    pushdown to prevent, and adding the fence measured strictly WORSE:
    `basketball_ncaab` went 56 blocks to 5,130 when it was applied here.
    A fence is a claim about one plan, not a house style.

    🔴 The status × time filter is `utils.event_rails.upcoming_rail_condition`
    and is no longer written here (#3211). It was the same two lines on the team
    page, and the pair of rails is only correct as a PAIR — the third state to
    fall between them cost 171 US Open matches. The module carries the argument
    for `live` losing this rail's `now - 2h` floor.
    """
    return (
        select(Event)
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Sport.key == sport_key,
            upcoming_rail_condition(now),
            # #2263: THE rail that made this visible. Read on 2026-08-29, the MLB
            # page printed Dodgers–Tigers, Marlins–Nationals and Padres–Rays TWICE
            # each — 3 of its 8 slots spent on second copies of a game already
            # above them. A row the registry PROVED duplicates another does not
            # get a slot. The proof is written at
            # `event_registry._proven_duplicates`; this only declines to print.
            not_a_proven_duplicate(),
        )
        # Q438: live-AND-started, not the raw column. A row that is live a month
        # before kickoff held this rail's first slot for ten weeks. The comment
        # sits ABOVE the clause because `league_rails_fence_mutations:M4` pins
        # the ORDER BY block verbatim as its needle.
        .order_by(
            live_first_order(now),
            Event.commence_time.asc(),
        )
        # +1 so the cap can be DECLARED rather than silently applied. A full
        # COUNT would be a second round trip to say the same thing.
        .limit(UPCOMING_GAMES_LIMIT + 1)
    )


def recent_results_query(sport_key: str, now: datetime):
    """The RECENT RESULTS rail, scoped to one league.

    🔴 **THE `OFFSET 0` IS AN OPTIMIZATION FENCE, NOT A PAGING CLAUSE.** Removing
    it re-opens a 4.9-second cold read. LAT-P110, #2260.

    The flat form — these same filters with `ORDER BY commence_time DESC
    LIMIT 9` applied directly — lets the planner satisfy the ordering from
    `ix_events_commence_time` and stop as soon as it has nine rows. That is the
    right plan for a league that played yesterday and a catastrophic one for a
    league that did not: the walk is bounded only by the 14-day window, so it
    reads EVERY event in that window looking for this league's own. Measured on
    production slug `67e2585c` with `EXPLAIN (ANALYZE, BUFFERS)` over the exact
    statement this function compiles — quoting BLOCKS, because wall time swings
    with the buffer cache while blocks do not:

        league                 flat blocks   fenced blocks   rows returned
        americanfootball_cfl        41,495             204               7
        basketball_ncaab            41,707             208               0
        baseball_ncaa               41,731             329               0
        soccer_epl                  41,731             219              11
        basketball_wncaab           41,731             205               0
        americanfootball_nfl        13,975             292              14
        baseball_mlb                 4,062             427              14
        tennis_atp                   3,824             429              14
        TOTAL                      230,256           2,313

    ~325 MB of buffer traffic per cold league open, and it is the QUIET leagues
    that pay most — precisely the ones whose 24h mirror has expired, so the
    person who opens the CFL tab is the person who waits. First cold read of
    `/api/leagues/americanfootball_cfl` on that slug: **4,649 ms**, of which the
    `EXPLAIN` attributes 4,923 ms to this statement alone on a cold buffer cache.

    `OFFSET 0` blocks subquery pull-up — PostgreSQL's `is_simple_subquery()`
    refuses any subquery carrying a limit or offset node, and the check is on
    the node's PRESENCE, not on its value — so the filter must run to completion
    before the sort. The planner then reaches for `ix_events_sport_id` and the
    ordering costs a sort over one league's own rows. Same rows, same order,
    same LIMIT: row counts were asserted identical between the two forms on all
    eight leagues above. Only the plan changes.

    Every measured league improves or holds; none regresses. The inner set is
    unbounded by design — bounding it would need an ORDER BY to be correct,
    which is the very pushdown this fence exists to prevent — and the 14-day
    window is the bound: the largest inner set across all 29 registered leagues
    is `tennis_atp` at 470 rows (measured, same slug).

    `literal_column("0")` rather than `.offset(0)`: a bind renders `OFFSET $1`,
    which fences just as well but makes the emitted statement differ from the
    one every number above was measured on.
    """
    inner = (
        select(Event)
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Sport.key == sport_key,
            # #2263, as on the upcoming rail. Placed INSIDE the fence with the
            # other filters, which is where the fence's own measurement says the
            # filtering happens — it runs to completion before the sort either
            # way, so this adds a predicate to a scan that was already reading
            # these rows and does not change the plan shape the table above
            # measured. The largest inner set across all 29 leagues is 470 rows.
            #
            # It sits ABOVE `settled_rail_condition` rather than below it, and
            # that is deliberate: these are ANDed, so the order is semantically
            # free, but `scripts/evals/league_rails_fence_mutations.py` anchors
            # M1, M2 and M7 on `settled_rail_condition(...)` being the last line
            # before the fence's `)`. Splitting that pair drifts three needles at
            # once — three mutants that then score NOT-APPLIED and silently guard
            # nothing. Free ordering, so spend it on keeping the needles alive.
            not_a_proven_duplicate(),
            # 'closed' as well as 'completed' — #1204's lesson: a settled
            # doubleheader (and every source that closes rather than completes)
            # is orphaned from a recents rail that only looks for 'completed'.
            #
            # 🔴 AND `suspended` (live/056) AND a `scheduled` row past its own
            # kickoff (#3211) — the second and third states to fall between this
            # rail and the upcoming one and appear on this league's page
            # NOWHERE. Both arms now live in `utils.event_rails`, with this
            # rail's lookback passed in rather than assumed, because the pair is
            # only correct as a pair and it was written twice. A copy is how the
            # omission survived CERT-786's sweep of the feed and
            # `GET /api/events`, and then survived live/056's sweep of this file.
            #
            # 🔴 #3211 rows are NOT here — they are `unreported_games_query`
            # below, and the split is load-bearing rather than tidy. They are
            # stamped midnight of the current day, so on this rail's
            # `commence_time DESC LIMIT 8` they sort above every Final: all
            # eight slots, measured against production, with Sabalenka's result
            # pushed off the page. Widening this condition is the same
            # disappearance aimed at the other population.
            settled_rail_condition(now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)),
        )
        .offset(literal_column("0"))
        .subquery()
    )
    fenced_event = aliased(Event, inner)
    return (
        select(fenced_event)
        .order_by(fenced_event.commence_time.desc())
        .limit(RESULTS_LIMIT + 1)
    )


def unreported_games_query(sport_key: str, now: datetime):
    """The NO RESULT REPORTED rail, scoped to one league — #3211.

    Matches whose kickoff has passed while the row still says `scheduled`. They
    are on this page at all because of #3211 (171 US Open matches were on no
    rail whatsoever) and they are on a rail of their OWN because of the cap:
    `utils.event_rails.unreported_rail_condition` carries the measurement.

    Same shape as `recent_results_query` deliberately, down to the `OFFSET 0`
    fence, because it is the same shape of question — a status filter over one
    league inside a 14-day window, ordered by time and capped. The fence's
    measurement (LAT-P110) is a claim about that shape and about this table's
    indexes, so it transfers; what would NOT transfer is inheriting the sibling
    rail's *no-fence* decision, which was measured on an ORDER BY leading with a
    CASE and does not apply here.

    Its own cap constant rather than a share of `RESULTS_LIMIT`: two rails whose
    lengths are set by one number cannot be tuned independently, and the whole
    reason this rail exists is that one number over two populations starved one
    of them.
    """
    inner = (
        select(Event)
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Sport.key == sport_key,
            unreported_rail_condition(
                now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)
            ),
        )
        .offset(literal_column("0"))
        .subquery()
    )
    fenced_event = aliased(Event, inner)
    return (
        select(fenced_event)
        .order_by(fenced_event.commence_time.desc())
        .limit(UNREPORTED_LIMIT + 1)
    )


def _event_probability(event: Event) -> float | None:
    """The blended home win probability, or None when we never measured one.

    Calls the canonical blend — it does NOT roll its own mean over sources.
    Register E9 records a second blend algorithm living in
    `teams.py::_get_championship_path`; this is not a third.

    #1776: this used to read `win_probability_sources["aggregate"]["home"]`, and
    THAT KEY HAS NEVER EXISTED. The column's schema is
    `{source: {value, display_name, type, color}}` — there is no `aggregate`
    member, because the blend is COMPUTED (`compute_aggregate_probability`, the
    reader CLAUDE.md names for this JSONB) rather than stored. So the function
    returned None unconditionally, for every event, and every league rail rendered
    its fixtures with no number at all: measured 118 of 118 upcoming games across
    all 29 registered leagues, including a LIVE MLB game holding five sources.
    The docstring above was already right about the intent; only the read was wrong.

    `status` travels implicitly on the event, and that matters here: the same
    formatter serves the RECENT RESULTS rail, and the canonical blend deliberately
    drops Kalshi/Polymarket once a game is completed/closed (their prices go stale
    post-final). Re-deriving a status rule locally would be the second algorithm
    this docstring exists to refuse.

    The isinstance guard is KEPT from the pre-#1776 version rather than dropped as
    dead weight: `compute_aggregate_probability` does `wps.items()` on
    `win_probability_sources or {}`, so a truthy NON-dict in that JSONB column
    (a list, a bare string) raises AttributeError rather than returning None. This
    runs inside a per-item formatter, and a throw here does not blank one row — it
    empties the entire rail (gotcha #42). The upstream fragility is real and is
    reported on #1776; guarding at the call site is this queue's business, editing
    the shared blend every surface depends on is not.
    """
    if not isinstance(event.win_probability_sources, (dict, type(None))):
        return None
    return compute_aggregate_probability(event)


def _format_game_brief(
    event: Event,
    sport_key: str | None = None,
    team_lookup: dict | None = None,
) -> dict:
    """League-rail shape for one game — the SHARED event card's contract.

    Deliberately NOT the team page's `_format_event_brief`: that one takes a team
    and renders from that team's perspective ("we had them at 72%"). A league rail
    has no home side to speak from, so the probability is stated as the home team's
    and named as such rather than left ambiguous.

    ── UX-P074 (#1860), ruling 047 ──
    The rail now renders through the SAME event card as `/sports/[key]`, search and
    My Stuff, so this payload has to carry what that card draws: the league chip,
    both sides of the blend, team colours/logos, and the live clock. Ruling 047's
    scope clause is explicit that the answer to "the shared card needs a field this
    page does not send" is to EXTEND THE CONTRACT, not to fork the card — so these
    keys are added under the names `_format_event` already uses on every other
    surface, rather than under rail-local ones a second reader would have to learn.

    `sport_key` is passed in rather than read off `event.sport`: the rails' query
    joins Sport for the WHERE clause without eager-loading the relationship, and a
    lazy attribute access inside an async request is a MissingGreenlet, not a slow
    read. The route knows the key — it is the argument the whole payload is built
    for.

    `home_win_probability` is KEPT alongside the new `current_odds`. It is what the
    tier census reads (a game with no blend is a fixture, not an answer) and what
    the iOS decoder already types; dropping it to "clean up" would silently retier
    every league.
    """
    home_prob = _event_probability(event)
    away_prob = round(1.0 - home_prob, 6) if home_prob is not None else None

    brief: dict = {
        "id": event.id,
        "external_id": getattr(event, "external_id", None),
        "sport": sport_key,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        # A FINAL card prefers this over commence_time for its date (gotcha #22
        # family): a Kalshi-sourced commence_time can be a close/resolution stamp.
        "completed_at": (
            event.completed_at.isoformat()
            if getattr(event, "completed_at", None)
            else None
        ),
        # Q438: through the lifecycle invariant, not raw. This is the SHARED
        # event card's status, so a raw read here puts a LIVE badge on every
        # surface that draws the card. Measured on production 2026-08-29:
        # `/api/leagues/americanfootball_nfl` served 15292756 (Colts vs Lions,
        # kickoff 17:00Z) and 15292757 (Titans vs Bears, 22:00Z) as `"live"`
        # hours before either kicked off, while `/api/events` — which already
        # routed through this helper — served the same two rows as `scheduled`.
        # One row, two answers, and the one the league page drew was the wrong
        # one. Admin/debug surfaces deliberately keep the raw value.
        "status": served_event_status(
            event.status, event.commence_time, datetime.now(timezone.utc)
        ),
        "home_score": event.home_score,
        "away_score": event.away_score,
        "home_win_probability": home_prob,
    }

    # THE ONE BLEND. `home_probability` here is the same number
    # `home_win_probability` carries — the same `compute_aggregate_probability`
    # call, not a second derivation — because the shared card reads `current_odds`
    # and the census reads the flat key, and the two must never be able to differ.
    if home_prob is not None:
        brief["current_odds"] = {
            "home_probability": home_prob,
            "away_probability": away_prob,
        }

    # Opening line — the card's live footer says "Opened 62/38" from this, and a
    # settled card falls back to it. Both columns are on the row already.
    opening_home = getattr(event, "opening_home_probability", None)
    if opening_home is not None:
        opening_away = getattr(event, "opening_away_probability", None)
        brief["opening_odds"] = {
            "home_probability": float(opening_home),
            "away_probability": (
                float(opening_away)
                if opening_away is not None
                else round(1.0 - float(opening_home), 6)
            ),
        }

    if team_lookup:
        home_team = team_lookup.get(event.home_team_name)
        away_team = team_lookup.get(event.away_team_name)
        if home_team and (home_team.primary_color or home_team.logo_url_small):
            brief["home_team_data"] = _format_team_data(home_team)
        if away_team and (away_team.primary_color or away_team.logo_url_small):
            brief["away_team_data"] = _format_team_data(away_team)

    # Live clock, normalised by the SAME helper the event route uses — the card
    # prints this string verbatim, and #1710's lesson was that an un-normalised
    # period field puts a pre-game sentence where "Q3" belongs.
    espn: dict = {}
    try:
        display_period, display_clock = normalize_live_game_state(
            sport_key,
            getattr(event, "period", None),
            getattr(event, "game_clock", None),
        )
        if display_period:
            espn["period"] = display_period
        if display_clock:
            espn["game_clock"] = display_clock
        if getattr(event, "broadcast_info", None):
            espn["broadcast"] = event.broadcast_info
    except Exception:  # pragma: no cover - defensive, a rail must not die on chrome
        logger.exception("league page: espn chrome failed for event %s", event.id)
    if espn:
        brief["espn"] = espn

    return brief


def _assign_section(market: FuturesMarket, sport_key: str = "") -> str:
    """Assign a market to a display section.

    Uses sport-aware keyword matching to classify into one of six sections:
    series, matches, awards, props, season_stats, more_markets.

    Individual match/fight sports (tennis, MMA, boxing, esports) use "matches"
    instead of "series" for head-to-head markets.
    """
    name_lower = (market.name or "").lower()
    cat = (market.category or "").lower()
    tier = market.market_tier

    # Determine sport category for match vs series classification
    sport_cat = sport_key.split("_")[0] if sport_key else ""
    is_individual_sport = sport_cat in _INDIVIDUAL_MATCH_SPORTS

    # Championship / conference / division (tier 1-2, 4) — already on grid
    if tier in (1, 2):
        return "championship"
    if tier == 4:
        return "championship"

    # --- Series / Matches ---
    # "vs" in a tier-5 market is a matchup — "series" for team sports, "matches"
    # for individual sports (tennis, MMA, boxing, esports).
    matchup_section = "matches" if is_individual_sport else "series"

    if any(kw in name_lower for kw in _SERIES_KEYWORDS):
        # Exception: "World Series Winner" is a championship, not a series
        if "world series winner" in name_lower:
            return "championship"
        return matchup_section
    if " vs " in name_lower or " vs. " in name_lower:
        # Tier-5 matchup
        if tier == 5:
            return matchup_section

    # For individual match sports, game_prop category markets are matches too
    if is_individual_sport and cat == "game_prop":
        return "matches"

    # --- Awards ---
    # Tier 3 = award by definition. Also match known award name fragments.
    if tier == 3 or cat in ("award", "mvp"):
        return "awards"
    if any(kw in name_lower for kw in _AWARD_KEYWORDS):
        return "awards"

    # --- Season stats (player-level) ---
    # Check before props because "leader" could overlap with "win total" props.
    if cat == "season_stat" or any(kw in name_lower for kw in _SEASON_STAT_KEYWORDS):
        return "season_stats"

    # --- Props (team/season-level) ---
    if any(kw in name_lower for kw in _PROPS_KEYWORDS):
        return "props"

    return "more_markets"


def league_cache_keys(sport_key: str) -> ConceptCacheKeys:
    """Every Redis key one league owns. Shared by the route and the refresh task so
    the two can never disagree about where the mirror lives."""
    return cache_keys(sport_key, prefix=LEAGUE_CACHE_PREFIX)


def _redis_or_none():
    """The bounded shared client, or None. Never raises (gotcha #39)."""
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _read_league_slot(rc, key: str) -> dict | None:
    """Read one league cache slot, or None.

    Deliberately NOT `event_concept_cache.read_slot`: that helper validates the
    stamped `cache` envelope and reads an unstamped payload as a MISS, so adopting
    it here would silently invalidate every live league entry and, worse, couple a
    revalidation fix to a payload-shape migration. The keys are shared; the codec
    is this tier's own until it adopts the envelope deliberately.
    """
    if rc is None:
        return None
    try:
        raw = rc.get(key)
    except Exception:
        logger.warning("league cache: read failed for %s", key)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception:
        logger.warning("league cache: refusing undecodable payload for %s", key)
        return None
    return payload if isinstance(payload, dict) else None


def _write_league_payload(rc, keys: ConceptCacheKeys, payload: dict) -> None:
    """Write both slots. Never raises."""
    if rc is None:
        return
    try:
        encoded = json.dumps(payload, default=str)
        rc.setex(keys.primary, LEAGUE_PRIMARY_TTL, encoded)
        rc.setex(keys.stale, LEAGUE_STALE_TTL, encoded)
    except Exception:
        logger.warning("league cache: write failed for %s", keys.primary)


def _schedule_league_refresh(rc, keys: ConceptCacheKeys, sport_key: str) -> None:
    """Kick exactly one background rebuild for `sport_key` and return immediately.

    #1767. This is the half that was missing, and its absence was not a slow cache
    — it was a 24-hour one. The stale branch returned the mirror and scheduled
    NOTHING, and the build path is reached only when BOTH slots miss, so a league
    rebuilt once per `LEAGUE_STALE_TTL` and served a stale copy for the other
    23h55m: ~99.6% of loads, measured in production an hour after the UX-P062
    deploy with every sampled league still pinned on a pre-deploy payload.

    Single-flight: a burst of readers arriving behind one TTL expiry produces one
    rebuild, not one per reader. The owner token travels WITH the dispatch because
    this request acquires the lock and the worker releases it (#1678 finding 1) —
    a producer that cannot name the token does not get to release.

    Best-effort throughout: the caller has already decided to serve the mirror, and
    nothing here may turn a served page into an error. If the dispatch itself fails
    the lock is released, so a dead broker costs the next reader a retry rather
    than wedging the key for `REFRESH_LOCK_TTL`.

    The guard wraps the ACQUIRE as well as the dispatch, so "never errors the
    page" is a property of this function rather than one inherited from
    `acquire_refresh_lock`'s internal hardening. A guarantee that holds only
    because a callee currently swallows its own exceptions is one refactor away
    from being false, and the caller has already committed to a 200 by the time it
    gets here.
    """
    token = None
    try:
        token = acquire_refresh_lock(rc, keys)
        if not token:
            return

        from app.tasks import celery_app

        celery_app.send_task(
            "app.tasks.refresh_league", args=[sport_key, token], queue="background"
        )
    except Exception:
        logger.warning("league: refresh dispatch failed for %s", sport_key, exc_info=True)
        if token:
            release_refresh_lock(rc, keys, token)


# #3245: the payload keys that carry games, in ONE place.
#
# Two decisions ask "does this league have anything on it": the mirror-write
# guard (`is_empty_league`) and the envelope's `availability`. #3211 added a
# third rail and only `availability` learned about it, so a league whose only
# content was unreported matches was judged EMPTY by the guard, never written
# to the primary slot, and served off the 24h mirror forever.
#
# Restating the rail list a third time would set the fourth rail up to repeat
# this exactly. Both decisions now derive from this tuple, and `availability`
# is computed by calling `is_empty_league` on the very payload it ships in —
# the two cannot disagree, whatever gets added next.
GAMES_RAIL_KEYS: tuple[str, ...] = (
    "upcoming_games",
    "recent_results",
    "unreported_games",
)


def is_empty_league(payload: dict) -> bool:
    """A league with no sections and no games on ANY rail has nothing on it."""
    return not (
        payload.get("sections")
        or any(payload.get(rail) for rail in GAMES_RAIL_KEYS)
    )


def has_games(payload: dict) -> bool:
    """Does this payload describe any GAMES?

    The age policy applies to games and only to games (#3389). A futures board is
    a standing answer and a 24-hour-old copy of it is very nearly right; a match
    has a clock, a score and a status that move under the snapshot. Derived from
    `GAMES_RAIL_KEYS` for the reason that tuple exists — the fourth rail must not
    have to teach a third call site about itself.
    """
    return any(payload.get(rail) for rail in GAMES_RAIL_KEYS)


def payload_age_seconds(payload: dict, now: datetime) -> float | None:
    """How long ago this payload was BUILT, or None if it cannot say.

    None is returned for a payload with no `built_at` and for one whose stamp
    does not parse. Both callers treat None as *too old* rather than as young
    (#3389): every mirror written before this stamp shipped is unstamped, and
    reading "no stamp" as "fresh" would pin those payloads in place for their
    full 24 hours — the exact failure being fixed, preserved by its own fix. Fail
    closed and the first reader after the deploy rebuilds.

    A stamp from the FUTURE (clock skew between web dynos) reads as age 0, not as
    a negative age: it is a reason to distrust the clock, never a licence to serve
    a payload for longer than the bound.
    """
    stamp = payload.get("built_at")
    if not isinstance(stamp, str):
        return None
    try:
        built = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if built.tzinfo is None:
        built = built.replace(tzinfo=timezone.utc)
    return max(0.0, (now - built).total_seconds())


def mirror_is_too_old(payload: dict, now: datetime) -> bool:
    """May this mirror still be served, or must the reader wait for a build?

    Keyed on the payload having GAMES, never on it having LIVE games. A mirror
    built before tonight's kickoffs has no live rows in it at all and is exactly
    the copy that prints "scheduled" over a match already in its second half —
    the symptom this queue was opened on. Its own contents cannot be the test of
    whether it is out of date.
    """
    if not has_games(payload):
        return False
    age = payload_age_seconds(payload, now)
    return age is None or age > LEAGUE_GAMES_MIRROR_MAX_AGE


async def build_and_cache_league(sport_key: str, db: AsyncSession, rc=None) -> dict:
    """Build one league, write both slots, return the payload.

    One implementation for the route's cold path and the background refresh, so the
    two cannot drift in what they store.

    **A degraded build is never mirrored.** `build_league` returns the `degraded`
    envelope when its market query times out, and caching that would pin an outage
    into the 24h mirror — the one payload that must never outlive its cause.

    **An empty build never overwrites a NON-EMPTY mirror**, the ordering
    `build_and_cache_hub` established: writing first would clobber the good
    snapshot with the blank page and then "rescue" by reading back the blank we
    just stored.

    This diverges from the hub's version in one deliberate way: the hub skips the
    write whenever *any* stale entry exists, and this skips only when the existing
    mirror still has content. An empty league whose mirror is also empty is the
    ordinary steady state for the 7 registered leagues that genuinely have nothing
    (`wncaab`, `cfl`, `ufl`, …), and skipping there would leave the primary slot
    permanently unset — so every request would fall to the stale branch and
    schedule another refresh, forever. Refusing to overwrite nothing with nothing
    protects no data and costs a rebuild per lock window.
    """
    payload = await build_league(sport_key, db)
    keys = league_cache_keys(sport_key)

    if payload.get("availability") == AVAILABILITY_DEGRADED:
        return payload

    if is_empty_league(payload):
        mirror = _read_league_slot(rc, keys.stale)
        if mirror is not None and not is_empty_league(mirror):
            return payload

    _write_league_payload(rc, keys, payload)
    return payload


@router.get("/{sport_key}")
async def get_league_futures(
    sport_key: str = Path(..., description="Sport key (e.g., basketball_nba, icehockey_nhl)"),
    db: AsyncSession = Depends(get_db),
):
    """Get all open futures markets for a league, grouped by section."""
    rc = _redis_or_none()
    keys = league_cache_keys(sport_key)
    now = datetime.now(timezone.utc)

    cached = _read_league_slot(rc, keys.primary)
    if cached is not None:
        # #3389: revalidate BEFORE the slot expires, not after. #1767 put the
        # rebuild behind the expiry, and the rebuild is delivered over the
        # `background` queue — 167s, measured, against a 300s TTL — so every
        # cycle ended in a stale window a third as long as the fresh one. The
        # dispatch is single-flight and idempotent, so an early one costs the
        # same single rebuild it always did, just soon enough to land in time.
        age = payload_age_seconds(cached, now)
        if has_games(cached) and (age is None or age >= LEAGUE_EARLY_REVALIDATE_AFTER):
            _schedule_league_refresh(rc, keys, sport_key)
        return cached

    stale = _read_league_slot(rc, keys.stale)
    if stale is not None and not mirror_is_too_old(stale, now):
        # UX-P062 (#1743), register E6: this served a 24h-old snapshot with no
        # declaration at all, so a substituted answer was indistinguishable from
        # a current one — ruling 025 clause 4, the named violation. The payload
        # was cached with `availability: fresh`; it is not fresh now.
        #
        # #1767: and the declaration is what made the REAL defect visible — the
        # mirror was being served almost always, because nothing ever rebuilt it.
        # Serve it (a fast answer beats a correct wait) and revalidate behind it.
        #
        # #3389: "a fast answer beats a correct wait" is true of a futures board
        # and false of a match in progress, and `mirror_is_too_old` is where the
        # two part company. Declaring the age as well as the substitution is the
        # rest of ruling 025 clause 4 — "stale" alone does not distinguish the
        # forty-second-old copy from the two-hour-old one, and on the night this
        # was found only the second was a lie.
        _schedule_league_refresh(rc, keys, sport_key)
        stale["availability"] = AVAILABILITY_STALE
        stale["stale_age_seconds"] = payload_age_seconds(stale, now)
        return stale

    built = await build_and_cache_league(sport_key, db, rc)

    # #3389. The age bound must cost the mirror's ORIGINAL job, which is outages.
    # A build that could not read the database returns the `degraded` envelope —
    # no games, no sections, `tier: None` — and preferring that to a ten-minute-old
    # page would be a worse answer than the one the bound was added to prevent.
    # The bound decides which of two REAL answers is better; it does not license
    # replacing an answer with an admission of failure. The mirror is still
    # declared stale, and now declares its age too, so nothing here is passed off
    # as current.
    if built.get("availability") == AVAILABILITY_DEGRADED and stale is not None:
        stale["availability"] = AVAILABILITY_STALE
        stale["stale_age_seconds"] = payload_age_seconds(stale, now)
        return stale

    return built


def _sport_category_for(sport_key: str) -> str:
    """`basketball_nba` → the `llm_sport_category` value ("basketball")."""
    sport_category = sport_key.split("_")[0]
    # Map common prefixes to their llm_sport_category values
    _SPORT_KEY_TO_LLM_CATEGORY: dict[str, str] = {
        "americanfootball": "football",
        "icehockey": "hockey",
        "motorsport": "motorsports",
    }
    return _SPORT_KEY_TO_LLM_CATEGORY.get(sport_category, sport_category)


def _league_scope_filters(
    sport_key: str,
    now: datetime,
    *,
    also_sport_keys: Sequence[str] = (),
) -> list:
    """Everything that scopes a market to THIS league, and nothing else.

    UX-P180 (#2167). Extracted so `build_league` and the hub's linked-matches rail
    (`build_linked_matches`) cannot drift about what "a tennis_atp market" means.

    Deliberately EXCLUDES the `event_id` predicate. That predicate is the one
    thing the two callers legitimately disagree about — a futures list wants the
    markets NOT tied to a game, a matches rail wants precisely the ones that ARE —
    and it was that single line, applied to both through one shared code path,
    that made `/hub/tennis` head a rail "MATCHES · 56" over zero matches. Keeping
    it out of the shared helper is what stops the next caller inheriting it by
    accident.

    ── UX-P182 (#3447): `also_sport_keys`, for a hub that spans two tours ──

    A LEAGUE is one tour; a HUB is a sport. `/hub/tennis` is the site's only
    tennis surface and it was declared `sport_key="tennis_atp"`, so the league OR
    below resolved to `KXATP%` + `%ATP%`/`%US Open%Men%`/… and the women's draw
    could not enter: measured on production 2026-09-06, the rail carried 126 cards
    — 80 of them men's Challenger matches — and zero `KXWTA*` rows, while the
    page's own starred MARQUEE card was the Women's US Open Winner.

    The extra keys widen the LEAGUE clause only. Everything else — status, the
    resolution-date floor, `llm_sport_category`, the `% at %` exclusion — is
    unchanged and still applies to every row, so this can add rows from a sibling
    tour and can never add a row the primary scope would have rejected for any
    other reason. Callers that pass nothing get byte-identical filters.

    Raises `ValueError` when an extra key belongs to a different sport category:
    `llm_sport_category` is a single-valued equality above, so a mismatched key
    would widen the OR while the AND above still rejected every row it added —
    a filter that reads wider and returns nothing. Loud beats silent (D55).
    """
    scope_keys = [sport_key, *also_sport_keys]
    primary_category = _sport_category_for(sport_key)
    mismatched = {
        k: _sport_category_for(k)
        for k in also_sport_keys
        if _sport_category_for(k) != primary_category
    }
    if mismatched:
        raise ValueError(
            f"also_sport_keys must share {sport_key}'s sport category "
            f"{primary_category!r}; got {mismatched!r}"
        )

    filters = [
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        FuturesMarket.llm_sport_category == primary_category,
    ]

    if sport_key in _CATEGORY_WIDE_FUTURES_ONLY:
        # Whole category (already scoped by llm_sport_category above) — no per-game
        # league split. Drop head-to-head matchups; for esports these are the
        # thousands of per-map "Team A vs Team B" rows that would bury the real
        # tournament futures.
        filters.append(~FuturesMarket.name.ilike("% vs %"))
        filters.append(~FuturesMarket.name.ilike("% vs. %"))
    else:
        # League-level filtering: use ticker prefix (Kalshi) + name patterns
        league_conditions = []
        for key in scope_keys:
            for prefix in LEAGUE_TICKER_PREFIXES.get(key, []):
                league_conditions.append(FuturesMarket.external_id.ilike(f"{prefix}%"))

            for pattern in LEAGUE_NAME_PATTERNS.get(key, []):
                league_conditions.append(FuturesMarket.name.ilike(pattern))

            # Also match llm_league if set
            league_short = key.split("_", 1)[1] if "_" in key else key
            league_conditions.append(FuturesMarket.llm_league.ilike(league_short))

        if league_conditions:
            filters.append(or_(*league_conditions))

    # Exclude game-level matchup markets (vs patterns)
    filters.append(~FuturesMarket.name.ilike("% at %"))
    return filters


def _sorted_outcomes(market: FuturesMarket) -> list:
    """A market's outcomes, most probable first."""
    return sorted(
        market.outcomes,
        key=lambda o: float(o.current_probability) if o.current_probability else 0,
        reverse=True,
    )


def _effectively_resolved(sorted_outcomes: list) -> bool:
    """Has this market already answered itself? (leader ≥97% having opened ≥85%,
    or every outcome pinned below 3% / above 97%.)"""
    if not sorted_outcomes:
        return False
    leader = sorted_outcomes[0]
    leader_prob = float(leader.current_probability) if leader.current_probability else 0
    if leader_prob >= 0.97:
        leader_opening = (
            float(leader.opening_probability) if leader.opening_probability else None
        )
        if leader_opening is not None and leader_opening >= 0.85:
            return True
    # All-settled filter: skip if every outcome is <3% or >97% (post-season resolved)
    probs = [
        float(o.current_probability)
        for o in sorted_outcomes
        if o.current_probability is not None
    ]
    return len(probs) >= 2 and all(p < 0.03 or p > 0.97 for p in probs)


def _serialize_outcomes(sorted_outcomes: list, market=None) -> list[dict]:
    """The top ten outcomes in the shape every league/hub card renders.

    ``market`` is what lets a bare "Yes" name its side (#3089): the side lives
    only in the market's NAME, and an outcome row cannot see it. Passing None
    keeps the raw venue labels — the pre-#3089 behaviour — so a caller that has
    no market in hand degrades to the status quo rather than guessing.
    """
    labels = (
        sided_yes_no_labels(
            getattr(market, "name", None),
            getattr(market, "llm_sport_category", None),
            [o.name for o in sorted_outcomes],
        )
        if market is not None
        else None
    )
    return [
        {
            "id": o.id,
            # Renamed for READING only. The row keeps its id, so anything that
            # resolves, settles or charts this outcome still addresses it by id
            # and is untouched by the label.
            "name": (labels or {}).get(o.name, o.name),
            "probability": float(o.current_probability) if o.current_probability else None,
            "opening_probability": float(o.opening_probability) if o.opening_probability else None,
            "rank": o.rank,
            "movement_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
            "team_id": o.team_id,
        }
        for o in sorted_outcomes[:10]
    ]


def _competition_echoes_name(competition: str, market_name: str | None) -> bool:
    """True when the competition says nothing the card's own name does not.

    MEASURED ON PRODUCTION, and the reason this function exists — outside
    tennis, Kalshi's competition IS the card's own name, or its prefix:

        card "MMA: Loud vs Natividad"              competition "MMA"
        card "331: Chikadze vs Brito"              competition "331"
        card "Canelo Alvarez vs Christian Mbilli"  competition "Alvarez vs Mbilli"

    Drawn literally, every MMA card on `/hub/mma` would wear a "MMA" eyebrow
    over a name already starting "MMA:", which is UX-P239 / #3491's bug — a card
    printing its own question back at itself — reintroduced on another surface.

    Token containment rather than a prefix or equality test, because the boxing
    case is neither: "Alvarez vs Mbilli" is the surnames of "Canelo Alvarez vs
    Christian Mbilli", scattered through it. If every word of the label is
    already on the card, the label is redundant BY DEFINITION, so this needs no
    per-sport denylist and no sport_key — and tennis passes it untouched
    ("US Open Women Doubles" shares no token with "Dart / Lumsden vs Bucsa /
    Melichar-Martinez").
    """
    tokens = set(re.findall(r"[a-z0-9]+", competition.lower()))
    if not tokens:
        return True
    return tokens <= set(re.findall(r"[a-z0-9]+", (market_name or "").lower()))


def _market_competition(market) -> str | None:
    """The tournament a match card belongs to, or None when nobody said.

    Read straight from what the venue stated at ingest — never derived here.
    A Kalshi tennis match market's name is only the two players ("Iannaccone vs
    Weis"), so without this the reader cannot tell a US Open match from a
    third-tier Challenger; both render as a bare "X vs Y" (#3508).

    None is a first-class answer, and it is the COMMON case rather than an error
    path. Polymarket rows carry no competition key — their own name already
    leads with the tournament ("US Open WTA: …"). Kalshi omits it on series with
    no tournament. And on every non-tennis hub measured, the value it does carry
    merely restates the card, so it is dropped by `_competition_echoes_name`.
    A card that cannot say something new says nothing.
    """
    metadata = getattr(market, "market_metadata", None)
    if not isinstance(metadata, dict):
        return None
    competition = metadata.get("competition")
    if not isinstance(competition, str):
        return None
    competition = competition.strip()
    if not competition:
        return None
    if _competition_echoes_name(competition, getattr(market, "name", None)):
        return None
    return competition


async def build_league(sport_key: str, db: AsyncSession) -> dict:
    """Build one league payload from the database. Does not touch the cache."""
    now = datetime.now(timezone.utc)

    filters = _league_scope_filters(sport_key, now)
    # A futures/awards list is the markets NOT tied to a game — a market linked to
    # an event belongs on that event's page. See `_league_scope_filters`.
    filters.append(FuturesMarket.event_id.is_(None))

    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*filters)
        .order_by(FuturesMarket.market_tier.asc().nulls_last())
        .limit(200)
    )

    try:
        result = await asyncio.wait_for(db.execute(query), timeout=25)
    except asyncio.TimeoutError:
        # UX-P062 (#1743), register E6: a statement timeout returned the SAME empty
        # shape as a league that genuinely has no markets, so an outage and an
        # off-season rendered identically. `degraded` is the whole distinction
        # (ruling 025 clause 4), and `tier: None` would tell the page to render a
        # confident T0 statement about data we failed to read.
        return {
            "sport_key": sport_key,
            "sections": {},
            "total_markets": 0,
            "error": "timeout",
            "tier": None,
            "availability": AVAILABILITY_DEGRADED,
            "pool_counts": {"answers": 0, "dropped": 0, "settled": 0},
            "section_counts": {},
        }
    markets = list(result.scalars().unique().all())

    # Group by section + deduplicate by canonical_market_key
    sections: dict[str, list[dict]] = {
        "futures": [],
        "series": [],
        "matches": [],
        "awards": [],
        "props": [],
        "season_stats": [],
        "more_markets": [],
    }

    # LAT-P086 (F1, Fable directive 2026-08-24 item 1). Keyed on the market's
    # NAME, via the one shared implementation in `app.routes.events` — never on
    # `canonical_market_key`. See the block at the bottom of this loop for what
    # the old key cost; the short version is that a category is not an identity.
    seen_dedup: dict[str, dict] = {}

    # UX-P062 (#1743), register E8 / ruling 025 clause 3. The two price-based skips
    # below used to be bare `continue`s, so a section that lost every row to them
    # simply disappeared and the page reported the remainder as if it were the
    # whole. A swallow that counts is detection; a swallow that doesn't is
    # concealment. This counts them PER SECTION so the envelope can say "showing 3
    # of 11" instead of quietly saying "3".
    #
    # It deliberately does NOT change WHICH markets are skipped. Spec §10 E8 records
    # that skipping on price alone is the C16 class and that whatever Alex rules for
    # Discover binds here identically — that ruling is not this queue's to make, and
    # counting the skip is what makes the eventual decision measurable.
    resolved_skipped: dict[str, int] = {}

    #: Championship/conference/division rows, kept for the CENSUS only — the grid
    #: renders them. See the amendment note at the skip site below.
    championship_census: list[dict] = []

    for market in markets:
        section = _assign_section(market, sport_key)

        # Skip championship/conference/division — already on the grid
        if section == "championship":
            if sport_key in _CATEGORY_WIDE_FUTURES_ONLY:
                # No championship grid exists for these hubs — surface the
                # title/winner markets in a dedicated "futures" section instead of
                # dropping them (they are the whole point of the esports hub).
                section = "futures"
            else:
                # UX-P062 (#1743) + Alex's 2026-08-11 amendment: the grid IS the
                # rendering of this family, and it is the league page's centerpiece
                # — so it must COUNT, even though it is not rendered as cards here.
                #
                # This was the census hole. Dropping the row entirely meant the
                # title-winner family was invisible to the tier resolver, which is
                # why MLB measured "awards + props" and nothing else, and why zero
                # of 29 leagues could reach T3. Counted, not rendered.
                championship_census.append(
                    {
                        "id": market.id,
                        "group_id": market.group_id,
                        "canonical_market_key": market.canonical_market_key,
                        "status": market.status,
                        "resolution_date": (
                            market.resolution_date.isoformat()
                            if market.resolution_date
                            else None
                        ),
                        "top_outcomes": [
                            {
                                "probability": (
                                    float(o.current_probability)
                                    if o.current_probability is not None
                                    else None
                                )
                            }
                            for o in market.outcomes
                        ],
                    }
                )
                continue

        sorted_outcomes = _sorted_outcomes(market)

        # Skip effectively resolved markets (leader ≥97% and opened ≥85%)
        if _effectively_resolved(sorted_outcomes):
            resolved_skipped[section] = resolved_skipped.get(section, 0) + 1
            continue

        outcomes_data = _serialize_outcomes(sorted_outcomes, market)

        market_data = {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "external_id": market.external_id,
            "market_tier": market.market_tier,
            "category": market.category,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "outcome_count": len(market.outcomes),
            "top_outcomes": outcomes_data,
            "canonical_market_key": market.canonical_market_key,
            # UX-P061 (#1742, epic #1741): the entity tier resolver counts ANSWERS,
            # not rows, and it deduplicates by `group_id` + `canonical_market_key`
            # (spec §2). MEASURED before adding this: on the esports hub only 7 of
            # 190 rows carried a canonical key and `group_id` was not in the payload
            # at all, so 190 rows resolved to 187 "answers" — the flagship
            # answers-not-rows case the spec cites did not collapse ANYTHING.
            #
            # `group_id` is what makes ten Polymarket sub-markets about one question
            # count as one question. It is already on the model, already indexed,
            # and already the feed's dedup key; it was simply never serialized here.
            "group_id": market.group_id,
            "section": section,
        }

        # ── Deduplicate by NAME (keep the row with the most outcomes) ──
        #
        # LAT-P086 (F1). This used to key on `canonical_market_key`, which is
        # the second site of the defect ruled at `events.py:101-157` under
        # LAT-P038/#1769 — and the worse of the two, because search only
        # *ranked* by that key while this loop DELETES siblings by it.
        #
        # `compute_canonical_market_key` builds `{sport}:{league}:{category}:
        # {season}`. Nothing in that string names a market, so every market a
        # league runs in a season collides. Measured on production 2026-08-24
        # against this route's own 200-row pool query for `soccer_epl`,
        # counting only rows that reach this line (tier not in 1/2/4):
        #
        #     rows reaching the dedup ............. 168
        #     of those, carrying a canonical key ... 80
        #     distinct canonical keys among them .... 8
        #     rows DELETED ......................... 72
        #
        # `soccer:EPL:championship:2026-27` alone held 23 of them: the EPL
        # Playmaker Award, "EPL: Next Chelsea Manager?", the Egypt Premier
        # League runner-up, the Ukrainian Premier League 3rd-place finish, the
        # English Premier League top goalscorer. Twenty-two deleted so the
        # twenty-third could render — not duplicates, not even the same league.
        #
        # Two further consequences, both fixed here:
        #
        # 1. The removal filtered a whole section by the shared key, so it took
        #    every row carrying it rather than the one being replaced. That was
        #    invisible only because the dedup had already stopped the others
        #    from being appended. It now keys on the row's `id`.
        # 2. The key spans tiers, so the removal reached ACROSS sections — the
        #    tier-3 award above was appended to `awards` and then deleted by a
        #    tier-5 manager market. The name key carries `market_tier`, so
        #    cross-tier collisions cannot happen at all now.
        #
        # The deletions were also invisible to the envelope: `section_counts`
        # is derived from `sections` after this loop and `total` is
        # `shown + resolved_skipped`, so canonically-deleted rows were
        # subtracted before anything counted them (ruling 025 clause 3).
        dedup_key = _normalize_futures_dedup_key(market)
        existing = seen_dedup.get(dedup_key)
        if existing is not None:
            if len(outcomes_data) <= len(existing["top_outcomes"]):
                continue
            # Replace the thinner row — and remove THAT ROW, by id.
            old_section = existing["section"]
            sections[old_section] = [
                m for m in sections[old_section] if m["id"] != existing["id"]
            ]
        seen_dedup[dedup_key] = market_data

        sections[section].append(market_data)

    # Sort within each section by market importance
    for section_name, items in sections.items():
        items.sort(key=lambda m: (
            -(m.get("market_tier") or 99),
            -(m.get("outcome_count") or 0),
        ))

    # Remove empty sections
    sections = {k: v for k, v in sections.items() if v}

    # ── Alex's 2026-08-11 amendment: the games rails ──
    #
    # "League pages include an UPCOMING GAMES rail and a RECENT RESULTS rail — event
    # cards, the product's richest and freshest content. No new pipeline; events
    # already exist." They are served from THIS route rather than fetched separately
    # by the page, because the tier is declared here (ruling 021) and a census that
    # counts content the page sourced elsewhere can silently diverge from what the
    # reader actually sees.
    #
    # `events` has no sport_key column, so the league scope is a join through
    # `sports` (memory: project_events_no_sport_key). Guarded like every optional
    # section on the team page: a failure here degrades the rails, never the page.
    upcoming_games: list[dict] = []
    recent_results: list[dict] = []
    unreported_games: list[dict] = []
    more_games = False
    more_results = False
    more_unreported = False
    try:
        _games_q = upcoming_games_query(sport_key, now)
        _results_q = recent_results_query(sport_key, now)
        _unreported_q = unreported_games_query(sport_key, now)
        _g = await asyncio.wait_for(db.execute(_games_q), timeout=10)
        _g_events = list(_g.scalars().all())
        _r = await asyncio.wait_for(db.execute(_results_q), timeout=10)
        _r_events = list(_r.scalars().all())
        _u = await asyncio.wait_for(db.execute(_unreported_q), timeout=10)
        _u_events = list(_u.scalars().all())

        # UX-P074 (#1860): colours and logos for the SHARED event card, fetched
        # ONCE for both rails. `_build_team_lookup` is the same in-memory-cached
        # helper the events and feed routes use (a ~500-row table, 5-minute TTL),
        # so this is one small query at worst and zero at best — not N per game.
        # getattr, because this loop runs OUTSIDE the per-item guard below: a row
        # that cannot answer for its own team names would otherwise take both
        # rails down from here, one statement before the guard that exists to
        # stop exactly that (gotcha #42).
        _team_names: list[str] = []
        for _e in (*_g_events, *_r_events, *_u_events):
            for _n in (
                getattr(_e, "home_team_name", None),
                getattr(_e, "away_team_name", None),
            ):
                if _n:
                    _team_names.append(_n)
        _teams: dict = {}
        if _team_names:
            try:
                _teams = await asyncio.wait_for(
                    _build_team_lookup(db, _team_names), timeout=10
                )
            except Exception:
                # Chrome, not content: a game with no logo is still a game.
                logger.exception("league page: team lookup failed for %s", sport_key)

        # Per-item, not per-rail (gotcha #42: "one bad item must never wipe a
        # whole scoring pass"). This formatter reads twice as many columns since
        # UX-P074, and the whole rails block sits under ONE except — so a single
        # unreadable row used to take all sixteen games with it.
        def _format_all(events: list) -> list[dict]:
            out: list[dict] = []
            for _e in events:
                try:
                    out.append(_format_game_brief(_e, sport_key, _teams))
                except Exception:
                    logger.exception(
                        "league page: game %s failed to format for %s",
                        getattr(_e, "id", "?"),
                        sport_key,
                    )
            return out

        _grows = _format_all(_g_events)
        more_games = len(_grows) > UPCOMING_GAMES_LIMIT
        upcoming_games = _grows[:UPCOMING_GAMES_LIMIT]

        _rrows = _format_all(_r_events)
        more_results = len(_rrows) > RESULTS_LIMIT
        recent_results = _rrows[:RESULTS_LIMIT]

        _urows = _format_all(_u_events)
        more_unreported = len(_urows) > UNREPORTED_LIMIT
        unreported_games = _urows[:UNREPORTED_LIMIT]
    except Exception:
        logger.exception("league page: games rails failed for %s", sport_key)

    # ── UX-P062 (#1743, epic #1741): the entity envelope (spec §7) ──
    #
    # Spec §2 / ruling 021: the TIER is a typed backend field. The moment web and
    # SwiftUI each count arrays to pick a layout, the same league renders as a map
    # on one and an answer on the other, and the parity bug is unfindable because
    # both clients are "correct". Counts come from the SHARED resolver and are never
    # reimplemented here — a second count is a second policy, and the histogram
    # would then predict a tier the page does not render.
    # The census is a SUPERSET of the rendered card sections, because two kinds of
    # content are rendered by something other than a card list (Alex's amendment):
    #   `championship` — rendered as the GRID, the page's centerpiece
    #   `games`        — rendered as the upcoming-games rail
    # Both are real content a reader sees, so both earn their place in the count.
    #
    # RECENT RESULTS are deliberately NOT a census section: settled content feeds
    # the RECORD, never the answer count (doctrine A4, which the kernel encodes —
    # settled rows resolve to zero answers, so a results "section" could never be
    # populated without changing the resolver). They arrive as `record_n`, which is
    # what the receipts strip is for (spec §5.3). Stated here because it is the one
    # clause of the amendment that does not resolve mechanically.
    census_sections = dict(sections)
    if championship_census:
        census_sections["championship"] = championship_census
    if upcoming_games:
        census_sections["games"] = [
            {
                "id": f"game:{g['id']}",
                # A game with no blended number is not an answer — it is a fixture.
                # Shaping it this way lets the ONE resolver make that call, instead
                # of this route inventing a second rule about what counts.
                "top_outcomes": [{"probability": g["home_win_probability"]}],
            }
            for g in upcoming_games
        ]

    tiering = resolve_entity_tier(
        census_sections,
        now=now,
        # A league in SPORT_HIERARCHY is a real entity; an unrecognised key is not a
        # page at all. That is the generation gate, and it is an IDENTITY question,
        # not a density one.
        entity_is_real=sport_key in _REGISTERED_SPORT_KEYS,
        # Settled games are the league's receipts. This is what makes a registered
        # league with zero live answers a legitimate T0 PAGE (a statement with a
        # record on it) rather than a generation-gate 404.
        # #3211: `unreported_games` is deliberately NOT added in. A match nobody
        # reported is not a receipt — it is the absence of one — and counting it
        # would let a league with no results at all claim a record it does not
        # have. Same reasoning as the settled-only census clause above.
        record_n=len(recent_results),
        next_event_count=len(upcoming_games),
        season_known=False,
    )

    # Per-section total/shown/dropped. The key set is the UNION of what survived and
    # what was skipped on price: a section whose every row was skipped vanished from
    # `sections` entirely, and reporting nothing about it is precisely the silent
    # truncation clause 3 forbids.
    section_counts: dict[str, dict[str, int]] = {}
    for name in set(tiering["per_section"]) | set(resolved_skipped):
        s = tiering["per_section"].get(
            name, {"total": 0, "answers": 0, "unpriced": 0, "settled": 0}
        )
        skipped = resolved_skipped.get(name, 0)
        section_counts[name] = {
            # `total` is what we HAD before the price skip, so "showing X of Y" is
            # true about the league rather than true about the leftovers.
            "total": s["total"] + skipped,
            "shown": s["total"],
            "dropped": s["unpriced"] + skipped,
            "answers": s["answers"],
        }

    total_skipped = sum(resolved_skipped.values())
    pool_counts = dict(tiering["pool_counts"])
    pool_counts["dropped"] = pool_counts["dropped"] + total_skipped

    response = {
        "sport_key": sport_key,
        "sections": sections,
        "total_markets": sum(len(v) for v in sections.values()),
        # Alex's amendment. The cap is DECLARED, not silent: `has_more` says there
        # is more behind it (spec §4 — an uncounted cap reads as coverage).
        "upcoming_games": upcoming_games,
        "upcoming_games_has_more": more_games,
        "recent_results": recent_results,
        "recent_results_has_more": more_results,
        # #3211 — its own key, its own declared cap. NOT folded into
        # `recent_results`: these rows sort above every Final and would have
        # taken all eight of its slots (see `unreported_games_query`).
        "unreported_games": unreported_games,
        "unreported_games_has_more": more_unreported,
        "record_n": len(recent_results),
        "tier": tiering["tier"],
        "pool_counts": pool_counts,
        "section_counts": section_counts,
        # #3389. `now` is the build's own logical clock — the instant every rail
        # above was read as of — so this dates the CONTENT, not the moment the
        # dict was assembled or the moment it was served. A banked payload that
        # stamps serve time answers a different question than the one the reader
        # is asking (memory: banked_pass_endpoint_stamps_serve_time), and the
        # question here is "how far behind the game is this copy".
        "built_at": now.isoformat(),
    }

    # Ruling 025's vocabulary, never live/stale_ok/unavailable (register E10).
    # A freshly built response with nothing AT ALL in it is EMPTY — a real
    # state, and a different one from the degraded reads stamped on the cache
    # and timeout paths, which is the whole point of declaring it. "Nothing"
    # has to include the games rails, or a league mid-season with a full
    # schedule and no futures would declare itself empty.
    #
    # #3211: `unreported_games` counts too. A league whose entire visible
    # fortnight is matches nobody reported has content — that is exactly
    # what the tennis pages were during the US Open — and calling that page
    # EMPTY would be the same claim of absence this issue exists to remove,
    # made one level up in the envelope.
    #
    # #3245: this asks the mirror-write guard's OWN predicate rather than
    # restating its rail list. When the two were written out separately they
    # drifted the moment #3211 landed; sharing the function is what stops it
    # happening again.
    response["availability"] = (
        AVAILABILITY_EMPTY if is_empty_league(response) else AVAILABILITY_FRESH
    )

    return response


# ---------------------------------------------------------------------------
# UX-P180 (#2167) — the hub's OWN matches source
# ---------------------------------------------------------------------------
#
# `build_hub` filled its `matches` section from `get_league_futures`, which
# filters `FuturesMarket.event_id.is_(None)`. That filter is correct for a
# futures/awards list and exactly wrong for a matches rail, because **a real
# match is precisely a market that HAS an event_id**. The rail could therefore
# only ever show the head-to-heads the matcher FAILED to link — the better
# matching got, the emptier it became.
#
# Measured on production 2026-09-05 (`GET /api/hub/tennis`, mid-US-Open): the
# rail was headed "MATCHES · 56" over 55 season-long ranking props, 7 doubles
# and one row reading "Ferrari vs Ferrari". Zero singles matches, while 204
# linked, correctly-classified, currently-playable US Open head-to-heads sat
# excluded.
#
# This is the disjoint second source. It does NOT relax the filter above.

#: How far back a linked match may have started and still be "on now".
#
# The event rows carry a `status`, but it is not trustworthy enough to be the
# only test: measured on production 2026-09-05, 18 head-to-heads dated Sep 2
# were still `scheduled` three days after they were played. The hub card renders
# a name and prices and NO date or status (`app/hub/[competition]/page.tsx`), so
# a finished first-round match is indistinguishable from tonight's quarter-final
# — which is the same lying-heading defect this ship exists to remove, one row
# down. A clock floor is the honest test; a tennis match runs to roughly five
# hours, so twelve gives a completed match room to be reported without admitting
# yesterday's card.
LINKED_MATCH_LOOKBACK = timedelta(hours=12)

#: Cap on the linked-matches rail. A Grand Slam main draw plus doubles and
#: juniors is legitimately large; this bounds the payload without pretending the
#: remainder does not exist (the count travels in `section_counts`).
LINKED_MATCH_LIMIT = 200

#: Cap on the market pool read before the event read narrows it.
#:
#: UX-P182 (#3447) re-sized this. It was 1500 for a per-LEAGUE scope — "measured
#: on production 2026-09-05 the whole `tennis_atp` pool was 725 rows mid-US-Open"
#: — and `also_sport_keys` makes the tennis hub's scope per-SPORT, which is a
#: different population: measured 2026-09-06, ATP side 686 rows, WTA side 418,
#: 1,104 together. That is 74% of the old cap, and the pool query carries no
#: ORDER BY, so the row that falls off the end is whichever one Postgres reached
#: last. A shared cap over two unequal populations does not degrade evenly — it
#: caps the smaller one out, and the smaller one here is the women's draw, which
#: is the entire defect this ship exists to remove.
#:
#: So the cap is sized for the widened scope AND truncation is made loud below:
#: the read asks for one row more than the cap and warns when it gets it. A
#: number chosen from today's maximum is refuted by next season's; a log line
#: that fires the first time it is wrong is not.
LINKED_MATCH_POOL_LIMIT = 4000

#: Tiers that can never produce a `matches` row — `_assign_section` sends 1, 2
#: and 4 straight to "championship". Pruned in SQL so the event read below has
#: fewer rows to resolve. Tier 3 and NULL are NOT pruned: they can still reach
#: "matches" through the series-keyword and game_prop branches.
_NON_MATCH_TIERS = (1, 2, 4)


def _is_submarket_bundle(market: FuturesMarket) -> bool:
    """Does this market's OUTCOME list hold its own sub-markets rather than sides?

    Polymarket serialises a match's nested sub-markets as outcomes of the group
    (gotcha #18): "US Open ATP: A vs B Set 2 Winner" and "… Total Sets: O/U 3.5"
    arrive as outcomes of "US Open ATP: A vs B". Under a MATCHES heading that
    card answers everything except who wins — measured on production
    2026-09-05, the Mensik–Tien card led with "Set 2 Winner >99%" and never
    named a player, and four such rows printed >99% on the same card.

    Detected by the prefix each sub-market name carries, because that is what
    the serialisation actually does — not by counting outcomes, which would
    also condemn a legitimate multi-way market. Majority rather than any, so a
    head-to-head that happens to repeat its own name in one outcome is safe.
    Measured over the whole 126-row tennis rail the split is unambiguous: the
    eight bundles ran 8/9 to 16/17 prefixed, and all 71 two-sided markets ran 0.
    """
    name = (market.name or "").strip().lower()
    if not name:
        return False
    outcomes = [(o.name or "").strip().lower() for o in (market.outcomes or [])]
    if not outcomes:
        return False
    prefixed = sum(1 for o in outcomes if o.startswith(name))
    return prefixed * 2 > len(outcomes)


def _venue_competition(market: FuturesMarket) -> str | None:
    """The competition string exactly as the venue wrote it, or None.

    Deliberately NOT `_market_competition`, which is the DISPLAY reader and
    suppresses a label that merely echoes the card's own name. A rail-ordering
    rule wants the raw fact — "did the venue say which draw this is" — and a
    label that echoes the name is still an answer to that question.
    """
    metadata = getattr(market, "market_metadata", None)
    if not isinstance(metadata, dict):
        return None
    competition = metadata.get("competition")
    return competition if isinstance(competition, str) and competition.strip() else None


def _rail_tier(
    market: FuturesMarket,
    is_undercard: Callable[[str | None, str | None, str | None], object] | None = None,
) -> int:
    """0 for the tournament the reader came for, 1 for a feeder-circuit match.

    #3640, the ordering half. See `build_linked_matches` for why this sorts
    INSIDE the live band rather than above it.
    """
    if is_undercard is None:
        return 0
    return (
        1
        if is_undercard(market.external_id, market.name, _venue_competition(market))
        else 0
    )


def _match_card_rank(
    market: FuturesMarket,
    is_prop: Callable[[str | None, str | None], object] | None = None,
) -> tuple[int, int, int]:
    """Which of two markets for ONE event should be the card? Higher wins.

    A real match outranks a prop, a head-to-head outranks a sub-market bundle,
    and only then does the old "most outcomes" rule apply. The order matters and
    is the whole point: the loser of each pair is always the one with MORE
    outcomes, so ranking by size alone picks the card that cannot name a winner
    and discards the one that can.

    ── #3640: the prop key, and why it is FIRST ──

    `is_prop` is the caller's own prop predicate — for a hub, the very
    `_PROP_CLASSIFIERS` entry that is about to move props OUT of the matches
    section. A card elected here that predicate then evicts does not move the
    event to another section: this function elects exactly ONE card per event,
    so the eviction takes the whole match off the rail.

    Measured on production 2026-09-06 19:20Z, replaying these functions over the
    34 playable in-scope tennis events: the elected card was a prop for NINE of
    them, and those nine were exactly the absent US Open singles —
    Alcaraz–Paul (LIVE), Medvedev–Tiafoe (LIVE), Michelsen, Kalinskaya,
    Jovic–Gauff, Gea, Osaka, Zverev, Khachanov. Each lost to a Kalshi
    "<A> vs <B>: Exact Match Score" row whose six outcomes ("Alcaraz wins 3-0",
    …) outnumbered the two-sided head-to-head's two. Notice 27, the Marquee
    Axiom: a Slam match that is on court is never absent because we picked the
    wrong one of its own markets.

    It is a RANK key and not a filter, so an event whose every market is a prop
    still gets a card rather than vanishing — the failure this repairs, inverted,
    is not a repair. `is_prop=None` (every non-hub caller) is byte-identical to
    the pre-#3640 ordering.
    """
    prop = bool(is_prop(market.external_id, market.name)) if is_prop else False
    return (
        0 if prop else 1,
        0 if _is_submarket_bundle(market) else 1,
        len(market.outcomes or []),
    )


async def build_linked_matches(
    sport_key: str,
    db: AsyncSession,
    *,
    now: datetime | None = None,
    also_sport_keys: Sequence[str] = (),
    is_prop: Callable[[str | None, str | None], object] | None = None,
    is_undercard: (
        Callable[[str | None, str | None, str | None], object] | None
    ) = None,
) -> list[dict]:
    """The head-to-head markets for this league's CURRENTLY PLAYABLE events.

    The mirror image of `build_league`'s pool: same league scope, opposite
    `event_id` predicate. Returns rows in the section shape every hub/league card
    already renders, ordered live-first then soonest-first, so a person opening
    the page during a tournament sees what is on now and next.

    `also_sport_keys` widens the LEAGUE clause to sibling tours of the same sport
    — UX-P182 (#3447), where `/hub/tennis` could show the men's draw and not the
    women's. See `_league_scope_filters`. It reaches this rail and NOT
    `build_league`, because `/api/leagues/tennis_atp` is a tour page and is
    correct as it stands: a hub is a sport, a league is a tour.

    `is_prop` is the caller's prop predicate, used ONLY to rank each event's
    candidates (`_match_card_rank`, #3640). A caller that will later move props
    out of this section must pass the same predicate it will move them with, or
    the one card this function elects per event can be a card that caller then
    deletes — which removes the match, not the prop.

    `is_undercard` is the caller's feeder-circuit predicate, used ONLY to order
    the rail (`_rail_tier`, #3640's ordering half): a match the venue itself
    labels a Challenger sorts below one it does not, INSIDE the live band. It
    ranks, never filters, so a rail of nothing but Challengers is unchanged.

    Only rows `_assign_section` calls `matches` survive: the same query also
    lands hundreds of markets ABOUT a match ("… : Total Sets O/U 3.5"), and a
    rail that showed those under "MATCHES" would have swapped one false heading
    for another.

    ── Why this is two reads and not one join ──

    Written first as a single joined query, measured on production, and rewritten
    — the join cost **5.2s** against `build_league`'s 729ms on the same scope,
    which is not a price a hub rebuild can pay. Two separate causes, both
    measured with EXPLAIN (ANALYZE, BUFFERS) on 2026-09-05:

    1. Spelling `event_id IS NOT NULL` in SQL made the planner AND in the whole
       588,398-row `ix_futures_markets_event_id` bitmap: **1.23s** to express a
       predicate that costs nothing in Python over rows already fetched.
    2. The join drove one `events_pkey` probe per MARKET (611 of them) where the
       distinct event count is 240 — and `events` is currently 437% dead tuples
       (1,015,682 dead against 231,980 live), so a single-row pkey lookup reads
       ~400 buffers instead of ~4. Deduplicating the event ids and reading them
       in one set-based statement removes 60% of the probes.

    The bloat is a production database problem, not this rail's, and it is filed
    as its own issue — but it is the reason this function is shaped defensively
    rather than as the obvious join. Net: ~1.4s, behind the hub's 180s cache and
    background refresh.
    """
    now = now or datetime.now(timezone.utc)

    filters = _league_scope_filters(sport_key, now, also_sport_keys=also_sport_keys)
    # NB: no `event_id IS NOT NULL` here — see the docstring. Filtered in Python.
    filters.append(
        or_(
            FuturesMarket.market_tier.is_(None),
            FuturesMarket.market_tier.notin_(_NON_MATCH_TIERS),
        )
    )

    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*filters)
        # One MORE than the cap, so the truncation test below can tell "exactly
        # full" from "overflowed" — see LINKED_MATCH_POOL_LIMIT.
        .limit(LINKED_MATCH_POOL_LIMIT + 1)
    )

    try:
        result = await asyncio.wait_for(db.execute(query), timeout=15)
    except asyncio.TimeoutError:
        # The hub is a composition: losing this rail must not cost the page its
        # futures sections. `build_hub` records the typed loss.
        logger.warning("linked matches timed out for %s", sport_key)
        raise

    pool = list(result.scalars().unique().all())
    if len(pool) > LINKED_MATCH_POOL_LIMIT:
        # The pool outgrew its cap. Which rows survive is undefined — the query
        # has no ORDER BY — so this can drop an entire tour from a hub that spans
        # two, without changing anything a reader could point at. Say so.
        logger.warning(
            "linked match pool truncated for %s (+%s): read %s rows at cap %s; "
            "rows beyond the cap are arbitrary and a whole league can vanish",
            sport_key,
            ",".join(also_sport_keys) or "-",
            len(pool),
            LINKED_MATCH_POOL_LIMIT,
        )
        pool = pool[:LINKED_MATCH_POOL_LIMIT]

    candidates = [
        m
        for m in pool
        if m.event_id is not None and _assign_section(m, sport_key) == "matches"
    ]
    if not candidates:
        return []

    # One set-based read of the distinct events, then the currency test in
    # Python. `status` alone is not enough (a stale `scheduled` row outlives the
    # match it describes), and the clock alone is not enough (a `completed`
    # event inside the window is still over), so both are applied.
    event_rows = await asyncio.wait_for(
        db.execute(
            select(Event.id, Event.commence_time, Event.status).where(
                Event.id.in_({m.event_id for m in candidates})
            )
        ),
        timeout=15,
    )
    playable: dict[int, tuple] = {}
    floor = now - LINKED_MATCH_LOOKBACK
    for event_id, commence_time, raw_status in event_rows.all():
        # Repairing CERT-1987. This was `raw_status != "completed"` — a DENYLIST,
        # which admitted every status nobody had thought of. `closed` is the
        # dominant terminal state on production (212,289 rows against 15,731
        # `completed`) and is what a definitive StatPal completion writes, so the
        # rail was rejecting the rare ending and admitting the common one. The
        # retirement markers `voided` and `merged` walked through too.
        #
        # `served_event_status` first, so a row claiming `live` before its own
        # start time is read as `scheduled` and has to clear the floor like any
        # other future match (the #1779 class this module exists for) instead of
        # bypassing it and leading the rail.
        status = served_event_status(raw_status, commence_time, now)
        if not event_is_playable(status):
            continue
        if status != "live" and (commence_time is None or commence_time < floor):
            continue
        playable[event_id] = (commence_time, status)

    if not playable:
        return []

    # Live first, then the tournament the reader came for, then soonest — the
    # order a person watching a tournament reads the rail in. In Python because
    # the currency test it sorts on is.
    #
    # ── #3640, the ordering half: why the middle key exists ──
    #
    # Measured on production 2026-09-06 at 19:45Z, mid-US-Open: eight of the
    # nineteen cards on `/hub/tennis` were ATP Challenger matches, and they held
    # rail positions 2 and 4–10 — above Swiatek–Zheng at 11, Osaka–Rybakina at
    # 12, Khachanov at 16 and Zverev at 17. Nothing had gone wrong: the
    # Challengers at Phan Thiet and Shanghai start at 06:00–07:10Z and the US
    # Open singles at 15:00Z, so pure soonest-first is doing exactly what it
    # says. It is the RULE that is wrong. A reader who opens the tennis page
    # during a Slam came for the Slam, and a clock is not a reason to bury it.
    #
    # ── and why it sorts INSIDE the live band, not above it ──
    #
    # The outer key is untouched, so a Challenger that is ON COURT still leads a
    # Slam match that has not started. That is the deliberate half of this
    # change: "what is on now" stays the rail's first promise, and the one case
    # it costs — a live Challenger above a Slam two hours out — is rarer, and
    # less wrong, than a not-yet-started match displacing a live one. On the
    # measured population it costs nothing at all: both live rows were US Open
    # doubles and every Challenger was scheduled.
    #
    # A rank key, never a filter: a rail of nothing BUT Challengers is still a
    # full rail in its own chronological order. `is_undercard=None` — every
    # non-hub caller, including `/api/leagues/tennis_atp`, which is a TOUR page
    # where a Challenger is on topic — is byte-identical to the prior ordering.
    candidates = [m for m in candidates if m.event_id in playable]
    candidates.sort(
        key=lambda m: (
            0 if playable[m.event_id][1] == "live" else 1,
            _rail_tier(m, is_undercard),
            playable[m.event_id][0],
        )
    )

    # ── UX-P181 (#2167): ONE card per event ──
    #
    # The name dedup below cannot see this pair, because the two venues do not
    # spell the match the same way: Kalshi's "Zverev vs Tabilo" and Polymarket's
    # "US Open ATP: Alexander Zverev vs Alejandro Tabilo" normalise differently.
    # But we are not being asked to GUESS that they are one match — the matcher
    # already decided it and wrote the answer down, and both rows carry
    # `event_id = 15304537`. Printing them as two cards contradicts an identity
    # this row already holds, and contradicts it visibly: measured on production
    # 2026-09-05 the rail showed Zverev at 97% and, one card later, at 96%. The
    # blend is the product — one number per question.
    #
    # This is deliberately NOT the open cross-source identity problem (#2166).
    # It resolves only pairs the database already calls one event; two markets
    # linked to two DIFFERENT event rows are a twin, which is matching's to fix
    # (#2693) and stays visible here rather than being papered over.
    #
    # #3640 adds the prop key to that rank. Same principle one step out: the
    # `event_id` already decides WHICH match this is, and electing a prop to
    # speak for it hands the row to the caller's prop split, which then removes
    # the match. Nine live-or-today US Open singles, Alcaraz among them, left
    # `/hub/tennis` this way on 2026-09-06.
    chosen: dict[int, FuturesMarket] = {}
    for market in candidates:
        current = chosen.get(market.event_id)
        if current is None or _match_card_rank(market, is_prop) > _match_card_rank(
            current, is_prop
        ):
            chosen[market.event_id] = market
    # Filtered rather than rebuilt from `chosen.values()`, so the live-first /
    # soonest-first order established above survives the dedup.
    candidates = [m for m in candidates if chosen[m.event_id] is m]

    rows: list[dict] = []
    # Same name-normalising dedup `build_league` applies, for the same reason and
    # by the same rule (keep the row with the most outcomes). Measured on
    # production 2026-09-05 the raw rail listed "US Open ATP: Ben Shelton vs
    # Stefanos Tsitsipas" twice and the live Bergs match three times.
    by_name: dict[str, dict] = {}
    for market in candidates:
        if len(rows) >= LINKED_MATCH_LIMIT:
            break
        sorted_outcomes = _sorted_outcomes(market)
        if _effectively_resolved(sorted_outcomes):
            continue
        dedup_key = _normalize_futures_dedup_key(market)
        prior = by_name.get(dedup_key)
        if prior is not None:
            if len(sorted_outcomes[:10]) <= len(prior["top_outcomes"]):
                continue
            rows = [r for r in rows if r["id"] != prior["id"]]
        row = {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "external_id": market.external_id,
            "market_tier": market.market_tier,
            "category": market.category,
            "resolution_date": (
                market.resolution_date.isoformat()
                if market.resolution_date
                else None
            ),
            "outcome_count": len(market.outcomes),
            "top_outcomes": _serialize_outcomes(sorted_outcomes, market),
            "canonical_market_key": market.canonical_market_key,
            "group_id": market.group_id,
            "section": "matches",
            "competition": _market_competition(market),
        }
        by_name[dedup_key] = row
        rows.append(row)
    return rows
