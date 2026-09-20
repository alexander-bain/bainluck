"""#6598 — `rank` is derived across the market's FIELD, not the write batch.

The defect this file guards, in the reporter's own specimen: a NASCAR futures
board printed three drivers all badged `1` and an 11% row ranked below a 9% row,
because each poll renumbered the legs it happened to write, from 1, against a
field the other legs were never re-measured in. Census: 1,326 open markets
serving a duplicate rank across legs whose prices are NOT equal.

The statement under test runs for real here. sqlite 3.25+ has `rank() OVER` and
3.33+ has `UPDATE … FROM`, so the production statement executes unmodified
against the production model — no hand-written SQL, no re-implementation of the
ordering in Python, which is the only way a test of a ranking can avoid grading
its own restatement of the rule. The JSONB/ARRAY shims are DDL-only and touch no
predicate (the established pattern: `test_futures_categories_unclassified_4047`).

Each test below is aimed at ONE way the rule could be rewritten wrong:

* the specimen        → the batch-scoped derivation is gone
* ties share a rank   → `rank()`, not `row_number()`, and no id tiebreak
* unpriced legs last  → `NULLS LAST` survives
* scope               → the `market_id` filter survives
* healthy = no write  → the `IS DISTINCT FROM` guard survives
* the touch-stamp     → `last_updated` is never in the SET clause
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
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
from app.utils.futures_rank import rerank_market_field_stmt  # noqa: E402

#: The board from #6598, with the stored ranks it actually served: three `1`s
#: from three different writes, no `4`, and Christopher Bell (10.5%) numbered
#: below Chase Briscoe (9.0%).
NASCAR_SPECIMEN = [
    # (name, current_probability, stored rank as served)
    ("Kyle Larson", 0.225, 1),
    ("Ty Gibbs", 0.120, 1),
    ("Denny Hamlin", 0.115, 2),
    ("Ryan Blaney", 0.115, 1),
    ("Christopher Bell", 0.105, 3),
    ("Chase Briscoe", 0.090, 2),
    ("Joey Logano", 0.060, 5),
    ("Chase Elliott", 0.050, 6),
    ("Carson Hocevar", 0.050, 7),
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FuturesOutcome.__table__])
    with Session(engine) as s:
        yield s


def _seed(session, market_id, rows):
    for i, (name, prob, rank) in enumerate(rows, 1):
        session.add(
            FuturesOutcome(
                market_id=market_id,
                external_id=f"M{market_id}-{i}",
                name=name,
                current_probability=prob,
                rank=rank,
            )
        )
    session.commit()


def _field(session, market_id):
    """(name, rank) in served order — probability desc, as the page renders."""
    rows = (
        session.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market_id)
            .order_by(FuturesOutcome.rank, FuturesOutcome.name)
        )
        .scalars()
        .all()
    )
    return [(o.name, o.rank) for o in rows]


def test_the_6598_specimen_stops_printing_three_rows_numbered_one(session):
    _seed(session, 1, NASCAR_SPECIMEN)

    session.execute(rerank_market_field_stmt(1))
    session.commit()

    assert _field(session, 1) == [
        ("Kyle Larson", 1),
        ("Ty Gibbs", 2),
        ("Denny Hamlin", 3),
        ("Ryan Blaney", 3),
        ("Christopher Bell", 5),
        ("Chase Briscoe", 6),
        ("Joey Logano", 7),
        ("Carson Hocevar", 8),
        ("Chase Elliott", 8),
    ]


def test_no_rank_is_held_by_two_different_prices(session):
    """#6598's census definition of the defect, asserted directly.

    A duplicate rank is legitimate when the prices are EQUAL and never
    otherwise. This is the assertion that survives someone rewriting the
    ordering expression into something that happens to pass the specimen.
    """
    _seed(session, 1, NASCAR_SPECIMEN)
    session.execute(rerank_market_field_stmt(1))
    session.commit()

    by_rank: dict[int, set] = {}
    for o in (
        session.execute(
            select(FuturesOutcome).where(FuturesOutcome.market_id == 1)
        )
        .scalars()
        .all()
    ):
        by_rank.setdefault(o.rank, set()).add(float(o.current_probability))

    offenders = {r: p for r, p in by_rank.items() if len(p) > 1}
    assert offenders == {}, f"rank(s) shared by unequal prices: {offenders}"


def test_tied_prices_share_a_rank_rather_than_being_ordered_by_something_else(
    session,
):
    """`rank()`, not `row_number()`.

    Denny Hamlin and Ryan Blaney are both at 11.5%. Any tiebreak — id, name,
    insertion order — would assert one of them is ahead of the other, which the
    prices do not say. A `row_number()` rewrite makes these two 3 and 4 and this
    test is the one that fails.
    """
    _seed(session, 1, NASCAR_SPECIMEN)
    session.execute(rerank_market_field_stmt(1))
    session.commit()

    ranks = dict(_field(session, 1))
    assert ranks["Denny Hamlin"] == ranks["Ryan Blaney"] == 3
    assert ranks["Chase Elliott"] == ranks["Carson Hocevar"] == 8
    # Competition ranking skips the gap a tie consumes: two rows at 3 means the
    # next rank is 5, and nobody is numbered 4.
    assert 4 not in ranks.values()


def test_an_unpriced_leg_never_outranks_a_priced_one(session):
    """Kalshi's placeholder pass (#3518) states this intent in prose and can only
    implement it for the legs it inserts. `NULLS LAST` makes it true field-wide.
    """
    _seed(
        session,
        1,
        [
            ("Priced low", 0.010, 9),
            ("Venue lists it, no book", None, 1),
            ("Priced high", 0.400, 7),
            ("Also no book", None, 2),
        ],
    )
    session.execute(rerank_market_field_stmt(1))
    session.commit()

    ranks = dict(_field(session, 1))
    assert ranks["Priced high"] == 1
    assert ranks["Priced low"] == 2
    # Both unpriced legs tie behind every priced one.
    assert ranks["Venue lists it, no book"] == 3
    assert ranks["Also no book"] == 3


def test_the_statement_touches_only_its_own_market(session):
    _seed(session, 1, NASCAR_SPECIMEN)
    _seed(session, 2, [("Someone else", 0.5, 99), ("Their sibling", 0.1, 98)])

    session.execute(rerank_market_field_stmt(1))
    session.commit()

    assert _field(session, 2) == [("Their sibling", 98), ("Someone else", 99)]


def test_a_field_already_ranked_correctly_is_not_written_at_all(session):
    """The `IS DISTINCT FROM` guard.

    It is not an optimisation: a poll that saw the whole field already wrote the
    right numbers, and a statement that rewrote them anyway would put a row
    version on every leg of every market on every poll.
    """
    _seed(
        session,
        1,
        [("Leader", 0.5, 1), ("Second", 0.3, 2), ("Third", 0.2, 3)],
    )

    result = session.execute(rerank_market_field_stmt(1))
    assert result.rowcount == 0

    # …and one wrong row is one written row, not a whole-field rewrite.
    session.execute(
        FuturesOutcome.__table__.update()
        .where(FuturesOutcome.name == "Third")
        .values(rank=17)
    )
    session.commit()
    assert session.execute(rerank_market_field_stmt(1)).rowcount == 1


def test_the_statement_can_never_refresh_the_liveness_touch_stamp():
    """`last_updated` is a TOUCH-STAMP that `routes/playoffs.py` reads as a
    liveness gate, and this statement is not a poll.

    Asserted on the compiled SET clause rather than on a row, because the
    failure mode is somebody ADDING a column to `.values()` — a row assertion
    would only catch it for the columns the fixture happens to seed.
    """
    sql = str(
        rerank_market_field_stmt(1).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    set_clause = sql.split("SET", 1)[1].split("FROM", 1)[0]
    assigned = [c.split("=")[0].strip() for c in set_clause.split(",")]
    assert assigned == ["rank"], f"the SET clause assigns more than rank: {assigned}"


def test_the_stale_row_a_poll_never_saw_keeps_its_age(session):
    """The same claim, executed. A six-week-old leg gets a coherent rank and
    stays six weeks old — a re-rank that bumped `last_updated` would make the
    fossil rows of #6598's own specimen read as freshly polled.
    """
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc) - timedelta(days=42)
    session.add(
        FuturesOutcome(
            market_id=1,
            external_id="stale",
            name="Fossil",
            current_probability=0.24,
            rank=43,
            last_updated=old,
        )
    )
    session.add(
        FuturesOutcome(
            market_id=1,
            external_id="fresh",
            name="Polled today",
            current_probability=0.50,
            rank=1,
        )
    )
    session.commit()

    session.execute(rerank_market_field_stmt(1))
    session.commit()

    fossil = session.execute(
        select(FuturesOutcome).where(FuturesOutcome.external_id == "stale")
    ).scalar_one()
    assert fossil.rank == 2
    assert abs((fossil.last_updated.replace(tzinfo=timezone.utc) - old).total_seconds()) < 1


def test_every_batch_ranking_poller_re_derives_the_field_after_its_writes():
    """Reachability. The helper repairs nothing it is not called from, and the
    three tasks that rank a BATCH of a larger field are the three that need it.

    (The Polymarket over/under pair writer is deliberately NOT in this list: it
    writes its complete two-leg field in one statement with a positional
    Over=1 / Under=2 numbering, so it cannot produce the fragment defect and
    re-ranking it would reorder a display that is intentional.)
    """
    import pathlib

    # One entry per batch-ranking write path that was wired, counted rather than
    # merely present: `polymarket.py` ranks a batch in the main poll AND in the
    # dark-linked-book pass (#3613), `kalshi.py` in the main poll AND in the
    # linked-series refresh (#3518/#4356), `futures.py` in its single odds_api
    # pass. A call removed from one of the two-call modules reads as 1 here and
    # this fails, which a bare "does it call it at all" assertion would not.
    expected_calls = {"polymarket.py": 2, "kalshi.py": 2, "futures.py": 1}

    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks"
    for module, calls in expected_calls.items():
        src = (root / module).read_text()
        assert "from app.utils.futures_rank import rerank_market_field_stmt" in src, (
            f"{module} does not import the field-wide re-rank"
        )
        found = src.count("rerank_market_field_stmt(")
        assert found == calls, (
            f"{module} calls the field-wide re-rank {found}×, expected {calls} — "
            "a write path either lost its re-rank or gained one nobody graded"
        )
