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

═══ WHAT THIS SHIPS, AND WHAT IT DELIBERATELY DOES NOT ═══

Measured on production, 2026-09-01, over the 29,658 markets that pass the
candidate SQL (``status='open'``, no ``event_id``, resolution date null or
future):

    645  parent says fresh (≤2d), prices older than 2 days   -> NEWLY BLOCKED
    897  parent says stale (>2d), prices fresher than 2 days  -> still blocked

The clock is wrong in BOTH directions. This queue ships only the first half:
the freshness clock becomes the OLDER of the two stamps, so a market must have
positive evidence of recency from its own prices, and **nothing that is blocked
today becomes visible today**. The 897 wrongly-suppressed markets are a
loosening — a feed-composition change nothing in this queue validates — and
they are named here with their number rather than absorbed silently.

The top ten outcomes are NOT a safe proxy for "the prices", and that is
measured too: 207 of the 29,658 carry a tail outcome more than a day fresher
than anything in their top ten. So the stamp is taken over ALL outcomes.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _market_runtime_filter_trace
from app.utils.market_staleness import freshness_clock, newest_outcome_stamp

NOW = datetime(2026, 9, 1, 12, 50, tzinfo=timezone.utc)

# The real row, to the day. `updated_at` is when the poller last touched the
# PARENT; the outcomes are when the prices last moved.
BRIDESMAIDS_PARENT_TOUCHED = NOW - timedelta(minutes=3)
BRIDESMAIDS_PRICES_FROZE = NOW - timedelta(days=59)


def _outcome(name, probability, last_updated, *, change=None, opening=None):
    return {
        "name": name,
        "probability": probability,
        "probability_change_24h": change,
        "opening_probability": opening,
        "rank": None,
        "rank_change_24h": None,
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
        assert "stale_no_movement" in trace["blockers"]

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
    """`freshness_clock` takes the OLDER stamp. Both arms, and both Nones."""

    def test_takes_the_older_of_the_two(self):
        parent = NOW - timedelta(hours=1)
        prices = NOW - timedelta(days=59)
        assert freshness_clock(parent, prices) == prices
        assert freshness_clock(prices, parent) == prices

    def test_a_missing_stamp_is_not_a_fresh_one(self):
        parent = NOW - timedelta(hours=1)
        assert freshness_clock(parent, None) == parent
        assert freshness_clock(None, parent) == parent
        assert freshness_clock(None, None) is None

    def test_naive_datetimes_are_read_as_utc(self):
        # Postgres hands these back tz-aware, but the ORM fixtures and some
        # older rows do not, and a naive/aware comparison raises TypeError at
        # request time rather than in any test.
        naive = datetime(2026, 7, 4, 18, 16)
        aware = datetime(2026, 7, 4, 18, 16, tzinfo=timezone.utc)
        assert freshness_clock(naive, None) == aware

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

    def test_the_LOOSENING_half_is_deliberately_not_shipped(self):
        """Parent stale + prices fresh stays BLOCKED. 897 rows on production.

        This is the half of the fix this queue does NOT ship, pinned so it reads
        as a decision rather than an oversight. Deleting this test is how the
        follow-up queue announces itself.
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
        assert not trace["eligible"]
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
        assert "newest_outcome_stamp(" in src, (
            f"{func} must derive its staleness from the outcomes' own stamps; "
            "market.updated_at is a touch-stamp on the parent row"
        )

    @pytest.mark.parametrize("func", ["_score_futures", "_score_sports_mode_futures"])
    def test_the_path_loads_last_updated_from_the_database(self, func):
        # Gotcha: `load_only` without this column lazy-loads per outcome and
        # crashes the async route — the same trap `calibration_probability` and
        # `current_yes_bid` each carry a comment about a few lines above it.
        src = self._src(func)
        assert "FuturesOutcome.last_updated" in src, (
            f"{func} reads outcome.last_updated, so it must be in the "
            "load_only list or the async route lazy-loads and crashes"
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
