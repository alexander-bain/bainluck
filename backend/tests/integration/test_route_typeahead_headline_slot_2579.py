"""UX-P261 / #2579 round two — the tournament you can win LEADS the dropdown.

WHY THIS FILE EXISTS. CERT-718 blocked round one of this ship, and it was right.
`promote_headline_contenders` put the US Open winner market at the front of the
typeahead's *futures* list, and then `typeahead_search` sent every pool through
`search_match_class.rank`, whose first and inviolable sort key is the match class.
The winner market holds "Alcaraz" only as an OUTCOME (MC4); every
"… vs Carlos Alcaraz: Total Games" prop holds him in its own NAME (MC1). The
global scorer therefore undid the promotion in full:

    after promote_headline_contenders   [winner, prop0, prop1, prop2]
    after search_match_class.rank       [prop0, prop1, prop2, winner]

Round one's guards stopped at that intermediate list and at an AST wiring check,
so both were green while the dropdown a user sees was still wrong. CERT-718's
remediation note asked for exactly one thing: **an endpoint-level test over the
final `suggestions` array.** That is what this file is.

Every assertion below goes through `GET /api/events/typeahead` and reads
`body["suggestions"]` — the array that becomes the dropdown. Nothing here asserts
on an intermediate list, because an intermediate list is what round one proved
you can satisfy while shipping the bug.

RED-FIRST, and the arm is BOTH source files. `reserve_headline_slot` is imported
lazily inside the test bodies that name it, so reverting
`app/utils/search_headline_contender.py` alone leaves this module collectable.
Reverting `app/routes/events.py` as well is the true red arm: the route's import
line is what would otherwise turn a revert into a collection error, which grades
as "the harness never ran" rather than "the defect is present" (gotcha #124).

NON-VACUITY. The seeded session answers most queries empty, so a loop over
suggestions is a loop over nothing. `TestTheSeedIsReal` fails loudly if the props
or the winner stop reaching the pool, and every ordering assertion below first
asserts the row it is about is actually present.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

#: Applied per-class rather than module-wide: `TestReserveHeadlineSlotIsTotal`
#: is synchronous, and a blanket `pytestmark` marks it asyncio too, which pytest
#: reports as ten warnings on every run. Warnings on a guard file are noise the
#: next reader has to re-triage.
_asyncio = pytest.mark.asyncio


# --------------------------------------------------------------------------
# The production shape, measured 2026-09-01/02. `Alcaraz` had 41 open name
# matches and 19 outcome-only matches; the window is 20 rows, so the winner
# market never reached it. The four props below stand for those name matches
# and the winner is the real row (`114159`, volume 4,108,808, tier 1).
# --------------------------------------------------------------------------
WINNER_MARKET_ID = 114159
WINNER_MARKET = "2026 Men’s US Open Winner (Tennis)"

#: Name matches. Each contains "Alcaraz" in its own NAME, so each is MC1 and
#: outranks the winner market under the scorer's class key. These are the rows
#: that buried the answer.
PROP_NAMES = [
    "Roman Safiullin vs Carlos Alcaraz: Total Games",
    "Carlos Alcaraz: Next Match Played",
    "Carlos Alcaraz: Grand Slam wins in 2026",
    "Faria vs Alcaraz",
]


def _outcome(name: str, prob: float, oid: int):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None, sort_order=oid,
        external_id=None,
    )


def _market(*, mid, name, outcomes, volume=4_108_808.0, tier=1):
    """A futures market shaped as `typeahead_search` reads it."""
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=f"KX-{mid}",
        llm_sport_category="tennis",
        category="tennis",
        market_tier=tier,
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
        outcomes=outcomes,
    )


def _winner_market(mid=WINNER_MARKET_ID, name=WINNER_MARKET, volume=4_108_808.0):
    """The answer. Its NAME says nothing about Alcaraz; he is an OUTCOME."""
    return _market(
        mid=mid,
        name=name,
        volume=volume,
        outcomes=[
            _outcome("Carlos Alcaraz", 0.355, mid * 10 + 1),
            _outcome("Jannik Sinner", 0.330, mid * 10 + 2),
            _outcome("Novak Djokovic", 0.070, mid * 10 + 3),
        ],
    )


def _props(n=len(PROP_NAMES)):
    return [
        _market(
            mid=900_000 + i,
            name=PROP_NAMES[i],
            volume=5_000.0,
            outcomes=[
                _outcome("Over", 0.52, (900_000 + i) * 10 + 1),
                _outcome("Under", 0.48, (900_000 + i) * 10 + 2),
            ],
        )
        for i in range(n)
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
    return result


def _seeded_session(*, window, contenders):
    """A session that tells the two futures lanes apart.

    The headline-contender lane is the ONLY place in `routes/events.py` that
    builds a `~*` predicate (two call sites, both it: `/search` at 4519 and the
    typeahead at 5865), so the operator is an exact discriminator rather than a
    guess. Handing the same rows to both lanes would defeat the route's own gate
    — it only runs the bonus lane when every row the window kept is a name match
    — and would quietly test nothing.
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
        rows = contenders if "~*" in sql else window
        result.scalars.return_value.unique.return_value.all.return_value = list(rows)
        result.scalars.return_value.all.return_value = list(rows)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


def _app_for(*, window, contenders, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _seeded_session(window=window, contenders=contenders)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app


async def _client(*, window, contenders, monkeypatch):
    app = _app_for(window=window, contenders=contenders, monkeypatch=monkeypatch)
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def alcaraz_client(monkeypatch):
    """The reported case: a window full of name matches, the answer outside it."""
    async for ac in _client(
        window=_props(), contenders=[_winner_market()], monkeypatch=monkeypatch
    ):
        yield ac


@pytest_asyncio.fixture
async def no_contender_client(monkeypatch):
    """The same page with NOTHING earning a slot. The control."""
    async for ac in _client(
        window=_props(), contenders=[], monkeypatch=monkeypatch
    ):
        yield ac


@pytest_asyncio.fixture
async def cheap_outcome_client(monkeypatch):
    """An outcome-only market that FAILS the volume floor, so it earns no slot.

    The control that separates "a slot was reserved" from "the scorer was
    weakened". This row is MC4 exactly like the winner and must still lose to
    every MC1 prop.
    """
    async for ac in _client(
        window=[*_props(), _winner_market(mid=777_001, name="Cincinnati Open: Winner",
                                         volume=140.0)],
        contenders=[],
        monkeypatch=monkeypatch,
    ):
        yield ac


def _texts(body):
    return [s.get("text") for s in body["suggestions"]]


async def _suggest(client, q="Alcaraz"):
    resp = await client.get(f"/api/events/typeahead?q={q}")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ==========================================================================
@_asyncio
class TestTheSeedIsReal:
    """If these fail, every ordering assertion below is vacuous."""

    async def test_the_dropdown_is_not_empty(self, alcaraz_client):
        body = await _suggest(alcaraz_client)
        assert body["suggestions"], (
            "empty dropdown — the seeded futures never reached the pool, so "
            "this whole file is measuring nothing"
        )

    async def test_the_name_matching_props_reach_the_dropdown(self, alcaraz_client):
        body = await _suggest(alcaraz_client)
        texts = _texts(body)
        assert any(p in texts for p in PROP_NAMES), (
            "no name-matching prop reached the dropdown, so there is nothing "
            f"for the winner market to have to beat. Got: {texts}"
        )


# ==========================================================================
# RED on the round-one head (`7e816a48`) — the defect CERT-718 found.
# ==========================================================================
@_asyncio
class TestTheAnswerLeadsTheDropdown:
    async def test_the_winner_market_is_suggestion_one(self, alcaraz_client):
        """#2579's ship, stated as the user sees it.

        This is the assertion round one did not have. On `7e816a48` the winner
        market IS in the array — it is simply last, beneath every prop, because
        the global scorer re-sorted it there.
        """
        body = await _suggest(alcaraz_client)
        texts = _texts(body)
        assert WINNER_MARKET in texts, (
            "the tournament market a player can win never reached the dropdown "
            f"at all. Got: {texts}"
        )
        assert texts[0] == WINNER_MARKET, (
            "the winner market is present but not first — this is CERT-718's "
            "finding exactly: promote_headline_contenders put it at the front "
            "of the futures list and search_match_class.rank sank it beneath "
            f"every MC1 name match. Order was: {texts}"
        )

    async def test_it_is_the_market_id_that_leads_not_a_lookalike_title(
        self, alcaraz_client
    ):
        """Assert on the id, so a title-only match cannot fake this green."""
        body = await _suggest(alcaraz_client)
        first = body["suggestions"][0]
        assert first.get("type") == "futures", f"lead row was {first.get('type')!r}"
        assert first.get("market_id") == WINNER_MARKET_ID, (
            f"lead row was market {first.get('market_id')!r}, expected the "
            f"seeded winner {WINNER_MARKET_ID}"
        )

    async def test_the_answer_survives_a_pool_that_would_truncate_it(
        self, monkeypatch
    ):
        """The invisible half of the bug, and the reason the reservation runs
        BEFORE the `[:7]` slice.

        With enough MC1 rows the winner does not merely rank low — it falls off
        the end of the dropdown entirely. A reservation applied after truncation
        would rescue the visible case and lose this one.
        """
        many = _props(n=len(PROP_NAMES))
        many += [
            _market(
                mid=910_000 + i,
                name=f"Carlos Alcaraz: prop {i}",
                volume=5_000.0,
                outcomes=[_outcome("Yes", 0.5, (910_000 + i) * 10 + 1)],
            )
            for i in range(8)
        ]
        async for ac in _client(
            window=many, contenders=[_winner_market()], monkeypatch=monkeypatch
        ):
            body = await _suggest(ac)
            texts = _texts(body)
            assert texts, "vacuous — empty dropdown"
            assert texts[0] == WINNER_MARKET, (
                "with a crowded page the winner market was pushed out of the "
                f"visible suggestions rather than reserved a slot. Got: {texts}"
            )


# ==========================================================================
# GREEN IN BOTH ARMS. These must pass on the round-one head too — they are what
# proves the red arm above is measuring the fix and not a broken checkout.
# ==========================================================================
@_asyncio
class TestControlsGreenInBothArms:
    async def test_a_page_with_no_contender_is_unchanged(self, no_contender_client):
        """A query that earns no reserved slot pays nothing.

        The props keep the scorer's own order, and no futures row is displaced.
        """
        body = await _suggest(no_contender_client)
        texts = _texts(body)
        assert texts, "vacuous — empty dropdown"
        assert WINNER_MARKET not in texts, (
            "a winner market appeared with no contender seeded — the lane is "
            "firing on rows it was never handed"
        )
        assert all(t in PROP_NAMES for t in texts if t), (
            f"unexpected rows in a props-only dropdown: {texts}"
        )

    async def test_name_match_still_beats_outcome_only_for_everything_else(
        self, cheap_outcome_client
    ):
        """MC1-before-MC4 is untouched. THE control for this whole change.

        `Cincinnati Open: Winner` is outcome-only for "Alcaraz" exactly like the
        US Open market, but its volume (140) fails the contender floor, so it
        earns no reserved slot. It must therefore stay BELOW the name matches.
        If this ever goes green-by-inversion, the fix stopped being a reserved
        slot and became a weakening of the scorer's class key — which is the
        repair CERT-718 explicitly warned against, because that key is what
        keeps `Chess Candidates 2026: Winner` off the page for `fed`.
        """
        body = await _suggest(cheap_outcome_client)
        texts = [t for t in _texts(body) if t]
        assert texts, "vacuous — empty dropdown"
        assert "Cincinnati Open: Winner" in texts, (
            f"the cheap outcome-only row never reached the pool: {texts}"
        )
        assert texts[0] != "Cincinnati Open: Winner", (
            "an outcome-only market that earned NO reserved slot led the "
            "dropdown — the scorer's class key has been weakened rather than a "
            f"single slot reserved. Order was: {texts}"
        )
        assert texts.index("Cincinnati Open: Winner") > 0

    async def test_the_endpoint_still_answers_a_query_with_no_futures_at_all(
        self, monkeypatch
    ):
        async for ac in _client(window=[], contenders=[], monkeypatch=monkeypatch):
            resp = await ac.get("/api/events/typeahead?q=Alcaraz")
            assert resp.status_code == 200, resp.text
            assert "suggestions" in resp.json()


# ==========================================================================
# The pure rule, unit-level. Lazy imports keep the module collectable when
# `search_headline_contender.py` is reverted.
# ==========================================================================
class TestReserveHeadlineSlotIsTotal:
    def test_it_moves_the_reserved_row_to_the_front(self):
        from app.utils.search_headline_contender import reserve_headline_slot

        ranked = [
            {"type": "futures", "market_id": 1},
            {"type": "futures", "market_id": 2},
            {"type": "futures", "market_id": WINNER_MARKET_ID},
        ]
        out = reserve_headline_slot(ranked, {WINNER_MARKET_ID})
        assert [r["market_id"] for r in out] == [WINNER_MARKET_ID, 1, 2], (
            "the reserved row must lead and everything else must keep the "
            f"scorer's order. Got: {out}"
        )

    def test_one_slot_only(self):
        from app.utils.search_headline_contender import reserve_headline_slot

        ranked = [
            {"type": "futures", "market_id": 1},
            {"type": "futures", "market_id": 10},
            {"type": "futures", "market_id": 11},
        ]
        out = reserve_headline_slot(ranked, {10, 11})
        assert [r["market_id"] for r in out] == [10, 1, 11], (
            "MAX_HEADLINE_SLOTS is 1 — a second reserved row would put the same "
            f"question on the page twice. Got: {out}"
        )

    @pytest.mark.parametrize(
        "ids", [set(), None, {None}, {999_999}], ids=["empty", "none", "null", "absent"]
    )
    def test_no_op_cases_return_the_list_unchanged(self, ids):
        from app.utils.search_headline_contender import reserve_headline_slot

        ranked = [{"type": "futures", "market_id": 1}, {"type": "team", "id": 2}]
        assert reserve_headline_slot(ranked, ids) == ranked

    def test_a_non_futures_row_with_a_colliding_id_is_not_reserved(self):
        """`market_id` is only meaningful on a futures payload. A team whose id
        happens to equal a market id must never be lifted."""
        from app.utils.search_headline_contender import reserve_headline_slot

        ranked = [
            {"type": "futures", "market_id": 1},
            {"type": "team", "market_id": WINNER_MARKET_ID},
        ]
        assert reserve_headline_slot(ranked, {WINNER_MARKET_ID}) == ranked

    def test_cap_zero_is_a_no_op(self):
        from app.utils.search_headline_contender import reserve_headline_slot

        ranked = [{"type": "futures", "market_id": 1},
                  {"type": "futures", "market_id": 2}]
        assert reserve_headline_slot(ranked, {2}, cap=0) == ranked

    def test_it_survives_payloads_that_are_not_dicts(self):
        from app.utils.search_headline_contender import reserve_headline_slot

        ranked = [object(), {"type": "futures", "market_id": 7}]
        out = reserve_headline_slot(ranked, {7})
        assert out[0] == {"type": "futures", "market_id": 7}
        assert len(out) == 2
