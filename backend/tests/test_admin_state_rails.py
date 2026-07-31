"""#1500 / #1484 — read-only admin state rails.

Two blind spots that forced source-reading or an expensive debug call:

* **Candidate-base state.** Verifying which provenance path (`fresh` /
  `last_good` / `direct` / `disabled`) served a request needed an admin
  ``debug=true`` feed call — which runs the ~10.7 s ground-truth block and
  disables the response cache, i.e. the only way to read the signal was a
  request ~2x slower than the thing being measured. The kill-switch value, the
  namespace actually written, and the key ages were unobservable entirely.
* **Category precompute.** A grid warm that timed out was swallowed into a log
  line, and the task's return value listed only the SUCCESSES — so "the MLB grid
  warm timed out" and "the task never reached grids" (they run last) were the
  same observation from outside.

Both rails are strictly READ-ONLY: no flip, no flush, no trigger.
"""

import importlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.utils import candidate_base as cb


def _envelope(identity, epoch_ms, ids=(1, 2, 3)):
    return {
        "schema_version": cb.CANDIDATE_BASE_SCHEMA_VERSION,
        "generated_at": "2026-07-31T19:00:00+00:00",
        "generated_epoch_ms": epoch_ms,
        "identity": identity,
        "candidate_ids": list(ids),
        "external_curator_recall_ids": [],
        "pool_counts": {"volume": 2, "movement": 1},
        "source_watermark": "2026-07-31T18:59:00+00:00",
    }


class TestCandidateBaseState:
    @pytest.mark.asyncio
    async def test_reports_namespace_version_and_freshness(self):
        from app.routes.admin import get_candidate_base_state
        import time

        identity = cb.base_identity(None, None)
        fresh_key, last_good_key = cb._redis_keys(identity)
        now_ms = time.time() * 1000

        r = MagicMock()
        store = {
            cb.CANDIDATE_BASE_ENABLED_KEY: "1",
            fresh_key: json.dumps(_envelope(identity, now_ms - 5_000)),
            last_good_key: json.dumps(_envelope(identity, now_ms - 900_000)),
        }
        r.get.side_effect = lambda k: store.get(k)
        r.ttl.side_effect = lambda k: 3600

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_candidate_base_state(MagicMock(), "s")

        assert out["namespace"] == cb._REDIS_NS
        assert out["key_version"] == "v2"
        assert out["schema_version"] == 2
        assert out["enabled"] is True
        assert out["status"] == "enabled"
        assert out["default_identity"] == identity
        assert out["keys"]["fresh"]["present"] is True
        assert out["keys"]["fresh"]["valid"] is True
        assert out["keys"]["fresh"]["is_fresh"] is True
        assert out["keys"]["fresh"]["candidate_id_count"] == 3
        assert out["keys"]["last_good"]["is_fresh"] is False
        assert out["would_serve"] == cb.PROV_FRESH

    @pytest.mark.asyncio
    async def test_never_exposes_candidate_ids(self):
        """Counts and ages only — never market content."""
        from app.routes.admin import get_candidate_base_state
        import time

        identity = cb.base_identity(None, None)
        fresh_key, _ = cb._redis_keys(identity)
        r = MagicMock()
        r.get.side_effect = lambda k: {
            cb.CANDIDATE_BASE_ENABLED_KEY: "1",
            fresh_key: json.dumps(
                _envelope(identity, time.time() * 1000, ids=(99991, 99992))
            ),
        }.get(k)
        r.ttl.return_value = 100

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_candidate_base_state(MagicMock(), "s")

        assert "99991" not in json.dumps(out)
        assert out["keys"]["fresh"]["candidate_id_count"] == 2

    @pytest.mark.asyncio
    async def test_kill_switch_off_reports_disabled_and_would_serve_disabled(self):
        from app.routes.admin import get_candidate_base_state

        r = MagicMock()
        r.get.side_effect = lambda k: "0" if k == cb.CANDIDATE_BASE_ENABLED_KEY else None
        r.ttl.return_value = -2

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_candidate_base_state(MagicMock(), "s")

        assert out["enabled"] is False
        assert out["kill_switch_value"] == "0"
        assert out["would_serve"] == cb.PROV_DISABLED

    @pytest.mark.asyncio
    async def test_unset_switch_is_enabled_but_distinguishable(self):
        from app.routes.admin import get_candidate_base_state

        r = MagicMock()
        r.get.return_value = None
        r.ttl.return_value = -2

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_candidate_base_state(MagicMock(), "s")

        assert out["enabled"] is True
        assert out["kill_switch_value"] is None    # unset != explicitly "1"
        assert out["would_serve"] == cb.PROV_DIRECT   # no usable keys

    @pytest.mark.asyncio
    async def test_redis_down_is_unavailable_not_disabled(self):
        """An unreadable store is not a configuration — UNKNOWN, never a
        confident 'disabled'."""
        from app.routes.admin import get_candidate_base_state

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client",
                   side_effect=RuntimeError("connection refused")):
            out = await get_candidate_base_state(MagicMock(), "s")

        assert out["status"] == "unavailable"
        assert out["enabled"] is None

    @pytest.mark.asyncio
    async def test_unparseable_envelope_reported_not_crashed(self):
        from app.routes.admin import get_candidate_base_state

        identity = cb.base_identity(None, None)
        fresh_key, _ = cb._redis_keys(identity)
        r = MagicMock()
        r.get.side_effect = lambda k: {
            cb.CANDIDATE_BASE_ENABLED_KEY: "1", fresh_key: "{not json",
        }.get(k)
        r.ttl.return_value = 60

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_candidate_base_state(MagicMock(), "s")

        assert out["keys"]["fresh"]["valid"] is False
        assert "unparseable" in out["keys"]["fresh"]["error"]

    @pytest.mark.asyncio
    async def test_is_read_only(self):
        """No mutation verb may be issued against Redis."""
        from app.routes.admin import get_candidate_base_state

        r = MagicMock()
        r.get.return_value = None
        r.ttl.return_value = -2

        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            await get_candidate_base_state(MagicMock(), "s")

        for verb in ("set", "setex", "delete", "flushdb", "flushall", "expire"):
            assert not getattr(r, verb).called, f"{verb} must not be called"

    @pytest.mark.asyncio
    async def test_requires_admin_auth(self):
        from app.routes.admin import get_candidate_base_state

        with patch("app.routes.admin._check_admin_secret",
                   side_effect=HTTPException(status_code=403, detail="no")):
            with pytest.raises(HTTPException) as exc:
                await get_candidate_base_state(MagicMock(), None)
        assert exc.value.status_code == 403


class TestCategoryPrecomputeRail:
    @pytest.mark.asyncio
    async def test_absent_report_is_unknown_not_ok(self):
        from app.routes.admin import get_category_precompute_last

        r = MagicMock()
        r.get.return_value = None
        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_category_precompute_last(MagicMock(), "s")

        assert out["status"] == "unknown"
        assert out["report"] is None

    @pytest.mark.asyncio
    async def test_returns_the_report(self):
        from app.routes.admin import get_category_precompute_last

        report = {"sections": {"grids": {"outcome": "ok"}},
                  "grid_leagues": {"mlb": {"outcome": "timeout"}}}
        r = MagicMock()
        r.get.return_value = json.dumps(report)
        with patch("app.routes.admin._check_admin_secret", return_value=True), \
             patch("app.tasks.redis_state.get_redis_client", return_value=r):
            out = await get_category_precompute_last(MagicMock(), "s")

        assert out["status"] == "ok"
        assert out["report"]["grid_leagues"]["mlb"]["outcome"] == "timeout"

    @pytest.mark.asyncio
    async def test_requires_admin_auth(self):
        from app.routes.admin import get_category_precompute_last

        with patch("app.routes.admin._check_admin_secret",
                   side_effect=HTTPException(status_code=403, detail="no")):
            with pytest.raises(HTTPException):
                await get_category_precompute_last(MagicMock(), None)


class TestPrecomputeObservability:
    @pytest.mark.asyncio
    async def test_grid_timeout_is_recorded_not_swallowed(self):
        """The #1484 observability gap: a timed-out warm looked identical to a
        warm that was never attempted."""
        import asyncio

        # NB: `from app.tasks import precompute_category_pages` resolves to the
        # registered CELERY TASK of that name, not the module — import by path.
        pcp = importlib.import_module("app.tasks.precompute_category_pages")

        async def _grid(slug, **kw):
            if slug == "mlb":
                raise asyncio.TimeoutError()
            return {"teams": [{"name": "x"}], "columns": [{"key": "c"}]}

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
        session_cm.__aexit__ = AsyncMock(return_value=False)

        # No wait_for stubbing: the MLB coroutine raises TimeoutError itself, so
        # the real asyncio.wait_for propagates it exactly as a genuine timeout.
        report: dict = {}
        with patch("app.tasks.base.get_task_session", return_value=session_cm), \
             patch("app.routes.playoffs.get_playoff_grid", side_effect=_grid), \
             patch("app.tasks.redis_state.get_redis_client", return_value=MagicMock()):
            warmed = await pcp._precompute_grids(report)

        leagues = report["grid_leagues"]
        assert leagues["mlb"]["outcome"] == "timeout"
        assert leagues["mlb"]["timeout_s"] == pcp.GRID_WARM_TIMEOUT_S
        # A timeout on one league must not stop the others.
        assert leagues["nba"]["outcome"] == "ok"
        assert leagues["nba"]["teams"] == 1
        assert "mlb" not in warmed and "nba" in warmed

    @pytest.mark.asyncio
    async def test_report_is_written_even_when_a_section_explodes(self):
        # NB: `from app.tasks import precompute_category_pages` resolves to the
        # registered CELERY TASK of that name, not the module — import by path.
        pcp = importlib.import_module("app.tasks.precompute_category_pages")

        written = {}

        async def _boom():
            raise RuntimeError("kaboom")

        async def _ok():
            return 1

        with patch.object(pcp, "_precompute_politics", _boom), \
             patch.object(pcp, "_precompute_entertainment", _ok), \
             patch.object(pcp, "_precompute_economics", _ok), \
             patch.object(pcp, "_precompute_weather", _ok), \
             patch.object(pcp, "_precompute_golf", _ok), \
             patch.object(pcp, "_precompute_grids", AsyncMock(return_value=[])), \
             patch.object(pcp, "_write_precompute_report",
                          side_effect=lambda rep: written.update(rep)):
            await pcp._precompute_all_category_pages()

        assert written["sections"]["politics"]["outcome"] == "error"
        assert "kaboom" in written["sections"]["politics"]["error"]
        assert written["sections"]["weather"]["outcome"] == "ok"
        assert "duration_s" in written

    @pytest.mark.asyncio
    async def test_unreached_sections_stay_not_attempted(self):
        """Grids run LAST, so they starve first. A section still marked
        `not_attempted` when the report lands is the starvation signal."""
        # NB: `from app.tasks import precompute_category_pages` resolves to the
        # registered CELERY TASK of that name, not the module — import by path.
        pcp = importlib.import_module("app.tasks.precompute_category_pages")

        written = {}

        async def _die():
            raise KeyboardInterrupt("soft time limit")

        async def _ok():
            return 1

        with patch.object(pcp, "_precompute_politics", _ok), \
             patch.object(pcp, "_precompute_entertainment", _die), \
             patch.object(pcp, "_precompute_economics", _ok), \
             patch.object(pcp, "_precompute_weather", _ok), \
             patch.object(pcp, "_precompute_golf", _ok), \
             patch.object(pcp, "_precompute_grids", AsyncMock(return_value=[])), \
             patch.object(pcp, "_write_precompute_report",
                          side_effect=lambda rep: written.update(rep)):
            with pytest.raises(KeyboardInterrupt):
                await pcp._precompute_all_category_pages()

        assert written["sections"]["politics"]["outcome"] == "ok"
        assert written["sections"]["grids"]["outcome"] == "not_attempted"
        assert written["section_order"][-1] == "grids"
