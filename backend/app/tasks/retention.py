"""
Snapshot retention — collapse consecutive identical rows to save DB space.

Pure SQL implementation using window functions for constant memory usage.
No snapshot rows are loaded into Python — all collapsing happens in the database.

WIN-PROBABILITY ROWS HAVE THEIR OWN PASS (#7878, Codex card-B decision
2026-09-24, producer option b). The chart draws `win_prob_snapshots`, and a
consumer judges "were we watching here?" from the spacing of consecutive
`captured_at` values — the only column that is an observation instant. The
generic pass below merged runs of equal HOME price with no gap bound and kept
`MIN(id)`, so a 10:00 and a 10:01 reading followed by a 12:00 one became one row
whose `valid_until` claimed two unobserved hours; it also merged rows that
differed in away/draw, period or score, and could keep a row that was not the
earliest. `_collapse_winprob_partition_sql` replaces it for this table only:

* **merges only raw observations** — never candle/price-history backfill
  (`game_state.poll_type = 'history_backfill'` or `game_state.backfill`), never
  a row written after the fact with `game_state.backfilled` (ESPN's play-by-play
  backfill, #8514: its estimated rows sat 200 s apart, so equal neighbours were
  eligible to merge and come back stamped as observed coverage), never
  a row with no home price, never a series' LAST row (a completed game rewrites
  that one in place, so its value was not observed at its `captured_at`);
* **only when the whole tuple matches** — home/away/draw, period/inning/half,
  score, and the market/outcome identity the reading came from;
* **only across a proven gap ≤ G** (`EVIDENCE_RESOLUTION_S`, 5 minutes): measured
  from the previous row's proven end — its own `captured_at`, or the
  `covered_through` of a span this same contract already stamped — to the next
  row's `captured_at`. Exactly G merges; wider does not;
* **keeps the earliest row** (`captured_at`, then `id`) and stamps it with
  `game_state.evidence_span = {contract, resolution_s, covered_through}`, where
  `covered_through` is the latest genuine member capture or validated span end.
  A repeat pass composes stamped spans and is otherwise a no-op.

It never reads `valid_until` or `reading_count` as evidence: those are closure
and count, and a legacy row compacted before this contract carries no stamp, so
its coverage is its own `captured_at` and nothing more. `valid_until` and
`reading_count` keep their existing continuity meaning on the keeper.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.tasks.base import get_task_session
# #7878: the evidence contract's constants live with its served half, so the
# SQL that stamps a span and the route that serves it cannot drift apart.
from app.utils.winprob_evidence import (
    COVERED_THROUGH_RE as _COVERED_THROUGH_RE,
    EVIDENCE_CONTRACT,
    EVIDENCE_RESOLUTION_S,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table-specific configuration
# ---------------------------------------------------------------------------

_TABLE_CONFIG = {
    "odds": {
        "table": "odds_snapshots",
        "partition_col": "event_id",        # main partition key
        "sub_partition_col": "bookmaker",   # sub-partition key
        "value_col": "home_win_probability",
        "parent_table": "odds_snapshots",   # for finding partition IDs
    },
    "winprob": {
        "table": "win_prob_snapshots",
        "partition_col": "event_id",
        "sub_partition_col": "source",
        "value_col": "home_win_probability",
        "parent_table": "win_prob_snapshots",
        # #7878: collapsed by `_collapse_winprob_partition_sql`, not the
        # generic equal-value pass.
        "evidence_contract": True,
    },
    "futures": {
        "table": "futures_odds_snapshots",
        "partition_col": "outcome_id",
        "sub_partition_col": "bookmaker",
        "value_col": "probability",
        "parent_table": "futures_odds_snapshots",
    },
}


async def _collapse_snapshots_impl(min_age_hours: int = 48, table: str = "odds", limit: int = 200):
    from datetime import timedelta

    if table not in _TABLE_CONFIG:
        return {"error": f"Unknown table: {table}. Use 'odds', 'winprob', or 'futures'."}

    cfg = _TABLE_CONFIG[table]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    total_deleted = 0
    total_updated = 0
    partitions_processed = 0

    # Step 1: Find partition IDs with old snapshots (constant memory — just IDs).
    # For futures, prioritize resolved markets (they'll never get new data).
    async with get_task_session() as session:
        if table == "futures":
            # Resolved markets first, then open markets
            result = await session.execute(
                text("""
                    SELECT outcome_id FROM (
                        SELECT DISTINCT fos.outcome_id,
                            MIN(CASE WHEN fm.status = 'resolved' THEN 0 ELSE 1 END) AS priority
                        FROM futures_odds_snapshots fos
                        JOIN futures_outcomes fo ON fo.id = fos.outcome_id
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        WHERE fos.captured_at < :cutoff
                        GROUP BY fos.outcome_id
                    ) sub
                    ORDER BY priority
                    LIMIT :lim
                """),
                {"cutoff": cutoff, "lim": limit},
            )
        else:
            result = await session.execute(
                text(f"""
                    SELECT DISTINCT {cfg['partition_col']}
                    FROM {cfg['table']}
                    WHERE captured_at < :cutoff
                    LIMIT :lim
                """),
                {"cutoff": cutoff, "lim": limit},
            )
        partition_ids = [r[0] for r in result.fetchall()]

    # Step 2: Process each partition entirely in SQL
    for part_id in partition_ids:
        async with get_task_session() as session:
            deleted, updated = await _collapse_partition_sql(
                session, cfg, part_id, cutoff
            )
            total_deleted += deleted
            total_updated += updated
        partitions_processed += 1

    logger.info(
        f"Snapshot collapse [{table}]: {total_deleted} rows deleted, "
        f"{total_updated} keepers updated across {partitions_processed} partitions"
    )
    return {
        "table": table,
        "rows_deleted": total_deleted,
        "keepers_updated": total_updated,
        "partitions_processed": partitions_processed,
    }


async def _collapse_partition_sql(session, cfg: dict, partition_id: int, cutoff: datetime) -> tuple[int, int]:
    """Collapse consecutive identical rows for one partition using pure SQL.

    Uses window functions to identify runs of identical values, then:
    1. Updates keepers (first row of each run) with aggregated valid_until + reading_count
    2. Deletes non-keeper rows from runs of length > 1

    Returns (rows_deleted, keepers_updated).
    """
    if cfg.get("evidence_contract"):
        return await _collapse_winprob_partition_sql(session, cfg, partition_id, cutoff)

    tbl = cfg["table"]
    pcol = cfg["partition_col"]
    scol = cfg["sub_partition_col"]
    vcol = cfg["value_col"]

    # ------------------------------------------------------------------
    # CTE-based approach:
    #
    # 1. ordered: all rows for this partition (before cutoff), with LAG()
    #    to compare each row's value with the previous row in the same
    #    (partition_col, sub_partition_col) group.
    #
    # 2. run_marked: flag each row as a "new run" boundary when the value
    #    changes (or is the first row). Use IS DISTINCT FROM for NULL-safe
    #    comparison.
    #
    # 3. run_grouped: assign a run_group_id via cumulative SUM of boundaries.
    #
    # 4. run_stats: for each run of length > 1, compute the keeper ID
    #    (MIN(id)), last timestamp, and total reading count.
    #
    # Then UPDATE keepers and DELETE non-keepers.
    # ------------------------------------------------------------------

    # Step 1: Update keepers with aggregated valid_until and reading_count
    update_sql = text(f"""
        WITH ordered AS (
            SELECT
                id,
                {scol},
                captured_at,
                valid_until,
                reading_count,
                {vcol},
                LAG({vcol}) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) AS prev_value
            FROM {tbl}
            WHERE {pcol} = :part_id
              AND captured_at < :cutoff
        ),
        run_marked AS (
            SELECT
                *,
                CASE
                    WHEN prev_value IS NULL AND {vcol} IS NULL THEN 0
                    WHEN {vcol} IS DISTINCT FROM prev_value THEN 1
                    ELSE 0
                END AS is_new_run
            FROM ordered
        ),
        run_grouped AS (
            SELECT
                *,
                SUM(is_new_run) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) AS run_group
            FROM run_marked
        ),
        run_stats AS (
            SELECT
                {scol} AS sub_key,
                run_group,
                MIN(id) AS keeper_id,
                MAX(COALESCE(valid_until, captured_at)) AS last_time,
                SUM(COALESCE(reading_count, 1)) AS total_readings,
                COUNT(*) AS run_len
            FROM run_grouped
            GROUP BY {scol}, run_group
            HAVING COUNT(*) > 1
        )
        UPDATE {tbl} t
        SET valid_until = rs.last_time,
            reading_count = rs.total_readings
        FROM run_stats rs
        WHERE t.id = rs.keeper_id
    """)

    result = await session.execute(update_sql, {"part_id": partition_id, "cutoff": cutoff})
    keepers_updated = result.rowcount

    # Step 2: Delete non-keeper rows from runs of length > 1
    # We need to re-run the CTE to identify which rows are NOT keepers
    delete_sql = text(f"""
        WITH ordered AS (
            SELECT
                id,
                {scol},
                captured_at,
                {vcol},
                LAG({vcol}) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) AS prev_value
            FROM {tbl}
            WHERE {pcol} = :part_id
              AND captured_at < :cutoff
        ),
        run_marked AS (
            SELECT
                *,
                CASE
                    WHEN prev_value IS NULL AND {vcol} IS NULL THEN 0
                    WHEN {vcol} IS DISTINCT FROM prev_value THEN 1
                    ELSE 0
                END AS is_new_run
            FROM ordered
        ),
        run_grouped AS (
            SELECT
                *,
                SUM(is_new_run) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) AS run_group
            FROM run_marked
        ),
        keepers AS (
            SELECT
                {scol} AS sub_key,
                run_group,
                MIN(id) AS keeper_id
            FROM run_grouped
            GROUP BY {scol}, run_group
            HAVING COUNT(*) > 1
        ),
        to_delete AS (
            SELECT rg.id
            FROM run_grouped rg
            JOIN keepers k
              ON rg.{scol} = k.sub_key
             AND rg.run_group = k.run_group
             AND rg.id != k.keeper_id
        )
        DELETE FROM {tbl}
        WHERE id IN (SELECT id FROM to_delete)
    """)

    result = await session.execute(delete_sql, {"part_id": partition_id, "cutoff": cutoff})
    rows_deleted = result.rowcount

    await _bridge_valid_until(session, cfg, partition_id, cutoff)

    return rows_deleted, keepers_updated


async def _bridge_valid_until(session, cfg: dict, partition_id: int, cutoff: datetime) -> None:
    """Step 3 of both passes: close out rows whose ``valid_until`` is still NULL.

    When a value changes, the previous keeper's valid_until should be set to the
    next row's captured_at, matching the Python implementation's behavior. This
    is continuity (closure), never evidence — see the module docstring.
    """
    tbl = cfg["table"]
    pcol = cfg["partition_col"]
    scol = cfg["sub_partition_col"]

    bridge_sql = text(f"""
        WITH ordered AS (
            SELECT
                id,
                {scol},
                captured_at,
                valid_until,
                LEAD(captured_at) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) AS next_captured_at
            FROM {tbl}
            WHERE {pcol} = :part_id
              AND captured_at < :cutoff
        )
        UPDATE {tbl} t
        SET valid_until = o.next_captured_at
        FROM ordered o
        WHERE t.id = o.id
          AND t.valid_until IS NULL
          AND o.next_captured_at IS NOT NULL
    """)

    await session.execute(bridge_sql, {"part_id": partition_id, "cutoff": cutoff})


# ---------------------------------------------------------------------------
# Win-probability evidence collapse (#7878)
# ---------------------------------------------------------------------------

async def _collapse_winprob_partition_sql(
    session, cfg: dict, partition_id: int, cutoff: datetime
) -> tuple[int, int]:
    """Collapse one event's win-probability rows without inventing coverage.

    The rules are the module docstring's. One statement: the keeper UPDATE and the
    DELETE are data-modifying CTEs over one snapshot, so the run grouping the
    delete acts on is exactly the one the keepers were stamped from.

    Returns (rows_deleted, keepers_updated).
    """
    tbl = cfg["table"]
    pcol = cfg["partition_col"]
    scol = cfg["sub_partition_col"]

    collapse_sql = text(f"""
        WITH series AS (
            SELECT
                id,
                {scol},
                captured_at,
                valid_until,
                reading_count,
                game_state,
                home_win_probability,
                -- The series' last row, judged over ALL its rows (not only the
                -- aged ones): a completed game refreshes that row in place
                -- (#922), so its value was not observed at its captured_at.
                LEAD(id) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) IS NULL AS is_series_last,
                jsonb_build_array(
                    home_win_probability,
                    away_win_probability,
                    draw_probability,
                    game_state->'period',
                    game_state->'inning',
                    game_state->'inning_half',
                    game_state->'home_score',
                    game_state->'away_score',
                    game_state->'market_id',
                    game_state->'outcome_name'
                ) AS tuple_key
            FROM {tbl}
            WHERE {pcol} = :part_id
        ),
        aged AS (
            SELECT
                *,
                (
                    home_win_probability IS NOT NULL
                    AND NOT is_series_last
                    AND COALESCE(game_state->>'poll_type', '') <> 'history_backfill'
                    AND COALESCE(game_state->>'backfill', '') <> 'true'
                    AND COALESCE(game_state->>'backfilled', '') <> 'true'
                ) AS eligible,
                CASE
                    WHEN game_state->'evidence_span'->>'contract' = CAST(:contract AS text)
                     AND game_state->'evidence_span'->>'resolution_s' = CAST(:resolution_text AS text)
                     AND game_state->'evidence_span'->>'covered_through' ~ CAST(:ts_re AS text)
                    THEN GREATEST(
                        captured_at,
                        CAST(game_state->'evidence_span'->>'covered_through' AS timestamptz)
                    )
                    ELSE captured_at
                END AS proven_end
            FROM series
            WHERE captured_at < :cutoff
        ),
        lagged AS (
            SELECT
                *,
                LAG(eligible) OVER w AS prev_eligible,
                LAG(proven_end) OVER w AS prev_end,
                LAG(tuple_key) OVER w AS prev_tuple
            FROM aged
            WINDOW w AS (PARTITION BY {scol} ORDER BY captured_at, id)
        ),
        run_marked AS (
            SELECT
                *,
                CASE
                    WHEN NOT eligible THEN 1
                    WHEN prev_eligible IS NOT TRUE THEN 1
                    WHEN tuple_key IS DISTINCT FROM prev_tuple THEN 1
                    WHEN captured_at - prev_end
                         > make_interval(secs => CAST(:g_seconds AS double precision)) THEN 1
                    ELSE 0
                END AS is_new_run
            FROM lagged
        ),
        run_grouped AS (
            SELECT
                *,
                SUM(is_new_run) OVER (
                    PARTITION BY {scol}
                    ORDER BY captured_at, id
                ) AS run_group
            FROM run_marked
        ),
        keepers AS (
            SELECT
                {scol} AS sub_key,
                run_group,
                (ARRAY_AGG(id ORDER BY captured_at, id))[1] AS keeper_id,
                MAX(COALESCE(valid_until, captured_at)) AS last_time,
                SUM(COALESCE(reading_count, 1)) AS total_readings,
                MAX(proven_end) AS covered_through
            FROM run_grouped
            GROUP BY {scol}, run_group
            HAVING COUNT(*) > 1
        ),
        stamped AS (
            UPDATE {tbl} t
            SET valid_until = k.last_time,
                reading_count = k.total_readings,
                game_state = (
                    CASE WHEN jsonb_typeof(t.game_state) = 'object'
                         THEN t.game_state ELSE '{{}}'::jsonb END
                ) || jsonb_build_object(
                    'evidence_span',
                    jsonb_build_object(
                        'contract', CAST(:contract AS text),
                        'resolution_s', CAST(:resolution_s AS integer),
                        'covered_through', to_char(
                            k.covered_through AT TIME ZONE 'UTC',
                            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                        )
                    )
                )
            FROM keepers k
            WHERE t.id = k.keeper_id
            RETURNING t.id
        ),
        to_delete AS (
            SELECT rg.id
            FROM run_grouped rg
            JOIN keepers k
              ON rg.{scol} = k.sub_key
             AND rg.run_group = k.run_group
             AND rg.id != k.keeper_id
        ),
        deleted AS (
            DELETE FROM {tbl}
            WHERE id IN (SELECT id FROM to_delete)
            RETURNING id
        )
        SELECT
            (SELECT COUNT(*) FROM deleted) AS rows_deleted,
            (SELECT COUNT(*) FROM stamped) AS keepers_updated
    """)

    result = await session.execute(
        collapse_sql,
        {
            "part_id": partition_id,
            "cutoff": cutoff,
            "g_seconds": float(EVIDENCE_RESOLUTION_S),
            "contract": EVIDENCE_CONTRACT,
            "resolution_s": EVIDENCE_RESOLUTION_S,
            "resolution_text": str(EVIDENCE_RESOLUTION_S),
            "ts_re": _COVERED_THROUGH_RE,
        },
    )
    rows_deleted, keepers_updated = result.one()

    await _bridge_valid_until(session, cfg, partition_id, cutoff)

    return int(rows_deleted or 0), int(keepers_updated or 0)


# ---------------------------------------------------------------------------
# Crypto cleanup
# ---------------------------------------------------------------------------

async def _cleanup_crypto_impl(batch_size: int = 5000):
    """Delete all crypto futures data (markets, outcomes, snapshots) in batches."""
    async with get_task_session() as session:
        stats = {"snapshots_deleted": 0, "outcomes_deleted": 0, "markets_deleted": 0}

        # Get crypto market IDs
        result = await session.execute(text(
            "SELECT id FROM futures_markets WHERE llm_sport_category = 'crypto'"
        ))
        market_ids = [r[0] for r in result.fetchall()]
        if not market_ids:
            return {"status": "nothing_to_delete", **stats}

        # Get outcome IDs
        result = await session.execute(text(
            "SELECT id FROM futures_outcomes WHERE market_id = ANY(:ids)"
        ), {"ids": market_ids})
        outcome_ids = [r[0] for r in result.fetchall()]

        # Delete snapshots in batches
        if outcome_ids:
            while True:
                result = await session.execute(text("""
                    DELETE FROM futures_odds_snapshots
                    WHERE id IN (
                        SELECT id FROM futures_odds_snapshots
                        WHERE outcome_id = ANY(:ids) LIMIT :batch
                    )
                """), {"ids": outcome_ids, "batch": batch_size})
                deleted = result.rowcount
                await session.commit()
                stats["snapshots_deleted"] += deleted
                logger.info("Crypto cleanup: deleted %d snapshots (total: %d)",
                           deleted, stats["snapshots_deleted"])
                if deleted < batch_size:
                    break

        # Delete outcomes
        result = await session.execute(text(
            "DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"
        ), {"ids": market_ids})
        stats["outcomes_deleted"] = result.rowcount
        await session.commit()

        # Delete markets
        result = await session.execute(text(
            "DELETE FROM futures_markets WHERE llm_sport_category = 'crypto'"
        ))
        stats["markets_deleted"] = result.rowcount
        await session.commit()

        logger.info("Crypto cleanup complete: %s", stats)
        return {"status": "success", **stats}
