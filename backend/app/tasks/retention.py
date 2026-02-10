"""
Snapshot retention — collapse consecutive identical rows to save DB space.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


async def _collapse_snapshots_impl(min_age_hours: int = 48, table: str = "odds", limit: int = 200):
    from app.models import (
        OddsSnapshot, WinProbSnapshot, FuturesOddsSnapshot,
        FuturesOutcome, Event,
    )
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    total_deleted = 0
    partitions_processed = 0

    CHUNK_SIZE = 5000

    if table == "odds":
        # Find events with old snapshots, process in batches
        async with get_task_session() as session:
            result = await session.execute(
                select(OddsSnapshot.event_id)
                .where(OddsSnapshot.captured_at < cutoff)
                .group_by(OddsSnapshot.event_id)
                .limit(limit)
            )
            event_ids = [r[0] for r in result.fetchall()]

        for event_id in event_ids:
            # Each event gets its own session/transaction
            async with get_task_session() as session:
                deleted = await _collapse_table_for_partition(
                    session,
                    table_class=OddsSnapshot,
                    partition_cols=[OddsSnapshot.event_id, OddsSnapshot.bookmaker],
                    value_cols=[OddsSnapshot.home_win_probability],
                    partition_values={"event_id": event_id},
                    cutoff=cutoff,
                    chunk_size=CHUNK_SIZE,
                )
                total_deleted += deleted
            partitions_processed += 1

    elif table == "winprob":
        async with get_task_session() as session:
            result = await session.execute(
                select(WinProbSnapshot.event_id)
                .where(WinProbSnapshot.captured_at < cutoff)
                .group_by(WinProbSnapshot.event_id)
                .limit(limit)
            )
            event_ids = [r[0] for r in result.fetchall()]

        for event_id in event_ids:
            async with get_task_session() as session:
                deleted = await _collapse_table_for_partition(
                    session,
                    table_class=WinProbSnapshot,
                    partition_cols=[WinProbSnapshot.event_id, WinProbSnapshot.source],
                    value_cols=[WinProbSnapshot.home_win_probability],
                    partition_values={"event_id": event_id},
                    cutoff=cutoff,
                    chunk_size=CHUNK_SIZE,
                )
                total_deleted += deleted
            partitions_processed += 1

    elif table == "futures":
        async with get_task_session() as session:
            result = await session.execute(
                select(FuturesOddsSnapshot.outcome_id)
                .where(FuturesOddsSnapshot.captured_at < cutoff)
                .group_by(FuturesOddsSnapshot.outcome_id)
                .limit(limit)
            )
            outcome_ids = [r[0] for r in result.fetchall()]

        for outcome_id in outcome_ids:
            async with get_task_session() as session:
                deleted = await _collapse_table_for_partition(
                    session,
                    table_class=FuturesOddsSnapshot,
                    partition_cols=[FuturesOddsSnapshot.outcome_id, FuturesOddsSnapshot.bookmaker],
                    value_cols=[FuturesOddsSnapshot.probability],
                    partition_values={"outcome_id": outcome_id},
                    cutoff=cutoff,
                    chunk_size=CHUNK_SIZE,
                )
                total_deleted += deleted
            partitions_processed += 1

    else:
        return {"error": f"Unknown table: {table}. Use 'odds', 'winprob', or 'futures'."}

    logger.info(
        f"Snapshot collapse [{table}]: {total_deleted} rows deleted "
        f"across {partitions_processed} partitions"
    )
    return {
        "table": table,
        "rows_deleted": total_deleted,
        "partitions_processed": partitions_processed,
    }


async def _collapse_table_for_partition(
    session,
    table_class,
    partition_cols: list,
    value_cols: list,
    partition_values: dict,
    cutoff,
    chunk_size: int = 5000,
) -> int:
    """Collapse consecutive identical rows within a single partition key (e.g., one event).

    Iterates over all distinct sub-partitions (e.g., per-bookmaker within an event),
    finds consecutive rows with identical values, and merges them by:
    - Keeping the first row (earliest captured_at)
    - Setting its valid_until to the last row's captured_at (or valid_until)
    - Summing reading_counts
    - Deleting the duplicate rows

    Returns total rows deleted.
    """
    from sqlalchemy import delete

    total_deleted = 0

    # Get distinct sub-partition values (e.g., all bookmakers for this event)
    # partition_cols[0] is the main partition (event_id/outcome_id) — filtered by partition_values
    # partition_cols[1] is the sub-partition (bookmaker/source) — we iterate over these
    main_col = partition_cols[0]
    sub_col = partition_cols[1]

    main_filter = main_col == list(partition_values.values())[0]

    result = await session.execute(
        select(sub_col).where(
            main_filter,
            table_class.captured_at < cutoff,
        ).distinct()
    )
    sub_keys = [r[0] for r in result.fetchall()]

    for sub_key in sub_keys:
        # Fetch all rows for this partition, ordered by time
        result = await session.execute(
            select(table_class).where(
                main_filter,
                sub_col == sub_key,
                table_class.captured_at < cutoff,
            ).order_by(table_class.captured_at.asc())
        )
        rows = result.scalars().all()

        if len(rows) <= 1:
            continue

        # Walk through rows, finding runs of identical values
        ids_to_delete = []
        keeper = rows[0]
        value_col = value_cols[0]

        for row in rows[1:]:
            keeper_val = getattr(keeper, value_col.key)
            row_val = getattr(row, value_col.key)

            # Exact match comparison
            vals_equal = False
            if keeper_val is None and row_val is None:
                vals_equal = True
            elif keeper_val is not None and row_val is not None:
                vals_equal = float(keeper_val) == float(row_val)

            if vals_equal:
                # Same value — absorb into keeper
                last_time = row.valid_until or row.captured_at
                keeper.valid_until = last_time
                keeper.reading_count = (keeper.reading_count or 1) + (row.reading_count or 1)
                ids_to_delete.append(row.id)
            else:
                # Value changed — this row becomes the new keeper
                if keeper.valid_until is None:
                    keeper.valid_until = row.captured_at
                keeper = row

        # Delete absorbed rows in chunks
        for i in range(0, len(ids_to_delete), chunk_size):
            chunk = ids_to_delete[i:i + chunk_size]
            await session.execute(
                delete(table_class).where(table_class.id.in_(chunk))
            )
            await session.flush()

        total_deleted += len(ids_to_delete)

    return total_deleted
