"""#11995 — dedicated panels use the shared complete-field display rule."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import golf, march_madness, oscars


def outcome(oid, name, probability, **extra):
    return SimpleNamespace(
        id=oid, name=name, current_probability=probability,
        probability_change_24h=0.02, opening_probability=0.1,
        last_updated=None, current_yes_bid=probability, current_yes_ask=probability,
        is_winner=extra.get("is_winner"), resolution_source=extra.get("resolution_source"),
    )


def market(rows, *, exclusive=True, name="2027 Oscars Best Picture", source="polymarket"):
    return SimpleNamespace(id=1, name=name, source=source, outcomes=rows,
                           mutually_exclusive=exclusive, external_id="one-winner", market_metadata=None)


async def awards_body(monkeypatch, rows, *, exclusive=True):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [market(rows, exclusive=exclusive)]
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    monkeypatch.setattr(oscars, "_MAX_NOMINEES", 2)
    return await oscars.build_oscars_payload(db)


@pytest.mark.asyncio
async def test_oscars_cap_cannot_become_its_own_denominator(monkeypatch):
    rows = [outcome(i, name, 0.28) for i, name in enumerate(["Film Alpha", "Film Beta", "Film Gamma"], 1)]
    category = (await awards_body(monkeypatch, rows))["categories"][0]
    assert category["nominee_count"] == 3
    assert category["remaining_outcome_count"] == 1
    assert [r["rendered_percent"] for r in category["nominees"]] == [34, 33]
    assert all(r["probability"] == pytest.approx(1 / 3, abs=1e-8) for r in category["nominees"])
    assert all(r["opening_probability"] is None and r["movement_24h"] is None for r in category["nominees"])


@pytest.mark.asyncio
@pytest.mark.parametrize("exclusive,missing", [(False, False), (None, False), (True, True)])
async def test_awards_unknown_or_nonexclusive_fields_stay_raw(monkeypatch, exclusive, missing):
    rows = [outcome(1, "Film Alpha", 0.28), outcome(2, "Film Beta", 0.28),
            outcome(3, "Film Gamma", None if missing else 0.28)]
    nominees = (await awards_body(monkeypatch, rows, exclusive=exclusive))["categories"][0]["nominees"]
    assert all(r["probability"] == 0.28 and "rendered_percent" not in r for r in nominees)


@pytest.mark.asyncio
async def test_awards_venue_winner_remains_a_result(monkeypatch):
    rows = [outcome(1, "Film Alpha", 1.0, is_winner=True, resolution_source="api_settlement"),
            outcome(2, "Film Beta", 0.03), outcome(3, "Film Gamma", 0.02)]
    nominees = (await awards_body(monkeypatch, rows))["categories"][0]["nominees"]
    assert nominees[0]["probability"] == 1.0
    assert all("rendered_percent" not in row for row in nominees)


def test_march_madness_uses_the_same_stable_full_field_allocation():
    rows = [outcome(i, name, p) for i, (name, p) in enumerate(
        zip(["Alpha", "Beta", "Gamma", "Delta"], [0.255, 0.255, 0.25, 0.24]), 1)]
    teams = march_madness._aggregate_championship_odds([market(rows)], "men")
    assert {r["team_name"]: r["rendered_percent"] for r in teams} == {
        "Alpha": 26, "Beta": 25, "Gamma": 25, "Delta": 24,
    }
    assert sum(r["rendered_percent"] for r in teams) == 100


@pytest.mark.parametrize("exclusive,missing", [(False, False), (None, False), (True, True)])
def test_championship_unknown_or_nonexclusive_fields_stay_raw(exclusive, missing):
    rows = [outcome(1, "Alpha", 0.3), outcome(2, "Beta", 0.2),
            outcome(3, "Gamma", None if missing else 0.1)]
    teams = march_madness._aggregate_championship_odds([market(rows, exclusive=exclusive)], "men")
    assert teams[0]["probability"] == 0.3
    assert all("rendered_percent" not in r for r in teams)


def golf_entry(monkeypatch, *, complete=True, result=False):
    names = ["Alice Smith", "Bob Jones", "Casey Reed", "Dani Lane"]
    data = {}
    prices = [[0.7, 0.4, 0.3, 0.2], [0.4, 0.3, 0.2, 0.1]]
    for source, values in zip(["kalshi", "polymarket"], prices):
        factor = golf._golf_winner_renorm_factor("Masters Winner", len(names), sum(values), mutually_exclusive=True)
        assert factor == 1.0, "normalizing before the blend changes the final probabilities"
        for i, (name, p) in enumerate(zip(names, values), 1):
            row = outcome(i, name, p, is_winner=result and i == 1,
                          resolution_source="api_settlement" if result and i == 1 and source == "kalshi" else None)
            golf._aggregate_golfer_outcome(row, source, data, {}, prob_scale=factor)
    monkeypatch.setattr(golf, "_MAX_GOLFERS", 2)
    return golf._build_tournament_entry("masters", [market([], name="Masters Winner")],
                                      data, [], [1], ["kalshi", "polymarket"], None, None,
                                      mutually_exclusive=True, field_complete=complete)


def test_golf_normalizes_only_the_final_full_blend_before_the_cap(monkeypatch):
    entry = golf_entry(monkeypatch)
    full = entry["_all_golfers"]
    assert len(entry["golfers"]) == 2 and len(full) == 4
    assert full[0]["probability"] == pytest.approx(0.55 / 1.3, abs=1e-8)
    assert [g["rendered_percent"] for g in full] == [42, 27, 19, 12]
    assert sum(g["rendered_percent"] for g in full) == 100
    assert full[0]["sources"] == {"kalshi": 0.7, "polymarket": 0.4}
    assert all(g["opening_probability"] is None and g["movement_24h"] is None for g in full)


@pytest.mark.parametrize("complete,result", [(False, False), (True, True)])
def test_golf_keeps_incomplete_fields_and_authoritative_results_raw(monkeypatch, complete, result):
    full = golf_entry(monkeypatch, complete=complete, result=result)["_all_golfers"]
    assert full[0]["probability"] == 0.55
    assert all("rendered_percent" not in g for g in full)


def test_championship_later_ungraded_source_cannot_erase_a_venue_result():
    graded = [outcome(1, "Alpha", 1, is_winner=True, resolution_source="api_settlement"),
              outcome(2, "Beta", 0.01)]
    ungraded = [outcome(3, "Alpha", 0.98, is_winner=True), outcome(4, "Beta", 0.02)]
    teams = march_madness._aggregate_championship_odds([market(graded), market(ungraded)], "men")
    assert all("rendered_percent" not in row for row in teams)
    assert teams[0]["resolution_source"] == "api_settlement"


def test_golf_abbreviation_merge_keeps_the_venue_result_guard():
    data = {}
    for i, (name, probability, source, winner) in enumerate([
        ("Alice Smith", 0.9, "kalshi", False),
        ("A Smith", 1.0, "polymarket", True),
        ("Bob Jones", 0.05, "kalshi", False),
        ("Dani Lane", 0.03, "kalshi", False),
    ], 1):
        row = outcome(i, name, probability, is_winner=winner,
                      resolution_source="api_settlement" if winner else None)
        golf._aggregate_golfer_outcome(row, source, data, {})
    entry = golf._build_tournament_entry("masters", [market([], name="Masters Winner")],
                                        data, [], [1], ["kalshi", "polymarket"], None, None,
                                        mutually_exclusive=True)
    winner = entry["golfers"][0]
    assert winner["name"] == "Alice Smith"
    assert winner["resolution_source"] == "api_settlement"
    assert winner["probability"] == 0.95
    assert all("rendered_percent" not in g for g in entry["golfers"])


async def golf_overflow_body(monkeypatch, source, overflow_name, overflow_probability=0.27):
    rows = [outcome(1, "Alice Smith", 0.54), outcome(2, "Bob Jones", 0.27),
            outcome(3, "Casey Reed", 0.27), outcome(4, overflow_name, overflow_probability)]
    m = market(rows, name="Masters Tournament Winner", source=source)
    m.commence_time = m.resolution_date = None
    m.status, m.llm_sport_category, m.market_tier = "open", "golf", 1
    result, empty = MagicMock(), MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [m]
    empty.__iter__ = lambda _: iter(())
    calls = 0

    async def execute(*args, **kwargs):
        nonlocal calls
        calls += 1
        return result if calls == 1 else empty

    monkeypatch.setattr(golf, "_get_golf_schedule", AsyncMock(return_value=[]))
    body = await golf.get_golf(SimpleNamespace(execute=execute))
    return body["tournaments"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
@pytest.mark.parametrize("overflow_name", ["Field", "Other", "The Field", "Tie"])
async def test_golf_priced_overflow_stays_in_the_full_denominator(monkeypatch, source, overflow_name):
    entry = await golf_overflow_body(monkeypatch, source, overflow_name)
    assert [g["rendered_percent"] for g in entry["golfers"]] == [40, 20, 20]
    overflow = entry["overflow_outcomes"]
    assert len(overflow) == 1 and overflow[0]["name"] == overflow_name
    assert overflow[0]["rendered_percent"] == 20
    assert sum(g["rendered_percent"] for g in entry["_all_golfers"] + overflow) == 100
    assert entry["golfers"][0]["probability"] == pytest.approx(0.4)
    assert overflow[0]["sources"] == {source: 0.27}


@pytest.mark.asyncio
async def test_golf_unpriced_overflow_is_unknown_mass_not_zero(monkeypatch):
    entry = await golf_overflow_body(monkeypatch, "kalshi", "Field", None)
    assert [g["probability"] for g in entry["golfers"]] == [0.54, 0.27, 0.27]
    assert all("rendered_percent" not in g for g in entry["golfers"])
    assert "overflow_outcomes" not in entry
