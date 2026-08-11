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
    """
    from app.utils import request_cache as _rc
    from app.utils import candidate_base as _cb

    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    _cb._reset_l0_for_tests()
    yield
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    _cb._reset_l0_for_tests()


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
