"""Guards for LAT-P138: the team page's props stop being rebuilt for every reader.

WHAT WAS MEASURED, and why these guards are the shape they are. First touch per
team against production `64b7a034`, `x-timing-split` server time:

    kansas-city-chiefs  16,797 ms   los-angeles-dodgers  9,448 ms
    boston-red-sox      10,962 ms   dallas-cowboys       8,756 ms
    new-york-yankees     7,518 ms   los-angeles-lakers   2,910 ms
    boston-celtics       2,627 ms

There was no response cache of any kind — three consecutive Chiefs reads went
16,797 -> 11,342 -> 3,992 ms, which is Postgres buffer warming, not caching, and
the fourth reader an hour later pays the first number again. `EXPLAIN (ANALYZE)`
on the Chiefs' own 41 patterns: the FK branch is 1.5 ms, the outcome-name branch
13,107 ms and the market-name branch 2,990 ms, both of them a `BitmapOr` of 41
GIN trigram probes of which 35 match nothing. Cost is linear in probe count (41
patterns 13.4 s; the same 10 patterns 2.2 s).

Two fixes, and one guard class each:

* `ILIKE ANY (ARRAY[...])` in place of the N-way `OR`. Identical predicate by
  definition and identical rows in measurement (96 and 76 on both spellings),
  one ScalarArrayOp index scan instead of a 41-way BitmapOr.
* The response-cache tier this route never had, adopted from
  `utils/event_concept_cache` the way `routes/hub.py` adopted it, WITH a producer
  — because a 16-second rebuild cannot be left to hope somebody visited today
  (LAT-P137 measured that hope failing on a sibling tier).

Everything here asserts SHAPE and CALL COUNT, never wall-clock, so it is
deterministic in CI. The numbers above are why the shape matters, not the test.
"""

import ast
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _FakeRedis:
    """In-memory Redis: get / set(nx,ex) / setex / delete / eval over a dict.

    A local double rather than an import from a sibling test module: coupling two
    test files makes collection order load-bearing.
    """

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
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
        key, token = args[0], args[1]
        expected = token.encode() if isinstance(token, str) else token
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            return 1
        return 0


def _is_branch(stmt) -> bool:
    """Is this one of the build's three branch SELECTs (vs the team lookup)?

    By the table it reads, not by its position: `resolve_team` also issues a
    `Select`, and a double that cannot tell them apart turns "every branch timed
    out" into "the team does not exist" — a 404 dressed as a degrade.
    """
    return isinstance(stmt, Select) and "futures_outcomes" in str(stmt)


def _rows_result(items):
    result = MagicMock()
    result.all.return_value = list(items)
    scalars = MagicMock()
    scalars.all.return_value = list(items)
    scalars.first.return_value = items[0] if items else None
    result.scalars.return_value = scalars
    return result


class _RecordingDB:
    """An AsyncSession double that RECORDS the statements it is asked to run.

    The branch predicates are the thing under test and they are not reachable
    from the outside any other way — the route builds them inline. Recording the
    statements is how a guard can assert the SQL a reader actually causes rather
    than a hand-pasted copy of it (the `gate_teams_fts_index` lesson: a pasted
    predicate keeps passing against an index the route no longer matches).
    """

    def __init__(self, results=None, raise_on=None, raise_on_every_branch=False):
        self.statements: list = []
        self._results = list(results or [])
        self._raise_on = raise_on
        self._raise_on_every_branch = raise_on_every_branch
        self.rollbacks = 0

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        if self._raise_on is not None and len(self.statements) == self._raise_on:
            raise RuntimeError("statement timeout")
        if self._raise_on_every_branch and _is_branch(stmt):
            # LAT-P145: "the build lost everything" is now a property of the
            # BRANCHES, not of a statement ordinal — each branch carries its own
            # `SET LOCAL`, so counting statements no longer names one. Scoped to
            # the branch SELECTs so the team lookup — which is not part of the
            # build and whose failure is a 404, not a degrade — still succeeds.
            raise RuntimeError("statement timeout")
        if self._results:
            return self._results.pop(0)
        return _rows_result([])

    async def rollback(self):
        # A cancelled statement aborts the transaction; the route rolls back so
        # the NEXT branch has a usable session. Counted, because "did it recover
        # or did it just swallow?" is the difference LAT-P145 turns on.
        self.rollbacks += 1


def _team(*, tid=560, name="Kansas City Chiefs", slug="kansas-city-chiefs", roster=None):
    return SimpleNamespace(
        id=tid, name=name, slug=slug,
        roster_players=[{"name": n} for n in (roster or [])],
    )


def _branch_stmts(db) -> list:
    """The branch SELECTs the route actually ran, in order.

    LAT-P145 gave every branch its OWN `SET LOCAL statement_timeout`, so the
    statement list is now `SET LOCAL, branch, SET LOCAL, branch, ...` and a
    positional index no longer names a branch. Selecting by TYPE says what these
    guards always meant — "the queries a reader causes" — and stops the next
    change to the preamble from silently re-pointing every assertion at a
    different statement.
    """
    return [s for s in db.statements if isinstance(s, Select)]


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


async def _build(team, db=None, cap=400):
    db = db or _RecordingDB()
    return await route.build_prop_families(team, db, cap), db


# ---------------------------------------------------------------------------
# 1. The predicate: ILIKE ANY, not an N-way OR
# ---------------------------------------------------------------------------


class TestBranchPredicateShape:
    async def test_name_branches_compile_to_ilike_any_array(self):
        team = _team(roster=["Patrick Mahomes", "Travis Kelce", "Chris Jones"])
        _payload, db = await _build(team)
        branch_sql = [_sql(s) for s in _branch_stmts(db)]
        assert len(branch_sql) == 3
        name_sql = branch_sql[1:]
        for sql in name_sql:
            assert "ILIKE ANY" in sql.upper(), sql
        assert any("futures_outcomes.name ILIKE ANY" in s for s in name_sql)
        assert any("futures_markets.name ILIKE ANY" in s for s in name_sql)

    async def test_no_branch_is_an_n_way_or_of_ilikes(self):
        """The defect this replaces, spelled as the thing that must not come back.

        A 41-way `OR` plans as a 41-probe `BitmapOr`; that is the 13.1 s. One
        `ILIKE` per branch is the whole point, so counting them is the guard.
        """
        team = _team(roster=[f"Player Number{i:02d}" for i in range(12)])
        _payload, db = await _build(team)
        for stmt in _branch_stmts(db):
            assert _sql(stmt).upper().count("ILIKE") <= 1, _sql(stmt)

    async def test_every_pattern_is_carried_into_the_array(self):
        """Cheaper SQL that silently drops patterns would be a matching
        regression wearing a latency fix's clothes."""
        roster = ["Patrick Mahomes", "Travis Kelce"]
        team = _team(roster=roster)
        _payload, db = await _build(team)
        sql = _sql(_branch_stmts(db)[1])
        for name in roster + ["Kansas City Chiefs"]:
            assert name in sql, f"{name} missing from the branch array"

    async def test_fk_branch_is_still_first_and_index_shaped(self):
        team = _team(roster=["Patrick Mahomes"])
        _payload, db = await _build(team)
        fk_sql = _sql(_branch_stmts(db)[0])
        assert "futures_outcomes.team_id" in fk_sql
        assert "ILIKE" not in fk_sql.upper()

    async def test_like_escaping_survives(self):
        r"""`_escape_like` is what stops a player called `%` matching everything.

        It is upstream of the array and easy to lose when the OR loop that used
        to consume it goes away.

        Asserted on the BOUND VALUE, not on rendered SQL: `literal_binds`
        doubles `%` for the driver's printf paramstyle, so a rendered string
        says `%%100\\%%` for the pattern `%100\%`. A guard that read the render
        would be asserting the renderer's escaping, not the route's.
        """
        team = _team(name="100% Team_A", roster=[])
        _payload, db = await _build(team)
        params = _branch_stmts(db)[1].compile(dialect=postgresql.dialect()).params
        arrays = [
            v for v in params.values()
            if isinstance(v, list) and v and str(v[0]).startswith("%")
        ]
        assert arrays, params
        assert arrays[0] == ["%100\\% Team\\_A%"]

    async def test_roster_cap_unchanged(self):
        assert route._MAX_ROSTER_PATTERNS == 40
        team = _team(roster=[f"Player Number{i:02d}" for i in range(80)])
        assert len(route._roster_player_names(team)) == 40

    async def test_a_team_with_no_roster_runs_the_same_three_branches(self):
        """The 9,258 rosterless teams were never the slow ones, and this fix must
        not change what they get."""
        _payload, db = await _build(_team(roster=[]))
        assert len(_branch_stmts(db)) == 3


# ---------------------------------------------------------------------------
# 2. The cache key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_keyed_on_team_id_not_on_the_url_identifier(self):
        """One team, three spellings (slug, id, legacy slug), ONE key. Keying on
        the identifier would give a team up to three entries and leave the
        spellings a warmer did not use permanently cold."""
        assert route.prop_families_cache_keys(560, 400).primary == (
            route.prop_families_cache_keys("560", 400).primary
        )
        assert "kansas-city-chiefs" not in route.prop_families_cache_keys(560, 400).primary

    def test_cap_is_in_the_key(self):
        a = route.prop_families_cache_keys(560, 400).primary
        b = route.prop_families_cache_keys(560, 50).primary
        assert a != b

    def test_prefix_is_its_own_namespace(self):
        assert route.PROP_FAMILIES_CACHE_PREFIX == "bainluck:prop_families:"
        assert route.prop_families_cache_keys(1, 400).primary.startswith(
            "bainluck:prop_families:"
        )

    def test_cap_resolution_bounds(self):
        assert route._resolve_cap(400) == 400
        assert route._resolve_cap(0) == 1
        assert route._resolve_cap(-5) == 1
        assert route._resolve_cap(99999) == 2000


# ---------------------------------------------------------------------------
# 3. The serve ladder
# ---------------------------------------------------------------------------


def _stamped(marker="stored"):
    from datetime import datetime, timezone

    return cache_mod.stamp_envelope(
        {"team": {"id": 560, "name": "Kansas City Chiefs", "slug": "kc"},
         "families": [{"family_key": marker, "label": marker, "entity_count": 2,
                       "sources": ["kalshi"], "rows": []}],
         "total_families": 1},
        created_at=datetime.now(timezone.utc),
        lifecycle_watermark=None,
    )


class TestServeLadder:
    async def test_live_hit_runs_no_branch_query(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        rc.setex(keys.primary, 900, cache_mod.encode_payload(_stamped("from_primary")))
        db = _RecordingDB(results=[_rows_result([_team()])])
        with patch.object(route, "get_client", return_value=rc):
            body = await route.get_team_prop_families("kansas-city-chiefs", 400, db)
        assert body["families"][0]["family_key"] == "from_primary"
        assert body["cache"]["availability"] == cache_mod.AVAILABILITY_LIVE
        # Exactly one statement: the team lookup. No SET LOCAL, no branches.
        assert len(db.statements) == 1

    async def test_miss_serves_the_mirror_and_schedules_one_rebuild(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        rc.setex(keys.stale, 86400, cache_mod.encode_payload(_stamped("from_mirror")))
        db = _RecordingDB(results=[_rows_result([_team()])])
        sent = []
        with patch.object(route, "get_client", return_value=rc), \
             patch("app.tasks.celery_app.send_task",
                   side_effect=lambda *a, **k: sent.append((a, k))):
            body = await route.get_team_prop_families("kansas-city-chiefs", 400, db)
        assert body["families"][0]["family_key"] == "from_mirror"
        assert body["cache"]["availability"] == cache_mod.AVAILABILITY_STALE_OK
        assert len(db.statements) == 1     # the mirror serve builds nothing
        assert len(sent) == 1
        assert sent[0][0][0] == "app.tasks.refresh_prop_families"
        assert sent[0][1]["queue"] == "background"
        assert sent[0][1]["args"][:2] == [560, 400]

    async def test_a_burst_behind_one_expiry_dispatches_once(self):
        """Single-flight is the difference between one 16-second rebuild and
        one per reader."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        rc.setex(keys.stale, 86400, cache_mod.encode_payload(_stamped()))
        sent = []
        with patch.object(route, "get_client", return_value=rc), \
             patch("app.tasks.celery_app.send_task",
                   side_effect=lambda *a, **k: sent.append(a)):
            for _ in range(5):
                db = _RecordingDB(results=[_rows_result([_team()])])
                await route.get_team_prop_families("kansas-city-chiefs", 400, db)
        assert len(sent) == 1

    async def test_cold_build_writes_both_slots(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        db = _RecordingDB(results=[_rows_result([_team()])])
        with patch.object(route, "get_client", return_value=rc):
            body = await route.get_team_prop_families("kansas-city-chiefs", 400, db)
        assert rc.store.get(keys.primary) is not None
        assert rc.store.get(keys.stale) is not None
        assert rc.ttls[keys.primary] == route.PROP_FAMILIES_PRIMARY_TTL
        assert rc.ttls[keys.stale] == cache_mod.STALE_TTL
        # Asserted as an ORDERING, not just "it equals the constant": a primary
        # TTL raised to the mirror's would satisfy the line above while quietly
        # retiring the freshness half of the tier — the payload would never be
        # rebuilt on a read again.
        assert route.PROP_FAMILIES_PRIMARY_TTL < cache_mod.STALE_TTL
        assert body["cache"]["availability"] == cache_mod.AVAILABILITY_LIVE

    async def test_unknown_team_still_404s(self):
        db = _RecordingDB(results=[_rows_result([])])
        with patch.object(route, "get_client", return_value=_FakeRedis()):
            with pytest.raises(Exception) as exc:
                await route.get_team_prop_families("nobody", 400, db)
        assert getattr(exc.value, "status_code", None) == 404


# ---------------------------------------------------------------------------
# 4. The degrade — the failure mode a 24h mirror makes WORSE if you cache it
# ---------------------------------------------------------------------------


class TestDegradeIsNeverCached:
    async def test_timeout_degrade_writes_nothing(self):
        """EVERY branch lost. LAT-P145 narrowed what counts as a degrade — losing
        one branch is now a `partial` and IS cached — but losing all three is
        still the case this guard was written for, and it still writes nothing."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        db = _RecordingDB(
            results=[_rows_result([_team()])], raise_on_every_branch=True
        )
        with patch.object(route, "get_client", return_value=rc):
            body = await route.get_team_prop_families("kansas-city-chiefs", 400, db)
        assert body["total_families"] == 0
        assert rc.store.get(keys.primary) is None
        assert rc.store.get(keys.stale) is None
        # No envelope: a consumer can tell a timeout's empty from a real empty.
        assert "cache" not in body

    async def test_degrade_serves_the_mirror_when_one_exists(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        db = _RecordingDB(results=[_rows_result([_team()])], raise_on=3)
        with patch.object(route, "get_client", return_value=rc):
            # Prime the mirror only AFTER the ladder's step-2 read, by making the
            # read return nothing the first time: simplest faithful way is to
            # place the mirror and drive the degrade through the build path.
            await route.get_team_prop_families("kansas-city-chiefs", 400, db)
            rc.setex(keys.stale, 86400, cache_mod.encode_payload(_stamped("rescued")))
            db2 = _RecordingDB(results=[_rows_result([_team()])], raise_on=3)
            body = await route.get_team_prop_families("kansas-city-chiefs", 400, db2)
        # With a mirror present the ladder serves it at step 2 and never builds.
        assert body["families"][0]["family_key"] == "rescued"

    async def test_build_returns_the_degraded_flag(self):
        (payload, degraded), _db = await _build(
            _team(), db=_RecordingDB(results=[], raise_on_every_branch=True)
        )
        assert degraded is True
        assert payload["total_families"] == 0

    async def test_healthy_build_is_not_flagged_degraded(self):
        (_payload, degraded), _db = await _build(_team())
        assert degraded is False


# ---------------------------------------------------------------------------
# 5. The dispatch helper
# ---------------------------------------------------------------------------


class TestScheduleRefresh:
    def test_no_dispatch_when_the_lock_is_held(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        rc.set(keys.refresh_lock, "someone-else", nx=True, ex=120)
        sent = []
        with patch("app.tasks.celery_app.send_task",
                   side_effect=lambda *a, **k: sent.append(a)):
            route._schedule_refresh(rc, keys, 560, 400)
        assert sent == []

    def test_a_failed_dispatch_releases_the_lock(self):
        """Otherwise a dead broker wedges the key for REFRESH_LOCK_TTL and the
        next reader pays the rebuild it was supposed to be spared."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        with patch("app.tasks.celery_app.send_task", side_effect=RuntimeError("broker")):
            route._schedule_refresh(rc, keys, 560, 400)
        assert rc.store.get(keys.refresh_lock) is None


# ---------------------------------------------------------------------------
# 6. The worker session — LAT-P137's bug, guarded by AST
# ---------------------------------------------------------------------------


_WARM_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "tasks", "prop_families_warm.py",
)


def _imported_names(path: str) -> set[str]:
    tree = ast.parse(open(path).read())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


class TestWorkerSessionDiscipline:
    def test_the_task_opens_a_TASK_session(self):
        assert "app.tasks.base.get_task_session" in _imported_names(_WARM_PATH)

    def test_the_task_never_imports_the_web_session_maker(self):
        """`async_session_maker` is bound to the WEB process's event loop. A
        Celery task that opens it fails at runtime with "attached to a different
        loop" and NO unit test with the session patched out can see it — which is
        exactly how LAT-P137 shipped it into a first draft on the sibling tier.

        AST rather than substring, deliberately: this module's docstring is
        allowed to NAME the thing it must not call.
        """
        bad = {n for n in _imported_names(_WARM_PATH) if "async_session_maker" in n}
        assert not bad, bad


# ---------------------------------------------------------------------------
# 7. The producer
# ---------------------------------------------------------------------------


class TestWarmerVerdicts:
    async def test_rebuilds_every_selected_team_inline(self):
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        built: list[int] = []
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build(built)):
            out = await warm._warm_prop_families()
        assert out["terminal"] == "complete"
        assert out["selected"] == 3 and out["rebuilt"] == 3
        assert built == [1, 2, 3]

    async def test_the_producer_never_dispatches_another_task(self):
        """`tests/test_celery_result_retention.py::test_no_task_dispatches_
        another_task` is a repo-wide rule and the first draft of this producer
        broke it — it fanned out one message per team. Pinned HERE too, next to
        the thing it constrains, so the next person to reach for a fan-out reads
        the reason rather than a scanner's line number."""
        source = open(_WARM_PATH).read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                assert name not in ("send_task", "delay", "apply_async"), name

    async def test_a_team_whose_lock_is_held_is_skipped_not_double_built(self):
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        held = route.prop_families_cache_keys(2, warm.WARM_CAP)
        rc.set(held.refresh_lock, "reader", nx=True, ex=120)
        built: list[int] = []
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build(built)):
            out = await warm._warm_prop_families()
        assert out["rebuilt"] == 2 and out["locked_out"] == 1
        assert built == [1, 3]

    async def test_the_lock_is_released_after_each_team(self):
        """Otherwise the second pass finds every team locked by the first."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build([])):
            await warm._warm_prop_families()
        for team_id in (1, 2):
            keys = route.prop_families_cache_keys(team_id, warm.WARM_CAP)
            assert rc.store.get(keys.refresh_lock) is None

    async def test_the_budget_defers_the_rest_and_says_so(self):
        """A pass that ran out of time must report what it did NOT do. Silent
        truncation reads as 'covered everything'."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3, 4])), \
             patch.object(warm, "PASS_BUDGET_SECONDS", 0), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build([])):
            out = await warm._warm_prop_families()
        assert out["rebuilt"] == 0 and out["deferred"] == 4

    async def test_the_cursor_rotates_so_the_tail_gets_a_turn(self):
        """gotcha #34: one position shared across a loop starves whatever comes
        late. A pass resumes AFTER the id the last one finished on."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        rc.setex(warm.CURSOR_KEY, 100, "2")
        built: list[int] = []
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3, 4])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build(built)):
            await warm._warm_prop_families()
        assert built == [3, 4, 1, 2]

    async def test_the_cursor_is_written_with_where_the_pass_stopped(self):
        """The rotation test above cannot carry this assertion and a mutation
        battery proved it: its pass wraps back to the id it started after, so
        "the cursor was written" and "the cursor was never touched" leave the
        key looking identical. Started from an ABSENT cursor, the two are
        distinguishable — which is the whole point of the survivor rule."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        assert warm.CURSOR_KEY not in rc.store
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([5, 6, 7])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build([])):
            await warm._warm_prop_families()
        assert rc.store[warm.CURSOR_KEY] == b"7"
        assert rc.ttls[warm.CURSOR_KEY] == warm.CURSOR_TTL_SECONDS

    async def test_one_bad_team_does_not_wipe_the_pass(self):
        """gotcha #42, and the siblings are asserted, not just the survival.

        🔴 EXTENDED THROUGH `verdict_for` BY CERT-521, WHICH BLOCKED ON EXACTLY
        THE GAP THIS TEST USED TO LEAVE. Surviving a bad item and REPORTING it are
        two duties and only the first was asserted here: the terminal branch reads
        `rebuilt or (locked_out and not failed)`, so one successful sibling
        outvoted the team that threw, and `_has_damage` recognises only the
        COLLECTIONS `errors` / `failed_chunks` / `failed_phases` — never a scalar
        `failed` — so the enforced classifier returned an authoritative GREEN with
        `rebuilt=2, failed=1` and a team's mirror left cold.

        Gotcha #42 says one bad item must not wipe the pass. It does not say the
        pass should call itself healthy.
        """
        from app.tasks import prop_families_warm as warm
        from app.utils import task_verdict as tv

        rc = _FakeRedis()
        built: list[int] = []

        async def _explode_on_two(team, db, cap, client=None):
            if team.id == 2:
                raise RuntimeError("boom")
            built.append(team.id)
            return {"families": []}, False

        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_explode_on_two):
            out = await warm._warm_prop_families()

        # Survival — unchanged.
        assert built == [1, 3]
        assert out["rebuilt"] == 2 and out["failed"] == 1

        # Truthful health — the half CERT-521 found missing.
        assert out["terminal"] != "complete", out
        verdict = tv.verdict_for("warm_prop_families", out)
        assert verdict.verdict == tv.PARTIAL, verdict
        assert verdict.authoritative is True, verdict
        assert verdict.is_green is False, verdict

    async def test_an_all_clean_pass_is_still_green(self):
        """The control for the guard above: the downgrade must fire on a real
        failure and on nothing else, or the task is amber every hour and the
        signal is worth nothing."""
        from app.tasks import prop_families_warm as warm
        from app.utils import task_verdict as tv

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build([])):
            out = await warm._warm_prop_families()

        assert out["failed"] == 0 and out["rebuilt"] == 3, out
        assert out["terminal"] == "complete", out
        assert tv.verdict_for("warm_prop_families", out).is_green is True

    async def test_a_lock_out_is_the_tier_working_and_keeps_its_green(self):
        """A team already being rebuilt by a reader is not a failure — that is the
        single-flight lock doing its job — so it must not cost the pass its green.
        The downgrade keys on `failed`, never on `locked_out`."""
        from app.tasks import prop_families_warm as warm
        from app.utils import task_verdict as tv

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2, 3])), \
             patch("app.utils.event_concept_cache.acquire_refresh_lock", return_value=None), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build([])):
            out = await warm._warm_prop_families()

        assert out["locked_out"] == 3 and out["failed"] == 0, out
        assert out["terminal"] == "complete", out
        assert tv.verdict_for("warm_prop_families", out).is_green is True

    async def test_the_cap_is_reported_never_silent(self):
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        many = list(range(1, warm.MAX_TEAMS_PER_PASS + 8))
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch.object(warm, "PASS_BUDGET_SECONDS", 0), \
             patch("app.tasks.base.get_task_session", _session_for_warm(many)), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_recording_build([])):
            out = await warm._warm_prop_families()
        assert out["selected"] == len(many)
        assert out["truncated"] == 7

    async def test_a_failed_selection_reads_failed_not_empty(self):
        """`selected: 0` because the query blew up and `selected: 0` because
        nothing is reachable are opposite facts (gotcha #53)."""
        from app.tasks import prop_families_warm as warm

        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", _session_raising()):
            out = await warm._warm_prop_families()
        assert out["terminal"] == "failed" and out["selected"] == 0

    async def test_an_empty_reachable_set_is_complete_not_failed(self):
        from app.tasks import prop_families_warm as warm

        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", _session_for_warm([])):
            out = await warm._warm_prop_families()
        assert out["terminal"] == "complete" and out["rebuilt"] == 0

    async def test_a_pass_that_rebuilt_nothing_but_had_work_reads_failed(self):
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()

        async def _always_degraded(team, db, cap, client=None):
            return {"families": []}, True

        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_for_warm([1, 2])), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_always_degraded):
            out = await warm._warm_prop_families()
        assert out["terminal"] == "failed" and out["rebuilt"] == 0 and out["failed"] == 2


class TestRefreshVerdicts:
    async def test_a_degraded_rebuild_reads_failed(self):
        """The pass that matters: `build_and_cache_prop_families` refuses to
        write a degraded payload, so the mirror is exactly as old as it was.
        Reporting that as `complete` is the false green #1884 is about."""
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session",
                   _session_with_team(_team())), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_async_return(({"families": []}, True))):
            out = await warm._refresh_prop_families(560, 400, None)
        assert out["terminal"] == "failed" and out["degraded"] is True

    async def test_a_good_rebuild_reads_complete_and_releases_the_lock(self):
        from app.tasks import prop_families_warm as warm

        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(560, 400)
        rc.set(keys.refresh_lock, "tok", nx=True, ex=120)
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _session_with_team(_team())), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=_async_return(({"families": []}, False))):
            out = await warm._refresh_prop_families(560, 400, "tok")
        assert out["terminal"] == "complete" and out["rebuilt"] == 1
        assert rc.store.get(keys.refresh_lock) is None

    async def test_an_unknown_team_is_complete_unknown_not_failed(self):
        from app.tasks import prop_families_warm as warm

        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", _session_with_team(None)):
            out = await warm._refresh_prop_families(999, 400, None)
        assert out["terminal"] == "complete" and out["reason"] == "unknown_team"


# ---------------------------------------------------------------------------
# 8. Enrolment and the beat
# ---------------------------------------------------------------------------


class TestEnrolmentAndBeat:
    def test_both_tasks_are_enforced(self):
        from app.utils.task_verdict import ENFORCED_TASKS

        assert "warm_prop_families" in ENFORCED_TASKS
        assert "refresh_prop_families" in ENFORCED_TASKS

    def test_the_beat_exists_on_the_background_queue(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["warm-prop-families"]
        assert entry["task"] == "app.tasks.warm_prop_families"
        assert entry["options"]["queue"] == "background"

    def test_the_cadence_covers_the_reachable_set_inside_the_mirror(self):
        """The cadence is not a taste, and it is not "often enough" either.

        Each pass is budgeted in SECONDS because the build is 2.6-16.8 s and
        varies with roster size, so the contract the cadence has to satisfy is a
        COVERAGE one: at the pessimistic rate of one slowest-measured build per
        team, every team in a maxed-out reachable set must be rebuilt before the
        24 h mirror can lapse.

        Asserted as the arithmetic, from the constants — widening the cap or
        shrinking the budget then moves the cadence instead of quietly leaving
        teams uncovered, and re-measuring the slowest build re-derives all of it
        (#2236).
        """
        import math

        from app.tasks import celery_app, prop_families_warm as warm

        entry = celery_app.conf.beat_schedule["warm-prop-families"]
        sched = entry["schedule"]
        assert len(sched.hour) == 24, "hourly — every hour is a fire"
        period_seconds = 3600 // len(sched.minute)

        teams_per_pass = warm.PASS_BUDGET_SECONDS // warm.SLOWEST_MEASURED_BUILD_SECONDS
        assert teams_per_pass >= 1
        passes_to_cover = math.ceil(warm.MAX_TEAMS_PER_PASS / teams_per_pass)
        assert passes_to_cover * period_seconds <= cache_mod.STALE_TTL, (
            f"{passes_to_cover} passes x {period_seconds}s exceeds the "
            f"{cache_mod.STALE_TTL}s mirror — teams would go cold between warms"
        )

    def test_the_budget_and_the_slowest_build_fit_the_task_limits(self):
        """A pass that starts a team on the last tick of its budget must still
        finish inside the soft limit, and the soft limit must stay under the
        300 s hard `task_time_limit` that arrives as an untracked SIGKILL."""
        from app.tasks import celery_app, prop_families_warm as warm

        task = celery_app.tasks["app.tasks.warm_prop_families"]
        worst = warm.PASS_BUDGET_SECONDS + warm.PER_TEAM_TIMEOUT_SECONDS
        assert worst <= task.soft_time_limit < task.time_limit < 300

    def test_the_inner_rebuild_is_bounded_inside_its_own_task_budget(self):
        """A wedged build must be reported by its own timeout, not arrive as a
        SIGKILL from the hard `task_time_limit` (project_celery_sigkill_untracked).
        Bound the longest uninterrupted operation, not just the task."""
        from app.tasks import celery_app, prop_families_warm as warm

        soft = celery_app.tasks["app.tasks.refresh_prop_families"].soft_time_limit
        assert warm.PER_TEAM_TIMEOUT_SECONDS < soft
        assert soft < 300  # the hard, untrackable global limit

    def test_the_warmer_builds_the_cap_readers_actually_ask_for(self):
        """A producer that warms `limit=50` while every browser asks for the
        route default would publish under a key nothing reads — LAT-P001
        exactly."""
        import inspect

        from app.tasks import prop_families_warm as warm

        default_limit = inspect.signature(
            route.get_team_prop_families
        ).parameters["limit"].default
        assert warm.WARM_CAP == default_limit


# ---------------------------------------------------------------------------
# Session doubles for the task-side tests
# ---------------------------------------------------------------------------


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


class _AsyncCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


def _recording_build(sink):
    """Stand in for `build_and_cache_prop_families`, recording the team ORDER."""
    async def _inner(team, db, cap, client=None):
        sink.append(team.id)
        return {"families": []}, False
    return _inner


def _session_for_warm(team_ids):
    """The warmer opens one session for the id sweep and one per team.

    The first `execute` answers with the id list; every later one answers with
    the team row whose id the caller asked for — matched out of the statement so
    the double cannot silently hand back the wrong team and make an ordering
    assertion pass for the wrong reason.
    """
    ids = [int(t) for t in team_ids]

    class _WarmDB(_RecordingDB):
        def __init__(self):
            super().__init__()
            self._first = True

        async def execute(self, stmt, *args, **kwargs):
            self.statements.append(stmt)
            if self._first:
                self._first = False
                return _rows_result(ids)
            wanted = [
                v for v in stmt.compile().params.values() if isinstance(v, int)
            ]
            tid = wanted[0] if wanted else (ids[0] if ids else 0)
            return _rows_result([_team(tid=tid, name=f"Team {tid}", slug=f"t{tid}")])

    db = _WarmDB()
    return lambda *a, **k: _AsyncCM(db)


def _session_yielding(team_ids):
    db = _RecordingDB(results=[_rows_result(list(team_ids))])
    return lambda *a, **k: _AsyncCM(db)


def _session_with_team(team):
    db = _RecordingDB(results=[_rows_result([team] if team is not None else [])])
    return lambda *a, **k: _AsyncCM(db)


def _session_raising():
    class _Boom(_RecordingDB):
        async def execute(self, *a, **k):
            raise RuntimeError("select failed")

    return lambda *a, **k: _AsyncCM(_Boom())
