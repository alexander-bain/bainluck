"""#9120 — Kalshi keeps a moved MLB game's ticker; the matcher follows the contract.

Production, 2026-09-27: MLB moved Cubs @ Red Sox to Sun 9/27 19:05Z at Tropicana
Field (event 15319741, ESPN 401817089). Kalshi did not re-mint: its only open
CHC-BOS game market is ``KXMLBGAME-26SEP261915CHCBOS``, whose rules name "the
game originally scheduled for Sep 26, 2026 at 7:15 PM EDT" and stay open "after
the rescheduled game has finished (within two days)". The ±3h date guard read
the ticker's 9/26 23:15Z as another game: 195 refusals, 95 Phase 2 unlinks, no
Kalshi price on the page.

Everything that decides the carry is SQL — the same-matchup rows on the
ticker's Eastern day, the venue's own tickers for the later game — and a
recording session cannot run it. So: real PostgreSQL, the real tables in a
private schema, the real ``_kalshi_postponed_game_carries`` and the real link
guard. Every fence has a control that flips it (gotcha #43); every instant is a
fixed literal (gotcha #44).
"""

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9120 "
            "postponed-ticker carry gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "kalshi_postponed_carry_9120"
UTC = timezone.utc
MLB, NHL = 3, 4
CUBS, SOX = 10714, 10709

NOW = datetime(2026, 9, 27, 10, 53, tzinfo=UTC)          # last refused attempt
SUNDAY = datetime(2026, 9, 27, 19, 5, tzinfo=UTC)        # the moved game
# extract_game_date_from_ticker's wall-clock carrier: 19:15 EASTERN on 9/26.
TICKER_SEP26 = datetime(2026, 9, 26, 19, 15, tzinfo=UTC)

GAME = "KXMLBGAME-26SEP261915CHCBOS"
EXTRAS = "KXMLBEXTRAS-26SEP261915CHCBOS"
CANDIDATE = 15319741


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base, Event, FuturesMarket, Sport, Team, Venue

    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    Sport.__table__, Team.__table__, Venue.__table__,
                    Event.__table__, FuturesMarket.__table__,
                ],
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for sid, key in ((MLB, "baseball_mlb"), (NHL, "icehockey_nhl")):
            await s.execute(
                text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
                {"i": sid, "k": key},
            )
        for tid, name in ((CUBS, "Chicago Cubs"), (SOX, "Boston Red Sox")):
            await s.execute(
                text("INSERT INTO teams (id, sport_id, name) VALUES (:i, :s, :n)"),
                {"i": tid, "s": MLB, "n": name},
            )
        # Production's rows around the move: Friday's doubleheader (both
        # finished, each holding its own Kalshi ticker) and Sunday's game.
        await _event(s, 15318549, datetime(2026, 9, 25, 17, 5, tzinfo=UTC),
                     espn="401817104", status="completed")
        await _event(s, 15318545, datetime(2026, 9, 25, 21, 30, tzinfo=UTC),
                     espn="401817074", status="completed")
        await _event(s, CANDIDATE, SUNDAY, espn="401817089")
        await _market(s, 62341416, "KXMLBGAME-26SEP251305CHCBOSG1", 15318549)
        await _market(s, 62013565, "KXMLBGAME-26SEP251910CHCBOS", 15318545)
        await _market(s, 62341415, GAME, None)
        # Kalshi DID mint Sunday inning props; only a GAME ticker says "this is
        # a different game", so these must not block the carry.
        await _market(s, 62400001, "KXMLBINNINGTOTAL-26SEP271505CHCBOS-1", None)
        await s.commit()
        yield s
        await s.rollback()
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
    await engine.dispose()


async def _event(s, eid, at, *, espn=None, status="scheduled", sport=MLB,
                 home="Boston Red Sox", away="Chicago Cubs",
                 home_id=SOX, away_id=CUBS):
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "home_team_id, away_team_id, commence_time, status, espn_id) "
            "VALUES (:id, :sp, :h, :a, :hi, :ai, :t, :st, :espn)"
        ),
        {"id": eid, "sp": sport, "h": home, "a": away, "hi": home_id,
         "ai": away_id, "t": at, "st": status, "espn": espn},
    )


async def _market(s, mid, ext, event_id):
    await s.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, name, category, "
            "mutually_exclusive, status, created_at, updated_at, event_id) "
            "VALUES (:i, 'kalshi', :x, :x, 'game', true, 'open', now(), now(), :e)"
        ),
        {"i": mid, "x": ext, "e": event_id},
    )


async def _carries(s, ext=GAME, td=TICKER_SEP26, event_id=CANDIDATE, now=NOW):
    from app.tasks.prediction_market_matching import _kalshi_postponed_game_carries

    return await _kalshi_postponed_game_carries(s, ext, td, event_id, now=now)


# ── The specimen ─────────────────────────────────────────────────────────────
async def test_the_moved_game_carries_its_kalshi_ticker(pg):
    assert await _carries(pg) is True


async def test_the_same_segments_props_carry_too(pg):
    assert await _carries(pg, ext=EXTRAS) is True


async def test_the_link_guard_now_lets_the_winner_reach_sunday(pg, monkeypatch):
    """End to end through the real guard: refusal before, link after."""
    from types import SimpleNamespace

    from app.tasks import prediction_market_matching as pmm

    market = SimpleNamespace(id=62341415, source="kalshi", external_id=GAME)
    monkeypatch.setattr(
        pmm, "_kalshi_postponed_game_carries",
        _pinned_now(pmm._kalshi_postponed_game_carries),
    )
    assert await pmm._check_duplicate_kalshi_linkage_reason(
        pg, CANDIDATE, market, TICKER_SEP26,
    ) is None

    # Strawman: without the carry the same guard refuses — the date conflict is
    # real, so the carry is what moved the answer.
    async def _never(*a, **k):
        return False

    monkeypatch.setattr(pmm, "_kalshi_postponed_game_carries", _never)
    assert await pmm._check_duplicate_kalshi_linkage_reason(
        pg, CANDIDATE, market, TICKER_SEP26,
    ) == pmm._REFUSAL_EVENT_DATE


def _pinned_now(fn):
    async def _call(session, ext, td, event_id, *, now=None):
        return await fn(session, ext, td, event_id, now=NOW)
    return _call


# ── Each fence, flipped ──────────────────────────────────────────────────────
async def test_a_live_row_on_the_tickers_day_means_the_game_was_not_moved(pg):
    await _event(pg, 15316408, datetime(2026, 9, 26, 23, 15, tzinfo=UTC))
    assert await _carries(pg) is False


async def test_a_postponed_row_on_the_tickers_day_does_not_block(pg):
    await _event(pg, 15316408, datetime(2026, 9, 26, 23, 15, tzinfo=UTC),
                 status="postponed")
    assert await _carries(pg) is True


async def test_a_row_under_other_names_but_the_same_clubs_still_blocks(pg):
    await _event(pg, 15316408, datetime(2026, 9, 26, 23, 15, tzinfo=UTC),
                 home="Boston", away="Chicago C")
    assert await _carries(pg) is False


async def test_the_tickers_eastern_day_not_its_utc_day_is_read(pg):
    # 01:00Z 9/27 is 9:00 PM EDT on 9/26 — the ticker's day. It blocks.
    await _event(pg, 15316408, datetime(2026, 9, 27, 1, 0, tzinfo=UTC))
    assert await _carries(pg) is False


async def test_a_late_slot_is_read_on_its_eastern_day_not_the_utc_day_after(pg):
    # 22:10 EDT on 9/26 is 02:10Z on 9/27. A 9/26 afternoon row is on the
    # ticker's day and blocks; reading the UTC day would look at 9/27 instead.
    await _event(pg, 15316408, datetime(2026, 9, 26, 18, 0, tzinfo=UTC))
    td = datetime(2026, 9, 26, 22, 10, tzinfo=UTC)
    assert await _carries(pg, ext="KXMLBGAME-26SEP262210CHCBOS", td=td) is False


async def test_kalshi_minting_its_own_ticker_for_the_later_game_blocks(pg):
    # The ordinary series: every day has its own game ticker.
    await _market(pg, 62400002, "KXMLBGAME-26SEP271505CHCBOS", None)
    assert await _carries(pg) is False


async def test_an_unanchored_later_row_does_not_carry(pg):
    await pg.execute(text("UPDATE events SET espn_id = NULL WHERE id = :i"), {"i": CANDIDATE})
    assert await _carries(pg) is False


async def test_before_the_original_slot_nothing_carries(pg):
    assert await _carries(pg, now=datetime(2026, 9, 26, 20, 0, tzinfo=UTC)) is False


async def test_a_game_moved_earlier_is_not_carried(pg):
    # Kalshi re-mints a game moved EARLIER (#8547); the carry is forward only.
    td = datetime(2026, 9, 28, 19, 15, tzinfo=UTC)
    assert await _carries(pg, ext="KXMLBGAME-26SEP281915CHCBOS", td=td,
                          now=datetime(2026, 9, 29, 0, 0, tzinfo=UTC)) is False


async def test_past_kalshis_two_days_nothing_carries(pg):
    await _event(pg, 15319900, datetime(2026, 9, 29, 0, 5, tzinfo=UTC), espn="401817999")
    assert await _carries(pg, event_id=15319900) is False
    # ...and inside the window the same shape does (control for the bound).
    await _event(pg, 15319901, datetime(2026, 9, 28, 22, 0, tzinfo=UTC), espn="401817998")
    assert await _carries(pg, event_id=15319901) is True


async def test_a_doubleheader_ticker_is_never_guessed(pg):
    assert await _carries(pg, ext="KXMLBGAME-26SEP261915CHCBOSG2") is False


async def test_other_sports_keep_the_date_guard(pg):
    await _event(pg, 15319950, SUNDAY, espn="401878104", sport=NHL,
                 home="Boston Bruins", away="Chicago Blackhawks",
                 home_id=None, away_id=None)
    assert await _carries(pg, ext="KXNHLGAME-26SEP261915CHIBOS",
                          event_id=15319950) is False
