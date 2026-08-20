"""One place that decides whether an ``espn_id`` may be written onto a row (#2017).

## The defect this exists to delete

``app/tasks/sports.py`` had this, immediately after ``find_or_create_event``::

    # Set ESPN ID if matched and not already set
    if espn_event_id and not event.espn_id:
        event.espn_id = espn_event_id

A raw column assignment that bypasses the registry entirely. It asks one
question — *does THIS row have an espn_id?* — and never the one that matters:
**does another row already hold this one?** ``ix_events_espn_id`` is a plain
btree and not UNIQUE, so the database accepts the contradiction silently.

Measured live 2026-08-20: the Odds API issues a NEW event id for a fixture we
already hold (``event_registry.py`` acknowledges this in ``_attach_claim`` and
merely logs it), so step 1 misses, ruling 048 refuses the structured absorb, and
``find_or_create_event`` CREATEs. The stamp then runs in the SAME transaction and
writes the keeper's ``espn_id`` onto the fresh row. The duplicate is BORN
carrying the collision. Example: keeper ``14947545`` (Marseille/Strasbourg,
``espn_id=401876489``) and new row ``15249444`` — same clubs, same ``espn_id``,
different ``external_id``.

## Why refusing is unconditionally correct, independent of ruling 048

Ruling 042 — *dereference the id, never the label*. The id being written here was
not dereferenced: it was picked by matching TEAM NAMES against a scoreboard
listing. Writing a provider id derived from a label, onto a row whose current
holder was never checked, fabricates an identity claim. The refusal is not an
identity decision; it is a refusal to invent one.

## Why the id is NOT used as a lookup key

The obvious-looking fix — let the ESPN id participate in the registry lookup so
the claim resolves onto the keeper instead of creating — is UNSAFE today, and
``app/utils/event_merge_invariant.py`` has the measurement: of the 13 pairs
sharing an ``espn_id`` in a 60-day window, at least three are genuinely
DIFFERENT GAMES (``401816142`` Dodgers @ Yankees / Dodgers @ Mets;
``401882919``; ``401856667``). ``espn_id`` is not trustworthy identity while
this very defect is still minting bad ones by name-match, so promoting it to a
lookup key would let a wrong id silently resolve a claim onto a different real
game — strictly worse than the duplicate it would prevent.

So: **the stamp refuses, and nothing else changes.** Whether the duplicate
should have been created at all is the separate ruling-048 question.

This is the ``espn_id`` analogue of ``sports.py``'s existing
``_external_id_in_use`` — the same "is another row already holding this?" check
the ``external_id`` column has had all along, for the one provider id column
that never got it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select

from app.models import Event

logger = logging.getLogger(__name__)

#: The id was written onto the row.
STAMPED = "stamped"
#: Nothing to do — no incoming id, or the row already carries one.
SKIPPED = "skipped"
#: Another row already holds this id. Refused; the row keeps its NULL.
REFUSED = "refused"


async def espn_id_holder(
    session,
    espn_id: str,
    *,
    exclude_event_id: Optional[int] = None,
) -> Optional[int]:
    """Return the id of an event already holding ``espn_id``, or None.

    ``exclude_event_id`` is dropped from the predicate when it is None (an
    unflushed row has no id yet, and ``id <> NULL`` is NULL — which would match
    nothing and turn this check into a rubber stamp).
    """
    if not espn_id:
        return None

    stmt = select(Event.id).where(Event.espn_id == espn_id)
    if exclude_event_id is not None:
        stmt = stmt.where(Event.id != exclude_event_id)

    result = await session.execute(stmt.limit(1))
    # ``.scalars().all()`` rather than ``.first()``/``.scalar_one_or_none()``:
    # the query is already LIMIT 1, and this is the one result-API shape every
    # async session double in the suite already implements.
    rows = result.scalars().all()
    return rows[0] if rows else None


async def stamp_espn_id_if_unheld(
    session,
    event: Any,
    espn_id: Optional[str],
    *,
    context: str,
    claimed: Optional[set] = None,
) -> tuple[str, Optional[int]]:
    """Write ``espn_id`` onto ``event`` only if no OTHER row already holds it.

    Returns ``(verdict, holder_id)`` where verdict is :data:`STAMPED`,
    :data:`SKIPPED` or :data:`REFUSED`. Callers are expected to COUNT the
    refusals — a guard whose refusals are invisible reads exactly like a guard
    that never fired.

    ``claimed`` is an optional caller-maintained set of ids already spoken for in
    this pass. The database check alone is nearly sufficient (SQLAlchemy
    autoflushes pending assignments before the SELECT), but "nearly" is the word
    that makes a guard accidental — the set makes the in-pass case explicit and
    survives autoflush being turned off. Stamped ids are added to it.
    """
    if not espn_id or event.espn_id:
        return (SKIPPED, None)

    if claimed is not None and espn_id in claimed:
        logger.warning(
            "%s: REFUSED espn_id=%s on event %s — already claimed earlier in "
            "this pass. Not stamping; the row keeps a NULL espn_id rather than "
            "a contradicted one (#2017).",
            context, espn_id, getattr(event, "id", None),
        )
        return (REFUSED, None)

    holder_id = await espn_id_holder(
        session, espn_id, exclude_event_id=getattr(event, "id", None)
    )
    if holder_id is not None:
        logger.warning(
            "%s: REFUSED espn_id=%s on event %s — event %s already holds it. "
            "The id was derived from a NAME match, not a dereference (ruling "
            "042), so writing it would fabricate an identity claim and leave "
            "two rows contradicting each other (#2017).",
            context, espn_id, getattr(event, "id", None), holder_id,
        )
        return (REFUSED, holder_id)

    event.espn_id = espn_id
    if claimed is not None:
        claimed.add(espn_id)
    return (STAMPED, holder_id)
