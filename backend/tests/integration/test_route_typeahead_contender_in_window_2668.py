"""UX-P272 / #2668 — the answer reaches the DROPDOWN, not just the window.

WHY THIS FILE EXISTS, AND WHY THE UX-P261 SUITE COULD NOT CATCH IT.
#2641 (CERT-723, GREEN) shipped the reserved headline slot and `/search` really
was fixed by it. The header dropdown was not, and stayed broken through the
merge and the deploy. Measured on production `53ddf6d1`/`04adbb77`:

    GET /api/events/search?q=Alcaraz     -> #1 = 114159 "2026 Men's US Open Winner"
    GET /api/events/typeahead?q=Alcaraz  -> five props, market 114159 ABSENT

The mechanism, confirmed end to end rather than inferred:

  * `debug_timing` reports the stage `headline_contenders` at 27 ms, so the lane
    RUNS. It is not the `_TIMED_OUT` variant.
  * Replaying the lane's SQL against production returns 114159 as its top row.
  * The typeahead's futures window is `LIMIT 20` ordered `market_tier ASC,
    volume DESC`, and `Alcaraz` has only 5 tier-1 and 3 tier-2 candidates, so
    114159 (tier 1, volume 4,108,808) is row **1** of the raw window.
  * `_rerank_search_futures` then sinks it below nine name-matching props, to
    window position 10 — inside the 20-row window, outside the 5 rows the
    dropdown ships.
  * `promote_headline_contenders` was handed that whole 20-row window as `page`
    and skipped 114159 as "already on the page", returning `promoted = 0`. With
    no promoted ids, `reserve_headline_slot` is a documented no-op.

So "already on the page" was measured against the wrong population: the window,
not the five rows the user sees. `/search` never had the bug because it slices
to its shipped ten BEFORE promoting (`futures_markets =
deduped_futures[:_SEARCH_FUTURES_PAGE]`).

THE FIXTURE THAT MATTERS, and the reason this is a new file rather than a case
appended to the UX-P261 suite. That suite's `alcaraz_client` seeds
`window=_props()` — the winner market is deliberately OUTSIDE the window, which
is the shape #2579 described. A window without the contender cannot exercise the
skip branch at all, so every test in that file is green on this defect and green
on its fix. #2668 says so in its own acceptance note. Every client below seeds a
window that ALREADY CONTAINS the contender.

RED-FIRST. `promote_headline_contenders` is imported inside test bodies, so
reverting the helper leaves this module collectable and the failures land as
assertions rather than as a collection error (gotcha #124).

CONTROLS. `TestControlsGreenInBothArms` must pass on clean master AND here.
They are what proves the red arm measures this fix and not a broken checkout.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio

from tests.integration.test_route_typeahead_headline_slot_2579 import (
    PROP_NAMES,
    WINNER_MARKET,
    WINNER_MARKET_ID,
    _client,
    _market,
    _outcome,
    _props,
    _winner_market,
)

_asyncio = pytest.mark.asyncio


def _extra_prop(mid: int, name: str):
    """A fifth name-matching prop, so the winner cannot ride inside the cut.

    `_props()` ships four. The dropdown keeps five futures rows, so with only
    four name matches the winner lands at position five and is visible WITHOUT
    any promotion — which is exactly why `Gauff` looks healthy on production
    while `Alcaraz` does not. That coincidence is pinned as a control below; the
    defect needs a fifth prop to push the answer past the cut.
    """
    return _market(
        mid=mid,
        name=name,
        volume=6_000.0,
        outcomes=[
            _outcome("Over", 0.51, mid * 10 + 1),
            _outcome("Under", 0.49, mid * 10 + 2),
        ],
    )


#: Five name matches, then the answer. This is the production shape: the
#: contender IS in the window and IS below the five rows that ship.
def _window_containing_the_winner():
    return [
        *_props(),
        _extra_prop(900_500, "Carlos Alcaraz vs Jaume Munar: Total Games"),
        _winner_market(),
    ]


@pytest_asyncio.fixture
async def winner_in_window_client(monkeypatch):
    """The #2668 case: the lane fires AND the answer is already in the window."""
    async for ac in _client(
        window=_window_containing_the_winner(),
        contenders=[_winner_market()],
        monkeypatch=monkeypatch,
    ):
        yield ac


@pytest_asyncio.fixture
async def gauff_shaped_client(monkeypatch):
    """Four name matches only — the answer already rides inside the cut.

    Production's `Gauff` shape. The route's gate does not even fire here, and
    the market must appear exactly ONCE either way.
    """
    async for ac in _client(
        window=[*_props(), _winner_market()],
        contenders=[_winner_market()],
        monkeypatch=monkeypatch,
    ):
        yield ac


@pytest_asyncio.fixture
async def no_contender_client(monkeypatch):
    """`fed` / `Trump`: the lane runs and correctly promotes nothing."""
    async for ac in _client(
        window=_window_containing_the_winner(),
        contenders=[],
        monkeypatch=monkeypatch,
    ):
        yield ac


def _futures(body):
    return [s for s in body["suggestions"] if s.get("type") == "futures"]


def _ids(body):
    return [s.get("market_id") for s in _futures(body)]


# --------------------------------------------------------------------------


class TestTheSeedIsReal:
    """Non-vacuity. Every ordering claim below is a claim about a real list."""

    @_asyncio
    async def test_the_dropdown_is_not_empty(self, winner_in_window_client):
        body = (await winner_in_window_client.get(
            "/api/events/typeahead?q=Alcaraz")).json()
        assert len(_futures(body)) >= 2, (
            "the seeded session answered with nothing — every assertion in this "
            "file would be a loop over an empty list"
        )

    @_asyncio
    async def test_the_contender_lane_actually_fires(self, winner_in_window_client):
        """If the gate does not fire, the skip branch is never reached and the
        whole file tests nothing. Production reports this stage at 27 ms."""
        body = (await winner_in_window_client.get(
            "/api/events/typeahead?q=Alcaraz&debug_timing=1")).json()
        stages = body.get("debug_timing") or {}
        assert "headline_contenders" in stages, (
            f"the contender lane did not run; stages were {sorted(stages)}"
        )
        assert "headline_contenders_TIMED_OUT" not in stages

    def test_the_window_fixture_really_contains_the_winner(self):
        """The fixture's whole point. If this ever stops holding, this file
        silently degrades into a copy of the UX-P261 suite."""
        ids = [m.id for m in _window_containing_the_winner()]
        assert WINNER_MARKET_ID in ids
        assert len(ids) > 5, "the winner must sit BELOW the five-row cut"
        assert ids.index(WINNER_MARKET_ID) >= 5


class TestTheDefect:
    """Red on master. These are the user-visible claims."""

    @_asyncio
    async def test_the_winner_market_leads_the_dropdown(
        self, winner_in_window_client
    ):
        body = (await winner_in_window_client.get(
            "/api/events/typeahead?q=Alcaraz")).json()
        ids = _ids(body)
        assert WINNER_MARKET_ID in ids, (
            "the US Open winner market is absent from the dropdown entirely — "
            f"the user sees {[s['text'] for s in _futures(body)]}"
        )
        assert ids[0] == WINNER_MARKET_ID, (
            f"the answer is on the page but not first: order was {ids}"
        )

    @_asyncio
    async def test_the_winner_appears_exactly_once(self, winner_in_window_client):
        """The counter-case guard. A fix that INSERTS the contender instead of
        hoisting it satisfies the test above and ships the same question twice."""
        body = (await winner_in_window_client.get(
            "/api/events/typeahead?q=Alcaraz")).json()
        ids = _ids(body)
        assert ids.count(WINNER_MARKET_ID) == 1, f"duplicated: {ids}"
        assert len(ids) == len(set(ids)), f"the dropdown repeats a market: {ids}"

    @_asyncio
    async def test_promoting_does_not_empty_the_rest_of_the_dropdown(
        self, winner_in_window_client
    ):
        """One tail row is the documented cost. Losing the page is not."""
        body = (await winner_in_window_client.get(
            "/api/events/typeahead?q=Alcaraz")).json()
        texts = [s["text"] for s in _futures(body)]
        assert WINNER_MARKET in texts
        assert any(p in texts for p in PROP_NAMES), (
            "every name match was evicted — the promotion grew past its cap"
        )


class TestControlsGreenInBothArms:
    """Green on clean master AND on this branch."""

    @_asyncio
    async def test_a_query_with_no_contender_promotes_nothing(
        self, no_contender_client
    ):
        """`fed` and `Trump` on production: the lane fires and finds nothing.
        A fix that reserves a slot unconditionally breaks this."""
        body = (await no_contender_client.get(
            "/api/events/typeahead?q=Alcaraz")).json()
        ids = _ids(body)
        assert ids, "control seeded nothing"
        assert ids[0] != WINNER_MARKET_ID or len(ids) == 1, (
            "a market was promoted although the contender lane returned none"
        )

    @_asyncio
    async def test_the_gauff_shape_still_shows_the_market_once(
        self, gauff_shaped_client
    ):
        """Production's accidental pass. Four name matches, so the answer is
        inside the cut on its own merits. It must not become a duplicate."""
        body = (await gauff_shaped_client.get(
            "/api/events/typeahead?q=Gauff")).json()
        ids = _ids(body)
        assert ids.count(WINNER_MARKET_ID) == 1, (
            f"the already-visible market was duplicated by the fix: {ids}"
        )

    @_asyncio
    async def test_the_dropdown_never_exceeds_its_slice(
        self, winner_in_window_client
    ):
        body = (await winner_in_window_client.get(
            "/api/events/typeahead?q=Alcaraz")).json()
        assert len(body["suggestions"]) <= 7


class TestThePromoterContract:
    """Unit level. The invariants the route relies on, asserted directly."""

    def test_a_contender_already_on_the_page_is_hoisted(self):
        from app.utils.search_headline_contender import promote_headline_contenders

        winner = SimpleNamespace(id=WINNER_MARKET_ID, name=WINNER_MARKET)
        page = [SimpleNamespace(id=i, name=f"prop {i}") for i in range(9)]
        page.append(winner)

        rows, promoted = promote_headline_contenders(page, [winner])

        assert promoted == 1, "the row was skipped, so nothing reserves a slot"
        assert rows[0] is winner
        assert len(rows) == len(page), "a hoist must not grow the page"
        assert [m.id for m in rows].count(WINNER_MARKET_ID) == 1

    def test_a_mid_page_contender_is_not_duplicated(self):
        """THE COUNTER-CASE GUARD, and it exists because the obvious one is blind.

        A naive "insert instead of hoist" fix (`rest = list(page)`) leaves the
        contender in the body AND puts a copy at the front. When the contender
        happens to be the page's LAST row that duplicate is then truncated away
        by the tail cut, so a fixture with the winner at the end passes on the
        broken fix — measured: the whole file stayed 41/41 green under that
        mutation. The duplicate is only observable when the contender sits above
        the cut line, so this fixture puts it in the MIDDLE.
        """
        from app.utils.search_headline_contender import promote_headline_contenders

        winner = SimpleNamespace(id=WINNER_MARKET_ID, name=WINNER_MARKET)
        page = [SimpleNamespace(id=i, name=f"prop {i}") for i in range(5)]
        page.insert(2, winner)

        rows, promoted = promote_headline_contenders(page, [winner])

        assert promoted == 1
        assert rows[0] is winner
        ids = [m.id for m in rows]
        assert ids.count(WINNER_MARKET_ID) == 1, (
            f"the contender was inserted rather than hoisted: {ids}"
        )
        assert len(rows) == len(page), "a hoist must not grow the page"

    def test_hoisting_loses_no_row(self):
        from app.utils.search_headline_contender import promote_headline_contenders

        winner = SimpleNamespace(id=WINNER_MARKET_ID, name=WINNER_MARKET)
        page = [SimpleNamespace(id=i, name=f"prop {i}") for i in range(9)] + [winner]
        rows, _ = promote_headline_contenders(page, [winner])
        assert {m.id for m in rows} == {m.id for m in page}

    def test_the_hoisted_row_is_the_pages_own_object(self):
        """The window's row and the contender query's row are separate result
        sets. Shipping the page's object keeps the serialized suggestion
        byte-identical to what the window would have produced."""
        from app.utils.search_headline_contender import promote_headline_contenders

        on_page = SimpleNamespace(id=WINNER_MARKET_ID, name=WINNER_MARKET)
        from_lane = SimpleNamespace(id=WINNER_MARKET_ID, name=WINNER_MARKET)
        page = [SimpleNamespace(id=i, name=f"prop {i}") for i in range(4)] + [on_page]

        rows, promoted = promote_headline_contenders(page, [from_lane])

        assert promoted == 1
        assert rows[0] is on_page, "the contender query's copy was shipped instead"

    def test_a_new_contender_still_costs_the_weakest_tail_row(self):
        """CONTROL — green on master too. The pre-existing path is unchanged."""
        from app.utils.search_headline_contender import promote_headline_contenders

        winner = SimpleNamespace(id=WINNER_MARKET_ID, name=WINNER_MARKET)
        page = [SimpleNamespace(id=i, name=f"prop {i}") for i in range(10)]
        rows, promoted = promote_headline_contenders(page, [winner])
        assert promoted == 1
        assert rows[0] is winner
        assert len(rows) == 10
        assert 9 not in [m.id for m in rows], "the tail row should have been cut"

    def test_a_different_market_sharing_a_dedup_key_is_still_skipped(self):
        """CONTROL — green on master too. Alex's blend-is-the-product ruling.

        Hoisting is keyed on IDENTITY. A different market that normalizes to a
        page row's key stays a skip, so one question cannot reach the page under
        two sources at two prices.
        """
        from app.utils.search_headline_contender import promote_headline_contenders

        kalshi = SimpleNamespace(id=1, name="US Open Men's Singles Winner")
        polymarket = SimpleNamespace(id=2, name="2026 Men's US Open Winner")
        page = [SimpleNamespace(id=50 + i, name=f"prop {i}") for i in range(9)]
        page.append(kalshi)

        rows, promoted = promote_headline_contenders(
            page, [polymarket], dedup_key=lambda m: "one-question"
        )

        assert promoted == 0
        assert rows == page
        assert polymarket not in rows


class TestSearchIsInertByConstruction:
    """`/search` cannot reach the hoist branch, and this pins the reason.

    Its lane only fires when EVERY row of the shipped page is a name match, and
    the caller filters contenders down to outcome-only rows. So a contender that
    is already on `/search`'s page makes the gate false and the lane never runs.
    """

    def test_a_contender_on_the_page_makes_the_search_gate_false(self):
        from app.routes.events import _query_name_match

        expanded = [("alcaraz", None)]
        winner = SimpleNamespace(name=WINNER_MARKET)
        props = [SimpleNamespace(name=n) for n in PROP_NAMES]

        assert all(_query_name_match(m, expanded) for m in props), (
            "the props must be name matches, or the gate is false for the "
            "wrong reason and this control proves nothing"
        )
        assert not _query_name_match(winner, expanded), (
            "the winner must be outcome-only — that is what the caller's own "
            "filter selects for"
        )
        page_with_winner = [*props, winner]
        assert not all(
            _query_name_match(m, expanded) for m in page_with_winner
        ), "the /search gate would fire with the contender on its page"
