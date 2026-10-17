"""#698 chart half: `/history` never ends a line at a result the detail row withholds.

`/futures/62134744` (*Marchi vs. Lokoli: Match O/U 21.5*, Polymarket, resolved)
stores both legs at `current_probability 0.500000, is_winner false,
resolution_source 'clob_authoritative'`. After #11150 (cdd20661) the page says
"RESOLVED · Result unknown", the rows say "Result unknown · Last recorded 50%",
and the caption says "Result unknown; chart shows recorded prices." But the
served `/api/futures/62134744/history?hours=8760` (shopper, 2026-10-17T0100Z,
`artifacts/shopper/698-served-20261017/hist-62134744.json`) still ended BOTH
lines with `{2026-10-01T07:30Z, 0.0, bookmaker: "settlement"}`, so the chart
under that caption drew Over and Under falling to 0% together.

The loser arm (#7927) took the sourced `false` as an evidenced loss. These tests
pin that it now defers to the detail contract (`utils/settlement_display`) on
the contract's own scope, and that every control outside it is untouched.

Pure values plus one endpoint pass; the settle stamp is an argument (gotcha #44).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.futures import (
    _apply_settled_loser_freeze,
    _apply_settled_winner_freeze,
    _detail_withholds_result,
    get_futures_history,
)
from app.utils.settlement_display import settlement_display

SETTLE = datetime(2026, 10, 1, 7, 30, 0, tzinfo=timezone.utc)
LAST_REAL = datetime(2026, 9, 24, 6, 16, 4, tzinfo=timezone.utc)


def _outcome(oid, name, *, is_winner, resolution_source, prob):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.is_winner = is_winner
    o.resolution_source = resolution_source
    o.current_probability = prob
    o.last_updated = None
    return o


def _market(outcomes, *, source="polymarket", status="resolved", mutually_exclusive=True):
    m = MagicMock()
    m.id = 62134744
    m.name = "Marchi vs. Lokoli: Match O/U 21.5"
    m.outcomes = outcomes
    # Real strings: `applies_to_market` keys on them, and a MagicMock attribute
    # would silently put every test on the out-of-scope arm.
    m.source = source
    m.status = status
    m.resolution_date = SETTLE
    m.settled_at = None
    m.mutually_exclusive = mutually_exclusive
    return m


def _series(oid, name, prob):
    return {
        "outcome_id": oid,
        "name": name,
        "history": [
            {"timestamp": (LAST_REAL - timedelta(hours=1)).isoformat(),
             "probability": prob, "american_odds": None, "bookmaker": "consensus"},
            {"timestamp": LAST_REAL.isoformat(),
             "probability": prob, "american_odds": None, "bookmaker": "consensus"},
        ],
        "eliminated": False,
        "eliminated_at": None,
    }


def _coin_flip():
    """The 62134744 shape: both legs 0.5 / false / clob_authoritative."""
    over = _outcome(1, "Over", is_winner=False, resolution_source="clob_authoritative", prob=0.5)
    under = _outcome(2, "Under", is_winner=False, resolution_source="clob_authoritative", prob=0.5)
    history = {1: _series(1, "Over", 0.465), 2: _series(2, "Under", 0.535)}
    return over, under, history


class TestTheSpecimen:
    def test_neither_coin_flip_leg_gains_a_settlement_point(self):
        over, under, history = _coin_flip()
        _apply_settled_loser_freeze(_market([over, under]), history, SETTLE)
        for oid, prob in ((1, 0.465), (2, 0.535)):
            assert len(history[oid]["history"]) == 2
            last = history[oid]["history"][-1]
            assert last["bookmaker"] == "consensus"
            assert last["probability"] == prob

    def test_a_stored_winner_at_a_nonterminal_price_is_not_drawn_to_one(self):
        # The mirror: the page says "Result unknown", so the chart may not
        # say "won" either.
        yes = _outcome(1, "Yes", is_winner=True, resolution_source="clob_authoritative", prob=0.5)
        no = _outcome(2, "No", is_winner=False, resolution_source="clob_authoritative", prob=0.5)
        history = {1: _series(1, "Yes", 0.5), 2: _series(2, "No", 0.5)}
        _apply_settled_winner_freeze(_market([yes, no]), history, {1: "Yes", 2: "No"},
                                     settle_ts=SETTLE)
        assert history[1]["history"][-1]["bookmaker"] == "consensus"

    def test_a_withheld_champion_is_not_synthesized_either(self):
        yes = _outcome(1, "Yes", is_winner=True, resolution_source="clob_authoritative", prob=0.5)
        history: dict = {}
        _apply_settled_winner_freeze(_market([yes]), history, {1: "Yes"}, settle_ts=SETTLE)
        assert history == {}

    def test_the_gate_is_the_detail_contract_not_a_second_rule(self):
        # Every specimen shape: the gate answers exactly what the served
        # `settlement_display` says, inside scope.
        rows = [
            (False, "clob_authoritative", 0.5),
            (True, "clob_authoritative", 1),
            (False, "clob_authoritative", 0),
            (True, "clob_authoritative", 0),
            (False, "ungradeable_result", 0),
            (False, None, 0),
            (None, "clob_authoritative", 0),
            (False, "clob_authoritative", None),
            (False, "clob_authoritative", 0.001),
        ]
        for is_winner, source, prob in rows:
            o = _outcome(9, "x", is_winner=is_winner, resolution_source=source, prob=prob)
            served = settlement_display(
                is_winner=is_winner, resolution_source=source, stored_probability=prob
            )["verdict"]
            assert _detail_withholds_result(_market([o]), o) is (served == "unknown"), (
                is_winner, source, prob,
            )


class TestTheControls:
    def test_a_terminal_agreement_loss_still_ends_at_zero(self):
        # 12194657 shape: stored 0 / false / sourced is a stated "Lost".
        lost = _outcome(1, "A", is_winner=False, resolution_source="clob_authoritative", prob=0)
        history = {1: _series(1, "A", 0.3)}
        _apply_settled_loser_freeze(_market([lost], mutually_exclusive=False), history, SETTLE)
        assert history[1]["history"][-1] == {
            "timestamp": SETTLE.isoformat(), "probability": 0.0,
            "american_odds": None, "bookmaker": "settlement",
        }

    def test_a_terminal_agreement_win_still_ends_at_one(self):
        # 13798072 shape: No WON 100% / Yes Lost 0%.
        no = _outcome(1, "No", is_winner=True, resolution_source="clob_authoritative", prob=1)
        yes = _outcome(2, "Yes", is_winner=False, resolution_source="clob_authoritative", prob=0)
        history = {1: _series(1, "No", 0.7), 2: _series(2, "Yes", 0.3)}
        market = _market([no, yes])
        _apply_settled_winner_freeze(market, history, {1: "No", 2: "Yes"}, settle_ts=SETTLE)
        _apply_settled_loser_freeze(market, history, SETTLE)
        assert history[1]["history"][-1]["probability"] == 1.0
        assert history[1]["history"][-1]["bookmaker"] == "settlement"
        assert history[2]["history"][-1]["probability"] == 0.0
        assert history[2]["history"][-1]["bookmaker"] == "settlement"

    @pytest.mark.parametrize("source,status", [("kalshi", "resolved"), ("polymarket", "open")])
    def test_outside_the_contracts_scope_nothing_moves(self, source, status):
        # The detail contract serves nothing on these, so the chart keeps its
        # #7927 behaviour exactly — this change is not a new loss rule.
        over, under, history = _coin_flip()
        _apply_settled_loser_freeze(
            _market([over, under], source=source, status=status), history, SETTLE
        )
        for oid in (1, 2):
            assert history[oid]["history"][-1]["probability"] == 0.0
            assert history[oid]["history"][-1]["bookmaker"] == "settlement"


def _snapshot(outcome_id, captured_at, prob):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "test"
    return s


async def _serve(market, snaps):
    call_count = 0

    async def mock_execute(query):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = market
            return result
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = snaps
        result.scalars.return_value = scalars_mock
        return result

    db = AsyncMock()
    db.execute = mock_execute
    return await get_futures_history(
        market_id=market.id, hours=8760, top_n=8, outcome_id=None, db=db
    )


class TestTheEndpointServesIt:
    @pytest.mark.asyncio
    async def test_the_coin_flip_is_served_ending_on_recorded_prices(self):
        now = datetime.now(timezone.utc)
        over, under, _ = _coin_flip()
        market = _market([over, under])
        market.resolution_date = now - timedelta(hours=6)
        snaps = []
        for i in range(30):
            ts = now - timedelta(hours=12 + i * 2)
            snaps.append(_snapshot(1, ts, 0.465))
            snaps.append(_snapshot(2, ts, 0.535))

        result = await _serve(market, snaps)
        assert {o["name"] for o in result["outcomes"]} == {"Over", "Under"}
        for o in result["outcomes"]:
            assert all(pt["bookmaker"] != "settlement" for pt in o["history"]), o["name"]
            assert o["history"][-1]["probability"] not in (0.0, 1.0)

    @pytest.mark.asyncio
    async def test_the_same_board_off_scope_still_gets_its_zeros(self):
        # The strawman for the test above: identical rows on a Kalshi market
        # still end at 0.0, so the passing assertion is the gate, not the rig.
        now = datetime.now(timezone.utc)
        over, under, _ = _coin_flip()
        market = _market([over, under], source="kalshi")
        market.resolution_date = now - timedelta(hours=6)
        snaps = []
        for i in range(30):
            ts = now - timedelta(hours=12 + i * 2)
            snaps.append(_snapshot(1, ts, 0.465))
            snaps.append(_snapshot(2, ts, 0.535))

        result = await _serve(market, snaps)
        for o in result["outcomes"]:
            assert o["history"][-1]["bookmaker"] == "settlement"
            assert o["history"][-1]["probability"] == 0.0


# Root's upstream witness (artifacts/shopper/698-served-20261017/
# ROOT-UPSTREAM-GRADE-WITNESS.json, AST-extracted from cdd20661): the #7935
# republication drop read the same sourced `false` as a 0.0 grade and pruned a
# withheld line that touched 0 three times. Genuine zeros included on purpose —
# they must be served too.
_WITNESS = [0.4, 0, 0.3, 0, 0.6, 0, 0.5, 0, 0.465]
_WITNESS_PRUNED = [0.4, 0, 0, 0, 0]


def _witness_snaps(now):
    # Both legs of the pair, Under = 1 - Over, so the de-vig is the identity
    # and the served Over line is the recorded one (a lone leg squeezes to 1.0).
    start = now - timedelta(hours=12 + len(_WITNESS))
    snaps = []
    for i, p in enumerate(_WITNESS):
        ts = start + timedelta(hours=i)
        snaps.append(_snapshot(1, ts, p))
        snaps.append(_snapshot(2, ts, round(1 - p, 6)))
    return snaps


def _pair_market(*, source, now, stated=False):
    if stated:
        # 13798072 shape: a stated result on both legs (Over Lost 0%, Under WON).
        over = _outcome(1, "Over", is_winner=False, resolution_source="clob_authoritative", prob=0)
        under = _outcome(2, "Under", is_winner=True, resolution_source="clob_authoritative", prob=1)
    else:
        over, under, _ = _coin_flip()
    market = _market([over, under], source=source)
    market.resolution_date = now - timedelta(hours=6)
    return market


def _served_values(result):
    (line,) = [o for o in result["outcomes"] if o["outcome_id"] == 1]
    return [pt["probability"] for pt in line["history"] if pt["bookmaker"] != "settlement"]


class TestTheRepublicationDropDefersToo:
    @pytest.mark.asyncio
    async def test_the_withheld_line_keeps_every_recorded_observation(self):
        now = datetime.now(timezone.utc)
        market = _pair_market(source="polymarket", now=now)
        result = await _serve(market, _witness_snaps(now))
        assert _served_values(result) == pytest.approx(_WITNESS)

    @pytest.mark.asyncio
    async def test_the_same_line_off_scope_is_still_pruned(self):
        # Strawman: the rig reaches the #7935 drop — identical rows on a
        # Kalshi market (no detail contract) are pruned exactly as the witness
        # says, so the passing assertion above is the gate, not the fixture.
        now = datetime.now(timezone.utc)
        market = _pair_market(source="kalshi", now=now)
        result = await _serve(market, _witness_snaps(now))
        assert _served_values(result) == pytest.approx(_WITNESS_PRUNED)

    @pytest.mark.asyncio
    async def test_a_stated_polymarket_loss_is_still_pruned(self):
        # Control inside scope: stored 0 / false / sourced is a stated "Lost",
        # so its republication echo is still dropped.
        now = datetime.now(timezone.utc)
        market = _pair_market(source="polymarket", now=now, stated=True)
        result = await _serve(market, _witness_snaps(now))
        assert _served_values(result) == pytest.approx(_WITNESS_PRUNED)
