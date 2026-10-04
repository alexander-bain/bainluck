"""#4971 — record what a nonvenue writer actually PUBLISHED, in its own transaction.

## the ship

Chart history and the published live probability tell the same recorded story:
from the moment recording starts, each committed state of an event's source
bag that a nonvenue writer (betting / stat_model / mlb / espn, the writers that
go through ``nonvenue_live_push.write_nonvenue_probability``) committed is kept
as a row, with the exact bag, the exact blend computed from it, and the
producer evidence behind each write. Nothing is reconstructed later from a
mutable book population or a ``valid_until`` window.

## the contract, clause by clause

1. **One publication per event per committed transaction, and it is the FINAL
   committed bag.** ``_after_commit`` coalesces an event's frames to the last
   one, so an ESPN write followed by a stat_model write in the same transaction
   only ever exposed the second state. The row is therefore built at
   ``before_commit`` from the row as the transaction will commit it (after a
   flush, re-read inside the transaction), not from any one writer's
   ``RETURNING``. A writer this module does not see (a venue stamp, a raw
   update) that changes the bag later in the same transaction is in the
   recorded bag, and its keys are listed in ``uncovered_keys`` with
   ``coverage = 'uncovered_writer_in_txn'``: the bag is exact, but the
   evidence covers only the nonvenue writes.

   Each nonvenue write in the transaction, intermediate ones included, is kept
   in ``observations``. Those are what a producer OBSERVED and wrote, never a
   vertex anyone was shown.

   The row is inserted inside the writing transaction, before COMMIT. It commits
   with the price or not at all: an outer rollback never reaches
   ``before_commit``, and a rolled-back savepoint has already removed both its
   write and its observation (``nonvenue_live_push._after_rollback``).

2. **A null source value is a source REMOVAL, not a missing blend.** Removed
   sources are listed in ``removed_sources`` (removed in this transaction and
   still absent at commit); ``blend_probability`` / ``blend_tier`` say what the
   surviving siblings still produce, and ``blend_probability IS NULL`` is the
   only "no overall probability" state. ``stream_frame_eligible`` says whether
   the existing hook queued a live frame for this commit. It is NOT a delivery
   receipt, and it is false for a removal.

3. **The evidence is the producer's own.** ``sources`` is the committed bag
   verbatim (JSONB, full precision). Each observation carries the writer's
   ``evidence`` (for betting: every book's home probability, the median, the
   floor and the split decision as ``_ingest_event_odds`` computed them).
   ``blend_probability`` is ``compute_aggregate_probability_tiered`` over the
   committed bag and the two non-bag inputs it reads, named in ``blend_method``,
   so the method is the frame's method. No weighting, expiry or median policy
   is introduced or changed here.

4. **Three clocks, never conflated.** ``source_clocks`` holds each source's
   stamped ``updated_at``: when the writer stamped the reading, not when a
   device received it and not commit time. ``txn_started_at`` is
   ``now()`` (transaction start) and ``recorded_at`` is ``clock_timestamp()``
   at insert, which is before COMMIT. **Commit time is not recorded**; it is not
   available inside the transaction. Order is ``rev``: the database's per-row
   ``win_probability_sources_rev``, which follows commit order for the row
   (#9051), and the row exists only if the transaction committed. Nothing here
   supports a latency or age SLA.

5. **Same identity, same payload, or a loud diagnostic.** ``(event_id, rev)`` is
   unique. A second transaction that commits the same bag at the same rev (a
   removal of an absent source moves no rev) inserts nothing when its payload
   hash matches. When the hash differs, for example a status change with no bag
   change, the existing row is kept and an ERROR names both hashes.

6. **Coverage is explicit.** Venue writers do not go through this path, so a
   jump of more than one between an event's consecutive ``rev`` values,
   counting the transaction's own writes in ``observations``, is a commit this
   table did not see. The first row of an event is where its recording starts;
   it says nothing about history before it, and legacy points stay where they
   are. This table is not the complete blend history and must not be called
   one.

## rollout

Dark behind ``PROBABILITY_PUBLICATION_RECORDING`` (OFF unless ``true``). With
it off, nothing here runs. With it on, a failure to record (a missing table, for
instance) is contained in a SAVEPOINT and logged at ERROR. The price write
commits anyway, and the event simply has no row for that commit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

RECORDING_FLAG = "PROBABILITY_PUBLICATION_RECORDING"
SCHEMA_VERSION = 1
BLEND_METHOD = "aggregation.compute_aggregate_probability_tiered/v1"
COVERAGE_COMPLETE = "nonvenue_complete"
COVERAGE_UNCOVERED = "uncovered_writer_in_txn"


def recording_enabled() -> bool:
    """Read at call time; OFF unless the env var is exactly ``true``."""
    return os.getenv(RECORDING_FLAG, "false").strip().lower() == "true"


def _number(value: Any) -> Optional[float]:
    # Numeric columns arrive as Decimal; JSON and the hash take floats.
    return None if value is None else float(value)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_publication(
    *,
    event_id: int,
    sources: Any,
    rev: int,
    status: Optional[str],
    espn_win_prob_home: Any,
    opening_home_probability: Any,
    observations: list[dict[str, Any]],
    stream_frame_eligible: bool,
) -> dict[str, Any]:
    """The row for one committed event bag. Pure: no session, no clock."""
    from app.utils.aggregation import (
        SOURCE_WEIGHTS,
        compute_aggregate_probability_tiered,
    )

    if not observations:
        raise ValueError("a publication needs the nonvenue write it records")
    bag = sources if isinstance(sources, dict) else {}
    inputs = {
        "espn_win_prob_home": _number(espn_win_prob_home),
        "opening_home_probability": _number(opening_home_probability),
    }
    probability, tier = compute_aggregate_probability_tiered(
        SimpleNamespace(win_probability_sources=bag, status=status, **inputs),
        status,
    )
    probability = _number(probability)

    last = observations[-1]["returned_sources"]
    last = last if isinstance(last, dict) else {}
    uncovered = sorted(
        key for key in set(bag) | set(last) if bag.get(key) != last.get(key)
    )
    removed = sorted(
        {o["source"] for o in observations if o["removed"]} - set(bag)
    )
    clocks = {
        key: (value.get("updated_at") if isinstance(value, dict) else None)
        for key, value in bag.items()
        if key in SOURCE_WEIGHTS
    }
    recorded_observations = [
        {
            "source": o["source"],
            "value": o["value"],
            "removed": o["removed"],
            "rev": o["rev"],
            "stamped_at": o["stamped_at"],
            "evidence": o.get("evidence"),
        }
        for o in observations
    ]
    payload_sha256 = hashlib.sha256(
        _canonical(
            {
                "event_id": int(event_id),
                "rev": int(rev),
                "sources": bag,
                "status": status,
                "inputs": inputs,
                "blend": probability,
                "tier": tier,
                "method": BLEND_METHOD,
            }
        ).encode()
    ).hexdigest()
    return {
        "event_id": int(event_id),
        "rev": int(rev),
        "schema_version": SCHEMA_VERSION,
        "sources": bag,
        "event_status": status,
        "blend_inputs": inputs,
        "blend_probability": probability,
        "blend_tier": tier,
        "blend_method": BLEND_METHOD,
        "source_clocks": clocks,
        "removed_sources": removed,
        "observations": recorded_observations,
        "coverage": COVERAGE_UNCOVERED if uncovered else COVERAGE_COMPLETE,
        "uncovered_keys": uncovered,
        "stream_frame_eligible": bool(stream_frame_eligible),
        "payload_sha256": payload_sha256,
    }


def record_committing_publications(
    session, entries: Iterable[tuple[int, dict[str, Any], bool]]
) -> dict[str, int]:
    """Insert one publication per event, inside the transaction about to commit.

    Runs in the sync ``before_commit`` hook. ``entries`` is
    ``(event_id, observation, frame_would_be_sent)`` in write order, holding
    only writes whose transaction or savepoint is still alive. Returns counts
    for tests and logs. Never raises: a failure rolls back only its SAVEPOINT.
    """
    from app.models.models import Event, ProbabilityPublication

    by_event: dict[int, list[dict[str, Any]]] = {}
    eligible: dict[int, bool] = {}
    for event_id, observation, would_send in entries:
        by_event.setdefault(int(event_id), []).append(observation)
        eligible[int(event_id)] = bool(would_send)
    counts = {"inserted": 0, "idempotent": 0, "divergent": 0, "missing_row": 0}
    if not by_event:
        return counts

    # The ORM's own pending changes flush AFTER before_commit; flush now so the
    # re-read below sees the bag exactly as COMMIT will store it.
    session.flush()
    connection = session.connection()
    table = ProbabilityPublication.__table__
    try:
        with connection.begin_nested():
            rows = connection.execute(
                select(
                    Event.id,
                    Event.win_probability_sources,
                    Event.win_probability_sources_rev,
                    Event.status,
                    Event.espn_win_prob_home,
                    Event.opening_home_probability,
                ).where(Event.id.in_(list(by_event)))
            ).all()
            found = {row[0]: row for row in rows}
            publications = []
            for event_id, observations in by_event.items():
                row = found.get(event_id)
                if row is None:
                    counts["missing_row"] += 1
                    logger.error(
                        "probability publication: event %s vanished before "
                        "commit; nothing recorded",
                        event_id,
                    )
                    continue
                _, bag, rev, status, espn, opening = row
                publications.append(
                    build_publication(
                        event_id=event_id,
                        sources=bag,
                        rev=rev,
                        status=status,
                        espn_win_prob_home=espn,
                        opening_home_probability=opening,
                        observations=observations,
                        stream_frame_eligible=eligible[event_id],
                    )
                )
            if not publications:
                return counts
            stamped = [
                {
                    **p,
                    "txn_started_at": func.now(),
                    "recorded_at": func.clock_timestamp(),
                }
                for p in publications
            ]
            inserted = {
                (r[0], r[1])
                for r in connection.execute(
                    pg_insert(table)
                    .values(stamped)
                    .on_conflict_do_nothing(index_elements=["event_id", "rev"])
                    .returning(table.c.event_id, table.c.rev)
                )
            }
            counts["inserted"] = len(inserted)
            for p in publications:
                if (p["event_id"], p["rev"]) in inserted:
                    continue
                existing = connection.execute(
                    select(table.c.payload_sha256).where(
                        table.c.event_id == p["event_id"], table.c.rev == p["rev"]
                    )
                ).scalar_one_or_none()
                if existing == p["payload_sha256"]:
                    counts["idempotent"] += 1
                    continue
                counts["divergent"] += 1
                logger.error(
                    "probability publication DIVERGENT under one identity: "
                    "event=%s rev=%s kept=%s refused=%s coverage=%s — the "
                    "blend changed without the bag revision moving (a non-bag "
                    "blend input changed, or the revision trigger is absent); "
                    "the existing row is kept",
                    p["event_id"],
                    p["rev"],
                    existing,
                    p["payload_sha256"],
                    p["coverage"],
                )
    except Exception:
        logger.error(
            "probability publication NOT recorded for events %s; the price "
            "write commits without it",
            sorted(by_event),
            exc_info=True,
        )
        counts["inserted"] = 0
        counts["failed"] = len(by_event)
    return counts
