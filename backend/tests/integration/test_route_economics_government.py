"""UX-P171 — GET /api/economics must actually SERVE the government distributions.

The sibling unit file (``tests/test_economics_government_distributions.py``)
proves ``_distribution_row`` is correct. A pure-lib guard like that stays green
when someone deletes the CALL, so this file drives the route itself: the
government theme must carry a ``distributions`` key, and the three real
production markets must come back through it.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

FIXTURE = (
    pathlib.Path(__file__).parent.parent
    / "fixtures"
    / "uxp171_economics_government.json"
)


@pytest.fixture(scope="module")
def banked():
    return json.loads(FIXTURE.read_text())

class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars


def _route_market(md):
    """A production government market, shaped the way the route's query yields it."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=md["id"],
        name=md["name"],
        external_id=md["external_id"],
        source="polymarket" if md["external_id"].isdigit() else "kalshi",
        category="news",
        llm_sport_category="economics",
        outcomes=[
            SimpleNamespace(
                id=i,
                name=o["name"],
                current_probability=o["current_probability"],
                probability_change_24h=0,
                rank=o["rank"],
            )
            for i, o in enumerate(md["outcomes"], start=1)
        ],
        resolution_date=now + timedelta(days=200),
        updated_at=now,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


class TestTheRouteActuallyServesThem:
    async def test_government_carries_a_distributions_key(self, client):
        body = (await client.get("/api/economics")).json()
        assert "distributions" in body["themes"]["government"]
        assert body["themes"]["government"]["distributions"] == []

    async def test_the_three_real_markets_come_back_as_distributions(
        self, client, mock_db, banked
    ):
        mock_db.execute.return_value = _MockResult(
            [_route_market(md) for md in banked["_raw_markets"]]
        )
        gov = (await client.get("/api/economics")).json()["themes"]["government"]
        assert gov["count"] == 3
        # The defect in one line: three counted, none rendered.
        assert gov["markets"] == []
        assert len(gov["distributions"]) == 3
        assert {d["kind"] for d in gov["distributions"]} == {"ladder", "brackets"}

    async def test_the_served_ladder_is_not_rescaled_on_the_way_out(
        self, client, mock_db, banked
    ):
        mock_db.execute.return_value = _MockResult(
            [_route_market(md) for md in banked["_raw_markets"]]
        )
        gov = (await client.get("/api/economics")).json()["themes"]["government"]
        ladder = next(
            d for d in gov["distributions"]
            if d["q"] == "Government spending increase in 2026"
        )
        assert sum(r[0] for r in ladder["rows"]) == pytest.approx(571.3, abs=0.5)
