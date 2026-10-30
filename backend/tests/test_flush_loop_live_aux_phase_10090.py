"""#10090 — Argon's flush-loop Rank 3: a live game's headline is its own phase.

Production 2026-10-30 00:16-00:20Z (Kalshi minute lines): the slowest flush's
slowest phase was a LIVE one of 140 rows (`db_phase=1.64s/live/140`, also
`/live/67`, `/live/51`) — live event 14780569's outcomes, which the flush keeps
in the event's cohort (`kalshi_non_speaking_ticker` keeps unknown series) but
the refresher's headline read never looks at (`_read_groups` reads only
`feeds_win_prob_blend` tickers, or none). Every other live game's headline
waited behind that board.

WHAT THIS FILE PROVES, on the planner and on the SHIPPED `flush_prices`
(AST-exec'd, as the #10655 rig does):

1. A live game with 140 auxiliary outcomes yields a headline phase of only its
   speaking outcomes; every live headline phase comes first, then the live-aux
   phases, then every non-live phase. Strawman: without the aux set the live
   game is one 142-row phase.
2. The auxiliary outcomes are written before any non-live phase, inside the
   same flush (live work is never budget-deferred).
3. The event is not stamped between its two phases: its headline commit asks
   for its stamp with the event still deferred (its aux rows unfinished).
4. The aux classification is the refresher's own ticker rule.

Production latency is not claimed here.
"""

import ast
import asyncio
import contextlib  # noqa: F401 — the exec'd flush reads it
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.tasks.live_blend_refresh as lbr
from app.tasks.kalshi_ws import (  # noqa: F401 — the exec'd flush reads these
    FLUSH_BUDGET_SECONDS,
    NONLIVE_PHASE_MAX_GAMES,
    NONLIVE_PHASE_MAX_ROWS,
    PRICE_PHASE_LOCK_TIMEOUT_MS,
    _FlushTimings,
    _KalshiPriceOwner,
    flush_budget_spent,
    kalshi_headline_aux_ticker,
    linked_first_phases,
    live_preempts_tail,
    yield_written_nonlive_tail,
)
from app.tasks.live_blend_refresh import event_ids_for_outcomes  # noqa: F401
from app.utils.futures_rank import rerank_market_fields_stmt  # noqa: F401
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from app.utils.repair_lock_budget import (  # noqa: F401 — read by the exec'd flush
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)
from tests._kalshi_price_session import bind_session, consumer_engine
from tests.pm_bulk_test_support import price_writes, statement_params

LIVE_A, LIVE_B, PREGAME = 5000, 5001, 5002
HEAD_A, HEAD_B, NONLIVE = (0, 1), (2, 3), (4, 5)
AUX_A = tuple(range(10_000, 10_140))  # 14 markets x 10 outcomes on LIVE_A
FUTURES = tuple(range(100_000, 100_010))


def maps():
    markets, events = {}, {}
    for oids, market, event in (
        (HEAD_A, 1000, LIVE_A), (HEAD_B, 1001, LIVE_B), (NONLIVE, 1002, PREGAME),
    ):
        for oid in oids:
            markets[oid], events[oid] = market, event
    for oid in AUX_A:
        markets[oid], events[oid] = 2000 + (oid - AUX_A[0]) // 10, LIVE_A
    for oid in FUTURES:
        markets[oid] = 9000
    return markets, events


def batch_oldest_aux_first():
    """The aux board ticked first (oldest), the headline last."""
    order = AUX_A + NONLIVE + FUTURES + HEAD_B + HEAD_A
    return {oid: (0.5, 0.49, 0.51) for oid in order}


# ── 1. the planner ──────────────────────────────────────────────────────────


def test_a_live_game_with_140_aux_outcomes_yields_a_headline_phase_of_its_speakers():
    markets, events = maps()
    phases = linked_first_phases(
        batch_oldest_aux_first(), markets, events,
        live_events={LIVE_A, LIVE_B}, headline_aux=set(AUX_A),
    )
    assert [set(p) for p in phases[:3]] == [set(HEAD_A), set(HEAD_B), set(AUX_A)]
    # Then the non-live tail, untouched: the pre-game game, then the futures.
    assert [set(p) for p in phases[3:]] == [set(NONLIVE), set(FUTURES)]


def test_strawman_without_the_aux_set_the_live_game_is_one_142_row_phase():
    markets, events = maps()
    phases = linked_first_phases(
        batch_oldest_aux_first(), markets, events, live_events={LIVE_A, LIVE_B},
    )
    assert len(phases[0]) == 142 and set(phases[1]) == set(HEAD_B)


def test_a_live_game_whose_buffered_input_is_only_aux_is_one_live_aux_phase():
    markets, events = maps()
    batch = {oid: (0.5, 0.49, 0.51) for oid in AUX_A + NONLIVE + HEAD_B}
    phases = linked_first_phases(
        batch, markets, events, live_events={LIVE_A, LIVE_B},
        headline_aux=set(AUX_A),
    )
    assert [set(p) for p in phases] == [set(HEAD_B), set(AUX_A), set(NONLIVE)]


def test_non_live_games_are_never_split():
    markets, events = maps()
    phases = linked_first_phases(
        batch_oldest_aux_first(), markets, events, live_events={LIVE_B},
        headline_aux=set(AUX_A),
    )
    # LIVE_A is not live: its headline and aux stay one whole game, as today.
    assert set(phases[0]) == set(HEAD_B)
    assert any(set(HEAD_A) | set(AUX_A) <= set(p) for p in phases[1:])


@pytest.mark.parametrize("ticker, aux", [
    ("KXNFLGAME-25OCT30BALMIA-BAL", False),   # read: a game winner
    ("KXATPMATCH-25OCT30-SIN", False),        # read: a racquet match winner
    ("KXUFCFIGHT-25NOV01-JON", False),        # read: a fight winner
    ("KXNFLSPREAD-25OCT30BALMIA-BAL3", True),  # a known non-speaker
    ("KXNEWSERIESPROP-25OCT30-X", True),      # unknown series: never read
    (None, False), ("", False),               # the resolver's name fallback
])
def test_the_aux_rule_is_the_refreshers_headline_read(ticker, aux):
    assert kalshi_headline_aux_ticker(ticker) is aux


def test_the_aux_rule_matches_the_refreshers_sql_text():
    # `_read_groups` (source=kalshi) admits outcomes of a NULL/empty ticker or a
    # prefix that ends in "game" or is a combat/tennis winner prefix; the
    # helper reads the same shared sets through `feeds_win_prob_blend`.
    import inspect

    from app.utils import prediction_market_matching as pmm

    body = inspect.getsource(lbr.LiveBlendRefresher._read_groups)
    for clause in (
        'FuturesMarket.external_id.is_(None)', 'FuturesMarket.external_id == ""',
        'prefix.endswith("game")', "COMBAT_FIGHT_WINNER_PREFIXES | TENNIS_MATCH_WINNER_PREFIXES",
    ):
        assert clause in body
    feeds = inspect.getsource(pmm.feeds_win_prob_blend)
    assert 'prefix.endswith("game")' in feeds
    assert "COMBAT_FIGHT_WINNER_PREFIXES" in feeds and "TENNIS_MATCH_WINNER_PREFIXES" in feeds


# ── 2-3. the shipped flush ──────────────────────────────────────────────────


def rig(*, aux=AUX_A):
    markets, events = maps()
    clock = {"now": 0.0}
    commits = []  # one tuple of outcome ids per committed phase
    stamps = []  # (events asked for, events deferred, phases committed so far)
    stats = defaultdict(int)

    class Session:
        def __init__(self):
            self.rows = []

        async def execute(self, stmt, bind=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                return SimpleNamespace(rowcount=1)
            pairs = price_writes(stmt, statement_params(stmt, bind))
            if not pairs:
                return SimpleNamespace(rowcount=0)  # the field re-rank
            (oid, _prob), = pairs
            self.rows.append(oid)
            row = SimpleNamespace(id=oid, market_id=markets[oid],
                                  last_updated=clock["now"], quote_moved=True)
            return SimpleNamespace(rowcount=1, all=lambda: [row])

    engine = consumer_engine()

    @asynccontextmanager
    async def session():
        s = bind_session(Session(), engine)
        yield s
        clock["now"] += 0.4 + 0.002 * len(s.rows)
        if s.rows:
            commits.append(tuple(s.rows))

    class Refresher:
        def pending_event_ids(self):
            return frozenset()

        def admit_fresh(self, ids, **_kw):
            return frozenset()

        async def publish_market_changes(self, _s):
            return 0

        async def refresh(self, ids, *, defer_event_ids=(), **_kw):
            stamps.append((set(ids), set(defer_event_ids), len(commits)))

        async def refresh_pending(self, **_kw):
            return None

    class Receipts:
        def stage(self, _marks):
            return None

    buffer = {}
    prices = _KalshiPriceOwner()
    prices.timings = _FlushTimings()
    prices.headline_aux_outcome_ids.update(aux)
    ns = dict(globals(), price_buffer=buffer, buffer_lock=asyncio.Lock(),
              market_id_by_outcome=markets, event_id_by_outcome=events,
              non_blend_outcome_ids=set(),
              input_marks={}, tail_receipts=Receipts(),
              primary_quote_custody=PrimaryQuoteCustody(), ticker_to_ids={},
              open_contract_outcome_ids=set(), blend_refresher=Refresher(),
              get_task_session=session, stats=stats, prices=prices,
              live_event_ids={LIVE_A, LIVE_B},
              flush_budget=None, flush_period=1.0,
              logger=logging.getLogger(__name__),
              queue_market_change=lambda *a, **k: None)
    path = Path(__file__).resolve().parents[1] / "app/tasks/kalshi_ws.py"
    (node,) = [n for n in ast.walk(ast.parse(path.read_text()))
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "flush_prices"]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return SimpleNamespace(flush=ns["flush_prices"], buffer=buffer, clock=clock,
                           commits=commits, stamps=stamps, ns=ns)


@pytest.fixture
def r(monkeypatch):
    built = rig()
    monkeypatch.setattr(lbr, "_mono", lambda: built.clock["now"])
    return built


def _phase_of(commits, oid):
    return next(i for i, rows in enumerate(commits) if oid in rows)


@pytest.mark.asyncio
async def test_the_aux_outcomes_are_written_before_any_nonlive_phase(r):
    r.buffer.update(batch_oldest_aux_first())
    assert await r.flush(0.0) is True
    assert not r.buffer, "one flush wrote everything"
    head_a, head_b = _phase_of(r.commits, HEAD_A[0]), _phase_of(r.commits, HEAD_B[0])
    aux = {_phase_of(r.commits, oid) for oid in AUX_A}
    nonlive = {_phase_of(r.commits, oid) for oid in NONLIVE + FUTURES}
    assert set(r.commits[head_a]) == set(HEAD_A)
    assert set(r.commits[head_b]) == set(HEAD_B)
    assert max(head_a, head_b) < min(aux), "every live headline first"
    assert max(aux) < min(nonlive), "live props ahead of the non-live tail"


@pytest.mark.asyncio
async def test_the_headline_is_stamped_at_its_own_commit_not_after_its_aux_board(r):
    # Commit C (Argon Rank 1): the prop board is not what the refresher reads,
    # so a headline/board split is not a partly written board. The headline's
    # commit asks for its stamp with nothing deferring it; the board's commit
    # asks for none (A1: it wrote nothing the refresher reads). (Commit B
    # alone deferred it until the board committed; C alone asked again.) The
    # non-live game keeps today's fence until its own phase commits.
    r.buffer.update(batch_oldest_aux_first())
    assert await r.flush(0.0) is True
    head_done = _phase_of(r.commits, HEAD_A[0]) + 1
    assert head_done < min(_phase_of(r.commits, oid) for oid in AUX_A) + 1
    pregame_done = _phase_of(r.commits, NONLIVE[0]) + 1
    asks = [(deferred, committed) for asked, deferred, committed in r.stamps
            if LIVE_A in asked]
    assert [committed for _d, committed in asks] == [head_done]
    assert all(LIVE_A not in deferred for deferred, _c in asks)
    for _asked, deferred, committed in r.stamps:
        assert (PREGAME in deferred) is (committed < pregame_done)


@pytest.mark.asyncio
async def test_strawman_an_empty_aux_set_keeps_the_142_row_live_phase(monkeypatch):
    built = rig(aux=())
    monkeypatch.setattr(lbr, "_mono", lambda: built.clock["now"])
    built.buffer.update(batch_oldest_aux_first())
    assert await built.flush(0.0) is True
    assert len(built.commits[0]) == 142


@pytest.mark.asyncio
async def test_beside_a_flush_the_newest_first_order_keeps_headlines_ahead_of_aux(r):
    # Beside a flush the helper serves the newest live event first. The aux
    # board holding the newest input must not jump the headline phases.
    live_only = {oid: e for oid, e in batch_oldest_aux_first().items()
                 if oid in AUX_A + HEAD_A + HEAD_B}
    r.buffer.update(live_only)
    r.ns["input_marks"].update(
        {oid: SimpleNamespace(seq=1) for oid in HEAD_A + HEAD_B}
        | {oid: SimpleNamespace(seq=9) for oid in AUX_A}
    )
    beside = (frozenset(), frozenset(), frozenset())
    assert await r.flush(0.0, beside=beside) is True
    aux = min(_phase_of(r.commits, oid) for oid in AUX_A)
    assert _phase_of(r.commits, HEAD_A[0]) < aux
    assert _phase_of(r.commits, HEAD_B[0]) < aux
