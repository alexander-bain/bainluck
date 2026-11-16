"""A live prop's two stored sides must receive the book the poll just read.

The public Wake Forest-SMU spread kept 19/81 while Gamma quoted 83/17.
The route's fresh read retained that old observation. This offline full-poll
reproduction uses the ingest's suffixed IDs; public payloads do not expose the
stored external IDs, so it proves the code path rather than production linkage.
"""

from datetime import timedelta

import pytest

from tests import test_live_poll_polymarket_event_id_5823 as h

CONDITION = "0xc8c400862a1b9abbc86308b381964c09e05321de39ba7c070fdc4085e9737de5"
EVENT = "1303999"


def specimen(names=("Wake Forest", "SMU")):
    market = h._Market(69747210, CONDITION, group_id="polymarket:" + EVENT)
    event = h._Event(15342468)
    yes = h._Outcome(261532038, market.id, CONDITION + "_yes", names[0])
    no = h._Outcome(261532039, market.id, CONDITION + "_no", names[1])
    for row, price in ((yes, 0.19), (no, 0.81)):
        row.current_probability = price
        row.last_updated = h._now() - timedelta(minutes=90)
    population = h._Population([(market, event)], [yes, no])
    return market, population, yes, no


async def run(
    monkeypatch,
    population,
    names=("Wake Forest", "SMU"),
    *,
    session_type=h._Session,
    **market_values
):
    journal = []
    venue_market = {
        "conditionId": CONDITION,
        "outcomes": list(names),
        "outcomePrices": ["0.83", "0.17"],
        "bestBid": 0.82,
        "bestAsk": 0.84,
        "lastTradePrice": 0.52,
        **market_values,
    }
    session = session_type(population, journal=journal)
    venue = h._PolyService({EVENT: {"markets": [venue_market]}}, journal)
    stats = await h._run(monkeypatch, session, venue)
    assert h._fetches(journal) == [EVENT]
    assert stats["session_recoveries"] == 0
    return stats


@pytest.mark.parametrize(
    "names", [("Wake Forest", "SMU"), ("Over", "Under"), ("Yes", "No")]
)
async def test_one_read_prices_both_existing_sides(monkeypatch, names):
    _, population, yes, no = specimen(names)
    previous = yes.last_updated
    stats = await run(monkeypatch, population, names)
    assert [yes.current_probability, no.current_probability] == pytest.approx(
        [0.83, 0.17]
    )
    assert [yes.current_yes_bid, yes.current_yes_ask] == pytest.approx([0.82, 0.84])
    assert [no.current_yes_bid, no.current_yes_ask] == pytest.approx([0.16, 0.18])
    assert yes.last_updated == no.last_updated > previous
    assert stats["outcomes_updated"] == stats["futures_snapshots_written"] == 2


async def test_a_same_price_read_still_advances_both_observations(monkeypatch):
    _, population, yes, no = specimen()
    yes.current_probability, no.current_probability = 0.83, 0.17
    previous = yes.last_updated
    await run(monkeypatch, population)
    assert yes.current_probability == 0.83
    assert no.current_probability == pytest.approx(0.17)
    assert yes.last_updated == no.last_updated > previous


@pytest.mark.parametrize("names", [("", ""), ("Wake Forest", "Wake Forest")])
async def test_unverified_venue_names_never_price_either_side(monkeypatch, names):
    _, population, yes, no = specimen()
    before = [(o.current_probability, o.last_updated) for o in (yes, no)]
    stats = await run(monkeypatch, population, outcomes=list(names))
    assert [(o.current_probability, o.last_updated) for o in (yes, no)] == before
    assert stats["polymarket_identity_side_mismatch"] == 1
    assert stats["outcomes_updated"] == stats["futures_snapshots_written"] == 0


async def test_a_changed_row_writes_no_snapshot_or_observation(monkeypatch):
    class ChangedRowSession(h._Session):
        async def execute(self, stmt, params=None):
            if h._classify(stmt) == "update" and stmt.table.name == "futures_outcomes":
                return h._Result()
            return await super().execute(stmt, params)

    _, population, yes, no = specimen()
    before = [(o.current_probability, o.last_updated) for o in (yes, no)]
    stats = await run(monkeypatch, population, session_type=ChangedRowSession)
    assert [(o.current_probability, o.last_updated) for o in (yes, no)] == before
    assert stats["polymarket_children_changed_row"] == 2
    assert stats["outcomes_updated"] == stats["futures_snapshots_written"] == 0


@pytest.mark.parametrize(
    "defect", ["missing_no", "wrong_condition", "mixed_keys", "swapped_names"]
)
async def test_identity_refusals_leave_both_values_and_times_untouched(
    monkeypatch, defect
):
    market, population, yes, no = specimen()
    before = [(o.current_probability, o.last_updated) for o in (yes, no)]
    if defect == "missing_no":
        population.outcomes.remove(no)
    elif defect == "wrong_condition":
        market.external_id = "0xother"
    elif defect == "mixed_keys":
        population.outcomes.append(h._Outcome(999, market.id, CONDITION, "Wake Forest"))
    else:
        yes.name, no.name = no.name, yes.name
    stats = await run(monkeypatch, population)
    assert [(o.current_probability, o.last_updated) for o in (yes, no)] == before
    assert stats["outcomes_updated"] == stats["futures_snapshots_written"] == 0
    assert any(
        key.startswith("polymarket_identity_") and value for key, value in stats.items()
    )


async def test_confirmed_winner_and_venue_graded_loser_are_preserved(monkeypatch):
    _, population, yes, no = specimen()
    yes.is_winner, yes.current_probability = True, 1.0
    no.is_winner, no.current_probability = False, 0.0
    no.resolution_source = "api_settlement"
    before = [(o.current_probability, o.last_updated) for o in (yes, no)]
    stats = await run(monkeypatch, population)
    assert [(o.current_probability, o.last_updated) for o in (yes, no)] == before
    assert stats["polymarket_children_settled"] == 2
    assert stats["outcomes_updated"] == stats["futures_snapshots_written"] == 0


async def test_closed_market_is_not_reopened_by_a_quoting_venue(monkeypatch):
    market, population, yes, no = specimen()
    market.status = "resolved"
    before = [(o.current_probability, o.last_updated) for o in (yes, no)]
    stats = await run(monkeypatch, population)
    assert [(o.current_probability, o.last_updated) for o in (yes, no)] == before
    assert stats["polymarket_children_settled"] == 2


@pytest.mark.parametrize("book", [{"bestBid": 0.1, "bestAsk": 0.9}, {"closed": True}])
async def test_a_refused_read_never_claims_a_new_observation(monkeypatch, book):
    _, population, yes, no = specimen()
    before = [(o.current_probability, o.last_updated) for o in (yes, no)]
    stats = await run(monkeypatch, population, **book)
    assert [(o.current_probability, o.last_updated) for o in (yes, no)] == before
    assert stats["polymarket_quotes_refused"] == 2
    assert stats["outcomes_updated"] == stats["futures_snapshots_written"] == 0
