"""
Analyze OddsSnapshot table for duplicate values that could be collapsed.

Run with: heroku run python analyze_duplicates.py -a your-app-name

This script identifies rows where the odds values haven't changed from the
previous snapshot for the same event+bookmaker combination. These could be
collapsed into a single row with a "duplicate_count" field.
"""

import os
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy import select, func, text
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


async def analyze_duplicates():
    """Analyze duplicate patterns in OddsSnapshot table."""

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    engine = create_async_engine(DATABASE_URL, connect_args=connect_args)
    async_session = async_sessionmaker(engine, class_=AsyncSession)

    async with async_session() as session:
        # Get total row count
        result = await session.execute(text("SELECT COUNT(*) FROM odds_snapshots"))
        total_rows = result.scalar()
        print(f"\n=== OddsSnapshot Analysis ===")
        print(f"Total rows: {total_rows:,}")

        if total_rows == 0:
            print("No data to analyze.")
            return

        # Get date range
        result = await session.execute(text("""
            SELECT MIN(captured_at), MAX(captured_at)
            FROM odds_snapshots
        """))
        row = result.fetchone()
        print(f"Date range: {row[0]} to {row[1]}")

        # Get rows by age
        now = datetime.now(timezone.utc)
        result = await session.execute(text("""
            SELECT
                CASE
                    WHEN captured_at > NOW() - INTERVAL '1 day' THEN '< 1 day'
                    WHEN captured_at > NOW() - INTERVAL '7 days' THEN '1-7 days'
                    WHEN captured_at > NOW() - INTERVAL '30 days' THEN '7-30 days'
                    ELSE '> 30 days'
                END as age_bucket,
                COUNT(*) as row_count
            FROM odds_snapshots
            GROUP BY 1
            ORDER BY 1
        """))
        print(f"\nRows by age:")
        for row in result:
            print(f"  {row[0]}: {row[1]:,}")

        # Analyze duplicates for events older than 7 days
        # A duplicate is when all odds values are the same as the previous row
        # for the same event_id + bookmaker combination
        print(f"\n=== Duplicate Analysis (events > 7 days old) ===")

        # This query finds consecutive rows with identical values
        # Using LAG to compare with previous row
        result = await session.execute(text("""
            WITH ranked_snapshots AS (
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
                    LAG(home_moneyline) OVER w as prev_home_ml,
                    LAG(away_moneyline) OVER w as prev_away_ml,
                    LAG(home_spread) OVER w as prev_spread,
                    LAG(over_under) OVER w as prev_ou,
                    LAG(home_win_probability) OVER w as prev_prob,
                    ROW_NUMBER() OVER w as rn
                FROM odds_snapshots
                WHERE captured_at < NOW() - INTERVAL '7 days'
                WINDOW w AS (PARTITION BY event_id, bookmaker ORDER BY captured_at)
            ),
            duplicates AS (
                SELECT
                    id,
                    event_id,
                    bookmaker,
                    rn,
                    CASE
                        WHEN rn = 1 THEN false  -- First row is never a duplicate
                        WHEN (home_moneyline IS NOT DISTINCT FROM prev_home_ml)
                         AND (away_moneyline IS NOT DISTINCT FROM prev_away_ml)
                         AND (home_spread IS NOT DISTINCT FROM prev_spread)
                         AND (over_under IS NOT DISTINCT FROM prev_ou)
                         AND (home_win_probability IS NOT DISTINCT FROM prev_prob)
                        THEN true
                        ELSE false
                    END as is_duplicate
                FROM ranked_snapshots
            )
            SELECT
                COUNT(*) as total_old_rows,
                SUM(CASE WHEN is_duplicate THEN 1 ELSE 0 END) as duplicate_rows,
                COUNT(DISTINCT event_id) as unique_events
            FROM duplicates
        """))

        row = result.fetchone()
        if row and row[0] > 0:
            total_old = row[0]
            duplicates = row[1]
            unique_events = row[2]
            pct_duplicates = (duplicates / total_old) * 100
            potential_savings = duplicates

            print(f"Rows older than 7 days: {total_old:,}")
            print(f"Duplicate rows (unchanged from previous): {duplicates:,}")
            print(f"Percentage that are duplicates: {pct_duplicates:.1f}%")
            print(f"Unique events in old data: {unique_events:,}")
            print(f"\nPotential row reduction: {duplicates:,} rows ({pct_duplicates:.1f}%)")
            print(f"Rows after dedup: {total_old - duplicates:,}")
        else:
            print("No rows older than 7 days found.")

        # Also show distribution of duplicates per event
        print(f"\n=== Duplicate Distribution (sample) ===")
        result = await session.execute(text("""
            WITH ranked_snapshots AS (
                SELECT
                    event_id,
                    bookmaker,
                    home_moneyline,
                    away_moneyline,
                    home_spread,
                    over_under,
                    home_win_probability,
                    LAG(home_moneyline) OVER w as prev_home_ml,
                    LAG(away_moneyline) OVER w as prev_away_ml,
                    LAG(home_spread) OVER w as prev_spread,
                    LAG(over_under) OVER w as prev_ou,
                    LAG(home_win_probability) OVER w as prev_prob,
                    ROW_NUMBER() OVER w as rn
                FROM odds_snapshots
                WHERE captured_at < NOW() - INTERVAL '7 days'
                WINDOW w AS (PARTITION BY event_id, bookmaker ORDER BY captured_at)
            ),
            event_stats AS (
                SELECT
                    event_id,
                    COUNT(*) as total_rows,
                    SUM(CASE
                        WHEN rn = 1 THEN 0
                        WHEN (home_moneyline IS NOT DISTINCT FROM prev_home_ml)
                         AND (away_moneyline IS NOT DISTINCT FROM prev_away_ml)
                         AND (home_spread IS NOT DISTINCT FROM prev_spread)
                         AND (over_under IS NOT DISTINCT FROM prev_ou)
                         AND (home_win_probability IS NOT DISTINCT FROM prev_prob)
                        THEN 1
                        ELSE 0
                    END) as dup_rows
                FROM ranked_snapshots
                GROUP BY event_id
            )
            SELECT
                CASE
                    WHEN total_rows = 0 THEN '0'
                    ELSE CONCAT(FLOOR(dup_rows::float / total_rows * 10) * 10, '-',
                                FLOOR(dup_rows::float / total_rows * 10) * 10 + 10, '%')
                END as dup_pct_bucket,
                COUNT(*) as event_count,
                SUM(total_rows) as total_rows,
                SUM(dup_rows) as dup_rows
            FROM event_stats
            WHERE total_rows > 0
            GROUP BY 1
            ORDER BY 1
        """))

        print("Events grouped by duplicate percentage:")
        for row in result:
            print(f"  {row[0]}: {row[1]:,} events ({row[2]:,} rows, {row[3]:,} duplicates)")

        # Table size info
        print(f"\n=== Storage Info ===")
        result = await session.execute(text("""
            SELECT
                pg_size_pretty(pg_total_relation_size('odds_snapshots')) as total_size,
                pg_size_pretty(pg_relation_size('odds_snapshots')) as data_size,
                pg_size_pretty(pg_indexes_size('odds_snapshots')) as index_size
        """))
        row = result.fetchone()
        print(f"Total table size: {row[0]}")
        print(f"Data size: {row[1]}")
        print(f"Index size: {row[2]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(analyze_duplicates())
