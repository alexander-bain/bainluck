"""#7458 — the grid's trend chart must draw the SAME quantity as its table.

#1844 made both sides of the movers delta agree about vig. #6675 made them
agree about what a column sums to. Both fixed ``_compute_movers``; neither
touched the rail beside it, and the trend chart went on pooling
``FuturesOddsSnapshot.probability`` by row and taking the median.

That column is the raw, vig-inclusive, per-BOOKMAKER price. So on 2026-09-20 the
NBA grid's legend published OKC at 28.17% four centimetres above its own table
saying 21.50%, and every one of the five leagues disagreed with itself — EPL's
top NINE clubs summed to 102%, which is not a probability distribution, it is a
21% overround.

Two symptoms, one defect, and the second is the one a guard is most likely to
miss. Because the Odds API's four books write together at one minute and
polymarket writes alone at another, a *row*-pooled median is decided by whoever
happened to write in that bucket. On the register-backed path only one source
reaches the chart at all, so NBA drew 41 identical buckets — a flat "Past 7d"
line beside a movers card reporting OKC −1.7%. De-vigging alone would only
trade that flat line for a sawtooth between the venues' two honest opinions.

These are guards for the CLASS: the arithmetic was wrong on every league, and
NHL/NFL merely had less of it to be wrong about.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.playoffs import (
    _ALREADY_PROBABILITY_SOURCES,
    _build_trend_chart,
)


# ---------------------------------------------------------------------------
# The production specimen, transcribed
# ---------------------------------------------------------------------------

#: The four Odds API books' raw prices for OKC on the NBA championship column,
#: read off production on 2026-09-20. Vig-inclusive: each book's full 30-team
#: column sums to ~1.21, so OKC de-vigs to ~0.23 and the pooled median of these
#: four — 0.281746 — is the number the legend used to publish.
_OKC_BOOK_PRICES = {
    "betmgm": 0.2778,
    "betonlineag": 0.25,
    "betrivers": 0.2857,
    "fanduel": 0.2941,
}
_SAS_BOOK_PRICES = {
    "betmgm": 0.2703,
    "betonlineag": 0.2597,
    "betrivers": 0.2778,
    "fanduel": 0.2857,
}
#: What a book's whole column adds up to before de-vigging.
_BOOK_COLUMN_SUM = 1.21

#: polymarket publishes a probability, not a price: its column is already
#: normalized and must survive de-vig untouched (#6675).
_OKC_POLYMARKET = 0.215
_SAS_POLYMARKET = 0.215

_ODDS_API_MARKET = 2
_POLYMARKET_MARKET = 20569230

_OKC, _SAS = 101, 102
#: The rest of the 30-team field, collapsed into one sibling per market. It is
#: never drawn — it exists because the de-vig denominator is the whole column,
#: and reading a tenth of a column and dividing by its sum is #6675 with a
#: different numerator.
_FIELD_ODDS_API, _FIELD_POLYMARKET = 901, 902

_DRAWN = {_OKC: "Oklahoma City Thunder", _SAS: "San Antonio Spurs"}


class _Row(SimpleNamespace):
    pass


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the two reads ``_build_trend_chart`` makes, in order.

    Deliberately not a mock that returns the same thing to everything: the
    market lookup and the snapshot read have different shapes, and a fake that
    cannot tell them apart would pass whatever the function did.
    """

    def __init__(self, market_ids, snapshot_rows):
        self._market_ids = [(m,) for m in market_ids]
        self._snapshot_rows = snapshot_rows
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return _FakeResult(self._market_ids)
        return _FakeResult(self._snapshot_rows)


def _snapshots(
    *,
    hours_back: int,
    okc_book_prices=None,
    okc_polymarket=_OKC_POLYMARKET,
    include_polymarket=True,
):
    """Build the production write CADENCE, not just the production values.

    The Odds API's books land together on even hours; polymarket lands alone on
    odd ones. That alternation is the whole of symptom two, so a fixture that
    wrote every source in every bucket could not see it.
    """
    okc_book_prices = okc_book_prices or _OKC_BOOK_PRICES
    now = datetime(2026, 9, 20, 4, 30, tzinfo=timezone.utc)
    rows = []
    for hour in range(hours_back):
        captured = now - timedelta(hours=hour)
        if hour % 2 == 0:
            for book, okc_price in okc_book_prices.items():
                sas_price = _SAS_BOOK_PRICES[book]
                rows.append(_Row(
                    outcome_id=_OKC, market_id=_ODDS_API_MARKET, bookmaker=book,
                    captured_at=captured, probability=okc_price,
                ))
                rows.append(_Row(
                    outcome_id=_SAS, market_id=_ODDS_API_MARKET, bookmaker=book,
                    captured_at=captured, probability=sas_price,
                ))
                rows.append(_Row(
                    outcome_id=_FIELD_ODDS_API, market_id=_ODDS_API_MARKET,
                    bookmaker=book, captured_at=captured,
                    probability=_BOOK_COLUMN_SUM - okc_price - sas_price,
                ))
        elif include_polymarket:
            for outcome_id, probability in (
                (_OKC, okc_polymarket),
                (_SAS, _SAS_POLYMARKET),
                (_FIELD_POLYMARKET, 1.0 - okc_polymarket - _SAS_POLYMARKET),
            ):
                rows.append(_Row(
                    outcome_id=outcome_id, market_id=_POLYMARKET_MARKET,
                    bookmaker="polymarket", captured_at=captured,
                    probability=probability,
                ))
    # The read is ordered newest-first.
    rows.sort(key=lambda r: r.captured_at, reverse=True)
    return rows


async def _chart(rows, market_ids=(_ODDS_API_MARKET, _POLYMARKET_MARKET)):
    session = _FakeSession(market_ids, rows)
    return await _build_trend_chart(
        session, list(_DRAWN), dict(_DRAWN), hours=168, top_n=10,
    )


def _series(chart, name):
    return [b["outcomes"][name] for b in chart["timeline"] if name in b["outcomes"]]


def _legend(chart, name):
    for entry in chart["outcomes"]:
        if entry["name"] == name:
            return entry["current_probability"]
    raise AssertionError(f"{name} is not in the legend")


# ---------------------------------------------------------------------------
# Symptom one: the legend published a price, and called it a probability
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legend_is_devigged_not_the_raw_pooled_median():
    chart = await _chart(_snapshots(hours_back=48))

    legend = _legend(chart, "Oklahoma City Thunder")

    assert legend == pytest.approx(0.2219, abs=0.005), (
        "the legend must be the de-vigged consensus of the two venues "
        "(~0.229 from the books, 0.215 from polymarket), not a price"
    )
    assert legend < 0.25, (
        "0.281746 is the median of the four RAW book prices — the exact number "
        "the NBA legend printed while its table said 0.215"
    )


@pytest.mark.asyncio
async def test_the_drawn_names_no_longer_sum_to_an_overround():
    """EPL's top nine summed to 102%. Two co-favourites must not sum to a price."""
    chart = await _chart(_snapshots(hours_back=48))

    total = sum(e["current_probability"] for e in chart["outcomes"])
    raw_total = (
        sorted(_OKC_BOOK_PRICES.values())[1:3][0]
        + sorted(_SAS_BOOK_PRICES.values())[1:3][0]
    )

    assert total < raw_total, (
        "the two favourites' de-vigged sum must fall below their raw one; if it "
        "does not, the overround is still in the published numbers"
    )
    assert total == pytest.approx(0.4438, abs=0.01)


# ---------------------------------------------------------------------------
# Symptom two: the bucket's value was decided by whoever wrote in it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_unmoved_market_draws_a_flat_line_not_a_sawtooth():
    """The guard the de-vig alone would NOT have earned.

    Nothing moves in this fixture. The books write on even hours and polymarket
    on odd ones, so without carrying each column forward the line alternates
    between the two venues' honest but different opinions — measured ±1.8pt on
    production, on a market that did not move.
    """
    chart = await _chart(_snapshots(hours_back=48))

    series = _series(chart, "Oklahoma City Thunder")

    assert len(series) >= 20, "fixture must produce a real series to be a guard"
    # Bucket one sees only the source that wrote first; from the moment both
    # venues have been seen, an unmoved market is a flat line.
    settled = series[1:]
    assert max(settled) - min(settled) < 0.001, (
        f"unmoved market drew a {(max(settled) - min(settled)) * 100:.2f}pt "
        f"range: the line is still reporting which venue wrote that hour"
    )


@pytest.mark.asyncio
async def test_a_real_move_still_moves_the_line():
    """Non-vacuous: the flatness guard above must not be satisfiable by a
    function that simply returns a constant."""
    steady = _snapshots(hours_back=48)
    moved = _snapshots(
        hours_back=48,
        okc_book_prices={k: v + 0.08 for k, v in _OKC_BOOK_PRICES.items()},
    )
    # Splice: the older half is the steady market, the newer half has re-priced.
    cut = datetime(2026, 9, 19, 16, tzinfo=timezone.utc)
    spliced = [r for r in moved if r.captured_at >= cut] + [
        r for r in steady if r.captured_at < cut
    ]

    chart = await _chart(spliced)
    series = _series(chart, "Oklahoma City Thunder")

    assert max(series) - min(series) > 0.02, (
        "an 8pt re-price across four books must reach the line; if it does "
        "not, the flatness guard above is vacuous"
    )


# ---------------------------------------------------------------------------
# The #6675 classification, on this rail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_probability_source_is_not_rescaled_by_its_own_column():
    """polymarket alone: its 0.215 must arrive as 0.215, not 0.215/column_sum."""
    rows = [
        r for r in _snapshots(hours_back=48) if r.market_id == _POLYMARKET_MARKET
    ]
    chart = await _chart(rows, market_ids=(_POLYMARKET_MARKET,))

    assert _legend(chart, "Oklahoma City Thunder") == pytest.approx(0.215, abs=1e-6)


@pytest.mark.asyncio
async def test_polymarket_is_classified_as_already_normalized():
    """The classification is the load-bearing part; pin it by name."""
    assert "polymarket" in _ALREADY_PROBABILITY_SOURCES
    assert "kalshi" in _ALREADY_PROBABILITY_SOURCES
    assert "fanduel" not in _ALREADY_PROBABILITY_SOURCES


# ---------------------------------------------------------------------------
# The widened read must not widen the PAYLOAD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sibling_outcomes_are_a_denominator_never_a_line():
    chart = await _chart(_snapshots(hours_back=48))

    names = {e["name"] for e in chart["outcomes"]}
    assert names == set(_DRAWN.values())
    for bucket in chart["timeline"]:
        assert set(bucket["outcomes"]) <= set(_DRAWN.values()), (
            "the rest of the field is read to make the de-vig honest and must "
            "never reach the chart"
        )


@pytest.mark.asyncio
async def test_no_snapshots_is_an_empty_chart_not_a_half_built_one():
    chart = await _chart([])

    assert chart["timeline"] == []
    assert chart["outcomes"] == []


@pytest.mark.asyncio
async def test_no_outcomes_short_circuits_before_any_query():
    session = _FakeSession([], [])
    chart = await _build_trend_chart(session, [], {}, hours=168)

    assert chart == {"timeline": [], "outcomes": []}
    assert session.calls == 0, "an empty grid must not query at all"
