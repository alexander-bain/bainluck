"""Recovered event-identity boundaries reach the actual Prop Races reader."""

from datetime import datetime, timezone

import pytest

from tests.integration.test_route_prop_families import (
    _market,
    _mock_team,
    _outcome,
    _routed,
    _screened,
)


@pytest.mark.parametrize("reverse", [False, True])
async def test_prior_conference_result_does_not_settle_or_pad_current_race(
    client, mock_db, reverse
):
    team = _mock_team(team_id=9861, slug="thunder", name="Oklahoma City Thunder")
    current = _market(
        601, "Western Conference Finals MVP Winner", group_id="kalshi:KXNBAWFINMVP-27"
    )
    old = _market(
        602,
        "Western Conference Finals MVP Winner",
        group_id="kalshi:KXNBAWFINMVP-26",
        status="resolved",
    )
    markets = (current, old)
    for market in markets:
        market.llm_sport_category = "basketball"
        market.resolution_date = datetime(2030, 7, 1, tzinfo=timezone.utc)
    rows = [
        (_outcome(6011, "Shai Gilgeous-Alexander", 0.325), current),
        (_outcome(6012, "Chet Holmgren", 0.1), current),
        (_outcome(6021, "Shai Gilgeous-Alexander", 0.0), old),
        (_outcome(6022, "Victor Wembanyama", 1.0, True), old),
    ]
    if reverse:
        rows.reverse()
    mock_db.execute.side_effect = _routed(
        team,
        [rows, [], []],
        markets=[
            _screened(m, [o for o, parent in rows if parent is m]) for m in markets
        ],
    )
    response = await client.get("/api/teams/thunder/prop-families")
    assert response.status_code == 200
    [family] = response.json()["families"]
    assert family["label"] == "Western Conference Finals MVP"
    assert family["entity_count"] == 2
    assert {r["entity"]: r["probability"] for r in family["rows"]} == {
        "Shai Gilgeous-Alexander": 0.325,
        "Chet Holmgren": 0.1,
    }
    assert {r["market_id"] for r in family["rows"]} == {601}
    assert {r["outcome_id"] for r in family["rows"]} == {6011, 6012}
    assert all(not r["settled"] and r["result"] is None for r in family["rows"])
    assert all(not any(key.startswith("_") for key in r) for r in family["rows"])
