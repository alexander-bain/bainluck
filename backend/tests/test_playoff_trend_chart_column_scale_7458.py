"""#7458, second half — the chart must also run the table's LAST stage.

``bf8744402`` made the trend chart de-vig each venue and blend every venue that
prices a team, and that closed NBA, NHL and NFL to 0.00pt. EPL and MLB did not
move, and the reason was not the one first recorded.

The legend/table ratio is a CONSTANT across every club in the league — EPL
x1.140, MLB x1.052, measured on production 2026-09-20 — and a constant ratio is
a column rescale, not a per-venue vig decision. ``normalize_column_sums`` scales
a championship column that sums outside ``[0.85, 1.05]`` back onto 1.0; the
chart is built from snapshots afterwards and never saw it. So EPL published
Arsenal at 47.50% in the legend and 41.67% in the table, on one phone screen.

Why these guards are shaped the way they are:

* The specimen is a league where the scale actually BITES. An NBA-shaped column
  sums to 0.9961 — inside the dead band — so its scale is 1.0 and every
  assertion about scaling passes whether or not the scaling exists. That is the
  same vacuous-control mistake that let the first attempt look complete: OKC's
  venues coincided, so an OKC-shaped specimen could not tell the blend from one
  venue. Here the in-band league is kept as an explicit NO-OP control instead.

* The expected numbers are computed BY HAND from the production column
  (``0.4750 / 1.14 = 0.4167``), not from the functions under test, so the guard
  cannot agree with a wrong implementation of itself.

* One test pins the SHAPE, because the tempting per-bucket version of this fix
  is wrong: the policy has a hard threshold at 1.05 and MLB's column sits at
  1.0524, so a per-bucket factor would snap on and off and draw ~5pt steps no
  market ever moved.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.playoffs import _build_trend_chart
from app.utils.playoff_grid import column_scale_factor, normalize_column_sums


# ---------------------------------------------------------------------------
# The production specimen, transcribed: EPL, kalshi-only, column sums to 1.14
# ---------------------------------------------------------------------------

#: Read off production 2026-09-20. kalshi is the only source on this column, and
#: it publishes a probability, so ``devig_consensus`` correctly leaves each value
#: alone (#6675) — the whole overround survives into the chart.
_EPL_RAW = {
    "Arsenal": 0.4750,
    "Manchester City": 0.4050,
    "Chelsea": 0.0450,
    "Liverpool": 0.0350,
}
#: The other 16 clubs, collapsed into one never-drawn sibling. It carries the
#: column to its real sum: without it the denominator is 0.96 and the scale
#: comes out the wrong side of 1.0 entirely.
_EPL_FIELD = 0.180
_EPL_COLUMN_SUM = 1.14

#: Hand-computed: raw / 1.14, rounded to 4dp the way a cell is. These are the
#: numbers production's TABLE actually serves.
_EPL_TABLE = {
    "Arsenal": 0.4167,
    "Manchester City": 0.3553,
    "Chelsea": 0.0395,
    "Liverpool": 0.0307,
}

#: An NBA-shaped column: sums to 0.9961, inside the dead band, scale 1.0.
_NBA_RAW = {"Oklahoma City Thunder": 0.2150, "San Antonio Spurs": 0.2150}
_NBA_FIELD = 0.5661

_KALSHI_MARKET = 52755651
_FIELD_OUTCOME = 299


def _ids(raw: dict) -> dict[str, int]:
    """One outcome id per drawn club, stable within a test."""
    return {name: 200 + i for i, name in enumerate(raw)}


class _Row(SimpleNamespace):
    pass


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, market_ids, rows):
        self._market_ids = [(m,) for m in market_ids]
        self._rows = rows
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        if self.calls == 1:
            return _FakeResult(self._market_ids)
        return _FakeResult(self._rows)


def _rows(raw: dict, field: float, *, buckets: int = 6, drift: float = 0.0):
    """kalshi writes its whole column in one pass, once an hour.

    ``drift`` moves the drawn clubs bucket to bucket so a shape assertion has
    something to be a shape OF; the field absorbs it so the column sum — and
    therefore the scale — stays put.
    """
    ids = _ids(raw)
    now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    out = []
    for bucket in range(buckets):
        captured = now - timedelta(hours=bucket)
        step = drift * bucket
        moved = 0.0
        for name, probability in raw.items():
            moved += step
            out.append(_Row(
                outcome_id=ids[name], market_id=_KALSHI_MARKET,
                bookmaker="kalshi", captured_at=captured,
                probability=probability + step,
            ))
        out.append(_Row(
            outcome_id=_FIELD_OUTCOME, market_id=_KALSHI_MARKET,
            bookmaker="kalshi", captured_at=captured,
            probability=field - moved,
        ))
    out.sort(key=lambda r: r.captured_at, reverse=True)
    return out


def _teams(raw: dict):
    return [
        {"name": name, "cells": {"championship": {
            "merged_probability": probability,
            "sources": [{"source": "kalshi", "probability": probability}],
        }}}
        for name, probability in raw.items()
    ]


class _Col:
    key = "championship"


async def _chart(raw, field, scale, **kw):
    session = _FakeSession([_KALSHI_MARKET], _rows(raw, field, **kw))
    names = {i: n for n, i in _ids(raw).items()}
    return await _build_trend_chart(
        session, list(names), names, hours=168, column_scale=scale,
    )


def _legend(chart, name):
    for entry in chart["outcomes"]:
        if entry["name"] == name:
            return entry["current_probability"]
    raise AssertionError(f"{name} is not in the legend: {chart['outcomes']}")


# ---------------------------------------------------------------------------
# The policy itself
# ---------------------------------------------------------------------------


def test_the_dead_band_is_left_alone():
    """A column whose sources already agree is never nudged."""
    assert column_scale_factor(0.9961, 1.0) == 1.0, "NBA's real column sum"
    assert column_scale_factor(1.0369, 1.0) == 1.0, "NHL's real column sum"
    assert column_scale_factor(0.85, 1.0) == 1.0
    assert column_scale_factor(1.05, 1.0) == 1.0


def test_an_overshooting_column_is_scaled_onto_its_expected_sum():
    assert column_scale_factor(1.14, 1.0) == pytest.approx(1 / 1.14)
    # MLB sits a hair over the threshold — 1.0524 — and must still scale, or the
    # 1.47pt gap this fixes reappears for exactly one league.
    assert column_scale_factor(1.0524, 1.0) == pytest.approx(1 / 1.0524)


def test_an_undershooting_column_is_scaled_up():
    assert column_scale_factor(0.80, 1.0) == pytest.approx(1.25)


def test_a_column_over_two_and_a_half_times_expected_is_a_bug_not_a_distribution():
    """Scaling it would hide a matching defect behind a plausible shape."""
    assert column_scale_factor(3.0, 1.0) == 1.0
    assert column_scale_factor(2.6, 1.0) == 1.0
    # ...but just under the ceiling is still a normalization.
    assert column_scale_factor(2.4, 1.0) == pytest.approx(1 / 2.4)


def test_expected_sums_other_than_one_are_honoured():
    """A conference column expects 2.0 — two winners."""
    assert column_scale_factor(2.0, 2.0) == 1.0
    assert column_scale_factor(2.5, 2.0) == pytest.approx(0.8)


def test_a_column_with_no_expected_sum_or_no_probability_is_untouched():
    assert column_scale_factor(1.14, 0) == 1.0
    assert column_scale_factor(0.0, 1.0) == 1.0


# ---------------------------------------------------------------------------
# The two surfaces now share that policy
# ---------------------------------------------------------------------------


def test_normalize_column_sums_reports_the_factor_it_applied():
    """The chart takes this number rather than recomputing it.

    A second copy of ``expected / col_sum`` would agree today and drift the
    first time a threshold moves, which is the defect being fixed, one level up.
    """
    teams = _teams({**_EPL_RAW, "The rest": _EPL_FIELD})

    applied = normalize_column_sums(teams, [_Col()], "epl")

    assert applied["championship"] == pytest.approx(1 / _EPL_COLUMN_SUM)
    # And it is the factor the cells actually carry, not just a reported one.
    arsenal = teams[0]["cells"]["championship"]["merged_probability"]
    assert arsenal == _EPL_TABLE["Arsenal"]


def test_an_in_band_column_reports_no_factor():
    teams = _teams({**_NBA_RAW, "The rest": _NBA_FIELD})

    applied = normalize_column_sums(teams, [_Col()], "nba")

    assert "championship" not in applied, (
        "reporting 1.0 and reporting 'policy declined' are different facts"
    )
    assert teams[0]["cells"]["championship"]["merged_probability"] == 0.2150


@pytest.mark.asyncio
async def test_the_epl_legend_publishes_the_same_number_as_the_epl_table():
    """The production defect: 47.50% in the legend, 41.67% in the table.

    Both halves are built here the way production builds them — the table
    through ``normalize_column_sums``, the chart through ``_build_trend_chart``
    — and both are checked against the hand-computed 0.4750/1.14.
    """
    teams = _teams({**_EPL_RAW, "The rest": _EPL_FIELD})
    applied = normalize_column_sums(teams, [_Col()], "epl")

    chart = await _chart(_EPL_RAW, _EPL_FIELD, applied["championship"])

    for name, expected in _EPL_TABLE.items():
        cell = next(
            t["cells"]["championship"]["merged_probability"]
            for t in teams if t["name"] == name
        )
        assert cell == expected, f"table cell for {name}"
        assert _legend(chart, name) == expected, (
            f"{name}: legend {_legend(chart, name)} vs table {expected} — the "
            "chart is skipping the column normalization the table applies"
        )


@pytest.mark.asyncio
async def test_without_the_factor_the_legend_is_the_raw_overround():
    """The strawman: this is what the chart published before the fix.

    Without this, every assertion above would also pass against an
    implementation that ignored ``column_scale`` and happened to be handed 1.0.
    """
    chart = await _chart(_EPL_RAW, _EPL_FIELD, 1.0)

    assert _legend(chart, "Arsenal") == pytest.approx(0.4750), (
        "the unscaled chart must still be reproducible, or this file is not "
        "testing the scaling at all"
    )
    assert _legend(chart, "Arsenal") != _EPL_TABLE["Arsenal"]


@pytest.mark.asyncio
async def test_an_in_band_league_is_not_rescaled_by_this_change():
    """The no-op control: NBA/NHL/NFL were already at 0.00pt and must stay.

    A fix that over-applies — scaling every league onto 1.0 — would move three
    leagues that are currently correct, and the gap would reopen with the sign
    flipped.
    """
    teams = _teams({**_NBA_RAW, "The rest": _NBA_FIELD})
    applied = normalize_column_sums(teams, [_Col()], "nba")

    chart = await _chart(_NBA_RAW, _NBA_FIELD, applied.get("championship", 1.0))

    assert _legend(chart, "Oklahoma City Thunder") == pytest.approx(0.2150)
    assert _legend(chart, "San Antonio Spurs") == pytest.approx(0.2150)


@pytest.mark.asyncio
async def test_the_factor_rescales_the_level_and_leaves_the_shape_alone():
    """Why one scalar and not a per-bucket sum.

    A per-bucket factor crossing the 1.05 threshold would inject a step into
    every series that no market ever moved — the same class of lie as the flat
    line this issue's other half was about. A single scalar cannot: every
    bucket-to-bucket ratio survives it unchanged.
    """
    unscaled = await _chart(_EPL_RAW, _EPL_FIELD, 1.0, drift=0.004)
    scaled = await _chart(
        _EPL_RAW, _EPL_FIELD, 1 / _EPL_COLUMN_SUM, drift=0.004,
    )

    before = [b["outcomes"]["Arsenal"] for b in unscaled["timeline"]]
    after = [b["outcomes"]["Arsenal"] for b in scaled["timeline"]]

    assert len(set(before)) > 1, "a flat series cannot evidence a shape claim"
    assert len(before) == len(after)
    for b, a in zip(before, after):
        assert a == pytest.approx(b / _EPL_COLUMN_SUM, abs=1e-4)
    # No step: consecutive deltas keep their ratio to one another.
    for i in range(1, len(before)):
        assert (after[i] - after[i - 1]) == pytest.approx(
            (before[i] - before[i - 1]) / _EPL_COLUMN_SUM, abs=1e-4
        )


@pytest.mark.asyncio
async def test_a_scaled_value_is_still_capped_at_one():
    """Scaling UP a dominant favourite must not publish 103%.

    The table caps its cells; a legend that did not would print an impossible
    number beside a possible one.
    """
    chart = await _chart({"Arsenal": 0.90}, 0.10, 2.0)

    assert _legend(chart, "Arsenal") == 1.0
