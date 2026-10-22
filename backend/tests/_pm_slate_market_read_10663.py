"""#10663 — what a database returns for the Polymarket slate's market read.

Slate fixtures describe STORED market rows,
``(market_id, external_id, market_metadata, event_status)``. Since #10663 the
slate's market read selects four ``market_metadata`` keys rather than the
whole blob, so a fake that hands back the stored tuple no longer answers the
statement it was asked.

``answer_slate_market_read`` answers the columns the statement ACTUALLY
selects, read off the statement itself — never off the production key list —
so a key dropped from the read is dropped from the answer too, and the parent's
bare-blob read is answered unchanged. A JSONB subscript of an absent key, or
of a blob that is not an object, is SQL NULL (PostgreSQL ``jsonb['key']``),
which is ``None`` here. Any other statement gets its rows back untouched.
"""

from sqlalchemy.sql import operators


def _slate_market_columns(stmt):
    """``[getter, ...]`` for the slate market read, else ``None``."""
    columns = list(getattr(stmt, "selected_columns", None) or ())
    if len(columns) < 4:
        return None

    def named(column, table, name):
        return (
            getattr(getattr(column, "table", None), "name", None) == table
            and getattr(column, "name", None) == name
        )

    first, second, *middle, last = columns
    if not (
        named(first, "futures_markets", "id")
        and named(second, "futures_markets", "external_id")
        and named(last, "events", "status")
    ):
        return None
    getters = [lambda row: row[0], lambda row: row[1]]
    for column in middle:
        if named(column, "futures_markets", "market_metadata"):
            getters.append(lambda row: row[2])
        elif getattr(column, "operator", None) is operators.json_getitem_op and named(
            column.left, "futures_markets", "market_metadata"
        ):
            key = column.right.value
            getters.append(
                lambda row, key=key: row[2].get(key)
                if isinstance(row[2], dict)
                else None
            )
        else:
            return None
    getters.append(lambda row: row[3])
    return getters


def is_slate_market_read(stmt) -> bool:
    return _slate_market_columns(stmt) is not None


def answer_slate_market_read(stmt, stored_rows):
    """The rows ``stmt`` returns over these stored market rows."""
    getters = _slate_market_columns(stmt)
    if getters is None:
        return stored_rows
    return [tuple(get(row) for get in getters) for row in stored_rows]
