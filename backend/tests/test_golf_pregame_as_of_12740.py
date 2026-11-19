"""#12740 step 2 — golf "Pregame" is the blend as of the first tee, not the first reading.

The golf page's "Pregame" used to print `opening_probability`, the first reading
ever stored: weeks early, or mid-tournament for a market picked up late. These pin
the replacement: the SAME pipeline as the live number (`_build_one_tournament`)
run over each outcome's reading in force at the cutoff, the cutoff itself
(recorded first round-1 play, else midnight UTC of the start date), and the
"empty, never a guess" cases. Clocks are a fixed anchor far from today.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import golf as golf_route

NOW = datetime(2031, 4, 12, 18, 0, tzinfo=timezone.utc)
START = "2031-04-10T00:00:00+00:00"
FIRST_PLAY = datetime(2031, 4, 10, 11, 42, tzinfo=timezone.utc)

_OID = iter(range(1, 10_000))


def _outcome(name, prob):
    return SimpleNamespace(
        id=next(_OID), name=name, current_probability=prob,
        current_yes_bid=round(prob - 0.005, 4), current_yes_ask=round(prob + 0.005, 4),
        opening_probability=0.99,  # the old "Pregame": must never be served now
        probability_change_24h=None, is_winner=None, resolution_source=None,
    )


def _market(mid, source, external_id, outcomes):
    return SimpleNamespace(
        id=mid, name="The Masters Tournament Winner", source=source,
        external_id=external_id, outcomes=outcomes,
        commence_time=datetime(2031, 4, 10, tzinfo=timezone.utc),
        resolution_date=datetime(2031, 4, 14, tzinfo=timezone.utc),
        status="open", llm_sport_category="golf", market_tier=1,
        market_metadata=None, mutually_exclusive=True,
    )


def _field():
    """Now: Scheffler 40%, McIlroy 35%, Schauffele 25% (one venue)."""
    return [_outcome("Scottie Scheffler", 0.40), _outcome("Rory McIlroy", 0.35),
            _outcome("Xander Schauffele", 0.25)]


class _FakeDB:
    def __init__(self, snaps):
        self.snaps = snaps  # {outcome_id: (probability, yes_bid, yes_ask)}
        self.calls = []

    async def execute(self, _sql, params):
        self.calls.append(params)
        return [SimpleNamespace(outcome_id=oid, probability=p, yes_bid=b, yes_ask=a)
                for oid, (p, b, a) in self.snaps.items() if oid in params["outcome_ids"]]


class _FakeRedis:
    def __init__(self, values):
        self.values = values

    def get(self, key):
        return self.values.get(key)


def _tournament(markets, *, start=START):
    entry = golf_route._build_one_tournament("masters", markets, {})
    assert entry is not None
    entry["start_date"] = start
    return entry


def _by_name(entry):
    return {g["name"]: g for g in entry.get("_all_golfers") or entry["golfers"]}


async def _attach(monkeypatch, entry, markets, snaps, redis_values=None, now=NOW):
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: _FakeRedis(redis_values or {}))
    db = _FakeDB(snaps)
    await golf_route._attach_pregame(db, [entry], {"masters": markets}, now)
    return db


def _snap(p):
    return (p, round(p - 0.005, 4), round(p + 0.005, 4))


@pytest.mark.asyncio
async def test_pregame_is_the_blend_of_the_readings_at_the_first_tee(monkeypatch):
    field = _field()
    markets = [_market(1, "polymarket", "pm-masters", field)]
    entry = _tournament(markets)
    # At the first tee: Scheffler 50%, McIlroy 30%, Schauffele 20%.
    db = await _attach(monkeypatch, entry, markets,
                       {field[0].id: _snap(0.50), field[1].id: _snap(0.30), field[2].id: _snap(0.20)})
    g = _by_name(entry)
    assert g["Scottie Scheffler"]["pregame_probability"] == pytest.approx(0.50, abs=1e-3)
    assert g["Rory McIlroy"]["pregame_probability"] == pytest.approx(0.30, abs=1e-3)
    assert g["Scottie Scheffler"]["probability"] == pytest.approx(0.40, abs=1e-3)  # Now untouched
    assert all(x["opening_probability"] != x["pregame_probability"] for x in g.values())
    assert entry["pregame_cutoff_basis"] == "start_date"
    assert entry["pregame_as_of"] == "2031-04-10T00:00:00+00:00"
    assert db.calls[0]["cutoff"] == datetime(2031, 4, 10, tzinfo=timezone.utc)
    assert db.calls[0]["floor"] == db.calls[0]["cutoff"] - golf_route.PREGAME_READING_MAX_AGE


@pytest.mark.asyncio
async def test_the_recorded_first_round_one_play_is_the_cutoff(monkeypatch):
    field = _field()
    markets = [
        _market(1, "polymarket", "pm-masters", field),
        _market(2, "datagolf", "datagolf:pga:14:win",
                [_outcome("Scottie Scheffler", 0.42), _outcome("Rory McIlroy", 0.33),
                 _outcome("Xander Schauffele", 0.25)]),
    ]
    entry = _tournament(markets)
    db = await _attach(monkeypatch, entry, markets, {field[0].id: _snap(0.5)},
                       redis_values={"bainluck:golf:first_play:pga:14": FIRST_PLAY.isoformat()})
    assert entry["pregame_cutoff_basis"] == "first_play"
    assert entry["pregame_as_of"] == FIRST_PLAY.isoformat()
    assert db.calls[0]["cutoff"] == FIRST_PLAY


@pytest.mark.asyncio
async def test_before_the_first_tee_pregame_is_empty_and_nothing_is_read(monkeypatch):
    field = _field()
    markets = [_market(1, "polymarket", "pm-masters", field)]
    entry = _tournament(markets, start="2031-04-20T00:00:00+00:00")
    db = await _attach(monkeypatch, entry, markets, {field[0].id: _snap(0.5)})
    assert db.calls == []
    assert entry["pregame_as_of"] is None
    assert all(g["pregame_probability"] is None for g in _by_name(entry).values())


@pytest.mark.asyncio
async def test_a_golfer_nobody_priced_before_the_tee_has_no_pregame(monkeypatch):
    field = _field()
    markets = [_market(1, "polymarket", "pm-masters", field)]
    entry = _tournament(markets)
    await _attach(monkeypatch, entry, markets, {field[0].id: _snap(0.5), field[1].id: _snap(0.3)})
    g = _by_name(entry)
    assert g["Xander Schauffele"]["pregame_probability"] is None
    assert g["Scottie Scheffler"]["pregame_probability"] is not None


@pytest.mark.asyncio
async def test_no_readings_at_all_leaves_the_tournament_without_pregame(monkeypatch):
    field = _field()
    markets = [_market(1, "polymarket", "pm-masters", field)]
    entry = _tournament(markets)
    await _attach(monkeypatch, entry, markets, {})
    assert entry["pregame_as_of"] is None
    assert all(g["pregame_probability"] is None for g in _by_name(entry).values())


@pytest.mark.asyncio
async def test_the_placeholder_rule_reads_the_as_of_book(monkeypatch):
    """An empty book at the tee is withheld exactly as the live number withholds it."""
    field = _field()
    markets = [_market(1, "polymarket", "pm-masters", field)]
    entry = _tournament(markets)
    empty_book = (0.5, 0.0, 0.999)
    await _attach(monkeypatch, entry, markets,
                  {field[0].id: empty_book, field[1].id: _snap(0.30), field[2].id: _snap(0.20)})
    g = _by_name(entry)
    assert g["Scottie Scheffler"]["pregame_probability"] is None
    assert g["Rory McIlroy"]["pregame_probability"] is not None


def test_as_of_copies_never_carry_the_present():
    real = _outcome("Scottie Scheffler", 0.40)
    real.is_winner = True
    copy = golf_route._AsOfOutcome(real, _snap(0.5))
    assert copy.current_probability == 0.5 and copy.current_yes_bid == 0.495
    assert copy.opening_probability is None and copy.is_winner is None
    assert copy.probability_change_24h is None
    assert copy.name == "Scottie Scheffler" and copy.id == real.id  # the rest delegates
    assert golf_route._AsOfOutcome(real, None).current_probability is None


@pytest.mark.asyncio
async def test_a_pregame_failure_never_costs_the_listing(monkeypatch):
    from tests.test_golf_lotte_one_card_9752 import (
        _CapturedClock, _db, _kalshi_lotte, _polymarket_lotte,
    )

    async def boom(*_a, **_k):
        raise RuntimeError("pregame exploded")

    async def no_schedule():
        return []

    # The LOTTE module's own clock and schedule pins (its autouse fixtures).
    monkeypatch.setattr(golf_route, "datetime", _CapturedClock)
    monkeypatch.setattr("app.routes.golf._get_golf_schedule", no_schedule)
    monkeypatch.setattr(golf_route, "_attach_pregame", boom)
    body = await golf_route.get_golf(_db([_kalshi_lotte(), _polymarket_lotte()]))
    assert body["tournaments"], "the listing must survive a Pregame failure"
