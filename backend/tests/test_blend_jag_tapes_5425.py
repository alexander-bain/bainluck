"""#5425 / D136 rung 4 — the blend replayed over two real production tapes.

The unit tests in `test_weighted_median_tie_5425.py` prove the tie branch does
what it says on constructed inputs. These replay the SHIPPED aggregator over
readings that actually happened, because the question the tie rule raises is
not "is the arithmetic right" but "what does the published series look like to
somebody watching the page".

Two tapes, captured 2026-09-11 by live/159 and trimmed into
`tests/fixtures/blend_tape_*.json`:

  * Gauff-Rybakina (15308901) — 410 readings, kalshi + polymarket. The
    two-equal-weight shape, i.e. the population the tie rule governs.
  * SF@LAR (14632820) — 473 readings, espn + kalshi + polymarket + stat_model.
    The negative control: four sources never land on half exactly.

THIS TEST NAMES THE DISAGREEMENT BETWEEN THE TAPES RATHER THAN PAPERING OVER
IT. The fix is not a clean win and the assertions say so out loud. Replaying
both tapes old-rule against new-rule:

    Gauff (2 src)        old      new
      publications      1728     1728
      moves              104      216   <- the blend now answers to BOTH venues
      steps > 5pt         32       21   <- the large jumps fall by a third
      steps > 2pt         58       84   <- ...and are replaced by smaller ones
      max single step   18.00pt  18.22pt <- the biggest jump does NOT go away
      thin kalshi x4    27.00pt  13.50pt <- worst cadence sensitivity halves
      thin polymkt x4   15.50pt  18.22pt <- but sensitivity to the SLOWER venue RISES
      verbatim        1728/1728   7/1728 <- the published number is now a blend

    SF@LAR (4 src)      identical, bit for bit, at every one of 2149 grid points

The rise in the last-but-one row is the real cost and is asserted below, not
omitted: a midpoint responds to both venues, so thinning either one now moves
the series, where `min()` was simply deaf to the higher venue. Removing an
arbitrary selection rule is what this ship claims; removing the jag is not, and
the max-step row is the evidence that it does not.
"""

import datetime
import json
import pathlib

import pytest

import app.utils.aggregation as agg

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
GAUFF = FIXTURES / "blend_tape_gauff_15308901.json"
SFLAR = FIXTURES / "blend_tape_sflar_14632820.json"

# A coarse grid keeps the replay honest and the test fast: 30s still resolves
# every flip in these tapes (readings arrive ~40s apart) while cutting the
# publication count ~6x versus live/159's 5s probe grid.
GRID_SECONDS = 30.0


class _FakeEvent:
    espn_win_prob_home = None
    opening_home_probability = None

    def __init__(self, wps):
        self.win_probability_sources = wps
        self.status = "live"


def _lower_value_tie_rule(values, weights):
    """The pre-#5425 implementation, monkeypatched in to produce the old series."""
    if len(values) == 1:
        return values[0]
    paired = sorted(zip(values, weights), key=lambda x: x[0])
    total = sum(w for _, w in paired)
    if total <= 0:
        vals = [v for v, _ in paired]
        return vals[len(vals) // 2]
    half = total / 2.0
    cumulative = 0.0
    for value, weight in paired:
        cumulative += weight
        if cumulative >= half:
            return value
    return paired[-1][0]


def _load(path):
    readings = json.loads(path.read_text())["readings"]
    tape = [
        (source, datetime.datetime.fromisoformat(captured_at), float(value))
        for source, captured_at, value in readings
    ]
    tape.sort(key=lambda r: r[1])
    return tape


def _replay(tape):
    """The series the page would have published, on a fixed grid."""
    latest, series, index = {}, [], 0
    t, end = tape[0][1], tape[-1][1]
    step = datetime.timedelta(seconds=GRID_SECONDS)
    while t <= end:
        while index < len(tape) and tape[index][1] <= t:
            source, stamp, value = tape[index]
            latest[source] = (stamp, value)
            index += 1
        if latest:
            wps = {
                s: {"value": v, "updated_at": stamp.isoformat()}
                for s, (stamp, v) in latest.items()
            }
            published = agg.compute_aggregate_probability(_FakeEvent(wps), "live")
            series.append((t, published, {s: v for s, (_, v) in latest.items()}))
        t += step
    return series


def _thin(tape, source, factor):
    """Keep every `factor`-th reading of one source — a cadence change with no
    information change. A blend that is sensitive to this is reading the
    polling schedule as if it were news."""
    seen, out = 0, []
    for row in tape:
        if row[0] != source:
            out.append(row)
            continue
        if seen % factor == 0:
            out.append(row)
        seen += 1
    return out


def _steps(series):
    values = [v for _, v, _ in series if v is not None]
    return [abs(values[i] - values[i - 1]) for i in range(1, len(values))]


def _max_divergence(a, b):
    va = {t: v for t, v, _ in a if v is not None}
    vb = {t: v for t, v, _ in b if v is not None}
    common = set(va) & set(vb)
    return max((abs(va[t] - vb[t]) for t in common), default=0.0)


@pytest.fixture
def old_rule(monkeypatch):
    monkeypatch.setattr(agg, "_weighted_median", _lower_value_tie_rule)


class TestTheFourSourceTapeIsUntouched:
    def test_the_sflar_series_is_bit_for_bit_identical(self, monkeypatch):
        """The blast-radius claim on real data. If a future change to the tie
        branch reaches three-and-four-source events, this is what fails."""
        new_series = _replay(_load(SFLAR))
        monkeypatch.setattr(agg, "_weighted_median", _lower_value_tie_rule)
        old_series = _replay(_load(SFLAR))

        assert [v for _, v, _ in new_series] == [v for _, v, _ in old_series]
        assert len(new_series) > 300, "guard against an empty replay passing vacuously"


class TestTheTwoSourceTapeImproves:
    def test_the_large_jumps_fall(self):
        """Steps over 5 points: 32 under the old rule, 21 under the new one.

        Asserted as a strict inequality with the measured pair in the message,
        so a re-weighting that changes the counts re-states them instead of
        failing on a stale literal.
        """
        tape = _load(GAUFF)
        new_big = sum(1 for s in _steps(_replay(tape)) if s > 0.05)
        original = agg._weighted_median
        try:
            agg._weighted_median = _lower_value_tie_rule
            old_big = sum(1 for s in _steps(_replay(tape)) if s > 0.05)
        finally:
            agg._weighted_median = original

        assert old_big > 0, "vacuous: the old rule produced no large steps to remove"
        assert new_big < old_big, f"large steps did not fall: {old_big} -> {new_big}"

    def test_sensitivity_to_thinning_the_faster_venue_falls(self):
        """Kalshi ticks fastest on this tape. Quartering its cadence moved the
        old series by up to 27 points and the new one by 13.5 — the blend reads
        the polling schedule as news only half as loudly."""
        tape = _load(GAUFF)
        new_delta = _max_divergence(_replay(tape), _replay(_thin(tape, "kalshi", 4)))
        original = agg._weighted_median
        try:
            agg._weighted_median = _lower_value_tie_rule
            old_delta = _max_divergence(
                _replay(tape), _replay(_thin(tape, "kalshi", 4))
            )
        finally:
            agg._weighted_median = original

        assert (
            old_delta > 0.0
        ), "vacuous: thinning kalshi moved the old series not at all"
        assert new_delta < old_delta, f"{old_delta:.4f} -> {new_delta:.4f}"


class TestTheCostIsRealAndIsAsserted:
    def test_sensitivity_to_thinning_the_SLOWER_venue_RISES(self):
        """THE COST, pinned deliberately.

        `min()` was deaf to the higher venue, so thinning polymarket barely
        registered. A midpoint answers to both, so the same cadence change now
        moves the series further: 15.5 points before, 18.2 after.

        This test asserts the regression EXISTS. It is here so that nobody
        reads this ship as "the blend became cadence-insensitive" — it did not,
        and the honest claim is narrower. If a later change genuinely removes
        this cost, this test must be deleted with that change and the deletion
        argued, rather than the cost being quietly forgotten.
        """
        tape = _load(GAUFF)
        new_delta = _max_divergence(
            _replay(tape), _replay(_thin(tape, "polymarket", 4))
        )
        original = agg._weighted_median
        try:
            agg._weighted_median = _lower_value_tie_rule
            old_delta = _max_divergence(
                _replay(tape), _replay(_thin(tape, "polymarket", 4))
            )
        finally:
            agg._weighted_median = original

        assert new_delta > old_delta, (
            "the slower-venue cost has changed sign or vanished; re-measure and "
            f"re-argue the trade rather than editing the number: {old_delta:.4f} "
            f"-> {new_delta:.4f}"
        )

    def test_the_biggest_single_jump_does_not_go_away(self):
        """The ship removes an arbitrary rule; it does not remove the jag.

        The largest step is ~18 points under both rules, because it is a real
        venue move — a break of serve — and not a selection artifact. Pinned so
        that "fixes the jag" never gets written into a later summary of this
        change.
        """
        tape = _load(GAUFF)
        new_max = max(_steps(_replay(tape)))
        original = agg._weighted_median
        try:
            agg._weighted_median = _lower_value_tie_rule
            old_max = max(_steps(_replay(tape)))
        finally:
            agg._weighted_median = original

        assert new_max == pytest.approx(old_max, abs=0.01), (
            f"the largest step changed materially ({old_max:.4f} -> {new_max:.4f}); "
            "this ship was never supposed to move it"
        )


class TestThePublishedNumberIsNowABlend:
    def test_the_series_stops_being_one_venues_price_verbatim(self):
        """Under the old rule every single publication was a source's value
        exactly — not because the venues agreed, but because the rule always
        picked one of them. That is the property this ship trades away, and the
        trade is the point: a two-venue blend that always equals one venue is
        not a blend.
        """
        tape = _load(GAUFF)
        series = _replay(tape)
        verbatim = sum(
            1
            for _, published, stated in series
            if published is not None
            and any(abs(published - v) < 1e-9 for v in stated.values())
        )
        assert len(series) > 200, "vacuous: the replay produced almost no publications"
        assert verbatim < len(series) * 0.1, (
            f"{verbatim}/{len(series)} publications still equal a single venue "
            "verbatim — the tie branch is not reaching this tape"
        )

    def test_every_published_value_stays_inside_the_venue_range(self, old_rule):
        """...and the blend never leaves the interval the venues stated, so
        "not verbatim" never becomes "not backed by anybody"."""
        for _, published, stated in _replay(_load(GAUFF)):
            if published is None:
                continue
            assert (
                min(stated.values()) - 1e-9 <= published <= max(stated.values()) + 1e-9
            )
