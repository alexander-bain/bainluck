"""#11138 — `HeldRowQuotes`: a held price row's received quote, and only a newer one.

The real-PostgreSQL flush/stamp/restart/release behaviour is
`tests/integration/test_pm_held_price_row_stamps_received_quote_11138_pg.py`;
these are the pure rules it relies on.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.tasks.live_blend_refresh import HeldRowQuotes, LiveBlendRefresher
from app.utils.aggregation import observation_basis

T = datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)


def row(oid=1, price=0.6, at=T):
    return SimpleNamespace(id=oid, current_probability=price, last_updated=at)


def test_hold_reports_only_changed_quotes_at_stored_precision():
    held = HeldRowQuotes()
    seen = (T + timedelta(seconds=1)).timestamp()
    assert held.hold({1: (0.8200000004, seen), 2: (0.18, seen)}) == {1, 2}
    assert held.hold({1: (0.82, seen), 2: (0.18, seen)}) == set()
    assert held.hold({1: (0.84, seen + 1)}) == {1}
    r = row()
    held.overlay(r)
    assert r.current_probability == 0.84


def test_overlay_replaces_only_an_older_stored_row_and_dates_it_by_receipt():
    held = HeldRowQuotes()
    seen = (T + timedelta(seconds=2)).timestamp()
    held.hold({1: (0.82, seen)})
    older, newer, undated, other = (
        row(), row(price=0.7, at=T + timedelta(seconds=3)), row(at=None), row(oid=2)
    )
    for r in (older, newer, undated, other):
        held.overlay(r)
    assert (older.current_probability, older.last_updated.timestamp()) == (0.82, seen)
    assert (newer.current_probability, newer.last_updated) == (0.7, T + timedelta(seconds=3))
    assert undated.current_probability == 0.82
    assert (other.current_probability, other.last_updated) == (0.6, T)
    # The stamp's per-row basis is the receive time: a later stamp built from
    # the still-held row (basis T) is older and `observation_admits_clause`
    # refuses it.
    assert observation_basis([older])["1"] == seen > observation_basis([row()])["1"]


def test_release_and_withdrawal_end_the_overlay():
    held = HeldRowQuotes()
    held.hold({1: (0.82, T.timestamp() + 5), 2: (0.18, T.timestamp() + 5)})
    held.release(iter([1]))
    assert 1 not in held and 2 in held
    r = row()
    held.overlay(r)
    assert r.current_probability == 0.6


def test_refresher_reads_no_overlay_unless_its_consumer_installs_one():
    assert LiveBlendRefresher("kalshi").held_quotes is None
    source = (
        Path(__file__).resolve().parents[1] / "app/tasks/polymarket_ws.py"
    ).read_text()
    assert source.count("blend_refresher.held_quotes = HeldRowQuotes()") == 1
