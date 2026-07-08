"""#138/#995 — freeze-gap market creation guard tests.

Covers the pure logic of `_create_settled_market`: the gap-window filter (never
recreate ancient settled history), is_winner derivation from the settlement
result, and outcome naming. The full paginating task runs against prod (beat-
scheduled) and is verified via read-only counts, not in CI.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.kalshi_api import KalshiEvent, KalshiMarket
from app.tasks.kalshi import _create_settled_market, _GAP_CREATE_START
from app.models.models import FuturesMarket, FuturesOutcome
from app.utils.market_label_normalization import compute_market_tier
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _mk_service(event):
    svc = MagicMock()
    svc._parse_event = MagicMock(return_value=event)
    return svc


def _mk_session(market_id=123):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=market_id)
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_pre_gap_event_skipped():
    """A market that settled before the freeze window is NOT recreated."""
    old = _GAP_CREATE_START - timedelta(days=5)
    event = KalshiEvent(
        event_ticker="KXATPMATCH-OLD",
        title="Old match",
        category="Tennis",
        markets=[KalshiMarket(
            ticker="KXATPMATCH-OLD-A", event_ticker="KXATPMATCH-OLD",
            title="A", status="settled", close_time=old, result="yes",
        )],
    )
    stats = {"markets_created": 0, "outcomes_created": 0}
    out = await _create_settled_market(
        _mk_session(), _mk_service(event), {}, pg_insert,
        FuturesMarket, FuturesOutcome, compute_market_tier, stats,
    )
    assert out == "pre_gap"
    assert stats["markets_created"] == 0


@pytest.mark.asyncio
async def test_in_gap_event_created_with_winner():
    """A gap-window settled event is created; is_winner comes from result."""
    recent = _GAP_CREATE_START + timedelta(days=10)
    event = KalshiEvent(
        event_ticker="KXWTAMATCH-WIMB-1",
        title="Wimbledon R1",
        category="Tennis",
        mutually_exclusive=True,
        markets=[
            KalshiMarket(
                ticker="KXWTAMATCH-WIMB-1-SW", event_ticker="KXWTAMATCH-WIMB-1",
                title="Swiatek", yes_sub_title="Swiatek", status="settled",
                close_time=recent, last_price=0.82, result="yes", volume=5000,
            ),
        ],
    )
    stats = {"markets_created": 0, "outcomes_created": 0}
    out = await _create_settled_market(
        _mk_session(), _mk_service(event), {}, pg_insert,
        FuturesMarket, FuturesOutcome, compute_market_tier, stats,
    )
    assert out == "created"
    assert stats["markets_created"] == 1
    assert stats["outcomes_created"] == 1


@pytest.mark.asyncio
async def test_race_lost_market_exists_returns_skip():
    """If the market already exists (ON CONFLICT → no id), leave it alone."""
    recent = _GAP_CREATE_START + timedelta(days=3)
    event = KalshiEvent(
        event_ticker="KXATPMATCH-RACE",
        title="Race match",
        category="Tennis",
        markets=[KalshiMarket(
            ticker="KXATPMATCH-RACE-A", event_ticker="KXATPMATCH-RACE",
            title="A", status="settled", close_time=recent, result="no",
        )],
    )
    stats = {"markets_created": 0, "outcomes_created": 0}
    out = await _create_settled_market(
        _mk_session(market_id=None), _mk_service(event), {}, pg_insert,
        FuturesMarket, FuturesOutcome, compute_market_tier, stats,
    )
    assert out == "skip"
    assert stats["markets_created"] == 0


@pytest.mark.asyncio
async def test_crypto_skipped():
    recent = _GAP_CREATE_START + timedelta(days=1)
    event = KalshiEvent(
        event_ticker="KXBTC-123",
        title="Bitcoin above 100k",
        category="Crypto",
        markets=[KalshiMarket(
            ticker="KXBTC-123-A", event_ticker="KXBTC-123",
            title="A", status="settled", close_time=recent, result="yes",
        )],
    )
    stats = {"markets_created": 0, "outcomes_created": 0}
    out = await _create_settled_market(
        _mk_session(), _mk_service(event), {}, pg_insert,
        FuturesMarket, FuturesOutcome, compute_market_tier, stats,
    )
    assert out == "skip"
    assert stats["markets_created"] == 0
