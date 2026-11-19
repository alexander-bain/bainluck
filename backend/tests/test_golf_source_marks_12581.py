"""Golf tournament cards explain each golfer's own winner price (#12581)."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.routes.golf import (
    _aggregate_golfer_outcome,
    _build_h2h_entry,
    _build_tournament_entry,
    _enrich_with_schedule,
)
from tests.test_golf_card_leader_needs_the_field_8334 import (
    _FEED_NOW,
    _served,
    _tournament,
)


def _outcome(oid, name, price):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=price,
        probability_change_24h=None,
        opening_probability=None,
        last_updated=_FEED_NOW.isoformat(),
    )


def _field(prices, *, complete=False):
    golfers = {}
    markets = []
    for mid, (source, rows, scale) in enumerate(prices, 1):
        market = SimpleNamespace(
            id=mid,
            name="The RSM Classic - Winner",
            source=source,
            external_id=f"golf_rsm_{mid}",
            market_metadata={},
            outcomes=[],
        )
        markets.append(market)
        for oid, (name, price) in enumerate(rows, mid * 100):
            outcome = _outcome(oid, name, price)
            market.outcomes.append(outcome)
            label = "datagolf_model" if source == "datagolf" else source
            _aggregate_golfer_outcome(outcome, label, golfers, {}, scale, market=market)
    result = _build_tournament_entry(
        "the_rsm_classic",
        markets,
        golfers,
        [],
        [m.id for m in markets],
        [m.source for m in markets],
        None,
        None,
        mutually_exclusive=complete,
    )
    assert result is not None
    return result


def test_public_golf_rows_bind_only_the_sources_that_priced_that_golfer(monkeypatch):
    field = _field(
        [
            ("kalshi", [("Ben James", 0.05), ("Jordan Smith", 0.0295)], 1.0),
            ("datagolf", [("Ben James", 0.042067), ("Jordan Smith", 0.032183)], 1.0),
            ("polymarket", [("Ben James", 0.0315)], 1.0),
        ]
    )
    # The real invitee filter requires DataGolf coverage of its featured golfers.
    base = _tournament(None)
    base["golfers"] = field["golfers"]
    before = deepcopy(base)
    cards = _served(monkeypatch, base)
    assert base == before
    rows = {r["name"]: r for r in cards[0]["data"]["golfers"]}
    mark = rows["Ben James"]["source_mark"]
    assert mark["state"] == "blend"
    assert [(s["key"], s["probability"]) for s in mark["sources"]] == [
        ("kalshi", 0.05),
        ("polymarket", 0.0315),
        ("datagolf", 0.042067),
    ]
    assert rows["Ben James"]["probability"] == 0.041
    assert all(s["observed_at"] is None for s in mark["sources"])
    assert [s["key"] for s in rows["Jordan Smith"]["source_mark"]["sources"]] == [
        "kalshi",
        "datagolf",
    ]


def test_single_source_and_legacy_field_scaling_keep_the_raw_quote():
    entry = _field([("polymarket", [("Matthew Fitzpatrick", 0.395)], 0.121 / 0.395)])
    row = entry["golfers"][0]
    assert row["probability"] == 0.121
    mark = row["source_mark"]
    assert mark["state"] == "single"
    assert mark["sources"][0]["probability"] == 0.395
    assert "scal" in mark["method"].lower()


def test_whole_field_scaling_keeps_raw_inputs_and_separates_it_from_price_rounding():
    rows = [("Ben James", 0.52), ("Brian Harman", 0.47), ("Jordan Smith", 0.31)]
    normalized = _field([("kalshi", rows, 1.0)], complete=True)
    by_name = {r["name"]: r for r in normalized["golfers"]}
    assert sum(r["rendered_percent"] for r in by_name.values()) == 100
    mark = by_name["Ben James"]["source_mark"]
    assert mark["sources"][0]["probability"] == 0.52
    assert by_name["Ben James"]["probability"] != 0.52
    assert "scal" in mark["method"].lower()
    rounded = _field([("kalshi", [("Jeeno Thitikul", 0.0895)], 1.0)])
    mark = rounded["golfers"][0]["source_mark"]
    assert mark["sources"][0]["probability"] == 0.0895
    assert "method" not in mark


def test_head_to_head_mark_precedes_display_rounding_and_follows_sorted_side():
    market = SimpleNamespace(
        id=91,
        source="kalshi",
        outcomes=[
            _outcome(1, "Team Europe", 0.41234),
            _outcome(2, "Team USA", 0.58766),
        ],
    )
    matchup = _build_h2h_entry(market, "ryder_cup")
    assert matchup["golfer_a"]["source_mark"]["sources"][0]["probability"] == 0.58766
    assert matchup["golfer_b"]["source_mark"]["sources"][0]["probability"] == 0.41234


def test_removing_placeholders_before_ranking_keeps_each_price_with_its_owner():
    placeholders = [(f"Placeholder {i}", 0.5) for i in range(12)]
    real = [("Brian Harman", 0.55), ("Jordan Smith", 0.45)]
    field = _field([("kalshi", [real[0], *placeholders, real[1]], 1.0)], complete=True)
    assert [
        (r["name"], r["source_mark"]["sources"][0]["probability"])
        for r in field["golfers"]
    ] == real


def test_an_old_golf_base_cannot_supply_the_original_quote_from_a_scaled_price(
    monkeypatch,
):
    base = _tournament([("Jeeno Thitikul", 0.60), ("Nelly Korda", 0.40)])
    base["golfers"][0]["sources"] = {"kalshi": 0.60}
    card = _served(monkeypatch, base)[0]
    for row in card["data"]["golfers"]:
        assert row["source_mark"] == {
            "state": "none",
            "sources": [],
            "reason": "source_evidence_incomplete",
        }


@pytest.mark.parametrize("listed", [True, False])
def test_only_a_matched_official_champion_certifies_result_rows(monkeypatch, listed):
    base = _tournament([("Matthew Fitzpatrick", 0.60), ("Jordan Smith", 0.40)])
    champion = "Matt Fitzpatrick" if listed else "Another Team"
    _enrich_with_schedule([base], {base["key"]: {"champion": champion}})
    rows = _served(monkeypatch, base)[0]["data"]["golfers"]
    if listed:
        assert [r["source_mark"]["settled"]["result"] for r in rows] == ["Won", "Lost"]
        assert all(r["source_mark"]["settled"]["source"] == "espn" for r in rows)
    else:
        assert all(r["source_mark"]["reason"] == "result_unknown" for r in rows)
