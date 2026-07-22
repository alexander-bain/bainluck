"""Queue #228 Item 1 (#1171): the time-horizon calibration task must never strand
the /api/calibration/time-horizon endpoint on the "computing" placeholder.

Root cause: the served main key was published ONLY after all four horizons
completed in one accumulated WIP run. A single persistently-slow horizon (the
statement_timeout poison T-0, or an OOM SIGKILL mid-run) killed the task before
that publish, so the endpoint returned "computing" forever.

Fix (pure helpers tested here): publish whatever horizons are computed after EACH
one lands, as an honest PARTIAL payload — so the endpoint serves 3/4 horizons
instead of nothing. The full task loop is exercised end-to-end against production
after deploy (the live-proof gate)."""

import json

from app.tasks.precompute_calibration import (
    _HORIZONS,
    _publish_time_horizon,
    _time_horizon_payload,
)


class _FakeRedis:
    """Minimal Redis stand-in capturing set() calls."""

    def __init__(self):
        self.store: dict = {}

    def set(self, key, value, ex=None):
        self.store[key] = value


def _one_horizon():
    return {"T-30": {"total_outcomes": 500, "total_winners": 250, "mce": 3.1}}


class TestTimeHorizonPayload:
    def test_partial_is_flagged_with_missing(self):
        payload = _time_horizon_payload(_one_horizon())
        assert payload["complete"] is False
        # every horizon except the one computed is reported missing
        assert set(payload["missing"]) == {lbl for lbl, _ in _HORIZONS} - {"T-30"}
        assert "T-30" in payload["horizons"]

    def test_complete_when_all_horizons_present(self):
        full = {label: {"mce": 1.0} for label, _ in _HORIZONS}
        payload = _time_horizon_payload(full)
        assert payload["complete"] is True
        assert payload["missing"] == []

    def test_shape_is_backward_compatible(self):
        payload = _time_horizon_payload(_one_horizon())
        # historical keys the endpoint/frontend already consume
        assert "horizons" in payload
        assert "description" in payload
        assert "generated_at" in payload


class TestPublishTimeHorizon:
    def test_publishes_partial_to_served_key(self):
        rc = _FakeRedis()
        _publish_time_horizon(rc, _one_horizon())
        raw = rc.store.get("bainluck:calibration:time_horizon")
        assert raw is not None  # the endpoint's key IS set on a partial (#1171)
        served = json.loads(raw)
        assert served["complete"] is False
        assert "T-30" in served["horizons"]

    def test_empty_result_publishes_nothing(self):
        rc = _FakeRedis()
        _publish_time_horizon(rc, {})
        # never overwrite a good cache with an empty placeholder
        assert "bainluck:calibration:time_horizon" not in rc.store

    def test_publish_never_raises_on_redis_failure(self):
        class _BoomRedis:
            def set(self, *a, **k):
                raise RuntimeError("redis down")

        # best-effort: a publish failure must not propagate and kill the task
        _publish_time_horizon(_BoomRedis(), _one_horizon())
