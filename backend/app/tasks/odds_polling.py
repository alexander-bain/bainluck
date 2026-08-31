"""
Main odds polling tasks: poll_all_odds, poll_sport_odds, and snapshot helpers.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, case, or_, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models import Sport, Event, OddsSnapshot, ScoreSnapshot
from app.services.event_registry import ODDS_LISTING_IS_NOT_A_DEREFERENCE
from app.services.odds_api import OddsAPIService
from app.utils.game_pairing import IdCurrency, external_id_currency
from app.utils.odds_math import moneyline_to_probability, project_scores
from app.utils.polling_config import compute_effective_interval
from app.tasks.base import get_task_session, run_async
from app.tasks.config import (
    LIVE_POLL_INTERVAL,
    SOON_POLL_INTERVAL,
    LATER_POLL_INTERVAL,
    ODDS_STALE_MINUTES,
    MIN_HOURS_BEFORE_STALENESS_CHECK,
    SPORT_MAX_DURATIONS,
    SPORT_POLLING_TIERS,
    SPORT_POLLING_DEFAULT_TIER,
    SPORT_TIER_MULTIPLIERS,
    SPORT_REGION_OVERRIDES,
)
from app.tasks.redis_state import (
    get_redis_client,
    compute_odds_hash,
    should_poll_now,
    update_poll_state,
    check_quota_guard,
    POLL_STATE_KEY,
    QUOTA_GUARD_LIVE_ONLY,
    QUOTA_GUARD_PRIORITY_SPORTS,
)

logger = logging.getLogger(__name__)

# Ruling 051 (#1841), Alex 2026-08-14: the sportsbook consensus floors at THREE
# books. At or above the floor `betting` is written as the median; below it the
# key is DROPPED from `Event.win_probability_sources` and the blend re-weights
# over whatever remains fresh. Never frozen at a last value.
#
# Three, and not two, because the measured failure had three books left and was
# already broken: fanduel 0.0140, betmgm 0.0288, rebet 0.1347 — a 10x spread in
# which the median still had to pick one of them. Two books cannot have a median
# at all in any meaningful sense. Below three there is no consensus to report,
# and reporting one anyway is what produced 87-13 on event 15192596.
BETTING_BOOK_FLOOR = 3


def tier_adjusted_interval(base_interval: float, tier: str, sport_key: str) -> float:
    """Apply the sport-tier multiplier — to PRE-GAME traffic only (LAT-P159).

    🔴 THE MULTIPLIER IS A PRE-GAME ECONOMY AND IT USED TO APPLY TO `live` TOO,
    which made a live game's refresh rate a function of its league's POPULARITY:
    60 s for the NBA, 120 s for NCAAF, 180 s for anything unlisted. Alex reported
    a live Stanford game whose probability lagged the action — Stanford is
    `americanfootball_ncaaf`, Tier 2 — so its odds were two minutes old by
    construction. Betting carries weight 3.0 in `utils/aggregation.py`; it IS the
    number on the card.

    The file already said as much and then did the opposite: the adaptive
    slowdown thirty lines down is guarded `tier != "live"` under the comment
    *"live games always poll fast"*. Tiering exists to conserve quota on sports
    nobody is watching YET. Once a game is live somebody is watching it, whatever
    the league.

    Extracted as a function rather than left inline because it is the rule a
    guard has to be able to call. Re-implementing the rule under test in the test
    is how this lane published a corruption count that moved four times
    (LAT-P156); a guard must exercise the shipped code, not a copy that agrees
    with it today.
    """
    if tier == "live":
        return base_interval
    sport_tier = SPORT_POLLING_TIERS.get(sport_key, SPORT_POLLING_DEFAULT_TIER)
    return base_interval * SPORT_TIER_MULTIPLIERS.get(sport_tier, 4)


def get_statpal_end_time(event) -> Optional[datetime]:
    """
    Extract StatPal end time from event — checks dedicated column first,
    falls back to JSONB win_probability_sources storage.

    Returns a timezone-aware datetime if found, else None.
    """
    statpal_end = getattr(event, "statpal_end_time", None)
    if statpal_end:
        return statpal_end
    sources = getattr(event, "win_probability_sources", None) or {}
    end_str = sources.get("statpal_end_time")
    if end_str:
        try:
            return datetime.fromisoformat(end_str)
        except (ValueError, TypeError):
            pass
    return None


def get_max_duration_for_sport(sport_key: str) -> float:
    """
    Get the maximum expected duration (in hours) for a sport.

    Used for staleness detection - we only mark events as "closed"
    if they've been live longer than this duration AND odds are stale.
    """
    # Check for exact match first
    for sport_prefix, duration in SPORT_MAX_DURATIONS.items():
        if sport_prefix == "default":
            continue
        if sport_key.startswith(sport_prefix):
            return duration

    return SPORT_MAX_DURATIONS["default"]


async def _last_post_commence_snapshot(session, event_id):
    """Last real snapshot at/after this event's start, or None.

    Per-event rather than batched: only events that are actually about to close
    pay for it, and a staleness close is rare by construction.
    """
    from sqlalchemy import text as _sql_text

    from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

    row = (await session.execute(
        _sql_text(LAST_POST_COMMENCE_SNAPSHOT_SQL), {"event_ids": [event_id]}
    )).first()
    return row.last_snap if row else None


async def detect_and_close_stale_events(session) -> int:
    """
    Detect live events with stale odds and mark them as "closed".

    This provides a fallback when the Scores API doesn't report completion,
    which can happen with tennis and other sports.

    An event is marked as "closed" when:
    1. It's currently "live" status
    2. It started at least MIN_HOURS_BEFORE_STALENESS_CHECK hours ago
    3. Either:
       a. It has no odds snapshots at all (bookmakers stopped offering odds), OR
       b. The latest odds snapshot is older than ODDS_STALE_MINUTES

    Returns the number of events marked as closed.
    """
    now = datetime.now(timezone.utc)
    closed_count = 0

    # Find all live events that started more than MIN_HOURS ago
    min_start_time = now - timedelta(hours=MIN_HOURS_BEFORE_STALENESS_CHECK)

    result = await session.execute(
        select(Event)
        .join(Sport)
        .where(
            Event.status == "live",
            Event.commence_time <= min_start_time,
        )
        .options(selectinload(Event.sport))
    )
    live_events = result.scalars().all()

    for event in live_events:
        try:
            hours_since_start = (now - event.commence_time).total_seconds() / 3600

            # Check StatPal end time first — definitive close signal
            statpal_end = get_statpal_end_time(event)
            if statpal_end and statpal_end <= now:
                close_vals = {"status": "closed"}
                if not event.completed_at:
                    close_vals["completed_at"] = statpal_end
                await session.execute(
                    Event.__table__.update()
                    .where(Event.id == event.id)
                    .values(**close_vals)
                )
                closed_count += 1
                logger.info(
                    f"Marked event {event.id} ({event.home_team_name} vs {event.away_team_name}) "
                    f"as closed: statpal_end_time, {hours_since_start:.1f}h since start"
                )
                continue

            # Check if ANY bookmaker has provided odds recently
            # We need to find the most recently updated snapshot across all bookmakers
            # valid_until is updated when we see the same odds again; captured_at is when odds changed
            stale_threshold = now - timedelta(minutes=ODDS_STALE_MINUTES)

            # Count snapshots that have been updated recently
            recent_snapshot_count = await session.execute(
                select(func.count())
                .select_from(OddsSnapshot)
                .where(
                    OddsSnapshot.event_id == event.id,
                    or_(
                        OddsSnapshot.valid_until >= stale_threshold,
                        and_(
                            OddsSnapshot.valid_until == None,
                            OddsSnapshot.captured_at >= stale_threshold
                        )
                    )
                )
            )
            recent_count = recent_snapshot_count.scalar()

            should_close = False
            close_reason = ""

            if recent_count == 0:
                # No bookmaker has updated odds recently - check if we ever had odds
                any_snapshot = await session.execute(
                    select(func.count())
                    .select_from(OddsSnapshot)
                    .where(OddsSnapshot.event_id == event.id)
                )
                total_snapshots = any_snapshot.scalar()

                if total_snapshots == 0:
                    should_close = True
                    close_reason = "no_odds_data"
                else:
                    # Had odds but all bookmakers stopped updating
                    should_close = True
                    close_reason = "all_bookmakers_stale"

            if should_close:
                close_values = {"status": "closed"}
                if not event.completed_at:
                    # gotcha #22: completed_at is a GAME-END time. now() is when
                    # the backend noticed, which is wrong by however long the
                    # bookmakers had been stale — and it is what chart domains
                    # and "settled" language stand on. Derive it from the last
                    # real post-commence snapshot, or leave it NULL: a visible
                    # gap the CAL-P002 repair can fill beats a plausible-looking
                    # wrong value that nothing will ever question.
                    from app.utils.event_completion import derive_completed_at

                    close_values["completed_at"] = derive_completed_at(
                        await _last_post_commence_snapshot(session, event.id),
                        event.commence_time,
                    )
                await session.execute(
                    Event.__table__.update()
                    .where(Event.id == event.id)
                    .values(**close_values)
                )
                closed_count += 1
                logger.info(f"Marked event {event.id} ({event.home_team_name} vs {event.away_team_name}) "
                      f"as closed: {close_reason}, {hours_since_start:.1f}h since start")

        except Exception as e:
            logger.warning(f"Error checking staleness for event {event.id}: {e}")
            continue

    return closed_count


def _snapshots_are_equal(existing: OddsSnapshot, new_values: dict) -> bool:
    """Check if the key odds values are the same."""
    # Compare the fields that matter for deduplication
    # Using rough equality for decimals
    def eq(a, b):
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # For numeric types, compare values
        return float(a) == float(b) if isinstance(a, (int, float)) or hasattr(a, '__float__') else a == b

    return (
        eq(existing.home_moneyline, new_values.get("home_moneyline")) and
        eq(existing.away_moneyline, new_values.get("away_moneyline")) and
        eq(existing.home_spread, new_values.get("home_spread")) and
        eq(existing.over_under, new_values.get("over_under")) and
        eq(existing.home_win_probability, new_values.get("home_win_probability"))
    )


def _parse_snapshot_values(bookmaker: dict, event_data: dict) -> dict:
    """Parse bookmaker data into snapshot field values."""
    values = {
        "home_moneyline": None,
        "away_moneyline": None,
        "home_spread": None,
        "home_spread_odds": None,
        "away_spread_odds": None,
        "over_under": None,
        "over_odds": None,
        "under_odds": None,
        "home_win_probability": None,
        "away_win_probability": None,
        "projected_home_score": None,
        "projected_away_score": None,
    }

    home_team = event_data["home_team"]
    away_team = event_data["away_team"]

    for market in bookmaker.get("markets", []):
        market_key = market["key"]
        outcomes = {o["name"]: o for o in market["outcomes"]}

        if market_key == "h2h":
            home_outcome = outcomes.get(home_team, {})
            away_outcome = outcomes.get(away_team, {})
            values["home_moneyline"] = home_outcome.get("price")
            values["away_moneyline"] = away_outcome.get("price")

            if values["home_moneyline"] and values["away_moneyline"]:
                home_prob, away_prob = moneyline_to_probability(
                    values["home_moneyline"],
                    values["away_moneyline"],
                )
                values["home_win_probability"] = round(home_prob, 4)
                values["away_win_probability"] = round(away_prob, 4)

        elif market_key == "spreads":
            home_outcome = outcomes.get(home_team, {})
            away_outcome = outcomes.get(away_team, {})
            values["home_spread"] = home_outcome.get("point")
            values["home_spread_odds"] = home_outcome.get("price")
            values["away_spread_odds"] = away_outcome.get("price")

        elif market_key == "totals":
            over_outcome = outcomes.get("Over", {})
            under_outcome = outcomes.get("Under", {})
            values["over_under"] = over_outcome.get("point")
            values["over_odds"] = over_outcome.get("price")
            values["under_odds"] = under_outcome.get("price")

    # Calculate projected scores
    if values["home_spread"] is not None and values["over_under"]:
        home_score, away_score = project_scores(
            float(values["home_spread"]),
            float(values["over_under"]),
        )
        values["projected_home_score"] = home_score
        values["projected_away_score"] = away_score

    return values


async def _maybe_set_opening_odds(
    session,
    event_id: int,
    home_prob: float | None,
    away_prob: float | None,
    home_spread: float | None,
    over_under: float | None,
    commence_time: datetime | None = None,
):
    """
    Update opening odds for a scheduled event.

    Opening odds represent the last pregame consensus — they keep updating
    on every poll while the game is still scheduled. Once the game starts,
    they freeze, capturing what the market thought right before kickoff.

    If commence_time is not provided, falls back to checking the event status.
    """
    if home_prob is None:
        return

    now = datetime.now(timezone.utc)

    # Only update if the game hasn't started yet
    if commence_time is not None and commence_time <= now:
        return

    # Also check event status as a fallback
    result = await session.execute(
        select(Event.status)
        .where(Event.id == event_id)
    )
    status = result.scalar_one_or_none()
    if status and status != "scheduled":
        return

    # Determine opening favorite
    if home_prob > 0.52:
        opening_favorite = "home"
    elif home_prob < 0.48:
        opening_favorite = "away"
    else:
        opening_favorite = "even"

    # Update opening odds (keeps updating until game starts)
    await session.execute(
        Event.__table__.update()
        .where(Event.id == event_id)
        .values(
            opening_home_probability=home_prob,
            opening_away_probability=away_prob,
            opening_home_spread=home_spread,
            opening_over_under=over_under,
            opening_favorite=opening_favorite,
        )
    )


async def _create_or_update_snapshot(
    session,
    event_id: int,
    bookmaker: dict,
    event_data: dict,
    snapshot_cache: dict = None,
) -> tuple[OddsSnapshot, bool]:
    """
    Create a new snapshot or update existing if values unchanged.

    Returns (snapshot, is_new) tuple.
    - If values changed: creates new snapshot, returns (new_snapshot, True)
    - If values same: updates existing snapshot's reading_count/valid_until, returns (existing, False)
    """
    now = datetime.now(timezone.utc)
    bookmaker_key = bookmaker["key"]

    # Parse the new values
    new_values = _parse_snapshot_values(bookmaker, event_data)

    # Find the most recent snapshot for this event+bookmaker
    cache_key = (event_id, bookmaker_key)
    existing = snapshot_cache.get(cache_key) if snapshot_cache is not None else None
    if existing is None:
        result = await session.execute(
            select(OddsSnapshot)
            .where(
                OddsSnapshot.event_id == event_id,
                OddsSnapshot.bookmaker == bookmaker_key
            )
            .order_by(OddsSnapshot.captured_at.desc())
            .limit(1)
        )
        existing = result.scalar_one_or_none()

    # If no existing snapshot or values changed, create new one
    if existing is None or not _snapshots_are_equal(existing, new_values):
        # If there was an existing one, set its valid_until
        if existing is not None:
            existing.valid_until = now

        # Create new snapshot
        snapshot = OddsSnapshot(
            event_id=event_id,
            bookmaker=bookmaker_key,
            captured_at=now,
            reading_count=1,
            **new_values
        )
        if snapshot_cache is not None:
            snapshot_cache[cache_key] = snapshot
        return snapshot, True
    else:
        # Values are the same - just update the existing snapshot
        existing.reading_count += 1
        existing.valid_until = now
        return existing, False


# _create_or_update_win_prob_snapshot moved to tasks/snapshots.py
from app.tasks.snapshots import _create_or_update_win_prob_snapshot  # noqa: F401


async def _create_snapshot(
    event_id: int,
    bookmaker: dict,
    event_data: dict
) -> OddsSnapshot:
    """Create an OddsSnapshot from API data. (Legacy - used by poll_sport_odds)"""
    values = _parse_snapshot_values(bookmaker, event_data)
    snapshot = OddsSnapshot(
        event_id=event_id,
        bookmaker=bookmaker["key"],
        captured_at=datetime.now(timezone.utc),
        reading_count=1,
        **values
    )
    return snapshot


async def _ingest_event_odds(
    session,
    event,
    event_data: dict,
    commence_time: datetime,
    snapshot_cache: dict,
) -> int:
    """Create odds snapshots for every bookmaker of one event, then update the
    event's opening-odds consensus and win_probability_sources['betting'].

    Extracted from the _poll_all_odds inner loop so the MLB pre-game polling
    task (_poll_mlb_pregame, issue #892) reuses identical snapshot/consensus
    logic and the two paths cannot drift. Returns the number of bookmaker
    snapshots processed.
    """
    event_id = event.id

    # Collect all bookmaker values for opening-odds consensus.
    all_home_probs: list[float] = []
    all_away_probs: list[float] = []
    all_spreads: list[float] = []
    all_ous: list[float] = []
    snapshots_processed = 0

    for bookmaker in event_data.get("bookmakers", []):
        snapshot, is_new = await _create_or_update_snapshot(
            session,
            event_id,
            bookmaker,
            event_data,
            snapshot_cache=snapshot_cache,
        )
        if is_new:
            session.add(snapshot)
        # Collect values from ALL bookmakers (new or existing) for consensus.
        if snapshot.home_win_probability:
            all_home_probs.append(float(snapshot.home_win_probability))
            if snapshot.away_win_probability:
                all_away_probs.append(float(snapshot.away_win_probability))
            if snapshot.home_spread is not None:
                all_spreads.append(float(snapshot.home_spread))
            if snapshot.over_under is not None:
                all_ous.append(float(snapshot.over_under))
        snapshots_processed += 1

    # Update opening odds with consensus across all bookmakers
    # (keeps updating on every poll while the game is scheduled).
    if all_home_probs:
        # #1841: MEDIAN, not mean. Books PULL the moneyline when a game goes out
        # of reach, and they drop out one at a time. Under a mean, the
        # "consensus" silently narrows as `len()` shrinks until it is a single
        # book — measured on event 15192596 (Red Sox @ Blue Jays, 2026-08-13):
        # 12 books at 20:55 UTC, then 3 at 21:05 (fanduel 0.0140, betmgm 0.0288,
        # rebet 0.1347), then ONE. `win_probability_sources['betting']` was left
        # at 0.1347 — one minor book's last quote, stored as the sportsbook
        # consensus, while the two sharper books still pricing it at 1-3% had
        # already dropped out. That number rendered 87-13 for a team trailing
        # 5-0 in the 9th.
        #
        # A median cannot be carried by one book among three. It is NOT a
        # complete fix on its own: with a single book left, median == that book.
        # The minimum-book-count refusal that closes the rest WAS the open policy
        # call, and Alex ruled it on 2026-08-14 — see BETTING_BOOK_FLOOR and
        # ruling 051 below. Median and floor are complements: the floor decides
        # whether we have a consensus at all, the median decides what it says.
        #
        # Same integrity question as #1844, one step upstream: that one is about
        # how a consensus is COMPARED, this one about what the consensus IS when
        # sources drop out.
        from statistics import median as _median

        avg_home = _median(all_home_probs)
        avg_away = _median(all_away_probs) if all_away_probs else (1 - avg_home)
        avg_spread = _median(all_spreads) if all_spreads else None
        avg_ou = _median(all_ous) if all_ous else None
        await _maybe_set_opening_odds(
            session, event_id,
            avg_home, avg_away,
            avg_spread, avg_ou,
            commence_time=commence_time,
        )

        # Write betting consensus to win_probability_sources so the multi-source
        # aggregation system sees it. Reuse the loaded event object (N+1 fix).
        # #1829: stamp the write time alongside the value. `betting` is the
        # source this matters most for, and for a reason visible right here —
        # `all_home_probs` is only non-empty while at least one book still
        # quotes a moneyline. Books PULL the line when a game is out of reach,
        # so this branch simply stops running and the key freezes at whatever
        # it last said, with nothing in the JSONB to admit it. That frozen
        # number is what rendered "87 - 13" for a team trailing 5-0 in the 9th.
        from sqlalchemy import update as _update
        from app.utils.aggregation import stamp_source_reading
        betting_val = round(avg_home, 4)
        _book_count = len(all_home_probs)

        if _book_count >= BETTING_BOOK_FLOOR:
            _current = stamp_source_reading(
                event.win_probability_sources, "betting", betting_val
            )
        else:
            # ── RULING 051: below its evidence floor a source is ABSENT ──────
            # Alex's ruled policy for #1841. Under the floor the sportsbook
            # consensus is DROPPED — not written, not frozen, not down-weighted.
            # The blend then re-weights over whichever sources are still fresh.
            #
            # The argument (ruling 051, and gotcha #53's best formulation):
            # nothing downstream can tell "the books say 13%" from "the books
            # SAID 13% before they stopped saying anything". Those are different
            # facts and they must not render identically. A stale value left in
            # place is indistinguishable from a live one, so the only honest
            # representation of "we no longer know" is the key's ABSENCE.
            #
            # Removal — not merely skipping the write — is the load-bearing part:
            # `betting` is very likely ALREADY in the JSONB from an earlier poll
            # when there were still enough books. Skipping would leave exactly
            # the frozen 0.1347 that rendered 87-13 for a team trailing 5-0.
            _current = dict(event.win_probability_sources or {})
            _current.pop("betting", None)
            logger.info(
                "event %s: betting DROPPED below floor — %d book(s) < %d "
                "(would have written %.4f); blend re-weights over remaining "
                "fresh sources (ruling 051 / #1841)",
                event_id, _book_count, BETTING_BOOK_FLOOR, betting_val,
            )
        # #1841: record HOW MANY books stand behind that number. A consensus of
        # one is not a consensus, and today nothing downstream can tell the
        # difference. `compute_aggregate_probability` skips keys absent from
        # SOURCE_WEIGHTS, so this is inert for the blend and readable by humans
        # and by any future weighting rule.
        #
        # INT-067 conflict resolution: #1829's `stamp_source_reading` (which
        # nests `betting` as {value, updated_at} and is the ONLY thing making
        # the hero's recency decay work) landed on master via ux-59 while this
        # branch waited. Both halves are kept — the stamp writes the reading,
        # this line adds the book count as a TOP-LEVEL sibling. Deliberately
        # not nested inside the `betting` entry: the count describes the
        # measurement, not the reading, and every reader added since #1829
        # expects that entry to hold value/updated_at.
        #
        # Ruling 051: the count is written in BOTH directions — including when
        # `betting` was just dropped. It describes the MEASUREMENT, not the
        # reading, so "0 books stand behind a value that is no longer here" is a
        # meaningful, readable statement, and it is what makes the drop visible
        # to a human rather than silent.
        _current["betting_book_count"] = _book_count
        await session.execute(
            _update(Event)
            .where(Event.id == event_id)
            .values(win_probability_sources=_current)
        )
    elif snapshots_processed:
        # gotcha #53, in the odds pipeline: "no book quotes a moneyline" (a FACT
        # — the market has closed) and "we did not poll" (an absence) are the
        # same silence today, because both simply skip the write and leave a
        # stale `betting` in place. Naming the first one is the prerequisite for
        # ever treating them differently.
        logger.info(
            "event %s: %d bookmaker snapshot(s) processed but NO moneyline "
            "quoted by any book — market closed, not a polling gap (#1841). "
            "The prior betting consensus is left in place and is now stale.",
            event_id, snapshots_processed,
        )

    return snapshots_processed


# MLB pre-game polling tier (issue #892) — config.
# The main _poll_all_odds loop only selects sports with a game within 6h and
# drops to h2h-only beyond 2h out, so MLB's pitcher/lineup/weather-driven line
# moves 12-48h before first pitch (on ~64% of games per the #892 eval) get
# recorded as coarse multi-hour steps. This tier densely samples that dark
# window. Hard-scoped to MLB, us region, full game markets, 30-min cadence
# (~2.48%/mo per the #892 cost sizing — do NOT add us2).
MLB_PREGAME_SPORT_KEY = "baseball_mlb"
MLB_PREGAME_WINDOW_START_H = 2    # T-2h: hand off to the "soon" tier (no overlap)
MLB_PREGAME_WINDOW_END_H = 48     # T-48h: far edge of the pre-game window
MLB_PREGAME_MIN_INTERVAL = 1740   # ~29 min floor (beat fires every 30 min)
MLB_PREGAME_REGIONS = "us"        # us ONLY — adding us2 would double the cost (#892)
MLB_PREGAME_MARKETS = "h2h,spreads,totals"  # full game markets


async def _poll_mlb_pregame():
    """Densely poll MLB game odds in the T-48h..T-2h pre-game window (issue #892).

    MLB only, full game markets (h2h+spreads+totals), us region only, every
    30 min. The window ends at T-2h precisely so it never double-polls the
    "soon" tier (0-2h, full markets, every 5 min) which takes over at T-2h.

    Double-poll guard: the main _poll_all_odds loop polls MLB (full slate, all
    upcoming games in one call) whenever an MLB game sits inside its ±6h
    lookahead. When that's true it already covers the pre-game window, so this
    task skips. It only fires when the main loop is dormant for MLB — i.e. the
    dark window where pre-game sampling is otherwise sparse. This also keeps the
    tier strictly at-or-under the sized 2.48%/mo cost.
    """
    # Quota guard: pre-game enrichment is non-essential. Skip under any
    # conservation/live-only/full-stop pressure — live polling has priority.
    guard_ok, guard_reason = check_quota_guard(
        "poll_odds", sport_key=MLB_PREGAME_SPORT_KEY
    )
    if not guard_ok or "live_only" in guard_reason or "conservation" in guard_reason:
        return {"skipped": True, "reason": f"quota_guard:{guard_reason}"}

    try:
        r = get_redis_client()
    except Exception:
        r = None

    now = datetime.now(timezone.utc)

    # Per-sport interval gate (belt-and-suspenders with the 30-min beat).
    if r:
        try:
            last_key = f"bainluck:last_pregame_poll:{MLB_PREGAME_SPORT_KEY}"
            last = r.get(last_key)
            if last and (now.timestamp() - float(last.decode())) < MLB_PREGAME_MIN_INTERVAL:
                return {"skipped": True, "reason": "interval"}
        except Exception:
            pass

    window_start = now + timedelta(hours=MLB_PREGAME_WINDOW_START_H)
    window_end = now + timedelta(hours=MLB_PREGAME_WINDOW_END_H)

    service = OddsAPIService()
    total_events = 0
    total_snapshots = 0

    async with get_task_session() as session:
        # Double-poll guard: if the main loop is active for MLB (any MLB game in
        # [-6h, +6h]), it already polls the full slate — skip to avoid redundant
        # billing and double-writes.
        main_loop_active = await session.execute(
            select(func.count(Event.id))
            .join(Sport)
            .where(
                Sport.key == MLB_PREGAME_SPORT_KEY,
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time <= now + timedelta(hours=6),
                Event.commence_time >= now - timedelta(hours=6),
            )
        )
        if (main_loop_active.scalar() or 0) > 0:
            return {"skipped": True, "reason": "main_loop_active"}

        # Only spend quota when MLB actually has games in the pre-game window.
        pregame_count = await session.execute(
            select(func.count(Event.id))
            .join(Sport)
            .where(
                Sport.key == MLB_PREGAME_SPORT_KEY,
                Event.status == "scheduled",
                Event.commence_time >= window_start,
                Event.commence_time <= window_end,
            )
        )
        if (pregame_count.scalar() or 0) == 0:
            return {"skipped": True, "reason": "no_pregame_games"}

        # Full game markets, us region only (per #892 cost sizing — no us2).
        try:
            pre_used = service.last_requests_used
            events_data = await service.get_odds(
                MLB_PREGAME_SPORT_KEY,
                regions=MLB_PREGAME_REGIONS,
                markets=MLB_PREGAME_MARKETS,
            )
        except Exception as e:
            logger.warning("MLB pre-game poll failed: %s", e)
            return {"skipped": True, "reason": "api_error", "error": str(e)}

        # Record quota from response headers.
        if service.last_requests_remaining is not None:
            from app.tasks.redis_state import record_odds_api_quota
            record_odds_api_quota(
                service.last_requests_remaining,
                service.last_requests_used or 0,
                "poll_odds_pregame",
                pre_call_used=pre_used,
                sport_key=MLB_PREGAME_SPORT_KEY,
            )

        if r:
            try:
                r.set(
                    f"bainluck:last_pregame_poll:{MLB_PREGAME_SPORT_KEY}",
                    str(now.timestamp()), ex=7200,
                )
            except Exception:
                pass

        from app.services.event_registry import (
            find_or_create_event, EventIdentity, EventClaim,
        )
        snapshot_cache: dict = {}
        for event_data in events_data:
            commence_time = datetime.fromisoformat(
                event_data["commence_time"].replace("Z", "+00:00")
            )
            # The API returns the full MLB slate; only ingest games inside the
            # pre-game window so we never touch live/soon games owned by the
            # main loop (no double-write).
            if not (window_start <= commence_time <= window_end):
                continue

            identity = EventIdentity(
                sport_key=MLB_PREGAME_SPORT_KEY,
                home_team_name=event_data["home_team"],
                away_team_name=event_data["away_team"],
                commence_time=commence_time,
                # Ruling 048: NOT arm B — the Odds listing is not a dereference.
                claim=EventClaim(
                    "odds_api", event_data["id"],
                    schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE,
                ),
                commence_time_source="odds_api",
                status="scheduled",
            )
            event, was_created = await find_or_create_event(session, identity)
            if was_created:
                total_events += 1
            total_snapshots += await _ingest_event_odds(
                session, event, event_data, commence_time, snapshot_cache,
            )

        await session.commit()

    logger.info(
        "MLB pre-game poll: %d new events, %d snapshots in T-%dh..T-%dh window",
        total_events, total_snapshots,
        MLB_PREGAME_WINDOW_END_H, MLB_PREGAME_WINDOW_START_H,
    )
    return {
        "events": total_events,
        "snapshots": total_snapshots,
        "window_hours": [MLB_PREGAME_WINDOW_START_H, MLB_PREGAME_WINDOW_END_H],
    }


async def _poll_all_odds():
    """
    Async implementation of poll_all_odds with tiered per-sport polling.

    Tiered polling based on game proximity:
    - Live games (in progress): Poll every 60 seconds
    - Starting soon (0-2 hours): Poll every 5 minutes
    - Starting later (2-6 hours): Poll every 15 minutes
    - No games in 6 hours: Don't poll that sport

    Uses per-sport last poll times stored in Redis.
    Also fetches scores for live/completed games.
    """
    from app.tasks.excitement_index import update_live_ei as update_live_gei

    # Emergency quota guard: check overall quota level
    guard_ok, guard_reason = check_quota_guard("poll_odds")
    if not guard_ok:
        # Full stop — but priority sports may still be allowed (checked per-sport below)
        if "full_stop" in guard_reason:
            logger.info("poll_all_odds in FULL STOP — only priority sports allowed")
        else:
            logger.warning("poll_all_odds SKIPPED by quota guard: %s", guard_reason)
            return {"skipped": True, "reason": f"quota_guard:{guard_reason}"}

    # Check if we're in live-only mode (quota < QUOTA_GUARD_LIVE_ONLY)
    quota_live_only = "live_only" in guard_reason
    quota_full_stop = "full_stop" in guard_reason
    quota_conservation = quota_full_stop or "conservation" in guard_reason

    service = OddsAPIService()

    try:
        total_events = 0
        total_snapshots = 0
        all_events_data = []
        has_live_games = False
        sports_polled = 0
        sports_skipped = 0
        scores_updated = 0
        stat_model_from_poll = 0
        # #1981: every score write refused because the row's own commence says the
        # provider id on it names a DIFFERENT game. Counted, never silent — a guard
        # whose refusals are invisible is indistinguishable from a guard that is off.
        scores_refused_stale_id = 0
        scores_refused_unverifiable = 0
        scores_unbound_id = 0

        # Get Redis client for per-sport poll tracking
        try:
            r = get_redis_client()
        except Exception:
            r = None

        async with get_task_session() as session:
            now = datetime.now(timezone.utc)

            # Get all sports with upcoming/live games in the next 6 hours
            lookahead_6h = now + timedelta(hours=6)

            # Query to get sports with their soonest game time
            result = await session.execute(
                select(
                    Sport.key,
                    func.min(Event.commence_time).label("soonest_game"),
                    func.bool_or(Event.status == "live").label("has_live")
                )
                .join(Event)
                .where(
                    Sport.active == True,
                    Event.status.in_(["scheduled", "live"]),
                    Event.commence_time <= lookahead_6h,
                    Event.commence_time >= now - timedelta(hours=6)
                )
                .group_by(Sport.key)
            )
            sport_data = result.all()

            # Even if no sports need odds polling, we should still check for stale events
            # and update scores for recently started games
            if not sport_data:
                # Still run staleness detection for any live events that may have ended
                events_closed = await detect_and_close_stale_events(session)
                await session.commit()
                return {
                    "events": 0,
                    "snapshots": 0,
                    "sports": 0,
                    "sports_skipped": 0,
                    "events_closed": events_closed,
                    "message": "No sports with games in the next 6 hours.",
                    "skipped": True,
                }

            # Set when the per-sport quota re-read reports the absolute stop
            # mid-pass. `absolute_stop` means "no exceptions, no priority sports,
            # nothing" (redis_state.check_quota_guard), so it has to halt the
            # SCORES fetch too — that block runs off its own independent query and
            # consults no quota guard at all, so breaking the odds loop alone would
            # keep spending on `get_scores` while the breaker says stop.
            absolute_stop_hit = False

            for row in sport_data:
                sport_key = row[0]
                soonest_game = row[1]
                is_live = row[2]

                # Skip sports that returned 404 (cached for 24h)
                if r:
                    try:
                        if r.get(f"bainluck:sport_404:{sport_key}"):
                            sports_skipped += 1
                            continue
                    except Exception:
                        pass

                # Determine poll interval for this sport
                if is_live or (soonest_game and soonest_game <= now):
                    # Live game - poll every 32 seconds
                    poll_interval = LIVE_POLL_INTERVAL
                    tier = "live"
                    has_live_games = True
                elif soonest_game and soonest_game <= now + timedelta(hours=2):
                    # Starting soon (0-2 hours) - poll every 5 minutes
                    poll_interval = SOON_POLL_INTERVAL
                    tier = "soon"
                else:
                    # Starting later (2-6 hours) - poll every 1 hour
                    poll_interval = LATER_POLL_INTERVAL
                    tier = "later"

                # Sport-tier multiplier: Tier 2 polls 2x slower, Tier 3 polls 4x slower.
                # Core sports (Tier 1) keep default intervals; long-tail sports poll less.
                sport_tier = SPORT_POLLING_TIERS.get(sport_key, SPORT_POLLING_DEFAULT_TIER)
                poll_interval = tier_adjusted_interval(poll_interval, tier, sport_key)

                # Quota guard: in full-stop mode, only priority sports allowed
                if quota_full_stop:
                    if sport_key not in QUOTA_GUARD_PRIORITY_SPORTS:
                        sports_skipped += 1
                        continue
                    # Re-check per-sport to get the conservation reason.
                    #
                    # 🔴 CERT-528: this re-read used to be `_, guard_reason` plus
                    # `quota_conservation = "conservation" in guard_reason`. Both
                    # halves were fail-open, and the casualty was the outer
                    # FULL_STOP result — the thing we already knew:
                    #   * the allow/deny boolean was DISCARDED, so quota crossing
                    #     `absolute_stop` mid-pass ("no exceptions, no priority
                    #     sports, nothing") polled anyway;
                    #   * a transient Redis failure returns (True, "redis_error"),
                    #     which contains no "conservation", so the assignment
                    #     ERASED the floor set at line 859 and dropped a
                    #     known-constrained live sport to the flat live cadence.
                    # Both spend the constrained API at exactly the moment the
                    # circuit breaker says not to. The rule this encodes: within
                    # one pass a re-read may only ADD constraint, never remove it.
                    sport_ok, sport_reason = check_quota_guard(
                        "poll_odds", sport_key=sport_key
                    )
                    if "absolute_stop" in sport_reason:
                        # No exceptions — abandon the whole pass, not just this sport.
                        logger.critical(
                            "poll_all_odds ABSOLUTE STOP mid-pass (%s) — halting all polling",
                            sport_reason,
                        )
                        sports_skipped += 1
                        absolute_stop_hit = True
                        break
                    if not sport_ok:
                        sports_skipped += 1
                        continue
                    # Monotonic: a failed re-read (or one taken after quota
                    # refilled) can never clear the conservation floor the outer
                    # full-stop read established.
                    quota_conservation = quota_conservation or "conservation" in sport_reason
                    # In full-stop conservation, only poll live games
                    if tier != "live":
                        sports_skipped += 1
                        continue

                # Quota guard: in live-only mode, skip non-live sports entirely
                if quota_live_only and not quota_full_stop and tier != "live":
                    sports_skipped += 1
                    continue

                # 🔴 EVERY FLOOR IS APPLIED BEFORE THE ONE GATE THAT READS IT
                # (CERT-523). There is exactly one `elapsed < poll_interval`
                # check in this task, and `SPORT_MIN_POLL_INTERVALS` and
                # `QUOTA_GUARD_CONSERVATION_INTERVAL` used to be applied AFTER
                # it — so both were dead. Nothing downstream reads
                # `poll_interval`; the only thing it can affect is the skip
                # decision, and it was raised past the point where the decision
                # was taken. Live AFL gated at its tier interval and never at its
                # declared 600 s minimum, and FULL_STOP conservation never
                # slowed a live sport at all.
                #
                # That hole predates LAT-P159 and the queue's own cadence change
                # would have made it MATERIAL — a 10 s gate against a 600 s
                # declared floor, at exactly the moment quota is most
                # constrained. **Widening a rate must enumerate what the
                # widening newly admits** (LAT-P156's lesson, missed here first
                # time round and caught by CERT-523).
                #
                # `compute_effective_interval` is used rather than reimplemented:
                # it already applied the sport minimum, the conservation floor
                # and the adaptive slowdown in one place, and it was reachable
                # ONLY from its own tests — ~30 of them guarding a helper
                # production never called. Wiring it in is what makes those tests
                # mean something, and it is the remedy already written in the
                # repo (this lane's standing "grep for the problem, not the
                # remedy" rule).
                unchanged_count = 0
                if r:
                    try:
                        unchanged_raw = r.get(f"bainluck:unchanged_count:{sport_key}")
                        unchanged_count = int(unchanged_raw.decode()) if unchanged_raw else 0
                    except Exception:
                        unchanged_count = 0
                poll_interval = compute_effective_interval(
                    base_interval=poll_interval,
                    sport_key=sport_key,
                    tier=tier,
                    unchanged_count=unchanged_count,
                    quota_conservation=quota_conservation,
                )

                # Check if enough time has elapsed since last poll for this sport
                should_poll_sport = True
                if r:
                    try:
                        last_poll_key = f"bainluck:last_poll:{sport_key}"
                        last_poll = r.get(last_poll_key)
                        if last_poll:
                            last_poll_time = float(last_poll.decode())
                            elapsed = now.timestamp() - last_poll_time
                            if elapsed < poll_interval:
                                # Not enough time elapsed, skip this sport
                                should_poll_sport = False
                                sports_skipped += 1
                    except Exception:
                        pass  # If Redis fails, just poll

                if not should_poll_sport:
                    continue

                # Quota optimization: use lighter API params for non-live tiers.
                # - "later" tier: h2h only (saves 2/3 of billed requests per event)
                # - "soon"/"later" tiers: primary US bookmakers only (saves 1/2)
                # - "live" tier: full params for maximum coverage
                # - Conservation mode: always h2h + us only (even live)
                #
                # The per-sport minimum and the conservation floor USED to be
                # applied here, below the gate that is the only thing that reads
                # them (CERT-523). They now live above it, in
                # `compute_effective_interval`.
                if quota_conservation:
                    api_markets = "h2h"
                    api_regions = "us"
                elif tier == "live":
                    api_markets = "h2h,spreads,totals"
                    # Tier 1 sports get us+us2 for full bookmaker coverage;
                    # Tier 2-3 use us only to save quota.
                    api_regions = "us,us2" if sport_tier == 1 else "us"
                elif tier == "soon":
                    api_markets = "h2h,spreads,totals"
                    api_regions = "us,us2" if sport_tier == 1 else "us"
                else:  # "later" — h2h only, primary US only (saves ~83% vs live)
                    api_markets = "h2h"
                    api_regions = "us"

                # Per-sport region override (e.g., MLB -> us only for quota savings)
                region_override = SPORT_REGION_OVERRIDES.get(sport_key)
                if region_override and not quota_conservation:
                    api_regions = region_override

                try:
                    pre_used = service.last_requests_used
                    events_data = await service.get_odds(
                        sport_key,
                        regions=api_regions,
                        markets=api_markets,
                    )
                    all_events_data.extend(events_data)
                    sports_polled += 1

                    # Record quota from response headers
                    if service.last_requests_remaining is not None:
                        from app.tasks.redis_state import record_odds_api_quota
                        record_odds_api_quota(
                            service.last_requests_remaining,
                            service.last_requests_used or 0,
                            "poll_odds",
                            pre_call_used=pre_used,
                            sport_key=sport_key,
                        )

                    # Update last poll time and per-sport adaptive state in Redis
                    if r:
                        try:
                            last_poll_key = f"bainluck:last_poll:{sport_key}"
                            r.set(last_poll_key, str(now.timestamp()), ex=3600)

                            # Per-sport adaptive slowdown: track unchanged polls.
                            # Hash only the odds for this sport to detect per-sport changes.
                            sport_hash = compute_odds_hash(events_data)
                            prev_sport_hash_key = f"bainluck:odds_hash:{sport_key}"
                            unchanged_key = f"bainluck:unchanged_count:{sport_key}"
                            prev_sport_hash = r.get(prev_sport_hash_key)
                            prev_sport_hash = prev_sport_hash.decode() if prev_sport_hash else None

                            if prev_sport_hash and prev_sport_hash == sport_hash:
                                # Odds unchanged — increment counter
                                r.incr(unchanged_key)
                            else:
                                # Odds changed — reset counter
                                r.set(unchanged_key, "0", ex=7200)

                            r.set(prev_sport_hash_key, sport_hash, ex=7200)
                            r.expire(unchanged_key, 7200)
                        except Exception:
                            pass

                    # Snapshot cache to avoid N+1 queries in _create_or_update_snapshot.
                    # Accumulates across events within this sport batch.
                    snapshot_cache = {}

                    for event_data in events_data:
                        commence_time = datetime.fromisoformat(
                            event_data["commence_time"].replace("Z", "+00:00")
                        )

                        # ── Unified event matching via Event Registry ──
                        event_status = "scheduled" if commence_time > now else "live"
                        from app.services.event_registry import (
                            find_or_create_event, EventIdentity, EventClaim,
                        )
                        identity = EventIdentity(
                            sport_key=sport_key,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=commence_time,
                            # Ruling 048: NOT arm B — the Odds listing is not a
                            # dereference.
                            claim=EventClaim(
                                "odds_api", event_data["id"],
                                schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE,
                            ),
                            commence_time_source="odds_api",
                            status=event_status,
                        )
                        event, was_created = await find_or_create_event(
                            session, identity,
                        )
                        if was_created:
                            total_events += 1

                        # Create snapshots + opening-odds/betting consensus.
                        # Shared with the MLB pre-game tier via _ingest_event_odds
                        # so the two polling paths stay identical (issue #892).
                        total_snapshots += await _ingest_event_odds(
                            session, event, event_data, commence_time, snapshot_cache,
                        )

                except Exception as e:
                    # Cache 404 sports to avoid retrying for 24h
                    if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 404:
                        logger.info("Sport %s returned 404, skipping for 24h", sport_key)
                        if r:
                            try:
                                r.set(f"bainluck:sport_404:{sport_key}", "1", ex=86400)
                            except Exception:
                                pass
                    else:
                        logger.warning("Error polling %s: %s", sport_key, e)
                    continue

            # Fetch scores for sports with events that have started.
            # Rate-limited per-sport: ESPN-matched sports already get scores every
            # 60s from ESPN sync, so we only need the Odds API scores as a backup
            # for non-ESPN sports and for status transitions (completed detection).
            # 5-minute interval keeps scores fresh without burning quota every 30s.
            SCORE_FETCH_INTERVAL = 300  # 5 minutes per sport
            sports_needing_scores = await session.execute(
                select(Sport.key)
                .join(Event)
                .where(
                    Sport.active == True,
                    Event.commence_time <= now,
                    Event.commence_time >= now - timedelta(days=3),
                    Event.status.in_(["scheduled", "live", "completed", "closed"]),
                )
                .distinct()
            )
            sports_for_scores = [row[0] for row in sports_needing_scores.all()]

            if absolute_stop_hit:
                # The breaker said stop with no exceptions; scores are Odds API
                # calls like any other.
                sports_for_scores = []

            from app.utils.sport_keys import ESPN_SPORT_MAPPING

            # Skip score fetching for ESPN-mapped sports where ALL recent
            # events have espn_event_id (ESPN already provides scores faster).
            espn_covered_sports = set()
            for sport_key in sports_for_scores:
                if sport_key in ESPN_SPORT_MAPPING:
                    unmatched = await session.execute(
                        select(func.count(Event.id))
                        .join(Sport)
                        .where(
                            Sport.key == sport_key,
                            Event.commence_time <= now,
                            Event.commence_time >= now - timedelta(days=3),
                            Event.status.in_(["scheduled", "live"]),
                            Event.espn_id.is_(None),
                        )
                    )
                    if (unmatched.scalar() or 0) == 0:
                        espn_covered_sports.add(sport_key)

            for sport_key in sports_for_scores:
                if sport_key in espn_covered_sports:
                    continue

                # Skip sports that returned 404 (cached for 24h)
                if r:
                    try:
                        if r.get(f"bainluck:sport_404:{sport_key}"):
                            continue
                    except Exception:
                        pass

                # Per-sport rate limiting for score fetches
                if r:
                    try:
                        last_score_key = f"bainluck:last_score_fetch:{sport_key}"
                        last_score = r.get(last_score_key)
                        if last_score:
                            elapsed = now.timestamp() - float(last_score.decode())
                            if elapsed < SCORE_FETCH_INTERVAL:
                                continue
                    except Exception:
                        pass

                try:
                    pre_used = service.last_requests_used
                    scores_data = await service.get_scores(sport_key, days_from=3)

                    # Track score API quota usage
                    if service.last_requests_remaining is not None:
                        from app.tasks.redis_state import record_odds_api_quota
                        record_odds_api_quota(
                            service.last_requests_remaining,
                            service.last_requests_used or 0,
                            "score_fetch",
                            pre_call_used=pre_used,
                            sport_key=sport_key,
                        )

                    # Record last fetch time for rate limiting
                    if r:
                        try:
                            r.set(f"bainluck:last_score_fetch:{sport_key}", str(now.timestamp()), ex=3600)
                        except Exception:
                            pass

                    # Pre-load events for score updates to avoid N+1
                    _score_ext_ids = [s.get("id") for s in scores_data if s.get("id")]
                    _score_events_by_ext = {}
                    if _score_ext_ids:
                        _score_result = await session.execute(
                            select(Event).where(Event.external_id.in_(_score_ext_ids))
                        )
                        for _se in _score_result.scalars().all():
                            _score_events_by_ext[_se.external_id] = _se

                    for score_event in scores_data:
                        try:
                            external_id = score_event.get("id")
                            is_completed = score_event.get("completed", False)

                            # Parse scores from the API response
                            event_scores = score_event.get("scores")
                            home_team = score_event.get("home_team")
                            away_team = score_event.get("away_team")

                            # Find scores for home and away teams
                            home_score = None
                            away_score = None

                            if event_scores is not None and len(event_scores) > 0:
                                for team_score in event_scores:
                                    score_str = team_score.get("score")
                                    # Safely parse score - handles empty strings, None, non-numeric
                                    # Note: score of 0 is valid and should be stored
                                    try:
                                        if score_str is not None and score_str != "":
                                            score_val = int(score_str)
                                        else:
                                            score_val = None
                                    except (ValueError, TypeError):
                                        score_val = None

                                    team_name = team_score.get("name")
                                    if team_name == home_team:
                                        home_score = score_val
                                    elif team_name == away_team:
                                        away_score = score_val

                            # Determine status from scores API response.
                            # CRITICAL: Only set "live" if the event has actually started.
                            # The Scores API returns upcoming events with completed=False,
                            # which would incorrectly set scheduled games to "live".
                            score_commence_str = score_event.get("commence_time")
                            if score_commence_str:
                                try:
                                    score_commence = datetime.fromisoformat(
                                        score_commence_str.replace("Z", "+00:00")
                                    )
                                except (ValueError, TypeError):
                                    score_commence = None
                            else:
                                score_commence = None

                            # #1981 — THE GUARD. Everything below this point writes to a
                            # row we found BY `external_id`, so `external_id` cannot also
                            # be the evidence that the row is the right one; that is
                            # circular, and it is exactly how this site stamped the
                            # previous night's final onto the next night's game every
                            # SCORE_FETCH_INTERVAL seconds. The row's OWN commence_time is
                            # the independent signal, so ask it: is the id on this row
                            # still current?
                            #
                            # Ruling (b)(2), queue 371: the writer owns `external_id`
                            # currency — it re-verifies, re-binds, or nulls a stale id; it
                            # never compares against one. This site takes the RE-VERIFY
                            # arm and refuses. It deliberately does NOT re-bind or null
                            # here: `events.external_id` is UNIQUE, so nulling a stale id
                            # with no replacement makes the next discovery pass create a
                            # duplicate of a game that is on tonight's slate, and re-binding
                            # is an attended repair with a reviewed population and an Alex
                            # MC (#1981 cleanup, queue 371 item 5) — not something a 300s
                            # poller does to production rows unwatched.
                            event_obj = _score_events_by_ext.get(external_id)
                            currency = external_id_currency(
                                event_obj.commence_time if event_obj else None,
                                score_commence,
                                row_found=event_obj is not None,
                            )
                            if currency is not IdCurrency.CURRENT:
                                if currency is IdCurrency.STALE:
                                    scores_refused_stale_id += 1
                                    logger.warning(
                                        "#1981 refused score write: external_id %s is STALE on "
                                        "event %s (row commence %s) — provider record is %s @ %s, "
                                        "start %s. No write made; the stale binding needs the "
                                        "attended repair.",
                                        external_id,
                                        event_obj.id,
                                        event_obj.commence_time,
                                        away_team,
                                        home_team,
                                        score_commence,
                                    )
                                elif currency is IdCurrency.UNVERIFIABLE:
                                    scores_refused_unverifiable += 1
                                    logger.warning(
                                        "#1981 refused score write: cannot verify external_id %s "
                                        "on event %s — row commence %s, provider start %s. A check "
                                        "that could not run is not a check that passed.",
                                        external_id,
                                        event_obj.id,
                                        event_obj.commence_time,
                                        score_commence,
                                    )
                                else:  # UNBOUND — no row of ours holds this provider id
                                    scores_unbound_id += 1
                                continue

                            if is_completed and (not score_commence or score_commence <= now):
                                event_status = "completed"
                            elif is_completed and score_commence and score_commence > now:
                                event_status = None
                            elif score_commence and score_commence <= now:
                                event_status = "live"
                            elif home_score is not None and away_score is not None:
                                event_status = "live"
                            else:
                                event_status = None

                            update_values = {}
                            if event_status is not None:
                                update_values["status"] = event_status
                            if event_status == "completed" and not event_obj.completed_at:
                                update_values["completed_at"] = now

                            if home_score is not None:
                                update_values["home_score"] = home_score
                            if away_score is not None:
                                update_values["away_score"] = away_score

                            # Record score snapshot if scores changed
                            if home_score is not None and away_score is not None:
                                old_home = event_obj.home_score
                                old_away = event_obj.away_score
                                if old_home != home_score or old_away != away_score:
                                    # Score changed - record a snapshot
                                    score_snap = ScoreSnapshot(
                                        event_id=event_obj.id,
                                        home_score=home_score,
                                        away_score=away_score,
                                    )
                                    session.add(score_snap)

                            if update_values:
                                # Write to the row we VERIFIED, by primary key. Addressing
                                # the UPDATE by `external_id` again would re-open the gap
                                # the guard just closed: the row checked and the row written
                                # would be joined by nothing but the id under suspicion.
                                await session.execute(
                                    Event.__table__.update()
                                    .where(Event.id == event_obj.id)
                                    .values(**update_values)
                                )
                            scores_updated += 1

                            # Compute stat model for live events WITHOUT an ESPN link.
                            # Events with espn_id get stat_model from ESPN sync
                            # (which has authoritative clock/period data). Running
                            # both paths causes oscillation: ESPN sync writes from
                            # ESPN scores, odds_polling writes from Odds API scores
                            # with stale ESPN clock data, and they fight.
                            if (
                                event_obj
                                and event_status == "live"
                                and not event_obj.espn_id
                                and home_score is not None
                                and away_score is not None
                                and (event_obj.game_clock or event_obj.period or event_obj.commence_time)
                            ):
                                try:
                                    from app.utils.win_probability import compute_statistical_win_prob

                                    pregame_spread = None
                                    if event_obj.opening_home_spread is not None:
                                        pregame_spread = float(event_obj.opening_home_spread)

                                    stat_wp = compute_statistical_win_prob(
                                        home_score=home_score,
                                        away_score=away_score,
                                        clock=event_obj.game_clock,
                                        period=event_obj.period,
                                        sport_key=sport_key,
                                        pregame_spread=pregame_spread,
                                        commence_time=event_obj.commence_time,
                                    )
                                    if (stat_wp is not None and pregame_spread is None
                                            and home_score == 0 and away_score == 0
                                            and event_obj.opening_home_probability is not None):
                                        stat_wp = float(event_obj.opening_home_probability)
                                    if stat_wp is not None:
                                        # Update event's win_probability_sources
                                        # Need to re-fetch to get current JSONB
                                        # Write stat_model to win_probability_sources.
                                        # Use event object from batch pre-load (N+1 fix).
                                        from sqlalchemy import update as _sql_upd
                                        from app.utils.aggregation import (
                                            stamp_source_reading as _stamp,
                                        )
                                        _sm_wps = _stamp(
                                            event_obj.win_probability_sources,
                                            "stat_model",
                                            round(stat_wp, 4),
                                        )
                                        await session.execute(
                                            _sql_upd(Event)
                                            .where(Event.id == event_obj.id)
                                            .values(win_probability_sources=_sm_wps)
                                        )

                                        stat_snap, is_new = await _create_or_update_win_prob_snapshot(
                                            session,
                                            event_id=event_obj.id,
                                            source="stat_model",
                                            home_win_probability=round(stat_wp, 4),
                                            away_win_probability=round(1.0 - stat_wp, 4),
                                            game_state={
                                                "clock": event_obj.game_clock,
                                                "period": event_obj.period,
                                                "home_score": home_score,
                                                "away_score": away_score,
                                                "pregame_spread": pregame_spread,
                                                "source": "odds_poll",
                                                "time_source": "espn" if event_obj.game_clock else "wall_clock",
                                            },
                                        )
                                        if is_new:
                                            session.add(stat_snap)
                                        stat_model_from_poll += 1
                                except Exception as e:
                                    logger.warning(f"stat_model in odds poll failed for event {event_obj.id}: {e}")

                        except Exception as e:
                            logger.warning("Error updating score for event %s: %s", score_event.get('id'), e)
                            continue

                except Exception as e:
                    if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 404:
                        logger.info("Scores for %s returned 404, skipping for 24h", sport_key)
                        if r:
                            try:
                                r.set(f"bainluck:sport_404:{sport_key}", "1", ex=86400)
                            except Exception:
                                pass
                    else:
                        logger.warning("Error fetching scores for %s: %s", sport_key, e)
                    continue

            # Detect and mark stale events as "closed"
            # This catches matches that the Scores API didn't report as completed
            events_closed = await detect_and_close_stale_events(session)

            # Update GEI for all live events (real-time excitement scores)
            live_gei_updated = 0
            if has_live_games:
                live_gei_updated = await update_live_gei(session)

            await session.commit()

        # Compute hash and check for changes
        new_hash = compute_odds_hash(all_events_data)

        # Get previous hash to detect changes
        try:
            r = get_redis_client()
            prev_hash = r.hget(POLL_STATE_KEY, "last_hash")
            prev_hash = prev_hash.decode() if prev_hash else None
        except Exception:
            prev_hash = None

        data_changed = prev_hash is None or prev_hash != new_hash

        # Update adaptive polling state
        update_poll_state(data_changed, has_live_games, new_hash)

        return {
            "events": total_events,
            "snapshots": total_snapshots,
            "sports_polled": sports_polled,
            "sports_skipped": sports_skipped,
            "scores_updated": scores_updated,
            # #1981 — the guard's refusals ride out with the run so a spike is legible
            # from `task-metrics` without reading logs. A non-zero `stale_id` count is a
            # standing population for the attended `external_id` repair, not noise.
            "scores_refused_stale_id": scores_refused_stale_id,
            "scores_refused_unverifiable": scores_refused_unverifiable,
            "scores_unbound_id": scores_unbound_id,
            "stat_model_from_poll": stat_model_from_poll,
            "events_closed": events_closed,
            "live_gei_updated": live_gei_updated,
            "data_changed": data_changed,
            "has_live_games": has_live_games,
        }
    finally:
        await service.close()


async def _poll_sport_odds(sport_key: str):
    """Async implementation of poll_sport_odds."""
    service = OddsAPIService()

    try:
        events_data = await service.get_odds(sport_key)

        async with get_task_session() as session:
            # Get or create sport
            result = await session.execute(
                select(Sport).where(Sport.key == sport_key)
            )
            sport = result.scalar_one_or_none()

            if not sport:
                sport = Sport(
                    key=sport_key,
                    name=sport_key.replace("_", " ").title(),
                    active=True,
                )
                session.add(sport)
                await session.flush()

            total_snapshots = 0

            for event_data in events_data:
                commence_time = datetime.fromisoformat(
                    event_data["commence_time"].replace("Z", "+00:00")
                )

                event_status = "scheduled" if commence_time > datetime.now(timezone.utc) else "live"

                # ── Unified event matching via Event Registry ──
                from app.services.event_registry import (
                    find_or_create_event, EventIdentity, EventClaim,
                )
                identity = EventIdentity(
                    sport_key=sport_key,
                    home_team_name=event_data["home_team"],
                    away_team_name=event_data["away_team"],
                    commence_time=commence_time,
                    # Ruling 048: NOT arm B — the Odds listing is not a dereference.
                    claim=EventClaim(
                        "odds_api", event_data["id"],
                        schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE,
                    ),
                    commence_time_source="odds_api",
                    status=event_status,
                )
                event, was_created = await find_or_create_event(
                    session, identity,
                )
                event_id = event.id

                for bookmaker in event_data.get("bookmakers", []):
                    snapshot = await _create_snapshot(event_id, bookmaker, event_data)
                    session.add(snapshot)
                    total_snapshots += 1

            await session.commit()

        return {
            "sport": sport_key,
            "events": len(events_data),
            "snapshots": total_snapshots,
        }
    finally:
        await service.close()
