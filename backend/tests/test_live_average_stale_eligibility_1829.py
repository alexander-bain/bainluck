"""#1829 follow-through — stale-input eligibility for the LIVE weighted average.

Alex, 2026-10-10: "Keep the weighted average and strengthen stale-input
eligibility." #10764 replaced the live hero's weighted median with a weighted
average of the same decayed, capped weights. A median only needed a stale arm
to stop straddling the midpoint; an average lets every unit of weight pull by
value. The rule, as `_live_average_inputs` implements it:

  1. An arm whose stamp is ``HERO_RELATIVE_GRACE_SECONDS +
     HERO_RELATIVE_DECAY_SECONDS`` (40 min) or more behind the freshest stamped
     sibling carries ZERO weight in the live average (the chart's live floor),
     not the hero's 0.1 median floor. Inside the ramp it keeps its partial
     weight, unchanged.
  2. An undated arm (no ``updated_at``, or one that does not parse) carries zero
     weight when at least two dated arms are present. With fewer than two dated
     arms nothing is refused: one clock cannot rank anyone.

Pre-game, completed, suspended and ``final_result`` events keep the weighted
median and are untouched. Every timestamp below is a literal (gotcha #44).
"""

from datetime import datetime, timezone

import pytest

from app.utils.aggregation import (
    HERO_RELATIVE_DECAY_SECONDS,
    HERO_RELATIVE_GRACE_SECONDS,
    TimestampedProb,
    _weighted_average,
    cap_weight_shares,
    compute_aggregate_probability,
    compute_aggregated_probability,
    effective_source_weights_detailed,
)
from app.utils.probability_eligibility import (
    ELIGIBILITY_KEY,
    INELIGIBLE,
    EligibilityRecord,
)
from tests.test_probability_recency_and_cap import (
    SPECIMEN_STAMPED,
    SPECIMEN_VALUES,
    T0,
    _FakeEvent,
    _stamped,
)

WINDOW = HERO_RELATIVE_GRACE_SECONDS + HERO_RELATIVE_DECAY_SECONDS


def _hero(sources, status="live"):
    return compute_aggregate_probability(_FakeEvent(sources, status))


def _plain_average(**values):
    """The #10764 average over base weights with the share cap, no refusals."""
    from app.utils.aggregation import SOURCE_WEIGHTS

    keys = list(values)
    weights = cap_weight_shares([SOURCE_WEIGHTS[k] for k in keys])
    return round(_weighted_average([values[k] for k in keys], weights), 6)


# ── The retained specimen, replayed ──────────────────────────────────────────


class TestTheBlueJaysSpecimenReplay:
    """Event 15192596, top of the 9th, Toronto trailing 0-5 (final 0-7)."""

    def test_stamped_live_reads_95_5(self):
        home = _hero(SPECIMEN_STAMPED)
        assert home == pytest.approx(0.049069, abs=1e-6)
        assert (round((1 - home) * 100), round(home * 100)) == (95, 5)

    def test_stamped_live_drops_the_day_old_kalshi_price_entirely(self):
        """kalshi 0.565 was stamped the PREVIOUS day. Under the #10764 average it
        still pulled at the 0.1 floor (0.060397 -> 94/6); now it carries nothing,
        so the hero equals the same bag with kalshi deleted."""
        without_kalshi = {k: v for k, v in SPECIMEN_STAMPED.items() if k != "kalshi"}
        assert _hero(SPECIMEN_STAMPED) == _hero(without_kalshi)

        # The before, computed rather than remembered: the hero-floor weights
        # the average used until this change.
        _keys, values, weights, floored = effective_source_weights_detailed(
            _FakeEvent(SPECIMEN_STAMPED), "live"
        )
        assert floored == {"kalshi"}
        assert round(_weighted_average(values, weights), 6) == pytest.approx(
            0.060397, abs=1e-6
        )

    def test_the_residual_pull_is_an_arm_inside_the_ramp_not_past_it(self):
        """What 95/5 is made of, so nobody reads it as the rule failing.

        `betting` (0.1347) is 24m58s behind stat_model and `espn` (0.008) is
        26m00s behind: both sit inside the 10-40 minute ramp at about half
        weight. The timestamps cannot tell the frozen sportsbook from the
        correct ESPN model, so no recency rule refuses one and keeps the other.
        The sportsbook's one-book quote is handled writer-side by ruling 051
        (`BETTING_BOOK_FLOOR`), which removes `betting` entirely.
        """
        stamps = {
            k: datetime.fromisoformat(v["updated_at"])
            for k, v in SPECIMEN_STAMPED.items()
        }
        freshest = max(stamps.values())
        for key in ("betting", "espn"):
            age = (freshest - stamps[key]).total_seconds()
            assert HERO_RELATIVE_GRACE_SECONDS < age < WINDOW, (key, age)

        no_betting = {k: v for k, v in SPECIMEN_STAMPED.items() if k != "betting"}
        assert _hero(no_betting) == pytest.approx(0.003123, abs=1e-6)

    def test_unstamped_live_is_unchanged_at_88_12(self):
        """MISSING TIME, explicit: with no clock on any arm nothing can be ranked,
        so the bag averages exactly as #10764 accepted it. This is the legacy
        shape; every writer has stamped since 2026-08-14."""
        home = _hero(dict(SPECIMEN_VALUES))
        assert home == pytest.approx(0.120991, abs=1e-6)
        assert (round((1 - home) * 100), round(home * 100)) == (88, 12)
        assert home == _plain_average(**SPECIMEN_VALUES)

    @pytest.mark.parametrize("status", ["completed", "suspended", "scheduled"])
    @pytest.mark.parametrize("shape", ["stamped", "unstamped"])
    def test_non_live_statuses_keep_the_median(self, status, shape):
        """The pre-#10764 answer on every shape: the capped median lands on espn."""
        sources = SPECIMEN_STAMPED if shape == "stamped" else dict(SPECIMEN_VALUES)
        assert _hero(sources, status) == pytest.approx(0.008, abs=1e-9)


# ── Rule 1: the 40-minute boundary ───────────────────────────────────────────


class TestTheStaleBoundary:
    def test_fresh_inputs_are_the_plain_average(self):
        """FRESH CONTROL: every arm stamped at the same instant refuses nothing,
        and reads exactly what #10764's undated average reads."""
        values = {"betting": 0.9, "espn": 0.1, "mlb": 0.12}
        fresh = _stamped(**{k: (v, 0) for k, v in values.items()})
        assert _hero(fresh) == _plain_average(**values)
        assert _hero(fresh) == _hero(dict(values))

    def test_uniformly_old_inputs_are_still_the_plain_average(self):
        values = {"betting": 0.9, "espn": 0.1, "mlb": 0.12}
        old = _stamped(**{k: (v, 7200) for k, v in values.items()})
        assert _hero(old) == _plain_average(**values)

    def test_an_arm_at_the_window_leaves(self):
        at = _stamped(betting=(0.9, WINDOW), espn=(0.1, 0), mlb=(0.12, 0))
        assert _hero(at) == _plain_average(espn=0.1, mlb=0.12)

    def test_an_arm_just_inside_the_window_still_counts(self):
        inside = _stamped(betting=(0.9, WINDOW - 60), espn=(0.1, 0), mlb=(0.12, 0))
        assert _hero(inside) > _plain_average(espn=0.1, mlb=0.12)

    def test_an_arm_inside_the_grace_keeps_full_weight(self):
        graced = _stamped(
            betting=(0.9, HERO_RELATIVE_GRACE_SECONDS), espn=(0.1, 0), mlb=(0.12, 0)
        )
        assert _hero(graced) == _plain_average(betting=0.9, espn=0.1, mlb=0.12)

    def test_the_freshest_arm_can_never_leave(self):
        for behind in (0, WINDOW, 86400):
            lone = _stamped(betting=(0.9, 0), espn=(0.1, behind), mlb=(0.12, behind))
            assert _hero(lone) is not None


# ── Rule 2: missing time ─────────────────────────────────────────────────────


class TestMissingTime:
    def test_an_undated_arm_beside_two_dated_ones_leaves(self):
        mixed = {
            "betting": 0.9,
            **_stamped(espn=(0.1, 0), mlb=(0.12, 0)),
        }
        assert _hero(mixed) == _plain_average(espn=0.1, mlb=0.12)

    def test_a_malformed_stamp_is_undated(self):
        malformed = {
            "betting": {"value": 0.9, "updated_at": "not-a-date"},
            **_stamped(espn=(0.1, 0), mlb=(0.12, 0)),
        }
        assert _hero(malformed) == _plain_average(espn=0.1, mlb=0.12)

    def test_one_clock_refuses_nobody(self):
        """With one dated arm among bare ones that arm would be "freshest" by
        default; refusing the bare ones would hand it the whole hero. On the
        specimen that would be the day-old kalshi 0.565."""
        one_dated = dict(SPECIMEN_VALUES)
        one_dated["kalshi"] = SPECIMEN_STAMPED["kalshi"]
        assert _hero(one_dated) == _hero(dict(SPECIMEN_VALUES))
        assert _hero(one_dated) != pytest.approx(0.565)

    def test_no_clock_anywhere_refuses_nobody(self):
        bare = {"betting": 0.9, "espn": 0.1, "mlb": 0.12}
        assert _hero(bare) == _plain_average(**bare)


# ── What the rule must not disturb ───────────────────────────────────────────


class TestPreservedBehaviour:
    def test_a_positive_refusal_still_removes_the_arm(self):
        refused = {
            **_stamped(espn=(0.1, 0), mlb=(0.12, 0)),
            "betting": {
                "value": 0.9,
                "updated_at": T0.isoformat(),
                ELIGIBILITY_KEY: EligibilityRecord(status=INELIGIBLE).to_entry(),
            },
        }
        assert _hero(refused) == _plain_average(espn=0.1, mlb=0.12)

    def test_the_divergence_gate_still_runs_first(self):
        """A broken two-source pair renders its primary, never an average."""
        pair = _stamped(betting=(0.65, 2400), kalshi=(0.05, 0))
        assert _hero(pair) == pytest.approx(0.05)
        fresh_pair = _stamped(betting=(0.65, 0), kalshi=(0.05, 0))
        assert _hero(fresh_pair) == pytest.approx(0.65)

    def test_final_result_keeps_the_median(self):
        settled = {
            **_stamped(betting=(0.9, WINDOW), espn=(0.1, 0), mlb=(0.12, 0)),
            "final_result": 1.0,
        }
        assert _hero(settled) == pytest.approx(1.0)


# ── One number per question: the headline and the chart edge ────────────────


class TestHeroEqualsTheLiveChartEdge:
    def _series(self, stamped):
        return {
            key: [
                TimestampedProb(
                    timestamp=datetime.fromisoformat(entry["updated_at"]),
                    home_probability=entry["value"],
                )
            ]
            for key, entry in stamped.items()
        }

    def test_on_the_specimen(self):
        """The chart's live buckets already ended the ramp at zero; the hero now
        does too, so the two agree on a game with a lapsed arm. Under the 0.1
        floor this read hero 0.060397 against edge 0.049069."""
        line = compute_aggregated_probability(
            self._series(SPECIMEN_STAMPED), bucket_seconds=30, live_blend=True
        )
        assert line[-1].timestamp == datetime(2026, 8, 13, 21, 33, 30, tzinfo=timezone.utc)
        assert _hero(SPECIMEN_STAMPED) == pytest.approx(
            line[-1].home_probability, abs=1e-6
        )

    @pytest.mark.parametrize("behind", [0, 900, 1800, WINDOW - 60, WINDOW, 7200])
    def test_across_the_ramp(self, behind):
        stamped = _stamped(betting=(0.9, behind), espn=(0.1, 0), mlb=(0.12, 30))
        line = compute_aggregated_probability(
            self._series(stamped), bucket_seconds=30, live_blend=True
        )
        assert _hero(stamped) == pytest.approx(line[-1].home_probability, abs=1e-6)


def test_the_specimen_clock_is_a_literal():
    assert T0 == datetime(2026, 8, 13, 21, 33, 34, tzinfo=timezone.utc)
