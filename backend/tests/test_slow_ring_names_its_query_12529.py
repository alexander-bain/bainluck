"""#12529: the slow-event ring names the slowest query, not just its duration.

The ring (`/api/admin/latency-slow-events`, every request >= 5 s) could say a
`/api/events/{id}/related-futures` read spent 18.8 s in ONE statement (Nov 10)
but never which statement, and `related-futures` and `history` record no stages.
The request's DB accumulator now keeps the first 160 characters of its slowest
statement, and the slow event carries it. It never reaches a response header.
"""
import json

from sqlalchemy import create_engine, text

from app.utils import request_timing as rt
from app.utils.latency_stats import build_slow_event


def _acc():
    token = rt.begin_db_timing()
    return token, rt.current_db_timing()


def test_the_slowest_statement_is_kept_with_its_duration():
    token, acc = _acc()
    try:
        rt.record_query(12.0, statement="SELECT 1")
        rt.record_query(18831.3, statement="SELECT futures_markets.id,\n   futures_markets.name FROM futures_markets WHERE x = $1")
        rt.record_query(40.0, statement="SELECT 2")
        assert acc.max_query_ms == 18831.3
        assert acc.max_query_sql == "SELECT futures_markets.id, futures_markets.name FROM futures_markets WHERE x = $1"
    finally:
        rt.end_db_timing(token)


def test_long_statements_are_capped():
    assert len(rt.sql_head("SELECT " + "a, " * 400 + "b FROM t")) == rt.MAX_QUERY_SQL_CHARS
    assert rt.sql_head(None) is None and rt.sql_head("   ") is None


def test_the_engine_listener_passes_the_statement():
    token, acc = _acc()
    try:
        engine = create_engine("sqlite://")
        rt.install_request_db_timer(engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 42 AS answer"))
        assert acc.max_query_sql == "SELECT 42 AS answer"
    finally:
        rt.end_db_timing(token)


def test_it_reaches_the_slow_event_but_never_the_response_header():
    db = rt.DbTiming()
    db.record(7004.4, "SELECT win_prob_snapshots.id FROM win_prob_snapshots WHERE event_id = $1")
    split = rt.build_split(wall_ms=13280.8, db=db, router_ms=5.9)
    assert "SELECT" not in rt.format_split_header(split)
    event = json.loads(build_slow_event(
        timestamp=1.0, path="/api/events/{event_id}/history", duration_ms=13280.8,
        cache_bucket="miss", stages=None, rss_mb=None, split=split))
    assert event["max_query_sql"].startswith("SELECT win_prob_snapshots.id FROM win_prob_snapshots")
    assert event["max_query_ms"] == 7004.4


def test_a_request_without_queries_adds_nothing():
    split = rt.build_split(wall_ms=10.0, db=rt.DbTiming(), router_ms=None)
    assert "max_query_sql" not in split
