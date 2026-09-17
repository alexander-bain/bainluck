"""#6702 — the /economics mortgage card stops printing a rescaled ladder.

Measured on production 2026-09-16 22:28 PDT at 390px, the HOUSING & MORTGAGES
card was headed by the hardcoded string "30-year mortgage rate by end of 2026"
over thirteen bars, every one of them labelled ``Above 6.…`` and ramping
smoothly from 8.5% to 6.1%. Three defects in one card:

1. The rows were a CUMULATIVE ladder run through ``_brackets_from_outcomes``,
   which rescales anything summing past 105% back to 100. Market ``60775281``
   sums to **1111%**, so its ``Above 6.73%`` rung — which Kalshi prices at
   **94.5** — printed as **8.5**. The monotone ramp was the rescale, not a shape
   in the data. This is ``economics.py``'s own documented rule (see
   ``_CUMULATIVE_PREFIXES``: such rows "must never be normalized or rescaled
   against each other"), one call site short.
2. The labels differ only in their last two characters and were rendered in a
   56px right-truncating column, so all thirteen read ``Above 6.…``.
3. The header named end-of-2026 while the market it drew was *"30-year mortgage
   rate this week"*, resolving the next morning — and WHICH market it drew was
   undefined: last match wins, on a query with no ``ORDER BY``.

═══ WHERE THESE ASSERTIONS LOOK ═══

Same discipline as ``test_economics_recession_headline_2674.py``: the
load-bearing tests call ``get_economics`` and read
``result["themes"]["housing"]``, which IS the published payload — what the
precompute task serializes into the cache and what the endpoint returns. There
is no transform between the assertion point and the bytes the page receives.
Asserting on ``select_mortgage_ladder`` alone would stop short of the two things
that were actually wrong: the rescale and the binding.

═══ FOUR WAYS THESE GUARDS COULD HAVE BEEN VACUOUS ═══

1. **The extreme filter.** ``should_exclude_from_featured`` drops a market whose
   leader clears 0.98, and a cumulative ladder's leader is its loosest bound —
   a near-certainty by construction. Two of the three real mortgage markets are
   dropped this way before the theme loop, so a fixture pool copied verbatim
   would leave the suite ranking a one-element list and every ordering claim
   below would be a loop over nothing. ``TestTheSeedIsReal`` pins the arrival
   count, and ``_LADDERS`` deliberately holds two SURVIVING ladders.
2. **Containment.** The rescaled 8.5 and the true 94.5 are different numbers,
   but ``"6.73"`` appears in both labels. Every rung claim below is an equality
   on the PRICE, and the sum-of-rows assertion is the one that cannot be passed
   by a relabelling.
3. **Order.** A fixture listing the intended winner last would be green under
   the old "last one wins" code. ``_LADDERS`` puts the winner FIRST, and
   ``test_shuffling_the_query_order_cannot_change_the_card`` runs the whole
   route over every permutation.
4. **The clock.** ``get_economics`` calls ``datetime.now(timezone.utc)`` and
   ``should_exclude_from_featured`` reads it, so an unpinned test would change
   meaning as the fixtures' implied dates recede (gotcha #44). ``datetime`` is
   patched to a fixed instant in every run.
"""

from datetime import datetime, timezone
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.economics import get_economics
from app.utils.economics_headline import LadderCandidate, select_mortgage_ladder

# Mid-year, well away from any implied title date in the pool below.
FIXED_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _outcome(idx: int, name: str, pct: float):
    return SimpleNamespace(
        id=idx, name=name, current_probability=pct / 100.0, rank=idx
    )


def _ladder(mid: int, name: str, rungs: list[tuple[str, float]], source="kalshi"):
    """A cumulative-threshold mortgage market shaped as `get_economics` reads it."""
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=f"kxmortgage-{mid}",
        outcomes=[_outcome(i, n, p) for i, (n, p) in enumerate(rungs)],
        status="open",
        llm_sport_category="economics",
        group_id=None,
        volume=10_000.0,
    )


# `60775281`'s thirteen real rungs, measured by db-query 2026-09-17 06:4xZ.
# They sum to 1111.0% — the input that produced the 8.5% on screen.
_WEEKLY_RUNGS = [
    ("Above 6.73%", 94.5), ("Above 6.74%", 94.5), ("Above 6.75%", 93.5),
    ("Above 6.76%", 92.0), ("Above 6.77%", 90.0), ("Above 6.78%", 89.0),
    ("Above 6.79%", 88.5), ("Above 6.80%", 88.5), ("Above 6.81%", 81.5),
    ("Above 6.82%", 81.0), ("Above 6.83%", 77.0), ("Above 6.84%", 73.0),
    ("Above 6.85%", 68.0),
]

# A second SURVIVING ladder — wider spread, so it should take the card. Its top
# rung is held at 96.0 on purpose: the real wide ladder in the pool (109321,
# 99.9 → 57.0) is dropped by the extreme filter before it can be chosen, and a
# fixture that reproduced that would make the ranking untestable. See vacuity
# note 1.
_ANNUAL_RUNGS = [
    ("Above 6.5%", 96.0), ("Above 6.6%", 93.0), ("Above 6.7%", 88.0),
    ("Above 6.8%", 79.0), ("Above 6.9%", 68.0), ("Above 7.0%", 57.0),
]

# Polymarket `115646`, which is NOT a ladder: mixed direction arrows plus a
# stray Yes/No pair. Its spread is the widest in the pool, so a ranking without
# the candidacy gate picks it — and `_brackets_from_outcomes` would then rescale
# it, which is the defect. Held under 0.98 so the extreme filter is not what
# keeps it out; this suite is testing the candidacy gate, not that filter.
_NOT_A_LADDER = [
    ("↑ 6.20%", 95.0), ("↓ 6.00%", 95.0), ("↑ 6.50%", 90.0),
    ("↑ 7.00%", 72.0), ("↓ 5.90%", 5.5), ("Yes", 3.0),
]

# NOTE the order: the intended winner is FIRST, so a fix that only reshuffles
# cannot pass by accident (vacuity note 3).
_LADDERS = [
    (109321, "How high will 30yr mortgage rate get this year?", _ANNUAL_RUNGS),
    (115646, "Will the 30-year Mortgage Rate hit __ in 2026?", _NOT_A_LADDER),
    (60775281, "30-year mortgage rate this week", _WEEKLY_RUNGS),
]


def _mortgage_markets():
    return [_ladder(mid, name, rungs) for mid, name, rungs in _LADDERS]


async def _run(markets):
    """Call the builder and return the published housing theme."""
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = FIXED_NOW
        payload = await get_economics(db)
    return payload["themes"]["housing"]


# ---------------------------------------------------------------------------
# Non-vacuity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheSeedIsReal:
    """If the fixtures stop reaching the housing theme, or the extreme filter
    starts eating them, everything below is a loop over nothing."""

    async def test_every_seeded_market_reaches_the_housing_theme(self):
        housing = await _run(_mortgage_markets())
        assert housing["count"] == len(_LADDERS), (
            "the seeded markets no longer classify as `housing`, or "
            "should_exclude_from_featured is dropping them — every assertion "
            "in this file is vacuous until this passes"
        )

    async def test_two_of_them_are_ladders_so_the_ranking_has_a_choice(self):
        """The property vacuity note 1 exists for. If only one candidate ever
        reaches `select_mortgage_ladder`, the ordering tests below prove
        nothing about the ranking."""
        assert (
            len(
                [
                    r
                    for _, _, r in _LADDERS
                    if all(n.lower().startswith("above ") for n, _ in r)
                ]
            )
            == 2
        )

    async def test_the_card_is_published_at_all(self):
        housing = await _run(_mortgage_markets())
        assert housing["mortgage_dist"] is not None


# ---------------------------------------------------------------------------
# The ship, defect 1: the rows are the prices the venue quotes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheRowsAreNotRescaled:

    async def test_a_ladders_rungs_are_published_raw(self):
        """The defect in one assertion: 94.5 is what Kalshi quotes, 8.5 is what
        the page printed."""
        housing = await _run([_ladder(60775281, "30-year mortgage rate this week", _WEEKLY_RUNGS)])
        by_label = {label: prob for prob, label in housing["mortgage_dist"]["rows"]}
        assert by_label["Above 6.73%"] == 94.5
        assert by_label["Above 6.85%"] == 68.0

    async def test_the_reported_screen_does_not_reproduce(self):
        """#6702's exact card: 8.5 at the top, 6.1 at the bottom."""
        housing = await _run([_ladder(60775281, "30-year mortgage rate this week", _WEEKLY_RUNGS)])
        probs = [prob for prob, _ in housing["mortgage_dist"]["rows"]]
        assert 8.5 not in probs
        assert 6.1 not in probs

    async def test_the_rows_are_allowed_to_sum_past_one_hundred(self):
        """The invariant behind the number, stated so it survives the fixture
        being re-measured: a cumulative ladder is not a distribution. A
        rescaling regression cannot pass this, whatever the rungs become."""
        housing = await _run([_ladder(60775281, "30-year mortgage rate this week", _WEEKLY_RUNGS)])
        total = sum(prob for prob, _ in housing["mortgage_dist"]["rows"])
        assert total > 105, f"rows sum to {total} — they have been rescaled"

    async def test_a_short_ladder_still_draws_a_card(self):
        """The branch's own floor is three rungs; ``_distribution_row``'s
        default floor is six, because it exists to catch what ``_market_row``
        drops above five. Passing that default through would delete the card
        for a four-rung market instead of drawing it — and the two ladders in
        the main pool are both long enough to hide it."""
        short = _ladder(
            77_777,
            "30-year mortgage rate at year end",
            [("Above 6.5%", 92.0), ("Above 6.8%", 70.0), ("Above 7.1%", 41.0)],
        )
        housing = await _run([short])
        assert housing["mortgage_dist"] is not None
        assert len(housing["mortgage_dist"]["rows"]) == 3

    async def test_the_page_is_told_these_are_thresholds_not_brackets(self):
        """`kind` is what routes the rows to the ladder renderer instead of the
        histogram, which is defect 2's half of the repair."""
        housing = await _run(_mortgage_markets())
        assert housing["mortgage_dist"]["kind"] == "ladder"


# ---------------------------------------------------------------------------
# The ship, defect 3: the card asks the question it answers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheCardNamesItsOwnMarket:

    async def test_the_published_question_is_the_selected_markets_own_name(self):
        housing = await _run(_mortgage_markets())
        assert (
            housing["mortgage_dist"]["q"]
            == "How high will 30yr mortgage rate get this year?"
        )
        assert housing["mortgage_dist"]["market_id"] == 109321

    async def test_the_question_and_the_rows_come_from_one_market(self):
        """Stated as an invariant over the pool rather than one expected
        string, so it survives the ranking being changed for good reasons."""
        housing = await _run(_mortgage_markets())
        dist = housing["mortgage_dist"]
        by_id = {mid: (name, rungs) for mid, name, rungs in _LADDERS}
        name, rungs = by_id[dist["market_id"]]
        assert dist["q"] == name
        assert [label for _, label in dist["rows"]] == [n for n, _ in rungs]

    async def test_the_hardcoded_timeframe_is_not_what_the_card_asks(self):
        """The literal the page used to print, over a market resolving in a
        week. Nothing may reintroduce it as a question."""
        housing = await _run(_mortgage_markets())
        assert "by end of 2026" not in housing["mortgage_dist"]["q"]


# ---------------------------------------------------------------------------
# The defect class: order dependence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOrderCannotChangeTheCard:

    async def test_shuffling_the_query_order_cannot_change_the_card(self):
        """The query feeding the theme loop carries no ORDER BY. Under the old
        code the card was whichever mortgage market came last, so this fails on
        every permutation that does not end on the intended winner."""
        seen = set()
        for perm in permutations(_mortgage_markets()):
            housing = await _run(list(perm))
            seen.add(housing["mortgage_dist"]["market_id"])
        assert seen == {109321}, f"card depends on query order: {seen}"


# ---------------------------------------------------------------------------
# Candidacy — the load-bearing half of the helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestANonLadderNeverDrawsTheCard:

    async def test_the_polymarket_market_is_not_chosen(self):
        """It has the widest spread in the pool, so a ranking without the
        candidacy gate picks it — and it would then be rescaled."""
        housing = await _run(_mortgage_markets())
        assert housing["mortgage_dist"]["market_id"] != 115646

    async def test_a_pool_of_only_non_ladders_publishes_no_card(self):
        """Rather than a card whose numbers are a rescale of something that was
        never a distribution. An empty space beats a confident wrong one."""
        housing = await _run(
            [_ladder(115646, "Will the 30-year Mortgage Rate hit __ in 2026?", _NOT_A_LADDER)]
        )
        assert housing["mortgage_dist"] is None

    async def test_a_section_with_no_mortgage_market_publishes_no_card(self):
        housing = await _run([])
        assert housing["mortgage_dist"] is None


# ---------------------------------------------------------------------------
# The other housing markets keep their rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheRestOfTheSectionSurvives:

    async def test_a_non_chosen_non_ladder_still_reaches_the_market_list(self):
        """The branch `continue`s on a candidate, so a regression that
        `continue`d on every mortgage market would silently empty the list
        beside the card."""
        binary = SimpleNamespace(
            id=13794328,
            name="Will the U.S. 30-year Fixed-Rate Mortgage hit 7.00% by 2027?",
            source="polymarket",
            external_id="pm-13794328",
            outcomes=[_outcome(0, "Yes", 41.0), _outcome(1, "No", 59.0)],
            status="open",
            llm_sport_category="economics",
            group_id=None,
            volume=10_000.0,
        )
        housing = await _run([*_mortgage_markets(), binary])
        assert 13794328 in [m["market_id"] for m in housing["markets"]]


# ---------------------------------------------------------------------------
# The ranking, in isolation
# ---------------------------------------------------------------------------


class TestSelectMortgageLadder:

    def test_the_widest_spread_wins(self):
        narrow = LadderCandidate(1, "narrow", [94.5, 90.0, 88.0])
        wide = LadderCandidate(2, "wide", [96.0, 70.0, 57.0])
        assert select_mortgage_ladder([narrow, wide]) is wide
        assert select_mortgage_ladder([wide, narrow]) is wide

    def test_an_equal_spread_falls_to_market_id(self):
        """A total tiebreak, so the result never depends on query order — the
        property #2674 found missing."""
        a = LadderCandidate(7, "a", [90.0, 50.0])
        b = LadderCandidate(3, "b", [80.0, 40.0])
        assert select_mortgage_ladder([a, b]).market_id == 3
        assert select_mortgage_ladder([b, a]).market_id == 3

    def test_a_hairs_breadth_of_float_cannot_flip_the_card(self):
        """Spread is rounded to the precision the page prints. Two ladders that
        render identically must not swap the card between reingests."""
        a = LadderCandidate(9, "a", [90.0, 50.0])
        b = LadderCandidate(4, "b", [90.0, 50.000000001])
        assert select_mortgage_ladder([a, b]).market_id == 4
        assert select_mortgage_ladder([b, a]).market_id == 4

    def test_no_candidates_is_no_card(self):
        assert select_mortgage_ladder([]) is None

    def test_a_single_rung_ladder_has_no_spread_and_still_selects(self):
        """Today's production pool is one survivor; a degenerate one must not
        raise on the way to being the only thing there is."""
        only = LadderCandidate(5, "only", [94.5])
        assert select_mortgage_ladder([only]) is only
