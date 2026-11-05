"""#11995 replaces #11948: normalize the complete field on card and page."""

import pytest

from tests import test_midterms_kalshi_grade_reaches_served_card as proof
from tests.test_midterms_kalshi_grade_reaches_served_card import served  # noqa: F401

PRICES = [
    ("Nebraska", 0.91),
    ("Kansas", 0.1205),
    ("Texas", 0.115),
    ("Florida", 0.095),
    ("Nevada", 0.0905),
    ("Pennsylvania", 0.07),
]
# A healthy complete fixture; the real one-cent-bound venue field is below.
PRICES += [(f"State {index}", 0.004) for index in range(17)] + [
    ("Zero-priced state", 0.0)
]


@pytest.fixture
def full_field(monkeypatch):
    monkeypatch.setitem(proof.KALSHI_OUTCOMES, 108629, PRICES)
    original = proof._market

    def market(*args, **kwargs):
        row = original(*args, **kwargs)
        if row.id == 108629:
            row.mutually_exclusive = True
        return row

    monkeypatch.setattr(proof, "_market", market)


def test_full_http_read_normalizes_all_24_prices_before_the_top_five(
    served, full_field
):
    _, read = served
    _, cards = read()
    outcomes = cards[108629]["top_outcomes"]
    assert len(outcomes) == 24
    mass = sum(p for _, p in PRICES)
    assert {o["name"]: o["probability"] for o in outcomes} == pytest.approx(
        {n: p / mass for n, p in PRICES}
    )
    assert sum(o["rendered_percent"] for o in outcomes) == 100
    assert outcomes[0]["name"] == "Nebraska"
    assert outcomes[0]["probability"] == pytest.approx(0.91 / mass)
    assert sum(o["probability"] for o in outcomes) == pytest.approx(1)
    assert len({o["id"] for o in outcomes}) == 24


def test_the_detail_pages_withheld_price_stays_withheld_without_scaling_other_legs(
    served, full_field, monkeypatch
):
    original = proof._database

    def database(*args, **kwargs):
        db, refused = original(*args, **kwargs)
        refused[108629] = {10862900}
        return db, refused

    monkeypatch.setattr(proof, "_database", database)
    _, read = served
    _, cards = read()
    outcomes = {o["name"]: o["probability"] for o in cards[108629]["top_outcomes"]}
    assert len(outcomes) == 24
    assert outcomes["Nebraska"] is None
    assert outcomes["Kansas"] == 0.1205
    assert outcomes["Zero-priced state"] == 0


# Nov 3, 11:29 PM PT: raw sum 118.5%, priced-leg divisor 112.5%.
VENUE_FIELD_PRICES = [
    ("Kansas", 0.948),
    ("Alaska", 0.035),
    ("Florida", 0.03),
    ("Nebraska", 0.025),
    ("Oklahoma", 0.02),
    ("Pennsylvania", 0.001),
    ("Minnesota", 0.0055),
    ("New York", 0.001),
    ("Nevada", 0.001),
    ("Georgia", 0.001),
    ("Ohio", 0.01),
    ("Arizona", 0.0055),
    ("New Hampshire", 0.0195),
    ("Iowa", 0.0015),
    ("Michigan", 0.001),
    ("New Mexico", 0.0055),
    ("Colorado", 0.01),
    ("Maine", 0.0035),
    ("Wisconsin", 0.001),
    ("South Carolina", 0.01),
    ("South Dakota", 0.01),
    ("Vermont", 0.01),
    ("Oregon", 0.02),
    ("Texas", 0.01),
]


@pytest.fixture
def raw_governor_field(full_field, monkeypatch):
    monkeypatch.setitem(proof.KALSHI_OUTCOMES, 108629, VENUE_FIELD_PRICES)


def _detail_field(*, market_id=108629, source="kalshi", winner=None):
    market = proof._market(
        market_id,
        "Closest Governor race in 2026?",
        source,
        VENUE_FIELD_PRICES,
        winner=winner,
        shape="rest_poll" if winner else None,
    )
    market.mutually_exclusive = True
    return market


def test_one_winner_detail_matches_the_midterms_priced_mass_with_bound_tail(
    served, raw_governor_field
):
    from app.routes.futures import _format_market_detail

    _, read = served
    _, cards = read()
    market = _detail_field()
    detail = _format_market_detail(market)
    card_prices = {o["name"]: o["probability"] for o in cards[108629]["top_outcomes"]}
    detail_prices = {o["name"]: o["probability"] for o in detail["outcomes"]}

    assert all("rendered_percent" not in o for o in detail["outcomes"])
    assert all("rendered_percent" not in o for o in cards[108629]["top_outcomes"])
    assert sum(card_prices.values()) == pytest.approx(1.185 / 1.125)
    assert len(detail_prices) == 24
    assert detail_prices == card_prices
    assert detail_prices == pytest.approx(
        {n: p / 1.125 for n, p in VENUE_FIELD_PRICES}, abs=1e-8
    )
    assert detail["mutually_exclusive"] is market.mutually_exclusive is True


def test_normalized_field_withholds_raw_opening_and_dated_move():
    from datetime import datetime, timedelta, timezone

    from app.routes.futures import _format_market_detail

    market = _detail_field()
    kansas = market.outcomes[0]
    kansas.opening_probability = 0.90
    kansas.probability_change_24h = 0.001
    market.market_metadata = {
        "dated_movement_basis": {
            str(kansas.id): [
                0.90,
                (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat(),
            ]
        }
    }
    detail = _format_market_detail(market)
    row = next(o for o in detail["outcomes"] if o["name"] == "Kansas")

    assert row["probability"] == pytest.approx(0.948 / 1.125)
    assert row["opening_probability"] is None
    assert row["probability_change_24h"] is None
    assert detail["openings_withheld"] is True


def test_raw_field_still_withholds_an_unsupported_price():
    from app.routes.futures import _format_market_detail

    market = _detail_field()
    detail = _format_market_detail(
        market, unsupported_price_outcome_ids={market.outcomes[0].id}
    )
    rows = {o["name"]: o for o in detail["outcomes"]}
    assert rows["Kansas"]["probability"] is None
    assert rows["Alaska"]["probability"] == 0.035
    assert detail["prices_withheld"] == 1


@pytest.mark.parametrize(
    "market_id,source", [(108630, "kalshi"), (108629, "polymarket")]
)
def test_other_fields_use_the_same_venue_blind_display_policy(market_id, source):
    from app.routes.futures import _format_market_detail

    detail = _format_market_detail(_detail_field(market_id=market_id, source=source))
    kansas = next(o for o in detail["outcomes"] if o["name"] == "Kansas")
    assert kansas["probability"] == pytest.approx(0.948 / 1.125)
    assert detail["mutually_exclusive"] is True


def test_raw_field_preserves_a_real_venue_result(served, raw_governor_field):
    from app.routes.futures import _format_market_detail

    state, read = served
    state.update(graded_mid=108629, shape="rest_poll")
    _, cards = read()
    winner = proof._upset(108629)
    detail = _format_market_detail(_detail_field(winner=winner))

    assert detail["status"] == "resolved"
    assert {o["name"] for o in detail["outcomes"] if o["is_winner"]} == {winner}
    assert {o["resolution_source"] for o in detail["outcomes"]} == {"api_settlement"}
    assert cards[108629]["settled_winner"] == winner
    assert all(o["probability"] is None for o in cards[108629]["top_outcomes"])
