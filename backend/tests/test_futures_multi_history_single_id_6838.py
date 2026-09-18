"""#6838 — a stage tab with ONE market gets a chart, not a 500.

`/api/futures/multi-history` is the only path a league page's stage tabs use
(`futures.py`'s own note at the `_STAGE` helpers). Its single-id branch
delegates to `get_futures_history`, and it used to delegate like this:

    return await get_futures_history(parsed_ids[0], hours=hours, top_n=top_n, db=db)

A DIRECT PYTHON CALL DOES NOT GET FASTAPI'S RESOLUTION. The omitted `outcome_id`
arrives as the unresolved ``Query(None, ...)`` default OBJECT, which is not None
and is truthy, so `if outcome_id:` took the single-outcome branch and filtered
the chart to ``[Query(...)]`` — an id no column can be compared against.
Measured on production 2026-09-18: `?market_ids=7&hours=168` returned **500**.

Why it needs a guard rather than a one-line memory: #4992 widened the snapshot
read from `outcome_id IN (...)` to `market_id = ...`, which stops the bogus id
reaching SQL at all — so the same mistake now returns an EMPTY chart instead of
an error, and nothing would say so. The regression this file catches is silent.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.routes import futures as futures_route


T0 = datetime(2026, 9, 18, 1, 0, 0, tzinfo=timezone.utc)


def _outcome(oid, name, prob):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.external_id = name
    o.current_probability = prob
    o.is_winner = None
    o.resolution_source = None
    return o


def _snapshot(oid, book, prob, stamp):
    s = MagicMock()
    s.outcome_id = oid
    s.bookmaker = book
    s.probability = prob
    s.captured_at = stamp
    s.yes_bid = None
    s.yes_ask = None
    s.last_price = None
    return s


class _Result:
    def __init__(self, rows=(), scalar=None):
        self._rows, self._scalar = list(rows), scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar


class _Session:
    """Answers each ``execute`` from a queue; the last entry repeats."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


@pytest.mark.asyncio
async def test_one_market_id_returns_the_series_it_would_have_500d_on():
    """The reader's stage tab draws its lines."""
    outcomes = [_outcome(1, "Team A", 0.55), _outcome(2, "Team B", 0.45)]
    market = MagicMock()
    market.id = 7
    market.name = "AL East Winner"
    market.outcomes = outcomes
    market.mutually_exclusive = True
    market.market_metadata = None
    market.status = "open"

    rows = []
    for k in range(4):
        stamp = T0 - timedelta(hours=k)
        rows.append(_snapshot(1, "draftkings", 0.58, stamp))
        rows.append(_snapshot(2, "draftkings", 0.47, stamp))

    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_multi_market_history(
        market_ids="7", hours=168, top_n=10, db=db
    )

    series = {o["outcome_id"]: o["history"] for o in payload["outcomes"]}
    # BOTH halves of the assertion are the defect: the pre-#4992 handler raised
    # on the bogus id, and the post-#4992 handler returns this payload with
    # every series empty. Neither draws a chart.
    assert set(series) == {1, 2}, "the stage tab lost its outcomes"
    assert all(len(h) == 4 for h in series.values()), "the stage tab drew no line"

    # And the delegated call is on #4992's scale, not the raw book price: a
    # column of 0.58/0.47 sums to 1.05 and de-vigs to 0.552.
    assert series[1][0]["probability"] == pytest.approx(0.552, abs=0.001)
