"""#11493 — tapping the Division Winner card lands on a page without "AL Central <1%".

Production, 2026-10-23 10:22Z (main v5892): PR #11502 took the eliminated AL
Central off Discover's "MLB 2026: World Series Division Winner" card (polymarket
63448360), but the card's destination ``/futures/63448360`` at 390px still
printed All Outcomes row 3 "AL Central · OPEN 13% · LATEST <1%" and listed "AL
Central" in the Probability Trend legend. All five AL Central clubs are
``championship: eliminated`` in ``/api/playoffs/mlb``; the venue has not graded
the leg, so it keeps its last quote (0.0005, 20 Oct).

The detail route now applies the card's rule (``grid_out_division_legs``) before
its divisor, and the history route leaves the leg out of the DRAWN selection —
its field, which the scale contract divides and validates by, is untouched.
Assertions are on served payloads, never on source text.

Fixtures: the board's six legs as ``/api/futures/63448360`` served them at
10:25Z, and the grid's (conference, division, title state) counts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import futures as futures_route
from app.routes.futures import _format_market_detail
from app.utils import grid_out_division_legs as mod
from tests.test_discover_division_card_reads_the_grid_out_verdict_11493 import _grid
from tests.test_futures_history_chartable_selection_7546 import _Result, _Session

BOARD = 63448360
KEY = "baseball:MLB:division_winner:2026"
NAME = "MLB 2026: World Series Division Winner"

#: (id, name, price, opening, is_winner) as served at 10:25Z. Graded legs carry
#: no price.
_LEGS = [
    (239258839, "NL Central", 0.63, 0.18, None),
    (239258838, "AL East", 0.36, 0.24, None),
    (239631550, "AL Central", 0.0005, 0.13, None),
    (240589843, "NL East", None, 0.095, False),
    (239214419, "AL West", None, 0.06, False),
    (239274268, "NL West", None, 0.19, False),
]
AL_CENTRAL = 239631550


def _outcome(oid, name, prob, opening, is_winner):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"0x{oid:064x}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=opening,
        opening_american_odds=None,
        is_winner=is_winner,
        resolution_source="clob_authoritative" if is_winner is False else None,
        last_updated=None,
        team_id=None,
        team=None,
        current_yes_bid=None,
        current_yes_ask=None,
    )


def _board(key=KEY, name=NAME, status="open"):
    return SimpleNamespace(
        id=BOARD,
        external_id="mlb-2026-world-series-division-winner",
        name=name,
        description=None,
        sport=None,
        sport_name=None,
        category=None,
        llm_sport_category="baseball",
        status=status,
        source="polymarket",
        market_type="field",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=key,
        hook_description=None,
        category_tags=None,
        image_url=None,
        market_metadata={},
        event_id=None,
        outcomes=[_outcome(*leg) for leg in _LEGS],
    )


def _names(detail):
    return [o["name"] for o in detail["outcomes"]]


def _cached(payload):
    """Patch the grid read at its cache seam — the route's own wiring runs."""
    return patch.object(mod, "read_cached_grid", AsyncMock(return_value=payload))


# ── the serializer ───────────────────────────────────────────────────────────


class TestTheSerializer:
    def test_the_out_division_leaves_all_outcomes(self):
        labels = mod.out_division_labels(_grid(), "2026")
        detail = _format_market_detail(_board(), [], set(), out_division_labels=labels)
        assert "AL Central" not in _names(detail)
        assert AL_CENTRAL not in {o["id"] for o in detail["outcomes"]}

    def test_control_the_live_divisions_keep_their_numbers(self):
        """The 0.0005 leaving the divisor moves no printed number."""
        labels = mod.out_division_labels(_grid(), "2026")
        before = _format_market_detail(_board(), [], set())
        after = _format_market_detail(_board(), [], set(), out_division_labels=labels)

        def price(d):
            return {o["name"]: o["probability"] for o in d["outcomes"]}

        for name in ("NL Central", "AL East"):
            assert round(price(after)[name], 2) == round(price(before)[name], 2)

    def test_strawman_without_labels_the_page_still_prints_it(self):
        """Today's payload: the defect the reader saw is in the fixture."""
        detail = _format_market_detail(_board(), [], set())
        assert "AL Central" in _names(detail)


# ── the detail route ─────────────────────────────────────────────────────────


async def _detail(market, grid):
    result = MagicMock()
    result.scalar_one_or_none.return_value = market
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    seams = {
        "_load_market_sources": AsyncMock(return_value=([], [])),
        "_withheld_price_outcome_ids": AsyncMock(return_value=set()),
        "_game_container_leg_sides": AsyncMock(return_value={}),
        "_fleet_newest_observation": AsyncMock(return_value=None),
        "_game_container_lead_leg": AsyncMock(return_value=None),
        "_game_container_of_event_id": AsyncMock(return_value=None),
    }
    with _cached(grid), patch.multiple(futures_route, **seams):
        return await futures_route.get_futures_market(
            BOARD, db=db, representation=futures_route.REPRESENTATION_SOURCE
        )


class TestTheDetailRoute:
    @pytest.mark.anyio
    async def test_the_served_page_drops_the_out_division(self):
        detail = await _detail(_board(), _grid())
        assert "AL Central" not in _names(detail)
        assert {"NL Central", "AL East"} <= set(_names(detail))

    @pytest.mark.anyio
    async def test_a_cold_grid_keeps_every_leg(self):
        """A miss is today's answer, never a reason to build."""
        detail = await _detail(_board(), None)
        assert "AL Central" in _names(detail)

    @pytest.mark.anyio
    async def test_last_seasons_grid_keeps_every_leg(self):
        detail = await _detail(_board(), _grid(season="2025"))
        assert "AL Central" in _names(detail)

    @pytest.mark.anyio
    async def test_another_board_never_reads_the_grid(self):
        """A per-division board ("NHL Atlantic Division Winner") is not this question."""
        read = AsyncMock(return_value=_grid())
        market = _board(key="hockey:NHL:division_winner:2026", name="NHL Atlantic Division Winner")
        result = MagicMock()
        result.scalar_one_or_none.return_value = market
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        with patch.object(mod, "read_cached_grid", read), patch.multiple(
            futures_route,
            _load_market_sources=AsyncMock(return_value=([], [])),
            _withheld_price_outcome_ids=AsyncMock(return_value=set()),
            _game_container_leg_sides=AsyncMock(return_value={}),
            _fleet_newest_observation=AsyncMock(return_value=None),
            _game_container_lead_leg=AsyncMock(return_value=None),
            _game_container_of_event_id=AsyncMock(return_value=None),
        ):
            await futures_route.get_futures_market(
                BOARD, db=db, representation=futures_route.REPRESENTATION_SOURCE
            )
        read.assert_not_awaited()


# ── the history route (the trend legend) ─────────────────────────────────────

_AGES_HOURS = [30.0, 24.0, 18.0, 12.0, 6.0, 3.0]
#: Hourly for the whole week — dense enough that no extend tier runs, so the
#: FIRST selection is the one served (the sparse rows above re-select).
_DENSE_AGES_HOURS = [h + 0.5 for h in range(167)]


def _rows(ages=_AGES_HOURS):
    rows = []
    for oid, _name, prob, _opening, _won in _LEGS:
        if prob is None:
            continue
        for age in ages:
            rows.append(
                SimpleNamespace(
                    outcome_id=oid,
                    bookmaker="polymarket",
                    # A small wobble per hour, so identical consecutive prices
                    # cannot collapse the dense week back into a sparse one.
                    probability=prob * (1 + (int(age) % 3 - 1) * 0.01),
                    yes_bid=None,
                    yes_ask=None,
                    last_price=None,
                    captured_at=datetime.now(timezone.utc) - timedelta(hours=age),
                )
            )
    rows.sort(key=lambda r: r.captured_at)
    return rows


async def _history(grid, outcome_id=None, ages=_AGES_HOURS):
    rows = _rows(ages)
    # Two answers, not 7546's three: a Polymarket board asks no trade-row
    # question before its snapshot read, so the second execute IS that read
    # (and the repeat serves the extend tiers the sparse rows trigger).
    session = _Session(_Result(value=_board()), _Result(rows=rows))
    with _cached(grid):
        return await futures_route.get_futures_history(
            BOARD, outcome_id=outcome_id, hours=168, top_n=10, champion=None, db=session
        )


def _drawn(payload):
    return {entry["name"] for entry in payload["outcomes"]}


class TestTheTrendLegend:
    @pytest.mark.anyio
    async def test_the_out_division_is_not_drawn(self):
        assert _drawn(await _history(_grid())) == {"NL Central", "AL East"}

    @pytest.mark.anyio
    async def test_a_dense_week_does_not_draw_it_either(self):
        payload = await _history(_grid(), ages=_DENSE_AGES_HOURS)
        assert _drawn(payload) == {"NL Central", "AL East"}

    @pytest.mark.anyio
    async def test_strawman_a_cold_dense_grid_draws_it(self):
        assert "AL Central" in _drawn(await _history(None, ages=_DENSE_AGES_HOURS))

    @pytest.mark.anyio
    async def test_strawman_a_cold_grid_draws_it(self):
        """The fixture carries the defect: without the verdict, it is drawn."""
        assert "AL Central" in _drawn(await _history(None))

    @pytest.mark.anyio
    async def test_an_explicit_outcome_ask_is_served(self):
        payload = await _history(_grid(), outcome_id=AL_CENTRAL)
        assert _drawn(payload) == {"AL Central"}
