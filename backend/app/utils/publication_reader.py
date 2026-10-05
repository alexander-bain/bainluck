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
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
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
