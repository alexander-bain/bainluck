"""#11254 — the feed's snapshot fallback runs the withdrawal-aware statement.

The real-Postgres gate (``tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py``)
proves what ``SNAPSHOT_FALLBACK_SQL`` returns, but it skips without a server and
cannot see the call site. This file needs no server: it checks that
``routes/feed.py`` executes that statement and that the old inline one, which
skipped the withdrawal row and served the retired price, is gone.
"""

import ast
from pathlib import Path

FEED = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"


def _feed_tree():
    return ast.parse(FEED.read_text())


def test_feed_executes_the_withdrawal_aware_statement():
    calls = [
        node
        for node in ast.walk(_feed_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "text"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "SNAPSHOT_FALLBACK_SQL"
    ]
    assert len(calls) == 1


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
