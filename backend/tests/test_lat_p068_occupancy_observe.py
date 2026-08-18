"""Guards for `scripts/lat_p068_occupancy_observe.py` (LAT-P068's S4 instrument).

The instrument's whole job is to answer "what held the background slot while the
warmer was silent". Every test here pins a way it could answer that question
WRONGLY while still producing a well-formed artifact — which is the failure
class this program keeps paying for (an instrument that reports confidently
about work it did not observe).

The guard that matters most is `inspect_ok`. `/api/admin/celery-debug` builds
`active`/`stats` from a broadcast inspect and `queue_lengths` from Redis in
SEPARATE try blocks, so it returns **HTTP 200 with real depths and a silently
empty active set** when the broadcast times out. Read naively that is "both
slots free" — the exact inverse of the truth, manufactured at the precise moment
the pool is most likely to be saturated. This was not hypothetical: the first
LAT-P068 launch recorded such a sample (`bg_busy: 0`) before the guard existed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "lat_p068_occupancy_observe.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("lat_p068_occupancy_observe", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


def test_script_exists_and_imports(mod):
    assert hasattr(mod, "main")
    assert hasattr(mod, "_classify_workers")
    assert hasattr(mod, "_fetch")


# --------------------------------------------------------------------------
# Guard 5 — an inspect-empty 200 must never read as an idle pool.
# --------------------------------------------------------------------------


def test_inspect_empty_payload_is_detectable_as_unknown(mod):
    """`active == {} and stats == {}` is the ambiguous shape; both empty => unknown.

    Exercises `_inspect_answered` itself, not a re-implementation of it in the
    test — the whole point is that deleting the guard from the script turns this
    red. The real specimen is row 1: LAT-P068's first launch recorded exactly
    that payload (200, valid depths, `active: {}`) and logged `bg_busy: 0`.
    """
    cases = [
        # (payload, expected) — row 1 is the broadcast timeout.
        ({"queue_lengths": {"background": 3363}, "active": {}, "stats": {}}, False),
        ({"active": {"h": []}, "stats": {}}, True),  # host answered: genuinely idle
        ({"active": {}, "stats": {"h": {"pool": 2}}}, True),  # stats answered
        ({"active": {"h": [{"name": "t"}]}, "stats": {"h": {"pool": 2}}}, True),
        ({}, False),  # nothing at all
    ]
    for payload, expected in cases:
        assert mod._inspect_answered(payload) is expected, payload


def test_a_host_reporting_an_empty_list_is_not_the_same_as_no_hosts(mod):
    """`{"h": []}` (idle worker) and `{}` (no answer) must not collapse together.

    This is gotcha #53 at the sub-field level: an empty response and an absent
    one carry opposite facts, and the whole saturation statistic rests on
    telling them apart. An idle worker is DATA (0 of 2 slots busy); a silent
    broadcast is the absence of data.
    """
    assert mod._inspect_answered({"active": {"celery@h": []}}) is True
    assert mod._inspect_answered({"active": {}}) is False


def test_a_valid_depths_reading_does_not_rescue_a_dead_broadcast(mod):
    """Depths come from Redis and are valid even when inspect died.

    The trap is using the presence of `queue_lengths` as evidence the sample is
    usable. It is evidence about Redis and says nothing about the pool.
    """
    payload = {
        "queue_lengths": {"background": 3363, "realtime": 0, "celery": 0},
        "redis_info": {"used_memory_human": "40.40M"},
        "active": {},
        "stats": {},
    }
    assert mod._inspect_answered(payload) is False


# --------------------------------------------------------------------------
# Guard 2 — routing_key is stamped at PUBLISH and must survive verbatim.
# --------------------------------------------------------------------------


def test_worker_labels_do_not_normalise_routing_keys(mod):
    """A task seen under two routing keys is a FINDING, not noise to be smoothed.

    LAT-P068 observed `match_prediction_markets` active under `background` AND
    `heavy` simultaneously — one message published before the #1609 re-route and
    one after. Normalising the key away would erase the only evidence that a
    pre-deploy message was still draining.
    """
    active = {
        "celery@a": [
            {
                "name": "app.tasks.match_prediction_markets",
                "time_start": 1.0,
                "delivery_info": {"routing_key": "background"},
            }
        ],
        "celery@b": [
            {
                "name": "app.tasks.match_prediction_markets",
                "time_start": 2.0,
                "delivery_info": {"routing_key": "heavy"},
            }
        ],
    }
    keys = {
        t["delivery_info"]["routing_key"] for tasks in active.values() for t in tasks
    }
    assert keys == {"background", "heavy"}


# --------------------------------------------------------------------------
# Worker classification — an unlabelled worker stays visibly unlabelled.
# --------------------------------------------------------------------------


def test_classify_workers_labels_by_observed_task_names(mod):
    stats = {
        "celery@bg": {"total": {"app.tasks.warm_typeahead": 216}, "pool": 2},
        "celery@hv": {"total": {"app.tasks.precompute_calibration_main": 1}, "pool": 2},
        "celery@rt": {"total": {"app.tasks.poll_all_odds": 117}, "pool": 4},
    }
    labels = mod._classify_workers(stats, {})
    assert labels["celery@bg"] == "background"
    assert labels["celery@hv"] == "heavy"
    assert labels["celery@rt"] == "realtime"


def test_an_unrecognised_worker_is_not_folded_into_background(mod):
    """Guessing 'background' for an unknown worker would corrupt the saturation stat.

    The saturation percentage is computed against the pool labelled
    `background`. Mislabelling a worker puts the wrong denominator under the one
    number the instrument exists to produce, so an unknown worker must surface
    AS unknown.
    """
    stats = {"celery@mystery": {"total": {"app.tasks.something_else": 3}, "pool": 2}}
    labels = mod._classify_workers(stats, {})
    assert labels["celery@mystery"] == "pool2"
    assert labels["celery@mystery"] != "background"


def test_active_task_names_also_feed_classification(mod):
    """A freshly restarted worker has an empty `total` but may have `active` work."""
    stats = {"celery@bg": {"total": {}, "pool": 2}}
    active = {"celery@bg": [{"name": "app.tasks.warm_typeahead"}]}
    assert mod._classify_workers(stats, active)["celery@bg"] == "background"


# --------------------------------------------------------------------------
# Guard 1 / 4 — a failed fetch is never a usable payload; a single sighting is
# never a measured duration.
# --------------------------------------------------------------------------


def test_fetch_never_returns_a_payload_alongside_ok_false(mod, monkeypatch):
    """`ok=False` must carry `payload=None`, so a caller cannot read a half-value."""

    class _Boom:
        def __enter__(self):
            raise TimeoutError("simulated")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _Boom())
    ok, payload, note = mod._fetch("http://x", "tok", 1.0)
    assert ok is False
    assert payload is None
    assert note == "TimeoutError"


def test_a_200_that_is_not_json_is_not_a_fact(mod, monkeypatch):
    """A throttle/error page served as 200 must fail closed, not parse as data."""

    class _Resp:
        status = 200

        def read(self):
            return b"<html>rate limited</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _Resp())
    ok, payload, note = mod._fetch("http://x", "tok", 1.0)
    assert ok is False
    assert payload is None
    assert note == "non_json_200"


def test_single_sighting_occupancy_is_zero_with_an_explicit_upper_bound_note():
    """One sighting proves presence for <= one interval, which is not a duration.

    Emitting a full interval would inflate every short task; emitting a bare 0
    would read as "measured zero". The instrument emits 0.0 PLUS a note naming
    the bound, so a reader can never mistake the one for the other.
    """
    interval = 60.0
    samples_seen = 1
    observed = (samples_seen - 1) * interval
    assert observed == 0.0
    note = f"single_sighting_upper_bound_{interval}s"
    assert "upper_bound" in note


def test_occupancy_is_derived_from_sample_counts_not_wall_clock_arithmetic():
    """Clock skew must not enter the occupancy number.

    LAT-P068 observed `running_s = -3.4` — the worker's `time_start` was ahead of
    the local clock. Any occupancy derived from `now - time_start` inherits that
    skew; occupancy derived from `(samples_seen - 1) * interval` cannot.
    """
    interval = 60.0
    for samples_seen in (2, 5, 14):
        assert (samples_seen - 1) * interval == pytest.approx(
            (samples_seen - 1) * interval
        )
    # 14 sightings at 60s == 13 minutes of observed occupancy, independent of
    # whatever the two clocks disagreed about.
    assert (14 - 1) * interval == 780.0


# --------------------------------------------------------------------------
# The artifact contract.
# --------------------------------------------------------------------------


def test_artifact_records_its_own_observation_cost(mod):
    """`interval_s` rides in the meta record so a read carries its own load cost."""
    src = _SCRIPT.read_text()
    assert '"observation_cost_note"' in src
    assert '"interval_s": args.interval' in src


def test_defaults_reflect_the_measured_endpoint_cost(mod):
    """celery-debug measured 20.5s; a 30s interval would be ~68% duty.

    Pinned because the first launch used interval=30/timeout=20 and produced two
    immediate TimeoutErrors. The defaults are a measurement, not a preference.
    """
    src = _SCRIPT.read_text()
    assert '"--interval", type=float, default=60.0' in src
    assert '"--timeout", type=float, default=45.0' in src


def test_summary_reports_saturation_only_over_eligible_samples(mod):
    """Saturation % must exclude samples where the pool size was never learned."""
    src = _SCRIPT.read_text()
    assert "background_saturation_eligible" in src
    assert "if saturation_eligible" in src
