"""#10689: extract the actual consuming expression and model the proposed edit.

The original price expression is pinned as a test oracle. Tests lift the
consuming counter loop and transaction flow; only price execute arguments are
replaced.

#10693: the consumer no longer executes the price statement itself — it hands
each phase to the run's price pipeline (`utils/kalshi_price_pipeline.py`),
whose ordinary path is that same per-row execute. So the #10689 closure these
oracles lift is now the FROZEN pre-#10693 one
(`fixtures/kalshi_flush_before_10693.py.txt`), and the current-source pin
follows the execute to where it lives: the consumer's `prices.phase(...)` call
and the pipeline's per-row `session.execute`.
"""

import ast
import inspect
from pathlib import Path

from sqlalchemy import func, or_, update
from sqlalchemy.dialects.postgresql.asyncpg import dialect

from app.models.models import FuturesOutcome
from app.tasks import kalshi_ws
from app.utils import kalshi_price_pipeline
from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES


FROZEN_FLUSH = Path(__file__).parent / "fixtures/kalshi_flush_before_10693.py.txt"


def flush_ast():
    """The consumer's CURRENT `flush_prices`."""
    tree = ast.parse(inspect.getsource(kalshi_ws._run_kalshi_ws_consumer))
    return next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "flush_prices"
    )


def frozen_flush_ast():
    """FROZEN: `flush_prices` at 2cafa8f56a, the closure #10689 shipped into."""
    return ast.parse(FROZEN_FLUSH.read_text()).body[0]


def pipeline_handoff(node):
    """The flush's `async with aclosing(prices.phase(session, phase))` block."""
    return next(
        n
        for n in ast.walk(node)
        if isinstance(n, ast.AsyncWith)
        and ast.unparse(n.items[0].context_expr)
        == "contextlib.aclosing(prices.phase(session, phase))"
    )


def pipeline_price_execute():
    """The pipeline's ordinary per-row `session.execute` (its singleton path)."""
    tree = ast.parse(inspect.getsource(kalshi_price_pipeline.KalshiPricePipeline))
    iter_phase = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "iter_phase"
    )
    (call,) = [
        n.value
        for n in ast.walk(iter_phase)
        if isinstance(n, ast.Await)
        and isinstance(n.value, ast.Call)
        and ast.unparse(n.value.func) == "session.execute"
    ]
    return call


def price_execute(node):
    loop = next(
        n
        for n in ast.walk(node)
        if isinstance(n, ast.For)
        and ast.unparse(n.target) == "(outcome_id, (prob, yes_bid, yes_ask))"
    )
    return next(
        n.value
        for n in ast.walk(loop)
        if isinstance(n, ast.Await)
        and isinstance(n.value, ast.Call)
        and ast.unparse(n.value.func) == "session.execute"
    )


def baseline_expression():
    fixture = (
        Path(__file__).parent / "fixtures/kalshi_price_expression_before_10689.py.txt"
    )
    return ast.parse(fixture.read_text()).body[0].value


def consuming_arguments():
    return [
        ast.parse("KALSHI_PRICE_STATEMENTS[tick_has_book]", mode="eval").body,
        ast.parse(
            "kalshi_price_parameters(outcome_id, prob, yes_bid, yes_ask)", mode="eval"
        ).body,
    ]


def pipeline_arguments():
    """`consuming_arguments`, in the pipeline's spelling of the same row."""
    return [
        ast.parse("KALSHI_PRICE_STATEMENTS[book]", mode="eval").body,
        ast.parse("kalshi_price_parameters(oid, *values)", mode="eval").body,
    ]


def assert_known_source_price_arguments():
    # The frozen closure carries the #10689 arguments (its own fixture; checked
    # so a damaged fixture cannot silently feed every oracle below).
    call = price_execute(frozen_flush_ast())
    frozen = ast.dump(ast.List(elts=call.args, ctx=ast.Load()))
    hoisted = ast.dump(ast.List(elts=consuming_arguments(), ctx=ast.Load()))
    assert frozen == hoisted, "frozen pre-#10693 flush fixture changed"
    # #10693: the current consumer writes through the pipeline, and the
    # pipeline's per-row execute binds the same template and the same values.
    pipeline_handoff(flush_ast())
    source = ast.dump(ast.List(elts=pipeline_price_execute().args, ctx=ast.Load()))
    expected = ast.dump(ast.List(elts=pipeline_arguments(), ctx=ast.Load()))
    assert source == expected, "writer price expression changed; review the pinned oracle"


def original_statement(outcome_id, probability, yes_bid, yes_ask):
    assert_known_source_price_arguments()
    ns = dict(
        update=update,
        func=func,
        or_=or_,
        FuturesOutcome=FuturesOutcome,
        AUTHORITATIVE_SOURCES=AUTHORITATIVE_SOURCES,
        price_changed_at_value=price_changed_at_value,
        quote_moved_column=quote_moved_column,
        outcome_id=outcome_id,
        prob=probability,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        tick_has_book=yes_bid is not None and yes_ask is not None,
    )
    return eval(
        compile(ast.Expression(body=baseline_expression()), kalshi_ws.__file__, "eval"),
        ns,
    )


def consuming_flush(candidate):
    """The FROZEN pre-#10693 closure with baseline or #10689 price arguments."""
    assert_known_source_price_arguments()
    node = frozen_flush_ast()
    call = price_execute(node)
    call.args = consuming_arguments() if candidate else [baseline_expression()]
    return ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))


def compiled_signature(statement, parameters=None):
    compiled = statement.compile(dialect=dialect())
    expanded = compiled.construct_expanded_state(parameters or {})
    origins = {
        new: old for old, news in expanded.parameter_expansion.items() for new in news
    }
    types = [
        (
            type(compiled.binds[origins.get(key, key)].type).__name__,
            str(compiled.binds[origins.get(key, key)].type),
        )
        for key in expanded.positiontup
    ]
    values = [
        (
            expanded.processors[key](expanded.parameters[key])
            if key in expanded.processors
            else expanded.parameters[key]
        )
        for key in expanded.positiontup
    ]
    return expanded.statement, types, values
