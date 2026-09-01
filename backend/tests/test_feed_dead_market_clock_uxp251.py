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

Version three prefers ``price_changed_at`` (#2024, the column maintained only
when a price actually moves) and keeps ``last_updated`` as the fallback, because
that column is NULLABLE, populated forward from 2026-08-20, and NULL on 97% of
rows — including all twelve of the named specimen's. The fallback is sound and
not merely convenient: a price cannot move after the poller last wrote the row,
so ``last_updated`` is a true UPPER bound, and an upper bound can only make a
market look fresher. Composition across all 37,967 open markets is unchanged —
9,457 blocked either way, **0 newly blocked**, 4,495 clocks made truer.
`TestAnActivelyPolledFrozenMarket` and `TestTheCoalesceChangesNoOneToday` below
are those two halves.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _market_runtime_filter_trace
from app.utils.market_staleness import (
    PRICES_STOPPED_DAYS,
    newest_outcome_stamp,
    prices_have_stopped,
)

NOW = datetime(2026, 9, 1, 12, 50, tzinfo=timezone.utc)

# The real row, to the day. `updated_at` is when the poller last touched the
# PARENT; the outcomes are when the prices last moved.
BRIDESMAIDS_PARENT_TOUCHED = NOW - timedelta(minutes=3)
BRIDESMAIDS_PRICES_FROZE = NOW - timedelta(days=59)


def _outcome(
    name, probability, last_updated, *, change=None, opening=None, price_changed_at=None
):
    """One outcome, in the scoring loop's dict shape.

    `price_changed_at` defaults to None because that is the production shape:
    the #2024 column is populated FORWARD from 2026-08-20 and 97% of outcome
    rows — including all twelve of the named specimen's — are still NULL.
    """
    return {
        "name": name,
        "probability": probability,
        "probability_change_24h": change,
        "opening_probability": opening,
        "rank": None,
        "rank_change_24h": None,
        "price_changed_at": price_changed_at,
        "last_updated": last_updated,
    }


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
            newest_outcome_at=newest_outcome_stamp(outcomes),
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

    def test_newest_outcome_stamp_reads_EVERY_outcome_not_the_top_ten(self):
        # Measured on production: 207 of 29,658 candidate markets carry a tail
        # outcome more than a day fresher than anything in their top ten. A
        # top-ten proxy would call all 207 of them dead.
        stale = [
            SimpleNamespace(
                last_updated=NOW - timedelta(days=40), current_probability=0.9
            )
            for _ in range(10)
        ]
        fresh_tail = SimpleNamespace(
            last_updated=NOW - timedelta(hours=2), current_probability=0.001
        )
        assert newest_outcome_stamp(stale + [fresh_tail]) == NOW - timedelta(hours=2)

    def test_no_outcomes_is_None_not_now(self):
        assert newest_outcome_stamp([]) is None
        assert newest_outcome_stamp([SimpleNamespace(last_updated=None)]) is None

    def test_it_reads_BOTH_outcome_shapes(self):
        # The feed carries an outcome as an ORM row AND as the scoring loop's
        # plain dict, and both reach this helper.
        stamp = NOW - timedelta(days=3)
        assert newest_outcome_stamp([SimpleNamespace(last_updated=stamp)]) == stamp
        assert newest_outcome_stamp([{"last_updated": stamp}]) == stamp

    def test_an_unreadable_shape_is_no_evidence_and_NEVER_raises(self):
        """🔴 THIS CLAUSE IS THE REVERSE OF WHAT IT SAID AN HOUR AGO.

        The helper first RAISED on a shape it could not read, arguing that a
        silent ``None`` would disarm the gate. Mutant D came back SURVIVE, so a
        test was added to pin the raise — and then the full backend suite failed
        **32 tests across six files** with:

            Feed: skipping futures market 1 — scoring error:
            cannot read last_updated from _Outcome

        That is the refutation, and it is not about fixtures. `_score_futures`
        wraps every market in `try/except` (gotcha #42 — one bad item must never
        wipe a scoring pass), so **a raise in here is not loud. It is caught,
        logged at WARNING, and the card silently disappears.** The strict version
        converted a shape mismatch into invisible card loss, which is worse than
        the parent-clock fallback and is this ship's own failure class.

        The danger was real; the remedy was in a place that swallows it. So the
        tripwire moved to the test below, where nothing can catch it.
        """
        assert newest_outcome_stamp([object()]) is None
        assert newest_outcome_stamp([{"name": "Yes", "probability": 0.6}]) is None
        assert newest_outcome_stamp([{"last_updated": None}]) is None

        # A value that is not a datetime is not a stamp. The seeded route
        # fixtures hand this helper `MagicMock`s, and comparing two of them
        # raises `TypeError: '>' not supported` — inside the same swallowing
        # try/except, so it too showed up as vanished cards rather than as a
        # failure. The column is `DateTime(timezone=True)`; a non-datetime is
        # never a legitimate stamp.
        assert newest_outcome_stamp([SimpleNamespace(last_updated="2026-07-04")]) is None
        assert newest_outcome_stamp([SimpleNamespace(last_updated=object())]) is None
        # …and two unreadable stamps do not blow up comparing themselves.
        assert (
            newest_outcome_stamp(
                [SimpleNamespace(last_updated=object()), SimpleNamespace(last_updated=object())]
            )
            is None
        )

        # And "no evidence" must not read as death — otherwise the swallow
        # above becomes a silent suppression instead of a silent admission.
        assert prices_have_stopped(newest_outcome_stamp([object()]), NOW) is False

    def test_the_orm_model_still_carries_the_columns(self):
        """The tripwire, in the one place a `try/except` cannot swallow it.

        If either column is ever renamed or dropped, `newest_outcome_stamp`
        degrades silently — to the parent-row clock if `last_updated` goes, or
        back to the touch-stamp CERT-688 refuted if `price_changed_at` goes.
        Nothing else in this file would go red. This fails CI instead.
        """
        from app.models.models import FuturesOutcome

        assert hasattr(FuturesOutcome, "last_updated"), (
            "the staleness clock reads FuturesOutcome.last_updated; without it "
            "newest_outcome_stamp returns None for every market and the feed "
            "silently goes back to trusting the parent row's touch-stamp"
        )
        assert hasattr(FuturesOutcome, "price_changed_at"), (
            "the staleness clock PREFERS FuturesOutcome.price_changed_at "
            "(#2024); without it the gate falls all the way back to the poll "
            "touch-stamp and an actively polled frozen market reaches the feed"
        )


class TestAnActivelyPolledFrozenMarket:
    """🔴 CERT-688. THE THIRD VERSION OF THIS SHIP EXISTS BECAUSE OF THIS CLASS.

    Version two read `FuturesOutcome.last_updated` and nothing else. The cert
    refuted it with one exact-head probe: ``price_changed_at`` 59 days old,
    ``last_updated`` three minutes old, ``eligible=True``, no blockers. **An
    actively polled market whose probability froze two months ago still reached
    the feed** — this ship's own failure class, one column to the left.

    The model states the split in as many words: `last_updated` is a
    *TOUCH-STAMP … written unconditionally by every poll*, and `price_changed_at`
    is the #2024 column that answers when a price actually moved.

    Why this class fakes its clock instead of naming a production row: measured
    2026-09-01, `price_changed_at`'s oldest value is **2026-08-20**, so the
    column carries twelve days of history and no live row can yet be fourteen
    days frozen on it. The arm is correct now and becomes load-bearing as
    coverage matures. `TestTheCoalesceChangesNoOneToday` pins that.
    """

    FROZE = NOW - timedelta(days=59)
    POLLED = NOW - timedelta(minutes=3)

    def _polled_but_frozen(self):
        """The cert's probe, in the scoring loop's own shape: polled hard,
        priced never. The Yes/No pair is deliberately non-extreme so no
        price-shaped gate can take the credit for the block."""
        return [
            _outcome("Yes", 0.645, self.POLLED, opening=0.595, price_changed_at=self.FROZE),
            _outcome("No", 0.355, self.POLLED, opening=0.405, price_changed_at=self.FROZE),
        ]

    def test_the_clock_reads_the_MOVEMENT_stamp_not_the_poll_stamp(self):
        assert newest_outcome_stamp(self._polled_but_frozen()) == self.FROZE

    def test_and_so_the_market_is_blocked(self):
        assert prices_have_stopped(
            newest_outcome_stamp(self._polled_but_frozen()), NOW
        ) is True

    def test_the_cert_s_probe_through_the_REAL_ORACLE(self):
        """Not the helper — the gate, end to end, exactly as CERT-688 ran it."""
        outcomes = self._polled_but_frozen()
        market = _market(
            updated_at=self.POLLED,
            resolution_date=NOW + timedelta(days=302),
            name="Who will Taylor Swift's bridesmaids be?",
            category="entertainment",
        )
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "Yes",
            0.645,
            NOW,
            sport_category="entertainment",
            newest_outcome_at=newest_outcome_stamp(outcomes),
        )
        assert "prices_stopped" in trace["blockers"], (
            "CERT-688: an actively polled market whose price froze 59 days ago "
            "returned eligible=True with no blockers. That is the defect."
        )
        assert not trace["eligible"]

    def test_the_poll_stamp_alone_would_have_let_it_through(self):
        """The red-if-reverted arm. Without this, the test above is vacuous.

        Read on `last_updated` only — version two's reading — the same rows
        look three minutes old and every staleness blocker stands down.
        """
        assert prices_have_stopped(self.POLLED, NOW) is False

    def test_a_polled_market_that_IS_still_moving_keeps_its_card(self):
        """Gotcha #43 — the other direction, or this proves only half a rule."""
        outcomes = [
            SimpleNamespace(
                name="Yes",
                probability=0.62,
                price_changed_at=NOW - timedelta(hours=2),
                last_updated=self.POLLED,
            )
        ]
        assert prices_have_stopped(newest_outcome_stamp(outcomes), NOW) is False


class TestTheCoalesceChangesNoOneToday:
    """`price_changed_at` is preferred; `last_updated` is the bound behind it.

    The fallback is not convenience, it is soundness: **a price cannot have
    moved after the poller last wrote the row**, so `last_updated` is a true
    UPPER bound on the movement time. An upper bound can only make a market
    look FRESHER, which for a suppression gate is the safe direction — it can
    never over-block, which is the CERT-685 failure `TestTheSeasonFuturesShelf`
    guards.

    Measured across all 37,967 open markets on 2026-09-01:

        blocked on last_updated alone   9,457
        blocked on this coalesce        9,457
        NEWLY blocked                       0
        clock value actually changed    4,495
    """

    def test_a_null_movement_stamp_falls_back_to_the_poll_stamp(self):
        # 97% of production rows are exactly this shape, the named specimen's
        # twelve outcomes among them.
        stamp = NOW - timedelta(days=59)
        assert (
            newest_outcome_stamp(
                [SimpleNamespace(price_changed_at=None, last_updated=stamp)]
            )
            == stamp
        )

    def test_the_named_specimen_is_still_caught_through_the_fallback(self):
        """The ship itself. Market 12194657 carries NO `price_changed_at`.

        If the coalesce had dropped `last_updated`, the one card Alex read
        would have walked straight back onto the feed.
        """
        market, outcomes = _bridesmaids()
        for outcome in outcomes:
            assert outcome.get("price_changed_at") is None
        trace = _market_runtime_filter_trace(
            market,
            outcomes,
            "No",
            0.645,
            NOW,
            sport_category="entertainment",
            newest_outcome_at=newest_outcome_stamp(outcomes),
        )
        assert "prices_stopped" in trace["blockers"]

    def test_the_clock_can_only_move_BACKWARDS_never_forwards(self):
        """`price_changed_at` is written on the same statement as the price, so
        it is always <= `last_updated`. Preferring it can only age the clock —
        which is why the coalesce cannot UNBLOCK anything the old reading
        blocked, and why the 9,457 above is the same number twice.
        """
        polled = NOW - timedelta(minutes=5)
        for days in (0, 1, 4, 12, 40, 130):
            # Derived FROM the poll stamp, never independently of it — the
            # production invariant is `price_changed_at <= last_updated`
            # because the two are written by the same statement, and a fixture
            # that violates it is testing a row that cannot exist.
            moved = polled - timedelta(days=days)
            outcome = SimpleNamespace(price_changed_at=moved, last_updated=polled)
            assert newest_outcome_stamp([outcome]) <= polled

    def test_an_unreadable_movement_stamp_falls_through_to_the_poll_stamp(self):
        # Same swallowing `try/except` as every other shape case here: a bad
        # `price_changed_at` must degrade to the older reading, not to `None`,
        # or one malformed column silently disarms the gate for a whole source.
        stamp = NOW - timedelta(days=59)
        assert (
            newest_outcome_stamp(
                [SimpleNamespace(price_changed_at="2026-07-04", last_updated=stamp)]
            )
            == stamp
        )
        assert (
            newest_outcome_stamp([{"price_changed_at": object(), "last_updated": stamp}])
            == stamp
        )

    def test_it_reads_the_movement_stamp_in_BOTH_outcome_shapes(self):
        stamp = NOW - timedelta(days=20)
        fresh = NOW - timedelta(minutes=1)
        assert (
            newest_outcome_stamp(
                [SimpleNamespace(price_changed_at=stamp, last_updated=fresh)]
            )
            == stamp
        )
        assert (
            newest_outcome_stamp([{"price_changed_at": stamp, "last_updated": fresh}])
            == stamp
        )

    def test_neither_column_present_is_still_None(self):
        assert newest_outcome_stamp([object()]) is None
        assert (
            newest_outcome_stamp(
                [SimpleNamespace(price_changed_at=None, last_updated=None)]
            )
            is None
        )


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
            newest_outcome_at=newest_outcome_stamp(outcomes),
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
            newest_outcome_at=newest_outcome_stamp(outcomes),
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
            newest_outcome_at=newest_outcome_stamp(outcomes),
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
    def test_the_path_reads_the_outcome_clock(self, func):
        src = self._src(func)
        assert "_newest_outcome_stamp(" in src, (
            f"{func} must derive its staleness from the outcomes' own stamps; "
            "market.updated_at is a touch-stamp on the parent row"
        )

    @pytest.mark.parametrize("func", ["_score_futures", "_score_sports_mode_futures"])
    @pytest.mark.parametrize("column", ["price_changed_at", "last_updated"])
    def test_the_path_loads_both_clock_columns_from_the_database(self, func, column):
        # Gotcha: `load_only` without a column lazy-loads per outcome and
        # crashes the async route — the same trap `calibration_probability` and
        # `current_yes_bid` each carry a comment about a few lines above it.
        #
        # `price_changed_at` is the one that bites QUIETLY: it is NULL on 97% of
        # rows, so a missing load_only entry would look fine on most markets and
        # blow up only on the freshly-repriced ones.
        src = self._src(func)
        assert f"FuturesOutcome.{column}" in src, (
            f"{func} reads outcome.{column}, so it must be in the load_only "
            "list or the async route lazy-loads and crashes"
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

        assert callable(feed_module._newest_outcome_stamp)


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
            newest_outcome_at=newest_outcome_stamp(outcomes),
        )
        assert "prices_stopped" not in trace["blockers"]
        assert trace["eligible"], trace["blockers"]
