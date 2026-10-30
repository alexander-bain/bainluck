"""#10090 (A1 on Argon Rank 3) — a live game's prop board never holds or
repeats its stamp.

Rank 3 writes a live game's headline as its own phase and its prop board
(`prices.headline_aux_outcome_ids`, the outcomes the refresher's
`_read_groups` leaves out) as a later one. On serving 31baf599 the board's
commit still queued the game for a second stamp, and beside a flush the
board's unfinished rows deferred the stamp of a headline that had already
committed. Neither stamp read anything the board wrote.

WHAT THIS FILE PROVES, on the SHIPPED `flush_prices` (the Rank 3 rig):

1. lane1's P3 (two live games, each with a 20-row board): each game is asked
   for exactly once, right after its own headline commit, never again after
   its board commits. Red on 31baf599 (each game asked twice).
2. Beside a flush, a game whose board is still unfinished in that pass is
   stamped at its headline commit, not deferred. Red on 31baf599.
3. Controls that keep today's cohort: a NON-live game whose only input is
   board rows still queues its stamp, and the final drain (whole-game
   contract, `headline_aux=()`) still queues a live game's board-only phase.
4. The truth guard (lane1's P1), on PostgreSQL: the refresher's read taken
   between the headline commit and the board commit equals the read taken
   after both. The board commit is the shipped price write
   (`_KalshiPriceOwner.phase`) plus the shipped re-rank, in one transaction.
   A headline write does change the read (the strawman guard).

Production latency is not claimed here.
"""

import datetime as dt

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.tasks.live_blend_refresh as lbr
import tests.test_flush_loop_live_aux_phase_10090 as bfile
from tests.pm_bulk_test_support import cleanup_pg_engines as cleanup_pg_engines  # noqa: F401
from tests.pm_bulk_test_support import pg_engine

AUX_B = tuple(range(20_000, 20_020))
AUX_A20 = bfile.AUX_A[:20]
_MAPS = bfile.maps


def _two_board_maps():
    markets, events = _MAPS()
    for oid in AUX_B:
        markets[oid], events[oid] = 3000 + (oid - AUX_B[0]) // 10, bfile.LIVE_B
    return markets, events


def _rig(monkeypatch, *, aux, maps=None):
    if maps is not None:
        monkeypatch.setattr(bfile, "maps", maps)
    built = bfile.rig(aux=aux)
    monkeypatch.setattr(lbr, "_mono", lambda: built.clock["now"])
    return built


def _asks(built, event):
    """(deferred, phases committed so far) for each stamp ask naming `event`."""
    return [(event in deferred, committed)
            for asked, deferred, committed in built.stamps if event in asked]


def _done(built, oid):
    return next(i for i, rows in enumerate(built.commits) if oid in rows) + 1


# ── 1. lane1's P3 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_p3_each_board_game_is_stamped_once_right_after_its_own_headline(monkeypatch):
    built = _rig(monkeypatch, aux=set(AUX_A20) | set(AUX_B), maps=_two_board_maps)
    order = bfile.HEAD_A + AUX_A20 + bfile.HEAD_B + AUX_B
    built.buffer.update({oid: (0.5, 0.49, 0.51) for oid in order})
    assert await built.flush(0.0) is True
    assert not built.buffer
    # Both headlines, then both boards (Rank 3's order, unchanged).
    assert [len(rows) for rows in built.commits] == [2, 2, 20, 20]
    head_a, head_b = _done(built, bfile.HEAD_A[0]), _done(built, bfile.HEAD_B[0])
    assert (head_a, head_b) == (1, 2)
    # 31baf599: [(False, 1), (False, 3)] and [(False, 2), (False, 4)].
    assert _asks(built, bfile.LIVE_A) == [(False, head_a)]
    assert _asks(built, bfile.LIVE_B) == [(False, head_b)]
    assert len(built.stamps) == 2, "a board's commit starts no stamp of its own"


@pytest.mark.asyncio
async def test_strawman_without_the_aux_set_each_game_is_one_whole_phase(monkeypatch):
    # The base plan: no split, so one ask per whole game, each after its game.
    built = _rig(monkeypatch, aux=(), maps=_two_board_maps)
    order = bfile.HEAD_A + AUX_A20 + bfile.HEAD_B + AUX_B
    built.buffer.update({oid: (0.5, 0.49, 0.51) for oid in order})
    assert await built.flush(0.0) is True
    assert [len(rows) for rows in built.commits] == [22, 22]
    assert _asks(built, bfile.LIVE_A) == [(False, 1)]
    assert _asks(built, bfile.LIVE_B) == [(False, 2)]


# ── 2. beside a flush ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_beside_a_flush_an_unfinished_board_does_not_defer_its_committed_headline(
    monkeypatch,
):
    built = _rig(monkeypatch, aux=bfile.AUX_A)
    built.buffer.update(
        {oid: (0.5, 0.49, 0.51) for oid in bfile.HEAD_A + bfile.AUX_A}
    )
    beside = (frozenset(), frozenset(), frozenset())
    assert await built.flush(0.0, beside=beside) is True
    head_a = _done(built, bfile.HEAD_A[0])
    assert head_a < _done(built, bfile.AUX_A[0])
    # 31baf599: [(True, 1), (False, 2)] — deferred until the board committed.
    assert _asks(built, bfile.LIVE_A) == [(False, head_a)]


# ── 3. controls: today's cohort where A1 does not apply ─────────────────────


@pytest.mark.asyncio
async def test_a_nonlive_games_board_only_input_still_queues_its_stamp(monkeypatch):
    built = _rig(monkeypatch, aux=set(bfile.AUX_A) | set(bfile.NONLIVE))
    built.buffer.update({oid: (0.5, 0.49, 0.51) for oid in bfile.NONLIVE})
    assert await built.flush(0.0) is True
    assert _asks(built, bfile.PREGAME) == [(False, 1)]


@pytest.mark.asyncio
async def test_the_final_drain_still_queues_a_live_games_board_only_phase(monkeypatch):
    built = _rig(monkeypatch, aux=bfile.AUX_A)
    built.buffer.update({oid: (0.5, 0.49, 0.51) for oid in AUX_A20})
    assert await built.flush(None, final_drain=True) is True
    assert not built.buffer
    assert [ask for ask in _asks(built, bfile.LIVE_A) if not ask[0]], \
        "whole-game contract: the drain's commit queues its game"


@pytest.mark.asyncio
async def test_a_live_games_board_only_input_queues_no_stamp(monkeypatch):
    # The same board-only input outside the drain: nothing the refresher
    # reads changed, so nothing is owed for this game.
    built = _rig(monkeypatch, aux=bfile.AUX_A)
    built.buffer.update({oid: (0.5, 0.49, 0.51) for oid in AUX_A20})
    assert await built.flush(0.0) is True
    assert not built.buffer
    assert _asks(built, bfile.LIVE_A) == []


# ── 3b. the receipts (lane1's R1/R1b; probes in test_lane1_a1_review_probes_10090) ──


@pytest.mark.asyncio
async def test_board_inputs_leave_the_receipt_queue_and_the_headline_stamp_covers_only_its_own(
    monkeypatch,
):
    """Interleaved headline and board ticks: the board's commit delivers its
    inputs (nothing is owed for them), and the headline stamp still covers
    every headline input, oldest first. An `unowed` that dropped every queued
    input up to the board's newest mark would also drop the headline's and
    leave `covered=0` — the queue empties either way, so only `covered` tells
    the two apart."""
    import tests.test_lane1_a1_review_probes_10090 as probes

    monkeypatch.setattr(lbr, "_wall", lambda: 1_800_000_000.0)  # one minute, no roll
    tr = probes._receipts()
    built = probes._rig(monkeypatch, tr)
    order = (bfile.HEAD_A[0], AUX_A20[0], bfile.HEAD_A[1], AUX_A20[1])
    for oid in order:
        probes._input(tr, built, oid)
    assert await built.flush(0.0) is True
    for asked, _d, _c in built.stamps:
        probes._refresher_side(tr, asked, 1.0)
    stamps = tr._window[bfile.LIVE_A]["stamps"]
    assert [s.rsplit("@", 1)[1] for s in stamps] == [str(len(bfile.HEAD_A))], stamps
    assert len(tr._uncovered.get(bfile.LIVE_A, ())) == 0


# ── 4. the truth guard, on PostgreSQL ───────────────────────────────────────

HEAD_TICKER = "KXNFLGAME-26OCT30SFLAR-SF"
BOARD_TICKER = "KXNFLPROPNEW-26OCT30SFLAR-X"
PRIOR = dt.datetime(2026, 10, 30, 0, 0, tzinfo=dt.timezone.utc)


def _plain(groups):
    """The refresher's read as plain, comparable data. A preview read also
    returns its statement's own clock (`preview_context_at`): when it read,
    not what it read, so it is left out."""
    out = {}
    for event_id, (event, entries) in groups.items():
        out[event_id] = (
            sorted((k, v) for k, v in vars(event).items() if k != "preview_context_at"),
            sorted(
                (
                    sorted(vars(entry.market).items(), key=lambda kv: kv[0]),
                    sorted(sorted(vars(row).items()) for row in entry.outcomes),
                )
                for entry in entries
            ),
        )
    return out


@pytest.mark.asyncio
async def test_truth_the_refreshers_read_is_the_same_before_and_after_the_board_commit():
    from app.models.models import Base, FuturesOutcome
    from app.tasks.kalshi_ws import _KalshiPriceOwner, kalshi_headline_aux_ticker
    from app.utils.futures_rank import rerank_market_fields_stmt

    assert not kalshi_headline_aux_ticker(HEAD_TICKER)
    assert kalshi_headline_aux_ticker(BOARD_TICKER)
    sync = pg_engine()
    with sync.begin() as conn:
        schema = conn.scalar(text("SELECT current_schema()"))
        Base.metadata.create_all(conn, tables=[
            Base.metadata.tables[name] for name in (
                "sports", "teams", "venues", "events", "futures_markets",
                "futures_outcomes",
            )
        ])
        conn.execute(insert(Base.metadata.tables["sports"]).values(
            id=1, key="americanfootball_nfl", name="NFL"))
        conn.execute(insert(Base.metadata.tables["events"]).values(
            id=100, sport_id=1, home_team_name="Rams", away_team_name="49ers",
            status="live", commence_time=PRIOR))
        for market_id, ticker, name in (
            (1, HEAD_TICKER, "49ers at Rams"), (2, BOARD_TICKER, "Total sacks"),
        ):
            conn.execute(insert(Base.metadata.tables["futures_markets"]).values(
                id=market_id, source="kalshi", external_id=ticker, name=name,
                category="game", status="open", mutually_exclusive=True, event_id=100))
        for oid, market_id, ticker, probability in (
            (11, 1, HEAD_TICKER, 0.55), (12, 1, "KXNFLGAME-26OCT30SFLAR-LAR", 0.45),
            (21, 2, f"{BOARD_TICKER}1", 0.30), (22, 2, f"{BOARD_TICKER}2", 0.70),
        ):
            conn.execute(insert(FuturesOutcome.__table__).values(
                id=oid, market_id=market_id, external_id=ticker, name=ticker,
                rank=oid % 10, current_probability=probability,
                current_yes_bid=probability - 0.01, current_yes_ask=probability + 0.01,
                last_updated=PRIOR, price_changed_at=PRIOR))
    engine = create_async_engine(
        sync.url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
    )
    refresher = lbr.LiveBlendRefresher("kalshi")
    owner = _KalshiPriceOwner()

    async def commit(phase):
        # The shipped phase transaction: the price write and the re-rank.
        async with AsyncSession(engine) as session:
            written = []
            async for result in owner.phase(session, phase):
                written += [row.id for row in result.all()]
            await session.execute(rerank_market_fields_stmt(sorted(
                {1 if oid < 20 else 2 for oid in written})))
            await session.commit()
        return written

    async def read():
        # Both statements the stamp may issue: the plain read, and the read
        # of an arm that previews this event (its whole bag and revision).
        reads = []
        for scope in (frozenset(), frozenset({100})):
            refresher.preview_events = scope
            async with AsyncSession(engine) as session:
                groups = await refresher._read_groups(session, [100], overlay_held=False)
            assert ("preview_rev" in vars(groups[100][0])) is bool(scope)
            reads.append(_plain(groups))
        return reads

    try:
        assert await commit({11: (0.60, 0.59, 0.61), 12: (0.40, 0.39, 0.41)}) == [11, 12]
        between = await read()
        # The board's commit moves both props and flips their order.
        assert sorted(await commit({21: (0.80, 0.79, 0.81), 22: (0.20, 0.19, 0.21)})) == [21, 22]
        async with AsyncSession(engine) as session:
            board = (await session.execute(text(
                "SELECT id, current_probability, rank FROM futures_outcomes "
                "WHERE market_id = 2 ORDER BY id"))).all()
        assert [(r.id, round(float(r.current_probability), 2)) for r in board] == [(21, 0.8), (22, 0.2)]
        after = await read()
        assert after == between, "the refresher reads nothing the board wrote"
        # Strawman guard: the same read DOES see a headline write.
        await commit({11: (0.70, 0.69, 0.71), 12: (0.30, 0.29, 0.31)})
        assert await read() != after
    finally:
        owner.close()
        await engine.dispose()
