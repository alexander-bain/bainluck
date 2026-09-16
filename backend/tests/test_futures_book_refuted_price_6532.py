"""#6532 — a price the row's own book prices out, on the futures ladder and chart.

The grid half of this ship (the event page's *Season context* card and
``/sport/soccer/laliga``, which is where the reader actually met the defect) is
gated against real PostgreSQL in
``tests/integration/test_grid_book_refuted_price_6532_pg.py``. This file is the
other reader path — ``/api/futures/{market_id}`` and the chart above it — plus
the predicate's own truth table and the one-copy check on the rule it imports.

WHAT A READER SAW. Real Sociedad printed at **Relegated 99%** beneath its own
**2-1-3** record while its row carried ``current_yes_ask 0.4900``: you can buy
the outcome at 49c. ``/api/futures/56775508`` served the same column, summing to
**8.24** where exactly three clubs go down, with ``price_unsupported`` null on
every leg.

WHY THE TWO SHIPPED ARMS WERE INERT, both by their own rules and both in this
file's controls: ``price_is_unsupported`` asks "does a TRADE support this?" and
``is_lone_ask_on_empty_book`` wants ``yes_ask > 0.50`` (the specimen's is 0.49,
missing by one cent); and every arm exempts a graded row, while 15 of that
market's 19 priced legs carry ``resolution_source='api_settlement'`` on a
contest that resolves in July 2027.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    WITHHELD_PRICE_FIELDS,
    price_is_unsupported,
    price_refuted_by_live_book,
    snapshot_price_is_unsupported,
)

#: ``(label, source, resolution_source, is_winner, p, bid, ask, refuted)``.
#: Read off market ``56775508`` on production 2026-09-16 ~10:5xZ, except where a
#: control needed a shape that market does not happen to carry.
CORPUS = (
    # 🔴 The specimen.
    ("real sociedad", "kalshi", "api_settlement", False, 0.99, 0.00, 0.49, True),
    ("valencia (ungraded)", "kalshi", None, False, 0.48, 0.00, 0.47, True),
    # A graded loser priced under its own ask: the book does not refute 0.60
    # when nobody will sell below 0.97.
    ("levante", "kalshi", "api_settlement", False, 0.60, 0.00, 0.97, False),
    # A settled WINNER beside a book nobody refreshed. Never touched — 163
    # Polymarket and 1 Kalshi leg are in this shape and withholding one deletes
    # a result, which is the harm the graded exemption exists to prevent.
    ("settled winner", "kalshi", "api_settlement", True, 1.00, 0.00, 0.07, False),
    # Graded, but no verdict: ignorance about which way it went is not evidence.
    ("graded, verdict unknown", "kalshi", "api_settlement", None, 0.99, 0.00, 0.49, False),
    # A graded loser BELOW a live bid keeps its price: its number is still the
    # ~0 its grade implies. 110 production legs are here and the symmetric form
    # blanks every one of them.
    ("graded loser under the bid", "kalshi", "api_settlement", False, 0.02, 0.40, 0.62, False),
    # The same shape UNGRADED is a quote, and a quote the live bid prices out is
    # refuted whichever side prices it out.
    ("ungraded under the bid", "kalshi", None, False, 0.10, 0.40, 0.62, True),
    # An ask of 1.00 cannot be exceeded, so the empty book falls through — the
    # shape `kalshi_resolution_sweep` screens on to find a stuck 99% ladder.
    ("empty book", "kalshi", None, False, 0.99, 0.00, 1.00, False),
    # No offer at all is not an offer of zero.
    ("no ask", "kalshi", None, False, 0.47, 0.00, 0.00, False),
    # Inside the display rounding: the page prints whole percents, so these two
    # numbers are the same number to the person looking at them.
    ("within the tolerance", "kalshi", None, False, 0.7040, 0.00, 0.70, False),
    # 🔴 The venue control. Byte-identical to the specimen, written by
    # Polymarket, whose rule for these columns is a different one (gotcha #19:
    # a wide spread falls back to `lastTradePrice`, so the price legitimately
    # sits above the ask whenever the last trade did). #5876 answers for these.
    ("polymarket, same shape", "polymarket", None, False, 0.99, 0.00, 0.49, False),
    ("no source", None, None, False, 0.99, 0.00, 0.49, False),
    ("no price", "kalshi", None, False, None, 0.00, 0.49, False),
)


def _kalshi_legs():
    """The Kalshi, priced rows of :data:`CORPUS`, in ladder order.

    One reader for both ladder tests so the fixture and the expectation can never
    be built from two different filters — the expectation below zips against this
    list, and a second copy of the filter is how that zip comes to compare a row
    with somebody else's verdict.
    """
    return [
        (name, p, bid, ask, resolution_source, is_winner)
        for name, source, resolution_source, is_winner, p, bid, ask, _refuted in CORPUS
        if source == "kalshi" and p is not None
    ]


@pytest.mark.parametrize(
    "label,source,resolution_source,is_winner,p,bid,ask,refuted",
    CORPUS,
    ids=[row[0] for row in CORPUS],
)
def test_the_predicate_truth_table(
    label, source, resolution_source, is_winner, p, bid, ask, refuted
):
    assert (
        price_refuted_by_live_book(source, resolution_source, is_winner, p, bid, ask)
        is refuted
    ), label


def test_the_specimen_is_invisible_to_the_two_shipped_arms():
    """🔴 THE REASON THIS ARM EXISTS, asserted rather than asserted-about.

    If ``price_is_unsupported`` already caught the specimen, #6532 would be a
    second copy of a shipped rule. It does not, and it misses for two
    independent reasons — the grade, and an ask one cent under
    ``ASK_ONLY_TRUSTED_MAX``. Both are pinned so that a later widening of that
    arm makes this test fail loudly rather than leaving two rules overlapping in
    silence.
    """
    graded = price_is_unsupported(
        "kalshi", "api_settlement", 0.00, 0.49, 0.99, has_trade_evidence=True
    )
    assert graded is False, "the grade alone disarms the shipped arm"

    ungraded_same_book = price_is_unsupported(
        "kalshi", None, 0.00, 0.49, 0.0, has_trade_evidence=True
    )
    assert ungraded_same_book is False, (
        "an ask of 0.49 is under ASK_ONLY_TRUSTED_MAX, so the lone-ask rule "
        "misses the specimen's book even with the grade removed"
    )


def test_the_write_side_rule_is_imported_and_not_copied():
    """One price policy, one definition — the whole reason this module exists.

    ``book_refutes_price`` is #5121's shipped predicate. It moved from
    ``app.tasks.kalshi`` into ``app.utils.kalshi_empty_book`` so the serve layer
    could ask the identical question; the poller must still be asking the SAME
    object, not a fork of it.
    """
    import app.tasks.kalshi as kalshi_task
    from app.utils import kalshi_empty_book

    assert kalshi_task.book_refutes_price is kalshi_empty_book.book_refutes_price

    # And the writer's behaviour on #5121's own measured row is unchanged:
    # KXNBAWINS-27MIA-60 traded at 0.5200 under a live ask of 0.0900, and rule 2
    # must refuse that trade. It then falls to rule 3's longshot ask cap, so the
    # tell is that the answer is NOT the trade — asserting `is None` would be
    # asserting the wrong rule.
    assert kalshi_task._kalshi_yes_probability(0.0, 0.09, 0.52) == 0.09
    # While the empty book still falls through to the trade, which
    # `kalshi_resolution_sweep` depends on.
    assert kalshi_task._kalshi_yes_probability(0.0, 1.0, 0.99) == 0.99


class TestTheLadder:
    """``/api/futures/{id}`` — the ladder the reader can open from the event page."""

    @staticmethod
    def _market(source="kalshi"):
        legs = _kalshi_legs()
        return SimpleNamespace(
            id=56775508,
            name="La Liga Relegation",
            description=None,
            category="championship",
            source=source,
            external_id="KXLALIGARELEGATION-27",
            status="open",
            sport=None,
            sport_id=None,
            event_id=None,
            market_type=None,
            market_tier=5,
            llm_sport_category="soccer",
            mutually_exclusive=True,
            commence_time=None,
            resolution_date=None,
            created_at=None,
            updated_at=None,
            group_id=None,
            canonical_market_key=None,
            hook_description=None,
            image_url=None,
            category_tags=[],
            market_metadata=None,
            outcomes=[
                SimpleNamespace(
                    id=i,
                    name=name,
                    external_id=f"KXLALIGARELEGATION-27-{i}",
                    current_probability=p,
                    current_yes_bid=bid,
                    current_yes_ask=ask,
                    current_american_odds=110,
                    rank=i,
                    rank_change_24h=None,
                    probability_change_24h=0.01,
                    opening_probability=None,
                    opening_american_odds=None,
                    is_winner=w,
                    resolution_source=rs,
                    last_updated=None,
                )
                for i, (name, p, bid, ask, rs, w) in enumerate(legs, start=1)
            ],
        )

    def test_the_arm_selects_exactly_the_refuted_legs(self):
        from app.routes.futures import _book_refuted_outcome_ids

        market = self._market()
        # The verdicts are re-read from CORPUS under the SAME filter `_market`
        # used, and zipped by position, so the expectation cannot drift from the
        # fixture when a row is added in the middle.
        verdicts = [
            refuted
            for _label, source, _rs, _w, p, _b, _a, refuted in CORPUS
            if source == "kalshi" and p is not None
        ]
        assert len(verdicts) == len(market.outcomes)
        expected = {
            o.id for o, refuted in zip(market.outcomes, verdicts) if refuted
        }
        assert _book_refuted_outcome_ids(market) == expected

    def test_a_polymarket_market_is_left_entirely_alone(self):
        from app.routes.futures import _book_refuted_outcome_ids

        assert _book_refuted_outcome_ids(self._market(source="polymarket")) == set()

    def test_the_refused_price_reaches_the_reader_as_null_and_is_counted(self):
        """Withheld, PRESENT and null, and counted — the module's serve contract.

        The clients test ``!== null`` and ``undefined !== null`` is true, so an
        omitted key is not a withheld one (#5539). And a row nulled here is nulled
        before ``normalize_display_probs``, so it leaves the divisor instead of
        halving every honest row on the same board.
        """
        from app.routes.futures import _book_refuted_outcome_ids, _format_market_detail

        market = self._market()
        withheld = _book_refuted_outcome_ids(market)
        detail = _format_market_detail(market, None, withheld)

        assert detail["prices_withheld"] == len(withheld) > 0
        for row in detail["outcomes"]:
            if row["id"] in withheld:
                for field in WITHHELD_PRICE_FIELDS:
                    assert field in row, f"{field} must be present, not omitted"
                    assert row[field] is None
            else:
                assert row["probability"] is not None, row["name"]


class TestTheChart:
    """The chart above the ladder must not plot what the ladder just refused.

    #5898's rule, one arm later. All three refuted legs of market 56775508 carry
    four charted points each in the page's own 168-hour window and every one of
    those points is refuted, so leaving this out would rebuild #5898's defect
    with #6532's own repair.
    """

    @staticmethod
    def _snapshot(outcome_id, probability, yes_bid, yes_ask):
        return SimpleNamespace(
            outcome_id=outcome_id,
            bookmaker="kalshi",
            probability=probability,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            last_price=None,
        )

    def test_a_refuted_point_is_dropped_and_an_honest_one_survives(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [
            SimpleNamespace(id=1, resolution_source="api_settlement", is_winner=False),
            SimpleNamespace(id=2, resolution_source=None, is_winner=False),
        ]
        snapshots = [
            self._snapshot(1, 0.99, 0.00, 0.49),  # the specimen's own point
            self._snapshot(1, 0.40, 0.00, 0.49),  # the same series, honest
            self._snapshot(2, 0.30, 0.00, 0.90),  # honest throughout
        ]
        kept = _drop_unsupported_snapshot_points(snapshots, outcomes)
        assert [s.probability for s in kept] == [0.40, 0.30]

    def test_a_settled_winner_keeps_every_point(self):
        """Settled means settled, on the chart too (#225 item 3, #232)."""
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [
            SimpleNamespace(id=1, resolution_source="api_settlement", is_winner=True)
        ]
        snapshots = [self._snapshot(1, 1.00, 0.00, 0.07)] * 3
        assert len(_drop_unsupported_snapshot_points(snapshots, outcomes)) == 3

    def test_an_outcome_we_did_not_load_keeps_its_points(self):
        """Absence fails OPEN, here as everywhere else in this module."""
        from app.routes.futures import _drop_unsupported_snapshot_points

        snapshots = [self._snapshot(99, 0.99, 0.00, 0.49)]
        assert _drop_unsupported_snapshot_points(snapshots, []) == snapshots

    def test_the_default_verdict_fails_open(self):
        """A caller that never learned about ``is_winner`` loses nothing.

        ``None`` is the graded-verdict-unknown case, which the arm exempts. The
        keyword default therefore keeps every point a caller serves today rather
        than making ignorance a reason to drop a reader's data.
        """
        assert (
            snapshot_price_is_unsupported(
                "kalshi", "api_settlement", 0.99, 0.00, 0.49, None
            )
            is False
        )
        assert (
            snapshot_price_is_unsupported(
                "kalshi", "api_settlement", 0.99, 0.00, 0.49, None, is_winner=False
            )
            is True
        )
