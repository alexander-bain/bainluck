"""Recompute `futures_markets.market_type` (display shape) + the semantics v2
contract in `market_metadata['shape']` (Queue #194 Item 1 → Queue #260).

The #193 census established that shape is not stored anywhere (`market_type` and
`group_type` are 100% NULL across ~456K rows). Queue #194 assigned a display
shape to every row. Queue #260 (the C16 P1 trio) makes classification:

  * **recomputable, not frozen** — the old task only touched `market_type IS
    NULL`, so first-sight classification became permanent truth. Late siblings,
    late event links, and repaired outcome sets never re-classified. This task
    now rolls over ALL rows (bounded/resumable) and recomputes when the row is
    unclassified, classifier-version-old, or its input fingerprint changed. It
    writes only on change (idempotent).
  * **explicit about semantics** — it persists the full v2 contract from
    `app.utils.market_shape.classify_market_semantics`:

      market_type            → the DISPLAY shape (claim/quantity/duel/field/
                               participation/container_member/unshaped)
      market_metadata.shape  → {shape, side_kind, outcome_count, v,
                               classifier_version, input_fingerprint,
                               outcome_relation, exhaustive, expected_winners,
                               push_void_capable, confidence, evidence,
                               container_group?}

Bounded + resumable + deadline-guarded (the #1100 pattern): a wall-clock budget
under the soft time limit, a persisted id cursor that wraps to 0 when a full
pass completes (so drift on already-classified rows is caught on the next
sweep), and per-batch commit. Because writes are change-gated, a converged table
costs reads only.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict

from sqlalchemy import text

from app.tasks.base import get_task_session
from app.tasks.redis_state import get_redis_client
from app.utils.market_shape import CLASSIFIER_VERSION, classify_market_semantics

logger = logging.getLogger(__name__)

_CURSOR_KEY = "bainluck:market_shape_backfill_cursor"
_CURSOR_TTL = 86400 * 14


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _source_kind(source, external_id, meta: dict) -> str | None:
    """Structured source market-kind hint. Prefer explicit metadata; fall back to
    the DataGolf external-id suffix (``datagolf:pga:x:top_5`` → ``top_5``)."""
    for key in ("source_market_kind", "market_kind", "datagolf_market_type"):
        v = meta.get(key)
        if v:
            return str(v)
    if source == "datagolf" and external_id and ":" in str(external_id):
        return str(external_id).rsplit(":", 1)[-1]
    return None


async def _backfill_market_shapes(
    limit: int = 40000,
    batch_size: int = 2000,
    deadline_s: float = 500.0,
    dry_run: bool = False,
) -> dict:
    """Recompute + persist the semantics v2 contract for up to ``limit`` markets.

    Returns stats: scanned, updated, by_shape counts, by_relation counts,
    transitions (old_shape->new_shape), cursor, stopped_at, elapsed_s, wrapped.
    """
    start = time.monotonic()
    rc = get_redis_client()
    raw = rc.get(_CURSOR_KEY)
    try:
        cursor = int(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        cursor = 0

    stats: dict = {
        "scanned": 0,
        "updated": 0,
        "by_shape": defaultdict(int),
        "by_relation": defaultdict(int),
        "transitions": defaultdict(int),
        "cursor_start": cursor,
        "stopped_at": None,
        "wrapped": False,
        "dry_run": dry_run,
        "classifier_version": CLASSIFIER_VERSION,
    }
    by_shape: Counter = Counter()
    by_relation: Counter = Counter()
    transitions: Counter = Counter()

    while stats["scanned"] < limit:
        if time.monotonic() - start > deadline_s:
            stats["stopped_at"] = "deadline"
            break

        async with get_task_session() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, source, external_id, event_id, group_id,
                               group_type, mutually_exclusive, market_type,
                               market_metadata
                        FROM futures_markets
                        WHERE id > :cursor
                        ORDER BY id ASC
                        LIMIT :batch
                        """
                    ),
                    {"cursor": cursor, "batch": batch_size},
                )
            ).all()

            if not rows:
                # Full pass complete — wrap the cursor so the next run re-scans
                # from the start and catches drift + freshly-ingested rows.
                if cursor != 0:
                    rc.delete(_CURSOR_KEY)
                    stats["wrapped"] = True
                    stats["stopped_at"] = stats["stopped_at"] or "wrapped"
                else:
                    stats["stopped_at"] = stats["stopped_at"] or "empty"
                break

            market_ids = [r[0] for r in rows]

            # Outcome names for the whole batch in one query.
            oc_rows = (
                await session.execute(
                    text(
                        """
                        SELECT market_id, name
                        FROM futures_outcomes
                        WHERE market_id = ANY(:ids)
                        """
                    ),
                    {"ids": market_ids},
                )
            ).all()
            names_by_market: dict[int, list[str]] = defaultdict(list)
            for mid, nm in oc_rows:
                names_by_market[mid].append(nm)

            # Group sizes for the batch's non-null group_ids in one query.
            group_ids = sorted({r[4] for r in rows if r[4]})
            group_sizes: dict[str, int] = {}
            if group_ids:
                gs_rows = (
                    await session.execute(
                        text(
                            """
                            SELECT group_id, COUNT(*)
                            FROM futures_markets
                            WHERE group_id = ANY(:gids)
                            GROUP BY group_id
                            """
                        ),
                        {"gids": group_ids},
                    )
                ).all()
                group_sizes = {g: n for g, n in gs_rows}

            for (
                mid,
                source,
                external_id,
                event_id,
                group_id,
                group_type,
                mutually_exclusive,
                old_market_type,
                market_metadata,
            ) in rows:
                meta = _as_dict(market_metadata)
                stored_shape = _as_dict(meta.get("shape"))
                names = names_by_market.get(mid, [])

                result = classify_market_semantics(
                    outcome_names=names,
                    external_id=external_id,
                    event_id=event_id,
                    group_id=group_id,
                    group_size=group_sizes.get(group_id, 1),
                    source=source,
                    source_kind=_source_kind(source, external_id, meta),
                    expected_winners=meta.get("expected_winners"),
                    mutually_exclusive=mutually_exclusive,
                    push_possible=meta.get("push_possible"),
                    conditional=bool(meta.get("conditional", False)),
                    parent_condition_id=meta.get("parent_condition_id"),
                    group_type=group_type,
                )
                new_shape = result["display_shape"]

                by_shape[new_shape] += 1
                by_relation[result["outcome_relation"]] += 1

                stored_v = stored_shape.get("classifier_version", stored_shape.get("v"))
                stored_fp = stored_shape.get("input_fingerprint")
                changed = (
                    old_market_type != new_shape
                    or stored_v != CLASSIFIER_VERSION
                    or stored_fp != result["input_fingerprint"]
                )
                if not changed:
                    continue

                transitions[f"{old_market_type or 'null'}->{new_shape}"] += 1
                if dry_run:
                    continue

                shape_blob = {
                    "shape": new_shape,
                    "side_kind": result["side_kind"],
                    "outcome_count": result["outcome_count"],
                    "v": CLASSIFIER_VERSION,
                    "classifier_version": result["classifier_version"],
                    "input_fingerprint": result["input_fingerprint"],
                    "outcome_relation": result["outcome_relation"],
                    "exhaustive": result["exhaustive"],
                    "expected_winners": result["expected_winners"],
                    "push_void_capable": result["push_void_capable"],
                    "confidence": result["confidence"],
                    "evidence": result["evidence"],
                }
                # field↔container link: a container_member records the group_id
                # of the field question it belongs to.
                if new_shape == "container_member" and group_id:
                    shape_blob["container_group"] = group_id

                await session.execute(
                    text(
                        """
                        UPDATE futures_markets
                        SET market_type = :shape,
                            market_metadata = (
                                CASE
                                    WHEN jsonb_typeof(market_metadata) = 'object'
                                        THEN market_metadata
                                    ELSE '{}'::jsonb
                                END
                            ) || jsonb_build_object('shape', CAST(:meta AS jsonb))
                        WHERE id = :id
                        """
                    ),
                    {"shape": new_shape, "meta": json.dumps(shape_blob), "id": mid},
                )
                stats["updated"] += 1

            if not dry_run:
                await session.commit()

            stats["scanned"] += len(rows)
            cursor = market_ids[-1]
            if not dry_run:
                rc.setex(_CURSOR_KEY, _CURSOR_TTL, cursor)

    stats["by_shape"] = dict(by_shape)
    stats["by_relation"] = dict(by_relation)
    stats["transitions"] = dict(transitions)
    stats["cursor"] = cursor
    stats["elapsed_s"] = round(time.monotonic() - start, 1)
    if stats["stopped_at"] is None:
        stats["stopped_at"] = "limit"
    logger.info(
        "market_shape recompute: scanned=%d updated=%d by_shape=%s by_relation=%s "
        "stopped=%s elapsed=%ss",
        stats["scanned"],
        stats["updated"],
        stats["by_shape"],
        stats["by_relation"],
        stats["stopped_at"],
        stats["elapsed_s"],
    )
    return stats
