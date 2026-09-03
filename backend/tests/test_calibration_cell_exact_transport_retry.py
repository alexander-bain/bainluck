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
