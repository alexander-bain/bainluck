"""Is this the database cancelling our statement, or is it a real error?

A Postgres ``statement_timeout`` does not arrive as a Python timeout. It arrives
as the server cancelling the running statement, which asyncpg raises as
``QueryCanceledError`` and SQLAlchemy re-raises wrapped in ``DBAPIError``. To a
request handler that only catches ``asyncio.TimeoutError`` it is therefore
indistinguishable from a genuine query bug, and it becomes a bare HTTP 500
(#2303: ``/api/playoffs/nfl`` returned 500 at 20.3 s while its own 25 s wall —
which degrades truthfully — never fired).

The predicate here is deliberately **narrow**, and narrowness is the whole
point. A caller that widens its ``except`` to ``DBAPIError`` would also contain
a syntax error, a bad bind parameter, a dead connection and a constraint
violation, and would report every one of them to the user as "we ran out of
time". That is the same failure #1484 removed from the grid route in the other
direction — a real defect wearing a healthy costume — so the containment must
be able to say *no*.

**The test is SQLSTATE ``57014`` (``query_canceled``)**, not the exception's
text. The string form of an asyncpg error is the server's ``ERROR`` message and
is localisable; the SQLSTATE is defined by the wire protocol and is the same
five characters from every driver (asyncpg exposes it as ``sqlstate``, psycopg2
as ``pgcode``). ``57014`` is raised for a ``statement_timeout``, for a
client-issued cancel and for ``pg_cancel_backend`` — all three are "the database
stopped this statement", which is exactly the class a caller wants to degrade
on, so no attempt is made to tell them apart.

A second, subordinate test matches the driver exception's **class name**
(``QueryCanceledError``) for a driver that raises the right error without
populating a SQLSTATE attribute. That is a type check, not the message sniffing
this module rejects — the message is server output, the class is the driver's
own classification — and it is a widening of exactly one exception type. It is
listed second because SQLSTATE is the authority when both are available.

🔴 **``asyncio.CancelledError`` is NOT this and must never match.** It means the
client hung up or the task was cancelled by us; treating it as a degraded serve
would keep work alive that the event loop is trying to tear down.
"""

from __future__ import annotations

# SQLSTATE class 57 is "operator intervention"; 57014 is query_canceled.
QUERY_CANCELED_SQLSTATE = "57014"

# asyncpg's generated class for 57014. Matched by name so this module — and
# therefore every route that imports it — does not have to import the driver.
QUERY_CANCELED_CLASS_NAME = "QueryCanceledError"

# Depth bound on the cause chain walk. A wrapped driver error is one or two
# links deep (DBAPIError -> orig, or raise-from); anything deeper is a cycle or
# a pathological chain and is not worth following into an unbounded loop.
_MAX_CHAIN_DEPTH = 8


def _chain(exc: BaseException):
    """Yield ``exc`` and the driver/cause exceptions reachable from it.

    Three links matter and they are not the same link:

    * ``.orig`` — SQLAlchemy's wrapper attribute. ``DBAPIError.orig`` is the
      raw driver exception and is where the SQLSTATE actually lives.
    * ``.__cause__`` — an explicit ``raise ... from ...``.
    * ``.__context__`` — an implicit re-raise inside an ``except`` block, which
      is how several of our own helpers re-shape driver errors.

    Visited identities are tracked because ``__context__`` chains can loop.
    """
    seen: set[int] = set()
    stack: list[tuple[BaseException, int]] = [(exc, 0)]
    while stack:
        current, depth = stack.pop()
        if current is None or depth > _MAX_CHAIN_DEPTH:
            continue
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for attr in ("orig", "__cause__", "__context__"):
            nxt = getattr(current, attr, None)
            if isinstance(nxt, BaseException):
                stack.append((nxt, depth + 1))


def is_query_canceled(exc: BaseException) -> bool:
    """True only when Postgres cancelled the statement (SQLSTATE 57014).

    Returns False for every other database error and for every non-database
    error, including ``asyncio.CancelledError``. Callers use it to degrade a
    read the same way they degrade their own wall clock, while letting real
    bugs keep propagating to a 500 where they are visible.
    """
    import asyncio

    # Asked about a cancellation directly, the answer is no — whatever is in
    # its cause chain. asyncpg cancels the running statement when its task is
    # cancelled, so a ``CancelledError`` very often DOES carry a 57014 in
    # ``__context__``; reading that as "the database timed out" would turn
    # structured cancellation into a degraded 200.
    if isinstance(exc, asyncio.CancelledError):
        return False

    for candidate in _chain(exc):
        for attr in ("sqlstate", "pgcode"):
            if getattr(candidate, attr, None) == QUERY_CANCELED_SQLSTATE:
                return True
        if type(candidate).__name__ == QUERY_CANCELED_CLASS_NAME:
            return True
    return False
