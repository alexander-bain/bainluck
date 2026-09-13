"""#5809 — a card's price age may not be dated by a leg the reader cannot see.

## The defect, in one sentence

`price_observed_at` was `MAX(FuturesOutcome.last_updated)` over ALL of a
market's outcomes while the card prints only its top three, so one refreshed
outcome nobody can see vouched for three probabilities that were a day old.

## The measurement that filed it

Production `/api/feed?limit=40`, 2026-09-13 ~03:00Z, 38 cards carrying the key:
**1** served a stamp newer than EVERY price it displayed, and 3 served one more
than an hour newer than the oldest price displayed.

Specimen — market `108445`, "2028 Democratic presidential nominee", 48 outcomes
and 3 shown. Jon Ossoff 17% / Alexandria Ocasio-Cortez 16% / Gavin Newsom 14%
were all last observed `2026-09-12 03:51:10Z`, twenty-three hours old. The
served `price_observed_at` was `2026-09-13T02:50:25.442938Z` — byte-identical to
the observation time of Chris Van Hollen at 1%, who is not on the card.

The reader-visible failure is a SUPPRESSED disclosure, not a printed wrong
number, and that is why it is worth a file of its own: `PriceAgeMark` draws
nothing below thirty minutes, so the card computed ~0 and the mark went silent
on exactly the card it exists for. Reach: 890 of 26,971 open markets (3.3%)
carry a leader more than an hour behind their own market max; 503 by a day.

## What this file proves, and why each leg is here

1. **The specimen reproduces** — the production shape, rebuilt as rows, serves
   the invisible leg's stamp under the old rule and the displayed legs' under
   the new one. Without this leg the rest is a test of a story.
2. **The concern the old rule was defending still holds** — a dead fifth leg at
   123 days (the measurement in `_card_price_observed_at`'s own docstring) must
   not date a card whose displayed prices are current. That is preserved by the
   top-N filter, not by `MAX`, so it needs its own assertion: a fix that took
   `MIN` over ALL legs would pass leg 1 and fail here.
3. **It survives the carrier** — three carriers (build-path ORM rows, a
   `from_plain` rebuild, a `__slots__` row) must agree, or the defect moves to
   whichever path is not tested rather than being fixed.
4. **The two stamps did not get swapped** — `price_poll_stamp` still answers the
   market-wide question its own consumers (the dead-market clock,
   `newest_outcome_at`) ask. A "fix" that redefined it would empty cards.
5. **The leg count cannot drift** from the slice `feed.py` actually prints.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.routes import feed as feed_module
from app.utils import futures_market_snapshot as fms

UTC = timezone.utc

#: The specimen's real instants, to the second, from the production read above.
DISPLAYED_AT = datetime(2026, 9, 12, 3, 51, 10, tzinfo=UTC)
INVISIBLE_LEG_AT = datetime(2026, 9, 13, 2, 50, 25, 442938, tzinfo=UTC)


class _Outcome:
    """A duck-typed outcome row with a real instance dict.

    The folds read `__dict__` on purpose (gotcha #42 — `getattr` on a deferred
    mapped column lazy-loads and raises `MissingGreenlet` inside the per-item
    serializer, which empties the whole futures pool), so a fixture that is not
    dict-readable would test a code path production never takes.
    """

    def __init__(self, name: str, probability, last_updated):
        self.name = name
        self.current_probability = probability
        self.last_updated = last_updated


class _SlotsOutcome:
    """`tennis_population.OutcomeRow`'s shape: a slots row with NO stamp column.

    The compact projection LAT-P146 caches cannot hold `last_updated` at all,
    so the honest answer for such a row is "we do not know" — and the folds must
    reach that answer by degrading, never by raising.
    """

    __slots__ = ("name", "current_probability")

    def __init__(self, name: str, probability):
        self.name = name
        self.current_probability = probability


class _SlotsMarket:
    __slots__ = ("id", "outcomes")

    def __init__(self, market_id: int, outcomes):
        self.id = market_id
        self.outcomes = outcomes


class _DictMarket:
    """A market whose outcomes are reachable through its instance dict.

    This is the build-path carrier: a `load_only`-restricted ORM object, whose
    `outcomes` are hydrated and whose derived columns do not exist yet.
    """

    def __init__(self, outcomes):
        self.outcomes = outcomes


def _specimen_outcomes():
    """Market `108445`'s shape: three old displayed legs, 45 fresher hidden ones.

    Probabilities descend so the top-three-by-probability window is exactly the
    three the card prints, which is what the production card did.
    """
    displayed = [
        _Outcome("Jon Ossoff", 0.17, DISPLAYED_AT),
        _Outcome("Alexandria Ocasio-Cortez", 0.16, DISPLAYED_AT),
        _Outcome("Gavin Newsom", 0.14, DISPLAYED_AT),
    ]
    hidden = [
        _Outcome("Chris Van Hollen", 0.01, INVISIBLE_LEG_AT),
        *[_Outcome(f"Candidate {i}", 0.01, INVISIBLE_LEG_AT) for i in range(44)],
    ]
    return displayed + hidden


# ══════════════════════════════════════════════════════════════════════════
# 1. THE SPECIMEN REPRODUCES
# ══════════════════════════════════════════════════════════════════════════


class TestTheSpecimen:
    def test_the_old_rule_dated_the_card_by_a_leg_it_does_not_show(self):
        """The BEFORE, asserted rather than described (it is still shipped).

        `price_poll_stamp` keeps its `MAX` semantics for its own consumers, so
        this is not a frozen copy of deleted code — it is the live function,
        showing the value the card used to serve.
        """
        market = _DictMarket(_specimen_outcomes())

        assert fms.price_poll_stamp(market) == INVISIBLE_LEG_AT

    def test_the_new_rule_dates_it_by_the_prices_it_prints(self):
        market = _DictMarket(_specimen_outcomes())

        assert fms.top_price_stamp(market) == DISPLAYED_AT

    def test_the_served_string_is_the_displayed_age_and_carries_an_offset(self):
        """Through the route's own serializer, not just the fold beneath it.

        The offset is asserted because `Date.parse` reads an offsetless stamp as
        LOCAL time in the reader's browser, which would age a fresh price by the
        reader's own UTC offset — the whole mark, wrong, for everyone west of
        Greenwich.
        """
        market = _DictMarket(_specimen_outcomes())

        served = feed_module._card_price_observed_at(market)

        assert served == DISPLAYED_AT.isoformat()
        assert served.endswith("+00:00")

    def test_the_mark_would_have_been_SUPPRESSED_under_the_old_rule(self):
        """The reader-visible consequence, stated as a threshold not a vibe.

        `PriceAgeMark` draws only above thirty minutes. The point of the file is
        that the old value fell BELOW that bar while the displayed prices were a
        day above it, so the card drew nothing at all.
        """
        now = INVISIBLE_LEG_AT + timedelta(minutes=1)
        market = _DictMarket(_specimen_outcomes())

        old_age = now - fms.price_poll_stamp(market)
        new_age = now - fms.top_price_stamp(market)

        assert old_age < timedelta(minutes=30)
        assert new_age > timedelta(hours=23)


# ══════════════════════════════════════════════════════════════════════════
# 2. THE CONCERN THE OLD RULE WAS DEFENDING
# ══════════════════════════════════════════════════════════════════════════


class TestTheDeadLegIsStillExcluded:
    """`MIN` over ALL legs would pass every test above and break these.

    The `MAX` docstring cited a measured market whose fifth leg was 123 DAYS old
    while its leader was 50 minutes old. Narrowing the SET is what answers that,
    and a reviewer has to be able to see the difference between narrowing the set
    and inverting the rule.
    """

    def _card_with_a_dead_fifth_leg(self):
        fresh = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        return _DictMarket(
            [
                _Outcome("Leader", 0.40, fresh),
                _Outcome("Second", 0.30, fresh),
                _Outcome("Third", 0.20, fresh),
                _Outcome("Fourth", 0.09, fresh),
                _Outcome("Dead fifth", 0.01, fresh - timedelta(days=123)),
            ]
        )

    def test_a_dead_leg_outside_the_top_three_does_not_date_the_card(self):
        market = self._card_with_a_dead_fifth_leg()

        assert fms.top_price_stamp(market) == datetime(2026, 9, 13, 2, 0, tzinfo=UTC)

    def test_a_naive_min_over_all_legs_would_have_dated_it_123_days_old(self):
        """The mutant this class exists to kill, run explicitly.

        Without this, "take the oldest" reads as the whole fix and the top-N
        filter looks like an optimisation someone may later simplify away.
        """
        market = self._card_with_a_dead_fifth_leg()
        every_stamp = [o.last_updated for o in market.outcomes]

        assert min(every_stamp) != fms.top_price_stamp(market)

    def test_a_dead_leg_INSIDE_the_top_three_does_date_the_card(self):
        """The other direction, which is not symmetry — it is the point.

        If the reader can SEE a price we last observed 123 days ago, saying so is
        correct. The old rule hid exactly this.
        """
        fresh = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        dead = fresh - timedelta(days=123)
        market = _DictMarket(
            [
                _Outcome("Leader", 0.60, fresh),
                _Outcome("Second", 0.30, dead),
                _Outcome("Third", 0.10, fresh),
            ]
        )

        assert fms.top_price_stamp(market) == dead


# ══════════════════════════════════════════════════════════════════════════
# 3. THE FOLD'S OWN EDGES
# ══════════════════════════════════════════════════════════════════════════


class TestTheFold:
    def test_it_takes_the_oldest_of_the_three_not_the_first_it_meets(self):
        base = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        market = _DictMarket(
            [
                _Outcome("Leader", 0.50, base),
                _Outcome("Second", 0.30, base - timedelta(hours=9)),
                _Outcome("Third", 0.20, base - timedelta(hours=4)),
            ]
        )

        assert fms.top_price_stamp(market) == base - timedelta(hours=9)

    def test_the_window_is_by_PROBABILITY_not_by_list_order(self):
        """The rows do not arrive sorted on every path, so the fold sorts.

        Written because a fold that trusted arrival order would pass every test
        above — the specimen's rows happen to descend — and silently pick three
        arbitrary legs on the sports-mode path.
        """
        base = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        market = _DictMarket(
            [
                _Outcome("Tail", 0.01, base - timedelta(days=30)),
                _Outcome("Leader", 0.50, base),
                _Outcome("Second", 0.30, base),
                _Outcome("Third", 0.20, base),
            ]
        )

        assert fms.top_price_stamp(market) == base

    def test_an_unstamped_leg_is_ignored_not_treated_as_undatable(self):
        """This module's rule everywhere, and not a regression: `MAX` did it too.

        A leg that was never stamped is not evidence about the legs that were.
        """
        base = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        market = _DictMarket(
            [
                _Outcome("Leader", 0.50, None),
                _Outcome("Second", 0.30, base),
                _Outcome("Third", 0.20, base),
            ]
        )

        assert fms.top_price_stamp(market) == base

    def test_an_unreadable_probability_sorts_BELOW_every_readable_one(self):
        """So it can never displace a leg the reader actually sees.

        A `None` probability compared against a float raises in `sorted`; the
        fold coerces, and the direction of the coercion is the assertion.
        """
        base = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        market = _DictMarket(
            [
                _Outcome("Unpriced", None, base - timedelta(days=30)),
                _Outcome("Leader", 0.50, base),
                _Outcome("Second", 0.30, base),
                _Outcome("Third", 0.20, base),
            ]
        )

        assert fms.top_price_stamp(market) == base

    @pytest.mark.parametrize(
        "outcomes, why",
        [
            ([], "a market with no outcomes at all"),
            ([_Outcome("Only leg", 0.5, None)], "no leg carries a stamp"),
            ([_SlotsOutcome("Compact row", 0.5)], "the carrier has no such column"),
        ],
    )
    def test_unknown_is_None_and_never_an_exception(self, outcomes, why):
        """`None` is "we do not know", which every consumer reads as not-fresh.

        Never a raise: this runs inside the per-item serializer, where one
        exception drops the entire futures pool rather than one card (#42).
        """
        assert fms.top_price_stamp(_DictMarket(outcomes)) is None, why


# ══════════════════════════════════════════════════════════════════════════
# 4. IT SURVIVES THE CARRIER
# ══════════════════════════════════════════════════════════════════════════


class TestTheThreeCarriersAgree:
    """A card served from the shared artifact must date itself identically.

    The module's whole reason to exist: a value that is right on the build path
    and absent on the cached one is a DIFFERENT feed, not a slower one.
    """

    def _orm_specimen(self):
        from tests.test_my_stuff_price_freshness_cert949 import _orm_market

        market = _orm_market(58091, "2028 Democratic presidential nominee")
        probabilities = (0.17, 0.16, 0.14, 0.01)
        for outcome, probability in zip(market.outcomes, probabilities):
            outcome.current_probability = probability
            outcome.last_updated = (
                INVISIBLE_LEG_AT if probability == 0.01 else DISPLAYED_AT
            )
        return market

    def test_the_build_path_folds_from_its_hydrated_outcomes(self):
        assert fms.top_price_stamp(self._orm_specimen()) == DISPLAYED_AT

    def test_the_value_survives_the_wire(self):
        rebuilt = fms.from_plain(fms.to_plain([self._orm_specimen()]))[0]

        assert rebuilt.__dict__["top_price_observed_at"] == DISPLAYED_AT
        assert fms.top_price_stamp(rebuilt) == DISPLAYED_AT

    def test_the_rebuilt_market_agrees_with_the_one_it_was_built_from(self):
        """Stated as an equality between carriers, which is the actual contract.

        Two assertions against the same literal can both drift to the same wrong
        value; this one cannot pass unless the carriers agree.
        """
        direct = self._orm_specimen()
        rebuilt = fms.from_plain(fms.to_plain([self._orm_specimen()]))[0]

        assert fms.top_price_stamp(rebuilt) == fms.top_price_stamp(direct)

    def test_the_rebuilt_market_does_not_re_derive_from_stampless_outcomes(self):
        """`last_updated` is OUTCOME_LOAD_ONLY_EXTRA: loaded, never on the wire.

        So the rebuilt outcomes cannot answer this question and the folded row
        value must win. If the order of those two branches ever inverted, every
        cached card would read "we do not know".
        """
        rebuilt = fms.from_plain(fms.to_plain([self._orm_specimen()]))[0]

        assert fms._top_price_observed_at(rebuilt.__dict__["outcomes"]) is None
        assert fms.top_price_stamp(rebuilt) == DISPLAYED_AT

    def test_a_slots_row_degrades_instead_of_raising(self):
        """The third carrier (#5778): a compact row with no instance dict.

        It reached this module once and raised `AttributeError` through the fold
        — nine tennis tests, not a wrong number.
        """
        market = _SlotsMarket(1, [_SlotsOutcome("Compact", 0.5)])

        assert fms.top_price_stamp(market) is None

    def test_a_previous_schema_entry_is_never_read(self):
        """A v4 entry's market row is one value SHORT.

        Read under v5 it would tell every cached card that its price age is
        unknown while the build path knows it, so the reader's mark would blink
        with the cache rather than track the price.
        """
        stale = fms.to_plain([self._orm_specimen()])
        stale["v"] = 4

        assert fms.is_snapshot_payload(stale) is False
        assert fms.from_plain(stale) == []


# ══════════════════════════════════════════════════════════════════════════
# 5. THE TWO STAMPS DID NOT GET SWAPPED
# ══════════════════════════════════════════════════════════════════════════


class TestTheOtherConsumersKeptTheirAnswer:
    """`price_polled_at` is still `MAX` over ALL legs, and must be.

    The dead-market clock and `newest_outcome_at` ask "when did we last read
    this book". Giving them the displayed-legs `MIN` would age every market by
    its stalest shown leg and start culling live cards — a much larger defect
    than the one being fixed.
    """

    def test_price_poll_stamp_is_untouched(self):
        assert fms.price_poll_stamp(_DictMarket(_specimen_outcomes())) == (
            INVISIBLE_LEG_AT
        )

    def test_the_two_derived_columns_are_both_carried_and_distinct(self):
        market = _DictMarket(_specimen_outcomes())
        row = fms.to_plain([market])["rows"][0][0]
        values = dict(zip(fms.MARKET_ROW_COLUMNS, row))

        assert values["price_polled_at"] == INVISIBLE_LEG_AT
        assert values["top_price_observed_at"] == DISPLAYED_AT

    def _code_lines(self):
        return [
            line.strip()
            for line in inspect.getsource(feed_module).splitlines()
            if not line.lstrip().startswith("#")
        ]

    def test_the_dead_market_clock_still_reads_the_market_wide_stamp(self):
        """Asserted on the ROUTE's source, because the swap would be invisible.

        Both stamps are datetimes; handing the clock the wrong one changes which
        cards exist, not whether the code runs.

        Two call shapes, so the scan names both — the first draft matched only
        the inline one and read the other, which reaches the clock through a
        `newest_outcome_at` parameter, as a violation.
        """
        code = self._code_lines()
        inline = [ln for ln in code if "_prices_have_stopped(_" in ln]
        bound = [ln for ln in code if "newest_outcome_at=" in ln]

        assert inline, "the inline dead-market clock call moved or was renamed"
        assert bound, "the `newest_outcome_at` bindings moved or were renamed"
        for call in inline + bound:
            assert "_price_poll_stamp(" in call, (
                "the dead-market clock must keep the market-wide MAX; the "
                f"displayed-legs MIN would cull live cards: {call}"
            )

    def test_the_displayed_legs_stamp_has_exactly_ONE_consumer(self):
        """The other half: the new fold must not spread to the clock's callers.

        A scan that only checked the clock would pass if a later edit added a
        third consumer of the displayed-legs stamp somewhere else entirely.
        """
        callers = [ln for ln in self._code_lines() if "_top_price_stamp(" in ln]

        assert len(callers) == 1, (
            "the displayed-legs stamp answers ONE question — the age mark under "
            f"a card. Every other consumer wants the market-wide MAX: {callers}"
        )
        assert "_top_price_stamp(market)" in callers[0]
        assert "_top_price_stamp" in inspect.getsource(
            feed_module._card_price_observed_at
        )


# ══════════════════════════════════════════════════════════════════════════
# 6. THE LEG COUNT CANNOT DRIFT FROM WHAT THE CARD PRINTS
# ══════════════════════════════════════════════════════════════════════════


class TestTheLegCountTracksTheCard:
    def test_the_constant_matches_the_slice_the_serializers_print(self):
        """Both futures serializers slice `card_outcomes[:3]`.

        A fold over more legs than the card shows OVER-states the age; one over
        fewer UNDER-states it. #5809 is on record that both directions are
        equally a lie, so the number may not drift in either.
        """
        source = Path(inspect.getfile(feed_module)).read_text()
        slices = {
            line.strip()
            for line in source.splitlines()
            if "card_outcomes[:" in line and not line.lstrip().startswith("#")
        }

        assert slices, "the card slice moved — re-aim this scan before trusting it"
        expected = f"card_outcomes[:{fms.CARD_PRICE_AGE_LEG_COUNT}]"
        for sliced in slices:
            assert expected in sliced, (
                "the card prints a different number of legs than "
                "`CARD_PRICE_AGE_LEG_COUNT` folds over: "
                f"{sliced} vs {expected}"
            )

    def test_the_fold_actually_honours_the_constant(self):
        """So the scan above is not a pin on a number nothing reads.

        Built from the constant rather than from a literal 3: a fold hard-coded
        to three would pass the scan and ignore a later change to the constant.
        """
        base = datetime(2026, 9, 13, 2, 0, tzinfo=UTC)
        count = fms.CARD_PRICE_AGE_LEG_COUNT
        inside = [
            _Outcome(f"Shown {i}", 1.0 - i / 100, base - timedelta(hours=i))
            for i in range(count)
        ]
        just_outside = _Outcome("Hidden", 0.0, base - timedelta(days=365))

        market = _DictMarket([*inside, just_outside])

        assert fms.top_price_stamp(market) == base - timedelta(hours=count - 1)
