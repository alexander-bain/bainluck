"""LAT-P111 / #2261 — the futures window is fetched TIER-ORDERED, and that is
answer-identical to fetching it all at once.

WHY THIS SUITE EXISTS, AND WHY IT IS A PROPERTY TEST AND NOT THREE EXAMPLES.

`/api/events/search`'s dominant cost is the outcome arm — `markets whose
OUTCOME name matches`. Measured in production 2026-08-28 with
`EXPLAIN (ANALYZE, BUFFERS)` on the statement the ORM actually emits, `oscars`:

    Bitmap Heap Scan futures_outcomes   2,334 rows   1,572 blocks   583 ms
      -> Index Scan futures_markets_pkey   x931      3,735 blocks   220 ms
    = 67 candidate markets, 805 ms of an 839 ms query

...against a name arm that returned **84** rows in 23 ms in the same plan. The
name matches are tier 0, the outcome-only rows are tier 2, and tier is the first
ORDER BY key — so those 67 rows could not have reached a 20-row page under any
circumstances. The fix skips the arm exactly when the tier order proves it
cannot matter, and merges it in when it can.

THE RISK THIS SUITE IS AIMED AT IS NOT SLOWNESS. It is a WRONG ANSWER that looks
like a right one. LAT-P002 shed this same stage, returned HTTP 200 with the
primary result class missing, and **survived a full deploy verification** because
an empty futures bucket reads as "no matches" to everyone who looks. A latency
change that quietly drops a row would do the same. So the assertion is not
"is it faster" — it is **"is the page byte-identical to the un-split query"**,
asserted over randomised corpora rather than three hand-picked ones, because
hand-picked examples test the cases the author already thought of and the defect
class here is precisely the case they did not.

`_fetch_futures_window` takes its query builders as PARAMETERS, so this suite
drives the real function against a model of the ORDER BY instead of a database.
That is deliberate: the seeded CI database is always small, so a data-volume
test would prove nothing, while the ordering property is volume-independent and
is the entire basis of the optimisation.
"""

from __future__ import annotations

import random

import pytest

from app.routes.events import _SEARCH_FUTURES_WINDOW, _fetch_futures_window

WINDOW = _SEARCH_FUTURES_WINDOW

#: The arms, as opaque tokens. `name`/`ticker`/`alias` reach tier 0-1;
#: `outcome` alone reaches tier 2. Mirrors `_futures_name_tier`.
TIER1_ARMS = ["name", "ticker", "alias"]
OUTCOME_ARM = "outcome"


class Row:
    """A candidate market: which arms match it, and where it sorts."""

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


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class FakeDB:
    """Answers a candidate marker from a corpus under the ONE shared ORDER BY.

    The sort key models `_futures_window_query`'s `.order_by(...)`: tier first,
    then everything else (collapsed here into a single unique `sort`, so the
    order is total and no assertion can pass on a coin flip).
    """

    def __init__(self, corpus: list[Row]) -> None:
        self.corpus = corpus
        self.executed: list[frozenset] = []

    async def execute(self, marker):
        _tag, arms = marker
        self.executed.append(arms)
        rows = [r for r in self.corpus if r.arms & arms]
        rows.sort(key=lambda r: (r.tier, r.sort))
        return _Result(rows[:WINDOW])


def _candidates_in(arms):
    return frozenset(arms)


def _window_query(candidate_filter):
    return ("Q", candidate_filter)


@pytest.fixture(autouse=True)
def _no_statement_timeout(monkeypatch):
    """`_fetch_futures_window` re-arms the bound; the fake DB has no SQL."""
    calls = []

    async def _fake(db, deadline=None):
        calls.append(deadline)

    monkeypatch.setattr("app.routes.events._apply_search_statement_timeout", _fake)
    return calls


async def _run(corpus, *, outcome_arm=OUTCOME_ARM):
    db = FakeDB(corpus)
    rows, state = await _fetch_futures_window(
        db, _window_query, _candidates_in, list(TIER1_ARMS), outcome_arm, 0.0
    )
    return db, rows, state


async def _unsplit(corpus, *, outcome_arm=OUTCOME_ARM):
    """What the route did before the split: every arm, one query."""
    arms = list(TIER1_ARMS) + ([outcome_arm] if outcome_arm else [])
    db = FakeDB(corpus)
    result = await db.execute(_window_query(_candidates_in(arms)))
    return result.scalars().unique().all()


# ---------------------------------------------------------------------------
# THE LOAD-BEARING PROPERTY
# ---------------------------------------------------------------------------


def _corpus(rng: random.Random, n: int) -> list[Row]:
    rows = []
    for i in range(n):
        arms = {a for a in (*TIER1_ARMS, OUTCOME_ARM) if rng.random() < 0.35}
        if not arms:
            arms = {rng.choice([*TIER1_ARMS, OUTCOME_ARM])}
        rows.append(Row(i, arms, rng.randrange(10_000_000)))
    # A total order: no two rows may tie, or "identical" would be untestable.
    for pos, r in enumerate(sorted(rows, key=lambda r: r.sort)):
        r.sort = pos
    return rows


@pytest.mark.parametrize("seed", range(40))
async def test_the_split_page_is_identical_to_the_unsplit_page(seed):
    """The whole optimisation, asserted directly: same rows, same order.

    Forty seeded corpora across sizes that straddle the window on both sides —
    the boundary (exactly WINDOW tier<=1 rows) is where an off-by-one would
    live, and a fixed-size fixture would never visit it.
    """
    rng = random.Random(seed)
    corpus = _corpus(rng, rng.choice([0, 1, 5, 19, 20, 21, 60, 200]))

    _db, rows, _state = await _run(corpus)
    expected = await _unsplit(corpus)

    assert [r.id for r in rows] == [r.id for r in expected]


@pytest.mark.parametrize("n_tier1", [0, 1, 19, 20, 21, 50])
async def test_identical_at_every_window_boundary(n_tier1):
    """The boundary walked explicitly, not left to the random draw.

    `n_tier1 == WINDOW` is the exact point the skip turns on. One row either
    side of it is where a `>` that should be `>=` hides.
    """
    corpus = [Row(i, {"name"}, i) for i in range(n_tier1)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(30)]

    _db, rows, _state = await _run(corpus)
    expected = await _unsplit(corpus)

    assert [r.id for r in rows] == [r.id for r in expected]


# ---------------------------------------------------------------------------
# ...AND THAT IT ACTUALLY SKIPS. Identity alone is satisfiable by doing nothing.
# ---------------------------------------------------------------------------


async def test_the_outcome_arm_is_not_queried_when_it_cannot_matter():
    """The saving, asserted as an absence.

    Without this, every test above still passes on a "fix" that changed nothing
    — which is the failure mode a latency guard is most prone to.
    """
    corpus = [Row(i, {"name"}, i) for i in range(WINDOW + 5)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(30)]

    db, rows, state = await _run(corpus)

    assert state == "skipped"
    assert len(db.executed) == 1, (
        "the outcome arm was queried anyway — the 805 ms this change exists to "
        "remove is still being paid"
    )
    assert OUTCOME_ARM not in db.executed[0]
    assert len(rows) == WINDOW


async def test_the_outcome_arm_is_queried_when_it_can_matter():
    """The other direction. A skip that fires always is a recall bug."""
    corpus = [Row(i, {"name"}, i) for i in range(3)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(30)]

    db, rows, state = await _run(corpus)

    assert state == "merged"
    assert len(db.executed) == 2
    assert db.executed[1] == frozenset({OUTCOME_ARM})
    assert [r.id for r in rows[:3]] == [
        0,
        1,
        2,
    ], "tier<=1 rows must lead the page — tier is the first ORDER BY key"
    assert len(rows) == WINDOW


async def test_a_market_matching_both_arms_appears_once_at_its_tier_position():
    """The merge dedups by id, and keeps the TIER<=1 position.

    The outcome-arm query is not filtered against the rows already fetched, so a
    market matching both arms comes back twice. Appending it a second time would
    duplicate a card on the page; dropping the first copy would demote a name
    match below a substring collision.
    """
    both = Row(7, {"name", OUTCOME_ARM}, 5)
    corpus = [both, Row(8, {"name"}, 6)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(5)]

    _db, rows, state = await _run(corpus)

    assert state == "merged"
    ids = [r.id for r in rows]
    assert ids.count(7) == 1
    assert ids[0] == 7
    assert [r.id for r in rows] == [r.id for r in await _unsplit(corpus)]


async def test_the_merged_page_never_exceeds_the_window():
    """The window is the dedup headroom the page depends on (LAT-P038)."""
    corpus = [Row(i, {"name"}, i) for i in range(WINDOW - 1)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(100)]

    _db, rows, _state = await _run(corpus)

    assert len(rows) == WINDOW


async def test_no_outcome_arm_means_one_query_and_no_pretence_of_skipping():
    """`absent` is not `skipped`, and the difference is not cosmetic.

    A short single term with no expansion drops the outcome arm upstream
    (LAT-P010). Reporting that as `skipped` would credit this change with a
    saving it did not make, and the post-deploy check reads this field.
    """
    corpus = [Row(i, {"name"}, i) for i in range(3)]

    db, rows, state = await _run(corpus, outcome_arm=None)

    assert state == "absent"
    assert len(db.executed) == 1
    assert [r.id for r in rows] == [0, 1, 2]


async def test_an_empty_corpus_returns_an_empty_page_not_an_error():
    corpus: list[Row] = []
    db, rows, state = await _run(corpus)
    assert rows == []
    assert state == "merged"
    assert len(db.executed) == 2


async def test_the_second_query_rearms_the_statement_timeout(
    _no_statement_timeout,
):
    """Behavioural twin of the source guard in test_search_latency_contract.

    The outcome-arm query is the expensive half and it runs AFTER the tier<=1
    query has spent part of the budget. Inheriting that bound is the exact
    defect LAT-P005's re-arm exists to prevent.
    """
    corpus = [Row(i, {"name"}, i) for i in range(2)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(5)]

    await _run(corpus)

    assert (
        len(_no_statement_timeout) == 1
    ), "the outcome-arm query did not re-arm the statement timeout"


async def test_the_skip_path_does_not_rearm_because_it_issues_no_second_query(
    _no_statement_timeout,
):
    """The negative control for the test above — otherwise it passes on a
    re-arm that fires unconditionally, which would prove nothing about the
    second query."""
    corpus = [Row(i, {"name"}, i) for i in range(WINDOW)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(5)]

    _db, _rows, state = await _run(corpus)

    assert state == "skipped"
    assert _no_statement_timeout == []
