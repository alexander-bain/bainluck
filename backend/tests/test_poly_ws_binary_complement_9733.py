"""#9733 follow-on — a streamed Yes/No pair keeps adding to 100.

WHAT A READER SAW. ``/api/futures/61352683`` (2026-09-30 13:3xZ), "Will George
Kittle have 524.5+ receiving yards …": **Yes 77% / No 10%**. The venue read
76.5 / 23.5. A 20-share No sell at 0.10 (12:24:08Z) went through
``handle_trade``, so the No leg took 0.10. The Yes leg kept its own number,
since its wide book is refused and it had no trade since 9/27. 29 of 7,883
streamed binaries whose price moved after 12:50Z stored a pair more than 10
points from 100 (HOOD $125 week high, market 62403481: Yes 0.815 / No 0.55).

THE RULE. Two tokens of one condition pay out 1 between them. A price accepted
for one is ``1 - p`` for the other, so both legs are written from the same tick.
``complement_pairs`` admits only a market with exactly two legs that are token
0 and token 1 of one condition. Both must be carried by the open-contract arm
and neither graded. Every other leg is priced exactly as before.

#9733's min-order rule still runs first: a leftover trade prices neither leg.
"""

import json

import pytest
from sqlalchemy import insert, text

import app.tasks.polymarket_open_contracts as open_mod
from app.models.models import FuturesOutcome
from app.tasks.polymarket_ws import with_complements
from tests.test_ws_polymarket_open_contract_prices_9484 import (
    GAME_SLATE,
    OPEN_MARKET_ROWS,
    OPEN_OUTCOME_ROWS,
    _database,
    _drive,
    _frames_by_token,
    _Rig,
    _stored,
    _tick,
)

KITTLE = "0x79126b8aae0ff33236367a94662609fb3172852133a140e0957349eeac551a4b"
KITTLE_MARKET, KITTLE_YES, KITTLE_NO = 61352683, 230960369, 230960370
YES_TOKEN, NO_TOKEN = "kittleYes", "kittleNo"


class TestComplementPairs:
    def _pairs(self, legs, admitted=None, graded=(), excluded=()):
        by_market: dict = {}
        for oid, mid, ext in legs:
            by_market.setdefault(mid, []).append((oid, ext))
        return open_mod.complement_pairs(
            by_market,
            set(admitted if admitted is not None else [o for o, _m, _e in legs]),
            set(graded),
            set(excluded),
        )

    def test_a_yes_no_binary_is_one_pair(self):
        assert self._pairs(
            [(1, 10, f"{KITTLE}_yes"), (2, 10, f"{KITTLE}_no")]
        ) == {1: 2, 2: 1}

    def test_a_named_two_sided_game_bare_plus_side1_is_one_pair(self):
        # #7505's single-market shape: leg 0 is the bare condition id.
        assert self._pairs([(1, 10, "0xabc"), (2, 10, "0xabc_side1")]) == {
            1: 2,
            2: 1,
        }

    @pytest.mark.parametrize(
        "legs",
        [
            # a two-leg field board: two conditions, both token 0
            [(1, 10, "0xaaa"), (2, 10, "0xbbb")],
            # two conditions, token 0 and token 1
            [(1, 10, "0xaaa_yes"), (2, 10, "0xbbb_no")],
            # one condition, but both legs name token 0
            [(1, 10, "0xaaa"), (2, 10, "0xaaa_yes")],
            # three legs
            [(1, 10, "0xaaa_yes"), (2, 10, "0xaaa_no"), (3, 10, "0xccc")],
            # a suffix naming no token
            [(1, 10, "0xaaa_yes"), (2, 10, "0xaaa_draw")],
            # not a Polymarket condition id
            [(1, 10, "KXNFL-1_yes"), (2, 10, "KXNFL-1_no")],
        ],
    )
    def test_anything_but_one_binary_has_no_complement(self, legs):
        assert self._pairs(legs) == {}

    def test_a_graded_leg_is_never_paired(self):
        legs = [(1, 10, "0xaaa_yes"), (2, 10, "0xaaa_no")]
        assert self._pairs(legs, graded=[2]) == {}

    def test_a_leg_this_arm_does_not_carry_is_never_paired(self):
        legs = [(1, 10, "0xaaa_yes"), (2, 10, "0xaaa_no")]
        assert self._pairs(legs, admitted=[1]) == {}

    def test_a_game_slate_market_is_never_paired(self):
        legs = [(1, 10, "0xaaa_yes"), (2, 10, "0xaaa_no")]
        assert self._pairs(legs, excluded=[10]) == {}


class TestAdmission:
    BOARD = (60087232, None, None, {"601": "cubsYes", "602": "sdYes"})
    BINARY = (61380842, ["cubsYes", "cubsNo"], None, None)
    LEGS = [
        (601, 60087232, "0x52f9", False),
        (602, 60087232, "0x77aa", False),
        (611, 61380842, "0x52f9_yes", False),
        (612, 61380842, "0x52f9_no", False),
    ]

    @pytest.mark.parametrize("board_first", [True, False])
    def test_the_binary_is_paired_and_the_board_is_not(self, board_first):
        """#9736's shape: the board's Cubs leg and the binary's Yes leg share
        a token. Whichever owns it, only the binary's two legs are complements;
        the board is a field, never a pair."""
        rows = [self.BOARD, self.BINARY] if board_first else [self.BINARY, self.BOARD]
        adm = open_mod.open_contract_asset_map(rows, self.LEGS)
        assert adm.complement_of == {611: 612, 612: 611}
        assert adm.counts["legs_complemented"] == 2

    def test_a_graded_binary_leg_unpairs_both(self):
        legs = [*self.LEGS[:3], (612, 61380842, "0x52f9_no", True)]
        adm = open_mod.open_contract_asset_map([self.BINARY], legs[2:])
        assert adm.complement_of == {}

    def test_a_market_on_the_game_slate_is_not_paired(self):
        adm = open_mod.open_contract_asset_map(
            [self.BINARY], self.LEGS[2:], excluded_market_ids={61380842}
        )
        assert adm.complement_of == {}


class TestWithComplements:
    def test_a_tick_prices_its_leg_and_the_complement(self):
        assert with_complements([1], 0.1, {1: 2, 2: 1}) == [(1, 0.1), (2, 0.9)]

    def test_the_complement_is_rounded_to_the_stored_precision(self):
        # 1 - 0.7 is 0.30000000000000004 in binary floating point.
        assert with_complements([1], 0.7, {1: 2, 2: 1})[1] == (2, 0.3)

    def test_an_unpaired_leg_is_priced_exactly_as_before(self):
        assert with_complements([1, 3], 0.42, {}) == [(1, 0.42), (3, 0.42)]

    def test_a_mirror_leg_brings_its_own_complement(self):
        # #9736: a board leg (owner, unpaired) and the binary's Yes leg
        # (mirror) take the tick; only the binary's No leg is complemented.
        assert with_complements([601, 611], 0.235, {611: 612, 612: 611}) == [
            (601, 0.235),
            (611, 0.235),
            (612, 0.765),
        ]

    def test_a_complement_that_is_also_a_target_keeps_the_tick(self):
        assert with_complements([1, 2], 0.3, {1: 2, 2: 1}) == [(1, 0.3), (2, 0.3)]


def _kittle_database(tmp_path):
    engine = _database(tmp_path)
    markets = text(
        "INSERT INTO futures_markets (id, source, external_id, name, status) "
        "VALUES (:i, 'polymarket', :e, 'Kittle 524.5+', 'open')"
    )
    with engine.begin() as conn:
        conn.execute(markets, {"i": KITTLE_MARKET, "e": KITTLE})
        for oid, side, prob in [(KITTLE_YES, "yes", 0.77), (KITTLE_NO, "no", 0.24)]:
            conn.execute(
                insert(FuturesOutcome.__table__).values(
                    id=oid,
                    market_id=KITTLE_MARKET,
                    external_id=f"{KITTLE}_{side}",
                    name=side.title(),
                    current_probability=prob,
                )
            )
    return engine


def _open_rows():
    return (
        [*OPEN_MARKET_ROWS, (KITTLE_MARKET, [YES_TOKEN, NO_TOKEN], None, None)],
        [
            *OPEN_OUTCOME_ROWS,
            (KITTLE_YES, KITTLE_MARKET, f"{KITTLE}_yes", False),
            (KITTLE_NO, KITTLE_MARKET, f"{KITTLE}_no", False),
        ],
    )


def _trade(token, price, size):
    return json.dumps(
        {
            "event_type": "last_trade_price",
            "asset_id": token,
            "price": price,
            "size": size,
        }
    )


class TestTheConsumer:
    async def test_the_kittle_sell_moves_both_legs(self, monkeypatch, tmp_path):
        """THE REGRESSION. Before this, the 20-share No sell at 0.10 wrote No
        0.10 beside a Yes still reading 0.77 (the served 77 / 10)."""
        engine = _kittle_database(tmp_path)
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token({NO_TOKEN: [(0.0, _trade(NO_TOKEN, "0.10", "20"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert stats["errors"] == 0
        assert _stored(engine, KITTLE_NO) == pytest.approx(0.10)
        assert _stored(engine, KITTLE_YES) == pytest.approx(0.90)
        assert stats["open_contract_legs_complemented"] == 2

    async def test_a_book_tick_on_the_yes_token_prices_the_no_leg(
        self, monkeypatch, tmp_path
    ):
        engine = _kittle_database(tmp_path)
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token({YES_TOKEN: [(0.0, _tick(YES_TOKEN, "0.74", "0.79"))]}),
        )
        await _drive(monkeypatch, rig)

        assert _stored(engine, KITTLE_YES) == pytest.approx(0.765)
        assert _stored(engine, KITTLE_NO) == pytest.approx(0.235)

    async def test_a_leftover_trade_still_prices_neither_leg(
        self, monkeypatch, tmp_path
    ):
        """#9733's rule runs first: a 2-share print is not a price on either
        side."""
        engine = _kittle_database(tmp_path)
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token({NO_TOKEN: [(0.0, _trade(NO_TOKEN, "0.10", "2"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert _stored(engine, KITTLE_NO) == pytest.approx(0.24)
        assert _stored(engine, KITTLE_YES) == pytest.approx(0.77)
        assert stats["trades_below_min_order"] == 1

    async def test_a_single_leg_future_is_untouched(self, monkeypatch, tmp_path):
        """Control: an open future with one leg (market 7) takes its tick and
        nothing else moves."""
        engine = _kittle_database(tmp_path)
        rig = _Rig(
            engine,
            GAME_SLATE,
            _open_rows(),
            _frames_by_token({"711": [(0.0, _tick("711"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert _stored(engine, 71) == pytest.approx(0.42)
        assert _stored(engine, KITTLE_YES) == pytest.approx(0.77)
        assert _stored(engine, KITTLE_NO) == pytest.approx(0.24)
        assert stats["open_contract_prices_written"] == 1
