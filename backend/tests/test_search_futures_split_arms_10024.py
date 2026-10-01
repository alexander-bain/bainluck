"""#10024 — the split arms (`dodgers world series`) are read by the futures
window only when the other tier<=1 arms come back short, and that is
page-identical to reading every arm in one statement.

The real `_fetch_futures_window` is driven against a model of the ORDER BY, as
`test_search_futures_tier_split.py` does for the outcome arm (read that
suite's docstring for why a model and not a seeded database). Split rows are
tier 1.5 in the model because the route ranks them 1.5 — below the tier-1
inferences, above outcome-only rows. When they were tier 1, the first property
run here failed 5 of 40 corpora: a full window of tier-1 alias rows skipped a
split row that outranked them. The last test pins the route's wiring, which the
route-level gate cannot see (a merged page is appended in order either way).

`tests/integration/test_search_team_plus_competition_pg_10024.py` is the
real-Postgres half: the arms' SQL, the one-option rule and the route wiring.
"""

from __future__ import annotations

import inspect
import random

import pytest

from app.routes import events as ev
from app.routes.events import (
    _SEARCH_FUTURES_WINDOW,
    _fetch_futures_window,
    _split_futures_arms,
)

WINDOW = _SEARCH_FUTURES_WINDOW
TIER1_ARMS = ["name", "alias"]
SPLIT = "split"
OUTCOME = "outcome"


class Row:
    def __init__(self, id: int, arms: set[str], sort: int) -> None:
        self.id = id
        self.arms = arms
        self.sort = sort

    @property
    def tier(self) -> int:
        if "name" in self.arms:
            return 0
        if "alias" in self.arms:
            return 1
        if SPLIT in self.arms:
            return 1.5
        return 2


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
    def __init__(self, db):
        self._db = db

    async def commit(self):
        self._db.savepoints.append("release")

    async def rollback(self):
        self._db.savepoints.append("rollback")


class QueryCanceledError(Exception):
    """Named like asyncpg's, which `_is_query_timeout` recognises by name."""


class FakeDB:
    def __init__(self, corpus, *, cancel_split=False):
        self.corpus = corpus
        self.executed: list[frozenset] = []
        self.savepoints: list[str] = []
        self.cancel_split = cancel_split

    async def execute(self, marker):
        _tag, arms = marker
        self.executed.append(arms)
        if self.cancel_split and SPLIT in arms:
            raise QueryCanceledError("canceling statement due to statement timeout")
        rows = sorted(
            (r for r in self.corpus if r.arms & arms), key=lambda r: (r.tier, r.sort)
        )
        return _Result(rows[:WINDOW])

    async def begin_nested(self):
        self.savepoints.append("begin")
        return _Savepoint(self)


def _candidates_in(arms):
    return frozenset(arms)


def _window_query(candidate_filter):
    return ("Q", candidate_filter)


@pytest.fixture(autouse=True)
def _timeouts(monkeypatch):
    calls = []

    async def _fake(db, deadline=None, bound_ms=None):
        calls.append(bound_ms)

    monkeypatch.setattr(ev, "_apply_search_statement_timeout", _fake)
    return calls


async def _run(corpus, *, split=(SPLIT,), outcome=OUTCOME, cancel_split=False):
    db = FakeDB(corpus, cancel_split=cancel_split)
    report: dict = {}
    rows, state = await _fetch_futures_window(
        db, _window_query, _candidates_in, list(TIER1_ARMS), outcome, None,
        split_arms=list(split), split_report=report,
    )
    return db, rows, state, report.get("state")


def _one_statement(corpus):
    arms = frozenset([*TIER1_ARMS, SPLIT, OUTCOME])
    rows = sorted((r for r in corpus if r.arms & arms), key=lambda r: (r.tier, r.sort))
    return [r.id for r in rows[:WINDOW]]


def _corpus(rng, n):
    rows = []
    for i in range(n):
        arms = {a for a in (*TIER1_ARMS, SPLIT, OUTCOME) if rng.random() < 0.3}
        rows.append(Row(i, arms or {rng.choice([*TIER1_ARMS, SPLIT, OUTCOME])}, 0))
    for pos, r in enumerate(rng.sample(rows, len(rows))):
        r.sort = pos
    return rows


@pytest.mark.parametrize("seed", range(40))
async def test_the_staged_page_is_the_one_statement_page(seed):
    rng = random.Random(seed)
    corpus = _corpus(rng, rng.choice([0, 1, 5, 19, 20, 21, 40, 200]))
    _db, rows, _state, _split = await _run(corpus)
    assert [r.id for r in rows] == _one_statement(corpus)


@pytest.mark.parametrize("n_tier1", [0, 1, 19, 20, 21])
async def test_identical_at_every_window_boundary(n_tier1):
    corpus = [Row(i, {"name"}, i) for i in range(n_tier1)]
    corpus += [Row(100 + i, {SPLIT}, 100 + i) for i in range(5)]
    corpus += [Row(200 + i, {OUTCOME}, 200 + i) for i in range(30)]
    _db, rows, _state, _split = await _run(corpus)
    assert [r.id for r in rows] == _one_statement(corpus)


async def test_a_full_tier1_window_never_reads_the_split_arms():
    """The saving, asserted as an absence: `red sox` pays nothing for them."""
    corpus = [Row(i, {"name"}, i) for i in range(WINDOW + 3)]
    corpus += [Row(100, {SPLIT}, 100)]
    db, _rows, state, split = await _run(corpus)
    assert split == "skipped"
    assert state == "skipped"
    assert db.executed == [frozenset(TIER1_ARMS)]


async def test_a_window_of_tier1_inferences_still_outranks_a_split_row():
    """The counterexample the first property run found, kept explicit: a full
    window of alias rows, and a split row with a better rank than all of them."""
    corpus = [Row(i, {"alias"}, 10 + i) for i in range(WINDOW)]
    corpus += [Row(100, {SPLIT}, 0)]
    db, rows, _state, split = await _run(corpus)
    assert split == "skipped"
    assert [r.id for r in rows] == _one_statement(corpus) == list(range(WINDOW))


async def test_an_empty_tier1_read_reaches_the_split_rows():
    """`dodgers world series`: nothing in tier<=1, the board is a split row."""
    corpus = [Row(100, {SPLIT}, 5), Row(200, {OUTCOME}, 1)]
    db, rows, _state, split = await _run(corpus)
    assert split == "merged"
    assert [r.id for r in rows] == [100, 200]
    assert frozenset([*TIER1_ARMS, SPLIT]) in db.executed
    assert db.savepoints == ["begin", "release", "begin", "release"]


async def test_split_rows_that_fill_the_window_skip_the_outcome_arm():
    corpus = [Row(i, {SPLIT}, i) for i in range(WINDOW)]
    corpus += [Row(100 + i, {OUTCOME}, i) for i in range(5)]
    db, rows, state, split = await _run(corpus)
    assert (split, state) == ("merged", "skipped")
    assert all(OUTCOME not in arms for arms in db.executed)
    assert [r.id for r in rows] == _one_statement(corpus)


async def test_over_its_bound_the_page_is_the_rows_already_in_hand(_timeouts):
    corpus = [Row(1, {"name"}, 1), Row(100, {SPLIT}, 0), Row(200, {OUTCOME}, 2)]
    db, rows, state, split = await _run(corpus, cancel_split=True)
    assert split == "budget_exceeded"
    assert db.savepoints[:2] == ["begin", "rollback"]
    assert [r.id for r in rows] == [1, 200]
    assert state == "merged"


async def test_no_time_left_sheds_the_split_arms(monkeypatch):
    monkeypatch.setattr(ev, "_search_outcome_arm_bound_ms", lambda deadline: None)
    corpus = [Row(100, {SPLIT}, 0)]
    db, rows, _state, split = await _run(corpus)
    assert split == "shed"
    assert all(SPLIT not in arms for arms in db.executed)
    assert rows == []


async def test_the_split_read_is_bounded_and_the_deadline_rearmed(_timeouts, monkeypatch):
    monkeypatch.setattr(ev, "_search_outcome_arm_bound_ms", lambda deadline: 777)
    await _run([Row(100, {SPLIT}, 0)], outcome=None)
    assert _timeouts == [777, None]


async def test_no_split_arms_is_one_statement_and_absent():
    db, _rows, state, split = await _run([Row(1, {"name"}, 0)], split=(), outcome=None)
    assert (split, state) == ("absent", "absent")
    assert len(db.executed) == 1


# --- the arm builder --------------------------------------------------------


def _expanded(q):
    return ev._apply_search_synonyms(ev.expand_search_terms(q.split()))


@pytest.mark.parametrize(
    "q, arms",
    [
        ("dodgers", 0),                    # one term: the primary arms cover it
        ("dodgers world series", 4),       # 2 cuts x 2 orientations
        ("chiefs super bowl", 4),
        ("red sox world series", 6),       # 3 cuts x 2
        ("los angeles dodgers world series", 0),  # 5 terms: past the cap
        ("us open", 0),                    # `us` cannot use a trigram index
        ("f1 world championship", 0),
    ],
)
def test_the_arms_built_per_query(q, arms):
    assert len(_split_futures_arms(_expanded(q))) == arms


def test_split_rows_are_ranked_between_the_inferences_and_outcome_rows():
    """The route's CASE must score a split row as the window's model does, or
    an outcome-only row could outrank one the skip proof assumed it could not."""
    src = inspect.getsource(ev.search_events)
    assert "_futures_tier_whens.append((or_(*_futures_split_arms), 1.5))" in src
    assert "split_arms=_futures_split_arms," in src
