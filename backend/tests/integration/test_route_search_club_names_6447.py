"""THE READER'S OWN TWO SCREENS — `/api/events/search` and `/api/events/typeahead`.

The unit file (`tests/test_search_club_names_6447.py`) pins the repair. This one
pins the thing a reader can see, and it has to be at the route for three reasons
a formatter assertion cannot reach:

1. **The veto is a DATABASE read.** `protected_names` on the search paths comes
   from one keyed select against `events`, composed in the route. A unit test
   passes its own list and can never see a route that forgets to issue the query
   — or issues it and drops the result.
2. **The pre-test is a LATENCY claim.** "A clean page pays for no extra read" is
   a statement about how many statements the route executes.
   :class:`TestACleanPagePaysNothing` counts them; nothing smaller can.
3. **Two surfaces, two payload shapes, one bug.** The dropdown keys on `text`
   and `market_id`, the results page on `name` and `id`. A repair wired with one
   pair on both call sites is green everywhere except in production.

THE SPECIMEN IS THE PRODUCTION ROW, read 2026-09-16 while the defect was live::

    id 59659439  kalshi  KXNFLGAME-26SEP20GBNYJ  "GB Packers vs NY Jets"
                 outcomes: "Green Bay" 0.625 · "New York J" 0.365
    events.14782704  home "New York Jets"  away "Green Bay Packers"

RED-FIRST, measured by reverting `routes/events.py` to `origin/master`
(`2bd74e556`) with both other files in place: **6 failed, 2 passed.** The six
reds are every test that asserts a served string — both results-page tests, both
dropdown tests, the veto test and the unattached-market test. The two greens are
:class:`TestACleanPagePaysNothing`, and that split is the file's own control: a
route that never calls the repair also never issues the extra read, so "a clean
page pays nothing" is true on BOTH arms and cannot be what turns the file red.
If that class ever goes red on master, the red arm is a broken checkout rather
than a missing fix.

🔴 ONE RIG NOTE, because it cost a full cycle: the futures window query names
`home_team_name` too, so a session stub that routes on that substring swallows
the window and every test here fails on an empty page for a reason unrelated to
the ship. :func:`_seeded_session` discriminates on the club read's PROJECTION.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

_asyncio = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# The production specimen.
# ---------------------------------------------------------------------------

JETS_MARKET_ID = 59659439
JETS_TICKER = "KXNFLGAME-26SEP20GBNYJ"
JETS_EVENT_ID = 14782704
JETS_HOME = "New York Jets"
JETS_AWAY = "Green Bay Packers"
TRUNCATED = "New York J"


def _outcome(oid, name, prob):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, current_yes_ask=None,
        current_yes_bid=None, rank=None, sort_order=oid,
        external_id=f"{JETS_TICKER}-{oid}", last_updated=None,
        calibration_probability=None, volume=None, price_changed_at=None,
    )


def _market(*, mid=JETS_MARKET_ID, name="GB Packers vs NY Jets",
            outcome_names=("Green Bay", TRUNCATED),
            external_id=JETS_TICKER, event_id=JETS_EVENT_ID, volume=900_000.0):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id,
        llm_sport_category="football",
        category="football",
        market_tier=5,
        market_type=None,
        sport=None,
        sport_id=None,
        source="kalshi",
        volume=volume,
        status="open",
        resolution_date=(now + timedelta(days=5)).date(),
        updated_at=now,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=event_id,
        mutually_exclusive=True,
        outcomes=[
            _outcome(mid * 10 + i, n, 0.625 if i == 1 else 0.365)
            for i, n in enumerate(outcome_names, start=1)
        ],
    )


#: The control: the same card with the club already spelled out. Every
#: assertion below must hold on it unchanged, which is what separates "the page
#: was repaired" from "the page was rewritten".
def _already_correct_market():
    return _market(outcome_names=("Green Bay", "New York Jets"))


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


def _seeded_session(window, club_rows, *, seen):
    """Answers the futures window, the club-name read, and nothing else.

    `seen` collects a tag per statement so a test can assert on what the route
    DID and DID NOT execute.

    🔴 THE CLUB READ IS RECOGNISED BY ITS PROJECTION, NOT BY A COLUMN NAME. The
    futures window query names `home_team_name` too — its recall arms reach
    `events` — so a `"home_team_name" in sql` discriminator swallows the window
    and every assertion in this file fails on an empty page for a reason that
    has nothing to do with the ship. Measured, not guessed: 2 of the statements
    this route issues match both. The club read is the only one whose select
    list IS those two columns, so that prefix is the exact test.
    """
    session = AsyncMock()
    _CLUB_SELECT = "SELECT events.home_team_name, events.away_team_name"

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if " ".join(sql.split()).startswith(_CLUB_SELECT):
            seen.append("club_names")
            result.all.return_value = list(club_rows)
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper():
            return result
        if "~*" in sql:
            return result
        seen.append("futures_window")
        result.scalars.return_value.unique.return_value.all.return_value = list(window)
        result.scalars.return_value.all.return_value = list(window)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


async def _client(window, club_rows, monkeypatch, seen):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _seeded_session(window, club_rows, seen=seen)

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


@pytest_asyncio.fixture
async def seen():
    return []


@pytest_asyncio.fixture
async def truncated_client(monkeypatch, seen):
    """Production's state on 2026-09-16: the row is truncated, the event is not."""
    async for ac in _client(
        [_market()], [(JETS_HOME, JETS_AWAY)], monkeypatch, seen
    ):
        yield ac


def _cards(body):
    """Every futures card the response shows, from BOTH reader buckets."""
    out = list(body.get("futures") or [])
    for family in body.get("futures_families") or []:
        headline = family.get("headline")
        if headline:
            out.append(headline)
        out.extend(family.get("markets") or [])
    return out


def _dropdown_rows(body):
    return [s for s in (body.get("suggestions") or []) if s.get("type") == "futures"]


def _names(card):
    return [o.get("name") for o in (card.get("top_outcomes") or [])]


# ---------------------------------------------------------------------------


class TestTheResultsPage:
    @_asyncio
    async def test_the_card_offers_new_york_jets(self, truncated_client):
        body = (await truncated_client.get("/api/events/search?q=Jets")).json()
        cards = _cards(body)

        assert cards, "the specimen must reach the page or nothing below means anything"
        for card in cards:
            assert "New York Jets" in _names(card)
            assert TRUNCATED not in _names(card)

    @_asyncio
    async def test_both_reader_buckets_agree(self, truncated_client):
        """`futures` and `futures_families` serve the same dict; prove it served.

        A repair applied to one list and not the other is invisible to a test
        that reads either one alone.
        """
        body = (await truncated_client.get("/api/events/search?q=Jets")).json()

        flat = body.get("futures") or []
        families = body.get("futures_families") or []
        assert flat, "flat bucket empty"
        served = {n for card in _cards(body) for n in _names(card)}
        assert TRUNCATED not in served
        if families:
            assert "New York Jets" in _names(families[0]["headline"])


class TestTheDropdown:
    @_asyncio
    async def test_the_suggestion_offers_new_york_jets(self, truncated_client):
        body = (await truncated_client.get("/api/events/typeahead?q=Jets")).json()
        rows = _dropdown_rows(body)

        assert rows, "the specimen must reach the dropdown"
        for row in rows:
            assert "New York Jets" in _names(row)
            assert TRUNCATED not in _names(row)

    @_asyncio
    async def test_the_dropdown_keys_on_text_not_name(self, monkeypatch, seen):
        """The two shapes are wired with their own field pair.

        A title-side truncation is the only thing that can catch a dropdown
        wired with the results page's `name`/`id`: the row has no `name` key at
        all, so the repair would read `None`, find no sides, and silently do
        nothing to the title while the outcomes still looked fixed.
        """
        window = [_market(
            name="Green Bay vs New York J: 2nd Half Total",
            outcome_names=("Over", "Under"),
        )]
        async for client in _client(
            window, [(JETS_HOME, JETS_AWAY)], monkeypatch, seen
        ):
            body = (await client.get("/api/events/typeahead?q=Jets")).json()
            rows = _dropdown_rows(body)
            assert rows
            assert rows[0]["text"] == "Green Bay vs New York Jets: 2nd Half Total"


class TestTheVetoIsReadFromTheDatabase:
    @_asyncio
    async def test_an_anchored_club_named_new_york_j_stops_the_rewrite(
        self, monkeypatch, seen
    ):
        """Same card, same ticker — only the `events` row differs.

        This is the only test in the file that can tell "the route reads the
        club names" from "the route passes an empty list": everything else is
        green either way, because the repair this specimen needs is not vetoed.
        """
        async for client in _client(
            [_market()], [(TRUNCATED, JETS_AWAY)], monkeypatch, seen
        ):
            body = (await client.get("/api/events/search?q=Jets")).json()
            cards = _cards(body)
            assert cards
            for card in cards:
                assert TRUNCATED in _names(card)
                assert "New York Jets" not in _names(card)
        assert "club_names" in seen


class TestACleanPagePaysNothing:
    @_asyncio
    async def test_no_truncation_means_no_extra_read(self, monkeypatch, seen):
        """181 of 187 measured cards are this case, and so is every keystroke.

        Green on both arms by construction — a route that never calls the repair
        also never issues the read — so this is a control, not a red driver. Its
        job is to fail the day somebody moves the club read above the pre-test.
        """
        async for client in _client(
            [_already_correct_market()], [(JETS_HOME, JETS_AWAY)], monkeypatch, seen
        ):
            body = (await client.get("/api/events/search?q=Jets")).json()
            assert _cards(body)

        assert "futures_window" in seen
        assert "club_names" not in seen

    @_asyncio
    async def test_an_already_correct_card_is_served_unchanged(
        self, monkeypatch, seen
    ):
        async for client in _client(
            [_already_correct_market()], [(JETS_HOME, JETS_AWAY)], monkeypatch, seen
        ):
            body = (await client.get("/api/events/search?q=Jets")).json()
            cards = _cards(body)
            assert cards
            for card in cards:
                assert _names(card) == ["Green Bay", "New York Jets"]
                assert card["name"] == "GB Packers vs NY Jets"


class TestARowThatCannotAnswerIsNotA500:
    """The class that actually bit: reading a new column off an old double.

    `market.event_id` on a row that has no such attribute turned 22 green tests
    in `test_route_typeahead_intent_5060.py` into 500s — mapped columns are
    always there on a real row and are not on the doubles that reach these
    formatters. `_market_facts` reads all three through `getattr`, and this is
    the guard for the class rather than for the one column: the fixture below
    omits every attribute the repair wants.
    """

    @_asyncio
    async def test_a_row_with_no_event_id_still_serves_200(self, monkeypatch, seen):
        """`event_id` is the attribute THIS ship newly reads, so it is the class.

        Scoped to that one column deliberately. `external_id` and `id` are read
        by code that predates this — `_derive_awards_concept` takes the ticker
        four hundred lines up — so a row lacking those was already outside the
        route's contract and asserting about it here would be this file
        claiming a guarantee it did not create.
        """
        now = datetime.now(timezone.utc)
        thin = SimpleNamespace(
            id=1, name="GB Packers vs New York J", external_id=JETS_TICKER,
            llm_sport_category="football", category="football", market_tier=5,
            market_type=None, sport=None, sport_id=None, source="kalshi",
            volume=1.0, status="open", resolution_date=(now + timedelta(days=5)).date(),
            updated_at=now, canonical_market_key=None, image_url=None,
            hook_description=None, group_id=None, mutually_exclusive=True,
            outcomes=[_outcome(11, "Green Bay", 0.6), _outcome(12, TRUNCATED, 0.4)],
        )
        assert not hasattr(thin, "event_id")

        async for client in _client(
            [thin], [(JETS_HOME, JETS_AWAY)], monkeypatch, seen
        ):
            for path in ("search", "typeahead"):
                resp = await client.get(f"/api/events/{path}?q=Jets")
                assert resp.status_code == 200, resp.text


class TestTheRouteSurvivesAMarketWithNoEvent:
    @_asyncio
    async def test_an_unattached_market_has_no_clubs_to_veto_with(
        self, monkeypatch, seen
    ):
        """`event_id IS NULL` is most of the futures corpus.

        The repair still runs — the ticker is the source, the event is only the
        lock — and the route must not issue a keyed read for an empty id set.
        """
        async for client in _client(
            [_market(event_id=None)], [], monkeypatch, seen
        ):
            body = (await client.get("/api/events/search?q=Jets")).json()
            cards = _cards(body)
            assert cards
            for card in cards:
                assert "New York Jets" in _names(card)

        assert "club_names" not in seen
