"""#836 Batch 2 (SHADOW) — WS shadow grader: verdict parse, flag default,
shadow-write (never is_winner), comparison, and deploy-dark consumer guard.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import app.services.ws_shadow as sh


# ---- verdict_from_lifecycle (pure) ----

def test_verdict_yes():
    assert sh.verdict_from_lifecycle({"market_ticker": "KXabc-1", "status": "settled", "result": "yes"}) == ("KXABC-1", True)

def test_verdict_no():
    assert sh.verdict_from_lifecycle({"market_ticker": "KXabc-1", "status": "finalized", "result": "no"}) == ("KXABC-1", False)

def test_verdict_non_terminal_status_is_none():
    assert sh.verdict_from_lifecycle({"market_ticker": "X", "status": "active", "result": "yes"}) is None

def test_verdict_missing_result_is_none():
    assert sh.verdict_from_lifecycle({"market_ticker": "X", "status": "settled"}) is None
    assert sh.verdict_from_lifecycle({"market_ticker": "X", "status": "settled", "result": "void"}) is None

def test_verdict_bad_input_is_none():
    assert sh.verdict_from_lifecycle(None) is None
    assert sh.verdict_from_lifecycle({"status": "settled", "result": "yes"}) is None  # no ticker


# ---- flag default + record (Redis only, never is_winner) ----

def _fake_async_redis():
    rc = AsyncMock()
    rc.get = AsyncMock(return_value=None)
    rc.hset = AsyncMock()
    rc.expire = AsyncMock()
    rc.aclose = AsyncMock()
    return rc

async def test_flag_defaults_off():
    rc = _fake_async_redis()
    with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
        assert await sh.is_ws_shadow_enabled() is False

async def test_flag_on():
    rc = _fake_async_redis()
    rc.get = AsyncMock(return_value=b"true")
    with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
        assert await sh.is_ws_shadow_enabled() is True

async def test_record_writes_redis_hash_not_is_winner():
    rc = _fake_async_redis()
    with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
        await sh.record_shadow_verdict("KXABC-1", True)
    rc.hset.assert_awaited_once_with(sh.SHADOW_VERDICT_KEY, "KXABC-1", "1")
    rc.expire.assert_awaited_once()
    # by construction record_shadow_verdict has no DB/session access — it cannot
    # touch is_winner.


# ---- comparison logic ----

async def test_compare_counts_agree_disagree_ungraded_per_source():
    rc = _fake_async_redis()
    # shadow says: A=yes(1), B=no(0), C=yes(1), D=yes(1)
    rc.hgetall = AsyncMock(return_value={b"A": b"1", b"B": b"0", b"C": b"1", b"D": b"1"})
    # DB: A kalshi is_winner True (agree), B kalshi True (disagree vs shadow 0),
    #     C kalshi None (ungraded), D polymarket True (agree)
    rows = [
        ("A", True, "kalshi"),
        ("B", True, "kalshi"),
        ("C", None, "kalshi"),
        ("D", True, "polymarket"),
    ]
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
        report = await sh.compare_shadow_verdicts(session)

    k = report["sources"]["kalshi"]
    assert k["agree"] == 1 and k["disagree"] == 1 and k["ungraded"] == 1
    assert k["match_rate"] == 0.5  # 1 agree / (1+1) graded
    p = report["sources"]["polymarket"]
    assert p["agree"] == 1 and p["match_rate"] == 1.0
    assert report["total"]["agree"] == 2 and report["total"]["disagree"] == 1
    assert report["shadow_count"] == 4

async def test_compare_empty_shadow():
    rc = _fake_async_redis()
    rc.hgetall = AsyncMock(return_value={})
    session = AsyncMock()
    with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
        report = await sh.compare_shadow_verdicts(session)
    assert report["shadow_count"] == 0
    assert report["total"]["match_rate"] is None


# ---- deploy-dark consumer guard ----

async def test_shadow_consumer_is_deploy_dark_when_flag_off():
    """The shadow consumer must NOT connect when the flag is off (default)."""
    from app.tasks import kalshi_ws
    with patch("app.services.ws_shadow.is_ws_shadow_enabled", AsyncMock(return_value=False)):
        result = await kalshi_ws._run_kalshi_ws_shadow_consumer()
    assert result == {"status": "shadow_disabled"}
