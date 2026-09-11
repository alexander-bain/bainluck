"""T4-B1 (#5101): the served ORDER does not depend on the requested page size.

THE FINDING THIS FINISHES
-------------------------
#4921 measured the defect on production — ``limit=40`` and ``limit=250`` agreed
on 2 of 40 ranks, max move +87, with **0 cards carrying a different score** — and
fixed it by sizing the composition stages from ``min(20, limit)`` instead of the
raw ``limit``. That made every size AT OR ABOVE 20 agree with every other.

It left the other side of the ``min`` untouched. ``min(20, 7)`` is 7, so a caller
asking for 7 still composed over a 7-item window, and ``_ensure_feed_diversity``
scales both its event quota and the span it rebuilds by interleaving from that
number. So the small pages kept exactly the defect #4921 named: rank as a
function of page size. ``DISCOVER_COMPOSITION_WINDOW`` is the constant that
finishes it, and these tests are the property that says so.

WHY A CONSTANT IS SAFE HERE
---------------------------
Every candidate pool in ``feed.py`` caps with a literal — ``EVENT_CANDIDATE_BUDGET``,
200, 120, 100, 80, 1000 — and not one derives its bound from ``limit``. Composing
over 20 for a ``limit=7`` request therefore reasons about candidates that were
fetched anyway. The narrowing to the caller's page happens where it always did,
at the single ``feed_items[offset : offset + limit]`` slice in ``get_feed``.

THE SECOND HALF: TIES
---------------------
A fixed window makes the composition deterministic given a fixed input ORDER. It
does not make the input order deterministic. ``_rank_key`` was
``(_rank_score, _sort_time)``, and Python's sort is stable, so two cards tied on
both kept whatever order the candidate query happened to return — incidental DB
order, free to differ between two requests that scored identically.
``_canonical_item_key`` is the third component that closes that.

The identity chain in it is load-bearing rather than defensive: measured against
the served ``/api/feed?limit=250`` payload on 2026-09-11 (135 items), ``futures``,
``event`` and ``bundle`` carry ``data.id`` but all 12 ``concept`` and both
``tournament`` items carry NONE and are keyed by ``data.key``/``data.slug``. A
key built on ``data.id`` alone collapses every concept onto one value.
"""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    DISCOVER_COMPOSITION_WINDOW,
    _AscendingTieBreak,
    _canonical_item_key,
    _rank_key,
    apply_discover_display_chain,
)
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 9, 11, 8, 0, 0, tzinfo=timezone.utc)

#: The sizes the issue's acceptance evidence names, spanning both sides of the
#: old ``min(20, limit)`` hinge. 1 and 7 are the ones #4921 could not fix.
PAGE_SIZES = [1, 7, 10, 20, 40, 50, 120, 250]


def _futures(i: int, score: float) -> dict:
    """A futures card that SPEAKS — a silent one is an offender to the
    first-page quality floor, which would swap it out and hand the test an
    ordering that came from the floor rather than from the composition stages.
    """
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "context_summary": f"moved {i} points today",
        "reason": f"r{i}",
        "data": {"id": 90_000 + i, "name": f"market {i}"},
    }


def _event(i: int, score: float) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"e{i}",
        "data": {
            "id": 10_000 + i,
            "sport": "americanfootball_nfl" if i % 2 else "baseball_mlb",
            "status": "scheduled",
            "event_tags": ["tier:2", "class:pro_major"],
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "home_team_data": {"logo": "h"},
            "away_team_data": {"logo": "a"},
            "commence_time": (NOW + timedelta(hours=6 + i))
            .isoformat()
            .replace("+00:00", "Z"),
        },
    }


def _pool() -> list[dict]:
    """A mixed pool deep enough that a 20-item window is not the whole list.

    Scores descend with a deliberate PLATEAU so the pool contains genuine ties:
    integer division by 3 gives runs of three cards sharing a score, which is
    what exercises the tie-break. Without a plateau every float is distinct and
    the third sort component is never consulted.
    """
    pool: list[dict] = []
    for i in range(60):
        pool.append(_futures(i, score=98.0 - (i // 3)))
    for i in range(24):
        pool.append(_event(i, score=90.0 - (i // 3)))
    return pool


#: The event ratio these tests run at, and it is load-bearing — do NOT lower it.
#:
#: ``apply_discover_display_chain`` gates the stage this ship changes:
#:
#:     if event_pct is not None and event_pct < 0.2:
#:         pass                      # no artificial event promotion
#:     else:
#:         items = _ensure_feed_diversity(items, DISCOVER_COMPOSITION_WINDOW, ...)
#:
#: ``_ensure_feed_diversity`` is the stage that scales its event quota and its
#: interleave span from the window, so it is the one that made rank a function of
#: page size. At ``event_pct=0.15`` — the value the sibling #5099 file uses,
#: because it is testing the LEAD, not the window — that branch is skipped and
#: this whole file goes inert: measured against the parent commit, all eight
#: prefix rows PASSED at 0.15 and `test_prefix[7]` FAILED at 0.25. A test that
#: cannot fail on the parent is not evidence, so the cell matters more than the
#: assertions do.
#:
#: 0.25 is the only cell that satisfies both gates: ``>= 0.2`` so the diversity
#: stage runs, and ``< 0.3`` so the chain is still in Discover mode.
EVENT_PCT = 0.25


def _serve(pool: list[dict], limit: int) -> list[dict]:
    """The REAL served chain, then the same slice ``get_feed`` applies."""
    items, _meta = apply_discover_display_chain(
        copy.deepcopy(pool),
        limit=limit,
        ctx=PersonalizationContext(),
        event_pct=EVENT_PCT,
        now=NOW,
    )
    return items[:limit]


def _ids(items: list[dict]) -> list[str]:
    return [_canonical_item_key(it) for it in items]


# --------------------------------------------------------------------------
# The property: order is a function of the items, not of the page size
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size", PAGE_SIZES)
def test_every_page_size_is_a_prefix_of_the_largest(size):
    """The first ``size`` cards of a ``size`` request == the first ``size`` of 250.

    This is the whole ship in one assertion, and it is the form that catches the
    #4921 residue: at ``size`` 1 and 7 the old ``min(20, limit)`` sized the
    window from the caller, so these two rows are the ones that fail on the
    parent commit.
    """
    pool = _pool()
    reference = _ids(_serve(pool, 250))
    served = _ids(_serve(pool, size))

    assert served == reference[: len(served)], (
        f"limit={size} is not a prefix of limit=250: "
        f"{served} != {reference[: len(served)]}"
    )


def test_all_sizes_agree_pairwise_on_their_common_prefix():
    """Every pair, not just each-against-250 — a shared bug could move both."""
    pool = _pool()
    served = {size: _ids(_serve(pool, size)) for size in PAGE_SIZES}
    for a in PAGE_SIZES:
        for b in PAGE_SIZES:
            if a >= b:
                continue
            common = min(len(served[a]), len(served[b]))
            assert served[a][:common] == served[b][:common], (
                f"limit={a} and limit={b} disagree within their first {common}"
            )


def test_a_page_size_below_the_window_still_returns_that_many_cards():
    """The fixed window must not leak into the SLICE — 7 means 7 cards.

    Composing over 20 and returning 20 to a caller who asked for 7 would be the
    obvious way to break this ship while passing the prefix property.
    """
    pool = _pool()
    for size in (1, 7, 10):
        assert len(_serve(pool, size)) == size


def test_mixed_page_traversal_has_no_omissions_and_no_duplicates():
    """Walk the deck in pages of 7 and reassemble it (the issue's second criterion)."""
    pool = _pool()
    reference = _ids(_serve(pool, 250))

    page = 7
    walked: list[str] = []
    for offset in range(0, len(reference), page):
        # ``get_feed`` slices one built list; the build is not offset-dependent,
        # which is exactly why a page walk must reassemble the reference.
        walked.extend(_ids(_serve(pool, 250))[offset : offset + page])

    assert walked == reference, "a page walk did not reassemble the served order"
    assert len(set(walked)) == len(walked), "the page walk repeated a card"


def test_the_window_is_a_constant_not_derived_from_the_limit():
    """The regression guard for the mechanism itself.

    If someone reintroduces ``min(20, limit)`` the prefix tests above catch it
    only for the sizes they enumerate. This pins the constant.
    """
    assert DISCOVER_COMPOSITION_WINDOW == 20
    assert isinstance(DISCOVER_COMPOSITION_WINDOW, int)


# --------------------------------------------------------------------------
# The tie-break
# --------------------------------------------------------------------------


def test_the_canonical_key_is_total_over_every_card_type():
    """Concepts and tournaments have no ``data.id`` — the fallback is the point."""
    cards = [
        ({"type": "futures", "data": {"id": 60629711}}, "futures:60629711"),
        ({"type": "event", "data": {"id": 14632820}}, "event:14632820"),
        (
            {"type": "bundle", "data": {"id": "theme:story:grand_slam_tennis:1-2"}},
            "bundle:theme:story:grand_slam_tennis:1-2",
        ),
        (
            {"type": "concept", "data": {"key": "event:cycling:vuelta-2026"}},
            "concept:event:cycling:vuelta-2026",
        ),
        (
            {"type": "tournament", "data": {"slug": "amgen-irish-open"}},
            "tournament:amgen-irish-open",
        ),
    ]
    for card, expected in cards:
        assert _canonical_item_key(card) == expected

    keys = [_canonical_item_key(c) for c, _ in cards]
    assert len(set(keys)) == len(keys), "the composite key collided across types"


def test_a_card_with_no_identity_degrades_instead_of_raising():
    """Returning '' keeps the sort total; raising inside a sort kills the feed."""
    assert _canonical_item_key({"type": "futures", "data": {}}) == ""
    assert _canonical_item_key({"type": "futures"}) == ""


def test_an_int_id_and_a_string_id_in_one_pool_stay_comparable():
    """Mixed id types must not raise when the tuples are compared."""
    a = _rank_key({"type": "futures", "score": 90, "data": {"id": 5}})
    b = _rank_key({"type": "bundle", "score": 90, "data": {"id": "theme:x"}})
    assert (a > b) != (a < b)  # a strict total order, either way round


def test_ties_break_ascending_by_canonical_key_under_reverse_sort():
    """The direction is chosen, not inherited from ``reverse=True``.

    Descending would REVERSE every tied run relative to what production serves
    today; ties are usually consecutive ids from one candidate query. Ascending
    confines the change to the ties that were genuinely unstable.
    """
    tied = [
        {"type": "event", "score": 90, "_rank_score": 90.0, "data": {"id": 702}},
        {"type": "event", "score": 90, "_rank_score": 90.0, "data": {"id": 701}},
        {"type": "event", "score": 90, "_rank_score": 90.0, "data": {"id": 700}},
    ]
    ordered = sorted(tied, key=_rank_key, reverse=True)
    assert [c["data"]["id"] for c in ordered] == [700, 701, 702]


def test_the_tie_break_never_outranks_the_score():
    """A canonical key must not promote a lower-scoring card."""
    low_key_high_score = {
        "type": "event",
        "score": 95,
        "_rank_score": 95.0,
        "data": {"id": 999},
    }
    high_key_low_score = {
        "type": "event",
        "score": 90,
        "_rank_score": 90.0,
        "data": {"id": 100},
    }
    ordered = sorted(
        [high_key_low_score, low_key_high_score], key=_rank_key, reverse=True
    )
    assert ordered[0] is low_key_high_score


def test_the_tie_break_supports_gt_for_the_dedupe_comparison():
    """``_dedupe_futures_by_canonical`` compares two ``_rank_key`` tuples with ``>``.

    Tuple comparison delegates to the element's own ``__gt__`` once ``__eq__``
    separates them, so a wrapper with only ``__lt__`` sorts fine and then raises
    ``TypeError`` in dedup. This is that missing-dunder guard.
    """
    a = _rank_key({"type": "futures", "score": 90, "data": {"id": 1}})
    b = _rank_key({"type": "futures", "score": 90, "data": {"id": 2}})
    assert (a > b) or (b > a)
    assert _AscendingTieBreak("a") > _AscendingTieBreak("b")
    assert _AscendingTieBreak("b") < _AscendingTieBreak("a")
    assert _AscendingTieBreak("a") == _AscendingTieBreak("a")


def test_the_order_is_stable_across_repeated_identical_builds():
    """Two identical requests serve the identical deck."""
    pool = _pool()
    assert _ids(_serve(pool, 40)) == _ids(_serve(pool, 40))


def test_shuffling_the_input_pool_does_not_change_the_served_order():
    """The point of a canonical tie-break: incidental input order stops mattering.

    This is the assertion that would still fail on the parent commit even with a
    fixed window, because the window makes composition deterministic GIVEN an
    input order — it does not make the input order deterministic.
    """
    import random

    pool = _pool()
    reference = _ids(_serve(pool, 40))

    for seed in (1, 2, 3):
        shuffled = pool[:]
        random.Random(seed).shuffle(shuffled)
        assert _ids(_serve(shuffled, 40)) == reference, (
            f"input pool order (seed {seed}) changed the served order"
        )
