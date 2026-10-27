"""Lane1b R1/R2: invisible old editions and explicit joint-award qualifiers."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import permutations

import pytest

from app.utils import prop_families as pf
from tests.test_prop_families_award_editions_9858 import board, current, members


@pytest.mark.parametrize(
    "source,group,title",
    [
        ("polymarket", "polymarket:old", "NBA: 2025-26 MVP"),
        ("kalshi", "kalshi:KXNBAMVP-26", "Pro Basketball MVP Winner"),
    ],
)
def test_aged_out_prior_board_cannot_split_current_race(source, group, title):
    old = board(101, title, source, group, settled=True)
    # Offset first; no branching on the wall clock, and no hard-coded expiry.
    old["resolution_date"] = (
        datetime.now(timezone.utc) - timedelta(days=180)
    ).isoformat()
    other = board(103, "NBA MVP", "polymarket", "polymarket:current")
    inputs = [current(), other, old]
    before = deepcopy(inputs)
    for ordered in permutations(inputs):
        [family] = pf.group_prop_families(list(ordered))
        assert members(family) == {100, 103}
        assert family["label"] == "MVP"
        assert all(not r["settled"] for r in family["rows"])
    assert inputs == before


@pytest.mark.parametrize(
    "title",
    [
        "Will Shohei Ohtani win the Cy Young and NL MVP?",
        "Ohtani to win Cy Young & AL MVP",
        "Shohei Ohtani: NL MVP and NL Cy Young",
        "Shohei Ohtani: Cy Young/MVP Winner",
        "Will someone win DPOY and NBA MVP?",
    ],
)
@pytest.mark.parametrize(
    "hint",
    [
        {},
        {"family_key_hint": "cy young"},
        {"market_metadata": {"prop_family": {"family_key": "mvp"}}},
    ],
)
def test_league_qualified_and_slash_joint_titles_cannot_borrow_single_family(
    title, hint
):
    assert pf.resolve_family_key({"name": title, **hint}) is None


@pytest.mark.parametrize(
    "title,want",
    [
        ("NL Cy Young", "cy young"),
        ("AL MVP", "mvp"),
        ("NBA MVP", "mvp"),
        ("Will Roy Hibbert win MVP?", "mvp"),
        ("Cy Young and NL mvplayer", "cy young"),
        ("Cy Young and NL player to win MVP", "cy young"),
    ],
)
def test_single_awards_and_incidental_mentions_remain(title, want):
    assert pf.resolve_family_key({"name": title}) == want
