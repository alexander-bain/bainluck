"""#8704 — the futures collapse refill reads rows the window already fetched.

`united` on production 2026-09-25: `futures_outcome_arm: skipped`, `futures`
6,650 ms, `futures_refill` 11,794 ms, `total_ms` 18,720. The window proved the
outcome arm could not reach its page and skipped it; the refill then re-ran the
FULL arm set at OFFSET 20 — a second ranking of every candidate, outcome arm
included.

The fix widens the tier<=1 statement to rank 60 so the refill's rows come back
from the same execution, and uses them only where that is provably the page the
old query returned. So the property here is the same as LAT-P111's suite — not
"is it faster" but **"is the refill byte-identical to the old refill query"** —
asserted over randomised corpora, plus the window itself staying identical.
"""

from __future__ import annotations

import inspect
import random

import pytest

from app.routes import events as events_module
from app.routes.events import _SEARCH_FUTURES_REFILL, _SEARCH_FUTURES_WINDOW


# Read off the module at call time, not imported by value (CodeQL
# py/import-of-mutable-attribute): a monkeypatch of either is then seen here.
def _fetch_futures_window(*args, **kwargs):
    return events_module._fetch_futures_window(*args, **kwargs)


def _futures_refill_in_hand(*args, **kwargs):
    return events_module._futures_refill_in_hand(*args, **kwargs)


WINDOW = _SEARCH_FUTURES_WINDOW
REFILL = _SEARCH_FUTURES_REFILL
TIER1_ARMS = ["name", "ticker", "alias"]
OUTCOME_ARM = "outcome"


class Row:
    def __init__(self, id: int, arms: set[str], sort: int) -> None:
        self.id = id
        self.arms = arms
        self.sort = sort

    @property
    def tier(self) -> int:
        if "name" in self.arms:
            return 0
        if "ticker" in self.arms or "alias" in self.arms:
            return 1
        return 2

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Row(id={self.id}, tier={self.tier}, sort={self.sort})"


class Stmt:
    """A window statement: a candidate filter plus LIMIT/OFFSET, like `Select`."""

    def __init__(self, arms: frozenset, limit: int = WINDOW, offset: int = 0) -> None:
        self.arms = arms
        self._limit = limit
        self._offset = offset

    def limit(self, n: int) -> "Stmt":
        return Stmt(self.arms, n, self._offset)

    def offset(self, n: int) -> "Stmt":
        return Stmt(self.arms, self._limit, n)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Savepoint:
    async def commit(self):
        pass

    async def rollback(self):  # pragma: no cover - nothing here cancels
        pass


class FakeDB:
    """Answers a statement under the ONE shared ORDER BY: tier, then a total sort."""

    def __init__(self, corpus: list[Row]) -> None:
        self.corpus = corpus
        self.executed: list[Stmt] = []

    async def execute(self, stmt: Stmt):
        self.executed.append(stmt)
        rows = [r for r in self.corpus if r.arms & stmt.arms]
        rows.sort(key=lambda r: (r.tier, r.sort))
        return _Result(rows[stmt._offset: stmt._offset + stmt._limit])

    async def begin_nested(self):
        return _Savepoint()


def _candidates_in(arms):
    return frozenset(arms)


def _window_query(candidate_filter):
    return Stmt(candidate_filter)


@pytest.fixture(autouse=True)
def _no_statement_timeout(monkeypatch):
    async def _fake(db, deadline=None, bound_ms=None):
        return None

    monkeypatch.setattr("app.routes.events._apply_search_statement_timeout", _fake)


def _full_arms(outcome_arm):
    return frozenset(TIER1_ARMS + ([outcome_arm] if outcome_arm else []))


async def _old(corpus, outcome_arm):
    """The route before #8704: window at LIMIT 20, refill = full arms at OFFSET 20."""
    db = FakeDB(corpus)
    window, state = await _fetch_futures_window(
        db, _window_query, _candidates_in, list(TIER1_ARMS), outcome_arm, None
    )
    refill = (
        await db.execute(Stmt(_full_arms(outcome_arm)).offset(WINDOW).limit(REFILL))
    ).scalars().unique().all()
    return window, state, refill


async def _new(corpus, outcome_arm):
    """The route after #8704: widened tier<=1 statement, refill in hand or queried."""
    db = FakeDB(corpus)
    rows, state = await _fetch_futures_window(
        db, _window_query, _candidates_in, list(TIER1_ARMS), outcome_arm, None,
        tier1_limit=WINDOW + REFILL,
    )
    window, spare = rows[:WINDOW], rows[WINDOW:]
    before = len(db.executed)
    refill = _futures_refill_in_hand(state, spare)
    source = "window"
    if refill is None:
        source = "query"
        refill = (
            await db.execute(
                Stmt(_full_arms(outcome_arm)).offset(WINDOW).limit(REFILL)
            )
        ).scalars().unique().all()
    return window, state, refill, source, len(db.executed) - before


def _corpus(rng: random.Random, n: int, p_tier1: float = 0.35) -> list[Row]:
    rows = []
    for i in range(n):
        arms = {a for a in TIER1_ARMS if rng.random() < p_tier1}
        if rng.random() < 0.35:
            arms.add(OUTCOME_ARM)
        if not arms:
            arms = {rng.choice([*TIER1_ARMS, OUTCOME_ARM])}
        rows.append(Row(i, arms, rng.randrange(10_000_000)))
    for pos, r in enumerate(sorted(rows, key=lambda r: r.sort)):
        r.sort = pos
    return rows


def _ids(rows):
    return [r.id for r in rows]


# ---------------------------------------------------------------------------
# THE LOAD-BEARING PROPERTY: same window, same refill, same order
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome_arm", [OUTCOME_ARM, None])
@pytest.mark.parametrize("seed", range(40))
async def test_the_window_and_the_refill_are_identical_to_the_old_route(seed, outcome_arm):
    rng = random.Random(seed)
    corpus = _corpus(rng, rng.randrange(0, 260), p_tier1=rng.choice([0.05, 0.2, 0.5]))
    old_window, old_state, old_refill = await _old(corpus, outcome_arm)
    new_window, new_state, new_refill, _, _ = await _new(corpus, outcome_arm)
    assert new_state == old_state
    assert _ids(new_window) == _ids(old_window)
    assert _ids(new_refill) == _ids(old_refill)


@pytest.mark.parametrize("n_tier1", [0, 1, 19, 20, 21, 39, 59, 60, 61, 120])
@pytest.mark.parametrize("n_outcome_only", [0, 5, 80])
async def test_identical_at_every_page_boundary(n_tier1, n_outcome_only):
    """The two edges that matter: tier<=1 ending just short of / exactly at 60."""
    rng = random.Random(n_tier1 * 1000 + n_outcome_only)
    corpus = [Row(i, {"name"}, 0) for i in range(n_tier1)]
    corpus += [Row(n_tier1 + i, {OUTCOME_ARM}, 0) for i in range(n_outcome_only)]
    rng.shuffle(corpus)
    for pos, r in enumerate(corpus):
        r.sort = pos
    old_window, _, old_refill = await _old(corpus, OUTCOME_ARM)
    new_window, _, new_refill, source, _ = await _new(corpus, OUTCOME_ARM)
    assert _ids(new_window) == _ids(old_window)
    assert _ids(new_refill) == _ids(old_refill)
    if n_tier1 >= WINDOW + REFILL:
        assert source == "window"


# ---------------------------------------------------------------------------
# THE POINT: the specimen's shape issues NO refill statement
# ---------------------------------------------------------------------------


async def test_the_united_shape_refills_without_a_second_ranking():
    """Hundreds of name matches ⇒ window `skipped`, refill read from the window."""
    corpus = [Row(i, {"name"} | ({OUTCOME_ARM} if i % 3 else set()), i) for i in range(400)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(300)]
    window, state, refill, source, refill_statements = await _new(corpus, OUTCOME_ARM)
    assert state == "skipped"
    assert source == "window"
    assert refill_statements == 0
    assert _ids(window) == list(range(WINDOW))
    assert _ids(refill) == list(range(WINDOW, WINDOW + REFILL))


async def test_a_short_tier1_tail_still_queries_so_outcome_rows_keep_their_place():
    """tier<=1 = 30 rows: ranks 31-60 belong to outcome-only rows — query, as before."""
    corpus = [Row(i, {"name"}, i) for i in range(30)]
    corpus += [Row(100 + i, {OUTCOME_ARM}, 100 + i) for i in range(50)]
    _, state, refill, source, refill_statements = await _new(corpus, OUTCOME_ARM)
    assert state == "skipped"
    assert source == "query"
    assert refill_statements == 1
    assert _ids(refill) == list(range(20, 30)) + list(range(100, 130))


async def test_the_widened_limit_never_widens_the_window_itself():
    corpus = [Row(i, {"name"}, i) for i in range(200)]
    rows, state = await _fetch_futures_window(
        FakeDB(corpus), _window_query, _candidates_in, list(TIER1_ARMS),
        OUTCOME_ARM, None, tier1_limit=WINDOW + REFILL,
    )
    assert state == "skipped"
    assert len(rows) == WINDOW + REFILL  # the caller slices; the helper returns all


async def test_the_outcome_arm_statement_is_never_widened():
    corpus = [Row(i, {"name"}, i) for i in range(5)]
    corpus += [Row(100 + i, {OUTCOME_ARM}, 100 + i) for i in range(200)]
    db = FakeDB(corpus)
    rows, state = await _fetch_futures_window(
        db, _window_query, _candidates_in, list(TIER1_ARMS), OUTCOME_ARM, None,
        tier1_limit=WINDOW + REFILL,
    )
    assert state == "merged"
    assert len(rows) == WINDOW
    outcome_stmts = [s for s in db.executed if s.arms == frozenset({OUTCOME_ARM})]
    assert [s._limit for s in outcome_stmts] == [WINDOW]


# ---------------------------------------------------------------------------
# `_futures_refill_in_hand`, state by state
# ---------------------------------------------------------------------------


def test_absent_uses_whatever_spare_rows_exist():
    assert _futures_refill_in_hand("absent", [1, 2, 3]) == [1, 2, 3]
    assert _futures_refill_in_hand("absent", []) == []


def test_skipped_uses_the_spare_rows_only_when_they_fill_the_refill():
    full = list(range(REFILL))
    assert _futures_refill_in_hand("skipped", full) == full
    assert _futures_refill_in_hand("skipped", full[:-1]) is None
    assert _futures_refill_in_hand("skipped", []) is None


@pytest.mark.parametrize(
    "state", ["merged", "shed", "budget_exceeded", "not_reached"]
)
def test_every_other_state_queries(state):
    assert _futures_refill_in_hand(state, list(range(REFILL))) is None


# ---------------------------------------------------------------------------
# WIRING: the route really passes the wider limit and consults the helper first
# ---------------------------------------------------------------------------


def _route_source() -> str:
    return inspect.getsource(events_module.search_events)


def test_the_route_widens_the_tier1_statement_to_the_refill_depth():
    src = _route_source()
    assert "tier1_limit=_SEARCH_FUTURES_WINDOW + _SEARCH_FUTURES_REFILL" in src
    assert "_futures_spare_rows = futures_markets_raw[_SEARCH_FUTURES_WINDOW:]" in src
    assert "futures_markets_raw = futures_markets_raw[:_SEARCH_FUTURES_WINDOW]" in src


def test_the_refill_consults_the_rows_in_hand_before_it_queries():
    src = _route_source()
    consult = src.index("refill_rows = _futures_refill_in_hand(")
    gate = src.index("if refill_rows is None:", consult)
    query = src.index("futures_query.offset(_SEARCH_FUTURES_WINDOW)", gate)
    assert consult < gate < query


def test_debug_timing_says_where_the_refill_came_from():
    src = _route_source()
    assert '"futures_refill_source": _futures_refill_source' in src
    assert '_futures_refill_source = "not_fired"' in src
