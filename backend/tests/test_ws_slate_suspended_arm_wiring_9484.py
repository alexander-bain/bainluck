"""#9484 — the suspended-market arm is WIRED into both venue sockets' slates.

The real-Postgres contract (``integration/test_ws_slate_suspended_open_market_pg_9484.py``)
reads each venue's slate predicate function, not the consumer's call site, so
a consumer that stopped calling the function would leave it green while the
socket dropped suspended matches again. These run without a database.
"""

import ast
import inspect

from sqlalchemy.dialects import postgresql


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _where_call_names(module) -> set:
    """Every bare-name call passed directly to any `.where(...)` in `module`."""
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "where"
        ):
            names |= {
                a.func.id
                for a in node.args
                if isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
            }
    return names


def test_the_kalshi_consumer_subscribes_through_its_slate_window():
    from app.tasks import kalshi_ws

    assert "_kalshi_slate_event_window" in _where_call_names(kalshi_ws)


def test_the_polymarket_consumer_subscribes_through_its_slate_window():
    from app.tasks import polymarket_ws

    assert "_slate_event_window" in _where_call_names(polymarket_ws)


def test_both_slate_windows_carry_the_suspended_open_market_arm():
    from app.tasks.kalshi_ws import _kalshi_slate_event_window
    from app.tasks.polymarket_ws import _slate_event_window
    from app.tasks.ws_slate import suspended_open_market_arm

    arm = _sql(suspended_open_market_arm())
    assert "events.status = 'suspended'" in arm
    assert "NOW() - INTERVAL '24 hours'" in arm
    assert "futures_markets.status IS NULL" in arm
    assert "futures_markets.status != 'resolved'" in arm

    for window in (_kalshi_slate_event_window(), _slate_event_window()):
        sql = _sql(window)
        assert arm in sql
        # The live and scheduled arms are untouched beside it.
        assert "events.status = 'live'" in sql
        assert "events.status = 'scheduled'" in sql

