"""#9343: /economics stops printing two dead prices as live numbers.

Seen on production 2026-09-28 ~08:40Z at 390px (payload `updated_at`
08:25:37Z):

  * MARKETS & INDICES → TODAY'S CLOSE · LIVE printed
    "Will Nasdaq 100 (NDX — 49.5% up". The market is 13849888, *"Will Nasdaq
    100 (NDX) close over $24,000 on the final trading day of December 2026?"*
    (Polymarket 148025): a year-end threshold, not a daily question, and both
    legs were last written 2026-04-29. The venue lists it `active=false` with
    no bid, so 0.495 is a placeholder.
  * TRADE printed "Will a court order a tariff refund? — 99% · Before July
    2026" (112829, `KXTARIFFREFUND-25`) off legs last written 2026-03-05;
    Kalshi's event now answers `markets: []`.

Two arms, each pinned on its own so neither can pass on the other's work:

  A. TODAY'S CLOSE admits only a market that resolves by the next close
     (`_resolves_by_the_next_close`). A matching name that fails it is
     DROPPED, not re-routed into the side list.
  B. A market whose FRESHEST leg is older than `PROVABLY_PURGED_AGE_DAYS` is
     refused page-wide, spotlight included
     (`last_priced_before_the_venue_forgets`).

HOW THESE GUARDS COULD HAVE BEEN VACUOUS

  1. A fixture the old code already refused for another reason (the tariff
     leader is 0.99, near the extreme-probability bar). `TestTheDefectIsInTheSeed`
     re-runs the route with both new gates switched off and requires both
     specimens to be SERVED, so every "gone" below is the new gates' doing.
  2. Arm A hiding behind arm B: the NDX specimen is ALSO ancient, so B alone
     removes it. `TestArmA` re-stamps it fresh, so only the horizon can drop it.
  3. The clock: `get_economics` reads `datetime.now`; it is patched to a
     fixed instant (gotcha #44), and the boundary tests are offsets from the
     constant, never a literal day count.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import economics as econ
from app.routes.economics import _resolves_by_the_next_close, get_economics
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS
from app.utils.market_staleness import last_priced_before_the_venue_forgets

#: The served payload's `updated_at`, 2026-09-28 (a Monday).
FIXED_NOW = datetime(2026, 9, 28, 8, 25, 37, tzinfo=timezone.utc)

TARIFF_STAMP = datetime(2026, 3, 5, 0, 45, 17, tzinfo=timezone.utc)
NDX_STAMP = datetime(2026, 4, 29, 23, 11, 29, tzinfo=timezone.utc)
FRESH = datetime(2026, 9, 28, 3, 31, tzinfo=timezone.utc)


def _outcome(idx, name, prob, stamp):
    return SimpleNamespace(
        id=idx, name=name, current_probability=prob, rank=idx, last_updated=stamp
    )


def _market(mid, source, ext, name, legs, *, resolves, group_id=None):
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=ext,
        outcomes=[_outcome(i, n, p, s) for i, (n, p, s) in enumerate(legs)],
        status="open",
        llm_sport_category="economics",
        group_id=group_id,
        volume=100_000,
        volume_24h=5_000,
        resolution_date=resolves,
    )


# --- production specimens, read from `futures_outcomes` 2026-09-28 ~08:45Z --


def tariff_refund(stamp=TARIFF_STAMP):
    return _market(
        112829, "kalshi", "KXTARIFFREFUND-25", "Will a court order a tariff refund?",
        [
            ("Before July 2026", 0.99, stamp),
            ("Before Apr 1, 2026", 0.985, stamp),
            ("Before 2027", 0.985, stamp),
            ("Before Jan 1, 2026", 0.5, stamp),
        ],
        resolves=datetime(2027, 1, 8, 15, tzinfo=timezone.utc),
    )


def ndx_year_end(stamp=NDX_STAMP):
    return _market(
        13849888, "polymarket",
        "0xd2b1535097b21fa7099183dc0c35d8581716b22043d386f3bc56670f0b8546f9",
        "Will Nasdaq 100 (NDX) close over $24,000 on the final trading day of December 2026?",
        [("Yes", 0.495, stamp), ("No", 0.505, stamp)],
        resolves=datetime(2026, 12, 31, 21, tzinfo=timezone.utc),
        group_id="polymarket:148025",
    )


def spx_daily(resolves=datetime(2026, 9, 28, 20, tzinfo=timezone.utc)):
    return _market(
        62323312, "polymarket", "1079745", "S&P 500 (SPX) Up or Down on September 28?",
        [("Up", 0.29, FRESH), ("Down", 0.71, FRESH)],
        resolves=resolves, group_id="polymarket:1079745",
    )


def dow_daily():
    return _market(
        62323307, "polymarket", "1079750", "Dow Jones (DJIA) Up or Down on September 28?",
        [("Up", 0.94, FRESH), ("Down", 0.06, FRESH)],
        resolves=datetime(2026, 9, 28, 20, tzinfo=timezone.utc),
        group_id="polymarket:1079750",
    )


def trade_sibling():
    """Synthetic healthy trade row: the section must keep what is alive."""
    return _market(
        900001, "kalshi", "KXTRADEDEAL-26", "Will the US sign a trade deal with India in 2026?",
        [("Yes", 0.4, FRESH), ("No", 0.6, FRESH)],
        resolves=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )


def pool(**over):
    base = {
        "tariff": tariff_refund(),
        "ndx": ndx_year_end(),
        "spx": spx_daily(),
        "dow": dow_daily(),
        "trade": trade_sibling(),
    }
    base.update(over)
    return [m for m in base.values() if m is not None]


async def _run(markets, *, now=FIXED_NOW):
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = now
        return await get_economics(db)


def _today_syms(payload):
    return [r["sym"] for r in payload["themes"]["markets"]["today"]]


def _trade_ids(payload):
    return [r.get("market_id") for r in payload["themes"]["trade"]["markets"]]


def _all_market_ids(payload):
    ids = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("market_id", "id") and isinstance(v, int):
                    ids.add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return ids


class TestTheDefectIsInTheSeed:
    """With both new gates off, the fixtures reproduce the production page."""

    @pytest.mark.asyncio
    async def test_both_specimens_are_served_without_the_gates(self):
        with patch.object(econ, "last_priced_before_the_venue_forgets", return_value=False), \
                patch.object(econ, "_resolves_by_the_next_close", return_value=True):
            payload = await _run(pool())
        assert "Will Nasdaq 100 (NDX" in _today_syms(payload)
        assert 112829 in _trade_ids(payload)


class TestTheShip:
    @pytest.mark.asyncio
    async def test_the_nasdaq_year_end_row_leaves_todays_close(self):
        payload = await _run(pool())
        assert not any(s.startswith("Will Nasdaq") for s in _today_syms(payload))

    @pytest.mark.asyncio
    async def test_the_tariff_refund_row_leaves_the_trade_section(self):
        payload = await _run(pool())
        assert 112829 not in _trade_ids(payload)
        assert 112829 not in _all_market_ids(payload)

    @pytest.mark.asyncio
    async def test_the_live_siblings_survive(self):
        payload = await _run(pool())
        assert sorted(_today_syms(payload)) == ["Dow Jones (DJIA)", "S&P 500 (SPX)"]
        assert 900001 in _trade_ids(payload)

    @pytest.mark.asyncio
    async def test_the_spotlight_is_not_handed_a_dead_market(self):
        seen = []

        def capture(markets, **kw):
            seen.extend(m.id for m in markets)
            return []

        with patch.object(econ, "find_cross_source_markets", side_effect=capture):
            await _run(pool())
        assert 112829 not in seen and 13849888 not in seen
        assert 900001 in seen


class TestArmA:
    """The horizon alone: every specimen here carries a fresh stamp."""

    @pytest.mark.asyncio
    async def test_a_fresh_year_end_threshold_is_still_not_todays_close(self):
        payload = await _run(pool(ndx=ndx_year_end(stamp=FRESH)))
        assert not any(s.startswith("Will Nasdaq") for s in _today_syms(payload))

    @pytest.mark.asyncio
    async def test_it_is_dropped_not_rerouted_to_the_side_list(self):
        payload = await _run(pool(ndx=ndx_year_end(stamp=FRESH)))
        assert 13849888 not in _all_market_ids(payload)

    @pytest.mark.asyncio
    async def test_friday_evening_still_shows_mondays_close(self):
        friday = datetime(2026, 9, 25, 21, tzinfo=timezone.utc)
        payload = await _run(pool(dow=None), now=friday)
        assert _today_syms(payload) == ["S&P 500 (SPX)"]

    def test_the_horizon_boundary(self):
        edge = FIXED_NOW + econ._TODAYS_CLOSE_HORIZON
        assert _resolves_by_the_next_close(spx_daily(resolves=edge), FIXED_NOW)
        assert not _resolves_by_the_next_close(
            spx_daily(resolves=edge + timedelta(minutes=1)), FIXED_NOW
        )

    def test_a_market_with_no_resolution_date_is_not_todays(self):
        assert not _resolves_by_the_next_close(spx_daily(resolves=None), FIXED_NOW)

    def test_a_naive_resolution_date_reads_as_utc(self):
        naive = datetime(2026, 9, 28, 20)
        assert _resolves_by_the_next_close(spx_daily(resolves=naive), FIXED_NOW)


class TestArmB:
    """The freshness rule itself, on offsets from the constant."""

    def _one_leg(self, stamp):
        return SimpleNamespace(outcomes=[SimpleNamespace(last_updated=stamp)])

    def test_the_boundary(self):
        cutoff = FIXED_NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)
        assert last_priced_before_the_venue_forgets(
            self._one_leg(cutoff - timedelta(hours=1)), FIXED_NOW
        )
        assert not last_priced_before_the_venue_forgets(
            self._one_leg(cutoff + timedelta(hours=1)), FIXED_NOW
        )

    def test_the_freshest_leg_decides(self):
        m = tariff_refund()
        m.outcomes[3].last_updated = FRESH
        assert not last_priced_before_the_venue_forgets(m, FIXED_NOW)

    @pytest.mark.asyncio
    async def test_one_fresh_leg_keeps_the_row_on_the_page(self):
        m = tariff_refund()
        m.outcomes[3].last_updated = FRESH
        payload = await _run(pool(tariff=m))
        assert 112829 in _trade_ids(payload)

    def test_no_stamp_is_no_evidence(self):
        assert not last_priced_before_the_venue_forgets(self._one_leg(None), FIXED_NOW)
        assert not last_priced_before_the_venue_forgets(SimpleNamespace(outcomes=[]), FIXED_NOW)
        assert not last_priced_before_the_venue_forgets(SimpleNamespace(), FIXED_NOW)

    def test_a_naive_stamp_reads_as_utc(self):
        naive = TARIFF_STAMP.replace(tzinfo=None)
        assert last_priced_before_the_venue_forgets(self._one_leg(naive), FIXED_NOW)
