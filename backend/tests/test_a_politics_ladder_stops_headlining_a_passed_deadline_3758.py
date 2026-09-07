"""A /politics LADDER STOPS HEADLINING A DEADLINE THAT HAS ALREADY PASSED — #3758.

═══ WHY THIS SUITE EXISTS ═══

`_market_row` ranked a market's outcomes on `current_probability` alone. A
"When will X happen?" ladder prices its rungs in the order they were written,
and nothing ever re-prices an impossibility to zero — a rung whose date has gone
keeps its last traded price for as long as the market stays open. So the biggest
number on the ladder is routinely a date that cannot happen, and it becomes the
row's headline AND the `prob` the page sorts and displays on.

MEASURED on production 2026-09-07. `/api/politics` served five date-bounded
ladders; two headlined a rung that had already expired:

    "When will Nick Adams be confirmed as Ambassador of Malaysia?"
        Before Apr 1, 2026   3.0   <- headline, five months gone
        Before Jul 1, 2026   1.5
        Before Jan 1, 2027   0.9     the only rung that can still happen
    "Will Trump pull CBP from a sanctuary city airport?"
        Before Sep 1, 2026   2.0   <- headline, six days gone
        Before Aug 1, 2026   2.0
        Before Jan 1, 2027   1.0     the only rung that can still happen

🔴 NOTHING IN THE PIPELINE COULD HAVE CAUGHT IT, which is the part worth
recording. `should_exclude_from_featured` reads the market's TITLE, and both
titles are perfectly current questions with no date in them at all. The date
lives one level down, in the OUTCOME label. `is_title_implied_stale` cannot fire
on a market whose title is undated, however stale its rungs are.

═══ WHAT IS ASSERTED, AND WHY IT IS A SWEEP ═══

The invariant is not "these two rows look right today" — that is a fact about
2026-09-07 and it rots. It is:

    at any instant, the rung a row headlines is one that can still happen,
    unless no rung can

so the specimens are run at 72 anchors across three years (gotcha #44 — offsets
from a fixed base, never a branch on the real clock), and the invariant is
checked against the SHIPPED `outcome_deadline_expired` at each one rather than
against a remembered expectation.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import _market_row
from app.utils.market_staleness import (
    EXPIRED_RUNG_MAX_PROBABILITY,
    outcome_deadline_expired,
)

#: The day the census above was taken. Every other anchor in this file is an
#: offset from it.
NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _outcome(name: str, prob: float, oid: int = 1):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        probability_change_24h=None,
        rank=None,
    )


def _market(name: str, rungs: list[tuple[str, float]]):
    return SimpleNamespace(
        id=1,
        name=name,
        source="kalshi",
        external_id="kxtest",
        outcomes=[_outcome(n, p, oid=i + 1) for i, (n, p) in enumerate(rungs)],
    )


#: The production ladders, verbatim, with their measured prices. Named so a
#: failure says which real market broke rather than which fixture.
SPECIMENS = {
    "nick adams ambassador": [
        ("Before Apr 1, 2026", 0.030),
        ("Before Jul 1, 2026", 0.015),
        ("Before Jan 1, 2027", 0.009),
    ],
    "trump cbp sanctuary airport": [
        ("Before Sep 1, 2026", 0.020),
        ("Before Aug 1, 2026", 0.020),
        ("Before Jan 1, 2027", 0.010),
        ("Before Jul 1, 2026", 0.010),
    ],
    "tim walz out as governor": [
        ("Before 2027", 0.045),
        ("Before Sep 1, 2026", 0.020),
        ("Before February", 0.010),
        ("Before July", 0.001),
    ],
    # Controls: both already headline a live rung on 2026-09-07, so a change
    # here means the fix is too wide.
    "chuck schumer out as leader": [
        ("Before Nov 3, 2026", 0.022),
        ("Before 2026", 0.010),
        ("Before July 2026", 0.002),
    ],
    "iran presidential election": [
        ("Before Jan 1, 2027", 0.028),
        ("Before Jul 1, 2026", 0.004),
    ],
}

#: 72 anchors: the 1st and the 15th of every month across three years, centred
#: on the census date. Offsets from `NOW`'s own year, so the sweep does not
#: encode today's date, and THREE years rather than two because the latest rung
#: on these ladders is "Before Jan 1, 2027" — a two-year window never reaches
#: the all-expired state and `test_the_sweep_actually_exercises_both_states` is
#: what caught that.
_BASE_YEAR = NOW.year - 1
CLOCK_ANCHORS = [
    datetime(_BASE_YEAR + year_offset, month, day, 12, 0, 0, tzinfo=timezone.utc)
    for year_offset in (0, 1, 2)
    for month in range(1, 13)
    for day in (1, 15)
]


def _headline(rungs, now):
    row = _market_row(_market("When will it happen?", rungs), now=now)
    return row["top_outcomes"][0]["name"], row


def _live(name, now):
    return not outcome_deadline_expired(name, now)


class TestTheDefectReproduces:
    """🔴 RED-FIRST. The pre-fix ordering, hand-written, over the same rungs.

    The one place in this file where a copy is the artefact under test. Without
    it the greens below could be passing over ladders the old code also got
    right — three of the five specimens are controls, so that is not idle.
    """

    @staticmethod
    def _pre_fix_headline(rungs):
        return max(rungs, key=lambda r: r[1])[0]

    @pytest.mark.parametrize(
        "specimen", ["nick adams ambassador", "trump cbp sanctuary airport"]
    )
    def test_the_old_order_headlined_a_date_that_had_passed(self, specimen):
        headline = self._pre_fix_headline(SPECIMENS[specimen])
        assert not _live(headline, NOW), (
            f"{specimen!r} headlined {headline!r} before the fix and that rung "
            "has NOT expired — the specimen no longer demonstrates the defect"
        )

    @pytest.mark.parametrize(
        "specimen", ["chuck schumer out as leader", "iran presidential election"]
    )
    def test_the_controls_were_already_right(self, specimen):
        """A fix that changes these is too wide, and this is what says so."""
        assert _live(self._pre_fix_headline(SPECIMENS[specimen]), NOW)


class TestTheShip:
    """The two rows a reader can point at, on the day they were measured."""

    def test_nick_adams_headlines_the_rung_that_can_still_happen(self):
        headline, row = _headline(SPECIMENS["nick adams ambassador"], NOW)
        assert headline == "Before Jan 1, 2027"
        assert row["prob"] == 0.9

    def test_trump_cbp_headlines_the_rung_that_can_still_happen(self):
        headline, row = _headline(SPECIMENS["trump cbp sanctuary airport"], NOW)
        assert headline == "Before Jan 1, 2027"

    @pytest.mark.parametrize(
        "specimen", ["chuck schumer out as leader", "iran presidential election"]
    )
    def test_a_healthy_ladder_is_untouched(self, specimen):
        rungs = SPECIMENS[specimen]
        headline, _ = _headline(rungs, NOW)
        assert headline == max(rungs, key=lambda r: r[1])[0]

    def test_both_arms_of_the_year_less_rule_land_on_the_walz_ladder(self):
        """This ladder is the interesting one: it carries a year-less rung on
        EACH side of `_BARE_DATE_LOOKBACK_DAYS`, and the shipped parser splits
        them. Asserted rather than assumed, because this is exactly the place a
        reader of the diff would guess wrong (this suite's author did).

        At 2026-09-07, "Before February" is 219 days past a current-year reading
        — beyond the look-back, so it reads as NEXT February and stays LIVE.
        "Before July" is 69 days past, inside it, so it reads as this July and
        is EXPIRED. Ambiguity resolves toward live, which is the right way for
        it to fail: demoting a rung that might still happen hides a real option,
        while keeping one costs a place in the ordering.

        So the page shows the two live rungs first and then, because only two
        are live, the best-priced expired one in slot three."""
        headline, row = _headline(SPECIMENS["tim walz out as governor"], NOW)
        assert headline == "Before 2027"
        assert [o["name"] for o in row["top_outcomes"]] == [
            "Before 2027",  # live, 4.5
            "Before February",  # live — beyond the look-back, reads as next year
            "Before Sep 1, 2026",  # expired, demoted, but nothing live is left
        ]
        assert _live("Before February", NOW)
        assert not _live("Before July", NOW)


class TestItDemotesAndNeverDrops:
    """The difference from `routes/feed.py`, which STRIPS the same rungs."""

    def test_the_outcome_count_is_unchanged(self):
        rungs = SPECIMENS["trump cbp sanctuary airport"]
        row = _market_row(_market("q", rungs), now=NOW)
        assert row["outcome_count"] == len(rungs)

    def test_an_all_expired_ladder_is_left_exactly_as_it_was(self):
        """Every rung gone means the demotion is a no-op, not an emptying. A row
        that vanished would be a worse answer than a stale one — the same rule
        `event_rails` applies to a match nobody reported on."""
        rungs = [("Before Apr 1, 2026", 0.03), ("Before Jul 1, 2026", 0.015)]
        row = _market_row(_market("q", rungs), now=NOW)
        assert [o["name"] for o in row["top_outcomes"]] == [
            "Before Apr 1, 2026",
            "Before Jul 1, 2026",
        ]

    def test_an_undated_ladder_is_untouched(self):
        """Most of the page. A market with no dates in any rung must sort exactly
        as it did, or this change is a rewrite of /politics rather than a fix."""
        rungs = [("Gavin Newsom", 0.24), ("Kamala Harris", 0.09), ("AOC", 0.08)]
        row = _market_row(_market("2028 Democratic nominee?", rungs), now=NOW)
        assert [o["name"] for o in row["top_outcomes"]] == [
            "Gavin Newsom",
            "Kamala Harris",
            "AOC",
        ]

    def test_a_past_dated_rung_that_is_the_answer_keeps_the_headline(self):
        """`EXPIRED_RUNG_MAX_PROBABILITY`'s clause, inherited rather than
        re-derived. A past-dated rung priced at or above it already resolved YES
        — it is the ladder's ANSWER, and demoting it would hide the winner
        (UX-P005's defect class)."""
        answer = EXPIRED_RUNG_MAX_PROBABILITY + 0.4
        rungs = [("Before Apr 1, 2026", answer), ("Before Jan 1, 2027", 0.05)]
        headline, _ = _headline(rungs, NOW)
        assert headline == "Before Apr 1, 2026"


class TestTheInvariantHoldsAtEveryClock:
    """🔴 THE SWEEP. "These two rows look right today" is a fact about one day.

    48 anchors across two years, each derived by offset (gotcha #44), each
    checked against the SHIPPED `outcome_deadline_expired` rather than against a
    remembered expectation — so the assertion cannot drift away from the parser
    it is about.
    """

    @pytest.mark.parametrize("specimen", sorted(SPECIMENS))
    def test_the_headline_can_always_still_happen(self, specimen):
        rungs = SPECIMENS[specimen]
        for anchor in CLOCK_ANCHORS:
            live = [n for n, _ in rungs if _live(n, anchor)]
            headline, _ = _headline(rungs, anchor)
            if not live:
                continue  # nothing can happen; see the all-expired test above
            assert headline in live, (
                f"{specimen!r} at {anchor.date()} headlines {headline!r}, whose "
                f"deadline has passed, while {live} could still happen"
            )

    @pytest.mark.parametrize("specimen", sorted(SPECIMENS))
    def test_the_headline_is_the_best_priced_live_rung(self, specimen):
        """Not merely live — the LEADER among the live. Demotion must not
        reorder the rungs that survive it."""
        rungs = SPECIMENS[specimen]
        for anchor in CLOCK_ANCHORS:
            live = [(n, p) for n, p in rungs if _live(n, anchor)]
            if not live:
                continue
            headline, _ = _headline(rungs, anchor)
            assert headline == max(live, key=lambda r: r[1])[0]

    def test_the_sweep_actually_exercises_both_states(self):
        """A sweep on which every anchor took the same branch would pass while
        asserting nothing (gotcha #53 in its sweep-shaped form)."""
        rungs = SPECIMENS["nick adams ambassador"]
        seen = {
            len([n for n, _ in rungs if _live(n, anchor)]) for anchor in CLOCK_ANCHORS
        }
        assert len(seen) > 1, (
            f"every anchor saw the same number of live rungs ({seen}) — the "
            "anchors do not straddle any of this ladder's deadlines"
        )
        assert 0 in seen, "no anchor reaches the all-expired state"
        assert len(rungs) in seen, "no anchor sits before every deadline"


class TestTheClockIsTheCallersToState:
    """`now` is required, and that is the guard against a per-row clock."""

    def test_market_row_will_not_read_the_clock_for_you(self):
        with pytest.raises(TypeError):
            _market_row(_market("q", [("Before Jan 1, 2027", 0.5)]))

    def test_two_rows_on_one_page_are_judged_at_one_instant(self):
        """`_cross_source_row_fn` binds `now` once and returns the builder, so
        every row on a response answers the same instant. A per-row
        `datetime.now()` would let two rungs of one ladder be judged against two
        clocks across a midnight boundary."""
        import inspect

        from app.routes.politics import _cross_source_row_fn

        assert list(inspect.signature(_cross_source_row_fn).parameters) == ["now"]
        built = _cross_source_row_fn(NOW)
        assert list(inspect.signature(built).parameters) == ["market"]
