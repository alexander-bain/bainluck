"""The roundup and the container explain the exact numbers they already serve."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.discover_bundles import (
    NFL_DIVISION_ROUNDUP_SLUG,
    assemble_nfl_division_roundup,
    nfl_division_roundup,
    reset_nfl_division_roundup_cache_for_tests,
)
from app.utils.nfl_division_register import (
    NFL_DIVISION_REGISTER,
    board_from_row,
    compose_register,
)


def markets():
    fixture = Path(__file__).parent / "fixtures/nfl_division_boards_20261102.json"
    return json.loads(fixture.read_text())["markets"]


def decisions(rows):
    blends, refusals = compose_register([board_from_row(row) for row in rows])
    assert not refusals
    return blends


def inputs_for(rows, division, club):
    pair = next(p for p in NFL_DIVISION_REGISTER if p.division == division)
    identity = next(c for c in pair.clubs if c.club == club)
    values = {}
    for source, external_id, name in (
        ("kalshi", pair.kalshi_event_ticker, identity.kalshi_outcome),
        ("polymarket", pair.polymarket_event_id, identity.polymarket_outcome),
    ):
        board = next(
            row
            for row in rows
            if row["source"] == source and row["external_id"] == external_id
        )
        values[source] = next(
            o["probability"] for o in board["outcomes"] if o["name"] == name
        )
    return values


def assert_mark(row, expected):
    mark = row["source_mark"]
    assert mark["state"] == "blend"
    assert {s["key"]: s["probability"] for s in mark["sources"]} == expected
    assert [s["name"] for s in mark["sources"]] == ["Kalshi", "Polymarket"]
    # The register's legacy age comes from last_updated, not a price-bound read.
    assert all(s["observed_at"] is None for s in mark["sources"])
    assert all(s["reason"] == "observation_unknown" for s in mark["sources"])
    assert row["probability"] == pytest.approx(sum(expected.values()) / 2)


@pytest.mark.asyncio
async def test_every_roundup_and_container_number_retains_its_actual_inputs():
    rows = markets()
    original = copy.deepcopy(rows)
    blends = decisions(rows)
    by_id = {b.kalshi_market_id: b for b in blends}
    feed, container = await nfl_division_roundup(rows)
    assert rows == original
    assert feed is not None and container is not None
    roundup = feed["data"]["roundup"]["rows"]
    assert len(roundup) == 4
    for row in roundup:
        blend = by_id[row["market_id"]]
        assert_mark(row, inputs_for(rows, blend.division, blend.leader.club))
    cards = [item["data"] for item in feed["data"]["items"]]
    cards += [m["card"] for m in container["sections"][0]["members"]]
    assert len(cards) == 8
    for card in cards:
        assert len(card["top_outcomes"]) == 4
        for row in card["top_outcomes"]:
            assert_mark(row, inputs_for(rows, by_id[card["id"]].division, row["name"]))


@pytest.mark.parametrize("second_price", [0.3175, 0.3173])
def test_tied_labels_explain_which_clubs_inputs_produced_the_row_number(second_price):
    rows = markets()
    pair = next(p for p in NFL_DIVISION_REGISTER if p.division == "NFC South")
    for row in rows:
        if row["external_id"] not in {
            pair.kalshi_event_ticker,
            pair.polymarket_event_id,
        }:
            continue
        for outcome in row["outcomes"]:
            if outcome["name"] in {"Carolina", "Carolina Panthers"}:
                outcome["probability"] = 0.325 if row["source"] == "kalshi" else 0.31
            if outcome["name"] in {"Tampa Bay", "Tampa Bay Buccaneers"}:
                outcome["probability"] = second_price
    feed = assemble_nfl_division_roundup(decisions(rows), [])
    row = next(
        r
        for r in feed["data"]["roundup"]["rows"]
        if r["label"].startswith("NFC South:")
    )
    assert row["label"] == "NFC South: Panthers and Buccaneers"
    assert_mark(row, {"kalshi": 0.325, "polymarket": 0.31})
    assert "Inputs for Panthers" in row["source_mark"]["method"]


def test_held_composition_does_not_acquire_a_new_price_or_row_touch_time():
    rows = markets()
    blends = decisions(rows)
    expected = {
        b.kalshi_market_id: inputs_for(rows, b.division, b.leader.club) for b in blends
    }
    for row in rows:
        for outcome in row["outcomes"]:
            outcome["probability"] = 0.01
            outcome["last_updated"] = "changed after composition"
    feed = assemble_nfl_division_roundup(blends, [])
    for row in feed["data"]["roundup"]["rows"]:
        assert_mark(row, expected[row["market_id"]])


@pytest.mark.asyncio
async def test_a_real_zero_is_still_a_two_source_input():
    rows = markets()
    for row in rows:
        if row["external_id"] in {"KXNFLNFCEAST-27", "232617"}:
            for outcome in row["outcomes"]:
                if outcome["name"] in {"Dallas", "Dallas Cowboys"}:
                    outcome["probability"] = 0.0
    _, container = await nfl_division_roundup(rows)
    card = next(
        m["card"] for m in container["sections"][0]["members"] if m["id"] == 53674
    )
    zero = next(o for o in card["top_outcomes"] if o["name"] == "Cowboys")
    assert_mark(zero, {"kalshi": 0.0, "polymarket": 0.0})


@pytest.mark.asyncio
async def test_cached_container_retains_the_original_marks_without_a_second_query(
    monkeypatch,
):
    from app.routes.containers import get_container

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "true")
    reset_nfl_division_roundup_cache_for_tests()

    class Session:
        def __init__(self):
            self.rows = markets()
            self.statements = []

        async def execute(self, statement):
            self.statements.append(str(statement))
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: self.rows)
            )

    session = Session()
    try:
        feed, first = await nfl_division_roundup(session)
        expected = copy.deepcopy(first)
        # All 16 member numbers are checked, including the rows below the leader.
        assert all(
            "source_mark" in row
            for member in first["sections"][0]["members"]
            for row in member["card"]["top_outcomes"]
        )
        session.rows.clear()
        later = await get_container(slug=NFL_DIVISION_ROUNDUP_SLUG, db=session)
        assert later == expected
        assert len(session.statements) == 1
        assert len(feed["data"]["roundup"]["rows"]) == 4
    finally:
        reset_nfl_division_roundup_cache_for_tests()


@pytest.mark.asyncio
async def test_a_refused_pair_still_withholds_the_whole_roundup():
    rows = markets()
    rows[0]["status"] = "resolved"
    assert await nfl_division_roundup(rows) == (None, None)
