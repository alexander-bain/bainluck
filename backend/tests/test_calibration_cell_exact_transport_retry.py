"""CAL-P991 — a dropped connection must not discard a completed sweep.

THE DEFECT THIS PINS. ``db_query``'s retry loop caught exactly one exception,
``urllib.error.HTTPError``. A dropped connection does not raise that — it raises
``http.client.RemoteDisconnected`` or ``ConnectionResetError``, both of which are
SIBLINGS of ``HTTPError``, not subclasses. So they escaped the loop, unwound the
sweep, and threw away every chunk already folded. Measured 2026-09-02 on three of
the largest cells on the board (``polymarket/soccer``, ``polymarket/tennis``, and
rank 1's holdout half): each lost 20+ minutes of completed work to one blip.

WHY IT IS A RETRY AND NOT A SPLIT. ``QueryTimeout`` means the server cancelled the
statement, so the range is known to be too wide and the fix is to narrow it. A
transport failure means the server never got to say anything at all — nothing was
learned about the range, so re-asking the SAME range is the correct response. The
two must not be conflated, and the ordering of the ``except`` clauses is what keeps
them apart: ``HTTPError`` IS a ``URLError`` subclass, so if the transport arm were
written first it would swallow the ``statement_timeout`` that tells the caller to
split. ``test_a_statement_timeout_still_raises_rather_than_retrying`` is the guard
on that ordering, and it is the one that would fail SILENTLY — the sweep would
still finish, having quietly retried a too-wide range three times and then given
up, instead of bisecting it.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import urllib.error
from io import BytesIO
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


class _Resp:
    """The minimal shape ``db_query`` reads: ``.read()`` returning JSON bytes."""

    def __init__(self, payload: dict) -> None:
        self._b = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._b


def _http_error(body: dict) -> urllib.error.HTTPError:
    raw = json.dumps(body).encode()
    return urllib.error.HTTPError(
        "http://x/api/admin/db-query", 400, "Bad Request", {}, BytesIO(raw)
    )


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("BAINLUCK_API", "http://x")
    monkeypatch.setenv("ADMIN_TOKEN", "t")
    monkeypatch.setattr(cce.time, "sleep", lambda _s: None)


def _urlopen_returning(monkeypatch, sequence):
    """Each call pops the next item; an exception instance is raised, else returned."""
    calls = {"n": 0}

    def fake(_req, timeout=None):
        item = sequence[calls["n"]]
        calls["n"] += 1
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(cce.urllib.request, "urlopen", fake)
    return calls


class TestATransportFailureIsRetriedOnTheSameRange:
    def test_remote_disconnected_retries_and_then_succeeds(self, env, monkeypatch):
        calls = _urlopen_returning(monkeypatch, [
            http.client.RemoteDisconnected("closed"),
            _Resp({"rows": [[1]]}),
        ])
        assert cce.db_query("SELECT 1") == {"rows": [[1]]}
        assert calls["n"] == 2, "the second attempt is the whole point"

    def test_connection_reset_retries_and_then_succeeds(self, env, monkeypatch):
        calls = _urlopen_returning(monkeypatch, [
            ConnectionResetError(54, "Connection reset by peer"),
            _Resp({"rows": []}),
        ])
        assert cce.db_query("SELECT 1") == {"rows": []}
        assert calls["n"] == 2

    def test_url_error_retries_and_then_succeeds(self, env, monkeypatch):
        calls = _urlopen_returning(monkeypatch, [
            urllib.error.URLError(ConnectionResetError(54, "reset")),
            _Resp({"rows": []}),
        ])
        assert cce.db_query("SELECT 1") == {"rows": []}
        assert calls["n"] == 2

    def test_it_gives_up_loudly_rather_than_looping_forever(self, env, monkeypatch):
        calls = _urlopen_returning(
            monkeypatch, [http.client.RemoteDisconnected("closed")] * 3
        )
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            cce.db_query("SELECT 1")
        assert calls["n"] == 3


class TestTheSplitSignalSurvivesTheNewArm:
    """The SILENT one. Both of these still pass if the arms are ordered wrong —
    except that a ``statement_timeout`` would come back as a ``RuntimeError``
    after three pointless retries instead of the ``QueryTimeout`` the sweep
    bisects on, so the range would never be narrowed."""

    def test_a_statement_timeout_still_raises_rather_than_retrying(
        self, env, monkeypatch
    ):
        calls = _urlopen_returning(monkeypatch, [
            _http_error({"detail": {"error": "query_failed",
                                    "reason": "statement_timeout"}}),
        ])
        with pytest.raises(cce.QueryTimeout):
            cce.db_query("SELECT 1")
        assert calls["n"] == 1, "a too-wide range must be split, never re-asked"

    def test_http_error_is_a_urlerror_so_clause_order_is_load_bearing(self):
        assert issubclass(urllib.error.HTTPError, urllib.error.URLError)
        assert urllib.error.URLError in cce._TRANSPORT_ERRORS

    def test_a_non_timeout_http_error_still_retries_as_before(self, env, monkeypatch):
        calls = _urlopen_returning(monkeypatch, [
            _http_error({"detail": {"error": "boom"}}),
            _Resp({"rows": [[7]]}),
        ])
        assert cce.db_query("SELECT 1") == {"rows": [[7]]}
        assert calls["n"] == 2


class TestTheThrottleIsATHIRDShapeAndOutlastsItsWindow:
    """CAL-P991: ``429 Rate limit exceeded: 300/minute`` with a ``retry_after``.

    Measured 2026-09-03: this arrived as a plain ``HTTPError``, took the generic
    2/4/6 s backoff, and killed a 29-minute fold inside one 60-second window
    with every completed chunk discarded. It is neither a timeout (the range was
    never judged, so splitting is wrong) nor a transport failure (the server
    answered, and told us how long to wait).
    """

    @staticmethod
    def _throttle(retry_after=21):
        raw = json.dumps({"detail": "Rate limit exceeded: 300/minute",
                          "retry_after": retry_after}).encode()
        return urllib.error.HTTPError(
            "http://x/api/admin/db-query", 429, "Too Many Requests", {},
            BytesIO(raw))

    def test_a_throttle_waits_the_servers_own_retry_after(self, env, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(cce.time, "sleep", slept.append)
        calls = _urlopen_returning(monkeypatch, [
            self._throttle(21), _Resp({"rows": [[1]]}),
        ])
        assert cce.db_query("SELECT 1") == {"rows": [[1]]}
        assert calls["n"] == 2
        assert slept == [22.0], (
            "the generic 2/4/6 backoff is shorter than the window being waited "
            "out; honouring retry_after is the whole repair"
        )

    def test_a_throttle_does_not_consume_the_failure_retry_budget(
        self, env, monkeypatch
    ):
        """Four throttles then success — more throttles than ``retries``."""
        calls = _urlopen_returning(monkeypatch, [
            self._throttle(), self._throttle(), self._throttle(),
            self._throttle(), _Resp({"rows": [[9]]}),
        ])
        assert cce.db_query("SELECT 1", retries=3) == {"rows": [[9]]}
        assert calls["n"] == 5

    def test_a_sustained_throttle_still_gives_up_rather_than_looping_forever(
        self, env, monkeypatch
    ):
        calls = _urlopen_returning(
            monkeypatch, [self._throttle()] * 40)
        with pytest.raises(RuntimeError, match="db-query failed"):
            cce.db_query("SELECT 1", retries=3)
        # Bounded: THROTTLE_MAX_WAITS free re-asks, then the ordinary budget.
        assert calls["n"] <= cce.THROTTLE_MAX_WAITS + 3

    def test_a_malformed_throttle_body_still_waits_rather_than_hot_looping(self):
        assert cce._retry_after_seconds("Rate limit exceeded") == 30.0
        assert cce._retry_after_seconds(
            '{"detail": "429 Too Many Requests"}') == 1.0

    def test_a_statement_timeout_is_not_read_as_a_throttle(self, env, monkeypatch):
        """The control. The split signal must survive the new arm."""
        assert cce._retry_after_seconds(
            '{"detail": {"reason": "statement_timeout"}}') is None
        calls = _urlopen_returning(monkeypatch, [
            _http_error({"detail": {"reason": "statement_timeout"}}),
        ])
        with pytest.raises(cce.QueryTimeout):
            cce.db_query("SELECT 1")
        assert calls["n"] == 1

    def test_the_throttle_predicate_is_the_one_the_sharded_folds_use(self):
        """Two copies of this predicate is one copy that goes stale."""
        import sys
        from pathlib import Path as _P
        sys.path.insert(0, str(_P(cce.__file__).resolve().parent))
        import sharded_sweep

        assert cce.is_throttle is sharded_sweep.is_throttle
