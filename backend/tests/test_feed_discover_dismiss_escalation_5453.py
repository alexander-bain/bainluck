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
    CATEGORY_INTEREST_MAX_BONUS,
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


# ---------------------------------------------------------------------------
# CERT-2672 — THE REPAIR: ONE CANONICAL CATEGORY KEY, WRITE THROUGH TO SCORING
# ---------------------------------------------------------------------------
#
# The first presentation of this ship was BLOCKed, correctly, on a real served
# path: everything above uses `politics`, a category whose two vocabularies
# happen to agree, and the escalation is therefore proven only where the defect
# could not occur.
#
# An EVENT card writes the sport-key ROOT (`americanfootball`); a FUTURES card
# writes the LLM category (`football`); `compute_event_multiplier` looks up
# `_category_from_sport_key("americanfootball_nfl")`, which is `football`. So an
# NFL event swipe landed in a bucket the event scorer never reads, and the
# staged production specimen — Alex's own rows — names six of them.
#
# Measured over 30 days on 2026-09-12, `discover_interactions`:
#
#     football | native | futures | 520   americanfootball | native | event | 151
#     hockey   | native | futures | 470   americanfootball | web    | event |   4
#     football | web    | futures | 132   basketball       | native | event |  10
#
# These drive the REAL loader and the REAL `compute_event_multiplier`, at every
# rung, with the positive-engagement control beside them.


def _nfl_multiplier(ctx):
    """What a real NFL game card scores through the real event scorer."""
    from app.utils.personalization import compute_event_multiplier

    return compute_event_multiplier(
        ctx,
        home_team_id=None,
        away_team_id=None,
        sport_key="americanfootball_nfl",
        event_id=None,
    )


@pytest.mark.asyncio
async def test_eight_nfl_event_swipes_reach_the_eight_swipe_floor_5453():
    """THE CERT-2672 SPECIMEN, end to end.

    Eight NFL EVENT swipes — written under `americanfootball`, the only key a
    web or native event card has ever produced — must reach the deepest floor
    when the card they are meant to push down is scored. Before the repair this
    returned multiplier 1.0 with no personalization reason at all: the rollup
    key and the lookup key were two different strings, and `.get(key, 0.0)`
    cannot report a miss.
    """
    ctx = await _load([("americanfootball", "unlike", 8), _WARM])
    result = _nfl_multiplier(ctx)

    assert result.multiplier == pytest.approx(
        1.0 + CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY
    ), (
        f"an NFL card scored {result.multiplier} after eight swipes away from "
        f"NFL cards; reasons={result.reasons}"
    )
    assert any("discover_dismiss" in r for r in result.reasons), result.reasons


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "swipes,expected",
    [
        # -0.15 is master's shallow end and this tree keeps serving it: three
        # swipes do not reach the -0.40 floor, because the floor is a BOUND and
        # `max(floor, value)` returns the value. Same number as
        # `test_three_swipes_are_unchanged_by_this_fix` asserts for politics —
        # the point of repeating it here is that NFL must behave identically to
        # a category whose two vocabularies never disagreed.
        (3, -0.15),
        (5, CATEGORY_DISMISS_5_SWIPE_MAX_PENALTY),
        (8, CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY),
    ],
)
async def test_the_nfl_ladder_runs_through_the_real_event_scorer(swipes, expected):
    """Every rung, on the vocabulary the defect lives in — not just the top one.

    A single 8-swipe assertion would pass against a repair that merged the keys
    but broke the ladder underneath it.
    """
    ctx = await _load([("americanfootball", "unlike", swipes), _WARM])

    assert _nfl_multiplier(ctx).multiplier == pytest.approx(1.0 + expected)


@pytest.mark.asyncio
async def test_the_nfl_ladder_is_monotonic_through_the_real_event_scorer():
    multipliers = [
        _nfl_multiplier(
            await _load([("americanfootball", "unlike", n), _WARM])
        ).multiplier
        for n in (3, 5, 8)
    ]

    assert multipliers == sorted(multipliers, reverse=True), multipliers
    assert len(set(multipliers)) == 3, f"rungs must be distinguishable: {multipliers}"


@pytest.mark.asyncio
async def test_an_nfl_reader_who_also_engages_is_not_penalised():
    """POSITIVE CONTROL. The repair must not become a mute button on NFL.

    A reader who opens and likes football cards as well as swiping some away
    keeps a non-negative multiplier — #1091 and notice 35 guard this side, and
    a key merge is exactly the change that could over-collect negatives.
    """
    ctx = await _load(
        [
            ("americanfootball", "unlike", 3),
            ("americanfootball", "open", 12),
            ("americanfootball", "like", 8),
            _WARM,
        ]
    )

    assert _nfl_multiplier(ctx).multiplier >= 1.0


@pytest.mark.asyncio
async def test_a_football_futures_swipe_and_an_nfl_event_swipe_are_one_reader():
    """The merge itself: the two vocabularies must reach the SAME bucket.

    Five swipes under each key is ten swipes at one sport, and a reader who has
    said no ten times should be past the eight-swipe rung — not sitting at the
    three-swipe floor twice over.
    """
    ctx = await _load(
        [("americanfootball", "unlike", 5), ("football", "unlike", 5), _WARM]
    )

    assert ctx.discover_category_negative_counts == {"football": 10}
    assert _nfl_multiplier(ctx).multiplier == pytest.approx(
        1.0 + CATEGORY_DISMISS_8_SWIPE_MAX_PENALTY
    )


@pytest.mark.asyncio
async def test_an_untouched_sport_is_unaffected_by_the_merge():
    """CONTROL. Merging football keys must not colour hockey, or anything else."""
    from app.utils.personalization import compute_event_multiplier

    ctx = await _load([("americanfootball", "unlike", 8), _WARM])

    assert compute_event_multiplier(
        ctx,
        home_team_id=None,
        away_team_id=None,
        sport_key="baseball_mlb",
        event_id=None,
    ).multiplier == 1.0


def test_the_alias_map_covers_every_root_that_disagrees():
    """The alias map is DERIVED, not remembered.

    Every sport-key root served in the last 30 days (measured 2026-09-12), with
    the `llm_sport_category` its futures cards report. The roots that already
    agree are listed too, so a wrong alias fails here as loudly as a missing
    one — a map asserted only against its own keys can never be wrong.
    """
    from app.utils.personalization import canonical_discover_category

    served_roots_to_futures_category = {
        "americanfootball": "football",
        "icehockey": "hockey",
        "motorsport": "motorsports",
        "rugbyleague": "rugby",
        "rugbyunion": "rugby",
        # Agree already — the reason the split was invisible for years.
        "soccer": "soccer",
        "tennis": "tennis",
        "baseball": "baseball",
        "basketball": "basketball",
        "mma": "mma",
        "boxing": "boxing",
        "cricket": "cricket",
        "golf": "golf",
        "esports": "esports",
        "lacrosse": "lacrosse",
        "handball": "handball",
        "aussierules": "aussierules",
        "rugby": "rugby",
    }

    for root, futures_category in served_roots_to_futures_category.items():
        assert canonical_discover_category(root) == futures_category, root
        # and the futures vocabulary is a fixed point — canonicalising twice
        # must not walk further, or two readers could land in different buckets
        assert canonical_discover_category(futures_category) == futures_category


def test_the_canonicaliser_keeps_absence_absent():
    """It normalises a spelling; it does not invent a category.

    Returning `"other"` for a blank would file every unclassified swipe into one
    real bucket and let it accumulate a penalty nobody asked for.
    """
    from app.utils.personalization import canonical_discover_category

    assert canonical_discover_category(None) is None
    assert canonical_discover_category("") is None
    assert canonical_discover_category("   ") is None
    assert canonical_discover_category("  AmericanFootball ") == "football"


def test_the_two_builders_agree_on_the_canonical_key():
    """RED CHECK for the repair itself: both dicts are one key space.

    The BLOCKed tree passed every assertion above this section while these two
    dictionaries were keyed differently from the scorer's lookup.
    """
    rows = [("americanfootball", "unlike", 6), _WARM]

    assert _build_discover_category_negative_counts(rows) == {"football": 6}
    assert "football" in _build_discover_category_affinities(rows)
    assert "americanfootball" not in _build_discover_category_affinities(rows)


# ---------------------------------------------------------------------------
# CERT-2676 — A DOWNRANK IS NOT A FILTER
# ---------------------------------------------------------------------------
#
# Presentation two was BLOCKed for the half the first two presentations did not
# look at: once the multiplier finally reached NFL cards, it reached the
# ADMISSION GATE with them. `feed.py` compared `base_score * multiplier` against
# a floor, so at the eight-swipe rung (multiplier 0.20) base scores of 40, 60
# and 98 arrived as 7, 11 and 19 — all three below the `min_score` of 30, all
# three `continue`d. Futures had the same shape at the 15 and 55 bars.
#
# That is the standing Discover rule inverted: "personalization is bounded and
# latency-safe — left-swipe is a soft downrank, never a hard dismissal"
# (CLAUDE.md), and #1091's "game events are never capped into an empty tab".
# A reader who swipes eight football cards away is asking for less football.
#
# `admission_multiplier` adds only the swipe-derived category dismissal back.
# The onboarding gates — "Nah" to a sport, "only if it's wild" — are intentional
# exclusions the reader chose, and they stay inside the number so they keep
# filtering. The tests below assert BOTH: the downrank survives, and so do the
# deliberate filters.

_EVENT_MIN_SCORE = 30  # the ordinary event admission floor in `feed.py`
_FUTURES_MIN_SCORE = 15  # the ordinary futures floor
#: The three base scores CERT-2676's probe used: a weak card, a middling one,
#: and one at the display cap.
_BASE_SCORES = (40, 60, 98)


def _futures_multiplier(ctx, sport_category="football"):
    from app.utils.personalization import compute_futures_multiplier

    return compute_futures_multiplier(
        ctx,
        sport_category=sport_category,
        outcome_team_ids=[],
        futures_market_id=None,
        sport_key="americanfootball_nfl",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("base_score", _BASE_SCORES)
async def test_eighth_nfl_swipe_downranks_without_filtering_the_event_5453(base_score):
    """THE CERT-2676 SPECIMEN. Both halves, on one card, at three base scores.

    Driven through the real `_discover_admission_score` — the function both
    gates in `feed.py` call — rather than through a copy of its arithmetic.
    """
    from app.routes.feed import _discover_admission_score

    ctx = await _load([("americanfootball", "unlike", 8), _WARM])
    p_result = _nfl_multiplier(ctx)

    # It DOWNRANKS: the rank score still carries the full eight-swipe penalty.
    ranked = min(98, int(base_score * p_result.multiplier))
    assert ranked < base_score, "the eighth swipe stopped pushing the card down"

    # It does NOT FILTER.
    admission = _discover_admission_score(base_score, p_result)
    assert admission >= _EVENT_MIN_SCORE, (
        f"base {base_score} reaches the admission gate as {admission}, below the "
        f"{_EVENT_MIN_SCORE} floor — eight swipes have become a hard dismissal "
        f"(multiplier={p_result.multiplier}, "
        f"admission_multiplier={p_result.admission_multiplier})"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("base_score", _BASE_SCORES)
async def test_the_eighth_swipe_does_not_filter_a_futures_card_either_5453(base_score):
    """The futures equivalent the repair asked for. Bars are 15 and 55."""
    from app.routes.feed import _discover_admission_score

    ctx = await _load([("football", "unlike", 8), _WARM])
    p_result = _futures_multiplier(ctx)

    assert min(98, int(base_score * p_result.multiplier)) < base_score
    assert _discover_admission_score(base_score, p_result) >= _FUTURES_MIN_SCORE


@pytest.mark.asyncio
@pytest.mark.parametrize("base_score", _BASE_SCORES)
async def test_the_eighth_swipe_does_not_filter_a_sports_mode_futures_card_5453(
    base_score,
):
    """THE THIRD GATE. `/sports` mode has its own futures scorer and its own
    15-bar, and it reads the SAME personalization context as Discover —
    `_load_personalization_context` is called once for both modes and handed to
    `_score_sports_mode_futures`. So the reader's DISCOVER swipes were deciding
    what the SPORTS feed is allowed to show: at the eighth swipe a base-40 NFL
    futures card arrived as 8 and was dropped from a surface the reader never
    swiped on.

    CERT-2676 named the event gate and the futures gate; this one has the
    identical shape and was missed by both of the first two repairs.
    """
    from app.routes.feed import _discover_admission_score

    ctx = await _load([("football", "unlike", 8), _WARM])
    p_result = _futures_multiplier(ctx)

    # The gate's own bar, as written at `_score_sports_mode_futures`.
    assert min(98, int(base_score * p_result.multiplier)) < base_score
    assert _discover_admission_score(base_score, p_result) >= 15


@pytest.mark.asyncio
async def test_the_blocked_tree_is_what_this_guard_would_have_caught():
    """RED CHECK, stated as the arithmetic CERT-2676 actually reported.

    `base * multiplier` at the eight-swipe rung must be BELOW the floor — if it
    were not, the two tests above would pass against the BLOCKed tree and prove
    nothing. 40/60/98 -> 7/11/19 is the cert's own probe.
    """
    ctx = await _load([("americanfootball", "unlike", 8), _WARM])
    m = _nfl_multiplier(ctx).multiplier

    dropped = [min(98, int(b * m)) for b in _BASE_SCORES]
    assert dropped == [7, 11, 19], dropped  # CERT-2676's own probe
    assert all(d < _EVENT_MIN_SCORE for d in dropped)


@pytest.mark.asyncio
async def test_the_downrank_still_reorders_against_an_untouched_sport():
    """The ship itself, restated as ORDER rather than as a number.

    Admitting the card is only correct if it still loses to a baseball card of
    the same base score — otherwise the fix has quietly removed the penalty.
    """
    ctx = await _load([("americanfootball", "unlike", 8), _WARM])
    from app.utils.personalization import compute_event_multiplier

    nfl = _nfl_multiplier(ctx).multiplier
    mlb = compute_event_multiplier(
        ctx, None, None, "baseball_mlb", None
    ).multiplier

    assert 60 * nfl < 60 * mlb


@pytest.mark.asyncio
async def test_a_nah_sport_is_still_filtered():
    """CONTROL. The onboarding exclusions must keep excluding.

    `sport_nah` is read off `p_result.reasons` by the gate and its penalty is
    INSIDE `admission_multiplier`, so a "Nah" sport is untouched by this repair.
    """
    from app.utils.personalization import (
        NAH_AFFINITY_PENALTY,
        PersonalizationContext,
        compute_event_multiplier,
    )
    from app.routes.feed import _discover_admission_score

    ctx = PersonalizationContext(
        is_authenticated=True, sport_affinities={"baseball_mlb": 1.0}
    )
    p_result = compute_event_multiplier(ctx, None, None, "americanfootball_nfl", None)

    assert any("sport_nah" in r for r in p_result.reasons)
    assert p_result.admission_multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
    assert _discover_admission_score(40, p_result) < _EVENT_MIN_SCORE


@pytest.mark.asyncio
async def test_a_low_affinity_sport_still_faces_the_higher_bar():
    """CONTROL. "Only if it's wild" is a reader's own choice, not a swipe."""
    from app.utils.personalization import (
        LOW_AFFINITY_PENALTY,
        PersonalizationContext,
        compute_event_multiplier,
    )
    from app.routes.feed import _discover_admission_score

    ctx = PersonalizationContext(
        is_authenticated=True, sport_affinities={"americanfootball_nfl": 0.1}
    )
    p_result = compute_event_multiplier(ctx, None, None, "americanfootball_nfl", None)

    assert any("sport_suppress" in r for r in p_result.reasons)
    assert p_result.admission_multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)
    assert _discover_admission_score(70, p_result) < 55


@pytest.mark.asyncio
async def test_a_positive_affinity_still_raises_the_admission_score():
    """CONTROL. Only the NEGATIVE side is held out of the gate.

    A boost that could not lift a card over an admission floor would be a
    different bug introduced by the same edit.
    """
    from app.routes.feed import _discover_admission_score

    ctx = await _load(
        [("americanfootball", "open", 20), ("americanfootball", "share", 6), _WARM]
    )
    p_result = _nfl_multiplier(ctx)

    assert p_result.multiplier > 1.0
    assert p_result.admission_multiplier == pytest.approx(p_result.multiplier)
    assert _discover_admission_score(40, p_result) > 40


def test_an_unpersonalized_card_is_unchanged_by_the_split():
    """CONTROL, the widest one: for every reader with no dismissals the two
    numbers are the same, so this repair is inert everywhere it should be."""
    from app.routes.feed import _discover_admission_score
    from app.utils.personalization import PersonalizationContext, compute_event_multiplier

    p_result = compute_event_multiplier(
        PersonalizationContext(), None, None, "americanfootball_nfl", None
    )

    assert p_result.multiplier == 1.0
    assert p_result.admission_multiplier == 1.0
    assert _discover_admission_score(40, p_result) == 40


def test_both_admission_gates_read_the_shared_helper():
    """The wiring. Two gates computed the same expression separately, which is
    why one could be repaired and the other left broken.

    Reads the CALL SITES: a helper nothing calls is the same defect in a new
    shape, and the futures gate must pass `recycled=`.
    """
    import ast
    import inspect

    import app.routes.feed as feed_module

    tree = ast.parse(inspect.getsource(feed_module))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_discover_admission_score"
    ]
    assert len(calls) == 3, (
        f"expected the Discover event gate, the Discover futures gate and the "
        f"/sports-mode futures gate to share the helper, found {len(calls)} "
        f"call sites"
    )
    # Named, not just counted: three calls that all moved into one function
    # would satisfy a bare count while a gate sat unrepaired again.
    callers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(call in ast.walk(node) for call in calls)
    }
    assert callers == {
        "_score_events",
        "_score_futures",
        "_score_sports_mode_futures",
    }, f"the three admission gates are not the three callers: {sorted(callers)}"
    assert any(
        "recycled" in {kw.arg for kw in call.keywords} for call in calls
    ), "the futures gate must keep applying the recycle penalty to admission"

    # And NO gate anywhere in the module still compares a `personalized_score`
    # against a floor. Derived from the parse tree rather than from a list of
    # forbidden source lines: the list this replaces held three strings, one of
    # which ("and not my_teams_only and personalized_score < 15") matched no
    # line in either tree, and the gate it was meant to describe — the
    # /sports-mode one at `_score_sports_mode_futures` — was live and unrepaired
    # while this guard passed. A scan that enumerates its own population cannot
    # miss a fourth gate the way a hand-written list missed the third.
    comparisons = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(
            isinstance(operand, ast.Name) and operand.id == "personalized_score"
            for operand in [node.left, *node.comparators]
        )
    ]
    assert comparisons == [], (
        f"`personalized_score` is compared at feed.py line(s) "
        f"{[node.lineno for node in comparisons]}: a swipe-derived downrank is "
        f"deciding eligibility again (CERT-2676). It may RANK; the number a "
        f"gate reads is `_discover_admission_score`."
    )
