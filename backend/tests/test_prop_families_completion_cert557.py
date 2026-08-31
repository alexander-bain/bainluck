"""CERT-557's repair: the deferral's destination is not allowed to false-green.

WHAT THE CERT FOUND, and it was right.

LAT-P164 gave the first reader of a team page a 2,500 ms total budget and let it
DEFER the roster branch — 40 trigram probes, 11,789 ms of a 464 MB GIN index on a
box at 103% of plan — handing the page over in milliseconds and dispatching
`refresh_prop_families` to fetch the rest for everyone after. The whole ship rests
on one sentence: *the deferral is a WAIT, not a LOSS.*

Three separate things had to be true for that sentence to hold, and only the
first one was:

1. the cold reader must DISPATCH the completion.               <- shipped
2. the completion must SUCCEED, or SAY that it did not.        <- it said
   `terminal: complete, rebuilt: 1` while writing a `quality: partial` payload
   carrying `branch_timeout:outcome_roster`. An exact-head task probe reproduced
   exactly that. `refresh_prop_families` is in `ENFORCED_TASKS`, so `task_verdict`
   was reading that green tick and believing it.
3. a reader arriving AFTERWARDS must not be able to end the story. Step 1 of the
   route — the live primary hit — returned unconditionally, and it is the one
   path a warm reader takes. So a partial in the primary served for a full
   `PROP_FAMILIES_PRIMARY_TTL` with nothing scheduled and nothing said: the one
   place that inspects quality was the one place a warm reader never reached.

Together those made the deliberate deferral into persistent missing content
behind a live cache, which is the exact failure this queue existed to prevent,
reintroduced one layer further out.

🔴 WHAT THESE GUARDS REFUSE TO LET THE REPAIR BUY ITS WIN WITH. "Retry until it
works" is one line away and it is the wrong fix: the branch being completed is the
11.8 s one, on a database `pg:diagnose` rates RED on hit rate. So the assertions
below are as much about the BOUND as about the retry —

  * one completion attempt per key per primary TTL, not one per reader and not
    one per `REFRESH_LOCK_TTL` (which is 120 s, and would be seven per window);
  * a `branch_timeout:` partial does NOT get re-dispatched. It was asked with the
    full 12 s ceiling and expired; asking again now costs another twelve seconds
    and cannot succeed. It is REPORTED (see the terminal) and left to the
    structural fix named on #2383;
  * `budget_ms=None` on the background path stays untouched, again, because a
    completion that inherits the reader's budget can never complete anything.

Every assertion is on SHAPE, CALL COUNT, TERMINAL and REASON STRINGS. Nothing
sleeps and nothing reads a real clock.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod
from app.utils.task_verdict import COMPLETE, PARTIAL, verdict_for

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Doubles — local, so collection order is never load-bearing.
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.sets: list[tuple[str, bool, int | None]] = []

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        self.sets.append((k, nx, ex))
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)

    def eval(self, script, numkeys, *args):
        key = args[0]
        if script is cache_mod._SETEX_IF_UNCHANGED_LUA:
            absent_only, expected, ttl, value = args[1], args[2], args[3], args[4]
            current = self.store.get(key)
            if absent_only == "1":
                if current is not None:
                    return 0
            elif current != (
                expected.encode() if isinstance(expected, str) else expected
            ):
                return 0
            self.ttls[key] = int(ttl)
            self.store[key] = value.encode() if isinstance(value, str) else value
            return 1
        expected = args[1].encode() if isinstance(args[1], str) else args[1]
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            return 1
        return 0


class _UnreachableRedis(_FakeRedis):
    def set(self, k, v, nx=False, ex=None):
        raise RuntimeError("redis is down")


TEAM_ID = 547
CAP = 400


def _team(tid=TEAM_ID, name="New York Giants", slug="new-york-giants"):
    return SimpleNamespace(
        id=tid, name=name, slug=slug, roster_players=[{"name": "Malik Nabers"}]
    )


def _families():
    """Non-empty, because an empty partial is the `degraded` path and would test
    a different branch than the one the cert found."""
    return [{"family_key": "mvp", "label": "NFL MVP", "entity_count": 2, "rows": []}]


def _stamped(quality, reasons=()):
    """Stamped by the MODULE'S OWN stamper, never by hand.

    A hand-rolled envelope is missing `generation` / `availability` /
    `lifecycle_watermark`, and `read_slot` rejects it as malformed — so a reader
    fed one gets a cache MISS and every "a live partial does X" assertion would
    be testing the cold path instead. It fails loudly here; it would not
    necessarily fail loudly in a guard whose assertion is `== 0`.
    """
    from datetime import datetime, timezone

    return cache_mod.stamp_envelope(
        {
            "team": {
                "id": TEAM_ID, "name": "New York Giants", "slug": "new-york-giants"
            },
            "families": _families(),
            "total_families": 1,
        },
        created_at=datetime.now(timezone.utc),
        lifecycle_watermark=None,
        quality=quality,
        quality_reasons=list(reasons),
    )


def _serve_primary(rc, payload):
    """Put `payload` in the LIVE primary slot, through the module's own writer,
    so the bytes a reader gets back are the bytes the tier really stores."""
    keys = route.prop_families_cache_keys(TEAM_ID, CAP)
    cache_mod.write_payload(
        rc, keys, payload, primary_ttl=route.PROP_FAMILIES_PRIMARY_TTL, mirror=False
    )
    return keys


class _TeamOnlyDB:
    """Resolves the team and nothing else. A live primary hit must never reach a
    branch query, and a double that would happily serve one could not tell us so."""

    def __init__(self, team=None):
        self._team = team if team is not None else _team()
        self.branch_queries = 0

    async def execute(self, stmt, *args, **kwargs):
        rendered = str(stmt)
        if "futures_outcomes" in rendered:
            self.branch_queries += 1
        result = MagicMock()
        scalars = MagicMock()
        scalars.first.return_value = self._team
        scalars.all.return_value = [self._team]
        result.scalars.return_value = scalars
        result.all.return_value = []
        return result

    async def rollback(self):
        pass


class _AsyncCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *a):
        return False


def _session_with(db):
    return lambda *a, **k: _AsyncCM(db)


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


async def _read(rc, db, identifier="new-york-giants"):
    sent = MagicMock()
    with patch.object(route, "get_client", return_value=rc), patch(
        "app.tasks.celery_app.send_task", sent
    ):
        payload = await route.get_team_prop_families(identifier, CAP, db)
    return payload, sent


# ---------------------------------------------------------------------------
# 1. THE FINDING — the background completion is not allowed to false-green
# ---------------------------------------------------------------------------


class TestTheCompletionTaskTellsTheTruth:
    """CERT-557 finding 1, at the exact seam it named: `_refresh_prop_families`
    checked `degraded`, which is True only when the build produced NOTHING. A
    build that kept the cheap rows and lost the roster is `degraded=False` AND
    incomplete, and it was being stamped `terminal: complete, rebuilt: 1`."""

    async def test_a_rebuild_that_lost_the_roster_branch_is_not_complete(self):
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), patch(
            "app.tasks.base.get_task_session", _session_with(_TeamOnlyDB())
        ), patch(
            "app.routes.prop_families.build_and_cache_prop_families",
            side_effect=_async_return(
                (_stamped("partial", ["branch_timeout:outcome_roster"]), False)
            ),
        ):
            out = await warm._refresh_prop_families(TEAM_ID, CAP, None)

        assert out["terminal"] == "partial", (
            "a rebuild that lost the roster branch reported itself complete — "
            "this is the false green CERT-557 blocked"
        )
        assert out["rebuilt"] == 0, "an incomplete rebuild counted as a rebuild"
        assert out["quality"] == "partial"
        assert out["quality_reasons"] == ["branch_timeout:outcome_roster"]

    async def test_the_summary_still_says_the_primary_was_written(self):
        """`partial` must not read as `did nothing`. The build DID write and the
        page IS better; what it is not, is settled (gotcha #53)."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), patch(
            "app.tasks.base.get_task_session", _session_with(_TeamOnlyDB())
        ), patch(
            "app.routes.prop_families.build_and_cache_prop_families",
            side_effect=_async_return(
                (_stamped("partial", ["branch_deferred:outcome_roster"]), False)
            ),
        ):
            out = await warm._refresh_prop_families(TEAM_ID, CAP, None)
        assert out["stored"] is True

    async def test_a_full_rebuild_is_still_complete(self):
        """The repair must not turn every completion red — that would be the
        same blindness with the sign flipped."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), patch(
            "app.tasks.base.get_task_session", _session_with(_TeamOnlyDB())
        ), patch(
            "app.routes.prop_families.build_and_cache_prop_families",
            side_effect=_async_return((_stamped("full"), False)),
        ):
            out = await warm._refresh_prop_families(TEAM_ID, CAP, None)
        assert out["terminal"] == "complete" and out["rebuilt"] == 1

    async def test_a_payload_with_no_envelope_at_all_is_not_complete(self):
        """The unstamped shape. `envelope_quality` returns `None`, and `None` is
        not `full` — a caller that cannot prove completeness does not get to
        claim it."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), patch(
            "app.tasks.base.get_task_session", _session_with(_TeamOnlyDB())
        ), patch(
            "app.routes.prop_families.build_and_cache_prop_families",
            side_effect=_async_return(({"families": _families()}, False)),
        ):
            out = await warm._refresh_prop_families(TEAM_ID, CAP, None)
        assert out["terminal"] == "partial" and out["stored"] is False

    async def test_a_degraded_rebuild_is_still_failed_not_softened(self):
        """`partial` is added BESIDE `failed`, never in front of it."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), patch(
            "app.tasks.base.get_task_session", _session_with(_TeamOnlyDB())
        ), patch(
            "app.routes.prop_families.build_and_cache_prop_families",
            side_effect=_async_return(({"families": []}, True)),
        ):
            out = await warm._refresh_prop_families(TEAM_ID, CAP, None)
        assert out["terminal"] == "failed" and out["degraded"] is True


class TestTheHealthGateActuallySeesIt:
    """🔴 THE TERMINAL IS ONLY WORTH ANYTHING IF THE CONSUMER READS IT — CERT-518's
    lesson, one module over, and the reason this class exists rather than a
    comment. A field nothing consumes is a false green with extra steps."""

    def test_the_partial_terminal_is_classified_non_green(self):
        v = verdict_for(
            "refresh_prop_families",
            {
                "terminal": "partial",
                "team_id": TEAM_ID,
                "rebuilt": 0,
                "quality": "partial",
                "quality_reasons": ["branch_timeout:outcome_roster"],
                "stored": True,
            },
        )
        assert v.verdict == PARTIAL
        assert v.is_green is False
        assert v.authoritative is True

    def test_the_shape_that_was_shipped_would_have_read_green(self):
        """The control that makes the assertion above non-vacuous: the OLD
        summary, run through the SAME classifier, is an authoritative green."""
        v = verdict_for(
            "refresh_prop_families",
            {"terminal": "complete", "team_id": TEAM_ID, "rebuilt": 1},
        )
        assert v.verdict == COMPLETE and v.is_green is True


# ---------------------------------------------------------------------------
# 2. THE PERSISTENCE MECHANISM — a warm reader could end the story
# ---------------------------------------------------------------------------


class TestALivePartialStillChasesItsCompletion:
    async def test_a_live_hit_carrying_a_deferral_schedules_the_completion(self):
        rc = _FakeRedis()
        _serve_primary(rc, _stamped("partial", ["branch_deferred:outcome_roster"]))
        db = _TeamOnlyDB()

        payload, sent = await _read(rc, db)

        assert sent.call_count == 1, (
            "a live partial served without chasing its missing branch — the "
            "deferral had become a loss"
        )
        assert sent.call_args.args[0] == "app.tasks.refresh_prop_families"
        # And the reader was still served instantly from cache, not rebuilt.
        assert db.branch_queries == 0
        assert payload["total_families"] == 1

    async def test_a_live_full_hit_schedules_nothing(self):
        rc = _FakeRedis()
        _serve_primary(rc, _stamped("full"))
        _payload, sent = await _read(rc, _TeamOnlyDB())
        assert sent.call_count == 0

    async def test_a_live_timeout_partial_is_reported_not_hammered(self):
        """🔴 THE BOUND, NOT THE RETRY. `branch_timeout:` means the branch ran
        with the full 12 s ceiling and expired. Re-dispatching cannot succeed and
        costs another twelve seconds on a database already at 103% of plan. It is
        left to the structural fix on #2383 — a denormalised scope column and a
        PARTIAL trigram index — which is an attended migration, not a retry."""
        rc = _FakeRedis()
        _serve_primary(rc, _stamped("partial", ["branch_timeout:outcome_roster"]))
        _payload, sent = await _read(rc, _TeamOnlyDB())
        assert sent.call_count == 0

    async def test_only_one_completion_attempt_per_primary_ttl(self):
        """Six readers inside one window buy ONE background build.

        Note what this is NOT bounded by: `acquire_refresh_lock` is a
        single-flight lock with a 120 s TTL, so a dispatch gated only by it would
        fire `900 // 120` = 7 times per window. The marker is a rate bound and
        the lock is a concurrency bound; the difference is six unbudgeted builds.
        """
        rc = _FakeRedis()
        _serve_primary(rc, _stamped("partial", ["branch_deferred:outcome_roster"]))

        total = 0
        for _ in range(6):
            # The refresh lock is released by the worker, which is not running
            # here, so clear it between reads: this test is about the ATTEMPT
            # marker, and leaving the lock held would let the lock take the
            # credit and pass for the wrong reason.
            keys = route.prop_families_cache_keys(TEAM_ID, CAP)
            rc.delete(keys.refresh_lock)
            _payload, sent = await _read(rc, _TeamOnlyDB())
            total += sent.call_count
        assert total == 1, f"{total} background builds for one deferral window"

    async def test_the_marker_expires_with_the_primary_it_bounds(self):
        rc = _FakeRedis()
        keys = _serve_primary(
            rc, _stamped("partial", ["branch_deferred:outcome_roster"])
        )
        await _read(rc, _TeamOnlyDB())
        marker = route._completion_attempt_key(keys)
        assert marker in rc.store
        assert rc.ttls[marker] == route.PROP_FAMILIES_PRIMARY_TTL
        assert route.COMPLETION_ATTEMPT_TTL == route.PROP_FAMILIES_PRIMARY_TTL

    async def test_an_unreachable_redis_does_not_unbound_the_dispatch(self):
        """Fails CLOSED. An unreachable Redis is not a licence to dispatch an
        unbounded number of 12-second builds, and the reader is served either
        way — here from a primary that was seeded before Redis 'broke'."""
        rc = _UnreachableRedis()
        # Seed the primary directly: the writer would raise on this double.
        keys = route.prop_families_cache_keys(TEAM_ID, CAP)
        import json

        rc.store[keys.primary] = json.dumps(
            _stamped("partial", ["branch_deferred:outcome_roster"])
        ).encode()

        _payload, sent = await _read(rc, _TeamOnlyDB())
        assert sent.call_count == 0

    async def test_the_live_hit_is_still_served_from_cache_either_way(self):
        """The repair must not cost the reader anything. Both partial shapes are
        returned from the primary with no branch query at all."""
        for reasons in (
            ["branch_deferred:outcome_roster"],
            ["branch_timeout:outcome_roster"],
        ):
            rc = _FakeRedis()
            _serve_primary(rc, _stamped("partial", reasons))
            db = _TeamOnlyDB()
            payload, _sent = await _read(rc, db)
            assert db.branch_queries == 0
            assert payload["total_families"] == 1
            assert payload[cache_mod.ENVELOPE_FIELD]["availability"] == (
                cache_mod.AVAILABILITY_LIVE
            )


# ---------------------------------------------------------------------------
# 3. AN IOU DOES NOT GET THE 24-HOUR SLOT
# ---------------------------------------------------------------------------


class TestADeferralIsNeverFrozenIntoTheMirror:
    """CERT-557 fix-sketch, second clause: "do not publish a partial cold rebuild
    as the long-lived completion target". A TIMEOUT partial still may — it is the
    best answer anyone can get, and LAT-P145's table is unchanged for it. A
    DEFERRED partial may not: nothing established the branch is unreachable, we
    declined to wait for it, and a 24-hour slot outlives the reader we declined
    for by four orders of magnitude."""

    async def _cache(self, reasons):
        rc = _FakeRedis()
        team = _team()
        keys = route.prop_families_cache_keys(TEAM_ID, CAP)

        async def _build(_team, _db, _cap, budget_ms=None):
            payload = {
                "team": {"id": TEAM_ID, "name": team.name, "slug": team.slug},
                "families": _families(),
                "total_families": 1,
            }
            for r in reasons:
                cache_mod.note_build_loss(payload, r, cache_mod.LOSS_PARTIAL)
            return payload, False

        with patch.object(route, "build_prop_families", _build):
            await route.build_and_cache_prop_families(
                team, _TeamOnlyDB(), CAP, rc, budget_ms=route._READER_BUDGET_MS
            )
        return rc, keys

    async def test_a_deferral_only_partial_takes_the_primary_and_not_the_mirror(self):
        rc, keys = await self._cache(["branch_deferred:outcome_roster"])
        assert keys.primary in rc.store, "the page must still be fast"
        assert keys.stale not in rc.store, (
            "a branch nobody asked for was frozen into the 24-hour mirror"
        )

    async def test_a_timeout_partial_still_reaches_the_mirror(self):
        """The control. Without it the assertion above passes on a build that
        stores nothing anywhere, which is a regression, not a fix."""
        rc, keys = await self._cache(["branch_timeout:outcome_roster"])
        assert keys.primary in rc.store
        assert keys.stale in rc.store

    async def test_a_deferral_beside_a_real_timeout_is_treated_as_a_timeout(self):
        """A build carrying both contains a fact about the DATABASE, not only
        about our budget, so the mirror rule that applies is the timeout one."""
        rc, keys = await self._cache(
            ["branch_timeout:outcome_name", "branch_deferred:outcome_roster"]
        )
        assert keys.stale in rc.store

    async def test_a_full_build_still_writes_both_slots(self):
        rc, keys = await self._cache([])
        assert keys.primary in rc.store and keys.stale in rc.store


# ---------------------------------------------------------------------------
# 4. THE SEAM ITSELF — one reader of the envelope, and the vocabulary is shared
# ---------------------------------------------------------------------------


class TestOneEnvelopeReaderNotTwo:
    """The defect was two callers forming different opinions about one field.
    These pin the single reader and the single spelling, because the next edit
    that reintroduces a second one is how this comes back."""

    def test_envelope_quality_refuses_every_unstamped_shape(self):
        for shape in (None, [], "partial", {}, {cache_mod.ENVELOPE_FIELD: "partial"}):
            assert route.envelope_quality(shape) == (None, [])

    def test_envelope_quality_reads_the_stamped_shape(self):
        assert route.envelope_quality(_stamped("partial", ["branch_deferred:x"])) == (
            "partial",
            ["branch_deferred:x"],
        )

    def test_the_task_reads_the_envelope_through_the_route_helper(self):
        """Containment, anchored on the CALL — the two must not re-derive the
        field independently, which is exactly how they drifted apart."""
        import inspect

        from app.tasks import prop_families_warm as warm

        src = inspect.getsource(warm._refresh_prop_families)
        assert "envelope_quality(" in src
        assert "QUALITY_FULL" in src

    def test_the_two_reason_prefixes_are_declared_once_and_used(self):
        """The prefixes are the vocabulary the bound is written in. A second
        spelling in a `note_build_loss` call would silently stop
        `_deferral_reasons` recognising an IOU."""
        import inspect

        src = inspect.getsource(route.build_prop_families)
        assert '"branch_timeout:' not in src and '"branch_deferred:' not in src
        assert route._REASON_TIMEOUT == "branch_timeout:"
        assert route._REASON_DEFERRED == "branch_deferred:"

    def test_deferral_reasons_selects_only_the_ious(self):
        assert route._deferral_reasons(
            ["branch_timeout:a", "branch_deferred:b", "something_else"]
        ) == ["branch_deferred:b"]
        assert route._deferral_reasons([]) == []

    def test_the_branch_timeout_constant_is_declared_exactly_once(self):
        """CERT-557 finding 3. Two identical declarations of one policy is a
        future edit that changes the one nobody is reading."""
        import inspect

        src = inspect.getsource(route)
        assert src.count("_BRANCH_TIMEOUT_MS = 12000") == 1
        assert route._BRANCH_TIMEOUT_MS == 12000


class TestTheBackgroundPathStillHasNoBudget:
    """Re-asserted here rather than only in the LAT-P164 file: the completion
    path is what this repair touched, and a completion that inherited the
    reader's budget could never complete anything, so the whole repair would be
    a more honest report of a permanent loss."""

    def test_the_refresh_task_passes_no_budget(self):
        import inspect

        from app.tasks import prop_families_warm as warm

        src = inspect.getsource(warm._refresh_prop_families)
        assert "build_and_cache_prop_families" in src
        assert "budget_ms" not in src

    def test_the_warm_pass_passes_no_budget(self):
        import inspect

        from app.tasks import prop_families_warm as warm

        src = inspect.getsource(warm._warm_prop_families)
        assert "build_and_cache_prop_families" in src
        assert "budget_ms" not in src
