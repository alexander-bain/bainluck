"""#12042: Phase 2 loads only the columns its scalar copy keeps.

Measured on worker-heavy (Nov 9, 22:13Z, #12481's mark): the matcher sat at
212 MB after `relink_and_reconcile` and 612 MB right after Phase 2's
`select(FuturesMarket, Event).all()`; the loop after it added 3 MB. The load
held 22,328 whole ORM pairs, and `_LinkedMarketRef` copies eleven fields from
each. A 495-row sample put the decoded `market_metadata` dicts at ~108 MB for
the full set, so most of the climb was ORM state for columns never read.
"""
import inspect
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql

from app.tasks import prediction_market_matching as pmm

NOW = datetime(2025, 6, 15, 22, 0, tzinfo=timezone.utc)

#: What `_LinkedMarketRef` is built from — the whole select, in order.
COLUMNS = [
    "market_id",
    "source",
    "external_id",
    "name",
    "status",
    "market_metadata",
    "event_id",
    "event_commence_time",
    "home_team_name",
    "away_team_name",
    "event_completed_at",
]

Row = namedtuple("Row", COLUMNS)


def _sql() -> str:
    stmt = pmm._phase2_linked_select(NOW)
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_the_load_selects_exactly_the_copied_columns():
    stmt = pmm._phase2_linked_select(NOW)
    assert [c["name"] for c in stmt.column_descriptions] == COLUMNS


def test_the_load_reads_no_whole_rows():
    sql = _sql()
    # Columns of either table that the scalar copy never reads.
    for unread in ("market_tags", "group_id", "volume_updated_at", "win_probability_sources",
                   "box_score_data", "event_tags"):
        assert unread not in sql, unread


def test_the_population_is_unchanged():
    sql = _sql()
    assert "futures_markets.source IN ('kalshi', 'polymarket')" in sql
    assert "futures_markets.event_id IS NOT NULL" in sql
    assert "events.status IN ('scheduled', 'live')" in sql
    assert "events.status IN ('completed', 'closed')" in sql
    assert f"events.commence_time >= '{(NOW - timedelta(hours=24)).isoformat(sep=' ')}'" in sql


def _row(**over):
    base = dict(
        market_id=7, source="kalshi", external_id="KXNBAGAME-25JUN15LALATL-LAL", name="Lakers at Hawks",
        status="open", market_metadata={"content_understanding_v1": {"semantic_type": "game_winner"}},
        event_id=15344868, event_commence_time=NOW, home_team_name="Atlanta Hawks",
        away_team_name="Los Angeles Lakers", event_completed_at=None,
    )
    base.update(over)
    return Row(**base)


def test_a_row_becomes_the_same_scalar_copy():
    row = _row()
    ref = pmm._linked_ref_from_row(row)
    assert (ref.market_id, ref.source, ref.external_id, ref.name, ref.status) == (
        7, "kalshi", "KXNBAGAME-25JUN15LALATL-LAL", "Lakers at Hawks", "open")
    assert (ref.event_id, ref.event_commence_time, ref.home_team_name, ref.away_team_name) == (
        15344868, NOW, "Atlanta Hawks", "Los Angeles Lakers")
    # #9348: the venue's own label still reaches the blend gate.
    assert ref.market_metadata is row.market_metadata
    assert ref.id == 7


def test_event_has_result_reads_the_events_completed_at():
    assert pmm._linked_ref_from_row(_row(event_completed_at=None)).event_has_result is False
    assert pmm._linked_ref_from_row(_row(event_completed_at=NOW)).event_has_result is True


def test_phase2_uses_the_narrow_load_once():
    src = inspect.getsource(pmm._match_prediction_markets)
    assert src.count("_phase2_linked_select(now)") == 1
    assert "linked_refs = [_linked_ref_from_row(row) for row in linked_rows]" in src
    load = src.index("_phase2_linked_select(now)")
    assert src.index('_mem(stats, "phase2_load")') > load
