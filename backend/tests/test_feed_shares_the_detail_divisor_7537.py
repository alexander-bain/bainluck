"""#7537 feed half — a Discover card divides by the same legs the detail page does.

#7274 closed on one sentence: "the membership rule is SHARED, not the divisor ...
so the two surfaces cannot drift into two answers about which rungs are real."
#7537 adds a membership rule to `_format_market_detail`. A rule the page applies
and `feed.py` does not is #7274 reopening under a new name — which is why Codex
ruled on 2026-09-20 that "Feed/detail (and applicable category/timeline
consumers) must share eligibility".

WHAT A READER SAW, measured on the SERVED feed on 2026-09-20 (not on the market
population — live's census looked at page one, the top ~60 by score, and the
card pool is wider). Of the 115 futures cards `/api/feed` actually returned,
five carry a priced stale leg and three would print a different rounded leader
percent on card and page once the detail half lands. The worst is live's own
specimen, market 3971707 (*Super League Rugby Champion*), which IS served as a
card — `Leeds Rhinos`, Kalshi midpoint 0.3950:

    card  36.1%   page  30.2%   <- 5.9 points apart, already #7274, live today
    card  36.1%   page  39.5%   <- after the detail half alone
    card  39.5%   page  39.5%   <- with this fix

Eleven of its fourteen legs were last written 2026-09-06 at one microsecond
(a poll pass stamps every row it touches with one `now`); three were written
that day. Every row below is the row production served, copied from the named
market rather than invented, and every stamp is an OFFSET from the fixture's own
frozen instant (gotcha #44) so no assertion here can age out.

🔴 `TestTheCachedPathIsNotSilentlyInert` IS THE LOAD-BEARING CLASS. A rehydrated
snapshot leg does not carry `last_updated` at all, and `_as_utc` answers `None`
for a non-datetime instead of raising, so the obvious wiring is not a crash — it
is a filter that does nothing on the path nearly every card is served from,
while passing every ORM-row test in this file. That class fails if the stamp is
ever read off the raw column again.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import feed as feed_module
from app.routes.feed import (
    _drop_stale_observation_legs,
    _feed_display_scale,
)
from app.utils.feed_market_quality import classify_fabricated_book
from app.utils.futures_market_snapshot import outcome_observed_at

# The fixture's own instant. Every stamp below is an offset from it, so the
# suite reads the same on any clock (gotcha #44 — offset first, never branch).
NOW = datetime(2026, 9, 20, 14, 53, 14, 933824, tzinfo=timezone.utc)
FOSSIL = NOW - timedelta(days=14, hours=9, minutes=7)  # production 2026-09-06

# Market 3971707 as production served it on 2026-09-20, read from the row:
# (name, raw probability, yes_bid, yes_ask, observed). The three fresh legs are
# the three Kalshi was still quoting; the eleven at FOSSIL were all written at
# one microsecond by a single poll pass.
#
# The BOOK columns are carried because the card's divisor is not the board's
# sum: `_score_futures` runs the fabricated-book gate first, and on this market
# that gate removes exactly `Hull Kingston Rovers` (0.19/0.47) and
# `Wigan Warriors` (0.19/0.40) — 0.6250 of mass — which is what takes the 1.7200
# board down to the 1.0950 the card actually divided by (0.3950/1.0950 = 0.3607,
# the percent production printed). Deriving that by CALLING the gate rather than
# by subtracting it keeps this suite honest about the chain it inserts into.
SUPER_LEAGUE: tuple[tuple[str, float | None, float, float, datetime], ...] = (
    ("Leeds Rhinos", 0.3950, 0.3300, 0.4600, NOW),
    ("Hull Kingston Rovers", 0.3300, 0.1900, 0.4700, FOSSIL),
    ("Wigan Warriors", 0.2950, 0.1900, 0.4000, FOSSIL),
    ("St Helens", 0.1300, 0.0000, 0.9600, NOW),
    ("Wakefield Trinity", 0.1200, 0.0000, 0.1200, FOSSIL),
    ("Warrington Wolves", 0.1100, 0.0000, 0.9600, NOW),
    ("Hull FC", 0.0900, 0.0000, 0.0900, FOSSIL),
    ("Leigh Leopards", 0.0800, 0.0000, 0.0800, FOSSIL),
    ("Catalan Dragons", 0.0400, 0.0000, 0.0400, FOSSIL),
    ("Toulouse Olympique", 0.0300, 0.0000, 0.0300, FOSSIL),
    ("Huddersfield Giants", 0.0300, 0.0000, 0.0300, FOSSIL),
    ("York Knights", 0.0300, 0.0000, 0.0300, FOSSIL),
    ("Castleford Tigers", 0.0200, 0.0000, 0.0200, FOSSIL),
    ("Bradford Bulls", 0.0200, 0.0000, 0.0200, FOSSIL),
)


def orm_leg(idx, name, prob, bid, ask, observed):
    """A leg as a plain ORM query hands it over: `last_updated`, no derived value."""
    return SimpleNamespace(
        id=idx,
        name=name,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        last_updated=observed,
    )


def rehydrated_leg(idx, name, prob, bid, ask, observed):
    """A leg as `from_plain` rebuilds it: `price_observed_epoch`, NO `last_updated`.

    This is the shape the cached path serves, and the reason it is a separate
    constructor rather than a flag is that the absence is the whole point.
    """
    return SimpleNamespace(
        id=idx,
        name=name,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        price_observed_epoch=int(observed.timestamp()),
    )


def restamp(fn):
    """`SUPER_LEAGUE` with every observation instant replaced by `fn(index, old)`.

    The board's prices and books are the production ones in every case; only the
    stamp spread changes, which is the single variable these controls vary.
    """
    return tuple(
        (n, p, bid, ask, fn(i, observed))
        for i, (n, p, bid, ask, observed) in enumerate(SUPER_LEAGUE)
    )


def board(build=orm_leg, rows=SUPER_LEAGUE):
    return [build(i, *row) for i, row in enumerate(rows)]


def card_board(legs):
    """The legs `_score_futures` reaches the divisor with — the board after the
    fabricated-book gate, which is the filter standing between the two."""
    keep, drop_card = classify_fabricated_book(
        [(o.current_probability, o.current_yes_bid, o.current_yes_ask) for o in legs],
        is_exclusive=True,
    )
    assert not drop_card
    return [o for o, k in zip(legs, keep) if k]


def market(status: str = "open"):
    return SimpleNamespace(status=status)


def printed(legs, name: str) -> float | None:
    """What the card prints for one leg: its raw price over the card's divisor."""
    scale = _feed_display_scale(legs)
    for leg in legs:
        if leg.name == name:
            return round(float(leg.current_probability) / scale, 4)
    return None


class TestTheSpecimenCardAndPageAgree:
    def test_the_fossils_are_the_ones_dropped(self):
        kept = _drop_stale_observation_legs(market(), board())
        assert [leg.name for leg in kept] == [
            "Leeds Rhinos",
            "St Helens",
            "Warrington Wolves",
        ]

    def test_the_card_stops_dividing_by_fossil_mass(self):
        before = card_board(board())
        assert sum(leg.current_probability for leg in before) == pytest.approx(1.0950)
        after = _drop_stale_observation_legs(market(), before)
        assert sum(leg.current_probability for leg in after) == pytest.approx(0.6350)

    def test_leeds_prints_the_price_kalshi_is_quoting(self):
        """0.6350 is under `_feed_display_scale`'s 1.05 floor, so the card stops
        scaling at all and prints the venue's own midpoint — which is the number
        the detail page reaches from the other side once #7537 lands."""
        after = _drop_stale_observation_legs(market(), card_board(board()))
        assert _feed_display_scale(after) == 1.0
        assert printed(after, "Leeds Rhinos") == pytest.approx(0.3950)

    def test_the_number_actually_moves_and_lands_on_the_production_figure(self):
        """The assertion above is worthless if the card already printed 0.3950.

        This is the mutation control, and it is pinned to what production
        actually served rather than to arithmetic invented here: Discover's card
        for 3971707 printed `Leeds Rhinos 36.1%` (0.3607) on 2026-09-20 while
        `/api/futures/3971707` printed 30.2% for the same leg and the same
        stamp. Reproducing 0.3607 from the row is what proves this fixture is
        the card's real divisor and not a model of it.
        """
        before = card_board(board())
        assert printed(before, "Leeds Rhinos") == pytest.approx(0.3607, abs=1e-4)
        after = _drop_stale_observation_legs(market(), before)
        assert printed(after, "Leeds Rhinos") == pytest.approx(0.3950)
        assert printed(after, "Leeds Rhinos") != printed(before, "Leeds Rhinos")

    def test_the_gate_in_front_removes_exactly_the_two_measured_legs(self):
        """Names what this suite is composing with, so a change to the
        fabricated-book gate shows up here as a failure rather than as a silent
        re-basing of the 0.3607 above."""
        dropped = {leg.name for leg in board()} - {
            leg.name for leg in card_board(board())
        }
        assert dropped == {"Hull Kingston Rovers", "Wigan Warriors"}

    def test_a_fossil_can_no_longer_be_crowned_leader(self):
        """Placed before the leader pick for the phantom filter's reason: a leg
        whose book the venue no longer keeps must not name the card."""
        rows = (("Ghost", 0.9000, 0.8900, 0.9100, FOSSIL),) + SUPER_LEAGUE
        kept = _drop_stale_observation_legs(market(), board(rows=rows))
        assert "Ghost" not in [leg.name for leg in kept]


class TestTheCachedPathIsNotSilentlyInert:
    """🔴 The class that fails if the stamp is read off `last_updated` again."""

    def test_a_rehydrated_leg_has_no_last_updated_at_all(self):
        """The strawman control. If this ever passes a `last_updated`, every
        other assertion in this class proves nothing."""
        leg = rehydrated_leg(0, "Leeds Rhinos", 0.3950, 0.3300, 0.4600, NOW)
        assert not hasattr(leg, "last_updated")

    def test_the_reader_still_dates_it(self):
        leg = rehydrated_leg(0, "Leeds Rhinos", 0.3950, 0.3300, 0.4600, NOW)
        assert outcome_observed_at(leg) == NOW.replace(microsecond=0)

    def test_the_reader_returns_a_datetime_not_an_epoch(self):
        """`_as_utc` answers `None` for anything that is not a `datetime`, so an
        int here would make the whole predicate return the empty set."""
        assert isinstance(outcome_observed_at(rehydrated_leg(0, "x", 0.5, 0.49, 0.51, NOW)), datetime)

    def test_the_filter_fires_on_the_cached_path_too(self):
        kept = _drop_stale_observation_legs(market(), board(build=rehydrated_leg))
        assert [leg.name for leg in kept] == [
            "Leeds Rhinos",
            "St Helens",
            "Warrington Wolves",
        ]

    def test_both_carriers_reach_the_same_verdict(self):
        assert [leg.name for leg in _drop_stale_observation_legs(market(), board())] == [
            leg.name
            for leg in _drop_stale_observation_legs(
                market(), board(build=rehydrated_leg)
            )
        ]

    def test_a_leg_with_neither_carrier_is_not_stale(self):
        """`tennis_population.OutcomeRow`'s shape: no evidence is not evidence."""

        class SlotsRow:
            __slots__ = ("id", "name", "current_probability")

            def __init__(self, idx, name, prob):
                self.id, self.name, self.current_probability = idx, name, prob

        legs = [SlotsRow(0, "Leeds Rhinos", 0.3950), SlotsRow(1, "St Helens", 0.1300)]
        assert outcome_observed_at(legs[0]) is None
        assert _drop_stale_observation_legs(market(), legs) == legs


class TestOnlyLegsThatPrintANumberAreJudged:
    """#6256's boundary, pinned here because this fix went red against it once.

    `test_unpriced_leg_cannot_date_the_mark_6256` keeps a specimen whose whole
    tail is `NULL` and 125 days old, and asserts those blank rows still print so
    that the guard about them not dating the card's age mark has something to
    stand on. A blanket staleness drop deletes the specimen. It is also the
    wrong rule: this fix is about a DIVISOR, and a leg rendering no number is in
    no divisor.
    """

    HOUSE = (
        ("Democratic Party", 0.8750, 0.8700, 0.8800, NOW),
        ("Republican Party", 0.1350, 0.1300, 0.1400, NOW),
        ("Green Party", None, None, None, FOSSIL),
        ("Libertarian Party", None, None, None, FOSSIL),
        ("Working Families Party", None, None, None, FOSSIL),
    )

    def test_an_unpriced_fossil_stays_on_the_card(self):
        legs = board(rows=self.HOUSE)
        assert _drop_stale_observation_legs(market(), legs) == legs

    def test_a_priced_fossil_beside_it_still_goes(self):
        """The control that keeps the clause above from reading as 'this fix is
        off whenever any leg is blank'."""
        rows = self.HOUSE + (("Forward Party", 0.0400, 0.0300, 0.0500, FOSSIL),)
        kept = _drop_stale_observation_legs(market(), board(rows=rows))
        assert "Forward Party" not in [leg.name for leg in kept]
        assert "Green Party" in [leg.name for leg in kept]

    def test_an_unpriced_leg_cannot_make_a_priced_sibling_look_stale(self):
        """The reference stamp is the newest among PRICED legs. A blank row
        carrying a newer stamp than every price must not move it."""
        rows = (
            ("Democratic Party", 0.8750, 0.8700, 0.8800, FOSSIL),
            ("Republican Party", 0.1350, 0.1300, 0.1400, FOSSIL),
            ("Green Party", None, None, None, NOW),
        )
        legs = board(rows=rows)
        assert _drop_stale_observation_legs(market(), legs) == legs


class TestOurOwnOutageCannotBlankACard:
    def test_a_whole_market_ingestion_stall_withholds_nothing(self):
        """The rule is relative to the board's own newest stamp, never to `now`.
        If ingestion stalls for every leg they age together, the spread stays at
        zero, and a card cannot be emptied by our own failure."""
        stalled = restamp(lambda i, observed: FOSSIL)
        legs = board(rows=stalled)
        assert _drop_stale_observation_legs(market(), legs) == legs

    def test_a_board_polled_daily_is_nowhere_near_the_threshold(self):
        legs = board(rows=restamp(lambda i, observed: NOW - timedelta(days=i % 3)))
        assert _drop_stale_observation_legs(market(), legs) == legs


class TestTheHarmfulDirectionIsGuarded:
    def test_a_settled_board_is_untouched(self):
        """A settled board is a RESULT, and a result shows what ran — #7274's own
        bound, and the detail half's."""
        legs = board()
        assert _drop_stale_observation_legs(market("settled"), legs) == legs
        assert _drop_stale_observation_legs(market("closed"), legs) == legs

    def test_an_all_stale_board_keeps_every_leg(self):
        """Unreachable by construction — the leg holding the newest stamp is
        never stale — and guarded anyway, because the harmful direction here is
        taking a card's numbers away rather than leaving one stale.
        """
        legs = board()
        stale_all = {leg.id for leg in legs}

        original = feed_module._stale_observation_keys
        feed_module._stale_observation_keys = lambda _observations: stale_all
        try:
            assert _drop_stale_observation_legs(market(), legs) == legs
        finally:
            feed_module._stale_observation_keys = original

    def test_a_clean_board_is_returned_unchanged_not_rebuilt(self):
        legs = board(rows=restamp(lambda i, observed: NOW))
        assert _drop_stale_observation_legs(market(), legs) is legs


class TestBothSerializersCarryTheRule:
    """#4610: both serializers print the same card type, so a divisor rule that
    lands in one of them just moves the disagreement from card-vs-page to
    card-vs-card."""

    @pytest.mark.parametrize(
        "func_name", ["_score_futures", "_score_sports_mode_futures"]
    )
    def test_the_serializer_calls_the_shared_filter(self, func_name):

        source = inspect.getsource(getattr(feed_module, func_name))
        tree = ast.parse(source.lstrip())
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_drop_stale_observation_legs" in called

    def test_the_filter_reads_the_dual_carrier_reader_not_the_raw_column(self):
        """The mechanism, not the outcome — asserting the verdict alone would
        still pass a wiring that reads `last_updated` and dies on the cache."""

        source = inspect.getsource(feed_module._drop_stale_observation_legs)
        body = source.split('"""')[-1]
        assert "_outcome_observed_at" in body
        assert "last_updated" not in body
