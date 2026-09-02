"""
Prediction market → Event matching task.

Periodically scans futures_markets from Kalshi and Polymarket to:
1. Detect game-level binary markets (moneyline-style outcomes)
2. Match them to Event records by team name + commence_time
3. Auto-create Event records when The Odds API doesn't cover a sport (e.g., Olympics)
4. Write win_prob_snapshots so they appear as trend lines on OddsChart

Runs after Kalshi (:45) and Polymarket (:15) polling to pick up fresh data.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, and_, func, delete, case, update, text
from sqlalchemy.orm import joinedload

from app.tasks.base import get_task_session
from app.utils.event_completion import (
    TICKER_DERIVED_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)
from app.utils.sport_keys import is_kalshi_shadowed_futures_ticker
from app.utils.prediction_market_matching import (
    is_game_level_market,
    _KALSHI_GAME_TICKER_PREFIXES,
    get_sport_prefix_from_ticker,
    _TICKER_TO_SPORT_PREFIX,
    extract_matchup,
    extract_matchup_with_ticker_fallback,
    extract_teams_from_ticker,
    extract_game_date_from_ticker,
    extract_ticker_fragments,
    _score_fragment_match,
    match_teams_to_event,
    find_moneyline_outcome,
    feeds_win_prob_blend,
    is_combat_fight_ticker,
    is_kalshi_match_segment_ticker,
    _fuzzy_team_match,
    _expand_team_search_terms,
    _SPORT_CATEGORY_TO_KEY_PREFIX,
    MAX_TIME_DELTA,
    MAX_PAST_GAME_DELTA,
)
from app.utils.live_blend import (
    MarketOutcomes as _LiveBlendGroup,
    compute_source_home_probability as _compute_source_home_probability,
    select_primary_market as _select_primary_market,
)

logger = logging.getLogger(__name__)

# #195: how far ahead of commence the live poller pins THE SCRIPT pregame mark.
# The poll already covers scheduled events within +3h; the mark is captured only
# in the final window before (or after) commence so it reflects the settled
# pregame consensus rather than a stale hours-out price.
_PREGAME_MARK_LEAD_MINUTES = 15


@dataclass(frozen=True)
class _LinkedMarketRef:
    """Scalar copy of a linked market/event row.

    Phase 2 commits and rolls back per market. SQLAlchemy expires ORM instances
    on rollback, and reading an expired async ORM attribute can raise
    MissingGreenlet. Keep only scalar values in the long-running Phase 2 loop.
    """

    market_id: int
    source: str
    external_id: str | None
    name: str
    event_id: int
    event_commence_time: datetime | None
    home_team_name: str | None
    away_team_name: str | None

    @property
    def is_game_winner(self) -> bool:
        # A5 (#1024): a two-sided winner line — team-sport …game OR a combat
        # fight winner (kxufcfight/kxboxing) — so the fight-winner is preferred
        # over its card's props when picking the group's primary market.
        return feeds_win_prob_blend(self.external_id)


def _derive_sport_category(external_id: str | None) -> str | None:
    """Derive llm_sport_category from a Kalshi ticker's sport key.

    Maps ticker → sport_key → LLM category prefix. Returns None for
    non-Kalshi or unparseable tickers.
    """
    if not external_id:
        return None
    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY
    sport_key = get_sport_prefix_from_ticker(external_id)
    if not sport_key:
        return None
    prefix = sport_key.split("_")[0]
    return SPORT_PREFIX_TO_LLM_CATEGORY.get(prefix)


def _set_market_sport_fields(market, matched_event: dict) -> None:
    """Propagate sport_id and fix llm_sport_category on a newly linked market."""
    if matched_event.get("sport_id"):
        market.sport_id = matched_event["sport_id"]
    ticker_category = _derive_sport_category(market.external_id)
    if ticker_category and market.llm_sport_category != ticker_category:
        market.llm_sport_category = ticker_category


async def _register_market_team_identities(session, event_id, matchup, market):
    """Register team identities after a successful market→event link.

    When a prediction market is linked to an event, we know the team names
    from both sources. Register these mappings so future lookups are instant.
    """
    from app.models.models import Event
    from app.services.team_identity import team_identity_service

    # Must eager-load sport to avoid lazy-load in async context
    event_result = await session.execute(
        select(Event)
        .options(joinedload(Event.sport))
        .where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    if not event or not event.sport:
        return

    sport_key = event.sport.key if event.sport else ""
    source = market.source  # "kalshi" or "polymarket"

    # Register the event's team names with the identity service
    if event.home_team_id and event.home_team_name:
        await team_identity_service.register_team_identity(
            session, event.home_team_id, source, sport_key,
            source_name=matchup.team_a if matchup else event.home_team_name,
        )
    if event.away_team_id and event.away_team_name:
        await team_identity_service.register_team_identity(
            session, event.away_team_id, source, sport_key,
            source_name=matchup.team_b if matchup else event.away_team_name,
        )

# ── Duplicate linkage guard ──────────────────────────────────────────────────
# Prevents multiple Kalshi game markets from DIFFERENT games being linked to
# the same event. This is the root cause of sawtooth oscillation: e.g.,
# "Washington vs Loyola Marymount Game 1" and "Game 2" both linked to one
# event, producing alternating probabilities in win_prob_snapshots.


def _is_game_winner_kalshi_prefix(prefix: str) -> bool:
    """A Kalshi ticker prefix whose per-market granularity is a single game or
    esports map — the level at which two DIFFERENT-dated markets sharing one
    event signal a wrong-game linkage.

    Covers traditional ``…game`` prefixes (kxnbagame, kxncaambgame, …) plus
    esports per-map winners (kxcs2map, kxlolmap, kxvalorantmap, and the
    explicit kxcs2mapwinner). The plural ``…maps`` total-count props
    (kxcs2totalmaps, kxloltotalmaps) are over/under props, NOT per-game
    markers, and are correctly excluded — ``endswith("map")`` does not match
    ``…maps`` (#210 Item 1b: the old ``endswith("game")`` gate silently
    exempted every esports map ticker from the duplicate-linkage guard).
    """
    return (
        prefix.endswith("game")
        or prefix.endswith("map")
        or prefix.endswith("mapwinner")
    )


# Kalshi game/map WINNER ticker prefixes — the per-match granularity at which a
# different-dated ticker sharing one event means a DIFFERENT game (not a prop of
# the same game). Props (spread/total/mention/totalmaps) legitimately share the
# game's date and must never be date-unlinked, so they are intentionally absent.
# #210 Item 1e adds NCAAMB / college basketball (same-day doubleheaders) and
# esports (teamless tournament-dump different-day matches). Combat prefixes are
# absent by design — their date-only tickers legitimately sit up to ~28h off
# (gotcha #14).
WRONG_GAME_PREFIXES = frozenset({
    # Traditional single-game sports
    "kxnbagame", "kxnhlgame", "kxmlbgame", "kxnflgame",
    "kxwnbagame", "kxmlsgame", "kxsoccergame", "kxsocgame",
    # College basketball (NCAAMB + siblings) — same-day doubleheaders
    "kxncaambgame", "kxncaabbgame", "kxncaabgame", "kxncaawbgame",
    # Esports game/map winners — teamless tournament-dump wrong-games
    "kxcs2game", "kxcs2map", "kxcs2mapwinner",
    "kxlolgame", "kxlolmap",
    "kxvalorantgame", "kxvalorantmap",
})


# ── DELETED (Q439, #2214): _ticker_date_far_from_event ───────────────────────
# It answered "is this ticker's game the same game as this event?" by comparing
# the ticker's wall clock to the event's UTC commence AS IF THE TICKER WERE UTC.
# It is not — a Kalshi game ticker embeds the game's US EASTERN date and start
# time, which the block below already says, in this file, with the measurement
# attached. #1811 corrected the arm that DECIDES A LINK
# (_ticker_date_conflicts_with_event) and left the two arms that DECIDE AN
# UNLINK on the uncorrected helper, so the same module answered one question
# two ways and the inverse operation won.
#
# What that cost, measured on production 2026-08-29 — the day this was deleted:
#   * 44 of 44 open KXMLBGAME rows unlinked. Every one had a real event, and
#     every one was 4h (EDT) outside a ±3h window centred on the wrong instant.
#   * 45 of 48 MLB games commencing within 36h carried no `kalshi` key in
#     `win_probability_sources` — the game card showed no Kalshi price.
#   * 44 of 44 open KXMLSGAME rows unlinked on the date-only arm: a midnight-
#     anchored ticker sits ~24h from an evening kickoff's UTC commence, which
#     the old ±18h rule called a different game.
# The link-rate metric did not show it, because the settled backfill re-links
# these rows once the game is over. The gap was only ever visible while the
# game was worth watching.
#
# There is now ONE decider: _ticker_date_conflicts_with_event. Its ±3h HHMM
# tolerance is unchanged and is still the number the ESPN identity rail
# (app/utils/espn_candidate_selection) pins itself to; only the instant the
# tolerance is measured FROM has moved.


# ── #1811: ticker-date vs CANDIDATE-EVENT date ───────────────────────────────
# Until #1811 the duplicate-linkage guard date-checked a candidate link only
# when the ticker prefix passed _is_game_winner_kalshi_prefix. Totals, spreads,
# period markets (F3/F5/F7) and props were skipped by design.
#
# THE SHARPEST FACT: the guard protected exactly the markets the venue (Kalshi)
# grades and settles itself, and skipped exactly the markets we grade from our
# own `events` scores — the inverse of where protection was needed. Measured on
# production 2026-08-12: of 21,085 linked MLB Kalshi markets carrying a ticker
# date, 5,142 (24.4%) across 540 events had ticker date != linked event date,
# and 2,097 outcomes across 167 markets had been graded from our own scores
# against the WRONG GAME.
#
# That 5,142 / 540 is an EASTERN-calendar-day count and is the acceptance
# baseline — do not "correct" it to UTC. Whole population, production
# 2026-08-12: 21,386 linked MLB Kalshi markets carry a parseable ticker date;
# 8,158 markets / 736 events disagree on the UTC day, 5,142 markets / 540
# events disagree on the EASTERN day. The UTC reading is the inflated one (by
# ~3,000 — that surplus IS evening rollover, see below).
#
# Fable's ruling (2026-08-13, under rulings 031/036): the provider's ticker
# defines the market's referent. Where ticker and event link disagree, the LINK
# is wrong. So the date guard now covers EVERY Kalshi ticker class that carries
# a parseable ticker date, not just game winners.
#
# ── Why the ticker's clock must be converted before it is compared ───────────
# Q439 (#2214): what follows was written to explain why this arm did not reuse
# `_ticker_date_far_from_event`. That helper is now DELETED, because the two
# unlink arms it still drove were the reason MLB never carried a live Kalshi
# price — this paragraph named the bug and the codebase kept it anyway. The
# measurement below is unchanged and is now the ONE rule.
#
# The retired helper compared the ticker's wall clock to the event's UTC
# commence as if the ticker were UTC. It is not: a Kalshi game ticker embeds the
# game's US EASTERN date and start time. MEASURED (1,000-row systematic sample of linked
# MLB Kalshi markets, production, 2026-08-12):
#   * ticker HHMM read as UTC  → modal delta is -4h (i.e. OUTSIDE the ±3h
#     window); the helper's rule would refuse 98.0% of currently-linked MLB
#     markets, and 91.2% across all sports.
#   * ticker HHMM read as US/Eastern → 744/1000 land at EXACTLY 0h, and the
#     rule refuses 24.7% — which reproduces the issue's independently measured
#     24.4% almost exactly.
# So this arm keeps the SAME ±3h tolerance, applied after the timezone is
# corrected. For date-only tickers it compares EASTERN CALENDAR DAYS instead of
# a ±18h window, because ±18h around a midnight-ET anchor wrongly excludes
# every evening game: a 10pm ET start is 02:00 UTC the NEXT day, so a date-only
# ticker and the event's UTC commence sit ~22h apart while naming the same
# game. (This rollover is what inflates the UTC-day census above; it is not a
# claim about the issue's ET-day baseline, which is correct as published.)
_EVENT_DATE_MAX_DIFF_HOURS = 3
# Date-only tickers: refuse only at >=2 Eastern days apart. Eastern is a
# US-VENUE proxy, not the event's own local zone, so an international match
# (ITF/ATP/esports) can legitimately sit one ET day off its ticker. Refusing at
# >=1 would drop those real links; the #1811 long tail is -19d..-80d, far
# outside this band, so nothing that matters is lost by being generous here.
_EVENT_DATE_MAX_DIFF_DAYS = 2

# ── Esports carry a WIDER HHMM window, and here is why (measured) ────────────
# Esports events are almost never scheduled by an upstream schedule provider —
# they are auto-created FROM the prediction market itself
# (_create_event_from_prediction_market), so their commence_time is roughly
# "when we first scraped the market", not a start time. MEASURED, production
# 2026-08-12, the 120 most recent esports events (381 linked markets):
#   * 114/119 events (96%) have a commence_time with NONZERO SECONDS — the
#     ingest-timestamp signature. Real schedule times land on the minute.
#   * 113/119 events are COHERENT: every Kalshi market on the event shares one
#     ticker date-token AND one team-code, i.e. there is only one match on the
#     event and no sibling it could be mislinked to. The 3–12h disagreements
#     sit on these coherent events, so they measure OUR scrape latency, not a
#     referent conflict. Refusing them would have the guard deny a market the
#     link to the very event that market created.
#
# NOTE — a plausible-sounding theory that the data REFUTES: "map 2 of a
# best-of-N legitimately starts hours after the series". It does not show up in
# the ticker. KXVALORANTMAP-26JUL311400THGX-1 and -2 carry the IDENTICAL
# date-token; the map number is a suffix. The series winner
# (KXVALORANTGAME-26JUL311400THGX) sits at the same delta as its maps — which
# is also why this widening keys on the esports FAMILY, not on a "…map" suffix.
#
# Where the cliff goes, from the distribution and not from taste. All-time
# systematic sample of linked kxcs2/kxlol/kxvalorant markets (n=865 with HHMM),
# ET-normalised signed delta (ticker − commence):
#   -8h:7  -7h:7  -6h:10  -5h:21  -4h:32  -3h:69  -2h:96  -1h:47  0h:13
#   +1h:8  +2h:8  +3h:3  +4h:2  +5h:3  +6h:4  +7h:1  +8h:1  +9h:2
#   ...then NOTHING until +17h:2 +19h:2 +20h:1 +21h:2 +22h:2 +23h:1 +38h:1,
#   -12h:2 -14h:3 -15h:1 -19h:1 -21h:1 -23h:1 -27h:1 -30h:2 -31h:1 -33h:1
#   -48h:16 -52h:1, and 489 beyond ±60h.
# There is a real gap between roughly +9h and +17h. Cliff sweep (refusal rate):
#   3h → 71.8%   6h → 63.5%   8h → 61.6%   10h → 61.4%
#   12h → 61.2%  14h → 60.8%  18h → 60.5%  24h → 59.2%
# The curve falls steeply to ~10–12h and is flat after: 3h→12h recovers 92
# markets (10.6% of the sample), 12h→24h recovers only 17 more. So 12h sits in
# the gap, admits the whole near cluster, and still refuses the 489+ beyond
# ±60h tournament-dump population that WRONG_GAME_PREFIXES exists to catch.
# The date-only rule is UNCHANGED for esports (>=2 Eastern days).
_ESPORTS_TICKER_PREFIXES = ("kxcs2", "kxlol", "kxvalorant")
_ESPORTS_EVENT_DATE_MAX_DIFF_HOURS = 12

try:  # pragma: no cover - exercised implicitly; only the absence path is dead
    from zoneinfo import ZoneInfo as _ZoneInfo

    _KALSHI_TICKER_TZ = _ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - no tzdata on the platform
    _KALSHI_TICKER_TZ = None
    logger.warning(
        "zoneinfo America/New_York unavailable — the #1811 ticker-vs-event date "
        "guard will fail OPEN (no refusals) rather than refuse real links."
    )

# Refusal reasons from _check_duplicate_kalshi_linkage_reason. Distinct so a
# production run can report WHICH mechanism fired (see the funnel keys at the
# three call sites).
_REFUSAL_EVENT_DATE = "event_date"      # (a) #1811: ticker date vs the event
_REFUSAL_SIBLING_DATE = "sibling_date"  # (b) pre-existing: vs a sibling ticker


def _is_combat_kalshi_prefix(prefix: str) -> bool:
    """True for ANY UFC/boxing Kalshi ticker — the bout winner AND its card
    props (method of finish, rounds, distance, victory round, …).

    Deliberately broader than ``is_combat_fight_ticker`` (fight-WINNER prefixes
    only), because the widened #1811 guard now covers props too and every
    ticker on a combat card shares the card's date-only token. Combat is
    EXEMPT from date-unlinking by design: those date-only tickers legitimately
    sit up to ~28h from the event's UTC commence (gotcha #14 — Kalshi's
    close-time is not the start time), and fights are disambiguated by fighter
    names, not dates.
    """
    return prefix.startswith("kxufc") or prefix.startswith("kxboxing")


def _event_date_max_diff_hours(prefix: str) -> int:
    """The HHMM tolerance for a ticker class, in hours.

    Per-class, not a carve-out: an esports event's commence_time is an ingest
    stamp rather than a schedule time (see the measurement above), so the
    honest window for that class is wider. Everything else keeps ±3h.
    """
    if prefix.startswith(_ESPORTS_TICKER_PREFIXES):
        return _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS
    return _EVENT_DATE_MAX_DIFF_HOURS


def ticker_start_utc(ticker_date):
    """The real UTC instant a Kalshi ticker's HHMM names, or None.

    ``extract_game_date_from_ticker`` returns the ticker's wall clock stamped
    with ``tzinfo=UTC`` — a carrier, not a claim. The clock is US EASTERN. This
    is the ONE place that conversion happens, so a caller cannot half-apply it.

    Returns None when there is nothing to convert: no ticker date, a date-only
    ticker (midnight — there is no start time to place), or no tz database. A
    None means "no instant available", never "midnight UTC".
    """
    if not ticker_date or _KALSHI_TICKER_TZ is None:
        return None
    if not (ticker_date.hour or ticker_date.minute):
        return None  # date-only: compare Eastern CALENDAR DAYS instead
    return (
        ticker_date.replace(tzinfo=None)
        .replace(tzinfo=_KALSHI_TICKER_TZ)
        .astimezone(timezone.utc)
    )


def _ticker_date_conflicts_with_event(
    ticker_date, event_commence, prefix: str = "",
) -> bool:
    """True when a Kalshi ticker's embedded game date/time cannot be the same
    game as the candidate event's ``commence_time``.

    Timezone-corrected (see the block comment above): the ticker's wall clock
    is US Eastern. When the ticker carries HHMM the window is ±3h, widened to
    ±12h for the esports family (``prefix``); when it is date-only the rule is
    >=2 Eastern calendar days for every class. Returns False whenever there is
    no signal — a missing ticker date, a missing/NULL commence_time, or no tz
    database — because a guard that over-refuses silently drops real markets.
    """
    if not ticker_date or not event_commence or _KALSHI_TICKER_TZ is None:
        return False

    ec = (
        event_commence if event_commence.tzinfo
        else event_commence.replace(tzinfo=timezone.utc)
    )
    # extract_game_date_from_ticker returns midnight for a date-only ticker, so
    # `ticker_start_utc` returning None IS the has-HHMM test. A literal 00:00
    # start would read as date-only and fall to the LOOSER rule — it fails open,
    # which is the safe direction.
    naive = ticker_date.replace(tzinfo=None)
    start_utc = ticker_start_utc(ticker_date)

    if start_utc is not None:
        diff_hours = abs((start_utc - ec).total_seconds()) / 3600
        return diff_hours > _event_date_max_diff_hours(prefix)

    day_delta = abs((naive.date() - ec.astimezone(_KALSHI_TICKER_TZ).date()).days)
    return day_delta >= _EVENT_DATE_MAX_DIFF_DAYS


async def _event_commence_time(session, event_id: int):
    """The candidate event's ``commence_time``, or None when there is no usable
    value. Anything that is not a datetime (NULL column, absent row) is NO
    SIGNAL and must leave the guard failing open."""
    from app.models.models import Event

    result = await session.execute(
        select(Event.commence_time).where(Event.id == event_id)
    )
    value = result.scalar_one_or_none()
    return value if isinstance(value, datetime) else None


async def _check_duplicate_kalshi_linkage_reason(
    session, event_id: int, market, ticker_game_date,
) -> str | None:
    """Why linking this Kalshi market to ``event_id`` must be refused, if it must.

    Returns None to PROCEED, or one of ``_REFUSAL_EVENT_DATE`` /
    ``_REFUSAL_SIBLING_DATE`` to SKIP.

    Two independent comparisons, both live here:

      (a) #1811 — this market's TICKER DATE vs the CANDIDATE EVENT's
          commence_time. Applies to every Kalshi ticker class with a parseable
          date (totals, spreads, F3/F5/F7 periods, props), because a mis-linked
          totals market typically sits on an otherwise-healthy event with no
          game-winner sibling to compare against. Combat is exempt entirely;
          esports gets a wider (±12h) window, both for measured reasons stated
          above the constants.

      (b) pre-existing — this market's ticker date vs an EXISTING SIBLING Kalshi
          market's ticker date on the same event. Still scoped to game/map
          WINNER prefixes on both sides, unchanged.
    """
    from app.models.models import FuturesMarket

    if market.source != "kalshi":
        return None  # Only guard Kalshi markets

    ext = (market.external_id or "").lower()
    prefix = ext.split("-")[0] if "-" in ext else ext

    # ── (a) #1811: ticker date vs the candidate event ────────────────────────
    # Derive the ticker date defensively: a caller that passes None must not
    # silently disable the guard.
    td = ticker_game_date or extract_game_date_from_ticker(market.external_id)
    if td is not None and not _is_combat_kalshi_prefix(prefix):
        event_commence = await _event_commence_time(session, event_id)
        if _ticker_date_conflicts_with_event(td, event_commence, prefix):
            logger.warning(
                "Event-date linkage blocked (#1811): %s ticker=%s would link to "
                "event %d (commence=%s) — the ticker defines the referent, so "
                "the link is wrong",
                market.external_id, td.isoformat(), event_id,
                event_commence.isoformat() if event_commence else None,
            )
            return _REFUSAL_EVENT_DATE

    # ── (b) pre-existing sibling comparison ──────────────────────────────────
    if not _is_game_winner_kalshi_prefix(prefix):
        return None  # Only guard game/map-level markets

    # Find existing Kalshi game markets already linked to this event
    existing_result = await session.execute(
        select(FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.name)
        .where(
            FuturesMarket.event_id == event_id,
            FuturesMarket.source == "kalshi",
            FuturesMarket.id != market.id,
        )
    )
    existing = existing_result.all()
    if not existing:
        return None  # No existing Kalshi markets — safe to link

    # Check if any existing market is a game market with a different date
    for row in existing:
        existing_ext = (row.external_id or "").lower()
        existing_prefix = existing_ext.split("-")[0] if "-" in existing_ext else existing_ext
        if not _is_game_winner_kalshi_prefix(existing_prefix):
            continue  # Skip non-game markets (props, totals, etc.)

        # Both are game markets — compare ticker dates
        existing_date = extract_game_date_from_ticker(row.external_id)
        if ticker_game_date and existing_date:
            # If dates differ by more than 4 hours, these are different games
            td1 = ticker_game_date if ticker_game_date.tzinfo else ticker_game_date.replace(tzinfo=timezone.utc)
            td2 = existing_date if existing_date.tzinfo else existing_date.replace(tzinfo=timezone.utc)
            if abs((td1 - td2).total_seconds()) > 4 * 3600:
                logger.warning(
                    "Duplicate linkage blocked: market %s (date=%s) vs existing market %d '%s' (date=%s) on event %d",
                    market.external_id, td1.date(), row.id, row.external_id, td2.date(), event_id,
                )
                return _REFUSAL_SIBLING_DATE  # Different game — do NOT link

        # Same date or unparseable — compare full tickers.
        # If external_ids are different but same prefix, they might be
        # different games on the same day (Game 1 vs Game 2 in a tournament).
        # The ticker suffix after the date encodes teams, so if tickers differ
        # significantly, it's a different matchup or game number.
        if market.external_id and row.external_id:
            if market.external_id.lower() == row.external_id.lower():
                continue  # Same market (duplicate) — safe
            # Different tickers — could be dual market (Team A win? + Team B win?)
            # or truly different games. Dual markets have the same date+teams portion
            # but that's already handled by the devig averaging. For safety, allow
            # the link — the Phase 2 devig logic will handle dual markets correctly.

    return None  # No conflicts detected


def _kalshi_prefix(external_id) -> str:
    ext = (external_id or "").lower()
    return ext.split("-")[0] if "-" in ext else ext


def auto_create_commence_time(market, fallback):
    """The commence_time an auto-created event should carry, and its source.

    Returns ``(commence_time, commence_time_source_or_None)``. Pure: no DB, no
    clock — ``fallback`` is what the caller already computed from
    ``market.commence_time``/``now``.

    #2020. Gotcha #14 states it plainly: **a Kalshi market's ``commence_time`` is
    often its RESOLUTION/CLOSE time, not the game start.** The standing Fable
    ruling above ``_EVENT_DATE_MAX_DIFF_HOURS`` says the same thing from the other
    side — *the provider's ticker defines the market's referent* — which is why
    the whole linkage guard is written against the TICKER date and not against
    this field.

    So writing ``market.commence_time`` onto a row we create contradicts the only
    referent the rest of this module trusts. Measured specimen, production
    2026-08-20: ``KXLOLGAME-26AUG210500GAMTSW`` carries ticker time
    ``2026-08-21 05:00Z`` and ``market.commence_time`` ``2026-08-23 09:00Z`` —
    **two days apart**, and every event auto-created from it was stamped with the
    close time. Prefer the ticker; fall back when there is no parseable one
    (Polymarket has no ticker at all, so it always falls back).

    Deliberately NARROW: the ticker time is used **only when the fallback
    actually disagrees with it**, i.e. only where the loop exists. A market whose
    `commence_time` already agrees with its ticker is the healthy majority and is
    left exactly as it was — a fix for a runaway must not quietly re-time every
    event it passes on the way. (Date-only tickers resolve to midnight, which is
    coarser than a close time that happens to be right; that trade is only worth
    taking on rows that would otherwise re-create themselves forever.)
    """
    ticker_time = extract_game_date_from_ticker(getattr(market, "external_id", None))
    if ticker_time is None:
        return fallback, None
    if not auto_create_self_refutes(market, fallback):
        return fallback, None  # already coherent — change nothing
    return ticker_time, TICKER_DERIVED_COMMENCE_SOURCE


def auto_create_status(commence_time, commence_time_source, now) -> str:
    """The status an auto-created row should be BORN in. Pure: no DB.

    q076, and this is the OTHER DOOR into the frozen-final-score class.
    ``espn_sync._transition_event_statuses_impl`` promoting ``scheduled -> live``
    every 60s is the one everybody looks at; this line creates rows already live,
    and for a ticker-derived time it does so almost every time.

    :func:`auto_create_commence_time` returns the ticker's DATE, which has no
    time-of-day and therefore resolves to **midnight UTC**. Every auto-create
    that happens after midnight on the ticker's own day then satisfies
    ``commence_time <= now``, so the row is born ``live`` for a match played that
    AFTERNOON — and from there the staleness nets settle it at the sport's
    maximum duration with no score, exactly as if it had been promoted.

    Measured on production 2026-09-01: of every event ever stamped
    ``kalshi_ticker``, 705 are ``closed`` and **all 705 are unscored**. Refusing
    to birth this population live cannot cost a real result, because it has never
    produced one.

    The predicate is shared with the promotion gate rather than restated, so the
    two doors cannot drift on what counts as a start. Anything else — including a
    ``None`` source, which is most of the table — keeps the original rule
    untouched.
    """
    if not commence_time_is_a_reported_start(commence_time_source):
        return "scheduled"
    return "live" if commence_time <= now else "scheduled"


def auto_create_self_refutes(market, commence_time) -> bool:
    """True when creating this row would produce a link the guard must refuse.

    Pure: no DB, no clock. A TERMINATION check, not a matching rule.

    #2020, and this is the loop it closes. Measured in production 2026-08-19/20:
    one esports matchup held **297 events for one market** — a new row every ~5
    minutes for 21.5 hours — and the tagged population went 500 -> 51,673 in three
    days, bleeding ~2,400 rows/hour. The cycle is self-sustaining and every step
    of it was individually correct:

      1. the matcher finds a candidate event for the market;
      2. :func:`_check_duplicate_kalshi_linkage_reason` REFUSES the link, because
         the ticker date (``26AUG21 05:00``) disagrees with the candidate's
         ``commence_time`` (``2026-08-23 09:00Z`` — the close time, gotcha #14);
      3. :func:`_try_link_market` clears ``matched_event`` and falls through to
         the auto-create;
      4. the auto-create writes a new event carrying that same close time — so the
         guard is **guaranteed** to refuse the row we just made, on the next poll,
         for the identical reason. Go to 1.

    The create path was manufacturing rows its own guard could never accept, and
    the guard was faithfully refusing them. Neither side is wrong alone.

    This is NOT ruling 048 misfiring. 048 accepts duplicates as a *bounded* cost,
    bounded by id-keyed reconciliation. A row that re-creates itself every five
    minutes forever is not a bounded cost; it is a generator, and no drain can
    outrun it. So the bound has to go where the generation is.

    The rule: **if the row we are about to write would be refused by the very
    predicate that sent us here, the create cannot converge and must not happen.**
    Leave the market unlinked and let the funnel say so — an unlinked market is
    visible and countable; an infinite duplicate stream is only visible in
    ``count(*)``.

    Note this returns False for the fixed path, by construction: once
    :func:`auto_create_commence_time` stamps the ticker time, the created row
    agrees with its own ticker and the next poll LINKS it instead of creating.
    That is the fix; this predicate is the proof that the fix holds, and the
    backstop if the commence_time selection is ever changed back.
    """
    if getattr(market, "source", None) != "kalshi":
        return False  # only the Kalshi guard can refuse on ticker date
    ticker_time = extract_game_date_from_ticker(getattr(market, "external_id", None))
    if ticker_time is None or commence_time is None:
        return False  # the guard cannot fire without a ticker date either
    prefix = _kalshi_prefix(getattr(market, "external_id", None))
    if _is_combat_kalshi_prefix(prefix):
        return False  # combat is exempt from the date guard entirely
    return _ticker_date_conflicts_with_event(ticker_time, commence_time, prefix)


#: How far into the past an auto-created fixture's start may be. See
#: :func:`auto_create_is_stale_fixture` for the measurement and the derivation.
AUTO_CREATE_MAX_PAST_AGE = timedelta(hours=36)


def auto_create_is_stale_fixture(commence_time, now) -> bool:
    """True when the row we are about to write would be BORN FINISHED.

    Pure: no DB. The third member of the family above, and the same shape as
    :func:`auto_create_self_refutes`: a termination check on the create, not a
    matching rule.

    #2623. Searching `Sabalenka` returned every WTA match twice — a real
    odds_api row with the score beside a surname-only Kalshi ghost with none.
    The specimen says how the ghost is made: event 15300722,
    `Sabalenka vs Bejlek`, **created 2026-09-01 22:05 for a fixture that started
    2026-08-20 04:14** — twelve days after the match was played. Kalshi's settled
    markets stay `status='open'` in our table (gotcha #33), so the matcher keeps
    finding them, and each pass mints an event for a game that finished nearly a
    fortnight ago. It is born past, the staleness net closes it, and it renders
    on `/search` as a FINAL with no score — D26's class exactly.

    ── WHY A ROW BORN FINISHED IS ALWAYS WRONG, MEASURED ──

    Production census 2026-09-01, every event stamped `kalshi` /`kalshi_ticker` /
    `polymarket` created in the preceding 14 days — **72,796 rows, and 0 of them
    carry a score.** Not "few": none. A prediction venue is not a scorer, and
    nothing downstream ever fills one in. Of those, 27,801 were already in the
    past at the moment of creation, and 18,859 were for fixtures **more than
    seven days** gone. There is no result waiting to arrive for any of them, so
    declining to create them cannot cost a single real one.

    ── WHY 36 HOURS, AND NOT 0 ──

    A create for a fixture that started an hour ago is legitimate: the match may
    still be in play, and the row is how a live Kalshi price reaches the site.
    The bound also has to clear the MIDNIGHT STAND-IN.
    :func:`auto_create_commence_time` stamps a ticker's DATE, which has no
    time-of-day and resolves to midnight UTC, so a match played at 23:00 local
    on the ticker's own day sits up to ~30 hours after its own stand-in. 36
    hours is the smallest bound that cannot refuse a fixture which might still
    be running under such a stand-in — deliberately generous, because the cost
    of refusing a real fixture is a missing game and the cost of allowing a
    stale one is a duplicate the display layer already collapses
    (`app/utils/fixture_twins.py`).

    A `None` commence_time is NOT stale. Absence is not age (gotcha #53), and
    the caller has already replaced a missing time with `now` before reaching
    here.
    """
    if commence_time is None or now is None:
        return False
    return (now - commence_time) > AUTO_CREATE_MAX_PAST_AGE


async def _check_duplicate_kalshi_linkage(
    session, event_id: int, market, ticker_game_date,
) -> bool:
    """Boolean form of :func:`_check_duplicate_kalshi_linkage_reason`.

    True to PROCEED, False to SKIP. Kept for callers that do not need to know
    WHICH mechanism refused; the three production call sites use the reason
    form so their funnel counters can distinguish (a) from (b).
    """
    reason = await _check_duplicate_kalshi_linkage_reason(
        session, event_id, market, ticker_game_date,
    )
    return reason is None


# ── Consensus inversion detection ─────────────────────────────────────────────
# Prediction market data sometimes gets stored with inverted home/away mapping
# due to outcome-order mismatches or matchup parsing errors. This threshold
# detects probable inversions by comparing against the sportsbook consensus.
# If the prediction market home_prob and (1 - home_prob) are compared to
# consensus, and the FLIPPED version is closer, we flip it.

INVERSION_THRESHOLD = 0.30  # 30% — if flipping brings it 30%+ closer to consensus

# Peer-consensus fallback (#1112): when the sportsbook consensus is ambiguous
# (~0.5) or missing — the mid-game case where the only OddsSnapshot is a stale
# pregame line — consult already-written INDEPENDENT live sources on the event.
# These sources derive from the game itself, not the prediction-market linkage,
# so they cannot share the yes_is_home orientation bug we are guarding against.
# Kalshi/polymarket are excluded: they can carry the SAME inversion.
_PEER_CONSENSUS_SOURCES = ("stat_model", "mlb", "espn", "betting")
_PEER_EXTREME_HI = 0.80
_PEER_EXTREME_LO = 0.20
_PEER_MIN_VOTES = 2  # require >=2 extreme peers agreeing before we trust them


def _peer_consensus_side(win_probability_sources: dict, exclude_source: str):
    """Return 'home' / 'away' if >=2 independent live peers are extreme and
    unanimous on a side, else None. Peers on opposite extremes cancel to None."""
    if not win_probability_sources:
        return None
    home_votes = 0
    away_votes = 0
    for ps in _PEER_CONSENSUS_SOURCES:
        if ps == exclude_source:
            continue
        # #1829: read through the shared parser. `float({"value": 0.9})` raises
        # TypeError, and the except below SWALLOWS it — so once the writers
        # started stamping, every peer would have dropped out silently,
        # `_PEER_MIN_VOTES` would never be reached, and the #1112 inversion
        # guard would have stopped firing forever with nothing in any log.
        from app.utils.aggregation import parse_source_entry
        pv, _ = parse_source_entry(win_probability_sources.get(ps))
        if pv is None:
            continue
        if pv >= _PEER_EXTREME_HI:
            home_votes += 1
        elif pv <= _PEER_EXTREME_LO:
            away_votes += 1
    if home_votes >= _PEER_MIN_VOTES and away_votes == 0:
        return "home"
    if away_votes >= _PEER_MIN_VOTES and home_votes == 0:
        return "away"
    return None


# ── #1163: source-implies-linked-market invariant ──────────────────────────
# A prediction-market source (kalshi/polymarket) may only appear in
# Event.win_probability_sources while a linked market of that source backs it.
# The two snapshot writers above only add the key for a LINKED market, but the
# unlink sites (Phase 1.5 mislink, Phase 2 wrong-game + date-mismatch) set
# event_id=None WITHOUT pruning the key — leaving a phantom blend input that the
# aggregation keeps averaging in forever (all 4 of a night's MLB games carried a
# kalshi key with ZERO backing linked kalshi markets → matured-linkage 33%).
# Only PM sources are subject to this: betting/espn/mlb/stat_model come from
# their own pollers, not from linked futures_markets, and must never be pruned.
_PM_BLEND_SOURCES = frozenset({"kalshi", "polymarket"})


def prune_blend_source(
    win_probability_sources: dict | None, source: str, remaining_linked: int
) -> tuple[dict, bool]:
    """Pure: given an event's win_probability_sources, a source, and how many
    linked markets of that source remain, return (new_wps, changed). A PM source
    with zero remaining linked markets is removed (the phantom-orphan case). A PM
    source with >=1 remaining, or any non-PM source, is left untouched."""
    wps = dict(win_probability_sources or {})
    if source not in _PM_BLEND_SOURCES:
        return wps, False
    if remaining_linked > 0:
        return wps, False
    if source not in wps:
        return wps, False
    wps.pop(source, None)
    return wps, True


async def _prune_orphaned_blend_source(
    session, event_id: int, source: str, exclude_market_id: int | None = None
) -> bool:
    """Enforce the source-implies-linked-market invariant after an unlink: if no
    linked market of ``source`` remains for ``event_id``, drop that source key
    from Event.win_probability_sources (Core SQL JSONB write, gotcha #4). No-op
    for non-PM sources. Returns True when a phantom key was pruned. #1163."""
    if source not in _PM_BLEND_SOURCES or event_id is None:
        return False
    from app.models.models import Event, FuturesMarket

    q = select(func.count(FuturesMarket.id)).where(
        FuturesMarket.event_id == event_id,
        FuturesMarket.source == source,
    )
    if exclude_market_id is not None:
        q = q.where(FuturesMarket.id != exclude_market_id)
    remaining = (await session.execute(q)).scalar() or 0

    r = await session.execute(
        select(Event.win_probability_sources).where(Event.id == event_id)
    )
    new_wps, changed = prune_blend_source(r.scalar_one_or_none(), source, remaining)
    if changed:
        await session.execute(
            update(Event).where(Event.id == event_id).values(win_probability_sources=new_wps)
        )
    return changed


async def _cleanup_orphaned_blend_sources(session, time_remaining_fn=None, limit: int = 2000) -> int:
    """Backfill/clean EXISTING phantom PM source keys — events carrying a
    kalshi/polymarket key in win_probability_sources with no linked market of
    that source (created before the prune-on-unlink guard existed). Bounded and
    idempotent so it can ride the 15-min matching task and self-heal the slate.
    Returns the number of phantom keys removed. #1163."""
    from app.models.models import Event

    pruned = 0
    for source in sorted(_PM_BLEND_SOURCES):
        # Candidate events: the source key is present AND no linked market of that
        # source exists. Raw SQL (asyncpg-safe jsonb_exists + an explicit
        # correlated NOT EXISTS — the ORM ``select().exists()`` correlation was
        # unreliable here) mirrors the existing text()/jsonb_exists pattern in
        # this file. ``:source`` is a plain text bind (no ::cast trap, gotcha #45).
        rows = (
            await session.execute(
                text(
                    "SELECT e.id, e.win_probability_sources FROM events e "
                    "WHERE jsonb_exists(e.win_probability_sources, :source) "
                    "AND NOT EXISTS (SELECT 1 FROM futures_markets fm "
                    "WHERE fm.event_id = e.id AND fm.source = :source) "
                    "LIMIT :lim"
                ),
                {"source": source, "lim": limit},
            )
        ).all()
        for eid, wps in rows:
            if time_remaining_fn is not None and time_remaining_fn() < 20:
                if pruned:
                    await session.commit()
                return pruned
            new_wps, changed = prune_blend_source(wps, source, 0)
            if changed:
                await session.execute(
                    update(Event).where(Event.id == eid).values(win_probability_sources=new_wps)
                )
                pruned += 1
    if pruned:
        await session.commit()
    return pruned


async def _check_and_fix_inversion(
    session, event_id: int, home_prob: float, source: str,
) -> float:
    """
    Compare prediction market home_prob against sportsbook consensus.
    If the probability appears inverted (flipping it brings it much closer
    to consensus), return the flipped value. Otherwise return as-is.

    This catches systematic inversions from yes_is_home mismatches,
    outcome-order bugs, and matchup parsing errors.

    Two independent checks:
      1. Sportsbook consensus (primary): flip if flipping lands far closer to
         the latest/opening OddsSnapshot line.
      2. Peer consensus (#1112 fallback): when the sportsbook line is ambiguous
         (~0.5) or missing — the mid-game stale-pregame case where check (1)
         cannot fire — flip when this source is the extreme MIRROR of >=2
         unanimous, independent live peers (stat_model/mlb/espn/betting).
    """
    from app.models.models import Event, OddsSnapshot

    event = await session.get(Event, event_id)
    if not event:
        return home_prob

    # Get sportsbook consensus: latest odds snapshot first, opening odds as fallback
    consensus = None

    # Try latest odds snapshot (most accurate for live/recent games)
    latest_snap = await session.execute(
        select(OddsSnapshot.home_win_probability)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.home_win_probability.isnot(None),
        )
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(1)
    )
    snap_prob = latest_snap.scalar_one_or_none()
    if snap_prob is not None:
        consensus = float(snap_prob)

    # Fallback to opening odds (always available, set pre-game)
    if consensus is None and event.opening_home_probability is not None:
        consensus = float(event.opening_home_probability)

    # Primary check: sportsbook consensus (only when it is reliable, i.e. extreme
    # enough to disambiguate a flip).
    if consensus is not None and 0.01 < consensus < 0.99:
        raw_diff = abs(home_prob - consensus)
        flipped = 1.0 - home_prob
        flipped_diff = abs(flipped - consensus)

        # Only flip if: (a) flipping brings it significantly closer, and
        # (b) the raw value is far enough from consensus to be suspicious
        if raw_diff > INVERSION_THRESHOLD and flipped_diff < raw_diff * 0.5:
            logger.warning(
                "Inversion detected for event %d source=%s: "
                "raw=%.3f consensus=%.3f flipped=%.3f (raw_diff=%.3f > %.2f, "
                "flipped_diff=%.3f). Using flipped value.",
                event_id, source, home_prob, consensus, flipped,
                raw_diff, INVERSION_THRESHOLD, flipped_diff,
            )
            return flipped

    # Fallback check: peer consensus (#1112). Only meaningful when THIS source is
    # itself extreme — a mirror is an extreme value on the wrong side. This never
    # fires pregame (peers are not extreme until the game decides).
    if home_prob <= _PEER_EXTREME_LO or home_prob >= _PEER_EXTREME_HI:
        peer_side = _peer_consensus_side(
            event.win_probability_sources or {}, exclude_source=source,
        )
        if peer_side == "home" and home_prob <= _PEER_EXTREME_LO:
            logger.warning(
                "Peer-consensus inversion for event %d source=%s: raw=%.3f is the "
                "mirror of >=2 unanimous home-extreme peers. Using flipped value.",
                event_id, source, home_prob,
            )
            return 1.0 - home_prob
        if peer_side == "away" and home_prob >= _PEER_EXTREME_HI:
            logger.warning(
                "Peer-consensus inversion for event %d source=%s: raw=%.3f is the "
                "mirror of >=2 unanimous away-extreme peers. Using flipped value.",
                event_id, source, home_prob,
            )
            return 1.0 - home_prob

    return home_prob


# SQL LIKE patterns for Kalshi game tickers (e.g., "kxnbagame%")
# Used to directly query game-level markets without scanning all markets.
_KALSHI_TICKER_LIKE_PATTERNS = [f"{prefix}%" for prefix in _KALSHI_GAME_TICKER_PREFIXES]


async def _try_link_market(
    session, market, matchup, matched_event, stats: dict,
    ticker_game_date, now: datetime, polymarket_backfill_queue: list,
) -> None:
    """Link a matched market to its event, or auto-create an event if needed."""
    from app.models.models import FuturesMarket

    if matched_event:
        refusal = await _check_duplicate_kalshi_linkage_reason(
            session, matched_event["event_id"], market, ticker_game_date,
        )
        if refusal:
            # Two mechanisms, two counters (#1811): "duplicate_linkage_blocked"
            # stays the SIBLING-ticker case so its history is comparable;
            # "event_date_linkage_blocked" is the widened ticker-vs-event case.
            key = (
                "event_date_linkage_blocked"
                if refusal == _REFUSAL_EVENT_DATE
                else "duplicate_linkage_blocked"
            )
            stats["funnel"].setdefault(key, 0)
            stats["funnel"][key] += 1
            matched_event = None

    if matched_event:
        market.event_id = matched_event["event_id"]
        _set_market_sport_fields(market, matched_event)
        stats["newly_linked"] += 1
        stats["funnel"]["linked"] += 1
        logger.info(
            "Linked %s market '%s' -> event %d (%s vs %s)",
            market.source, market.name, matched_event["event_id"],
            matched_event["home_team"], matched_event["away_team"],
        )
        await _register_market_team_identities(
            session, matched_event["event_id"], matchup, market,
        )
        if market.group_id and market.source == "polymarket":
            from sqlalchemy import text as _text
            await session.execute(_text("""
                UPDATE futures_markets
                SET event_id = :eid
                WHERE group_id = :gid
                  AND group_type = 'polymarket_sub_market'
                  AND (event_id IS NULL OR event_id != :eid)
            """), {"eid": matched_event["event_id"], "gid": market.group_id})
        if market.source == "polymarket":
            polymarket_backfill_queue.append(
                (market.id, matched_event["event_id"])
            )
        return

    # No existing event — try auto-creating
    if matchup and matchup.team_b:
        auto_event = await _create_event_from_prediction_market(
            session, matchup, market, now,
        )
        if auto_event:
            market.event_id = auto_event["event_id"]
            _set_market_sport_fields(market, auto_event)
            stats["newly_linked"] += 1
            stats["funnel"]["linked"] += 1
            stats["funnel"].setdefault("auto_created_events", 0)
            stats["funnel"]["auto_created_events"] += 1
            if market.source == "polymarket":
                polymarket_backfill_queue.append(
                    (market.id, auto_event["event_id"])
                )
            return

    # Record failure
    if not matchup:
        stats["funnel"]["no_matchup_extracted"] += 1
    stats["funnel"]["no_event_found"] += 1
    if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
        stats["funnel"]["sample_game_level_no_event"].append({
            "source": market.source,
            "name": market.name,
            "team_a": matchup.team_a if matchup else None,
            "team_b": matchup.team_b if matchup else None,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
            "external_id": market.external_id,
        })


async def _phase1_pass1_ticker_scan(
    session, stats: dict, now: datetime,
    polymarket_backfill_queue: list, _time_remaining,
) -> set[int]:
    """Phase 1 Pass 1: scan Kalshi markets with known game ticker patterns."""
    from app.models.models import FuturesMarket

    ticker_conditions = [
        func.lower(FuturesMarket.external_id).like(pattern)
        for pattern in _KALSHI_TICKER_LIKE_PATTERNS
    ]
    ticker_result = await session.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.event_id.is_(None),
            or_(*ticker_conditions),
        )
        .order_by(FuturesMarket.updated_at.desc())
    )
    ticker_markets = ticker_result.scalars().all()
    stats["funnel"]["ticker_scan_count"] = len(ticker_markets)

    processed_ids = set()
    for market in ticker_markets:
        if _time_remaining() < 120:
            logger.info("Phase 1 Pass 1 time budget exhausted after %d/%d ticker markets",
                        stats["markets_scanned"], len(ticker_markets))
            break
        processed_ids.add(market.id)
        stats["markets_scanned"] += 1
        stats["funnel"]["game_level_detected"] += 1

        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )

        ticker_sport = get_sport_prefix_from_ticker(market.external_id)
        if ticker_sport:
            stats["funnel"].setdefault("sport_key_extracted", 0)
            stats["funnel"]["sport_key_extracted"] += 1
        else:
            stats["funnel"].setdefault("sport_key_extraction_failed", 0)
            stats["funnel"]["sport_key_extraction_failed"] += 1

        ticker_game_date = extract_game_date_from_ticker(market.external_id)

        if matchup:
            matched_event = await _find_matching_event(
                session, matchup, market, now,
                game_date_override=ticker_game_date,
            )
            if matched_event and matchup.format_type == "ticker_parsed":
                stats["funnel"].setdefault("ticker_abbrev_linked", 0)
                stats["funnel"]["ticker_abbrev_linked"] += 1
        else:
            matched_event = await _find_event_by_sport_and_time(
                session, market, now,
                game_date_override=ticker_game_date,
            )
            if matched_event:
                stats["funnel"].setdefault("sport_time_fallback_linked", 0)
                stats["funnel"]["sport_time_fallback_linked"] += 1

        try:
            await _try_link_market(
                session, market, matchup, matched_event, stats,
                ticker_game_date, now, polymarket_backfill_queue,
            )
        except Exception as e:
            if "deadlock" in str(e).lower():
                stats["funnel"].setdefault("phase1_deadlocks", 0)
                stats["funnel"]["phase1_deadlocks"] += 1
            else:
                stats["errors"].append(f"pass1 market {market.id}: {str(e)[:100]}")
            try:
                await session.rollback()
            except Exception:
                pass

    return processed_ids


async def _phase1_pass2_general_scan(
    session, stats: dict, now: datetime, limit: int,
    processed_ids: set[int], polymarket_backfill_queue: list,
    _time_remaining,
) -> None:
    """Phase 1 Pass 2: scan non-ticker game markets (Polymarket + edge cases)."""
    from app.models.models import FuturesMarket

    _matchup_base_where = [
        FuturesMarket.source.in_(["kalshi", "polymarket"]),
        FuturesMarket.event_id.is_(None),
        FuturesMarket.status == "open",
    ]
    _matchup_name_filter = or_(
        FuturesMarket.name.ilike("% vs.%"),
        FuturesMarket.name.ilike("% vs %"),
        FuturesMarket.name.ilike("% – %"),
    )

    matchup_result = await session.execute(
        select(FuturesMarket)
        .where(*_matchup_base_where, _matchup_name_filter)
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit)
    )
    matchup_markets = matchup_result.scalars().all()

    remaining_budget = max(0, limit // 5)
    remaining_markets = []
    if remaining_budget > 0:
        remaining_result = await session.execute(
            select(FuturesMarket)
            .where(*_matchup_base_where, ~_matchup_name_filter)
            .order_by(FuturesMarket.updated_at.desc())
            .limit(remaining_budget)
        )
        remaining_markets = remaining_result.scalars().all()

    unlinked_markets = matchup_markets + remaining_markets
    stats["funnel"]["general_scan_count"] = len(unlinked_markets)
    stats["funnel"]["matchup_scan_count"] = len(matchup_markets)
    stats["funnel"]["remaining_scan_count"] = len(remaining_markets)

    for market in unlinked_markets:
        if _time_remaining() < 120:
            logger.info("Phase 1 Pass 2 time budget exhausted after %d markets scanned",
                        stats["markets_scanned"])
            break
        if market.id in processed_ids:
            continue

        stats["markets_scanned"] += 1

        if not is_game_level_market(
            market.name, market.category,
            external_id=market.external_id,
        ):
            stats["funnel"]["not_game_level"] += 1
            if len(stats["funnel"]["sample_not_game_level"]) < 10:
                stats["funnel"]["sample_not_game_level"].append(
                    {"source": market.source, "name": market.name,
                     "external_id": market.external_id}
                )
            continue

        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )
        if not matchup:
            stats["funnel"]["no_matchup_extracted"] += 1
            continue

        stats["funnel"]["game_level_detected"] += 1
        pass2_game_date = (
            extract_game_date_from_ticker(market.external_id)
            if market.source == "kalshi" else None
        )

        matched_event = await _find_matching_event(
            session, matchup, market, now,
            game_date_override=pass2_game_date,
        )

        try:
            await _try_link_market(
                session, market, matchup, matched_event, stats,
                pass2_game_date, now, polymarket_backfill_queue,
            )
        except Exception as e:
            if "deadlock" in str(e).lower():
                stats["funnel"].setdefault("phase1_deadlocks", 0)
                stats["funnel"]["phase1_deadlocks"] += 1
            else:
                stats["errors"].append(f"pass2 market {market.id}: {str(e)[:100]}")
            try:
                await session.rollback()
            except Exception:
                pass


async def _relink_collapsed_game_markets(session) -> int:
    """#944: re-link Kalshi multi-game-series GAME markets that collapsed onto
    the LAST game's event.

    Kalshi ``commence_time`` is the resolution/close date (gotcha #14), so every
    game in a series shares one commence_time and the registry's structured
    match collapses all of that series' game markets onto the last game's event
    (e.g. 7 MIN-COL ``KXNHLSPREAD`` games all linked to the single May-14 event).
    The real game date lives in the TICKER (``KXNHLSPREAD-26MAY03MINCOL`` ->
    May 3); the currently-linked event already has the correct TEAMS (right
    matchup, wrong date), so we find the event with the same team-set — either
    home/away orientation, since Kalshi ticker order differs from our home/away
    (gotchas #16/#32) — on the ticker date and move ``event_id`` +
    ``commence_time`` there. Completed/closed events are eligible (gotcha #32),
    closest-by-ticker-date tiebreaker.

    Idempotent + write-on-change (so this ALSO serves as the forward-fix on each
    matching run — cheap no-op once clean). It moves ONLY ``event_id`` and the
    derived ``commence_time`` — it NEVER touches ``is_winner`` /
    ``calibration_probability`` (those live on futures_outcomes; the stored
    Kalshi settlements are correct, only the link was wrong — gotcha #21).
    Bounded to the game-market cohort (no broad in-memory pull, gotcha #899).
    """
    try:
        # #1147 family: this correlated self-join UPDATE (a LATERAL scan of events
        # per mislinked market) can grow with the population and hang the realtime
        # matching worker if it ever runs long. Bound it — a timeout aborts THIS
        # statement, the except below logs it, and the next run retries; it never
        # blocks live polling. SET LOCAL is scoped to this transaction (reset on the
        # commit below).
        await session.execute(text("SET LOCAL statement_timeout = '30s'"))
        r = await session.execute(text(r"""
            WITH mislinked AS (
                SELECT fm.id AS mid, fm.event_id AS cur_eid,
                       to_date(substring(fm.external_id from '^KX[A-Z]+-(\d{2}[A-Z]{3}\d{2})'),'YYMONDD') AS tdate,
                       cur.home_team_name AS h, cur.away_team_name AS a
                FROM futures_markets fm
                JOIN events cur ON cur.id = fm.event_id
                WHERE fm.source = 'kalshi'
                  AND fm.external_id ~ '^KX(NHL|NBA|MLB)(SPREAD|TOTAL|GAME|MONEYLINE)'
                  AND substring(fm.external_id from '^KX[A-Z]+-(\d{2}[A-Z]{3}\d{2})') IS NOT NULL
                  AND ABS(cur.commence_time::date - to_date(substring(fm.external_id from '^KX[A-Z]+-(\d{2}[A-Z]{3}\d{2})'),'YYMONDD')) > 1
            )
            UPDATE futures_markets fm
            SET event_id = tgt.id, commence_time = tgt.commence_time, updated_at = NOW()
            FROM mislinked ml
            JOIN LATERAL (
                SELECT e2.id, e2.commence_time
                FROM events e2
                WHERE ((e2.home_team_name = ml.h AND e2.away_team_name = ml.a)
                    OR (e2.home_team_name = ml.a AND e2.away_team_name = ml.h))
                  AND e2.commence_time::date BETWEEN ml.tdate - 1 AND ml.tdate + 1
                  AND e2.id <> ml.cur_eid
                  AND e2.status IN ('scheduled','live','completed','closed')
                ORDER BY ABS(e2.commence_time::date - ml.tdate), e2.id
                LIMIT 1
            ) tgt ON true
            WHERE fm.id = ml.mid AND fm.event_id <> tgt.id
        """))
        n = r.rowcount or 0
        await session.commit()
        if n:
            logger.info(
                "Relink collapsed game markets (#944): moved %d markets to correct-date events", n
            )
        return n
    except Exception as e:
        logger.error("Relink collapsed game markets error: %s", e)
        # #1147: a statement_timeout (or any error) leaves the transaction aborted;
        # roll back so the shared session isn't poisoned for the caller's next op
        # ("current transaction is aborted" cascade).
        try:
            await session.rollback()
        except Exception:
            pass
        return 0


#: Hard cap on the Kalshi tennis rows pulled for segment reconciliation. The
#: source+window+prefix filter already bounds this to the low thousands
#: (measured 2026-09-02: 589 open ATP/WTA rows of any age + 3,782 resolved rows
#: created inside `KALSHI_SEGMENT_WINDOW_DAYS`, during the US Open fortnight —
#: i.e. at the yearly peak). The cap is a BACKSTOP against a Kalshi series
#: explosion, not a routine bound, which is why tripping it now REFUSES the pass
#: (see `_reconcile_kalshi_match_segments`) instead of silently reconciling a
#: partial view.
MAX_KALSHI_SEGMENT_ROWS = 20000

#: Q048: how far back the segment reconciler looks for markets that are no
#: longer `open`.
#:
#: The reconciler used to read `status == "open"` and nothing else, which made
#: convergence a RACE it loses exactly when it matters. A tennis match-winner
#: market (`KXATPMATCH-…`) resolves the moment the match ends — and the moment
#: the match ends is precisely when a ghost event holding it becomes the
#: user-visible defect: a finished match still advertised as upcoming. If the
#: schedule-derived twin had not appeared yet while the market was still open,
#: `_choose_segment_event` saw ONE candidate, returned `single`, moved nothing,
#: and the market then resolved out of the reconciler's sight forever.
#:
#: Measured on production 2026-09-02 with this module's own
#: `kalshi_match_segment_key`: of 2,933 Kalshi tennis markets created since the
#: US Open began, **25 sit on the wrong event of their own segment, and all 25
#: are `resolved`** — a 100% blind spot. 17 of them are ones where the
#: open-only read concludes `single` and moves nothing.
KALSHI_SEGMENT_WINDOW_DAYS = 14

#: A `commence_time_source` of this value means the time was DERIVED FROM THE
#: TICKER because nothing better existed — an auto-created row, midnight UTC,
#: with names parsed out of a market title ("Wu" / "Walton"). Any other non-null
#: provenance means the event came from a real schedule (`odds_api`, `espn`,
#: `statpal`), which is what the draw register and the tournament page point at.
#:
#: q076 moved the literal to `app.utils.event_completion`, where the two status
#: clocks now read it as well. Re-exported under the old private name so this
#: module's reconciliation rule and those clocks can never disagree about which
#: provenance is derived — one string, three readers.
_TICKER_DERIVED_COMMENCE_SOURCE = TICKER_DERIVED_COMMENCE_SOURCE


def _choose_segment_event(event_ids, provenance: dict) -> tuple:
    """Pick the ONE event a tennis match segment's markets should all sit on.

    Returns ``(event_id, reason)``; ``event_id`` is ``None`` when the choice is
    ambiguous, in which case nothing moves and the reason is counted.

    * One candidate → it wins, and nothing is moved off anything.
    * Several candidates → the one whose ``commence_time_source`` is NOT
      ticker-derived wins, because that row came from a real schedule and is the
      row the draw register and the event page already point at. This is the
      whole rule: a Kalshi auto-create is the duplicate, never the survivor.
    * Several candidates and none (or more than one) schedule-derived → REFUSE.
      Two ticker-derived twins are indistinguishable on evidence, and picking by
      row order would be a coin flip dressed as a reconciliation.
    """
    ids = sorted({int(e) for e in event_ids if e})
    if not ids:
        return None, "no_anchor"
    if len(ids) == 1:
        return ids[0], "single"
    scheduled = [
        eid for eid in ids
        if provenance.get(eid) not in (None, _TICKER_DERIVED_COMMENCE_SOURCE)
    ]
    if len(scheduled) == 1:
        return scheduled[0], "schedule_derived"
    return None, "ambiguous"


async def _reconcile_kalshi_match_segments(session) -> dict:
    """Q435: every market on ONE Kalshi tennis match resolves to ONE event.

    ═══ THE BUG THIS CLOSES ═══

    Kalshi prices a tennis match through several of its OWN events, one per
    series, all carrying the same match segment in the ticker. Our matcher
    treats each as an independent game market, so they scatter. Measured on
    production 2026-08-29, `KXATPMATCH-26AUG30BUBWOL` and its four siblings:

        KXATPMATCH-26AUG30BUBWOL       -> event 15293809  (odds_api, 15:00Z)
        KXATPSETWINNER-…BUBWOL-1/2/3   -> event 15295024  (kalshi_ticker, 00:00Z)
        KXATPEXACTMATCH-…BUBWOL        -> event 15295024
        KXATPGTOTAL-…BUBWOL-T22        -> (nothing)

    The US Open draw register pins 15293809, so `/api/events/15293809/game-
    markets` returned the winner and NOTHING ELSE, while the four props rendered
    perfectly on 15295024 — an event page with no route to it. The page was not
    missing the data. It was pointed at the wrong one of two rows for one match.

    ═══ WHY THIS IS ID-ANCHORED AND NOT A LOOSENING ═══

    `kalshi_match_segment_key` READS Kalshi's own event segment out of the
    ticker: same source, same key, parsed (ruling 048 arm A). No name is
    compared, no time window is opened, and no event row is absorbed into
    another — the twin survives, it simply stops holding markets that belong to
    the match the register named. That is exactly the "id-keyed reconciliation
    drains the duplicate" clause, executed.

    Two operations, both idempotent and write-on-change:

    * **ADOPT** — a market with no event joins the one its own segment already
      resolved to. Purely additive; nothing is unlinked.
    * **CONVERGE** — a segment spanning two events moves onto the
      schedule-derived one (see `_choose_segment_event`). Refuses when the
      choice is not forced.

    ═══ Q048: WHY THIS READS RESOLVED MARKETS, NOT JUST OPEN ONES ═══

    The first cut of this pass read `status == "open"`, and that one word made
    convergence a RACE that it loses at exactly the worst moment.

    A tennis match-winner market resolves when the match ends. The match ending
    is also the instant the ghost becomes the user-visible defect — a finished
    match still advertised as an upcoming fixture. So if the schedule-derived
    twin had not yet appeared while the winner market was open (one candidate ⇒
    `_choose_segment_event` returns `single` ⇒ nothing moves), the market
    resolved straight out of this pass's sight and stayed on the ghost forever.

    Measured on production 2026-09-02, over the 2,933 Kalshi tennis markets
    created since the US Open began: **25 markets sat on the wrong event of
    their own segment, and all 25 were `resolved`** — the open-only read had a
    100% blind spot on exactly this population. Every one of the 25 was a
    `KX*MATCH-*` ticker, i.e. the market that decides the card, sitting on a
    `kalshi_ticker` duplicate while the props sat on the real event.

    The worked example is the one that opened the queue. `26AUG30VALMON`:

        KXATPSETWINNER/GTOTAL/GSPREAD/EXACTMATCH-26AUG30VALMON
                                    -> 15293804  (odds_api, 2026-09-01 23:04Z,
                                                  completed 1-3 — the real row)
        KXATPMATCH-26AUG30VALMON    -> 15300759  (kalshi_ticker, 2026-08-30
                                                  00:00Z midnight stand-in,
                                                  still "scheduled")

    ESPN had the match final at 2026-09-01 23:05Z. A user searching "Monfils"
    got the GHOST first — "Vallejo v Monfils, scheduled" — above the real,
    correctly-settled row. Widening this read to resolved-and-linked markets
    converges that winner market onto 15293804 and the ghost stops holding any
    reason to be rendered.

    Only `event_id` moves. `is_winner`, `calibration_probability` and every
    `futures_outcomes` column are untouched (gotcha #21): the settlements were
    always right, only the link was wrong. `commence_time` is deliberately NOT
    rewritten either — unlike #944's relink these markets keep Kalshi's own
    close time, which the rest of the pipeline already reads as such (gotcha
    #14).
    """
    from app.models.models import FuturesMarket, Event
    from app.utils.prediction_market_matching import kalshi_match_segment_key

    stats = {
        "candidates": 0, "segments": 0, "adopted": 0,
        "converged": 0, "ambiguous": 0, "no_anchor": 0,
        "truncated": False,
    }
    try:
        window_floor = (
            datetime.now(timezone.utc)
            - timedelta(days=KALSHI_SEGMENT_WINDOW_DAYS)
        )
        rows = (
            await session.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.external_id,
                    FuturesMarket.event_id,
                )
                .where(
                    FuturesMarket.source == "kalshi",
                    # Q048: a STRICT SUPERSET of the old `status == "open"`
                    # population, so nothing that reconciles today stops
                    # reconciling. The second arm is what closes the blind
                    # spot: a market that has already resolved is still the
                    # provider's own evidence about which event its segment
                    # belongs to, and settlement columns are never touched
                    # here (only `event_id`/`sport_id` move), so reading a
                    # resolved row costs nothing that gotcha #21 protects.
                    #
                    # `event_id IS NOT NULL` on that arm is deliberate and is
                    # the difference between a fix and a sprawl. A resolved
                    # market that is ALREADY LINKED is the only kind that can
                    # reveal a WRONG link, which is this pass's job; a resolved
                    # market with no event at all is an ADOPT candidate, and
                    # measured on production 2026-09-02 admitting those would
                    # have attached 176 historical props to events in one pass
                    # — a different, larger question with its own blast radius
                    # (event pages, calibration grouping), parked rather than
                    # smuggled in here. Candidate-event sets are identical
                    # either way, because an unlinked row contributes no
                    # candidate, so this narrowing cannot change a single
                    # CONVERGE decision.
                    or_(
                        FuturesMarket.status == "open",
                        and_(
                            FuturesMarket.created_at >= window_floor,
                            FuturesMarket.event_id.isnot(None),
                        ),
                    ),
                    or_(
                        FuturesMarket.external_id.like("KXATP%"),
                        FuturesMarket.external_id.like("KXWTA%"),
                    ),
                )
                .order_by(FuturesMarket.id)
                .limit(MAX_KALSHI_SEGMENT_ROWS)
            )
        ).all()
        stats["candidates"] = len(rows)

        # A TRUNCATED READ IS NOT A SMALLER JOB — it is a different, wrong one.
        # The cap slices by `id`, which cuts across segments: a segment whose
        # schedule-derived member fell off the end reads as all-ticker-derived,
        # and `_choose_segment_event` will then hand an `event_id IS NULL`
        # sibling to the GHOST via the `single` branch. That is an actively
        # wrong move, not a missed one, so refuse the pass and say so loudly
        # rather than reconcile half a picture (gotcha #53 — and no silent
        # caps).
        if len(rows) >= MAX_KALSHI_SEGMENT_ROWS:
            stats["truncated"] = True
            logger.error(
                "Kalshi match-segment reconcile REFUSED: read hit the %d-row "
                "cap, so segment membership is unknowable and a partial view "
                "could adopt markets onto a ticker-derived duplicate. No "
                "markets moved. Raise MAX_KALSHI_SEGMENT_ROWS or shorten "
                "KALSHI_SEGMENT_WINDOW_DAYS (currently %d days).",
                MAX_KALSHI_SEGMENT_ROWS, KALSHI_SEGMENT_WINDOW_DAYS,
            )
            return stats

        # ONE definition of "same match" — the pure helper, in Python. Writing
        # the segment split a second time in SQL is how the two drift.
        segments: dict[str, list] = {}
        for row in rows:
            key = kalshi_match_segment_key(row.external_id)
            if key:
                segments.setdefault(key, []).append(row)
        stats["segments"] = len(segments)
        if not segments:
            return stats

        # Provenance for every candidate event, in one bounded read.
        candidate_event_ids = {
            int(r.event_id)
            for members in segments.values() for r in members if r.event_id
        }
        provenance: dict[int, str] = {}
        sport_ids: dict[int, int] = {}
        if candidate_event_ids:
            for eid, src, sport_id in (
                await session.execute(
                    select(Event.id, Event.commence_time_source, Event.sport_id)
                    .where(Event.id.in_(candidate_event_ids))
                )
            ).all():
                provenance[int(eid)] = src
                if sport_id:
                    sport_ids[int(eid)] = int(sport_id)

        moves: dict[int, list[int]] = {}
        for members in segments.values():
            target, reason = _choose_segment_event(
                [r.event_id for r in members], provenance,
            )
            if target is None:
                stats["ambiguous" if reason == "ambiguous" else "no_anchor"] += 1
                continue
            for row in members:
                if row.event_id == target:
                    continue
                moves.setdefault(target, []).append(row.id)
                stats["adopted" if row.event_id is None else "converged"] += 1

        for target, market_ids in moves.items():
            # `sport_id` rides the link, exactly as `_set_market_sport_fields`
            # does on a fresh one: a market pointing at event X while tagged
            # with the twin's sport row is the same split-brain one column down.
            #
            # `updated_at` is deliberately NOT stamped, and the omission is the
            # considered answer rather than an oversight — see #2024 and
            # `tests/test_futures_stamp_semantics.py`, which reds on any new
            # writer of it. That column's LIVE consumers read it as "the poller
            # ran" (`routes/playoffs.py` DROPS an outcome from the playoff grid
            # on a stale stamp) and, in one place, as "this price is fresh". A
            # link move is neither: no price was observed and no poll happened,
            # so stamping it would forge a poll under a column the repo has
            # already declared ambiguous. Nothing needs it either — this
            # reconciliation is verified by `event_id`, not by a timestamp.
            values = {"event_id": target}
            if target in sport_ids:
                values["sport_id"] = sport_ids[target]
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id.in_(market_ids))
                .values(**values)
            )
        if moves:
            await session.commit()
            logger.info(
                "Kalshi match-segment reconcile (Q435): %d adopted, %d converged "
                "across %d segments (%d ambiguous, %d without an anchor)",
                stats["adopted"], stats["converged"], stats["segments"],
                stats["ambiguous"], stats["no_anchor"],
            )
        return stats
    except Exception as e:
        logger.error("Kalshi match-segment reconcile error: %s", e)
        # Same posture as #944's relink: an aborted transaction must not poison
        # the shared session for the caller's next phase.
        try:
            await session.rollback()
        except Exception:
            pass
        return stats


async def _phase15_revalidate(
    session, stats: dict, now: datetime, _time_remaining,
) -> None:
    """Phase 1.5: fix stale and mislinked markets."""
    from app.models.models import FuturesMarket, Event, WinProbSnapshot

    stats["funnel"].setdefault("stale_relinked", 0)
    stats["funnel"].setdefault("mislink_fixed", 0)
    stats["funnel"].setdefault("phase15_skipped_budget", False)
    stats["funnel"].setdefault("phase15_checked", 0)

    if _time_remaining() < 120:
        logger.info("Skipping Phase 1.5 — only %.0fs remaining", _time_remaining())
        stats["funnel"]["phase15_skipped_budget"] = True
        return

    all_linked_result = await session.execute(
        select(FuturesMarket, Event)
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
            FuturesMarket.status == "open",
        )
        .order_by(
            case(
                (Event.status.in_(["completed", "closed"]), 0),
                (Event.external_id.is_(None), 1),
                else_=2,
            ),
            FuturesMarket.updated_at.desc(),
        )
        .limit(1000)
    )
    all_linked_rows = all_linked_result.all()

    for market, linked_event in all_linked_rows:
        if _time_remaining() < 60:
            logger.info("Phase 1.5 time budget exhausted after %d/%d markets",
                        stats["funnel"]["phase15_checked"], len(all_linked_rows))
            break
        stats["funnel"]["phase15_checked"] += 1
        try:
            # Backfill sport_id from event if missing
            if market.sport_id is None and linked_event.sport_id:
                market.sport_id = linked_event.sport_id
                stats["funnel"].setdefault("sport_id_backfilled", 0)
                stats["funnel"]["sport_id_backfilled"] += 1

            ticker_cat = _derive_sport_category(market.external_id)
            if ticker_cat and market.llm_sport_category != ticker_cat:
                market.llm_sport_category = ticker_cat
                stats["funnel"].setdefault("sport_category_fixed", 0)
                stats["funnel"]["sport_category_fixed"] += 1

            if not is_game_level_market(
                market.name, market.category, external_id=market.external_id,
            ):
                # Q440 (#2231): this pass used to walk straight past a linked
                # market that is not game-level, so a season market that got
                # linked by the old bare-`startswith` gate was never re-examined
                # and stayed on the game's page forever.
                #
                # The re-examination is scoped to the ONE class the deleted
                # predicate created — a ticker whose game prefix is shadowed by a
                # LONGER futures prefix. Not to "not game-level", which is 14,046
                # correctly name-linked rows on production against 3 of these
                # (see is_kalshi_shadowed_futures_ticker). Widening this arm to
                # the broad predicate is the reassuring-direction failure: the
                # counters would look healthy while the links vanished.
                #
                # No WinProbSnapshot delete. A season market never wrote the
                # game's win-prob curve, so there is nothing of its own to clean
                # up, and deleting by (event, source) would take a sibling game
                # market's real history with it. The blend key is pruned only if
                # no other market of this source is left on the event.
                if market.source == "kalshi" and is_kalshi_shadowed_futures_ticker(
                    market.external_id
                ):
                    logger.info(
                        "Unlinking %s '%s' (%s) from event %d — futures ticker "
                        "shadowed a game prefix (#2231)",
                        market.source, market.name, market.external_id,
                        linked_event.id,
                    )
                    _shadowed_event_id = linked_event.id
                    market.event_id = None
                    await session.flush()
                    if await _prune_orphaned_blend_source(
                        session, _shadowed_event_id, market.source,
                        exclude_market_id=market.id,
                    ):
                        stats.setdefault("phantom_blend_sources_pruned", 0)
                        stats["phantom_blend_sources_pruned"] += 1
                    stats["funnel"].setdefault("shadowed_futures_unlinked", 0)
                    stats["funnel"]["shadowed_futures_unlinked"] += 1
                continue

            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )
            if not matchup or not matchup.team_b:
                continue

            a_matches = (
                _fuzzy_team_match(matchup.team_a, linked_event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, linked_event.away_team_name)
            )
            b_matches = (
                _fuzzy_team_match(matchup.team_b, linked_event.home_team_name)
                or _fuzzy_team_match(matchup.team_b, linked_event.away_team_name)
            )
            teams_match = a_matches and b_matches
            is_finished = linked_event.status in ("completed", "closed")
            is_auto_created = (
                linked_event.external_id
                and str(linked_event.external_id).startswith("pm_")
            )

            # Cross-sport mislinkage detection: if the market's sport (from
            # ticker or llm_sport_category) doesn't match the event's sport,
            # treat it as a mislink even if team names match. This catches
            # cases like baseball "Royals" linked to cricket "Rajasthan Royals".
            sport_mismatch = False
            market_sport = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None
            if not market_sport and market.llm_sport_category:
                market_sport = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)
            if market_sport and linked_event.sport_id:
                from app.models.models import Sport as _Sport
                event_sport_result = await session.execute(
                    select(_Sport.key).where(_Sport.id == linked_event.sport_id)
                )
                event_sport_key = event_sport_result.scalar_one_or_none()
                if event_sport_key and not event_sport_key.startswith(market_sport):
                    sport_mismatch = True
                    logger.info(
                        "Cross-sport mislinkage detected: %s market '%s' (sport=%s) "
                        "linked to %s event %d",
                        market.source, market.name, market_sport,
                        event_sport_key, linked_event.id,
                    )

            if teams_match and not is_finished and not is_auto_created and not sport_mismatch:
                continue

            reason = (
                "auto_created" if is_auto_created
                else "cross_sport" if sport_mismatch
                else "mislinked" if not teams_match
                else "completed"
            )
            ticker_game_date = (
                extract_game_date_from_ticker(market.external_id)
                if market.source == "kalshi" else None
            )

            better_match = await _find_matching_event(
                session, matchup, market, now,
                game_date_override=ticker_game_date,
            )

            # #210 Item 1c: Phase 1.5's relink previously bypassed the
            # duplicate-linkage guard, letting a re-validated market land on an
            # event that already holds a different-dated game market. Route the
            # relink through the same guard the forward path (_try_link_market)
            # uses. If blocked, the elif chain below unlinks a genuinely
            # mismatched market rather than moving the wrong-game link.
            relink_blocked = False
            if better_match and better_match["event_id"] != linked_event.id:
                refusal = await _check_duplicate_kalshi_linkage_reason(
                    session, better_match["event_id"], market, ticker_game_date,
                )
                if refusal:
                    relink_blocked = True
                    key = (
                        "phase15_event_date_linkage_blocked"
                        if refusal == _REFUSAL_EVENT_DATE
                        else "phase15_duplicate_linkage_blocked"
                    )
                    stats["funnel"].setdefault(key, 0)
                    stats["funnel"][key] += 1

            if better_match and better_match["event_id"] != linked_event.id and not relink_blocked:
                logger.info(
                    "Re-linking %s '%s' from %s event %d -> event %d",
                    market.source, market.name, reason,
                    linked_event.id, better_match["event_id"],
                )
                if is_auto_created or not teams_match or sport_mismatch:
                    del_result = await session.execute(
                        delete(WinProbSnapshot).where(
                            WinProbSnapshot.event_id == linked_event.id,
                            WinProbSnapshot.source == market.source,
                        )
                    )
                    stats["orphaned_snapshots_deleted"] += del_result.rowcount
                market.event_id = better_match["event_id"]
                _set_market_sport_fields(market, better_match)
                if market.group_id and market.source == "polymarket":
                    from sqlalchemy import text as _text
                    await session.execute(_text("""
                        UPDATE futures_markets
                        SET event_id = :eid
                        WHERE group_id = :gid
                          AND group_type = 'polymarket_sub_market'
                          AND (event_id IS NULL OR event_id != :eid)
                    """), {"eid": better_match["event_id"], "gid": market.group_id})
                if is_auto_created:
                    stats["funnel"].setdefault("auto_created_relinked", 0)
                    stats["funnel"]["auto_created_relinked"] += 1
                elif not teams_match or sport_mismatch:
                    stats["funnel"]["mislink_fixed"] += 1
                else:
                    stats["funnel"]["stale_relinked"] += 1
            elif is_auto_created:
                pass
            elif not teams_match or sport_mismatch:
                logger.info(
                    "Unlinking %s '%s' from mismatched event %d — no better match (reason=%s)",
                    market.source, market.name, linked_event.id, reason,
                )
                del_result = await session.execute(
                    delete(WinProbSnapshot).where(
                        WinProbSnapshot.event_id == linked_event.id,
                        WinProbSnapshot.source == market.source,
                    )
                )
                stats["orphaned_snapshots_deleted"] += del_result.rowcount
                _unlinked_event_id = linked_event.id
                market.event_id = None
                await session.flush()  # persist event_id=None before the count query
                # #1163: prune the now-orphaned blend source key (invariant:
                # a PM source may not sit in the blend without a linked market).
                if await _prune_orphaned_blend_source(
                    session, _unlinked_event_id, market.source, exclude_market_id=market.id
                ):
                    stats.setdefault("phantom_blend_sources_pruned", 0)
                    stats["phantom_blend_sources_pruned"] += 1
                stats["funnel"]["mislink_fixed"] += 1
        except Exception as e:
            logger.debug("Error checking link for market %d: %s", market.id, e)
            continue


async def _match_prediction_markets(limit: int = 500):
    """
    Match game-level prediction markets to events and write win_prob_snapshots.

    Two phases:
    1. Link: Find unlinked game-level markets and match to events (set event_id)
    2. Snapshot: For all linked markets, write current probability to win_prob_snapshots
    """
    from app.models.models import (
        FuturesMarket, FuturesOutcome, Event, Sport, WinProbSnapshot,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    stats = {
        "markets_scanned": 0,
        "newly_linked": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "orphaned_snapshots_deleted": 0,
        "errors": [],
        "funnel": {
            "total_unlinked": 0,
            "not_game_level": 0,
            "no_matchup_extracted": 0,
            "game_level_detected": 0,
            "no_event_found": 0,
            "linked": 0,
            "sample_game_level_no_event": [],
            "sample_not_game_level": [],
        },
    }

    import time as _time
    _task_start = _time.monotonic()
    _TIME_BUDGET_SECONDS = 780

    def _time_remaining() -> float:
        return _TIME_BUDGET_SECONDS - (_time.monotonic() - _task_start)

    now = datetime.now(timezone.utc)
    polymarket_backfill_queue = []

    async with get_task_session() as session:
        # Phase 1, Pass 1: Kalshi ticker scan
        logger.info("Phase 1 starting — %.0fs budget remaining", _time_remaining())
        processed_ids = await _phase1_pass1_ticker_scan(
            session, stats, now, polymarket_backfill_queue, _time_remaining,
        )

        # Phase 1, Pass 2: General scan
        stats["funnel"]["total_unlinked"] = (
            stats["funnel"].get("ticker_scan_count", 0)
        )
        await _phase1_pass2_general_scan(
            session, stats, now, limit, processed_ids,
            polymarket_backfill_queue, _time_remaining,
        )
        stats["funnel"]["total_unlinked"] += stats["funnel"].get("general_scan_count", 0)

        # Phase 1.5: Re-validate linked markets
        logger.info("Phase 1 done (%d scanned, %d linked) — %.0fs remaining",
                    stats["markets_scanned"], stats["newly_linked"], _time_remaining())
        await _phase15_revalidate(session, stats, now, _time_remaining)

        await session.commit()

        # #944: correct Kalshi game markets that collapsed onto the last game's
        # event (commence_time = resolution date). Idempotent + write-on-change,
        # so this is both the forward-fix and the one-shot historical relink.
        stats["funnel"]["game_markets_relinked"] = await _relink_collapsed_game_markets(session)

        # Q435: converge every market on one Kalshi tennis match onto one event.
        # Runs AFTER the relink so a market this run has just moved to its
        # correct-date event is already where its segment siblings can see it.
        stats["funnel"]["kalshi_segment_reconcile"] = (
            await _reconcile_kalshi_match_segments(session)
        )

        # ── Phase 2: Write win_prob_snapshots for active linked markets ────
        #
        # Only process markets linked to scheduled/live events.
        # Completed/closed events are excluded — prediction market prices
        # after game end are stale and stretch the OddsChart past the real
        # game boundary (the "prediction market bleed" bug, 0t-1).
        #
        # Time-budgeted: skip if running low on time
        stats["funnel"].setdefault("phase2_skipped_budget", False)
        linked_rows = []
        if _time_remaining() < 60:
            logger.info("Skipping Phase 2 — only %.0fs remaining", _time_remaining())
            stats["funnel"]["phase2_skipped_budget"] = True
        else:
            linked_result = await session.execute(
                select(FuturesMarket, Event)
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source.in_(["kalshi", "polymarket"]),
                    FuturesMarket.event_id.isnot(None),
                    or_(
                        Event.status.in_(["scheduled", "live"]),
                        and_(
                            Event.status.in_(["completed", "closed"]),
                            Event.commence_time >= now - timedelta(hours=24),
                        ),
                    ),
                )
            )
            linked_rows = linked_result.all()

        # DEDUP: Kalshi creates separate binary markets per team outcome
        # (e.g., "Celtics win?" and "76ers win?" for the same game). If both
        # are linked to the same event, we want to AVERAGE their implied
        # home probabilities to cancel out vig. Pick a primary market for
        # processing (matchup extraction, ticker validation), and store all
        # sibling markets for probability averaging.
        linked_refs = [
            _LinkedMarketRef(
                market_id=market.id,
                source=market.source,
                external_id=market.external_id,
                name=market.name,
                event_id=event.id,
                event_commence_time=event.commence_time,
                home_team_name=event.home_team_name,
                away_team_name=event.away_team_name,
            )
            for market, event in linked_rows
        ]

        all_per_event_source: dict[tuple[int, str], list[_LinkedMarketRef]] = {}
        for market_ref in linked_refs:
            key = (market_ref.event_id, market_ref.source)
            if key not in all_per_event_source:
                all_per_event_source[key] = []
            all_per_event_source[key].append(market_ref)

        # ── Wrong-game detection: unlink Kalshi game/map markets whose ticker
        # date is far from the event's commence_time. Each of these prefixes is
        # a per-game (or per-esports-map) winner, so a different-dated ticker on
        # one event is a different match, not a prop of the same game.
        #
        # #210 Item 1e: the set now covers NCAAMB / college basketball (the
        # same-day doubleheader wrong-game class from #209) and esports (the
        # teamless tournament-dump class where different-day matches pile onto
        # one event). Only game/map WINNERS are listed — props (spread, total,
        # mention, totalmaps) legitimately share the game's date and must never
        # be date-unlinked.
        #
        # #210 Item 1d: this loop runs over EVERY linked market in EVERY group
        # (not just the dedup primary + blend-feeding tickers the Phase-2 primary
        # loop below covers), so same-day doubleheader mislinks (~5h apart) are
        # caught too. The prefix allowlist (WRONG_GAME_PREFIXES) is module-level
        # (#210 Item 1e) and combat is skipped defensively.
        #
        # Q439 (#2214): the threshold is now _ticker_date_conflicts_with_event —
        # the SAME function the link path uses, so this arm and its inverse can
        # no longer disagree. It reads the ticker's clock as US Eastern, which is
        # what it is; the previous helper read it as UTC and therefore unlinked
        # every MLB game market it was ever shown, 4h out, every run.
        stats["funnel"].setdefault("phase2_multi_game_unlinked", 0)
        for key, group in list(all_per_event_source.items()):
            if key[1] != "kalshi" or not group:
                continue

            ev_ref = group[0]
            if not ev_ref.event_commence_time:
                continue
            ec = ev_ref.event_commence_time if ev_ref.event_commence_time.tzinfo else ev_ref.event_commence_time.replace(tzinfo=timezone.utc)

            for m in list(group):
                ext = (m.external_id or "").lower()
                prefix = ext.split("-")[0] if "-" in ext else ext
                if prefix not in WRONG_GAME_PREFIXES:
                    continue
                # Combat fights are date-disambiguated by fighter names, not
                # dates — never date-unlink them (defense-in-depth; combat
                # prefixes are not in the set, but a shared token could alias).
                if is_combat_fight_ticker(m.external_id):
                    continue
                td = extract_game_date_from_ticker(m.external_id)
                if not _ticker_date_conflicts_with_event(td, ec, prefix):
                    continue
                # Report the diff from the instant the decision was made on, not
                # from the raw ticker stamp — a log line that disagrees with the
                # rule it explains is how this bug survived twelve days.
                d = ticker_start_utc(td) or (
                    td if td.tzinfo else td.replace(tzinfo=timezone.utc)
                )
                diff_hours = abs((d - ec).total_seconds()) / 3600
                logger.warning(
                    "Phase 2 wrong-game unlink: %s (date=%s) is %.0fh from event %d (date=%s) — unlinking",
                    m.external_id, d.date(), diff_hours, ev_ref.event_id, ec.date(),
                )
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == m.market_id)
                    .values(event_id=None)
                )
                stats["funnel"]["phase2_multi_game_unlinked"] += 1
                # #1163: prune the orphaned blend source key on unlink.
                if await _prune_orphaned_blend_source(
                    session, ev_ref.event_id, m.source, exclude_market_id=m.market_id
                ):
                    stats.setdefault("phantom_blend_sources_pruned", 0)
                    stats["phantom_blend_sources_pruned"] += 1
                group[:] = [gm for gm in group if gm.market_id != m.market_id]

            await session.commit()

        # Pick the primary market per group: prefer game-winner, then lowest id.
        # Without this, a prop market with a lower id shadows the game-winner
        # and no win_prob_snapshots are written for Kalshi.
        best_per_event_source: dict[tuple[int, str], _LinkedMarketRef] = {}
        for key, group in all_per_event_source.items():
            if not group:
                continue  # Group emptied by multi-game unlink
            primary = group[0]
            for market_ref in group[1:]:
                if market_ref.is_game_winner and not primary.is_game_winner:
                    primary = market_ref
                elif primary.is_game_winner == market_ref.is_game_winner and market_ref.market_id < primary.market_id:
                    primary = market_ref
            best_per_event_source[key] = primary

        stats["phase2_markets_raw"] = len(linked_rows)
        stats["phase2_markets_deduped"] = len(best_per_event_source)

        phase2_processed = 0
        phase2_skipped_not_ml = 0
        for market in best_per_event_source.values():
            if _time_remaining() < 60:
                logger.info("Phase 2 time budget exhausted after %d/%d markets", phase2_processed, len(linked_rows))
                break
            phase2_processed += 1
            try:
                # Only write win_prob_snapshots for moneyline/game-winner
                # markets. Props (spread, total, player stats, overtime,
                # half winner) are correctly linked for display but should
                # not contribute to the probability time-series.
                if market.source == "kalshi" and market.external_id:
                    if not feeds_win_prob_blend(market.external_id):
                        phase2_skipped_not_ml += 1
                        continue

                    # Validate ticker date matches event date. Colorado plays
                    # Cincinnati on Apr 28 AND Apr 29 — both games' markets
                    # match by team name. If the ticker date doesn't match the
                    # event's commence_time, this market is linked to the wrong
                    # event. Unlink it rather than writing bad data.
                    #
                    # Combat fights are exempt: they are disambiguated by fighter
                    # names (no same-card double-header), and their date-only
                    # ticker (e.g. 26JUL11) legitimately sits up to ~28h from the
                    # event's UTC commence (gotcha #14 — Kalshi close-time ≠ start).
                    #
                    # Q439 (#2214): decided by _ticker_date_conflicts_with_event,
                    # the same function the link path uses — the ticker's clock is
                    # US Eastern, and reading it as UTC unlinked every MLB game
                    # market on every run.
                    #
                    # Q504-b: Kalshi tennis match segments are exempt for the same
                    # reason combat fights are, and the measurement is on the
                    # record. `KXATPMATCH-26AUG30FERMUS` carries the TOURNAMENT
                    # SEGMENT's date; Fery played Musetti on 2026-09-01, 48h after
                    # the `26AUG30` in its own ticker. Every one of its five prop
                    # siblings carries that same stale date and none of them ever
                    # reaches this check — props `continue` on the
                    # `feeds_win_prob_blend` gate three lines up. So this arm fired
                    # on exactly one market per tennis match: THE WINNER, the only
                    # one that writes the blend.
                    #
                    # The result was a fight between two phases of this same task.
                    # `_reconcile_kalshi_match_segments` (Q435) adopts the winner
                    # onto the event its segment siblings already hold — an
                    # id-anchored link, ruling 048 arm A — and then, seconds later
                    # in the same run, this unlinked it again. Measured 2026-09-01
                    # 22:47Z: adopted=2 against phase2_date_unlinked=27, and 15 open
                    # ATP/WTA match-winner markets sitting unlinked beside linked
                    # prop siblings. Downstream, those 15 events hold Kalshi PROPS
                    # ONLY, so `compute_source_home_probability` returns None, the
                    # WS consumer never subscribes the winner ticker (it selects on
                    # `event_id IS NOT NULL`), and the hero's Kalshi number freezes
                    # at whatever the last transient link happened to stamp.
                    #
                    # A date test cannot adjudicate this link: the segment token
                    # already did, with the provider's own id. Declining here does
                    # not loosen the LINK path — Phase 1 still refuses these on the
                    # same predicate, and the only thing that may link them remains
                    # the id-anchored reconciler.
                    ticker_date = extract_game_date_from_ticker(market.external_id)
                    _prefix = _kalshi_prefix(market.external_id)
                    if (
                        not is_combat_fight_ticker(market.external_id)
                        and not is_kalshi_match_segment_ticker(market.external_id)
                        and _ticker_date_conflicts_with_event(
                            ticker_date, market.event_commence_time, _prefix
                        )
                    ):
                        _td = ticker_start_utc(ticker_date) or (
                            ticker_date if ticker_date.tzinfo
                            else ticker_date.replace(tzinfo=timezone.utc)
                        )
                        _ec = market.event_commence_time if market.event_commence_time.tzinfo else market.event_commence_time.replace(tzinfo=timezone.utc)
                        logger.warning(
                            "Phase 2 date mismatch: %s ticker=%s event=%s (diff=%.0fh) — unlinking",
                            market.external_id, _td.date(), _ec.date(),
                            abs((_td - _ec).total_seconds()) / 3600,
                        )
                        await session.execute(
                            update(FuturesMarket)
                            .where(FuturesMarket.id == market.market_id)
                            .values(event_id=None)
                        )
                        # #1163: prune the orphaned blend source key on unlink
                        # (before the commit so it lands atomically).
                        if await _prune_orphaned_blend_source(
                            session, market.event_id, market.source, exclude_market_id=market.market_id
                        ):
                            stats.setdefault("phantom_blend_sources_pruned", 0)
                            stats["phantom_blend_sources_pruned"] += 1
                        await session.commit()
                        stats["funnel"].setdefault("phase2_date_unlinked", 0)
                        stats["funnel"]["phase2_date_unlinked"] += 1
                        continue

                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup:
                    continue

                outcome_result = await session.execute(
                    select(FuturesOutcome)
                    .where(FuturesOutcome.market_id == market.market_id)
                    .order_by(FuturesOutcome.rank)
                )
                all_outcomes = outcome_result.scalars().all()
                if not all_outcomes:
                    continue

                ml_result = find_moneyline_outcome(
                    all_outcomes, matchup,
                    market.home_team_name, market.away_team_name,
                )
                if not ml_result:
                    continue

                outcome, yes_is_home = ml_result
                yes_prob = float(outcome.current_probability)

                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob

                # Devig: if dual markets exist (e.g., "Celtics win?" +
                # "76ers win?"), average both sides to cancel vig.
                es_key = (market.event_id, market.source)
                siblings = all_per_event_source.get(es_key, [])
                if len(siblings) == 2:
                    home_probs = [home_prob]
                    for sib_market in siblings:
                        if sib_market.market_id == market.market_id:
                            continue
                        sib_outcomes_result = await session.execute(
                            select(FuturesOutcome)
                            .where(FuturesOutcome.market_id == sib_market.market_id)
                            .order_by(FuturesOutcome.rank)
                        )
                        sib_outcomes = sib_outcomes_result.scalars().all()
                        if sib_outcomes:
                            sib_ml = find_moneyline_outcome(
                                sib_outcomes, matchup,
                                market.home_team_name, market.away_team_name,
                            )
                            if sib_ml:
                                sib_outcome, sib_yes_is_home = sib_ml
                                sib_prob = float(sib_outcome.current_probability)
                                sib_home = sib_prob if sib_yes_is_home else 1.0 - sib_prob
                                home_probs.append(sib_home)
                    if len(home_probs) == 2:
                        home_prob = sum(home_probs) / 2.0

                home_prob = await _check_and_fix_inversion(
                    session, market.event_id, home_prob, market.source,
                )
                away_prob = 1.0 - home_prob

                source_key = market.source
                snapshot, is_new = await _create_or_update_win_prob_snapshot(
                    session,
                    event_id=market.event_id,
                    source=source_key,
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    game_state={
                        "market_name": market.name,
                        "market_id": market.market_id,
                        "outcome_name": outcome.name,
                        "yes_probability": yes_prob,
                        "yes_bid": float(outcome.current_yes_bid) if outcome.current_yes_bid else None,
                        "yes_ask": float(outcome.current_yes_ask) if outcome.current_yes_ask else None,
                    },
                )

                if is_new:
                    session.add(snapshot)
                    stats["snapshots_written"] += 1
                else:
                    stats["snapshots_deduped"] += 1

                from sqlalchemy import update as _sql_upd
                from app.utils.aggregation import stamp_source_reading
                _pm_r = await session.execute(
                    select(Event.win_probability_sources).where(Event.id == market.event_id)
                )
                # #1829: value + write time (a linked market can stop updating
                # long before anything notices it has).
                _pm_wps = stamp_source_reading(
                    _pm_r.scalar_one_or_none(), source_key, round(home_prob, 4)
                )
                await session.execute(
                    _sql_upd(Event)
                    .where(Event.id == market.event_id)
                    .values(win_probability_sources=_pm_wps)
                )

                # Commit per-market to avoid deadlocks with live polling task
                await session.commit()

            except Exception as e:
                err_str = str(e)
                if "deadlock" in err_str.lower():
                    await session.rollback()
                    stats["funnel"].setdefault("phase2_deadlocks", 0)
                    stats["funnel"]["phase2_deadlocks"] += 1
                else:
                    await session.rollback()
                    stats["errors"].append(f"market {market.market_id}: {err_str[:100]}")
                continue

    stats["phase2_skipped_not_moneyline"] = phase2_skipped_not_ml

    # ── Phase 3: Backfill Polymarket price history for newly linked markets ──
    # Runs outside the main DB session to avoid holding transactions open
    # during API calls. Each backfill is independent and idempotent.
    if polymarket_backfill_queue:
        if _time_remaining() < 60:
            logger.info("Skipping Phase 3 — only %.0fs remaining", _time_remaining())
            stats["funnel"]["polymarket_backfills_skipped_budget"] = True
        else:
            stats["funnel"]["polymarket_backfills_queued"] = len(polymarket_backfill_queue)
            for market_id, event_id in polymarket_backfill_queue:
                if _time_remaining() < 30:
                    logger.info("Phase 3 time budget exhausted after %d/%d backfills",
                                stats["funnel"].get("polymarket_backfill_snapshots", 0),
                                len(polymarket_backfill_queue))
                    break
                try:
                    backfill_stats = await _backfill_polymarket_win_prob_history(
                        market_id, event_id,
                    )
                    stats["funnel"].setdefault("polymarket_backfill_snapshots", 0)
                    stats["funnel"]["polymarket_backfill_snapshots"] += (
                        backfill_stats.get("snapshots_created", 0)
                    )
                except Exception as e:
                    stats["errors"].append(f"backfill_{market_id}: {str(e)[:100]}")

    # ── #1163: self-heal phantom blend sources ─────────────────────────────
    # Sweep events whose win_probability_sources carries a kalshi/polymarket key
    # with no linked market of that source (orphans left by pre-guard unlinks).
    # Bounded by the task's remaining budget so it never starves the poll.
    if _time_remaining() > 30:
        try:
            async with get_task_session() as cleanup_session:
                pruned = await _cleanup_orphaned_blend_sources(
                    cleanup_session, time_remaining_fn=_time_remaining
                )
            stats["phantom_blend_sources_cleaned"] = pruned
            if pruned:
                logger.info("Pruned %d phantom blend source key(s) (#1163)", pruned)
        except Exception as e:
            stats["errors"].append(f"phantom_cleanup: {str(e)[:100]}")

    logger.info(
        "Prediction market matching: scanned=%d, linked=%d, "
        "snapshots_written=%d, deduped=%d, errors=%d, %.0fs remaining",
        stats["markets_scanned"], stats["newly_linked"],
        stats["snapshots_written"], stats["snapshots_deduped"],
        len(stats["errors"]), _time_remaining(),
    )
    return stats


async def _find_matching_event(session, matchup, market, now, game_date_override=None):
    """
    Find an Event that matches the given matchup and market.

    Two-pass strategy:
    1. Time-windowed search: ±48h around game date (from ticker or market.commence_time)
    2. Broad fallback: If no time-windowed match AND we have both team names,
       search scheduled/live events without time restriction. This handles
       Polymarket markets (commence_time = market creation date, not game date)
       and Kalshi markets without parseable ticker dates.

    Args:
        game_date_override: If provided, use this as the reference time instead
            of market.commence_time. Critical for Kalshi game markets where
            commence_time is the market resolution date (weeks after the game),
            not the actual game date.
    """
    from app.models.models import Event, Sport

    # Build team name search patterns
    teams_to_search = [matchup.team_a]
    if matchup.team_b:
        teams_to_search.append(matchup.team_b)

    # Create ILIKE conditions for team names.
    # _expand_team_search_terms produces multiple patterns for abbreviated
    # names (e.g., "WSH Capitals" → ["WSH Capitals", "Capitals"]) so that
    # ILIKE '%Capitals%' matches "Washington Capitals" in the events table.
    ilike_conditions = []
    for team in teams_to_search:
        for search_term in _expand_team_search_terms(team):
            pattern = f"%{_escape_like(search_term)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

    # Also restrict: don't match events that started more than 6 hours ago
    # (unless they're still live)
    past_cutoff = now - MAX_PAST_GAME_DELTA

    # ── Pass 1: Time-windowed search ──────────────────────────────────
    # Kalshi commence_time is the market RESOLUTION date (often weeks after
    # the game), so we use the ticker-extracted game date when available.
    # When the ticker date includes HHMM (non-midnight), use a tight ±3h
    # window. This correctly distinguishes double-header games (same teams,
    # same day, ~5h apart — e.g., 1:40 PM and 7:10 PM). Without HHMM,
    # use an asymmetric window: -6h to +30h. Ticker dates are US calendar
    # dates stored as UTC midnight, but US evening games (7-11 PM ET) fall
    # on the NEXT UTC day (00:00-04:00 UTC). A symmetric ±18h missed these.
    #
    # Q439 (#2214): the ±3h window is centred on the ticker's REAL instant, not
    # on its Eastern wall clock read as UTC. Measured on production 2026-08-29,
    # `KXMLBGAME-26AUG291610KCCLE` — a 16:10 EDT first pitch, i.e. 20:10Z — was
    # searched over 13:10Z..19:10Z and returned ZERO candidates while its event
    # sat one hour past the end of the window. Every MLB game ticker failed the
    # same way, in both directions of the year: EDT is 4h and EST is 5h, and the
    # window is 3h. Only the CENTRE moves; the tolerance is untouched, because
    # ±3h is the measured doubleheader-separating number the ESPN identity rail
    # also pins itself to.
    ticker_start = (
        ticker_start_utc(game_date_override)
        if game_date_override and getattr(market, "source", None) == "kalshi"
        else None
    )
    # The instant proximity is SCORED from, too — a candidate 4h out of a wrong
    # centre is 0h out of the right one, and the score decides which of two
    # same-teams rows the market lands on.
    scoring_ref = ticker_start or game_date_override
    reference_time = ticker_start or game_date_override or market.commence_time or now
    if game_date_override:
        if ticker_start is not None:
            time_start = reference_time - timedelta(hours=3)
            time_end = reference_time + timedelta(hours=3)
        elif game_date_override.hour != 0 or game_date_override.minute != 0:
            time_start = reference_time - timedelta(hours=3)
            time_end = reference_time + timedelta(hours=3)
        else:
            time_start = reference_time - timedelta(hours=6)
            time_end = reference_time + timedelta(hours=30)
    elif market.source == "kalshi":
        time_delta = timedelta(days=7)
        time_start = reference_time - time_delta
        time_end = reference_time + time_delta
    else:
        time_delta = MAX_TIME_DELTA
        time_start = reference_time - time_delta
        time_end = reference_time + time_delta

    event_result = await session.execute(
        select(Event)
        .options(joinedload(Event.sport))
        .where(
            or_(*ilike_conditions),
            Event.commence_time.between(time_start, time_end),
            or_(
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time >= past_cutoff,
            ),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().unique().all()

    result = _score_candidates(candidates, matchup, market, now, scoring_ref)
    if result:
        return result

    # ── Pass 2: Broad fallback (no time window) ──────────────────────
    # Only when we have BOTH team names (strong signal) and Pass 1 found nothing.
    # This handles Polymarket (commence_time = market creation date) and
    # Kalshi markets without parseable ticker dates.
    # Restrict to scheduled/live events within ±14 days of now to avoid
    # matching ancient or far-future events.
    if matchup.team_b:
        broad_start = now - timedelta(days=1)  # Allow games that started today
        broad_end = now + timedelta(days=14)   # Up to 2 weeks ahead

        event_result = await session.execute(
            select(Event)
            .options(joinedload(Event.sport))
            .where(
                or_(*ilike_conditions),
                Event.commence_time.between(broad_start, broad_end),
                Event.status.in_(["scheduled", "live"]),
            )
            .order_by(Event.commence_time)
            .limit(20)
        )
        broad_candidates = event_result.scalars().unique().all()

        result = _score_candidates(broad_candidates, matchup, market, now, scoring_ref)
        if result:
            logger.info(
                "Broad fallback matched %s '%s' → event %d (time window bypass)",
                market.source, market.name, result["event_id"],
            )
            return result

    return None


def _score_candidates(candidates, matchup, market, now, game_date_override=None):
    """Score candidate events and return the best match (or None)."""
    if not candidates:
        return None

    # Compute sport prefix once (depends only on market, not on candidates).
    # Ticker-derived prefix (Kalshi) is most reliable. Falls back to
    # llm_sport_category (Polymarket and Kalshi without parseable ticker).
    ticker_sport_prefix = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None
    sport_prefix = ticker_sport_prefix
    if not sport_prefix and market.llm_sport_category:
        sport_prefix = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)

    best_match = None
    best_score = -1

    for event in candidates:
        # When we have both team names, REQUIRE both to fuzzy-match the event.
        # Prevents false positives like "Thunder vs. Pistons" matching
        # "Bulls vs. Pistons" (Thunder ≠ Bulls), or "Pistons vs. Bulls"
        # matching "Georgia Southern Eagles vs South Florida Bulls"
        # (Pistons ≠ Georgia Southern Eagles).
        if matchup.team_b:
            a_matches = (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            )
            b_matches = (
                _fuzzy_team_match(matchup.team_b, event.home_team_name)
                or _fuzzy_team_match(matchup.team_b, event.away_team_name)
            )
            if not (a_matches and b_matches):
                continue

        # Check team name matching (determine yes/no home/away mapping)
        team_match = match_teams_to_event(
            matchup,
            event.home_team_name,
            event.away_team_name,
            external_id=market.external_id or "",
        )
        if not team_match:
            continue

        # For "Will X win?" with only one team, verify the market team
        # actually matches an event team
        if matchup.format_type == "will_win" and not matchup.team_b:
            if not (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            ):
                continue

        # Score: prefer closer to now + live games
        score = 0

        # Time proximity to now (max 10 points, closer = higher)
        ref = game_date_override or now
        if event.commence_time:
            delta_hours = abs(
                (event.commence_time - ref).total_seconds()
            ) / 3600
            score += max(0, 10 - delta_hours / 4)  # Gradual decay over ~40h

        # Live games get a bonus
        if event.status == "live":
            score += 5
        elif event.status == "scheduled":
            score += 3

        # Both teams verified matching (gate above ensures this when team_b exists)
        if matchup.team_b:
            score += 10

        # Prefer Odds API events (external_id set) over auto-created ones
        if event.external_id:
            score += 8

        # Sport validation: hard-reject events from the wrong sport.
        # Both ticker and llm_sport_category are hard rejects — city-name
        # collisions (Boston/New York) and generic team names (Royals/Indians)
        # cause cross-sport mismatches if we only use soft scoring.
        if sport_prefix and event.sport and event.sport.key:
            if not event.sport.key.startswith(sport_prefix):
                continue  # Wrong sport — skip this candidate
            score += 5  # Same sport confirmed
        elif not sport_prefix:
            score -= 5  # No sport validation — penalize to prefer validated matches

        if score > best_score:
            best_score = score
            best_match = {
                "event_id": event.id,
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "yes_is_home": team_match["yes_is_home"],
                "score": score,
                "sport_id": event.sport_id,
            }

    # When we have no sport prefix (no ticker sport, no llm_sport_category),
    # require a higher confidence threshold to prevent cross-sport mismatches.
    # A score of 21 requires: both teams match (+10) + close time (+~10) +
    # scheduled (+3), preventing generic team names like "Royals" or "Indians"
    # from matching across cricket/baseball.
    if best_match and not sport_prefix and best_match.get("score", 0) < 21:
        logger.info(
            "Rejecting low-confidence match (score=%d, no sport prefix) for %s",
            best_match["score"], market.external_id,
        )
        return None

    return best_match


async def _find_event_by_sport_and_time(session, market, now, game_date_override=None):
    """
    Fallback matching for ticker-detected markets with generic names.

    When extract_matchup() fails (e.g., market name is "Professional Basketball
    Game"), we use the Kalshi ticker to determine the sport and search for
    events by sport_key + commence_time proximity.

    Returns a match if EXACTLY ONE event matches (unambiguous), or uses
    ticker fragment matching to disambiguate when multiple candidates exist
    (critical for NCAAB/NCAAF where dozens of games happen per day).

    Returns the same dict format as _find_matching_event, with
    yes_is_home=True as default (will be corrected if outcome names
    match team names in Phase 2).
    """
    from app.models.models import Event, Sport

    # Determine sport from ticker
    sport_prefix = get_sport_prefix_from_ticker(market.external_id)
    if not sport_prefix:
        return None

    # Use game_date_override (from ticker) if available — Kalshi commence_time
    # is the market RESOLUTION date (often weeks after the game), not the
    # actual game date.
    # Tighten to ±3h when we have a ticker game date (more precise)
    reference_time = game_date_override or market.commence_time
    if not reference_time:
        return None

    if game_date_override:
        # Tight window when HHMM is available; wider for date-only tickers
        has_time = game_date_override.hour != 0 or game_date_override.minute != 0
        window_hours = 3 if has_time else 18
    elif market.source == "kalshi":
        window_hours = 48  # Kalshi commence_time is resolution date, very imprecise
    else:
        window_hours = 6
    time_start = reference_time - timedelta(hours=window_hours)
    time_end = reference_time + timedelta(hours=window_hours)

    # Query events by sport and time
    # Event has sport_id (FK), Sport has key (e.g., "basketball_nba")
    event_result = await session.execute(
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key.like(f"{sport_prefix}%"),
            Event.commence_time.between(time_start, time_end),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().all()

    if len(candidates) == 1:
        # Unambiguous COUNT — exactly one event in that sport + time window.
        # But an unambiguous count is NOT proof of the right teams: the window
        # is as wide as ±48h for date-less Kalshi tickers, so a lone candidate
        # can easily be a DIFFERENT game (the wrong-game link class, #210 1a).
        # Team gate: when the ticker yields two team fragments, reject the link
        # if they match NEITHER of the candidate's teams (score 0). Un-parseable
        # tickers keep the prior behavior — there is no team signal to gate on,
        # and the single-candidate + tight-window case is reasonably safe.
        event = candidates[0]
        fragments = extract_ticker_fragments(market.external_id)
        if fragments:
            abbrev_a, abbrev_b, _ = fragments
            gate_score = _score_fragment_match(
                abbrev_a, abbrev_b,
                event.home_team_name or "", event.away_team_name or "",
            )
            if gate_score == 0:
                logger.info(
                    "Sport+time fallback REJECTED %s '%s' → event %d (%s vs %s): "
                    "ticker fragments %s/%s match neither team (wrong-game gate)",
                    market.external_id, market.name, event.id,
                    event.home_team_name, event.away_team_name, abbrev_a, abbrev_b,
                )
                return None
        logger.info(
            "Sport+time fallback matched %s '%s' → event %d (%s vs %s)",
            market.external_id, market.name, event.id,
            event.home_team_name, event.away_team_name,
        )
        return {
            "event_id": event.id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "yes_is_home": True,
            "sport_id": event.sport_id,
        }

    if len(candidates) > 1:
        # Try ticker fragment matching to disambiguate
        fragments = extract_ticker_fragments(market.external_id)
        if fragments:
            abbrev_a, abbrev_b, _ = fragments
            best_event = None
            best_score = 0
            for event in candidates:
                score = _score_fragment_match(
                    abbrev_a, abbrev_b,
                    event.home_team_name, event.away_team_name,
                )
                if score > best_score:
                    best_score = score
                    best_event = event
            if best_score >= 2 and best_event:
                logger.info(
                    "Fragment-matched %s → event %d (%s vs %s) [fragments=%s/%s, score=%d]",
                    market.external_id, best_event.id,
                    best_event.home_team_name, best_event.away_team_name,
                    abbrev_a, abbrev_b, best_score,
                )
                return {
                    "event_id": best_event.id,
                    "home_team": best_event.home_team_name,
                    "away_team": best_event.away_team_name,
                    "yes_is_home": True,
                    "sport_id": best_event.sport_id,
                }

        logger.debug(
            "Sport+time fallback found %d candidates for %s (ambiguous, skipping)",
            len(candidates), market.external_id,
        )

    return None


def _escape_like(s: str) -> str:
    """Escape special characters for ILIKE patterns."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# =============================================================================
# Auto-create Events from Prediction Markets
# =============================================================================

# Sport key → human-readable name for auto-created sports
_SPORT_KEY_NAMES: dict[str, tuple[str, str]] = {
    "icehockey_olympics": ("Ice Hockey - Olympics", "Ice Hockey"),
    "basketball_olympics": ("Basketball - Olympics", "Basketball"),
    "soccer_olympics": ("Soccer - Olympics", "Soccer"),
    "fieldhockey_olympics": ("Field Hockey - Olympics", "Field Hockey"),
    "curling_olympics": ("Curling - Olympics", "Curling"),
}


async def _resolve_combat_opponent(session, external_id, known_fighter, sport_key):
    """Recover a combat bout's OPPONENT from the entity registry via the ticker.

    #175 Item 2 — the fighter-abbrev grammar fix. A UFC/boxing fight-winner
    market names only ONE competitor, so a matchup parsed from it degenerates to
    "Saint-Denis vs Saint-Denis". The ticker (``KXUFCFIGHT-26JUL11SAIPIM``)
    carries BOTH fighter abbrevs; given the one fighter we already know
    ("Benoit Saint-Denis"), the OTHER abbrev ("pim") resolves to the opponent
    ("Paddy Pimblett") against the seeded person registry (18.6K persons, surname
    aliases).

    Honest-unknown contract — the crux of the fix: it NEVER guesses and NEVER
    returns the known fighter again. It returns a name only when
      1. exactly one ticker abbrev is a surname-prefix of the known fighter (so we
         know which side is the opponent), AND
      2. the OTHER abbrev resolves to EXACTLY ONE distinct combat person whose
         surname it prefixes, who isn't the known fighter.
    Any ambiguity (0 or >1 matches, can't tell which side is known) -> None, so
    the caller creates no event rather than a duplicate-person degenerate.
    """
    from app.utils.prediction_market_matching import combat_fighter_abbrevs
    from app.utils.event_matcher import player_key

    abbrevs = combat_fighter_abbrevs(external_id)
    if not abbrevs:
        return None
    known_key = player_key(known_fighter)
    if not known_key:
        return None

    # Which abbrev is the known fighter, which is the opponent? Exactly one must
    # prefix the known surname — otherwise we can't tell the sides apart.
    a, b = abbrevs
    a_is_known = known_key.startswith(a)
    b_is_known = known_key.startswith(b)
    if a_is_known and not b_is_known:
        opp_abbrev = b
    elif b_is_known and not a_is_known:
        opp_abbrev = a
    else:
        return None  # ambiguous (neither or both prefix the known fighter)
    if len(opp_abbrev) < 2:
        return None

    # Resolve the opponent abbrev against the registry: a combat-sport person
    # whose surname starts with the abbrev, distinct from the known fighter.
    from sqlalchemy import func, select
    from app.models.models import Entity, EntityAlias
    from app.services.entity_registry import KIND_PERSON

    family = (sport_key or "").split("_")[0].lower()
    stmt = (
        select(func.distinct(Entity.canonical_name))
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(
            Entity.kind == KIND_PERSON,
            EntityAlias.alias_type == "common_name",  # the surname alias
            EntityAlias.alias_norm.like(f"{_escape_like(opp_abbrev)}%", escape="\\"),
        )
    )
    if family:
        stmt = stmt.where(func.lower(Entity.sport_key).like(f"{_escape_like(family)}%", escape="\\"))
    names = [
        n for n in (await session.execute(stmt.limit(5))).scalars().all()
        if player_key(n) != known_key
    ]
    if len(names) == 1:
        return names[0]
    return None  # 0 or ambiguous — honest unknown, no guess


async def _create_event_from_prediction_market(session, matchup, market, now):
    """
    Auto-create an Event when a game-level prediction market has no matching Event.

    This handles sports that The Odds API doesn't cover (e.g., Olympics).
    The prediction market itself becomes the primary data source for the event.

    Returns the same dict format as _find_matching_event, or None if creation fails.
    """
    from app.models.models import Event, Sport, Team
    from app.utils.prediction_market_matching import (
        match_teams_to_event, _strip_sport_name_prefix, _strip_championship_suffix,
    )

    if not matchup or not matchup.team_a:
        return None

    # Q435: a PROP about a tennis match may not invent the match. This is the
    # writer that produced event 15295024 — a second row for Bublik v Wolf,
    # created by a set-winner market while the register's own event already
    # existed — and every prop that followed rendered on the twin. The prop is
    # not absorbed anywhere; it waits for its match segment to resolve.
    from app.utils.prediction_market_matching import is_kalshi_tennis_prop_ticker

    if market.source == "kalshi" and is_kalshi_tennis_prop_ticker(market.external_id):
        logger.debug(
            "Refusing auto-create from tennis prop %s (Q435) — a prop is not "
            "evidence that a match exists",
            market.external_id,
        )
        return None

    # Clean team names: strip sport name prefixes ("Ice Hockey USA" → "USA")
    # and championship suffixes that may leak through ("Canada Medal" → "Canada")
    team_a = _strip_championship_suffix(_strip_sport_name_prefix(matchup.team_a.strip())).strip()
    team_b = _strip_championship_suffix(_strip_sport_name_prefix((matchup.team_b or "").strip())).strip()

    # Determine sport key from ticker or category
    sport_key = get_sport_prefix_from_ticker(market.external_id) if market.external_id else None

    # #175 Item 2 — combat degenerate guard. A fight-winner market names only ONE
    # competitor, so a matchup parsed from it degenerates to "Saint-Denis vs
    # Saint-Denis". Recover the real opponent from the ticker+registry; if we
    # can't (honest unknown), create NO event rather than a duplicate-person one.
    from app.utils.name_normalization import names_match as _names_match
    if team_a and (not team_b or _names_match(team_a, team_b)):
        opponent = await _resolve_combat_opponent(
            session, market.external_id, team_a, sport_key
        )
        if opponent and not _names_match(team_a, opponent):
            team_b = opponent
        else:
            logger.debug(
                "Skipping auto-create for '%s' — degenerate combat matchup "
                "(one fighter, opponent unresolved): %s",
                market.name, team_a,
            )
            return None

    if not team_a or not team_b:
        return None
    if not sport_key and market.llm_sport_category:
        cat_prefix = _SPORT_CATEGORY_TO_KEY_PREFIX.get(market.llm_sport_category)
        if cat_prefix:
            sport_key = f"{cat_prefix}_other"

    if not sport_key:
        logger.debug(
            "Cannot auto-create event for '%s' — no sport key determinable",
            market.name,
        )
        return None

    # NEVER auto-create events for major sports covered by The Odds API.
    # These sports always have events from the Odds API; auto-creating from
    # prediction markets causes duplicates with wrong commence_times
    # (Kalshi uses market resolution date, not game date).
    _ODDS_API_COVERED_PREFIXES = (
        "basketball_nba", "basketball_ncaab", "basketball_wnba",
        "americanfootball_nfl", "americanfootball_ncaaf",
        "baseball_mlb", "icehockey_nhl",
        "soccer_usa_mls",
    )
    if any(sport_key.startswith(prefix) for prefix in _ODDS_API_COVERED_PREFIXES):
        logger.debug(
            "Skipping auto-create for '%s' — sport %s is covered by The Odds API",
            market.name, sport_key,
        )
        return None

    # ── Unified event matching via Event Registry ──
    # Determine commence_time: use market's commence_time if reasonable,
    # otherwise use now (the market is probably live)
    commence_time = market.commence_time
    if not commence_time or abs((commence_time - now).total_seconds()) > 86400 * 30:
        commence_time = now

    # #2020, half one: prefer the TICKER-derived time over Kalshi's own
    # `commence_time`. See `auto_create_commence_time` for the why.
    commence_time, commence_source = auto_create_commence_time(
        market, commence_time,
    )

    # #2020, half two: REFUSE to create a row this pipeline's own guard will
    # refuse to link. See `auto_create_self_refutes` for the measured loop.
    if auto_create_self_refutes(market, commence_time):
        logger.warning(
            "Refusing self-refuting auto-create (#2020): %s would create an event "
            "at commence=%s that _check_duplicate_kalshi_linkage_reason is "
            "guaranteed to refuse — the create cannot converge",
            market.external_id, commence_time.isoformat(),
        )
        return None

    # #2623, and it is the same shape as the refusal above: a create whose row
    # can never become anything a reader wants. See
    # `auto_create_is_stale_fixture` — 0 of 72,796 venue-created events in 14
    # days ever carried a score, and this one's fixture finished more than 36
    # hours ago, so it would be born already-over and render as a FINAL with no
    # result beside the real row that has one.
    if auto_create_is_stale_fixture(commence_time, now):
        logger.warning(
            "Refusing born-finished auto-create (#2623): %s would create an event "
            "at commence=%s, %.1fh in the past — a venue never scores it, so the "
            "row can only ever be an unscored FINAL",
            market.external_id, commence_time.isoformat(),
            (now - commence_time).total_seconds() / 3600.0,
        )
        return None

    status = auto_create_status(commence_time, commence_source, now)
    external_id = f"pm_{market.source}_{market.external_id}"

    from app.services.event_registry import (
        find_or_create_event, EventIdentity, EventClaim,
    )
    identity = EventIdentity(
        sport_key=sport_key,
        home_team_name=team_a,
        away_team_name=team_b,
        commence_time=commence_time,
        # #2020: say where the time came from. `kalshi_ticker` is a strictly
        # better provenance than the bare source name, because it records that
        # this is the TICKER's game time and not Kalshi's close time (gotcha #14)
        # — the distinction the duplicate loop turned on.
        commence_time_source=commence_source,
        # RULING 048: schedule_derived stays FALSE here, deliberately. This is the
        # population the ruling was written for. team_a/team_b were PARSED OUT OF
        # THE MARKET NAME or ticker — a label, not a dereference (ruling 042) — and
        # `commence_time` above may have just been replaced with `now`, which is not
        # a game time at all (gotcha #14). Kalshi and Polymarket also have no id
        # column on `events`, so arm A is unavailable too: there is nothing here to
        # anchor an absorption to, and #1779/#1798 are what absorbing anyway cost.
        #
        # DO NOT set this True to "fix" a duplicate. Duplicates are the declared,
        # bounded price; reconciliation drains them once a real id arrives. Setting
        # it True re-opens the path that blended two games onto one row.
        # `external_id` here is SYNTHETIC — `pm_{source}_{market.external_id}`.
        # `provider_id` carries what Kalshi/Polymarket actually call the thing,
        # which is the only string the anchor channel can key on (#2213). Without
        # it, `kalshi_anchor_key` finds no game token inside the `pm_kalshi_`
        # prefix and degrades to `id_kind='market'` — recorded, and permanently
        # unable to anchor. The rail would have written rows and resolved nothing.
        claim=EventClaim(
            market.source, external_id, provider_id=market.external_id
        ),
        status=status,
    )
    try:
        event, was_created = await find_or_create_event(session, identity)
    except ValueError as e:
        logger.warning(
            "Cannot auto-create event for '%s' — %s",
            market.name, e,
        )
        return None

    # Determine yes_is_home mapping
    team_match = match_teams_to_event(matchup, team_a, team_b, external_id=external_id)
    yes_is_home = team_match["yes_is_home"] if team_match else True

    logger.info(
        "Auto-created event %d for %s market '%s': %s vs %s [sport=%s, status=%s]",
        event.id, market.source, market.name,
        team_a, team_b, sport_key, status,
    )

    return {
        "event_id": event.id,
        "home_team": team_a,
        "away_team": team_b,
        "yes_is_home": yes_is_home,
        "auto_created": True,
    }


# =============================================================================
# Live Game Price Polling
# =============================================================================

async def _poll_live_prediction_market_prices():
    """
    Fast-poll current prices for prediction markets linked to LIVE events.

    Unlike the full Kalshi/Polymarket polling tasks (which run hourly and scan
    the entire catalog), this task is targeted: it only fetches prices for
    markets already linked to events that are currently live. This enables
    2-minute polling frequency without hitting rate limits.

    For Kalshi: Fetches market data via the /markets endpoint filtered by
    event_ticker to get fresh yes_bid/yes_ask.

    For Polymarket: Fetches event data from the Gamma API to get current
    outcomePrices (one call per event).

    After updating FuturesOutcome.current_probability, writes win_prob_snapshots
    so the OddsChart trend line updates in near-real-time.
    """
    import asyncio
    import json

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import (
        FuturesMarket, FuturesOddsSnapshot, FuturesOutcome, Event, WinProbSnapshot,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot
    from app.utils.odds_math import probability_to_american

    stats = {
        "live_events": 0,
        "linked_markets": 0,
        "kalshi_fetched": 0,
        "polymarket_fetched": 0,
        "outcomes_updated": 0,
        "futures_snapshots_written": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "pregame_marks_written": 0,
        "errors": [],
    }

    now = datetime.now(timezone.utc)

    async with get_task_session() as session:
        # Find linked prediction markets where the event is live OR starting
        # within 3 hours. Pre-game prop prices undergo price discovery in the
        # hours before game time — polling only live events misses this entirely
        # and leaves props with 1-2 snapshots from the 2h full-poll interval.
        from datetime import timedelta
        upcoming_cutoff = now + timedelta(hours=3)
        result = await session.execute(
            select(FuturesMarket, Event)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
                or_(
                    Event.status == "live",
                    and_(
                        Event.status == "scheduled",
                        Event.commence_time.isnot(None),
                        Event.commence_time <= upcoming_cutoff,
                        Event.commence_time > now,
                    ),
                ),
            )
        )
        rows = result.all()

        if not rows:
            logger.debug("No live or upcoming linked prediction markets to poll")
            return stats

        live_event_ids = set()
        kalshi_markets = []
        polymarket_markets = []

        for market, event in rows:
            live_event_ids.add(event.id)
            if market.source == "kalshi":
                kalshi_markets.append((market, event))
            else:
                polymarket_markets.append((market, event))

        stats["live_events"] = len(live_event_ids)
        stats["linked_markets"] = len(rows)

        # Batch-load all outcomes for linked markets to avoid N+1
        all_market_ids = [market.id for market, event in rows]
        outcome_lookup = {}
        outcomes_by_market = {}
        if all_market_ids:
            outcomes_result = await session.execute(
                select(FuturesOutcome).where(FuturesOutcome.market_id.in_(all_market_ids))
            )
            for o in outcomes_result.scalars().all():
                if o.external_id:
                    outcome_lookup[(o.market_id, o.external_id)] = o
                outcomes_by_market.setdefault(o.market_id, []).append(o)

        # ── Fetch Kalshi prices ────────────────────────────────────────
        if kalshi_markets:
            from app.services.kalshi_api import KalshiAPIService
            service = KalshiAPIService()
            try:
                for market, event in kalshi_markets:
                    try:
                        # Kalshi external_id is the event ticker
                        markets_data, _ = await service.get_markets(
                            event_ticker=market.external_id,
                            status=None,  # Get all statuses
                            limit=10,
                        )
                        stats["kalshi_fetched"] += 1

                        # Update outcomes with fresh prices
                        for mkt_data in markets_data:
                            yes_bid = mkt_data.get("yes_bid")
                            yes_ask = mkt_data.get("yes_ask")
                            last_price = mkt_data.get("last_price")

                            # Kalshi prices are in cents (0-100)
                            if yes_bid is not None:
                                yes_bid = yes_bid / 100.0
                            if yes_ask is not None:
                                yes_ask = yes_ask / 100.0
                            if last_price is not None:
                                last_price = last_price / 100.0

                            # Prefer last_price (actual traded price) over
                            # bid/ask midpoint. The midpoint oscillates wildly
                            # when the spread widens/narrows on illiquid markets,
                            # creating a jagged chart line that doesn't reflect
                            # real probability changes.
                            if last_price is not None and 0 < last_price < 1:
                                prob = last_price
                            elif yes_bid is not None and yes_ask is not None:
                                prob = (yes_bid + yes_ask) / 2
                            else:
                                continue

                            if prob <= 0 or prob >= 1:
                                continue

                            # Find matching outcome by ticker (batch-loaded)
                            ticker = mkt_data.get("ticker", "")
                            outcome = outcome_lookup.get((market.id, ticker))

                            if not outcome:
                                market_outcomes = outcomes_by_market.get(market.id, [])
                                if len(market_outcomes) == 1:
                                    outcome = market_outcomes[0]
                                else:
                                    continue

                            # Update outcome probability
                            outcome.current_probability = prob
                            outcome.current_yes_bid = yes_bid
                            outcome.current_yes_ask = yes_ask
                            american = probability_to_american(prob) if 0 < prob < 1 else None
                            outcome.current_american_odds = american
                            outcome.last_updated = now
                            stats["outcomes_updated"] += 1

                            # Write FuturesOddsSnapshot for chart history
                            await session.execute(
                                pg_insert(FuturesOddsSnapshot).values(
                                    outcome_id=outcome.id,
                                    bookmaker="kalshi",
                                    probability=prob,
                                    american_odds=american,
                                    yes_bid=yes_bid,
                                    yes_ask=yes_ask,
                                    last_price=last_price,
                                    captured_at=now,
                                )
                            )
                            stats["futures_snapshots_written"] += 1

                        # Rate limit between Kalshi requests
                        await asyncio.sleep(0.3)

                    except Exception as e:
                        stats["errors"].append(f"kalshi_{market.external_id}: {str(e)[:100]}")

            finally:
                await service.close()

        # ── Fetch Polymarket prices ────────────────────────────────────
        if polymarket_markets:
            from app.services.polymarket_api import PolymarketAPIService
            poly_service = PolymarketAPIService()
            try:
                # Group by external_id (Polymarket event ID) to avoid duplicate fetches
                seen_events = {}
                for market, event in polymarket_markets:
                    if market.external_id in seen_events:
                        continue

                    try:
                        event_data = await poly_service.get_event_by_id(market.external_id)
                        stats["polymarket_fetched"] += 1

                        if not event_data:
                            continue

                        seen_events[market.external_id] = event_data

                        # Parse markets from event data
                        poly_markets = event_data.get("markets", [])
                        if not poly_markets:
                            continue

                        for pm in poly_markets:
                            condition_id = pm.get("conditionId", "")

                            # Parse outcomePrices and outcomes (both stringified JSON arrays)
                            prices_raw = pm.get("outcomePrices", "[]")
                            outcomes_raw = pm.get("outcomes", "[]")
                            try:
                                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                                outcomes_names = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if not prices:
                                continue

                            # Find matching outcome by condition_id (batch-loaded)
                            outcome = outcome_lookup.get((market.id, condition_id))
                            if not outcome:
                                continue

                            # Determine the correct price for this outcome.
                            #
                            # Polymarket outcomePrices is parallel to outcomes:
                            #   outcomes: ["Team A", "Team B"]  →  prices: [0.6, 0.4]
                            #
                            # For NegRisk events, each sub-market has outcomes
                            # ["Yes", "No"] where prices[0] = "Yes" probability
                            # for that specific team. prices[0] is always correct.
                            #
                            # For non-NegRisk binary markets with team-name outcomes
                            # (e.g., outcomes: ["Warriors", "Celtics"]), prices[0]
                            # corresponds to the FIRST listed team, not necessarily
                            # the team our outcome record represents. We must match
                            # by name to get the right price.
                            ltp = pm.get("lastTradePrice")
                            best_bid = pm.get("bestBid")
                            best_ask = pm.get("bestAsk")

                            # Skip entirely if no trading activity — stale price from
                            # hours/days ago is worse than no data.
                            if ltp is None and (best_bid is None or float(best_bid) == 0):
                                continue

                            prob = float(prices[0])  # default: outcomePrices midpoint

                            # Prefer lastTradePrice when bid/ask spread is wide (>15pp).
                            # During blowouts, the order book becomes illiquid and the
                            # midpoint is meaningless (e.g., bid=0.34 ask=0.43 → mid=0.385
                            # but the game is effectively over).
                            if (ltp is not None
                                and best_bid is not None and best_ask is not None):
                                spread = abs(float(best_ask) - float(best_bid))
                                if spread > 0.15 and 0 < float(ltp) < 1:
                                    prob = float(ltp)

                            if (
                                len(outcomes_names) >= 2
                                and len(prices) >= 2
                                and outcome.name
                                and outcomes_names[0].lower().strip() not in ("yes", "no", "")
                            ):
                                # Non-generic outcome names — find which price
                                # index corresponds to this outcome's team
                                outcome_name_lower = outcome.name.lower().strip()
                                for idx, oname in enumerate(outcomes_names):
                                    if idx < len(prices) and _fuzzy_team_match(
                                        outcome_name_lower, oname
                                    ):
                                        prob = float(prices[idx])
                                        break

                            if prob <= 0 or prob >= 1:
                                continue

                            # Update outcome probability
                            outcome.current_probability = prob
                            american = probability_to_american(prob) if 0 < prob < 1 else None
                            outcome.current_american_odds = american

                            # Parse bid/ask if available
                            best_bid = pm.get("bestBid")
                            best_ask = pm.get("bestAsk")
                            if best_bid is not None:
                                outcome.current_yes_bid = float(best_bid)
                            if best_ask is not None:
                                outcome.current_yes_ask = float(best_ask)

                            outcome.last_updated = now
                            stats["outcomes_updated"] += 1

                            # Write FuturesOddsSnapshot for chart history
                            best_bid_val = float(best_bid) if best_bid is not None else None
                            best_ask_val = float(best_ask) if best_ask is not None else None
                            ltp_val = float(ltp) if ltp is not None else None
                            await session.execute(
                                pg_insert(FuturesOddsSnapshot).values(
                                    outcome_id=outcome.id,
                                    bookmaker="polymarket",
                                    probability=prob,
                                    american_odds=american,
                                    yes_bid=best_bid_val,
                                    yes_ask=best_ask_val,
                                    last_price=ltp_val,
                                    captured_at=now,
                                )
                            )
                            stats["futures_snapshots_written"] += 1

                        # Rate limit between Polymarket requests
                        await asyncio.sleep(0.3)

                    except Exception as e:
                        stats["errors"].append(f"polymarket_{market.external_id}: {str(e)[:100]}")

            finally:
                await poly_service.close()

        # ── Write win_prob_snapshots for all live linked markets ───────
        # Re-query to pick up freshly-updated probabilities.
        #
        # DEDUP: Kalshi creates separate binary markets per team outcome
        # (e.g., "Celtics win?" and "76ers win?" for the same game). Both
        # are linked to the same event. We pick a primary market for
        # processing but AVERAGE both sides to cancel vig when computing
        # the home probability.
        all_per_event_source_live: dict[tuple[int, str], list[tuple]] = {}
        for market, event in rows:
            key = (event.id, market.source)
            if key not in all_per_event_source_live:
                all_per_event_source_live[key] = []
            all_per_event_source_live[key].append((market, event))

        # Q460: primary selection + moneyline + devig now live in
        # `app/utils/live_blend.py`, because the WebSocket fast lane writes this
        # same blend key between polls and the two writers must agree exactly.
        # A second copy of this arithmetic would not throw when it drifted — the
        # hero would just flicker between two opinions every two minutes.
        def _group_for(key) -> list[_LiveBlendGroup]:
            return [
                _LiveBlendGroup(market=m, outcomes=outcomes_by_market.get(m.id, []))
                for m, _e in all_per_event_source_live.get(key, [])
            ]

        best_per_event_source: dict[tuple[int, str], tuple] = {}
        for key, group in all_per_event_source_live.items():
            primary_entry = _select_primary_market(
                [
                    _LiveBlendGroup(market=m, outcomes=outcomes_by_market.get(m.id, []))
                    for m, _e in group
                ]
            )
            if primary_entry is None:
                continue
            for market, event in group:
                if market.id == primary_entry.market.id:
                    best_per_event_source[key] = (market, event)
                    break

        for market, event in best_per_event_source.values():
            try:
                reading = _compute_source_home_probability(
                    _group_for((event.id, market.source)),
                    event.home_team_name,
                    event.away_team_name,
                )
                if reading is None:
                    continue
                home_prob = reading.home_probability
                outcome = reading.outcome
                yes_prob = reading.yes_probability

                # Cross-check against sportsbook consensus to catch inversions
                home_prob = await _check_and_fix_inversion(
                    session, event.id, home_prob, market.source,
                )
                away_prob = 1.0 - home_prob

                # Write snapshot with deduplication
                snapshot, is_new = await _create_or_update_win_prob_snapshot(
                    session,
                    event_id=event.id,
                    source=market.source,
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    game_state={
                        "market_name": market.name,
                        "market_id": market.id,
                        "outcome_name": outcome.name,
                        "yes_probability": yes_prob,
                        "yes_bid": float(outcome.current_yes_bid) if outcome.current_yes_bid else None,
                        "yes_ask": float(outcome.current_yes_ask) if outcome.current_yes_ask else None,
                        "poll_type": "live_fast",
                    },
                )

                if is_new:
                    session.add(snapshot)
                    stats["snapshots_written"] += 1
                else:
                    stats["snapshots_deduped"] += 1

                # Write to win_probability_sources on the event
                from sqlalchemy import update as _sql_upd2
                from app.utils.aggregation import stamp_source_reading as _stamp2
                _pm_r2 = await session.execute(
                    select(Event.win_probability_sources).where(Event.id == event.id)
                )
                # #1829: value + write time.
                _pm_wps2 = _stamp2(
                    _pm_r2.scalar_one_or_none(), market.source, round(home_prob, 4)
                )
                await session.execute(
                    _sql_upd2(Event)
                    .where(Event.id == event.id)
                    .values(win_probability_sources=_pm_wps2)
                )

            except Exception as e:
                stats["errors"].append(f"snapshot_{market.id}: {str(e)[:100]}")

        # ── #195: pregame-mark pinning (THE SCRIPT baseline for props) ────
        # At/just-before commence, snapshot each linked market's current
        # per-outcome probabilities into market_metadata["pregame_mark"], the
        # divergence baseline the event page renders as THE SCRIPT (pregame
        # expectation) vs THE DIVERGENCE (live movement). Piggybacks on the
        # existing poll loop — no new scan (the rows/outcomes are already loaded
        # and freshly re-priced above). Idempotent: the first mark per market is
        # captured and never overwritten (Python skip + a NOT jsonb_exists SQL
        # guard for the concurrent-poll case). Core JSONB merge (gotcha #4) via
        # CAST to dodge the asyncpg ':param::jsonb' bind trap, preserving any
        # existing keys (shape, discover_llm, ...).
        pregame_cutoff = now + timedelta(minutes=_PREGAME_MARK_LEAD_MINUTES)
        for market, event in rows:
            commence = event.commence_time
            if commence is None:
                continue
            # Fire once the game is inside the final lead window or has started —
            # this captures the settled pregame consensus, not a stale opening.
            if commence > pregame_cutoff:
                continue
            existing_meta = market.market_metadata or {}
            if isinstance(existing_meta, dict) and "pregame_mark" in existing_meta:
                continue
            outcome_probs = {}
            for o in outcomes_by_market.get(market.id, []):
                if o.current_probability is not None:
                    outcome_probs[str(o.id)] = round(float(o.current_probability), 6)
            if not outcome_probs:
                continue
            mark_payload = {
                "captured_at": now.isoformat(),
                "commence_time": commence.isoformat(),
                "outcomes": outcome_probs,
            }
            try:
                await session.execute(
                    text(
                        "UPDATE futures_markets SET market_metadata = "
                        "COALESCE(market_metadata, '{}'::jsonb) "
                        "|| jsonb_build_object('pregame_mark', CAST(:mark AS jsonb)) "
                        "WHERE id = :id "
                        "AND NOT jsonb_exists("
                        "COALESCE(market_metadata, '{}'::jsonb), 'pregame_mark')"
                    ),
                    {"mark": json.dumps(mark_payload), "id": market.id},
                )
                stats["pregame_marks_written"] += 1
            except Exception as e:
                stats["errors"].append(f"pregame_mark_{market.id}: {str(e)[:100]}")

        await session.commit()

    logger.info(
        "Live prediction market poll: events=%d, markets=%d, "
        "kalshi=%d, polymarket=%d, outcomes=%d, "
        "futures_snaps=%d, wp_snaps=%d (deduped=%d)",
        stats["live_events"], stats["linked_markets"],
        stats["kalshi_fetched"], stats["polymarket_fetched"],
        stats["outcomes_updated"], stats["futures_snapshots_written"],
        stats["snapshots_written"], stats["snapshots_deduped"],
    )
    return stats


async def _backfill_polymarket_win_prob_history(
    market_id: int,
    event_id: int,
    fidelity: int = 30,
    interval: str = "max",
):
    """
    Backfill win_prob_snapshots from Polymarket's CLOB price history.

    When a Polymarket market is first linked to an event, we only have
    the current price. This function fetches the full price history from
    the CLOB API and writes it as win_prob_snapshots, giving us a complete
    trend line from market creation onward.

    Args:
        market_id: FuturesMarket.id (our internal ID)
        event_id: Event.id to write snapshots against
        fidelity: Price data granularity in minutes (30 = every half hour)
        interval: Time range ('1h', '6h', '1d', '1w', 'max')
    """
    import asyncio
    import json

    from app.models.models import (
        FuturesMarket, FuturesOutcome, Event, WinProbSnapshot,
    )

    stats = {
        "snapshots_created": 0,
        "errors": [],
    }

    async with get_task_session() as session:
        # Load market and event
        market = await session.get(FuturesMarket, market_id)
        event = await session.get(Event, event_id)
        if not market or not event:
            stats["errors"].append("market or event not found")
            return stats
        if market.source != "polymarket":
            stats["errors"].append("not a polymarket market")
            return stats

        # Extract matchup and find moneyline outcome
        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )
        if not matchup:
            stats["errors"].append("no matchup extracted")
            return stats

        outcome_result = await session.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market.id)
            .order_by(FuturesOutcome.rank)
        )
        all_outcomes = outcome_result.scalars().all()
        if not all_outcomes:
            stats["errors"].append("no outcomes")
            return stats

        ml_result = find_moneyline_outcome(
            all_outcomes, matchup,
            event.home_team_name, event.away_team_name,
        )
        if not ml_result:
            stats["errors"].append("no moneyline outcome found")
            return stats

        outcome, yes_is_home = ml_result
        moneyline_condition_id = outcome.external_id

        # Fetch the Polymarket event to get clobTokenIds
        from app.services.polymarket_api import PolymarketAPIService
        service = PolymarketAPIService()
        try:
            event_data = await service.get_event_by_id(market.external_id)
            if not event_data:
                stats["errors"].append("failed to fetch polymarket event")
                return stats

            # Find the clobTokenId for our moneyline outcome's conditionId
            token_id = None
            for pm in event_data.get("markets", []):
                if pm.get("conditionId") == moneyline_condition_id:
                    clob_ids_raw = pm.get("clobTokenIds", "[]")
                    try:
                        if isinstance(clob_ids_raw, str):
                            clob_ids = json.loads(clob_ids_raw)
                        else:
                            clob_ids = clob_ids_raw
                    except (json.JSONDecodeError, TypeError):
                        clob_ids = []
                    if clob_ids:
                        token_id = clob_ids[0]  # First token = "Yes" side
                    break

            if not token_id:
                stats["errors"].append(
                    f"no clobTokenId for conditionId {moneyline_condition_id}"
                )
                return stats

            # Fetch price history
            history = await service.get_prices_history(
                token_id=token_id,
                interval=interval,
                fidelity=fidelity,
            )
            if not history:
                stats["errors"].append("empty price history")
                return stats

            logger.info(
                "Backfilling %d Polymarket price points for market %d → event %d",
                len(history), market_id, event_id,
            )

            # Check for inversion against sportsbook consensus ONCE before
            # writing the entire history (avoids N queries in the loop).
            # Use a mid-history sample point to determine if we need to flip.
            sample_idx = len(history) // 2
            sample_price = history[sample_idx].get("p") if history else None
            needs_flip = False
            if sample_price is not None:
                sample_yes = float(sample_price)
                if 0 < sample_yes < 1:
                    if yes_is_home:
                        sample_home = sample_yes
                    else:
                        sample_home = 1.0 - sample_yes
                    checked = await _check_and_fix_inversion(
                        session, event_id, sample_home, "polymarket",
                    )
                    needs_flip = abs(checked - sample_home) > 0.01

            # Write win_prob_snapshots from price history
            for point in history:
                ts = point.get("t")
                price = point.get("p")
                if ts is None or price is None:
                    continue

                yes_prob = float(price)
                if yes_prob <= 0 or yes_prob >= 1:
                    continue

                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob

                # Apply inversion fix if detected from sample
                if needs_flip:
                    home_prob = 1.0 - home_prob
                away_prob = 1.0 - home_prob

                captured_at = datetime.fromtimestamp(ts, tz=timezone.utc)

                snapshot = WinProbSnapshot(
                    event_id=event_id,
                    source="polymarket",
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    captured_at=captured_at,
                    game_state={
                        "market_id": market_id,
                        "backfill": True,
                    },
                )
                session.add(snapshot)
                stats["snapshots_created"] += 1

            await session.commit()

        finally:
            await service.close()

    logger.info(
        "Polymarket win_prob backfill: market=%d event=%d snapshots=%d errors=%d",
        market_id, event_id, stats["snapshots_created"], len(stats["errors"]),
    )
    return stats


async def _backfill_historical_links(batch_size: int = 100):
    """Link past-game Kalshi AND Polymarket markets to their (now closed) events.

    The live matching task skips closed/completed events (past_cutoff filter).
    This backfill removes that filter to link markets for games that already
    happened. Idempotent: marks failed attempts in market_metadata so we
    don't re-check the same markets every run.

    Handles both sources:
    - Kalshi: ticker-based game detection + ticker date for time window
    - Polymarket: name-based game detection + commence_time for time window
    """
    from app.models.models import FuturesMarket, Event
    from sqlalchemy import text as _text, update as _update

    stats = {
        "scanned": 0, "linked": 0, "no_match": 0, "errors": [],
        "by_source": {"kalshi": {"scanned": 0, "linked": 0}, "polymarket": {"scanned": 0, "linked": 0}},
    }
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    async with get_task_session() as session:
        # ── Kalshi: ticker-prefix detection ──
        ticker_conditions = [
            func.lower(FuturesMarket.external_id).like(f"{p}%")
            for p in _KALSHI_GAME_TICKER_PREFIXES
        ]
        kalshi_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.is_(None),
                or_(*ticker_conditions),
                or_(
                    FuturesMarket.market_metadata.is_(None),
                    ~FuturesMarket.market_metadata.has_key("backfill_link_failed"),
                ),
                FuturesMarket.commence_time < cutoff,
            )
            .order_by(FuturesMarket.commence_time.asc())
            .limit(batch_size)
        )
        kalshi_markets = kalshi_result.scalars().all()

        # ── Polymarket: fetch candidates, filter through is_game_level_market() in Python ──
        _SUPPORTED_SPORT_CATS = [
            "basketball", "baseball", "hockey", "soccer", "football",
            "tennis", "mma", "rugby", "lacrosse", "cricket",
        ]
        poly_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.is_(None),
                FuturesMarket.llm_sport_category.in_(_SUPPORTED_SPORT_CATS),
                or_(
                    FuturesMarket.market_metadata.is_(None),
                    ~FuturesMarket.market_metadata.has_key("backfill_link_failed"),
                ),
                FuturesMarket.commence_time < cutoff,
            )
            .order_by(FuturesMarket.commence_time.asc())
            .limit(batch_size * 3)
        )
        poly_candidates = poly_result.scalars().all()
        poly_markets = [
            m for m in poly_candidates
            if is_game_level_market(m.name, m.category, external_id=m.external_id)
        ][:batch_size]

        all_markets = kalshi_markets + poly_markets

        for market in all_markets:
            stats["scanned"] += 1
            src = market.source
            stats["by_source"][src]["scanned"] += 1
            try:
                matchup = extract_matchup_with_ticker_fallback(
                    market.name, external_id=market.external_id,
                )
                if not matchup or not matchup.team_b:
                    await _mark_backfill_failed(session, market)
                    stats["no_match"] += 1
                    continue

                # Determine time reference: Kalshi uses ticker date, Polymarket uses commence_time
                if src == "kalshi":
                    ref_time = extract_game_date_from_ticker(market.external_id)
                    if not ref_time:
                        await _mark_backfill_failed(session, market)
                        stats["no_match"] += 1
                        continue
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)
                else:
                    ref_time = market.commence_time
                    if not ref_time:
                        await _mark_backfill_failed(session, market)
                        stats["no_match"] += 1
                        continue
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)

                matched = await _find_historical_event(
                    session, matchup, market, ref_time,
                )
                # #210 Item 1c: the historical backfill also bypassed the
                # duplicate-linkage guard. Route it through the same check so a
                # past-game market can't pile onto an event that already holds a
                # different-dated game market. Kalshi ref_time IS the ticker game
                # date; polymarket short-circuits to True inside the guard.
                refusal = None
                if matched:
                    refusal = await _check_duplicate_kalshi_linkage_reason(
                        session, matched["event_id"], market,
                        ref_time if src == "kalshi" else None,
                    )
                if refusal:
                    logger.info(
                        "Backfill linkage blocked (%s): %s %s would collide with "
                        "a different-dated game on event %d",
                        refusal, src, market.external_id or market.name[:40],
                        matched["event_id"],
                    )
                    # This stats dict has no "funnel" sub-dict; the counters are
                    # top-level here but keep the same (a)/(b) split (#1811).
                    key = (
                        "event_date_linkage_blocked"
                        if refusal == _REFUSAL_EVENT_DATE
                        else "duplicate_linkage_blocked"
                    )
                    stats.setdefault(key, 0)
                    stats[key] += 1
                    await _mark_backfill_failed(session, market)
                    stats["no_match"] += 1
                    matched = None
                if matched:
                    eid = matched["event_id"]
                    await session.execute(
                        _update(FuturesMarket)
                        .where(FuturesMarket.id == market.id)
                        .values(event_id=eid)
                    )
                    stats["linked"] += 1
                    stats["by_source"][src]["linked"] += 1
                    logger.info(
                        "Backfill linked %s %s → event %d (%s vs %s)",
                        src, market.external_id or market.name[:40],
                        eid, matched["home_team"], matched["away_team"],
                    )
                    if market.group_id and src == "polymarket":
                        from sqlalchemy import text as _sql_text
                        await session.execute(_sql_text("""
                            UPDATE futures_markets
                            SET event_id = :eid
                            WHERE group_id = :gid
                              AND group_type = 'polymarket_sub_market'
                              AND (event_id IS NULL OR event_id != :eid)
                        """), {"eid": eid, "gid": market.group_id})
                else:
                    await _mark_backfill_failed(session, market)
                    stats["no_match"] += 1

                if stats["scanned"] % 20 == 0:
                    await session.commit()

            except Exception as e:
                logger.error("Backfill error for %s: %s", market.external_id or market.id, e)
                stats["errors"].append(str(e))

        await session.commit()

    logger.info(
        "Historical link backfill: scanned=%d linked=%d no_match=%d errors=%d",
        stats["scanned"], stats["linked"], stats["no_match"], len(stats["errors"]),
    )
    return stats


async def _mark_backfill_failed(session, market):
    """Mark a market as attempted-and-failed so we skip it next run."""
    from app.models.models import FuturesMarket
    from sqlalchemy import update

    meta = dict(market.market_metadata) if market.market_metadata else {}
    meta["backfill_link_failed"] = True
    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == market.id)
        .values(market_metadata=meta)
    )


async def _find_historical_event(session, matchup, market, ref_time):
    """Like _find_matching_event but without status/past_cutoff filters.

    Args:
        ref_time: For Kalshi = ticker-extracted game date (precise).
                  For Polymarket = commence_time (approximate, wider window).
    """
    from app.models.models import Event

    teams_to_search = [matchup.team_a]
    if matchup.team_b:
        teams_to_search.append(matchup.team_b)

    ilike_conditions = []
    for team in teams_to_search:
        for search_term in _expand_team_search_terms(team):
            pattern = f"%{_escape_like(search_term)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

    if market.source == "kalshi":
        time_start = ref_time - timedelta(hours=6)
        time_end = ref_time + timedelta(hours=30)
    else:
        time_start = ref_time - timedelta(hours=48)
        time_end = ref_time + timedelta(hours=48)

    event_result = await session.execute(
        select(Event)
        .options(joinedload(Event.sport))
        .where(
            or_(*ilike_conditions),
            Event.commence_time.between(time_start, time_end),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().unique().all()

    result = _score_candidates(candidates, matchup, market, ref_time, ref_time)
    if result and result.get("score", 0) < 15:
        logger.debug(
            "Backfill rejecting low-confidence match (score=%d) for %s",
            result["score"], market.external_id or market.name[:40],
        )
        return None
    return result
