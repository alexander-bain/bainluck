"""
One-time script to deduplicate existing OddsSnapshot rows.

This script collapses consecutive identical snapshots for each event+bookmaker
into a single row with reading_count and valid_until set.

Run with: heroku run python deduplicate_snapshots.py -a bainluck

WARNING: This modifies data! Run analyze_duplicates.py first to preview.
"""

import asyncio
import os
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# SSL for Heroku
connect_args = {}
if DATABASE_URL and "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    connect_args["ssl"] = "require"


async def deduplicate_snapshots():
    """
    Deduplicate OddsSnapshot rows by:
    1. Finding consecutive identical rows for each event+bookmaker
    2. Keeping only the first row in each group
    3. Setting reading_count = number of rows in group
    4. Setting valid_until = last captured_at in group
    5. Deleting the duplicate rows
    """

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    engine = create_async_engine(DATABASE_URL, connect_args=connect_args)
    async_session = async_sessionmaker(engine, class_=AsyncSession)

    async with async_session() as session:
        print(f"\n=== OddsSnapshot Deduplication ===")
        print(f"Started at: {datetime.utcnow().isoformat()}")

        # First, ensure the new columns exist
        print("\n1. Checking schema...")
        try:
            await session.execute(text("""
                ALTER TABLE odds_snapshots
                ADD COLUMN IF NOT EXISTS reading_count INTEGER DEFAULT 1,
                ADD COLUMN IF NOT EXISTS valid_until TIMESTAMP WITH TIME ZONE
            """))
            await session.commit()
            print("   Schema OK")
        except Exception as e:
            print(f"   Schema check failed: {e}")
            await session.rollback()

        # Get counts before
        result = await session.execute(text("SELECT COUNT(*) FROM odds_snapshots"))
        count_before = result.scalar()
        print(f"\n2. Rows before dedup: {count_before:,}")

        # The deduplication strategy:
        # Use a CTE to identify groups of consecutive identical rows,
        # then update the first row in each group and delete the rest.

        print("\n3. Identifying duplicate groups...")

        # This query identifies groups of consecutive identical snapshots
        # and calculates the reading_count and valid_until for each group
        dedup_query = text("""
            WITH ranked AS (
                SELECT
                    id,
                    event_id,
                    bookmaker,
                    captured_at,
                    home_moneyline,
                    away_moneyline,
                    home_spread,
                    over_under,
                    home_win_probability,
                    LAG(home_moneyline) OVER w as prev_hml,
                    LAG(away_moneyline) OVER w as prev_aml,
                    LAG(home_spread) OVER w as prev_sp,
                    LAG(over_under) OVER w as prev_ou,
                    LAG(home_win_probability) OVER w as prev_prob,
                    ROW_NUMBER() OVER w as rn
                FROM odds_snapshots
                WINDOW w AS (PARTITION BY event_id, bookmaker ORDER BY captured_at)
            ),
            with_group_marker AS (
                SELECT
                    *,
                    CASE
                        WHEN rn = 1 THEN 1  -- First row starts a new group
                        WHEN (home_moneyline IS NOT DISTINCT FROM prev_hml)
                         AND (away_moneyline IS NOT DISTINCT FROM prev_aml)
                         AND (home_spread IS NOT DISTINCT FROM prev_sp)
                         AND (over_under IS NOT DISTINCT FROM prev_ou)
                         AND (home_win_probability IS NOT DISTINCT FROM prev_prob)
                        THEN 0  -- Same as previous = same group
                        ELSE 1  -- Different = new group
                    END as is_new_group
                FROM ranked
            ),
            with_group_id AS (
                SELECT
                    *,
                    SUM(is_new_group) OVER (
                        PARTITION BY event_id, bookmaker
                        ORDER BY captured_at
                        ROWS UNBOUNDED PRECEDING
                    ) as group_id
                FROM with_group_marker
            ),
            group_stats AS (
                SELECT
                    event_id,
                    bookmaker,
                    group_id,
                    MIN(id) as keep_id,
                    COUNT(*) as reading_count,
                    MAX(captured_at) as valid_until,
                    ARRAY_AGG(id ORDER BY captured_at) as all_ids
                FROM with_group_id
                GROUP BY event_id, bookmaker, group_id
            )
            SELECT
                keep_id,
                reading_count,
                valid_until,
                all_ids
            FROM group_stats
            WHERE reading_count > 1
        """)

        result = await session.execute(dedup_query)
        groups = result.fetchall()

        print(f"   Found {len(groups):,} groups with duplicates")

        if len(groups) == 0:
            print("\n   No duplicates to process!")
            return

        # Process in batches to avoid memory issues
        batch_size = 1000
        total_updated = 0
        total_deleted = 0

        print(f"\n4. Processing {len(groups):,} groups in batches of {batch_size}...")

        for i in range(0, len(groups), batch_size):
            batch = groups[i:i + batch_size]

            for keep_id, reading_count, valid_until, all_ids in batch:
                # Update the row we're keeping
                await session.execute(
                    text("""
                        UPDATE odds_snapshots
                        SET reading_count = :count, valid_until = :valid_until
                        WHERE id = :id
                    """),
                    {"id": keep_id, "count": reading_count, "valid_until": valid_until}
                )
                total_updated += 1

                # Delete the duplicate rows (all except the one we're keeping)
                ids_to_delete = [id for id in all_ids if id != keep_id]
                if ids_to_delete:
                    await session.execute(
                        text("DELETE FROM odds_snapshots WHERE id = ANY(:ids)"),
                        {"ids": ids_to_delete}
                    )
                    total_deleted += len(ids_to_delete)

            await session.commit()
            print(f"   Processed batch {i // batch_size + 1}/{(len(groups) + batch_size - 1) // batch_size}")

        # Get counts after
        result = await session.execute(text("SELECT COUNT(*) FROM odds_snapshots"))
        count_after = result.scalar()

        print(f"\n=== Deduplication Complete ===")
        print(f"Rows before: {count_before:,}")
        print(f"Rows after: {count_after:,}")
        print(f"Rows deleted: {total_deleted:,}")
        print(f"Groups updated: {total_updated:,}")
        print(f"Reduction: {(1 - count_after / count_before) * 100:.1f}%")

        # Vacuum to reclaim space (can't run in transaction)
        print(f"\nNote: Run 'VACUUM ANALYZE odds_snapshots;' manually to reclaim disk space")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(deduplicate_snapshots())
