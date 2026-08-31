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

# LAT-P166/#2388: THIS ANCHOR WAS A TIME BOMB AND IT DETONATED ON 2026-08-31 AT
# 12:00:00Z, TAKING EVERY LANE'S CI RED ON SHARD 4.
#
# It used to be the literal `datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)`.
# The reader it feeds bounds durable evidence at
# :data:`app.services.durable_snapshots.SENTINEL_MAX_AGE_S` = 30 days, and
# 2026-08-01T12:00:00Z + 30 days IS 2026-08-31T12:00:00Z. For thirty days the
# fixture was "fresh"; at that instant it became "ancient", `read_sentinel_evidence`
# started returning `None`, and four tests began failing on code nobody had touched.
#
# 🔴 THE TELL THAT IT WAS THE CLOCK AND NOT A COMMIT: master's own CI run at this
# exact SHA passed at 05:56Z and the same tree failed at 12:24Z. If a suite goes red
# with no diff between the green and red runs, compare the two run TIMES before you
# read a single line of the diff.
#
# Gotcha #44 — offset FIRST, then truncate, and never let an anchor be a literal it
# can outlive. One minute back so the row is unambiguously in the past, microseconds
# dropped so the value is stable within a run. `TestTheAnchorCannotExpireAgain`
# below fails loudly if anyone puts a literal back.
NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)
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


# --- The anchor itself -------------------------------------------------------


class TestTheAnchorCannotExpireAgain:
    """LAT-P166/#2388. The module's `NOW` outlived its own freshness window.

    A fixed literal against a ROLLING bound is a bomb with a fuse exactly as long as
    the bound. It sat green for thirty days, which is precisely why nobody caught it
    in review: on the day it was written, and on every day for a month after, it was
    correct. These two tests are cheap and they are the only thing standing between a
    later reader's tidy-looking literal and another silent thirty-day fuse.
    """

    def test_the_anchor_is_comfortably_inside_the_readers_max_age(self):
        from app.services.durable_snapshots import SENTINEL_MAX_AGE_S

        age_s = (datetime.now(timezone.utc) - NOW).total_seconds()
        assert 0 <= age_s < SENTINEL_MAX_AGE_S / 2, (
            f"the fixture anchor is {age_s:.0f}s old against a "
            f"{SENTINEL_MAX_AGE_S:.0f}s bound. If this is a hardcoded datetime it "
            "will pass until it silently crosses the bound and takes shard 4 red "
            "on a day nobody changed anything. Anchor it to the real clock."
        )

    def test_the_anchor_is_DERIVED_from_the_clock_not_merely_NEAR_it(self):
        """CERT-568 repair. The value-comparison version of this guard was a hole.

        🔴 IT ORIGINALLY COMPARED `NOW` AGAINST A RE-DERIVED VALUE and passed if
        the two were within an hour. That kills the ORIGINAL literal — a month
        stale — and it kills nothing else. The cert broke it in one move: replace
        the expression with a *fresh* hardcoded timestamp and the whole file stayed
        green at 19/19, re-arming the identical no-code-change CI failure with a
        one-hour fuse instead of a thirty-day one.

        The lesson is general enough to be worth the words: **a guard against
        "someone hardcoded a value" cannot itself be a check on the value.** Any
        value test is satisfied by a value, which is exactly what you are trying to
        forbid. It has to read the CODE.

        So this reads the assignment's own AST and requires it to CALL something —
        `datetime.now`, `time.time`, whatever — rather than construct a constant.
        A literal has no `Call` node reaching the clock, and no amount of choosing
        a friendly-looking date gives it one.
        """
        import ast
        import pathlib

        src = pathlib.Path(__file__).read_text()
        tree = ast.parse(src)
        assign = next(
            (
                n
                for n in tree.body
                if isinstance(n, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "NOW" for t in n.targets
                )
            ),
            None,
        )
        assert assign is not None, "module-level `NOW` assignment not found"

        rhs = ast.dump(assign.value)
        assert "attr='now'" in rhs or "attr='today'" in rhs or "id='time'" in rhs, (
            "`NOW` is not derived from the clock — its right-hand side never calls "
            f"`datetime.now`/`time`. It reads as:\n    {ast.unparse(assign.value)}\n"
            "A hardcoded timestamp passes every check on its VALUE (it is 'recent' "
            "on the day you write it) and then silently crosses "
            "SENTINEL_MAX_AGE_S later, taking shard 4 red with no code change. "
            "See this method's docstring."
        )
        # And it must not be a constructed constant wearing a call's clothes,
        # e.g. `datetime(2026, 9, 1, ...)` — which IS a Call node.
        for node in ast.walk(assign.value):
            if isinstance(node, ast.Call):
                fn = node.func
                is_bare_datetime_ctor = (
                    isinstance(fn, ast.Name) and fn.id == "datetime"
                ) or (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == "datetime"
                )
                assert not is_bare_datetime_ctor, (
                    "`NOW` constructs a datetime literal. "
                    f"It reads as:\n    {ast.unparse(assign.value)}"
                )
