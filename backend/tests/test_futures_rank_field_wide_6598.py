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
* the population      → every writer of the PRICE re-derives the rank

THE LAST ONE IS CERT-3182's, AND IT REPLACES A GUARD THAT ASKED THE WRONG
QUESTION. The first cut of this file enumerated the three pollers that NUMBER a
batch and asserted each still called the helper. That guard was green while the
ship was broken, because `rank` is not corrupted only by writers that number it
wrong — it is corrupted by every writer that moves ``current_probability`` and
leaves the number alone. Six modules did exactly that, `futures_price_refresh`
loudest among them: it is the scheduled hourly net over precisely the served,
registered and high-value markets the pollers cannot reach, so a price crossing
there re-created the served defect within the hour on rows nothing else was
going to repair.

So the population is taken by AST from ``app/tasks/**`` rather than typed from
memory, and a module that writes the price must either re-derive the field or be
named in :data:`EXEMPT_WRITERS` with a reason. A seventh writer fails a test on
the day it is written. The behaviour that guard protects — a crossing actually
reordering the board — is executed in
``test_futures_price_refresh_reranks_the_field_6598.py``.
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


# ── CERT-3182: the population is "writes the price", not "writes the rank" ───
#
# One entry per wired module, and the number is the count of write BOUNDARIES it
# re-derives at, not a boolean. A boolean cannot tell a module that lost one of
# its two call sites from one that still has both, and two of these modules got
# their second boundary precisely because the first one did not cover the whole
# path.
#
#   futures.py                     1  the odds_api pass
#   kalshi.py                      2  main poll · linked-series refresh (#3518/#4356)
#   polymarket.py                  2  main poll · dark-linked-book pass (#3613)
#   futures_price_refresh.py       4  polymarket write+retire · kalshi write ·
#                                     the pre-kick-off withdrawal · the delisted
#                                     retirement (inside the helper, so both of
#                                     ITS callers are covered by one)
#   tournament_price_refresh.py    1  one PARTITION BY statement per pass
#   kalshi_ws.py                   1  per flush
#   polymarket_ws.py               1  per flush
#   datagolf.py                    2  pre-tournament poll · live poll
#   prediction_market_matching.py  2  the live poll's Kalshi and Polymarket arms
WIRED_WRITERS = {
    "futures.py": 1,
    "kalshi.py": 2,
    "polymarket.py": 2,
    "futures_price_refresh.py": 4,
    "tournament_price_refresh.py": 1,
    "kalshi_ws.py": 1,
    "polymarket_ws.py": 1,
    "datagolf.py": 2,
    "prediction_market_matching.py": 2,
}

#: Writers that move ``current_probability`` and deliberately do NOT re-derive
#: the field. Both write 1.0/0.0 as a SETTLEMENT onto a board that is over, and
#: #6325 refused to renumber a settled board: a finished field's `rank` is the
#: record of how it finished, and re-deriving it from the grade would collapse
#: every loser onto one number. Named here rather than merely absent, because
#: "nobody wired it" and "we decided not to" are the two states this file exists
#: to keep apart.
EXEMPT_WRITERS = {
    "backfill_winners.py": "settlement — writes the grade, not a quote (#6325)",
    "repair_winner_field.py": "settlement repair — same board, same refusal",
}


def _price_writing_task_modules():
    """Modules under `app/tasks` that WRITE ``futures_outcomes.current_probability``.

    By AST, not by grep, so the essay-length comments and docstrings this
    codebase runs on — several of which quote the column inside SQL — cannot
    enter the population and cannot be used to leave it either. Three shapes are
    a write and nothing else is: a ``.values()``/constructor keyword, an ORM
    attribute assignment on something that is not ``self``, and the column
    appearing in the SET clause of a raw-SQL string.
    """
    import ast
    import pathlib
    import re

    column = "current_probability"
    set_clause = re.compile(r"\bSET\b(.*?)(?:\bWHERE\b|\bRETURNING\b|$)", re.S | re.I)
    assigned = re.compile(r"\b" + column + r"\s*=")

    def _docstrings(tree):
        out = set()
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                body = getattr(node, "body", None)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    out.add(id(body[0].value))
        return out

    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks"
    writers = set()
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text())
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == column:
                writers.add(path.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == column
                        and not (
                            isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        )
                    ):
                        writers.add(path.name)
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and "UPDATE" in node.value.upper()
            ):
                if any(
                    assigned.search(m.group(1))
                    for m in set_clause.finditer(node.value)
                ):
                    writers.add(path.name)
    return writers


def test_the_detector_finds_the_writers_this_ship_was_bounced_for():
    """The guard's own control, and it is not ceremony.

    Everything below rests on `_price_writing_task_modules` seeing a write. A
    detector that quietly stopped matching would turn the whole population empty
    and every assertion after it vacuous — which is the exact shape of the
    failure this file is being rewritten to fix, one level down. So: the module
    CERT-3182 named, two it did not, and one non-writer that must stay out.
    """
    writers = _price_writing_task_modules()

    assert "futures_price_refresh.py" in writers, (
        "the detector cannot see the hourly writer CERT-3182 named — every "
        "assertion below is vacuous"
    )
    assert {"kalshi_ws.py", "polymarket_ws.py"} <= writers
    # A reader, not a writer: `precompute_interestingness` selects the column
    # and never assigns it. If this ever enters the population the detector has
    # started matching reads, and the exemption list will grow to hide it.
    assert "precompute_interestingness.py" not in writers


def test_every_writer_of_the_price_re_derives_the_rank_or_is_exempt_by_name():
    """CERT-3182's finding, as a test.

    `rank` is a function of ``current_probability``. A writer that moves the
    price and leaves the number is not neutral — it publishes a stale ordering,
    and on `futures_price_refresh` it did so hourly over the served book. The
    population is therefore every price writer, and silence is not a permitted
    answer for any of them.
    """
    writers = _price_writing_task_modules()
    unaccounted = writers - set(WIRED_WRITERS) - set(EXEMPT_WRITERS)

    assert unaccounted == set(), (
        f"{sorted(unaccounted)} write futures_outcomes.current_probability and "
        "neither re-derive the field nor carry a reason. `rank` is derived from "
        "that column, so leaving it alone publishes the ordering of whatever "
        "wrote it last — which is CERT-3182's finding. Wire "
        "`rerank_market_field_stmt` at the write's own commit boundary, or add "
        "the module to EXEMPT_WRITERS with the reason."
    )


def test_each_wired_writer_still_re_derives_at_every_boundary_it_claims():
    """A call site lost is the defect back, silently, on that path only."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks"
    for module, boundaries in sorted(WIRED_WRITERS.items()):
        src = (root / module).read_text()
        assert "from app.utils.futures_rank import" in src, (
            f"{module} does not import the field-wide re-rank"
        )
        found = src.count("rerank_market_field_stmt(") + src.count(
            "rerank_market_fields_stmt("
        )
        assert found == boundaries, (
            f"{module} re-derives the field at {found} boundaries, expected "
            f"{boundaries} — a write path either lost its re-rank or gained one "
            "nobody graded"
        )


def test_an_exempt_writer_is_still_a_writer():
    """The exemption list is a set of DECISIONS, not a residue.

    A name left here after the module stopped writing the price is a reason
    nobody can check, and it is how an exemption outlives the argument for it.
    """
    writers = _price_writing_task_modules()
    stale = set(EXEMPT_WRITERS) - writers
    assert stale == set(), (
        f"{sorted(stale)} are exempted from re-deriving `rank` but no longer "
        "write the price. Drop the exemption rather than carrying it."
    )
