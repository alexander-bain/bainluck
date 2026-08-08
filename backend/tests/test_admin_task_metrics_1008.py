"""#1008 — /api/admin/task-metrics must never answer about a task you didn't ask for.

The endpoint took `task_name` with a default of `"kalshi_settled"`, while every
known caller asks for `?task=`. FastAPI drops unknown query params silently, so
every `?task=<anything>` call fell through to the default and answered about
`kalshi_settled` — and the response body carried no task name to reveal it.

Verified on production 2026-08-07, before the fix:

    GET /api/admin/task-metrics?task=poll_kalshi_markets     -> 200 {}
    GET /api/admin/task-metrics?task=poll_polymarket_markets -> 200 {}
    GET /api/admin/task-metrics?task=precompute_calibration  -> 200 {}
    GET /api/admin/task-metrics?task=backfill_winners        -> 200 {}

...while the working per-task route showed those four are genuinely different:

    GET /api/admin/celery/task-metrics/backfill_winners
        -> {"task":"backfill_winners","successes_24h":1,"failures_24h":2,...}
    GET /api/admin/celery/task-metrics/poll_kalshi_markets
        -> {"task":"poll_kalshi_markets","status":"no_data"}

In July the same four returned a byte-identical *populated* record (437803ms,
SoftTimeLimitExceeded) because `kalshi_settled` held one then. Ops read that as a
poll_kalshi soft-limit and filed a round-120 alarm on a number that never
belonged to poll_kalshi.
"""

import inspect

import pytest


def _endpoint():
    from app.routes import admin_data_quality

    return admin_data_quality.get_task_metrics


def _effective_default(param):
    """The value FastAPI would use when the caller omits this query param.

    Params are declared as `Query(...)`, so `param.default` is a Query object
    whose own `.default` carries the value.
    """
    d = param.default
    return getattr(d, "default", d)


def _body_src():
    """Source of the handler with its docstring removed.

    The docstring documents the old `hgetall` implementation by name, so a naive
    substring check over the whole source matches the prose rather than the code.
    """
    src = inspect.getsource(_endpoint())
    parts = src.split('"""')
    return parts[0] + "".join(parts[2:]) if len(parts) >= 3 else src


def _call(**kwargs):
    """Invoke the async handler with a throwaway Request."""
    import asyncio

    from fastapi import Request

    req = Request({"type": "http", "headers": [], "method": "GET",
                   "path": "/", "query_string": b""})
    return asyncio.run(_endpoint()(request=req, secret="x", **kwargs))


class TestNoSilentDefault:
    """The defect was a default, not a lookup bug. The default has to go."""

    def test_signature_has_no_default_task(self):
        sig = inspect.signature(_endpoint())
        for param in ("task", "task_name"):
            assert param in sig.parameters, f"{param} must be accepted"
        # The bug was a DEFAULT, so assert on the defaults rather than on the
        # source text — the handler legitimately names kalshi_settled in its 400
        # hint, and a substring check cannot tell a helpful message from a trap.
        for param in ("task", "task_name"):
            assert _effective_default(sig.parameters[param]) is None, (
                f"{param} must have no default — omitting the task has to be an "
                "error, not a silent answer about some other task"
            )

    def test_task_param_is_accepted_not_ignored(self):
        """`?task=` was silently dropped; it must now be a real parameter."""
        sig = inspect.signature(_endpoint())
        assert sig.parameters["task"].annotation is str

    def test_task_name_still_accepted_for_back_compat(self):
        sig = inspect.signature(_endpoint())
        assert sig.parameters["task_name"].annotation is str


class TestDelegatesToTheCanonicalReader:
    """One definition of 'task metrics' across every surface.

    The hand-rolled hgetall skipped the 24h counters, the bytes decoding, the
    retired-task label and the explicit no_data marker that
    `/celery/task-metrics/{name}` and the cockpit tile all rely on.
    """

    def test_uses_redis_state_get_task_metrics(self):
        src = _body_src()
        assert "redis_state" in src
        assert "hgetall" not in src, (
            "must not hand-roll the read — that is how this surface drifted from "
            "the celery endpoint and the cockpit in the first place"
        )

    def test_response_always_identifies_its_task(self, monkeypatch):
        """The missing `task` echo is why the wrong answer was invisible."""
        import app.tasks.redis_state as rs

        monkeypatch.setattr(
            rs, "get_task_metrics",
            lambda name: {"task": name, "status": "no_data"},
        )
        monkeypatch.setattr(
            "app.routes.admin_data_quality._check_admin_secret",
            lambda *a, **k: None,
        )
        out = _call(task="poll_kalshi_markets", task_name=None)
        assert out["task"] == "poll_kalshi_markets", (
            "the reply must name the task it describes"
        )


class TestTheFourProductionSpecimens:
    """The exact four that returned byte-identical bodies must now differ."""

    SPECIMENS = [
        "poll_kalshi_markets",
        "poll_polymarket_markets",
        "precompute_calibration",
        "backfill_winners",
    ]

    @pytest.mark.parametrize("name", SPECIMENS)
    def test_each_specimen_is_answered_about_itself(self, monkeypatch, name):
        import app.tasks.redis_state as rs

        monkeypatch.setattr(
            rs, "get_task_metrics",
            lambda n: {"task": n, "successes_24h": len(n)},
        )
        monkeypatch.setattr(
            "app.routes.admin_data_quality._check_admin_secret",
            lambda *a, **k: None,
        )
        out = _call(task=name, task_name=None)
        assert out["task"] == name

    def test_the_four_are_no_longer_byte_identical(self, monkeypatch):
        """Pins the reported symptom directly."""
        import app.tasks.redis_state as rs

        monkeypatch.setattr(
            rs, "get_task_metrics",
            lambda n: {"task": n, "status": "no_data"},
        )
        monkeypatch.setattr(
            "app.routes.admin_data_quality._check_admin_secret",
            lambda *a, **k: None,
        )
        bodies = [_call(task=n, task_name=None) for n in self.SPECIMENS]
        assert len({repr(b) for b in bodies}) == len(self.SPECIMENS), (
            "four different tasks still return identical bodies — #1008 is back"
        )


class TestMissingTaskIsAnErrorNotAGuess:
    def test_no_task_raises_400_listing_known_tasks(self, monkeypatch):
        import app.tasks.redis_state as rs
        from fastapi import HTTPException

        monkeypatch.setattr(
            rs, "get_all_task_metrics",
            lambda: [{"task": "backfill_winners"}, {"task": "poll_kalshi_markets"}],
        )
        monkeypatch.setattr(
            "app.routes.admin_data_quality._check_admin_secret",
            lambda *a, **k: None,
        )
        with pytest.raises(HTTPException) as exc:
            _call(task=None, task_name=None)
        assert exc.value.status_code == 400
        assert "known_tasks" in exc.value.detail
        assert "backfill_winners" in exc.value.detail["known_tasks"]
