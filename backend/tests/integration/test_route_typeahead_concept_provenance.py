"""#1846 — the ROUTE's concept-provenance line, exercised through the endpoint.

This file exists because a mutation gate said it had to.

LAT-P051 replaced typeahead's blanket `_derived = True` with a per-row predicate
and wrote unit tests for it. Those tests computed the flag themselves —
``row["_derived"] = not _query_names_typeahead_concept(q, row)`` — which asserts
the predicate and says nothing whatever about the route. The mutation plan proved
it: restoring the blanket flag in `typeahead_search`, and separately INVERTING the
predicate there, both **SURVIVED** a 148-test oracle set. The defect could have
been reintroduced verbatim, in the one line the change is about, without a single
test noticing.

That is the same seam LAT-P048 found when `_ta_evidence` was a closure, and the
same lesson gotcha #131 banks: plan the mutations before you trust the tests,
because the missing instrument is what the plan finds.

So the assertions here go through `GET /api/events/typeahead` against a seeded
session, and each one names the mutant it kills.

**Non-vacuity.** The shared `client` fixture answers every query empty, so a loop
over suggestions is a loop over nothing. `TestTheSeedIsReal` fails loudly if the
seeded market stops reaching the concept loop, and every test below asserts a
non-empty bucket before it asserts anything about ordering.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

pytestmark = pytest.mark.asyncio


def _outcome(name: str, prob: float, oid: int):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None, sort_order=oid,
        # Q480: the display path reads `external_id` to drop a `_yes`/`_no` leg
        # duplicating a bare rung. None = not a leg (pass-through).
        external_id=None,
    )


def _market(*, mid: int, name: str, category: str, external_id: str, volume=10_000.0):
    """A futures market shaped as `typeahead_search` reads it."""
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id,
        llm_sport_category=category,
        category=category,
        market_tier=1,
        market_type="winner",
        sport_id=None,
        volume=volume,
        status="open",
        resolution_date=None,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        outcomes=[
            _outcome("Aryna Sabalenka", 0.28, mid * 10 + 1),
            _outcome("Iga Swiatek", 0.24, mid * 10 + 2),
            _outcome("Coco Gauff", 0.19, mid * 10 + 3),
        ],
    )


#: The exact market production holds for the `us open` gold probe, verified
#: against GET /api/events/search on v3807 (2026-08-14). Its derived concept id
#: is `concept:event:tennis:2026-women-s-us-open-winner-tennis`, which is that
#: probe's expected answer — and on that read production dropped it as derived
#: and answered with the market underneath instead.
US_OPEN_MARKET = "2026 Women’s US Open Winner (Tennis)"

#: The over-match family ruling 041 was written against. An Emmys market
#: FTS-matches `world series` on a nominee token; the concept must stay dead.
EMMYS_MARKET = "Emmy Winner: Outstanding Drama Series"


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.unique.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


def _seeded_session(markets):
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if "futures_markets" in sql and "SELECT" in sql.upper():
            result.scalars.return_value.unique.return_value.all.return_value = list(markets)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


def _client_for(markets, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _seeded_session(markets)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app


@pytest.fixture
async def tennis_client(monkeypatch):
    app = _client_for(
        [_market(mid=114160, name=US_OPEN_MARKET, category="tennis",
                 external_id="KXUSOPENW-26")],
        monkeypatch,
    )
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def emmys_client(monkeypatch):
    app = _client_for(
        [_market(mid=99001, name=EMMYS_MARKET, category="entertainment",
                 external_id="KXEMMY-26")],
        monkeypatch,
    )
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


def _types(body):
    return [s.get("type") for s in body["suggestions"]]


def _concepts(body):
    return [s for s in body["suggestions"] if s.get("type") == "event_concept"]


# ---------------------------------------------------------------------------


class TestTheSeedIsReal:
    async def test_the_market_reaches_the_dropdown(self, tennis_client):
        body = (await tennis_client.get("/api/events/typeahead?q=us open")).json()
        assert body["suggestions"], "empty dropdown — every assertion below is vacuous"
        assert US_OPEN_MARKET in [s.get("text") for s in body["suggestions"]], (
            "the seeded market did not reach the futures pool, so the concept "
            "loop never ran and this file is measuring nothing"
        )

    async def test_the_emmys_seed_reaches_the_dropdown(self, emmys_client):
        body = (await emmys_client.get("/api/events/typeahead?q=world series")).json()
        assert body["suggestions"], "empty dropdown — the over-match test is vacuous"


class TestTheConceptSurvivesWhenTheQueryNamesIt:
    """Kills M1 (blanket flag restored) and M3 (wrong shape adapter)."""

    async def test_the_concept_is_returned(self, tennis_client):
        body = (await tennis_client.get("/api/events/typeahead?q=us open")).json()
        concepts = _concepts(body)
        assert concepts, (
            "the concept was dropped — this is #1846 exactly: the market minted "
            f"it, the blanket flag made it UNRANKABLE, and {US_OPEN_MARKET!r} "
            "answered in its place"
        )
        assert concepts[0]["event_key"].startswith("event:tennis:")

    async def test_the_concept_leads_the_dropdown(self, tennis_client):
        """Kind order puts a concept above the market it aggregates (ruling 041),
        so recovering it is not enough — it has to win."""
        body = (await tennis_client.get("/api/events/typeahead?q=us open")).json()
        assert body["suggestions"], "vacuous"
        assert _types(body)[0] == "event_concept"


class TestTheOverMatchFamilyStaysDead:
    """Kills M2 (predicate inverted) and M4 (core always True).

    `world series` must not answer with an Emmys concept. This is one of the four
    measured failures (2026-08-12 21:48Z) that owned-evidence-only exists for, and
    it is the half of the fix that is easy to lose while making the other half
    work.
    """

    async def test_no_awards_concept_for_world_series(self, emmys_client):
        body = (await emmys_client.get("/api/events/typeahead?q=world series")).json()
        assert body["suggestions"], "vacuous"
        assert not _concepts(body), (
            "an awards concept came back for 'world series' — the over-match "
            f"defence is gone: {[c.get('event_key') for c in _concepts(body)]}"
        )

    @pytest.mark.parametrize("query", ["super bowl", "wwe", "stranger things"])
    async def test_the_rest_of_the_family(self, emmys_client, query):
        body = (await emmys_client.get(f"/api/events/typeahead?q={query}")).json()
        assert not _concepts(body), f"{query!r} surfaced an unowned concept"


class TestTheEndpointStillHidesItsRankingInputs:
    """The flag is ranking evidence, never payload — asserted at the seam where
    it is now computed per row rather than set once."""

    async def test_derived_is_not_on_the_wire(self, tennis_client):
        body = (await tennis_client.get("/api/events/typeahead?q=us open")).json()
        assert body["suggestions"], "vacuous"
        for s in body["suggestions"]:
            assert "_derived" not in s
            assert "_aliases" not in s
            assert "_outcome_names" not in s
