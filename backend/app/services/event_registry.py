"""
Unified Event Registry — single entry point for event creation and matching.

All sources (Odds API, ESPN, StatPal, Kalshi, Polymarket) call find_or_create_event()
when they encounter a game. First source in creates the event; every subsequent source
finds it and attaches its source ID. No duplicates.

Matching cascade:
1. Exact source ID — check if this source already claimed an event
2. Cross-source ID — check if ANY source already claimed it via other ID columns
3. Structured match — sport + commence_time ± _MATCH_WINDOW (28h) + names_match on both teams
4. Create — no match found, create new event
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Sport
from app.utils.espn_helpers import commence_correction_inverts_completion
from app.utils.name_normalization import names_match

logger = logging.getLogger(__name__)

# Source priority for field updates (higher index = higher priority)
_SOURCE_PRIORITY = {
    "kalshi": 0,
    "polymarket": 0,
    "odds_api": 1,
    "statpal": 2,
    "espn": 3,
}

# Time window for structured matching (±28 hours covers Kalshi settlement
# dates that are 24h off from game start, and UTC/local date boundary issues)
_MATCH_WINDOW = timedelta(hours=28)  # Wide enough for cross-source date disagreements (Kalshi settlement vs game start)

# Maximum retries on IntegrityError (race condition between concurrent tasks)
_MAX_RETRIES = 2

# Max structured-match candidates scanned per lookup (#1085). The old value (30)
# silently truncated the candidate set: prediction-market auto-creates that fall
# back to a batch-shared ``now`` commence_time (gotcha #14 — no real game time on
# the market) collapse EVERY same-day, same-sport event onto one identical
# timestamp, so the ±28h window can hold a full day's slate. NCAA baseball hit
# 177 events on one timestamp on 2026-07-13; with an un-ordered LIMIT 30 the true
# same-game sibling was usually not among the 30 rows returned, so the structured
# match missed and Step 4 created a duplicate every matching cycle (a treadmill
# the 30-min merge task could never drain). We now ORDER BY time-proximity (so the
# real siblings, which share the collapsed timestamp, sort first) AND raise the
# cap well above any realistic single-sport-day count so the sibling is always in
# the scanned set. names_match still guards the final decision, so a larger set
# can only surface true matches, never invent false ones.
_STRUCTURED_MATCH_CANDIDATE_LIMIT = 500


@dataclass
class EventClaim:
    """A source's claim on an event — its external ID for this source."""
    source: str      # "odds_api", "statpal", "espn", "kalshi", "polymarket"
    source_id: str   # The external ID from that source


@dataclass
class EventIdentity:
    """The structured data needed to find or create an event."""
    sport_key: str           # e.g., "basketball_nba"
    home_team_name: str
    away_team_name: str
    commence_time: datetime  # timezone-aware UTC
    claim: EventClaim

    # Optional enrichment
    commence_time_source: Optional[str] = None  # "odds_api", "espn", "statpal"
    status: Optional[str] = None  # "scheduled" or "live"


async def find_or_create_event(
    session: AsyncSession,
    identity: EventIdentity,
) -> tuple[Event, bool]:
    """Find an existing event or create a new one. Returns (event, was_created).

    Thread-safe via optimistic locking with retry on IntegrityError.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            # Resolve sport_key to sport_id
            sport_id = await _resolve_sport_id(session, identity.sport_key)
            if not sport_id:
                raise ValueError(f"Unknown sport key: {identity.sport_key}")

            # Steps 1-3: Try to find existing event
            event = await _find_existing(session, identity, sport_id)
            if event:
                _attach_claim(event, identity.claim)
                _update_fields_by_priority(event, identity)
                await session.flush()
                return event, False

            # #210 / gotcha #32: never CREATE a teamless placeholder event. A
            # mislinked prediction-market prop (e.g. a World Cup corner/round
            # market) can arrive with blank team names; fabricating an event for
            # it spawns the teamless phantom rows the WC concept page then has to
            # filter out at render time (#209 Item 3's _match_is_real). Refuse the
            # CREATE — the prediction-market auto-create caller catches ValueError
            # and skips linking. Steps 1-3 above may still ATTACH such a claim to
            # a REAL event by source id; only fabrication of a new teamless row is
            # blocked here.
            if (
                not (identity.home_team_name or "").strip()
                or not (identity.away_team_name or "").strip()
            ):
                raise ValueError(
                    "refusing to create teamless event "
                    f"(home={identity.home_team_name!r} away={identity.away_team_name!r}, "
                    f"source={identity.claim.source})"
                )

            # Step 4: Create new event
            status = identity.status or "scheduled"
            event = Event(
                sport_id=sport_id,
                home_team_name=identity.home_team_name,
                away_team_name=identity.away_team_name,
                commence_time=identity.commence_time,
                commence_time_source=identity.commence_time_source or identity.claim.source,
                status=status,
            )
            _attach_claim(event, identity.claim)
            session.add(event)
            await session.flush()

            logger.info(
                "Created event %d: %s vs %s (%s, %s) [source=%s]",
                event.id, identity.home_team_name, identity.away_team_name,
                identity.sport_key, identity.commence_time.isoformat(),
                identity.claim.source,
            )
            return event, True

        except IntegrityError:
            await session.rollback()
            if attempt < _MAX_RETRIES:
                logger.info(
                    "IntegrityError on event creation (attempt %d), retrying: %s vs %s",
                    attempt + 1, identity.home_team_name, identity.away_team_name,
                )
                continue
            raise


async def _find_existing(
    session: AsyncSession,
    identity: EventIdentity,
    sport_id: int,
) -> Optional[Event]:
    """Find an existing event via the 3-step cascade."""

    # Step 1: Exact source ID lookup
    event = await _find_by_source_id(session, identity.claim)
    if event:
        return event

    # Step 2: Cross-source ID lookup (not applicable for the first source,
    # but handles cases where we have the ESPN ID and want to find
    # the event created by Odds API)
    # This step is implicit — Step 3 will find it by sport+date+teams

    # Step 3: Structured match — sport + date + teams
    event = await _find_by_structured_match(
        session, sport_id,
        identity.home_team_name, identity.away_team_name,
        identity.commence_time,
    )
    if event:
        return event

    return None


async def _find_by_source_id(
    session: AsyncSession,
    claim: EventClaim,
) -> Optional[Event]:
    """Step 1: Find event by this source's specific ID column."""
    if claim.source == "odds_api":
        result = await session.execute(
            select(Event).where(Event.external_id == claim.source_id)
        )
    elif claim.source == "statpal":
        result = await session.execute(
            select(Event).where(Event.statpal_fixture_id == claim.source_id)
        )
    elif claim.source == "espn":
        result = await session.execute(
            select(Event).where(Event.espn_id == claim.source_id)
        )
    else:
        # Kalshi/Polymarket don't have direct ID columns on events
        return None

    return result.scalar_one_or_none()


async def _find_by_structured_match(
    session: AsyncSession,
    sport_id: int,
    home_team: str,
    away_team: str,
    commence_time: datetime,
) -> Optional[Event]:
    """Step 3: Find event by sport + date + team names.

    Queries events with the same sport_id and commence_time within
    ±_MATCH_WINDOW (28h), then scores each candidate using names_match().
    Requires BOTH teams to match (either in normal or swapped home/away
    orientation).

    Uses a PostgreSQL advisory lock to prevent TOCTOU race conditions when
    concurrent workers (ESPN sync on realtime, Odds API on background) both
    call find_or_create_event() for the same game simultaneously.
    """
    from sqlalchemy import text as _text
    lock_key = hash((sport_id, commence_time.date().isoformat())) & 0x7FFFFFFF
    await session.execute(_text(f"SELECT pg_advisory_xact_lock({lock_key})"))

    candidates_result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.commence_time.between(
                commence_time - _MATCH_WINDOW,
                commence_time + _MATCH_WINDOW,
            ),
            Event.status.in_(["scheduled", "live", "completed", "closed"]),
        )
        # #1085: order closest-in-time first so the true same-game sibling — which
        # shares this event's (often collapsed) commence_time — is always retained
        # even when the cap binds; then take a generous slice (see the constant).
        .order_by(
            func.abs(func.extract("epoch", Event.commence_time - commence_time))
        )
        .limit(_STRUCTURED_MATCH_CANDIDATE_LIMIT)
    )
    candidates = candidates_result.scalars().all()

    # Score all name-matching candidates and pick the closest by time.
    # This handles doubleheaders: Game 1 at 1 PM and Game 2 at 7 PM both
    # match by team names, but the closer one wins.
    matches = []
    for candidate in candidates:
        matched = False
        # Normal orientation
        if (names_match(home_team, candidate.home_team_name) and
                names_match(away_team, candidate.away_team_name)):
            matched = True
        # Swapped orientation
        elif (names_match(home_team, candidate.away_team_name) and
                names_match(away_team, candidate.home_team_name)):
            matched = True

        if matched:
            time_diff = abs((commence_time - candidate.commence_time).total_seconds())
            matches.append((time_diff, candidate))

    if matches:
        matches.sort(key=lambda x: x[0])
        return matches[0][1]

    return None


def _attach_claim(event: Event, claim: EventClaim) -> None:
    """Attach a source's ID to an event. Idempotent — won't overwrite existing IDs."""
    if claim.source == "odds_api":
        if not event.external_id:
            event.external_id = claim.source_id
        elif event.external_id != claim.source_id:
            logger.info(
                "Event %d already has external_id=%s, incoming=%s (same game, different API ID)",
                event.id, event.external_id, claim.source_id,
            )
    elif claim.source == "statpal":
        if not event.statpal_fixture_id:
            event.statpal_fixture_id = claim.source_id
    elif claim.source == "espn":
        if not event.espn_id:
            event.espn_id = claim.source_id


def _update_fields_by_priority(event: Event, identity: EventIdentity) -> None:
    """Update event fields if the incoming source has higher priority.

    Source priority: ESPN > StatPal > Odds API > prediction markets.
    Higher-priority sources overwrite team names and commence_time.
    """
    incoming_priority = _SOURCE_PRIORITY.get(identity.claim.source, 0)
    current_priority = _SOURCE_PRIORITY.get(event.commence_time_source or "", 0)

    if incoming_priority > current_priority:
        # Higher-priority source: update team names and time
        if identity.home_team_name:
            event.home_team_name = identity.home_team_name
        if identity.away_team_name:
            event.away_team_name = identity.away_team_name
        if identity.commence_time:
            # Guard (#46 invariant; gotcha #32 family): refuse to move
            # commence_time to a value AFTER an already-completed event's
            # completed_at. That inversion (completed_at < commence_time) means we
            # folded a higher-priority source's forward commence_time onto the
            # WRONG sibling (series row-reuse / doubleheader). The ESPN write path
            # already guards this; the registry did not. Only the commence_time
            # move is refused — team-name updates above still apply.
            if event.completed_at is not None and commence_correction_inverts_completion(
                identity.commence_time, event.completed_at
            ):
                logger.warning(
                    "Refusing commence_time move on completed event %s: incoming "
                    "commence=%s is AFTER completed_at=%s (would invert #46 "
                    "invariant — likely wrong-sibling match from source %s)",
                    event.id, identity.commence_time, event.completed_at,
                    identity.claim.source,
                )
            else:
                event.commence_time = identity.commence_time
                event.commence_time_source = identity.commence_time_source or identity.claim.source


# ── Sport resolution cache ──────────────────────────────────────────

_sport_id_cache: dict[str, int] = {}


async def _resolve_sport_id(session: AsyncSession, sport_key: str) -> Optional[int]:
    """Resolve sport key string to sport_id integer. Cached."""
    if sport_key in _sport_id_cache:
        return _sport_id_cache[sport_key]

    result = await session.execute(
        select(Sport.id).where(Sport.key == sport_key)
    )
    row = result.first()
    if row:
        _sport_id_cache[sport_key] = row.id
        return row.id
    return None


# ── Post-creation audit ─────────────────────────────────────────────

async def audit_event_counts(
    session: AsyncSession,
    sport_key: str,
    espn_events_by_date: dict[str, list],
) -> list[dict]:
    """Compare our event count per date against ESPN's schedule count.

    Returns a list of date/sport pairs where we have MORE events than
    ESPN, indicating possible duplicates.
    """
    from sqlalchemy import func

    sport_id = await _resolve_sport_id(session, sport_key)
    if not sport_id:
        return []

    alerts = []
    for date_str, espn_events in espn_events_by_date.items():
        espn_count = len(espn_events)
        if espn_count == 0:
            continue

        # Count our scheduled/live events for this sport on this date
        # Use a 36-hour window to catch UTC boundary crossings
        from datetime import datetime as _dt
        try:
            date_noon = _dt.strptime(date_str, "%Y%m%d").replace(
                hour=12, tzinfo=timezone.utc
            )
        except ValueError:
            continue

        our_count_result = await session.execute(
            select(func.count(Event.id)).where(
                Event.sport_id == sport_id,
                Event.commence_time.between(
                    date_noon - timedelta(hours=18),
                    date_noon + timedelta(hours=18),
                ),
                Event.status.in_(["scheduled", "live"]),
            )
        )
        our_count = our_count_result.scalar() or 0

        if our_count > espn_count:
            alerts.append({
                "sport_key": sport_key,
                "date": date_str,
                "our_count": our_count,
                "espn_count": espn_count,
                "excess": our_count - espn_count,
            })
            logger.warning(
                "DUPLICATE ALERT: %s on %s — we have %d events, ESPN has %d (excess: %d)",
                sport_key, date_str, our_count, espn_count, our_count - espn_count,
            )

    return alerts
