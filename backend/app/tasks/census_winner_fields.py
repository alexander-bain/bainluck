"""CAL-P006 (#1527): bounded census of winner-field coherence violations.

Two defect classes on **mutually-exclusive** markets, both of which #1527 found on
the same rows:

``multi_winner``      more than one leg is ``is_winner`` — a single-winner
                      partition crowned twice. Every extra winner is one
                      perfectly-confident wrong forecast in the calibration curve.
``incoherent_field``  more than one leg is near-certain — the field sums far past
                      100%, so it is not a price at all.

**Why this is an endpoint and not a query.** #1527's own scope note records that
the unscoped aggregate was "cancelled by the server's statement timeout three
times", which is why its census had to be narrowed to soccer and the true
population was left unmeasured. Re-measuring it ad-hoc failed the same way twice
more while staging this queue. That is CAL-P002B's lesson exactly: bound the scan
BEFORE the work, not after.

So the scan is bounded by a **market-id window**, not by a defect count. Each call
walks at most ``limit`` markets by primary key and reports what it found in that
window plus ``next_offset``. A driver walks the whole table in bounded steps and
the population is the sum — no single statement can run long enough to be
cancelled, and progress is resumable rather than restarting on the same rows (the
non-terminating loop CAL-P002B had to fix).

Read-only by construction: ``apply`` is accepted for rail-signature compatibility
and ignored. Repairing the existing population is a WRITE with its own authority
question (gotcha #21 — no bulk ``is_winner`` reset without a source that can
immediately re-resolve) and is deliberately not in this module.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.utils.winner_field_coherence import NEAR_CERTAIN_PROB

logger = logging.getLogger(__name__)

# Markets walked per call. 5,000 keeps a window comfortably under the statement
# timeout even when every market in it is wide; the caller can lower it.
DEFAULT_SCAN = 5000
MAX_SCAN = 50000

# Per-window statement timeout. Fails this window fast instead of holding the
# 30s router wall open and returning an H12 with no evidence at all.
_WINDOW_TIMEOUT = "20s"

# A defect whose outcome rows were written inside this horizon is evidence the
# producer is still LIVE, not a frozen legacy artifact — the distinction #1527
# needed and the one the sentinel alarms on.
FRESH_WRITE_HOURS = 48

_BOUNDS_SQL_ASC = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n
    FROM (SELECT id FROM futures_markets WHERE id > :cursor
          ORDER BY id ASC LIMIT :scan) w
"""

_BOUNDS_SQL_DESC = """
    SELECT MIN(id) AS lo, MAX(id) AS hi, COUNT(*) AS n
    FROM (SELECT id FROM futures_markets WHERE id < :cursor
          ORDER BY id DESC LIMIT :scan) w
"""

_DEFECT_SQL = """
    WITH win AS (
        SELECT id FROM futures_markets
        WHERE id >= :lo AND id <= :hi
    )
    SELECT m.id, m.source, m.status, m.llm_sport_category, m.llm_league,
           m.market_type, m.name, m.resolution_date,
           COUNT(*)                                               AS legs,
           COUNT(*) FILTER (WHERE o.is_winner)                     AS winners,
           COUNT(*) FILTER (WHERE o.current_probability >= :bar)   AS near_certain,
           SUM(o.current_probability)                              AS field_sum,
           MAX(o.last_updated)                                     AS last_written
    FROM win
    JOIN futures_markets m ON m.id = win.id
    JOIN futures_outcomes o ON o.market_id = m.id
    WHERE m.mutually_exclusive = true
    GROUP BY m.id, m.source, m.status, m.llm_sport_category, m.llm_league,
             m.market_type, m.name, m.resolution_date
    HAVING COUNT(*) > 1
       AND (COUNT(*) FILTER (WHERE o.is_winner) > 1
            OR COUNT(*) FILTER (WHERE o.current_probability >= :bar) > 1)
    ORDER BY m.id
"""


def classify_defect(winners: int, near_certain: int) -> list[str]:
    """Which of the two invariants this market violates (it may be both)."""
    classes = []
    if winners > 1:
        classes.append("multi_winner")
    if near_certain > 1:
        classes.append("incoherent_field")
    return classes


def summarize(rows, *, fresh_cutoff=None) -> dict:
    """Pure roll-up of census rows — shared by the endpoint and its tests.

    ``fresh_cutoff`` is an aware datetime; rows written at or after it count as
    evidence the producer is still running.
    """
    by_class: dict[str, int] = {}
    by_category: dict[str, int] = {}
    fresh = 0
    bogus_winners = 0
    for r in rows:
        for c in classify_defect(r["winners"], r["near_certain"]):
            by_class[c] = by_class.get(c, 0) + 1
        cat = r.get("llm_sport_category") or "(none)"
        by_category[cat] = by_category.get(cat, 0) + 1
        if r["winners"] > 1:
            # Every winner past the first is a bogus one.
            bogus_winners += r["winners"] - 1
        lw = r.get("last_written")
        if fresh_cutoff is not None and lw is not None and lw >= fresh_cutoff:
            fresh += 1
    return {
        "defect_markets": len(rows),
        "by_class": by_class,
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "bogus_winner_outcomes": bogus_winners,
        "written_recently": fresh,
    }


async def census(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
    newest_first: bool | None = None,
) -> dict:
    """Walk one bounded market-id window and report coherence violations.

    ``limit``        markets to walk in this call (NOT a defect cap).
    ``offset``       market-id cursor, exclusive. Omit to start at the end
                     being walked. Pass the returned ``next_offset`` to continue.
    ``newest_first`` walk descending by id — newest markets first, which is what
                     a regression guard wants to know about.
    ``apply``        ignored; this census never writes.
    """
    from datetime import datetime, timedelta, timezone

    scan = min(int(limit or DEFAULT_SCAN), MAX_SCAN)
    descending = bool(newest_first)

    if offset is not None:
        cursor = int(offset)
    else:
        # Start past both ends of the id space so the first window is the true
        # oldest (ascending) or newest (descending) slice.
        cursor = 2**62 if descending else 0

    await session.execute(text(f"SET LOCAL statement_timeout = '{_WINDOW_TIMEOUT}'"))

    bounds = (
        await session.execute(
            text(_BOUNDS_SQL_DESC if descending else _BOUNDS_SQL_ASC),
            {"cursor": cursor, "scan": scan},
        )
    ).mappings().first()

    lo, hi, walked = bounds["lo"], bounds["hi"], int(bounds["n"] or 0)

    if not walked:
        return {
            "census": "winner-field-coherence",
            "markets_walked": 0,
            "exhausted": True,
            "next_offset": None,
            "near_certain_bar": NEAR_CERTAIN_PROB,
            "defect_markets": 0,
            "by_class": {},
            "by_category": {},
            "bogus_winner_outcomes": 0,
            "written_recently": 0,
            "fresh_write_hours": FRESH_WRITE_HOURS,
            "defects": [],
        }

    result = (
        await session.execute(
            text(_DEFECT_SQL), {"lo": lo, "hi": hi, "bar": NEAR_CERTAIN_PROB}
        )
    ).mappings().all()

    rows = [dict(r) for r in result]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_WRITE_HOURS)
    roll = summarize(rows, fresh_cutoff=cutoff)

    defects = [
        {
            "market_id": r["id"],
            "source": r["source"],
            "status": r["status"],
            "category": r["llm_sport_category"],
            "league": r["llm_league"],
            "market_type": r["market_type"],
            "name": (r["name"] or "")[:120],
            "resolution_date": str(r["resolution_date"]) if r["resolution_date"] else None,
            "legs": r["legs"],
            "winners": r["winners"],
            "near_certain": r["near_certain"],
            "field_sum": float(r["field_sum"]) if r["field_sum"] is not None else None,
            "last_written": str(r["last_written"]) if r["last_written"] else None,
            # Per-row freshness, not just the roll-up count: the sentinel fails on
            # rows a producer is STILL stamping, and needs to name them.
            "written_recently": bool(
                r["last_written"] is not None and r["last_written"] >= cutoff
            ),
            "classes": classify_defect(r["winners"], r["near_certain"]),
        }
        for r in rows
    ]

    return {
        "census": "winner-field-coherence",
        "markets_walked": walked,
        "window": {"lo": lo, "hi": hi, "descending": descending},
        # Exclusive cursor for the next call; None once the window came back short
        # of the scan size, which means we reached the end of the id space.
        "next_offset": (lo if descending else hi) if walked == scan else None,
        "exhausted": walked < scan,
        "near_certain_bar": NEAR_CERTAIN_PROB,
        "fresh_write_hours": FRESH_WRITE_HOURS,
        **roll,
        "defects": defects,
    }
