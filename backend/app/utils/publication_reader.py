"""#4974 reader slice 1: the stored probability checkpoints of one event.

Pure. Turns the rows ``GET /api/events/{event_id}/publications`` read from
``probability_publications`` into the served body. Nothing here touches the
database, the clock or any other row.

What a vertex is, and what it is NOT
------------------------------------
One vertex is one stored ``(rev, recorded_at, blend_probability)`` row and
nothing more. ``t`` is ``recorded_at``: ``clock_timestamp()`` at INSERT, before
COMMIT (``app/utils/probability_publication.py`` point 4). It is a checkpoint,
not the moment the value became public, and the body says so in
``time_basis``.

No vertex says anything about its neighbours. ``rev`` counts bag commits only,
so a status-only or blend-input-only commit can move the published probability
between two rows without moving ``rev`` (root's ABA counterexample). Current
fields therefore cannot prove two recorded states were adjacent, and this
module computes no connector, hold, step, interval or contiguity. A row whose
``blend_probability`` is NULL (or not a finite number, which JSON cannot carry)
is omitted; its neighbours are served exactly as stored.

Order is ``rev`` (per-row commit order), never ``recorded_at``: insert stamps
are taken before commit and need not be monotonic in commit order.

Boundary: ``4974-UX-READER-SLICE-1-BOUNDARY.md`` section A.

#12108 PR 1 adds ``select_horizon_rows`` (pure, same rules: order is ``rev``)
and ``horizon_rows`` (its one database read), the recorded value calibration
grades at T-24h / T-6h / T-1h / the start.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

SCHEMA_VERSION = 1
TIME_BASIS = "recorded_at_insert_before_commit"

#: Rows served at most. One more is read so "more than this" is detectable;
#: past the cap the body serves no vertices rather than a silent prefix.
MAX_VERTICES = 5000
READ_LIMIT = MAX_VERTICES + 1


def _iso_utc(value: datetime) -> str:
    # `recorded_at` is timestamptz; a naive value can only come from a rig, and
    # the column's contract is UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _servable_probability(value: Any) -> Optional[float]:
    if value is None:
        return None
    probability = float(value)
    if not math.isfinite(probability):
        return None
    return probability


def checkpoint_vertices(rows: Iterable[Sequence[Any]]) -> list[dict]:
    """``(rev, recorded_at, blend_probability)`` rows → vertices, ordered by ``rev``.

    Rows without a servable probability are dropped; nothing is derived from a
    neighbour to replace them.
    """
    vertices = []
    for rev, recorded_at, blend_probability in sorted(rows, key=lambda row: int(row[0])):
        probability = _servable_probability(blend_probability)
        if probability is None:
            continue
        vertices.append({"rev": int(rev), "t": _iso_utc(recorded_at), "p": probability})
    return vertices


def publications_body(
    event_id: int,
    rows: Optional[Sequence[Sequence[Any]]],
    *,
    folded: bool,
) -> dict:
    """The whole 200 body.

    ``folded``: the served row has fold contributors. Their publications are a
    different row's journey and slice 1 joins nothing, so it serves no vertices
    (Live amendment 3). ``rows`` is ignored and may be ``None``.

    ``rows`` is the read capped at ``READ_LIMIT``; more than ``MAX_VERTICES``
    rows (counted before null omission) serves no vertices and
    ``truncated: true``.
    """
    truncated = False
    vertices: list[dict] = []
    if not folded:
        rows = list(rows or ())
        if len(rows) > MAX_VERTICES:
            truncated = True
        else:
            vertices = checkpoint_vertices(rows)
    return {
        "event_id": int(event_id),
        "schema_version": SCHEMA_VERSION,
        "time_basis": TIME_BASIS,
        "truncated": truncated,
        "vertices": vertices,
    }


# ── #12108 PR 1: the recorded value at each grading horizon ──────────────────

#: The horizons calibration grades the served blend at (plan §5 on #11850):
#: name → how long before the event's start.
HORIZONS: tuple[tuple[str, timedelta], ...] = (
    ("t_minus_24h", timedelta(hours=24)),
    ("t_minus_6h", timedelta(hours=6)),
    ("t_minus_1h", timedelta(hours=1)),
    ("start", timedelta(0)),
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def select_horizon_rows(
    rows: Iterable[Sequence[Any]], start: Optional[datetime]
) -> dict[str, Optional[dict]]:
    """Per horizon, the row in force at it: among rows with ``recorded_at`` at
    or before ``start - offset``, the one with the highest ``rev``.

    Pure. ``rows`` are ``(rev, recorded_at, blend_probability)``. Order is
    ``rev`` (commit order), never ``recorded_at`` (an insert stamp taken before
    commit, so two rows may share one). A horizon no row reaches is ``None`` —
    never a later row. No ``start`` → every horizon ``None``. A row's
    ``blend_probability`` is served as stored, NULL included (NULL is the
    recorded "no overall probability" state, not a missing row).
    """
    out: dict[str, Optional[dict]] = {name: None for name, _ in HORIZONS}
    if start is None:
        return out
    start = _aware(start)
    ordered = sorted(rows, key=lambda row: int(row[0]))
    for name, offset in HORIZONS:
        cutoff = start - offset
        best = None
        for rev, recorded_at, blend_probability in ordered:
            if _aware(recorded_at) <= cutoff:
                best = (rev, recorded_at, blend_probability)
        if best is not None:
            rev, recorded_at, blend_probability = best
            out[name] = {
                "rev": int(rev),
                "recorded_at": _iso_utc(recorded_at),
                "blend_probability": _servable_probability(blend_probability),
            }
    return out


async def horizon_rows(db: Any, event_id: int) -> Optional[dict]:
    """``{"event_id", "start", "horizons"}`` for one event, or ``None`` when the
    event does not exist. Two reads: the event's start, then its rows by
    ``(event_id, rev)`` — the unique index ``uq_probability_publications_event_rev``."""
    from sqlalchemy import select

    from app.models.models import Event, ProbabilityPublication

    start = (
        await db.execute(select(Event.commence_time).where(Event.id == event_id))
    ).scalar_one_or_none()
    exists = start is not None or (
        await db.execute(select(Event.id).where(Event.id == event_id))
    ).scalar_one_or_none() is not None
    if not exists:
        return None
    rows = (
        await db.execute(
            select(
                ProbabilityPublication.rev,
                ProbabilityPublication.recorded_at,
                ProbabilityPublication.blend_probability,
            )
            .where(ProbabilityPublication.event_id == event_id)
            .order_by(ProbabilityPublication.rev)
        )
    ).all()
    return {
        "event_id": int(event_id),
        "start": _iso_utc(start) if start is not None else None,
        "horizons": select_horizon_rows(rows, start),
    }
