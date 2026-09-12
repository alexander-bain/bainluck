"""#5453 — swiping away the 8th boring card must push harder than the 3rd.

## The defect these tests pin

``PersonalizationContext.discover_category_negative_counts`` was **declared**
(``personalization.py:115``) and **read** (``_category_dismiss_floor``,
``personalization.py:500``) and written by nothing. A write-dead field reads as
its default, so ``_category_dismiss_floor`` always returned the shallow
``CATEGORY_DISMISS_MAX_PENALTY`` (-0.40), and ``_category_affinity_bonus``'s
closing ``max(floor, value)`` then clamped away the deeper floors that
``_build_discover_category_affinities`` had already computed upstream.

``CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY`` (-0.60) and
``CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY`` (-0.80) were therefore unreachable in
production, for every reader, since they were introduced.

Alex, on TestFlight build 7, is the reader-visible half:

    "when I swipe away a boring card, it's universally replaced with a similarly
    boring card."

Swiping away the eighth market in a category moved that category exactly as far
as swiping away the third, so the slot kept refilling from the same family.

## Why the pre-existing tests stayed green

``tests/test_personalization.py`` covers the escalated floors by CONSTRUCTING a
context with ``discover_category_negative_counts={"politics": 5}`` by hand. That
proves the ladder works *if fed*; nothing proved anything fed it. This file
therefore drives the REAL loader, ``_load_personalization_context``, and asserts
on what it produces — a test that constructs the context itself cannot catch a
write-dead field, which is precisely how the field stayed write-dead.

## Both directions

Escalation has an obvious failure mode on the other side: a category penalty
that runs away empties a surface, which is #1091's lesson and standing notice 35.
So the controls below are as load-bearing as the escalation tests —
``test_a_reader_who_also_engages_…`` and ``test_the_penalty_is_bounded_…`` fail
if this change ever turns into a mute button.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.feed import (
    _DISCOVER_NEGATIVE_ACTIONS,
    _build_discover_category_affinities,
    _build_discover_category_negative_counts,
)
from app.utils.personalization import (
    CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY,
    CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY,
    CATEGORY_DISMISS_MAX_PENALTY,
    CATEGORY_INTEREST_MAX_BONUS,
    PersonalizationContext,
    _category_affinity_bonus,
)

_SESSION_ID = "swipe-loop-session-5453"

#: Enough impressions to clear the ``< 20`` cold-start fast lane in
#: ``_build_discover_category_affinities``. Pinned explicitly because the
#: cold-start branch doubles every weight and halves every threshold — a test
#: that drifted across that boundary would be measuring the other ladder.
_WARM = ("politics", "impression", 40)


def _rollup_session(rollup_rows):
    """A DB stand-in that answers the three ``discover_interactions`` reads.

    ``_load_personalization_context`` issues three queries against that one
    table with three different row shapes, so routing on the table name alone
    (as ``test_feed_personalization_roundtrips_p113`` does) would hand a 3-tuple
    rollup to a reader unpacking six columns. Route on the projection instead:

    * ``max(`` .................. the recent-items read (6 columns)
    * ``item_name`` ............. the feature rollup (5 columns)
    * otherwise ................. the category rollup (3 columns) — ours
    """

    def _result(rows):
        result = MagicMock()
        result.all.return_value = rows
        result.fetchall.return_value = rows
        result.scalars.return_value.all.return_value = rows
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        return result

    async def mock_execute(stmt, *args, **kwargs):
        lowered = str(stmt).lower()
        if "discover_interactions" not in lowered:
            return _result([])
        if "max(" in lowered or "item_name" in lowered:
            return _result([])
        return _result(list(rollup_rows))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session


async def _load(rollup_rows):
    """Build a context the way a real request does, from a rollup."""
    from app.routes.feed import _load_personalization_context

    return await _load_personalization_context(
        _rollup_session(rollup_rows), None, session_id=_SESSION_ID, config=None
    )


# ---------------------------------------------------------------------------
# The wiring — the assertion that was missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_real_loader_populates_the_negative_counts_field():
    """The general clause: the field a reader branches on is WRITTEN.

    This is the whole defect in one line. It survives deleting every other test
    in this file, and it fails against any tree where the counts stop travelling
    from the rollup into the context — including a future refactor that keeps
    ``_build_discover_category_negative_counts`` but forgets to call it.
    """
    ctx = await _load([("politics", "unlike", 8), _WARM])

    assert ctx.discover_category_negative_counts == {"politics": 8}, (
        "the dismissal counts must reach the context; an empty dict here means "
        "_category_dismiss_floor is reading its default and the escalated "
        "floors are unreachable in production"
    )


@pytest.mark.asyncio
async def test_a_single_all_results_read_does_not_starve_the_second_builder():
    """``Result.all()`` is single-use; both builders read the same rollup.

    If the affinities are non-empty while the counts are empty, someone has
    called ``.all()`` twice and the second caller got the silent zero. That is
    the same shape as the original bug, so it gets its own name.
    """
    ctx = await _load([("politics", "unlike", 8), _WARM])

    assert ctx.discover_category_affinities, "affinities should be populated"
    assert ctx.discover_category_negative_counts, (
        "counts are empty while affinities are populated — the rollup was "
        "consumed twice"
    )


# ---------------------------------------------------------------------------
# The reader-visible effect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_five_swipes_reach_the_five_swipe_floor():
    ctx = await _load([("politics", "unlike", 5), _WARM])

    assert (
        _category_affinity_bonus(ctx, "politics")
        == CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY
    )


@pytest.mark.asyncio
async def test_eight_swipes_reach_the_eight_swipe_floor():
    """The rung Alex actually hit: the 8th swipe must outrank the 5th."""
    ctx_five = await _load([("politics", "unlike", 5), _WARM])
    ctx_eight = await _load([("politics", "unlike", 8), _WARM])

    assert (
        _category_affinity_bonus(ctx_eight, "politics")
        == CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY
    )
    assert _category_affinity_bonus(ctx_eight, "politics") < _category_affinity_bonus(
        ctx_five, "politics"
    ), "swiping away more of a category must push it down harder, not the same"


@pytest.mark.asyncio
async def test_the_ladder_is_monotonic_across_its_rungs():
    """3 -> 5 -> 8 never goes back up.

    An upper-bound-style assertion on each rung separately would stay green if
    two rungs were transposed. Ordering is the property.
    """
    bonuses = []
    for n in (3, 5, 8):
        ctx = await _load([("politics", "unlike", n), _WARM])
        bonuses.append(_category_affinity_bonus(ctx, "politics"))

    assert bonuses == sorted(bonuses, reverse=True), bonuses
    assert len(set(bonuses)) == 3, f"each rung must be distinguishable: {bonuses}"


# ---------------------------------------------------------------------------
# Paired controls — the other direction (#1091, standing notice 35)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_swipes_are_unchanged_by_this_fix():
    """Below the 5-swipe rung nothing moves. Pins the blast radius.

    -0.15 is what master serves for three swipes and what this tree must keep
    serving: the fix unlocks the deep floors, it does not re-tune the shallow end.
    """
    ctx = await _load([("politics", "unlike", 3), _WARM])

    assert _category_affinity_bonus(ctx, "politics") == pytest.approx(-0.15)


@pytest.mark.asyncio
async def test_a_reader_who_also_engages_with_a_category_is_not_penalised():
    """Five swipes do NOT mute a category the reader also opens and shares.

    The escalation is gated on a net-negative affinity, not on a raw swipe
    count. Without this control the change would read as "five swipes anywhere
    kills the category", which is how a personalization signal becomes a
    blacklist.
    """
    ctx = await _load(
        [("politics", "unlike", 5), ("politics", "share", 10), _WARM]
    )

    assert _category_affinity_bonus(ctx, "politics") == pytest.approx(
        CATEGORY_INTEREST_MAX_BONUS
    ), "a category with strong positive engagement must still earn its bonus"


@pytest.mark.asyncio
async def test_the_penalty_is_bounded_however_many_cards_are_swiped():
    """500 swipes is not worse than 8. The floor is a floor.

    A penalty that kept deepening would eventually cap a surface into emptiness
    (#1091, standing notice 35). The bonus is also a bounded score DELTA, never
    a filter — nothing here can remove a category from the candidate pool.
    """
    ctx = await _load([("politics", "unlike", 500), _WARM])

    assert (
        _category_affinity_bonus(ctx, "politics")
        == CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY
    )


@pytest.mark.asyncio
async def test_an_untouched_category_is_unaffected():
    ctx = await _load([("politics", "unlike", 8), _WARM])

    assert _category_affinity_bonus(ctx, "weather") == 0.0


# ---------------------------------------------------------------------------
# The naming trap — `unlike` IS the dismissal, on every surface
# ---------------------------------------------------------------------------


def test_unlike_counts_as_a_dismissal():
    """No client has ever written ``dismiss``; both send ``unlike``.

    Web's ``"dismiss"`` is the swipe-overlay LABEL (``DiscoverCard.tsx:159``)
    while its tracked action is ``unlike`` (``:104``); native has no heart
    button, so every ``.unlike`` is a swipe-away or a context-menu "not
    interested". A ``WHERE action = 'dismiss'`` query returns 0 and reads as
    "the swipe never reached the server" — it has misled two directives already.

    So: counting only ``dismiss`` would count nothing real. This test fails if
    anyone "tidies" ``unlike`` out of the negative set.
    """
    assert "unlike" in _DISCOVER_NEGATIVE_ACTIONS
    assert _build_discover_category_negative_counts(
        [("politics", "unlike", 4)]
    ) == {"politics": 4}


def test_every_negative_action_is_counted_by_both_builders():
    """The two readers of ``_DISCOVER_NEGATIVE_ACTIONS`` cannot drift apart.

    Asserted by EQUALITY over the whole set rather than by spot-checking one
    member, so an action added to the set is covered without anyone remembering
    to extend this test.
    """
    for action in _DISCOVER_NEGATIVE_ACTIONS:
        rows = [("politics", action, 6), _WARM]
        assert _build_discover_category_negative_counts(rows) == {"politics": 6}, action
        # and the affinity builder agrees it is negative
        assert _build_discover_category_affinities(rows)["politics"] < 0, action


def test_a_positive_action_is_never_counted_as_a_dismissal():
    assert _build_discover_category_negative_counts(
        [("politics", "like", 9), ("politics", "share", 9), ("politics", "open", 9)]
    ) == {}


def test_categories_are_lowercased_like_the_affinity_builder():
    """Both builders key the same dict space, so both must normalise the same.

    A counts dict keyed ``"Politics"`` against affinities keyed ``"politics"``
    would look populated and still miss every lookup — a write-dead field
    wearing a disguise.
    """
    rows = [("Politics", "unlike", 6), _WARM]

    assert _build_discover_category_negative_counts(rows) == {"politics": 6}
    assert set(_build_discover_category_negative_counts(rows)) <= set(
        _build_discover_category_affinities(rows)
    )
