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
from typing import Optional

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
    auto_create_sport_key_from_category,
    MAX_TIME_DELTA,
    MAX_PAST_GAME_DELTA,
)
from app.utils.live_blend import (
    MarketOutcomes as _LiveBlendGroup,
    compute_source_home_probability as _compute_source_home_probability,
    select_primary_market as _select_primary_market,
)
from app.utils import match_receipts as _receipts
from app.utils import matcher_pass_runs as _pass_runs
from app.utils.match_receipts import (
    CandidateTrace,
    MatchReceipt,
    flush_receipts,
    verify_links_are_durable,
)

logger = logging.getLogger(__name__)

# #195: how far ahead of commence the live poller pins THE SCRIPT pregame mark.
# The poll already covers scheduled events within +3h; the mark is captured only
# in the final window before (or after) commence so it reflects the settled
# pregame consensus rather than a stale hours-out price.
_PREGAME_MARK_LEAD_MINUTES = 15

# live/035: the cadence floor this 120s poll enforces on a LIVE event's chart.
# The WS fast lane (`live_blend_refresh`, 45s worst case) is the primary
# guarantee; this is the backstop for the sources and dynos it does not cover,
# so it is derived from the poll's OWN 120s period rather than from the WS one.
# 60s here would be observed 180s late — see `live_blend_refresh.heartbeat_deadline`
# for why a deadline must be the target minus the sampling period.
_LIVE_SNAPSHOT_HEARTBEAT_S = 60.0

# ── Matching receipts (#2705) ───────────────────────────────────────────────
# Group/container rows: a parent describes a set of sub-markets, and it is the
# SUB-markets that attach to an event (see the group_id propagation in
# _try_link_market). Recording the parent as "parent_row" rather than letting it
# fall through to "not_game_level" keeps the not-game-level bucket meaning what
# it says — a futures/award/prop market — so the reconciliation job's counts are
# about matching and not about row kinds.
_PARENT_GROUP_TYPES = frozenset({
    "polymarket_event", "kalshi_event", "negrisk",
})

# The candidate probe (the query that separates "no such event exists" from
# "the event exists but sits outside the window we searched") is one extra
# ILIKE per FAILED attempt. Failures are the majority of the population, so it
# is bounded two ways: a wide-but-indexed commence_time bracket, and a floor on
# the task's remaining time. When the floor is hit the receipt says so rather
# than silently reporting the weaker reason as if it had been checked.
_PROBE_PAST_DAYS = 45
_PROBE_FUTURE_DAYS = 120
_PROBE_MIN_SECONDS_REMAINING = 90
# How many rows either probe arm may return. It is a bound on EVIDENCE, never on
# the answer: the covering arm filters to rows carrying the whole matchup before
# the LIMIT applies, so what survives the cut is what the question asked for. It
# was the opposite before — a broad OR ordered by commence_time, cut at 5, with
# `covering_hits` counted over whatever the cut happened to leave (103 of 109
# live NCAAF rejects filled it exactly, CERT-810). When the broad arm is the one
# that ran and it fills up, the receipt now records `saturated`.
_PROBE_LIMIT = 5

# The whole cycle's wall-clock budget. Every floor and yield point below is
# carved out of it, so it is a module constant rather than a local: a harness
# that charges a fake clock has to charge the SAME budget production runs on,
# and a test that copies the number is a test that can quietly stop describing
# the task (CERT-837 follow-up).
_TIME_BUDGET_SECONDS = 780

# Phase 1 Pass 3 — the backlog sweep that makes "never attempted" impossible.
# Pass 2 orders by updated_at DESC and takes the top `limit` rows, so an older
# ingest wave behind 21k unlinked markets is never reached: measured 2026-09-02,
# all three zero-link US Open Polymarket groups were the 8/28 wave and every
# 8/31+ group linked (ARTIFACT-M-20260902-N). This pass orders by receipt
# staleness with NULLS FIRST, so the market nobody has ever looked at is always
# at the front of the queue and no wave can starve behind a newer one.
#
# The cap is explicit and REPORTED (stats["funnel"]["backlog_dropped"]): a
# silent truncation would read as "we attempted everything" when we did not,
# which is the failure this whole pass exists to end.
_BACKLOG_SCAN_MAX = 3000
# Pass 3 runs BEFORE Phase 1.5 / the relinkers / Phase 2, and Phase 2 is the one
# that writes win_prob_snapshots — the chart line on every live card. Measured
# task cost is 337s p50 / 699s p95 against an 840s soft limit, so a sweep that
# spent the slack would push Phase 2 into `phase2_skipped_budget` and take the
# US Open charts down to buy a diagnosis. It therefore holds a hard RESERVE for
# everything downstream of it: it will not start without the reserve free, and
# it stops the moment it would eat into it.
_BACKLOG_DOWNSTREAM_RESERVE_SECONDS = 420
_BACKLOG_MIN_SECONDS_REMAINING = 480

# ── The upstream passes yield above Pass 3's floor (CERT-817 repair) ────────
# THIS IS WHY PASS 3 HAD STILL NEVER RUN. Passes 1 and 2 both looped until only
# 120s of the 780s budget remained, and Pass 3 refuses to start below 480s — so
# on any cycle with enough work to fill the budget, Pass 3 was unreachable no
# matter what it was ordered by. #2798 cutting Pass 1's population from 138,676
# to 7,447 was necessary and NOT sufficient: at the measured ~12.5 markets/s
# that is still ~596s, leaving 184s, and Pass 3 skipped again. A floor nobody
# can reach is not a guarantee, and `backlog_skipped_budget` was the only thing
# saying so.
#
# So the two upstream passes now stand down ABOVE Pass 3's floor rather than
# running to the end of the budget. Every number is DERIVED from the floor it
# has to protect, so the four cannot drift apart the way 120 and 480 did.
#
# THIS TRADES TOTAL ATTEMPTS FOR REACH, deliberately. Pass 1 attempts fewer
# markets per cycle than it did; the ones it drops are the tail of an
# `updated_at DESC` scan that re-reads the same head every 15 minutes, and Pass
# 3 takes them never-attempted-first, which is the ship #2705 was built for and
# has never once delivered in production.
#: Slack between Pass 2 standing down and Pass 3 testing its floor, so one
#: long-running final attempt cannot push Pass 3 back under it.
_PASS3_START_CUSHION_SECONDS = 15
#: Pass 2's share. It is the smallest of the three because Pass 3 runs the same
#: `_attempt_market` over a strictly better-ordered queue.
_PASS2_SHARE_SECONDS = 60
_PASS2_YIELD_AT_SECONDS_REMAINING = (
    _BACKLOG_MIN_SECONDS_REMAINING + _PASS3_START_CUSHION_SECONDS
)
_PASS1_YIELD_AT_SECONDS_REMAINING = (
    _PASS2_YIELD_AT_SECONDS_REMAINING + _PASS2_SHARE_SECONDS
)

# The settled sweep (#2798). A settled market cannot link — the event population
# for a past date is frozen — but Pass 1 had no status predicate at all, so it
# re-attempted them forever: measured on production 2026-09-03, 7,464 of the
# 7,642 receipts written in an hour sat on `status='resolved'` rows, worst
# attempt_count 40, and the whole receipts table carried ONE phase, `pass1_ticker`
# — Passes 2 and 3 had never written a row, because Pass 1 spent the budget
# before they could start. Excluding the settled rows is therefore not a saving,
# it is what lets the rest of Phase 1 run at all.
#
# The cap exists because the exclusion must not silently re-open the "never
# attempted" hole: a market that leaves the scan says so, once, and the drain of
# the rows that left it before this shipped is bounded per run so the stamp can
# never cost a matching pass. Ordered newest-attempt-first (gotcha #41: ask what
# the ordering STARTS on) — the bus asks about the game that settled last night,
# not the 2025 ITF tail — and each stamped row is permanently excluded by the
# selection, so no ordering can starve the tail.
_SETTLED_SWEEP_MAX = 5000
_SETTLED_SWEEP_MIN_SECONDS_REMAINING = 600


def _new_receipt(market, phase: str, now: datetime) -> MatchReceipt:
    """Open a receipt for one attempt. Every scanned market gets one."""
    return MatchReceipt(
        market_id=market.id,
        source=market.source,
        external_id=market.external_id,
        market_name=market.name,
        phase=phase,
        attempted_at=now,
    )


def _record_link_change(
    sink: Optional[list[MatchReceipt]], market, phase: str, now: datetime,
) -> MatchReceipt:
    """Open a receipt for a link this pass is about to END or MOVE.

    Returns the receipt whether or not ``sink`` is collecting, so the call site
    reads the same either way — ``_record_link_change(...).unlink(42)`` — and a
    caller that opted out cannot accidentally skip the ``.unlink()`` and leave
    the receipt half-built. The discarded object costs one allocation on a path
    that is already doing a database write.

    ``market`` is duck-typed: Phase 1.5 passes ORM rows and the Polymarket
    sibling arm passes result tuples, and both carry the five denormalized
    fields a receipt keeps. Never touch a relationship here — this runs inside a
    loop with rollback boundaries, and a lazy load on an expired row would turn
    bookkeeping into the thing that raises (gotcha #6).
    """
    receipt = MatchReceipt(
        market_id=market.id,
        source=market.source,
        external_id=market.external_id,
        market_name=market.name,
        phase=phase,
        attempted_at=now,
    )
    if sink is not None:
        sink.append(receipt)
    return receipt


async def _receipt_bulk_moves(
    moves: list[tuple[Optional[int], int, dict]], *, phase: str, label: str,
) -> int:
    """Receipt a set of link MOVES made by one bulk SQL pass. Never raises.

    ``moves`` is ``(from_event_id, to_event_id, market_row)``. Rows with no
    previous event are dropped: those are first attaches, which the forward
    path already receipts, and calling them moves would inflate the very census
    this exists to make trustworthy.

    Grouped by ``(from, to)`` so one merge-shaped move of a whole group is one
    round trip rather than one per market — these passes move hundreds of rows
    in a run, and the record must stay cheaper than the thing it records.
    """
    grouped: dict[tuple[int, int], list[dict]] = {}
    for from_eid, to_eid, row in moves:
        if not from_eid or from_eid == to_eid:
            continue
        grouped.setdefault((int(from_eid), int(to_eid)), []).append(row)
    if not grouped:
        return 0

    written = 0
    for (from_eid, to_eid), rows in grouped.items():
        written += await _receipts.record_link_change_receipts(
            rows,
            previous_event_id=from_eid,
            new_event_id=to_eid,
            actor=_receipts.ACTOR_MATCHER_PASS,
            phase=phase,
        )
    if written != sum(len(v) for v in grouped.values()):
        logger.warning(
            "%s: %d link moves, %d receipted — the census will under-report",
            label, sum(len(v) for v in grouped.values()), written,
        )
    return written


def _receipt_parent_or_not_game_level(market, receipt: MatchReceipt) -> bool:
    """Classify a non-game row. Returns True when the row is a parent/container."""
    if (getattr(market, "group_type", None) or "") in _PARENT_GROUP_TYPES:
        receipt.reject(
            _receipts.REJECT_PARENT_ROW, group_type=market.group_type,
            group_id=market.group_id,
        )
        return True
    return False


def _reason_from_traces(traces: list[CandidateTrace]) -> str | None:
    """The reject reason implied by what happened to the candidates.

    Most specific wins. ``name_score_below`` beats everything (a candidate got
    all the way to a score and was still refused). ``wrong_sport`` beats
    ``name_mismatch`` because a candidate that reached the sport gate had
    already passed the name gate — reporting it as a name problem would send
    the next reader looking in the wrong place.

    A RETRIEVED ROW IS NOT A CANDIDATE. Returning ``name_mismatch`` for any
    non-empty trace was a lie. The retrieval ILIKE fires on ONE token, so a
    market whose game we simply do not carry still comes back holding rows —
    "Merrimack vs Maine" retrieves *Merrimack Warriors @ Delaware* and *Maine
    Black Bears @ Appalachian State*, two different games, each covering one
    side. Reported as ``name_mismatch``, that reads as "our fuzzy gate is too
    strict" and points the next reader at a matcher bug that is not there.

    So when nothing covered the whole matchup, this returns ``None`` — the same
    answer it gives for no rows at all — and :func:`_record_no_match_reason`
    runs its probe, which is the code that can tell an upstream gap
    (``no_candidate``) from a window or status bug (``outside_time_window`` /
    ``state_disagrees``). That is the distinction CLAUDE.md asks every matching
    fix to make, and it was unreachable before: ``no_candidate`` fired **once**
    in 333 rows, because a one-token coincidence always pre-empted it.

    THE OTHER DIRECTION IS THE WORSE LIE. Deferring a row that really is the
    game sends a genuine name-gate failure — ours, and fixable — into the
    upstream-absence bucket, where nobody will look for it. That is why
    coverage is measured by :func:`app.utils.match_receipts.row_coverage` and
    not by the gate under diagnosis, and why it is biased toward covered.
    Measured over the 222 ``name_mismatch`` receipts on production's open
    unlinked markets (2026-09-03): 109 stay ``name_mismatch`` (real gate
    failures — "CLE Browns" vs "Cleveland Browns", "LSU" vs "LSU Tigers", "The
    Citadel" vs "Citadel Bulldogs"), 113 defer to the probe.

    Traces from a matcher that never recorded coverage (``sides_named`` None)
    keep the old behaviour, so this cannot silently reclassify a caller that
    has not been taught to measure.
    """
    if not traces:
        return None
    verdicts = {t.verdict for t in traces}
    if _receipts.REJECT_NAME_SCORE_BELOW in verdicts:
        return _receipts.REJECT_NAME_SCORE_BELOW
    if _receipts.REJECT_WRONG_SPORT in verdicts:
        return _receipts.REJECT_WRONG_SPORT
    measured = [t for t in traces if t.sides_named is not None]
    if measured and not any(t.covers_matchup for t in measured):
        return None
    return _receipts.REJECT_NAME_MISMATCH


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
    def id(self) -> int:
        """Alias so this scalar copy IS a `live_blend.MarketOutcomes.market`.

        That protocol wants ``id``/``source``/``external_id``/``name``; this row
        already carries the other three under the same names. Aliasing here is
        what lets Phase 2 hand its scalar copies straight to the ONE shared
        blend decision without first re-loading ORM markets it deliberately
        does not hold (see this class's docstring — it exists precisely because
        Phase 2 commits and rolls back per group).
        """
        return self.market_id

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
    *, receipt=None,
) -> None:
    """Link a matched market to its event, or auto-create an event if needed.

    ``receipt`` (#2705) is write-only: the outcome of this call is the outcome
    the receipt records. Note that this is where the two REFUSALS live —
    ``_find_matching_event`` can hand back a perfectly good event that the
    duplicate-linkage guard then declines, and before receipts that refusal
    left the market indistinguishable from one with no candidate at all.
    """
    from app.models.models import FuturesMarket

    if matched_event:
        refusal = await _check_duplicate_kalshi_linkage_reason(
            session, matched_event["event_id"], market, ticker_game_date,
        )
        if refusal:
            if receipt is not None:
                receipt.reject(
                    _receipts.REJECT_EVENT_DATE_CONFLICT
                    if refusal == _REFUSAL_EVENT_DATE
                    else _receipts.REJECT_ALREADY_LINKED_ELSEWHERE,
                    refused_event_id=matched_event["event_id"],
                    refusal=refusal,
                )
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
        # Scalars BEFORE the commit, enqueued AFTER it (CERT-774). A failed
        # commit rolls back and expires every ORM row in the session (gotcha
        # #6), so reading ``market.id`` afterwards raises — and a request
        # enqueued before the commit would ask the backfill to fetch history
        # for a link that does not exist.
        backfill_request = (
            (int(market.id), matched_event["event_id"])
            if market.source == "polymarket" else None
        )
        # COMMIT THE LINK BEFORE ANYTHING CLAIMS IT (CERT-771).
        #
        # Phase 1 used to hold every pass's `event_id` assignments pending on one
        # session until after Phase 1.5. The per-market `except` arms below call
        # `session.rollback()`, which discards the WHOLE pending set — so one bad
        # market silently erased every link its predecessors had made in the same
        # pass. That was already a data-loss bug; receipts made it a LYING bug,
        # because the receipt is written on its own session and would still say
        # `linked_event_id=42` for a market left at NULL. The reproduction is
        # exact: market 1 links, market 2 raises, market 1 ends unattached and
        # its one-query answer reports the opposite of the database.
        #
        # Committing here is the same idiom Phase 2 already uses per market for
        # deadlock avoidance (gotcha #13), and it shrinks transactions rather
        # than growing them.
        await session.commit()
        if backfill_request is not None:
            polymarket_backfill_queue.append(backfill_request)
        if receipt is not None:
            receipt.link(matched_event["event_id"], how="matched_existing_event")
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
            backfill_request = (
                (int(market.id), auto_event["event_id"])
                if market.source == "polymarket" else None
            )
            # Durable before claimed — same reason as the matched branch above.
            await session.commit()
            if backfill_request is not None:
                polymarket_backfill_queue.append(backfill_request)
            if receipt is not None:
                receipt.link(auto_event["event_id"], how="auto_created_event")
            return
        if receipt is not None:
            # The matcher found nothing AND declined to invent an event. The
            # decline is always recorded; it only becomes THE reason when
            # nothing more specific was written upstream, because "why is there
            # no event" outranks "and we would not make one".
            receipt.detail["auto_create"] = "declined"
            if receipt.reject_reason is None:
                receipt.reject(_receipts.REJECT_AUTO_CREATE_DECLINED)

    # Record failure
    if not matchup:
        stats["funnel"]["no_matchup_extracted"] += 1
        if receipt is not None:
            receipt.reject(_receipts.REJECT_NO_MATCHUP)
    stats["funnel"]["no_event_found"] += 1
    if receipt is not None and receipt.reject_reason is None:
        # Reached only when _find_matching_event ran without a receipt, or
        # returned early. Never leave an attempt unexplained.
        receipt.reject(_receipts.REJECT_NO_CANDIDATE)
    if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
        stats["funnel"]["sample_game_level_no_event"].append({
            "source": market.source,
            "name": market.name,
            "team_a": matchup.team_a if matchup else None,
            "team_b": matchup.team_b if matchup else None,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
            "external_id": market.external_id,
        })


async def _load_market_row(session, market_id: int):
    """Read ONE market row, immediately before its own attempt (CERT-774).

    A PASS OWNS IDS, NEVER ROWS. Every Phase 1 pass runs across per-market
    rollback boundaries, and ``rollback()`` expires every persistent object in
    the session — ``expire_on_commit=False`` does not prevent it (gotcha #6).
    A pass that iterates a preloaded list of ORM instances therefore has its
    UNREACHED rows expired by the failure of an earlier one: the next
    ``market.id`` triggers an implicit refresh with no greenlet to run it,
    raises ``MissingGreenlet`` outside the per-market catcher, and takes the
    whole pass down before its receipts are flushed. The tail is then not
    merely unmatched but unattempted and unexplained — the exact state
    receipts exist to make impossible.

    So the passes select ids, and each row is loaded here on the line before
    it is used. The cost is one primary-key read per market, against a scan
    that already spends several queries per market on candidates; the benefit
    is that no failure can reach past the market that caused it.

    Returns ``None`` when the row is gone — it was deleted, or a sibling
    process linked and re-scoped it between the scan and the attempt.
    """
    from app.models.models import FuturesMarket

    return await session.get(FuturesMarket, market_id)


async def _abandon_attempt(
    session, *, market_id: int, phase: str, stats: dict, receipt, exc,
) -> None:
    """Record why one attempt failed, and hand the pass back a usable session.

    Two jobs, deliberately together, because doing either without the other
    reintroduces the bug. The receipt gets the reason (a failure that is not
    written down is indistinguishable from never having been tried), and the
    session is rolled back AND emptied, so the rows this pass has not reached
    yet are no longer expired ORM instances waiting to raise.
    """
    if "deadlock" in str(exc).lower():
        stats["funnel"].setdefault("phase1_deadlocks", 0)
        stats["funnel"]["phase1_deadlocks"] += 1
        if receipt is not None:
            receipt.reject(_receipts.REJECT_DEADLOCK, error=str(exc)[:200])
    else:
        stats["errors"].append(f"{phase} market {market_id}: {str(exc)[:100]}")
        if receipt is not None:
            receipt.reject(_receipts.REJECT_ATTEMPT_ERROR, error=str(exc)[:200])

    try:
        await session.rollback()
    except Exception:
        # A rollback that itself fails means the connection is already gone.
        # There is nothing left to undo and nothing useful to report beyond
        # the error already recorded above; re-raising here would replace a
        # per-market failure with a whole-pass one and lose the receipt.
        pass
    # Drop the expired instances the rollback left behind, so the next
    # ``session.get`` is a clean read rather than an implicit refresh of a row
    # that may no longer exist (gotcha #6).
    expunge_all = getattr(session, "expunge_all", None)
    if expunge_all is not None:
        try:
            expunge_all()
        except Exception:
            pass


async def _settled_sweep(session, stats: dict, now: datetime, _time_remaining) -> int:
    """Receipt the markets that left the matcher's population by SETTLING (#2798).

    THE ONE PASS THAT ATTEMPTS NOTHING. Every other pass writes a receipt as the
    by-product of a decision about a link; this one writes a receipt *because
    there will be no more decisions*. Its whole job is to stop the exclusion
    added to Pass 1 from re-creating the silence receipts exist to abolish: a
    market the scan stops visiting has to say why, or "we refuse it" and "we no
    longer look" are once again the same NULL.

    ONCE PER MARKET, and the selection is what guarantees it — a row carrying
    ``settled`` is not selected again. That is the difference between this and
    the behaviour it replaces: Pass 1 re-attempted the same resolved markets
    every cycle (worst ``attempt_count`` 40 on production), which not only cost
    the budget but kept their ``last_attempted_at`` fresh, so any census counted
    off the receipts read a dead ITF tennis tail as today's top matching defect.

    IT ONLY STAMPS MARKETS THAT WERE IN THE POPULATION. The join to
    ``market_match_receipts`` is the scope, not an optimisation: ~460k unlinked
    resolved rows exist, almost all of them archive nobody will ever ask about,
    and stamping them would be a 90-day drain writing rows to answer a question
    that is never asked. A market with a receipt is one the matcher looked at
    and has now stopped looking at — exactly the transition that needs a record.
    For the rest, ``GET /api/admin/match-receipts`` already reads settledness off
    ``futures_markets`` and publishes ``still_linkable`` / ``settled`` per reason.

    Returns rows stamped. Bounded by ``_SETTLED_SWEEP_MAX`` and by a time floor,
    because the record must never cost the thing it records.
    """
    from app.models.models import FuturesMarket, MarketMatchReceipt

    stats["funnel"].setdefault("settled_receipted", 0)
    stats["funnel"]["settled_sweep_skipped_budget"] = False

    if _time_remaining() < _SETTLED_SWEEP_MIN_SECONDS_REMAINING:
        logger.info(
            "Skipping the settled sweep — only %.0fs remaining", _time_remaining(),
        )
        stats["funnel"]["settled_sweep_skipped_budget"] = True
        return 0

    rows = (await session.execute(
        select(
            FuturesMarket.id, FuturesMarket.source,
            FuturesMarket.external_id, FuturesMarket.name,
        )
        .join(MarketMatchReceipt, MarketMatchReceipt.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.event_id.is_(None),
            FuturesMarket.status == "resolved",
            # Spelled out rather than IS DISTINCT FROM: the reason is NULL on
            # every `linked` and `unlinked` receipt, and those markets settle
            # too — a bare `<>` would silently skip all of them.
            or_(
                MarketMatchReceipt.reject_reason.is_(None),
                MarketMatchReceipt.reject_reason != _receipts.REJECT_SETTLED,
            ),
        )
        .order_by(MarketMatchReceipt.last_attempted_at.desc())
        .limit(_SETTLED_SWEEP_MAX)
    )).all()

    if not rows:
        return 0

    receipts = [
        _new_receipt(row, _receipts.PHASE_SETTLED_SWEEP, now).reject(
            _receipts.REJECT_SETTLED, market_status="resolved",
        )
        for row in rows
    ]
    await _flush_pass_receipts(
        session, receipts, stats, _receipts.PHASE_SETTLED_SWEEP,
    )
    stats["funnel"]["settled_receipted"] += len(receipts)
    logger.info(
        "Settled sweep: %d market(s) recorded as settled and out of the scan",
        len(receipts),
    )
    return len(receipts)


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
        select(FuturesMarket.id)
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.event_id.is_(None),
            # SETTLED MARKETS ARE NOT CANDIDATES (#2798). This pass is the only
            # one that never had a status predicate, and it is also the only one
            # with no LIMIT — so it pulled all 138,676 unlinked ticker-shaped
            # Kalshi rows, of which 131,229 had already resolved, and worked
            # down them by `updated_at DESC` until the clock ran out. It never
            # reached the end and never yielded to Pass 2 or Pass 3.
            #
            # `!= 'resolved'` rather than `== 'open'`: `suspended` is a market
            # whose trading is paused, not one whose answer is fixed, and
            # narrowing this pass is not the place to decide that. Kalshi
            # markets that settled upstream but still read 'open' here
            # (gotcha #33) stay eligible too — the conservative direction, since
            # the cost of attempting one is the status quo.
            FuturesMarket.status != "resolved",
            or_(*ticker_conditions),
        )
        .order_by(FuturesMarket.updated_at.desc())
    )
    ticker_market_ids = [int(mid) for mid in ticker_result.scalars().all()]
    stats["funnel"]["ticker_scan_count"] = len(ticker_market_ids)
    # Always present, so "Pass 1 ran to completion" and "Pass 1 stood down" are
    # distinguishable in the funnel instead of one being an absent key.
    stats["funnel"]["pass1_yielded_to_backlog"] = False
    stats["funnel"]["pass1_not_attempted"] = 0

    receipts: list[MatchReceipt] = []
    processed_ids = set()
    # The flush is in a ``finally`` so that even a failure this pass does NOT
    # anticipate still publishes the receipts already earned. Receipts that die
    # in memory leave their markets reading as never attempted, which is the
    # one state this table exists to abolish.
    try:
        # Counted here rather than off ``markets_scanned``, which skips a row
        # that vanished before its attempt: those rows WERE reached, and calling
        # them "not attempted" would inflate the tail Pass 3 is told to cover.
        reached = 0
        for market_id in ticker_market_ids:
            # Yields ABOVE Pass 3's floor, not at the end of the budget
            # (CERT-817). Running to 120s here is what kept the backlog sweep
            # from ever starting; the rows this drops are the tail of an
            # `updated_at DESC` scan and Pass 3 takes them oldest-first.
            if _time_remaining() < _PASS1_YIELD_AT_SECONDS_REMAINING:
                stats["funnel"]["pass1_yielded_to_backlog"] = True
                stats["funnel"]["pass1_not_attempted"] = (
                    len(ticker_market_ids) - reached
                )
                logger.info(
                    "Phase 1 Pass 1 yielded after %d/%d ticker markets with "
                    "%.0fs left, so Pass 3 can start above its %ds floor",
                    reached, len(ticker_market_ids),
                    _time_remaining(), _BACKLOG_MIN_SECONDS_REMAINING,
                )
                break
            reached += 1
            processed_ids.add(market_id)
            market = await _load_market_row(session, market_id)
            if market is None:
                stats["funnel"].setdefault("row_gone_before_attempt", 0)
                stats["funnel"]["row_gone_before_attempt"] += 1
                continue
            stats["markets_scanned"] += 1
            stats["funnel"]["game_level_detected"] += 1

            receipt = _new_receipt(market, _receipts.PHASE_PASS1_TICKER, now)
            receipts.append(receipt)

            try:
                await _attempt_ticker_market(
                    session, market, receipt, stats, now,
                    polymarket_backfill_queue, _time_remaining,
                )
            except Exception as e:
                await _abandon_attempt(
                    session, market_id=market_id,
                    phase=_receipts.PHASE_PASS1_TICKER,
                    stats=stats, receipt=receipt, exc=e,
                )
    finally:
        await _flush_pass_receipts(session, receipts, stats, _receipts.PHASE_PASS1_TICKER)
    return processed_ids


async def _attempt_ticker_market(
    session, market, receipt: MatchReceipt, stats: dict, now: datetime,
    polymarket_backfill_queue: list, _time_remaining,
) -> None:
    """Pass 1's attempt for one ticker market. Every line of it can raise.

    Lifted whole out of the loop (CERT-774) so that ONE catcher covers the
    entire attempt. The previous shape guarded only ``_try_link_market``, which
    left the candidate search — the part that runs the most queries — able to
    abort the pass and take every unflushed receipt with it.
    """
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
            receipt=receipt,
            probe_allowed=_time_remaining() > _PROBE_MIN_SECONDS_REMAINING,
        )
        if matched_event and matchup.format_type == "ticker_parsed":
            stats["funnel"].setdefault("ticker_abbrev_linked", 0)
            stats["funnel"]["ticker_abbrev_linked"] += 1
    else:
        matched_event = await _find_event_by_sport_and_time(
            session, market, now,
            game_date_override=ticker_game_date,
        )
        receipt.detail["path"] = "sport_and_time_fallback"
        if matched_event:
            stats["funnel"].setdefault("sport_time_fallback_linked", 0)
            stats["funnel"]["sport_time_fallback_linked"] += 1

    await _try_link_market(
        session, market, matchup, matched_event, stats,
        ticker_game_date, now, polymarket_backfill_queue,
        receipt=receipt,
    )


async def _flush_pass_receipts(
    session, receipts: list[MatchReceipt], stats: dict, phase: str,
    session_factory=None,
) -> None:
    """Persist one pass's receipts. Never let bookkeeping cost the matcher.

    IN ITS OWN SESSION, DELIBERATELY. Receipts are a record, not a constraint
    (#2705): nothing downstream reads one to decide a link. Writing them on the
    matcher's session would put the pass's work inside the same transaction as a
    log write, so one bad receipt row could roll back real matching. The record
    must never be able to cost the thing it is recording, so it gets its own
    connection and its own commit boundary.

    THE PRICE OF THAT SEPARATION, and how it is paid. Two sessions means the
    receipt can be durable while the link is not — CERT-771's exact
    reproduction: market 1 links, market 2 raises, the shared rollback erases
    market 1's pending ``event_id``, and the receipt still says
    ``linked_event_id=42``. Two things answer it, and both are needed. The
    matcher now commits each link before claiming it, so the window is closed at
    the source; and every claim is re-read against the database here before
    publication, so a receipt CANNOT assert a link the database does not hold
    even if that first guarantee is later changed.

    The failure IS counted. A receipts table that quietly stops being written is
    worse than no receipts table at all: every consumer would read the resulting
    silence as "nothing to report" (gotcha #53).

    ``session`` is accepted and unused so tests can inject a failing one via
    ``session_factory``; the matcher never passes a factory.
    """
    stats["funnel"].setdefault("receipts_written", 0)
    if not receipts:
        return
    factory = session_factory or get_task_session
    try:
        async with factory() as receipt_session:
            # Never publish a claim the database does not hold (CERT-771).
            downgraded = await verify_links_are_durable(receipt_session, receipts)
            if downgraded:
                stats["funnel"].setdefault("receipt_links_not_durable", 0)
                stats["funnel"]["receipt_links_not_durable"] += downgraded
                logger.warning(
                    "%d receipt(s) in %s claimed a link the database does not "
                    "hold — downgraded to link_not_durable. The matcher is "
                    "losing links to sibling failures.",
                    downgraded, phase,
                )
            written = await flush_receipts(receipt_session, receipts)
            await receipt_session.commit()
        stats["funnel"]["receipts_written"] += written
    except Exception as e:
        stats["funnel"].setdefault("receipt_write_failures", 0)
        stats["funnel"]["receipt_write_failures"] += 1
        stats["errors"].append(f"receipts_{phase}: {str(e)[:120]}")
        logger.warning("Receipt write failed for %s: %s", phase, str(e)[:200])


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
        select(FuturesMarket.id)
        .where(*_matchup_base_where, _matchup_name_filter)
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit)
    )
    matchup_ids = [int(mid) for mid in matchup_result.scalars().all()]

    remaining_budget = max(0, limit // 5)
    remaining_ids: list[int] = []
    if remaining_budget > 0:
        remaining_result = await session.execute(
            select(FuturesMarket.id)
            .where(*_matchup_base_where, ~_matchup_name_filter)
            .order_by(FuturesMarket.updated_at.desc())
            .limit(remaining_budget)
        )
        remaining_ids = [int(mid) for mid in remaining_result.scalars().all()]

    unlinked_ids = matchup_ids + remaining_ids
    stats["funnel"]["general_scan_count"] = len(unlinked_ids)
    stats["funnel"]["pass2_yielded_to_backlog"] = False
    stats["funnel"]["matchup_scan_count"] = len(matchup_ids)
    stats["funnel"]["remaining_scan_count"] = len(remaining_ids)

    receipts: list[MatchReceipt] = []
    try:
        for market_id in unlinked_ids:
            # Same reserve as Pass 1, one share lower (CERT-817).
            if _time_remaining() < _PASS2_YIELD_AT_SECONDS_REMAINING:
                stats["funnel"]["pass2_yielded_to_backlog"] = True
                logger.info(
                    "Phase 1 Pass 2 yielded after %d markets scanned with "
                    "%.0fs left, so Pass 3 can start above its %ds floor",
                    stats["markets_scanned"], _time_remaining(),
                    _BACKLOG_MIN_SECONDS_REMAINING,
                )
                break
            if market_id in processed_ids:
                continue

            processed_ids.add(market_id)
            market = await _load_market_row(session, market_id)
            if market is None:
                stats["funnel"].setdefault("row_gone_before_attempt", 0)
                stats["funnel"]["row_gone_before_attempt"] += 1
                continue
            await _attempt_market(
                session, market, stats, now, polymarket_backfill_queue,
                _time_remaining, receipts, _receipts.PHASE_PASS2_GENERAL,
            )
    finally:
        await _flush_pass_receipts(session, receipts, stats, _receipts.PHASE_PASS2_GENERAL)


async def _attempt_market(
    session, market, stats: dict, now: datetime,
    polymarket_backfill_queue: list, _time_remaining,
    receipts: list[MatchReceipt], phase: str,
) -> None:
    """One matching attempt against one market, with its receipt (#2705).

    Lifted verbatim out of Pass 2 so Pass 3 (the backlog sweep) runs the SAME
    decision path rather than a second copy of it. A backlog pass that matched
    by slightly different rules would be a new source of disagreement, and the
    whole point of the sweep is that the tail of the queue gets the identical
    treatment the head already gets.

    THE ATTEMPT IS THE UNIT OF FAILURE (CERT-774). The receipt is opened first
    and the whole body runs inside one catcher, so no path through the attempt
    — candidate search included, not just the link — can escape past this
    market and end the pass.
    """
    market_id = int(market.id)
    stats["markets_scanned"] += 1
    receipt = _new_receipt(market, phase, now)
    receipts.append(receipt)
    try:
        await _run_one_attempt(
            session, market, receipt, stats, now,
            polymarket_backfill_queue, _time_remaining,
        )
    except Exception as e:
        await _abandon_attempt(
            session, market_id=market_id, phase=phase,
            stats=stats, receipt=receipt, exc=e,
        )


async def _run_one_attempt(
    session, market, receipt: MatchReceipt, stats: dict, now: datetime,
    polymarket_backfill_queue: list, _time_remaining,
) -> None:
    """The attempt itself: classify, parse, search, link. May raise."""
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
        if not _receipt_parent_or_not_game_level(market, receipt):
            receipt.reject(_receipts.REJECT_NOT_GAME_LEVEL, category=market.category)
        return

    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id,
    )
    if not matchup:
        stats["funnel"]["no_matchup_extracted"] += 1
        receipt.reject(_receipts.REJECT_NO_MATCHUP)
        return

    stats["funnel"]["game_level_detected"] += 1
    game_date = (
        extract_game_date_from_ticker(market.external_id)
        if market.source == "kalshi" else None
    )

    matched_event = await _find_matching_event(
        session, matchup, market, now,
        game_date_override=game_date,
        receipt=receipt,
        probe_allowed=_time_remaining() > _PROBE_MIN_SECONDS_REMAINING,
    )

    await _try_link_market(
        session, market, matchup, matched_event, stats,
        game_date, now, polymarket_backfill_queue,
        receipt=receipt,
    )


async def _phase1_pass3_backlog_scan(
    session, stats: dict, now: datetime, processed_ids: set[int],
    polymarket_backfill_queue: list, _time_remaining,
) -> None:
    """Phase 1 Pass 3: attempt the markets the other two passes never reach.

    THE BUG THIS CLOSES. Pass 2 selects ``ORDER BY updated_at DESC LIMIT 500``
    from a population of 21,412 open unlinked markets (ARTIFACT-M-20260902-O).
    Whatever is not in the freshest 600 is not attempted — not refused, not
    scored, not looked at. Measured 2026-09-02, that is exactly what happened to
    the 8/28 Polymarket US Open wave: three groups at zero links while every
    8/31–9/01 group linked, with nothing about the names, the candidates or the
    market shapes separating them (ARTIFACT-M-20260902-N). A queue ordered by
    recency starves its own tail, and ``event_id IS NULL`` cannot tell you it is
    happening.

    THE ORDER IS THE FIX. Never-attempted first, then oldest receipt first. A
    market cannot be overtaken by a newer wave, because the thing that puts it
    at the front of the queue is precisely how long it has been waiting.

    THE CAP IS REPORTED, NOT SILENT. ``backlog_dropped`` says how many eligible
    markets this cycle did not reach; ``backlog_oldest_receipt_age_s`` says how
    stale the back of the queue is. Between them the bus can state the real
    coverage guarantee instead of inferring one from a scan that says nothing
    about what it skipped.
    """
    from app.models.models import FuturesMarket, MarketMatchReceipt

    stats["funnel"]["backlog_scanned"] = 0
    stats["funnel"]["backlog_dropped"] = 0
    stats["funnel"]["backlog_skipped_budget"] = False

    if _time_remaining() < _BACKLOG_MIN_SECONDS_REMAINING:
        logger.info("Skipping Phase 1 Pass 3 — only %.0fs remaining", _time_remaining())
        stats["funnel"]["backlog_skipped_budget"] = True
        return

    base_where = [
        FuturesMarket.source.in_(["kalshi", "polymarket"]),
        FuturesMarket.event_id.is_(None),
        FuturesMarket.status == "open",
    ]

    # Never-attempted first. Kept as its own query rather than an ORDER BY over
    # a LEFT JOIN: NOT EXISTS against a unique index is a cheap anti-join, while
    # sorting 21k rows on a nullable joined column is a sort every cycle.
    never_result = await session.execute(
        select(FuturesMarket.id)
        .where(
            *base_where,
            ~select(MarketMatchReceipt.id)
            .where(MarketMatchReceipt.market_id == FuturesMarket.id)
            .exists(),
        )
        .order_by(FuturesMarket.id)
        .limit(_BACKLOG_SCAN_MAX)
    )
    backlog = [int(mid) for mid in never_result.scalars().all()]
    stats["funnel"]["backlog_never_attempted"] = len(backlog)

    if len(backlog) < _BACKLOG_SCAN_MAX:
        stale_result = await session.execute(
            select(FuturesMarket.id, MarketMatchReceipt.last_attempted_at)
            .join(
                MarketMatchReceipt,
                MarketMatchReceipt.market_id == FuturesMarket.id,
            )
            .where(*base_where)
            .order_by(MarketMatchReceipt.last_attempted_at.asc())
            .limit(_BACKLOG_SCAN_MAX - len(backlog))
        )
        stale_rows = stale_result.all()
        backlog.extend(int(mid) for mid, _ in stale_rows)
        if stale_rows:
            oldest = stale_rows[0][1]
            if oldest is not None:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                stats["funnel"]["backlog_oldest_receipt_age_s"] = int(
                    (now - oldest).total_seconds()
                )

    # The honest denominator. Without it "backlog_dropped" would only count the
    # rows this pass FETCHED and did not reach, and would read as zero on every
    # cycle where the cap alone did the truncating — a silent cap wearing a
    # counter (gotcha: no silent caps).
    eligible_total = await session.scalar(
        select(func.count()).select_from(FuturesMarket).where(*base_where)
    )
    stats["funnel"]["backlog_eligible_total"] = int(eligible_total or 0)

    receipts: list[MatchReceipt] = []
    budget_exhausted = False
    try:
        for market_id in backlog:
            if _time_remaining() < _BACKLOG_DOWNSTREAM_RESERVE_SECONDS:
                logger.info(
                    "Phase 1 Pass 3 stopped at the downstream reserve after %d/%d "
                    "fetched backlog markets (%.0fs left for Phase 1.5 + Phase 2)",
                    stats["funnel"]["backlog_scanned"], len(backlog), _time_remaining(),
                )
                budget_exhausted = True
                break
            if market_id in processed_ids:
                continue
            processed_ids.add(market_id)
            market = await _load_market_row(session, market_id)
            if market is None:
                stats["funnel"].setdefault("row_gone_before_attempt", 0)
                stats["funnel"]["row_gone_before_attempt"] += 1
                continue
            stats["funnel"]["backlog_scanned"] += 1
            await _attempt_market(
                session, market, stats, now, polymarket_backfill_queue,
                _time_remaining, receipts, _receipts.PHASE_PASS3_BACKLOG,
            )

        stats["funnel"]["backlog_dropped"] = max(
            0, stats["funnel"]["backlog_eligible_total"]
            - stats["funnel"]["backlog_scanned"]
        )
        if stats["funnel"]["backlog_dropped"]:
            logger.info(
                "Phase 1 Pass 3: %d eligible market(s) not attempted this cycle "
                "(cap=%d, budget_exhausted=%s) — they lead the queue next run",
                stats["funnel"]["backlog_dropped"], _BACKLOG_SCAN_MAX, budget_exhausted,
            )
    finally:
        await _flush_pass_receipts(session, receipts, stats, _receipts.PHASE_PASS3_BACKLOG)
        # THE RUN IS RECORDED WHERE THE RUN CANNOT BE OVERWRITTEN. The receipts
        # just flushed carry phase=pass3_backlog, but that label is the market's,
        # not the run's: Pass 1/2 re-attempt these same open unlinked markets and
        # the upsert overwrites `phase`, so counting labels can report "the
        # backlog pass never ran" minutes after it ran (CERT-819). The durable
        # per-phase row cannot be touched by another pass. In the `finally` on
        # purpose — a pass that died partway through still ran, and the coverage
        # reader needs to know that more, not less.
        run_stage = await _pass_runs.record_pass_run(
            phase=_receipts.PHASE_PASS3_BACKLOG,
            ran_at=now,
            rows_attempted=stats["funnel"]["backlog_scanned"],
            eligible_total=stats["funnel"].get("backlog_eligible_total"),
        )
        stats["funnel"]["backlog_run_recorded"] = run_stage.get("status")


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
            RETURNING fm.id AS mid, fm.source AS msource,
                      fm.external_id AS mext, fm.name AS mname,
                      ml.cur_eid AS from_eid, tgt.id AS to_eid
        """))
        # RETURNING, not rowcount, because LINKLOSS-02 needs the PAIR. This
        # statement MOVES links — 261 of them in one run is an ordinary night —
        # and a count alone leaves every one of those moves looking, from
        # outside, exactly like the matcher having dropped a link.
        moved_rows = r.all()
        n = len(moved_rows)
        await session.commit()
        if n:
            logger.info(
                "Relink collapsed game markets (#944): moved %d markets to correct-date events", n
            )
            await _receipt_bulk_moves(
                [
                    (row.from_eid, row.to_eid, {
                        "id": row.mid, "source": row.msource,
                        "external_id": row.mext, "name": row.mname,
                    })
                    for row in moved_rows
                ],
                phase=_receipts.PHASE_RELINK_COLLAPSED,
                label="relink_collapsed_game_markets",
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
        # (from_event_id, to_event_id, market_row) for the CONVERGE half only —
        # the moves that take a price off an event (LINKLOSS-02).
        receipted_moves: list[tuple[Optional[int], int, dict]] = []
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
                if row.event_id is not None:
                    # A CONVERGE takes the market off an event it was on, so
                    # that event's card loses this source's price. An ADOPT
                    # takes it off nothing and is the forward path's to
                    # explain (LINKLOSS-02).
                    receipted_moves.append((row.event_id, target, {
                        "id": row.id, "source": "kalshi",
                        "external_id": row.external_id, "name": None,
                    }))
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
            await _receipt_bulk_moves(
                receipted_moves,
                phase=_receipts.PHASE_SEGMENT_RECONCILE,
                label="reconcile_kalshi_match_segments",
            )
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
    link_changes: Optional[list[MatchReceipt]] = None,
) -> None:
    """Phase 1.5: fix stale and mislinked markets.

    ``link_changes`` collects a receipt for every link this pass ENDS or MOVES
    (LINKLOSS-02). It is a list the caller owns and flushes AFTER its commit,
    not written here, for two reasons. The receipt session is separate on
    purpose (see :func:`_flush_pass_receipts`) so bookkeeping can never roll
    back matching — and a separate session cannot see this one's uncommitted
    unlinks, so a receipt written mid-pass would be re-read by
    ``verify_links_are_durable`` against a row that still looks linked and would
    be downgraded as un-durable. Collect now, publish once the unlink is real.

    ``None`` (the default) means the caller does not want them; the pass then
    behaves exactly as it did before. Tests rely on that.
    """
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
                    _record_link_change(
                        link_changes, market,
                        _receipts.PHASE_PHASE15_REVALIDATE, now,
                    ).unlink(
                        _shadowed_event_id,
                        cause="shadowed_futures_ticker",
                    )
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
                _record_link_change(
                    link_changes, market,
                    _receipts.PHASE_PHASE15_REVALIDATE, now,
                ).link(
                    better_match["event_id"],
                    previous_event_id=linked_event.id,
                    cause=reason,
                )
                if market.group_id and market.source == "polymarket":
                    from sqlalchemy import text as _text
                    # THE SIBLINGS MOVE TOO, AND THEY MOVE SILENTLY. This one
                    # statement can carry a whole Polymarket group onto the new
                    # event, and every row it touches is a link change nobody
                    # else in this loop will ever see: the pass iterates the
                    # PRIMARY market, not the group. Read the affected rows
                    # first so each one can name the event it came off — a
                    # receipt that cannot say where a link went is the shape
                    # that left LINKLOSS-02 unanswerable.
                    _siblings = (await session.execute(_text("""
                        SELECT id, source, external_id, name, event_id
                        FROM futures_markets
                        WHERE group_id = :gid
                          AND group_type = 'polymarket_sub_market'
                          AND (event_id IS NULL OR event_id != :eid)
                    """), {"eid": better_match["event_id"], "gid": market.group_id})).all()
                    await session.execute(_text("""
                        UPDATE futures_markets
                        SET event_id = :eid
                        WHERE group_id = :gid
                          AND group_type = 'polymarket_sub_market'
                          AND (event_id IS NULL OR event_id != :eid)
                    """), {"eid": better_match["event_id"], "gid": market.group_id})
                    for _sib in _siblings:
                        if _sib.id == market.id or _sib.event_id is None:
                            # A sibling attaching for the first time is an
                            # ordinary link, made by the forward path's own
                            # receipt; only a MOVE is this pass's to explain.
                            continue
                        _record_link_change(
                            link_changes, _sib,
                            _receipts.PHASE_PHASE15_REVALIDATE, now,
                        ).link(
                            better_match["event_id"],
                            previous_event_id=_sib.event_id,
                            cause="polymarket_group_follows_primary",
                            primary_market_id=market.id,
                        )
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
                _record_link_change(
                    link_changes, market,
                    _receipts.PHASE_PHASE15_REVALIDATE, now,
                ).unlink(_unlinked_event_id, cause=reason)
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


# Phase 2b bounds. A sweep over an ageing population needs BOTH ends (gotcha
# #41): the floor stops it walking backwards forever into events nothing renders,
# and the per-source cap stops it from starving the poll it shares a task with.
# Oldest-first inside the floor, so the tail that Phase 2's 24-hour window just
# dropped is the first thing picked up rather than the last.
_PHASE2B_AGE_FLOOR_DAYS = 7
_PHASE2B_EVENTS_PER_SOURCE = 75
_PHASE2B_CURSOR_KEY_PREFIX = "phase2b:completed_catchup:cursor:"


async def _phase2_persist_group_reading(
    session,
    group,
    stats: dict,
    *,
    write_snapshot: bool = True,
) -> int | None:
    """Persist ONE (event, source) group's blend reading. Returns the speaker's id.

    ONE DECISION, THREE WRITERS. `compute_source_home_probability` was extracted
    into `app/utils/live_blend.py` (Q460) so the 120-second poll and the
    WebSocket fast lane could not drift into two opinions of one number. This
    task — the 15-minute matcher — was the writer left behind. It kept its own
    inline copy of the arithmetic, and that copy asked the group's PRIMARY
    market and no other row.

    CERT-767 measured what that costs on the exact-head reproduction: the
    repaired shared helper reads the match-winner child at id 9 and answers
    0.62, while this writer still chose the empty parent at id 1 and wrote
    nothing at all. That matters more than it sounds, because this is the writer
    that stamps `win_probability_sources` for every SCHEDULED event — the poll
    only reaches live events and the three hours before commence. So on
    production the fixed helper was reachable for four live matches and the
    source stayed blank on the twenty-five scheduled ones the repair was for.

    So the reading is the shared one now, and the whole GROUP is what gets
    asked. The caller still computes the primary itself and still runs the two
    Kalshi unlink arms on it, deliberately: those are decisions about that row's
    LINK, not about what the source says, and they keep running exactly where
    they run today.

    ``write_snapshot=False`` is the completed-catch-up's setting — see
    `_phase2b_completed_catchup` for why a settled event gets the blend key but
    never a new point on the chart.
    """
    from app.models.models import Event, FuturesOutcome
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot
    from app.utils.aggregation import stamp_source_reading

    refs = [ref for ref in (group or [])]
    if not refs:
        return None
    anchor = refs[0]

    # One query for the whole group. The previous shape was one query for the
    # primary plus one per sibling on the devig path, so asking every row is not
    # a new round trip — it is fewer.
    outcome_rows = await session.execute(
        select(FuturesOutcome)
        .where(FuturesOutcome.market_id.in_([ref.market_id for ref in refs]))
        .order_by(FuturesOutcome.rank)
    )
    outcomes_by_market: dict[int, list] = {}
    for outcome_row in outcome_rows.scalars().all():
        outcomes_by_market.setdefault(outcome_row.market_id, []).append(outcome_row)

    reading = _compute_source_home_probability(
        [
            _LiveBlendGroup(market=ref, outcomes=outcomes_by_market.get(ref.market_id, []))
            for ref in refs
        ],
        anchor.home_team_name,
        anchor.away_team_name,
    )
    if reading is None:
        return None

    outcome = reading.outcome
    yes_prob = reading.yes_probability
    home_prob = await _check_and_fix_inversion(
        session, anchor.event_id, reading.home_probability, anchor.source,
    )
    away_prob = 1.0 - home_prob

    if write_snapshot:
        snapshot, is_new = await _create_or_update_win_prob_snapshot(
            session,
            event_id=anchor.event_id,
            source=anchor.source,
            home_win_probability=round(home_prob, 4),
            away_win_probability=round(away_prob, 4),
            game_state={
                # `reading.market`, NOT the group's primary. The primary is only
                # the row picked to iterate once per (event, source); since the
                # blend now falls through the group until a market can speak, it
                # is not always the row the number came from, and "why did the
                # blend say that" has to name the one that said it.
                "market_name": reading.market.name,
                "market_id": reading.market.id,
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

    _pm_r = await session.execute(
        select(Event.win_probability_sources).where(Event.id == anchor.event_id)
    )
    # #1829: value + write time (a linked market can stop updating long before
    # anything notices it has).
    _pm_wps = stamp_source_reading(
        _pm_r.scalar_one_or_none(), anchor.source, round(home_prob, 4)
    )
    await session.execute(
        update(Event)
        .where(Event.id == anchor.event_id)
        .values(win_probability_sources=_pm_wps)
    )

    # Commit per group to avoid deadlocks with the live polling task.
    await session.commit()
    return reading.market.id


async def _phase2b_completed_catchup(session, now, stats, time_remaining_fn) -> int:
    """Fill the blend key on completed events Phase 2's 24-hour window aged past.

    WHY THERE HAS TO BE ONE. Phase 2 admits a completed event only for its first
    24 hours, and the live poll never admits one at all. Both are right: a
    prediction-market price polled after the whistle stretches the OddsChart past
    the real game boundary, which is the "prediction market bleed" bug (0t-1).
    But the two windows together mean a group whose reading was VETOED while the
    game was on gets no second chance once the game ends — the repair above heals
    the live and scheduled cohorts and cannot reach the settled one. Measured on
    production 2026-09-02: US Open event 15298238 (completed 08-31) holds a
    readable Polymarket winner at 0.165 and a blank `win_probability_sources`,
    and nothing that runs today will ever ask it.

    WHY IT IS SAFE TO ANSWER NOW, in three properties this function must keep:

    1. NO SNAPSHOT. It writes the blend key only, never a `win_prob_snapshots`
       row, so the chart's completed journey is byte-for-byte what it is today
       and 0t-1 stays fixed. `write_snapshot=False` is that promise.
    2. HOLES ONLY. The candidate query demands the source key be ABSENT. It can
       therefore add a reading where the source said nothing; it can never move
       a number the user is already being shown, which is the same
       strictly-additive property the helper repair itself has.
    3. BOUNDED AT BOTH ENDS. `_PHASE2B_AGE_FLOOR_DAYS` and
       `_PHASE2B_EVENTS_PER_SOURCE`, plus the task's own clock. It shares a
       15-minute task with a link pass and a backfill and must never be the
       reason either is skipped.

    IT ROTATES, AND THAT IS NOT A DETAIL. Property 2 has a sharp edge: a
    candidate that the shared helper legitimately REFUSES never gets a key, so
    it never leaves the candidate set. A plain oldest-first `LIMIT 75` therefore
    re-selects the same refused page every fifteen minutes, forever, and the
    sweep advances zero rows. That is not a hypothesis — the first production
    page of this exact query is 75 Brazilian lower-division rows whose own
    `away_team_name` is `... - Halftime Result`, none of which will ever
    resolve. So the page start is a Redis cursor on `commence_time`, advanced
    past each page and WRAPPED to the floor when the scan runs dry. Refused rows
    cost one rotation, not the whole sweep. Restarting from the floor on a lost
    key is safe: every write here is a no-op on a row that already has the key.

    It does NOT unlink. Phase 2's two date arms exist to repair a live link
    before it writes; this pass reads settled rows and repairs nothing, so
    handing it a destructive verb would give an old, low-signal population power
    over the linkage table. Raw `text()` with `jsonb_exists` and a correlated
    EXISTS mirrors `_cleanup_orphaned_blend_sources` — the ORM's `select()
    .exists()` correlation is unreliable on this shape in this file.
    """
    from app.models.models import FuturesMarket

    filled = 0
    stats["funnel"].setdefault("phase2b_events_scanned", 0)
    stats["funnel"].setdefault("phase2b_sources_filled", 0)
    stats["funnel"].setdefault("phase2b_budget_stopped", False)
    stats["funnel"].setdefault("phase2b_wrapped", 0)

    recent_cutoff = now - timedelta(hours=24)
    age_floor = now - timedelta(days=_PHASE2B_AGE_FLOOR_DAYS)

    # A catch-up whose cursor is gone is a catch-up that pins on its first page,
    # so it declines to run rather than pretending to sweep (gotcha #53 — the
    # zero-yield case is recorded, not silent).
    try:
        from app.tasks.redis_state import get_redis_client

        redis_client = get_redis_client()
    except Exception as e:  # noqa: BLE001 — Redis down must not stop the beat
        stats["funnel"]["phase2b_cursor_unavailable"] = str(e)[:80]
        return 0

    for source in ("kalshi", "polymarket"):
        if time_remaining_fn() < 90:
            stats["funnel"]["phase2b_budget_stopped"] = True
            break

        cursor_key = f"{_PHASE2B_CURSOR_KEY_PREFIX}{source}"
        try:
            raw_cursor = redis_client.get(cursor_key)
        except Exception as e:  # noqa: BLE001
            stats["funnel"]["phase2b_cursor_unavailable"] = str(e)[:80]
            return filled
        if isinstance(raw_cursor, bytes):
            raw_cursor = raw_cursor.decode()
        cursor = age_floor
        if raw_cursor:
            try:
                parsed = datetime.fromisoformat(raw_cursor)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                # Clamp: a cursor left behind by a longer floor must not send the
                # scan back over ground the floor has since retired.
                cursor = max(parsed, age_floor)
            except ValueError:
                cursor = age_floor

        candidates = (
            await session.execute(
                text(
                    "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time "
                    "FROM events e "
                    "WHERE e.status IN ('completed', 'closed') "
                    "AND e.commence_time < :recent AND e.commence_time >= :floor "
                    "AND e.commence_time > :cursor "
                    "AND (e.win_probability_sources IS NULL "
                    "     OR NOT jsonb_exists(e.win_probability_sources, :source)) "
                    "AND EXISTS (SELECT 1 FROM futures_markets fm "
                    "WHERE fm.event_id = e.id AND fm.source = :source) "
                    "ORDER BY e.commence_time ASC LIMIT :lim"
                ),
                {
                    "recent": recent_cutoff,
                    "floor": age_floor,
                    "cursor": cursor,
                    "source": source,
                    "lim": _PHASE2B_EVENTS_PER_SOURCE,
                },
            )
        ).all()
        if not candidates:
            # Scan ran dry — wrap to the floor so the next run re-walks from the
            # oldest live row instead of sitting at the end of the population.
            try:
                redis_client.delete(cursor_key)
            except Exception:  # noqa: BLE001 — a stuck cursor self-heals next wrap
                pass
            stats["funnel"]["phase2b_wrapped"] += 1
            continue

        # Advance past this page BEFORE working it. A page that dies on the time
        # budget must not be the page the next run starts on again.
        page_end = max(row[3] for row in candidates)
        try:
            redis_client.set(cursor_key, page_end.isoformat())
        except Exception:  # noqa: BLE001
            pass

        event_names = {row[0]: (row[1], row[2]) for row in candidates}
        stats["funnel"]["phase2b_events_scanned"] += len(event_names)

        market_rows = (
            await session.execute(
                select(FuturesMarket).where(
                    FuturesMarket.event_id.in_(list(event_names)),
                    FuturesMarket.source == source,
                )
            )
        ).scalars().all()

        groups: dict[int, list[_LinkedMarketRef]] = {}
        for market_row in market_rows:
            home_name, away_name = event_names[market_row.event_id]
            groups.setdefault(market_row.event_id, []).append(
                _LinkedMarketRef(
                    market_id=market_row.id,
                    source=market_row.source,
                    external_id=market_row.external_id,
                    name=market_row.name,
                    event_id=market_row.event_id,
                    event_commence_time=None,
                    home_team_name=home_name,
                    away_team_name=away_name,
                )
            )

        for event_id, group in groups.items():
            if time_remaining_fn() < 60:
                stats["funnel"]["phase2b_budget_stopped"] = True
                break
            try:
                spoke = await _phase2_persist_group_reading(
                    session, group, stats, write_snapshot=False,
                )
            except Exception as e:
                await session.rollback()
                stats["errors"].append(f"phase2b_{event_id}: {str(e)[:100]}")
                continue
            if spoke is not None:
                filled += 1

    stats["funnel"]["phase2b_sources_filled"] += filled
    return filled


async def _match_prediction_markets(limit: int = 500):
    """
    Match game-level prediction markets to events and write win_prob_snapshots.

    Two phases:
    1. Link: Find unlinked game-level markets and match to events (set event_id)
    2. Snapshot: For all linked markets, write current probability to win_prob_snapshots
    """
    # `FuturesOutcome` and `_create_or_update_win_prob_snapshot` moved out with
    # the reading: Phase 2 no longer loads outcomes or writes snapshots inline,
    # `_phase2_persist_group_reading` does both.
    from app.models.models import (
        FuturesMarket, Event, Sport, WinProbSnapshot,
    )

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

    def _time_remaining() -> float:
        return _TIME_BUDGET_SECONDS - (_time.monotonic() - _task_start)

    now = datetime.now(timezone.utc)
    polymarket_backfill_queue = []

    async with get_task_session() as session:
        # The settled sweep (#2798) runs FIRST, before anything that attempts a
        # link. It is the record of the population Pass 1 has just stopped
        # visiting, and a record of an exclusion that only gets written when
        # there is budget left over is a record that reliably goes missing on
        # exactly the busy nights it is wanted for.
        await _settled_sweep(session, stats, now, _time_remaining)

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

        # Phase 1, Pass 3: the backlog sweep (#2705). Passes 1 and 2 are
        # recency-ordered and capped, so the tail of the unlinked population is
        # never attempted — that is why the 8/28 US Open wave sat at zero links
        # for four days while newer waves matched fine. This pass takes
        # never-attempted first, then oldest-receipt first, so nothing can be
        # overtaken forever. It runs the same _attempt_market path the other
        # passes do; it changes WHICH markets get tried, not HOW.
        await _phase1_pass3_backlog_scan(
            session, stats, now, processed_ids,
            polymarket_backfill_queue, _time_remaining,
        )

        # Phase 1.5: Re-validate linked markets
        logger.info("Phase 1 done (%d scanned, %d linked) — %.0fs remaining",
                    stats["markets_scanned"], stats["newly_linked"], _time_remaining())
        # LINKLOSS-02: Phase 1.5 and Phase 2 are the only passes that can END or
        # MOVE a link that already existed, and until now they did it with no
        # record at all — which is why "did tonight's merge drop 261 links?" had
        # no answer. Each collects its receipts here and they are published
        # AFTER the commit that makes the change real (see _phase15_revalidate).
        link_changes: list[MatchReceipt] = []
        await _phase15_revalidate(
            session, stats, now, _time_remaining, link_changes,
        )

        await session.commit()
        await _flush_pass_receipts(
            session, link_changes, stats, _receipts.PHASE_PHASE15_REVALIDATE,
        )

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
        # Declared before the budget check so the flush after Phase 2b always
        # has a list to publish, including on the skipped path (an empty flush
        # is a no-op; an undefined name is a NameError in the error handler).
        phase2_link_changes: list[MatchReceipt] = []
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
                _record_link_change(
                    phase2_link_changes, m, _receipts.PHASE_PHASE2_LINKED, now,
                ).unlink(
                    ev_ref.event_id,
                    cause="phase2_multi_game_wrong_date",
                    ticker_date=d,
                    event_commence_time=ec,
                    diff_hours=round(diff_hours, 1),
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
        for _es_key, market in best_per_event_source.items():
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
                        _record_link_change(
                            phase2_link_changes, market,
                            _receipts.PHASE_PHASE2_LINKED, now,
                        ).unlink(
                            market.event_id,
                            cause="phase2_ticker_date_conflict",
                            ticker_date=_td,
                            event_commence_time=_ec,
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

                # THE GROUP IS ASKED, NOT JUST THE PRIMARY. Everything from the
                # matchup parse to the devig used to be a second inline copy of
                # `live_blend.compute_source_home_probability`, run against this
                # one row. `market` above is only the group's PRIMARY — the row
                # picked to iterate once per (event, source) and to carry the
                # two Kalshi link arms — and for Polymarket "primary" degrades
                # to "lowest id", which is the oldest row: the event-level
                # parent and the derivative books are minted before the
                # match-winner child that holds the moneyline. When that row
                # could not speak, this writer wrote nothing and the source went
                # blank on the page (CERT-759, re-measured by CERT-767).
                #
                # The group's remaining rows are now tried too, under the shared
                # helper's admission gate, and the reading it returns names the
                # market that actually spoke.
                await _phase2_persist_group_reading(
                    session,
                    all_per_event_source.get(_es_key) or [market],
                    stats,
                )

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

        # ── Phase 2b: the completed cohort Phase 2's 24-hour window aged past ─
        # Blend key only, holes only, bounded at both ends — see the helper.
        try:
            await _phase2b_completed_catchup(
                session, now, stats, _time_remaining,
            )
        except Exception as e:
            await session.rollback()
            stats["errors"].append(f"phase2b: {str(e)[:100]}")

    # Published after the matcher's session is closed, on the receipts' own
    # session. Phase 2 commits each unlink inline, so by here every claim in the
    # list is durable and `verify_links_are_durable` re-reads it as such.
    await _flush_pass_receipts(
        None, phase2_link_changes, stats, _receipts.PHASE_PHASE2_LINKED,
    )

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


async def _find_matching_event(
    session, matchup, market, now, game_date_override=None,
    *, receipt=None, probe_allowed: bool = False,
):
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
        receipt: #2705. Write-only. Records the window actually searched, every
            candidate considered, and the reject reason — including the one
            distinction the funnel counters could never make: "no such event
            exists" vs "the event exists and our window excluded it".
        probe_allowed: whether the caller has budget for the extra unwindowed
            ILIKE that draws that distinction. When False the receipt says the
            probe was skipped rather than reporting the weaker reason as
            checked.
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

    if receipt is not None:
        receipt.detail.update({
            "team_a": matchup.team_a,
            "team_b": matchup.team_b,
            "format_type": matchup.format_type,
            "ticker_game_date": game_date_override,
            "scoring_ref": scoring_ref,
            "window_start": time_start,
            "window_end": time_end,
            "windowed_candidates": len(candidates),
        })

    result = _score_candidates(
        candidates, matchup, market, now, scoring_ref, receipt=receipt
    )
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

        if receipt is not None:
            receipt.detail["broad_window_start"] = broad_start
            receipt.detail["broad_window_end"] = broad_end
            receipt.detail["broad_candidates"] = len(broad_candidates)

        result = _score_candidates(
            broad_candidates, matchup, market, now, scoring_ref, receipt=receipt
        )
        if result:
            logger.info(
                "Broad fallback matched %s '%s' → event %d (time window bypass)",
                market.source, market.name, result["event_id"],
            )
            return result

    if receipt is not None:
        await _record_no_match_reason(
            session, receipt, ilike_conditions, now,
            time_start, time_end, matchup=matchup, probe_allowed=probe_allowed,
        )

    return None


def _row_coverage(
    market_name: str | None, matchup, home_team: str | None, away_team: str | None,
) -> tuple[int, int]:
    """``(sides_covered, sides_named)`` for one retrieved row — see
    :func:`app.utils.match_receipts.row_coverage`.

    Every coverage question in this module goes through here, so the candidate
    path and the probe path answer it the same way. The probe re-uses the SAME
    one-token ILIKE that produced the candidates and inherits the same defect:
    without a coverage check, a row retrieved on a shared mascot would be read
    as "the game IS in our table, the window excluded it" and reported as
    ``outside_time_window`` — moving the lie from one bucket to another instead
    of ending it.

    NOT ``_fuzzy_team_match``. That function's refusal is what a receipt is
    explaining; using it to decide whether the refused row was the right game
    guarantees the answer "it was not", and sends every real name-gate failure
    to the upstream-absence bucket. CERT-783 blocked that on Browns-Jaguars.
    """
    return _receipts.row_coverage(
        market_name, matchup.team_a, matchup.team_b, home_team, away_team,
    )


def _side_ilike_conditions(side: str | None) -> list:
    """Every ILIKE that would retrieve a row carrying ONE named side."""
    from app.models.models import Event

    conditions = []
    for term in _expand_team_search_terms(side or ""):
        if not term:
            continue
        pattern = f"%{_escape_like(term)}%"
        conditions.append(Event.home_team_name.ilike(pattern))
        conditions.append(Event.away_team_name.ilike(pattern))
    return conditions


def _covering_probe_condition(market_name: str | None, matchup):
    """A predicate that retrieves ONLY rows carrying BOTH named sides.

    THE PROBE HAD TO ANSWER A DIFFERENT QUESTION THAN IT ASKED. Its job is
    "is this game in our events table at all", and it went at that with an
    OR over every side's patterns, ordered by ``commence_time``, ``LIMIT 5``.
    The OR fires on ONE token, so for a market like "Morehouse Maroon Tigers vs
    Arkansas-Pine Bluff" the five earliest rows in a 165-day window are five
    other games that happen to share a word — and ``covering_hits: 0`` then
    means "none of five arbitrary rows was this game", which is not evidence of
    anything. Measured by the CERT-810 grader: 103 of 109 live NCAAF rejects
    came back with exactly 5 hits, i.e. saturated, so the bucket those receipts
    landed in was decided by a truncation.

    Asking for both sides at once moves the filter into the index scan, so the
    LIMIT stops choosing the answer: a row that comes back is a row that carries
    the whole matchup, and an empty result is the honest "no such game here".

    BOTH READINGS OF THE MATCHUP GET A VOTE, exactly as in
    :func:`app.utils.match_receipts.row_coverage`, and for the same reason: the
    parsed sides can be invented ("Denver vs Kansas City" parsed to the NBA
    ``Nuggets``/``Chiefs`` for an NFL market — 65 of 222 ``name_mismatch``
    receipts), and the market name can be unsplittable. Retrieving on only one
    of the two would rebuild the parse bug inside the instrument that is
    supposed to detect it.

    ``None`` when no reading names two sides — a single-sided market's broad
    probe already IS its covering probe, because one hit covers the one side.
    """
    from sqlalchemy import and_

    readings = []
    if matchup.team_b:
        readings.append((matchup.team_a, matchup.team_b))
    name_a, name_b = _receipts.sides_from_market_name(market_name)
    if name_a and name_b:
        readings.append((name_a, name_b))

    arms = []
    for side_a, side_b in readings:
        a_conditions = _side_ilike_conditions(side_a)
        b_conditions = _side_ilike_conditions(side_b)
        if a_conditions and b_conditions:
            arms.append(and_(or_(*a_conditions), or_(*b_conditions)))
    if not arms:
        return None
    return or_(*arms)


async def _record_no_match_reason(
    session, receipt, ilike_conditions, now, time_start, time_end,
    *, matchup, probe_allowed: bool,
) -> None:
    """Write the reject reason for an attempt that found no event (#2705).

    Three different states arrive here wearing the same NULL ``event_id``, and
    INVARIANTS-2026-09-02 query (c) exists because nothing could tell them
    apart:

    * candidates came back and lost — the trace says why (name, sport, score);
    * no candidate came back and no event anywhere carries these names
      (``no_candidate``): upstream has a market we have no game for;
    * no candidate came back but the game IS in our events table, excluded by
      the window (``outside_time_window``) or by its status
      (``state_disagrees``).

    Only the third is a matcher bug, and it is the one the funnel could never
    surface. Separating it costs one extra ILIKE, bracketed by commence_time so
    it stays on an index, and run only when the caller says there is budget.
    """
    from app.models.models import Event

    reason = _reason_from_traces(receipt.candidates)
    if reason is not None:
        receipt.reject(reason)
        return

    if not probe_allowed:
        receipt.reject(_receipts.REJECT_NO_CANDIDATE, candidate_probe="skipped_budget")
        return

    probe_start = now - timedelta(days=_PROBE_PAST_DAYS)
    probe_end = now + timedelta(days=_PROBE_FUTURE_DAYS)

    async def _probe(where_clause):
        result = await session.execute(
            select(
                Event.id, Event.home_team_name, Event.away_team_name,
                Event.commence_time, Event.status,
            )
            .where(where_clause, Event.commence_time.between(probe_start, probe_end))
            .order_by(Event.commence_time)
            .limit(_PROBE_LIMIT)
        )
        return result.all()

    # THE COVERING ARM RUNS FIRST and, when it hits, is the only one that runs.
    # It asks the question the receipt is about to answer; the broad OR arm is a
    # fallback that exists to record WHAT came back when nothing covers, which is
    # the evidence behind `no_candidate`.
    covering_condition = _covering_probe_condition(receipt.market_name, matchup)
    probe_rows = []
    arm = "broad"
    if covering_condition is not None:
        probe_rows = await _probe(covering_condition)
        arm = "covering"

    saturated = False
    if not probe_rows:
        probe_rows = await _probe(or_(*ilike_conditions))
        # A BROAD ARM THAT FILLED ITS LIMIT DECIDED NOTHING, and the receipt has
        # to say so. `covering_hits: 0` off a truncated result is the reading
        # that produced #2796's NCAAF numbers; a consumer that cannot see the
        # truncation cannot know to discount it (gotcha #53).
        saturated = len(probe_rows) >= _PROBE_LIMIT
        arm = "broad_after_covering_miss" if covering_condition is not None else "broad"

    receipt.detail["candidate_probe"] = {
        "start": probe_start,
        "end": probe_end,
        "hits": len(probe_rows),
        "arm": arm,
        "limit": _PROBE_LIMIT,
        "saturated": saturated,
    }

    if not probe_rows:
        receipt.reject(_receipts.REJECT_NO_CANDIDATE)
        return

    # A probe row inside the searched window can only have been excluded by the
    # status filter; anything else was excluded by the window itself. Both ends
    # are coerced to UTC-aware: a naive bound compared against an aware
    # commence_time raises, and a receipt that raises is a receipt nobody gets.
    def _aware(dt):
        if dt is None or dt.tzinfo is not None:
            return dt
        return dt.replace(tzinfo=timezone.utc)

    lo, hi = _aware(time_start), _aware(time_end)
    in_window = False
    covering = 0
    sides_named = 2 if matchup.team_b else 1
    for row in probe_rows:
        ct = _aware(row.commence_time)
        within = ct is not None and lo is not None and hi is not None and lo <= ct <= hi
        covered, sides_named = _row_coverage(
            receipt.market_name, matchup, row.home_team_name, row.away_team_name,
        )
        # Only a row that carries the WHOLE matchup is evidence that the game is
        # in our table; a partial hit is the same one-token coincidence the
        # candidate search already returned, and it decides nothing.
        if covered >= sides_named:
            covering += 1
            in_window = in_window or within
        receipt.trace(CandidateTrace(
            event_id=row.id,
            home_team=row.home_team_name,
            away_team=row.away_team_name,
            commence_time=ct,
            status=row.status,
            verdict=(
                (
                    _receipts.REJECT_STATE_DISAGREES if within
                    else _receipts.REJECT_OUTSIDE_TIME_WINDOW
                ) if covered >= sides_named
                else _receipts.REJECT_NO_CANDIDATE
            ),
            sides_matched=covered,
            sides_named=sides_named,
        ))

    receipt.detail["candidate_probe"]["covering_hits"] = covering

    if not covering:
        # Rows came back and not one of them is this game. That is the honest
        # "upstream has a market we have no event for" bucket — the one that
        # fired 1 time in 333 before coverage was measured.
        receipt.reject(_receipts.REJECT_NO_CANDIDATE)
        return

    receipt.reject(
        _receipts.REJECT_STATE_DISAGREES if in_window
        else _receipts.REJECT_OUTSIDE_TIME_WINDOW
    )


def _score_candidates(
    candidates, matchup, market, now, game_date_override=None, *, receipt=None
):
    """Score candidate events and return the best match (or None).

    ``receipt`` (#2705) is write-only: when supplied, every candidate this
    function considered is appended to it with the verdict that decided it. The
    return value is untouched, so the matcher's behaviour is identical with and
    without a receipt — the guard test asserts exactly that.
    """
    if not candidates:
        return None

    traces: list[CandidateTrace] = []

    #: The market named two sides, or one (the ``will_win`` shape). Every trace
    #: carries this so a rejected row can be read as "covered 1 of 2" without
    #: re-deriving the matchup from the market name.
    sides_named = 2 if matchup.team_b else 1
    market_name = getattr(market, "name", None)

    def _trace(event, verdict, score=None, measure_coverage=False):
        """Record one candidate.

        ``measure_coverage`` is set exactly where the NAME GATE refused the row,
        and only there. Everywhere else the row already cleared that gate, so it
        covers the matchup by construction and re-deriving it would be noise.
        """
        if receipt is None:
            return None
        covered = sides_named
        if measure_coverage:
            covered, _ = _row_coverage(
                market_name, matchup, event.home_team_name, event.away_team_name,
            )
        t = CandidateTrace(
            event_id=event.id,
            home_team=event.home_team_name,
            away_team=event.away_team_name,
            commence_time=event.commence_time,
            status=event.status,
            sport_key=(event.sport.key if event.sport else None),
            score=score,
            verdict=verdict,
            sides_matched=covered,
            sides_named=sides_named,
        )
        traces.append(t)
        receipt.trace(t)
        return t

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
                # Coverage is what separates a rejected candidate from a row
                # the ILIKE happened to return on one shared token — and it is
                # measured INDEPENDENTLY of a_matches/b_matches, which are the
                # verdict being explained. "CLE Browns vs JAC Jaguars" against
                # Jacksonville Jaguars / Cleveland Browns fails both halves here
                # and covers both sides; that is a name-gate bug of ours, not an
                # upstream absence (CERT-783).
                _trace(
                    event, _receipts.REJECT_NAME_MISMATCH, measure_coverage=True,
                )
                continue

        # Check team name matching (determine yes/no home/away mapping)
        team_match = match_teams_to_event(
            matchup,
            event.home_team_name,
            event.away_team_name,
            external_id=market.external_id or "",
        )
        if not team_match:
            # A two-sided matchup that reaches here already cleared the gate
            # above, so its coverage is full: this IS the documented
            # name_mismatch — both sides present, orientation refused. A
            # one-sided matchup never met that gate, so measure it.
            _trace(
                event, _receipts.REJECT_NAME_MISMATCH,
                measure_coverage=not matchup.team_b,
            )
            continue

        # For "Will X win?" with only one team, verify the market team
        # actually matches an event team
        if matchup.format_type == "will_win" and not matchup.team_b:
            if not (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            ):
                # The market named one side and the gate says this row does not
                # carry it. Measure independently before calling it a
                # coincidence — the gate cannot match a name of three
                # characters or fewer at all.
                _trace(
                    event, _receipts.REJECT_NAME_MISMATCH, measure_coverage=True,
                )
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
                _trace(event, _receipts.REJECT_WRONG_SPORT, score=score)
                continue  # Wrong sport — skip this candidate
            score += 5  # Same sport confirmed
        elif not sport_prefix:
            score -= 5  # No sport validation — penalize to prefer validated matches

        _trace(event, "considered", score=score)

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
        for t in traces:
            if t.event_id == best_match["event_id"] and t.verdict == "considered":
                t.verdict = _receipts.REJECT_NAME_SCORE_BELOW
        if receipt is not None:
            receipt.detail["score_floor"] = 21
        return None

    for t in traces:
        if t.verdict != "considered":
            continue
        if best_match is None:
            # Scored, and still nothing won — only reachable when every
            # candidate scored below the -1 seed. Report it as a score refusal,
            # not as a name problem: the names matched.
            t.verdict = _receipts.REJECT_NAME_SCORE_BELOW
        else:
            t.verdict = (
                "chosen" if t.event_id == best_match["event_id"] else "lower_score"
            )

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
        bracket_refusal_reason, question_refusal_reason,
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

    # #2871: same principle, the Polymarket shape. A title ending in a
    # dash-introduced market type ("… vs. … - Exact Score", "- Total Corners",
    # "- Halftime Result") is a derivative of a game, not evidence of one.
    # extract_matchup splits on " vs. ", so the market type rides into team_b
    # and the stamp below would name the away team "Lausanne-Sport - Total
    # Corners". Because an id-less Polymarket claim never absorbs (ruling 048),
    # each distinct suffix minted its own event: one real fixture became five
    # rows in /search. The game's own container market ("- More Markets") does
    # not match this and still creates the fixture normally.
    from app.utils.prediction_market_matching import is_derivative_market_name

    if is_derivative_market_name(market.name):
        logger.debug(
            "Refusing auto-create from derivative market '%s' (#2871) — a prop "
            "or period market is not evidence that a game exists",
            market.name,
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

    # #2993: a bracket is not a game. Checked HERE, after every name mutation
    # above (prefix/suffix stripping, combat opponent recovery), because these
    # are the exact strings the stamp below writes onto the row.
    bracket_reason = bracket_refusal_reason(team_a, team_b)
    if bracket_reason:
        logger.debug(
            "Refusing auto-create from '%s' (#2993) — %s",
            market.name, bracket_reason,
        )
        return None

    # #3026: a question is not a game. Same boundary and the same reason it sits
    # here rather than in the parser — these are the strings the stamp writes.
    question_reason = question_refusal_reason(team_a, team_b)
    if question_reason:
        logger.debug(
            "Refusing auto-create from '%s' (#3026) — %s",
            market.name, question_reason,
        )
        return None

    # Q453: the ticker is consulted first and wins; this is the fallback for a
    # market whose only evidence of sport is the LLM's per-market guess. It
    # refuses `football` — see `auto_create_sport_key_from_category`.
    if not sport_key:
        sport_key = auto_create_sport_key_from_category(market.llm_sport_category)

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
                        # `reading.market`, NOT the loop's `market`. The loop
                        # row is only the group's PRIMARY — the row picked to
                        # iterate once per (event, source). Since the blend
                        # falls through a group until a market can speak, the
                        # primary is not always the market the number came
                        # from, and "why did the blend say that" has to name
                        # the market that said it.
                        "market_name": reading.market.name,
                        "market_id": reading.market.id,
                        "outcome_name": outcome.name,
                        "yes_probability": yes_prob,
                        "yes_bid": float(outcome.current_yes_bid) if outcome.current_yes_bid else None,
                        "yes_ask": float(outcome.current_yes_ask) if outcome.current_yes_ask else None,
                        "poll_type": "live_fast",
                    },
                    # live/035: on a LIVE event a flat price must still gain a
                    # point. The poll's own period is 120s, so the deadline is
                    # derived from it the same way the WS lane derives its own —
                    # a deadline equal to the period is first noticed one period
                    # late. Scheduled (pre-game) events are excluded: their
                    # prices genuinely sit still for hours and a heartbeat there
                    # buys a longer table and no visible line.
                    max_gap_seconds=(
                        _LIVE_SNAPSHOT_HEARTBEAT_S
                        if (event.status or "").lower() == "live"
                        else None
                    ),
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

            # Fetch price history. `get_prices_history` raises when the venue
            # could not be asked at all and returns [] only when it answered and
            # holds nothing — the two must not land in the same bucket, or an
            # outage reads as a market with no history (gotcha #53).
            from app.services.polymarket_api import PolymarketHistoryUnavailable

            try:
                history = await service.get_prices_history(
                    token_id=token_id,
                    interval=interval,
                    fidelity=fidelity,
                )
            except PolymarketHistoryUnavailable as exc:
                stats["errors"].append(f"price history unavailable: {str(exc)[:120]}")
                return stats
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
