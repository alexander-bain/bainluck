"""Append the #2622 discipline axis to the canonical keys already in the table.

THE SHIP THIS SERVES. `/sports` Top Markets stops welding two different
questions into one card — the one that put **Carlos Alcaraz at #1, 36%, to win
the 2026 Women's US Open**. The producer fix (`compute_canonical_market_key`,
`app/utils/futures_categorization.py`) makes every NEW and re-ingested market
carry the axis. This rail is for the rows already sitting in the table, which is
where the two US Open boards actually live.

WHAT IT WRITES, EXACTLY. For an open market whose stored
`canonical_market_key` has the pre-#2622 four-segment shape, it appends the
discipline segment derived from that market's own name:

    tennis::championship:2026  ->  tennis::championship:2026:womens-us-open

Nothing else. Segments 0-3 are taken from the stored key VERBATIM and never
re-derived. That is the whole design: re-running `detect_league` /
`detect_season` over 861,809 rows would churn keys for reasons that have nothing
to do with #2622 — a league pattern added since ingest, a season boundary
crossed — and this rail would become an unbounded reclassification wearing a
narrow name. Appending is the only write it is capable of.

WHY THERE IS NO `plan_hash`. The repairs that demand one (CAL-P058,
C-CERT-1852) write GRADES: `is_winner`, `calibration_probability` — values whose
prior state is not recoverable once overwritten (gotcha #21). A canonical key is
a pure function of columns that stay on the row, so any key this rail writes can
be recomputed, and any key it should not have written can be un-written by the
same function. The gate it does carry is the one that matters here: it only ever
touches rows whose key has exactly four segments, so a second run over its own
output is a no-op by construction rather than by bookkeeping.

WHY `status='open'` IS THE DEFAULT POPULATION, and it is not timidity.
`precompute_calibration.py`'s fair-fight pairing joins Kalshi to Polymarket on
`canonical_market_key` across `status = 'resolved'` rows ONLY. Rekeying the
resolved set would re-cut those cohorts underneath a curve that is already
mid-rebuild. The feed, `/sports`, the category pages and the source-count badge
all read OPEN markets, so the open population is both the whole ship and the
whole blast radius. `population=all` exists, is refused unless asked for by
name, and is a calibration decision rather than a lane's.

    POST /api/admin/repairs/canonical-key-rekey-census
    POST /api/admin/repairs/canonical-key-rekey?apply=false&limit=2000
    POST /api/admin/repairs/canonical-key-rekey?apply=true&limit=2000&after_id=<next_cursor>

The cursor is a KEYSET on `id` (CAL-P058's lesson): a page that rekeys its rows
removes them from `PRE_DISCIPLINE_PREDICATE`, so an OFFSET would step over
exactly as many untouched rows as it had just repaired.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from app.utils.futures_categorization import market_discipline_axis

logger = logging.getLogger(__name__)

#: A pre-#2622 key has exactly four segments, so it has exactly three colons.
#: This is the whole eligibility test, and it is also the idempotence guarantee:
#: a rekeyed row grows a fourth colon and leaves the population for good.
PRE_DISCIPLINE_PREDICATE = (
    "canonical_market_key IS NOT NULL "
    "AND length(canonical_market_key) - length(replace(canonical_market_key, ':', '')) = 3"
)

#: `population` values the rail accepts. `all` is spelled out rather than
#: implied — see the module docstring on why the resolved set is not ours.
POPULATIONS = {
    "open": "status = 'open'",
    "all": "TRUE",
}

DEFAULT_LIMIT = 2000
MAX_LIMIT = 20000


def _population_sql(population: Optional[str]) -> tuple[str, str]:
    name = (population or "open").strip().lower()
    if name not in POPULATIONS:
        raise ValueError(
            f"unknown population {name!r} — expected one of {sorted(POPULATIONS)}"
        )
    return name, POPULATIONS[name]


async def census(session, apply: bool = False, population: str = "open") -> dict[str, Any]:
    """Never writes. Names the population and the collision it is there to break.

    `apply` is accepted and ignored — a census that could write would be a
    repair with a reassuring name.
    """
    pop_name, pop_sql = _population_sql(population)

    totals = (await session.execute(text(f"""
        SELECT
            count(*) FILTER (WHERE canonical_market_key IS NOT NULL) AS keyed,
            count(*) FILTER (WHERE canonical_market_key IS NULL) AS unkeyed,
            count(*) FILTER (WHERE {PRE_DISCIPLINE_PREDICATE}) AS pre_discipline,
            count(*) AS total
        FROM futures_markets
        WHERE {pop_sql}
    """))).mappings().one()

    worst = (await session.execute(text(f"""
        SELECT canonical_market_key AS key,
               count(*) AS markets,
               count(DISTINCT source) AS sources
        FROM futures_markets
        WHERE {pop_sql} AND {PRE_DISCIPLINE_PREDICATE}
        GROUP BY 1
        HAVING count(*) > 1
        ORDER BY 2 DESC
        LIMIT 15
    """))).mappings().all()

    return {
        "repair": "canonical-key-rekey-census",
        "writes": False,
        "population": pop_name,
        "counts": dict(totals),
        "worst_collisions": [dict(r) for r in worst],
        # Named so a reader cannot mistake the census for the whole story:
        # a key with a large group is not automatically wrong, it is
        # automatically UNPROVEN.
        "note": (
            "markets sharing one key ask ONE question only if they also share "
            "outcomes; this census counts the sharing, not the agreement"
        ),
    }


async def repair(
    session,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
    after_id: int = 0,
    population: str = "open",
) -> dict[str, Any]:
    """Append the discipline segment. Dry-run by default; returns its own census."""
    pop_name, pop_sql = _population_sql(population)
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    after_id = int(after_id or 0)

    rows = (await session.execute(text(f"""
        SELECT id, name, canonical_market_key
        FROM futures_markets
        WHERE {pop_sql} AND {PRE_DISCIPLINE_PREDICATE} AND id > :after_id
        ORDER BY id
        LIMIT :limit
    """), {"after_id": after_id, "limit": limit})).mappings().all()

    examined = len(rows)
    planned: list[dict[str, str]] = []
    # RULING 054 — the rows this rail cannot change leave with a NAME and a
    # number, never as silent attrition. "no discipline in the name" is the
    # honest majority verdict for a market called "Massachusetts Governor
    # Election Winner", and it is a different fact from "the axis failed".
    no_axis = 0

    for row in rows:
        axis = market_discipline_axis(row["name"])
        if not axis:
            no_axis += 1
            continue
        planned.append({
            "id": row["id"],
            "old_key": row["canonical_market_key"],
            "new_key": f"{row['canonical_market_key']}:{axis}",
        })

    written = 0
    if apply and planned:
        for change in planned:
            # Compare-and-set on the exact key the plan read. A concurrent
            # ingest re-upserting this market between the read and the write
            # already computed the axis itself (the producer has it), and its
            # key is the fresher one — a rowcount of zero here is that, not a
            # failure.
            result = await session.execute(text("""
                UPDATE futures_markets
                SET canonical_market_key = :new_key
                WHERE id = :id AND canonical_market_key = :old_key
            """), change)
            written += result.rowcount or 0
        await session.commit()

    next_cursor = rows[-1]["id"] if rows else None
    return {
        "repair": "canonical-key-rekey",
        "apply": apply,
        "population": pop_name,
        "after_id": after_id,
        "examined": examined,
        "planned": len(planned),
        "written": written,
        "skipped_no_discipline_in_name": no_axis,
        "exhausted": examined < limit,
        "next_cursor": next_cursor,
        "sample": planned[:10],
    }
