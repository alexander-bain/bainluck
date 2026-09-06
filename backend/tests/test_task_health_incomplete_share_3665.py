"""#3665 — a task that loses half its passes to teardown stops reading green.

`prediction_market_match` was measured on 2026-09-06 at 24 incompletes against
20 successes over an 11.7h window and reported `health: "healthy"`, because
health keyed off `consecutive_failures` (an interrupt is deliberately not a
failure) and, since Queue 300H, off the verdict of the single most recent run.
On a task that alternates between finishing and being torn down by a release,
that last band is a coin flip: it says "degraded" or "healthy" about one
unchanging steady state depending on which pass happened to end last.

These tests pin the two halves of the repair:

* the share is computed from WINDOW-NORMALISED rates, because the four `_24h`
  counters each open at their own first increment and a raw quotient compares
  two different spans of history (`precompute_discover_candidate_base`, same
  afternoon: 22 successes over 2.0h against 24 incompletes over 23.8h — raw
  0.52, normalised 0.09, and only the second is true); and
* an unmeasurable window produces no share and no band, rather than falling
  back to the raw counts this module refuses.
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
#: Both counters carry nearly a full day, so normalising barely moves the raw
#: quotient (0.545 → 0.505) — which is exactly why this task is the real finding
#: and `precompute_discover_candidate_base` below is not.
_MATCHER = {
    "successes": (20, 35888.0),
    "incompletes": (24, 42176.0),
    "starts": (44, 41914.0),
}

#: Same afternoon, same surface, opposite verdict: a task whose success counter
#: had rolled two hours earlier. Raw share 0.52, normalised 0.09.
_ROLLED_SUCCESS_WINDOW = {
    "successes": (22, 7353.0),
    "incompletes": (24, 85653.0),
    "starts": (46, 85653.0),
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
        assert "51%" in reason  # window-normalised, not the raw 55%

    def test_a_healthy_task_with_one_interrupt_stays_green(self, monkeypatch):
        result = _metrics(
            monkeypatch, "espn_sync",
            {"successes": (774, 57960.0), "incompletes": (36, 46313.0),
             "starts": (810, 57960.0)},
        )
        assert result["health"] == "healthy"
        assert result["incomplete_share"] < 0.1


class TestTheShareIsNormalisedByEachCountersOwnWindow:
    def test_a_rolled_success_window_is_not_slander(self, monkeypatch):
        """Raw arithmetic calls this task half-dead. It is not: its success
        counter rolled two hours ago and it has been finishing ~11 passes an
        hour ever since."""
        result = _metrics(
            monkeypatch, "precompute_discover_candidate_base",
            _ROLLED_SUCCESS_WINDOW,
        )
        raw = 24 / (22 + 24)
        assert raw > redis_state._INCOMPLETE_BAND_DEGRADED_SHARE
        assert result["incomplete_share"] < 0.15
        assert result["health"] == "healthy"

    def test_the_basis_is_stated_on_the_payload(self, monkeypatch):
        result = _metrics(monkeypatch, "prediction_market_match", _MATCHER)
        assert result["incomplete_share_basis"] == "window-normalised terminal rates"

    def test_no_incompletes_is_a_measured_zero(self, monkeypatch):
        result = _metrics(
            monkeypatch, "poll_odds",
            {"successes": (469, 57728.0), "failures": (13, 1517.0),
             "starts": (483, 57728.0)},
        )
        assert result["incomplete_share"] == 0.0
        assert result["health"] == "healthy"


class TestAnUnmeasurableWindowRefusesToBand:
    @pytest.mark.parametrize("rolled", ["successes", "incompletes"])
    def test_a_window_with_no_expiry_produces_no_share(self, monkeypatch, rolled):
        counters = dict(_MATCHER)
        counters[rolled] = (counters[rolled][0], None)  # ttl -1: no expiry
        result = _metrics(monkeypatch, "prediction_market_match", counters)
        assert result["incomplete_share"] is None
        assert "unmeasurable" in result["incomplete_share_basis"]
        # No share, so no band — and specifically not a band derived from the
        # raw counts, which here would read 0.55 and degrade the task.
        assert result["health"] == "healthy"
        assert "health_reason" not in result

    def test_a_young_window_is_not_yet_a_rate(self, monkeypatch):
        """Five teardowns inside twenty minutes is a deploy, not a steady
        state. The share is published; the band is not applied."""
        result = _metrics(
            monkeypatch, "prediction_market_match",
            {"successes": (20, 35888.0), "incompletes": (5, 1200.0),
             "starts": (25, 35888.0)},
        )
        assert result["incomplete_share"] > 0.25
        assert result["health"] == "healthy"

    def test_below_the_evidence_floor_the_share_is_published_not_banded(
        self, monkeypatch,
    ):
        """`espn_win_prob_backfill`, same afternoon: 2 successes, 2 incompletes.
        A share of 0.33 over four runs is one release, and banding it would put
        a quarter of the beat schedule permanently amber."""
        result = _metrics(
            monkeypatch, "espn_win_prob_backfill",
            {"successes": (2, 29525.0), "incompletes": (2, 60748.0),
             "starts": (4, 29525.0)},
        )
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
