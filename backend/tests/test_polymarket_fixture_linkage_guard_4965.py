"""#4965 — three dates of one series must not land on one event row.

Polymarket publishes ONE game market per date and every market in a series
carries the identical ``name``. The matcher's only time reference for a
Polymarket market was ``FuturesMarket.commence_time``, which is fed by Gamma's
``startDate`` — the LISTING stamp, not the fixture. Measured at the venue
2026-09-10, the three Rangers/Mariners markets read:

    id      slug                     startDate (stored)   startTime (the game)
    953429  mlb-tex-sea-2026-09-08   2026-09-02T13:00:44Z 2026-09-09T01:40:00Z
    959080  mlb-tex-sea-2026-09-09   2026-09-03T13:00:51Z 2026-09-09T20:10:00Z
    964211  mlb-tex-sea-2026-09-10   2026-09-04T13:00:41Z 2026-09-10T20:10:00Z

All three linked to event 15308638 (the Sep 10 game, commence
2026-09-10T20:10:00Z). The blend read the Sep 8 leg, which Texas had already
won, so it served 1 − 0.986 = **1.4% for Texas against a 26-30% six-source
consensus**.

The guard compares the venue's own UTC fixture instant against the event's
``commence_time``. It is deliberately NOT the slug: ``mlb-tex-sea-2026-09-08``
is played at 2026-09-09T01:40Z, a different UTC day, so the slug would have
needed a per-league timezone convention inferred. ``startTime`` needs none.

Per gotcha #43 every assertion comes in BOTH directions — the wrong date is
refused AND the right date still links. Per gotcha #44 every instant here is a
FIXED literal, so there is nothing for a clock sweep to move.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.prediction_market_matching import (
    _PM_FIXTURE_MAX_DIFF_HOURS,
    _REFUSAL_EVENT_DATE,
    _FUNNEL_KEY_BY_REFUSAL,
    _REFUSAL_SIBLING_DATE,
    _REFUSAL_VENUE_FIXTURE,
    _check_duplicate_kalshi_linkage_reason,
    _check_polymarket_fixture_reason,
    venue_game_start,
)

# The real specimens, read from Gamma 2026-09-10 (see the module docstring).
EVENT_COMMENCE = datetime(2026, 9, 10, 20, 10, tzinfo=timezone.utc)
FIXTURE_SEP08 = "2026-09-09T01:40:00Z"   # 42.5h from the event — a different game
FIXTURE_SEP09 = "2026-09-09T20:10:00Z"   # 24h   from the event — a different game
FIXTURE_SEP10 = "2026-09-10T20:10:00Z"   # 0h    — THE game


def _session(commence=EVENT_COMMENCE):
    """A session whose execute answers the event-commence lookup."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = commence
    session = AsyncMock()
    session.execute.return_value = result
    return session


def _pm_market(venue_start, mid=1, external_id="964211"):
    meta = {"polymarket_event_id": external_id}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start
    return SimpleNamespace(
        id=mid,
        source="polymarket",
        external_id=external_id,
        name="Texas Rangers vs. Seattle Mariners",
        market_metadata=meta,
    )


# ── The stamp reader ─────────────────────────────────────────────────────────
class TestVenueGameStart:
    def test_parses_the_z_suffixed_form_gamma_gives_on_the_event(self):
        assert venue_game_start(_pm_market(FIXTURE_SEP10)) == datetime(
            2026, 9, 10, 20, 10, tzinfo=timezone.utc
        )

    def test_parses_the_offset_form_gamma_gives_on_the_market(self):
        # `gameStartTime` comes back as "2026-09-10 20:10:00+00" — a space
        # separator and a 2-digit offset. Both forms must land on one instant.
        assert venue_game_start(
            _pm_market("2026-09-10 20:10:00+00")
        ) == datetime(2026, 9, 10, 20, 10, tzinfo=timezone.utc)

    def test_a_naive_stamp_is_read_as_utc_not_local(self):
        assert venue_game_start(_pm_market("2026-09-10T20:10:00")) == datetime(
            2026, 9, 10, 20, 10, tzinfo=timezone.utc
        )

    def test_accepts_a_datetime_that_survived_json_as_an_object(self):
        assert venue_game_start(
            _pm_market(datetime(2026, 9, 10, 20, 10))
        ) == datetime(2026, 9, 10, 20, 10, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "meta",
        [None, {}, {"polymarket_event_id": "964211"}, "not-a-dict", []],
        ids=["none", "empty", "no-stamp", "string-meta", "list-meta"],
    )
    def test_no_signal_reads_none_rather_than_raising(self, meta):
        market = SimpleNamespace(
            id=1, source="polymarket", external_id="964211", market_metadata=meta
        )
        assert venue_game_start(market) is None

    @pytest.mark.parametrize("raw", ["", "not a date", "2026-13-45T99:99:99Z"])
    def test_an_unparseable_stamp_is_no_signal_not_an_exception(self, raw):
        assert venue_game_start(_pm_market(raw)) is None


# ── The guard, both directions ───────────────────────────────────────────────
class TestPolymarketFixtureGuard:
    @pytest.mark.asyncio
    async def test_the_sep_8_market_is_refused_on_the_sep_10_event(self):
        # The specimen that produced the 1.4%: settled at Texas 0.986 two days
        # before the game the reader was looking at.
        assert await _check_polymarket_fixture_reason(
            _session(), 15308638, _pm_market(FIXTURE_SEP08, external_id="953429")
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_the_sep_9_market_is_refused_on_the_sep_10_event(self):
        # 24h out — the neighbour. This is the case a calendar-day rule with a
        # >=2-day tolerance (the Kalshi date-only rule) would have let through.
        assert await _check_polymarket_fixture_reason(
            _session(), 15308638, _pm_market(FIXTURE_SEP09, external_id="959080")
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_the_date_matched_market_still_links(self):
        # The other direction (gotcha #43): the guard must not cost us the one
        # market that is right. Gamma's startTime for 964211 equals our event's
        # commence_time exactly, so the margin here is 0h, not "within 3h".
        assert await _check_polymarket_fixture_reason(
            _session(), 15308638, _pm_market(FIXTURE_SEP10, external_id="964211")
        ) is None

    @pytest.mark.asyncio
    async def test_the_acceptance_three_same_named_markets_keep_only_one(self):
        """#4965's stated acceptance, as one assertion over the real trio."""
        offered = [
            ("953429", FIXTURE_SEP08),
            ("959080", FIXTURE_SEP09),
            ("964211", FIXTURE_SEP10),
        ]
        survivors = [
            ext
            for ext, fixture in offered
            if await _check_polymarket_fixture_reason(
                _session(), 15308638, _pm_market(fixture, external_id=ext)
            )
            is None
        ]
        assert survivors == ["964211"], (
            "exactly the date-matched market may hold the event row; "
            f"got {survivors}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "offset_hours,refused",
        [(0, False), (2.9, False), (3.0, False), (3.2, True), (24, True)],
    )
    async def test_the_tolerance_boundary_is_where_the_constant_says(
        self, offset_hours, refused
    ):
        # Derived from the constant so the two cannot drift apart, and asserted
        # on BOTH sides of it rather than only on the refusing side.
        assert _PM_FIXTURE_MAX_DIFF_HOURS == 3
        fixture = datetime(
            2026, 9, 10, 20, 10, tzinfo=timezone.utc
        ).timestamp() + offset_hours * 3600
        stamp = datetime.fromtimestamp(fixture, tz=timezone.utc).isoformat()
        reason = await _check_polymarket_fixture_reason(
            _session(), 15308638, _pm_market(stamp)
        )
        assert (reason == _REFUSAL_VENUE_FIXTURE) is refused

    @pytest.mark.asyncio
    async def test_a_row_not_yet_re_polled_fails_open(self):
        # No stamp yet — every existing row until the next hourly poll. A guard
        # that refused these would unlink the whole Polymarket estate at once.
        assert await _check_polymarket_fixture_reason(
            _session(), 15308638, _pm_market(None)
        ) is None

    @pytest.mark.asyncio
    async def test_an_event_with_no_commence_time_fails_open(self):
        assert await _check_polymarket_fixture_reason(
            _session(commence=None), 15308638, _pm_market(FIXTURE_SEP08)
        ) is None

    @pytest.mark.asyncio
    async def test_a_non_datetime_commence_fails_open(self):
        # `_event_commence_time` already filters this, but the guard must not
        # depend on that to avoid raising on a NULL column.
        assert await _check_polymarket_fixture_reason(
            _session(commence="2026-09-10"), 15308638, _pm_market(FIXTURE_SEP08)
        ) is None


# ── Routing through the shared entry point ───────────────────────────────────
class TestRoutingFromTheSharedGuard:
    @pytest.mark.asyncio
    async def test_a_polymarket_market_reaches_the_fixture_arm(self):
        # Before #4965 this returned None for every Polymarket market at the
        # very first line — the hole the whole issue sits in.
        assert await _check_duplicate_kalshi_linkage_reason(
            _session(),
            event_id=15308638,
            market=_pm_market(FIXTURE_SEP08, external_id="953429"),
            ticker_game_date=None,
        ) == _REFUSAL_VENUE_FIXTURE

    @pytest.mark.asyncio
    async def test_the_date_matched_polymarket_market_passes_the_shared_guard(self):
        assert await _check_duplicate_kalshi_linkage_reason(
            _session(),
            event_id=15308638,
            market=_pm_market(FIXTURE_SEP10, external_id="964211"),
            ticker_game_date=None,
        ) is None

    @pytest.mark.asyncio
    async def test_a_third_source_is_still_unguarded(self):
        market = SimpleNamespace(
            id=1, source="odds_api", external_id="x", market_metadata={}
        )
        assert await _check_duplicate_kalshi_linkage_reason(
            _session(), event_id=15308638, market=market, ticker_game_date=None,
        ) is None


# ── The producer half ────────────────────────────────────────────────────────
# The guard above reads `market_metadata['venue_game_start']`, and fails OPEN
# when it is absent. So if the parse or the ingest stamp silently stops
# happening, every test above still passes and the whole ship is inert on
# production. These assert the stamp is actually produced.
class TestTheVenueFixtureIsParsedFromGamma:
    def _service(self):
        from app.services.polymarket_api import PolymarketAPIService

        return PolymarketAPIService()

    # The real 964211 payload keys, trimmed to what this reads.
    def _payload(self, **over):
        base = {
            "id": "964211",
            "title": "Texas Rangers vs. Seattle Mariners",
            "slug": "mlb-tex-sea-2026-09-10",
            "startDate": "2026-09-04T13:00:41Z",
            "startTime": "2026-09-10T20:10:00Z",
            "markets": [],
        }
        base.update(over)
        return base

    def test_start_time_becomes_the_fixture_instant(self):
        event = self._service()._parse_event(self._payload())
        assert event.game_start_time == datetime(
            2026, 9, 10, 20, 10, tzinfo=timezone.utc
        )

    def test_the_listing_stamp_is_kept_apart_from_it(self):
        # The whole defect in one assertion: these two are different instants
        # six days apart, and the column we store is fed by the wrong one.
        event = self._service()._parse_event(self._payload())
        assert event.start_date == datetime(
            2026, 9, 4, 13, 0, 41, tzinfo=timezone.utc
        )
        assert event.game_start_time != event.start_date

    def test_falls_back_to_a_nested_market_game_start_time(self):
        event = self._service()._parse_event(
            self._payload(
                startTime=None,
                markets=[{
                    "conditionId": "0xabc",
                    "question": "Texas Rangers vs. Seattle Mariners",
                    "gameStartTime": "2026-09-10 20:10:00+00",
                }],
            )
        )
        assert event.game_start_time == datetime(
            2026, 9, 10, 20, 10, tzinfo=timezone.utc
        )

    def test_an_unparseable_event_stamp_falls_through_to_the_market(self):
        # `or None` rather than a truthiness chain on the parse result: a bad
        # event stamp must not pin the value to None while a good one sits on
        # the market below it.
        event = self._service()._parse_event(
            self._payload(
                startTime="not a date",
                markets=[{
                    "conditionId": "0xabc",
                    "question": "q",
                    "gameStartTime": "2026-09-10T20:10:00Z",
                }],
            )
        )
        assert event.game_start_time == datetime(
            2026, 9, 10, 20, 10, tzinfo=timezone.utc
        )

    def test_a_non_game_event_simply_has_none(self):
        # Awards/futures carry no fixture. None here means the guard fails open
        # for them, which is the intended behaviour, not a gap.
        event = self._service()._parse_event(
            self._payload(startTime=None, markets=[])
        )
        assert event.game_start_time is None


class TestTheIngestStampsIt:
    def test_the_stamp_is_written_into_market_metadata(self):
        """The two lines in `tasks.polymarket` that make the guard non-inert.

        Asserted as SOURCE rather than by driving the whole poll: the metadata
        build sits ~100 lines inside `poll_polymarket_markets` behind an HTTP
        client, and a test that mocked all of that would be asserting its own
        mocks. What must be true is narrow and checkable — the key the guard
        reads is written from the field the parser fills.
        """
        import inspect

        from app.tasks import polymarket as pm

        src = inspect.getsource(pm)
        assert 'poly_metadata["venue_game_start"]' in src, (
            "the ingest no longer stamps the key the #4965 guard reads — the "
            "guard fails open on every row and the ship is inert"
        )
        assert "event.game_start_time" in src, (
            "the stamp is no longer fed from the parsed fixture instant"
        )

    def test_the_stamp_rides_the_on_conflict_path_so_existing_rows_backfill(self):
        """No backfill task exists, by design — this is why.

        `market_metadata` is rewritten on the upsert's on-conflict `set_`, so
        every already-ingested Polymarket row picks the stamp up on the next
        hourly poll. If that stopped being true, the guard would only ever see
        rows created after the deploy and the 63 existing duplicate groups would
        never become fixable.
        """
        import inspect

        from app.tasks import polymarket as pm

        src = inspect.getsource(pm)
        assert '"market_metadata": preserve_venue_settled(' in src, (
            "market_metadata left the on-conflict update set — existing rows "
            "will never pick up venue_game_start and #4965 needs a backfill task"
        )


class TestFunnelReporting:
    def test_each_refusal_has_its_own_counter(self):
        # The mechanism this replaced was a two-armed conditional whose ELSE
        # meant "sibling ticker". A third reason routed through it would have
        # been counted as a Kalshi sibling collision, making #4965's guard
        # invisible in the funnel that exists to show it.
        keys = {
            _REFUSAL_EVENT_DATE: "event_date_linkage_blocked",
            _REFUSAL_VENUE_FIXTURE: "venue_fixture_linkage_blocked",
            _REFUSAL_SIBLING_DATE: "duplicate_linkage_blocked",
        }
        assert _FUNNEL_KEY_BY_REFUSAL == keys
        assert len(set(_FUNNEL_KEY_BY_REFUSAL.values())) == 3, (
            "two reasons sharing a counter is the bug this asserts against"
        )
