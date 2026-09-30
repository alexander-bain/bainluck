"""#9765 — a leg whose price was CLEARED stops being carried at the instant it was cleared.

WHAT A READER SAW. ``/golf`` at 390px, 2026-09-30 ~08:15Z, *Alfred Dunhill Links
Championship*: the hero printed **Matt Fitzpatrick 10%** and the Probability Trend
one screen below printed him at **6.6%**. Every line on the chart was the hero's
number divided by 1.587.

#8296's carry reads "no row means unchanged", which is what the write-time dedup
means. It is false for a price that went AWAY: DataGolf's withdrawal null-out
(``tasks/datagolf.py``) sets ``current_probability = None`` and writes no row, so
63 dropped golfers were carried at their last quotes (sum 0.5876) into every later
column. The clearing write advances ``price_changed_at``; that stamp bounds the carry.

Values are the production rows for board 62904927 (read-only db-query,
2026-09-30 09:1xZ): all 63 cleared legs last wrote a row at 2026-09-28 00:37:20Z,
were last confirmed (``valid_until``) at 17:38:08Z and were cleared
(``price_changed_at``) at 19:09:06Z; the 168 priced legs sum to 0.99932.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.utils.futures_history_basis import (
    carry_forward_quotes,
    devigged_consensus_by_time,
)
from tests.test_history_column_is_the_whole_field_8296 import _Result, _Session

BOOK = "datagolf_model"
FITZ, FLEET, MACI, FIELD, DROPPED = 1, 2, 3, 4, 5

T_SEED = datetime(2026, 9, 28, 0, 37, 20, tzinfo=timezone.utc)
T_CLEARED = datetime(2026, 9, 28, 19, 9, 6, tzinfo=timezone.utc)
T_FINAL = datetime(2026, 9, 29, 21, 8, 11, tzinfo=timezone.utc)

#: The priced board, collapsed: three named golfers plus the other 165 as one leg
#: holding the remainder of 0.99932 (the #23 squeeze reads only the column's sum).
_PRICED = {FITZ: 0.10435, FLEET: 0.080917, MACI: 0.0638}
_PRICED[FIELD] = round(0.99932 - sum(_PRICED.values()), 6)
#: The 63 dropped golfers, collapsed the same way.
_DROPPED_SUM = 0.587615

#: Hero `/api/futures/62904927` and the chart before this fix, same board.
_HERO = {FITZ: 0.10435, FLEET: 0.080917, MACI: 0.0638}
_CHART_BEFORE = {FITZ: 0.0658, FLEET: 0.0510, MACI: 0.0402}


def _raw_by_time():
    """Everyone quoted at T_SEED; only the three named golfers moved at T_FINAL."""
    seed = {oid: v * 0.9 for oid, v in _HERO.items()}
    seed[FIELD] = _PRICED[FIELD]
    seed[DROPPED] = _DROPPED_SUM
    return {
        T_SEED: {BOOK: seed},
        T_FINAL: {BOOK: dict((oid, _PRICED[oid]) for oid in (FITZ, FLEET, MACI))},
    }


def _final(raw):
    return devigged_consensus_by_time(raw, mutually_exclusive=True)[T_FINAL]


class TestTheCarryBound:
    def test_a_cleared_leg_is_not_carried_past_its_clearing(self):
        completed = carry_forward_quotes(
            _raw_by_time(), carry_until={DROPPED: T_CLEARED}
        )
        assert DROPPED not in completed[T_FINAL][BOOK]
        # An unmoved priced leg is still carried — #8296 is untouched.
        assert completed[T_FINAL][BOOK][FIELD] == _PRICED[FIELD]

    def test_a_cleared_leg_is_carried_up_to_its_clearing(self):
        """Before it was cleared it WAS in the field, so the column holds it."""
        t_mid = T_CLEARED - timedelta(hours=1)
        raw = _raw_by_time()
        raw[t_mid] = {BOOK: {FITZ: 0.1}}
        raw[T_CLEARED] = {BOOK: {FITZ: 0.1}}
        completed = carry_forward_quotes(raw, carry_until={DROPPED: T_CLEARED})
        assert completed[t_mid][BOOK][DROPPED] == _DROPPED_SUM
        assert completed[T_CLEARED][BOOK][DROPPED] == _DROPPED_SUM

    def test_its_own_rows_are_kept(self):
        completed = carry_forward_quotes(
            _raw_by_time(), carry_until={DROPPED: T_SEED - timedelta(days=1)}
        )
        assert completed[T_SEED][BOOK][DROPPED] == _DROPPED_SUM

    def test_no_bound_is_the_8296_carry(self):
        completed = carry_forward_quotes(_raw_by_time())
        assert completed[T_FINAL][BOOK][DROPPED] == _DROPPED_SUM


class TestTheServedScale:
    def test_the_fixture_really_does_reproduce_the_defect(self):
        point = _final(carry_forward_quotes(_raw_by_time()))
        for oid, before in _CHART_BEFORE.items():
            assert point[oid] == pytest.approx(before, abs=5e-4)

    def test_the_chart_ends_where_the_hero_is(self):
        point = _final(
            carry_forward_quotes(_raw_by_time(), carry_until={DROPPED: T_CLEARED})
        )
        for oid, hero in _HERO.items():
            assert point[oid] == pytest.approx(hero, abs=6e-4), (
                f"outcome {oid}: chart {point[oid]} vs hero {hero} — a cleared leg "
                "is still in the chart's divisor (#9765)"
            )


class TestTheBoundIsWired:
    """The helper argument is inert unless `/history` hands it the cleared legs."""

    @staticmethod
    def _outcome(oid, prob, *, changed_at, last_updated):
        return SimpleNamespace(
            id=oid,
            name=f"Golfer {oid}",
            team_id=None,
            probability_change_24h=None,
            current_probability=prob,
            current_yes_bid=None,
            current_yes_ask=None,
            resolution_source=None,
            is_winner=None,
            last_updated=last_updated,
            price_changed_at=changed_at,
            external_id=f"dg_{oid}",
        )

    @staticmethod
    def _market(outcomes):
        return SimpleNamespace(
            id=62904927,
            name="Alfred Dunhill Links Championship Winner",
            source="datagolf",
            market_type="field",
            external_id="dg_dunhill",
            status="open",
            mutually_exclusive=True,
            outcomes=outcomes,
            resolution_date=None,
            market_metadata={
                "shape": {
                    "shape": "field",
                    "exhaustive": True,
                    "expected_winners": 1,
                    "outcome_relation": "competitors",
                    "confidence": "high",
                },
            },
        )

    async def _served(self, *, dropped_changed_at):
        now = datetime.now(timezone.utc)
        shift = now - timedelta(minutes=5) - T_FINAL
        rows = []
        for stamp, books in _raw_by_time().items():
            for oid, value in books[BOOK].items():
                rows.append(SimpleNamespace(
                    outcome_id=oid, bookmaker=BOOK, probability=value,
                    yes_bid=None, yes_ask=None, last_price=None,
                    captured_at=stamp + shift,
                ))
        rows.sort(key=lambda r: r.captured_at)
        outcomes = [
            self._outcome(oid, v, changed_at=T_FINAL + shift, last_updated=now)
            for oid, v in _PRICED.items()
        ] + [
            self._outcome(
                DROPPED, None,
                changed_at=(dropped_changed_at + shift) if dropped_changed_at else None,
                last_updated=T_CLEARED + shift,
            )
        ]
        payload = await futures_route.get_futures_history(
            62904927,
            outcome_id=None,
            hours=168,
            top_n=50,
            champion=None,
            db=_Session(
                _Result(value=self._market(outcomes)), _Result(rows=()), _Result(rows=rows)
            ),
        )
        return {
            entry["outcome_id"]: entry["history"][-1]["probability"]
            for entry in payload["outcomes"]
            if entry["history"]
        }

    @pytest.mark.asyncio
    async def test_the_served_chart_ends_where_the_hero_is(self):
        served = await self._served(dropped_changed_at=T_CLEARED)
        off = {
            oid: (served.get(oid), hero)
            for oid, hero in _HERO.items()
            if served.get(oid) != pytest.approx(hero, abs=6e-4)
        }
        assert not off, f"lines ending off the hero (served, hero): {off}"

    @pytest.mark.asyncio
    async def test_a_cleared_leg_with_no_stamp_is_not_carried(self):
        served = await self._served(dropped_changed_at=None)
        assert served[FITZ] == pytest.approx(_HERO[FITZ], abs=6e-4)
