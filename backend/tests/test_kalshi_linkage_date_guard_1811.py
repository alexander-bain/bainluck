"""#1811 — the Kalshi duplicate-linkage date guard past game-winner prefixes.

Before #1811 ``_check_duplicate_kalshi_linkage`` date-checked a candidate link
only when the ticker prefix passed ``_is_game_winner_kalshi_prefix``. Totals,
spreads, period markets (F3/F5/F7) and props were skipped by design — which
means the guard protected exactly the markets Kalshi grades and settles itself,
and skipped exactly the markets we grade from our own ``events`` scores.

Fable's ruling (2026-08-13, rulings 031/036): the provider's ticker defines the
market's referent, so the widened guard covers every Kalshi ticker class with a
parseable ticker date.

Per gotcha #43 every guard assertion here comes in BOTH directions: the wrong
date is refused AND the right date still links. Per gotcha #44 no anchor
branches on the wall clock — every date in this file is a FIXED literal, so
there is nothing for a clock sweep to move.
"""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.prediction_market_matching import (
    _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS,
    _EVENT_DATE_MAX_DIFF_HOURS,
    _REFUSAL_EVENT_DATE,
    _REFUSAL_SIBLING_DATE,
    _check_duplicate_kalshi_linkage,
    _check_duplicate_kalshi_linkage_reason,
    _event_date_max_diff_hours,
    _is_combat_kalshi_prefix,
    _ticker_date_conflicts_with_event,
)


# All fixtures are fixed literals (gotcha #44). 2026-08-11 is inside EDT, so a
# 19:07 Eastern first pitch is 23:07 UTC.
EVENT_COMMENCE = datetime(2026, 8, 11, 23, 7, tzinfo=timezone.utc)


def _session(existing_rows=None, commence=EVENT_COMMENCE):
    """A session whose FIRST execute answers the event-commence lookup and
    whose SECOND answers the sibling-market scan."""
    commence_result = MagicMock()
    commence_result.scalar_one_or_none.return_value = commence

    sibling_result = MagicMock()
    sibling_result.all.return_value = list(existing_rows or [])

    session = AsyncMock()
    session.execute.side_effect = [commence_result, sibling_result] * 8
    return session


def _market(external_id, mid=1):
    return SimpleNamespace(id=mid, source="kalshi", external_id=external_id)


def _sibling(external_id, mid=999):
    return SimpleNamespace(id=mid, external_id=external_id, name="existing")


async def _reason(external_id, ticker_date, existing=None, commence=EVENT_COMMENCE):
    return await _check_duplicate_kalshi_linkage_reason(
        _session(existing, commence),
        event_id=42,
        market=_market(external_id),
        ticker_game_date=ticker_date,
    )


# ── The pure predicate ───────────────────────────────────────────────────────
class TestTickerDateConflictsWithEvent:
    def test_hhmm_ticker_is_eastern_not_utc(self):
        # KXMLBTOTAL-26AUG111907BOSTOR: 19:07 EASTERN == 23:07 UTC. Reading the
        # ticker as UTC would put it 4h out and refuse a correct link — the
        # measured failure mode (98% of linked MLB markets).
        td = datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc)
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE) is False

    def test_hhmm_ticker_next_day_conflicts(self):
        td = datetime(2026, 8, 12, 19, 7, tzinfo=timezone.utc)
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE) is True

    def test_hhmm_ticker_within_three_hours_ok(self):
        td = datetime(2026, 8, 11, 21, 30, tzinfo=timezone.utc)  # 21:30 ET = 01:30 UTC
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE) is False

    def test_date_only_same_eastern_day_ok(self):
        # 23:07 UTC on Aug 11 is 19:07 ET on Aug 11 — same Eastern day.
        td = datetime(2026, 8, 11, tzinfo=timezone.utc)
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE) is False

    def test_date_only_one_eastern_day_off_is_tolerated(self):
        # Eastern is a US-VENUE proxy, not the event's own zone; ±1 day stays
        # linked so international matches are not dropped.
        td = datetime(2026, 8, 10, tzinfo=timezone.utc)
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE) is False

    def test_date_only_two_eastern_days_off_conflicts(self):
        td = datetime(2026, 8, 9, tzinfo=timezone.utc)
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE) is True

    def test_evening_game_utc_rollover_is_not_a_conflict(self):
        # A 22:10 ET start is 02:10 UTC the NEXT day, so ticker and commence
        # sit ~22h and one UTC day apart while naming the same game. This is
        # why the date-only rule counts EASTERN days. (It is also the ~3,000
        # markets by which a UTC-day census over-counts the ET-day census; the
        # issue's published 5,142/540 is already the ET figure and is correct.)
        commence = datetime(2026, 8, 11, 2, 10, tzinfo=timezone.utc)
        td = datetime(2026, 8, 10, 22, 10, tzinfo=timezone.utc)
        assert _ticker_date_conflicts_with_event(td, commence) is False

    def test_missing_inputs_never_conflict(self):
        assert _ticker_date_conflicts_with_event(None, EVENT_COMMENCE) is False
        assert _ticker_date_conflicts_with_event(EVENT_COMMENCE, None) is False

    def test_naive_datetimes_are_treated_as_utc(self):
        td = datetime(2026, 8, 11, 19, 7)
        assert _ticker_date_conflicts_with_event(td, EVENT_COMMENCE.replace(tzinfo=None)) is False


# ── Totals: both directions (gotcha #43) ─────────────────────────────────────
class TestTotalsMarket:
    @pytest.mark.asyncio
    async def test_totals_one_day_early_is_refused(self):
        # The 5,142-market population: a totals ticker for the PREVIOUS day's
        # game sitting on a healthy event, with no game-winner sibling to
        # compare against. Before #1811 this linked silently.
        reason = await _reason(
            "KXMLBTOTAL-26AUG101907BOSTOR",
            datetime(2026, 8, 10, 19, 7, tzinfo=timezone.utc),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_totals_matching_date_still_links(self):
        reason = await _reason(
            "KXMLBTOTAL-26AUG111907BOSTOR",
            datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
        )
        assert reason is None


# ── Spreads: both directions ─────────────────────────────────────────────────
class TestSpreadMarket:
    @pytest.mark.asyncio
    async def test_spread_one_day_early_is_refused(self):
        reason = await _reason(
            "KXMLBSPREAD-26AUG101907BOSTOR-B1.5",
            datetime(2026, 8, 10, 19, 7, tzinfo=timezone.utc),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_spread_matching_date_still_links(self):
        reason = await _reason(
            "KXMLBSPREAD-26AUG111907BOSTOR-B1.5",
            datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
        )
        assert reason is None


# ── Period (F5) markets: both directions ─────────────────────────────────────
class TestPeriodMarket:
    @pytest.mark.asyncio
    async def test_f5_one_day_early_is_refused(self):
        reason = await _reason(
            "KXMLBF5-26AUG101907BOSTOR",
            datetime(2026, 8, 10, 19, 7, tzinfo=timezone.utc),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_f5_matching_date_still_links(self):
        reason = await _reason(
            "KXMLBF5-26AUG111907BOSTOR",
            datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_f5_total_matching_date_still_links(self):
        reason = await _reason(
            "KXMLBF5TOTAL-26AUG111907BOSTOR",
            datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
        )
        assert reason is None


# ── Game winners: the sibling path is unchanged ──────────────────────────────
class TestGameWinnerNoRegression:
    @pytest.mark.asyncio
    async def test_sibling_different_date_still_blocks_with_sibling_reason(self):
        # Event commence is deliberately UNAVAILABLE so only mechanism (b) can
        # fire — proving the pre-existing sibling comparison is intact.
        reason = await _reason(
            "KXCS2MAP-25JUL15FNCVIT",
            datetime(2025, 7, 15, tzinfo=timezone.utc),
            existing=[_sibling("KXCS2GAME-25JUL10FNCVIT")],
            commence=None,
        )
        assert reason == _REFUSAL_SIBLING_DATE

    @pytest.mark.asyncio
    async def test_sibling_same_date_still_links(self):
        reason = await _reason(
            "KXCS2MAP-25JUL15FNCVIT",
            datetime(2025, 7, 15, tzinfo=timezone.utc),
            existing=[_sibling("KXCS2GAME-25JUL15FNCVIT")],
            commence=None,
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_game_winner_matching_event_date_still_links(self):
        reason = await _reason(
            "KXMLBGAME-26AUG111907BOSTOR",
            datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_game_winner_wrong_event_date_now_refused_on_event_arm(self):
        reason = await _reason(
            "KXMLBGAME-26AUG121907BOSTOR",
            datetime(2026, 8, 12, 19, 7, tzinfo=timezone.utc),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_boolean_wrapper_still_returns_true_false(self):
        ok = await _check_duplicate_kalshi_linkage(
            _session(), event_id=42,
            market=_market("KXMLBGAME-26AUG111907BOSTOR"),
            ticker_game_date=datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
        )
        assert ok is True
        blocked = await _check_duplicate_kalshi_linkage(
            _session(), event_id=42,
            market=_market("KXMLBGAME-26AUG121907BOSTOR"),
            ticker_game_date=datetime(2026, 8, 12, 19, 7, tzinfo=timezone.utc),
        )
        assert blocked is False


# ── No signal → no refusal ───────────────────────────────────────────────────
class TestNoSignalStillLinks:
    @pytest.mark.asyncio
    async def test_ticker_without_parseable_date_links(self):
        # A season-long / award ticker carries no game date: nothing to unlink on.
        reason = await _reason("KXMLBWORLDSERIES-26", None)
        assert reason is None

    @pytest.mark.asyncio
    async def test_event_without_commence_time_links(self):
        reason = await _reason(
            "KXMLBTOTAL-26AUG101907BOSTOR",
            datetime(2026, 8, 10, 19, 7, tzinfo=timezone.utc),
            commence=None,
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_non_kalshi_short_circuits_without_querying(self):
        session = _session()
        reason = await _check_duplicate_kalshi_linkage_reason(
            session, event_id=42,
            market=SimpleNamespace(id=1, source="polymarket", external_id="abc"),
            ticker_game_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        assert reason is None
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_caller_passing_none_does_not_disable_the_guard(self):
        # The ticker date is re-derived from external_id when the caller omits it.
        reason = await _reason("KXMLBTOTAL-26AUG101907BOSTOR", None)
        assert reason == _REFUSAL_EVENT_DATE


# ── Combat is exempt (gotcha #14) ────────────────────────────────────────────
class TestCombatExemption:
    def test_combat_prefix_predicate_covers_props_not_just_the_bout(self):
        assert _is_combat_kalshi_prefix("kxufcfight") is True
        assert _is_combat_kalshi_prefix("kxufcrounds") is True
        assert _is_combat_kalshi_prefix("kxufcmof") is True
        assert _is_combat_kalshi_prefix("kxboxing") is True
        assert _is_combat_kalshi_prefix("kxboxingknockout") is True
        assert _is_combat_kalshi_prefix("kxmlbgame") is False
        assert _is_combat_kalshi_prefix("kxnbaspread") is False

    @pytest.mark.asyncio
    async def test_combat_fight_twenty_hours_off_still_links(self):
        # Kalshi's combat card token is date-only and its close-time is not the
        # start time, so ~28h of drift is legitimate (gotcha #14).
        commence = EVENT_COMMENCE + timedelta(hours=20)
        reason = await _reason(
            "KXUFCFIGHT-26AUG11JONMIO",
            datetime(2026, 8, 11, tzinfo=timezone.utc),
            commence=commence,
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_combat_prop_twenty_hours_off_still_links(self):
        commence = EVENT_COMMENCE + timedelta(hours=20)
        reason = await _reason(
            "KXUFCROUNDS-26AUG11JONMIO",
            datetime(2026, 8, 11, tzinfo=timezone.utc),
            commence=commence,
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_non_combat_prop_twenty_hours_off_is_refused_mlb(self):
        # The other direction of the same exemption (gotcha #43): the drift
        # allowance is combat-only, it is not a blanket loosening.
        commence = EVENT_COMMENCE + timedelta(hours=20)
        reason = await _reason(
            "KXMLBTOTAL-26AUG111907BOSTOR",
            datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc),
            commence=commence,
        )
        assert reason == _REFUSAL_EVENT_DATE


# ── Esports: a WIDER per-class HHMM window (both directions, gotcha #43) ─────
#
# Measured on production 2026-08-12: 96% of esports events carry a
# commence_time with nonzero seconds — the ingest-stamp signature of an event
# auto-created from the prediction market itself — and 113/119 sampled events
# are coherent (one match's markets only, so there is nothing to be mislinked
# to). A ±3h window would therefore refuse a market the link to the very event
# it created. The cliff sits at 12h, in the measured gap between the +9h edge
# of the near cluster and the +17h edge of the different-day population.
#
# Note the theory this does NOT rest on: "map 2 starts hours after map 1" is
# refuted by the tickers — every map of a series carries the SAME date-token
# and differs only by the -N suffix.
ESPORTS_TICKER = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)  # 14:00 ET
ESPORTS_SERIES_START_UTC = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


class TestEsportsWiderWindow:
    def test_tolerance_is_per_class(self):
        assert _event_date_max_diff_hours("kxcs2map") == _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS
        assert _event_date_max_diff_hours("kxcs2game") == _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS
        assert _event_date_max_diff_hours("kxcs2totalmaps") == _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS
        assert _event_date_max_diff_hours("kxlolmap") == _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS
        assert _event_date_max_diff_hours("kxvalorantgame") == _ESPORTS_EVENT_DATE_MAX_DIFF_HOURS
        # Everything else keeps the ±3h window — this is not a global loosening.
        assert _event_date_max_diff_hours("kxmlbtotal") == _EVENT_DATE_MAX_DIFF_HOURS
        assert _event_date_max_diff_hours("kxnbaspread") == _EVENT_DATE_MAX_DIFF_HOURS
        assert _event_date_max_diff_hours("") == _EVENT_DATE_MAX_DIFF_HOURS

    @pytest.mark.asyncio
    async def test_map_six_hours_after_series_start_links(self):
        reason = await _reason(
            "KXCS2MAP-26AUG111400NAVIVIT-2",
            ESPORTS_TICKER,
            commence=ESPORTS_SERIES_START_UTC + timedelta(hours=6),
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_series_winner_six_hours_after_series_start_links(self):
        # The GAME (series) ticker sits at the same delta as its maps, which is
        # why the widening keys on the family and not on a "…map" suffix.
        reason = await _reason(
            "KXCS2GAME-26AUG111400NAVIVIT",
            ESPORTS_TICKER,
            commence=ESPORTS_SERIES_START_UTC + timedelta(hours=6),
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_totalmaps_prop_six_hours_after_series_start_links(self):
        reason = await _reason(
            "KXCS2TOTALMAPS-26AUG111400NAVIVIT",
            ESPORTS_TICKER,
            commence=ESPORTS_SERIES_START_UTC + timedelta(hours=6),
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_map_three_days_off_is_refused(self):
        reason = await _reason(
            "KXCS2MAP-26AUG111400NAVIVIT-2",
            ESPORTS_TICKER,
            commence=ESPORTS_SERIES_START_UTC + timedelta(days=3),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_map_just_past_the_cliff_is_refused(self):
        # 13h > the 12h cliff: the window is wide, not absent.
        reason = await _reason(
            "KXVALORANTMAP-26AUG111400NAVIVIT-1",
            ESPORTS_TICKER,
            commence=ESPORTS_SERIES_START_UTC + timedelta(hours=13),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_same_six_hour_delta_on_a_non_esports_prop_is_refused(self):
        # The other direction of the per-class rule (gotcha #43): 6h is fine
        # for esports and NOT fine for MLB, from the same predicate.
        reason = await _reason(
            "KXMLBTOTAL-26AUG111400BOSTOR",
            ESPORTS_TICKER,
            commence=ESPORTS_SERIES_START_UTC + timedelta(hours=6),
        )
        assert reason == _REFUSAL_EVENT_DATE

    @pytest.mark.asyncio
    async def test_esports_date_only_rule_is_unchanged(self):
        # The wider window is HHMM-only; date-only esports keeps >=2 ET days.
        near = await _reason(
            "KXCS2MAP-26AUG11NAVIVIT-1",
            datetime(2026, 8, 11, tzinfo=timezone.utc),
            commence=ESPORTS_SERIES_START_UTC,
        )
        assert near is None
        far = await _reason(
            "KXCS2MAP-26AUG09NAVIVIT-1",
            datetime(2026, 8, 9, tzinfo=timezone.utc),
            commence=ESPORTS_SERIES_START_UTC,
        )
        assert far == _REFUSAL_EVENT_DATE
