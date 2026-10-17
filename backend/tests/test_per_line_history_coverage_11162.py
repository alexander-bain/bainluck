"""#11162 — a dense sibling must not hide a fillable line that is missing.

PILLARS: TRUTH / FORMATTING. SHIP: a market page can recover a genuinely
available sparse outcome history even when another outcome makes the total point
count look healthy.

WHAT A READER SAW. ``/futures/31519211`` (Devin Vassell 3-pointers O/U 2.5,
Polymarket), All selected, 2026-10-12: the Under line is 17 hourly captures and
then a 908-hour hole; the Over line has 162 captures. The served payload said
``venue_history: {state: cold, fill: chart_not_thin}`` — the bounded background
fill was never even asked. Both existing questions read the chart through its
densest part:

  * the thin gate counts POOLED rows (180 ≥ 20);
  * ``captures_are_coarse`` takes the densest line's median and refuses every
    window the 144-hour fine tier cannot half cover (All, 1M).

This file does not claim the venue still holds that history, or that a fill
repairs 31519211 — only that the existing planner is now ASKED, under its own
claim, budgets and negative cache, when one fillable line is absent where its
sibling was observed.

THE ROUTE ARMS ARE THE SHIP. They call the real ``get_futures_history`` and
``get_probability_timeline`` handlers, the real ``plan_on_demand_fill`` against a
fake Redis, and record the one ``apply_async`` the route makes. On the parent
commit both dense-sibling arms answer ``chart_not_thin`` and enqueue nothing.

WHAT WOULD MAKE THIS FILE VACUOUS — asserted, not trusted
(``TestTheFixturesCarryTheDefect``):

  * if the pooled count fell under 20, the old thin gate would fire and the ship
    arms would be measuring #7351;
  * if ``captures_are_coarse`` said True for the served window, they would be
    measuring #7547;
  * if the adequate control's sibling were not the same density, it could not
    tell a missing line from a sparse market.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes import futures as futures_route
from app.tasks import generic_market_history_fill as fill
from app.utils import generic_market_history as gmh
from app.utils.futures_chart_series import candle_calls, clob_calls

_CONDITION = "0x471297a7d5fb8afb24caf8b69b7e98a032a0804ea405c78ba0d7368b3ea1755c"
_OVER, _UNDER = 143914448, 143914449
_MARKET_ID = 31519211
#: The reader's 1M band — wider than twice the fine tier, so #7547 says no.
_WINDOW_HOURS = 720
#: One sibling capture every four hours across 25 days: 150 instants.
_SPACING_H = 4
_SPAN_H = 600

#: ONE anchor for the whole module. Captures written by one poll share an
#: instant; a per-row ``now()`` would give each leg its own microsecond.
_NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _instants(*, start_h=_SPAN_H, end_h=0, spacing_h=_SPACING_H):
    """Capture instants from `start_h` hours ago to `end_h` hours ago, oldest first."""
    out, h = [], start_h
    while h >= end_h:
        out.append(_NOW - timedelta(hours=h))
        h -= spacing_h
    return out


def _snap(oid, at, prob):
    return SimpleNamespace(
        outcome_id=oid, bookmaker="polymarket", probability=prob,
        yes_bid=round(prob - 0.01, 4), yes_ask=round(prob + 0.01, 4),
        last_price=prob, captured_at=at,
    )


def _rows(over_at, under_at):
    return [_snap(_OVER, t, 0.30) for t in over_at] + [_snap(_UNDER, t, 0.70) for t in under_at]


def _dense_sibling_sparse_leg():
    """Over every 4h for 25 days; Under only for its first 76 hours, then gone.

    The production shape, scaled: one line dense, the other a short run and a
    long hole while its sibling went on being captured.
    """
    over = _instants()
    under = [t for t in over if t <= _NOW - timedelta(hours=_SPAN_H - 76)]
    return over, under


def _materially_gapped_leg():
    """Both lines every 4h, but Under is missing a 15-day stretch in the middle."""
    over = _instants()
    hole_from, hole_to = _NOW - timedelta(hours=480), _NOW - timedelta(hours=120)
    under = [t for t in over if not (hole_from < t < hole_to)]
    return over, under


def _adequate():
    """THE CONTROL: the same sibling, and Under captured beside it every poll."""
    over = _instants()
    return over, list(over)


def _outcome(oid, name, prob, *, is_winner=None):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.external_id = f"{_CONDITION}_{name.lower()}"
    o.current_probability = prob
    o.current_yes_bid = round(prob - 0.01, 4)
    o.current_yes_ask = round(prob + 0.01, 4)
    o.probability_change_24h = None
    o.opening_probability = None
    o.rank = None
    o.team = None
    o.team_id = None
    o.is_winner = is_winner
    o.resolution_source = None
    o.last_updated = _NOW
    o.price_changed_at = None
    return o


def _market(*, source="polymarket"):
    m = MagicMock()
    m.id = _MARKET_ID
    m.name = "Devin Vassell Total 3-Pointers (incl. OT): O/U 2.5"
    m.source = source
    m.external_id = _CONDITION
    m.status = "open"
    m.market_type = "quantity"
    m.mutually_exclusive = True
    m.commence_time = None
    m.resolution_date = None
    m.created_at = _NOW - timedelta(hours=_SPAN_H + 24)
    m.market_metadata = {}
    m.sport = None
    m.outcomes = [_outcome(_OVER, "Over", 0.30), _outcome(_UNDER, "Under", 0.70)]
    return m


class _Result:
    def __init__(self, value=None, rows=()):
        self._value, self._rows = value, list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return None

    def fetchall(self):
        return []


class _Session:
    """First execute is the market, every later one the capture rows."""

    def __init__(self, market, rows):
        self._market, self._rows = market, rows

    async def execute(self, statement, *a, **k):
        if self._market is not None:
            market, self._market = self._market, None
            return _Result(value=market)
        return _Result(rows=self._rows)


class _Redis:
    def __init__(self):
        self.kv: dict = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    def get(self, key):
        return None

    def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    def decr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) - 1
        return self.kv[key]

    def expire(self, key, seconds):
        pass

    def delete(self, key):
        self.kv.pop(key, None)


class _Dispatch:
    def __init__(self):
        self.calls: list = []

    def apply_async(self, *a, **k):
        self.calls.append(k)


def _cold_venue(payload=None):
    venue = futures_route._GenericVenueHistory()
    venue.applicable = True
    venue.state = "cold" if payload is None else "empty"
    venue.payload = payload
    return venue


def _install(mp):
    """The real planner, a fake Redis, and the one dispatch recorded."""
    redis, dispatch = _Redis(), _Dispatch()
    state = SimpleNamespace(redis=redis, dispatch=dispatch, payload=None)

    async def _load(market, outcomes, field_ids, db=None):
        return _cold_venue(state.payload)

    async def _no_withheld(db, market):
        return set()

    mp.setattr(futures_route, "_load_generic_venue_history", _load)
    mp.setattr(futures_route, "_request_path_redis", lambda: redis)
    mp.setattr(futures_route, "_withheld_price_outcome_ids", _no_withheld)
    # By dotted path: the route imports the task from `app.tasks` at call time.
    mp.setattr("app.tasks.fill_generic_market_history", dispatch)
    return state


@pytest.fixture
def rig(monkeypatch):
    return _install(monkeypatch)


async def _history(rows):
    return await futures_route.get_futures_history(
        _MARKET_ID, outcome_id=None, hours=_WINDOW_HOURS, top_n=10, champion=None,
        db=_Session(_market(), rows), history_range=None,
    )


async def _timeline(rows):
    return await futures_route.get_probability_timeline(
        market_id=_MARKET_ID, top=10, hours=_WINDOW_HOURS,
        db=_Session(_market(), rows),
        representation=futures_route.REPRESENTATION_SOURCE, history_range=None,
    )


_READERS = [pytest.param(_history, id="history"), pytest.param(_timeline, id="timeline")]


def _hour_keys(redis):
    hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    return gmh.budget_key(hour), gmh.coarse_budget_key(hour)


# ── The ship: both readers ask the existing planner ─────────────────────────

class TestADenseSiblingNoLongerHidesAMissingLine:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    @pytest.mark.parametrize("shape", [_dense_sibling_sparse_leg, _materially_gapped_leg],
                             ids=["sparse_leg", "gapped_leg"])
    async def test_the_reader_asks_once_under_the_planners_claim_and_coarse_share(
        self, rig, reader, shape
    ):
        payload = await reader(_rows(*shape()))

        block = payload["venue_history"]
        assert block["fill"] == "requested", block
        assert futures_route._LEG_ABSENT_BASIS in block["fill_trigger"]
        # The real planner ran: it holds the market's claim and spent ONE unit of
        # the hour AND one of coarseness's share — never the thin reserve alone.
        bkey, ckey = _hour_keys(rig.redis)
        assert gmh.claim_key(_MARKET_ID) in rig.redis.kv
        assert rig.redis.kv[bkey] == 1 and rig.redis.kv[ckey] == 1
        assert rig.dispatch.calls == [
            {"kwargs": {"market_ids": [_MARKET_ID]}, "queue": "background"}
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    async def test_a_second_read_is_refused_by_the_claim_and_spends_nothing(self, rig, reader):
        rows = _rows(*_dense_sibling_sparse_leg())
        await reader(rows)
        again = await reader(rows)

        assert again["venue_history"]["fill"] == "already_claimed"
        bkey, ckey = _hour_keys(rig.redis)
        assert rig.redis.kv[bkey] == 1 and rig.redis.kv[ckey] == 1
        assert len(rig.dispatch.calls) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    async def test_an_exhausted_coarse_share_refuses_it_and_leaves_the_hour_alone(
        self, rig, reader
    ):
        bkey, ckey = _hour_keys(rig.redis)
        rig.redis.kv[ckey] = fill.COARSE_FILL_CAP
        rig.redis.kv[bkey] = 5

        payload = await reader(_rows(*_dense_sibling_sparse_leg()))

        assert payload["venue_history"]["fill"] == "coarse_hourly_cap"
        assert rig.redis.kv[ckey] == fill.COARSE_FILL_CAP
        assert rig.redis.kv[bkey] == 5
        assert gmh.claim_key(_MARKET_ID) not in rig.redis.kv
        assert rig.dispatch.calls == []


# ── The controls ────────────────────────────────────────────────────────────

class TestWhatMustStillRefuse:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    async def test_adequate_per_line_coverage_is_still_not_thin(self, rig, reader):
        payload = await reader(_rows(*_adequate()))

        assert payload["venue_history"]["fill"] == "chart_not_thin"
        assert futures_route._LEG_ABSENT_BASIS not in (
            payload["venue_history"].get("fill_trigger") or ""
        )
        assert rig.redis.kv == {} and rig.dispatch.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    async def test_an_answered_empty_attempt_is_not_asked_again_on_this_rule(
        self, rig, reader
    ):
        """The venue was asked for this bank and had nothing: the hole stands."""
        rig.payload = {
            "attempted_at": (_NOW - timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 60)).isoformat(),
            "built_at": None, "status": "empty", "outcomes": {}, "stats": {},
        }
        payload = await reader(_rows(*_dense_sibling_sparse_leg()))

        assert payload["venue_history"]["fill"] == "chart_not_thin"
        assert rig.redis.kv == {} and rig.dispatch.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    async def test_a_failed_attempt_answered_nothing_and_stays_eligible(self, rig, reader):
        rig.payload = {
            "attempted_at": (_NOW - timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 60)).isoformat(),
            "built_at": None, "status": "degraded", "outcomes": {},
            "stats": {"fetch_errors": 2},
        }
        payload = await reader(_rows(*_dense_sibling_sparse_leg()))

        assert payload["venue_history"]["fill"] == "requested"


class TestSettlementIsNotCoverage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", _READERS)
    async def test_settlement_rows_beside_a_missing_line_do_not_fill_it(self, rig, reader):
        """A settlement decoration at every sibling instant is still no observation."""
        over, under = _dense_sibling_sparse_leg()
        rows = _rows(over, under) + [
            SimpleNamespace(**{**vars(_snap(_UNDER, t, 1.0)), "bookmaker": "settlement"})
            for t in over if t not in set(under)
        ]
        payload = await reader(rows)

        assert payload["venue_history"]["fill"] == "requested"


class TestBothReadersAgree:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", [_dense_sibling_sparse_leg, _materially_gapped_leg, _adequate])
    async def test_history_and_timeline_reach_one_verdict_per_shape(self, monkeypatch, shape):
        verdicts = []
        for reader in (_history, _timeline):
            with monkeypatch.context() as mp:
                _install(mp)
                verdicts.append((await reader(_rows(*shape())))["venue_history"]["fill"])
        assert verdicts[0] == verdicts[1], verdicts


# ── The pure rule, and the fences it must keep ──────────────────────────────

_POLY_GRAIN = gmh.whole_life_grain_seconds("polymarket")
_KALSHI_GRAIN = gmh.whole_life_grain_seconds("kalshi")


def _absent(lines, *, fillable=(_OVER, _UNDER), graded=(), grain=_POLY_GRAIN):
    return gmh.leg_absent_beside_dense_sibling(
        lines, fillable_lines=fillable, graded_lines=graded,
        min_reference=futures_route._VENUE_FILL_THIN_CAPTURES,
        gap_grain_seconds=grain, window_end=_NOW,
    )


class TestTheRule:
    def test_the_grain_is_read_off_the_fills_own_whole_life_tier(self):
        assert _KALSHI_GRAIN == candle_calls(0)[-1].period_interval * 60 == 86400
        assert _POLY_GRAIN == clob_calls(0)[-1].fidelity * 60 == 43200
        assert gmh.whole_life_grain_seconds("odds_api") is None
        assert gmh.whole_life_grain_seconds(None) is None

    def test_an_unsupported_source_asks_nothing(self):
        over, under = _dense_sibling_sparse_leg()
        assert _absent({_OVER: over, _UNDER: under}, grain=None) is False

    def test_a_line_the_fill_would_not_fetch_is_never_the_absent_one(self):
        over, under = _dense_sibling_sparse_leg()
        assert _absent({_OVER: over, _UNDER: under}, fillable=(_OVER,)) is False

    def test_a_missing_side_with_no_capture_at_all_is_not_this_rule(self):
        over, _ = _dense_sibling_sparse_leg()
        assert _absent({_OVER: over, _UNDER: []}) is False
        assert _absent({_OVER: over}) is False

    def test_a_new_or_quiet_market_has_no_dense_sibling(self):
        """Fewer than the thin gate's 20 on the sibling: nothing hid this line."""
        over = _instants(start_h=60, spacing_h=4)  # 16 instants
        under = over[:3]
        assert len(over) < futures_route._VENUE_FILL_THIN_CAPTURES
        assert _absent({_OVER: over, _UNDER: under}) is False

    def test_a_newly_listed_line_is_not_missing_the_history_before_it_existed(self):
        over = _instants()
        under = [t for t in over if t >= _NOW - timedelta(hours=40)]
        assert _absent({_OVER: over, _UNDER: under}) is False

    def test_a_line_listed_late_that_then_vanished_is_judged_on_its_own_life(self):
        """Present for 40 hours, then gone for 60 while its sibling went on.

        Measured against the life it had — not against the 25 days before it was
        listed, which would dilute a real loss to a tenth and hide it.
        """
        over = _instants()
        under = [t for t in over if _NOW - timedelta(hours=100) <= t <= _NOW - timedelta(hours=60)]
        assert _absent({_OVER: over, _UNDER: under}) is True

    def test_a_graded_lines_tail_is_its_settlement_not_a_loss(self):
        over, under = _dense_sibling_sparse_leg()
        assert _absent({_OVER: over, _UNDER: under}, graded=(_UNDER,)) is False
        assert _absent({_OVER: over, _UNDER: under}) is True

    def test_holes_shorter_than_the_whole_life_grain_are_not_this_rules(self):
        """Under misses every other 4h poll — never a hole a daily tier can fill."""
        over = _instants()
        under = over[::2]
        assert _absent({_OVER: over, _UNDER: under}, grain=_KALSHI_GRAIN) is False

    def test_a_line_on_every_sibling_poll_is_never_absent_however_slow_the_polls(self):
        """Both lines captured together every 12 hours — a slow board, not a loss.

        Each capture is a whole-life grain from the next, so only the instant
        itself says the line was there.
        """
        over = _instants(spacing_h=12)
        assert len(over) >= futures_route._VENUE_FILL_THIN_CAPTURES
        assert _absent({_OVER: over, _UNDER: list(over)}) is False

    def test_repeated_rows_at_one_instant_are_one_observation(self):
        over, under = _dense_sibling_sparse_leg()
        assert _absent({_OVER: over, _UNDER: under * 10}) is True

    def test_a_minority_hole_does_not_fire(self):
        over = _instants()
        under = [t for t in over if not (_NOW - timedelta(hours=200) < t < _NOW - timedelta(hours=100))]
        assert _absent({_OVER: over, _UNDER: under}) is False

    def test_either_line_can_be_the_absent_one(self):
        over, under = _dense_sibling_sparse_leg()
        assert _absent({_OVER: under, _UNDER: over}) is True


class TestTheFixturesCarryTheDefect:
    @pytest.mark.parametrize("shape", [_dense_sibling_sparse_leg, _materially_gapped_leg, _adequate])
    def test_the_old_gates_say_neither_thin_nor_coarse(self, shape):
        over, under = shape()
        assert len(over) + len(under) >= futures_route._VENUE_FILL_THIN_CAPTURES
        assert gmh.captures_are_coarse([over, under], window_hours=_WINDOW_HOURS) is False

    def test_the_control_has_the_same_sibling_as_the_ship(self):
        assert _adequate()[0] == _dense_sibling_sparse_leg()[0] == _materially_gapped_leg()[0]
        assert len(_adequate()[0]) >= futures_route._VENUE_FILL_THIN_CAPTURES
