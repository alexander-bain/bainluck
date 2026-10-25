"""#2311: a roster branch runs as statements of at most ten patterns.

WHY. The warm task's latest verdict (2026-10-24 05:02Z) was selected 478,
truncated 278, deferred 195, partial 5, rebuilt 0, and its partial reasons were
`branch_timeout:outcome_roster` / `market_roster`: the single 40-pattern
`ILIKE ANY` trips the 12 s per-statement ceiling on large NFL rosters, so no
complete build lands and the Seahawks page served an empty Prop Races section.
Measured on production for #2311: 10 patterns 2.2 s, 41 patterns 13.4 s.

WHAT MUST NOT MOVE, and what each class below holds:

* the selection: the chunks' union, re-ordered and re-capped, is what the one
  statement returned (`TestSameSelectionAsOneStatement`, a differential run
  against the unchunked statement on the same table);
* the bounds: ONE 12 s deadline per branch however many chunks it has, the
  12 s per-statement ceiling, and the reader's total budget
  (`TestTheBranchDeadlineIsNotMultiplied`, `TestTheReaderBudgetIsNotMultiplied`);
* the honesty: a chunk that did not finish leaves the branch `branch_timeout:`
  (or `branch_deferred:` when the reader's budget skipped it), never full
  (`TestOneChunkFails`, `TestCompleteVersusPartial`);
* what already landed: a late chunk's matches, an early chunk's rows across a
  later rollback, and the sibling branches (`TestLateChunkMatches`,
  `TestRowsSurviveALaterChunksRollback`, `TestSiblingsSurviveAFailedBranch`).

The doubles execute the route's REAL statements against a small table: the
fake reads the compiled predicate, patterns and LIMIT and answers as Postgres
would (case-insensitive substring, probability DESC NULLS LAST, LIMIT), so the
aggregation under test is `build_prop_families`' own. The two screens after the
fetch are replaced with no-ops — they are steps after the merge with their own
suites (#8478, #11534, #9610) and run on whatever the merge produced.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod


TEAM_NAME = "Seattle Seahawks"


class QueryCanceledError(Exception):
    """asyncpg's class name: `is_statement_timeout` matches on it."""


def _timeout():
    return QueryCanceledError("canceling statement due to statement timeout")


class _Row(SimpleNamespace):
    """An ORM row that EXPIRES on rollback, as a real one does (gotcha #6).

    Reading any attribute of an expired row raises, so a route that kept ORM
    instances across a later chunk's rollback fails here the way it would
    fail in production — with a lazy-load error — instead of passing.
    """

    def __getattribute__(self, item):
        if item != "__dict__" and self.__dict__.get("_expired"):
            raise RuntimeError(f"expired ORM row read: {item}")
        return super().__getattribute__(item)


def _row(oid, oname, prob, mid, mname):
    outcome = _Row(id=oid, name=oname, current_probability=prob, is_winner=False)
    market = _Row(
        id=mid, name=mname, source="kalshi", group_id=None, status="open",
        resolution_date=None, market_metadata={},
    )
    return outcome, market


def _roster(n):
    return [f"Player{i:02d} Testman" for i in range(n)]


def _team(n_roster=40):
    return SimpleNamespace(
        id=77, name=TEAM_NAME, slug="seattle-seahawks", sport_id=None,
        roster_players=[{"name": nm} for nm in _roster(n_roster)],
    )


def _result(items):
    res = MagicMock()
    res.all.return_value = list(items)
    return res


class _TableDB:
    """An AsyncSession double that answers each branch statement from a table.

    `fail[(kind, i)]` raises on chunk `i` of branch `kind`; `costs[(kind, i)]`
    is the ms that chunk takes on the injected clock. A chunk whose cost reaches
    the `SET LOCAL` in force times out, charged exactly that timeout — the
    database cancelling it.
    """

    def __init__(self, rows, *, fail=None, costs=None, team_name=TEAM_NAME):
        self.rows = list(rows)
        self.fail = dict(fail or {})
        self.costs = dict(costs or {})
        self.team_pat = f"%{team_name}%"
        self.now = 0.0
        self.timeouts: list[int] = []
        self.calls: list[tuple[str, int, list[str], int]] = []
        self.rollbacks = 0
        self._returned: list[_Row] = []

    def monotonic(self):
        return self.now

    def _kind(self, sql, pats):
        if "futures_outcomes.team_id =" in sql:
            return route._BRANCH_TEAM_ID
        outcome_col = "futures_outcomes.name ILIKE ANY" in sql
        if pats == [self.team_pat]:
            return route._BRANCH_OUTCOME_NAME if outcome_col else route._BRANCH_MARKET_NAME
        return route._BRANCH_OUTCOME_ROSTER if outcome_col else route._BRANCH_MARKET_ROSTER

    async def execute(self, stmt, *args, **kwargs):
        rendered = str(stmt)
        if "statement_timeout" in rendered:
            self.timeouts.append(int("".join(c for c in rendered if c.isdigit())))
            return _result([])
        assert isinstance(stmt, Select) and "futures_outcomes" in rendered, rendered
        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        # The pattern array, not the `status IN (...)` list beside it.
        pats = next(
            (v for v in compiled.params.values()
             if isinstance(v, list) and v and all(str(x).startswith("%") for x in v)),
            [],
        )
        kind = self._kind(sql, pats)
        idx = sum(1 for c in self.calls if c[0] == kind)
        limit = stmt._limit_clause.value
        self.calls.append((kind, idx, list(pats), limit))

        cost = self.costs.get((kind, idx), 0)
        in_force = self.timeouts[-1]
        planned = self.fail.get((kind, idx))
        if planned is not None:
            self.now += min(cost, in_force) / 1000.0
            raise planned
        if cost >= in_force:
            self.now += in_force / 1000.0
            raise _timeout()
        self.now += cost / 1000.0

        # The table is read through `__dict__`: the database does not care
        # whether the SESSION has expired its copy of a row.
        if kind == route._BRANCH_TEAM_ID:
            hits = [r for r in self.rows if r[0].__dict__.get("team_id") == 77]
        else:
            needles = [p.strip("%").lower() for p in pats]
            col = 0 if kind in (route._BRANCH_OUTCOME_NAME, route._BRANCH_OUTCOME_ROSTER) else 1
            hits = [r for r in self.rows
                    if any(n in r[col].__dict__["name"].lower() for n in needles)]

        def _prob(r):
            return r[0].__dict__["current_probability"]

        hits = sorted(hits, key=lambda r: (_prob(r) is None, -(_prob(r) or 0)))[:limit]
        for o, m in hits:
            # A query that returns a row refreshes it, as the identity map does.
            o.__dict__["_expired"] = False
            m.__dict__["_expired"] = False
            self._returned.extend((o, m))
        return _result(hits)

    async def rollback(self):
        self.rollbacks += 1
        for row in self._returned:
            row.__dict__["_expired"] = True

    def patterns(self, kind):
        return [c[2] for c in self.calls if c[0] == kind]


async def _no_screen(*args, **kwargs):
    return None


async def _build(db, *, team=None, cap=400, budget_ms=None, chunk=None):
    """Run the real builder; return (payload, unusable, merged market dicts)."""
    team = team or _team()
    seen: list[list[dict]] = []
    real_group = route.group_prop_families

    def _spy(markets):
        seen.append([dict(m, outcomes=list(m["outcomes"])) for m in markets])
        return real_group(markets)

    patches = [
        patch.object(route, "time", SimpleNamespace(monotonic=db.monotonic)),
        patch.object(route, "_withhold_other_side", _no_screen),
        patch.object(route, "_withhold_refused_prices", _no_screen),
        patch.object(route, "group_prop_families", _spy),
    ]
    if chunk is not None:
        patches.append(patch.object(route, "_ROSTER_CHUNK_PATTERNS", chunk))
    for p in patches:
        p.start()
    try:
        payload, unusable = await route.build_prop_families(team, db, cap, budget_ms=budget_ms)
    finally:
        for p in reversed(patches):
            p.stop()
    return payload, unusable, (seen[0] if seen else [])


def _oids(markets):
    return [o["outcome_id"] for m in markets for o in m["outcomes"]]


def _reasons(payload):
    _quality, reasons = cache_mod.take_build_quality(payload)
    return set(reasons)


def _mvp_rows(players, *, base_oid, probs):
    """One award board whose legs are roster players — the outcome_roster shape."""
    return [_row(base_oid + i, p, probs[i], 500, "NFL MVP 2026") for i, p in enumerate(players)]


def _next_team_rows(players, *, base_oid, base_mid, probs):
    """One "<player> Next Team" board each — the market_roster shape."""
    return [
        _row(base_oid + i, "Kansas City", probs[i], base_mid + i, f"{p} Next Team")
        for i, p in enumerate(players)
    ]


def _fk_rows():
    rows = [
        _row(1, "Seattle Seahawks", 0.11, 100, "Super Bowl Champion 2027"),
        _row(2, "Kansas City Chiefs", 0.15, 100, "Super Bowl Champion 2027"),
    ]
    for o, _m in rows[:1]:
        o.__dict__["team_id"] = 77
    return rows


def _full_table(n=40):
    players = _roster(n)
    # Distinct probabilities, so no tie reaches the LIMIT boundary: Postgres
    # never ordered ties, and neither does this guard. One NULL leg rides in the
    # last chunk to hold NULLS LAST through the merge.
    probs = [round(0.01 + 0.0213 * ((i * 17) % n), 4) for i in range(n)]
    probs[n - 2] = None
    return (
        _fk_rows()
        + _mvp_rows(players, base_oid=1000, probs=probs)
        + _next_team_rows(players, base_oid=2000, base_mid=3000, probs=probs[::-1])
    )


# ---------------------------------------------------------------------------
# 1. The shape: at most ten patterns a statement, every searched name once
# ---------------------------------------------------------------------------


class TestChunkShape:
    def test_the_chunk_size_is_ten(self):
        assert route._ROSTER_CHUNK_PATTERNS == 10

    @pytest.mark.parametrize("n,sizes", [(40, [10, 10, 10, 10]), (25, [10, 10, 5]), (7, [7])])
    async def test_each_roster_branch_binds_every_searched_name_once(self, n, sizes):
        db = _TableDB(_full_table(40))
        payload, _unusable, _m = await _build(db, team=_team(n))
        expected = [f"%{nm}%" for nm in _roster(n)]
        for kind in (route._BRANCH_OUTCOME_ROSTER, route._BRANCH_MARKET_ROSTER):
            chunks = db.patterns(kind)
            assert [len(c) for c in chunks] == sizes, kind
            assert [p for c in chunks for p in c] == expected, kind
        assert payload["roster_search"]["searched"] == n

    async def test_the_other_branches_stay_one_statement(self):
        db = _TableDB(_full_table(40))
        await _build(db)
        for kind in (route._BRANCH_TEAM_ID, route._BRANCH_OUTCOME_NAME, route._BRANCH_MARKET_NAME):
            assert sum(1 for c in db.calls if c[0] == kind) == 1, kind

    async def test_every_chunk_carries_the_branch_limit(self):
        db = _TableDB(_full_table(40))
        await _build(db, cap=6)
        assert {c[3] for c in db.calls} == {6}

    async def test_the_roster_cap_and_its_declaration_are_unchanged(self):
        db = _TableDB(_full_table(40))
        payload, _u, _m = await _build(db, team=_team(65))
        assert route._MAX_ROSTER_PATTERNS == 40
        assert payload["roster_search"] == {"searched": 40, "total": 65, "truncated": True}
        assert sum(len(c) for c in db.patterns(route._BRANCH_OUTCOME_ROSTER)) == 40


# ---------------------------------------------------------------------------
# 2. The selection: what the one statement returned, differentially
# ---------------------------------------------------------------------------


class TestSameSelectionAsOneStatement:
    @pytest.mark.parametrize("cap", [3, 6, 15, 400])
    async def test_chunked_merge_equals_the_single_statement(self, cap):
        single_db = _TableDB(_full_table(40))
        single, _u1, single_markets = await _build(single_db, cap=cap, chunk=10_000)
        assert [len(c) for c in single_db.patterns(route._BRANCH_OUTCOME_ROSTER)] == [40]

        chunked_db = _TableDB(_full_table(40))
        chunked, _u2, chunked_markets = await _build(chunked_db, cap=cap)
        assert len(chunked_db.patterns(route._BRANCH_OUTCOME_ROSTER)) == 4

        assert chunked_markets == single_markets
        assert chunked == single
        assert _reasons(dict(chunked)) == set()

    async def test_a_small_cap_keeps_the_top_rows_across_chunks_not_the_first_chunk(self):
        # Without the re-cap the union is up to four caps long; without the
        # re-sort the first chunk's rows win. Either way this list differs.
        db = _TableDB(_full_table(40))
        _p, _u, markets = await _build(db, cap=3)
        mvp = next(m for m in markets if m["market_id"] == 500)
        probs = [o["probability"] for o in mvp["outcomes"]]
        all_probs = sorted(
            (o.current_probability for o, m in _full_table(40)
             if m.id == 500 and o.current_probability is not None),
            reverse=True,
        )
        assert probs == all_probs[:3]


# ---------------------------------------------------------------------------
# 3. Late chunks and duplicates
# ---------------------------------------------------------------------------


class TestLateChunkMatches:
    async def test_a_match_only_the_last_chunk_finds_is_served(self):
        late = _roster(40)[38]
        rows = _fk_rows() + _mvp_rows([late, _roster(40)[39]], base_oid=1000, probs=[0.3, 0.2])
        db = _TableDB(rows)
        _p, _u, markets = await _build(db)
        assert 1000 in _oids(markets)
        assert 1001 in _oids(markets)
        # It was the fourth statement that found it.
        assert late in " ".join(db.patterns(route._BRANCH_OUTCOME_ROSTER)[3])


class TestCrossChunkDuplicates:
    async def test_a_row_two_chunks_match_takes_one_place_under_the_cap(self):
        p = _roster(40)
        # Outcome 900's name matches a chunk-1 name AND a chunk-3 name.
        rows = _fk_rows() + [
            _row(900, f"{p[1]} / {p[21]}", 0.9, 500, "NFL MVP 2026"),
            _row(901, p[2], 0.8, 500, "NFL MVP 2026"),
            _row(902, p[22], 0.7, 500, "NFL MVP 2026"),
            _row(903, p[31], 0.6, 500, "NFL MVP 2026"),
        ]
        db = _TableDB(rows)
        _payload, _u, markets = await _build(db, cap=3)
        mvp = next(m for m in markets if m["market_id"] == 500)
        # The single statement's top 3: 900, 901, 902. Counting 900 twice
        # would push 902 out.
        assert [o["outcome_id"] for o in mvp["outcomes"]] == [900, 901, 902]

    async def test_no_outcome_or_family_is_duplicated_in_the_payload(self):
        p = _roster(40)
        rows = _fk_rows() + [
            _row(900, f"{p[1]} / {p[21]}", 0.9, 500, "NFL MVP 2026"),
            _row(901, p[2], 0.8, 500, "NFL MVP 2026"),
            _row(910, "Buffalo", 0.5, 3001, f"{p[1]} and {p[33]} Next Team"),
            _row(911, "Kansas City", 0.4, 3002, f"{p[5]} Next Team"),
        ]
        db = _TableDB(rows)
        payload, _u, markets = await _build(db)
        oids = _oids(markets)
        assert len(oids) == len(set(oids))
        keys = [f["family_key"] for f in payload["families"]]
        assert len(keys) == len(set(keys))
        for fam in payload["families"]:
            ids = [(r.get("market_id"), r.get("entity")) for r in fam["rows"]]
            assert len(ids) == len(set(ids)), fam["family_key"]


# ---------------------------------------------------------------------------
# 4. A chunk that fails, and the rows around it
# ---------------------------------------------------------------------------


class TestOneChunkFails:
    async def test_a_timed_out_chunk_leaves_the_branch_timed_out_and_the_others_served(self):
        p = _roster(40)
        rows = _fk_rows() + _mvp_rows([p[3], p[13], p[23], p[33]], base_oid=1000,
                                      probs=[0.4, 0.3, 0.2, 0.1])
        db = _TableDB(rows, fail={(route._BRANCH_OUTCOME_ROSTER, 1): _timeout()})
        payload, unusable, markets = await _build(db)
        assert unusable is False
        oids = set(_oids(markets))
        assert {1000, 1002, 1003} <= oids, "a chunk beside the failed one was lost"
        assert 1001 not in oids
        # Every chunk was asked: a failure does not end the branch's turn.
        assert len(db.patterns(route._BRANCH_OUTCOME_ROSTER)) == 4
        assert db.rollbacks == 1
        assert _reasons(payload) == {f"branch_timeout:{route._BRANCH_OUTCOME_ROSTER}"}

    async def test_a_real_error_in_a_chunk_is_contained_the_same_way(self):
        db = _TableDB(
            _full_table(40),
            fail={(route._BRANCH_MARKET_ROSTER, 2): ValueError("column does not exist")},
        )
        payload, unusable, _m = await _build(db)
        assert unusable is False
        assert _reasons(payload) == {f"branch_timeout:{route._BRANCH_MARKET_ROSTER}"}


class TestRowsSurviveALaterChunksRollback:
    async def test_an_earlier_chunks_rows_are_plain_data_before_the_rollback(self):
        p = _roster(40)
        rows = _fk_rows() + _mvp_rows([p[0], p[35]], base_oid=1000, probs=[0.5, 0.4])
        db = _TableDB(rows, fail={(route._BRANCH_OUTCOME_ROSTER, 2): _timeout()})
        # `_Row` raises on any read after a rollback: the build must not touch
        # chunk 0's instances again once chunk 2 has rolled back.
        payload, unusable, markets = await _build(db)
        assert unusable is False
        assert {1000, 1001} <= set(_oids(markets))
        assert db.rollbacks == 1


class TestSiblingsSurviveAFailedBranch:
    async def test_every_roster_chunk_failing_keeps_the_team_branches(self):
        rows = _full_table(40) + [_row(5, "Seattle Seahawks", 0.2, 600, "NFC West Winner")]
        fail = {(k, i): _timeout()
                for k in (route._BRANCH_OUTCOME_ROSTER, route._BRANCH_MARKET_ROSTER)
                for i in range(4)}
        db = _TableDB(rows, fail=fail)
        payload, unusable, markets = await _build(db)
        assert unusable is False
        oids = set(_oids(markets))
        assert {1, 5} <= oids
        assert not any(1000 <= o < 3000 for o in oids)
        assert _reasons(payload) == {
            f"branch_timeout:{route._BRANCH_OUTCOME_ROSTER}",
            f"branch_timeout:{route._BRANCH_MARKET_ROSTER}",
        }


# ---------------------------------------------------------------------------
# 5. The bounds: one deadline per branch, one budget per reader
# ---------------------------------------------------------------------------


def _roster_costs(kind, ms, n=4):
    return {(kind, i): ms for i in range(n)}


class TestTheBranchDeadlineIsNotMultiplied:
    async def test_chunks_share_the_branchs_twelve_seconds_and_the_rest_is_a_timeout(self):
        db = _TableDB(_full_table(40),
                      costs=_roster_costs(route._BRANCH_OUTCOME_ROSTER, 3950))
        payload, _u, _m = await _build(db)
        # FK, two team-name branches, then the roster chunks: 12,000 shared.
        assert db.timeouts[3:6] == [12000, 8050, 4100]
        # The fourth chunk had 150 ms left, under the floor: never started, and
        # no rollback for a statement nobody ran.
        assert len(db.patterns(route._BRANCH_OUTCOME_ROSTER)) == 3
        assert db.rollbacks == 0
        assert _reasons(payload) == {f"branch_timeout:{route._BRANCH_OUTCOME_ROSTER}"}
        # The next branch has its own twelve seconds, as it always did.
        assert db.timeouts[6] == 12000

    async def test_a_chunk_cancelled_at_the_deadline_ends_the_branch_at_twelve_seconds(self):
        db = _TableDB(_full_table(40),
                      costs=_roster_costs(route._BRANCH_OUTCOME_ROSTER, 5000))
        payload, _u, _m = await _build(db)
        assert db.timeouts[3:6] == [12000, 7000, 2000]
        assert db.now * 1000 == pytest.approx(12000)
        assert _reasons(payload) == {f"branch_timeout:{route._BRANCH_OUTCOME_ROSTER}"}

    async def test_no_statement_is_ever_given_more_than_the_ceiling(self):
        db = _TableDB(_full_table(40))
        await _build(db)
        assert max(db.timeouts) == route._BRANCH_TIMEOUT_MS == 12000

    async def test_a_hung_build_stays_inside_the_warm_tasks_per_team_wait(self):
        from app.tasks.prop_families_warm import PER_TEAM_TIMEOUT_SECONDS

        hang = 10 ** 9
        costs = {}
        for kind in (route._BRANCH_TEAM_ID, route._BRANCH_OUTCOME_NAME,
                     route._BRANCH_MARKET_NAME):
            costs[(kind, 0)] = hang
        for kind in (route._BRANCH_OUTCOME_ROSTER, route._BRANCH_MARKET_ROSTER):
            costs.update(_roster_costs(kind, hang))
        db = _TableDB(_full_table(40), costs=costs)
        _payload, unusable, _m = await _build(db)
        assert unusable is True
        # Five branches, one 12 s deadline each — the bound before chunking.
        # Four chunks at 12 s each would be 132 s and the warm task's wait
        # would cancel the whole build first.
        assert db.now * 1000 == pytest.approx(5 * 12000)
        assert db.now <= PER_TEAM_TIMEOUT_SECONDS


class TestTheReaderBudgetIsNotMultiplied:
    async def test_the_reader_spends_one_budget_across_chunks_and_defers_the_rest(self):
        p = _roster(40)
        rows = _fk_rows() + _mvp_rows([p[0], p[11], p[25], p[35]], base_oid=1000,
                                      probs=[0.4, 0.3, 0.2, 0.1])
        costs = {(route._BRANCH_TEAM_ID, 0): 10,
                 (route._BRANCH_OUTCOME_NAME, 0): 100,
                 (route._BRANCH_MARKET_NAME, 0): 100}
        costs.update(_roster_costs(route._BRANCH_OUTCOME_ROSTER, 450))
        db = _TableDB(rows, costs=costs)
        payload, unusable, markets = await _build(db, budget_ms=2500)
        assert unusable is False
        fetch_budget = 2500 - route._PRICE_SCREEN_RESERVE_MS
        assert db.now * 1000 <= fetch_budget
        # 1,750 - 210 = 1,540 for the roster, spent chunk by chunk.
        assert db.timeouts[3:] == [1540, 1090, 640]
        assert {1000, 1001, 1002} <= set(_oids(markets))
        assert 1003 not in set(_oids(markets))
        reasons = _reasons(payload)
        # Nothing expired: the reader chose not to ask. That is an IOU the
        # unbudgeted rebuild pays — not a timeout, and not full.
        assert reasons == {
            f"branch_deferred:{route._BRANCH_OUTCOME_ROSTER}",
            f"branch_deferred:{route._BRANCH_MARKET_ROSTER}",
        }
        assert set(route._deferral_reasons(sorted(reasons))) == reasons

    async def test_a_chunk_cancelled_by_the_budget_is_a_timeout_as_before(self):
        costs = {(route._BRANCH_OUTCOME_ROSTER, 0): 5000}
        db = _TableDB(_full_table(40), costs=costs)
        payload, _u, _m = await _build(db, budget_ms=2500)
        assert db.now * 1000 <= 2500 - route._PRICE_SCREEN_RESERVE_MS
        assert _reasons(payload) == {
            f"branch_timeout:{route._BRANCH_OUTCOME_ROSTER}",
            f"branch_deferred:{route._BRANCH_MARKET_ROSTER}",
        }


# ---------------------------------------------------------------------------
# 6. Complete versus partial
# ---------------------------------------------------------------------------


class TestCompleteVersusPartial:
    async def test_every_chunk_landing_is_a_full_build(self):
        db = _TableDB(_full_table(40))
        payload, unusable, _m = await _build(db)
        assert unusable is False
        assert cache_mod.take_build_quality(payload) == (cache_mod.QUALITY_FULL, [])

    @pytest.mark.parametrize("kind", [route._BRANCH_OUTCOME_ROSTER, route._BRANCH_MARKET_ROSTER])
    @pytest.mark.parametrize("i", [0, 3])
    async def test_one_missing_chunk_is_never_full(self, kind, i):
        db = _TableDB(_full_table(40), fail={(kind, i): _timeout()})
        payload, _u, _m = await _build(db)
        quality, reasons = cache_mod.take_build_quality(payload)
        assert quality == cache_mod.QUALITY_PARTIAL
        assert reasons == [f"branch_timeout:{kind}"]
