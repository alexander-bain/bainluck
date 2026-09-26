"""#8848 — Bigger Picture stops drawing a Polymarket parent beside its own children.

WHAT A READER SAW. `/events/15318843` (Hangzhou doubles), 2026-09-26: Bigger
Picture drew parent `62352559` (`field`, group `polymarket:1080694`) with four
legs that are its children's TITLES — "Hangzhou Open (Doubles): Reynolds/Watt vs
King/Stevens Set 2 Winner" 59.5%, "… Set 1 Winner" 59%, "Reynolds/Watt" 39% and
"Completed Match" 99% — next to the Set 1 / Set 2 children 62358024 / 62358025.

The group, read on production 18:30Z (every parent leg's id is a sibling's):

    62352559 field             legs 0x5f61… 0xc212… 0x5e26… 0xf70c…
    62358022 duel              0x5e26…  (match winner — folded by #4646)
    62358023 container_member  0xc212…  (Completed Match — names no team, no row)
    62358024 duel              0xf70c…  (Set 1 Winner — served)
    62358025 duel              0x5f61…  (Set 2 Winner — served)

The fixtures below are that group. The controls carry the file, because a
removal's characteristic failure is taking something it was never meant to take:
a parent with no served child stays (CERT-2335/2340), a season field is out of
scope, and a merged row speaking for a member survives.
"""

import inspect
from types import SimpleNamespace

from app.routes import events as events_module
from app.routes.events import (
    _redundant_parent_scope,
    _withhold_redundant_parent_futures,
)

EVENT_ID = 15318843
GROUP = "polymarket:1080694"
PARENT = 62352559
MATCH, COMPLETED, SET1, SET2 = 62358022, 62358023, 62358024, 62358025


def _gm(market_id, market_type, external_id, group_id=GROUP):
    return SimpleNamespace(
        id=market_id, group_id=group_id, market_type=market_type, external_id=external_id
    )


def _leg(external_id):
    return SimpleNamespace(external_id=external_id)


GROUP_MARKETS = [
    _gm(PARENT, "field", "1080694"),
    _gm(MATCH, "duel", "0x5e266a88a1"),
    _gm(COMPLETED, "container_member", "0xc2126e4d51"),
    _gm(SET1, "duel", "0xf70cf486bb"),
    _gm(SET2, "duel", "0x5f61aec95f"),
]
PARENT_LEGS = {
    PARENT: [
        _leg("0x5f61aec95f"),
        _leg("0xc2126e4d51"),
        _leg("0x5e266a88a1"),
        _leg("0xf70cf486bb"),
    ]
}


def _row(market_id, outcome_name, **extra):
    return {"market_id": market_id, "outcome_name": outcome_name, **extra}


def _specimen_lists():
    home = [
        _row(SET2, "Reynolds/Watt"),
        _row(SET1, "Reynolds/Watt"),
        _row(PARENT, "Hangzhou Open (Doubles): Reynolds/Watt vs King/Stevens Set 2 Winner"),
        _row(PARENT, "Hangzhou Open (Doubles): Reynolds/Watt vs King/Stevens Set 1 Winner"),
        _row(PARENT, "Reynolds/Watt"),
        _row(PARENT, "Completed Match"),
    ]
    away = [_row(SET1, "King/Stevens"), _row(SET2, "King/Stevens")]
    return home, away


def _ids(rows):
    return [r["market_id"] for r in rows]


def test_the_photographed_parent_leaves_and_its_children_stay():
    home, away = _specimen_lists()
    kept_home, kept_away = _withhold_redundant_parent_futures(
        home, away, {PARENT, SET1, SET2}, GROUP_MARKETS, PARENT_LEGS
    )
    assert _ids(kept_home) == [SET2, SET1]
    assert _ids(kept_away) == [SET1, SET2]


def test_the_leg_copy_route_alone_convicts_a_duel_group():
    """No member-shaped sibling at all: only #5273's by-id test can see it."""
    group = [m for m in GROUP_MARKETS if m.id != COMPLETED]
    legs = {PARENT: [leg for leg in PARENT_LEGS[PARENT] if leg.external_id != "0xc2126e4d51"]}
    home, away = _specimen_lists()
    kept_home, _ = _withhold_redundant_parent_futures(
        home, away, {PARENT, SET1, SET2}, group, legs
    )
    assert PARENT not in _ids(kept_home)


def test_the_whole_group_is_the_basis_not_the_served_rows():
    """Completed Match names no team and never produces a row at this door, yet
    the leg-copy test needs EVERY parent leg to name a sibling. Judged on served
    rows only, the parent would survive — the pre-fix page."""
    # No container_member either, so neither route fires on this basis.
    served_only = [m for m in GROUP_MARKETS if m.id in {PARENT, SET1, SET2}]
    home, away = _specimen_lists()
    kept_home, _ = _withhold_redundant_parent_futures(
        home, away, {PARENT, SET1, SET2}, served_only, PARENT_LEGS
    )
    assert PARENT in _ids(kept_home), "control: a partial group must refuse"

    kept_home, _ = _withhold_redundant_parent_futures(
        home, away, {PARENT, SET1, SET2}, GROUP_MARKETS, PARENT_LEGS
    )
    assert PARENT not in _ids(kept_home)


def test_a_parent_with_no_served_child_stays():
    """CERT-2335/2340: the parent is then the group's only representation."""
    home = [_row(PARENT, "Reynolds/Watt"), _row(PARENT, "Completed Match")]
    away = []
    kept_home, kept_away = _withhold_redundant_parent_futures(
        home, away, {PARENT}, GROUP_MARKETS, PARENT_LEGS
    )
    assert _ids(kept_home) == [PARENT, PARENT]
    assert kept_away == []


def test_a_parent_outside_scope_is_never_a_candidate():
    home, away = _specimen_lists()
    kept_home, _ = _withhold_redundant_parent_futures(
        home, away, {SET1, SET2}, GROUP_MARKETS, PARENT_LEGS
    )
    assert _ids(kept_home).count(PARENT) == 4


def test_a_merged_row_speaking_for_a_member_is_kept():
    home = [
        _row(PARENT, "Reynolds/Watt", contributor_market_ids=[PARENT, MATCH]),
        _row(PARENT, "Completed Match"),
        _row(SET1, "Reynolds/Watt"),
    ]
    kept_home, _ = _withhold_redundant_parent_futures(
        home, [], {PARENT, SET1}, GROUP_MARKETS, PARENT_LEGS
    )
    assert [r["outcome_name"] for r in kept_home] == ["Reynolds/Watt", "Reynolds/Watt"]
    assert kept_home[0].get("contributor_market_ids") == [PARENT, MATCH]


def test_a_row_with_no_market_id_is_never_removed():
    home, away = _specimen_lists()
    home.append({"outcome_name": "untagged"})
    kept_home, _ = _withhold_redundant_parent_futures(
        home, away, {PARENT, SET1, SET2}, GROUP_MARKETS, PARENT_LEGS
    )
    assert {"outcome_name": "untagged"} in kept_home


def test_the_shape_route_alone_convicts_a_field_with_a_served_member():
    """#4189's route: a `field` parent whose container_member row is served."""
    group = [
        _gm(1, "field", "ev1", group_id="g"),
        _gm(2, "container_member", "0xaa", group_id="g"),
    ]
    home = [_row(1, "Yes-copy"), _row(2, "Yes")]
    kept_home, _ = _withhold_redundant_parent_futures(home, [], {1, 2}, group, {})
    assert _ids(kept_home) == [2]


def test_one_foreign_leg_keeps_a_duel_parent():
    """The leg-copy test is EVERY leg; a leg naming no sibling refuses it."""
    group = [m for m in GROUP_MARKETS if m.id != COMPLETED]
    legs = {PARENT: [_leg("0x5f61aec95f"), _leg("0xnot-a-sibling")]}
    home, away = _specimen_lists()
    kept_home, _ = _withhold_redundant_parent_futures(
        home, away, {PARENT, SET1, SET2}, group, legs
    )
    assert _ids(kept_home).count(PARENT) == 4


def test_empty_inputs_are_returned_unchanged():
    home, away = _specimen_lists()
    assert _withhold_redundant_parent_futures(home, away, set(), GROUP_MARKETS, PARENT_LEGS) == (
        home,
        away,
    )
    assert _withhold_redundant_parent_futures(home, away, {PARENT}, [], PARENT_LEGS) == (home, away)


def test_scope_is_the_events_own_grouped_markets():
    row_markets = {
        PARENT: SimpleNamespace(group_id=GROUP, event_id=EVENT_ID),
        SET1: SimpleNamespace(group_id=GROUP, event_id=EVENT_ID),
        # A season field on a group: another door's question, never in scope.
        70000001: SimpleNamespace(group_id="polymarket:season", event_id=None),
        # Another meeting of the same pair.
        70000002: SimpleNamespace(group_id="polymarket:other", event_id=99999),
        # Ungrouped, event-linked: not a decomposed container.
        70000003: SimpleNamespace(group_id=None, event_id=EVENT_ID),
    }
    parent_ids, groups = _redundant_parent_scope(row_markets, EVENT_ID)
    assert parent_ids == {PARENT, SET1}
    assert groups == {GROUP}
    assert _redundant_parent_scope({}, EVENT_ID) == (set(), set())


def test_the_verdict_is_wired_in_after_the_partial_field_door():
    src = inspect.getsource(events_module._build_related_futures)
    partial_at = src.find("_withhold_partial_field_futures(")
    scope_at = src.find("_redundant_parent_scope(")
    # The ASSIGNMENT, not the call: a verdict whose result is dropped is inert.
    verdict_at = src.find("home_futures, away_futures = _withhold_redundant_parent_futures(")
    resp_at = src.find('"home_team_futures": home_futures')
    assert partial_at != -1 and scope_at != -1 and verdict_at != -1 and resp_at != -1
    assert partial_at < scope_at < verdict_at < resp_at
