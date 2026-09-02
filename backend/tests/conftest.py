"""Shared test fixtures for the Bain Luck backend test suite."""

import json

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.pulse import PulseDataPoint


@pytest.fixture(autouse=True)
def _reset_request_cache_state():
    """Isolate the process-local request-cache primitives (Queue 271).

    ``app.utils.request_cache`` keeps a process-global last-good store + in-flight
    singleflight registry. Without a reset they leak across tests (e.g. one
    calibration/feed test's last-good bleeding into the next). Cheap and safe.

    Also resets the Discover candidate-ID base process cache (Queue 285): the feed
    publishes a candidate base from the request path on a cold build, which stores
    it in ``candidate_base._l0``. Without a reset, one seeded feed test's base
    (its market IDs) would be served to the next test's differently-seeded DB.

    CAL-P076 adds ``calibration._staged_cache`` (#2007), which is the same class
    of hazard one file over: it is a process-global memo of the staged bank's
    as-of, it decides whether ``/api/calibration`` may say ``fresh``, and its TTL
    outlives a test. Leaked, one test's healthy bank makes the next test's frozen
    one invisible — and that direction is the reassuring one.

    LAT-P174 adds ``principal_independent_cache``'s process-local store, for the
    same reason as the candidate base one paragraph up and now with teeth: since
    the hydrated candidate ROWS are shared there, and its key is a digest of the
    candidate ID set, two tests that seed markets with the same IDs and different
    CONTENT are one cache entry. ``test_feed_fused_broaden_pass.py`` reuses IDs
    1-6 across tests with different ``updated_at`` and went red on exactly that.
    In production the TTL bounds this (the IDs really do identify the rows, and
    60s is tighter than the response cache above it); in a test suite nothing
    bounds it, because nothing takes 60 seconds.
    """
    from app.utils import request_cache as _rc
    from app.utils import candidate_base as _cb
    from app.utils.principal_independent_cache import clear_shared_builds

    def _reset_staged():
        from app.routes import calibration as _cal

        _cal._staged_cache["data"] = None
        _cal._staged_cache["timestamp"] = 0.0

    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    _cb._reset_l0_for_tests()
    clear_shared_builds()
    _reset_staged()
    yield
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    _cb._reset_l0_for_tests()
    clear_shared_builds()
    _reset_staged()


@pytest.fixture
def healthy_staged_bank():
    """#2007 / CAL-P076 — declare that the staged futures bank is fine.

    ``/api/calibration`` may not answer ``fresh`` unless the payload discloses
    when its futures bank was last staged and how far the roster has drifted
    under it (ruling (b): *"'fresh' may not render while drift is undisclosed"*).
    A route test that mocks the database with one row therefore gets an
    UNMEASURED disclosure and a ``stale`` answer — correct behaviour, and nothing
    to do with what most of those tests are about.

    So a test asserting ``fresh`` for some other reason declares this. It seeds
    the memo rather than the rows, deliberately: the read is exercised by
    ``test_calibration_staged_disclosure_p076.py`` and re-mocking it in every
    sibling suite would spread the disclosure's shape across files that do not
    care about it.
    """
    import time as _time

    from app.routes import calibration as _cal

    _cal._staged_cache["data"] = {
        "measured": True,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "staged_age_s": 120,
        "units_banked": 128,
        "units_this_beat": 9,
        "units_drifted": 0,
        "units_drift_checkable": 128,
        "units_drift_unknown": 0,
        "units_drifted_as_of": datetime.now(timezone.utc).isoformat(),
        "bank_advanced_this_beat": True,
        "frozen_over_drift": False,
    }
    _cal._staged_cache["timestamp"] = _time.time()
    yield
    _cal._staged_cache["data"] = None
    _cal._staged_cache["timestamp"] = 0.0


@pytest.fixture
def game_start():
    """A game start time for testing."""
    return datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def current_time(game_start):
    """A current time 2 hours after game start."""
    return game_start + timedelta(hours=2)


@pytest.fixture
def make_snapshots(game_start):
    """Factory for creating PulseDataPoint lists.

    Usage:
        snapshots = make_snapshots([0.50, 0.55, 0.48, 0.52], interval_seconds=60)
    """
    def _make(probabilities, interval_seconds=60, bookmaker="consensus"):
        return [
            PulseDataPoint(
                captured_at=game_start + timedelta(seconds=i * interval_seconds),
                home_win_probability=p,
                bookmaker=bookmaker,
            )
            for i, p in enumerate(probabilities)
        ]
    return _make


@pytest.fixture
def make_multi_bookmaker_snapshots(game_start):
    """Factory for creating multi-bookmaker snapshots at same timestamps.

    Usage:
        snapshots = make_multi_bookmaker_snapshots([
            [0.50, 0.51, 0.49],  # 3 bookmakers at t=0
            [0.55, 0.56, 0.54],  # 3 bookmakers at t=60s
        ])
    """
    def _make(prob_groups, interval_seconds=60):
        bookmakers = ["fanduel", "draftkings", "betmgm", "caesars", "pointsbet"]
        snapshots = []
        for i, probs in enumerate(prob_groups):
            t = game_start + timedelta(seconds=i * interval_seconds)
            for j, p in enumerate(probs):
                snapshots.append(PulseDataPoint(
                    captured_at=t,
                    home_win_probability=p,
                    bookmaker=bookmakers[j % len(bookmakers)],
                ))
        return snapshots
    return _make


# ---------------------------------------------------------------------------
# Queue 330 — reading the unavailable answer at the boundary it is served on
# ---------------------------------------------------------------------------


def unavailable_body(result) -> dict:
    """Assert ``result`` is the typed 503 and return its SERIALIZED body.

    ``/api/calibration`` used to signal "nothing to serve" by raising
    ``HTTPException(detail={...})``, and the suite read ``exc.value.detail`` — a
    Python attribute on an exception object, one layer above anything a client
    can see. That boundary is why B1's audit of Queue 324 found a defect the
    branch's own 112 green tests could not: FastAPI nests ``detail`` on the wire,
    so ``availability`` sat at ``detail.availability`` on the refusal and at the
    top level on all four served answers, and no test that stops at the exception
    could observe the difference. A suite that only calls the code the way the
    code expects to be called cannot audit a wire contract.

    The route now composes the response, so the honest read is the JSON body it
    will actually put on the socket. This decodes exactly that.
    """
    from fastapi.responses import JSONResponse

    assert isinstance(result, JSONResponse), (
        f"expected the typed unavailable response, got {type(result).__name__}"
    )
    assert result.status_code == 503
    return json.loads(bytes(result.body))
