"""Detail provenance follows admitted prices, never a row-touch clock (#12581)."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.routes.futures as routes
from app.utils.futures_source_mark import (
    describe_field_normalization,
    futures_outcome_source_mark,
)
from tests.test_futures_verified_title_9387 import (
    KALSHI_ID,
    NOW,
    ODDS_ID,
    PM_ID,
    PM_ROWS,
    VERIFIED,
    _route_io,  # noqa: F401 -- real-route IO fixture, shared with the existing suite
    by_name,
    detail,
    kalshi_market,
    odds_market,
    pm_market,
    trio,
)


@pytest.mark.parametrize(
    "original,displayed,scaled",
    [
        (Decimal("0.19"), Decimal("0.19"), False),
        (0.19, Decimal("0.25"), True),
        (Decimal("0.19"), 0.25, True),
        (Decimal("0"), Decimal("0"), False),
    ],
)
def test_database_decimal_prices_keep_the_scaling_explanation(
    original, displayed, scaled
):
    quoted = float(original)
    mark = {"state": "single", "sources": [{"probability": quoted}]}
    describe_field_normalization(
        mark,
        input_probability=original,
        displayed_probability=displayed,
    )
    assert ("method" in mark) is scaled
    if scaled:
        assert (
            mark["method"]
            == "Bain Luck field · scaled with the other outcomes to total 100%"
        )
    assert mark["sources"] == [{"probability": quoted}]


@pytest.mark.parametrize(
    "mid,oid,key,price",
    [
        (ODDS_ID, 1309486, "betting", 0.112913),
        (KALSHI_ID, 643833, "kalshi", 0.13),
        (PM_ID, 1709101, "polymarket", 0.135),
    ],
)
async def test_source_detail_retains_the_price_before_field_normalization(
    mid, oid, key, price
):
    payload, db = await detail(mid, trio())
    row = next(r for r in payload["outcomes"] if r["id"] == oid)
    if mid == ODDS_ID:
        assert row["probability"] != price
    expected = {
        "state": "single",
        "sources": [
            {
                "key": key,
                "name": {
                    "betting": "Sportsbooks",
                    "kalshi": "Kalshi",
                    "polymarket": "Polymarket",
                }[key],
                "probability": price,
                "observed_at": None,
                "reason": "observation_unknown",
            }
        ],
    }
    if mid in {ODDS_ID, KALSHI_ID}:
        expected["method"] = (
            "Bain Luck field · scaled with the other outcomes to total 100%"
        )
    assert row["source_mark"] == expected
    assert all("source_mark" in r for r in payload["outcomes"])
    assert db.kinds == ["market"]


async def test_withheld_quote_does_not_leak_into_the_source_sheet(monkeypatch):
    async def withheld(*args, **kwargs):
        return {643833}

    monkeypatch.setattr(routes, "_withheld_price_outcome_ids", withheld)
    payload, _ = await detail(KALSHI_ID, trio())
    row = next(r for r in payload["outcomes"] if r["id"] == 643833)
    assert row["probability"] is None
    assert row["source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "no_probability",
    }


async def test_real_zero_remains_a_source_quote():
    market = kalshi_market(rows=[(643833, "Buffalo", "KXSB-27-BUF", 0.0)], me=False)
    payload, _ = await detail(KALSHI_ID, [market])
    row = payload["outcomes"][0]
    assert row["probability"] == 0.0
    assert row["source_mark"]["sources"][0]["probability"] == 0.0
    assert row["source_mark"]["state"] == "single"


@pytest.mark.parametrize(
    "authority,grade,result",
    [
        ("api_settlement", True, "Won"),
        ("api_settlement", False, "Lost"),
        ("box_score_bound", True, "Won"),
    ],
)
async def test_proved_grade_names_its_actual_authority_without_a_made_up_time(
    authority, grade, result
):
    market = kalshi_market(rows=[(643833, "Buffalo", "KXSB-27-BUF", None)], me=False)
    market.outcomes[0].is_winner = grade
    market.outcomes[0].resolution_source = authority
    payload, _ = await detail(KALSHI_ID, [market])
    assert payload["outcomes"][0]["source_mark"] == {
        "state": "settled",
        "sources": [],
        "settled": {"source": authority, "result": result, "at": None},
    }


@pytest.mark.parametrize(
    "authority",
    [
        None,
        "ungradeable_result",
        "clean_resolution",
        "settlement_sync",
        "date_passed",
        "unclassified",
    ],
)
def test_unproved_results_cannot_be_called_official(authority):
    mark = futures_outcome_source_mark(
        SimpleNamespace(status="resolved", source="kalshi"),
        SimpleNamespace(
            is_winner=False, resolution_source=authority, current_probability=0.0
        ),
        {"probability": 0.0},
    )
    assert mark == {"state": "none", "sources": [], "reason": "result_unknown"}


async def test_polymarket_nonterminal_settlement_keeps_its_existing_unknown_verdict():
    market = pm_market(
        rows=[(1709101, "Buffalo Bills", 0.5)], status="resolved", me=False
    )
    for outcome in market.outcomes:
        outcome.is_winner = False
        outcome.resolution_source = "clob_authoritative"
    payload, _ = await detail(PM_ID, [market])
    row = by_name(payload, "Buffalo Bills")
    assert row["settlement_display"]["verdict"] == "unknown"
    assert row["source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "result_unknown",
    }


@pytest.mark.parametrize("mid", [ODDS_ID, KALSHI_ID, PM_ID])
async def test_verified_detail_lists_the_three_admitted_inputs_on_every_alias(mid):
    payload, db = await detail(mid, trio(), VERIFIED)
    row = by_name(payload, "Buffalo Bills")
    assert row["probability"] == pytest.approx(0.13 / 0.4715)
    mark = row["source_mark"]
    assert mark["state"] == "blend"
    assert (
        mark["method"]
        == "Bain Luck blend · the weighted middle of these sources · scaled with the other outcomes to total 100%"
    )
    assert [(s["key"], s["probability"]) for s in mark["sources"]] == [
        ("kalshi", 0.13),
        ("polymarket", 0.135),
        ("betting", 0.112913),
    ]
    assert all(
        s["observed_at"] is None and s["reason"] == "observation_unknown"
        for s in mark["sources"]
    )
    assert db.kinds == ["market", "candidates", "members", "roster"]


async def test_divergence_names_only_the_selected_source():
    rows = [r if r[1] != "Buffalo Bills" else (r[0], r[1], 0.60) for r in PM_ROWS]
    payload, _ = await detail(
        KALSHI_ID,
        trio(odds=odds_market(anchor=None), pm=pm_market(rows=rows)),
        VERIFIED,
    )
    row = next(r for r in payload["outcomes"] if r["id"] == 643833)
    assert row["aggregation_rule"] == "divergence_gate"
    mark = row["source_mark"]
    assert mark["state"] == "single"
    assert [s["key"] for s in mark["sources"]] == row["contributing_sources"]
    assert (
        mark["sources"][0]["probability"]
        == {"kalshi": 0.13, "polymarket": 0.60}[row["contributing_sources"][0]]
    )


async def test_cached_composition_keeps_its_inputs_when_an_unrelated_row_touch_arrives(
    monkeypatch,
):
    markets = trio()
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    monkeypatch.setattr(routes, "_VERIFIED_TITLE_CACHE", {})
    first, _ = await detail(ODDS_ID, markets, VERIFIED)
    markets[1].outcomes[0].current_probability = 0.9
    markets[1].outcomes[0].last_updated = NOW + timedelta(minutes=10)
    markets[1].outcomes[0].price_changed_at = NOW + timedelta(minutes=10)
    second, db = await detail(KALSHI_ID, markets, VERIFIED)
    a, b = (by_name(p, "Buffalo Bills") for p in (first, second))
    assert b["source_mark"] == a["source_mark"]
    assert b["probability"] == a["probability"]
    assert db.kinds == ["market"]


async def test_row_touch_and_price_change_clocks_never_mint_a_quote_age():
    markets = trio()
    first, _ = await detail(KALSHI_ID, markets)
    markets[1].outcomes[0].last_updated = NOW + timedelta(minutes=10)
    markets[1].outcomes[0].price_changed_at = NOW + timedelta(minutes=10)
    second, _ = await detail(KALSHI_ID, markets)
    a, b = (
        next(r for r in p["outcomes"] if r["id"] == 643833) for p in (first, second)
    )
    assert a["source_mark"] == b["source_mark"]


async def test_verified_composition_does_not_replace_an_official_grade_with_a_quote():
    markets = trio()
    markets[1].outcomes[0].is_winner = False
    markets[1].outcomes[0].resolution_source = "api_settlement"
    payload, _ = await detail(KALSHI_ID, markets, VERIFIED)
    row = by_name(payload, "Buffalo Bills")
    assert row["source_mark"] == {
        "state": "settled",
        "sources": [],
        "settled": {"source": "api_settlement", "result": "Lost", "at": None},
    }


async def test_two_admitted_sources_name_the_average_without_borrowing_age():
    payload, _ = await detail(KALSHI_ID, trio(odds=odds_market(anchor=None)), VERIFIED)
    row = next(r for r in payload["outcomes"] if r["id"] == 643833)
    mark = row["source_mark"]
    assert (
        mark["method"]
        == "Bain Luck blend · the average of these sources · scaled with the other outcomes to total 100%"
    )
    assert [(s["key"], s["probability"]) for s in mark["sources"]] == [
        ("kalshi", 0.13),
        ("polymarket", 0.135),
    ]


async def test_a_refused_composition_still_identifies_the_requested_source():
    payload, _ = await detail(KALSHI_ID, [kalshi_market()], VERIFIED)
    row = next(r for r in payload["outcomes"] if r["id"] == 643833)
    assert payload["representation"] == "source"
    assert row["source_mark"]["state"] == "single"
    assert row["source_mark"]["sources"][0]["key"] == "kalshi"
