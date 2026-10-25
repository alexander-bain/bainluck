"""Different NBA seasons stay separate through the actual HTTP reader.

Database, provider quotes and Redis are doubles; prices and IDs are synthetic.
This does not establish cache adoption or served reader acceptance.
"""

from datetime import datetime, timezone

import pytest

from tests.integration.test_route_prop_families import (
    _market,
    _mock_team,
    _outcome,
    _routed,
    _screened,
)


@pytest.mark.parametrize("previous_status", ["open", "resolved"])
async def test_prior_season_does_not_replace_current_race(
    client, mock_db, previous_status
):
    team = _mock_team(team_id=9860, slug="thunder", name="Oklahoma City Thunder")
    now = _market(501, "Pro Basketball MVP Winner", group_id="kalshi:KXNBAMVP-27")
    old = _market(
        502,
        "NBA: 2025-26 MVP",
        source="polymarket",
        group_id="polymarket:previous",
        status=previous_status,
    )
    settled = previous_status == "resolved"
    for market in (now, old):
        market.llm_sport_category = "basketball"
        market.resolution_date = datetime(2030, 7, 1, tzinfo=timezone.utc)
    rows = [
        (_outcome(5011, "Shai Gilgeous-Alexander", 0.145), now),
        (_outcome(5012, "Chet Holmgren", 0.01), now),
        (
            _outcome(5021, "Shai Gilgeous-Alexander", 1.0 if settled else 0.7, settled),
            old,
        ),
        (_outcome(5022, "Chet Holmgren", 0.0 if settled else 0.1), old),
    ]
    mock_db.execute.side_effect = _routed(
        team,
        [rows, [], []],
        markets=[
            _screened(m, [o for o, parent in rows if parent is m]) for m in (now, old)
        ],
    )
    response = await client.get("/api/teams/thunder/prop-families")
    assert response.status_code == 200
    families = response.json()["families"]
    assert len(families) == 2
    current = next(f for f in families if f["label"].endswith("2026–27"))
    previous = next(f for f in families if f["label"].endswith("2025–26"))
    assert {r["market_id"] for r in current["rows"]} == {501}
    assert {r["outcome_id"] for r in current["rows"]} == {5011, 5012}
    assert {r["entity"]: r["probability"] for r in current["rows"]} == {
        "Shai Gilgeous-Alexander": 0.145,
        "Chet Holmgren": 0.01,
    }
    assert all(not r["settled"] for r in current["rows"])
    assert {r["market_id"] for r in previous["rows"]} == {502}
    assert all(r["settled"] == settled for r in previous["rows"])
    assert all("_award_season" not in r for f in families for r in f["rows"])
