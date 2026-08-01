"""Queue 298 Item 2 — sentinel evidence survives Redis (#1512).

Every sentinel used to persist its scorecard with one 14-day Redis SETEX wrapped
in ``except: log``. On a 49.5/50MB allkeys-lru instance the TTL is irrelevant —
LRU evicts the key — and because the failure was swallowed, ``_tracked_run``
recorded a healthy run whose evidence no longer existed. By morning the ``/last``
rail said ``no_run_cached`` after a green nightly beat.

These pin both halves of the repair:

* the producer writes DURABLE FIRST and cannot report success without it;
* the reader serves the retained durable verdict when Redis is evicted or dead,
  while every Queue 294 classification it used to make stays exactly as it was.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils import durable_state as ds

NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
SCORECARD = {
    "mode": "live",
    "verdict": "GREEN",
    "scorecard": {"checked": 7, "green": 7},
    "generated_at": NOW.isoformat(),
}


def _redis_row(payload, generated_at=NOW, schema_version=None, complete=True):
    """A durable row as ``read_snapshot`` would see it come back from Postgres."""
    from app.services.durable_snapshots import SENTINEL_SCHEMA_VERSION

    return {
        "identity": "sentinel:flow",
        "schema_version": schema_version or SENTINEL_SCHEMA_VERSION,
        "generation": ds.generation_for(generated_at),
        "generated_at": generated_at,
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": complete,
        "source": "flow_sentinel",
    }


def _db_returning(row):
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    db.execute.return_value = result
    return db


# --- Producer ----------------------------------------------------------------


class TestPublishSentinelEvidence:
    @pytest.mark.asyncio
    async def test_durable_is_written_before_the_accelerator(self):
        """Ordering IS the contract: a volatile copy ahead of durable is torn."""
        import app.services.durable_snapshots as dsnap

        order: list[str] = []

        async def _durable(envelope):
            order.append("durable")
            return {"status": "ok", "identity": envelope.identity,
                    "generation": envelope.generation}

        rc = MagicMock()
        rc.setex.side_effect = lambda *a, **k: order.append("volatile")

        with patch.object(dsnap, "publish_snapshot_standalone", _durable), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            stages = await dsnap.publish_sentinel_evidence(
                identity="sentinel:flow", redis_key="k",
                stats=SCORECARD, source="flow_sentinel",
            )

        assert order == ["durable", "volatile"]
        assert stages["durable"] == "ok" and stages["volatile"] == "ok"

    @pytest.mark.asyncio
    async def test_accelerator_is_skipped_when_durable_fails(self):
        """Never leave a volatile copy with no durable backing."""
        import app.services.durable_snapshots as dsnap

        async def _boom(envelope):
            return {"status": "error", "identity": envelope.identity,
                    "generation": envelope.generation, "error": "db down"}

        rc = MagicMock()
        with patch.object(dsnap, "publish_snapshot_standalone", _boom), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            stages = await dsnap.publish_sentinel_evidence(
                identity="sentinel:flow", redis_key="k",
                stats=SCORECARD, source="flow_sentinel",
            )

        assert stages["durable"] == "error"
        assert stages["volatile"] == "not_attempted"
        rc.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_failed_durable_write_fails_the_run(self):
        """The swallowed-SETEX defect: a run that saved nothing said it was fine."""
        stages = {"durable": "error", "volatile": "not_attempted"}
        outcome = ds.evaluate_publication(
            compute_complete=True,
            durable_write="error",
            volatile_write="not_attempted",
            stages=stages,
        )
        assert not outcome.success
        with pytest.raises(RuntimeError, match="durable publication did not succeed"):
            outcome.raise_if_failed("flow sentinel evidence")

    @pytest.mark.asyncio
    async def test_losing_the_accelerator_does_not_fail_the_run(self):
        """Durable landed — Redis being down is a degraded write, not a failure."""
        import app.services.durable_snapshots as dsnap

        async def _ok(envelope):
            return {"status": "ok", "identity": envelope.identity,
                    "generation": envelope.generation}

        rc = MagicMock()
        rc.setex.side_effect = RuntimeError("connection refused")
        with patch.object(dsnap, "publish_snapshot_standalone", _ok), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            stages = await dsnap.publish_sentinel_evidence(
                identity="sentinel:flow", redis_key="k",
                stats=SCORECARD, source="flow_sentinel",
            )

        assert stages["durable"] == "ok" and stages["volatile"] == "error"
        assert ds.evaluate_publication(
            compute_complete=True, durable_write="ok", volatile_write="error"
        ).success

    @pytest.mark.asyncio
    async def test_generation_follows_the_scorecards_own_stamp(self):
        """A retry of the SAME artifact must not look like a newer generation."""
        import app.services.durable_snapshots as dsnap

        seen: list[int] = []

        async def _capture(envelope):
            seen.append(envelope.generation)
            return {"status": "ok", "identity": envelope.identity,
                    "generation": envelope.generation}

        with patch.object(dsnap, "publish_snapshot_standalone", _capture), \
             patch("app.tasks.redis_state.get_redis_client", return_value=MagicMock()):
            for _ in range(2):
                await dsnap.publish_sentinel_evidence(
                    identity="sentinel:flow", redis_key="k",
                    stats=SCORECARD, source="flow_sentinel",
                )

        assert seen[0] == seen[1] == ds.generation_for(NOW)


# --- Reader ------------------------------------------------------------------


class TestReadSentinelEvidence:
    @pytest.mark.asyncio
    async def test_evicted_redis_still_serves_the_retained_verdict(self):
        """THE #1512 CASE: healthy beat, key evicted by LRU, evidence retained."""
        from app.services.durable_snapshots import read_sentinel_evidence

        # Age is reported against the real clock, so stamp the row against it too.
        six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
        db = _db_returning(_redis_row(SCORECARD, generated_at=six_hours_ago))
        rc = MagicMock()
        rc.get.return_value = None  # evicted

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(
                db, identity="sentinel:flow", redis_key="bainluck:flow_sentinel:last"
            )

        assert out is not None, "an evicted key must not erase the verdict"
        assert out["verdict"] == "GREEN"
        assert out["provenance"]["source"] == "durable"
        assert out["provenance"]["dated"] is True
        assert out["provenance"]["age_s"] == pytest.approx(21600, abs=5)
        assert "evicted" in out["provenance"]["note"]

    @pytest.mark.asyncio
    async def test_dead_redis_still_serves_the_retained_verdict(self):
        from app.services.durable_snapshots import read_sentinel_evidence

        db = _db_returning(_redis_row(SCORECARD))
        rc = MagicMock()
        rc.get.side_effect = RuntimeError("Error 111 connecting to rediss://u:pw@h:6379")

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(
                db, identity="sentinel:flow", redis_key="bainluck:flow_sentinel:last"
            )

        assert out is not None and out["verdict"] == "GREEN"
        assert out["provenance"]["source"] == "durable"
        assert "pw" not in json.dumps(out["provenance"]["tiers"])

    @pytest.mark.asyncio
    async def test_nothing_anywhere_returns_none_so_the_rail_classifies(self):
        """The tier only ADDS an answer; it never redefines 'no answer'."""
        from app.services.durable_snapshots import read_sentinel_evidence

        db = _db_returning(None)
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(
                db, identity="sentinel:flow", redis_key="k"
            )
        assert out is None

    @pytest.mark.asyncio
    async def test_a_stale_durable_row_is_not_served(self):
        from app.services.durable_snapshots import (
            SENTINEL_MAX_AGE_S,
            read_sentinel_evidence,
        )

        ancient = NOW - timedelta(seconds=SENTINEL_MAX_AGE_S + 3600)
        db = _db_returning(_redis_row(SCORECARD, generated_at=ancient))
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(db, identity="sentinel:flow", redis_key="k")
        assert out is None

    @pytest.mark.asyncio
    async def test_a_wrong_version_durable_row_is_not_served(self):
        from app.services.durable_snapshots import read_sentinel_evidence

        db = _db_returning(_redis_row(SCORECARD, schema_version="v0"))
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(db, identity="sentinel:flow", redis_key="k")
        assert out is None

    @pytest.mark.asyncio
    async def test_fresh_redis_serves_the_accelerator_with_provenance(self):
        from app.services.durable_snapshots import read_sentinel_evidence

        db = _db_returning(_redis_row(SCORECARD))
        rc = MagicMock()
        rc.get.return_value = json.dumps(SCORECARD)

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(db, identity="sentinel:flow", redis_key="k")

        assert out["provenance"]["source"] == "volatile"
        assert out["verdict"] == "GREEN"

    @pytest.mark.asyncio
    async def test_a_red_verdict_is_retained_not_softened(self):
        """A retained RED must stay RED — losing it would read as 'all clear'."""
        from app.services.durable_snapshots import read_sentinel_evidence

        red = dict(SCORECARD, verdict="RED")
        db = _db_returning(_redis_row(red))
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(db, identity="sentinel:flow", redis_key="k")
        assert out["verdict"] == "RED"

    @pytest.mark.asyncio
    async def test_volatile_ahead_of_durable_is_flagged_as_torn(self):
        from app.services.durable_snapshots import read_sentinel_evidence

        newer = dict(SCORECARD, generated_at=(NOW + timedelta(hours=1)).isoformat())
        db = _db_returning(_redis_row(SCORECARD))
        rc = MagicMock()
        rc.get.return_value = json.dumps(newer)

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await read_sentinel_evidence(db, identity="sentinel:flow", redis_key="k")

        assert out["provenance"]["source"] == "durable"
        assert ds.ERR_VOLATILE_AHEAD in out["provenance"]["contract_errors"]
        assert out["provenance"]["health"] == ds.UNKNOWN


# --- Rail integration --------------------------------------------------------


class TestRailFallsBackAdditively:
    """The durable tier must never take away a Queue 294 guarantee."""

    @pytest.mark.asyncio
    async def test_rail_serves_durable_when_redis_is_evicted(self):
        import app.routes.admin as admin_mod

        db = _db_returning(_redis_row(SCORECARD))
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.routes.admin._check_admin_secret"), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await admin_mod.get_flow_sentinel_last(MagicMock(), "s", db=db)

        assert out["verdict"] == "GREEN"
        assert out["provenance"]["source"] == "durable"

    @pytest.mark.asyncio
    async def test_rail_keeps_no_run_cached_when_truly_nothing_exists(self):
        import app.routes.admin as admin_mod

        db = _db_returning(None)
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.routes.admin._check_admin_secret"), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await admin_mod.get_flow_sentinel_last(MagicMock(), "s", db=db)

        assert out == {
            "status": "no_run_cached", "key": "bainluck:flow_sentinel:last"
        }

    @pytest.mark.asyncio
    async def test_a_broken_durable_tier_cannot_break_the_rail(self):
        """Falls back to the pre-existing behavior rather than 500ing."""
        import app.routes.admin as admin_mod

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("db exploded")
        rc = MagicMock()
        rc.get.return_value = None

        with patch("app.routes.admin._check_admin_secret"), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await admin_mod.get_flow_sentinel_last(MagicMock(), "s", db=db)

        assert out["status"] == "no_run_cached"

    @pytest.mark.asyncio
    async def test_board_rail_is_untouched_by_this_queue(self):
        """Its producer is an excluded dirty path, so it keeps Queue 294 behavior."""
        import app.routes.admin as admin_mod

        rc = MagicMock()
        rc.get.return_value = json.dumps({"verdict": "GREEN"})

        with patch("app.routes.admin._check_admin_secret"), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            out = await admin_mod.get_board_sentinel_last(MagicMock(), "s")

        assert out == {"verdict": "GREEN"}  # verbatim, no provenance block
