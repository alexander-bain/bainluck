"""#10689: bind reuse must preserve the actual writer's SQL, types and values."""

import ast
from pathlib import Path

import pytest
from sqlalchemy import cast, literal, or_, select

from app.models.models import FuturesOutcome
from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)
from app.utils.price_change_stamp import quote_moved_column
from tests.kalshi_price_statement_support import (
    assert_known_source_price_arguments,
    compiled_signature,
    consuming_flush,
    original_statement,
    price_execute,
)

CASES = [
    (0.3, 0.2, 0.4),
    (0.30000001, 0.20001, 0.40001),
    (0.0512345678, 0.123456, 0.123457),
    (0.0, 0.0, 0.0),
    (1.0, 1.0, 1.0),
    (0.3, 0.3, 0.3),
    (0.7, None, None),
    (0.3, None, 0.9),
    (0.3, 0.8, None),
    (0.30000001, None, None),
]


def _old_scalar_quote_helper():
    fixture = Path(__file__).parent / "fixtures/kalshi_quote_helper_before_10689.py.txt"
    ns = dict(Any=object, select=select, or_=or_, cast=cast, literal=literal)
    exec(compile(fixture.read_text(), str(fixture), "exec"), ns)
    return ns["quote_moved_column"]


@pytest.mark.parametrize("probability,bid,ask", CASES)
def test_exact_actual_writer_sql_positional_types_and_processed_values(
    probability, bid, ask
):
    complete = bid is not None and ask is not None
    original = original_statement(17, probability, bid, ask)
    candidate = KALSHI_PRICE_STATEMENTS[complete]._generate()
    # The reviewed repeat predicate is covered by direct admission controls;
    # storage, returning expressions and bind precision remain exactly pinned.
    assert len(candidate._where_criteria) == 3
    candidate._where_criteria = candidate._where_criteria[:-1]
    parameters = kalshi_price_parameters(17, probability, bid, ask)
    assert compiled_signature(original) == compiled_signature(candidate, parameters)


def test_only_execute_arguments_change_in_the_consuming_closure():
    original, candidate = consuming_flush(False), consuming_flush(True)
    price_execute(candidate).args = price_execute(original).args
    assert ast.dump(candidate) == ast.dump(original)


def test_templates_are_reused_and_values_do_not_mutate_them():
    for complete in (False, True):
        statement = KALSHI_PRICE_STATEMENTS[complete]
        before = statement.compile().params
        first = kalshi_price_parameters(1, 0.3, 0.2, 0.4)
        second = kalshi_price_parameters(2, 0.7, None, None)
        assert first is not second
        assert statement is KALSHI_PRICE_STATEMENTS[complete]
        assert statement.compile().params == before
    with pytest.raises(TypeError):
        KALSHI_PRICE_STATEMENTS[False] = KALSHI_PRICE_STATEMENTS[True]


@pytest.mark.parametrize(
    "book", [None, (0.2, 0.4), (0.123456, 0.123457), (0.0, 1.0), (None, None)]
)
def test_scalar_quote_helper_is_exactly_the_predecessor(book):
    table = FuturesOutcome.__table__
    expected = select(_old_scalar_quote_helper()(table, book))
    actual = select(quote_moved_column(table, book))
    assert compiled_signature(actual) == compiled_signature(expected)


def test_current_source_uses_only_the_frozen_expression_or_reviewed_consuming_arguments():
    assert_known_source_price_arguments()
