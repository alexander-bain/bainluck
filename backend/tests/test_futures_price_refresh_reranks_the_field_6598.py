"""#6598 / CERT-3182 — the hourly price writer re-derives the field it moved.

WHAT THE CERT FOUND, AND WHY THE FIRST CUT OF THIS SHIP READ AS FIXED.
#6598 wired `rerank_market_field_stmt` into the three pollers that NUMBER a
batch. It did not wire the scheduled hourly `futures_price_refresh`, which
numbers nothing at all — it writes `current_probability` and has never touched
`rank`:

    scheduled hourly `_write_prices()` changes `FuturesOutcome.current_probability`
    for served / registered / high-value open markets and commits per market
    without updating `rank`.

`rank` is DERIVED from that column, so leaving it alone is not neutrality. The
module's own header says it exists because the discovery polls "structurally
cannot reach" these markets — which is exactly why nothing else was going to
repair the number afterwards. A price CROSSING on this path therefore re-created
#6598's served defect in full, hourly, on the rows most likely to be on screen:

* `/economics` SORTS by `rank` and prints no number, so a 40.2% bar is drawn
  below a 22.9% one with nothing on the page to reveal it;
* the team-page season-futures badge pairs the STORED rank with a LIVE
  `COUNT(*)`, so it printed "#43 of 50" on a field whose last write ranked 29.

THE CONTROL IS A CROSSING, NOT A RE-RANK. Calling the statement and asserting it
produces good numbers is a test of `futures_rank`, and that test already exists
next door. What had to be provable here is the thing the cert claimed: that a
price MOVEMENT through this writer's own boundary leaves the board ordered by
the new prices. So each test below moves a price the way the hourly pass moves
it and then asserts what a reader sees, and
`test_the_crossing_alone_reproduces_the_served_defect` is the strawman that
proves the assertions can fail — without it, a suite that never re-ranked at all
would be just as green.

WHAT IS PRODUCTION HERE AND WHAT IS NOT. The model, the re-derivation statement
and `_retire_delisted_kalshi_legs` are the production article, executed. The
PRICE MOVE is stood in for by a bare UPDATE of the one column: `_write_prices`
also writes `func.now()`, a `price_changed_at` CASE and a `pg_insert` snapshot,
none of which sqlite has, and none of which `rank` is derived from. The claim
under test is "the ordering follows the price", so the price is what the
stand-in has to be faithful about, and it is the same column, the same rows and
the same grain. That the real writer is WIRED to the statement is a separate
assertion with its own executed and AST controls below — neither claim leans on
the other.
"""

import ast
import os
import pathlib
import sys

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, FuturesOutcome  # noqa: E402
from app.tasks import futures_price_refresh as fpr  # noqa: E402
from app.utils.futures_rank import rerank_market_field_stmt  # noqa: E402

MARKET = 61176445

#: A rate-decision ladder as the last FULL poll left it: correctly numbered,
#: because the poll saw the whole field. This is the healthy state the hourly
#: refresh inherits — the defect is not a board that arrives broken, it is a
#: board that is broken BY the next price.
SERVED_BOARD = [
    # (external_id, name, probability, rank as the poll wrote it)
    ("ECON-NOCHANGE", "No change", 0.402, 1),
    ("ECON-25DEC", "25 bps decrease", 0.352, 2),
    ("ECON-50DEC", "50 bps decrease", 0.229, 3),
    ("ECON-25INC", "25 bps increase", 0.017, 4),
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FuturesOutcome.__table__])
    with Session(engine) as s:
        for external_id, name, prob, rank in SERVED_BOARD:
            s.add(
                FuturesOutcome(
                    market_id=MARKET,
                    external_id=external_id,
                    name=name,
                    current_probability=prob,
                    rank=rank,
                )
            )
        s.commit()
        yield s


def _hourly_price(session, external_id, probability):
    """The hourly refresh moving one leg's price. See the module docstring for
    what this stands in for and what it does not."""
    session.execute(
        update(FuturesOutcome)
        .where(
            FuturesOutcome.market_id == MARKET,
            FuturesOutcome.external_id == external_id,
        )
        .values(current_probability=probability)
    )


def _as_the_page_sorts_it(session):
    """`(name, probability)` in the order `/economics` renders — `ORDER BY rank`,
    which is the whole point: the page shows no number to contradict."""
    rows = (
        session.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == MARKET)
            .order_by(FuturesOutcome.rank, FuturesOutcome.external_id)
        )
        .scalars()
        .all()
    )
    return [
        (
            o.name,
            None if o.current_probability is None else float(o.current_probability),
        )
        for o in rows
    ]


def _a_crossing(session):
    """The market turns over between two hourly passes: the 25 bps cut becomes
    the favourite and "No change" falls to third."""
    _hourly_price(session, "ECON-25DEC", 0.548)
    _hourly_price(session, "ECON-NOCHANGE", 0.229)
    _hourly_price(session, "ECON-50DEC", 0.206)


class TestAPriceCrossingLeavesTheBoardInPriceOrder:
    def test_the_crossing_alone_reproduces_the_served_defect(self, session):
        """THE STRAWMAN. Without it every assertion in this class is satisfied by
        a suite that changed nothing.

        This is the production behaviour CERT-3182 refused the token over: the
        hourly pass writes the new prices, `rank` keeps the last poll's opinion,
        and `/economics` draws a 54.8% bar UNDER a 22.9% one.
        """
        _a_crossing(session)
        session.commit()

        served = _as_the_page_sorts_it(session)
        assert served[0] == ("No change", 0.229)
        assert served[1] == ("25 bps decrease", 0.548)
        # Said as the invariant rather than as a row list, so it keeps meaning
        # if the specimen is ever re-cast: the page is out of order.
        probabilities = [p for _, p in served]
        assert probabilities != sorted(probabilities, reverse=True)

    def test_the_re_derivation_puts_the_board_back_in_price_order(self, session):
        _a_crossing(session)
        session.execute(rerank_market_field_stmt(MARKET))
        session.commit()

        assert _as_the_page_sorts_it(session) == [
            ("25 bps decrease", 0.548),
            ("No change", 0.229),
            ("50 bps decrease", 0.206),
            ("25 bps increase", 0.017),
        ]

    def test_the_economics_sort_key_never_contradicts_the_bar_it_draws(
        self, session
    ):
        """The same claim as an invariant, because `/economics` is the surface
        with no number on it — the ONLY thing that can reveal a wrong `rank`
        there is the bar lengths being out of order."""
        _a_crossing(session)
        session.execute(rerank_market_field_stmt(MARKET))
        session.commit()

        probabilities = [p for _, p in _as_the_page_sorts_it(session)]
        assert probabilities == sorted(probabilities, reverse=True)

    def test_the_team_page_badge_cannot_outrun_its_own_denominator(self, session):
        """#6598's third surface. The badge reads "#{stored rank} of
        {live COUNT(*)}", so a rank derived against a field of a different size
        prints a numerator larger than its denominator — "Dawson Knox 24% #43 of
        50" on a market whose last write ranked 29 rows.
        """
        # A leg the hourly pass never saw, carrying a number from a field that
        # was twice this size. This is the fossil, and it is the row the badge
        # renders wrong.
        session.add(
            FuturesOutcome(
                market_id=MARKET,
                external_id="ECON-75DEC",
                name="75 bps decrease",
                current_probability=0.004,
                rank=43,
            )
        )
        session.commit()
        _a_crossing(session)
        session.execute(rerank_market_field_stmt(MARKET))
        session.commit()

        ranks = [
            o.rank
            for o in session.execute(
                select(FuturesOutcome).where(FuturesOutcome.market_id == MARKET)
            )
            .scalars()
            .all()
        ]
        field_size = session.scalar(
            select(func.count())
            .select_from(FuturesOutcome)
            .where(FuturesOutcome.market_id == MARKET)
        )
        assert max(ranks) <= field_size, (
            f"a badge would print #{max(ranks)} of {field_size}"
        )

    def test_a_withdrawn_leg_falls_behind_every_leg_still_quoted(self, session):
        """The retirement half. `_retire_unpriced_legs` and the Kalshi delisting
        pass take a price OFF a leg without renumbering anyone, so the withdrawn
        row keeps its old position at the top of a board it has left.
        """
        _hourly_price(session, "ECON-NOCHANGE", None)
        session.execute(rerank_market_field_stmt(MARKET))
        session.commit()

        served = _as_the_page_sorts_it(session)
        assert served[-1] == ("No change", None)
        assert [name for name, _ in served[:3]] == [
            "25 bps decrease",
            "50 bps decrease",
            "25 bps increase",
        ]


# ── The wiring, executed: `_retire_delisted_kalshi_legs` ─────────────────────


class _RecordingSession:
    """Records every statement, and every commit, in order.

    The retirement path is raw PG SQL (`ANY(:tickers)`, `RETURNING`), so it
    cannot run on sqlite — what is checkable here is the SEQUENCE, which is also
    the part of the claim a reader cannot verify by looking: that the re-rank
    goes out inside the withdrawal's own transaction, and not after a commit
    that could leave the board ranked against prices it no longer holds.
    """

    def __init__(self, retired_ids=(101,)):
        self.retired_ids = list(retired_ids)
        self.log: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        flat = " ".join(sql.split()).upper()
        if flat.startswith("UPDATE FUTURES_OUTCOMES SET CURRENT_PROBABILITY"):
            self.log.append("retire")
            return _Rows([(i,) for i in self.retired_ids])
        if flat.startswith("UPDATE FUTURES_OUTCOMES SET RANK"):
            self.log.append("rerank")
            return _Rows([])
        self.log.append("other")
        return _Rows([])

    async def scalar(self, statement, params=None):
        self.log.append("scalar")
        return False

    async def commit(self):
        self.log.append("commit")


class _Rows:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = len(rows)

    def fetchall(self):
        return self._rows


class _DelistedService:
    """Every ticker asked about is a confirmed 404 — the retiring case."""

    async def market_exists(self, ticker):
        return False


def _delisted_stats():
    return {
        "delisted_checks": 0,
        "delisted_indeterminate": 0,
        "delisted_still_listed": 0,
        "delisted_refused_market_graded": 0,
        "errors": [],
    }


@pytest.mark.asyncio
class TestTheRetirementPathReRanksBeforeItReturns:
    async def test_a_withdrawal_is_followed_by_the_re_rank_in_one_transaction(
        self,
    ):
        session = _RecordingSession()
        retired = await fpr._retire_delisted_kalshi_legs(
            session, _DelistedService(), MARKET, ["KXNFL-FAKE"], _delisted_stats()
        )

        assert retired == 1
        assert session.log == ["retire", "rerank"], (
            "the withdrawal must be followed by the field re-derivation, with no "
            f"commit between them — saw {session.log}"
        )

    async def test_a_pass_that_retired_nothing_writes_no_rank(self):
        """The control. The statement is cheap but it is not free, and a
        re-derivation on a market nothing happened to is this task reaching a
        board it has no business touching."""
        session = _RecordingSession(retired_ids=())
        retired = await fpr._retire_delisted_kalshi_legs(
            session, _DelistedService(), MARKET, ["KXNFL-FAKE"], _delisted_stats()
        )

        assert retired == 0
        assert "rerank" not in session.log


# ── The wiring, by AST: the three boundaries inside the hourly sweep ─────────


def _refresh_function():
    source = (
        pathlib.Path(fpr.__file__).read_text()
        if hasattr(fpr, "__file__")
        else ""
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_refresh_stale_futures_prices"
        ):
            return node
    raise AssertionError("_refresh_stale_futures_prices is gone")


def _innermost_try_bodies(function):
    """Every `try:` BODY in the function, innermost first.

    Innermost matters: these blocks nest (the per-market try sits inside the
    per-source one), so a walk that credits an outer block with an inner
    statement double-counts, and — worse — would let an inner re-rank be
    "guarded" by an outer commit that is a different transaction.
    """
    blocks = []
    for node in ast.walk(function):
        if isinstance(node, ast.Try):
            blocks.append(node)
    # Innermost first: a deeper block has a later start line among any pair that
    # contains the same statement.
    return sorted(blocks, key=lambda t: -t.lineno)


def _statement_lines(body, predicate):
    """Lines in `body` matching `predicate`, EXCLUDING anything inside a nested
    `try` — that statement belongs to the inner block."""
    lines = []
    for stmt in body:
        for child in ast.walk(stmt):
            if isinstance(child, ast.Try) and child is not stmt:
                continue
            if isinstance(child, ast.Call) and predicate(child):
                lines.append(child.lineno)
        for child in ast.walk(stmt):
            if isinstance(child, ast.Try):
                inner = _statement_lines(child.body, predicate)
                lines = [line for line in lines if line not in inner]
    return lines


def _is_rerank(call):
    return isinstance(call.func, ast.Name) and call.func.id == (
        "rerank_market_field_stmt"
    )


def _is_commit(call):
    return isinstance(call.func, ast.Attribute) and call.func.attr == "commit"


def test_every_re_rank_in_the_sweep_is_inside_a_try_that_commits_after_it():
    """"Same transaction" is the load-bearing half of the repair and it is the
    half a reader cannot see.

    A re-rank issued AFTER the commit would still produce the right numbers most
    of the time and would silently leave the board ranked against prices a
    rollback took away. Each of the sweep's three boundaries therefore has to
    live in the same `try` as the commit that follows it — which is a property of
    the tree, so it is asserted on the tree.
    """
    function = _refresh_function()

    guarded = 0
    for block in _innermost_try_bodies(function):
        reranks = _statement_lines(block.body, _is_rerank)
        if not reranks:
            continue
        guarded += 1
        commits = _statement_lines(block.body, _is_commit)
        assert commits, (
            f"the re-rank at line {reranks[0]} is in a try that never commits"
        )
        assert max(commits) > max(reranks), (
            f"the re-rank at line {max(reranks)} runs AFTER the commit at "
            f"{max(commits)} — it is not in the write's transaction"
        )

    assert guarded == 3, (
        "the hourly sweep re-derives the field at three boundaries — the "
        "Polymarket write+retire, the Kalshi write, and the pre-kick-off "
        f"withdrawal — but {guarded} were found. The fourth call is inside "
        "`_retire_delisted_kalshi_legs`, which has its own executed control."
    )
