"""#4974 reader slice 1: ``GET /api/events/{event_id}/publications``.

Read-only. Serves the event's stored probability checkpoints, one vertex per
``probability_publications`` row, so a finished game's chart can draw what was
actually recorded and nothing between. The body's meaning is
:mod:`app.utils.publication_reader`'s docstring; this module only decides which
row to read and reads it.

* **The served row.** Resolved exactly as ``/history`` resolves it
  (``resolve_served_event``, #6975), and only that ``event_id`` is read.
* **Folded rows serve nothing.** If the served row has fold contributors (the
  helpers ``event_stream._fold_stream_ids`` uses), their checkpoints belong to
  another row and slice 1 joins nothing: ``vertices: []``, no read.
* **Three columns.** ``rev, recorded_at, blend_probability``, ordered by
  ``rev``, capped at ``READ_LIMIT``. Never ``observations``, ``coverage``,
  ``queued_frame``, ``source_clocks`` or ``txn_started_at``.

No write, no flag, no migration. With recording off the table is empty and every
event serves ``vertices: []``, which the web reads as "draw today's chart".

Boundary: ``4974-UX-READER-SLICE-1-BOUNDARY.md`` section A.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event
from app.models.models import ProbabilityPublication
from app.routes.events import resolve_served_event
from app.services.database import get_db
from app.utils.proven_duplicates import folded_series_event_ids
from app.utils.publication_reader import READ_LIMIT, publications_body
from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

router = APIRouter()

CACHE_CONTROL = "public, max-age=60"


def publications_statement(event_id: int):
    """The one read: three columns of one event's rows, by ``rev``, capped."""
    return (
        select(
            ProbabilityPublication.rev,
            ProbabilityPublication.recorded_at,
            ProbabilityPublication.blend_probability,
        )
        .where(ProbabilityPublication.event_id == event_id)
        .order_by(ProbabilityPublication.rev)
        .limit(READ_LIMIT)
    )


@router.get("/{event_id}/publications")
async def get_event_publications(
    event_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Stored probability checkpoints for the event page's finished-game chart."""
    event = (
        await db.execute(
            select(Event).options(selectinload(Event.sport)).where(Event.id == event_id)
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    served = await resolve_served_event(db, event, requested_id=event_id)
    event = served.event
    event_id = served.event_id

    absorbed = await serve_fold_absorbed_rows(db, event)
    fold_ids = await folded_series_event_ids(db, event_id, absorbed)
    folded = len(fold_ids) > 1

    rows = None
    if not folded:
        rows = (await db.execute(publications_statement(event_id))).all()

    response.headers["Cache-Control"] = CACHE_CONTROL
    return publications_body(event_id, rows, folded=folded)
