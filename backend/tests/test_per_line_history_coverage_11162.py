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
from app.utils.futures_chart_series import FINE_TIER_HOURS, candle_calls, clob_calls

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


# ── #11162 F1 (lane1b review of 5538e89a0a): holes the DECLARED plan can fill ──

def _every(minutes: float, *, start_h: float, end_h: float = 0.0, offset_s: float = 0.0):
    out, t = [], _NOW - timedelta(hours=start_h) + timedelta(seconds=offset_s)
    stop = _NOW - timedelta(hours=end_h)
    while t <= stop:
        out.append(t)
        t += timedelta(minutes=minutes)
    return out


def _recent_short_gap():
    """24h: Over every 2 min (721), Under every 6h (5) — holes the fine tier fills."""
    over = _every(2, start_h=24)
    under = [t for t in over if (t - over[0]).total_seconds() % (6 * 3600) == 0]
    return over, under


def _week_eight_hour_holes():
    """1W: Over every 5 min, Under every 8h — under the 12h/24h whole-life grain."""
    over = _every(5, start_h=168)
    under = [t for t in over if (t - over[0]).total_seconds() % (8 * 3600) == 0]
    return over, under


def _month_hourly_tier_holes():
    """1M, Kalshi: Over hourly; Under every 20h from day 30 to day 7 (inside the
    declared 31-day HOURLY tier, under the 24h whole-life grain), then every poll."""
    over = _every(60, start_h=720)
    under = [
        t for t in over
        if t >= _NOW - timedelta(hours=168)
        or (t - over[0]).total_seconds() % (20 * 3600) == 0
    ]
    return over, under


async def _read(reader, rows, hours, source):
    db = _Session(_market(source=source), rows)
    if reader == "history":
        return await futures_route.get_futures_history(
            _MARKET_ID, outcome_id=None, hours=hours, top_n=10, champion=None,
            db=db, history_range=None,
        )
    return await futures_route.get_probability_timeline(
        market_id=_MARKET_ID, top=10, hours=hours, db=db,
        representation=futures_route.REPRESENTATION_SOURCE, history_range=None,
    )


_SEAMS = [
    pytest.param(_recent_short_gap, 24, "polymarket", id="24h-poly-6h-holes"),
    pytest.param(_recent_short_gap, 24, "kalshi", id="24h-kalshi-6h-holes"),
    pytest.param(_week_eight_hour_holes, 168, "polymarket", id="1w-poly-8h-holes"),
    pytest.param(_month_hourly_tier_holes, 720, "kalshi", id="1m-kalshi-20h-holes-in-31d-tier"),
]

_JITTER_CONTROLS = [
    pytest.param(lambda: (_every(2, start_h=24), _every(2, start_h=24)), 24, "polymarket",
                 id="2min-together-24h"),
    pytest.param(lambda: (_every(2, start_h=24), _every(2, start_h=24, offset_s=1)), 24,
                 "polymarket", id="2min-offset-1s-24h"),
    # Two legs of one HOURLY poll written a second apart: with a fine-tier grain
    # an exact-instant test would read every hour as absent on the 1M band.
    pytest.param(lambda: (_every(60, start_h=720), _every(60, start_h=720, offset_s=1)), 720,
                 "kalshi", id="hourly-offset-1s-1m-kalshi"),
    pytest.param(lambda: (_every(60, start_h=720), _every(60, start_h=720, offset_s=1)), 720,
                 "polymarket", id="hourly-offset-1s-1m-poly"),
    # A slow poll's legs two minutes apart — one live-poll interval, still one poll.
    pytest.param(lambda: (_every(60, start_h=720), _every(60, start_h=720, offset_s=120)), 720,
                 "kalshi", id="hourly-offset-2min-1m-kalshi"),
]


class TestHolesTheDeclaredPlanCanFill:
    @pytest.mark.parametrize("shape,hours,source", _SEAMS)
    def test_the_old_gates_are_blind_to_each_shape(self, shape, hours, source):
        over, under = shape()
        assert len(over) + len(under) >= futures_route._VENUE_FILL_THIN_CAPTURES
        assert gmh.captures_are_coarse([over, under], window_hours=hours) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", ["history", "timeline"])
    @pytest.mark.parametrize("shape,hours,source", _SEAMS)
    async def test_each_shape_asks_once_on_both_readers(
        self, monkeypatch, reader, shape, hours, source
    ):
        state = _install(monkeypatch)
        payload = await _read(reader, _rows(*shape()), hours, source)

        assert payload["venue_history"]["fill"] == "requested", payload["venue_history"]
        bkey, ckey = _hour_keys(state.redis)
        assert state.redis.kv[bkey] == 1 and state.redis.kv[ckey] == 1
        assert len(state.dispatch.calls) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reader", ["history", "timeline"])
    @pytest.mark.parametrize("shape,hours,source", _JITTER_CONTROLS)
    async def test_legs_of_one_poll_are_never_each_others_absence(
        self, monkeypatch, reader, shape, hours, source
    ):
        state = _install(monkeypatch)
        payload = await _read(reader, _rows(*shape()), hours, source)

        assert payload["venue_history"]["fill"] == "chart_not_thin", payload["venue_history"]
        assert state.redis.kv == {} and state.dispatch.calls == []


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

#: The fixture market's age (`_market().created_at`), so these are the SAME
#: declared calls the route reads for it.
_LIFETIME_H = _SPAN_H + 24
_POLY = gmh.declared_hole_grains("polymarket", _LIFETIME_H)
_KALSHI = gmh.declared_hole_grains("kalshi", _LIFETIME_H)


def _absent(lines, *, fillable=(_OVER, _UNDER), graded=(), grains=_POLY):
    return gmh.leg_absent_beside_dense_sibling(
        lines, fillable_lines=fillable, graded_lines=graded,
        min_reference=futures_route._VENUE_FILL_THIN_CAPTURES,
        declared_grains=grains, window_end=_NOW,
    )


class TestTheRule:
    def test_the_grains_are_read_off_the_fills_own_declared_plan(self):
        fine = timedelta(hours=FINE_TIER_HOURS).total_seconds()
        assert _KALSHI == [
            (fine, candle_calls(_LIFETIME_H)[0].period_interval * 60.0),
            (timedelta(days=31).total_seconds(), 3600.0),
            (None, 86400.0),
        ]
        # Polymarket's hourly tier is a NAMED range with no declared lookback:
        # not counted, so the whole-life 12-hourly grain stands past the fine reach.
        assert [c.interval for c in clob_calls(_LIFETIME_H)] == ["1d", "1m", "max"]
        assert _POLY == [(fine, 60.0), (None, 43200.0)]
        # A market younger than the hourly tier's floor gets no hourly tier.
        assert gmh.declared_hole_grains("kalshi", 24) == [(fine, 60.0), (None, 86400.0)]
        assert gmh.declared_hole_grains("odds_api", _LIFETIME_H) is None
        assert gmh.declared_hole_grains(None, _LIFETIME_H) is None

    def test_an_unsupported_source_asks_nothing(self):
        over, under = _dense_sibling_sparse_leg()
        assert _absent({_OVER: over, _UNDER: under}, grains=None) is False

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

    def test_a_hole_is_judged_at_the_grain_the_plan_declares_where_it_sits(self):
        """#11162 F1. Over hourly for 25 days; Under every 8h until the last 144h,
        then on every poll.

        Polymarket declares nothing finer than 12-hourly past the fine reach, so
        an 8h hole there is one no call can put a bucket into. Kalshi declares a
        31-day HOURLY tier, so the same holes are fillable — the rule must tell
        the two apart, not read both at one grain.
        """
        over = _instants(spacing_h=1)
        recent = _NOW - timedelta(hours=FINE_TIER_HOURS)
        under = [t for i, t in enumerate(over) if t >= recent or i % 8 == 0]
        assert _absent({_OVER: over, _UNDER: under}, grains=_POLY) is False
        assert _absent({_OVER: over, _UNDER: under}, grains=_KALSHI) is True

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
