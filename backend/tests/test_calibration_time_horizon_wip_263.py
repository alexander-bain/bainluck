"""Queue #263 Item 2 — the resumable horizon WIP accumulator must be version-fenced.

Before #263 the WIP was a bare ``{label: data}`` dict with no population fingerprint,
so after a population change (a version bump) a partial run left over from the OLD
population would be RESUMED — its stale horizons skipped from recompute and
republished under the new version. #263 wraps the WIP with ``population_version`` and
rejects legacy-unwrapped / corrupt / mismatched accumulators on load, so a horizon
computed under an older population is always recomputed, never resumed.

These are pure-helper tests against ``_load_time_horizon_wip`` / ``_save_time_horizon_wip``
(the heavy task loop is exercised end-to-end on production after deploy)."""

import json

import pytest

from app.tasks.precompute_calibration import (
    CALIBRATION_POPULATION_VERSION,
    _HORIZONS,
    _TIME_HORIZON_WIP_KEY,
    _load_time_horizon_wip,
    _save_time_horizon_wip,
)

_V = CALIBRATION_POPULATION_VERSION
_LABELS = [label for label, _ in _HORIZONS]


class _FakeRedis:
    """Minimal Redis stand-in for get/set/delete of the WIP key."""

    def __init__(self, initial=None):
        self.store: dict = {}
        if initial is not None:
            self.store[_TIME_HORIZON_WIP_KEY] = initial

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def _horizon(label, version=_V):
    """A minimal current-shape horizon entry (carries its population_version)."""
    return {
        "total_outcomes": 500,
        "total_winners": 250,
        "mce": 3.0,
        "population_version": version,
    }


class TestLoadRejectsStalePopulations:
    def test_missing_key_is_empty(self):
        assert _load_time_horizon_wip(_FakeRedis()) == {}

    def test_legacy_unwrapped_accumulator_recomputes(self):
        # The pre-#263 shape: a bare {label: data} dict with no wrapper.
        legacy = json.dumps({"T-30": {"total_outcomes": 500}, "T-7": {"total_outcomes": 400}})
        assert _load_time_horizon_wip(_FakeRedis(legacy)) == {}

    def test_corrupt_json_recomputes(self):
        assert _load_time_horizon_wip(_FakeRedis("{not json")) == {}

    def test_version_mismatched_wrapper_recomputes(self):
        stale = json.dumps({
            "population_version": "q000",
            "horizons": {"T-30": _horizon("T-30", version="q000")},
        })
        assert _load_time_horizon_wip(_FakeRedis(stale)) == {}

    def test_mixed_version_horizon_entries_dropped(self):
        # Wrapper is current but one horizon entry is stamped an old version — that
        # one is dropped (recomputed), the current ones survive. Belt-and-braces.
        mixed = json.dumps({
            "population_version": _V,
            "horizons": {
                "T-30": _horizon("T-30", version=_V),
                "T-7": _horizon("T-7", version="q000"),
            },
        })
        loaded = _load_time_horizon_wip(_FakeRedis(mixed))
        assert set(loaded) == {"T-30"}

    def test_unknown_labels_are_ignored(self):
        wrapped = json.dumps({
            "population_version": _V,
            "horizons": {"T-30": _horizon("T-30"), "BOGUS": _horizon("BOGUS")},
        })
        assert set(_load_time_horizon_wip(_FakeRedis(wrapped))) == {"T-30"}


class TestCurrentPopulationResumes:
    def test_current_partial_resumes(self):
        wrapped = json.dumps({
            "population_version": _V,
            "horizons": {"T-30": _horizon("T-30"), "T-7": _horizon("T-7")},
        })
        loaded = _load_time_horizon_wip(_FakeRedis(wrapped))
        assert set(loaded) == {"T-30", "T-7"}
        assert loaded["T-30"]["population_version"] == _V

    def test_current_complete_resumes_all_four(self):
        wrapped = json.dumps({
            "population_version": _V,
            "horizons": {label: _horizon(label) for label in _LABELS},
        })
        loaded = _load_time_horizon_wip(_FakeRedis(wrapped))
        assert set(loaded) == set(_LABELS)


class TestSaveWrapsWithVersion:
    def test_save_wraps_and_round_trips(self):
        rc = _FakeRedis()
        result = {label: _horizon(label) for label in _LABELS[:2]}
        _save_time_horizon_wip(rc, result)
        raw = rc.get(_TIME_HORIZON_WIP_KEY)
        parsed = json.loads(raw)
        assert parsed["population_version"] == _V
        assert set(parsed["horizons"]) == set(_LABELS[:2])
        # A load of what we just saved returns the same current horizons.
        assert set(_load_time_horizon_wip(rc)) == set(_LABELS[:2])

    def test_save_is_best_effort_on_redis_failure(self):
        class _BoomRedis:
            def set(self, *a, **k):
                raise RuntimeError("redis down")

        # Must not raise — WIP persistence is best-effort like the publish helper.
        _save_time_horizon_wip(_BoomRedis(), {"T-30": _horizon("T-30")})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
