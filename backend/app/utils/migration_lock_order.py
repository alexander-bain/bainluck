"""A migration takes its tables in the order the APP takes them (#2782).

WHAT HAPPENED, AND WHY #2724 COULD NOT SAVE IT

``link_loss_receipts`` added two columns, widened one and built two indexes on
``market_match_receipts`` — five ``ACCESS EXCLUSIVE`` acquisitions — and only
THEN reached for ``futures_markets``::

    ALTER TABLE futures_markets ADD COLUMN settled_at TIMESTAMP WITH TIME ZONE

Live code takes those two tables the other way round. The receipt writer holds
``futures_markets`` (a ``SELECT`` for ``verify_links_are_durable``, plus the
``FOR KEY SHARE`` the receipt's own foreign key implies) and *then* writes
``market_match_receipts`` — ``app/utils/match_receipts.py``, and every caller
of it. Two parties taking two locks in two orders is the textbook cycle::

    DeadlockDetected: Process 574225 waits for AccessExclusiveLock on
    futures_markets; blocked by process 574143.
    Process 574143 waits for AccessShareLock on market_match_receipts;
    blocked by process 574225.

Four Heroku releases died on it (v4016-v4019, 2026-09-02) and production sat on
stale code for ~50 minutes, blocking every lane rather than the one that wrote
the migration. #2724's lock budget is the wrong shape for it in both settings:
at the default ``lock_timeout`` the ``ALTER`` never wins the lock at all, and
raised high enough to wait, it waits long enough to *enter* the cycle and dies a
deadlock instead. Retrying a deadlock is now permitted
(:func:`app.utils.migration_lock_budget.should_retry`), but a retry is a
survival mechanism, not a fix: ``match_prediction_markets`` runs every 15
minutes at 337s p50 on the heavy queue and holds ``futures_markets`` for its
whole pass, so the contention is permanent and there is no gap to retry into.

THE FIX IS AN ORDER, AND IT IS ONLY A FIX IF IT IS GLOBAL

A deadlock needs a cycle, and a cycle needs two parties disagreeing about
order. If every party — every task, every request, every migration — acquires
these tables in one agreed sequence, no cycle can form, whatever the timing.
:data:`LOCK_ORDER` is that sequence, and it is not invented: each entry cites
the live path that establishes it.

There is a second, quieter reason the most contended table goes FIRST. A
migration's opening acquisition is taken while it holds nothing, so it cannot be
anyone's blocker — the worst it can do is wait. Every lock it takes after that
it takes while holding the hottest table, which is exactly the position from
which waiting is cheap for everyone else.

WHAT THIS MODULE DOES NOT CLAIM

Only the tables in :data:`LOCK_ORDER` are ranked, and only because a live path
was read to establish their relative order. An unranked table is unconstrained
here — a rank asserted without a measured path is a guess, and a guess in this
file reds honest migrations for a reason nobody can check. Extending the tuple
is the intended way to grow the guard, and it costs one citation.

Three static limits, all deliberate and all named so a reader does not mistake
silence for safety:

* Order is TEXTUAL. A branch or a loop is read in the order it is written,
  which is the order a single-pass migration actually runs in.
* ``DROP INDEX foo`` names no table, so the table it locks is invisible here.
  Its sibling ``CREATE INDEX … ON foo`` is visible.
* A ``REFERENCES`` clause locks the referenced table too; only the tables named
  by a statement's own verb are counted.

The complement of those limits is :func:`unreadable_statements`. A migration
that reaches a ranked table has to be statically readable end to end, because
that is precisely when an unprovable order is a deploy that can hang.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

#: The order in which every party — task, request and migration — must acquire
#: these tables. Position is the rank; earlier is taken first.
#:
#: * ``futures_markets`` — held for whole passes by ``match_prediction_markets``
#:   (heavy queue, every 15 min, 337s p50) and ``poll_kalshi_markets`` (320s
#:   p50). It is the most contended table in the schema, so it goes first.
#: * ``market_match_receipts`` — its ``market_id`` is a foreign key to
#:   ``futures_markets.id``, so writing a receipt ALREADY takes a lock on
#:   ``futures_markets`` first, whether the author asked for one or not. The
#:   receipt writer also reads ``futures_markets`` explicitly before flushing
#:   (``match_receipts.verify_links_are_durable``). Both facts point the same
#:   way, which is why this order is the one that was already true.
#: * ``market_link_changes`` — appended in the SAME transaction as the receipt
#:   it describes, immediately after it (``match_receipts.append_link_changes``:
#:   "a change is recorded once, in both places, or in neither").
LOCK_ORDER: tuple[str, ...] = (
    "futures_markets",
    "market_match_receipts",
    "market_link_changes",
)

_RANK = {table: index for index, table in enumerate(LOCK_ORDER)}


@dataclass(frozen=True)
class Acquisition:
    """One table locked by one statement, and where in the file it was asked for."""

    table: str
    lineno: int
    rank: int


@dataclass(frozen=True)
class LockOrderViolation:
    """A table taken while a table that must precede it was not yet held."""

    function: str
    held: Acquisition
    taken: Acquisition

    def __str__(self) -> str:
        return (
            f"{self.function}() takes {self.held.table!r} (line {self.held.lineno}) "
            f"before {self.taken.table!r} (line {self.taken.lineno}), but the app "
            f"takes {self.taken.table!r} first. Acquire in LOCK_ORDER "
            f"{LOCK_ORDER} or the release phase can deadlock against "
            f"match_prediction_markets (#2782)."
        )


def rank(table: str) -> Optional[int]:
    """This table's position in :data:`LOCK_ORDER`, or ``None`` if unranked."""
    return _RANK.get(table)


# --------------------------------------------------------------------------
# Reading a migration
# --------------------------------------------------------------------------

#: Which argument of each Alembic operation names a table. Positional indices
#: first, then the keyword spellings of the same arguments — Alembic accepts
#: both, and a guard that reads only one spelling is a guard with a bypass.
_TABLE_ARGUMENTS: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "create_table": ((0,), ("table_name",)),
    "drop_table": ((0,), ("table_name",)),
    "add_column": ((0,), ("table_name",)),
    "drop_column": ((0,), ("table_name",)),
    "alter_column": ((0,), ("table_name",)),
    "create_index": ((1,), ("table_name",)),
    "drop_index": ((1,), ("table_name",)),
    "create_unique_constraint": ((1,), ("table_name",)),
    "create_check_constraint": ((1,), ("table_name",)),
    "create_primary_key": ((1,), ("table_name",)),
    "drop_constraint": ((1,), ("table_name",)),
    # Both sides of a foreign key are locked while it is validated.
    "create_foreign_key": ((1, 2), ("source_table", "referent_table")),
    "rename_table": ((0, 1), ("old_table_name", "new_table_name")),
}

#: SQL verbs that lock the table they name. Comments are stripped before this
#: runs (gotcha #149's lesson one table over: a guard that reads prose reports
#: on prose). ``DROP INDEX`` is absent because it names an index, not a table.
_SQL_TABLE_RE = re.compile(
    r"""
    \b(?:
        ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?
      | CREATE\s+(?:UNLOGGED\s+|TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?
      | DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?
      | CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?
        (?:IF\s+NOT\s+EXISTS\s+)?[\w".]+\s+ON\s+(?:ONLY\s+)?
      | INSERT\s+INTO\s+
      | UPDATE\s+(?:ONLY\s+)?
      | DELETE\s+FROM\s+(?:ONLY\s+)?
      | TRUNCATE\s+(?:TABLE\s+)?(?:ONLY\s+)?
      | LOCK\s+(?:TABLE\s+)?(?:ONLY\s+)?
    )
    (?P<table>"[^"]+"(?:\."[^"]+")?|[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_sql_comments(sql: str) -> str:
    """Blank out comments, preserving newlines so line offsets still line up."""
    without_blocks = _BLOCK_COMMENT_RE.sub(
        lambda m: re.sub(r"[^\n]", " ", m.group(0)), sql
    )
    return _LINE_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), without_blocks)


def _bare_table_name(raw: str) -> str:
    """``public."futures_markets"`` -> ``futures_markets``."""
    last = raw.split(".")[-1].strip()
    return last.strip('"')


def tables_in_sql(sql: str) -> list[str]:
    """Every table a raw SQL string locks, in the order the statements name them."""
    cleaned = _strip_sql_comments(sql)
    return [
        _bare_table_name(match.group("table"))
        for match in _SQL_TABLE_RE.finditer(cleaned)
    ]


def _callee_name(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _receiver_name(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    return None


def _string_value(node: ast.AST) -> Optional[str]:
    """The literal string this expression is, or ``None`` if it is not one.

    ``sa.text("…")`` is unwrapped because it is the ordinary spelling of a raw
    statement here, and ``a + b`` is folded because long DDL is often written
    as a sum of literals. Anything computed — an f-string, a name, a call —
    returns ``None`` and becomes an :func:`unreadable_statements` entry rather
    than a silent zero tables.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_value(node.left)
        right = _string_value(node.right)
        if left is not None and right is not None:
            return left + right
        return None
    if isinstance(node, ast.Call) and _callee_name(node) == "text" and node.args:
        return _string_value(node.args[0])
    return None


def _argument(node: ast.Call, positions: Sequence[int], keywords: Sequence[str]):
    """Yield the table-naming arguments of one ``op.*`` call, in written order."""
    for index in positions:
        if index < len(node.args):
            yield node.args[index]
    wanted = set(keywords)
    for keyword in node.keywords:
        if keyword.arg in wanted:
            yield keyword.value


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _calls_in_source_order(node: ast.AST) -> list[ast.Call]:
    """Every call under ``node``, ordered by where it is written.

    ``ast.walk`` is breadth-first and therefore says nothing about order, which
    is the only thing this module is about.
    """
    calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
    calls.sort(key=lambda call: (call.lineno, call.col_offset))
    return calls


@dataclass(frozen=True)
class _Reading:
    acquisitions: list[Acquisition]
    unreadable: list[int]


def _read_function(
    function: ast.FunctionDef,
    functions: dict[str, ast.FunctionDef],
    visiting: frozenset[str],
) -> _Reading:
    acquisitions: list[Acquisition] = []
    unreadable: list[int] = []

    for call in _calls_in_source_order(function):
        name = _callee_name(call)
        if name is None:
            continue

        if name in _TABLE_ARGUMENTS and _receiver_name(call) == "op":
            positions, keywords = _TABLE_ARGUMENTS[name]
            for argument in _argument(call, positions, keywords):
                table = _string_value(argument)
                if table is None:
                    unreadable.append(call.lineno)
                    continue
                acquisitions.append(
                    Acquisition(
                        table=_bare_table_name(table),
                        lineno=call.lineno,
                        rank=_RANK.get(_bare_table_name(table), -1),
                    )
                )
            continue

        if name == "execute" and _receiver_name(call) == "op":
            sql = _string_value(call.args[0]) if call.args else None
            if sql is None:
                unreadable.append(call.lineno)
                continue
            for table in tables_in_sql(sql):
                acquisitions.append(
                    Acquisition(
                        table=table, lineno=call.lineno, rank=_RANK.get(table, -1)
                    )
                )
            continue

        # A helper defined in the same migration is part of the migration. One
        # level of indirection is all it takes to hide DDL from a source scan,
        # so calls into module-level helpers are followed, not skipped.
        helper = functions.get(name)
        if helper is not None and name not in visiting:
            nested = _read_function(helper, functions, visiting | {name})
            acquisitions.extend(nested.acquisitions)
            unreadable.extend(nested.unreadable)

    return _Reading(acquisitions=acquisitions, unreadable=unreadable)


def _read(source: str, function: str) -> _Reading:
    tree = ast.parse(source)
    functions = _module_functions(tree)
    target = functions.get(function)
    if target is None:
        return _Reading(acquisitions=[], unreadable=[])
    return _read_function(target, functions, frozenset({function}))


def acquisitions(source: str, *, function: str = "upgrade") -> list[Acquisition]:
    """Every table ``function`` locks, in the order it is written.

    Repeats are kept: the caller decides what a second touch means, and
    :func:`violations` needs to see that the second touch of an already-held
    table is free.
    """
    return _read(source, function).acquisitions


def unreadable_statements(source: str, *, function: str = "upgrade") -> list[int]:
    """Lines where a statement's SQL or table name could not be read statically."""
    return _read(source, function).unreadable


def first_acquisitions(source: str, *, function: str = "upgrade") -> list[Acquisition]:
    """The FIRST time each ranked table is locked, in order.

    Only first touches can violate an order. Once a migration holds
    ``ACCESS EXCLUSIVE`` on a table it holds it for the rest of the
    transaction, so a later statement against the same table acquires nothing
    and cannot deadlock. Flagging a re-touch would red the natural spelling of
    "add the column, then index it, then come back for the constraint".
    """
    seen: set[str] = set()
    ordered: list[Acquisition] = []
    for acquisition in acquisitions(source, function=function):
        if acquisition.table in seen:
            continue
        seen.add(acquisition.table)
        if acquisition.rank >= 0:
            ordered.append(acquisition)
    return ordered


def violations(source: str, *, function: str = "upgrade") -> list[LockOrderViolation]:
    """Every ranked table taken out of :data:`LOCK_ORDER` by ``function``."""
    found: list[LockOrderViolation] = []
    held: Optional[Acquisition] = None
    for acquisition in first_acquisitions(source, function=function):
        if held is not None and acquisition.rank < held.rank:
            found.append(
                LockOrderViolation(function=function, held=held, taken=acquisition)
            )
        if held is None or acquisition.rank > held.rank:
            held = acquisition
    return found


#: The functions a migration file may define that run against the database.
MIGRATION_FUNCTIONS: tuple[str, ...] = ("upgrade", "downgrade")


def violations_in_file(source: str) -> list[LockOrderViolation]:
    """Both directions of one migration. A downgrade deadlocks the same way."""
    found: list[LockOrderViolation] = []
    for function in MIGRATION_FUNCTIONS:
        found.extend(violations(source, function=function))
    return found


def unreadable_in_file(source: str) -> list[tuple[str, int]]:
    """``(function, line)`` for every statically unreadable statement."""
    return [
        (function, lineno)
        for function in MIGRATION_FUNCTIONS
        for lineno in unreadable_statements(source, function=function)
    ]


def touches_ranked_table(source: str) -> bool:
    """Whether this migration reaches any table in :data:`LOCK_ORDER`."""
    return any(
        first_acquisitions(source, function=function)
        for function in MIGRATION_FUNCTIONS
    )


def describe(found: Iterable[LockOrderViolation]) -> str:
    return "\n".join(f"  - {violation}" for violation in found)
