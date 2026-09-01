"""
Unified Event Registry — single entry point for event creation and matching.

All sources (Odds API, ESPN, StatPal, Kalshi, Polymarket) call find_or_create_event()
when they encounter a game. First source in creates the event; every subsequent source
finds it and attaches its source ID. No duplicates.

Matching cascade:
1. Exact source ID — check if this source already claimed an event
2. Cross-source ID — check if ANY source already claimed it via other ID columns
3. Structured match — sport + commence_time ± _MATCH_WINDOW (28h) + names_match on both
   teams, reachable ONLY for an id-anchored claim (ruling 048; see below)
4. Create — no match found, create new event, tagged with its provenance

── Ruling 048: an id-less claim never absorbs; it creates ──────────────

Absorption requires an **id-anchored correspondence**. There are exactly two arms:

  A. SHARED id — the claim's provider id is already on the candidate row. That is Step 1,
     and it needs no window and no names.
  B. DEREFERENCED id — the claim's id resolves, via *its own provider's schedule*, to the
     teams and date it presents. The id is not shared with the candidate, but the teams and
     date being matched carry that id's authority rather than a parsed label. This is the
     legitimate cross-source join (an ESPN claim finding the row Odds API created), and it
     is what ``EventClaim.schedule_derived`` attests.

A claim that fits neither arm CREATES. No time window, no name match, no heuristic — because
for two distinct games between the same clubs in the same window with no id in common there
is no discriminating signal at all, and any matcher able to join two same-game claims is the
same operation that destroys a doubleheader. Five certification rounds (C-CERT-1801-R1..R4)
each moved a threshold inside that design and each produced a new specimen class.

Duplicates therefore go up. That is the declared, bounded cost — bounded because id-keyed
reconciliation drains them as ids arrive — and it is the right side of an asymmetry: a
duplicate is visible and reversible, a wrong absorption is neither.

See ``docs/rulings/048-an-id-less-claim-never-absorbs.md`` and ruling 042 (dereference the id,
never the label). CLAUDE.md gotcha #32 is amended by this ruling.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Sport
from app.services.anchor_channel import (
    COLLISION,
    anchor_key_for_claim,
    duplicate_tag,
    find_event_by_anchor,
    record_anchor,
)
from app.utils.espn_helpers import commence_correction_inverts_completion
from app.utils.event_completion import settlement_is_a_staleness_artifact
from app.utils.name_normalization import names_match

logger = logging.getLogger(__name__)

# Source priority for field updates (higher index = higher priority)
_SOURCE_PRIORITY = {
    "kalshi": 0,
    "polymarket": 0,
    "odds_api": 1,
    "statpal": 2,
    "espn": 3,
    # MLB's OWN published schedule, reached only by the attended repair rail and
    # only after matching a Final on both teams AND the final score. It outranks
    # every poller because it is not a poll — it is the league saying when the
    # game started. Ranked above `espn` deliberately: ESPN is an excellent
    # secondary, and #1947 holds three `espn_id` values shared by genuinely
    # different games, so it is not the last word on MLB timing.
    "mlb_schedule_repair": 4,
}


def commence_time_write_authorized(
    current_source: Optional[str],
    incoming_source: Optional[str],
    *,
    same_record_revision: bool = False,
) -> tuple[bool, str]:
    """May ``incoming_source`` overwrite a ``commence_time`` written by
    ``current_source``? Returns ``(authorized, reason)``.

    Extracted as a named predicate for #2018 so that **every** rail writing
    `events.commence_time` shares one authority rule instead of each deciding
    locally. `repair_inverted_mlb_events` previously stamped its own source
    unconditionally — fine while it had one well-behaved caller, and the #1980
    manufacturer shape one table over the moment it had two.

    Two asymmetries, both deliberate:

    * **A tie loses.** Two readings from the same authority disagreeing is a data
      question, not a licence for whichever poll ran last. Strict ``>``, matching
      what ``_update_fields_by_priority`` has always done.
    * **Unknown ranks 0 on BOTH sides, which is not symmetric in effect.** An
      unknown *current* source confers no immunity — otherwise the rows with the
      worst provenance become the only unfixable ones. An unknown *incoming*
      source has no established authority and loses to everything known. So
      provenance we cannot vouch for may be corrected, and may not correct.

    ── ``same_record_revision``: a provider may revise its OWN reading (q066b) ──

    "A tie loses" is right about two *rivals* and wrong about one *record*. When
    the incoming claim's provider id is ALREADY the id on this row — Step 1, an
    exact-id match, no window and no names — the two readings are not two
    authorities disagreeing. They are one provider's row at two points in time,
    and the later one is the provider correcting itself. Refusing it does not
    hold a line; it freezes whatever the provider happened to publish first.

    Measured on the live US Open slate, 2026-09-01: The Odds API publishes the
    whole next day at one session-start default — all 21 ATP and 20 WTA matches
    at ``2026-09-02T15:00:00Z``, because no order of play exists yet — and then
    STAGGERS THE SAME EVENT IDS to real times once it does (Sep 1 read back
    15:00, 16:10, 16:40, 17:20, 17:50, 19:00, 20:30, 21:00, 23:00, 00:10). There
    is no placeholder field in the payload to detect: the only difference between
    the placeholder and the truth is that the provider sent the truth LATER. So
    the tie rule is not conservative here — it is the thing that makes the
    placeholder permanent, and every downstream clock reads it as a start.

    It is scoped to identity, not merely to source. ``incoming_source`` must EQUAL
    ``current_source``: a provider revising the value it itself wrote is a
    revision, whereas a different provider arriving at parity is still two
    authorities and still loses. And an unknown source cannot revise — it has no
    established authority to correct (same reason it cannot outrank).

    This does not widen absorption by one row. Step 1 is exact-id and was never
    the absorber; ``ODDS_LISTING_IS_NOT_A_DEREFERENCE`` closed that route through
    the ±28h structured matcher and is untouched here. Nor does it override the
    #46 inversion guard in ``_update_fields_by_priority``, which still refuses to
    move a completed event's start past its own ``completed_at``.
    """
    incoming = _SOURCE_PRIORITY.get(incoming_source or "", 0)
    current = _SOURCE_PRIORITY.get(current_source or "", 0)
    if incoming > current:
        return (True, "ok")
    if (
        same_record_revision
        and incoming_source
        and incoming_source == current_source
        and incoming_source in _SOURCE_PRIORITY
    ):
        return (True, f"revision: {incoming_source} correcting its own record")
    return (
        False,
        f"priority: {incoming_source or '<none>'}({incoming}) does not outrank "
        f"{current_source or '<none>'}({current})",
    )

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


# Provenance tags written to ``Event.event_tags`` on the create path (ruling 048).
# Namespaced to match the existing tag convention ("sport:basketball", "tier:1").
# These make a created row a REPAIRABLE FACT rather than an anonymous one: the
# unanchored tag is what the duplicate meter counts and what reconciliation looks
# for once an id finally arrives.
_TAG_UNANCHORED = "provenance:unanchored"


# ── The Odds listing is not a dereference (#1989) ───────────────────────────
#
# Cite this at every Odds API ingestion call site. It is a named ``False`` and
# not a bare literal because the bare literal is what got flipped: all four
# Odds call sites passed ``schedule_derived=True`` on the argument that "id and
# teams arrive together in one Odds API schedule record". That sentence is true
# and it is not arm B.
#
# Arm B is a DEREFERENCE — the provider was handed an id and asked "what game is
# this?", and answered. The Odds ``/v4/sports/{sport}/odds`` response is a
# LISTING: we asked by SPORT, and the id is the primary key of a row whose other
# columns are the teams and the date. Co-arrival is not dereference, and the
# proof is that the flag was then true of every record the provider has ever
# emitted — #1946's shape, a flag that is always true is not a gate.
#
# The decisive argument is not conservatism, though. It is that arm B's own
# authority argues AGAINST absorbing here. Arm B says: trust these teams and
# this date, because the provider vouches for them. But the provider ALSO
# vouches that its id ``c0a1041457ba…`` and its id ``f7e02d88c3c8…`` are two
# different games. Using a provider's authority to merge two rows that the same
# provider distinguishes is self-contradictory. Arm B exists for the CROSS-source
# join — an ESPN claim finding the row Odds API created — and applied
# intra-source it is incoherent.
#
# Measured on the live MLB slate, 2026-08-18 (22 records, read-only replay of
# the matcher's own predicate): 6 resolved at Step 1 on their own id, and all 16
# remaining absorbed onto a row that ALREADY HELD A DIFFERENT odds_api id.
# ZERO were the legitimate no-id cross-source join. Arm B was doing no
# legitimate work on this path at all; it was 100% absorber.
#
# Specimen, end to end: event 15199901 holds ``espn_id=401816572``, which ESPN
# dates 2026-08-18T22:40Z STATUS_FINAL. Its ``commence_time`` had been dragged to
# 2026-08-19T16:35Z — which is a DIFFERENT game, ESPN ``401816587``,
# STATUS_SCHEDULED — and its status set to ``live``. So a finished Tuesday game
# sat at Wednesday's first pitch wearing Wednesday's clock and a live badge,
# while the real Wednesday game had no row in production at all.
#
# Step 1 is untouched: a claim whose id is already on a row still finds it with
# no window and no names. Repeat polls are unaffected. What stops is a NEW id
# reaching the ±28h matcher, which is the only way the absorption happened.
ODDS_LISTING_IS_NOT_A_DEREFERENCE = False


# ── The StatPal listing is not a dereference either (#1989, queue 374) ──────
#
# The same defect as the Odds sites, on a second provider, and it is the reason
# the Odds fix alone did not restore the slate. Cite this at both StatPal
# ingestion call sites.
#
# What was there: ``schedule_derived=bool(fixture.fixture_id)``. That is true
# whenever a fixture carries an id — i.e. always, for MLB — so it is #1946's
# shape again: a flag that is always true is not a gate. And the record it was
# asserted on is a LISTING. ``:186`` reads ``get_fixtures(sport)`` and ``:342``
# reads ``get_live_scores(sport)``; both ask by SPORT and get rows back. Neither
# hands the provider an id and asks "what game is this?", which is the only
# thing arm B is for.
#
# Measured (queue 373 item 3, read-only replay of the real matcher's predicate
# against production MLB rows 2026-08-17 → 2026-08-28):
#
#   :186 season-schedule, population 94 — 40 step-1 hits, 54 window absorptions,
#        54/54 onto a row ALREADY HOLDING A DIFFERENT statpal fixture id.
#   :342 livescores,      population  8 —  0 step-1 hits,  8 window absorptions,
#         8/8 likewise.
#
# 62 of 62. Arm B was doing ZERO legitimate work on this path; it was 100%
# absorber. Unanchored, the same populations produce 54 and 8 CREATEs and no
# absorptions.
#
# ``:342`` is the more dangerous of the two BECAUSE of its own pre-check. It
# skips any event matching on exact team names within ±6h, which removes the
# same-game case and leaves only the wrong-game band: the eight survivors sit at
# +21.92h, −24.00h, +4.00h, −24.00h, +22.00h, −20.00h, −20.00h, −20.00h — the
# ±28h annulus, i.e. the adjacent game in the series. A narrower population that
# is ENTIRELY wrong beats a wider one that is mostly right.
#
# The two absorbers fed each other, and that is the specimen. Event 15199901
# holds statpal fixture ``355284`` (Tigers @ Pirates 2026-08-18T22:40Z) but its
# ``commence_time`` was dragged to 2026-08-19T16:35Z by the Odds absorber — a
# DIFFERENT game, fixture ``355299``. StatPal then found that row at dt=+0.00h
# and absorbed it, writing its second id on top. So a dt≈0.00h reading here is
# not evidence of a same-game match; it is evidence that a previous absorption
# already completed.
#
# Cost of leaving it, measured in production 2026-08-19T14:35Z with the Odds
# half already deployed: ESPN's Aug-19 MLB slate is 15 games, all scheduled. We
# held 6 correct rows — the six created 21 minutes after v3856, unabsorbed,
# which is the Odds fix working — plus 8 Aug-18 rows dragged +24h onto Aug-19
# clock slots, four of them flying ``live`` with a finished score (one 22-0) on
# a game that had not started. 7 of the 9 missing Aug-19 games map one-to-one
# onto a dragged row carrying the SAME two clubs inside ±28h.
#
# Step 1 is untouched, exactly as for Odds: a claim whose fixture id is already
# on a row still finds it with no window and no names, so repeat polls are
# unaffected. What stops is a NEW fixture id reaching the ±28h matcher.
STATPAL_LISTING_IS_NOT_A_DEREFERENCE = False


def _tag_source(source: str) -> str:
    return f"provenance:source:{source}"


@dataclass
class EventClaim:
    """A source's claim on an event — its external ID for this source."""
    source: str      # "odds_api", "statpal", "espn", "kalshi", "polymarket"
    source_id: str   # The external ID from that source

    # Ruling 048 arm B. TRUE only when this claim's ``source_id`` was dereferenced
    # against its OWN provider's schedule to produce the team names and
    # commence_time on this identity — i.e. the provider was asked "what game is
    # id X?" and answered. FALSE when the teams were parsed out of a market name,
    # a ticker, or any other label (ruling 042), and FALSE when the id itself was
    # synthesized from those labels.
    #
    # Defaults to FALSE deliberately: the conservative reading absorbs less, and a
    # caller that has not thought about provenance must not silently get the
    # absorbing behaviour. Adding a caller is the moment to answer this question.
    schedule_derived: bool = False

    # The PROVIDER's own id, when ``source_id`` above is something we synthesized.
    #
    # This exists because of a defect caught while wiring #2213's Step 2. The
    # prediction-market call site builds ``source_id`` as
    # ``f"pm_{market.source}_{market.external_id}"`` — a synthetic, prefixed
    # string. Kalshi and Polymarket have no id column on ``events``, so Step 1
    # ignores it and ``_attach_claim`` ignores it, which is why nobody noticed it
    # was not the provider's id: it had no reader.
    #
    # The anchor channel IS that reader, and it is the one place where the
    # distinction is load-bearing. ``kalshi_anchor_key("pm_kalshi_KXMLBGAME-...")``
    # cannot find a game token in a prefixed string, so it degrades to
    # ``id_kind='market'`` — recorded, and permanently unable to anchor. The rail
    # would have looked correct, passed every test, written rows, and resolved
    # nothing.
    #
    # Set this at any call site whose ``source_id`` is not verbatim what the
    # provider calls the thing. Leave it None when it is.
    provider_id: Optional[str] = None

    @property
    def anchor_source_id(self) -> Optional[str]:
        """The id an anchor key must be built from — the provider's, never ours."""
        return self.provider_id or self.source_id


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
                attached_new = _attach_claim(event, identity.claim)
                _update_fields_by_priority(event, identity)
                await session.flush()
                # A correspondence is established when a previously-empty column
                # just took this id, or when the provider has no column that
                # could ever have held it. Anything else is a repeat poll and
                # writes nothing (#2213).
                #
                # The column-less providers are re-offered every time rather
                # than tracked: arriving via their own anchor makes the write a
                # CONFIRMED no-op, and one `ON CONFLICT DO NOTHING` on the
                # 15-minute prediction-market matcher is cheaper than threading
                # "how did we get here" through the cascade's return type.
                await _record_claim_anchor(
                    session, event, identity, sport_id,
                    established=(
                        attached_new
                        or identity.claim.source in _SOURCES_WITHOUT_ID_COLUMN
                    ),
                )
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
            # Ruling 048: record the claim's provenance ON the created row. A row
            # that says where it came from is repairable; an anonymous one is not.
            # The unanchored tag is the declared cost made countable — it is what
            # the duplicate meter reads and what reconciliation drains against.
            tags = [_tag_source(identity.claim.source)]
            if not identity.claim.schedule_derived:
                tags.append(_TAG_UNANCHORED)

            event = Event(
                sport_id=sport_id,
                home_team_name=identity.home_team_name,
                away_team_name=identity.away_team_name,
                commence_time=identity.commence_time,
                commence_time_source=identity.commence_time_source or identity.claim.source,
                status=status,
                event_tags=tags,
            )
            _attach_claim(event, identity.claim)
            session.add(event)
            await session.flush()

            # A created row is always a new correspondence. Recording it here is
            # what stops the NEXT claim carrying the same provider id from
            # creating a third row — the failure mode #2213 is a photograph of.
            await _record_claim_anchor(
                session, event, identity, sport_id, established=True
            )

            logger.info(
                "Created event %d: %s vs %s (%s, %s) [source=%s anchored=%s]",
                event.id, identity.home_team_name, identity.away_team_name,
                identity.sport_key, identity.commence_time.isoformat(),
                identity.claim.source, identity.claim.schedule_derived,
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

    # Step 2: Cross-source ID — the anchor channel (#2213, queue 413).
    #
    # This step used to read "implicit — Step 3 will find it by sport+date+teams".
    # Ruling 048 closed Step 3 to unanchored claims and nothing replaced that
    # sentence, so Step 2 has been ABSENT rather than implicit ever since. For
    # Kalshi and Polymarket it was never implicit even before 048: they have no
    # id column on `events` at all, so Step 1 returns None unconditionally and
    # 99.61% of rows measured `NO_ANCHOR_CHANNEL`.
    #
    # This is ruling 048 ARM A — a SHARED id — read out of `event_provider_anchors`
    # instead of out of one of the three id columns that happen to exist. It is
    # not a new absorption power and it is deliberately NOT gated on
    # `schedule_derived`: Step 1 absorbs on a shared id today without that flag,
    # and requiring it here would make the table stricter than the column for no
    # reason. What keeps this honest is upstream, in `provider_anchor_keys`:
    # only `id_kind='game'` is ever consulted, every `source_id` is
    # namespace-qualified, and an unrecognised namespace yields no key at all.
    anchored_event = await _find_by_anchor(session, identity, sport_id)
    if anchored_event:
        return anchored_event

    # Step 3: Structured match — sport + date + teams.
    #
    # RULING 048 GATE. Reachable only for an id-anchored claim (arm B — the claim's
    # id dereferences via its own provider's schedule to the teams and date being
    # matched). An unanchored claim does not reach the matcher at all; it returns
    # None here and the caller CREATES. This is a gate on REACHABILITY rather than
    # a refusal inside the matcher, because a refusal is a behaviour that the next
    # patch can tune, and five rounds of tuning is what this ruling ended.
    if not identity.claim.schedule_derived:
        logger.debug(
            "Ruling 048: skipping structured match for unanchored %s claim "
            "(%s vs %s @ %s) — will create with provenance",
            identity.claim.source, identity.home_team_name,
            identity.away_team_name, identity.commence_time.isoformat(),
        )
        return None

    event = await _find_by_structured_match(
        session, sport_id,
        identity.home_team_name, identity.away_team_name,
        identity.commence_time,
        claim=identity.claim,
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


#: Providers with no id column on `events`. For these the anchor channel is not
#: an optimisation — it is the ONLY route to a prior row, which is why they made
#: up 99.61% of the `NO_ANCHOR_CHANNEL` population (kalshi 73,678, polymarket
#: 503, measured 2026-08-20).
_SOURCES_WITHOUT_ID_COLUMN = frozenset({"kalshi", "polymarket"})


async def _find_by_anchor(
    session: AsyncSession,
    identity: EventIdentity,
    sport_id: int,
) -> Optional[Event]:
    """Step 2: does some row already carry this provider id in the channel?"""
    key = anchor_key_for_claim(
        identity.claim.source, identity.claim.anchor_source_id
    )
    event_id = await find_event_by_anchor(
        session, key, expected_sport_id=sport_id
    )
    if event_id is None:
        return None

    event = (
        await session.execute(select(Event).where(Event.id == event_id))
    ).scalar_one_or_none()

    if event is None:
        # The anchor names a row that no longer exists. The FK is ON DELETE
        # CASCADE so this should be unreachable; if it happens, a dangling
        # assertion must not become an absorption target.
        logger.warning(
            "Anchor %s:%s names event %s, which does not exist — treating as a miss",
            key.source, key.source_id, event_id,
        )
        return None

    logger.info(
        "Step 2 anchor hit: %s claim %r resolved to event %s (%s vs %s)",
        identity.claim.source, identity.claim.source_id, event.id,
        identity.home_team_name, identity.away_team_name,
    )
    return event


async def _record_claim_anchor(
    session: AsyncSession,
    event: Event,
    identity: EventIdentity,
    sport_id: int,
    *,
    established: bool,
) -> None:
    """Write the claim's anchor when a correspondence was newly ESTABLISHED.

    ``established`` is the whole cost control. A repeat poll of a claim whose id
    is already on its column establishes nothing, and Tier-1 live polling runs at
    32s — an `INSERT ... ON CONFLICT DO NOTHING` per source per event per cycle
    would be a steady stream of no-op writes bought for no information.

    A ``COLLISION`` here is not an error to swallow. It is the first moment the
    system holds proof, keyed on an id rather than guessed from names and a time
    window, that two rows are one game.
    """
    if not established:
        return

    key = anchor_key_for_claim(
        identity.claim.source, identity.claim.anchor_source_id
    )
    if key is None:
        return

    result = await record_anchor(
        session,
        event_id=event.id,
        key=key,
        claim_context={
            "source": identity.claim.source,
            "schedule_derived": identity.claim.schedule_derived,
            "commence_time_source": identity.commence_time_source,
        },
    )

    if result.outcome != COLLISION or result.canonical_event_id == event.id:
        return

    # Re-run the Step 2 read to establish that the incumbent is in THIS sport.
    # A cross-sport hit is a data defect that `find_event_by_anchor` already
    # logged and refused; tagging on it would record a duplicate relationship
    # between two rows that are not the same game. One extra query, on a path
    # that fires only on a genuine conflict.
    same_sport_canonical = await find_event_by_anchor(
        session, key, expected_sport_id=sport_id
    )
    if same_sport_canonical != result.canonical_event_id:
        return

    await _tag_duplicate_of(session, event.id, result.canonical_event_id)


async def _tag_duplicate_of(
    session: AsyncSession, event_id: int, canonical_event_id: int
) -> None:
    """Record `event_id` as a proven duplicate of `canonical_event_id`.

    Written with Core SQL against the row rather than by mutating
    ``Event.event_tags`` in memory. ``event_tags`` is JSONB, and gotcha #4 is
    that a JSONB ORM assignment can silently fail to persist; gotcha #5 is that
    mixing the two styles in one session is where flush ordering bites. A
    server-side `||` on the column we are not otherwise touching avoids both,
    and the `NOT @>` predicate makes it idempotent in the database rather than
    in a caller's memory.

    This is a LABEL, not a merge. Nothing is deleted, nothing is repointed, and
    both rows stay addressable — the drain that consumes these tags is #1946
    Item 8 and does not exist yet. A tag that outruns its consumer is still the
    right thing to write, because the alternative is that the proof exists only
    in a log line.
    """
    from sqlalchemy import text as _text

    tag = duplicate_tag(canonical_event_id)
    await session.execute(
        _text(
            "UPDATE events SET event_tags = COALESCE(event_tags, '[]'::jsonb) "
            "|| CAST(:tag_array AS jsonb) "
            "WHERE id = :event_id "
            "AND NOT COALESCE(event_tags, '[]'::jsonb) @> CAST(:tag_array AS jsonb)"
        ),
        {"tag_array": f'["{tag}"]', "event_id": event_id},
    )
    logger.warning(
        "Tagged event %s as %s — id-anchored duplicate, proven not guessed (#2213)",
        event_id, tag,
    )


async def _find_by_structured_match(
    session: AsyncSession,
    sport_id: int,
    home_team: str,
    away_team: str,
    commence_time: datetime,
    *,
    claim: EventClaim,
) -> Optional[Event]:
    """Step 3: Find event by sport + date + team names — ID-ANCHORED CLAIMS ONLY.

    ``claim`` is REQUIRED and keyword-only: this matcher may not be invoked without
    stating whose claim it is acting on, and it raises on an unanchored one. The
    caller-side gate in ``_find_existing`` means that never happens in the data
    path; this assertion is what stops a FUTURE caller from re-opening the id-less
    absorption path by calling the matcher directly (ruling 048).

    Queries events with the same sport_id and commence_time within
    ±_MATCH_WINDOW (28h), then scores each candidate using names_match().
    Requires BOTH teams to match (either in normal or swapped home/away
    orientation).

    Uses a PostgreSQL advisory lock to prevent TOCTOU race conditions when
    concurrent workers (ESPN sync on realtime, Odds API on background) both
    call find_or_create_event() for the same game simultaneously.
    """
    if not claim.schedule_derived:
        raise AssertionError(
            "ruling 048: _find_by_structured_match reached with an unanchored "
            f"{claim.source} claim ({claim.source_id!r}). An id-less claim never "
            "absorbs — it creates. Do not add a bypass here; if this provider can "
            "dereference its id against its own schedule, set schedule_derived on "
            "the claim at the call site instead."
        )

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


def _attach_claim(event: Event, claim: EventClaim) -> bool:
    """Attach a source's ID to an event. Idempotent — won't overwrite existing IDs.

    Returns True when this call ESTABLISHED a binding that did not exist before —
    i.e. it wrote an id into a previously-empty column. That return is what the
    anchor write path uses to tell a new correspondence from a repeat poll
    (#2213); every caller that ignores it behaves exactly as before.
    """
    if claim.source == "odds_api":
        if not event.external_id:
            event.external_id = claim.source_id
            return True
        if event.external_id != claim.source_id:
            logger.info(
                "Event %d already has external_id=%s, incoming=%s (same game, different API ID)",
                event.id, event.external_id, claim.source_id,
            )
    elif claim.source == "statpal":
        if not event.statpal_fixture_id:
            event.statpal_fixture_id = claim.source_id
            return True
    elif claim.source == "espn":
        if not event.espn_id:
            event.espn_id = claim.source_id
            return True
    return False


#: Per-provider id column on ``events``, for the providers that have one. The
#: same three arms ``_attach_claim`` writes, read back so a caller can ask "is
#: this claim's id ALREADY the id on this row?" without duplicating the mapping.
_SOURCE_ID_COLUMN = {
    "odds_api": "external_id",
    "statpal": "statpal_fixture_id",
    "espn": "espn_id",
}


def claim_is_same_record(event: Event, claim: EventClaim) -> bool:
    """Is this claim the provider re-reading the row it already owns? (q066b)

    True only for an EXACT id identity: the provider has an id column on
    ``events`` and the value in it equals this claim's id. That is Step 1 —
    reached with no time window and no name match — so it carries no absorption
    risk of its own, and it is the one condition under which a second reading
    from the same source is a REVISION rather than a rival.

    False for the id-column-less providers (``kalshi``, ``polymarket``): they
    reach a row through the anchor channel, not through a column, so "the id on
    the row" is not a question this function can answer for them, and answering
    it optimistically would hand a revision right to the sources ranked 0.
    """
    column = _SOURCE_ID_COLUMN.get(claim.source)
    if column is None:
        return False
    existing = getattr(event, column, None)
    return bool(existing) and existing == claim.source_id


def _update_fields_by_priority(event: Event, identity: EventIdentity) -> None:
    """Update event fields if the incoming source has higher priority.

    Source priority: ESPN > StatPal > Odds API > prediction markets.
    Higher-priority sources overwrite team names and commence_time.

    ``commence_time`` additionally accepts a same-record revision at parity —
    see ``commence_time_write_authorized``. Team names deliberately do NOT: the
    ship this rides is a wrong START TIME (q066b), and a name rewrite is a
    different blast radius that no evidence here asks for.
    """
    incoming_priority = _SOURCE_PRIORITY.get(identity.claim.source, 0)
    current_priority = _SOURCE_PRIORITY.get(event.commence_time_source or "", 0)

    if incoming_priority > current_priority:
        # Higher-priority source: update team names.
        if identity.home_team_name:
            event.home_team_name = identity.home_team_name
        if identity.away_team_name:
            event.away_team_name = identity.away_team_name

    # commence_time has its own authority question, because it accepts one thing
    # the team names do not: the owning provider revising its own record (q066b).
    outranks, _why = commence_time_write_authorized(
        event.commence_time_source,
        identity.claim.source,
        same_record_revision=claim_is_same_record(event, identity.claim),
    )
    if identity.commence_time and outranks:
        # Guard (#46 invariant; gotcha #32 family): refuse to move
        # commence_time to a value AFTER an already-completed event's
        # completed_at. That inversion (completed_at < commence_time) means we
        # folded a higher-priority source's forward commence_time onto the
        # WRONG sibling (series row-reuse / doubleheader). The ESPN write path
        # already guards this; the registry did not. Only the commence_time
        # move is refused — team-name updates above still apply.
        #
        # UNLESS the settlement it would invert is itself a staleness artifact —
        # an unscored row a wall-clock net closed for a game that had not been
        # played. Then the inversion is evidence ABOUT THE COMPLETION, not about
        # the start, and refusing the correction is what keeps an unplayed match
        # wearing a FINAL badge. The scored case is untouched, so a real result
        # still wins every argument (gotcha #21).
        #
        # Asked only of a row that HAS a completion. An unsettled row cannot
        # carry an artifact settlement, so the score columns are never read on
        # the overwhelmingly common path.
        inverts = event.completed_at is not None and commence_correction_inverts_completion(
            identity.commence_time, event.completed_at
        )
        artifact = inverts and settlement_is_a_staleness_artifact(
            event.status, event.home_score, event.away_score,
            identity.commence_time, event.completed_at,
        )
        if inverts and not artifact:
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
            if artifact:
                # Void the artifact, exactly as `repair_inverted_mlb_events`
                # voids its own: back to `scheduled` with no completion. The
                # 60-second `transition_event_statuses` re-promotes it to `live`
                # off the CORRECTED start, so this un-settles without asserting
                # anything about when the match will actually be played.
                logger.info(
                    "Voiding staleness-artifact settlement on event %s: %s->scheduled, "
                    "completed_at %s cleared (unscored, and %s moved the start to %s)",
                    event.id, event.status, event.completed_at,
                    identity.claim.source, identity.commence_time,
                )
                event.status = "scheduled"
                event.completed_at = None


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
