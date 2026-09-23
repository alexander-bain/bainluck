"""#8296 — the chart's column at an instant is the FIELD, not the legs that moved.

WHAT A READER SAW. ``/futures/59698965`` (*KBO Korean Series Champion*) printed
**LG Twins 37%** in its hero and ended the same line at **47%** in the
Probability Trend directly below, both stamped 2026-09-23T21:50:32Z, every leg
off by the same 1.27 (found by discover/445 in a D48 shop).

``futures_odds_snapshots`` is de-duplicated at write time, so the rows stamped
21:50:32 were the 7 legs whose price moved. Samsung, Kia and NC had not moved
since 9/21-9/23. The partial column summed to 0.89, under the #23 squeeze's
threshold, so the chart printed it RAW, while the hero divided every leg's
standing price by the whole board's 1.268.

The values below are the production rows for that board (read-only db-query,
2026-09-23 22:1xZ) and the hero `/api/futures/59698965` served the same minute.
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

LG, KT, SAMSUNG, NC, KIA = 231037711, 231037713, 231037714, 232071072, 232071070
SSG, HANWHA, DOOSAN, LOTTE, KIWOOM = 231037715, 231037716, 231037712, 231037718, 231037717

T_FINAL = datetime(2026, 9, 23, 21, 50, 32, 597561, tzinfo=timezone.utc)

#: Legs that wrote a row at the final instant — the ones that MOVED.
_MOVED_AT_FINAL = {
    LG: 0.47, KT: 0.285, SSG: 0.0505, HANWHA: 0.04, DOOSAN: 0.03, LOTTE: 0.016,
}
#: Each unmoved leg's LAST row, and when it was written.
_LAST_ROW = {
    SAMSUNG: (datetime(2026, 9, 21, 1, 32, 23, tzinfo=timezone.utc), 0.16),
    NC: (datetime(2026, 9, 21, 14, 54, 36, tzinfo=timezone.utc), 0.1115),
    KIA: (datetime(2026, 9, 23, 1, 50, 55, tzinfo=timezone.utc), 0.105),
    # Graded LOST (`resolution_source='api_settlement'`) at 17:36Z; its last
    # Polymarket row, 0.01, predates that and must not be carried past it.
    KIWOOM: (datetime(2026, 9, 23, 9, 31, 5, tzinfo=timezone.utc), 0.01),
}

#: What the hero served for the same board the same minute.
_HERO = {LG: 0.371, KT: 0.225, SAMSUNG: 0.126, NC: 0.088, KIA: 0.083}
#: What the Probability Trend drew at the final instant before this fix.
_CHART_BEFORE = {LG: 0.47, KT: 0.285}


def _raw_by_time():
    raw: dict = {}
    for oid, (stamp, value) in _LAST_ROW.items():
        raw.setdefault(stamp, {}).setdefault("polymarket", {})[oid] = value
    raw[T_FINAL] = {"polymarket": dict(_MOVED_AT_FINAL)}
    return raw


class TestTheCarry:
    def test_an_unmoved_leg_stands_at_its_last_quote(self):
        completed = carry_forward_quotes(_raw_by_time(), do_not_carry={KIWOOM})
        column = completed[T_FINAL]["polymarket"]
        assert column[SAMSUNG] == 0.16
        assert column[NC] == 0.1115
        assert column[KIA] == 0.105
        assert column[LG] == 0.47

    def test_a_graded_leg_is_not_carried(self):
        completed = carry_forward_quotes(_raw_by_time(), do_not_carry={KIWOOM})
        assert KIWOOM not in completed[T_FINAL]["polymarket"]
        # ...but it keeps its own row, exactly as before.
        own_stamp = _LAST_ROW[KIWOOM][0]
        assert completed[own_stamp]["polymarket"][KIWOOM] == 0.01

    def test_an_observed_row_beats_a_carried_one(self):
        t1 = T_FINAL - timedelta(hours=2)
        raw = {t1: {"polymarket": {LG: 0.42, KT: 0.33}}, T_FINAL: {"polymarket": {LG: 0.47}}}
        column = carry_forward_quotes(raw)[T_FINAL]["polymarket"]
        assert column == {LG: 0.47, KT: 0.33}

    def test_a_book_absent_at_an_instant_is_not_resurrected(self):
        t1 = T_FINAL - timedelta(hours=2)
        raw = {
            t1: {"draftkings": {LG: 0.5, KT: 0.5}, "fanduel": {LG: 0.5, KT: 0.5}},
            T_FINAL: {"draftkings": {LG: 0.6}},
        }
        completed = carry_forward_quotes(raw)
        assert set(completed[T_FINAL]) == {"draftkings"}
        assert completed[T_FINAL]["draftkings"] == {LG: 0.6, KT: 0.5}

    def test_the_input_is_not_mutated(self):
        raw = _raw_by_time()
        before = {t: {b: dict(c) for b, c in books.items()} for t, books in raw.items()}
        carry_forward_quotes(raw, do_not_carry={KIWOOM})
        assert raw == before


class TestTheServedScale:
    def _final(self, raw):
        return devigged_consensus_by_time(raw, mutually_exclusive=True)[T_FINAL]

    def test_the_fixture_really_does_reproduce_the_defect(self):
        """Without the carry the partial column prints raw: LG 47%."""
        point = self._final(_raw_by_time())
        for oid, before in _CHART_BEFORE.items():
            assert point[oid] == pytest.approx(before, abs=5e-4)

    def test_the_chart_ends_where_the_hero_is(self):
        point = self._final(carry_forward_quotes(_raw_by_time(), do_not_carry={KIWOOM}))
        for oid, hero in _HERO.items():
            assert point[oid] == pytest.approx(hero, abs=6e-4), (
                f"outcome {oid}: chart {point[oid]} vs hero {hero} — the chart's "
                "last instant is not the hero's column (#8296)"
            )

    def test_carrying_the_graded_leg_would_miss_the_hero(self):
        """Why `do_not_carry` exists: Kiwoom's stale 0.01 inflates the divisor."""
        point = self._final(carry_forward_quotes(_raw_by_time()))
        assert point[LG] == pytest.approx(0.3678, abs=5e-4)
        assert point[LG] != pytest.approx(_HERO[LG], abs=6e-4)


class TestTheCarryIsActuallyWired:
    """The helper is inert unless `/history` calls it (#7747's lesson)."""

    @staticmethod
    def _outcome(oid, prob, *, last_updated, graded_lost=False):
        return SimpleNamespace(
            id=oid,
            name=f"Leg {oid}",
            team_id=None,
            probability_change_24h=None,
            current_probability=prob,
            current_yes_bid=prob,
            current_yes_ask=prob,
            resolution_source="api_settlement" if graded_lost else None,
            is_winner=False if graded_lost else None,
            last_updated=last_updated,
            external_id=f"0xkbo{oid}",
        )

    @staticmethod
    def _market(outcomes):
        return SimpleNamespace(
            id=59698965,
            name="KBO Korean Series Champion (2026)",
            source="polymarket",
            market_type="field",
            external_id="0xkbo",
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

    async def _history(self, *, graded_kiwoom=True):
        now = datetime.now(timezone.utc)
        shift = now - timedelta(minutes=5) - T_FINAL

        def row(oid, stamp, value):
            return SimpleNamespace(
                outcome_id=oid, bookmaker="polymarket", probability=value,
                yes_bid=value, yes_ask=value, last_price=value,
                captured_at=stamp + shift,
            )

        rows = [row(oid, T_FINAL, v) for oid, v in _MOVED_AT_FINAL.items()]
        rows += [row(oid, stamp, v) for oid, (stamp, v) in _LAST_ROW.items()]
        rows.sort(key=lambda r: r.captured_at)

        outcomes = [
            self._outcome(oid, v, last_updated=T_FINAL + shift)
            for oid, v in _MOVED_AT_FINAL.items()
        ] + [
            self._outcome(
                oid, 0.0 if oid == KIWOOM and graded_kiwoom else v,
                last_updated=stamp + shift,
                graded_lost=(oid == KIWOOM and graded_kiwoom),
            )
            for oid, (stamp, v) in _LAST_ROW.items()
        ]
        payload = await futures_route.get_futures_history(
            59698965,
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
        served = await self._history()
        assert served[LG] == pytest.approx(_HERO[LG], abs=6e-4), (
            f"/history served LG at {served[LG]} under a hero of {_HERO[LG]} — "
            "the handler squeezed the moved legs alone (#8296)"
        )
        assert served[KT] == pytest.approx(_HERO[KT], abs=6e-4)

    @pytest.mark.asyncio
    async def test_the_graded_set_reaches_the_carry(self):
        """Sever `do_not_carry` in the route and LG lands at 36.8%, not 37.1%."""
        served = await self._history()
        assert served[LG] != pytest.approx(0.3678, abs=2e-4)


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self


class _Session:
    """Answers each ``execute`` from a queue; the last entry repeats (#7747's rig)."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]
