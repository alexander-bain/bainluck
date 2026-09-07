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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.event_completion import TICKER_DERIVED_COMMENCE_SOURCE
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
    statpal_sport_from_source_id,
)
from app.utils.sport_keys import get_llm_category_for_prefix

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
        if warn_unqualified and sport_key is None and source_id:
            # WARNING and not DEBUG on purpose, and the reason changed with step
            # 3. While the digit fallback existed this was a COUNTDOWN — it
            # marked a call that still got an answer, by the wrong rule. Now it
            # marks a claim that got NO anchor at all, which is a hole in the
            # channel rather than a deprecation notice, so it must not get
            # quieter as it becomes more serious. D55's second clause is that a
            # key we cannot form raises or tags; this is the tag.
            logger.warning(
                "D55/#2879: StatPal anchor claim REFUSED — no sport_key for "
                "fixture id=%s, so no anchor was written or matched. The "
                "digit-derived fallback was deleted at step 3; the caller must "
                "pass sport_key.",
                source_id,
            )
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
MARKET_BORN_COMMENCE_SOURCES = frozenset(
    {SOURCE_KALSHI, SOURCE_POLYMARKET, TICKER_DERIVED_COMMENCE_SOURCE}
)

#: One statement, one round trip: every fact the drain verdict turns on.
#:
#: `mkt` resolves each of this event's MARKET anchors back through the market it
#: names — `(source, external_id)` is `uq_futures_source_external`, a UNIQUE
#: index, so each anchor yields at most one row and the LEFT JOIN cannot fan out.
_DRAIN_VERDICT_SQL = """
WITH anch AS (
    SELECT source, source_id, id_kind
      FROM event_provider_anchors
     WHERE event_id = :event_id
),
mkt AS (
    SELECT fm.event_id AS target
      FROM anch
      LEFT JOIN futures_markets fm
             ON fm.source = anch.source
            AND fm.external_id = anch.source_id
     WHERE anch.id_kind = :market_kind
)
SELECT
    e.commence_time_source AS provenance,
    s.key AS sport_key,
    (e.home_score IS NOT NULL OR e.away_score IS NOT NULL
     OR e.completed_at IS NOT NULL) AS carries_truth,
    (SELECT count(*) FROM anch WHERE id_kind = :game_kind) AS game_anchors,
    (SELECT count(*) FROM mkt) AS market_anchors,
    (SELECT count(*) FROM mkt WHERE target IS NULL) AS unresolved,
    (SELECT count(DISTINCT target) FROM mkt
      WHERE target IS NOT NULL AND target <> e.id) AS other_targets,
    (SELECT min(target) FROM mkt
      WHERE target IS NOT NULL AND target <> e.id) AS candidate_id,
    EXISTS (SELECT 1 FROM futures_markets WHERE event_id = e.id) AS holds_markets
  FROM events e
  LEFT JOIN sports s ON s.id = e.sport_id
 WHERE e.id = :event_id
"""

_CANONICAL_SPORT_SQL = (
    "SELECT s.key FROM events e LEFT JOIN sports s ON s.id = e.sport_id "
    "WHERE e.id = :event_id"
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
    6. **Same sport family** (:func:`_sport_family`). 505 of 505 today, so it
       costs nothing and refuses the one outcome that would be unrecoverable.

    Only `market` anchors are read. A `game` anchor is counted (refusal 1) and a
    `container` anchor — a Polymarket event id — is IGNORED rather than treated
    as an unresolvable market, which would refuse every Polymarket-born ghost
    the day containers start being written. The table holds none today; the
    key module already produces them.

    Returns the canonical event id, or ``None`` for every refusal. ``None`` is
    the answer on any error as well: this decorates a read, and a read that
    cannot decide must serve the row it was asked for.
    """
    try:
        row = (
            await session.execute(
                text(_DRAIN_VERDICT_SQL),
                {
                    "event_id": int(event_id),
                    "market_kind": ANCHOR_KIND_MARKET,
                    "game_kind": ANCHOR_KIND_GAME,
                },
            )
        ).first()
    except Exception:  # pragma: no cover - defensive, see docstring
        logger.exception(
            "Drain verdict query failed for event %s — serving the row as asked",
            event_id,
        )
        return None

    if row is None:
        return None

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
        return None

    canonical = (
        await session.execute(
            text(_CANONICAL_SPORT_SQL), {"event_id": int(candidate)}
        )
    ).first()
    if canonical is None:
        return None

    ghost_family = _sport_family(verdict["sport_key"])
    canonical_family = _sport_family(canonical[0])
    if ghost_family is None or ghost_family != canonical_family:
        logger.warning(
            "Refusing to resolve event %s to %s: sport families %r vs %r "
            "(Q050) — a cross-sport read is the one outcome worth refusing",
            event_id, candidate, ghost_family, canonical_family,
        )
        return None

    logger.info(
        "Event %s is a market-born duplicate of %s — reading as the canonical "
        "row (Q050, ruling 048 drain clause)",
        event_id, candidate,
    )
    return int(candidate)
