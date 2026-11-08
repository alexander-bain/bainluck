"""#12335: a Search futures card prints the numbers the page it opens prints.

THE DEFECT, on screen (Sat Nov 7, 9:31 PM PT). `/search?q=chiefs` drew the
`NFL: 2027 Champion` card (id 129037, a Polymarket row) at Bills 14% · Jaguars
11% · Chiefs 9%. One tap later, `/futures/129037` — which opts into
`representation=verified_title` (#10224) — printed the three-venue blend:
Bills 13% · Jaguars 10% · Chiefs 8%. The card read its own row alone.

THE SHIP. For a title question, the card is built from the SAME composition the
page uses (`routes/futures.py::_resolve_verified_title`), through the card's own
selection and the shared normalizer, so the two print the same value per
outcome. These tests compose the page's detail and the card from ONE market and
ONE composition and compare them outcome by outcome, rather than restating
either rule.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes.events import _format_futures_for_search
from app.routes.futures import _apply_verified_title_to_detail, _format_market_detail
from app.utils.futures_verified_title import Composition, OutcomeOverlay

NOW = datetime.now(timezone.utc)

# The specimen's names and its Polymarket row's own prices (search, 9:31 PM).
SOURCE = {
    "San Francisco 49ers": 0.137,
    "Buffalo Bills": 0.135,
    "Chicago Bears": 0.1225,
    "Jacksonville Jaguars": 0.1155,
    "Kansas City Chiefs": 0.0885,
    "Detroit Lions": 0.07,
}
# The page's three-venue values for the same legs (detail, 9:32 PM).
BLEND = {
    "San Francisco 49ers": 0.137,
    "Buffalo Bills": 0.125,
    "Chicago Bears": 0.1225,
    "Jacksonville Jaguars": 0.1009,
    "Kansas City Chiefs": 0.075,
    "Detroit Lions": 0.068,
}


def _market():
    m = FuturesMarket(
        id=129037,
        source="polymarket",
        external_id="pm-sb-2027",
        name="NFL: 2027 Champion",
        status="open",
        mutually_exclusive=True,
        market_tier=1,
        market_type="field",
        category="sports",
        llm_sport_category="football",
        market_metadata={"polymarket_event_slug": "pro-football-2027-champion"},
        resolution_date=NOW + timedelta(days=90),
        updated_at=NOW,
    )
    m.sport = None
    m.outcomes = [
        FuturesOutcome(
            id=1000 + i,
            market_id=129037,
            external_id=f"leg-{i}",
            name=name,
            current_probability=p,
            current_american_odds=None,
            probability_change_24h=0.01,
            rank=i + 1,
            is_winner=None,
            resolution_source=None,
            last_updated=NOW - timedelta(minutes=5),
        )
        for i, (name, p) in enumerate(SOURCE.items())
    ]
    return m


def _composition(market, *, changed=True):
    by_name = {o.name: o.id for o in market.outcomes}
    return Composition(
        question_identity={"competition": "NFL"},
        overlay={
            by_name[name]: OutcomeOverlay(
                probability=p if changed else SOURCE[name],
                contributing_sources=["odds_api", "kalshi", "polymarket"],
                observed_at=NOW.isoformat(),
                aggregation_rule="blend",
                changed=changed,
            )
            for name, p in BLEND.items()
        },
        contributing_sources=["odds_api", "kalshi", "polymarket"],
    )


def _page(market, verdict):
    detail = _format_market_detail(market, None, set(), normalize_numbers=False)
    _apply_verified_title_to_detail(detail, verdict, market)
    return {o["name"]: o["probability"] for o in detail["outcomes"]}


def test_the_card_prints_the_pages_value_for_every_outcome_it_shows():
    market = _market()
    verdict = _composition(market)
    page = _page(market, verdict)
    card = _format_futures_for_search(market, set(), verified=verdict)
    shown = {o["name"]: o["probability"] for o in card["top_outcomes"]}
    assert shown, "the card printed no ladder"
    for name, p in shown.items():
        assert p == pytest.approx(page[name], abs=1e-9), (name, p, page[name])


def test_control_without_the_composition_the_card_prints_its_own_venue():
    """Before #12335 — and still for every card that is not a title question."""
    market = _market()
    page = _page(market, _composition(market))
    card = _format_futures_for_search(market, set())
    shown = {o["name"]: o["probability"] for o in card["top_outcomes"]}
    assert shown["Buffalo Bills"] != pytest.approx(page["Buffalo Bills"], abs=1e-4)
    assert "representation" not in card


def test_the_card_orders_its_ladder_by_the_pages_values():
    market = _market()
    verdict = _composition(market)
    page = _page(market, verdict)
    card = _format_futures_for_search(market, set(), verified=verdict)
    names = [o["name"] for o in card["top_outcomes"]]
    expected = sorted(names, key=lambda n: -page[n])
    assert names == expected


def test_a_composed_value_carries_no_source_measured_movement():
    market = _market()
    card = _format_futures_for_search(market, set(), verified=_composition(market))
    assert all(o.get("movement") is None for o in card["top_outcomes"])


def test_the_card_says_which_numbers_these_are():
    market = _market()
    card = _format_futures_for_search(market, set(), verified=_composition(market))
    assert card["representation"] == "verified_title"
    assert card["contributing_sources"] == ["odds_api", "kalshi", "polymarket"]


def test_an_outcome_the_composition_does_not_price_prints_no_number():
    """The page's `_overlay_current(row, None)` rule: no overlay, no value."""
    market = _market()
    verdict = _composition(market)
    lions = next(o.id for o in market.outcomes if o.name == "Detroit Lions")
    overlay = dict(verdict.overlay)
    overlay.pop(lions)
    thinned = Composition(verdict.question_identity, overlay, verdict.contributing_sources)
    page = _page(market, thinned)
    card = _format_futures_for_search(market, set(), verified=thinned)
    for o in card["top_outcomes"]:
        assert o["probability"] == pytest.approx(page[o["name"]], abs=1e-9) if page[o["name"]] is not None else o["probability"] is None
    assert page["Detroit Lions"] is None


@pytest.mark.asyncio
async def test_no_engine_means_no_composition_and_no_read():
    """A test double keeps the card's own prices and issues nothing."""
    from app.routes.events import _search_verified_titles

    class _Fake:
        bind = None

        async def execute(self, *a, **k):  # pragma: no cover - must not be called
            raise AssertionError("no read without an engine")

    assert await _search_verified_titles(_Fake(), [_market()], None) == {}


@pytest.mark.asyncio
async def test_a_market_that_is_not_a_title_question_costs_nothing():
    from app.routes.events import _search_verified_titles

    market = _market()
    market.market_metadata = {"polymarket_event_slug": "some-other-event"}

    class _Fake:
        bind = None

    assert await _search_verified_titles(_Fake(), [market], None) == {}


def test_the_search_route_resolves_before_it_formats():
    import inspect

    from app.routes import events

    src = inspect.getsource(events.search_events)
    resolve = src.index("_verified_by_id = await _search_verified_titles(")
    fmt = src.index("verified=_verified_by_id.get(m.id)")
    assert resolve < fmt


def test_a_moved_field_ignores_the_stored_fields_24h_comparison(monkeypatch):
    """The page compares against the stored field only when nothing moved
    (`_apply_verified_title_to_detail`); a stored-field movement would describe
    the venue's estimator, not the blend the card now prints."""
    import app.utils.futures_market_snapshot as snap

    monkeypatch.setattr(
        snap,
        "normalized_field_comparisons",
        lambda market, rows, **kw: {
            r["id"]: {"probability": r["probability"], "opening_probability": 0.5,
                      "probability_change_24h": 0.04}
            for r in rows
        },
    )
    market = _market()
    moved = _format_futures_for_search(market, set(), verified=_composition(market))
    assert all(o.get("movement") is None for o in moved["top_outcomes"])
    control = _format_futures_for_search(market, set())
    assert any(o.get("movement") == 0.04 for o in control["top_outcomes"]), (
        "CONTROL: the patched comparison must reach an unverified card, or this test proves nothing"
    )
