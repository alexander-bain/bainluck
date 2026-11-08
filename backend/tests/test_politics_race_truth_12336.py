"""#12336. Finished election forecasts retire without manufacturing results."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import politics

AFTER = datetime(2026, 11, 8, 18, tzinfo=UTC)
BEFORE = datetime(2026, 11, 2, 18, tzinfo=UTC)


def market(mid, name, ticker, *, outcomes=None, **extra):
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=ticker,
        source="kalshi",
        status="open",
        mutually_exclusive=True,
        llm_sport_category="politics",
        category="news",
        group_id=None,
        resolution_date=AFTER + timedelta(days=90),
        updated_at=AFTER,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        market_metadata=None,
        outcomes=[
            SimpleNamespace(
                id=mid * 10 + i,
                name=label,
                current_probability=prob,
                is_winner=None,
                resolution_source=None,
                last_updated=AFTER,
                external_id=None,
                rank=i + 1,
                probability_change_24h=0,
            )
            for i, (label, prob) in enumerate(
                outcomes or [("Democratic", 0.974), ("Republican", 0.026)]
            )
        ],
        **extra,
    )


@pytest.mark.parametrize("exclusive", [True, False, None])
def test_house_popular_vote_forecast_retires_for_every_exclusivity(exclusive):
    field = market(
        65521844,
        "2026 Midterms: House popular vote vs. generic ballot?",
        "KXHOUSEPOPVSGB-26NOV03",
        outcomes=[("D+3 to D+4.9", 0.13), ("D+5 to D+6.9", 0.13)],
    )
    field.mutually_exclusive = exclusive
    assert not politics._finished_midterms_market(field, BEFORE)
    assert politics._finished_midterms_market(field, AFTER)
    assert all(o.is_winner is None for o in field.outcomes)


def test_future_and_undated_midterms_forecasts_keep_their_own_window():
    future = market(1, "2030 Midterms: House popular vote?", "KXHOUSEPOPVSGB-30NOV05")
    future.resolution_date = datetime(2031, 3, 1, tzinfo=UTC)
    unknown = market(2, "Midterms: House popular vote?", "UNKNOWN")
    unknown.resolution_date = None
    assert not politics._finished_midterms_market(future, AFTER)
    assert not politics._finished_midterms_market(unknown, AFTER)


def test_map_retires_2026_forecasts_and_can_advance_to_a_supported_cycle():
    alaska = market(109095, "Alaska Senate winner?", "SENATEAK-26")
    later = market(2, "Alaska Senate winner? (2028)", "SENATEAK-28")
    later.resolution_date = datetime(2029, 1, 4, tzinfo=UTC)
    assert politics._build_senate_map([alaska], now=BEFORE) == {"AK": 97.4}
    assert politics._build_senate_map([alaska], now=AFTER) == {}
    assert politics._build_senate_map([alaska, later], now=AFTER) == {"AK": 97.4}


async def test_route_keeps_confirmed_controls_but_retires_the_finished_forecasts(
    monkeypatch,
):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AFTER.astimezone(tz) if tz else AFTER.replace(tzinfo=None)

    monkeypatch.setattr(politics, "datetime", Clock)
    senate = market(108620, "Which party will win the U.S. Senate?", "CONTROLS-2026")
    house = market(108621, "Which party will win the U.S. House?", "CONTROLH-2026")
    for control in [senate, house]:
        control.market_metadata = {"shape": {"expected_winners": 1}}
        for outcome in control.outcomes:
            outcome.is_winner = outcome.name == "Democratic"
            outcome.resolution_source = "api_settlement"
    alaska = market(109095, "Alaska Senate winner?", "SENATEAK-26")
    popular_vote = market(
        65521844,
        "2026 Midterms: House popular vote vs. generic ballot?",
        "KXHOUSEPOPVSGB-26NOV03",
    )
    rows = [senate, house, alaska, popular_vote]
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            unique=lambda: SimpleNamespace(all=lambda: rows)
        )
    )
    payload = await politics.get_politics(
        SimpleNamespace(execute=AsyncMock(return_value=result))
    )
    congressional = payload["themes"]["congressional"]
    assert congressional["senate_map"] is None
    assert 65521844 not in [row["market_id"] for row in congressional["markets"]]
    for chamber in ["senate", "house"]:
        assert congressional["chamber_control"][chamber]["winner"] == "Democratic Party"
    assert all(o.is_winner is None for o in popular_vote.outcomes)


def kentucky_pair():
    kalshi = market(112821, "Kentucky governor winner? (2027)", "GOVPARTYKY-27")
    poly = market(
        58335990,
        "Kentucky Governor Election Winner (2027)",
        "798143",
        outcomes=[("Republican", 0.78061224), ("Democrat", 0.21938776)],
    )
    poly.source = "polymarket"
    return kalshi, poly


def test_same_race_fold_preserves_one_venues_price_and_working_destination():
    kalshi, poly = kentucky_pair()
    assert politics._same_registered_race(kalshi, poly)
    assert not politics._is_venue_twin(kalshi, poly)
    primary = politics._market_row(poly, now=AFTER)
    other = politics._market_row(kalshi, now=AFTER)
    assert politics._take_without_venue_twins(
        [(primary, poly), (other, kalshi)], 10
    ) == [primary]
    assert primary["src"] == "polymarket"
    assert primary["market_id"] == 58335990
    assert primary["prob"] == pytest.approx(78.061224)
    assert politics._take_without_venue_twins(
        [(other, kalshi), (primary, poly)], 10
    ) == [primary]


@pytest.mark.parametrize("kalshi_prob,poly_prob", [(0.6, 0.8), (0.8, 0.6)])
def test_prices_crossing_in_the_ranking_cannot_change_the_selected_source(
    kalshi_prob, poly_prob
):
    kalshi, poly = kentucky_pair()
    for member, probability in [(kalshi, kalshi_prob), (poly, poly_prob)]:
        for outcome in member.outcomes:
            outcome.current_probability = (
                probability if outcome.name == "Republican" else 1 - probability
            )
    pairs = [(politics._market_row(m, now=AFTER), m) for m in [kalshi, poly]]
    pairs.sort(key=lambda pair: politics._by_uncertainty(*pair))
    row = politics._take_without_venue_twins(pairs, 1)[0]
    assert row["market_id"] == 58335990
    assert row["src"] == "polymarket"
    assert row["prob"] == pytest.approx(max(poly_prob, 1 - poly_prob) * 100)


def test_preferred_source_past_the_cap_uses_the_pairs_first_slot():
    kalshi, poly = kentucky_pair()
    primary = market(
        65521846,
        "Kentucky Democratic Governor nominee?",
        "KXGOVKYNOMD-27",
        outcomes=[("Rocky Adkins", 0.62), ("Jacqueline Coleman", 0.38)],
    )
    pairs = [(politics._market_row(m, now=AFTER), m) for m in [kalshi, primary, poly]]
    assert [r["market_id"] for r in politics._take_without_venue_twins(pairs, 1)] == [
        58335990
    ]
    assert [r["market_id"] for r in politics._take_without_venue_twins(pairs, 2)] == [
        58335990,
        65521846,
    ]


def test_missing_primary_keeps_the_only_available_attributed_contract():
    kalshi, _ = kentucky_pair()
    row = politics._market_row(kalshi, now=AFTER)
    assert politics._take_without_venue_twins([(row, kalshi)], 1) == [row]


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 1),
        ("external_id", "GOVPARTYKY-28"),
        ("name", "Kentucky Lieutenant Governor winner? (2027)"),
        ("name", "Kentucky Democratic Governor nominee?"),
        ("source", "polymarket"),
    ],
)
def test_same_race_register_refuses_identity_drift(field, value):
    kalshi, poly = kentucky_pair()
    setattr(kalshi, field, value)
    assert not politics._same_registered_race(kalshi, poly)


def test_same_race_register_refuses_a_new_party_or_candidate_field():
    kalshi, poly = kentucky_pair()
    poly.outcomes.append(SimpleNamespace(name="Other", external_id=None))
    assert not politics._same_registered_race(kalshi, poly)


def test_same_race_register_refuses_independent_party_contracts():
    kalshi, poly = kentucky_pair()
    poly.mutually_exclusive = False
    assert not politics._same_registered_race(kalshi, poly)


def test_same_race_fold_backfills_the_slot_and_preserves_the_primary():
    kalshi, poly = kentucky_pair()
    primary = market(
        65521846,
        "Kentucky Democratic Governor nominee?",
        "KXGOVKYNOMD-27",
        outcomes=[("Rocky Adkins", 0.62), ("Jacqueline Coleman", 0.38)],
    )
    pairs = [(politics._market_row(m, now=AFTER), m) for m in [poly, kalshi, primary]]
    assert [r["market_id"] for r in politics._take_without_venue_twins(pairs, 2)] == [
        58335990,
        65521846,
    ]
