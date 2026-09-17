"""THE PHANTOM RUNG LEAVES THE RESPONSE — `GET /api/events/search`, #6676.

The unit file (`tests/test_search_empty_book_6676.py`) pins the predicates and
the builder's placement. This one pins what a reader can see, at the route, for
the reason #6327's twin states and CERT-718 wrote before it: the ship is a claim
about WHICH ROWS A RESPONSE CARRIES, and a builder that filters correctly while
the route ships the card anyway is green on the unit file alone.

WHAT PRODUCTION SERVED, `?q=lakers`, 2026-09-17 (the seed below is this card):

    57777176  polymarket  tier 5  "NBA: Steph Curry Next Team"
        Golden State Warriors  0.74   on 0.52/0.96    <- real
        Atlanta Hawks          0.48   on 0.01/0.95    <- phantom
        Brooklyn Nets          0.48   on 0.01/0.95    <- phantom
        Phoenix Suns           0.48   on 0.01/0.95    <- phantom
        Chicago Bulls          0.48   on 0.01/0.95    <- phantom

Four mutually exclusive teams at one manufactured number, and the payload carries
no bid/ask, so nothing on the reader's screen separates them from the 0.74.

THE FOUR CLASSES BELOW, one risk each:

1. THE RUNGS GO, AND THE HONEST ONES ARRIVE. A phantom sits at ~0.50 by
   construction, so it outranks every real longshot in the `[:limit]` slice. The
   fix is only a fix if the card refills from the market's own legs.
2. A CARD WITH NOTHING LEFT IS WITHDRAWN — and, like #6327's, it must not walk
   back in through a FAMILY card, which composes from the wider deduped set.
3. THE PAGE REFILLS. A withdrawal must cost the reader no answer: a priced
   market below the fold takes the vacated slot.
4. A FULLY PRICED PAGE IS UNTOUCHED. The control that separates "the page was
   made truthful" from "the page was made shorter" (#2646 asks for it by name),
   and the one that would catch a blanket suppression of 50% — the single
   constraint this ship carries.

RED-FIRST, MEASURED — `git checkout origin/master -- app/routes/events.py`, this
file alone (the unit file cannot run on that arm: it imports predicates master
does not have, and a collection error is exit 2, never a red):

    4 failed, 5 passed

The four reds are both assertions in class 1, the withdrawal in class 2 and the
refill in class 3. The five greens are the two seed checks, both class-4
controls, and `test_the_priced_market_beside_it_is_still_served` — which is green
on BOTH arms by construction, because it asserts what must not change. That split
is the file's own control: the page was made truthful, not shorter.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

_asyncio = pytest.mark.asyncio


def _outcome(oid, name, prob, bid=None, ask=None):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, current_yes_bid=bid, current_yes_ask=ask,
        rank=None, sort_order=oid, external_id=f"OUT-{oid}",
    )


def _market(*, mid, name, volume, outcomes, tier=5, category="basketball_nba",
            external_id=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id or f"PM-{mid}",
        llm_sport_category=category,
        category=category,
        market_tier=tier,
        market_type=None,
        sport=None,
        sport_id=None,
        source="polymarket",
        volume=volume,
        status="open",
        resolution_date=(now + timedelta(days=20)).date(),
        updated_at=now,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        mutually_exclusive=True,
        outcomes=outcomes,
    )


#: Market 57777176 as production stored it: one real leg, four phantoms sharing a
#: 0.48, and three honest longshots the `[:limit]` slice never reached.
def _curry_market():
    return _market(
        mid=57777176,
        name="NBA: Steph Curry Next Team",
        volume=900_000.0,
        outcomes=[
            _outcome(214465500, "Golden State Warriors", 0.74, 0.52, 0.96),
            _outcome(214465539, "Brooklyn Nets", 0.48, 0.01, 0.95),
            _outcome(214465537, "Atlanta Hawks", 0.48, 0.01, 0.95),
            _outcome(214465560, "Phoenix Suns", 0.48, 0.01, 0.95),
            _outcome(214465541, "Chicago Bulls", 0.48, 0.01, 0.95),
            _outcome(214465570, "San Antonio Spurs", 0.25, 0.01, 0.49),
            _outcome(214465571, "Charlotte Hornets", 0.205, 0.01, 0.40),
            _outcome(214465572, "Cleveland Cavaliers", 0.205, 0.01, 0.40),
        ],
    )


#: Market 61193385, the other reader-visible shape: every priced leg phantom, so
#: the card can state nothing at all.
def _corners_market():
    return _market(
        mid=61193385,
        name="Lakers Total Corners",  # named to the query; the shape is what matters
        volume=500_000.0,
        outcomes=[_outcome(230227120, "Over 12.5", 0.505, 0.01, 0.99)],
    )


def _real_market(mid=61300001, name="Lakers vs Suns Moneyline", volume=400_000.0):
    return _market(
        mid=mid,
        name=name,
        volume=volume,
        outcomes=[
            _outcome(mid * 10 + 1, "Los Angeles Lakers", 0.57, 0.56, 0.58),
            _outcome(mid * 10 + 2, "Phoenix Suns", 0.43, 0.42, 0.44),
        ],
    )


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
    result.mappings.return_value.all.return_value = []
    return result


def _seeded_session(window):
    """#6327's harness, unchanged: answer the futures window, everything else empty."""
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper():
            return result
        if "~*" in sql:  # the headline-contender lane, deliberately unfed
            return result
        result.scalars.return_value.unique.return_value.all.return_value = list(window)
        result.scalars.return_value.all.return_value = list(window)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


async def _client(window, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _seeded_session(window)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


async def _search(client, q):
    resp = await client.get(f"/api/events/search?q={q}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _card(body, mid):
    for m in body.get("futures") or []:
        if m["id"] == mid:
            return m
    return None


def _every_rendered_id(body):
    """Flat bucket PLUS every family headline and shown member."""
    ids = {m["id"] for m in (body.get("futures") or [])}
    for fam in body.get("futures_families") or []:
        ids.add(fam["headline"]["id"])
        for m in fam["members"]:
            ids.add(m["id"])
    return ids


# ==========================================================================
# 0. The seed is real. Most assertions below are ABSENCES, and an absence is
#    vacuously true against a window that never arrived.
# ==========================================================================


class TestTheSeedIsReal:
    @_asyncio
    async def test_the_window_reaches_the_route(self, monkeypatch):
        async for ac in _client([_curry_market()], monkeypatch):
            body = await _search(ac, "lakers")
            assert body.get("futures"), (
                "the mocked window never reached the page — every absence "
                "assertion in this file would be vacuous"
            )

    def test_the_specimen_really_carries_the_defect(self):
        """Four legs at 0.48 on a book that bounds nothing, and they really rank."""
        legs = _curry_market().outcomes
        phantoms = [o for o in legs if o.current_probability == 0.48]

        assert len(phantoms) == 4
        assert all(o.current_yes_bid == 0.01 and o.current_yes_ask == 0.95 for o in phantoms)
        # ...and they outrank the honest legs, which is why the slice hides those.
        assert sorted((o.current_probability for o in legs), reverse=True)[:5] == [
            0.74, 0.48, 0.48, 0.48, 0.48,
        ]


# ==========================================================================
# 1. The rungs go, and the honest ones arrive.
# ==========================================================================


class TestTheCardStopsPrintingThem:
    @_asyncio
    async def test_no_phantom_rung_is_served(self, monkeypatch):
        async for ac in _client([_curry_market()], monkeypatch):
            body = await _search(ac, "lakers")
            card = _card(body, 57777176)

            assert card is not None, "the card itself must survive — it has a real leg"
            names = [o["name"] for o in card["top_outcomes"]]
            for phantom in ("Atlanta Hawks", "Brooklyn Nets", "Phoenix Suns", "Chicago Bulls"):
                assert phantom not in names, f"{phantom}: 0.48 on a 0.01/0.95 book"

    @_asyncio
    async def test_the_honest_legs_underneath_are_promoted_onto_the_card(self, monkeypatch):
        """The placement claim, at the route. A post-slice drop would serve ONE rung."""
        async for ac in _client([_curry_market()], monkeypatch):
            body = await _search(ac, "lakers")
            names = [o["name"] for o in _card(body, 57777176)["top_outcomes"]]

            assert names == [
                "Golden State Warriors",
                "San Antonio Spurs",
                "Charlotte Hornets",
                "Cleveland Cavaliers",
            ]


# ==========================================================================
# 2. A card with nothing left is withdrawn — from the flat bucket AND families.
# ==========================================================================


class TestTheAnswerlessCardIsWithdrawn:
    @_asyncio
    async def test_a_market_priced_only_by_empty_books_leaves_the_page(self, monkeypatch):
        async for ac in _client([_corners_market(), _real_market()], monkeypatch):
            body = await _search(ac, "lakers")

            assert 61193385 not in _every_rendered_id(body), (
                "its one price is an empty book's midpoint — the card can state nothing, "
                "and a family card is the back door a half-applied withdrawal leaves open"
            )

    @_asyncio
    async def test_the_priced_market_beside_it_is_still_served(self, monkeypatch):
        """The withdrawal is not a page-wide failure."""
        async for ac in _client([_corners_market(), _real_market()], monkeypatch):
            body = await _search(ac, "lakers")

            assert 61300001 in _every_rendered_id(body)


# ==========================================================================
# 3. The page refills: a withdrawal costs the reader no answer.
# ==========================================================================


class TestThePageRefills:
    @_asyncio
    async def test_a_priced_market_below_the_fold_takes_the_vacated_slot(self, monkeypatch):
        """Eleven markets, the first answerless. Ten priced cards must still ship.

        Filter-then-slice: withdrawing the top row must pull the eleventh up, not
        leave a nine-card page.
        """
        window = [_corners_market()] + [
            _real_market(mid=61300000 + i, name=f"Lakers Market {i}", volume=400_000.0 - i)
            for i in range(1, 11)
        ]
        async for ac in _client(window, monkeypatch):
            body = await _search(ac, "lakers")

            assert len(body["futures"]) == 10, "the page must not shrink by the withdrawal"
            assert 61193385 not in _every_rendered_id(body)


# ==========================================================================
# 4. THE CONTROL. A fully priced page is untouched — including a genuine 50%,
#    which is the one thing this ship is not allowed to suppress.
# ==========================================================================


class TestAFullyPricedPageIsUntouched:
    @_asyncio
    async def test_a_genuine_coin_flip_on_a_real_book_is_served(self, monkeypatch):
        """0.50 on 0.48/0.52 — a tight book straddling the number. It stays."""
        coin_flip = _market(
            mid=61400001,
            name="Lakers Over/Under 2.5",
            volume=300_000.0,
            outcomes=[
                _outcome(614000011, "Over 2.5", 0.50, 0.48, 0.52),
                _outcome(614000012, "Under 2.5", 0.50, 0.48, 0.52),
            ],
        )
        async for ac in _client([coin_flip], monkeypatch):
            body = await _search(ac, "lakers")
            card = _card(body, 61400001)

            assert card is not None, "a real coin flip is an answer, not a phantom"
            assert {o["name"] for o in card["top_outcomes"]} == {"Over 2.5", "Under 2.5"}

    @_asyncio
    async def test_an_ordinary_priced_page_carries_every_card_and_rung(self, monkeypatch):
        window = [
            _real_market(mid=61300000 + i, name=f"Lakers Market {i}", volume=400_000.0 - i)
            for i in range(1, 4)
        ]
        async for ac in _client(window, monkeypatch):
            body = await _search(ac, "lakers")

            assert len(body["futures"]) == 3
            for card in body["futures"]:
                assert len(card["top_outcomes"]) == 2
