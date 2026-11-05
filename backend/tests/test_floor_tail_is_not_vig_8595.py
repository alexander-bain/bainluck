"""#8595 — a tail of one-cent long shots is not vig, and the squeeze stops dividing by it.

WHAT A READER SAW. `/futures/209` (*NL MVP Winner?*, Kalshi) at 390px,
2026-09-25 ~10:10Z: hero **65% · Pete Crow-Armstrong**. The same question on the
Cubs @ Red Sox game page read **MVP 99%**, and Kalshi's own book the same minute
was **bid 0.98 / ask 0.99**.

THE ROWS (read-only db-query on `futures_outcomes`, market 209, 2026-09-25 11:3xZ):

    0.985000 × 1   Pete Crow-Armstrong
    0.015000 × 1   Shohei Ohtani
    0.010000 × 51  every other candidate — Kalshi's one-cent floor, bid 0 / ask 0.01

The sum, 1.51, is under `_FIELD_SUM_MAX` (1.60), so `normalize_display_probs` read a
coherent one-winner field with 51 points of vig and printed 0.985 / 1.51 = 0.6523.
Those 51 points are 51 upper bounds. Without them the field sums to 1.00.

The card (`_feed_display_scale`) divides by the same mass as the page, and the chart
runs the page's own squeeze, so all three surfaces are pinned here.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app.routes.futures as futures_routes
from app.routes.feed import _feed_display_scale, _scale_display_probability
from app.routes.futures import _format_market_detail
from app.utils.futures_history_basis import devigged_consensus_by_time
from app.utils.outcome_display import (
    display_divisor_mass,
    is_venue_floor_price,
    normalize_display_probs,
)

MEASURED_AT = datetime(2026, 9, 25, 10, 10, tzinfo=timezone.utc)
LEADER, OHTANI = 1, 2
#: (outcome_id, name, stored probability) — market 209 as production stores it.
NL_MVP = [(LEADER, "Pete Crow-Armstrong", 0.985), (OHTANI, "Shohei Ohtani", 0.015)] + [
    (100 + i, f"Candidate {i}", 0.010) for i in range(51)
]
#: What the page printed: 0.985 / 1.51.
PAGE_BEFORE = 0.6523


def _page(rows, **kwargs):
    legs = [{"id": i, "probability": p} for i, _n, p in rows]
    moved = normalize_display_probs(legs, **kwargs)
    return moved, {leg["id"]: leg["probability"] for leg in legs}


def _card(rows, mutually_exclusive=True):
    outs = [SimpleNamespace(id=i, current_probability=p) for i, _n, p in rows]
    scale = _feed_display_scale(outs, "field", mutually_exclusive=mutually_exclusive)
    return scale, {i: _scale_display_probability(p, scale) for i, _n, p in rows}


def _outcome(outcome_id, name, prob):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        external_id=f"KXMLBNLMVP-26-{outcome_id}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=MEASURED_AT,
        price_changed_at=MEASURED_AT,
        team_id=None,
    )


def _market(rows):
    return SimpleNamespace(
        id=209,
        name="NL MVP Winner?",
        description=None,
        category="award",
        source="kalshi",
        external_id="KXMLBNLMVP-26",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="field",
        market_tier=1,
        llm_sport_category="baseball",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id="kalshi:KXMLBNLMVP-26",
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[_outcome(*r) for r in rows],
    )


def _detail(rows):
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return MEASURED_AT if tz is None else MEASURED_AT.astimezone(tz)

    with patch.object(futures_routes, "datetime", _Frozen):
        payload = _format_market_detail(_market(rows), None, set())
    return {o["id"]: o["probability"] for o in payload["outcomes"]}


class TestTheFixtureCanActuallyFail:
    def test_the_raw_field_sits_inside_the_squeeze_band(self):
        """Above 1.60 the page already printed raw and there was nothing to fix."""
        raw = sum(p for _i, _n, p in NL_MVP)
        assert 1.05 < raw <= 1.60
        assert raw == pytest.approx(1.51, abs=1e-9)

    def test_dividing_by_every_leg_is_the_65_the_reader_saw(self):
        raw = sum(p for _i, _n, p in NL_MVP)
        assert round(0.985 / raw, 4) == PAGE_BEFORE


class TestTheSpecimen:
    def test_the_detail_payload_prints_the_venues_price(self):
        """The issue's guard: `/api/futures/209` leader within 2 pts of 0.985."""
        served = _detail(NL_MVP)
        assert served[LEADER] == pytest.approx(0.985, abs=0.02)
        assert served[LEADER] != pytest.approx(PAGE_BEFORE, abs=0.01)

    def test_the_squeeze_does_not_fire_at_all(self):
        moved, page = _page(NL_MVP)
        assert moved is False
        assert page[LEADER] == 0.985
        assert page[OHTANI] == 0.015
        assert page[100] == 0.010

    def test_the_card_prints_the_same_number(self):
        scale, card = _card(NL_MVP)
        assert scale == 1.0
        assert card[LEADER] == 0.985

    def test_the_chart_prints_the_same_number(self):
        """The Probability Trend runs the page's squeeze per instant (#4992)."""
        column = {i: p for i, _n, p in NL_MVP}
        point = devigged_consensus_by_time(
            {MEASURED_AT: {"kalshi": column}}, mutually_exclusive=True
        )[MEASURED_AT]
        assert point[LEADER] == pytest.approx(0.985, abs=5e-4)


class TestOnlyTheFloorLeavesTheDivisor:
    def test_the_predicate_is_exactly_one_cent(self):
        assert is_venue_floor_price(0.01)
        assert is_venue_floor_price(0.010000)
        for p in (0.0099, 0.009901, 0.0066, 0.005, 0.0005, 0.011, 0.0, None):
            assert not is_venue_floor_price(p), p

    def test_a_sub_cent_tail_is_a_real_price_and_stays_in_the_divisor(self):
        """De-vigged sportsbook long shots and Polymarket 0.001 ticks sit under a cent.

        The same field with the tail at 0.0066 instead of 0.010 is a coherent
        distribution with a real tail, and it squeezes exactly as it always did.
        """
        rows = NL_MVP[:2] + [(100 + i, f"c{i}", 0.0066) for i in range(51)]
        moved, page = _page(rows)
        raw = 0.985 + 0.015 + 51 * 0.0066
        assert moved is True
        assert page[LEADER] == pytest.approx(0.985 / raw, abs=1e-4)

    def test_priced_legs_that_overround_are_still_squeezed(self):
        """The squeeze is kept, not removed: it divides by the priced legs alone."""
        rows = [(1, "a", 0.70), (2, "b", 0.40)] + [
            (100 + i, f"c{i}", 0.010) for i in range(30)
        ]
        moved, page = _page(rows)
        assert moved is True
        assert page[1] == pytest.approx(0.70 / 1.10, abs=1e-4)
        assert page[2] == pytest.approx(0.40 / 1.10, abs=1e-4)
        assert page[1] + page[2] == pytest.approx(1.0, abs=1e-3)
        # The floor legs follow the priced legs' scale: one divisor on the page.
        assert page[100] == pytest.approx(0.010 / 1.10, abs=1e-4)

    def test_and_the_card_divides_every_leg_by_the_same_mass(self):
        rows = [(1, "a", 0.70), (2, "b", 0.40)] + [
            (100 + i, f"c{i}", 0.010) for i in range(30)
        ]
        _moved, page = _page(rows)
        scale, card = _card(rows)
        assert scale == pytest.approx(1.10, abs=1e-9)
        for oid in page:
            assert card[oid] == page[oid], oid

    def test_the_overround_ceiling_still_reads_the_full_sum(self):
        """#1200 unchanged: past 1.60 with the tail counted, the field prints raw."""
        rows = NL_MVP[:2] + [(100 + i, f"c{i}", 0.010) for i in range(70)]
        moved, page = _page(rows)
        assert moved is False
        assert page[LEADER] == 0.985
        scale, _card_legs = _card(rows)
        assert scale == 1.0

    def test_a_card_that_does_not_know_keeps_the_full_sum(self):
        """`mutually_exclusive=None` is "caller does not know" and is never widened."""
        scale, _card_legs = _card(NL_MVP, mutually_exclusive=None)
        assert scale == pytest.approx(1.51, abs=1e-9)

    def test_the_mass_skips_only_floor_legs(self):
        assert display_divisor_mass([0.985, 0.015] + [0.01] * 51) == pytest.approx(1.0)
        assert display_divisor_mass([0.5, None, 0.0, 0.0066]) == pytest.approx(0.5066)


class TestEveryPageLegMatchesTheCard:
    @pytest.mark.parametrize(
        "rows",
        [
            NL_MVP,
            [(1, "a", 0.55), (2, "b", 0.35), (3, "c", 0.12)]
            + [(100 + i, f"c{i}", 0.010) for i in range(20)],
        ],
        ids=["nl-mvp-209", "priced-overround-with-floor-tail"],
    )
    def test_one_divisor(self, rows):
        _moved, page = _page(rows)
        _scale, card = _card(rows)
        for oid in page:
            assert card[oid] == page[oid], oid
