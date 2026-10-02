"""#10243: each Games This Week team row names the outcome its number came from.

WHAT A READER SAW, on production 2026-10-02 ~23:00Z, `/futures/86832` at
390px: the hero and All Outcomes table printed the verified title number
(Bills 13%) while Games This Week, further down the same page, printed the
source value (Bills 11%). One page, two numbers for one team.

The strip's rows had no identity, so the page could not print the row it
already holds. The route now serves `outcome_id` beside `outcome_name`, and the
page takes that outcome's number from its own detail by id.

Arms: a team field carries each team's own outcome id; a player field carries
the LEADING player's id (the one whose name and price it serves), in both
insertion orders, so the id can never belong to a different row than the price.
"""

import pytest

from app.routes.futures import get_related_events

from tests.test_futures_related_events_player_field_8627 import (  # noqa: E402
    _field,
    _linked,
)
from tests.test_futures_related_events_sport_guard import (  # noqa: E402
    _FakeSession,
    _events as _ws_events,
    _market as _ws_market,
)


@pytest.mark.asyncio
async def test_a_team_row_carries_its_own_outcome_id():
    market = _ws_market()
    payload = await get_related_events(1, db=_FakeSession(market, _ws_events()))

    (event,) = payload["events"]
    (dodgers,) = event["linked_teams"]
    (expected,) = [o for o in market.outcomes if o.name == dodgers["outcome_name"]]
    assert dodgers["outcome_id"] == expected.id


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["favourite_first", "favourite_last"])
async def test_a_player_field_row_carries_the_id_of_the_price_it_serves(order):
    field = _field()
    if order == "favourite_last":
        field = list(reversed(field))

    rows = await _linked(field)

    assert rows["Chicago Cubs"]["outcome_id"] == 21, rows["Chicago Cubs"]
    assert rows["Boston Red Sox"]["outcome_id"] == 23, rows["Boston Red Sox"]
