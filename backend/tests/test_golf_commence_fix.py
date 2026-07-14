"""Queue #189 Item 2: guardrails for the resurrected _fix_golf_commence_times.

The DataGolf-winner lookup used ``external_id LIKE '%:win'`` inside a text()
string; SQLAlchemy parses the ``:win`` as an unbound bind parameter (asyncpg
:param gotcha), so every call raised "value required for bind parameter 'win'"
and the fix had NEVER run. These tests lock in the bind fix and the
verify-before-enable dry-run gate (default OFF, gotcha #21) so it cannot
blind-rewrite ~1.7K resolved golf markets on deploy.
"""

import inspect

import pytest

from app.tasks import kalshi


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _MockSession:
    """Serves canned SELECT results in order; records every statement issued."""

    def __init__(self, results, log):
        self._results = list(results)
        self._i = 0
        self._log = log

    async def execute(self, stmt, params=None):
        self._log.append(str(stmt))
        if self._i < len(self._results):
            r = self._results[self._i]
            self._i += 1
            return r
        return _Result([])

    async def commit(self):
        self._log.append("COMMIT")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def test_datagolf_query_binds_win_suffix():
    # Regression guard for the unbound-:win bug: the buggy literal must be gone
    # and the pattern passed as a bound parameter.
    src = inspect.getsource(kalshi._fix_golf_commence_times)
    assert "LIKE '%:win'" not in src, "unbound :win literal reintroduced"
    assert ":win_suffix" in src


def test_flag_defaults_off_and_parses_redis(monkeypatch):
    import app.tasks.redis_state as rs

    class _RC:
        def __init__(self, v):
            self._v = v

        def get(self, _k):
            return self._v

    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: _RC(b"1"))
    assert kalshi._golf_commence_fix_enabled() is True
    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: _RC(b"0"))
    assert kalshi._golf_commence_fix_enabled() is False
    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: _RC(None))
    assert kalshi._golf_commence_fix_enabled() is False

    def _boom(*a, **k):
        raise RuntimeError("no redis")

    monkeypatch.setattr(rs, "get_redis_client", _boom)
    assert kalshi._golf_commence_fix_enabled() is False


@pytest.mark.asyncio
async def test_dry_run_never_writes(monkeypatch):
    from datetime import datetime, timezone

    import app.routes.golf as golf_mod

    # One resolved Kalshi golf market whose commence would move via the Tier-3
    # heuristic (name normalizes to "other" -> no DataGolf key match).
    market = _Row(
        id=42,
        name="Some Obscure Open",
        commence_time=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
    )
    sess_dg = _MockSession([_Result([])], log := [])
    sess_markets = _MockSession([_Result([market])], log)
    sessions = iter([sess_dg, sess_markets])

    monkeypatch.setattr(kalshi, "get_task_session", lambda: next(sessions))
    monkeypatch.setattr(golf_mod, "_get_golf_schedule", _async_none)
    monkeypatch.setattr(golf_mod, "_normalize_tournament", lambda *a, **k: "other")

    # Explicit dry_run wins regardless of the flag.
    fixed = await kalshi._fix_golf_commence_times(dry_run=True)

    assert fixed == 1  # counted as would-fix
    assert not any("UPDATE" in s for s in log), "dry-run must not UPDATE"
    assert "COMMIT" not in log, "dry-run must not commit"


async def _async_none(*a, **k):
    return None
