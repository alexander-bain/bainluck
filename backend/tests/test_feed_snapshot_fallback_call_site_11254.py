"""#11254 — the feed's snapshot fallback runs the withdrawal-aware statement.

The real-Postgres gate (``tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py``)
proves what ``SNAPSHOT_FALLBACK_SQL`` returns, but it skips without a server and
cannot see the call site. This file needs no server: it checks that
``routes/feed.py`` executes that statement and that the old inline one, which
skipped the withdrawal row and served the retired price, is gone.

#1459: the feed now reads through ``read_snapshot_fallbacks`` (recent window
first, then the unchanged statement for the rest), so the statement is executed
there and the pass-1 statement is pinned to differ from it ONLY by its two
window bounds.
"""

import ast
from pathlib import Path

FEED = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"


def _feed_tree():
    return ast.parse(FEED.read_text())


FALLBACK = FEED.parents[1] / "utils" / "feed_snapshot_fallback.py"


def _text_calls(tree, name):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "text"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == name
    ]


def test_feed_reads_the_fallback_through_the_two_pass_reader_at_the_request_clock():
    calls = [
        node
        for node in ast.walk(_feed_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "read_snapshot_fallbacks"
    ]
    assert len(calls) == 1
    [call] = calls
    assert [k.arg for k in call.keywords] == ["now"]
    assert isinstance(call.keywords[0].value, ast.Name)
    assert call.keywords[0].value.id == "now"
    # Nothing in the route runs either statement around the reader.
    assert _text_calls(_feed_tree(), "SNAPSHOT_FALLBACK_SQL") == []
    assert _text_calls(_feed_tree(), "SNAPSHOT_FALLBACK_RECENT_SQL") == []


def test_the_reader_executes_the_withdrawal_aware_statement_and_its_window():
    tree = ast.parse(FALLBACK.read_text())
    assert len(_text_calls(tree, "SNAPSHOT_FALLBACK_SQL")) == 1
    assert len(_text_calls(tree, "SNAPSHOT_FALLBACK_RECENT_SQL")) == 1


def test_pass_one_is_the_statement_plus_exactly_its_two_window_bounds():
    from app.utils.feed_snapshot_fallback import (
        SNAPSHOT_FALLBACK_RECENT_SQL,
        SNAPSHOT_FALLBACK_SQL,
    )

    cte_bound = "          AND captured_at >= :since\n"
    main_bound = "      AND s.captured_at >= :since\n"
    assert SNAPSHOT_FALLBACK_RECENT_SQL.count(cte_bound) == 1
    assert SNAPSHOT_FALLBACK_RECENT_SQL.count(main_bound) == 1
    assert (
        SNAPSHOT_FALLBACK_RECENT_SQL.replace(cte_bound, "").replace(main_bound, "")
        == SNAPSHOT_FALLBACK_SQL
    )


def test_the_old_inline_fallback_statement_is_gone():
    inline = [
        node.value
        for node in ast.walk(_feed_tree())
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "DISTINCT ON (event_id) event_id, home_win_probability" in node.value
    ]
    assert inline == []


def test_the_statement_reads_the_marker_as_json_true():
    from app.utils.feed_snapshot_fallback import SNAPSHOT_FALLBACK_SQL

    assert "-> 'live_source_withdrawal' = CAST('true' AS jsonb)" in SNAPSHOT_FALLBACK_SQL
    assert "home_win_probability IS NULL" in SNAPSHOT_FALLBACK_SQL
