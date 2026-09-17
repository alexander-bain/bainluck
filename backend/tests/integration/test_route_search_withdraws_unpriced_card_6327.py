"""THE CARD ITSELF LEAVES THE PAGE — `GET /api/events/search`, #6327.

The unit file (`tests/test_search_withdraws_wholly_unpriced_card_6327.py`) pins
the two predicates. This one pins the thing a reader can see, and it has to be at
the route for the reason CERT-718 wrote for #2579 and #2646 restated: the ship is
a claim about WHICH ROWS A RESPONSE CARRIES, and an assertion on a formatter
cannot see that. A builder that returns `[]` and a route that ships the card
anyway is green on the unit file alone — and that combination is not a fix, it is
a card with a name, a "2h ago" stamp and no ladder at all.

WHAT PRODUCTION SERVED (banked BEFORE the fix, `?q=Sonmez`, 2026-09-15 07:47Z,
`artifacts-latency-421/BEFORE-6327-search-sonmez.json`) — the seed in
`TestTheSpecimenPage` is this payload's own two rows:

    id 61110575  polymarket  tier 5  "…: Zeynep Sonmez vs Iva Jovic"   1 rung, PRICED
    id 61106176  kalshi      tier 1  "WTA Guadalajara Winner"          5 rungs, 0 priced

THE FOUR THINGS THIS SHIP MUST NOT BREAK, one class each below:

1. The page REFILLS. Filter-then-slice, so a real market at rank 11 takes the
   withdrawn row's slot — a withdrawal must cost the reader no answer.
2. A withdrawn card cannot WALK BACK IN through a family card. Families compose
   from the wider deduped set, so the flat bucket and the families need the same
   predicate or the fix is cosmetic on one surface and absent on the other.
3. The TOURNAMENT survives its own card. `deduped_futures` is left whole for the
   event-CONCEPT derivation: "WTA Guadalajara Winner" is a tennis winner field,
   which is exactly the shape that resolves to a tournament page. The market is
   unpriced; the tournament is real; deleting the destination to fix a card would
   have been a worse bug than the one being fixed.
4. A fully priced page is BYTE-IDENTICAL. `TestAFullyPricedPageIsUntouched` is
   green on both arms by construction — it separates "the page was made truthful"
   from "the page was made shorter", the control #2646 asks for by name.

RED-FIRST (measured on this file, `git checkout origin/master -- events.py`):
**4 failed, 4 passed.** The four reds are every test in classes 1-3 — the
withdrawn id present in `futures`, the page holding the unpriced row, the family
carrying it, and the tournament class (which asserts the withdrawal first, so on
the red arm it fails on that line rather than on its concept assertion; the
concept half is a forward guard, not a red driver). The four greens are class 4
and the two seed checks, and that split is the file's own control: the fix made
the page truthful without making it shorter.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

_asyncio = pytest.mark.asyncio

#: `_SEARCH_FUTURES_PAGE`. Mirrored, not imported, for #2646's stated reason: a
#: change to the constant should surface here as a readable number.
PAGE = 10


def _outcome(oid, name, prob):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, current_yes_ask=None, current_yes_bid=None, rank=None,
        sort_order=oid, external_id=f"OUT-{oid}",
    )


def _market(*, mid, name, volume, priced, tier=1, category="tennis",
            external_id=None, legs=4):
    """A futures market shaped as `search_events` reads it.

    `priced=False` is the specimen's condition and nothing else: the outcome ROWS
    are all there — a ranked ladder the page will happily draw — and not one of
    them carries a number. A fixture with no outcomes would prove a different
    issue (#3412) and would make every assertion below vacuous.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id or f"KX-{mid}",
        llm_sport_category=category,
        category=category,
        market_tier=tier,
        market_type=None,
        sport=None,
        sport_id=None,
        source="kalshi",
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
        outcomes=[
            _outcome(mid * 10 + i, f"Leg {i}", (0.4 if priced else None))
            for i in range(1, legs + 1)
        ],
    )


#: The BEFORE payload's own two rows, volumes ordered so the unpriced tier-1
#: winner field ranks FIRST — the position it actually occupied on the page.
def _specimen_window():
    return [
        _market(mid=61106176, name="WTA Guadalajara Winner", volume=900_000.0,
                priced=False, tier=1, external_id="KXWTAGUADALAJARA-26"),
        _market(mid=61110575, name="Guadalajara Open Akron: Zeynep Sonmez vs Iva Jovic",
                volume=100_000.0, priced=True, tier=5, external_id="KXWTAMATCH-26"),
    ]


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


def _seeded_session(window, contenders=()):
    """Answers the futures window with `window`, everything else empty.

    The headline-contender lane (`~*`, the only operator it builds) is given
    NOTHING by default — promotion is a separate mechanism with its own guards,
    and feeding it would make the page boundary depend on two things at once.
    #2646's harness, with one addition: `contenders` seeds that lane, for the one
    class below that exists to prove this ship did not disarm it.
    """
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper():
            return result
        if "~*" in sql:
            if not contenders:
                return result
            rows = list(contenders)
            result.scalars.return_value.unique.return_value.all.return_value = rows
            result.scalars.return_value.all.return_value = rows
            return result
        result.scalars.return_value.unique.return_value.all.return_value = list(window)
        result.scalars.return_value.all.return_value = list(window)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


async def _client(window, monkeypatch, contenders=()):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _seeded_session(window, contenders)

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


def _flat_ids(body):
    return [m["id"] for m in (body.get("futures") or [])]


def _family_ids(body):
    """Every id a family card renders — headline plus shown members."""
    ids = set()
    for fam in body.get("futures_families") or []:
        ids.add(fam["headline"]["id"])
        for m in fam["members"]:
            ids.add(m["id"])
    return ids


# ==========================================================================
# 0. The seed is real. Every assertion below is an ABSENCE, and an absence is
#    vacuously true against a window that never arrived.
# ==========================================================================


class TestTheSeedIsReal:
    @_asyncio
    async def test_the_window_reaches_the_route(self, monkeypatch):
        async for ac in _client(_specimen_window(), monkeypatch):
            body = await _search(ac, "Sonmez")
            assert body.get("futures"), (
                "the mocked window never reached the page — every absence "
                "assertion in this file would be vacuous"
            )

    def test_the_unpriced_specimen_really_carries_a_full_ladder(self):
        """The fixture's defect is the production one: rungs present, no price."""
        unpriced = _specimen_window()[0]
        assert len(unpriced.outcomes) == 4
        assert all(o.current_probability is None for o in unpriced.outcomes)
        priced = _specimen_window()[1]
        assert any(o.current_probability is not None for o in priced.outcomes)


# ==========================================================================
# 1. The specimen page, and the refill.
# ==========================================================================


class TestTheSpecimenPage:
    @_asyncio
    async def test_the_dashes_only_card_is_gone_and_the_real_one_stays(
        self, monkeypatch
    ):
        """`?q=Sonmez` served both. It must now serve only the market with a price."""
        async for ac in _client(_specimen_window(), monkeypatch):
            body = await _search(ac, "Sonmez")
            assert 61106176 not in _flat_ids(body), (
                "WTA Guadalajara Winner has no price on any of its rungs"
            )
            assert 61110575 in _flat_ids(body), (
                "the priced match market is the answer the reader came for"
            )


class TestThePageRefills:
    """A withdrawal must cost the reader no answer — filter THEN slice."""

    @staticmethod
    def _window():
        # Two unpriced rows at the TOP of the ranking (highest volume), twelve
        # priced below them. Pre-filter the page is [2 dashes + 8 real]; the fix
        # must ship ten REAL ones, not eight.
        unpriced = [
            _market(mid=900 + i, name=f"Sonmez Unpriced Field {i}",
                    volume=9_000_000.0 - i, priced=False)
            for i in range(2)
        ]
        priced = [
            _market(mid=1000 + i, name=f"Sonmez Priced Market {i}",
                    volume=1_000_000.0 - i, priced=True)
            for i in range(12)
        ]
        return unpriced + priced

    @_asyncio
    async def test_the_page_is_still_full_and_holds_no_withdrawn_row(
        self, monkeypatch
    ):
        async for ac in _client(self._window(), monkeypatch):
            body = await _search(ac, "Sonmez")
            ids = _flat_ids(body)

            assert len(ids) == PAGE, (
                f"the page shrank to {len(ids)} instead of refilling from below"
            )
            assert not [i for i in ids if i in (900, 901)], ids
            # The two slots were taken by rows that were BELOW the old cut —
            # this is the refill, stated as the thing it is.
            assert 1008 in ids and 1009 in ids, (
                "ranks 11 and 12 should have moved up into the freed slots"
            )


# ==========================================================================
# 2. The families. Same predicate, or the fix is half a fix.
# ==========================================================================


class TestAWithdrawnCardCannotWalkBackInThroughAFamily:
    @staticmethod
    def _window():
        """Six name-matching markets, one of them dashes-only, so they compose
        into one `entity:sonmez` family wide enough to have members."""
        rows = [
            _market(mid=2000 + i, name=f"Zeynep Sonmez: Market {i}",
                    volume=5_000_000.0 - i * 1000, priced=True)
            for i in range(5)
        ]
        rows.insert(
            2,
            _market(mid=2999, name="Zeynep Sonmez: Unpriced Field",
                    volume=4_500_000.0, priced=False),
        )
        return rows

    @_asyncio
    async def test_the_family_carries_no_unpriced_member(self, monkeypatch):
        async for ac in _client(self._window(), monkeypatch):
            body = await _search(ac, "Sonmez")
            families = body.get("futures_families") or []
            assert families, (
                "no family composed — this assertion would be vacuous; the seed "
                "is six name matches and should group under one entity key"
            )
            assert 2999 not in _family_ids(body), (
                "the card withdrawn from the flat bucket walked back in as a "
                "family member"
            )
            assert 2999 not in _flat_ids(body)


# ==========================================================================
# 3. The tournament outlives its own card. `deduped_futures` stays WHOLE.
# ==========================================================================


class TestTheTournamentPageSurvives:
    @_asyncio
    async def test_an_unpriced_winner_field_still_mints_its_event_concept(
        self, monkeypatch
    ):
        """The market is withdrawn; the tournament it names is still reachable.

        This is why the filter is applied to the SHIPPED list and not to
        `deduped_futures`: the concept loop reads that list, and a tennis winner
        field is exactly the shape that resolves to a tournament page. Filtering
        the shared list would delete a legitimate destination to fix a card.
        """
        async for ac in _client(_specimen_window(), monkeypatch):
            body = await _search(ac, "Guadalajara")

            assert 61106176 not in _flat_ids(body), "the card is still withdrawn"
            keys = [c.get("key") for c in (body.get("event_concepts") or [])]
            assert any(str(k).startswith("event:tennis:") for k in keys), (
                f"the tournament destination was deleted with the card: {keys}"
            )


# ==========================================================================
# 3b. THE EDGE THE FIRST DRAFT OF THIS SHIP GOT WRONG.
#
# The headline-contender lane fires only when the window saturated AND every row
# on the page is a name match — its way of asking "did name matches crowd out the
# outcome-only arm". Gate that on the page AFTER this filter and a page whose
# every row is withdrawn is EMPTY, `and futures_markets` short-circuits falsy, and
# the one lane that could have refilled it with a priced tier-1 market never runs:
# the reader's page goes from ten dashes-only cards to nothing at all. So the gate
# reads `_deduped_page`, the page BEFORE the filter, and its firing condition is
# byte-for-byte what it was before #6327.
#
# This is also where the fix proves it cannot undo itself: a contender is priced
# by its own query (`current_probability >= MIN_CONTENDER_PROBABILITY`), so
# promotion can never put a dashes-only card back on a page this ship cleared.
# ==========================================================================


class TestAnAllWithdrawnPageStillReachesThePromotionLane:
    #: `_SEARCH_FUTURES_WINDOW`. The lane's first condition is saturation, so the
    #: seed has to be the whole window, not a page of it.
    WINDOW = 20

    @staticmethod
    def _window():
        return [
            TestAnAllWithdrawnPageStillReachesThePromotionLane._row(i)
            for i in range(TestAnAllWithdrawnPageStillReachesThePromotionLane.WINDOW)
        ]

    @staticmethod
    def _row(i):
        return _market(mid=5000 + i, name=f"Zeynep Sonmez: Unpriced Field {i}",
                       volume=6_000_000.0 - i * 1000, priced=False)

    @staticmethod
    def _contender():
        """Outcome-only for this query (the name does NOT say Sonmez), tier 1,
        volume over `MIN_CONTENDER_VOLUME`, and priced — the shape the lane's own
        SQL selects."""
        return _market(mid=5999, name="WTA Guadalajara Winner", volume=2_000_000.0,
                       priced=True, tier=1, external_id="KXWTAGUADALAJARA-26")

    @_asyncio
    async def test_the_reader_gets_the_priced_market_not_an_empty_page(
        self, monkeypatch
    ):
        async for ac in _client(
            self._window(), monkeypatch, contenders=[self._contender()]
        ):
            body = await _search(ac, "Sonmez")
            ids = _flat_ids(body)

            assert not [i for i in ids if 5000 <= i < 5000 + self.WINDOW], (
                f"a withdrawn row survived: {ids}"
            )
            assert ids == [5999], (
                "the page emptied instead of promoting the priced contender — "
                f"the gate is reading the filtered page again: {ids}"
            )

    @_asyncio
    async def test_and_it_is_still_empty_when_there_is_nothing_priced_to_promote(
        self, monkeypatch
    ):
        """The honest zero. Withdrawing every card is the right answer when every
        candidate really is dashes-only — this pins that the class above proves
        promotion, not merely that something reached the page."""
        async for ac in _client(self._window(), monkeypatch):
            body = await _search(ac, "Sonmez")
            assert _flat_ids(body) == []


# ==========================================================================
# 4. CONTROL — green on BOTH arms. "Truthful", not merely "smaller".
# ==========================================================================


class TestAFullyPricedPageIsUntouched:
    @_asyncio
    async def test_every_priced_row_survives_in_its_original_order(
        self, monkeypatch
    ):
        window = [
            _market(mid=3000 + i, name=f"Sonmez Priced {i}",
                    volume=8_000_000.0 - i * 1000, priced=True)
            for i in range(PAGE)
        ]
        async for ac in _client(window, monkeypatch):
            body = await _search(ac, "Sonmez")
            assert _flat_ids(body) == [3000 + i for i in range(PAGE)]

    @_asyncio
    async def test_a_zero_priced_ladder_is_a_priced_ladder_and_ships(
        self, monkeypatch
    ):
        """91% of stored zeros carry a live ask. They are markets, not absences.

        The boundary that makes this ship safe to widen later: if anyone
        "simplifies" the predicate to a truthiness test, this page empties and
        this test says so at the route, not only at the helper.
        """
        window = [
            _market(mid=4000, name="Sonmez Longshot Field", volume=7_000_000.0,
                    priced=True),
        ]
        for o in window[0].outcomes:
            o.current_probability = 0.0
            o.probability = 0.0
            o.price = 0.0
            o.current_yes_ask = 0.02

        async for ac in _client(window, monkeypatch):
            body = await _search(ac, "Sonmez")
            assert _flat_ids(body) == [4000], (
                "a rung priced at zero with a live ask is a market a reader can "
                "still buy — withdrawing it deletes a real answer"
            )
