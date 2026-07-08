"""Tests for Kalshi API service parsing methods.

Covers:
- _parse_market: dual price format (dollars vs cents), zero handling, volume FP
- _parse_event: event with/without nested markets
- _parse_timestamp: ISO format variants
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks.kalshi import (
    _build_game_market_name,
    _categorize_kalshi_market,
    _is_kalshi_game_ticker,
    _partition_new_events_first,
)
from app.utils.prediction_market_matching import (
    extract_game_date_from_ticker,
    extract_matchup_with_ticker_fallback,
    extract_teams_from_ticker,
)


@pytest.fixture
def client():
    return KalshiAPIService()


@pytest.fixture
def fixtures():
    path = Path(__file__).parent / "fixtures" / "kalshi_fixtures.json"
    with open(path) as f:
        return json.load(f)


# ── _parse_market ─────────────────────────────────────────────────────


class TestParseMarket:
    """Test the dual price format parsing in _parse_market."""

    def test_dollars_preferred_over_cents(self, client, fixtures):
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.yes_bid == 0.65
        assert market.yes_ask == 0.68
        assert market.no_bid == 0.32
        assert market.no_ask == 0.35
        assert market.last_price == 0.66

    def test_cents_fallback_when_no_dollars(self, client, fixtures):
        market = client._parse_market(fixtures["market_cents_only"])
        assert market is not None
        assert market.yes_bid == pytest.approx(0.72)
        assert market.yes_ask == pytest.approx(0.75)
        assert market.no_bid == pytest.approx(0.25)
        assert market.no_ask == pytest.approx(0.28)
        assert market.last_price == pytest.approx(0.73)

    def test_zero_dollar_bid_is_valid(self, client, fixtures):
        """$0.00 bid is valid data (no one bidding), not missing."""
        market = client._parse_market(fixtures["market_zero_dollar_bid"])
        assert market is not None
        assert market.yes_bid == 0.0
        assert market.yes_ask == 0.01
        assert market.no_bid == 0.99
        assert market.no_ask == 1.0

    def test_invalid_dollar_price_falls_back_to_cents(self, client, fixtures):
        raw = dict(fixtures["market_cents_only"])
        raw.update(
            {
                "yes_bid_dollars": "not-a-price",
                "yes_ask_dollars": "",
                "last_price_dollars": None,
                "yes_bid": 41,
                "yes_ask": 44,
                "last_price": 42,
            }
        )

        market = client._parse_market(raw)

        assert market is not None
        assert market.yes_bid == pytest.approx(0.41)
        assert market.yes_ask == pytest.approx(0.44)
        assert market.last_price == pytest.approx(0.42)

    def test_decimal_cent_fields_are_not_divided_again(self, client, fixtures):
        raw = dict(fixtures["market_cents_only"])
        raw.update(
            {
                "yes_bid": 0.41,
                "yes_ask": 0.44,
                "no_bid": 0.56,
                "no_ask": 0.59,
                "last_price": 0.42,
            }
        )

        market = client._parse_market(raw)

        assert market is not None
        assert market.yes_bid == pytest.approx(0.41)
        assert market.yes_ask == pytest.approx(0.44)
        assert market.no_bid == pytest.approx(0.56)
        assert market.no_ask == pytest.approx(0.59)
        assert market.last_price == pytest.approx(0.42)

    def test_minimal_market(self, client, fixtures):
        market = client._parse_market(fixtures["market_minimal"])
        assert market is not None
        assert market.ticker == "KXMIN"
        assert market.status == "closed"
        assert market.yes_bid is None
        assert market.yes_ask is None
        assert market.last_price is None
        assert market.volume is None

    def test_settled_market_result(self, client, fixtures):
        market = client._parse_market(fixtures["market_settled"])
        assert market is not None
        assert market.result == "yes"
        assert market.last_price == 1.0
        assert market.volume == 99999

    def test_volume_fp_preferred(self, client, fixtures):
        """Volume FP string fields override integer fields."""
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.volume == 12345
        assert market.volume_24h == 678
        assert market.open_interest == 4500

    def test_volume_integer_fallback(self, client, fixtures):
        market = client._parse_market(fixtures["market_cents_only"])
        assert market is not None
        assert market.volume == 5000
        assert market.volume_24h == 200
        assert market.open_interest == 1500

    def test_basic_fields(self, client, fixtures):
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.ticker == "KXNBA-CELTICS-WIN-2026"
        assert market.event_ticker == "KXNBA-CELTICS-2026"
        assert market.title == "Will the Celtics win?"
        assert market.subtitle == "Game 7 Championship"
        assert market.yes_sub_title == "Celtics win"
        assert market.no_sub_title == "Celtics lose"
        assert market.status == "active"

    def test_timestamps_parsed(self, client, fixtures):
        market = client._parse_market(fixtures["market_dollars_format"])
        assert market is not None
        assert market.open_time is not None
        assert isinstance(market.open_time, datetime)
        assert market.close_time is not None
        assert market.expiration_time is not None

    def test_empty_dict(self, client):
        market = client._parse_market({})
        assert market is not None
        assert market.ticker == ""
        assert market.status == ""


# ── _parse_event ──────────────────────────────────────────────────────


class TestParseEvent:

    def test_event_with_markets(self, client, fixtures):
        event = client._parse_event(fixtures["event_with_markets"])
        assert event is not None
        assert event.event_ticker == "KXNBA-GAME1"
        assert event.title == "NBA Game 1"
        assert event.subtitle == "Eastern Conference Finals"
        assert event.category == "Sports"
        assert event.mutually_exclusive is True
        assert len(event.markets) == 2
        assert event.markets[0].ticker == "KXNBA-GAME1-WIN"
        assert event.markets[1].ticker == "KXNBA-GAME1-TOTAL"

    def test_event_empty_markets(self, client, fixtures):
        event = client._parse_event(fixtures["event_empty_markets"])
        assert event is not None
        assert event.event_ticker == "KXEMPTY-EVT"
        assert len(event.markets) == 0

    def test_event_no_subtitle(self, client, fixtures):
        event = client._parse_event(fixtures["event_no_subtitle"])
        assert event is not None
        assert event.subtitle is None
        assert event.category == "Politics"

    def test_event_missing_markets_key(self, client):
        event = client._parse_event({"event_ticker": "TEST", "title": "Test"})
        assert event is not None
        assert len(event.markets) == 0

    def test_event_defaults(self, client):
        event = client._parse_event({})
        assert event is not None
        assert event.event_ticker == ""
        assert event.title == ""
        assert event.mutually_exclusive is True


# ── _parse_timestamp ──────────────────────────────────────────────────


class TestParseTimestamp:

    def test_z_suffix(self, client):
        result = client._parse_timestamp("2026-04-10T15:00:00Z")
        assert result is not None
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 10

    def test_offset_format(self, client):
        result = client._parse_timestamp("2026-04-10T15:00:00+00:00")
        assert result is not None
        assert isinstance(result, datetime)

    def test_none_returns_none(self, client):
        assert client._parse_timestamp(None) is None

    def test_empty_string_returns_none(self, client):
        assert client._parse_timestamp("") is None

    def test_invalid_string_returns_none(self, client):
        assert client._parse_timestamp("not-a-date") is None

    def test_z_and_offset_produce_same_time(self, client):
        z = client._parse_timestamp("2026-04-10T15:00:00Z")
        offset = client._parse_timestamp("2026-04-10T15:00:00+00:00")
        assert z == offset


# ── Kalshi game-market linking guardrails ─────────────────────────────


class TestKalshiGameMarketLinkingHelpers:

    def test_game_ticker_detection_is_case_insensitive(self):
        assert _is_kalshi_game_ticker("KXMLBGAME-26MAR281910CWSMIL") == "MLB"
        assert _is_kalshi_game_ticker("kxmlbgame-26mar281910cwsmil") == "MLB"
        assert _is_kalshi_game_ticker("KXMLBWS-26") is None

    def test_game_market_name_prefers_existing_matchup_title(self):
        assert (
            _build_game_market_name(
                event_title="Boston Celtics at Golden State Warriors",
                event_ticker="KXNBAGAME-26FEB21BOSGSW",
                market_title="Professional Basketball Game",
                yes_sub_title="Celtics",
                no_sub_title="Warriors",
                sport_label="NBA",
            )
            == "Boston Celtics at Golden State Warriors"
        )

    def test_game_market_name_builds_matchup_from_subtitles_for_generic_title(self):
        assert (
            _build_game_market_name(
                event_title="Professional Baseball Game",
                event_ticker="KXMLBGAME-26MAR281910CWSMIL",
                market_title="Moneyline",
                yes_sub_title="Chicago White Sox",
                no_sub_title="Milwaukee Brewers",
                sport_label="MLB",
            )
            == "Chicago White Sox at Milwaukee Brewers"
        )

    def test_mlb_ticker_team_parsing_handles_start_time_and_outcome_suffix(self):
        assert extract_teams_from_ticker("KXMLBGAME-26MAR281910CWSMIL-CWS") == (
            "White Sox",
            "Brewers",
        )

    def test_mlb_ticker_date_parsing_preserves_embedded_start_time(self):
        game_date = extract_game_date_from_ticker("KXMLBGAME-26MAR281910CWSMIL")

        assert game_date == datetime(2026, 3, 28, 19, 10, tzinfo=timezone.utc)

    def test_matchup_fallback_uses_ticker_aliases_for_abbreviated_team_names(self):
        matchup = extract_matchup_with_ticker_fallback(
            "A's at Philadelphia Phillies",
            "KXMLBGAME-26MAY17ATHPHI-ATH",
        )

        assert matchup is not None
        assert matchup.team_a == "Athletics"
        assert matchup.team_b == "Phillies"
        assert matchup.format_type == "ticker_parsed"


# ── Kalshi futures categorization guardrails ──────────────────────────


class TestKalshiFuturesCategorization:

    def test_ticker_prefix_overrides_ambiguous_conference_market_name(self):
        assert (
            _categorize_kalshi_market(
                "Eastern Conference winner",
                "Sports",
                event_ticker="KXNHLEAST-26",
            )
            == "hockey"
        )

    def test_game_prop_ticker_prefix_overrides_generic_or_wrong_category(self):
        assert (
            _categorize_kalshi_market(
                "Player to record 2+ hits",
                "Politics",
                event_ticker="KXMLBHIT-26MAY17ATHPHI-JUDGE",
            )
            == "baseball"
        )


class TestKalshiPollMetadataBuilding:
    """Regression test: the metadata-building code in _poll_kalshi_markets
    must not reference undefined variables.

    Commit c485950 removed `has_multiple_markets = len(event.markets) > 1`
    but left a dangling `if has_multiple_markets:` reference, which raised
    NameError at runtime and silently broke ALL Kalshi ingestion.
    """

    def test_no_undefined_names_in_poll_function(self):
        """AST-compile _poll_kalshi_markets and check for NameErrors."""
        import ast
        import inspect
        import textwrap
        from app.tasks.kalshi import _poll_kalshi_markets

        source = inspect.getsource(_poll_kalshi_markets)
        source = textwrap.dedent(source)
        # This will raise SyntaxError if malformed, but won't catch NameError.
        # We do a deeper check below.
        tree = ast.parse(source)

        # Collect all Name nodes used in Load context (variable reads)
        # and all Name nodes used in Store context (variable assignments)
        loads: set[str] = set()
        stores: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    loads.add(node.id)
                elif isinstance(node.ctx, ast.Store):
                    stores.add(node.id)

        # 'has_multiple_markets' must NOT appear in loads without stores
        # (that was the exact bug)
        assert "has_multiple_markets" not in (loads - stores), (
            "Undefined variable 'has_multiple_markets' found in "
            "_poll_kalshi_markets — likely a dangling reference after refactor"
        )


class TestNullOutStaleOutcomesPreservesResolved:
    """Regression guard for Queue #63 / gotcha #21 (calibration-corrupting).

    `_poll_kalshi_markets` nulls `current_probability` on outcomes whose Kalshi
    market returns no pricing (the "phantom data" prevention for active events).
    But settled Kalshi markets stop returning bid/ask and stay status='open'
    (gotcha #33), and aged-out markets return empty pricing (gotcha #35) — so
    without a resolved-state guard, every settled market's final price gets
    nulled on re-poll, wiping resolved data and masking the #898 backlog metric.
    The null-out UPDATE MUST exclude outcomes that are already resolved
    (is_winner set) or have a captured closing line (calibration_probability set).
    """

    def _kalshi_source(self) -> str:
        from pathlib import Path

        path = Path(__file__).parent.parent / "app" / "tasks" / "kalshi.py"
        return path.read_text()

    def test_null_out_stale_excludes_resolved_outcomes(self):
        src = self._kalshi_source()
        # Isolate the null-out-stale block (the UPDATE that nulls pricing on
        # unpriced_tickers) and assert the resolved-state guards are present.
        assert "unpriced_tickers = all_tickers - priced_tickers" in src, (
            "null-out-stale block not found — test anchor moved"
        )
        start = src.index("unpriced_tickers = all_tickers - priced_tickers")
        # Window covers the if-block + the sa_update through .values(...).
        block = src[start : start + 1200]
        assert "current_probability=None" in block, "null-out block anchor moved"
        assert "FuturesOutcome.is_winner.is_(None)" in block, (
            "null-out-stale must NOT clear resolved outcomes (is_winner set) — "
            "gotcha #21: never wipe resolved Kalshi state on re-poll"
        )
        assert "FuturesOutcome.calibration_probability.is_(None)" in block, (
            "null-out-stale must preserve outcomes with a captured closing line "
            "(calibration_probability) — they are past resolution"
        )


class _StubEvent:
    def __init__(self, ticker):
        self.event_ticker = ticker


class TestPartitionNewEventsFirst:
    """#995: process-new-first ordering so a deadline-truncated poll still
    creates every new Kalshi market it fetched (creation froze 2026-06-09 →
    2026-07-06 because new short-dated events sat at the expiry-DESC tail)."""

    def test_new_events_moved_ahead_of_existing(self):
        events = [_StubEvent(t) for t in ["OLD1", "NEW1", "OLD2", "NEW2"]]
        existing = {"OLD1", "OLD2"}
        new, exist = _partition_new_events_first(events, existing)
        assert [e.event_ticker for e in new] == ["NEW1", "NEW2"]
        assert [e.event_ticker for e in exist] == ["OLD1", "OLD2"]
        # concatenation puts new first, so a truncated loop reaches them
        combined = [e.event_ticker for e in (new + exist)]
        assert combined == ["NEW1", "NEW2", "OLD1", "OLD2"]

    def test_relative_order_preserved_within_partitions(self):
        events = [_StubEvent(t) for t in ["A", "B", "C", "D"]]
        existing = {"A", "C"}
        new, exist = _partition_new_events_first(events, existing)
        assert [e.event_ticker for e in new] == ["B", "D"]
        assert [e.event_ticker for e in exist] == ["A", "C"]

    def test_all_new_when_db_empty(self):
        events = [_StubEvent(t) for t in ["X", "Y"]]
        new, exist = _partition_new_events_first(events, set())
        assert [e.event_ticker for e in new] == ["X", "Y"]
        assert exist == []

    def test_all_existing_when_all_known(self):
        events = [_StubEvent(t) for t in ["X", "Y"]]
        new, exist = _partition_new_events_first(events, {"X", "Y"})
        assert new == []
        assert [e.event_ticker for e in exist] == ["X", "Y"]

    def test_empty_events(self):
        new, exist = _partition_new_events_first([], {"X"})
        assert new == []
        assert exist == []


async def _no_sleep(*_a, **_k):
    return None


class TestFetchDeadlineAndSettledTrim:
    """#995: poll_kalshi's unfiltered fetch must (a) honor a monotonic deadline
    so it never SIGKILLs mid-fetch, and (b) never request settled game events
    (settled capture belongs to kalshi_settled — the 200-page settled loop is
    what froze market creation for a month)."""

    async def test_fetch_returns_early_when_deadline_passed(self, client, monkeypatch):
        import time
        calls = []

        async def fake_get_events(**kw):
            calls.append(kw)
            return ([], None)

        monkeypatch.setattr(client, "get_events", fake_get_events)
        res = await client._fetch_all_events_unfiltered(deadline=time.monotonic() - 1)
        assert res == []
        # deadline is checked before the first page — zero API calls
        assert calls == []

    async def test_fetch_never_requests_settled_status(self, client, monkeypatch):
        import asyncio
        statuses = []
        seen_kw = []

        async def fake_get_events(status=None, **kw):
            statuses.append(status)
            seen_kw.append(kw)
            return ([], None)  # no cursor -> one page per scan

        monkeypatch.setattr(client, "get_events", fake_get_events)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        await client._fetch_all_events_unfiltered(deadline=None)
        assert statuses, "expected at least the main-scan page"
        assert "settled" not in statuses
        assert all(s is None for s in statuses)
        # deadline is threaded through to every get_events call so page-level
        # 429 backoff also honors it (#995).
        assert all("deadline" in kw for kw in seen_kw)


class TestPollKalshiSigkillHardening:
    """#995 attempt-4 (observability-first): poll_kalshi SIGKILLs before it can
    record any metric (no_data). Guard the source so the timeouts + phase marker
    that make the 4th fix diagnosable can't be silently removed."""

    def _src(self):
        import inspect
        import textwrap
        from app.tasks.kalshi import _poll_kalshi_markets
        return textwrap.dedent(inspect.getsource(_poll_kalshi_markets))

    def test_sets_statement_and_lock_timeout(self):
        src = self._src()
        assert "SET statement_timeout" in src, (
            "poll_kalshi must bound its longest single DB op (the orphan-cleanup "
            "DELETE) with statement_timeout so it can't hang to the 660s wall"
        )
        assert "SET lock_timeout" in src, (
            "poll_kalshi must set lock_timeout so a DELETE blocked on a "
            "live-poller row lock fails fast instead of SIGKILLing"
        )

    def test_writes_phase_marker_for_each_stage(self):
        src = self._src()
        assert "_mark_phase" in src
        for phase in ('"fetch"', '"orphan_cleanup"', '"upsert_loop"',
                      '"post_loop"', '"done"'):
            assert f"_mark_phase({phase})" in src, (
                f"missing phase marker {phase} — the marker is how the next run "
                f"locates the SIGKILL without heroku logs"
            )

    def test_phase_marker_uses_stable_redis_key(self):
        src = self._src()
        assert "bainluck:poll_kalshi:phase" in src


class TestFetchAttempt5Instrumentation:
    """#995 attempt-5: the fetch phase is where poll_kalshi SIGKILLs (marker
    `fetch@0s`). Guard the sub-phase progress marker + the wall-time cancel."""

    async def test_progress_cb_called_with_subphase(self, client, monkeypatch):
        import asyncio
        seen = []

        async def fake_get_events(**kw):
            return ([], None)

        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr(client, "get_events", fake_get_events)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        await client._fetch_all_events_unfiltered(
            deadline=None, progress_cb=lambda s: seen.append(s)
        )
        assert "fetch:unfiltered:p0" in seen
        assert any(s.startswith("fetch:supp:") for s in seen)

    async def test_progress_cb_none_is_safe(self, client, monkeypatch):
        import asyncio

        async def fake_get_events(**kw):
            return ([], None)

        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr(client, "get_events", fake_get_events)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        res = await client._fetch_all_events_unfiltered(deadline=None)
        assert res == []

    def test_client_has_explicit_read_timeout(self):
        import httpx
        c = KalshiAPIService()
        assert isinstance(c.client.timeout, httpx.Timeout)
        assert c.client.timeout.read is not None

    def test_poll_hardcaps_fetch_with_wait_for(self):
        import inspect
        import textwrap
        from app.tasks.kalshi import _poll_kalshi_markets
        src = textwrap.dedent(inspect.getsource(_poll_kalshi_markets))
        assert "asyncio.wait_for(" in src
        assert "progress_cb=_mark_phase" in src
        assert "fetch_walltime_exceeded" in src


class TestKalshiSettledPhaseMarker:
    """#969 CRITICAL instrument-first: kalshi_settled busts its 900s wall with
    all guards present, so a phase marker must record WHICH sub-phase eats the
    budget before any fix (do NOT assume fetch)."""

    def _src(self):
        import inspect
        import textwrap
        from app.tasks.kalshi import _backfill_from_settled_events
        return textwrap.dedent(inspect.getsource(_backfill_from_settled_events))

    def test_uses_stable_marker_key(self):
        assert "bainluck:kalshi_settled:phase" in self._src()

    def test_marks_key_subphases(self):
        src = self._src()
        assert "_mark_ks(" in src
        assert '_mark_ks("series_discovery")' in src
        assert 'f"fetch:{series}:p{page_num}"' in src
        assert 'f"sql:{series}:p{page_num}"' in src
        assert '_mark_ks("done")' in src


class TestFetchAttempt6PageBound:
    """#995 attempt-6: a hung/erroring main-scan page must NOT hang the whole
    fetch — break gracefully, keep prior pages, emit :err/:done markers so the
    poll reaches the create step."""

    async def test_hung_page_breaks_scan_and_keeps_prior_pages(self, client, monkeypatch):
        import asyncio
        seen = []
        calls = {"n": 0}

        def _ev(t):
            return {"event_ticker": t, "title": t, "markets": [
                {"ticker": f"{t}-M", "status": "active"}]}

        async def fake_get_events(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return ([_ev("KXAAA")], "cursor1")   # page 0 ok
            raise asyncio.TimeoutError()             # page 1 hangs

        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr(client, "get_events", fake_get_events)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        res = await client._fetch_all_events_unfiltered(
            deadline=None, progress_cb=lambda s: seen.append(s)
        )
        # page 0's event survived; scan stopped instead of hanging
        assert any(e.event_ticker == "KXAAA" for e in res)
        assert any(s.startswith("fetch:unfiltered:p0:recv") for s in seen)
        assert any(s == "fetch:unfiltered:p1:err" for s in seen)
        assert any(s.startswith("fetch:unfiltered:done") for s in seen)

    def test_source_wraps_page_in_wait_for(self):
        import inspect
        import textwrap
        from app.services.kalshi_api import KalshiAPIService
        src = textwrap.dedent(inspect.getsource(
            KalshiAPIService._fetch_all_events_unfiltered))
        assert "asyncio.wait_for(" in src
        assert "fetch:unfiltered:done" in src


class TestFetchAttempt8SyncUnblock:
    """#995 attempt-8: the freeze was a SYNC parse block. get_events decodes off
    the event loop (to_thread) and game-level supplementary series drop nested
    markets (the monster payloads)."""

    def test_get_events_decodes_off_event_loop(self):
        import inspect, textwrap
        from app.services.kalshi_api import KalshiAPIService
        src = textwrap.dedent(inspect.getsource(KalshiAPIService.get_events))
        assert "to_thread(response.json)" in src, (
            "get_events must decode via asyncio.to_thread so a huge nested "
            "payload can't block the event loop (attempt-8 proven mechanism)"
        )

    async def test_game_level_series_drop_nested(self, client, monkeypatch):
        import asyncio
        nested_by_series = {}

        async def fake_get_events(status=None, series_ticker=None,
                                  with_nested_markets=True, **kw):
            if series_ticker:
                nested_by_series[series_ticker] = with_nested_markets
            return ([], None)

        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr(client, "get_events", fake_get_events)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        await client._fetch_all_events_unfiltered(deadline=None)
        # game-level heavy series → nested dropped
        assert nested_by_series.get("KXNBAGAME") is False
        assert nested_by_series.get("KXMLBSPREAD") is False
        # small championship series → nested kept
        assert nested_by_series.get("KXNBA") is True
