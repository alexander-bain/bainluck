"""#4992 — the hero and the chart under it are on ONE scale.

`GET /api/futures/{id}/history` used to average the RAW, vig-inclusive rows of
`futures_odds_snapshots` and hand them to the Probability Trend chart, while
`GET /api/futures/{id}` — the hero and every outcome row drawn directly above
that chart — serves the de-vigged consensus with the #23 display squeeze. Two
scales, one screen:

    /futures/56775503  hero "20% Spain"      chart plots Spain at 32.5
    /futures/7         hero "12% Scheffler"  chart plots Scheffler at 17.6

Both stamped the same second, so it is scale and never staleness. The charted
number was raw implied straight off the American odds (+469 -> 100/569).

THE NUMBERS IN THIS FILE ARE PRODUCTION ROWS, not invented ones: market 7
(*US Open Winner*, odds_api golf) at 2026-09-17T20:30:09.775418Z, five books
whose columns carry overrounds of 1.23 to 1.56. The served detail payload put
Scheffler at 0.118 and the chart at 0.1757576 the same second. `test_the_class`
pins the whole journey; `test_the_raw_value_is_gone` is the strawman guard that
fails if the fix is reverted.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.routes import futures as futures_route
from app.utils.futures_history_basis import devigged_consensus_by_time


T0 = datetime(2026, 9, 17, 20, 30, 9, 775418, tzinfo=timezone.utc)

#: MARKET 7'S WHOLE FIELD AT T0, EXACTLY AS PRODUCTION STORED IT — all 351
#: `futures_odds_snapshots` rows for that instant, five books over 98 outcomes,
#: read back through `/api/admin/db-query` on 2026-09-17. Book overrounds run
#: 1.227 (betmgm) to 1.564 (betrivers), and the books quote DIFFERENT SUBSETS
#: (betmgm 44 legs, draftkings 88), which is why the de-vig has to be per book.
#:
#: Kept whole rather than trimmed to the four legs under test: both helpers are
#: functions of the entire field — `remove_vig_nway` divides by the column's own
#: sum and the #23 squeeze tests the field's sum — so a trimmed fixture measures
#: a different computation and would agree with the handler while production did
#: not. A collapsed "rest of field" term was tried first and is what this
#: replaces: it reproduces the de-vig and NOT the squeeze, because it averages
#: the un-charted legs' cross-book disagreement away.
#: 546 Scheffler · 547 McIlroy · 549 Rahm · 552 Aberg.
_M7_FIELD = {
    "betmgm": {546: 0.181818, 547: 0.111111, 548: 0.038462, 549: 0.066667, 550: 0.058824, 551: 0.047619, 552: 0.047619, 553: 0.029412, 554: 0.02439, 555: 0.029412, 556: 0.02439, 557: 0.038462, 558: 0.02439, 559: 0.02439, 561: 0.019608, 563: 0.014925, 564: 0.021739, 565: 0.014925, 566: 0.021739, 567: 0.02439, 568: 0.009901, 569: 0.014925, 570: 0.029412, 571: 0.038462, 574: 0.019608, 575: 0.014925, 577: 0.010989, 578: 0.007937, 580: 0.034483, 581: 0.009901, 583: 0.019608, 587: 0.007937, 590: 0.009901, 603: 0.012346, 604: 0.012346, 605: 0.009901, 610: 0.009901, 611: 0.009901, 615: 0.006623, 619: 0.006623, 117954279: 0.007937, 117954282: 0.02439, 157141894: 0.019608, 157141895: 0.014925},
    "betonlineag": {546: 0.166667, 547: 0.090909, 548: 0.034483, 549: 0.052632, 550: 0.047619, 551: 0.047619, 552: 0.047619, 553: 0.027778, 554: 0.02439, 555: 0.019608, 556: 0.019608, 557: 0.038462, 558: 0.019608, 559: 0.019608, 560: 0.014085, 561: 0.016393, 563: 0.009901, 564: 0.016393, 565: 0.009901, 566: 0.027778, 567: 0.019608, 568: 0.006623, 569: 0.010989, 570: 0.029412, 571: 0.043478, 572: 0.007937, 574: 0.016393, 575: 0.012346, 577: 0.007937, 580: 0.038462, 581: 0.007937, 583: 0.016393, 585: 0.009901, 586: 0.005682, 587: 0.006623, 589: 0.009901, 590: 0.007937, 594: 0.007937, 597: 0.006623, 601: 0.005682, 602: 0.006623, 603: 0.009901, 604: 0.009901, 605: 0.007937, 607: 0.006623, 611: 0.009901, 612: 0.006623, 613: 0.004975, 614: 0.006623, 619: 0.006623, 621: 0.003322, 623: 0.005682, 624: 0.004975, 626: 0.003984, 627: 0.012346, 632: 0.009901, 640: 0.007937, 648: 0.004425, 668: 0.005682, 117954278: 0.009901, 117954279: 0.006623, 117954281: 0.004425, 117954282: 0.02439, 117954285: 0.003322, 152871110: 0.003984, 152871111: 0.003322, 152871112: 0.003984, 157141894: 0.012346, 157141895: 0.012346, 157141896: 0.012346},
    "betrivers": {546: 0.181818, 547: 0.111111, 548: 0.034483, 549: 0.076923, 550: 0.058824, 551: 0.052632, 552: 0.052632, 553: 0.029412, 554: 0.02439, 555: 0.029412, 556: 0.02439, 557: 0.038462, 558: 0.02439, 559: 0.029412, 560: 0.019608, 561: 0.019608, 563: 0.019608, 564: 0.019608, 565: 0.014925, 566: 0.02439, 567: 0.02439, 568: 0.009901, 569: 0.019608, 570: 0.034483, 571: 0.047619, 572: 0.009901, 574: 0.02439, 575: 0.014925, 577: 0.009901, 580: 0.034483, 581: 0.009901, 583: 0.02439, 585: 0.009901, 586: 0.009901, 587: 0.009901, 588: 0.006623, 589: 0.009901, 590: 0.009901, 594: 0.009901, 597: 0.009901, 601: 0.009901, 602: 0.009901, 603: 0.012346, 604: 0.012346, 605: 0.009901, 607: 0.009901, 608: 0.012346, 610: 0.009901, 611: 0.009901, 612: 0.009901, 613: 0.004975, 614: 0.009901, 619: 0.009901, 621: 0.003984, 623: 0.009901, 624: 0.006623, 626: 0.003984, 627: 0.014925, 632: 0.009901, 640: 0.009901, 648: 0.003984, 668: 0.006623, 117954278: 0.009901, 117954279: 0.009901, 117954281: 0.004975, 117954282: 0.02439, 117954285: 0.003984, 117954289: 0.003984, 117954291: 0.002849, 152871110: 0.004975, 152871111: 0.003984, 152871112: 0.003984, 152871114: 0.003984, 152871122: 0.002849, 152871127: 0.004975, 157141894: 0.014925, 157141895: 0.019608, 157141896: 0.014925, 161146327: 0.002849},
    "draftkings": {546: 0.181818, 547: 0.111111, 548: 0.043478, 549: 0.076923, 550: 0.058824, 551: 0.043478, 552: 0.043478, 553: 0.029412, 554: 0.019608, 555: 0.02439, 556: 0.027778, 557: 0.038462, 558: 0.02439, 559: 0.02439, 560: 0.017857, 561: 0.016393, 563: 0.014085, 564: 0.016393, 565: 0.014085, 566: 0.019608, 567: 0.021739, 568: 0.009901, 569: 0.017857, 570: 0.029412, 571: 0.038462, 572: 0.009901, 574: 0.019608, 575: 0.014085, 577: 0.009901, 578: 0.007937, 580: 0.029412, 581: 0.009901, 583: 0.019608, 584: 0.006623, 585: 0.005682, 586: 0.009901, 587: 0.007092, 588: 0.006623, 589: 0.009009, 590: 0.010989, 592: 0.003984, 593: 0.003623, 594: 0.005682, 597: 0.007937, 599: 0.002494, 601: 0.007937, 602: 0.009901, 603: 0.012346, 604: 0.011765, 605: 0.009901, 607: 0.009901, 608: 0.010989, 609: 0.004975, 610: 0.012346, 611: 0.009901, 613: 0.003984, 614: 0.009009, 616: 0.005682, 617: 0.003322, 619: 0.006623, 621: 0.003322, 624: 0.007092, 626: 0.003322, 627: 0.012346, 629: 0.004975, 630: 0.003984, 632: 0.010989, 640: 0.006623, 651: 0.003984, 658: 0.002494, 664: 0.004975, 668: 0.004425, 117954278: 0.009901, 117954279: 0.007937, 117954280: 0.003984, 117954281: 0.004975, 117954282: 0.016393, 117954284: 0.005682, 117954285: 0.003322, 152871112: 0.002494, 152871114: 0.002494, 152871119: 0.003322, 152871127: 0.003984, 153771227: 0.003322, 155516681: 0.003322, 157141894: 0.014085, 157141895: 0.016393, 157141896: 0.014085},
    "lowvig": {546: 0.166667, 547: 0.090909, 548: 0.034483, 549: 0.052632, 550: 0.047619, 551: 0.047619, 552: 0.047619, 553: 0.027778, 554: 0.02439, 555: 0.019608, 556: 0.019608, 557: 0.038462, 558: 0.019608, 559: 0.019608, 560: 0.014085, 561: 0.016393, 563: 0.009901, 564: 0.016393, 565: 0.009901, 566: 0.027778, 567: 0.019608, 568: 0.006623, 569: 0.010989, 570: 0.029412, 571: 0.043478, 572: 0.007937, 574: 0.016393, 575: 0.012346, 577: 0.007937, 580: 0.038462, 581: 0.007937, 583: 0.016393, 585: 0.009901, 586: 0.005682, 587: 0.006623, 589: 0.009901, 590: 0.007937, 594: 0.007937, 597: 0.006623, 601: 0.005682, 602: 0.006623, 603: 0.009901, 604: 0.009901, 605: 0.007937, 607: 0.006623, 611: 0.009901, 612: 0.006623, 613: 0.004975, 614: 0.006623, 619: 0.006623, 621: 0.003322, 623: 0.005682, 624: 0.004975, 626: 0.003984, 627: 0.012346, 632: 0.009901, 640: 0.007937, 648: 0.004425, 668: 0.005682, 117954278: 0.009901, 117954279: 0.006623, 117954281: 0.004425, 117954282: 0.02439, 117954285: 0.003322, 152871110: 0.003984, 152871111: 0.003322, 152871112: 0.003984, 157141894: 0.012346, 157141895: 0.012346, 157141896: 0.012346},
}

#: What `/api/futures/7` served for those four the same second.
_M7_SERVED = {546: 0.1180, 547: 0.0690, 549: 0.0430, 552: 0.0320}
#: What the chart drew for them the same second, before this fix.
_M7_RAW_CHARTED = {546: 0.1757576, 547: 0.1036, 549: 0.0651554, 552: 0.0477934}


def _m7_field(stamp=T0):
    """Market 7's whole field at ``stamp``, as ``{t: {book: {oid: raw}}}``."""
    return {stamp: _M7_FIELD}


class TestTheServedSeries:
    def test_the_class_the_chart_now_prints_what_the_hero_prints(self):
        """Every charted leg lands on the value the detail payload served."""
        point = devigged_consensus_by_time(_m7_field(), mutually_exclusive=True)[T0]

        for oid, served in _M7_SERVED.items():
            assert point[oid] == pytest.approx(served, abs=0.0006), (
                f"outcome {oid}: chart {point[oid]:.4f} vs hero {served:.4f} — "
                "the page is telling two stories again (#4992)"
            )

    def test_the_raw_value_is_gone(self):
        """Strawman guard: revert the fix and this is the assertion that fails.

        Without it the file could pass on a handler that still served raw prices
        whenever the two happened to round together.
        """
        point = devigged_consensus_by_time(_m7_field(), mutually_exclusive=True)[T0]

        # Asked as a RATIO, because the defect is one. The overround scales
        # every leg by the same factor (measured 1.49-1.52 here, 1.58-1.60 on
        # the filed Kalshi specimen), so a longshot's ABSOLUTE gap is small —
        # Aberg's is 0.0158 — and an absolute threshold either misses the
        # longshots or has to be set so low it stops discriminating.
        for oid, raw in _M7_RAW_CHARTED.items():
            assert raw / point[oid] > 1.3, (
                f"outcome {oid} still charts its RAW vig-inclusive price {raw}"
            )

    def test_the_field_the_reader_sees_sums_to_one(self):
        """Three of thirty-two candidates summed to 70% on the filed specimen."""
        point = devigged_consensus_by_time(_m7_field(), mutually_exclusive=True)[T0]
        assert sum(point.values()) == pytest.approx(1.0, abs=0.01)

    def test_each_book_is_devigged_on_its_own_column(self):
        """#1844's rule: a 1.23-overround book must not out-weight a 1.56 one.

        Two books quoting the SAME price for one leg disagree about its
        probability exactly in proportion to their own overrounds, so a
        consensus that skipped the per-book step would land on the raw mean.
        """
        stamp = T0
        field = {
            stamp: {
                # both quote 0.20 on leg 1; their columns sum to 1.0 and 2.0
                "draftkings": {1: 0.20, 99: 0.80},
                "betmgm": {1: 0.20, 99: 1.80},
            }
        }
        point = devigged_consensus_by_time(field, mutually_exclusive=True)[stamp]

        # draftkings says 0.20/1.0 = 0.20; betmgm says 0.20/2.0 = 0.10; mean 0.15.
        # The raw mean of the two quotes is 0.20 — the number this replaces.
        assert point[1] == pytest.approx(0.15, abs=0.001)


class TestTheBoundaries:
    def test_a_source_that_publishes_probabilities_is_not_devigged(self):
        """#6675: Kalshi/Polymarket/DataGolf columns are already probabilities.

        Dividing one by its own sum re-scales an honest price. A 28-way Kalshi
        candidate field summing to 1.6 is an INDEPENDENT-binary set, not an
        overround to divide out.
        """
        stamp = T0
        field = {stamp: {"kalshi": {1: 0.60, 2: 0.60, 3: 0.40}}}

        point = devigged_consensus_by_time(field, mutually_exclusive=True)[stamp]

        # Untouched by the de-vig. The #23 squeeze still owns whether the
        # DISPLAYED column is renormalized, and that is its call, not ours.
        assert point[1] == point[2]
        assert point[1] > point[3]

        # Asked again BELOW the squeeze's own trigger (sum 0.90), because the
        # field above sums to 1.6 and is squeezed downstream — which leaves the
        # ordering identical whether or not the de-vig ran, so the assertions
        # above cannot tell the two apart. Here the price must survive to the
        # digit: de-vigged it would read 0.667.
        quiet = {stamp: {"kalshi": {1: 0.60, 2: 0.30}}}
        held = devigged_consensus_by_time(quiet, mutually_exclusive=True)[stamp]
        assert held[1] == pytest.approx(0.60, abs=1e-9)

    def test_a_participation_family_is_never_squeezed(self):
        """#199: make-cut / top-N legs are simultaneously true.

        Squeezing one squashed an honest 86% make-cut to ~1% on The Open.
        """
        stamp = T0
        field = {stamp: {"datagolf_model": {1: 0.86, 2: 0.80, 3: 0.74}}}

        point = devigged_consensus_by_time(
            field, mutually_exclusive=False
        )[stamp]

        assert point[1] == pytest.approx(0.86, abs=0.0001)
        assert sum(point.values()) > 2.0  # left well over 100%, on purpose

        # A SQUEEZABLE participation family, which the field above is not: at a
        # sum of 2.40 the #23 helper declines on its own overround guard
        # (`_FIELD_SUM_MAX` 1.60), so it returns 0.86 either way and says
        # nothing about the flag being forwarded. Two legs summing to 1.41 sit
        # inside the squeezing band, where passing `mutually_exclusive=True`
        # would print this 86% make-cut as 61%.
        pair = {stamp: {"datagolf_model": {1: 0.86, 2: 0.55}}}
        honest = devigged_consensus_by_time(pair, mutually_exclusive=False)[stamp]
        squeezed = devigged_consensus_by_time(pair, mutually_exclusive=True)[stamp]
        assert honest[1] == pytest.approx(0.86, abs=0.0001)
        assert squeezed[1] == pytest.approx(0.61, abs=0.01)

    def test_an_unnormalizable_timestamp_is_absent_not_raw(self):
        """gotcha #53 — an absence and a fact must not share a shape.

        A gap in a line is honest. A raw point drawn between de-vigged ones
        renders as MOVEMENT, which is the failure mode #1844 shipped for months.
        """
        good, bad = T0, T0 - timedelta(hours=1)
        field = {
            good: {"draftkings": {1: 0.5, 2: 0.5}},
            bad: {"draftkings": {1: None, 2: 0.5}},  # None -> column refused
        }

        series = devigged_consensus_by_time(field, mutually_exclusive=True)

        assert good in series
        assert bad not in series

    def test_an_unclassified_source_says_so_once(self, caplog):
        """A new prediction market must not be de-vigged in silence (#6675)."""
        field = {T0: {"some_new_venue": {1: 0.5, 2: 0.5}}}

        with caplog.at_level("WARNING"):
            devigged_consensus_by_time(field, mutually_exclusive=True)

        assert "some_new_venue" in caplog.text
        assert "#6675" in caplog.text


# ---------------------------------------------------------------------------
# The served payload, through the handler
# ---------------------------------------------------------------------------


def _outcome(oid, name, prob):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.external_id = name
    o.current_probability = prob
    o.is_winner = None
    o.resolution_source = None
    return o


def _snapshot(oid, book, prob, stamp=T0):
    s = MagicMock()
    s.outcome_id = oid
    s.bookmaker = book
    s.probability = prob
    s.captured_at = stamp
    s.yes_bid = None
    s.yes_ask = None
    s.last_price = None
    return s


class _Result:
    def __init__(self, rows=(), scalar=None):
        self._rows, self._scalar = list(rows), scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar


class _Session:
    """Answers each ``execute`` from a queue; the last entry repeats."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


@pytest.mark.asyncio
async def test_the_handler_serves_the_devigged_series_and_withholds_the_price():
    """End to end: the payload the chart reads carries neither raw price."""
    outcomes = [
        _outcome(546, "Scottie Scheffler", 0.130446),
        _outcome(547, "Rory McIlroy", 0.0762),
        _outcome(900, "Rest Of Field", 0.79),
    ]
    market = MagicMock()
    market.id = 7
    market.name = "US Open Winner"
    market.outcomes = outcomes
    market.mutually_exclusive = True
    market.market_metadata = None
    market.status = "open"

    # Two books, each with a real overround, across three stamps.
    rows = []
    for k in range(3):
        stamp = T0 - timedelta(hours=k)
        for book, scale in (("draftkings", 1.0), ("betmgm", 1.2)):
            rows.append(_snapshot(546, book, 0.181818 * scale, stamp))
            rows.append(_snapshot(547, book, 0.111111 * scale, stamp))
            rows.append(_snapshot(900, book, 1.183203 * scale, stamp))

    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_futures_history(
        7, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    series = {o["outcome_id"]: o["history"] for o in payload["outcomes"]}
    assert series, "the chart lost every series"

    scheffler = series[546]
    assert len(scheffler) == 3
    for point in scheffler:
        # 0.181818 / 1.476132-ish column -> ~0.123, never the raw 0.1818.
        assert point["probability"] == pytest.approx(0.1232, abs=0.001)
        assert abs(point["probability"] - 0.181818) > 0.02
        # A de-vigged, squeezed probability is not a price anyone quoted, so
        # no American odds are invented for it (#5835's withheld-not-rescaled).
        assert point["american_odds"] is None

    # The counter reports what was DRAWN: three stamps on each of three legs.
    # (Nine is under the route's own `sparse` threshold of ten, which is
    # pre-existing and unmoved — this fixture is small, not thin.)
    assert payload["total_data_points"] == 9


@pytest.mark.asyncio
async def test_a_chart_that_drew_nothing_reports_nothing_and_says_sparse():
    """The counter follows the skip, or an empty chart calls itself dense.

    `total_data_points` is the only input to the `sparse` flag the chart's
    empty state reads, and #4992 introduced a point the grouping holds and the
    series drops. Counting the grouping would have this market promise 9 points
    over a chart with no line on it — gotcha #53, an absence wearing the shape
    of a fact. The rows below are stored, non-null and therefore grouped; every
    book column sums to zero, so `remove_vig_nway` refuses each one and no
    timestamp survives.
    """
    outcomes = [_outcome(546, "Scottie Scheffler", 0.13), _outcome(547, "Rory McIlroy", 0.08)]
    market = MagicMock()
    market.id = 7
    market.name = "US Open Winner"
    market.outcomes = outcomes
    market.mutually_exclusive = True
    market.market_metadata = None
    market.status = "open"

    rows = []
    for k in range(3):
        stamp = T0 - timedelta(hours=k)
        rows.append(_snapshot(546, "draftkings", 0.0, stamp))
        rows.append(_snapshot(547, "draftkings", 0.0, stamp))

    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_futures_history(
        7, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert all(o["history"] == [] for o in payload["outcomes"])
    assert payload["total_data_points"] == 0
    assert payload["sparse"] is True
