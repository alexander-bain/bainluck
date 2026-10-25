"""Explicitly different NBA MVP seasons never settle each other's rows.

Synthetic prices/results. The Kalshi season convention is anchored by the
provider's KXNBAMVP-27 event subtitle, '2026-27 season'. This is a negative
edition boundary, not proof of cross-venue settlement equivalence.
"""

from copy import deepcopy
from itertools import permutations

import pytest

from app.utils.prop_families import group_prop_families


def board(mid, title, source, group, *, settled=False, candidates=None):
    candidates = candidates or [
        ("Shai Gilgeous-Alexander", 0.145),
        ("Chet Holmgren", 0.01),
    ]
    return {
        "market_id": mid,
        "name": title,
        "source": source,
        "group_id": group,
        "sport": "basketball",
        "status": "resolved" if settled else "open",
        # Deliberately padded: schedule is not season identity or settlement time.
        "resolution_date": "2030-07-01T00:00:00+00:00",
        "outcomes": [
            {
                "outcome_id": mid * 10 + i,
                "name": name,
                "probability": 1.0 if settled and i == 0 else (0.0 if settled else p),
                "is_winner": (i == 0) if settled else None,
            }
            for i, (name, p) in enumerate(candidates)
        ],
    }


def current():
    return board(100, "Pro Basketball MVP Winner", "kalshi", "kalshi:KXNBAMVP-27")


def previous(*, settled=True):
    return board(
        101, "NBA: 2025-26 MVP", "polymarket", "polymarket:previous", settled=settled
    )


def members(family):
    return {
        mid
        for row in family["rows"]
        for mid in row.get("merged_market_ids", [row["market_id"]])
    }


@pytest.mark.parametrize("settled", [True, False])
@pytest.mark.parametrize("reverse", [True, False])
def test_different_named_editions_form_distinct_labeled_cards(settled, reverse):
    data = [current(), previous(settled=settled)]
    if reverse:
        data.reverse()
    before = deepcopy(data)
    families = group_prop_families(data)
    now = next(f for f in families if 100 in members(f))
    old = next(f for f in families if 101 in members(f))
    assert now is not old
    assert members(now) == {100}
    assert members(old) == {101}
    assert "2026–27" in now["label"]
    assert "2025–26" in old["label"]
    assert now["family_key"] != old["family_key"]
    assert all(not r["settled"] for r in now["rows"])
    assert (
        next(r for r in now["rows"] if r["entity"] == "Shai Gilgeous-Alexander")[
            "probability"
        ]
        == 0.145
    )
    assert data == before
    assert all(
        not any(k.startswith("_") for k in r) for f in families for r in f["rows"]
    )


@pytest.mark.parametrize(
    "title",
    ["NBA: 2026-27 MVP", "NBA: 2026–2027 MVP", "NBA: 2026-27 Most Valuable Player"],
)
def test_same_named_edition_keeps_existing_merge_without_new_rules_claim(title):
    other = board(102, title, "polymarket", "polymarket:current")
    [family] = group_prop_families([current(), other])
    assert members(family) == {100, 102}
    assert len(family["rows"]) == 2
    assert family["label"] == "MVP"


def test_unknown_season_cannot_bridge_two_known_conflicting_seasons():
    unknown = board(103, "NBA MVP", "polymarket", "polymarket:unknown")
    for data in permutations([current(), previous(), unknown]):
        families = group_prop_families(list(data))
        assert {frozenset(members(f)) for f in families} == {
            frozenset({100}),
            frozenset({101}),
            frozenset({103}),
        }
        assert next(f for f in families if 103 in members(f))["label"].endswith(
            "Season unspecified"
        )


def test_padded_dates_do_not_split_a_family_without_explicit_editions():
    a = board(104, "NBA MVP", "kalshi", None)
    b = board(105, "NBA MVP", "polymarket", None)
    a["resolution_date"] = "2031-01-01T00:00:00Z"
    [family] = group_prop_families([a, b])
    assert members(family) == {104, 105}
    assert family["label"] == "MVP"


@pytest.mark.parametrize(
    "source,group,title",
    [
        ("kalshi", "polymarket:KXNBAMVP-26", "NBA MVP"),
        ("kalshi", "kalshi:KXNBAMVP-260", "NBA MVP"),
        ("kalshi", "kalshi:KXNBAMVP-26SGA", "NBA MVP"),
        ("kalshi", "kalshi:KXNBAMVP-69", "NBA MVP"),
        ("kalshi", "kalshi:KXOTHER-26", "NBA MVP"),
        ("polymarket", "polymarket:unknown", "NBA: 2024-26 MVP"),
        ("polymarket", "polymarket:unknown", "NBA: 2026-25 MVP"),
        ("other", "polymarket:unknown", "NBA: 2025-26 MVP"),
    ],
)
def test_unsupported_identity_is_unknown_and_cannot_join_a_known_conflict(
    source, group, title
):
    unknown = board(103, title, source, group)
    families = group_prop_families([current(), previous(), unknown])
    assert {frozenset(members(f)) for f in families} == {
        frozenset({100}),
        frozenset({101}),
        frozenset({103}),
    }
    assert next(f for f in families if 103 in members(f))["label"].endswith(
        "Season unspecified"
    )


def test_single_entity_prior_season_cannot_settle_current_two_person_card():
    old = previous()
    old["outcomes"] = old["outcomes"][:1]
    [family] = group_prop_families([current(), old])
    assert members(family) == {100}
    assert family["label"].endswith("2026–27")
    assert all(not row["settled"] for row in family["rows"])


def test_other_awards_do_not_borrow_nba_mvp_ticker_convention():
    a = board(104, "Defensive Player of the Year", "kalshi", "kalshi:KXNBADPOY-26")
    b = board(105, "Defensive Player of the Year", "kalshi", "kalshi:KXNBADPOY-27")
    [family] = group_prop_families([a, b])
    assert family["label"] == "Defensive Player Of The Year"
    assert members(family) == {104, 105}
