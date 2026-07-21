"""Backfill `futures_markets.market_type` as the market *shape* (Queue #194 Item 1).

The #193 census established that shape is not stored anywhere (`market_type` and
`group_type` are 100% NULL across ~456K rows). This task assigns shape to every
row using the single classifier in `app.utils.market_shape`, writing:

  * ``market_type``            → the shape enum (claim/quantity/duel/field/
                                 container_member/unshaped)
  * ``market_metadata.shape``  → ``{shape, side_kind, container_group, outcome_count, v}``

It doubles as the "classify at ingest" mechanism: it runs frequently on a beat
and only touches rows whose ``market_type IS NULL``, so newly-ingested markets
get shaped within one beat interval without threading the classifier through the
three hot ingest loops (kalshi/polymarket/datagolf).

Bounded + resumable + deadline-guarded (the #1100 pattern): a wall-clock budget
under the soft time limit, a persisted id cursor that wraps to 0 when a pass
completes (so the next run re-scans for freshly-null rows), and per-batch commit.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict

from sqlalchemy import text

from app.tasks.base import get_task_session
from app.tasks.redis_state import get_redis_client
from app.utils.market_shape import classify_market_shape

logger = logging.getLogger(__name__)

_CURSOR_KEY = "bainluck:market_shape_backfill_cursor"
_CURSOR_TTL = 86400 * 14


async def _backfill_market_shapes(
    limit: int = 40000,
    batch_size: int = 2000,
    deadline_s: float = 500.0,
    dry_run: bool = False,
) -> dict:
    """Classify + persist shape for up to ``limit`` unshaped markets.

    Returns stats: scanned, updated, by_shape counts, cursor, stopped_at,
    elapsed_s, wrapped.
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
        "cursor_start": cursor,
        "stopped_at": None,
        "wrapped": False,
        "dry_run": dry_run,
    }
    by_shape: Counter = Counter()

    while stats["scanned"] < limit:
        if time.monotonic() - start > deadline_s:
            stats["stopped_at"] = "deadline"
            break

        async with get_task_session() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, external_id, event_id, group_id
                        FROM futures_markets
                        WHERE market_type IS NULL AND id > :cursor
                        ORDER BY id ASC
                        LIMIT :batch
                        """
                    ),
                    {"cursor": cursor, "batch": batch_size},
                )
            ).all()

            if not rows:
                # Pass complete — wrap the cursor so the next run re-scans from
                # the start and picks up freshly-ingested (null) rows.
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
            group_ids = sorted({r[3] for r in rows if r[3]})
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

            for mid, external_id, event_id, group_id in rows:
                shape, side_kind = classify_market_shape(
                    outcome_names=names_by_market.get(mid, []),
                    external_id=external_id,
                    event_id=event_id,
                    group_id=group_id,
                    group_size=group_sizes.get(group_id, 1),
                )
                by_shape[shape] += 1
                if dry_run:
                    continue

                meta = {
                    "shape": shape,
                    "side_kind": side_kind,
                    "outcome_count": len(names_by_market.get(mid, [])),
                    "v": 1,
                }
                # field↔container link: a container_member records the group_id
                # of the field question it belongs to.
                if shape == "container_member" and group_id:
                    meta["container_group"] = group_id

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
                    {"shape": shape, "meta": json.dumps(meta), "id": mid},
                )
                stats["updated"] += 1

            if not dry_run:
                await session.commit()

            stats["scanned"] += len(rows)
            cursor = market_ids[-1]
            if not dry_run:
                rc.setex(_CURSOR_KEY, _CURSOR_TTL, cursor)

    stats["by_shape"] = dict(by_shape)
    stats["cursor"] = cursor
    stats["elapsed_s"] = round(time.monotonic() - start, 1)
    if stats["stopped_at"] is None:
        stats["stopped_at"] = "limit"
    logger.info(
        "market_shape backfill: scanned=%d updated=%d by_shape=%s stopped=%s elapsed=%ss",
        stats["scanned"],
        stats["updated"],
        stats["by_shape"],
        stats["stopped_at"],
        stats["elapsed_s"],
    )
    return stats
