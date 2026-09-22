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

So the population is taken by AST from the application tree rather than typed
from memory, and a module that writes the price must either re-derive the field
or be named in :data:`EXEMPT_WRITERS` with a reason. A further writer fails a
test on the day it is written. The behaviour that guard protects — a crossing
actually reordering the board — is executed in
``test_futures_price_refresh_reranks_the_field_6598.py``.

WIDENED FROM ``app/tasks/**`` TO ``app/**`` BY CERT-3189's NAMED FOLLOW-UP.
That scope was never a finding that only tasks write the price; it was the blast
radius of the bounce. Outside it sat `routes/admin_providers.py`, an operator
pass that reprices every Odds API board and commits — the same defect reaching
the reader by the operator's hand rather than the hourly poll's. Widening a
detector demands narrowing it first, because its two failure modes are not
symmetric: a false positive is loud and pressures someone into writing an
untrue exemption, while a false negative is silent forever. Both were present
and both are pinned by their own control below.
"""

import os
import re
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
from app.utils.futures_rank import (  # noqa: E402
    rerank_market_field_stmt,
    rerank_market_fields_stmt,
)

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
#
# Keyed by path relative to `app/`, not by bare filename. The population is the
# whole application now (see `_price_writing_modules`), and two packages may
# hold the same filename — under bare names the wrong file would satisfy an
# entry and the real writer would leave the population silently.
WIRED_WRITERS = {
    "tasks/futures.py": 1,
    "tasks/kalshi.py": 2,
    "tasks/polymarket.py": 2,
    "tasks/futures_price_refresh.py": 4,
    "tasks/tournament_price_refresh.py": 1,
    "tasks/kalshi_ws.py": 1,
    "tasks/polymarket_ws.py": 1,
    "tasks/datagolf.py": 2,
    "tasks/prediction_market_matching.py": 2,
    # CERT-3189's named residual, wired by #6598's follow-up. The operator
    # normalization pass rewrites the price across every Odds API board and
    # commits; one deduped statement after the flush re-derives their fields.
    "routes/admin_providers.py": 1,
}

#: Writers that move ``current_probability`` and deliberately do NOT re-derive
#: the field. Named here rather than merely absent, because "nobody wired it"
#: and "we decided not to" are the two states this file exists to keep apart.
#:
#: The first two write 1.0/0.0 as a SETTLEMENT onto a board that is over, and
#: #6325 refused to renumber a settled board: a finished field's `rank` is the
#: record of how it finished, and re-deriving it from the grade would collapse
#: every loser onto one number.
#:
#: The third is a different kind of exemption and the difference matters: it is
#: not a write at all. `playoffs.py` coerces a winner's price to 1.0 on ORM
#: objects inside a GET whose session is `get_db`, which is read-only BY
#: CONSTRUCTION — its docstring is "closes without committing… accidental
#: writes are silently discarded". So the coercion is a display value that
#: never reaches a row, and re-deriving a rank from it would write a rank the
#: stored prices do not support. That exemption is CONDITIONAL, and the
#: condition is asserted by
#: `test_the_playoffs_exemption_still_rests_on_a_read_only_session` below —
#: the day that module takes a writable session the exemption is wrong, and a
#: reason nobody re-checks is how a stale exemption hides a real writer.
#: The fourth (#7987) is the third kind again — not a write at all, for a
#: different reason — and it is CONDITIONAL in the same way. `settled_price.py`
#: is SQL TEXT: every function in it RETURNS a string or a dict and none of them
#: takes a session, executes, or commits. There is therefore no "write's own
#: commit boundary" in that module to wire a re-rank to; the boundary belongs to
#: whichever caller splices the text, and those callers are scanned here on
#: their own account.
#:
#: It entered this population when #7987 added
#: `ungraded_settlement_withdraw_sql` — the first function here to emit a WHOLE
#: statement rather than a `SET`-clause fragment, which is the only reason the
#: scanner can see a module that has always written this column.
#:
#: AND RE-DERIVING WOULD BE THE WRONG ANSWER ANYWAY, by the refusal already
#: recorded two paragraphs up: every statement this module emits acts on a leg
#: whose board the venue has SETTLED, and #6325 refuses to renumber a settled
#: board because a finished field's `rank` is the record of how it finished.
#: The condition — that the module executes nothing — is asserted by
#: `test_the_settled_price_exemption_still_rests_on_a_module_that_executes_nothing`.
EXEMPT_WRITERS = {
    "tasks/backfill_winners.py": "settlement — writes the grade, not a quote (#6325)",
    "tasks/repair_winner_field.py": "settlement repair — same board, same refusal",
    "routes/playoffs.py": "display-only coercion in a read-only GET — never persisted",
    "utils/settled_price.py": "SQL text only — no session, no commit boundary to wire; settled boards are never renumbered (#6325/#7987)",
}


#: Call shapes that persist a price, measured rather than assumed: across the
#: whole of `app/`, the only callees taking a ``current_probability=`` keyword
#: are `.values(...)` (7 modules, Core insert/update) and the `FuturesOutcome`
#: constructor. The one other caller is `_MidPricedOutcome(...)` in
#: `utils/live_blend.py` — a local dataclass that models an outcome for the
#: blend and touches no row. Without this the widened population would carry
#: that dataclass, and the only way back out would be an exemption saying "not
#: really a writer", which is how an exemption list stops meaning anything.
_PERSISTING_CALLEES = {".values", "FuturesOutcome"}

_SET_CLAUSE_RE = re.compile(
    r"\bSET\b(.*?)(?:\bWHERE\b|\bRETURNING\b|\bFROM\b|$)", re.S | re.I
)
_SQL_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


def sql_set_assignment_targets(body: str) -> list[str]:
    """The column names a SET clause ASSIGNS, ignoring anything on the right.

    Module-level and separately tested ON PURPOSE. Its first home was a closure
    inside the scanner, and the control that was supposed to prove it worked
    asserted that `tasks/kalshi.py` was in the population — which that module
    satisfies through its seven ``.values()`` calls no matter what this parser
    does. Deleting the comment-stripping left the suite green. A helper reached
    only through a caller that has other ways to succeed is a helper with no
    test, so it is tested on the clause text itself.

    Comments are stripped BEFORE the split because a ``--`` comment's prose
    contains commas (see `tasks/kalshi.py`), and a comma inside what is
    logically one assignment shreds the clause.
    """
    body = _SQL_COMMENT_RE.sub(" ", body)
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)

    targets = []
    for part in parts:
        depth = 0
        for i, ch in enumerate(part):
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif (
                ch == "="
                and depth == 0
                and (i + 1 >= len(part) or part[i + 1] not in "=<>")
                and (i == 0 or part[i - 1] not in "!<>=")
            ):
                targets.append(part[:i].strip().strip('"').split(".")[-1])
                break
    return targets


def _price_writing_modules():
    """Modules under `app/` that WRITE ``futures_outcomes.current_probability``.

    By AST, not by grep, so the essay-length comments and docstrings this
    codebase runs on — several of which quote the column inside SQL — cannot
    enter the population and cannot be used to leave it either. Three shapes are
    a write and nothing else is: a persisting call keyword, an ORM attribute
    assignment on something that is not ``self``, and the column being an
    ASSIGNMENT TARGET in the SET clause of a raw-SQL string.

    WIDENED FROM `app/tasks` BY CERT-3189's FOLLOW-UP, AND NARROWED FIRST
    =====================================================================

    The tasks-only scope was not a judgement that only tasks write the price —
    it was the blast radius of the bounce that created this file. It missed
    `routes/admin_providers.py`, an operator pass that reprices every Odds API
    board and commits.

    Widening a detector before narrowing it is the trap, because the two
    failures are not symmetric. A false POSITIVE is loud: it fails this suite
    until someone wires or exempts an innocent module, and the pressure is to
    write the exemption. A false NEGATIVE is silent forever. Both were present
    and both are fixed here, each with its own control test below:

    * false positive — `routes/admin_data_quality.py` runs
      ``SET is_winner = (fo.current_probability = mu.max_prob)``. The column is
      on the RIGHT of that assignment, as a comparison; the column being
      ASSIGNED is `is_winner`. A substring search for ``current_probability =``
      inside the SET body cannot tell the two apart, so the body is split into
      its top-level assignments and only the text left of each ``=`` counts.
    * false negative — `tasks/kalshi.py` really does assign the column in a SET
      clause, but a ``--`` comment sits between the commas and its PROSE
      CONTAINS COMMAS. Splitting on commas without stripping SQL comments first
      shreds that clause and loses a genuine writer. Comments go before the
      split, not after.
    """
    import ast
    import pathlib

    column = "current_probability"

    def _callee(node):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return f".{func.attr}"
        return "?"

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

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    writers = set()
    # `rglob`, so a writer added inside a sub-package is seen the day it lands.
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - not our file to fix
            continue
        key = path.relative_to(root).as_posix()
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callee(node) in _PERSISTING_CALLEES:
                if any(kw.arg == column for kw in node.keywords):
                    writers.add(key)
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
                        writers.add(key)
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and "UPDATE" in node.value.upper()
            ):
                if any(
                    column in sql_set_assignment_targets(m.group(1))
                    for m in _SET_CLAUSE_RE.finditer(node.value)
                ):
                    writers.add(key)
    return writers


def test_the_detector_finds_the_writers_this_ship_was_bounced_for():
    """The guard's own control, and it is not ceremony.

    Everything below rests on `_price_writing_modules` seeing a write. A
    detector that quietly stopped matching would turn the whole population empty
    and every assertion after it vacuous — which is the exact shape of the
    failure this file is being rewritten to fix, one level down. So: the module
    CERT-3182 named, two it did not, and one non-writer that must stay out.
    """
    writers = _price_writing_modules()

    assert "tasks/futures_price_refresh.py" in writers, (
        "the detector cannot see the hourly writer CERT-3182 named — every "
        "assertion below is vacuous"
    )
    assert {"tasks/kalshi_ws.py", "tasks/polymarket_ws.py"} <= writers
    # A reader, not a writer: `precompute_interestingness` selects the column
    # and never assigns it. If this ever enters the population the detector has
    # started matching reads, and the exemption list will grow to hide it.
    assert "tasks/precompute_interestingness.py" not in writers


def test_the_detector_reaches_outside_app_tasks():
    """CERT-3189's residual was invisible because the population had a folder.

    `routes/admin_providers.py` reprices every Odds API board and commits, and
    sat outside the scan for the whole of #6598. Pin the reach itself: a scope
    that silently narrowed back to `app/tasks` would take this writer with it.
    """
    writers = _price_writing_modules()

    assert "routes/admin_providers.py" in writers, (
        "the operator normalization pass is not in the population — the scan "
        "has narrowed back towards app/tasks and CERT-3189's residual is "
        "invisible again"
    )
    assert any(not key.startswith("tasks/") for key in writers)


def test_a_comparison_in_a_set_clause_is_not_a_write():
    """The false POSITIVE, pinned on the statement that produced it.

    `admin_data_quality.py` grades a multi-outcome board with
    ``SET is_winner = (fo.current_probability = mu.max_prob)``. The column is
    read there, on the right of an assignment to a different column. A detector
    that counts it demands that a settlement grader "re-derive the field", and
    the only way to satisfy that demand is an exemption that is not true.
    """
    writers = _price_writing_modules()

    assert "routes/admin_data_quality.py" not in writers, (
        "a SET clause that COMPARES current_probability is being read as a "
        "write — the detector is matching the right-hand side"
    )


def test_a_dataclass_that_models_an_outcome_is_not_a_write():
    """The other false positive the widening would have introduced.

    `utils/live_blend.py` builds `_MidPricedOutcome(current_probability=...)`,
    a local dataclass standing in for an outcome while blending. It touches no
    row. It is kept out by the shape of the CALLEE rather than by name, so a
    second such dataclass does not need a second exemption.
    """
    writers = _price_writing_modules()

    assert "utils/live_blend.py" not in writers


#: `tasks/kalshi.py`'s settlement clause, reduced to the shape that matters: a
#: `--` comment between two assignments WHOSE PROSE CONTAINS COMMAS.
_COMMENTED_SET_CLAUSE = """
    is_winner = :w, resolution_source = 'api_settlement',
        -- #5246 / CERT-2637. The grade is a BIND PARAM here, so the price
        -- has to follow the same param rather than a literal: two
        -- statements keyed off one `:w` cannot disagree, a literal could.
        current_probability = CASE WHEN :w THEN 1.0 ELSE 0.0 END
"""

#: `routes/admin_data_quality.py`'s pass-7 grading clause. `current_probability`
#: appears on the RIGHT, inside a comparison, and `is_winner` is what is written.
_COMPARING_SET_CLAUSE = """
    is_winner = (fo.current_probability = mu.max_prob),
    resolution_source = 'multi_max_prob'
"""


def test_the_set_clause_parser_reads_targets_and_not_the_right_hand_side():
    """Both SQL failure modes, tested on the parser itself rather than through it.

    THIS TEST EXISTS BECAUSE ITS FIRST VERSION WAS VACUOUS. It asserted that
    `tasks/kalshi.py` was in the writer population, which looks like a test of
    the comment-stripping and is not: that module also writes through seven
    ``.values()`` calls, so it stays in the population no matter how badly this
    parser fails. Deleting the comment-stripping altogether left the suite
    green. A mutation that survives is the assertion telling you it cannot
    fail, so the parser is now called directly on both clauses.
    """
    commented = sql_set_assignment_targets(_COMMENTED_SET_CLAUSE)
    assert "current_probability" in commented, (
        "a real assignment was lost behind a `--` comment whose prose contains "
        "commas — comments must be stripped BEFORE the clause is split"
    )
    assert commented == ["is_winner", "resolution_source", "current_probability"]

    compared = sql_set_assignment_targets(_COMPARING_SET_CLAUSE)
    assert compared == ["is_winner", "resolution_source"]
    assert "current_probability" not in compared, (
        "a COMPARISON on the right-hand side is being read as a write target"
    )


def test_the_playoffs_exemption_still_rests_on_a_read_only_session():
    """An exemption nobody re-checks is how a stale reason hides a live writer.

    `playoffs.py` is exempt for one reason only: its coercion of a winner's
    price to 1.0 happens on ORM objects in a GET served by `get_db`, which
    never commits, so no row moves. That reason is a property of the MODULE,
    not of the line — the day a handler there takes `get_db_rw` or commits, the
    coercion starts persisting a price with no rank behind it and the exemption
    becomes a lie. So assert the condition, not the conclusion.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "playoffs.py"
    ).read_text()

    assert "routes/playoffs.py" in EXEMPT_WRITERS
    assert "get_db_rw" not in source and ".commit()" not in source, (
        "playoffs.py has taken a writable session or started committing, so "
        "its price coercion may now persist. Its EXEMPT_WRITERS reason "
        "('never persisted') no longer holds — wire the rerank or re-derive "
        "the reason."
    )


def test_the_settled_price_exemption_still_rests_on_a_module_that_executes_nothing():
    """#7987's exemption, asserted as its condition rather than its conclusion.

    `settled_price.py` is exempt because it is SQL TEXT — it emits statements
    and runs none of them, so it owns no commit boundary a re-rank could be
    wired to. That is a property of the MODULE, and the day a function there
    takes a session and executes, the module becomes a real writer on a real
    boundary and the reason becomes a lie.

    Asserted by AST rather than by grep so the module's essay-length docstrings
    — which quote `session.execute` while explaining its callers — cannot
    satisfy or break it.
    """
    import ast
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app" / "utils" / "settled_price.py"
    )
    tree = ast.parse(path.read_text())

    assert "utils/settled_price.py" in EXEMPT_WRITERS

    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                and not (isinstance(n, ast.ImportFrom) and n.module == "__future__")], (
        "settled_price.py has grown an import. Its exemption rests on being "
        "inert SQL text; re-check the reason."
    )

    calls = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert not ({"execute", "commit", "flush", "scalar"} & calls), (
        "settled_price.py now executes SQL, so it owns a commit boundary and "
        "its EXEMPT_WRITERS reason ('SQL text only') no longer holds — wire "
        f"the rerank or re-derive the reason. Found: {sorted(calls)}"
    )

    params = {
        a.arg
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        for a in n.args.args
    }
    assert "session" not in params and "conn" not in params, (
        "a function in settled_price.py now takes a session — see above"
    )


def test_every_writer_of_the_price_re_derives_the_rank_or_is_exempt_by_name():
    """CERT-3182's finding, as a test.

    `rank` is a function of ``current_probability``. A writer that moves the
    price and leaves the number is not neutral — it publishes a stale ordering,
    and on `futures_price_refresh` it did so hourly over the served book. The
    population is therefore every price writer, and silence is not a permitted
    answer for any of them.
    """
    writers = _price_writing_modules()
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

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
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
    writers = _price_writing_modules()
    stale = set(EXEMPT_WRITERS) - writers
    assert stale == set(), (
        f"{sorted(stale)} are exempted from re-deriving `rank` but no longer "
        "write the price. Drop the exemption rather than carrying it."
    )


# ── CERT-3189's residual: the operator path, executed ────────────────────────


def _operator_repriced_board(session, *, flush_before_rerank, autoflush=True):
    """The normalization pass's shape: ORM price writes, then the Core re-rank.

    Faithful about the part under test and honest about the rest. The prices are
    written the way `normalize_futures_probabilities` writes them — attribute
    assignment on loaded `FuturesOutcome` rows, which is what makes this path
    different from every other wired writer (they all write through Core). The
    snapshot averaging that DERIVES those numbers is not reproduced: the claim
    here is "the ordering follows whatever the pass wrote", so the written
    prices are what the stand-in must be faithful about.
    """
    session.autoflush = autoflush
    # Seeded ranks agree with the seeded prices — the board starts CORRECT, so
    # the only thing that can produce the expected numbers is a re-derivation
    # after the crossing. (Seeded the other way round, the stale ranks happen to
    # equal the right answer and every assertion below passes on a no-op. That
    # was the first version of this fixture and a mutation caught it.)
    _seed(session, 7, [("Drifted long", 0.10, 2), ("Shortened", 0.80, 1)])

    # The crossing: the pass recomputes both legs and they swap places.
    for outcome in (
        session.execute(select(FuturesOutcome).where(FuturesOutcome.market_id == 7))
        .scalars()
        .all()
    ):
        outcome.current_probability = 0.85 if outcome.name == "Drifted long" else 0.05

    if flush_before_rerank:
        session.flush()
    session.execute(rerank_market_fields_stmt([7]))
    session.commit()
    return dict(_field(session, 7))


def test_the_operator_pass_leaves_the_board_ordered_by_the_prices_it_wrote(session):
    """CERT-3189's residual as behaviour, not as a call-site count.

    `test_each_wired_writer_still_re_derives_at_every_boundary_it_claims` reads
    the source and counts. That catches a deleted call and cannot catch a call
    that runs at the wrong moment, which is the only interesting way this
    particular path breaks.
    """
    assert _operator_repriced_board(session, flush_before_rerank=True) == {
        "Drifted long": 1,
        "Shortened": 2,
    }


def test_without_the_rerank_the_operator_pass_serves_the_old_ordering(session):
    """The strawman. Without it the two tests above would pass on a no-op.

    This is the defect as the reader meets it: the operator normalizes the book,
    every price is correct, and the board still lists the 5% leg first because
    `rank` was left holding the ordering of whatever wrote it last.
    """
    _seed(session, 8, [("Drifted long", 0.10, 2), ("Shortened", 0.80, 1)])
    for outcome in (
        session.execute(select(FuturesOutcome).where(FuturesOutcome.market_id == 8))
        .scalars()
        .all()
    ):
        outcome.current_probability = 0.85 if outcome.name == "Drifted long" else 0.05
    session.commit()  # commit WITHOUT re-deriving, as the pass did before #6598

    ranks = dict(_field(session, 8))
    prices = {
        o.name: float(o.current_probability)
        for o in session.execute(
            select(FuturesOutcome).where(FuturesOutcome.market_id == 8)
        )
        .scalars()
        .all()
    }
    # The 85% leg is numbered BELOW the 5% leg: stale `rank`, correct prices.
    assert ranks["Drifted long"] == 2 and prices["Drifted long"] == 0.85
    assert ranks["Shortened"] == 1 and prices["Shortened"] == 0.05


def test_the_rerank_reads_the_written_prices_and_not_the_ones_it_replaced(session):
    """Why the flush is written out even though autoflush would do it.

    With `autoflush=False` the Core statement re-derives from the prices still
    on disk, and the board comes out EXACTLY INVERTED — a fresh-looking ordering
    that is precisely wrong. This pins the ordering of the two operations rather
    than the session flag that currently hides the question.
    """
    unflushed = _operator_repriced_board(
        session, flush_before_rerank=False, autoflush=False
    )
    assert unflushed == {"Drifted long": 2, "Shortened": 1}, (
        "expected the unflushed path to rank the OLD prices — if this now "
        "matches the written prices, the statement is no longer reading them "
        "back and this control has stopped meaning anything"
    )
