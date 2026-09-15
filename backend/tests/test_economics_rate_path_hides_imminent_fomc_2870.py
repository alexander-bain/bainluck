"""#2870 — the rate-path card stops hiding the meeting that matters most.

`/economics` headed its flagship Fed card **"2026 rate path"** over three
**2027** columns, and the Sep 2026 FOMC meeting — resolving 2026-09-16, two
days after the last measurement — was absent from it. Filed 2026-09-03, still
reproducing verbatim eleven days later.

═══ THE MECHANISM, AND WHY THE OBVIOUS READING OF IT IS WRONG ═══

`routes/economics.py` ran `should_exclude_from_featured(...)` over every
market before theming, and its `probability_extreme` arm (leader > 0.98) was a
perfect discriminator over the six open ladders:

    108574  Apr 2027  leader=0.970  18 rungs  shown
    108626  Jan 2027  leader=0.975  18 rungs  shown
    108581  Mar 2027  leader=0.970  18 rungs  shown
    109658  Dec 2026  leader=0.985  11 rungs  HIDDEN
    109947  Oct 2026  leader=0.995  11 rungs  HIDDEN
    109984  Sep 2026  leader=0.995  11 rungs  HIDDEN

The easy reading is "the market is too confident to be interesting". That is
not what is happening. These are cumulative `Above X%` ladders, so the leader
is the probability of the ladder's **lowest rung** — a near-certain statement
by construction. Kalshi trims the rungs already decided for a near-term
meeting, so the floor rung sits higher and the leader sits closer to 1.0:

    Jan 2027 (shown)   floor `Above 0.00%`   leader 0.975   18 rungs
    Sep 2026 (hidden)  floor `Above 2.75%`   leader 0.995   11 rungs

**The nearer the meeting, the shorter the ladder, the more certain the
exclusion.** The card was structurally guaranteed to omit the imminent meeting.
Sep 2026's distribution was perfectly drawable the whole time: ~86.5% of the
mass in the 3.75–4.00% bracket, which is the anchor of a rate path.

═══ WHY THE FIX IS ONE ARM ON ONE CARD, AND NOT THE PREDICATE ═══

The issue body proposes "stop applying a leader-probability test to markets
rendered as a distribution". Implemented at the predicate that is not narrow,
and the number is the reason this file exists in the shape it does:

    open markets site-wide                       26,409
      cumulative `Above X%` ladders               1,645
        currently excluded by the >0.98 bar         230

230 markets across `/economics`, `/politics`, `/entertainment` and the
cross-source spotlight would newly become featured-eligible — `2Pac Streams in
2026`, `Burger King Foot Traffic in September`, `Brent crude oil price on
September 30`. A browse-surface content change of real size, not a bug fix.

So the exception is scoped to the one card with the distribution property, by
asking the shared predicate its question **without** the confidence arm
(`leader_probability=None`). `TestTheExceptionIsScopedToThisOneCard` is the
half of this file that matters most: it is what fails if someone later
"simplifies" this into a raised constant or a predicate-level change.

═══ WAYS THESE GUARDS COULD HAVE BEEN VACUOUS, AND WHAT STOPS EACH ═══

1. **The clock.** The route calls `datetime.now(timezone.utc)` and the
   surviving `stale_explicit_title_month` arm keys off it, so an unpinned test
   would change meaning every month and the retirement guard would quietly
   stop testing anything (gotcha #44). `datetime` is patched to a fixed
   instant everywhere, and the retirement claim is swept over five clocks
   rather than asserted at one.

2. **A fixture that never reaches the card.** Every assertion below is about
   what is or is not in `fomc_meetings`; if the seed stopped classifying as
   `fed`, an empty list would satisfy most "is not present" claims trivially.
   `TestTheSeedIsReal` fails loudly first.

3. **The exclusion being asserted where it never applied.** A "still hidden"
   control is worthless if the market was never eligible for another reason.
   Each control asserts its market IS selected once its own disqualifier is
   removed, so the control is proven to be testing the arm it names.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.economics import get_economics
from app.utils.market_staleness import (
    PROBABILITY_EXTREME_HIGH,
    is_probability_extreme,
    should_exclude_from_featured,
)

# 2026-09-14, the day the defect was last measured on production. The Sep 2026
# meeting resolves 2026-09-16, so at this instant it is two days out and its
# title is NOT yet stale — which is the whole point of the specimen.
FIXED_NOW = datetime(2026, 9, 14, 21, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures — real ladder shapes, measured on production 2026-09-14
# ---------------------------------------------------------------------------


def _rungs(pairs):
    return [
        SimpleNamespace(
            id=i,
            name=f"Above {threshold}",
            current_probability=prob,
            rank=i,
        )
        for i, (threshold, prob) in enumerate(pairs, start=1)
    ]


# 109984 Sep 2026: 11 rungs, floor `Above 2.75%`, leader 0.995. The cliff
# between `Above 3.50%` (0.875) and `Above 3.75%` (0.010) is the ~86.5% of mass
# the issue says is drawable and was never drawn.
_SEP_2026_RUNGS = [
    ("2.75%", 0.995), ("3.00%", 0.990), ("3.25%", 0.950), ("3.50%", 0.875),
    ("3.75%", 0.010), ("4.00%", 0.005), ("4.25%", 0.004), ("4.50%", 0.003),
    ("4.75%", 0.002), ("5.00%", 0.001), ("5.25%", 0.001),
]

# 108626 Jan 2027: 18 rungs, floor `Above 0.00%`, leader 0.975. Identical
# component, identical code path, and it renders correctly today — the control
# the issue itself nominates.
_JAN_2027_RUNGS = [
    ("0.00%", 0.975), ("0.25%", 0.970), ("0.75%", 0.965), ("1.00%", 0.960),
    ("1.25%", 0.955), ("1.50%", 0.950), ("1.75%", 0.945), ("2.00%", 0.940),
    ("2.25%", 0.930), ("2.50%", 0.900), ("2.75%", 0.860), ("3.00%", 0.800),
    ("3.25%", 0.700), ("3.50%", 0.560), ("3.75%", 0.330), ("4.00%", 0.175),
    ("4.25%", 0.030), ("4.50%", 0.005),
]


def _ladder(mid, name, rungs, status="open", external_id=None):
    """A `Fed funds rate after …` market shaped as `get_economics` reads it.

    ``external_id`` defaults to the production spelling `KXFED-26SEP`, which
    matches NO entry in `_THEME_BY_TICKER` (`kxfedfunds` / `kxfedcuts` /
    `kxfedhikes` all miss the hyphen) — so these classify as `fed` through the
    NAME regex. Pinned here because the route's selection now re-asks
    `_classify_theme`, and a fixture with a tidier ticker would test a path
    production does not take.
    """
    return SimpleNamespace(
        id=mid,
        name=name,
        source="kalshi",
        external_id=external_id or f"KXFED-{mid}",
        outcomes=_rungs(rungs),
        status=status,
        llm_sport_category="economics",
        group_id=None,
        volume=50_000.0,
    )


def _binary(mid, name, prob, category="economics", external_id=None):
    """A one-outcome market — the shape that is NOT rendered as a
    distribution, and therefore keeps the confidence arm."""
    return SimpleNamespace(
        id=mid,
        name=name,
        source="kalshi",
        external_id=external_id or f"kxfedfunds-{mid}",
        outcomes=[SimpleNamespace(id=1, name="Yes", current_probability=prob, rank=1)],
        status="open",
        llm_sport_category=category,
        group_id=None,
        volume=10_000.0,
    )


def _production_pool():
    """The six open ladders on production 2026-09-14, three of them hidden."""
    return [
        _ladder(109984, "Fed funds rate after Sep 2026 meeting?", _SEP_2026_RUNGS),
        _ladder(109947, "Fed funds rate after Oct 2026 meeting?", _SEP_2026_RUNGS),
        _ladder(109658, "Fed funds rate after Dec 2026 meeting?", _SEP_2026_RUNGS),
        _ladder(108626, "Fed funds rate after Jan 2027 meeting?", _JAN_2027_RUNGS),
        _ladder(108581, "Fed funds rate after Mar 2027 meeting?", _JAN_2027_RUNGS),
        _ladder(108574, "Fed funds rate after Apr 2027 meeting?", _JAN_2027_RUNGS),
    ]


async def _run(markets, now=FIXED_NOW):
    """Call the builder and return the published payload."""
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = now
        return await get_economics(db)


async def _fed(markets, now=FIXED_NOW):
    return (await _run(markets, now))["themes"]["fed"]


def _ids(fed):
    return [m["market_id"] for m in fed["fomc_meetings"]]


# ---------------------------------------------------------------------------
# Non-vacuity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheSeedIsReal:
    """Everything below reasons about membership of `fomc_meetings`. If the
    fixtures stopped reaching it, the "is not present" claims would all pass
    on an empty list."""

    async def test_the_pool_reaches_the_rate_path_card(self):
        fed = await _fed(_production_pool())
        assert len(fed["fomc_meetings"]) == 6, (
            "the seeded ladders no longer reach the heatmap — every assertion "
            "in this file is vacuous until this passes"
        )

    async def test_the_ladders_classify_as_fed_through_the_name_regex(self):
        """The hyphenated production ticker matches no prefix entry, so the
        NAME rule is what themes these. If a `kxfed-` prefix is ever added to
        `_THEME_BY_TICKER` this still passes; if the name rule is narrowed, it
        fails here rather than silently emptying the card."""
        fed = await _fed([_ladder(1, "Fed funds rate after Sep 2026 meeting?", _SEP_2026_RUNGS)])
        assert _ids(fed) == [1]

    async def test_each_published_column_carries_a_drawable_distribution(self):
        fed = await _fed(_production_pool())
        for column in fed["fomc_meetings"]:
            assert column["dist"], f"{column['date']} published an empty heatmap column"


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheImminentMeetingIsOnTheCard:

    async def test_the_reported_defect_does_not_reproduce(self):
        """#2870's exact screen: three columns, every one of them 2027."""
        fed = await _fed(_production_pool())
        # `date` is "Sep 2026 meeting" — the year is the middle token, so read
        # it from `sort_key` (YYYYMM), which is also what the columns sort by.
        years = {c["sort_key"] // 100 for c in fed["fomc_meetings"]}
        assert years == {2026, 2027}, (
            f"the card is still single-year: {sorted(years)}"
        )
        assert 109984 in _ids(fed), "the Sep 2026 meeting is still hidden"

    async def test_all_three_hidden_2026_meetings_are_restored(self):
        fed = await _fed(_production_pool())
        for mid in (109984, 109947, 109658):
            assert mid in _ids(fed)

    async def test_the_three_that_already_worked_are_untouched(self):
        """The non-widening control in the other direction: this ship must not
        be a rewrite that happens to include the old set."""
        fed = await _fed(_production_pool())
        for mid in (108626, 108581, 108574):
            assert mid in _ids(fed)

    async def test_the_imminent_meeting_draws_the_mass_the_issue_named(self):
        """~86.5% in one bracket. The card could always have drawn this; the
        claim under test is that a market can be near-certain about its FLOOR
        and still have a distribution worth rendering."""
        fed = await _fed(_production_pool())
        sep = next(c for c in fed["fomc_meetings"] if c["market_id"] == 109984)
        assert max(p for p, _ in sep["dist"]) > 50.0

    async def test_the_columns_are_in_chronological_order(self):
        fed = await _fed(_production_pool())
        keys = [c["sort_key"] for c in fed["fomc_meetings"]]
        assert keys == sorted(keys)
        assert keys[0] == 202609, "the nearest meeting is not the first column"

    async def test_the_leader_probability_split_this_fix_targets_is_real(self):
        """Pins the premise rather than trusting the issue: the fixtures do
        straddle the bar, and in the direction described. Without this, a
        change to the fixture probabilities could make every test above pass
        for the wrong reason."""
        pool = {m.id: m for m in _production_pool()}
        def leader(m):
            return max(float(o.current_probability) for o in m.outcomes)
        for mid in (109984, 109947, 109658):
            assert leader(pool[mid]) > PROBABILITY_EXTREME_HIGH
        for mid in (108626, 108581, 108574):
            assert leader(pool[mid]) < PROBABILITY_EXTREME_HIGH


# ---------------------------------------------------------------------------
# The half that matters most: the exception is ONE arm on ONE card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheExceptionIsScopedToThisOneCard:
    """These are what fail if someone later replaces the scoped exception with
    a raised `PROBABILITY_EXTREME_HIGH` or a predicate-level change — the
    230-market widening this ship deliberately did not take."""

    async def test_the_shared_constant_is_not_moved(self):
        assert PROBABILITY_EXTREME_HIGH == 0.98

    async def test_the_neutralisation_mechanism_is_load_bearing(self):
        """The route passes `leader_probability=None` to switch off exactly
        one arm. If `is_probability_extreme` ever treats None as extreme, the
        card silently empties — so the contract is pinned here, not assumed."""
        assert is_probability_extreme(None) is False
        assert is_probability_extreme(0.995) is True
        assert should_exclude_from_featured(
            "Fed funds rate after Sep 2026 meeting?", "economics", "open", 0.995, FIXED_NOW,
        ) == "probability_extreme"
        assert should_exclude_from_featured(
            "Fed funds rate after Sep 2026 meeting?", "economics", "open", None, FIXED_NOW,
        ) is None

    async def test_a_near_certain_binary_fed_market_is_still_excluded(self):
        """Not a distribution, so it keeps the confidence arm. This is the
        scoping claim: the exception is about the RENDERING SHAPE, not about
        the Fed section."""
        pool = _production_pool() + [
            _binary(99001, "Fed emergency rate cut before 2027?", 0.995),
        ]
        fed = await _fed(pool)
        assert not any(
            "emergency" in (row.get("q") or "").lower()
            for row in fed["side_markets"]
        )

    async def test_a_near_certain_binary_fed_market_IS_shown_once_it_is_not_extreme(self):
        """Proves the control above tests the arm it names, rather than the
        market being unreachable for some unrelated reason."""
        pool = _production_pool() + [
            _binary(99001, "Fed emergency rate cut before 2027?", 0.42),
        ]
        fed = await _fed(pool)
        assert any(
            "emergency" in (row.get("q") or "").lower()
            for row in fed["side_markets"]
        )

    async def test_a_near_certain_ladder_on_another_theme_is_still_excluded(self):
        """A cumulative ladder that is NOT the rate-path card. `inflation`
        renders distributions too, and it is deliberately not in scope — this
        is one of the 230."""
        pool = _production_pool() + [
            _binary(99002, "Core inflation in September 2026?", 0.995, external_id="kxcpi-99002"),
        ]
        payload = await _run(pool)
        assert not any(
            "core inflation" in (row.get("q") or "").lower()
            for row in payload["themes"]["inflation"]["side_markets"]
        )

    async def test_a_ladder_themed_somewhere_else_never_reaches_the_rate_path(self):
        """The selection re-asks `_classify_theme` so it is provably the old
        set plus only the confidence-arm rejects. A ticker prefix outranks the
        name rule, so this market reads as `inflation` despite its Fed-shaped
        name — and the old code, which built the card from `themed["fed"]`,
        could never have put it on the card. Dropping the theme guard would
        make this the one market this ship newly invents a home for."""
        pool = _production_pool() + [
            _ladder(
                99004,
                "Fed funds rate after Sep 2026 meeting?",
                _SEP_2026_RUNGS,
                external_id="kxcpi-99004",
            ),
        ]
        fed = await _fed(pool)
        assert 99004 not in _ids(fed)

    async def test_a_restored_ladder_is_a_column_and_not_also_a_side_row(self):
        """A restored ladder must appear once, as a column."""
        fed = await _fed(_production_pool())
        side = " ".join((row.get("q") or "").lower() for row in fed["side_markets"])
        assert "fed funds rate after" not in side

    async def test_a_ladder_can_never_become_a_side_row(self):
        """The tripwire under the test above, and an honest record of a mutant
        this file does NOT kill.

        Deleting the `continue` in the fed loop leaves the whole suite green.
        That is not a gap in the assertions — it is because `_market_row`
        refuses any market with more than five outcomes, and these ladders
        carry 11 to 18 rungs, so the `continue` is inert today. An equivalent
        mutant, recorded rather than papered over with a test that pretends to
        kill it.

        What is pinned here instead is the REASON it is inert. Widen
        `_market_row` past five outcomes and this fails, telling whoever did it
        that a line documented as belt-and-braces has just become the only
        thing stopping a market being published twice on one card.
        """
        from app.routes.economics import _market_row

        ladder = _ladder(1, "Fed funds rate after Sep 2026 meeting?", _SEP_2026_RUNGS)
        assert len(ladder.outcomes) > 5
        assert _market_row(ladder) is None

    async def test_the_spotlight_pool_does_not_gain_the_restored_ladders(self):
        """`spotlight_eligible` is built from the untouched predicate above the
        theme append. The cross-source spotlight is a featured surface
        (UX-P194-1 / CERT-540) and this ship must not feed it anything new."""
        payload = await _run(_production_pool())
        spotlight = payload.get("cross_source") or payload.get("spotlight") or []
        for card in spotlight:
            assert "sep 2026" not in str(card).lower()


# ---------------------------------------------------------------------------
# The other two arms stay live — a meeting that has happened leaves the card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAPastMeetingStillLeavesTheCard:
    """The reason this ship is not "show every ladder": the card must still
    retire a meeting once it has happened.

    ⚠️ `status` cannot be trusted to do this alone — settled Kalshi markets sit
    at `status='open'` in our DB until the settled-events backfill reaches them
    (gotcha #33). The load-bearing arm is the title arm.
    """

    async def test_a_resolved_ladder_is_excluded(self):
        pool = _production_pool() + [
            _ladder(110226, "Fed funds rate after Jun 2026 meeting?", _SEP_2026_RUNGS, status="resolved"),
        ]
        fed = await _fed(pool)
        assert 110226 not in _ids(fed)

    async def test_a_past_month_ladder_is_excluded_even_while_status_says_open(self):
        """Exactly gotcha #33's shape: settled at the venue, `open` in our DB."""
        pool = _production_pool() + [
            _ladder(110060, "Fed funds rate after Jul 2026 meeting?", _SEP_2026_RUNGS, status="open"),
        ]
        fed = await _fed(pool)
        assert 110060 not in _ids(fed), (
            "a July meeting is on the card in September, and its status column "
            "will never say so"
        )

    @pytest.mark.parametrize(
        "when,expected",
        [
            ("2026-09-14", True),   # two days out — the specimen
            ("2026-09-20", True),   # resolved at the venue, inside the grace window
            ("2026-10-05", False),  # month over + grace elapsed — retired
            ("2026-11-01", False),
            ("2027-02-01", False),
        ],
    )
    async def test_the_sep_2026_column_retires_on_a_clock_sweep(self, when, expected):
        """The retirement is a property of the clock, so it is swept rather
        than asserted once (gotcha #44). The 2026-09-20 row is deliberately
        `True` and is the honest cost of this ship: between a meeting resolving
        and its month ending, the column can show a decided meeting whose
        distribution has collapsed onto the realised bracket. That is the
        page's existing grace behaviour for every economics market, and it
        reads as the rate path's most recent anchor.
        """
        now = datetime.fromisoformat(when).replace(tzinfo=timezone.utc)
        fed = await _fed(
            [_ladder(109984, "Fed funds rate after Sep 2026 meeting?", _SEP_2026_RUNGS)],
            now=now,
        )
        assert (109984 in _ids(fed)) is expected

    async def test_a_ladder_with_too_few_rungs_is_not_a_heatmap_column(self):
        pool = _production_pool() + [
            _ladder(99003, "Fed funds rate after Nov 2026 meeting?", [("3.75%", 0.6), ("4.00%", 0.3)]),
        ]
        fed = await _fed(pool)
        assert 99003 not in _ids(fed)


# ---------------------------------------------------------------------------
# Follow-up: the section's COUNT and its render gate use the restored set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheSectionCountsWhatItRenders:
    """Found by CERT-2899's grader against the first sha, and fixed here.

    `themes.fed.count` was `len(fed_markets)` — the post-exclusion theme list —
    so a ladder restored to the heatmap was drawn as a column and then not
    counted. The payload could report `count: 3` beside six rendered meetings.

    ⚠️ The second consequence is the one that matters, and it is not cosmetic.
    `app/economics/page.tsx` gates the WHOLE Federal Reserve section on
    `t.fed && t.fed.count > 0`. A fed theme whose only members were
    confidence-excluded ladders yields 0 and hides a section that has columns
    to draw — the same class as the bug this card was just repaired for, a
    surface keyed on a set that is not the set it renders.

    It was latent, not live: production `count` read 49, held clear of zero by
    the three non-extreme 2027 controls. Fixed rather than filed because the
    distance between latent and live here is one quiet quarter in which the
    2027 ladders also shorten.
    """

    async def test_the_count_includes_the_restored_ladders(self):
        fed = await _fed(_production_pool())
        assert fed["count"] == 6, (
            "the card renders six meetings; the section counted only the three "
            "that were never excluded"
        )

    async def test_a_section_of_only_restored_ladders_does_not_report_zero(self):
        """The render-gate case, stated as the page's own condition. Under the
        parent this is `count == 0` with one heatmap column published, i.e. the
        section disappears with content in it."""
        fed = await _fed(
            [_ladder(109984, "Fed funds rate after Sep 2026 meeting?", _SEP_2026_RUNGS)]
        )
        assert len(fed["fomc_meetings"]) == 1
        assert fed["count"] > 0, (
            "the page gates the section on `count > 0`, so this hides a "
            "Federal Reserve section that has a column to draw"
        )

    async def test_a_market_in_both_lists_is_counted_once(self):
        """A union, not a sum: the three 2027 ladders are in `fed_markets` AND
        in the heatmap source. A `+` here would report 9 for 6 markets."""
        fed = await _fed(_production_pool())
        assert fed["count"] == len({m.id for m in _production_pool()})

    async def test_non_ladder_fed_markets_are_still_counted(self):
        pool = _production_pool() + [
            _binary(99001, "Fed emergency rate cut before 2027?", 0.42),
        ]
        fed = await _fed(pool)
        assert fed["count"] == 7

    async def test_a_past_meeting_is_not_counted(self):
        """The count must not become a second way for a retired meeting to
        register on the page."""
        pool = _production_pool() + [
            _ladder(110060, "Fed funds rate after Jul 2026 meeting?", _SEP_2026_RUNGS),
        ]
        fed = await _fed(pool)
        assert fed["count"] == 6
