"""
Unified Event Registry — single entry point for event creation and matching.

All sources (Odds API, ESPN, StatPal, Kalshi, Polymarket) call find_or_create_event()
when they encounter a game. First source in creates the event; every subsequent source
finds it and attaches its source ID. No duplicates.

Matching cascade:
1. Exact source ID — check if this source already claimed an event
2. Cross-source ID — check if ANY source already claimed it via other ID columns
3. Structured match — sport + commence_time ± _MATCH_WINDOW (28h) + names_match on both teams,
   skipping candidates that (a) already hold a DIFFERENT game id from the incoming provider,
   (b) were individuated by ANY provider and disagree about the start by >2h, or (c) were
   individuated by nobody but carry a published start time >12h from the claim's (#1779)
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

# How far two SCHEDULE sources may disagree about one game's start before we stop
# believing they are describing the same game (#1802, Codex C-CERT-1801).
#
# The ±28h window above is a statement about SETTLEMENT dates, not start times: a
# Kalshi settlement date legitimately sits 24h off the first pitch. But once a row
# has been individuated by a schedule provider, the incoming claim's own start time
# is real evidence, and 24h of disagreement is not a timezone — it is tomorrow's game.
#
# Two hours: comfortably above any genuine cross-provider disagreement (they publish
# the same scheduled start; a TV move or an early rain-delay correction is the
# realistic worst case), and comfortably below both the ~3h that separates a
# doubleheader's second game and the 24h of a consecutive-day series.
_CROSS_PROVIDER_SAME_GAME_WINDOW = timedelta(hours=2)

# The same question for rows NO schedule provider has individuated (#1779 R3).
#
# The two guards above only speak when an id exists. Where the candidate carries
# none, nothing fires and the full ±28h window plus its closest-by-time tiebreaker
# decide exactly as they did before #1779 — i.e. the original defect is intact for
# that population, and that population is the LARGEST one we have: 63,952 of the
# 72,918 events in the last 90 days (88%) hold no odds_api / ESPN / StatPal id at
# all. Esports alone contributes 13,773 of them. Alex's bar is not scoped to rows
# that happen to have ids: *no absorption of a distinct scheduled game, full stop.*
#
# WHAT SIGNAL IS LEFT WHEN THERE IS NO ID. With no id, a 24h delta could be (i) one
# game whose start one source got wrong — the case the wide window exists for — or
# (ii) game 2 of a series. Names and times cannot tell those apart, so the question
# is what to do when you cannot tell, and the answer follows from the asymmetry of
# the two mistakes:
#
#   * A wrong CREATE leaves a duplicate event. Visible, mergeable, and the Flow
#     Sentinel already hunts duplicates (its first catch was 21 of them).
#   * A wrong ABSORB leaves a vanished game. Invisible to every check we own,
#     because an absence has no field to be wrong — which is exactly why #1779 ran
#     for days until Alex personally went looking for a Red Sox game.
#
# So we fail closed toward CREATING.
#
# A PLAIN DISTANCE FLOOR IS NOT ENOUGH, AND THE MEASUREMENT SAYS WHY. The obvious
# move is "id-less rows get a smaller window". It is wrong on its own, because most
# id-less rows have no clock to measure against. The prediction-market auto-create
# (tasks/prediction_market_matching.py::_create_event_from_prediction_market)
# substitutes ``now`` when the market has no usable commence_time, so a whole batch
# of unrelated games lands on one instant — measured in production 2026-08-13:
#
#     SELECT commence_time, count(*), count(DISTINCT sport_id) FROM events
#      WHERE commence_time > now() - interval '120 days'
#        AND external_id IS NULL AND espn_id IS NULL AND statpal_fixture_id IS NULL
#        AND commence_time <> date_trunc('minute', commence_time)
#      GROUP BY 1 ORDER BY 2 DESC;
#     -- 2026-05-13 18:35:00.015358+00  →  3,749 events across 10 sports
#
# 73% of id-less rows (e.g. esports 10,097/13,773) carry such a fabricated stamp.
# Applying a distance rule to those would refuse the join that #1085 exists to
# protect and re-open the NCAA-baseball duplicate treadmill. Conversely 16,638 of
# 16,777 (99.2%) of individuated rows sit on a whole minute, and 98.7% of the
# whole-minute id-less rows sit on a 5-minute boundary: a published start time is
# always a whole minute; ``datetime.now()`` essentially never is.
#
# THE PREDICATE: a distance rule applies only when BOTH sides actually have a clock
# — both commence_times are whole-minute, i.e. published start times rather than
# fabricated ones. Where either side's clock is fabricated the wide window survives
# untouched, because there is genuinely no information to rule on.
#
# THE THRESHOLD, AND HOW IT WAS CHOSEN. Gap histogram of consecutive same-sport,
# same-matchup id-less events whose times are BOTH whole-minute (120 days,
# 2026-08-13):
#
#     hours: 0    1-7  8-16  17-19  20-25          26+
#     pairs: 2747 94   24    30     265 (114 @ 24h) 14
#
# Two populations with a desert between them. Below ~1h: the same row seen twice.
# From 20h to 25h, peaking at exactly 24h: the consecutive-day series — the #1779
# class. Between them, 8–16h averages 2.7 pairs/hour against 44/hour in the 20–25h
# band, a 16× density step. Twelve hours sits in the deepest part of that desert
# and has a meaning, not just a percentile: it is the largest disagreement a CLOCK
# error can produce. Two sources reading the same instant off different clocks can
# differ by at most a timezone; more than half a day apart is not a clock error, it
# is a different calendar day, which is a different game. Re-derive with the query
# above before changing this number.
#
# WHAT THIS COSTS. (1) A Kalshi settlement date sitting a full 24h after a real
# start, on a row nothing has individuated, now creates a duplicate instead of
# joining — visible and mergeable, per the asymmetry. (2) Timezones beyond ±12
# (Kiribati, Chatham) would be misread; no league we carry plays there, and the
# cost is again a duplicate. (3) The 73% of id-less rows whose clock is fabricated
# are NOT protected by this rule and cannot be, from names and times alone: nothing
# has scheduled them, so there is no "distinct scheduled game" to observe. The
# honest fix for that residual is upstream — stop fabricating a timestamp, or carry
# a trust flag out of the auto-create — not a guess made here.
_UNINDIVIDUATED_SAME_GAME_WINDOW = timedelta(hours=12)

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
        identity.claim,
    )
    if event:
        return event

    return None


# Which Event column holds each source's own game id. Sources absent from this
# map (kalshi, polymarket) carry no per-game id column on ``events``, so the
# disqualification below cannot speak about them at all — see #1779.
_SOURCE_ID_COLUMN = {
    "odds_api": "external_id",
    "statpal": "statpal_fixture_id",
    "espn": "espn_id",
}


def _holds_distinct_provider_game_id(candidate: Event, claim: EventClaim) -> bool:
    """True when ``candidate`` already carries a DIFFERENT game id from this same provider.

    #1779. The structured match's ±28h window is wider than the 24h gap between
    consecutive games of a series, so the second game of a series name-matched the
    first and was absorbed into it instead of being created. Nine MLB games vanished
    and three rows were overwritten with the wrong day's score over Aug 10–12, 2026.

    The window is deliberately NOT narrowed (Alex ruling 2026-08-12): it exists for
    real cross-source date disagreements — a Kalshi settlement date sitting 24h off
    the game start, UTC/local boundary crossings. Narrowing it would re-open those.

    Instead we disqualify on identity. When the incoming claim's provider has already
    named a DIFFERENT game id on a candidate row, that provider is itself telling us
    these are two different games, and no amount of name-and-time similarity can
    outvote it. Doubleheaders are safe by the same token: both games carry distinct
    provider ids, so this separates them at least as reliably as the closest-by-time
    tiebreaker did — and when neither row has an id yet, nothing is disqualified and
    that tiebreaker still decides.

    Note this can only ever compare a provider against ITSELF. Two ids from different
    providers live in different id spaces and say nothing about each other, so a
    candidate holding an odds_api id is not disqualified by an incoming ESPN claim.
    """
    column = _SOURCE_ID_COLUMN.get(claim.source)
    if not column or not claim.source_id:
        return False
    existing = getattr(candidate, column, None)
    if not existing:
        return False
    return str(existing) != str(claim.source_id)


def _individuating_provider_ids(candidate: Event) -> dict[str, str]:
    """Every schedule provider's game id this candidate already carries.

    A row holding any of these has been *individuated*: some provider looked at the
    schedule and said "this specific game". Which provider it was does not matter for
    the question below — only that the row is not an anonymous name-and-time shell.
    """
    held: dict[str, str] = {}
    for source, column in _SOURCE_ID_COLUMN.items():
        value = getattr(candidate, column, None)
        if value:
            held[source] = str(value)
    return held


def _is_a_different_scheduled_game(
    candidate: Event,
    claim: Optional[EventClaim],
    commence_time: datetime,
) -> bool:
    """True when an already-individuated candidate is plainly a DIFFERENT game.

    #1802 (Codex C-CERT-1801). ``_holds_distinct_provider_game_id`` can only ever
    compare a provider against ITSELF, and treats that as a virtue. It is a real
    guard, but it leaves the incident open from the other side: when the candidate
    does not yet carry the INCOMING provider's id, the predicate returns False and
    the structured matcher happily accepts any same-teams row anywhere in ±28h.

    **Absence of the incoming provider's id was being read as evidence of sameness.**
    It is not. An empty column means "this provider has not spoken about this row",
    never "this row is the game you are describing" — the same shape as gotcha #53,
    where an empty 200 was read as a fact about the market instead of a response
    shape. So an Aug 10 row carrying only ``external_id`` absorbed an Aug 11 StatPal
    claim, took its id, and was dragged a day forward: #1779 reproduced end to end
    through a provider ordering nobody had tested.

    The rule, per Alex's ruled bar (2026-08-12) — *no absorption of a distinct
    scheduled game, regardless of which provider the claim arrives from*:

        A candidate that some schedule provider has already individuated may only
        take a new claim if the two agree about WHEN the game is.

    Deliberately asymmetric, and the asymmetry is the point. Refusing a true match
    costs a duplicate row — visible, and already drained by the 30-minute merge task.
    Accepting a false one destroys a game AND corrupts the survivor, which is #1779:
    the missing game is never created, and the row that ate it carries the wrong
    day's score. Those are not comparable, so this errs toward creating.

    Three cases deliberately left alone:

    * **Never-individuated candidates** (no provider id at all) — handled separately
      by ``_unindividuated_clocks_say_different_games`` (#1779 R3), which is where the
      prediction-market auto-creates that collapse onto a shared ``now`` live. Leaving
      them to the wide window, as this function originally did, left the defect fully
      intact for 88% of events.
    * **The incoming provider's own id, matching** — identity beats the clock. A rain
      delay that moves a game four hours must still find its own row on the next poll.
    * **Same provider, different id** — already disqualified by
      ``_holds_distinct_provider_game_id`` regardless of time. Untouched.
    """
    held = _individuating_provider_ids(candidate)
    if not held:
        return False

    # Identity beats the clock: the provider naming this exact game outranks any
    # amount of start-time drift, so a re-poll of a moved game still matches.
    if claim is not None and claim.source_id:
        own = held.get(claim.source)
        if own is not None and own == str(claim.source_id):
            return False

    candidate_time = candidate.commence_time
    if candidate_time is None:
        return False
    drift = abs((candidate_time - commence_time).total_seconds())
    return drift > _CROSS_PROVIDER_SAME_GAME_WINDOW.total_seconds()


def _is_a_published_start_time(moment: Optional[datetime]) -> bool:
    """True when this timestamp is a SCHEDULE rather than a fabricated ``now``.

    A published start time is always on a whole minute — every schedule provider we
    read (Odds API, ESPN, StatPal, Kalshi ticker dates) emits one, and 16,638 of the
    16,777 individuated events in the last 120 days satisfy this (99.2%); of the
    whole-minute id-less rows, 98.7% sit on a 5-minute boundary. A
    ``datetime.now(timezone.utc)`` fallback essentially never does: the odds of a
    fabricated stamp landing on a whole second AND zero microseconds are ~1e-6.

    Both misreadings are survivable and the safe one is the likely one. Reading a
    real time as fabricated (a provider that publishes ``:30`` seconds) keeps the
    wide window — today's behaviour, no new breakage. Reading a fabricated time as
    real costs a duplicate row, never a vanished game.
    """
    if moment is None:
        return False
    return moment.second == 0 and moment.microsecond == 0


def _unindividuated_clocks_say_different_games(
    candidate: Event,
    commence_time: datetime,
) -> bool:
    """True when two REAL clocks on an un-individuated row disagree by over half a day.

    #1779 R3 — the id-less class. See ``_UNINDIVIDUATED_SAME_GAME_WINDOW`` above for
    the full argument and the production measurement that chose 12h. In short: this
    is the only guard that speaks for the 88% of events no schedule provider has
    named, it fires only when both sides carry a published start time (a fabricated
    ``now`` is not a clock and cannot be measured against), and it fails closed
    toward creating because a duplicate is visible and a vanished game is not.

    Deliberately disjoint from the two id-based guards: it returns False the moment
    any provider has individuated the row, so exactly one rule ever applies to a
    given candidate and the 2h window above is never widened by this one.
    """
    if _individuating_provider_ids(candidate):
        return False
    if not _is_a_published_start_time(candidate.commence_time):
        return False
    if not _is_a_published_start_time(commence_time):
        return False
    drift = abs((candidate.commence_time - commence_time).total_seconds())
    return drift > _UNINDIVIDUATED_SAME_GAME_WINDOW.total_seconds()


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
    claim: Optional[EventClaim] = None,
) -> Optional[Event]:
    """Step 3: Find event by sport + date + team names.

    Queries events with the same sport_id and commence_time within
    ±_MATCH_WINDOW (28h), then scores each candidate using names_match().
    Requires BOTH teams to match (either in normal or swapped home/away
    orientation).

    Three disqualifications run before scoring (#1779), in order of how much evidence
    they need: a candidate holding a DIFFERENT game id from the incoming claim's own
    provider (``_holds_distinct_provider_game_id``); a candidate individuated by ANY
    provider whose start disagrees by more than 2h (``_is_a_different_scheduled_game``);
    and a candidate nobody has individuated whose PUBLISHED start time is more than
    half a day from the claim's (``_unindividuated_clocks_say_different_games``).

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
        # #1779: the provider has already said this is a different game. Names and
        # times cannot outvote an id, so drop the candidate before scoring it.
        if claim is not None and _holds_distinct_provider_game_id(candidate, claim):
            logger.debug(
                "Structured match: disqualifying event %s — holds %s id %s, incoming %s",
                candidate.id, claim.source,
                getattr(candidate, _SOURCE_ID_COLUMN[claim.source], None),
                claim.source_id,
            )
            continue

        # #1802: ...and the same is true when the id belongs to a DIFFERENT provider.
        # The row was individuated by somebody; a start time a day away means the
        # claim is describing tomorrow's game, not this one.
        if _is_a_different_scheduled_game(candidate, claim, commence_time):
            logger.debug(
                "Structured match: disqualifying event %s — individuated by %s at %s, "
                "incoming %s claims %s (%.1fh apart)",
                candidate.id, sorted(_individuating_provider_ids(candidate)),
                candidate.commence_time,
                getattr(claim, "source", None), commence_time,
                abs((candidate.commence_time - commence_time).total_seconds()) / 3600.0,
            )
            continue

        # #1779 R3: ...and when NOBODY has individuated the row, two published start
        # times more than half a day apart are still two games. The id-less class is
        # 88% of events; leaving it to the ±28h window left the original defect fully
        # intact there.
        if _unindividuated_clocks_say_different_games(candidate, commence_time):
            logger.debug(
                "Structured match: disqualifying event %s — un-individuated, its "
                "published start %s is %.1fh from the incoming %s claim's %s",
                candidate.id, candidate.commence_time,
                abs((candidate.commence_time - commence_time).total_seconds()) / 3600.0,
                getattr(claim, "source", None), commence_time,
            )
            continue

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
