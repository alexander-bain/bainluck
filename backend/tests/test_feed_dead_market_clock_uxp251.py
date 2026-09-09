"""UX-P251 — THE FEED ASKED THE WRONG ROW WHAT TIME IT WAS.

═══ WHAT ALEX READ ═══

    "the wedding was like July 1st"

Discover card, 2026-09-01, scored 88 and near the top of the page:

    New favorite: No (64%)
    Who will Taylor Swift's bridesmaids be?
      Gigi Hadid          0%
      Abigail Anderson    0%
      Brittany Mahomes    0%

Market ``12194657``. Every one of its twelve outcomes was last touched on
**2026-07-04** — fifty-nine days before that page was served — and their opening
probabilities were 27%-68%, so those zeros are not a market with no opinion.
They are the residue of a question that has been answered.

═══ WHY EVERY EXISTING GATE PASSED IT ═══

The runtime oracle already has four staleness blockers, and all four are driven
by one line:

    updated_at = _utc(market.updated_at)
    days_stale = (now - updated_at).total_seconds() / 86400

``futures_markets.updated_at`` carries ``onupdate=func.now()``. It is a
**touch-stamp on the PARENT row**, rewritten by any write to the market — a
volume refresh, a hook regeneration, a category re-label. For this market it
read ``2026-09-01 12:50``, so ``days_stale`` was ~0 and every staleness blocker
was disarmed.

The prices live on the CHILDREN. Nothing in the gate ever looked at them.

The price-shaped gates could not cover for it either: this is a Polymarket
group whose Yes/No pair sits at 0.645/0.355, so ``locked_market`` (leader ≥
0.97) and ``all_outcomes_settled`` (every probability extreme) both correctly
declined to fire. **A dead market with an ambiguous headline number is exactly
the case where the clock is the only witness, and it was the one witness nobody
called.**

═══ THE GENERAL CLAUSE ═══

    🔴 A PARENT ROW'S TIMESTAMP IS NOT EVIDENCE ABOUT ITS CHILDREN. When the
       thing being judged lives on the children, ask the children. An
       ``onupdate`` column answers "did anything about this row change", which
       is a different question from the one every caller of it was asking.

═══ WHAT THIS SHIPS ═══

One new blocker, ``prices_stopped``, with **its own threshold of 14 days**. The
four parent-row blockers are not touched, so the change is purely additive:
nothing that is blocked today becomes visible today, and #2512 — that the parent
clock ALSO wrongly suppresses 897 markets whose prices are fresh — stays open
and stays somebody else's queue.

🔴 **VERSION ONE OF THIS SHIP DID FOLD THE TWO CLOCKS TOGETHER** and ran the
existing blockers on the older stamp at their own 2 days. Every gate was green
— 19 targeted tests, 5,489 frontend, all four CI backend shards, a battery that
killed 10 of 11 mutants. **A census by market tier caught it before merge:**

    tier 3: 17 of 17 admitted markets blocked — 100%
    tier 4:  6 of 7                          —  86%

``NFC East Division Winner``, the Heisman, ``NHL Pacific Division Winner``, the
fantasy rookie markets — **season futures priced four days ago, on the eve of
the NFL season.** A low-liquidity season future does not reprice daily, and the
parent-row clock had been accidentally protecting every one of them. Two clocks
measuring different things must not share a constant. `TestTheSeasonFuturesShelf`
below is that shelf, kept as the regression case.

The threshold sits in a measured gap, not at a guess. Over the 3,409 markets the
parent clock admits: ``>2d 601 · >7d 137 · >14d 107 · >21d 107 · >30d 103 ·
>45d 67``. Flat from 14 to 30 — almost nothing is frozen between a fortnight and
a month.

The top ten outcomes are NOT a safe proxy for "the prices", and that is measured
too: 207 of the 29,658 carry a tail outcome more than a day fresher than
anything in their top ten. So the stamp is taken over ALL outcomes.

🔴 **VERSION TWO THEN ASKED THE WRONG CHILD COLUMN.** It read
``FuturesOutcome.last_updated``, which the model defines in as many words as a
*TOUCH-STAMP … written unconditionally by every poll*. CERT-688 refuted it with
one exact-head probe — ``price_changed_at`` 59 days old, ``last_updated`` three
minutes old, ``eligible=True``, no blockers — so **an actively polled market
whose probability froze two months ago still reached the feed.** The same
general clause, one level down: the column that gets written on every visit is
not evidence about the value it sits next to.

Version three read ``price_changed_at`` (#2024) with ``last_updated`` behind it,
and carried both columns per outcome into the feed's projection.

🔴 **VERSION FOUR — THIS ONE — TAKES THE STAMP FROM THE CARRIER MASTER ALREADY
BUILT, AND THAT IS THE WHOLE OF THE CHANGE.** While this ship sat unmerged,
CERT-949 landed ``price_polled_at``: ``MAX(outcome.last_updated)``, folded once
per market at snapshot BUILD time by ``futures_market_snapshot.to_plain``. It
exists because that module measured, and REFUSED, exactly what version three
was doing — carrying a per-outcome timestamp on the wire cost **+12%** of a
size-capped shared Redis artifact (2,928,973 B → 3,289,739 B) for one value
repeated across up to 193 outcomes per market.

Version three would also have been a live incident on the cached path.
``last_updated`` is ``OUTCOME_LOAD_ONLY_EXTRA`` — loaded, deliberately NOT on
the wire — so reading it off an outcome rebuilt by ``from_plain`` is an
``AttributeError`` inside the per-item serializer, which empties the WHOLE
futures pool rather than dropping one card (gotcha #42). ``_score_futures``
serves every market through ``from_plain``.

**Dropping the ``price_changed_at`` arm costs nothing that can be measured
today, and version three's own census is the evidence:**

    blocked on last_updated alone   9,457
    blocked on the coalesce         9,457
    NEWLY blocked                       0
    clock value actually changed    4,495

Zero. The column is populated forward from 2026-08-20 and holds 3% of rows, so
it cannot yet cross a fourteen-day line. CERT-688's finding — an actively polled
market whose price froze two months ago — is REAL and becomes load-bearing as
coverage matures; it is deferred to its own issue with the derived-column design
that answers it within the measured budget (``price_moved_at`` as a second
``DERIVED_MARKET_COLUMNS`` entry, one datetime per market rather than per
outcome). See `TestTheMovementStampIsDeferredNotForgotten`.

So this ship adds NO column, NO wire growth and NO projection change. It adds one
blocker and reads a value that is already on the row.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _market_runtime_filter_trace
from app.utils.futures_market_snapshot import price_poll_stamp
from app.utils.market_staleness import (
    PRICES_STOPPED_DAYS,
    prices_have_stopped,
)

NOW = datetime(2026, 9, 1, 12, 50, tzinfo=timezone.utc)

# The real row, to the day. `updated_at` is when the poller last touched the
# PARENT; the outcomes are when the prices last moved.
BRIDESMAIDS_PARENT_TOUCHED = NOW - timedelta(minutes=3)
BRIDESMAIDS_PRICES_FROZE = NOW - timedelta(days=59)


def _outcome(name, probability, last_updated, *, change=None, opening=None):
    """One outcome, in the scoring loop's dict shape."""
    return {
        "name": name,
        "probability": probability,
        "probability_change_24h": change,
        "opening_probability": opening,
        "rank": None,
        "rank_change_24h": None,
        "last_updated": last_updated,
    }


def _stamp(outcomes):
    """The price clock, taken the way production takes it.

    `price_poll_stamp` is the ONE reader of this value on both feed paths, so
    these tests take it from there rather than recomputing a max of their own: a
    change that breaks the accessor has to break these tests too, which a local
    `max(...)` would quietly survive.

    The dicts are re-shaped into the ORM/snapshot shape the accessor actually
    receives. That is not a convenience — the scoring loop's dict form never
    reaches it in production, because `price_poll_stamp` is handed the MARKET,
    and a test that fed it dicts would be pinning an interface nothing calls.
    """
    return price_poll_stamp(
        SimpleNamespace(outcomes=[SimpleNamespace(**o) for o in outcomes])
    )


def _market(*, updated_at, resolution_date=None, name="Test Market", category=None):
    return SimpleNamespace(
        status="open",
        updated_at=updated_at,
        resolution_date=resolution_date,
        commence_time=None,
        name=name,
        event_id=None,
        llm_sport_category=category,
    )


def _bridesmaids():
    """Market 12194657 as production served it on 2026-09-01."""
    names_and_openings = [
        ("Gigi Hadid", 0.0035, 0.525),
        ("Ashley Avignone", 0.0005, 0.650),
        ("Este Haim", 0.0005, 0.440),
        ("Sabrina Carpenter", 0.0005, 0.290),
        ("Blake Lively", 0.0005, 0.275),
        ("Cara Delevingne", 0.0005, 0.345),
        ("Selena Gomez", 0.0005, 0.650),
        ("Zoë Kravitz", 0.0005, 0.500),
        ("Abigail Anderson", 0.0005, 0.680),
        ("Brittany Mahomes", 0.0005, 0.325),
    ]
    outcomes = [
        # The Yes/No pair is what defeats every price-shaped gate: it is neither
        # extreme nor locked, so the card keeps a plausible-looking headline.
        _outcome("No", 0.645, NOW - timedelta(days=100), opening=0.595),
        _outcome("Yes", 0.355, NOW - timedelta(days=100), opening=0.405),
    ] + [
        _outcome(n, p, BRIDESMAIDS_PRICES_FROZE, opening=o)
        for n, p, o in names_and_openings
    ]
    market = _market(
        updated_at=BRIDESMAIDS_PARENT_TOUCHED,
        # 2027-06-30 — ten months away, so no date gate fires either.
        resolution_date=NOW + timedelta(days=302),
        name="Who will Taylor Swift's bridesmaids be?",
        category="entertainment",
    )
    return market, outcomes


class TestTheCardAlexRead:
    def test_the_bridesmaids_card_does_not_reach_the_feed(self):
        market, outcomes = _bridesmaids()
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "No",
            0.645,
            NOW,
            sport_category="entertainment",
            newest_outcome_at=_stamp(outcomes),
        )
        assert not trace["eligible"], (
            "The wedding was two months ago and every price froze 59 days "
            "before this page was served. This card scored 88 on production."
        )
        assert "prices_stopped" in trace["blockers"]

    def test_and_the_PARENT_row_is_why_it_used_to_pass(self):
        """The defect, isolated: same market, same now, parent clock only.

        This is the arm that must stay red-if-reverted. If the oracle goes back
        to reading `market.updated_at`, `newest_outcome_at` stops mattering and
        this assertion is what says so.
        """
        market, outcomes = _bridesmaids()
        # Told (falsely) that the prices are as fresh as the parent row — which
        # is exactly what the old code assumed — the market sails through.
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "No",
            0.645,
            NOW,
            sport_category="entertainment",
            newest_outcome_at=BRIDESMAIDS_PARENT_TOUCHED,
        )
        assert trace["eligible"], (
            "If this is already blocked on the parent clock alone then the "
            "bridesmaids case proves nothing about the outcome clock and the "
            "test above is measuring some other gate."
        )

    def test_no_price_shaped_gate_could_have_caught_it(self):
        """Why the fix had to be the clock and not another threshold."""
        _, outcomes = _bridesmaids()
        probs = [o["probability"] for o in outcomes]
        leader = max(probs)
        assert leader < 0.97, "would have been caught by locked_market"
        assert not all(
            p < 0.05 or p > 0.95 for p in probs
        ), "would have been caught by all_outcomes_settled"
        assert not all(
            p < 0.001 for p in probs
        ), "would have been caught by all_outcomes_zero"
        assert leader > 0.03, "would have been caught by near_zero_binary"


class TestTheClockItself:
    """`prices_have_stopped` — its own question, its own number."""

    def test_the_threshold_is_a_fortnight_not_the_parent_clock_s_two_days(self):
        # 🔴 THE NUMBER IS THE WHOLE FINDING. See the second version note in
        # `TestTheSeasonFuturesShelf` below.
        assert PRICES_STOPPED_DAYS == 14

    def test_a_boundary_not_a_slope(self):
        assert prices_have_stopped(NOW - timedelta(days=14), NOW) is False
        assert prices_have_stopped(NOW - timedelta(days=14, seconds=1), NOW) is True

    def test_a_missing_stamp_is_NO_EVIDENCE_not_death(self):
        # A writer that never sets the column must not take its whole source
        # dark. `None` falls through to the parent-row rules, untouched.
        assert prices_have_stopped(None, NOW) is False

    def test_naive_datetimes_are_read_as_utc(self):
        # Postgres hands these back tz-aware, but the ORM fixtures and some
        # older rows do not, and a naive/aware comparison raises TypeError at
        # request time rather than in any test.
        assert prices_have_stopped(datetime(2026, 7, 4, 18, 16), NOW) is True

    def test_the_parent_row_clock_is_NOT_TOUCHED_by_this_ship(self):
        """The 897 question is closed by construction, not by a promise.

        The first version folded both clocks together and had to argue that it
        was not also admitting the 897 markets the parent clock wrongly
        suppresses. A separate blocker makes the change purely ADDITIVE: the
        four parent-clock blockers read exactly what they read before, so
        nothing that is blocked today can become visible today.
        """
        import inspect

        from app.routes import feed as feed_module

        src = inspect.getsource(feed_module._market_runtime_filter_trace)
        assert "updated_at = _utc(market.updated_at)" in src, (
            "the parent-row staleness rules must keep reading the parent row; "
            "folding the price clock into them deletes the season-futures shelf"
        )

    def test_the_stamp_reads_EVERY_outcome_not_the_top_ten(self):
        # Measured on production: 207 of 29,658 candidate markets carry a tail
        # outcome more than a day fresher than anything in their top ten. A
        # top-ten proxy would call all 207 of them dead. `_price_polled_at`
        # folds over the market's whole outcome list, so the proxy never exists.
        stale = [
            SimpleNamespace(
                last_updated=NOW - timedelta(days=40), current_probability=0.9
            )
            for _ in range(10)
        ]
        fresh_tail = SimpleNamespace(
            last_updated=NOW - timedelta(hours=2), current_probability=0.001
        )
        market = SimpleNamespace(outcomes=stale + [fresh_tail])
        assert price_poll_stamp(market) == NOW - timedelta(hours=2)

    def test_no_outcomes_is_None_not_now(self):
        assert price_poll_stamp(SimpleNamespace(outcomes=[])) is None
        assert price_poll_stamp(SimpleNamespace(outcomes=None)) is None
        assert (
            price_poll_stamp(SimpleNamespace(outcomes=[SimpleNamespace(last_updated=None)]))
            is None
        )

    @pytest.mark.parametrize(
        "not_a_stamp", ["2026-07-04", 1751600000, object(), SimpleNamespace()]
    )
    def test_a_value_that_is_not_a_DATETIME_is_no_evidence_and_never_raises(
        self, not_a_stamp
    ):
        """🔴 THE ONE MUTANT THAT SURVIVED THE BATTERY, NOW PINNED.

        `_as_utc` opens with an `isinstance(value, datetime)` check, and
        replacing it with `value is None` left all 137 tests green — so the
        guard was load-bearing and unheld. Nothing in this file fed the clock a
        non-datetime any more: the tests that used to (`newest_outcome_stamp`
        with unreadable shapes) went out with version three's helper.

        The guard has to stay because a bad value here does not fail loudly. A
        string reaches `value.tzinfo` (`AttributeError`); two mocks reach `>`
        (`TypeError: '>' not supported`). Both land inside `_score_futures`'s
        per-market `try/except` (gotcha #42), so they are caught, logged at
        WARNING, and the card silently disappears — this ship's own failure
        class, arriving through the fix for it. The column is
        `DateTime(timezone=True)`; a non-datetime is never a legitimate stamp,
        and reading it as "no evidence" keeps the card and defers to the
        parent-row rules.
        """
        assert prices_have_stopped(not_a_stamp, NOW) is False

    def test_a_missing_stamp_must_not_read_as_death(self):
        # "No evidence" and "the prices stopped" are different answers, and only
        # one of them removes a card. If `None` ever started blocking, every
        # market whose writer does not set the column would go dark at once.
        assert prices_have_stopped(price_poll_stamp(SimpleNamespace(outcomes=[])), NOW) is False


class TestTheTwoCarrierShapes:
    """🔴 THE ONE THING THIS VERSION CHANGED, SO IT IS THE THING MOST TESTED.

    The same value arrives by two routes and the gate must not care which:

    * ``_score_futures`` serves markets through ``from_plain``, which carries
      ``price_polled_at`` ALREADY FOLDED on the row — and whose outcomes do NOT
      carry ``last_updated`` at all, because it is `OUTCOME_LOAD_ONLY_EXTRA`.
    * ``_score_sports_mode_futures`` runs a plain ORM query: no derived column
      anywhere, but `market_load_options()` projects ``last_updated`` onto the
      outcomes.

    Reading the folded value FIRST is what makes the rebuilt path work. A naive
    "always fold from the outcomes" would read `None` off every rebuilt market —
    the entire Discover futures pool — and `None` does not block, so the bug
    would be a silent no-op rather than a crash. That is the failure this class
    exists to make loud.
    """

    FOLDED = NOW - timedelta(days=30)
    FROM_OUTCOMES = NOW - timedelta(days=3)

    def test_a_rebuilt_snapshot_market_reads_its_FOLDED_value(self):
        market = SimpleNamespace(price_polled_at=self.FOLDED, outcomes=[])
        assert price_poll_stamp(market) == self.FOLDED

    def test_a_rebuilt_market_does_not_need_readable_outcomes(self):
        """The rebuilt path's outcomes genuinely lack the column, by design."""
        market = SimpleNamespace(
            price_polled_at=self.FOLDED,
            outcomes=[SimpleNamespace(name="Yes", current_probability=0.6)],
        )
        assert price_poll_stamp(market) == self.FOLDED

    def test_a_plain_ORM_market_folds_from_its_outcomes(self):
        market = SimpleNamespace(
            outcomes=[
                SimpleNamespace(last_updated=NOW - timedelta(days=9)),
                SimpleNamespace(last_updated=self.FROM_OUTCOMES),
            ]
        )
        assert price_poll_stamp(market) == self.FROM_OUTCOMES

    def test_the_folded_value_WINS_over_the_outcomes(self):
        """Not a preference — on the rebuilt path the outcomes are not evidence.

        If this ever inverted, a rebuilt market would read its own unprojected
        outcomes and every one of them would answer `None`.
        """
        market = SimpleNamespace(
            price_polled_at=self.FOLDED,
            outcomes=[SimpleNamespace(last_updated=self.FROM_OUTCOMES)],
        )
        assert price_poll_stamp(market) == self.FOLDED

    def test_a_folded_None_is_honoured_not_re_derived(self):
        """`to_plain` writes `None` for a market whose stamps are all NULL.

        `in`, not `or` / `.get(...) is not None`: a folded `None` is an ANSWER —
        "we looked, there is nothing" — and re-deriving it from outcomes that
        the wire format does not carry could only ever produce the same `None`
        by luck, while masking the day it does not.
        """
        market = SimpleNamespace(
            price_polled_at=None,
            outcomes=[SimpleNamespace(last_updated=self.FROM_OUTCOMES)],
        )
        assert price_poll_stamp(market) is None

    def test_an_OLDER_BUILD_snapshot_reads_unknown_and_never_raises(self):
        """Neither carrier present — a snapshot written before CERT-949.

        `__dict__.get`, never `getattr`, so this degrades to "we do not know"
        rather than to an `AttributeError` inside the per-item serializer, which
        `_score_futures` catches and turns into a silently vanished card
        (gotcha #42). `None` does not block, so an unknown market keeps its card
        and is judged by the parent-row rules alone.
        """
        market = SimpleNamespace(
            outcomes=[SimpleNamespace(name="Yes", current_probability=0.6)]
        )
        assert price_poll_stamp(market) is None
        assert prices_have_stopped(price_poll_stamp(market), NOW) is False

    def test_it_never_touches_an_attribute_that_could_LAZY_LOAD(self):
        """The rule the whole snapshot module is built on, pinned here too.

        A deferred SQLAlchemy attribute lazy-loads on access and raises
        `MissingGreenlet` on the async feed path. `__dict__` cannot trigger a
        load; `getattr` can. This asserts the mechanism rather than the outcome,
        because the outcome is indistinguishable from correct until production.
        """
        import inspect

        from app.utils import futures_market_snapshot as snap

        src = inspect.getsource(snap.price_poll_stamp)
        assert "getattr(" not in src, (
            "price_poll_stamp must read __dict__ only — a getattr here "
            "lazy-loads a deferred column and raises MissingGreenlet inside "
            "the per-item serializer, which empties the whole futures pool"
        )

    def test_the_orm_model_still_carries_the_column(self):
        """The tripwire, in the one place a `try/except` cannot swallow it.

        If `last_updated` is renamed or dropped, the fold returns `None` for
        every market, `None` does not block, and the feed silently goes back to
        trusting the parent row's touch-stamp. Nothing else in this file would
        go red. This fails CI instead.
        """
        from app.models.models import FuturesOutcome

        assert hasattr(FuturesOutcome, "last_updated"), (
            "the staleness clock reads FuturesOutcome.last_updated; without it "
            "price_poll_stamp returns None for every market and the feed "
            "silently goes back to trusting the parent row's touch-stamp"
        )


class TestTheMovementStampIsDeferredNotForgotten:
    """🔴 CERT-688's FINDING IS REAL. IT IS ALSO NOT REACHABLE TODAY.

    The cert refuted version two with one exact-head probe: a market whose
    ``price_changed_at`` was 59 days old and whose ``last_updated`` was three
    minutes old came back ``eligible`` with no blockers. An actively polled
    market whose probability froze two months ago reached the feed. That is this
    ship's own failure class, one column to the left, and nothing here disputes
    it.

    Version three answered it by carrying ``price_changed_at`` per outcome into
    the feed's projection. This version does not, for two reasons that are both
    measurements rather than opinions:

    1. ``futures_market_snapshot`` measured a per-outcome timestamp on the wire
       at **+12%** of a size-capped shared artifact and refused it. That refusal
       is not this ship's to overturn in passing.
    2. Version three's OWN production census says the arm changes nothing today:
       9,457 markets blocked with it, 9,457 without, **0 newly blocked**. The
       column is populated forward from 2026-08-20 and holds 3% of rows, so it
       cannot yet put anything on the far side of a fourteen-day line.

    So the honest split is: ship the half that changes what a reader sees, and
    file the half that becomes load-bearing later — with the design that answers
    it inside the budget, which is a second `DERIVED_MARKET_COLUMNS` entry
    (``price_moved_at`` = ``MAX(price_changed_at)``, one datetime per MARKET, the
    same shape and the same ~1/193 of the cost as ``price_polled_at``).

    These tests pin the deferral so it cannot rot into an omission: they assert
    the gap is still the gap that was measured, and they go RED the day the
    premise stops holding.
    """

    POLLED = NOW - timedelta(minutes=3)
    FROZE = NOW - timedelta(days=59)

    def test_the_gap_is_REAL_and_stated_not_papered_over(self):
        """The known hole, written as an executable sentence.

        A market polled three minutes ago whose price last MOVED 59 days ago is
        not blocked by this ship. Saying so in a passing test is the difference
        between a deferral and a silent omission — if someone later believes
        this case is covered, this is where they find out it is not.
        """
        outcomes = [
            _outcome("Yes", 0.645, self.POLLED, opening=0.595),
            _outcome("No", 0.355, self.POLLED, opening=0.405),
        ]
        assert prices_have_stopped(_stamp(outcomes), NOW) is False

    def test_the_specimen_this_ship_DOES_catch_is_the_common_shape(self):
        """And it is caught through the poll stamp alone, with no movement column.

        Market 12194657's twelve outcomes all read `price_changed_at IS NULL`,
        so version three caught it through its FALLBACK — the same value this
        version reads directly. The named case never needed the movement column.
        """
        _, outcomes = _bridesmaids()
        assert prices_have_stopped(_stamp(outcomes), NOW) is True

    def test_the_column_that_would_close_the_gap_still_exists(self):
        """The follow-up's premise. Red here means the deferral needs re-reading.

        If `price_changed_at` is ever dropped, the deferred design dies with it
        and the follow-up issue is describing a column that is not there.
        """
        from app.models.models import FuturesOutcome

        assert hasattr(FuturesOutcome, "price_changed_at"), (
            "the deferred movement-stamp design (#2024) reads "
            "FuturesOutcome.price_changed_at; without it the follow-up issue "
            "is proposing a fold over a column that no longer exists"
        )

    def test_the_wire_still_does_NOT_carry_a_per_outcome_timestamp(self):
        """The budget this ship declined to spend, pinned as a contract.

        `last_updated` is loaded and deliberately not carried; that asymmetry is
        the whole reason `price_polled_at` exists. If a later change puts a
        timestamp into `OUTCOME_COLUMNS`, the +12% measurement applies again and
        somebody should have to argue it rather than inherit it.
        """
        from app.utils import futures_market_snapshot as snap

        assert "last_updated" in snap.OUTCOME_LOAD_ONLY_EXTRA
        assert "last_updated" not in snap.OUTCOME_COLUMNS, (
            "a per-outcome timestamp on the wire is the +12% that "
            "futures_market_snapshot measured and refused"
        )
        assert "price_polled_at" in snap.DERIVED_MARKET_COLUMNS


class TestHealthySiblingsSurvive:
    """Gotcha #43 — assert BOTH directions or the guard only proves half a rule."""

    def test_a_live_market_whose_prices_moved_this_hour_still_surfaces(self):
        outcomes = [
            _outcome(
                "Yes", 0.62, NOW - timedelta(minutes=20), change=0.03, opening=0.4
            ),
            _outcome(
                "No", 0.38, NOW - timedelta(minutes=20), change=-0.03, opening=0.6
            ),
        ]
        market = _market(
            updated_at=NOW - timedelta(minutes=20),
            resolution_date=NOW + timedelta(days=30),
            name="Will the Fed cut in November?",
        )
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "Yes",
            0.62,
            NOW,
            newest_outcome_at=_stamp(outcomes),
        )
        assert trace["eligible"], trace["blockers"]

    def test_a_market_with_NO_outcome_stamps_falls_back_to_the_parent_row(self):
        """A source that does not stamp its rows must not go dark wholesale.

        `last_updated` has a server default and no `onupdate`, so a writer that
        never sets it would leave every row at insert time. Treating "no stamp"
        as "ancient" would empty the feed of that whole source; it falls back to
        the behaviour that shipped before this change.
        """
        outcomes = [
            _outcome("Yes", 0.62, None, change=0.03, opening=0.4),
            _outcome("No", 0.38, None, change=-0.03, opening=0.6),
        ]
        market = _market(
            updated_at=NOW - timedelta(minutes=20),
            resolution_date=NOW + timedelta(days=30),
        )
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "Yes",
            0.62,
            NOW,
            newest_outcome_at=_stamp(outcomes),
        )
        assert trace["eligible"], trace["blockers"]

    def test_a_stale_PARENT_row_still_decides_on_its_own_terms(self):
        """This ship is purely ADDITIVE to the parent-row rules — #2512 stands.

        Version one folded the two clocks together, which meant it had to argue
        that it was not also ADMITTING the 897 markets the parent clock wrongly
        suppresses (prices fresh, parent stamp stale). A separate blocker closes
        that question by construction instead of by argument: this market's
        prices moved twenty minutes ago, so `prices_stopped` must NOT fire, and
        whatever the parent-row rules then decide is exactly what they decided
        before this branch existed.

        #2512 — that the parent clock also wrongly suppresses — is still open
        and is still not this queue's to answer.
        """
        outcomes = [
            _outcome(
                "Yes", 0.62, NOW - timedelta(minutes=20), change=None, opening=0.4
            ),
            _outcome("No", 0.38, NOW - timedelta(minutes=20), change=None, opening=0.6),
        ]
        market = _market(
            updated_at=NOW - timedelta(days=9),
            resolution_date=NOW + timedelta(days=30),
        )
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "Yes",
            0.62,
            NOW,
            newest_outcome_at=_stamp(outcomes),
        )
        assert "prices_stopped" not in trace["blockers"], (
            "this market's prices moved 20 minutes ago; a fortnight-scale "
            "blocker has no business firing on it"
        )
        # …and the parent-row rule reaches its own verdict, untouched.
        assert "stale_no_movement" in trace["blockers"]


class TestBothFeedPathsUseTheSameClock:
    """Wiring guards. `/api/feed` and `?mode=sports` each had their OWN copy of
    the parent-row clock, so a fix to one is a half-swept fix.
    """

    def _src(self, name):
        import inspect

        from app.routes import feed as feed_module

        return inspect.getsource(getattr(feed_module, name))

    @pytest.mark.parametrize("func", ["_score_futures", "_score_sports_mode_futures"])
    def test_the_path_reads_the_price_clock(self, func):
        src = self._src(func)
        assert "price_poll_stamp(market)" in src, (
            f"{func} must derive its staleness from the price stamp; "
            "market.updated_at is a touch-stamp on the parent row"
        )

    @pytest.mark.parametrize("func", ["_score_futures", "_score_sports_mode_futures"])
    def test_the_path_owns_NO_projection_of_its_own(self, func):
        """Q480 / CERT-622's rule, which this ship had to be re-cut to obey.

        Version three added two `FuturesOutcome.*` columns to an inline copy of
        the projection in each of these functions — a copy master had since
        replaced with `_futures_feed_load_options()` precisely because two
        copies is the defect. This version needs no column at all, so the right
        assertion is the absence: if a `FuturesOutcome.` literal reappears here,
        somebody has re-opened the duplication CERT-622 closed.
        """
        src = self._src(func)
        assert "FuturesOutcome." not in src, (
            f"{func} must take its projection from _futures_feed_load_options(); "
            "an inline column list here is the Q480/CERT-622 defect returning"
        )

    def test_the_shared_projection_still_loads_the_column_the_fold_reads(self):
        """The load surface this ship depends on and does not own.

        `price_poll_stamp` folds `last_updated` on the ORM path. That column is
        projected by the SHARED factory, one level down — so the dependency is
        real, is not visible in either scorer's source, and would otherwise be
        pinned nowhere in this file.
        """
        from app.utils import futures_market_snapshot as snap

        assert "last_updated" in snap.OUTCOME_LOAD_ONLY_EXTRA, (
            "the sports-mode path folds outcome.last_updated; unprojected it "
            "lazy-loads per outcome and crashes the async route"
        )

    def test_the_oracle_REQUIRES_its_caller_to_state_the_price_clock(self):
        """No silent fallback: `newest_outcome_at` has no default.

        A defaulted `None` would mean a caller that forgot it quietly kept the
        old parent-row behaviour, which is the failure mode this whole file is
        about.
        """
        import inspect

        sig = inspect.signature(_market_runtime_filter_trace)
        param = sig.parameters["newest_outcome_at"]
        assert param.default is inspect.Parameter.empty
        assert param.kind is inspect.Parameter.KEYWORD_ONLY

    def test_the_helpers_are_importable_at_module_scope(self):
        # Gotcha #7: a local re-import shadows the module-level name and raises
        # UnboundLocalError at request time, not import time.
        from app.routes import feed as feed_module

        assert callable(feed_module._prices_have_stopped)
        assert callable(feed_module._price_poll_stamp)


class TestTheSeasonFuturesShelf:
    """🔴 THE SECOND VERSION OF THIS SHIP EXISTS BECAUSE OF THIS CLASS.

    Version one folded the prices' clock into ``market.updated_at`` and let the
    four existing staleness blockers run on the older of the two at their own
    **2 days**. Every gate was green: 19 targeted tests, 5,489 frontend, all
    four CI backend shards, and a battery that killed 10 of 11 mutants.

    **A census by market tier is what caught it, before merge and by one query:**

        tier 3: 17 of 17 admitted markets blocked — 100%
        tier 4:  6 of 7                          —  86%

    Those are not dead markets. They are the rows below: season futures priced
    four days ago, on the eve of the NFL season. A low-liquidity season future
    legitimately does not reprice daily, and the parent-row clock — the one this
    ship set out to discredit — had been accidentally protecting every one of
    them.

    Two clocks measuring different things must not share a constant. The whole
    reason ``prices_stopped`` is a separate blocker with its own number is this
    shelf, so the shelf is the regression case.
    """

    # Real names and real ages, from the production census on 2026-09-01.
    STILL_LIVE = [
        ("NFC East Division Winner", 4),
        ("NHL Pacific Division Winner", 4),
        ("Top Fantasy Rookie QB", 4),
        ("Biletnikoff Award Winner", 4),
        ("Doak Walker Award Winner", 4),
        ("MVP Winner?", 4),
        ("Pro Baseball Playoff Qualifiers", 14),
        ("College Football Heisman Trophy Winner", 14),
    ]
    REALLY_DEAD = [
        ("Ballon d'Or Winner 2026", 42),
        ("Who will Taylor Swift's bridesmaids be?", 59),
        ("Dublin-Central By-Election Winner", 101),
        ("Rookie of the Year Winner", 128),
        ("Most Improved Player Winner", 130),
        ("Clutch Player of the Year Winner", 133),
        ("Pro Basketball Playoff Qualifiers", 137),
    ]

    @pytest.mark.parametrize("name,age_days", STILL_LIVE)
    def test_a_season_future_that_prices_weekly_KEEPS_its_card(self, name, age_days):
        assert prices_have_stopped(NOW - timedelta(days=age_days), NOW) is False, (
            f"{name!r} last priced {age_days}d ago is a live season future; "
            "blocking it empties the whole tier-3/tier-4 shelf"
        )

    @pytest.mark.parametrize("name,age_days", REALLY_DEAD)
    def test_a_market_that_stopped_a_month_ago_LOSES_its_card(self, name, age_days):
        assert prices_have_stopped(NOW - timedelta(days=age_days), NOW) is True, (
            f"{name!r} last priced {age_days}d ago is over"
        )

    def test_the_two_populations_do_not_touch(self):
        """The threshold sits in a measured gap, not between two adjacent cases.

        Production, over the 3,409 markets the parent clock admits:
        >2d 601 · >7d 137 · >14d 107 · >21d 107 · >30d 103 · >45d 67.
        Flat from 14 to 30 — almost nothing is frozen between a fortnight and a
        month — so the threshold has real margin on both sides rather than
        splitting a continuum.
        """
        oldest_live = max(age for _, age in self.STILL_LIVE)
        youngest_dead = min(age for _, age in self.REALLY_DEAD)
        assert oldest_live <= PRICES_STOPPED_DAYS < youngest_dead
        assert youngest_dead - oldest_live >= 28, (
            "the observed gap between the live shelf and the dead one is four "
            "weeks; if it narrows, this threshold needs re-measuring rather "
            "than nudging"
        )

    def test_the_whole_card_survives_the_oracle_not_just_the_helper(self):
        """The shelf, through the real gate, not the pure function."""
        outcomes = [
            _outcome("Philadelphia Eagles", 0.42, NOW - timedelta(days=4), opening=0.38),
            _outcome("Dallas Cowboys", 0.31, NOW - timedelta(days=4), opening=0.34),
            _outcome("Washington Commanders", 0.19, NOW - timedelta(days=4), opening=0.20),
            _outcome("New York Giants", 0.08, NOW - timedelta(days=4), opening=0.08),
        ]
        market = _market(
            updated_at=NOW - timedelta(hours=3),
            resolution_date=NOW + timedelta(days=140),
            name="NFC East Division Winner",
            category="americanfootball",
        )
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "Philadelphia Eagles",
            0.42,
            NOW,
            sport_category="americanfootball",
            newest_outcome_at=_stamp(outcomes),
        )
        assert "prices_stopped" not in trace["blockers"]
        assert trace["eligible"], trace["blockers"]
