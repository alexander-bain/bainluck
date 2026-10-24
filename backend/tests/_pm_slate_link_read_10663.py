"""#10663 — what a database returns for the Polymarket slate's LINK read.

The link read is the slate's first query: every linked, in-window Polymarket
market that has an outcome, with its event. Slate fixtures describe it as the
parent's OUTCOME-level rows,
``(outcome_id, market_id, outcome_external_id, market_external_id, event_id)``.
Since #10663 the read selects only ``(market_id, linked_event_id)`` with
``DISTINCT`` — the three other columns fed a map nothing read — so a fake that
hands back the stored tuple no longer answers the statement it was asked.

``answer_slate_link_read`` answers the columns the statement ACTUALLY selects,
read off the statement itself, and applies its ``DISTINCT`` the way PostgreSQL
does (whole-row equality; first-seen order kept here, which a database does not
promise and the loader does not need). The parent's five-column read is answered
unchanged, so one fixture feeds both trees. Any other statement gets its rows
back untouched.
"""

#: (table, column) -> index in the stored outcome-level tuple. The inner join
#: makes ``futures_markets.id`` equal to ``futures_outcomes.market_id``.
_STORED_INDEX = {
    ("futures_outcomes", "id"): 0,
    ("futures_outcomes", "market_id"): 1,
    ("futures_markets", "id"): 1,
    ("futures_outcomes", "external_id"): 2,
    ("futures_markets", "external_id"): 3,
    ("futures_markets", "event_id"): 4,
}


def _slate_link_indexes(stmt):
    """``[stored index, ...]`` for the slate link read, else ``None``."""
    columns = list(getattr(stmt, "selected_columns", None) or ())
    if not any(getattr(c, "name", None) == "linked_event_id" for c in columns):
        return None
    indexes = []
    for column in columns:
        base = getattr(column, "element", column)
        key = (getattr(getattr(base, "table", None), "name", None),
               getattr(base, "name", None))
        if key not in _STORED_INDEX:
            raise AssertionError(f"slate link read selects an unknown column {key}")
        indexes.append(_STORED_INDEX[key])
    return indexes


def is_slate_link_read(stmt) -> bool:
    return _slate_link_indexes(stmt) is not None


def answer_slate_link_read(stmt, stored_rows):
    """The rows ``stmt`` returns over these stored outcome-level rows."""
    indexes = _slate_link_indexes(stmt)
    if indexes is None:
        return stored_rows
    rows = [tuple(row[i] for i in indexes) for row in stored_rows]
    if getattr(stmt, "_distinct", False):
        rows = list(dict.fromkeys(rows))
    return rows


def parent_slate_link_stmt(*, stored_live_only=False):
    """The parent's link read, frozen: five columns per OUTCOME, no DISTINCT.

    Written out rather than imported so the reference cannot move with the
    shipped read; the joins and filters are the shipped module's own functions,
    so a filter change moves both sides together."""
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    from app.tasks.polymarket_ws import _slate_event_window, _slate_market_filter

    return (
        select(
            FuturesOutcome.id,
            FuturesOutcome.market_id,
            FuturesOutcome.external_id,
            FuturesMarket.external_id.label("market_ext_id"),
            FuturesMarket.event_id.label("linked_event_id"),
        )
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(
            FuturesMarket.source == "polymarket",
            FuturesMarket.event_id.isnot(None),
            _slate_event_window(),
            _slate_market_filter(),
            *([Event.status.in_(("live", "suspended"))] if stored_live_only else []),
        )
    )


class _Captured(Exception):
    pass


async def shipped_slate_link_stmt(*, stored_live_only=False):
    """The link read the REAL nested ``load_game_slate`` issues first.

    The loader is compiled out of ``_run_polymarket_ws_consumer`` as the other
    slate tests do; its session records the first statement and stops it."""
    import ast
    import inspect
    import textwrap
    from contextlib import asynccontextmanager

    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome
    import app.tasks.polymarket_ws as ws

    captured = []

    class Session:
        async def execute(self, stmt, *args, **kwargs):
            captured.append(stmt)
            raise _Captured

    @asynccontextmanager
    async def context(**kwargs):
        yield Session()

    source = ast.parse(textwrap.dedent(inspect.getsource(ws._run_polymarket_ws_consumer)))
    loader = next(
        n for n in source.body[0].body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "load_game_slate"
    )
    namespace = dict(
        vars(ws), select=select, Event=Event, FuturesMarket=FuturesMarket,
        FuturesOutcome=FuturesOutcome, get_task_session=context,
    )
    exec(compile(ast.Module(body=[loader], type_ignores=[]), "pm_slate_link", "exec"),
         namespace)

    try:
        await namespace["load_game_slate"](stored_live_only=stored_live_only)
    except _Captured:
        pass
    assert len(captured) == 1, captured
    return captured[0]
