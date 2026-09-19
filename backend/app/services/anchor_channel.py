"""The consumer of ``provider_anchor_keys``: read and write ``event_provider_anchors``.

#2213, queue 413. The key function shipped in queue 412R (#2220) and **nothing
called it**. This module is the caller — the half that turns a correct answer to
"what would an anchor row for this id be?" into rows in the table and into a
cascade step in the registry.

## What this buys, stated precisely

`event_provider_anchors` held **0 rows** when this was written. Two consequences
followed, and this module addresses exactly those two:

1. **Kalshi and Polymarket have no id column on `events` at all.** Measured over
   the whole population on 2026-08-20: 99.61% of rows are `NO_ANCHOR_CHANNEL`,
   the creating provider being `kalshi` (73,678) or `polymarket` (503), against
   the three id columns that exist (`external_id`, `espn_id`,
   `statpal_fixture_id`). For those two providers the registry's Step 1 returns
   `None` unconditionally, so a second claim on the same game had no route to
   the first claim's row other than the ±28h name matcher that ruling 048
   closed. The channel gives them Step 1's guarantee without Step 3's risk.
2. **Ruling 048's bounding clause was unexecutable.** *"Id-keyed reconciliation
   drains the duplicate when an id arrives"* — measured `AWAITING_ANCHOR` = 0 of
   74,181. Nothing arrived, because nothing wrote. The unique index
   `(source, source_id, id_kind)` makes the *second* writer's conflict the
   detection event, so a duplicate becomes countable at the moment it is proven
   rather than at the moment someone runs a census.

## What this does NOT buy — read before describing it

**It collapses zero of #2213's 41 duplicate MLB groups retroactively, and that
is not a defect in this module.** Queue 411 measured them: 0 of 41 pairs share
any provider id (0 `espn_id`, 0 `statpal_fixture_id`, 0 `external_id`), and 21
carry *conflicting* StatPal ids because that column is an untagged union of a
6-digit and a 10-digit namespace. A channel keyed on shared ids has nothing to
join on for those rows. Under the namespace-qualified keys those 21 read
`INCOMPARABLE`, which authorizes nothing — deliberately, because the alternative
readings are "same game" (an absorption on no evidence) and "different games" (a
positive claim of difference, which is what the bare `a == b` comparison was
wrongly asserting).

Those 41 are resolved by *writing* the missing correspondences — dereferencing
each row's own provider id against that provider's own schedule, ruling 042 —
which is #1946 Item 8 and is gated on a sink census. This module is the rail
that work will write through; it is not that work.

## Absorption authority is not widened by a millimetre

Four properties, each pinned by a test:

* Only `id_kind == 'game'` is ever returned by :func:`find_event_by_anchor`. A
  Kalshi player-prop ticker, a Polymarket `conditionId` and a Polymarket event
  id are recorded and are never absorbable.
* Step 2 is ruling 048 **arm A** — a SHARED id — and arm A has never required
  `EventClaim.schedule_derived`. Step 1 absorbs on a shared id today without it.
  Reading the same shared id out of a table instead of out of a column is the
  same arm, so this module does not consult `schedule_derived` and must not be
  changed to grant anything when it is true.
* An anchor pointing at an event in a **different sport** is refused, logged,
  and treated as a miss. A cross-sport absorption is the worst outcome this
  table can produce, and the sport is free to check.
* A **scalar-derived** anchor — ESPN, StatPal, Odds API, the three providers with
  an id column on `events` — is authoritative only while it still agrees with the
  column it was copied from (CERT-410 [P1]). Those columns are mutable and
  non-unique, and two live paths change them: `repair_event_espn_id` re-keys
  `espn_id`, and the source-intelligence collision sweep clears it to NULL.
  Without corroboration the copy outlives its source and keeps absorbing, so an
  incoming claim carrying the OLD id lands on a row that is now a *different
  game*. Kalshi and Polymarket are exempt because no such column exists for them:
  their anchor row is the only record there is, and nothing can disagree with it.

  The same premise governs the write side. A `COLLISION` is this system's only
  *proof* that two rows are one game, and the proof is the shared id — so an
  incumbent that no longer holds the id yields `STALE_INCUMBENT` and tags
  nothing. The stale row is deleted where it becomes false, by
  :func:`invalidate_scalar_anchor` inside the re-keying transaction, rather than
  being repointed here: an anchor a later writer can move is not an identity.

## Why writes are rare rather than per-poll

The write path fires only when a correspondence is *established* — an event was
created, or a claim's id was attached to a column that was previously empty, or
the source has no column at all. A repeat poll of an already-attached claim
writes nothing and reads nothing. That matters: Tier-1 live polling runs at 32s,
and an `INSERT ... ON CONFLICT DO NOTHING` per source per event per poll would
be a steady stream of no-op writes bought for no information.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.event_completion import (
    KALSHI_OCCURRENCE_COMMENCE_SOURCE,
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    TICKER_DERIVED_COMMENCE_SOURCE,
)
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    ANCHOR_KIND_MARKET,
    SCALAR_DERIVED_ID_COLUMNS,
    SOURCE_KALSHI,
    SOURCE_POLYMARKET,
    AnchorKey,
    espn_anchor_key,
    kalshi_anchor_key,
    odds_api_anchor_key,
    polymarket_anchor_key,
    statpal_anchor_key,
    statpal_id_space,
    statpal_qualifier_refusal,
    statpal_sport_from_source_id,
)
from app.utils.sport_keys import get_llm_category_for_prefix, get_sport_key_from_ticker

logger = logging.getLogger(__name__)

# --- write outcomes -------------------------------------------------------------
#: The anchor did not exist and now does.
WROTE = "WROTE"
#: The anchor already existed and already pointed at this event. Nothing to do,
#: and specifically NOT a collision — repeat establishment is normal.
CONFIRMED = "CONFIRMED"
#: The anchor already existed and points at a DIFFERENT event. One provider id,
#: two event rows: an id-anchored duplicate, proven rather than guessed.
COLLISION = "COLLISION"
#: The claim yields no anchorable key (unknown StatPal namespace, empty id, a
#: provider this module does not key). Writing nothing is the correct answer.
NO_KEY = "NO_KEY"
#: The anchor already existed, points at a DIFFERENT event, and that event no
#: longer carries the id in its own column. CERT-410 [P1]: this is NOT a
#: collision, because a collision is *proof* that two rows are one game and a
#: disproven incumbent proves nothing. Nothing is written and nothing is tagged.
STALE_INCUMBENT = "STALE_INCUMBENT"

#: Tag written onto the losing row of a COLLISION so the duplicate is queryable
#: without re-deriving it. Mirrors the `provenance:` tag vocabulary the registry
#: already writes under ruling 048.
DUPLICATE_TAG_PREFIX = "provenance:duplicate-of:"


def duplicate_tag(canonical_event_id: int) -> str:
    """The tag naming the row this one was proven to duplicate."""
    return f"{DUPLICATE_TAG_PREFIX}{canonical_event_id}"


@dataclass(frozen=True)
class AnchorWriteResult:
    """What happened, and against which event.

    ``canonical_event_id`` is the event the anchor points at *after* the write.
    On ``COLLISION`` that is the incumbent, not the caller's event — first writer
    wins, deliberately, because it is the only rule that gives the same answer
    on every future call and a duplicate resolution that flip-flops is worse than
    one that is merely arbitrary.
    """

    outcome: str
    key: Optional[AnchorKey] = None
    canonical_event_id: Optional[int] = None


def anchor_key_for_claim(
    source: str,
    source_id: Optional[str],
    *,
    sport_key: Optional[str] = None,
    polymarket_event_id: Optional[str] = None,
    warn_unqualified: bool = True,
) -> Optional[AnchorKey]:
    """Map a registry claim onto its namespace-qualified anchor key.

    Returns ``None`` when the provider is unknown to the key module or the id
    cannot be qualified. ``None`` means *write nothing and match nothing* — the
    conservative answer, and the one an unrecognised StatPal namespace must get
    rather than being guessed into one of the two we know about.

    ``sport_key`` is used by StatPal only, and under D55 (#2879) it is what
    qualifies the key: a StatPal id is only an id *inside its sport*, because
    NFL's 6-digit `contestid` and MLB's 6-digit `id` are otherwise the same key.
    It stays optional in the signature after step 3 deleted the digit-derived
    fallback, because an optional argument that is absent now REFUSES rather
    than guessing — which is the behaviour D55 asks for and the reason the
    parameter no longer needs to be mandatory to be safe.

    ``sport_key`` is OUR ``sports.key`` and is folded to its StatPal ID SPACE
    (:func:`statpal_id_space`) before the key is built — #4393. For every sport
    but tennis and soccer that fold is the identity; for those two it is the
    difference between the key the stampers write (``soccer:9541493``) and a key
    nobody wrote (``soccer_argentina_primera_division:9541493``). Folding is not
    a guess: it is a lookup in our own key vocabulary, which is what D55 means by
    a namespace that is *given* rather than inferred from the id. The fold runs
    only for a qualifier that already passes ``statpal_qualifier_refusal``; see
    the comment at the call below for why that order is load-bearing.

    ``warn_unqualified=False`` turns the log below off for the two callers that
    RE-DERIVE a key from one already written (`anchor_is_current`,
    `invalidate_scalar_anchor`) rather than claiming. Those two legitimately have
    no sport to pass for a non-StatPal or unrecognised key, and a WARNING on a
    corroboration would report a refusal nobody asked for. It is off for
    corroborations and on for claims because only a claim is a write that did
    not happen.
    """
    if source == "odds_api":
        return odds_api_anchor_key(source_id)
    if source == "espn":
        return espn_anchor_key(source_id)
    if source == "statpal":
        # The refusal reason comes from the key module's own rule rather than
        # being re-tested here, so the log line cannot come to describe a rule
        # the code has stopped applying (`statpal_qualifier_refusal`).
        #
        # It is asked for EVERY unusable qualifier, not just an absent one. A
        # present-but-blank qualifier — an empty column, a stripped-to-nothing
        # string — refuses exactly like `None` does and used to do it in
        # silence, which is the one outcome D55 forbids: the caller sees no
        # anchor and no reason, and a hole in the channel looks identical to a
        # sport that simply has no fixture. Same for a qualifier carrying the
        # `:` separator, which is refused because the key could not be split
        # back apart by `anchor_is_current`.
        refusal = statpal_qualifier_refusal(sport_key) if warn_unqualified else None
        if refusal is not None and source_id and str(source_id).strip():
            # WARNING and not DEBUG on purpose, and the reason changed with step
            # 3. While the digit fallback existed this was a COUNTDOWN — it
            # marked a call that still got an answer, by the wrong rule. Now it
            # marks a claim that got NO anchor at all, which is a hole in the
            # channel rather than a deprecation notice, so it must not get
            # quieter as it becomes more serious. D55's second clause is that a
            # key we cannot form raises or tags; this is the tag.
            #
            # Gated on a non-blank `source_id` because a claim with no StatPal
            # id at all is the ordinary case for most events, not a defect, and
            # a warning that fires on the common path is one nobody reads.
            logger.warning(
                "D55/#2879: StatPal anchor claim REFUSED (%s sport_key=%r) for "
                "fixture id=%s, so no anchor was written or matched. The "
                "digit-derived fallback was deleted at step 3; the caller must "
                "pass a non-empty sport_key that contains no ':'.",
                refusal,
                sport_key,
                source_id,
            )
        # #4393. A CLAIM carries OUR `sports.key`; an ANCHOR is keyed by the
        # StatPal ID SPACE that key draws from, and for tennis and soccer those
        # are not the same string. Folded here rather than at either end:
        #
        #   * not in `statpal_anchor_key`, which is deliberately FAITHFUL to the
        #     qualifier it is handed — `test_link_tennis_statpal_anchors.py::
        #     test_the_control_the_raw_sport_key_would_fragment_it` is a control
        #     written to fail if that function ever becomes a folding
        #     pass-through, and it is right to keep failing;
        #   * not at the two `event_registry.py` call sites, which are lane1's
        #     file under D50 — and fixing it here covers every future claimant
        #     rather than the two that exist today.
        #
        # This function's own contract is "map a registry claim onto its
        # NAMESPACE-QUALIFIED anchor key", so choosing the namespace is the job
        # it is named for. Every other StatPal caller already folds explicitly
        # (both stampers, the tennis linker, `admin_providers`); the registry
        # was the only one that did not, and `anchor_is_current`'s comment 200
        # lines below already states the rule it was breaking: *"the writer
        # qualifies by `statpal_id_space()` (`tennis`), not by `sports.key`
        # (`tennis_atp_us_open`), so re-resolving from the event would re-derive
        # a key the writer never wrote."*
        #
        # AFTER the refusal ladder, never before it: `statpal_id_space` matches
        # on a PREFIX, so `statpal_id_space("soccer:9541493")` is `"soccer"` and
        # folding first would promote a `STATPAL_QUALIFIER_SEPARATOR` refusal
        # into an accepted key. Only a qualifier that is already usable is
        # folded; an unusable one is passed through untouched so
        # `statpal_anchor_key` refuses it exactly as it always has.
        #
        # Free at the moment it lands, which is why it lands now: all 1,040
        # StatPal anchors in production (2026-09-09) carry one of six
        # qualifiers — `americanfootball_nfl` 293, `soccer` 256, `tennis` 248,
        # `baseball_mlb` 175, `basketball_nba` 41, `icehockey_nhl` 27 — and
        # every one is already its own id space, so the fold is the identity on
        # every stored row and moves none of them. The four sports the schedule
        # sync actually has beats for are all 1:1, so nothing live changes
        # either; what changes is the FIRST soccer or tennis claim, which today
        # would miss all 256 stamper anchors and mint a second row for each.
        if statpal_qualifier_refusal(sport_key) is None:
            return statpal_anchor_key(source_id, statpal_id_space(sport_key))
        return statpal_anchor_key(source_id, sport_key)
    if source == "kalshi":
        return kalshi_anchor_key(source_id)
    if source == "polymarket":
        return polymarket_anchor_key(
            condition_id=source_id, event_id=polymarket_event_id
        )
    return None


#: One fixed statement for all three scalar columns rather than a column name
#: interpolated per source. The name would come from a frozen module constant
#: and be safe, but a SQL string that is assembled is a SQL string a later edit
#: can make unsafe, and there is nothing to buy by assembling this one.
_CURRENT_SCALAR_IDS_SQL = (
    "SELECT espn_id, external_id, statpal_fixture_id FROM events WHERE id = :event_id"
)
#: Positional order of `_CURRENT_SCALAR_IDS_SQL`. Kept beside it deliberately —
#: the two must change together.
_SCALAR_COLUMN_ORDER = ("espn_id", "external_id", "statpal_fixture_id")

#: Cascade Step 2's read, hoisted to a module constant so a test can execute the
#: STATEMENT rather than a paraphrase of it. A guard that retypes the SQL it is
#: guarding passes forever after the SQL changes.
#:
#: This read carried a second, `OR`-ed predicate for the D55 (#2879) transition:
#: a fixture written before the sport qualifier existed was stored under
#: `s6:`/`s10:` while the caller derived `sport_key:id`, so both shapes had to
#: resolve or the StatPal channel went dark for MLB. Step 3 removed the reason on
#: 2026-09-06 — the 94 legacy rows were re-keyed or deleted and the table holds
#: none — so the predicate is back to the single equality, in the same commit
#: that deleted the writer and `statpal_legacy_source_id`.
#:
#: The `ORDER BY` went with it, and that is the part worth being deliberate
#: about. It existed to make the two-shape case DETERMINISTIC, not to break ties
#: in general: with one predicate a `LIMIT 1` can only be arbitrary if the unique
#: index `(source, source_id, id_kind)` is violated, which it cannot be. An
#: `ORDER BY` retained past its cause reads as a tie-break rule someone relies
#: on, and it is a sort the planner now pays for on every claim.
_FIND_BY_ANCHOR_SQL = (
    "SELECT a.event_id, e.sport_id "
    "FROM event_provider_anchors a "
    "JOIN events e ON e.id = a.event_id "
    "WHERE a.source = :source AND a.id_kind = :id_kind "
    "AND a.source_id = :source_id "
    "LIMIT 1"
)


async def anchor_is_current(
    session: AsyncSession, key: AnchorKey, event_id: int
) -> bool:
    """Does ``event_id`` STILL carry the id this anchor was copied from?

    CERT-410 [P1]. The anchor table's unique key is `(source, source_id,
    id_kind)` and nothing in it records *when* the copy was taken, so an anchor
    derived from `events.espn_id` survives every later change to that column.
    Two live paths change it — `repair_event_espn_id` re-keys it and the
    source-intelligence collision sweep clears it to NULL — and after either one
    the anchor still resolves, still passes the sport check, and still absorbs.
    The executed specimen was `espn:old-id -> event 200` while event 200 carried
    `espn_id='new-id'`: an incoming `old-id` claim landed on event 200, which is
    a *different game*. The stale copy had more authority than the live column.

    ``True`` for any source not in :data:`SCALAR_DERIVED_ID_COLUMNS`. That is not
    a gap. Kalshi and Polymarket have no id column on `events`, which is why they
    were 99.61% of the `NO_ANCHOR_CHANNEL` population in the first place; for
    them the anchor row is the only record of the correspondence and there is no
    second value it could disagree with. Corroborating against a column that does
    not exist would refuse every anchor those two providers have.

    A missing event row is ``False``. The FK is `ON DELETE CASCADE` so it should
    be unreachable, but "the row I was going to corroborate against is gone" is
    not evidence that the anchor is current.
    """
    column = SCALAR_DERIVED_ID_COLUMNS.get(key.source)
    if column is None:
        return True

    row = (
        await session.execute(
            text(_CURRENT_SCALAR_IDS_SQL), {"event_id": event_id}
        )
    ).first()
    if row is None:
        return False

    current_value = dict(zip(_SCALAR_COLUMN_ORDER, row))[column]

    # Re-derive through the SAME key function the writer used rather than
    # comparing raw strings. StatPal's `source_id` is qualified
    # (`baseball_mlb:355372`) while the column holds the bare `355372`, so a raw
    # compare would read every live StatPal anchor as stale — and an id we
    # cannot qualify correctly yields `None` here, i.e. not current, which is
    # the same refusal `statpal_anchor_key` already makes on the write side.
    #
    # D55: the qualifier is read back off the key being tested, not resolved
    # from the event. That is exact — it is by definition the qualifier the
    # writer used — and it costs no query. It is also what makes tennis work,
    # where the two differ: the writer qualifies by `statpal_id_space()`
    # (`tennis`), not by `sports.key` (`tennis_atp_us_open`), so re-resolving
    # from the event would re-derive a key the writer never wrote.
    #
    # A legacy `s6:`/`s10:` key yields `None` from `statpal_sport_from_source_id`
    # and therefore `None` here: NOT current. Before step 3 that case fell
    # through to the digit path so pre-D55 anchors kept corroborating; after the
    # re-key there are none, and a resurrected one SHOULD read as stale rather
    # than authoritative.
    current_key = anchor_key_for_claim(
        key.source,
        current_value,
        sport_key=statpal_sport_from_source_id(key.source_id),
        warn_unqualified=False,
    )
    return (
        current_key is not None
        and current_key.source_id == key.source_id
        and current_key.id_kind == key.id_kind
    )


async def invalidate_scalar_anchor(
    session: AsyncSession,
    *,
    source: str,
    source_id: Optional[str],
    event_id: Optional[int] = None,
    sport_key: Optional[str] = None,
) -> int:
    """Delete the anchor that a scalar-column re-key or clear has just disproven.

    CERT-410 [P1], the write half. Read-side corroboration in
    :func:`anchor_is_current` makes a stale anchor harmless, but harmless is not
    the same as gone: a stale row still occupies its slot in the
    `(source, source_id, id_kind)` unique index, so the next event to genuinely
    acquire that id conflicts with a lie and gets tagged a duplicate of a row it
    has nothing to do with. Removing the assertion at the moment it becomes false
    is the only version of this that keeps the index meaning what it says.

    ``event_id`` scopes the delete to one row's claim, for a **re-key** — the id
    moved off *this* event, and because `ix_events_espn_id` is not unique some
    other event may legitimately hold it. Omit it for a **clear** that removed
    the id from every holder, where no event is left to corroborate.

    Returns the number of rows deleted, so a caller can report it rather than
    assume it. Deleting nothing is the normal case and is not a failure: the
    channel writes only on established correspondences, so most re-keyed rows
    never had an anchor at all.

    ``sport_key`` is the D55 qualifier and matters only for StatPal. Both live
    callers today are ESPN (`repair_event_espn_id` and the source-intelligence
    collision sweep), so it is unset in production; a StatPal re-key site that
    omits it would delete nothing, which is the safe direction — an anchor that
    survives a re-key is caught by `anchor_is_current` on the read side.
    """
    key = anchor_key_for_claim(
        source, source_id, sport_key=sport_key, warn_unqualified=False
    )
    if key is None:
        return 0

    params = {
        "source": key.source,
        "source_id": key.source_id,
        "id_kind": key.id_kind,
    }
    sql = (
        "DELETE FROM event_provider_anchors "
        "WHERE source = :source AND source_id = :source_id "
        "AND id_kind = :id_kind"
    )
    if event_id is not None:
        sql += " AND event_id = :event_id"
        params["event_id"] = int(event_id)

    result = await session.execute(text(sql), params)
    deleted = int(result.rowcount or 0)
    if deleted:
        logger.info(
            "Invalidated %d anchor row(s) for %s:%s (%s)%s — the column it was "
            "copied from no longer holds this id (#2225)",
            deleted, key.source, key.source_id, key.id_kind,
            f" on event {event_id}" if event_id is not None else "",
        )
    return deleted


async def find_event_by_anchor(
    session: AsyncSession,
    key: Optional[AnchorKey],
    *,
    expected_sport_id: Optional[int] = None,
) -> Optional[int]:
    """Cascade Step 2: which event does this provider id already name?

    Returns an ``event_id`` only for a ``game`` anchor whose event is in
    ``expected_sport_id`` (when supplied). Every other case is a miss.

    A ``market`` or ``container`` anchor is not consulted at all — not filtered
    late, not scored low, simply never queried — because the difference between
    "did not match" and "matched but was rejected" is the difference between a
    rule and a threshold, and ruling 048 exists because five rounds of threshold
    tuning each produced a new specimen class.
    """
    if key is None or not key.may_anchor_absorption:
        return None

    row = (
        await session.execute(
            text(_FIND_BY_ANCHOR_SQL),
            {
                "source": key.source,
                "source_id": key.source_id,
                "id_kind": key.id_kind,
            },
        )
    ).first()

    if row is None:
        return None

    event_id, sport_id = row[0], row[1]

    if expected_sport_id is not None and sport_id != expected_sport_id:
        # Never absorb across sports on an anchor. The anchor may be right and
        # the event's sport wrong, or the reverse; either way this is a data
        # defect to surface, not a correspondence to act on.
        logger.warning(
            "Anchor %s:%s (%s) points at event %s in sport %s, but the claim is "
            "sport %s — refusing the cross-sport absorption (#2213)",
            key.source, key.source_id, key.id_kind,
            event_id, sport_id, expected_sport_id,
        )
        return None

    if not await anchor_is_current(session, key, event_id):
        # CERT-410 [P1]. The column is the truth and the anchor is a copy of it.
        # A copy that disagrees with its source has been disproven, and a
        # disproven assertion may not absorb — this is the same refusal the
        # cross-sport branch above makes, arrived at from the other direction.
        logger.warning(
            "STALE ANCHOR (#2225): %s:%s (%s) names event %s, but that event no "
            "longer carries this id in events.%s. The column is the truth and "
            "the anchor is a copy — refusing the absorption.",
            key.source, key.source_id, key.id_kind, event_id,
            SCALAR_DERIVED_ID_COLUMNS[key.source],
        )
        return None

    return event_id


async def record_anchor(
    session: AsyncSession,
    *,
    event_id: int,
    key: Optional[AnchorKey],
    claim_context: Optional[dict] = None,
) -> AnchorWriteResult:
    """Establish ``key -> event_id``, idempotently, and report what was already there.

    ``ON CONFLICT DO NOTHING`` followed by a read-back rather than an upsert: the
    incumbent must never be repointed. An anchor that can be moved by a later
    writer is not an identity, and a duplicate resolution that changes answer
    depending on poll order is worse than an arbitrary one that is stable.

    The conflict is the point. It is the moment the system first holds proof —
    keyed on an id, not guessed from names and a window — that two event rows are
    one game. Swallowing it would discard the only signal ruling 048's drain
    clause has ever had.
    """
    if key is None:
        return AnchorWriteResult(outcome=NO_KEY)

    inserted = (
        await session.execute(
            text(
                "INSERT INTO event_provider_anchors "
                "(event_id, source, source_id, id_kind, claim_context) "
                "VALUES (:event_id, :source, :source_id, :id_kind, "
                "CAST(:claim_context AS jsonb)) "
                "ON CONFLICT (source, source_id, id_kind) DO NOTHING "
                "RETURNING event_id"
            ),
            {
                "event_id": event_id,
                "source": key.source,
                "source_id": key.source_id,
                "id_kind": key.id_kind,
                # gotcha: a bare `:param::jsonb` bind is dropped by `text()`;
                # CAST(:p AS jsonb) is the form that survives.
                "claim_context": _json_or_none(claim_context),
            },
        )
    ).first()

    if inserted is not None:
        return AnchorWriteResult(
            outcome=WROTE, key=key, canonical_event_id=event_id
        )

    incumbent = (
        await session.execute(
            text(
                "SELECT event_id FROM event_provider_anchors "
                "WHERE source = :source AND source_id = :source_id "
                "AND id_kind = :id_kind LIMIT 1"
            ),
            {
                "source": key.source,
                "source_id": key.source_id,
                "id_kind": key.id_kind,
            },
        )
    ).first()

    if incumbent is None:
        # The conflicting row vanished between the INSERT and the SELECT — a
        # concurrent delete, or a rollback in another session. Report NO_KEY
        # rather than inventing a canonical: the caller's correct response to
        # "we could not establish it" is to do nothing, and it will retry.
        logger.info(
            "Anchor %s:%s (%s) conflicted then disappeared — no canonical to report",
            key.source, key.source_id, key.id_kind,
        )
        return AnchorWriteResult(outcome=NO_KEY, key=key)

    canonical = incumbent[0]
    if canonical == event_id:
        return AnchorWriteResult(
            outcome=CONFIRMED, key=key, canonical_event_id=canonical
        )

    if not await anchor_is_current(session, key, canonical):
        # CERT-410 [P1], the same current-holder premise the read side applies.
        # A COLLISION is the system's only *proof* that two rows are one game,
        # and the proof is the shared id. If the incumbent no longer holds that
        # id, nothing is shared and there is nothing to prove — tagging here
        # would brand a live event a duplicate of a row it never matched. The
        # stale row is left for `invalidate_scalar_anchor` at the re-key site
        # rather than being repointed here: an anchor that a later writer can
        # move is not an identity, and this path cannot tell a disproven
        # incumbent from one whose column is mid-repair.
        logger.warning(
            "STALE INCUMBENT ANCHOR (#2225): %s id %r (%s) is held by event %s, "
            "which no longer carries it in events.%s. Event %s is NOT tagged a "
            "duplicate — a disproven anchor is not proof of anything.",
            key.source, key.source_id, key.id_kind, canonical,
            SCALAR_DERIVED_ID_COLUMNS[key.source], event_id,
        )
        return AnchorWriteResult(outcome=STALE_INCUMBENT, key=key)

    logger.warning(
        "ANCHOR COLLISION (#2213): %s id %r (%s) is claimed by event %s and "
        "event %s. One provider id, two rows — an id-anchored duplicate. "
        "Canonical is %s (first writer wins).",
        key.source, key.source_id, key.id_kind, canonical, event_id, canonical,
    )
    return AnchorWriteResult(
        outcome=COLLISION, key=key, canonical_event_id=canonical
    )


async def record_link_anchor(
    session: AsyncSession,
    *,
    event_id: int,
    source: str,
    provider_id: Optional[str],
) -> AnchorWriteResult:
    """Record the anchor a MATCHER LINK establishes — and never absorb on it.

    Q477 (P476-2). Until now the only writer into this channel was
    `find_or_create_event`, so an event acquired an anchor only if a provider
    claim CREATED it or resolved to it through the registry. When the matcher
    links a market to an event that already exists — the ordinary, healthy path
    — the correspondence was established and then not written down. Measured on
    production 2026-08-31: the four real EPL fixtures played that day carried
    **no `event_provider_anchors` row at all**, while the four scoreless twins
    minted beside them each carried one. The side with the schedule, the score
    and the users was the side missing from the channel.

    Two deliberate narrowings, both of which are the safety argument:

    **Only a `game` key is written.** A `market` or `container` anchor is never
    consulted by :func:`find_event_by_anchor`, so writing one here would add a
    row per newly-linked market and resolve nothing. That is a separate,
    unmeasured question and it is parked rather than ridden.

    **A COLLISION here NEVER tags.** :func:`record_anchor` resolves a conflict
    first-writer-wins, which is the right rule between two claims of equal
    standing and the WRONG one here: the incumbent is typically a ticker-derived
    twin that got there first, and the event being linked is typically the
    schedule-derived row carrying the score. Tagging on it would brand the real
    row a duplicate of its own twin and hide it from the league rails. So this
    writes when the id is unclaimed and otherwise reports and does nothing —
    monotone, and incapable of moving an identity that already exists.
    """
    key = anchor_key_for_claim(source, provider_id)
    if key is None or not key.may_anchor_absorption:
        return AnchorWriteResult(outcome=NO_KEY, key=key)

    result = await record_anchor(
        session,
        event_id=event_id,
        key=key,
        claim_context={"source": source, "established_by": "matcher_link"},
    )

    if result.outcome == COLLISION:
        logger.info(
            "Link anchor %s:%s (%s) is already held by event %s while linking a "
            "market to event %s — leaving the incumbent and NOT tagging: at a "
            "link site first-writer-wins cannot tell a real row from its twin "
            "(Q477)",
            key.source, key.source_id, key.id_kind,
            result.canonical_event_id, event_id,
        )

    return result


def _json_or_none(value: Optional[dict]) -> Optional[str]:
    if value is None:
        return None
    import json

    return json.dumps(value, default=str)


# ═══ Q050: the drain clause, on the read side ═══════════════════════════════
#
#: The `events.commence_time_source` values that mean **this row's start came
#: out of a prediction market**, i.e. the row was BORN from one. Written at
#: CREATE by `event_registry` (`identity.commence_time_source or
#: identity.claim.source`) and safe in both directions:
#:
#: * It cannot be acquired later by a real fixture. `_SOURCE_PRIORITY` ranks
#:   `kalshi` and `polymarket` at 0, below every schedule source, so nothing
#:   downgrades an `odds_api`/`espn`/`statpal` row into this set.
#: * It CAN be lost, and losing it is correct. A row a real schedule later
#:   rescues stops being a stand-in, and stops being drainable here, on the same
#:   write.
#:
#: `None` is deliberately absent. Most of the table predates the column, and
#: reading a missing provenance as "market-born" would put nearly every historic
#: row in this class — q076's stated narrowness, from the other side.
#:
#: ═══ #6262: A REFINEMENT OF A MEMBER IS STILL A MEMBER ══════════════════════
#:
#: `kalshi_occurrence` and `polymarket_venue` joined the vocabulary AFTER q076
#: wrote this set, and nothing here was ever wrong — two entries were simply
#: never added. Both are the SAME provider writing the SAME row, and both exist
#: only to record WHICH of that provider's two time fields answered
#: (`occurrence_datetime` rather than a day parsed out of a ticker; Gamma's
#: `startTime` rather than its `startDate` listing stamp). Their own docstrings
#: in `event_completion` say so. **A row does not stop being market-born
#: because its market told us a better hour.**
#:
#: 🔴 That omission had the perverse shape: `recover_kalshi_occurrence_starts`
#: REWRITES `commence_time_source` to `kalshi_occurrence`, so improving a
#: ghost's hour used to remove it from this class. Fixing the time un-drained
#: the row.
#:
#: The safety clause above survives both additions, and that is the reason they
#: are safe rather than merely plausible: `_SOURCE_PRIORITY` ranks
#: `polymarket_venue` at 0 explicitly, and `kalshi_occurrence` is unlisted,
#: which `commence_time_write_authorized` reads as 0 by its `.get(..., 0)`
#: default. A write lands only on `incoming > current`, so no `odds_api`(1),
#: `statpal`(2), `espn`(3) or `mlb_schedule_repair`(4) row can be downgraded
#: into this set — nor can a `None`-sourced historic row, which also reads 0.
#: `test_every_market_born_source_ranks_below_every_schedule_source_6262` pins
#: that in both directions so this stays a property and not a coincidence.
#:
#: Measured on production 2026-09-15 01:5xZ, over the whole `live`+`scheduled`
#: candidate population: the band clearing the first six refusals goes **35 ->
#: 42**, and all seven new members are genuine — six `polymarket_venue` tennis
#: rows that resolve to a same-family canonical (a search for `Badosa` served
#: `Justina Mikulskyte v Paula Badosa` TWICE, 13:00Z and 20:30Z, both "No price
#: yet"), and one `kalshi_occurrence` row, `15305046`, which the sport-family
#: refusal still declines. **This change does not close that one**: it is a
#: `basketball_other` ghost of an `americanfootball_nfl` fixture and needs the
#: separate catch-all-key question (#6262 gap B), which relaxes a guard rather
#: than completing a set.
MARKET_BORN_COMMENCE_SOURCES = frozenset(
    {
        SOURCE_KALSHI,
        SOURCE_POLYMARKET,
        TICKER_DERIVED_COMMENCE_SOURCE,
        KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        POLYMARKET_VENUE_COMMENCE_SOURCE,
    }
)

#: One statement, one round trip: every fact the drain verdict turns on, for
#: EVERY id asked about at once.
#:
#: `mkt` resolves each event's MARKET anchors back through the market they name
#: — `(source, external_id)` is `uq_futures_source_external`, a UNIQUE index, so
#: each anchor yields at most one row and the LEFT JOIN cannot fan out.
#:
#: `market_id` is the SECOND witness refusal 6 weighs (#6262 gap B), and it is
#: the anchor's `source_id` — **the venue's own ticker, read back verbatim**.
#: `kalshi_anchor_key` stores the raw ticker and `polymarket_anchor_key` the raw
#: `conditionId`; no code path anywhere writes an anchor's `source_id` from an
#: event. That is the whole reason this column and not another is the witness:
#: see refusal 6 for the one that looked right and was not.
#:
#: 🔴 THIS IS THE ONLY DRAIN VERDICT. #6231 needed the same seven refusals over a
#: PAGE of rows rather than one id, and the obvious shape — a second, batched
#: SQL beside this one — is the shape that goes wrong: two statements encoding
#: one rule drift, and the drift direction that matters is the one that ADMITS a
#: row this refuses, which serves a reader the wrong match. So the set form is
#: the only form, `resolve_market_born_duplicate` calls it with one id, and the
#: single-id battery in `test_market_born_duplicate_reads_as_canonical_q050.py`
#: — which pins all seven refusals — grades this statement unchanged.
_DRAIN_VERDICT_SQL = """
WITH cand AS (
    SELECT e.id AS event_id,
           e.commence_time_source AS provenance,
           s.key AS sport_key,
           (e.home_score IS NOT NULL OR e.away_score IS NOT NULL
            OR e.completed_at IS NOT NULL) AS carries_truth
      FROM events e
      LEFT JOIN sports s ON s.id = e.sport_id
     WHERE e.id IN :event_ids
),
anch AS (
    SELECT a.event_id, a.source, a.source_id, a.id_kind
      FROM event_provider_anchors a
      JOIN cand ON cand.event_id = a.event_id
),
mkt AS (
    SELECT anch.event_id, fm.event_id AS target, anch.source_id AS market_id
      FROM anch
      LEFT JOIN futures_markets fm
             ON fm.source = anch.source
            AND fm.external_id = anch.source_id
     WHERE anch.id_kind = :market_kind
)
SELECT
    cand.event_id,
    cand.provenance,
    cand.sport_key,
    cand.carries_truth,
    (SELECT count(DISTINCT mkt.market_id) FROM mkt
      WHERE mkt.event_id = cand.event_id) AS market_ids,
    (SELECT min(mkt.market_id) FROM mkt
      WHERE mkt.event_id = cand.event_id) AS market_id,
    (SELECT count(*) FROM anch
      WHERE anch.event_id = cand.event_id AND anch.id_kind = :game_kind)
        AS game_anchors,
    (SELECT count(*) FROM mkt WHERE mkt.event_id = cand.event_id)
        AS market_anchors,
    (SELECT count(*) FROM mkt
      WHERE mkt.event_id = cand.event_id AND mkt.target IS NULL) AS unresolved,
    (SELECT count(DISTINCT mkt.target) FROM mkt
      WHERE mkt.event_id = cand.event_id
        AND mkt.target IS NOT NULL AND mkt.target <> cand.event_id)
        AS other_targets,
    (SELECT min(mkt.target) FROM mkt
      WHERE mkt.event_id = cand.event_id
        AND mkt.target IS NOT NULL AND mkt.target <> cand.event_id)
        AS candidate_id,
    EXISTS (SELECT 1 FROM futures_markets f WHERE f.event_id = cand.event_id)
        AS holds_markets
  FROM cand
"""

#: The sport key of each id named — the canonical side of refusal 6.
#:
#: One statement for the whole page, for the same reason the verdict is: the
#: family check is not decoration. Measured on production 2026-09-15 05:30Z it
#: still refuses 4 of the 45 rows that clear every other refusal on the GHOST
#: ROW's key alone, and admits 3 of those 4 once the anchor TICKER's sport is
#: weighed beside it (#6262 gap B) — so a batch path that quietly dropped this
#: lookup would serve a reader a football game under a basketball card.
_SPORT_KEY_BY_ID_SQL = (
    "SELECT e.id, s.key FROM events e LEFT JOIN sports s ON s.id = e.sport_id "
    "WHERE e.id IN :event_ids"
)

#: The two statements above as executable clauses, built ONCE.
#:
#: `expanding=True` is what turns `IN :event_ids` into an id list at execution
#: time, with every value still a bound parameter — the set form adds no string
#: interpolation anywhere, which is the property that matters for a statement
#: taking a caller-supplied page of ids.
#:
#: Built at import rather than per call so that "the module's statement" is an
#: OBJECT a test can compare against, not a string a test has to re-derive; the
#: paraphrase guard in the Q050 battery asserts identity against these.
_DRAIN_VERDICT = text(_DRAIN_VERDICT_SQL).bindparams(
    bindparam("event_ids", expanding=True)
)
_SPORT_KEY_BY_ID = text(_SPORT_KEY_BY_ID_SQL).bindparams(
    bindparam("event_ids", expanding=True)
)


def _sport_family(sport_key: Optional[str]) -> Optional[str]:
    """The LLM category behind a sport key's prefix, or ``None`` if unreadable.

    `tennis_atp` and `tennis_atp_us_open` are two `sports` rows for one sport,
    and the ghost/canonical pair is very often exactly that pair — so an
    equal-`sport_id` check (which `find_event_by_anchor` can afford, because it
    guards an absorption) would refuse the whole specimen class. The family is
    the honest granularity: it still refuses tennis→soccer, which is the outcome
    worth refusing.
    """
    if not sport_key:
        return None
    return get_llm_category_for_prefix(sport_key.split("_", 1)[0])


def is_drain_candidate_row(
    *,
    commence_time_source: Optional[str],
    home_score: Optional[int],
    away_score: Optional[int],
    completed_at=None,
) -> bool:
    """Cheap, pure gate: could this row POSSIBLY be a market-born duplicate?

    Two of :func:`resolve_market_born_duplicate`'s seven refusals — market-born
    provenance, and no truth of its own — are answerable from columns the caller
    is already holding, and together they exclude essentially all event-page
    traffic. Without this an `odds_api` fixture's page would pay a verdict query
    it can never pass, on product priority #3.

    **This is an optimisation, and the SQL re-asserts both conditions.** The
    duplication is deliberate: a gate that drifts can only ever refuse a row the
    verdict would have drained (a ghost renders, which is today's behaviour),
    never admit one it would not (a reader served the wrong match). Only one of
    those two directions is recoverable, and this is the one.
    """
    if (
        home_score is not None
        or away_score is not None
        or completed_at is not None
    ):
        return False
    return commence_time_source in MARKET_BORN_COMMENCE_SOURCES


async def resolve_market_born_duplicate(
    session: AsyncSession, event_id: int
) -> Optional[int]:
    """The event a market-born duplicate row should be READ AS, or ``None``.

    One id. :func:`resolve_market_born_duplicates` is the implementation and
    carries the whole argument — the proof, the seven refusals and what this
    deliberately does not claim. Read it there; there is only one of it.
    """
    resolved = await resolve_market_born_duplicates(session, [event_id])
    return resolved.get(int(event_id))


async def resolve_market_born_duplicates(
    session: AsyncSession, event_ids: Sequence[int]
) -> dict[int, int]:
    """``{ghost id: canonical id}`` for every market-born duplicate among these.

    Ids that are not market-born duplicates are simply absent from the result,
    so a caller can treat the mapping as "what this page must not print" without
    checking anything twice. An empty input, or any error, is ``{}`` — this
    decorates a read, and a read that cannot decide serves the rows it was asked
    for.

    Q050. Ruling 048's bounding clause — *"id-keyed reconciliation drains the
    duplicate when an id arrives"* — has two halves, and only the first was ever
    built. `_reconcile_kalshi_match_segments` (Q435/Q048) moves the markets onto
    the schedule-derived row and its docstring calls that the drain; it is not.
    Measured on production 2026-09-02, after Q048 deployed: `KXATPMATCH-
    26AUG30VALMON` sits correctly on event 15293804, and event 15300759 — the
    row that market created — still answers `/api/events/15300759` with
    `status: scheduled, commence_time: 2026-08-30 00:00Z`, for a match ESPN had
    final at 2026-09-01 23:05Z. Moving the market did not drain the row; it
    orphaned it.

    ═══ WHERE THE PROOF COMES FROM, AND WHY IT IS NOT A LOOSENING ═══

    `event_provider_anchors` holds `KXATPMATCH-26AUG30VALMON -> 15300759`. The
    market itself now holds `event_id = 15293804`. **That contradiction is the
    id-keyed proof**, and neither side of it is a guess:

    * the anchor is a back-pointer written by the registry at the moment the
      market established the correspondence — one provider id, recorded, not
      inferred;
    * the market's current `event_id` was chosen by the segment reconciler out
      of Kalshi's OWN ticker segment (ruling 048 arm A), or by the matcher off a
      provider id. No name was compared and no time window was opened at any
      point in the chain.

    So this does not grant a `market` anchor the authority `may_anchor_absorption`
    withholds. It never asks "are these the same game?" — the system already
    answered that when it moved the market. It asks the strictly weaker question
    **"is this row now the abandoned side of a correspondence that has already
    been re-decided?"**, and nothing is absorbed, merged, deleted or repointed:
    the row stays addressable and the resolution is recomputed from live state
    on every call, so a market that moves back un-drains its row for free.

    ═══ THE SIX REFUSALS, EACH LOAD-BEARING ═══

    Measured over the whole production population on 2026-09-02: 505 events
    satisfy all of them, 505 of 505 carry `provenance:unanchored` — i.e. the
    class is exactly the declared, bounded cost ruling 048 said it was paying.

    1. **No `game` anchor.** A game anchor is a real schedule provider naming
       this row; that row is a fixture, whatever its markets did. (0 of 505.)
    2. **`commence_time_source` is market-born** — see
       :data:`MARKET_BORN_COMMENCE_SOURCES`. This is the guard that stops a real
       Odds API fixture which merely *acquired* a Kalshi market anchor from being
       read as a ghost: `_record_claim_anchor` fires on the ATTACH path too for
       the column-less providers, so a market anchor alone is not a birth record.
    3. **At least one market anchor, and every one of them resolves.** An
       unresolvable anchor is a market we no longer hold, which is silence, not
       evidence (gotcha #53).
    4. **Exactly one distinct destination.** Two destinations is an ambiguity,
       and picking by row order would be a coin flip dressed as a resolution —
       `_choose_segment_event`'s refusal, applied here. `DISTINCT` and not a
       plain count: a segment routinely moves several markets at once, and three
       anchors agreeing on one destination is the strongest case there is, not
       an ambiguity.
    5. **The row holds no markets of its own and carries no score, no
       `completed_at`.** A row with truth of its own is not an abandoned husk.
       This clause does two more jobs that are easy to miss:

       * it is why a **CHAIN** is impossible. The destination was found by
         reading a market's `event_id`, so the destination holds that market —
         a canonical can therefore never itself be drainable, whatever the data
         does. That is a proof, not a measurement.
       * it **subsumes** the "no anchor still names this row" case. A half-moved
         correspondence leaves a market pointing back here, and a market
         pointing here is a market this row holds. The battery found that out
         the hard way: the separate `still_own` clause was unkillable because it
         was unreachable, so it is gone rather than kept as decoration.

       Under-coverage is the safe failure direction — a missed ghost renders, a
       wrong resolution serves the wrong match.
    6. **Same sport family** (:func:`_sport_family`) — **weighed against TWO
       witnesses, not one** (#6262 gap B). The canonical's family must equal the
       ghost ROW's family, *or* the family the ghost's own anchor TICKER names.

       🔴 **THE GHOST ROW'S OWN SPORT IS THE WEAKER WITNESS, AND IT IS THE ONE
       THIS REFUSAL USED TO CONSULT ALONE.** A market-born row's `sport_id` is
       stamped once, at mint, from whatever `_categorize_kalshi_market` could
       tell at the time; for an UNMAPPED Kalshi series that is step 2, a guess
       off the market's TEXT. `sport_keys.py` records what that produces — one
       NFL series scattered across five sports, `kxnflrace`'s 80 markets all
       landing on `basketball_other`, "Fantasy POINTS" reading as basketball
       (Q453, #5621). The event row minted in the meantime keeps the guess
       forever. So the disagreement this refusal was firing on is not evidence
       of a cross-sport read — it is the fossil of a bug fixed elsewhere.

       🔴 **THE SECOND WITNESS MUST BE ONE THE LINK WRITER CANNOT TOUCH, AND THE
       OBVIOUS CANDIDATE IS NOT (CERT-2891).** The first build of this clause
       asked the MARKET's `sport_id` — and `_set_market_sport_fields` sets
       `market.sport_id = matched_event["sport_id"]`, so the market's sport is
       COPIED FROM THE EVENT THE DRAIN IS BEING ASKED TO CONFIRM. It agreed with
       the canonical in 42 of 42 rows measured, which read as overwhelming
       corroboration and was a tautology: a copy equalling its source. Worse
       than useless — a soccer ghost whose soccer market is mis-attached to a
       TENNIS canonical refuses on the first pass, the writer then stamps the
       market tennis, and the second pass admits the cross-sport read the
       refusal exists to stop. **Before two columns are allowed to vouch for
       each other here, find each one's writer.**

       The witness is therefore the **anchor's `source_id`** — the venue's own
       ticker — through :func:`get_sport_key_from_ticker`, a pure function over
       the static maps in `sport_keys.py`. `kalshi_anchor_key` stores the raw
       ticker verbatim and nothing derives it from an event, so no link writer
       can move it. It needs no join to `futures_markets` at all, so the market
       row cannot contaminate it either.

       **Measured through THIS STATEMENT over the whole production
       `live`+`scheduled` band, 2026-09-15 05:30Z** — 1,337 rows, of which 45
       clear every other refusal: 41 already folded on the ghost row's own key,
       and the ticker witness adds **3** — 15305032, 15305039, 15305046, all
       `basketball_other` rows minted by `KXNFLRACE-…` tickers that read
       `americanfootball_nfl`. **Three at that hour, and the fourth was named
       rather than rounded away:** ghost 15311150, ticker `KXNFLFG-26SEP14DENKC`,
       a series then absent from both ticker maps, so `get_sport_key_from_ticker`
       returned `None`, there was no second witness, and it stayed refused.
       Mapping `kxnflfg` is a `sport_keys.py` change with its own blast radius
       and was not smuggled in here. Under-coverage is the safe direction.
       (A fifth row of the same shape, 15305029, is declined by refusal 7 for
       holding its own markets — the refusals compose, and a claim counted
       before them is inflated.)

       🟢 **THE FOURTH FOLDS AS OF 2026-09-15, AND NOT ONE LINE OF THIS FILE
       MOVED (#6262 follow-up, `71e1e5b7`).** `kxnflfg` was mapped where it
       belonged — in `sport_keys.py`, in its own ship, carrying its own blast
       radius — and this statement picked the fold up for free. That is the
       property the second witness was built for, so the paragraph above is
       kept as written rather than rewritten: it is a true reading of 05:30Z,
       and the way its gap closed is the argument. **Measured on production
       2026-09-15 09:0xZ, after the main-app release recorded as carrying it:**
       `GET /api/events/15311150` answers `14638896`; the control `15311995`
       answers itself, so it is a fold and not a blanket redirect; and the ghost
       is off `/api/events/search?q=Denver` via `market_born_duplicates_on_page`
       while the canonical 14638896 is still served there. The ghost row itself
       is untouched in `events` — still `scheduled`, still `sport_id` 37873 —
       which is what "suppress, do not fold" means and why nothing here had to
       change. **The lesson for the next refusal that comes up one short: the
       repair is usually a map entry, never a loosened refusal.**

       **What still refuses, and it is the whole point:** a ghost whose ticker
       is a soccer ticker resolving onto an NFL canonical fails BOTH witnesses,
       *and goes on failing after the writer has run*, which is the property
       CERT-2891 found missing. `market_ids <> 1` (several distinct tickers on
       one ghost) yields no second witness and the row falls back to the ghost
       key exactly as before: ambiguity is not evidence, the same reading
       refusal 4 takes of two destinations. That branch is deliberately coarser
       than it could be — two tickers of the SAME sport read as ambiguity rather
       than as agreement — because collapsing them would mean deriving per
       ticker in Python and the aggregation is worth less than the single
       statement. Measured: **7,987 of 7,987** market-born ghosts carry exactly
       one distinct market anchor, so the coarse branch is empty today, and the
       direction it errs in is refusal.

       Under-coverage remains the safe direction here as in refusal 5 — which
       is why the second witness must AGREE with the canonical to admit, and can
       never be used to refuse something the first witness already cleared.

    Only `market` anchors are read. A `game` anchor is counted (refusal 1) and a
    `container` anchor — a Polymarket event id — is IGNORED rather than treated
    as an unresolvable market, which would refuse every Polymarket-born ghost
    the day containers start being written. The table holds none today; the
    key module already produces them.

    ═══ WHY THIS IS THE SET FORM AND THE SINGLE-ID ONE IS THE WRAPPER ═══

    #6231. The event page has folded a market-born ghost onto its canonical
    since Q050, and no LIST surface has. A reader on the Sports tab therefore
    saw `Celta Fortuna v Eibar` topping "Live Now" — scoreless, priceless, under
    a red LIVE chip, 1h40m after the real match went 0–4 final on another row —
    and tapping it landed them on the right game. The tab that sent them there
    was advertising a row the detail endpoint already knew was not a fixture.

    **The list rails' own instrument cannot reach this, whatever its key does.**
    `fold_twin_events` is a pure IN-PAGE fold: it needs both rows in the same
    result set. On `GET /api/events?status=live` the canonical is `completed`,
    so the very filter that selects the ghost excludes its twin, and no widening
    of `twin_fold_key` — names, minute, league — can close that. The verdict
    below has no such limit: it is id-keyed and asks the database, so the
    canonical does not have to be on the page, or be renderable at all.

    So a page-shaped caller needs this per ROW, and doing that one id at a time
    is a round trip per candidate. Hence the set form — and the set form is the
    ONLY form. See `_DRAIN_VERDICT_SQL` for why there is not a second batched
    statement beside the single-id one.

    Returns ``{}`` for a page with nothing to drain — which is nearly every page,
    because callers apply :func:`is_drain_candidate_row` first and the query is
    never issued when it excludes everything.
    """
    ids = sorted({int(e) for e in event_ids if e is not None})
    if not ids:
        return {}

    params = {
        "event_ids": ids,
        "market_kind": ANCHOR_KIND_MARKET,
        "game_kind": ANCHOR_KIND_GAME,
    }
    try:
        rows = (await session.execute(_DRAIN_VERDICT, params)).fetchall()
    except Exception:  # pragma: no cover - defensive, see docstring
        logger.exception(
            "Drain verdict query failed for %d event(s) — serving them as asked",
            len(ids),
        )
        return {}

    # Refusals 1-5, all answerable from the verdict row itself. An id that is
    # absent from `rows` (no such event) simply never reaches this loop.
    passed: dict[int, int] = {}
    ghost_witnesses: dict[int, tuple[Optional[str], Optional[str]]] = {}
    for row in rows:
        verdict = row._mapping
        candidate = verdict["candidate_id"]
        if (
            verdict["game_anchors"]
            or verdict["provenance"] not in MARKET_BORN_COMMENCE_SOURCES
            or not verdict["market_anchors"]
            or verdict["unresolved"]
            or verdict["other_targets"] != 1
            or verdict["carries_truth"]
            or verdict["holds_markets"]
            or candidate is None
        ):
            continue
        ghost_id = int(verdict["event_id"])
        passed[ghost_id] = int(candidate)
        # Refusal 6's two witnesses to the GHOST's sport. The second is derived
        # HERE, from the venue's own ticker, and never read from a column a link
        # writer fills — CERT-2891 blocked the version that asked the market's
        # `sport_id`, which `_set_market_sport_fields` copies off the very event
        # this drain is trying to confirm. `market_ids <> 1` is ambiguity, and
        # ambiguity is not evidence (refusal 4's reading).
        market_family = (
            _sport_family(get_sport_key_from_ticker(verdict["market_id"]))
            if verdict["market_ids"] == 1
            else None
        )
        ghost_witnesses[ghost_id] = (
            _sport_family(verdict["sport_key"]),
            market_family,
        )

    if not passed:
        return {}

    # Refusal 6, the canonical's half. One statement for every candidate.
    try:
        canonical_rows = (
            await session.execute(
                _SPORT_KEY_BY_ID, {"event_ids": sorted(set(passed.values()))}
            )
        ).fetchall()
    except Exception:  # pragma: no cover - defensive, see docstring
        logger.exception(
            "Canonical sport lookup failed for %d candidate(s) — serving the "
            "rows as asked",
            len(passed),
        )
        return {}

    # A candidate missing from this map is a row that vanished between the two
    # reads. It is a refusal, not a resolution: `.get` yields `None`, whose
    # family is `None`, which is never IN a witness set that excludes `None`.
    canonical_sports = {int(r[0]): r[1] for r in canonical_rows}

    resolved: dict[int, int] = {}
    for ghost_id, candidate in passed.items():
        ghost_family, market_family = ghost_witnesses[ghost_id]
        canonical_family = _sport_family(canonical_sports.get(candidate))
        # `None` is excluded by construction, which is what makes the plain
        # membership test below safe: an unreadable canonical key is `None`, and
        # `None` can never be in the set, so it refuses without a second clause.
        # Refusal 5's lesson — a clause that cannot fail is decoration, not a
        # guard — applied here rather than re-learned.
        witnesses = {f for f in (ghost_family, market_family) if f is not None}
        if canonical_family not in witnesses:
            logger.warning(
                "Refusing to resolve event %s to %s: canonical family %r is "
                "named by neither witness (ghost row %r, anchor ticker %r) "
                "(Q050) — a cross-sport read is the one outcome worth refusing",
                ghost_id, candidate, canonical_family,
                ghost_family, market_family,
            )
            continue
        logger.info(
            "Event %s is a market-born duplicate of %s — reading as the "
            "canonical row (Q050, ruling 048 drain clause; sport agreed by "
            "%s)",
            ghost_id, candidate,
            "the ghost row" if ghost_family == canonical_family
            else "the anchor ticker, over the ghost row's %r" % (ghost_family,),
        )
        resolved[ghost_id] = candidate

    return resolved


async def market_born_duplicates_on_page(
    session: AsyncSession, events: Sequence[Any]
) -> dict[int, int]:
    """``{ghost id: canonical id}`` for the rows on this page that must not print.

    The list-surface entry point. Hand it the hydrated rows a rail is about to
    serve and it names the ones the event page has already been declining to
    render since Q050 (#6231).

    **It costs nothing on a page with no candidates, and that is the whole
    reason it exists rather than the routes calling the resolver directly.**
    :func:`is_drain_candidate_row` is pure and answers from columns the rows are
    already holding, and it excludes every scored row, every completed row and
    everything a real schedule timed — so on the overwhelming majority of pages
    the candidate set is empty and NO query is issued. A rail whose rows all
    carry scores never touches the database for this.

    🔴 **SUPPRESS, DO NOT FOLD — and here that is a proof rather than a
    preference.** The usual hazard in hiding a ghost is that the ghost was the
    row holding the markets, so hiding it empties the fixture. It cannot happen
    here: refusal 5 admits a row only if it holds NO markets of its own, no
    score and no `completed_at`. The rows this names are empty by construction,
    which is exactly what the reader was complaining about — a card that could
    never be filled in. There is nothing on them to carry anywhere.

    Nothing is written. The rows stay in the table, addressable, visible to the
    sentinels and to #2693, and the verdict is recomputed from live state on
    every request — so a market that moves back un-suppresses its row for free.

    Never raises: a page is better unsuppressed than 500, and the caller's own
    `except` is the belt (gotcha #42 applied to a stage).
    """
    candidates = [
        int(e.id)
        for e in events
        if getattr(e, "id", None) is not None
        and is_drain_candidate_row(
            commence_time_source=getattr(e, "commence_time_source", None),
            home_score=getattr(e, "home_score", None),
            away_score=getattr(e, "away_score", None),
            completed_at=getattr(e, "completed_at", None),
        )
    ]
    if not candidates:
        return {}
    return await resolve_market_born_duplicates(session, candidates)
