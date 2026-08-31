"""Guards for LAT-P145: a team page stops waiting twelve seconds to show nothing.

WHAT WAS MEASURED. Production `944c466e`, 2026-08-30, three NFL team pages,
`x-timing-split` server time, first touch and every touch after it:

    new-york-giants      12,638 ms  wall=12,376  db=281  app=12,096  q=3  unfinished=1
    green-bay-packers    12,658 ms  wall=12,375  db=267  app=12,109  q=3  unfinished=1
    pittsburgh-steelers  12,908 ms  wall=12,389  db=284  app=12,106  q=3  unfinished=1

All three returned `total_families: 0` and NO cache envelope. `app_ms` ≈ the whole
wall with `db_ms` in the hundreds is the signature of a cancelled statement, not
of slow Python: `after_cursor_execute` does not fire for a cancelled cursor, so a
statement killed by `SET LOCAL statement_timeout` contributes zero to `db_ms` and
its whole duration is billed to the application. `unfinished=1` says it outright.

`q=3` is the finding. The three statements that COMPLETED are the team lookup,
the `SET LOCAL`, and the **team_id branch** — which had already returned its rows
(27, 29 and 31 for the three teams, counted in the same minute) when the
outcome-name branch was cancelled. Postgres aborts a transaction whose statement
is cancelled, so one expiry lost three things: branch 2's rows, branch 3's turn,
and branch 1's rows, which were sitting in memory. The empty payload that came
out is then — correctly — never cached, so the next reader repeated it. The ring
holds 13 such requests in one four-minute window, 12,074-12,195 ms each.

The population is not exotic. 285 of the 367 rostered teams sit outside the
warmer's reachable set (`roster AND a fixture within ±14 days`), and in late
August that set excludes most of the NFL — the Giants, Packers, Steelers,
Commanders, Broncos, Eagles, Cardinals and Panthers were all in it while their
season was more than a fortnight out.

WHAT THESE GUARDS PIN, and what they deliberately do not. Every assertion here is
about SHAPE, CALL COUNT and STORED BYTES — never wall-clock, so CI is
deterministic. The 12,000 ms budget itself is asserted to be UNCHANGED: LAT-P145
changed who survives an expiry, not how long the expiry takes, and a guard suite
that let the budget drift would let this ship quietly buy its win by making
complete builds fail.
"""

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Select

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod
from app.utils.statement_timeout import is_statement_timeout


# ---------------------------------------------------------------------------
# Doubles — local, because coupling two test modules makes collection order
# load-bearing.
# ---------------------------------------------------------------------------


def _as_bytes(value):
    return value.encode() if isinstance(value, str) else value


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.writes: list[str] = []

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
        self.writes.append(k)
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)

    def eval(self, script, numkeys, *args):
        """Both Lua scripts, dispatched on script IDENTITY.

        Modelled on Redis's documented semantics, not on what the caller happens
        to want: a missing key reads as false inside Lua, so a byte comparison
        against an absent key is unequal and the guarded write does NOT happen.
        Getting that arm wrong is what would make the race guards vacuous.
        """
        key = args[0]
        if script is cache_mod._SETEX_IF_UNCHANGED_LUA:
            absent_only, expected, ttl, value = args[1], args[2], args[3], args[4]
            current = self.store.get(key)
            if absent_only == "1":
                if current is not None:
                    return 0
            elif current != _as_bytes(expected):
                return 0
            self.writes.append(key)
            self.ttls[key] = int(ttl)
            self.store[key] = _as_bytes(value)
            return 1
        expected = _as_bytes(args[1])
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            return 1
        return 0


class QueryCanceledError(Exception):
    """What asyncpg raises when our own `SET LOCAL statement_timeout` fires.

    🔴 SPELLED WITH THE DRIVER'S EXACT CLASS NAME, and that is not cosmetic: the
    predicate's first arm matches on `type(exc).__name__`, so a double called
    anything else exercises only the message arm and leaves the name arm — the
    one that survives a driver rewording its text — untested.
    """


def _outcome(oid, name, prob, market_id, *, winner=False):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        market_id=market_id, is_winner=winner,
    )


def _market(mid, name, *, source="kalshi", group_id=None, status="open"):
    return SimpleNamespace(
        id=mid, name=name, source=source, group_id=group_id, status=status,
        resolution_date=None, market_metadata={},
    )


def _pair(oid, oname, prob, mid, mname):
    """One (outcome, market) row as the branch SELECT returns it."""
    return (_outcome(oid, oname, prob, mid), _market(mid, mname))


#: Award-shaped market names on purpose: `group_prop_families` drops any family
#: with fewer than two distinct entities, and a "…Winner 2026" name parses to no
#: family at all. A fixture that groups to nothing would make every assertion
#: below vacuously true — the empty-element trap in another costume.
FK_ROWS = [
    _pair(1, "Dexter Lawrence", 0.04, 100, "Defensive Player of the Year"),
    _pair(2, "Brian Burns", 0.06, 100, "Defensive Player of the Year"),
]
OUTCOME_NAME_ROWS = [
    _pair(5, "Malik Nabers", 0.09, 300, "Offensive Player of the Year"),
    _pair(6, "Saquon Barkley", 0.21, 300, "Offensive Player of the Year"),
]
MARKET_NAME_ROWS = [
    _pair(3, "Jaxson Dart", 0.02, 200, "NFL MVP 2026"),
    _pair(4, "Patrick Mahomes", 0.14, 200, "NFL MVP 2026"),
]


def _rows_result(items):
    result = MagicMock()
    result.all.return_value = list(items)
    scalars = MagicMock()
    scalars.all.return_value = list(items)
    scalars.first.return_value = items[0] if items else None
    result.scalars.return_value = scalars
    return result


def _is_branch(stmt) -> bool:
    return isinstance(stmt, Select) and "futures_outcomes" in str(stmt)


class _BranchDB:
    """An AsyncSession double driven BY BRANCH, not by statement ordinal.

    `plan` is one entry per branch, in the order the route runs them
    (team_id, outcome_name, market_name): either a list of rows to return, or an
    exception instance to raise. Keying on the branch rather than on a statement
    number is the whole reason this double exists — the route now issues a
    `SET LOCAL` per branch, and a test that counted statements would be asserting
    the preamble.
    """

    def __init__(self, plan, *, team=None, rollback_raises=False):
        self.plan = list(plan)
        self.statements: list = []
        self.rollbacks = 0
        self.branch_index = 0
        self._team = team if team is not None else _team()
        self._rollback_raises = rollback_raises
        self.timeouts_set: list[str] = []

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        rendered = str(stmt)
        if "statement_timeout" in rendered:
            self.timeouts_set.append(rendered)
            return _rows_result([])
        if not _is_branch(stmt):
            return _rows_result([self._team])  # the team lookup
        i = self.branch_index
        self.branch_index += 1
        step = self.plan[i] if i < len(self.plan) else []
        if isinstance(step, BaseException):
            raise step
        return _rows_result(step)

    async def rollback(self):
        self.rollbacks += 1
        if self._rollback_raises:
            raise RuntimeError("connection gone")


#: LAT-P164 split the two name branches by pattern class, so a team WITH a
#: roster now runs five branches rather than three. Pinned as a NAMED, ORDERED
#: list and not as a bare count, because a count cannot say WHICH branches exist
#: and the split is the whole point: the cheap one-pattern team-name probes must
#: stay separate from the 40-pattern roster probes. `assert x == 5` would still
#: pass if the two were merged back into one branch and something else were
#: added — this will not.
_BRANCHES_ROSTERED = (
    route._BRANCH_TEAM_ID,
    route._BRANCH_OUTCOME_NAME,
    route._BRANCH_MARKET_NAME,
    route._BRANCH_OUTCOME_ROSTER,
    route._BRANCH_MARKET_ROSTER,
)
_N_ROSTERED = len(_BRANCHES_ROSTERED)

#: A plan that loses EVERY branch a rostered team has. Derived, so that adding a
#: branch cannot quietly turn "every branch was lost" into "most were".
def _all_timeout():
    return [_timeout() for _ in range(_N_ROSTERED)]


def _team(*, tid=547, name="New York Giants", slug="new-york-giants", roster=None):
    return SimpleNamespace(
        id=tid, name=name, slug=slug,
        roster_players=[{"name": n} for n in (roster or ["Malik Nabers"])],
    )


def _timeout():
    return QueryCanceledError("canceling statement due to statement timeout")


def _envelope(payload):
    return payload.get(cache_mod.ENVELOPE_FIELD) or {}


def _stored(rc, key):
    raw = rc.store.get(key)
    return None if raw is None else json.loads(raw)


async def _build(plan, team=None, cap=400, **kw):
    db = _BranchDB(plan, team=team, **kw)
    team = team if team is not None else _team()
    return (await route.build_prop_families(team, db, cap)), db


async def _build_and_cache(plan, rc, team=None, cap=400):
    db = _BranchDB(plan, team=team)
    team = team if team is not None else _team()
    return await route.build_and_cache_prop_families(team, db, cap, rc)


# ---------------------------------------------------------------------------
# 1. THE SHIP — one branch's timeout no longer erases the others
# ---------------------------------------------------------------------------


class TestOneBranchTimeoutDoesNotEraseTheRest:
    async def test_the_giants_case_keeps_the_rows_it_already_fetched(self):
        """The measured production shape: branch 1 landed, branch 2 was cancelled.

        Before LAT-P145 this returned `total_families: 0`. The rows were fetched
        and thrown away, which is what made the page permanently empty AND
        permanently uncacheable.
        """
        (payload, unusable), _db = await _build(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS]
        )
        assert unusable is False
        # Named exactly, not counted: a `>= 1` would pass on the market-name
        # branch alone and miss the whole point, which is that the FK branch's
        # already-fetched rows are no longer thrown away.
        assert {f["family_key"] for f in payload["families"]} == {
            "defensive player of the year",  # the FK branch — the discarded one
            "mvp",                           # the branch that used to be unreachable
        }
        assert {
            r["entity"] for f in payload["families"] for r in f["rows"]
        } == {"Dexter Lawrence", "Brian Burns", "Jaxson Dart", "Patrick Mahomes"}

    async def test_the_third_branch_still_runs_after_the_second_is_cancelled(self):
        """Branch 3 never got a turn before this fix — the aborted transaction
        made it unrunnable, which is `_run_bounded`'s "takes down the parts AFTER
        it" in another costume."""
        (_payload, _unusable), db = await _build(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS]
        )
        assert db.branch_index == _N_ROSTERED, "a branch after the cancellation was skipped"

    async def test_market_name_rows_reach_the_payload_after_a_cancellation(self):
        (payload, _unusable), _db = await _build(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS]
        )
        markets = {
            r["market_id"] for f in payload["families"] for r in f["rows"]
        }
        # Branch 3's market id, specifically. It was unreachable before this fix
        # because the aborted transaction made it unrunnable.
        assert 200 in markets, markets

    async def test_a_cancelled_branch_rolls_the_transaction_back(self):
        """Without the rollback the next branch gets "current transaction is
        aborted" and the fix delivers nothing."""
        (_payload, _unusable), db = await _build(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS]
        )
        assert db.rollbacks == 1

    async def test_two_cancellations_still_serve_the_one_branch_that_landed(self):
        (payload, unusable), db = await _build(
            [FK_ROWS, _timeout(), _timeout()]
        )
        assert unusable is False
        assert db.rollbacks == 2
        assert payload["total_families"] >= 1

    async def test_a_cancellation_on_the_FIRST_branch_lets_the_others_run(self):
        (payload, unusable), db = await _build(
            [_timeout(), OUTCOME_NAME_ROWS, MARKET_NAME_ROWS]
        )
        assert unusable is False
        assert db.branch_index == _N_ROSTERED
        assert payload["total_families"] >= 1

    async def test_a_failing_rollback_does_not_take_the_request_down(self):
        """The recovery path must never be the thing that 500s the page."""
        (payload, unusable), _db = await _build(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS], rollback_raises=True
        )
        assert unusable is False
        assert isinstance(payload, dict)

    async def test_every_branch_lost_is_still_the_unusable_answer(self):
        (payload, unusable), db = await _build(_all_timeout())
        assert unusable is True
        assert payload["total_families"] == 0
        assert db.rollbacks == _N_ROSTERED

    async def test_a_healthy_build_is_untouched(self):
        (payload, unusable), db = await _build(
            [FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS]
        )
        assert unusable is False
        assert db.rollbacks == 0
        assert payload["total_families"] >= 1

    async def test_outcomes_are_still_deduped_across_branches(self):
        """Dedup by outcome id is what stops the same row appearing three times;
        moving the merge inside the loop must not have lost it."""
        (payload, _unusable), _db = await _build(
            [FK_ROWS, FK_ROWS, FK_ROWS]
        )
        oids = [
            r.get("outcome_id")
            for f in payload["families"] for r in f["rows"]
        ]
        assert len(oids) == len(set(oids)), oids


# ---------------------------------------------------------------------------
# 2. The budget is UNCHANGED — the ship must not buy its win by failing more
# ---------------------------------------------------------------------------


class TestBudgetUnchanged:
    def test_the_branch_timeout_is_still_twelve_seconds(self):
        assert route._BRANCH_TIMEOUT_MS == 12000

    async def test_every_branch_sets_its_own_timeout(self):
        _r, db = await _build([FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS])
        assert len(db.timeouts_set) == _N_ROSTERED, db.timeouts_set

    async def test_the_timeout_statement_still_says_twelve_thousand(self):
        _r, db = await _build([FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS])
        for stmt in db.timeouts_set:
            assert "12000" in stmt, stmt

    async def test_a_branch_that_was_cancelled_still_re_sets_it_for_the_next(self):
        """A `SET LOCAL` dies with its transaction. If the rollback is not
        followed by a fresh `SET LOCAL`, branch 3 runs UNBOUNDED — the fix would
        have replaced a 12 s ceiling with none at all."""
        _r, db = await _build([FK_ROWS, _timeout(), MARKET_NAME_ROWS])
        assert len(db.timeouts_set) == _N_ROSTERED, db.timeouts_set


# ---------------------------------------------------------------------------
# 3. The envelope tells the truth about what was lost
# ---------------------------------------------------------------------------


class TestQualityIsDeclared:
    async def test_a_partial_build_is_stamped_partial(self):
        rc = _FakeRedis()
        payload, degraded = await _build_and_cache(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc
        )
        assert degraded is False
        assert _envelope(payload)["quality"] == cache_mod.QUALITY_PARTIAL

    async def test_the_lost_branch_is_named_in_quality_reasons(self):
        rc = _FakeRedis()
        payload, _ = await _build_and_cache(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc
        )
        reasons = _envelope(payload)["quality_reasons"]
        assert reasons == ["branch_timeout:outcome_name"], reasons

    async def test_both_lost_branches_are_named(self):
        rc = _FakeRedis()
        payload, _ = await _build_and_cache([FK_ROWS, _timeout(), _timeout()], rc)
        assert _envelope(payload)["quality_reasons"] == [
            "branch_timeout:outcome_name",
            "branch_timeout:market_name",
        ]

    async def test_a_complete_build_is_stamped_full_with_no_reasons(self):
        rc = _FakeRedis()
        payload, _ = await _build_and_cache(
            [FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS], rc
        )
        assert _envelope(payload)["quality"] == cache_mod.QUALITY_FULL
        assert _envelope(payload)["quality_reasons"] == []

    async def test_the_private_loss_list_never_reaches_the_payload(self):
        """`_build_losses` is build-scoped bookkeeping. On the wire it would be a
        new public field nobody declared, and in Redis it would be frozen there
        for 24h."""
        rc = _FakeRedis()
        payload, _ = await _build_and_cache(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc
        )
        assert cache_mod.BUILD_LOSS_FIELD not in payload

    async def test_the_private_loss_list_is_popped_on_the_unusable_path_too(self):
        """The early return is the path most likely to leak it."""
        rc = _FakeRedis()
        payload, degraded = await _build_and_cache(
            [_timeout(), _timeout(), _timeout()], rc
        )
        assert degraded is True
        assert cache_mod.BUILD_LOSS_FIELD not in payload

    async def test_a_stored_partial_survives_envelope_validation(self):
        """A payload the module itself would refuse to read back is not cached,
        it is littered."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert cache_mod.read_slot(rc, keys.primary) is not None


# ---------------------------------------------------------------------------
# 4. A partial is CACHED — this is what ends the 12-second-every-time loop
# ---------------------------------------------------------------------------


class TestPartialIsCached:
    async def test_a_partial_with_rows_writes_the_primary(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.store.get(keys.primary) is not None

    async def test_the_primary_ttl_is_the_tier_s_own(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.ttls[keys.primary] == route.PROP_FAMILIES_PRIMARY_TTL

    async def test_the_second_reader_is_served_from_cache_and_builds_nothing(self):
        """The whole ship in one assertion: reader two runs ZERO branches."""
        rc = _FakeRedis()
        # LAT-P164: a cold build that is not `full` now dispatches the same
        # single-flight rebuild a mirror serve does. Patched to a no-op so this
        # test measures BRANCHES RUN, not broker reachability.
        with patch.object(route, "get_client", return_value=rc), \
             patch("app.tasks.celery_app.send_task", MagicMock()):
            db1 = _BranchDB([FK_ROWS, _timeout(), MARKET_NAME_ROWS])
            await route.get_team_prop_families("new-york-giants", 400, db1)
            db2 = _BranchDB([FK_ROWS, _timeout(), MARKET_NAME_ROWS])
            body = await route.get_team_prop_families("new-york-giants", 400, db2)
        assert db1.branch_index == _N_ROSTERED
        assert db2.branch_index == 0, "reader two paid for a rebuild"
        assert body["total_families"] >= 1

    async def test_a_partial_with_no_rows_is_served_but_not_stored(self):
        """An empty section is a response SHAPE, not an absence (gotcha #53) —
        freezing one behind a 24h mirror is the inversion this tier exists to
        prevent."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        payload, degraded = await _build_and_cache([[], _timeout(), []], rc)
        assert degraded is True
        assert rc.store.get(keys.primary) is None
        assert rc.store.get(keys.stale) is None
        assert _envelope(payload)["quality"] == cache_mod.QUALITY_PARTIAL

    async def test_a_complete_empty_build_is_still_stored(self):
        """"This team genuinely has no prop families" is an ANSWER and always
        was. Only the partial-and-empty case is withheld."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        _payload, degraded = await _build_and_cache([[], [], []], rc)
        assert degraded is False
        assert rc.store.get(keys.primary) is not None
        assert rc.store.get(keys.stale) is not None

    async def test_nothing_at_all_still_writes_nothing(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        _payload, degraded = await _build_and_cache(
            [_timeout(), _timeout(), _timeout()], rc
        )
        assert degraded is True
        assert rc.store.get(keys.primary) is None
        assert rc.store.get(keys.stale) is None


# ---------------------------------------------------------------------------
# 5. A partial must not cost a warmed team its complete answer
# ---------------------------------------------------------------------------


class TestPartialNeverDowngradesAFullMirror:
    def _full_mirror(self, rc, keys, label="complete"):
        stamped = cache_mod.stamp_envelope(
            {"team": {"id": 547}, "families": [{"family_key": label, "rows": []}],
             "total_families": 1},
            created_at=cache_mod._utcnow(),
            lifecycle_watermark=None,
            quality=cache_mod.QUALITY_FULL,
        )
        rc.setex(keys.stale, cache_mod.STALE_TTL, cache_mod.encode_payload(stamped))
        return stamped

    async def test_a_full_mirror_is_left_alone_by_a_partial_rebuild(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        self._full_mirror(rc, keys)
        before = rc.store[keys.stale]
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.store[keys.stale] == before, "the complete mirror was overwritten"

    async def test_but_the_partial_still_writes_the_primary(self):
        """Protecting the mirror must not re-create the loop: the primary write
        is what stops the NEXT reader rebuilding."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        self._full_mirror(rc, keys)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.store.get(keys.primary) is not None
        assert _envelope(_stored(rc, keys.primary))["quality"] == (
            cache_mod.QUALITY_PARTIAL
        )

    async def test_with_no_mirror_the_partial_writes_one(self):
        """The Giants case. There is nothing to protect, and refusing to write
        would leave the page uncacheable — the defect itself."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.store.get(keys.stale) is not None

    async def test_a_partial_mirror_is_replaced_by_a_fresher_partial(self):
        """Only `full` is protected. A stale partial must not become permanent."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        first = rc.store[keys.stale]
        await _build_and_cache([MARKET_NAME_ROWS, _timeout(), FK_ROWS], rc)
        assert rc.store[keys.stale] != first

    async def test_a_complete_rebuild_always_replaces_the_mirror(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        partial = rc.store[keys.stale]
        await _build_and_cache([FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS], rc)
        assert rc.store[keys.stale] != partial
        assert _envelope(_stored(rc, keys.stale))["quality"] == cache_mod.QUALITY_FULL

    def test_a_mirror_from_a_retired_generation_does_not_count_as_full(self):
        """`read_slot` reads it as a miss, so it must read as "nothing to
        protect" here too — otherwise a generation bump freezes every partial
        out of the mirror."""
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        stale = {
            "families": [], "total_families": 0,
            cache_mod.ENVELOPE_FIELD: {
                "generation": cache_mod.GENERATION - 1,
                "quality": cache_mod.QUALITY_FULL,
                "created_at": None, "availability": None,
                "lifecycle_watermark": None, "quality_reasons": [],
            },
        }
        rc.setex(keys.stale, 10, json.dumps(stale))
        assert route._mirror_is_full(rc, keys) is False

    def test_unreadable_bytes_do_not_count_as_full(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        rc.setex(keys.stale, 10, "not json")
        assert route._mirror_is_full(rc, keys) is False

    def test_no_mirror_does_not_count_as_full(self):
        rc = _FakeRedis()
        assert route._mirror_is_full(rc, route.prop_families_cache_keys(547, 400)) is False

    def test_a_dead_cache_does_not_count_as_full(self):
        assert route._mirror_is_full(None, route.prop_families_cache_keys(547, 400)) is False


# ---------------------------------------------------------------------------
# 6. `write_payload(mirror=False)` — the shared module's half
# ---------------------------------------------------------------------------


class TestWritePayloadMirrorFlag:
    def test_default_still_writes_both_slots(self):
        """Every existing customer passes no `mirror`, and none of them may
        change behaviour."""
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        cache_mod.write_payload(rc, keys, {"a": 1}, primary_ttl=60)
        assert rc.store.get(keys.primary) is not None
        assert rc.store.get(keys.stale) is not None

    def test_mirror_false_writes_only_the_primary(self):
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        cache_mod.write_payload(rc, keys, {"a": 1}, primary_ttl=60, mirror=False)
        assert rc.store.get(keys.primary) is not None
        assert rc.store.get(keys.stale) is None

    def test_mirror_false_leaves_an_existing_mirror_byte_identical(self):
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        rc.setex(keys.stale, 100, "KEEP-ME")
        cache_mod.write_payload(rc, keys, {"a": 1}, primary_ttl=60, mirror=False)
        assert rc.store[keys.stale] == b"KEEP-ME"

    def test_mirror_false_still_clears_the_negative(self):
        """A key that now resolves must not keep a 404 sentinel behind it,
        whichever slots were written."""
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        cache_mod.write_negative(rc, keys)
        assert cache_mod.has_negative(rc, keys) is True
        cache_mod.write_payload(rc, keys, {"a": 1}, primary_ttl=60, mirror=False)
        assert cache_mod.has_negative(rc, keys) is False

    def test_the_mirror_ttl_is_still_not_parameterised(self):
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        cache_mod.write_payload(rc, keys, {"a": 1}, primary_ttl=60)
        assert rc.ttls[keys.stale] == cache_mod.STALE_TTL


# ---------------------------------------------------------------------------
# 6b. CERT-480 finding 1 — the mirror decision must survive a CONCURRENT WRITER
#
# The guards in section 5 all drive ONE worker, so they can only ever observe
# sequential orderings: full-then-partial, partial-then-partial. The defect they
# cannot see is a partial and a full build interleaving on two web dynos with no
# lock between them. `_mirror_is_full()` answered truthfully at the instant it
# was asked, and the answer was acted on one round trip later:
#
#     partial worker   reads mirror -> absent/partial, decides "publish"
#     full  worker                     writes primary + FULL mirror
#     partial worker   writes ------------------------> partial over the full
#
# The mirror is then partial for 24 hours — the exact downgrade section 5 exists
# to prevent, arrived at by a legal ordering. `_RacingRedis` makes that window
# deterministic by committing the full build INSIDE the read the decision is
# taken on, which is the worst case and the only one worth pinning.
# ---------------------------------------------------------------------------


def _full_stamped(label="complete"):
    return cache_mod.stamp_envelope(
        {"team": {"id": 547}, "families": [{"family_key": label, "rows": []}],
         "total_families": 1},
        created_at=cache_mod._utcnow(),
        lifecycle_watermark=None,
        quality=cache_mod.QUALITY_FULL,
    )


class _RacingRedis(_FakeRedis):
    """A Redis that lets a COMPLETE build land between a reader's GET and its write.

    The interleaving is injected at the narrowest possible point — the mirror
    read itself — and exactly ONCE, so a fix cannot pass by simply re-reading in
    a loop. The value returned to the caller is the pre-race one, because that is
    what a real reader would have received.
    """

    def __init__(self, mirror_key, full_bytes):
        super().__init__()
        self._mirror_key = mirror_key
        self._full_bytes = full_bytes
        self.raced = False

    def get(self, k):
        seen = super().get(k)
        if k == self._mirror_key and not self.raced:
            self.raced = True
            super().setex(k, cache_mod.STALE_TTL, self._full_bytes)
        return seen


class TestAConcurrentFullBuildIsNotOverwritten:
    def _racer(self, keys):
        return _RacingRedis(keys.stale, cache_mod.encode_payload(_full_stamped()))

    async def test_a_full_landing_mid_decision_survives_when_the_mirror_was_absent(self):
        """The Giants arm. The partial reads "nothing here", which is the branch
        that decides to PUBLISH — so this is the ordering that actually loses
        data, and the one the sequential guards cannot reach."""
        keys = route.prop_families_cache_keys(547, 400)
        rc = self._racer(keys)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.raced is True, "the interleaving never happened — guard is vacuous"
        assert _envelope(_stored(rc, keys.stale))["quality"] == cache_mod.QUALITY_FULL, (
            "a partial overwrote a complete mirror that landed mid-decision"
        )

    async def test_a_full_landing_mid_decision_survives_over_a_stale_partial(self):
        """The other publishing arm: a partial mirror IS replaceable, so the
        decision is again "publish", and again it can be wrong by the time it is
        acted on."""
        keys = route.prop_families_cache_keys(547, 400)
        rc = self._racer(keys)
        rc.setex(keys.stale, cache_mod.STALE_TTL, cache_mod.encode_payload(
            cache_mod.stamp_envelope(
                {"team": {"id": 547}, "families": [{"family_key": "old", "rows": []}],
                 "total_families": 1},
                created_at=cache_mod._utcnow(),
                lifecycle_watermark=None,
                quality=cache_mod.QUALITY_PARTIAL,
            )
        ))
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.raced is True
        assert _envelope(_stored(rc, keys.stale))["quality"] == cache_mod.QUALITY_FULL

    async def test_losing_the_mirror_race_still_writes_the_primary(self):
        """Declining the mirror must not resurrect the twelve-second loop. The
        primary is uncontested and is what stops the NEXT reader rebuilding."""
        keys = route.prop_families_cache_keys(547, 400)
        rc = self._racer(keys)
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert rc.store.get(keys.primary) is not None
        assert _envelope(_stored(rc, keys.primary))["quality"] == (
            cache_mod.QUALITY_PARTIAL
        )

    async def test_losing_the_mirror_race_is_not_an_error(self):
        keys = route.prop_families_cache_keys(547, 400)
        rc = self._racer(keys)
        payload, degraded = await _build_and_cache(
            [FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc
        )
        assert degraded is False, "losing a benign race must not degrade the response"
        assert payload["total_families"] >= 1

    async def test_with_no_racer_the_partial_still_publishes(self):
        """The fix must not close the race by simply never writing — that would
        be the original defect wearing a lock."""
        keys = route.prop_families_cache_keys(547, 400)
        rc = _FakeRedis()
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert _envelope(_stored(rc, keys.stale))["quality"] == (
            cache_mod.QUALITY_PARTIAL
        )

    async def test_the_mirror_decision_costs_exactly_one_read(self):
        """Judging the mirror and proving it unchanged come from ONE observation.
        A second GET would be a second window, i.e. the same defect one level in."""
        keys = route.prop_families_cache_keys(547, 400)
        rc = _FakeRedis()
        reads = []
        inner = rc.get

        def counting_get(k):
            reads.append(k)
            return inner(k)

        rc.get = counting_get
        await _build_and_cache([FK_ROWS, _timeout(), MARKET_NAME_ROWS], rc)
        assert reads.count(keys.stale) == 1, f"mirror read {reads.count(keys.stale)}x"


# ---------------------------------------------------------------------------
# 6c. `setex_if_unchanged` / `publish_mirror_if_unchanged` — the primitive itself
# ---------------------------------------------------------------------------


class TestSetexIfUnchanged:
    def test_writes_when_the_key_is_still_absent(self):
        rc = _FakeRedis()
        assert cache_mod.setex_if_unchanged(rc, "k", None, 30, "v") is True
        assert rc.store["k"] == b"v"
        assert rc.ttls["k"] == 30

    def test_declines_when_something_appeared_under_an_absent_expectation(self):
        rc = _FakeRedis()
        rc.setex("k", 30, "landed-first")
        assert cache_mod.setex_if_unchanged(rc, "k", None, 30, "v") is False
        assert rc.store["k"] == b"landed-first"

    def test_writes_when_the_bytes_still_match(self):
        rc = _FakeRedis()
        rc.setex("k", 30, "before")
        assert cache_mod.setex_if_unchanged(rc, "k", b"before", 30, "after") is True
        assert rc.store["k"] == b"after"

    def test_declines_when_the_bytes_changed(self):
        rc = _FakeRedis()
        rc.setex("k", 30, "changed-under-us")
        assert cache_mod.setex_if_unchanged(rc, "k", b"before", 30, "after") is False
        assert rc.store["k"] == b"changed-under-us"

    def test_declines_when_the_key_vanished_under_a_byte_expectation(self):
        """An expired key is not "unchanged". Writing here would resurrect a
        value the TTL had already retired."""
        rc = _FakeRedis()
        assert cache_mod.setex_if_unchanged(rc, "k", b"before", 30, "after") is False
        assert "k" not in rc.store

    def test_a_dead_cache_declines_rather_than_raising(self):
        assert cache_mod.setex_if_unchanged(None, "k", None, 30, "v") is False

    def test_an_unrunnable_compare_and_set_fails_CLOSED(self):
        """If the CAS cannot run we do not fall back to an unguarded write —
        that is the check-then-act again, with the check deleted."""
        rc = _FakeRedis()
        rc.setex("k", 30, "keep")
        rc.eval = MagicMock(side_effect=RuntimeError("no scripting"))
        assert cache_mod.setex_if_unchanged(rc, "k", b"keep", 30, "v") is False
        assert rc.store["k"] == b"keep"


class TestTheLuaScriptItself:
    """⚠️ THE LIMIT OF THESE GUARDS, STATED OUT LOUD. The doubles above dispatch on
    script IDENTITY and re-implement Redis's semantics in Python, so they exercise
    the CONTRACT, never the Lua body — a Lua edit is invisible to them. These
    assertions are therefore about the script's STRUCTURE, which is the most that
    can be checked without a live Redis: they pin that neither precondition can be
    deleted while leaving a script that still writes. What they cannot prove is
    that the Lua is semantically correct; that is what the production read-back in
    the report is for.
    """

    def test_the_key_is_read_before_it_is_written(self):
        src = cache_mod._SETEX_IF_UNCHANGED_LUA
        assert src.index("redis.call('get'") < src.index("redis.call('setex'")

    def test_setex_is_unreachable_without_passing_both_guards(self):
        src = cache_mod._SETEX_IF_UNCHANGED_LUA
        setex_at = src.index("redis.call('setex'")
        declines = [m.start() for m in re.finditer(r"return 0", src)]
        assert len(declines) == 2, "both preconditions must be able to decline"
        assert all(at < setex_at for at in declines), (
            "a decline that follows the write does not prevent it"
        )

    def test_both_preconditions_are_present(self):
        src = cache_mod._SETEX_IF_UNCHANGED_LUA
        assert "ARGV[1] == '1'" in src, "the absent-key arm is gone"
        assert "current ~= ARGV[2]" in src, "the byte-comparison arm is gone"

    def test_the_script_writes_exactly_once(self):
        assert cache_mod._SETEX_IF_UNCHANGED_LUA.count("redis.call('setex'") == 1


class TestPublishMirrorIfUnchanged:
    def test_publishes_under_the_unparameterised_stale_ttl(self):
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        assert cache_mod.publish_mirror_if_unchanged(rc, keys, {"a": 1}, None) is True
        assert rc.ttls[keys.stale] == cache_mod.STALE_TTL

    def test_writes_the_same_bytes_write_payload_would_have(self):
        """The conditional path and the unconditional one must not encode
        differently, or a CAS on a later read compares against a stranger."""
        a, b = _FakeRedis(), _FakeRedis()
        keys = cache_mod.cache_keys("k")
        cache_mod.write_payload(a, keys, {"a": 1}, primary_ttl=60)
        cache_mod.publish_mirror_if_unchanged(b, keys, {"a": 1}, None)
        assert a.store[keys.stale] == b.store[keys.stale]

    def test_touches_only_the_mirror(self):
        rc = _FakeRedis()
        keys = cache_mod.cache_keys("k")
        cache_mod.publish_mirror_if_unchanged(rc, keys, {"a": 1}, None)
        assert rc.store.get(keys.primary) is None

    def test_a_dead_cache_declines(self):
        keys = cache_mod.cache_keys("k")
        assert cache_mod.publish_mirror_if_unchanged(None, keys, {"a": 1}, None) is False


class TestReadSlotRaw:
    def test_returns_both_the_bytes_and_the_payload(self):
        rc = _FakeRedis()
        stamped = _full_stamped()
        rc.setex("k", 30, cache_mod.encode_payload(stamped))
        raw, payload = cache_mod.read_slot_raw(rc, "k")
        assert raw == rc.store["k"]
        assert payload["total_families"] == 1

    def test_malformed_bytes_still_come_back_as_bytes(self):
        """The verdict is "unusable"; the BYTES are still what is sitting in the
        slot, and a conditional write has to be anchored to them."""
        rc = _FakeRedis()
        rc.setex("k", 30, "not json")
        raw, payload = cache_mod.read_slot_raw(rc, "k")
        assert raw == b"not json"
        assert payload is None

    def test_an_absent_key_is_no_bytes_and_no_payload(self):
        assert cache_mod.read_slot_raw(_FakeRedis(), "k") == (None, None)

    def test_a_failed_read_is_no_bytes_and_no_payload(self):
        rc = _FakeRedis()
        rc.get = MagicMock(side_effect=RuntimeError("down"))
        assert cache_mod.read_slot_raw(rc, "k") == (None, None)

    def test_read_slot_is_unchanged_by_the_split(self):
        rc = _FakeRedis()
        stamped = _full_stamped()
        rc.setex("k", 30, cache_mod.encode_payload(stamped))
        assert cache_mod.read_slot(rc, "k") == cache_mod.read_slot_raw(rc, "k")[1]

    def test_stored_mirror_agrees_with_the_predicate_it_replaced(self):
        rc = _FakeRedis()
        keys = route.prop_families_cache_keys(547, 400)
        rc.setex(keys.stale, 30, cache_mod.encode_payload(_full_stamped()))
        raw, is_full = route._stored_mirror(rc, keys)
        assert is_full is True
        assert raw == rc.store[keys.stale]
        assert route._mirror_is_full(rc, keys) is True


# ---------------------------------------------------------------------------
# 7. Containment stays NARROW — a real bug must not be filed as "ran out of time"
# ---------------------------------------------------------------------------


class TestIsStatementTimeout:
    def test_the_asyncpg_class_name(self):
        assert is_statement_timeout(QueryCanceledError("boom")) is True

    def test_the_message_form(self):
        assert is_statement_timeout(
            RuntimeError("canceling statement due to statement timeout")
        ) is True

    def test_a_wrapped_driver_cancellation_is_seen_through_the_wrapper(self):
        """SQLAlchemy re-raises as DBAPIError with the driver error as `__cause__`.
        A predicate that only looked at the outer exception would call every
        production cancellation a real error."""
        try:
            try:
                raise QueryCanceledError("cancelled")
            except Exception as inner:
                raise RuntimeError("(sqlalchemy wrapper)") from inner
        except RuntimeError as outer:
            assert is_statement_timeout(outer) is True

    def test_a_real_error_is_not_a_timeout(self):
        assert is_statement_timeout(ValueError("column does not exist")) is False

    def test_an_undefined_column_is_not_a_timeout(self):
        assert is_statement_timeout(
            RuntimeError('column "nope" does not exist')
        ) is False

    def test_a_cycle_in_the_cause_chain_terminates(self):
        a = RuntimeError("a")
        b = RuntimeError("b")
        a.__cause__ = b
        b.__cause__ = a
        assert is_statement_timeout(a) is False

    def test_an_exception_whose_str_raises_is_not_a_timeout(self):
        class _Nasty(Exception):
            def __str__(self):
                raise ValueError("no")

        assert is_statement_timeout(_Nasty()) is False

    def test_the_module_imports_nothing(self):
        """It is reached from route code on the request path, and a driver
        import there is a startup-order hazard for a two-line predicate."""
        import pathlib

        src = pathlib.Path(
            route.__file__
        ).resolve().parents[1] / "utils" / "statement_timeout.py"
        text = src.read_text()
        assert "\nimport " not in text and "\nfrom " not in text, text[:400]


class TestRealErrorsAreLoud:
    async def test_a_real_branch_error_is_still_contained_per_branch(self):
        """Contained, so one broken branch cannot blank the page — but it is
        recorded and it does not pretend to be a budget expiry."""
        (payload, unusable), db = await _build(
            [FK_ROWS, ValueError("column does not exist"), MARKET_NAME_ROWS]
        )
        assert unusable is False
        assert db.branch_index == _N_ROSTERED

    async def test_a_real_error_is_logged_at_exception_level(self, caplog):
        with caplog.at_level("ERROR"):
            await _build([FK_ROWS, ValueError("boom"), MARKET_NAME_ROWS])
        assert any(r.levelname == "ERROR" for r in caplog.records), caplog.records

    async def test_a_timeout_is_logged_at_warning_not_error(self, caplog):
        """A budget expiry is expected operation on this tier. Logging it as an
        ERROR would bury the real ones."""
        with caplog.at_level("WARNING"):
            await _build([FK_ROWS, _timeout(), MARKET_NAME_ROWS])
        assert not any(r.levelname == "ERROR" for r in caplog.records)
        assert any("timed out" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 8. Gotcha #6 — a rollback expires ORM objects, so read the scalars first
# ---------------------------------------------------------------------------


class TestOrmExpiryDiscipline:
    async def test_team_fields_are_read_before_the_first_branch_runs(self):
        """`team.id/name/slug` are used to assemble the payload AFTER the loop.
        If they are read then, a rollback three branches earlier has expired
        them and the read is a lazy load inside a route — the crash class.
        """
        reads: list[str] = []

        class _TrackingTeam:
            def __init__(self):
                self.roster_players = [{"name": "Malik Nabers"}]
                self._expired = False

            def __getattr__(self, item):
                if item in ("id", "name", "slug"):
                    reads.append(f"{item}@{len(reads)}")
                    if self._expired:
                        raise RuntimeError(f"lazy load of expired {item}")
                    return {"id": 547, "name": "New York Giants",
                            "slug": "new-york-giants"}[item]
                raise AttributeError(item)

        team = _TrackingTeam()

        class _ExpiringDB(_BranchDB):
            async def rollback(self):
                await super().rollback()
                team._expired = True

        db = _ExpiringDB([FK_ROWS, _timeout(), MARKET_NAME_ROWS], team=team)
        payload, unusable = await route.build_prop_families(team, db, 400)
        assert unusable is False
        assert payload["team"]["name"] == "New York Giants"

    async def test_the_payload_carries_plain_scalars_not_orm_objects(self):
        (payload, _unusable), _db = await _build(
            [FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS]
        )
        # JSON-serialisable end to end: anything ORM-shaped in here would be a
        # 500 at response time, not a test failure.
        json.dumps(payload)

    async def test_rows_from_an_earlier_branch_survive_a_later_rollback(self):
        """The materialise-inside-the-loop rule, asserted from the outside: the
        FK branch's content must be in the answer even though the session was
        rolled back after it."""
        (payload, _unusable), _db = await _build([FK_ROWS, _timeout(), []])
        assert payload["total_families"] >= 1


# ---------------------------------------------------------------------------
# 9. The serve ladder and the never-a-500 bar are unchanged
# ---------------------------------------------------------------------------


class TestRouteLadderUnchanged:
    async def test_a_live_hit_runs_no_branches(self):
        rc = _FakeRedis()
        with patch.object(route, "get_client", return_value=rc):
            db1 = _BranchDB([FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS])
            await route.get_team_prop_families("new-york-giants", 400, db1)
            db2 = _BranchDB([FK_ROWS, OUTCOME_NAME_ROWS, MARKET_NAME_ROWS])
            body = await route.get_team_prop_families("new-york-giants", 400, db2)
        assert db2.branch_index == 0
        assert _envelope(body)["availability"] == cache_mod.AVAILABILITY_LIVE

    async def test_a_dead_cache_leaves_the_route_working(self):
        """Redis down must be slow, never wrong and never a 500."""
        with patch.object(route, "get_client", return_value=None):
            db = _BranchDB([FK_ROWS, _timeout(), MARKET_NAME_ROWS])
            body = await route.get_team_prop_families("new-york-giants", 400, db)
        assert body["total_families"] >= 1

    async def test_an_unknown_team_is_still_a_404(self):
        from fastapi import HTTPException

        class _NoTeam(_BranchDB):
            async def execute(self, stmt, *args, **kwargs):
                self.statements.append(stmt)
                return _rows_result([])

        with pytest.raises(HTTPException) as exc:
            await route.get_team_prop_families("nope", 400, _NoTeam([]))
        assert exc.value.status_code == 404

    async def test_a_total_loss_still_serves_two_hundred_with_no_envelope(self):
        rc = _FakeRedis()
        with patch.object(route, "get_client", return_value=rc), \
             patch("app.tasks.celery_app.send_task", MagicMock()):
            db = _BranchDB(_all_timeout())
            body = await route.get_team_prop_families("new-york-giants", 400, db)
        assert body["total_families"] == 0
        assert cache_mod.ENVELOPE_FIELD not in body
