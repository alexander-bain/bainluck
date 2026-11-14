"""A book/trade rule switch is not a mover, an email item or a push alert."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY, reader_change_24h


def _metadata(basis, *, oid=7, hours=18):
    if basis is None:
        return {}
    stamp = datetime.now(timezone.utc) - timedelta(hours=hours)
    return {DATED_BASIS_METADATA_KEY: {str(oid): [basis, stamp.isoformat()]}}


def _outcome(basis=None, *, source="polymarket", stored=-0.56, hours=18):
    market = SimpleNamespace(source=source, name="Colts Win Total",
                             market_metadata=_metadata(basis, hours=hours))
    return SimpleNamespace(id=7, name="6.5+ Wins", market_id=59567948, market=market,
                           current_probability=0.15, probability_change_24h=stored,
                           current_american_odds=567, rank=1, rank_change_24h=0)


@pytest.mark.parametrize("basis,hours,expected", [
    (None, 18, None), (0.15, 18, 0), (0.12, 18, 0.03),
    (0.12, 25, None), (0.12, 11, None),
])
def test_raw_minus_56_points_needs_a_dated_quote_basis(basis, hours, expected):
    row = _outcome(basis, hours=hours)
    value = reader_change_24h(row.market, row.id, row.current_probability,
                             row.probability_change_24h)
    assert value == (None if expected is None else pytest.approx(expected))


def test_public_movers_omit_unknown_and_flat_moves_but_keep_dated_and_other_sources():
    from app.routes.futures import _movers_payload

    rows = [_outcome(), _outcome(0.15), _outcome(0.12), _outcome(source="kalshi")]
    payload = _movers_payload(rows, 24)
    assert payload["timeframe_hours"] == 24
    assert [r["probability_change_24h"] for r in payload["movers"]] == pytest.approx([0.03, -0.56])


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _DB:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    async def execute(self, statement):
        self.calls.append(statement)
        return _Result(next(self.replies))


async def test_daily_email_uses_dated_moves_without_sending_an_email():
    from app.tasks.daily_digest import build_digest_content

    rows = [_outcome(), _outcome(0.15), _outcome(0.12), _outcome(source="kalshi")]
    digest_rows = [SimpleNamespace(
        name=row.name, current_probability=row.current_probability,
        probability_change_24h=row.probability_change_24h, market_name=row.market.name,
        source=row.market.source, outcome_id=row.id, market_metadata=row.market.market_metadata,
    ) for row in rows]
    db = _DB([digest_rows, []])
    content = await build_digest_content(db)
    assert [r["change"] for r in content["movers"]] == pytest.approx([0.03, -0.56])
    assert len(db.calls) == 2


@pytest.mark.parametrize("basis,source,expected", [
    (None, "polymarket", 0), (0.15, "polymarket", 0),
    (0.12, "polymarket", 0), (0.40, "polymarket", 1),
    (None, "kalshi", 1),
])
async def test_big_move_alert_requires_the_dated_move_to_clear_its_threshold(
    monkeypatch, basis, source, expected,
):
    from app.tasks.push_notifications import _send_big_move_alerts

    row = _outcome(basis, source=source)
    nominee = (row.market_id, row.market.name, row.name, row.probability_change_24h,
               row.current_probability, row.id, source, row.market.market_metadata)
    # No pinned user: a valid nominee reaches the pin lookup, without any send.
    db = _DB([[], [nominee], []])

    @asynccontextmanager
    async def fake_session():
        yield db

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
    result = await _send_big_move_alerts()
    assert result["markets_checked"] == expected
    assert result["sent"] == 0
    assert len(db.calls) == 2 + expected
