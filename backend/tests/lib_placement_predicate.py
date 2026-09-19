"""A session fake for the placement guards that EVALUATES the predicate.

WHY THIS EXISTS
===============

#6392's guard test served rows by regex-parsing the SQL its statement compiled
to — it read ``sports.key = '…'``, ``events.commence_time >= '…'`` and the
``NOT IN`` list back out of the string. That was a deliberate and good choice:
a fake that ignores the predicate cannot fail when a WHERE clause is deleted,
and #6377 shipped exactly that mistake.

It does not survive #7086. The tournament guard asks three questions instead of
one, and two of them are shapes the regexes cannot read:

  * ``commence_time <= X OR commence_time >= Y`` — the regex finds the ``>=``
    and reads it as a floor, silently serving rows the query excluded;
  * ``commence_time >= A AND commence_time <= B`` — the regex has no notion of a
    ceiling at all, so the band degenerates into a half-line.

A rig that mis-reads the predicate does not merely weaken a test, it INVERTS
one: the NPB control would go red against correct code, and the Davis Cup
refusal would go green against broken code. So this walks the SQLAlchemy
expression tree and evaluates it against each row, which honours any predicate
the code emits — including ones nobody thought to write a regex for.

TWO PROPERTIES IT IS BUILT FOR
==============================

**It fails loudly on anything it does not understand.** An unknown column or
operator raises :class:`UnreadablePredicate` rather than being skipped. A rig
that quietly ignores a clause it cannot parse is the vacuous-guard trap wearing
a different hat: the tests would pass while testing less than they claim.

**It implements SQL's three-valued logic, not Python's.** This is load-bearing
rather than pedantry. The guard admits a legacy row whose ``commence_time_source``
is NULL through an explicit ``IS NULL`` arm, because in SQL
``NULL NOT IN (…)`` is NULL and therefore not a match. Under Python semantics
``None not in (…)`` is ``True``, so deleting that arm would leave
``test_a_legacy_null_source_row_still_anchors_a_season`` green against a
predicate that had stopped admitting NULL rows — a guard asserting a behaviour
it no longer has.
"""
import operator

from sqlalchemy.sql import operators as sa_operators
from sqlalchemy.sql.elements import BindParameter, Null


class UnreadablePredicate(AssertionError):
    """The rig met a clause it cannot evaluate, so it refuses to guess.

    Raised rather than returning False: a silent skip would turn a widened
    predicate into a passing test, which is the whole failure mode this rig is
    here to make impossible.
    """


class ScheduleRow:
    """One ``events``-joined-``sports`` row the guard's queries can see."""

    def __init__(self, league, commence_time, source):
        self.league = league
        self.commence_time = commence_time
        self.source = source

    def __repr__(self):
        return (
            f"ScheduleRow({self.league!r}, {self.commence_time.isoformat()}, "
            f"{self.source!r})"
        )


#: Every column the guard is allowed to read, and where it lives on a row.
#: A column outside this map raises — if the predicate starts reading a new
#: column, the rig must be taught what it means rather than ignore it.
_COLUMN_READERS = {
    ("sports", "key"): lambda row: row.league,
    ("events", "commence_time"): lambda row: row.commence_time,
    ("events", "commence_time_source"): lambda row: row.source,
}


def _sql_comparison(function):
    """Wrap a Python comparison in SQL's NULL propagation."""

    def compare(left, right):
        if left is None or right is None:
            return None
        return function(left, right)

    return compare


def _not_in(left, right):
    if left is None:
        return None
    return left not in tuple(right)


def _in(left, right):
    if left is None:
        return None
    return left in tuple(right)


_OPERATORS = {
    operator.eq: _sql_comparison(operator.eq),
    operator.ne: _sql_comparison(operator.ne),
    operator.lt: _sql_comparison(operator.lt),
    operator.le: _sql_comparison(operator.le),
    operator.gt: _sql_comparison(operator.gt),
    operator.ge: _sql_comparison(operator.ge),
    sa_operators.eq: _sql_comparison(operator.eq),
    sa_operators.ne: _sql_comparison(operator.ne),
    sa_operators.lt: _sql_comparison(operator.lt),
    sa_operators.le: _sql_comparison(operator.le),
    sa_operators.gt: _sql_comparison(operator.gt),
    sa_operators.ge: _sql_comparison(operator.ge),
    # IS / IS NOT are the two that are never NULL themselves.
    sa_operators.is_: lambda left, right: left is right,
    sa_operators.is_not: lambda left, right: left is not right,
    sa_operators.in_op: _in,
    sa_operators.not_in_op: _not_in,
}


def _literal(node, row):
    """The value of one side of a comparison, for this row."""
    if isinstance(node, BindParameter):
        return node.value
    if isinstance(node, Null) or node is None:
        return None
    table = getattr(node, "table", None)
    name = getattr(node, "name", None)
    if table is not None and name is not None:
        reader = _COLUMN_READERS.get((table.name, name))
        if reader is None:
            raise UnreadablePredicate(
                f"the guard read {table.name}.{name}, which this rig does not "
                f"know how to serve — teach it rather than ignore the clause"
            )
        return reader(row)
    raise UnreadablePredicate(f"cannot read a value out of {node!r}")


def _and(values):
    if any(value is False for value in values):
        return False
    if any(value is None for value in values):
        return None
    return True


def _or(values):
    if any(value is True for value in values):
        return True
    if any(value is None for value in values):
        return None
    return False


def evaluate(clause, row):
    """Evaluate one SQLAlchemy clause against ``row``. True / False / None."""
    if clause is None:
        return True
    clauses = getattr(clause, "clauses", None)
    if clauses is not None and not isinstance(clause, BindParameter):
        operator_name = getattr(clause.operator, "__name__", "")
        parts = [evaluate(part, row) for part in clauses]
        if operator_name in ("and_", "_conjunction", "conjunction"):
            return _and(parts)
        if operator_name in ("or_", "_disjunction", "disjunction"):
            return _or(parts)
        raise UnreadablePredicate(
            f"unknown boolean operator {operator_name!r} over {len(parts)} "
            f"clauses"
        )
    element = getattr(clause, "element", None)
    if element is not None and hasattr(clause, "self_group"):
        # A Grouping — parentheses around a nested expression.
        return evaluate(element, row)
    clause_operator = getattr(clause, "operator", None)
    if clause_operator is not None and hasattr(clause, "left"):
        evaluator = _OPERATORS.get(clause_operator)
        if evaluator is None:
            raise UnreadablePredicate(
                f"unknown comparison operator "
                f"{getattr(clause_operator, '__name__', clause_operator)!r} — "
                f"this rig will not guess what it means"
            )
        return evaluator(_literal(clause.left, row), _literal(clause.right, row))
    raise UnreadablePredicate(f"cannot evaluate clause {clause!r}")


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class PredicateSession:
    """Serves exactly the rows the statement's WHERE clause actually admits."""

    def __init__(self, rows):
        self._rows = list(rows)
        self.compiled = []
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        self.compiled.append(
            str(statement.compile(compile_kwargs={"literal_binds": True}))
        )
        where = statement.whereclause
        served = [row for row in self._rows if evaluate(where, row) is True]
        limit = getattr(statement, "_limit", None)
        if limit is None:
            limit_clause = getattr(statement, "_limit_clause", None)
            limit = getattr(limit_clause, "value", None)
        if limit is not None:
            served = served[:limit]
        return _Result(served)

    @property
    def round_trips(self) -> int:
        return len(self.statements)
