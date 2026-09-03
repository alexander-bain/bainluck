"""The one way to write ``futures_markets.settled_at`` (LINKLOSS-02).

WHY THIS IS A MODULE AND NOT A LINE OF SQL IN EIGHT PLACES
-----------------------------------------------------------

The night of 2026-09-02 the bus asked whether an event merge had dropped 261
links. The count of ``status='open' AND event_id IS NOT NULL`` markets really
had fallen — and there was no way to tell how much of the fall was markets that
simply *settled*, because nothing recorded when a market settled. `created_at`
is ingest time, `resolution_date` is a schedule rather than an observation, and
`updated_at` is bumped by any write at all and is not even bumped by the
settlement writers that go through raw SQL (`onupdate=func.now()` is a Core
construct; ``text("UPDATE futures_markets SET status = 'resolved'")`` never sees
it).

So the transition needs its own column, and the column needs every writer. There
are nine of them across the Kalshi poll, the Kalshi WebSocket, the Polymarket
poll and WebSocket, DataGolf, the futures poll, the winner backfill and two
admin repairs — written by different people at different times in three
different SQL dialects. A convention ("remember to also set settled_at") is
exactly the shape that goes short: a tenth writer lands, nobody notices, and the
column develops a hole that reads as "these never settled".

Everything here exists so that the guard test
``tests/test_link_loss_receipts_linkloss02.py`` can state the rule mechanically:
*a statement that moves ``futures_markets.status`` to ``'resolved'`` also names
``settled_at``.* The guard scans the source for the writes and fails on a write
it cannot see a stamp in — including on a write whose shape it cannot parse,
because a scanner that silently skips what it does not understand is a scanner
that reports zero for the case it was built to catch.

WHY ``COALESCE`` AND NOT A PLAIN ASSIGNMENT
--------------------------------------------

Every settlement writer here is idempotent by design — the Kalshi poll re-reads
its settled window, the winner backfill re-runs its phases, the admin repairs are
meant to be safe to run twice. A plain ``settled_at = NOW()`` would move the
stamp forward on every re-run, so a market that settled on Tuesday would report
having settled at whatever time the last backfill swept it. The first observation
is the one worth keeping, and ``COALESCE`` keeps it without any writer having to
know whether it is the first.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

#: The status value that means "this market settled". One spelling, so the guard
#: has one string to scan for and a writer cannot invent ``'RESOLVED'``.
SETTLED_STATUS = "resolved"


def settled_at_sql(alias: str | None = None) -> str:
    """The ``SET`` fragment for a raw-SQL settlement write.

    ``alias`` is the table alias the statement uses, if any::

        UPDATE futures_markets SET status = 'resolved', {settled_at_sql()}
        UPDATE futures_markets fm SET ..., {settled_at_sql("fm")}

    The unqualified right-hand ``settled_at`` reads the row's pre-update value
    in Postgres, which is what makes the COALESCE keep the first observation.
    """
    column = f"{alias}.settled_at" if alias else "settled_at"
    return f"settled_at = COALESCE({column}, NOW())"


def settled_values(column: Any) -> dict[str, Any]:
    """The ``.values()`` fragment for a Core/ORM settlement write.

    ``column`` is the mapped column itself (``FuturesMarket.settled_at``), taken
    as an argument rather than imported here so this module stays importable
    from anywhere without dragging in ``app.models`` — the same reason
    ``sport_keys.py`` imports nothing.

    Usage::

        update(FuturesMarket)
        .where(...)
        .values(status="resolved", **settled_values(FuturesMarket.settled_at))
    """
    return {"settled_at": func.coalesce(column, func.now())}
