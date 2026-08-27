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
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    SCALAR_DERIVED_ID_COLUMNS,
    AnchorKey,
    espn_anchor_key,
    kalshi_anchor_key,
    odds_api_anchor_key,
    polymarket_anchor_key,
    statpal_anchor_key,
)

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
    polymarket_event_id: Optional[str] = None,
) -> Optional[AnchorKey]:
    """Map a registry claim onto its namespace-qualified anchor key.

    Returns ``None`` when the provider is unknown to the key module or the id
    cannot be qualified. ``None`` means *write nothing and match nothing* — the
    conservative answer, and the one an unrecognised StatPal namespace must get
    rather than being guessed into one of the two we know about.
    """
    if source == "odds_api":
        return odds_api_anchor_key(source_id)
    if source == "espn":
        return espn_anchor_key(source_id)
    if source == "statpal":
        return statpal_anchor_key(source_id)
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
    # comparing raw strings. StatPal's `source_id` is namespace-qualified
    # (`s6:355372`) while the column holds the bare `355372`, so a raw compare
    # would read every live StatPal anchor as stale — and an unrecognised
    # namespace correctly yields `None` here, i.e. not current, which is the
    # same refusal `statpal_anchor_key` already makes on the write side.
    current_key = anchor_key_for_claim(key.source, current_value)
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
    """
    key = anchor_key_for_claim(source, source_id)
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
            text(
                "SELECT a.event_id, e.sport_id "
                "FROM event_provider_anchors a "
                "JOIN events e ON e.id = a.event_id "
                "WHERE a.source = :source AND a.source_id = :source_id "
                "AND a.id_kind = :id_kind "
                "LIMIT 1"
            ),
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


def _json_or_none(value: Optional[dict]) -> Optional[str]:
    if value is None:
        return None
    import json

    return json.dumps(value, default=str)
