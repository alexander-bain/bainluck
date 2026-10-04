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
   ``RETURNING``.

   Writers this module does not see (a venue stamp, a raw update) still land
   in the recorded bag, which is exact. What ``coverage`` states is whether
   every change to it in this transaction has a recorded observation:

   * ``uncovered_writer_in_txn``: proven NOT covered. After the first tracked
     write, a key the next tracked write did not write moved (listed in
     ``uncovered_keys``), or the revision moved more than the tracked writes
     explain (``unobserved_bumps``). That catches a write between two tracked
     writes, a write after the last one, and a change later undone.
   * ``prior_txn_write_unestablished``: nothing after the first tracked write
     is unexplained, but the row had ALREADY been modified by this transaction
     before it (``prior_txn_row_write``: true, or null when the probe did not
     run). Whether that earlier write touched the bag cannot be seen from
     inside the transaction, so completeness is not claimed.
   * ``nonvenue_complete``: the probe proved the first tracked write started
     from the committed row, and every later revision is a tracked write.

   Each nonvenue write in the recording transaction, intermediate ones
   included, is kept in ``observations`` (but see clause 5 for no-op repeats). Those are what a producer OBSERVED and wrote, never a
   vertex anyone was shown.

   The row is inserted inside the writing transaction, before COMMIT. It commits
   with the price or not at all: an outer rollback never reaches
   ``before_commit``, and a rolled-back savepoint has already removed both its
   write and its observation (``nonvenue_live_push._after_rollback``).

2. **A null source value is a source REMOVAL, not a missing blend.** Removed
   sources are listed in ``removed_sources`` (removed in this transaction and
   still absent at commit); ``blend_probability`` / ``blend_tier`` say what the
   surviving siblings still produce, and ``blend_probability IS NULL`` is the
   only "no overall probability" state.

   ``queued_frame`` is the exact frame the existing hook hands to fanout if
   this commit succeeds, or null (a removal queues none). It is not a delivery
   receipt. The frame is computed from the last tracked write's RETURNING, the
   row from the committed bag. ``queued_frame_matches`` is true only when the
   frame carries this row's revision and blend. False means the frame QUEUED
   for fanout describes a different state than the one committed (for example,
   a raw write after the last tracked write). It does not prove any client
   received or showed that frame, and a reader must not treat the row as the
   queued frame's state.

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

5. **One row per published STATE.** ``(event_id, rev)`` is unique, and
   ``payload_sha256`` covers the published state only: bag, status, blend
   inputs, blend and method. The row's ``observations``, ``removed_sources``,
   coverage and frame fields belong to the transaction that FIRST recorded that
   state. A later no-op attempt at the same identity coalesces into it and
   inserts nothing; its own observations are not kept. Removing an absent
   source moves no revision, and neither attempt sends a frame. This is
   deliberate, not a divergence. When the published state itself differs under
   one identity (for example, a status change with no bag change), the first
   row is kept and an ERROR names both hashes.

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
COVERAGE_PRIOR_UNESTABLISHED = "prior_txn_write_unestablished"


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
    queued_frame: Optional[dict[str, Any]],
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

    def returned(observation):
        value = observation["returned_sources"]
        return value if isinstance(value, dict) else {}

    # Between two tracked writes, a key the second did not write must not move,
    # and the revision may move by at most one, and only if its bag changed.
    # After the last tracked write, nothing may move at all.
    uncovered: set[str] = set()
    unobserved_bumps = 0
    for before, after in zip(observations, observations[1:]):
        prev, cur = returned(before), returned(after)
        own = {after["source"], *after.get("metadata_keys", ())}
        uncovered |= {
            key
            for key in set(prev) | set(cur)
            if key not in own and prev.get(key) != cur.get(key)
        }
        expected = 1 if cur != prev else 0
        unobserved_bumps += max(0, after["rev"] - before["rev"] - expected)
    last = returned(observations[-1])
    uncovered |= {key for key in set(bag) | set(last) if bag.get(key) != last.get(key)}
    unobserved_bumps += max(0, int(rev) - observations[-1]["rev"])
    uncovered = sorted(uncovered)
    prior = observations[0].get("prior_txn_row_write")
    if uncovered or unobserved_bumps:
        coverage = COVERAGE_UNCOVERED
    elif prior is False:
        coverage = COVERAGE_COMPLETE
    else:
        coverage = COVERAGE_PRIOR_UNESTABLISHED
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
            "metadata_keys": o.get("metadata_keys", []),
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
        "coverage": coverage,
        "uncovered_keys": uncovered,
        "unobserved_bumps": unobserved_bumps,
        "prior_txn_row_write": prior,
        "queued_frame": queued_frame,
        "queued_frame_matches": (
            None
            if queued_frame is None
            else queued_frame.get("rev") == {str(int(event_id)): int(rev)}
            and queued_frame.get("p") == probability
        ),
        "payload_sha256": payload_sha256,
    }


def record_committing_publications(
    session, entries: Iterable[tuple[int, dict[str, Any], Optional[dict[str, Any]]]]
) -> dict[str, int]:
    """Insert one publication per event, inside the transaction about to commit.

    Runs in the sync ``before_commit`` hook. ``entries`` is
    ``(event_id, observation, queued_frame)`` in write order, holding
    only writes whose transaction or savepoint is still alive. Returns counts
    for tests and logs. Never raises: a failure rolls back only its SAVEPOINT.
    """
    from app.models.models import Event, ProbabilityPublication

    by_event: dict[int, list[dict[str, Any]]] = {}
    frames: dict[int, Optional[dict[str, Any]]] = {}
    for event_id, observation, frame in entries:
        by_event.setdefault(int(event_id), []).append(observation)
        frames[int(event_id)] = frame
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
                        queued_frame=frames[event_id],
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
