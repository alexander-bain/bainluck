"""#10354 — the NFL division register and the round-up producer.

Pins Alex's 2026-11-02 instruction (an explicit eight-pair register, not fuzzy
matching) and the R4 membership rulings: all eight divisions must blend from
both venues or there is no card; the four lowest leaders are shown, highest
first; the footer is the ruled wording; every number is the blend.

`nfl_division_boards_20261102.json` is the sixteen registered rows as
production served them on 2026-11-02 (public `GET /api/futures/{id}`).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.utils.discover_bundles import (
    NFL_DIVISION_ROUNDUP_FOOTER,
    assemble_nfl_division_roundup,
)
from app.utils.nfl_division_register import (
    NFL_DIVISION_REGISTER,
    Refusal,
    board_from_row,
    compose_division,
    compose_register,
    register_identities,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "nfl_division_boards_20261102.json").read_text()
)


def boards(markets=None):
    return [board_from_row(m) for m in (markets if markets is not None else FIXTURE["markets"])]


def markets_copy():
    return copy.deepcopy(FIXTURE["markets"])


def row_for(markets, source, external_id):
    return next(m for m in markets if m["source"] == source and m["external_id"] == external_id)


# ── The register itself ─────────────────────────────────────────────────────


def test_the_register_is_exactly_eight_divisions_and_thirty_two_clubs():
    divisions = [p.division for p in NFL_DIVISION_REGISTER]
    assert sorted(divisions) == sorted(
        f"{c} {d}" for c in ("AFC", "NFC") for d in ("East", "North", "South", "West")
    )
    clubs = [c.club for p in NFL_DIVISION_REGISTER for c in p.clubs]
    assert len(clubs) == 32 and len(set(clubs)) == 32


def test_every_venue_identity_is_unique():
    ids = register_identities()
    assert len(ids) == 16 and len(set(ids)) == 16


def test_every_registered_outcome_name_is_what_production_stores():
    """The register was read off production; this keeps it honest against the capture."""
    for pair in NFL_DIVISION_REGISTER:
        k = row_for(FIXTURE["markets"], "kalshi", pair.kalshi_event_ticker)
        p = row_for(FIXTURE["markets"], "polymarket", pair.polymarket_event_id)
        assert {o["name"] for o in k["outcomes"]} == {c.kalshi_outcome for c in pair.clubs}
        assert {o["name"] for o in p["outcomes"]} - {"Other"} == {c.polymarket_outcome for c in pair.clubs}


# ── Composition ─────────────────────────────────────────────────────────────


def test_todays_production_rows_blend_for_all_eight_divisions():
    blends, refusals = compose_register(boards())
    assert refusals == []
    assert [b.division for b in blends] == [p.division for p in NFL_DIVISION_REGISTER]
    nfc_east = next(b for b in blends if b.division == "NFC East")
    giants = next(c for c in nfc_east.clubs if c.club == "Giants")
    # Kalshi 0.515, Polymarket 0.51 → the unchanged blend's equal-weight midpoint.
    assert giants.kalshi_probability == 0.515 and giants.polymarket_probability == 0.51
    assert giants.probability == pytest.approx(0.5125)
    assert giants.rule == "equal_weight_midpoint"
    assert nfc_east.leader.club == "Giants"


def test_a_club_is_as_old_as_its_oldest_contributing_price():
    blends, _ = compose_register(boards())
    nfc_east = next(b for b in blends if b.division == "NFC East")
    cowboys = next(c for c in nfc_east.clubs if c.club == "Cowboys")
    # Kalshi 14:00:33Z, Polymarket 07:42:01Z → 07:42:01Z.
    assert cowboys.observed_at == datetime(2026, 11, 2, 7, 42, 1, 622104, tzinfo=timezone.utc)


def test_other_is_never_mapped_to_a_club():
    blends, _ = compose_register(boards())
    assert all(c.club != "Other" for b in blends for c in b.clubs)


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda m: m.remove(row_for(m, "polymarket", "232617")), "polymarket_row_missing"),
        (lambda m: m.remove(row_for(m, "kalshi", "KXNFLNFCEAST-27")), "kalshi_row_missing"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27").update(status="closed"), "kalshi_not_open"),
        (lambda m: row_for(m, "polymarket", "232617").update(status="resolved"), "polymarket_not_open"),
        (lambda m: row_for(m, "polymarket", "232617").update(mutually_exclusive=False), "not_single_winner"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27").update(resolution_date="2027-02-01T00:00:00+00:00"), "settles_after_polymarket_cutoff"),
        (lambda m: row_for(m, "polymarket", "232617").update(resolution_date=None), "settlement_undated"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27")["outcomes"].append({"name": "Dallas Cowboys", "probability": 0.2}), "kalshi_outcomes_differ_from_register"),
        (lambda m: row_for(m, "polymarket", "232617")["outcomes"].pop(0), "polymarket_outcomes_differ_from_register"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27")["outcomes"][0].update(probability=None), "unpriced:"),
        (lambda m: m.append(dict(row_for(m, "kalshi", "KXNFLNFCEAST-27"), market_id=99)), "kalshi_identity_ambiguous"),
    ],
)
def test_each_failure_refuses_that_division_by_name(mutate, reason):
    markets = markets_copy()
    mutate(markets)
    blends, refusals = compose_register(boards(markets))
    assert [r.division for r in refusals] == ["NFC East"]
    assert refusals[0].reason.startswith(reason)
    assert len(blends) == 7


def test_venues_forty_points_apart_on_one_club_are_a_refusal_not_a_number():
    markets = markets_copy()
    pm = row_for(markets, "polymarket", "232617")
    for o in pm["outcomes"]:
        if o["name"] == "New York Giants":
            o["probability"] = 0.05  # Kalshi 0.515
    _, refusals = compose_register(boards(markets))
    assert refusals == [Refusal("NFC East", "venues_disagree:Giants")]


def test_a_display_name_alias_is_not_a_match():
    """'Dallas Cowboys' on the Kalshi row is NOT Kalshi's registered 'Dallas'."""
    markets = markets_copy()
    k = row_for(markets, "kalshi", "KXNFLNFCEAST-27")
    for o in k["outcomes"]:
        if o["name"] == "Dallas":
            o["name"] = "Dallas Cowboys"
    _, refusals = compose_register(boards(markets))
    assert refusals[0].reason == "kalshi_outcomes_differ_from_register"


def test_compose_division_refuses_a_row_under_another_identity():
    pair = NFL_DIVISION_REGISTER[0]
    b = {x.external_id: x for x in boards()}
    wrong = b["KXNFLNFCEAST-27"]
    assert compose_division(pair, wrong, b[pair.polymarket_event_id]).reason == "kalshi_identity_mismatch"


# ── The producer ────────────────────────────────────────────────────────────


def test_the_roundup_shows_the_four_closest_highest_first_with_the_ruled_footer():
    blends, refusals = compose_register(boards())
    item = assemble_nfl_division_roundup(blends, refusals)
    data = item["data"]
    assert data["kind"] == "roundup" and data["title"] == "NFL division front-runners"
    c = data["roundup"]
    assert c["kicker"] == "Round-up" and c["tag"] == "NFL"
    assert c["footer"] == NFL_DIVISION_ROUNDUP_FOOTER == "Bain Luck blend · the 4 closest of 8 divisions"
    assert [r["label"] for r in c["rows"]] == [
        "NFC East: Giants",
        "AFC West: Broncos",
        "NFC North: Lions",
        "NFC South: Buccaneers",
    ]
    probs = [r["probability"] for r in c["rows"]]
    assert probs == sorted(probs, reverse=True)
    # The four shown are the four LOWEST leaders of the eight.
    leaders = sorted(b.leader.probability for b in blends)
    assert sorted(probs) == leaders[:4]
    assert data["member_ids"] == [r["market_id"] for r in c["rows"]]


def test_the_row_number_is_the_blend_not_either_venue():
    blends, refusals = compose_register(boards())
    row = assemble_nfl_division_roundup(blends, refusals)["data"]["roundup"]["rows"][0]
    assert row["probability"] == pytest.approx(0.5125)  # Kalshi 0.515, Polymarket 0.51
    assert row["pair"] == {"kalshi_market_id": 53674, "polymarket_market_id": 2248395}


def test_one_refusal_and_there_is_no_card():
    markets = markets_copy()
    markets.remove(row_for(markets, "polymarket", "232647"))
    blends, refusals = compose_register(boards(markets))
    assert len(blends) == 7
    assert assemble_nfl_division_roundup(blends, refusals) is None


def test_no_collection_ref_is_passed_through_as_none_never_invented():
    blends, refusals = compose_register(boards())
    assert assemble_nfl_division_roundup(blends, refusals)["data"]["collection_ref"] is None
    ref = {"slug": "nfl-division-front-runners", "name": "NFL division front-runners", "revision": 3, "collection_count": 4}
    assert assemble_nfl_division_roundup(blends, refusals, collection_ref=ref)["data"]["collection_ref"] == ref


def test_reader_text_says_market_never_question_and_names_no_venue():
    blends, refusals = compose_register(boards())
    c = assemble_nfl_division_roundup(blends, refusals)["data"]["roundup"]
    text = " ".join([c["kicker"], c["footer"], *(r["label"] for r in c["rows"])])
    assert "question" not in text.lower()
    for venue in ("Kalshi", "Polymarket", "sportsbook"):
        assert venue.lower() not in text.lower()
