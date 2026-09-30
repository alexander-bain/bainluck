"""#9587 — which page rows the `/search` hoist arm may ask the contender rule about.

`on_page_contender_candidates` only nominates; the route's SQL decides. So every
clause here is a refusal that keeps the lane from running for nothing, and the
real-Postgres route gate (`tests/integration/test_search_contender_on_page_hoist_9587_pg.py`)
is where "the World Series leads `cubs`" is proven.
"""

from types import SimpleNamespace

from app.utils.search_headline_contender import (
    HEADLINE_MARKET_TIER,
    MIN_CONTENDER_VOLUME,
    on_page_contender_candidates,
)

NAME_MATCHES = {"prop"}


def _row(mid, *, tier=HEADLINE_MARKET_TIER, volume=MIN_CONTENDER_VOLUME * 10, kind="board"):
    return SimpleNamespace(id=mid, market_tier=tier, volume=volume, kind=kind)


def _is_name_match(m):
    return m.kind in NAME_MATCHES


def _ids(page):
    return on_page_contender_candidates(page, _is_name_match)


def test_a_tier1_outcome_only_row_below_row_zero_is_nominated():
    page = [_row(1, tier=5, kind="prop"), _row(2, tier=5, kind="prop"), _row(3)]
    assert _ids(page) == [3]


def test_row_zero_is_never_nominated_it_has_nowhere_to_go():
    assert _ids([_row(1), _row(2, tier=5, kind="prop")]) == []


def test_a_name_match_is_not_nominated():
    page = [_row(1, tier=5, kind="prop"), _row(2, kind="prop")]
    assert _ids(page) == []


def test_tier_two_is_refused_like_the_lanes_clause_one():
    page = [_row(1, tier=5, kind="prop"), _row(2, tier=2), _row(3, tier=None)]
    assert _ids(page) == []


def test_the_volume_floor_is_the_lanes_own():
    page = [
        _row(1, tier=5, kind="prop"),
        _row(2, volume=MIN_CONTENDER_VOLUME - 1),
        _row(3, volume=None),
        _row(4, volume="not a number"),
        _row(5, volume=MIN_CONTENDER_VOLUME),
    ]
    assert _ids(page) == [5]


def test_an_id_less_row_cannot_be_reconciled_so_it_is_skipped():
    page = [_row(1, tier=5, kind="prop"), _row(None)]
    assert _ids(page) == []


def test_every_candidate_is_nominated_in_page_order():
    page = [_row(1, tier=5, kind="prop"), _row(7), _row(2, tier=5, kind="prop"), _row(4)]
    assert _ids(page) == [7, 4]


def test_an_empty_page_nominates_nothing():
    assert _ids([]) == []
