"""#10331 — /weather's event lists stop serving questions whose period is over.

On production 2026-10-03 12:44Z the Seismic activity list served "Will a 9.0+
earthquake occur worldwide by September 30? <1%" and the Tornadoes list "US
Tornadoes in September 2026 · 50 - 74 · 95%". Both windows had closed; the
venue just had not graded them, so `resolution_date` kept them in the query and
they read as live odds. /featured already drops such rows through
`is_title_implied_stale` (#883 L2-56); /events applied no title rule at all.

"…by end of September" (the featured lead) is the helper's own gap — part (a),
discover's. The last test pins that /events reads the SAME helper, so when the
helper learns that phrasing these lists drop it with no second change.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.routes.weather as weather
from app.routes.weather import get_events
from tests.integration.test_route_weather import _market, _outcome, _query_result

# The clock of the production read.
OCT_3 = datetime(2026, 10, 3, 12, 40, tzinfo=timezone.utc)
# A clock inside every specimen's period, for the control.
SEP_20 = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

QUAKE_SEP_30 = "Will a 9.0+ earthquake occur worldwide by September 30?"
TORNADOES_SEP = "US Tornadoes in September 2026"
# Healthy siblings: open periods on both clocks.
TORNADOES_OCT = "US Tornadoes in October 2026"
MARIE = "Hurricane Marie category?"
VIRGINIA = "Will a hurricane make landfall in Virginia by November 30, 2026?"


def _db(markets):
    db = MagicMock()
    db.execute = AsyncMock(return_value=_query_result(markets))
    return db


def _yes(market_id, name, yes):
    return _market(
        market_id=market_id,
        name=name,
        outcomes=[_outcome("Yes", yes, outcome_id=market_id * 10),
                  _outcome("No", 1 - yes, outcome_id=market_id * 10 + 1)],
    )


def _board():
    return [
        _yes(59128645, QUAKE_SEP_30, 0.004),
        _yes(59917980, TORNADOES_SEP, 0.95),
        _yes(61000001, TORNADOES_OCT, 0.4),
        _yes(61000002, MARIE, 0.3),
        _yes(59159633, VIRGINIA, 0.05),
    ]


def _served(payload):
    return {g: [row["q"] for row in rows] for g, rows in payload.items()}


@pytest.mark.asyncio
async def test_past_period_rows_are_not_served_on_october_3():
    served = _served(await get_events(_db(_board()), now=OCT_3))
    all_qs = [q for qs in served.values() for q in qs]
    assert QUAKE_SEP_30 not in all_qs
    assert TORNADOES_SEP not in all_qs


@pytest.mark.asyncio
async def test_open_period_siblings_survive_the_drop():
    served = _served(await get_events(_db(_board()), now=OCT_3))
    assert served == {
        "hurricane": [MARIE, VIRGINIA],
        "earthquake": [],
        "tornadoes": [TORNADOES_OCT],
    }


@pytest.mark.asyncio
async def test_control_the_same_rows_are_served_while_their_period_is_open():
    # The drop is the clock, not an unparseable title: on 9/20 every row serves.
    served = _served(await get_events(_db(_board()), now=SEP_20))
    assert sorted(q for qs in served.values() for q in qs) == sorted(
        [QUAKE_SEP_30, TORNADOES_SEP, TORNADOES_OCT, MARIE, VIRGINIA]
    )


@pytest.mark.asyncio
async def test_events_read_the_shared_title_helper(monkeypatch):
    # Whatever the shared helper calls stale, /events drops — so part (a),
    # teaching it "by end of <Month>", reaches these lists unchanged.
    end_of_sep = "Where will a 6.0+ magnitude earthquake occur by end of September?"
    seen = []

    def fake_helper(name, category, now):
        seen.append(now)
        return "stale_test" if name == end_of_sep else None

    monkeypatch.setattr(weather, "is_title_implied_stale", fake_helper)
    served = _served(await get_events(
        _db([_yes(59953565, end_of_sep, 1.0), _yes(61000002, MARIE, 0.3)]),
        now=OCT_3,
    ))
    assert served["earthquake"] == []
    assert served["hurricane"] == [MARIE]
    assert seen and all(n == OCT_3 for n in seen)
