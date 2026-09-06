"""#3665 — a task that loses half its passes to teardown stops reading green.

`prediction_market_match` was measured on 2026-09-06 at 24 incompletes against
20 successes over an 11.7h window and reported `health: "healthy"`, because
health keyed off `consecutive_failures` (an interrupt is deliberately not a
failure) and, since Queue 300H, off the verdict of the single most recent run.
On a task that alternates between finishing and being torn down by a release,
that last band is a coin flip: it says "degraded" or "healthy" about one
unchanging steady state depending on which pass happened to end last.

These tests pin three things:

* the share is computed from WINDOW-NORMALISED rates, because the four `_24h`
  counters each open at their own first increment (`SET NX EX`, never
  refreshed) and a raw quotient compares two different spans of history;
* **the denominator is `starts`** — CERT-2127's BLOCK. Summing the three
  terminal rates instead lets an ordinary rollover silence the band: 24
  incompletes over 42,176s plus ONE success over a 60-second-old counter reads
  as 1 success/minute against 2 incompletes/hour, scores 0.033, and returns
  green on a task losing half its passes. `starts` is written once per run by
  the same `_tracked_run` wrapper that writes the incomplete; and
* the stability floor applies to EVERY positive count that reaches a
  denominator, and a term it refuses is DROPPED and named rather than counted
  as a small one — reading an unmeasurable success rate as a low one
  understates the share, which is the direction that hides the bug.
"""

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import TASK_METRICS_PREFIX, WINDOW_COUNTER_TTL


class _WindowedMetricsRedis:
    """Fake redis exposing counters WITH a measurable TTL.

    `_window_age_s` derives a counter's window age from that counter's own
    remaining TTL, so a fake with no `ttl()` reports every window as
    unmeasurable — which is the correct reading for it and useless for grading a
    rate. This one takes each counter as `(count, window_age_s)` and hands back
    the TTL that age implies.
    """

    def __init__(self, task, hash_fields=None, counters=None):
        self.task = task
        self.hash_fields = hash_fields or {}
        # counters: {"successes": (count, window_age_s | None), ...}
        self.counters = counters or {}

    def _label(self, key):
        return key.rsplit(":", 1)[-1]

    def hgetall(self, key):
        if self._label(key) != self.task:
            return {}
        return {k.encode(): str(v).encode() for k, v in self.hash_fields.items()}

    def get(self, key):
        entry = self.counters.get(self._label(key))
        return None if entry is None else str(entry[0]).encode()

    def ttl(self, key):
        entry = self.counters.get(self._label(key))
        if entry is None:
            return -2  # no such key
        age = entry[1]
        if age is None:
            return -1  # key exists with no expiry → unmeasurable, per contract
        return int(WINDOW_COUNTER_TTL - age)

    def lrange(self, _key, _start, _stop):
        return []

    def keys(self, _pattern):
        return [f"{TASK_METRICS_PREFIX}:{self.task}".encode()]


def _metrics(monkeypatch, task, counters, hash_fields=None):
    # An EMPTY metrics hash short-circuits `get_task_metrics` to
    # `{"status": "no_data"}` with no health at all, which is a different state
    # from the idle one these tests are about. Every specimen therefore carries
    # the field a tracked run always writes.
    fields = {"consecutive_failures": "0"} if hash_fields is None else hash_fields
    monkeypatch.setattr(
        redis_state,
        "get_redis_client",
        lambda: _WindowedMetricsRedis(task, fields, counters),
    )
    return redis_state.get_task_metrics(task)


#: The production specimen: `prediction_market_match`, read 2026-09-06 20:15Z.
#: 24 of 44 runs torn down; the two counters that matter carry nearly a full day
#: each and open within four minutes of one another.
_MATCHER = {
    "successes": (20, 35888.0),
    "incompletes": (24, 42176.0),
    "starts": (44, 41914.0),
}

#: CERT-2127's counterexample, and the reason the denominator is `starts`.
#: The same 24 incompletes, plus a success counter that rolled sixty seconds
#: ago. Summed as three terminal rates this reads 1 success/minute against 2
#: incompletes/hour — share 0.033, green, on a task losing half its passes.
_ROLLED_SUCCESS_COUNTER = {
    "successes": (1, 60.0),
    "incompletes": (24, 42176.0),
    "starts": (44, 41914.0),
}

#: The same rollover on a task with no usable `starts` counter at all, so the
#: fallback runs. The 60-second success term is DROPPED, not counted small.
_ROLLED_SUCCESS_NO_STARTS = {
    "successes": (1, 60.0),
    "incompletes": (24, 42176.0),
}

#: A mature healthy control, `espn_sync` on the same reading: every window a
#: full day old, 36 teardowns against 810 runs.
_MATURE_HEALTHY = {
    "successes": (774, 57960.0),
    "incompletes": (36, 46313.0),
    "starts": (810, 57960.0),
}


class TestTheMatcherStopsReadingGreen:
    def test_half_the_passes_torn_down_is_not_healthy(self, monkeypatch):
        result = _metrics(monkeypatch, "prediction_market_match", _MATCHER)
        assert result["health"] == "degraded"

    def test_the_verdict_does_not_flip_with_the_last_run(self, monkeypatch):
        """The whole defect: on 2026-09-06 the surface read healthy or degraded
        for the same steady state depending on which pass ended last. Both
        readings below now agree, and neither is the last run's."""
        survived = _metrics(
            monkeypatch, "prediction_market_match", _MATCHER,
            hash_fields={"last_verdict": "success", "consecutive_failures": "0"},
        )
        torn_down = _metrics(
            monkeypatch, "prediction_market_match", _MATCHER,
            hash_fields={"last_verdict": "partial", "consecutive_failures": "0"},
        )
        assert survived["health"] == torn_down["health"] == "degraded"

    def test_the_reason_names_teardown_and_not_a_failure_streak(self, monkeypatch):
        result = _metrics(
            monkeypatch, "prediction_market_match", _MATCHER,
            hash_fields={"last_verdict": "success"},
        )
        reason = result["health_reason"]
        assert "24" in reason and "torn down" in reason
        assert "54%" in reason  # 24 incompletes/42,176s over 44 starts/41,914s

    def test_a_healthy_task_with_one_interrupt_stays_green(self, monkeypatch):
        result = _metrics(monkeypatch, "espn_sync", _MATURE_HEALTHY)
        assert result["health"] == "healthy"
        assert result["incomplete_share"] < 0.1


class TestCert2127TheRolloverThatSilencedTheBand:
    """CERT-2127's BLOCK, which is the required regression.

    A denominator summing three independently-rolling terminal counters lets an
    ordinary rollover silence the band: 24 incompletes over 42,176s plus ONE
    success over a 60-second-old counter is 1 success/minute against 2
    incompletes/hour — 0.033, green. The denominator is now `starts`, which the
    same `_tracked_run` wrapper writes once per run alongside the incomplete.
    """

    def test_a_success_counter_that_rolled_a_minute_ago_cannot_hide_it(
        self, monkeypatch,
    ):
        result = _metrics(
            monkeypatch, "prediction_market_match", _ROLLED_SUCCESS_COUNTER,
            hash_fields={"last_verdict": "success", "consecutive_failures": "0"},
        )
        summed_terminal_rates = (24 / 42176.0) / (1 / 60.0 + 24 / 42176.0)
        assert summed_terminal_rates < 0.05  # the reading that was green
        assert result["incomplete_share"] > 0.5
        assert result["health"] == "degraded"

    def test_the_same_rollover_with_no_starts_counter_drops_the_term(
        self, monkeypatch,
    ):
        """The fallback must DROP a term it cannot rate, not count it as a
        small one. Counting it small is what produced the green reading."""
        result = _metrics(
            monkeypatch, "prediction_market_match", _ROLLED_SUCCESS_NO_STARTS,
            hash_fields={"last_verdict": "success", "consecutive_failures": "0"},
        )
        assert "dropped successes" in result["incomplete_share_basis"]
        assert result["incomplete_share"] == 1.0
        assert result["health"] == "degraded"

    def test_the_mature_rolled_healthy_control_stays_green(self, monkeypatch):
        """The other half of the required regression: the repair must not buy
        the rollover case by degrading everything with a stale window."""
        result = _metrics(
            monkeypatch, "espn_sync", _MATURE_HEALTHY,
            hash_fields={"last_verdict": "success", "consecutive_failures": "0"},
        )
        assert result["health"] == "healthy"
        assert "health_reason" not in result

    def test_the_stability_floor_covers_every_positive_count(self, monkeypatch):
        for label in ("successes", "failures", "incompletes", "starts"):
            assert redis_state._stable_rate(5, 60.0) is None, label
        assert redis_state._stable_rate(0, 60.0) == 0.0  # zero needs no window
        assert redis_state._stable_rate(5, None) is None
        assert redis_state._stable_rate(
            5, redis_state._TERMINAL_RATE_MIN_WINDOW_S,
        ) is not None


class TestTheShareIsNormalisedByEachCountersOwnWindow:
    def test_the_basis_is_stated_on_the_payload(self, monkeypatch):
        result = _metrics(monkeypatch, "prediction_market_match", _MATCHER)
        assert result["incomplete_share_basis"] == (
            "incompletes vs starts, each over its own window"
        )

    def test_the_raw_quotient_is_not_what_is_published(self, monkeypatch):
        """Both sides are divided by their own window before the quotient. On
        this specimen the two windows are close, so raw and normalised nearly
        agree — the point is that the arithmetic does not depend on that."""
        result = _metrics(monkeypatch, "prediction_market_match", _MATCHER)
        assert result["incomplete_share"] == pytest.approx(
            (24 / 42176.0) / (44 / 41914.0), rel=1e-3,
        )

    def test_a_share_above_one_is_clamped(self, monkeypatch):
        """Skewed windows can put the numerator's rate above the
        denominator's. A share above one is not a fact about the task."""
        result = _metrics(
            monkeypatch, "prediction_market_match",
            {"incompletes": (24, 4000.0), "starts": (26, 80000.0)},
        )
        assert result["incomplete_share"] == 1.0

    def test_no_incompletes_is_a_measured_zero(self, monkeypatch):
        result = _metrics(
            monkeypatch, "poll_odds",
            {"successes": (469, 57728.0), "failures": (13, 1517.0),
             "starts": (483, 57728.0)},
        )
        assert result["incomplete_share"] == 0.0
        assert result["health"] == "healthy"


class TestAnUnmeasurableWindowRefusesToBand:
    @pytest.mark.parametrize("rolled", ["incompletes", "starts"])
    def test_a_window_with_no_expiry_produces_no_usable_share(
        self, monkeypatch, rolled,
    ):
        counters = dict(_MATCHER)
        counters[rolled] = (counters[rolled][0], None)  # ttl -1: no expiry
        result = _metrics(monkeypatch, "prediction_market_match", counters)
        if rolled == "incompletes":
            # The numerator cannot be rated, so there is no share at all.
            assert result["incomplete_share"] is None
            assert result["health"] == "healthy"
            assert "health_reason" not in result
        else:
            # The denominator falls back to the terminal rates, all mature.
            assert "no usable starts counter" in result["incomplete_share_basis"]
            assert result["health"] == "degraded"

    def test_a_young_incompletes_window_is_not_yet_a_rate(self, monkeypatch):
        """Five teardowns inside twenty minutes is a deploy, not a steady
        state, and twenty minutes is too short to divide by."""
        result = _metrics(
            monkeypatch, "prediction_market_match",
            {"successes": (20, 35888.0), "incompletes": (5, 1200.0),
             "starts": (25, 35888.0)},
        )
        assert result["incomplete_share"] is None
        assert result["health"] == "healthy"

    def test_below_the_evidence_floor_the_share_is_published_not_banded(
        self, monkeypatch,
    ):
        """`espn_win_prob_backfill`, same afternoon: 2 incompletes over 4 runs.
        A share over four runs is one release, and banding it would put a
        quarter of the beat schedule permanently amber."""
        result = _metrics(
            monkeypatch, "espn_win_prob_backfill",
            {"successes": (2, 29525.0), "incompletes": (2, 40000.0),
             "starts": (4, 29525.0)},
        )
        # Above the band, so the EVIDENCE FLOOR is what stops it, not the share.
        assert result["incomplete_share"] > 0.25
        assert result["health"] == "healthy"


class TestTheExistingBandsStillWin:
    def test_a_failure_streak_still_reads_critical(self, monkeypatch):
        result = _metrics(
            monkeypatch, "prediction_market_match",
            {**_MATCHER, "failures": (6, 41914.0)},
            hash_fields={"consecutive_failures": "6"},
        )
        assert result["health"] == "critical"

    def test_an_idle_task_is_still_no_data(self, monkeypatch):
        result = _metrics(monkeypatch, "prediction_market_match", {})
        assert result["health"] == "no_data"
        assert result["incomplete_share"] == 0.0
