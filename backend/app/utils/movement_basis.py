"""#2408 — `probability_change_24h` as a dated move, and the one expression
every price writer maintains it with.

── THE DEFECT ──────────────────────────────────────────────────────────────

Every delta writer used to store `new - previous` at write time: a PER-WRITE
delta over whatever interval separated the last two writes, published under a
24-hour name. Outcome 1597099 (Kalshi `KXAISTREAMSERIES-27-AMA`) is the
specimen the issue was filed on: written 2026-08-18 at 0.985 and next written
2026-08-28 at 0.270, it served `-0.715` as "the last 24 hours" for the whole
day after the second write — a ten-day step under a one-day label. The sweep's
stale-delta expiry (statement A) only clears a row nothing has written for a
day; it cannot make a FRESH row's per-write number mean a day.

── THE MEANING THE COLUMN NOW HAS ──────────────────────────────────────────

`probability_change_24h = current_probability - basis`, where the basis is a
price this outcome was actually OBSERVED at inside the movement window. The
basis is chosen by `update_max_movement`'s statement A11 with the same
evidentiary bar as the dated bank (A8): the oldest priced in-window
observation, one source, same scale, at least half the window old. Where no
basis qualifies the column is NULL — "we cannot date a move", which every
reader already treats as "no movement".

The sweep re-anchors every ten minutes. Between sweeps the writers below must
keep the SAME basis, which is what this module's expression does: a price
moving from `old` to `new` carries the change from `old - basis` to
`new - basis`, i.e. `change + (new - old)`. So a poll that lands thirty
seconds after the sweep leaves a dated move standing rather than replacing it
with a thirty-second one, and a NULL (no dated evidence) stays NULL until the
sweep can date it.

── THE FRESH-ROW, OLD-PRIOR GUARD ─────────────────────────────────────────

The carried value is only as good as the basis already in the row. A row whose
previous write predates the window cannot hold a basis from inside it — the
sweep never anchors a row in that state, and statement A clears it — so a
writer touching it writes NULL, not a carried number. This is the 1597099
shape at the write: the 08-28 poll meets a row last written on 08-18 and must
not turn ten days into "today". Statement A drains the same population in
bounded, magnitude-ordered batches that skip locked rows, so without this guard
a row A had not reached yet would carry its fossil straight through the next
poll. `last_updated` is read as POLLER ALIVE ("did anything write this row
inside the window"), the reading `tests/test_futures_stamp_semantics.py`
records for this module.

── WHY A SHARED HELPER ────────────────────────────────────────────────────

Four writing sites across three tasks (`kalshi`, `polymarket` x2, `futures`),
and `price_change_stamp`'s module docstring is the standing lesson: a copy of a
predicate that drifts does not throw, it silently starts storing the old
meaning for one provider.

DataGolf is deliberately NOT one of them. #10248 built golf's dated move as its
own arm end to end — a per-write writer (`datagolf._per_write_change`), the
A8-DG bank with its zero-admission mark, and `reader_change_24h` routing every
raw reader through the bank — and A11 skips `source = 'datagolf'` so nothing
here reinterprets that column. The delta-blind price writers
(`futures_price_refresh`, the sockets) still move a price without its change;
A11 re-states those rows on its next run, so their drift is bounded by the
sweep's cadence rather than by A3/A4/A7 noticing it.

All arithmetic is done at the column's own `Numeric(7, 6)`, so the carried
change and the sweep's `current - basis` are the same exact decimal and the
sweep's `IS DISTINCT FROM` does not rewrite every carried row over float noise.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import Interval, case, cast, func, literal
from sqlalchemy.sql.elements import ColumnElement

from app.utils.futures_market_snapshot import DATED_BASIS_WINDOW_HOURS
from app.utils.price_change_stamp import PRICE_NUMERIC


def carried_change_value(
    change_col: Any, current_col: Any, last_updated: Any, new_probability: Any
) -> Any:
    """`probability_change_24h` for an UPDATE / ON CONFLICT DO UPDATE set clause.

    ``change + (new - current)`` when the row was written inside the movement
    window, otherwise NULL. NULL in, NULL out: a row with no dated move keeps
    none, and a row with no current price cannot carry one.

    :param change_col: ``FuturesOutcome.probability_change_24h`` (existing row).
    :param current_col: ``FuturesOutcome.current_probability`` (existing row —
        inside ``ON CONFLICT DO UPDATE`` a bare column renders as the EXISTING
        row, and PostgreSQL evaluates every SET expression of an UPDATE against
        the OLD row, so this is the price the write is about to replace).
    :param last_updated: ``FuturesOutcome.last_updated`` (existing row). Named
        for the column so `tests/test_futures_stamp_semantics.py`'s read-side
        census sees this comparison; it is recorded there as POLLER ALIVE.
    :param new_probability: the price about to be written, a bound value or a
        SQL expression.
    """
    if not isinstance(new_probability, ColumnElement):
        new_probability = literal(new_probability)
    window = literal(timedelta(hours=DATED_BASIS_WINDOW_HOURS), Interval())
    return case(
        (
            last_updated >= func.now() - window,
            cast(change_col, PRICE_NUMERIC)
            + (cast(new_probability, PRICE_NUMERIC) - cast(current_col, PRICE_NUMERIC)),
        ),
        else_=None,
    )


__all__ = ["carried_change_value"]
