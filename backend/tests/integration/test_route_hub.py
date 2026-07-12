"""Contract tests for the Competition Hub API: GET /api/hub/{competition}.

The hub is a thin, config-driven composition layer (B1 / #1028): an "upcoming"
rail from a per-domain event-concept lister + futures/awards/props sections from
the league-futures endpoint. These tests pin the response shape, the 404 for
unknown competitions, the upcoming-rail wiring, and the props reclassification
(combat-sport game_props that league_futures buries in "matches").
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirror test_route_league_futures for section-shaped mock markets)
# ---------------------------------------------------------------------------


def _mock_outcome(*, outcome_id=1, name="Yes", probability=0.55, rank=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        opening_probability=None,
        probability_change_24h=0,
        rank=rank,
        team_id=None,
    )


def _mock_market(
    *, market_id=1, name="Jones vs Aspinall", external_id="KXUFCFIGHT-26JUL11JONASP",
    category="game_prop", market_tier=5, status="open", outcomes=None,
    canonical_market_key=None,
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        source="kalshi",
        external_id=external_id,
        category=category,
        llm_sport_category="mma",
        llm_league="mma",
        market_tier=market_tier,
        status=status,
        event_id=None,
        outcomes=outcomes or [
            _mock_outcome(outcome_id=market_id * 10, name="Jones", probability=0.6),
            _mock_outcome(outcome_id=market_id * 10 + 1, name="Aspinall", probability=0.4, rank=2),
        ],
        resolution_date=now + timedelta(days=30),
        canonical_market_key=canonical_market_key,
    )


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    # list_ufc_card_concepts uses (await db.execute(...)).all()
    result.all.return_value = []
    return result


# ============================================================================
# Empty DB / basic contract
# ============================================================================


class TestHubContract:
    async def test_mma_returns_200(self, client):
        resp = await client.get("/api/hub/mma")
        assert resp.status_code == 200

    async def test_top_level_keys(self, client):
        body = (await client.get("/api/hub/mma")).json()
        for key in (
            "competition", "label", "title", "emoji", "blurb",
            "sport_key", "upcoming", "sections", "total_markets",
        ):
            assert key in body, f"missing {key}"

    async def test_config_values_echoed(self, client):
        body = (await client.get("/api/hub/mma")).json()
        assert body["competition"] == "mma"
        assert body["label"] == "MMA"
        assert body["sport_key"] == "mma_mixed_martial_arts"

    async def test_slug_is_case_insensitive(self, client):
        assert (await client.get("/api/hub/MMA")).status_code == 200

    async def test_empty_db_shapes(self, client):
        body = (await client.get("/api/hub/mma")).json()
        assert body["upcoming"] == []
        assert body["sections"] == {}
        assert body["total_markets"] == 0

    async def test_unknown_competition_404(self, client):
        resp = await client.get("/api/hub/quidditch")
        assert resp.status_code == 404

    async def test_rejects_post(self, client):
        assert (await client.post("/api/hub/mma")).status_code == 405


class TestBoxingHub:
    """L2-86 (B5): boxing is a config drop — the same generic hub, one HUB_CONFIGS
    entry + combat-engine lister/classifier, no new page code."""

    async def test_boxing_returns_200_and_echoes_config(self, client):
        body = (await client.get("/api/hub/boxing")).json()
        assert body["competition"] == "boxing"
        assert body["label"] == "Boxing"
        assert body["sport_key"] == "boxing_boxing"
        # Same top-level shape as MMA.
        for key in (
            "competition", "label", "title", "emoji", "blurb",
            "sport_key", "upcoming", "sections", "total_markets",
        ):
            assert key in body, f"missing {key}"

    async def test_boxing_case_insensitive(self, client):
        assert (await client.get("/api/hub/Boxing")).status_code == 200


# ============================================================================
# Upcoming rail (event-concept lister)
# ============================================================================


class TestHubUpcoming:
    async def test_upcoming_rail_serialized(self, client, monkeypatch):
        """A card concept flows into `upcoming` with only the public fields."""
        import app.routes.hub as hub

        async def _fake_lister(db, *, limit=20):
            return [{
                "key": "event:ufc:26jul11",
                "name": "UFC 329: Jones vs. Aspinall",
                "domain": "ufc",
                "status": "upcoming",
                "start_date": "2026-07-11T23:00:00+00:00",
                "is_major": True,
                "fight_count": 12,
                "main_event_id": 999,          # internal — must be dropped
                "latest_commence": "whatever",  # internal — must be dropped
            }]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "ufc", _fake_lister)

        body = (await client.get("/api/hub/mma")).json()
        assert len(body["upcoming"]) == 1
        card = body["upcoming"][0]
        assert card["key"] == "event:ufc:26jul11"
        assert card["name"] == "UFC 329: Jones vs. Aspinall"
        assert card["is_major"] is True
        assert card["fight_count"] == 12
        # internal fields not leaked
        assert "main_event_id" not in card
        assert "latest_commence" not in card


# ============================================================================
# Props reclassification (fights vs props out of league_futures "matches")
# ============================================================================


class TestHubPropSplit:
    async def test_props_split_out_of_matches(self, client, mock_db):
        """A KXUFCMOV prop lands in `props` (not `matches`); the fight stays."""
        mock_db.execute.return_value = _scalars_result([
            # A real fight (KXUFCFIGHT, two-sided) → stays in matches
            _mock_market(
                market_id=1,
                name="Jones vs Aspinall",
                external_id="KXUFCFIGHT-26JUL11JONASP",
            ),
            # A method-of-victory prop (KXUFCMOV) → moves to props
            _mock_market(
                market_id=2,
                name="Jones-Aspinall method of victory",
                external_id="KXUFCMOV-26JUL11JONASP",
            ),
        ])

        body = (await client.get("/api/hub/mma")).json()
        sections = body["sections"]

        assert "props" in sections
        prop_ids = {m["id"] for m in sections["props"]}
        assert 2 in prop_ids
        prop = next(m for m in sections["props"] if m["id"] == 2)
        assert prop["prop_type"] == "method"
        assert prop["section"] == "props"

        # The fight is not in props
        assert 2 not in {m["id"] for m in sections.get("matches", [])}
        assert 1 not in prop_ids
