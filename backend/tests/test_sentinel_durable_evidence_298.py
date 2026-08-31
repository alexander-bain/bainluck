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
        import pathlib

        _assert_now_is_clock_derived(pathlib.Path(__file__).read_text())

    def test_the_anchor_guard_can_actually_FAIL(self):
        """The control, and this file has now earned one THREE times over.

        Three certs in a row found the ANCHOR fine and the GUARD hollow: a value
        comparison any fresh literal satisfied (CERT-568); a first-binding AST
        scan a shadowing literal walked past (CERT-571); and a `tree.body` scan
        that missed a rebinding nested one level down under `if`/`try`
        (CERT-577). Every time the suite was green and every time the bomb was
        armed.

        A guard nobody has watched fail is a guard nobody knows the shape of, so
        every known attack is pinned here as a source string and each must raise.
        The list only grows — an attack that has been closed still runs, because
        the cheapest way to reopen one is to rewrite the guard for the next.

        In memory, never on disk: `scripts/evals/_mutation_guard.py` says an
        in-process harness that mutates a STRING is strictly the better design
        because it cannot leave residue in a real file, and nothing here needs
        a file.
        """
        import pytest as _pytest

        real = "NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)"
        literal = "NOW = datetime(2026, 8, 31, 12, 53, 0, tzinfo=timezone.utc)"

        attacks = {
            # CERT-568: swap the clock call for a timestamp that is fresh TODAY.
            "fresh literal replaces the clock call": literal,
            # CERT-571: leave the clock call in place and override it below.
            "a later assignment shadows it": f"{real}\n{literal}",
            # The same move in annotated clothing, which an `ast.Assign`-only
            # scan does not see at all.
            "an annotated later assignment shadows it": (
                f"{real}\nNOW: datetime = "
                "datetime(2026, 8, 31, 12, 53, 0, tzinfo=timezone.utc)"
            ),
            # 🔴 CERT-577's two, and the reason the scan is now scope-based
            # rather than depth-based: both of these execute at module scope and
            # both are invisible to a `tree.body` walk.
            "a rebinding nested under `if`": f"{real}\nif True:\n    {literal}",
            "a rebinding nested under `try`": (
                f"{real}\ntry:\n    {literal}\nexcept Exception:\n    pass"
            ),
            # The same class through the other binding forms, which are stores
            # rather than assignment statements.
            "a rebinding nested two levels down": (
                f"{real}\nif True:\n    if True:\n        {literal}"
            ),
            "a `for` target rebinds it": (
                f"{real}\nfor NOW in [datetime(2026, 8, 31, tzinfo=timezone.utc)]:\n    pass"
            ),
            "a `with ... as` target rebinds it": (
                f"{real}\nimport contextlib\n"
                "with contextlib.nullcontext("
                "datetime(2026, 8, 31, tzinfo=timezone.utc)) as NOW:\n    pass"
            ),
            # 🔴 CERT-581's class, and the reason the guard now RUNS the anchor
            # instead of reading it. Every one of these is a single module-level
            # plain assignment whose right-hand side genuinely contains a
            # `datetime.now(...)` call — and in every one the call's result is
            # thrown away and a constant binds. No source scan can separate
            # these from the real thing; evaluating them against a moving clock
            # separates them instantly.
            "an unreachable clock branch fronts a fixed value": (
                "NOW = datetime.now(timezone.utc) if False else "
                "datetime.fromtimestamp(1756645980, tz=timezone.utc)"
            ),
            "a short-circuit discards the clock call": (
                "NOW = datetime.fromtimestamp(1756645980, tz=timezone.utc) "
                "or datetime.now(timezone.utc)"
            ),
            "the clock call is an unused list element": (
                "NOW = [datetime.now(timezone.utc), "
                "datetime.fromtimestamp(1756645980, tz=timezone.utc)][1]"
            ),
            # The partial-derivation case: it moves with the clock but not by
            # the clock's own step, so it is not a fixed distance behind `now`
            # and can still drift across the bound.
            "only the date follows the clock, the time is pinned": (
                "NOW = datetime.now(timezone.utc).replace("
                "year=2026, month=8, day=31)"
            ),
        }
        for name, src in attacks.items():
            with _pytest.raises(AssertionError):
                _assert_now_is_clock_derived(src)

        # And the control's control: the real anchor must still pass, or every
        # `raises` above could be passing for an unrelated reason. A `NOW` bound
        # inside a FUNCTION is a local and must NOT trip the guard — the scope
        # rule has to cut both ways or the next author cannot write a helper.
        _assert_now_is_clock_derived(real)
        _assert_now_is_clock_derived(
            f"{real}\ndef _helper():\n    NOW = 1\n    return NOW"
        )
        _assert_now_is_clock_derived(
            f"{real}\nclass _C:\n    NOW = 2"
        )
        # 🔴 AND THE POSITIVE CONTROLS THAT PROVE IT IS NOT PATTERN-MATCHING
        # `datetime.now`. The old source check accepted an anchor because the
        # letters `now` appeared in its AST; if the replacement did the same
        # thing by another route it would reject these, which are all honestly
        # clock-derived and none of which spell `datetime.now(...)` in the
        # shape the previous version looked for.
        _assert_now_is_clock_derived(
            "NOW = datetime.fromtimestamp(time.time(), tz=timezone.utc)"
        )
        _assert_now_is_clock_derived(
            "NOW = datetime.now(timezone.utc) - timedelta(hours=6)"
        )
        _assert_now_is_clock_derived(
            "NOW = (datetime.utcnow() - timedelta(minutes=2)).replace("
            "microsecond=0, tzinfo=timezone.utc)"
        )


def _assert_now_is_clock_derived(src: str) -> None:
    """The anchor guard, over SOURCE TEXT rather than over this file.

    A parameter and not a `__file__` read, so `test_the_anchor_guard_can_
    actually_FAIL` can run the very same assertions against the attacks that
    beat the previous two versions of it. A guard whose failure path is never
    executed is a guard whose failure path is not known to work.
    """
    import ast

    tree = ast.parse(src)

    # 🔴 EVERY BINDING, NOT THE FIRST (CERT-571). This used to take
    # `next(...)` — the FIRST module-level assignment to `NOW` — and Python
    # uses the LAST one executed. So the guard could be satisfied by a dynamic
    # assignment that a literal one below it immediately overrides, and the
    # cert did exactly that: it left the clock call in place, added
    # `NOW = datetime(2026, 8, 31, 12, 53, 0, tzinfo=timezone.utc)` after it,
    # and the whole file stayed green at 19/19 with the same bomb re-armed on
    # a one-hour fuse.
    #
    # This is the third time this fixture's anchor has been attacked and the
    # second time the GUARD was the hole rather than the anchor. The
    # generalisation worth keeping: an oracle that reads source must bind to
    # the value that actually RUNS. Certifying the first of several candidates
    # certifies a statement the interpreter may never use — the same shape as
    # a containment check satisfied by a sibling call site.
    #
    # `AnnAssign` is included because `NOW: datetime = <literal>` binds just as
    # effectively and would otherwise walk straight past an `ast.Assign` scan.
    #
    # 🔴 AND "MODULE LEVEL" IS NOT `tree.body` (CERT-577). The first version of
    # this scan read only the direct children of the module, and the cert walked
    # around it in one line: `if True:\n    NOW = datetime(...)` — or the same
    # thing under `try:` — is nested one level down in the AST and executes at
    # module scope exactly like a top-level statement. Both attacks left the
    # guard green with the bomb re-armed.
    #
    # **The rule is SCOPE, not DEPTH.** Everything that is not a new binding
    # scope is module level however deeply it is nested, so this recurses
    # through executable bodies (`if` / `try` / `for` / `while` / `with` / `match`)
    # and stops only at `def` / `async def` / `class` / `lambda`, where a
    # `NOW = ...` is a LOCAL and cannot touch the fixture.
    #
    # It also collects every STORE, not just assignment statements — `for NOW in
    # ...`, `with ... as NOW`, `NOW += ...` and walrus all rebind the anchor, and
    # a scan that only knows about `Assign` calls each of them clean.
    def _module_level_now_stores(node, out):
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue  # a new scope — `NOW` in there is not this anchor
            if (
                isinstance(child, ast.Name)
                and child.id == "NOW"
                and isinstance(child.ctx, ast.Store)
            ):
                out.append(child)
            _module_level_now_stores(child, out)
        return out

    stores = _module_level_now_stores(tree, [])
    assert stores, "module-level `NOW` binding not found"
    assert len(stores) == 1, (
        f"`NOW` is bound {len(stores)} times at module scope, on lines "
        f"{sorted(n.lineno for n in stores)}. The LAST one executed wins at "
        "runtime, so a guard that inspects any single binding can be satisfied "
        "by a dead one while a literal elsewhere becomes the real fixture "
        "anchor. Nesting it under `if`/`try`/`for`/`with` does not make it a "
        "different scope. Keep exactly one binding."
    )

    # The sole store must belong to a plain assignment whose value we can read.
    # A `for`/`with`/augmented/walrus binding reaches here and is refused by
    # name, rather than falling through to an attribute error.
    assigns = [
        n
        for n in ast.walk(tree)
        if (
            isinstance(n, ast.Assign)
            and any(t is stores[0] for t in n.targets)
        )
        or (isinstance(n, ast.AnnAssign) and n.target is stores[0] and n.value is not None)
    ]
    assert len(assigns) == 1, (
        f"`NOW` is bound on line {stores[0].lineno} by something other than a "
        "plain assignment with a readable right-hand side (a `for`, `with`, "
        "augmented or walrus binding). The anchor must be a single assignment "
        "that calls the clock."
    )
    assign = assigns[0]

    # 🔴 CERT-581 — AND HERE THE SOURCE-READING STOPS.
    #
    # Four certs have now attacked this one anchor, and the first three repairs
    # all had the same shape: read the source a bit more carefully than last
    # time. Each closed the instance it was shown and left the class open one
    # level out — a fresh literal (CERT-568), a shadowing binding (CERT-571), a
    # binding nested under `if`/`try` (CERT-577). CERT-581 walked around the
    # third in one move that no amount of extra AST care can catch:
    #
    #     NOW = datetime.now(timezone.utc) if False else \
    #           datetime.fromtimestamp(1756645980, tz=timezone.utc)
    #
    # ONE module-level binding. A plain assignment. Its right-hand side really
    # does contain a `datetime.now(...)` Call, so `attr='now'` was satisfied. It
    # is not a bare `datetime(...)` constructor, so that check was satisfied too.
    # And the value that actually binds at runtime is a hardcoded instant with a
    # fuse on it. **The old check treated PRESENCE as PROVENANCE**, and presence
    # of a call in the source says nothing about whether its result is the value.
    #
    # So this stops asking what the anchor is SPELLED like and asks what it
    # DOES. Provenance is a behaviour: a clock-derived value MOVES when the
    # clock moves, and a hardcoded one does not, however it is dressed. The RHS
    # is evaluated twice against two different fake clocks and the result must
    # follow both of them, exactly.
    #
    # This is not one more patch on the walk — it strictly DOMINATES the two
    # source checks it replaces (every literal and every bare constructor they
    # rejected fails to track a moving clock as well), and unlike them it does
    # not have a "next level out" to be walked around. There is no way to write
    # a hardcoded anchor whose value changes when `datetime.now` changes.
    #
    # The single-binding and plain-assignment checks ABOVE are still load-bearing
    # and are why this can be trusted: they are what guarantee that the one
    # expression evaluated here is the one that really binds `NOW` at import.
    _assert_value_tracks_the_clock(assign)


def _assert_value_tracks_the_clock(assign) -> None:
    """Evaluate the anchor's right-hand side against two clocks; require it to follow.

    The sandbox hands the expression a `datetime` whose `.now()`/`.today()` and a
    `time` whose `.time()` report a controlled instant, then advances that instant
    and evaluates again. A clock-derived anchor shifts by exactly the amount the
    clock shifted. A constant — reached through a dead branch, a short-circuit, an
    index, or spelled plainly — does not move at all.

    `_FrozenDatetime` SUBCLASSES the real `datetime`, so arithmetic, `.replace()`
    and `.isoformat()` on the result behave exactly as they do in production; only
    the clock entry points are substituted.
    """
    import ast

    # Both instants are whole minutes with no sub-second component, so the
    # truncations a sane anchor performs (`.replace(microsecond=0)`,
    # `.replace(second=0)`) are no-ops and the tracking test is an exact
    # equality rather than a tolerance nobody can reason about.
    first = datetime(2031, 3, 4, 9, 0, 0, tzinfo=timezone.utc)
    shift = timedelta(days=23, hours=5, minutes=7)

    def _evaluate(instant):
        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant if tz else instant.replace(tzinfo=None)

            @classmethod
            def utcnow(cls):
                return instant.replace(tzinfo=None)

            @classmethod
            def today(cls):
                return instant.replace(tzinfo=None)

        class _FrozenTime:
            @staticmethod
            def time():
                return instant.timestamp()

            @staticmethod
            def time_ns():
                return int(instant.timestamp() * 1_000_000_000)

        sandbox = {
            "datetime": _FrozenDatetime,
            "timedelta": timedelta,
            "timezone": timezone,
            "time": _FrozenTime,
        }
        expression = ast.Expression(body=assign.value)
        ast.fix_missing_locations(expression)
        try:
            return eval(compile(expression, "<anchor>", "eval"), sandbox)  # noqa: S307
        except Exception as exc:  # noqa: BLE001 — fail CLOSED, never open
            raise AssertionError(
                "the anchor's right-hand side could not be evaluated against a "
                f"fake clock ({type(exc).__name__}: {exc}). It reads as:\n"
                f"    {ast.unparse(assign.value)}\n"
                "This guard proves the anchor tracks the clock by RUNNING it, so "
                "an expression it cannot run is refused rather than waved "
                "through. If the anchor legitimately needs another name, add it "
                "to `sandbox` above — do not weaken the check."
            ) from exc

    before, after = _evaluate(first), _evaluate(first + shift)

    assert before != after, (
        "`NOW` does NOT track the clock: moving the clock forward by "
        f"{shift} left the anchor at exactly {before!r}. It reads as:\n"
        f"    {ast.unparse(assign.value)}\n"
        "That means the value that actually binds is a CONSTANT, whatever the "
        "source looks like — a dead `datetime.now(...)` branch, a short-circuit, "
        "or an unused element all put a clock call in the text without letting it "
        "reach the result (CERT-581). A constant anchor is fresh on the day it is "
        "written and silently crosses SENTINEL_MAX_AGE_S later, taking a backend "
        "shard red with no code change. Derive it from the clock."
    )
    assert after - before == shift, (
        f"`NOW` moved by {after - before} when the clock moved by {shift}, so it "
        "is only PARTLY derived from the clock. It reads as:\n"
        f"    {ast.unparse(assign.value)}\n"
        "The anchor must be the current time plus or minus a fixed offset, so "
        "that it is always the same distance behind 'now' and can never age out."
    )
