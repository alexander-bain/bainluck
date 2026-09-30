"""#9849 — the event page prints the threshold a single-leg Kalshi market asks.

THE DEFECT, SEEN ON PRODUCTION (Wed 9/30 14:40Z, 390px, /events/15320289,
Phillies @ Braves, WC Game 1, final 5–3). Additional Markets read

    Philadelphia vs Atlanta: 1st Inning Total — Yes · Lost
    Will there be a run scored in the first inning? — Yes · Won

which contradicts itself as printed. The first market is
`KXMLBINNINGTOTAL-26SEP291400PHIATL-1` and its stored
`market_metadata.threshold_label` is "Over 1.5 runs in the 1st inning". One run
scored, so both cards were right. #9383 routed search, `/futures/{id}` and My
Stuff through `reader_outcome_name(..., market_threshold_label(market))`;
`GET /api/events/{id}/game-markets` served the bare `Yes`.

The controls: a market with no label keeps `Yes` (so the specimen assertion
cannot pass on a serializer that renames everything), and a plain Yes/No
binary beside it is served exactly as stored.
"""

import asyncio

import pytest

from app.routes.events import _game_markets_cache, get_game_markets
from tests.test_leg_copy_parent_leaves_game_markets_5273 import (
    _db_for,
    _make_event,
    _make_market,
    _make_outcome,
)

LABEL = "Over 1.5 runs in the 1st inning"
TICKER = "KXMLBINNINGTOTAL-26SEP291400PHIATL-1"
INNING_TOTAL = "Philadelphia vs Atlanta: 1st Inning Total"
RUN_IN_FIRST = "Will there be a run scored in the first inning?"


def _event():
    event = _make_event()
    event.id = 15320289
    event.home_team_name = "Atlanta Braves"
    event.away_team_name = "Philadelphia Phillies"
    return event


def _kalshi(market, metadata):
    market.source = "kalshi"
    market.group_id = None
    market.market_metadata = metadata
    return market


def _payload(label_metadata):
    _game_markets_cache.clear()
    event = _event()
    inning_total = _kalshi(
        _make_market(id=63153640, name=INNING_TOTAL, external_id=TICKER),
        label_metadata,
    )
    run_in_first = _kalshi(
        _make_market(
            id=63153641,
            name=RUN_IN_FIRST,
            external_id="KXMLBRFI-26SEP291400PHIATL",
        ),
        {},
    )
    for m in (inning_total, run_in_first):
        m.event_id = event.id
    outcomes = [
        _make_outcome(id=238113940, market_id=inning_total.id, name="Yes",
                      probability=0.18, external_id=TICKER),
        _make_outcome(id=238113941, market_id=run_in_first.id, name="Yes",
                      probability=0.47, external_id="KXMLBRFI-26SEP291400PHIATL-Y"),
        _make_outcome(id=238113942, market_id=run_in_first.id, name="No",
                      probability=0.53, external_id="KXMLBRFI-26SEP291400PHIATL-N"),
    ]
    markets = [inning_total, run_in_first]
    return asyncio.run(
        get_game_markets(event.id, _db_for(event, markets, outcomes))
    )


def _names(payload, market_name):
    return [
        r["outcome_name"] for r in payload["other"] if r["market_name"] == market_name
    ]


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def test_the_specimen_prints_the_venues_threshold_not_a_bare_yes():
    payload = _payload({"threshold_label": LABEL})
    assert _names(payload, INNING_TOTAL) == [LABEL]


def test_control_a_market_with_no_label_keeps_its_yes():
    # The strawman: without the stored label the row is served as stored, so the
    # specimen assertion above is about the label, not about renaming `Yes`.
    payload = _payload({})
    assert _names(payload, INNING_TOTAL) == ["Yes"]


def test_control_a_plain_yes_no_binary_beside_it_is_untouched():
    payload = _payload({"threshold_label": LABEL})
    assert sorted(_names(payload, RUN_IN_FIRST)) == ["No", "Yes"]


def test_the_row_keeps_its_price_and_market():
    payload = _payload({"threshold_label": LABEL})
    (row,) = [r for r in payload["other"] if r["market_name"] == INNING_TOTAL]
    assert row["probability"] == 0.18
    assert row["_market_id"] == 63153640
