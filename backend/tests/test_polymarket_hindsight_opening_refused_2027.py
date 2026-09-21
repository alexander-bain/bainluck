"""#2027 — a post-resolution capture is not stamped as `opening_probability`.

The hourly poll's supplementary settled-sports pass fetches `closed=True`
events and feeds them to the SAME `_process_event_batch` writer as the open
poll. That writer's opening gates were liquidity-only, so a settled book
quoting 0.99 through `lastTradePrice` passed `has_real_trading` and was
banked as the opening line — the answer wearing a price's clothes (ruling
103). The writer knew: the market row was stamped `resolved` on the same
pass.

CORRECTION under review: the first candidate's date arm truncated every
aware datetime to midnight (`datetime` IS a `date`, so an aware stamp fell
through to the `date` branch). `resolution 2026-09-20T20:00Z` captured at
noon the same day was wrongly refused. The same-day tests below pin the
exact-timestamp comparison through the helper AND the real writer harness.

The rail tests below START the real `_process_event_batch` over a recording
fake session (ruling 102): a settled specimen must keep its current price
and snapshot but bank no opening, while a live control still opens.

Fix-forward only: no existing row rewritten, `is_winner` untouched (#21).
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from app.utils.market_label_normalization import compute_market_tier
from app.utils.odds_math import probability_to_american


def _venue_event(*, active, closed, end_date, price, last_trade):
    """Venue-shaped single-market event, driven through the REAL parser."""
    return {
        "id": "evt-2027",
        "title": "Flyers vs. Hurricanes",
        "slug": "flyers-vs-hurricanes",
        "active": active,
        "closed": closed,
        "archived": False,
        "endDate": end_date,
        "startDate": "2026-05-03T23:00:00Z",
        "negRisk": False,
        "markets": [
            {
                "id": "m-1",
                "conditionId": "0x2027specimen",
                "question": "Flyers vs. Hurricanes",
                "slug": "flyers-hurricanes",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": f'["{price}", "{1 - price}"]',
                "clobTokenIds": '["111", "222"]',
                "bestBid": 0,
                "bestAsk": 1,
                "lastTradePrice": last_trade,
                "closed": closed,
            }
        ],
    }


def _parsed(**kwargs):
    svc = PolymarketAPIService()
    event = svc._parse_event(_venue_event(**kwargs))
    assert event is not None, "the parser refused a venue-shaped payload"
    assert event.markets, "the parser dropped the nested market"
    assert poly._parent_outcome_data(event), "no writable leg for this fixture"
    return event


def _open_event(end_date):
    return _parsed(
        active=True,
        closed=False,
        end_date=end_date,
        price=0.55,
        last_trade=0.55,
    )


class TestOpeningCaptureIsHindsight:
    def test_a_closed_event_is_hindsight(self):
        event = _parsed(
            active=True,
            closed=True,
            end_date="2026-05-04T00:00:00Z",
            price=0.99,
            last_trade=0.99,
        )
        now = datetime(2026, 6, 10, 8, 20, 29, tzinfo=timezone.utc)
        assert (
            poly.opening_capture_is_hindsight(event, None, event.end_date, now) is True
        )

    def test_a_capture_past_resolution_is_hindsight_even_when_flags_lag(self):
        event = _parsed(
            active=True,
            closed=False,
            end_date="2026-05-04T00:00:00Z",
            price=0.99,
            last_trade=0.99,
        )
        now = datetime(2026, 6, 10, 8, 20, 29, tzinfo=timezone.utc)
        assert (
            poly.opening_capture_is_hindsight(event, None, event.end_date, now) is True
        )

    def test_a_live_market_before_its_resolution_is_not(self):
        event = _parsed(
            active=True,
            closed=False,
            end_date="2026-12-01T00:00:00Z",
            price=0.55,
            last_trade=0.55,
        )
        now = datetime(2026, 6, 10, 8, 20, 29, tzinfo=timezone.utc)
        assert (
            poly.opening_capture_is_hindsight(event, None, event.end_date, now) is False
        )

    def test_a_closed_sub_market_taints_only_itself(self):
        event = _parsed(
            active=True,
            closed=False,
            end_date="2026-12-01T00:00:00Z",
            price=0.55,
            last_trade=0.55,
        )
        now = datetime(2026, 6, 10, tzinfo=timezone.utc)
        (market,) = event.markets
        assert (
            poly.opening_capture_is_hindsight(event, market, event.end_date, now)
            is False
        )
        market.closed = True
        assert (
            poly.opening_capture_is_hindsight(event, market, event.end_date, now)
            is True
        )

    def test_an_unparseable_stamp_refuses_nothing(self):
        event = _parsed(
            active=True,
            closed=False,
            end_date="2026-12-01T00:00:00Z",
            price=0.55,
            last_trade=0.55,
        )
        now = datetime(2026, 6, 10, tzinfo=timezone.utc)
        assert (
            poly.opening_capture_is_hindsight(event, None, "not-a-date", now) is False
        )
        assert poly.opening_capture_is_hindsight(event, None, None, now) is False


class TestSameDayCaptureIsNotTruncatedToMidnight:
    """Codex rejection: aware datetimes must compare exactly, not as dates.

    The first candidate fell through aware datetimes into the `date` arm
    (`datetime` subclasses `date`), truncating `2026-09-20T20:00Z` to
    midnight and wrongly refusing an open market captured at noon. Each
    test below FAILS on that ordering and passes on the corrected one.
    """

    RES = datetime(2026, 9, 20, 20, 0, 0, tzinfo=timezone.utc)

    def test_capture_before_resolution_same_day_is_not_hindsight(self):
        event = _open_event("2026-12-01T00:00:00Z")
        noon = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert poly.opening_capture_is_hindsight(event, None, self.RES, noon) is False

    def test_capture_exactly_at_resolution_is_not_hindsight(self):
        event = _open_event("2026-12-01T00:00:00Z")
        assert (
            poly.opening_capture_is_hindsight(event, None, self.RES, self.RES) is False
        )

    def test_capture_after_resolution_same_day_is_hindsight(self):
        event = _open_event("2026-12-01T00:00:00Z")
        late = datetime(2026, 9, 20, 21, 0, 0, tzinfo=timezone.utc)
        assert poly.opening_capture_is_hindsight(event, None, self.RES, late) is True

    def test_aware_non_utc_offset_compares_by_instant(self):
        from datetime import timezone as _tz

        plus2 = _tz(timedelta(hours=2))
        # Same instant as RES, spelled +02:00 — not hindsight.
        res_plus2 = datetime(2026, 9, 20, 22, 0, 0, tzinfo=plus2)
        event = _open_event("2026-12-01T00:00:00Z")
        assert (
            poly.opening_capture_is_hindsight(event, None, res_plus2, self.RES) is False
        )
        one_min_past = self.RES + timedelta(minutes=1)
        assert (
            poly.opening_capture_is_hindsight(event, None, res_plus2, one_min_past)
            is True
        )

    def test_naive_stamps_read_as_utc(self):
        event = _open_event("2026-12-01T00:00:00Z")
        naive_res = datetime(2026, 9, 20, 20, 0, 0)  # == RES in UTC
        noon_naive = datetime(2026, 9, 20, 12, 0, 0)
        noon_aware = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert (
            poly.opening_capture_is_hindsight(event, None, naive_res, noon_aware)
            is False
        )
        assert (
            poly.opening_capture_is_hindsight(event, None, self.RES, noon_naive)
            is False
        )
        late_naive = datetime(2026, 9, 20, 21, 0, 0)
        assert (
            poly.opening_capture_is_hindsight(event, None, naive_res, late_naive)
            is True
        )

    def test_pure_date_compares_at_utc_midnight(self):
        event = _open_event("2026-12-01T00:00:00Z")
        day = date(2026, 9, 20)
        noon = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        # A pure date has no clock: noon on the same calendar day IS past
        # its UTC-midnight start, so it reads as hindsight by the
        # ruling-103 predicate — the documented pure-date semantic.
        assert poly.opening_capture_is_hindsight(event, None, day, noon) is True
        before = datetime(2026, 9, 19, 23, 59, 0, tzinfo=timezone.utc)
        assert poly.opening_capture_is_hindsight(event, None, day, before) is False


class _FakeResult:
    def __init__(self, fake, stmt):
        self._fake = fake
        self._stmt = stmt

    def scalar_one(self):
        self._fake._next_id += 1
        return self._fake._next_id

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    @property
    def rowcount(self):
        return 0


class _FakeSession:
    """A recording stand-in for the task session: captures every statement
    the real writer emits without touching a database."""

    def __init__(self):
        self.statements = []
        self._next_id = 1000
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self, stmt)

    async def commit(self):
        self.commits += 1


def _outcome_inserts(fake):
    return [
        s
        for s in fake.statements
        if isinstance(s, Insert) and s.table.name == "futures_outcomes"
    ]


def _insert_values(stmt):
    """The literal VALUES arm of a postgres upsert, keyed by column name."""
    from sqlalchemy.dialects import postgresql

    return stmt.compile(dialect=postgresql.dialect()).params


async def _run_batch(monkeypatch, event):
    from collections import defaultdict

    fake = _FakeSession()
    monkeypatch.setattr(poly, "get_task_session", lambda: fake)
    # The writer setitems counters directly, as the hourly poll seeds them.
    stats = defaultdict(int, {"by_category": {}, "errors": []})
    await poly._process_event_batch(
        [event],
        stats,
        FuturesMarket,
        FuturesOutcome,
        FuturesOddsSnapshot,
        pg_insert,
        probability_to_american,
        compute_market_tier,
    )
    assert not stats.get("errors"), f"the rail errored: {stats.get('errors')}"
    return fake, stats


class TestTheRailRefusesTheHindsightOpening:
    """Ruling 102: the REAL `_process_event_batch`, stub transport only."""

    async def test_a_settled_first_sighting_banks_no_opening(self, monkeypatch):
        event = _parsed(
            active=True,
            closed=True,
            end_date="2026-05-04T00:00:00Z",
            price=0.99,
            last_trade=0.99,
        )
        fake, stats = await _run_batch(monkeypatch, event)
        inserts = _outcome_inserts(fake)
        assert inserts, "the writer produced no outcome row at all"
        for stmt in inserts:
            values = _insert_values(stmt)
            assert (
                values["opening_probability"] is None
            ), "a post-resolution capture was stamped as the opening line"
            assert values["opening_captured_at"] is None
        # The refusal is narrow: the current price and book still land.
        assert [_insert_values(s)["current_probability"] for s in inserts] == [0.99]
        assert (
            stats.get("opening_refused_hindsight", 0) >= 1
        ), "the refusal must be observable, not a belief (#2027)"

    async def test_a_flag_lagging_first_sighting_is_refused_by_date(self, monkeypatch):
        """Date path end-to-end: flags still open, resolution long past."""
        event = _parsed(
            active=True,
            closed=False,
            end_date="2026-05-04T00:00:00Z",
            price=0.99,
            last_trade=0.99,
        )
        fake, stats = await _run_batch(monkeypatch, event)
        inserts = _outcome_inserts(fake)
        assert inserts, "the writer produced no outcome row at all"
        for stmt in inserts:
            values = _insert_values(stmt)
            assert values["opening_probability"] is None
            assert values["opening_captured_at"] is None
        assert (
            stats.get("opening_refused_hindsight", 0) >= 1
        ), "the refusal must be observable, not a belief (#2027)"

    async def test_a_live_first_sighting_still_opens(self, monkeypatch):
        """Non-vacuity: a guard that refuses everything would pass the above."""
        event = _parsed(
            active=True,
            closed=False,
            end_date="2026-12-01T00:00:00Z",
            price=0.55,
            last_trade=0.55,
        )
        fake, stats = await _run_batch(monkeypatch, event)
        inserts = _outcome_inserts(fake)
        assert inserts, "the writer produced no outcome row at all"
        values = _insert_values(inserts[0])
        assert values["opening_probability"] == 0.55
        assert values["opening_captured_at"] is not None
        assert stats.get("opening_refused_hindsight", 0) == 0


def _venue_game_event(
    *, closed, end_date, price, second_market_closed=False, sub_closed=None
):
    """Venue-shaped GAME event: two sub-markets, so the writer DECOMPOSES.

    `_process_event_batch` takes the decomposed path only when
    `not event.neg_risk and len(event.markets) > 1`, and the decomposed
    Over/Under legs are the exact shape #2027 measured — `hockey/
    container_member`, outcome 'No', `op 0.001` on a winner. The
    single-market fixture above reaches the parent-field site and never
    those two, so a guard removed from either leg leaves it green.
    """
    def _sub(idx, question, sub_closed):
        return {
            "id": f"m-{idx}",
            "conditionId": f"0x2027game{idx}",
            "question": question,
            "slug": f"flyers-hurricanes-{idx}",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
            "clobTokenIds": f'["{idx}11", "{idx}22"]',
            "bestBid": 0,
            "bestAsk": 1,
            "lastTradePrice": price,
            "closed": sub_closed,
        }

    # Default: the sub-markets carry the event's own flag, as the venue sends
    # them. `sub_closed=False` separates the EVENT flag from the SUB-MARKET
    # flag, which is the only way to prove either arm alone.
    own = closed if sub_closed is None else sub_closed
    return {
        "id": "evt-2027-game",
        "title": "Flyers vs. Hurricanes",
        "slug": "flyers-vs-hurricanes-game",
        "active": True,
        "closed": closed,
        "archived": False,
        "endDate": end_date,
        "startDate": "2026-05-03T23:00:00Z",
        "negRisk": False,
        "markets": [
            _sub(1, "Flyers vs. Hurricanes", own),
            _sub(
                2,
                "Flyers vs. Hurricanes: total over 5.5",
                second_market_closed or own,
            ),
        ],
    }


def _parsed_game(**kwargs):
    svc = PolymarketAPIService()
    event = svc._parse_event(_venue_game_event(**kwargs))
    assert event is not None, "the parser refused a venue-shaped payload"
    assert len(event.markets) > 1 and not event.neg_risk, (
        "this fixture must reach the DECOMPOSED path, not the parent-field one"
    )
    return event


def _venue_single_child_event(*, price, child_closed):
    """CERT-3202's shape: ONE sub-market, settled, under an OPEN parent.

    Every other arm of the refusal is deliberately silenced so that only the
    per-child one can fire:

    * the parent is `closed: False` and `archived: False`, so the event arm
      says nothing;
    * `endDate` is months away, so the `resolution_date` arm says nothing;
    * there is exactly one market, so the writer takes the PARENT-FIELD path
      and the decomposed sub-market site — which already had this guard — is
      never reached.

    A two-sided book with a last trade, so `has_real_trading` is True on both
    of its arms and the leg is one the writer genuinely wants to open. The
    price is off the book's midpoint (0.985) on purpose, so the fabricated-
    midpoint filter cannot drop the leg and leave the test inert.
    """
    return {
        "id": "evt-3202-sole",
        "title": "Flyers vs. Hurricanes",
        "slug": "flyers-vs-hurricanes-sole",
        "active": True,
        "closed": False,
        "archived": False,
        "endDate": "2026-12-01T00:00:00Z",
        "startDate": "2026-05-03T23:00:00Z",
        "negRisk": False,
        "markets": [
            {
                "id": "m-sole",
                "conditionId": "0x3202sole",
                "question": "Flyers vs. Hurricanes",
                "slug": "flyers-hurricanes-sole",
                "outcomes": '["Flyers", "Hurricanes"]',
                "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
                "clobTokenIds": '["s11", "s22"]',
                "bestBid": 0.97,
                "bestAsk": 1.0,
                "lastTradePrice": price,
                "closed": child_closed,
            }
        ],
    }


def _parsed_single_closed_child(*, price, child_closed=True):
    svc = PolymarketAPIService()
    event = svc._parse_event(
        _venue_single_child_event(price=price, child_closed=child_closed)
    )
    assert event is not None, "the parser refused a venue-shaped payload"
    assert len(event.markets) == 1, (
        "this fixture must reach the PARENT-FIELD path, not the decomposed one"
    )
    assert not event.closed and not event.archived, (
        "the PARENT must be open, or the event arm does the refusing and the "
        "per-child arm this case exists to prove is never exercised"
    )
    return event


def _legs_by_external_id(fake):
    return {
        _insert_values(s)["external_id"]: _insert_values(s)
        for s in _outcome_inserts(fake)
    }


class TestTheDecomposedLegsRefuseToo:
    """The two sub-market sites, started through the real writer.

    The parent-field site has a rail test above; these two did not, and they
    are the ones the issue's specimens came through. Both legs of both
    sub-markets are asserted, so a guard deleted from either the Over or the
    Under arm reddens this file.
    """

    async def test_a_settled_game_refuses_both_decomposed_legs(self, monkeypatch):
        event = _parsed_game(
            closed=True, end_date="2026-05-04T00:00:00Z", price=0.99
        )
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)
        for external_id in (
            "0x2027game1_yes",
            "0x2027game1_no",
            "0x2027game2_yes",
            "0x2027game2_no",
        ):
            assert external_id in legs, f"the writer never reached {external_id}"
            assert legs[external_id]["opening_probability"] is None, (
                f"{external_id}: a post-resolution capture was stamped as the opening"
            )
            assert legs[external_id]["opening_captured_at"] is None
        # Narrow: the current price still lands on every refused leg.
        assert legs["0x2027game1_yes"]["current_probability"] == 0.99
        assert legs["0x2027game1_no"]["current_probability"] is not None
        assert stats.get("opening_refused_hindsight", 0) >= 4, (
            "each refused leg counts itself, or 'we stopped' is a belief (#2027)"
        )

    async def test_a_live_game_still_opens_both_decomposed_legs(self, monkeypatch):
        """Non-vacuity: a guard that refused everything would pass the above."""
        event = _parsed_game(
            closed=False, end_date="2026-12-01T00:00:00Z", price=0.6
        )
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)
        assert legs["0x2027game1_yes"]["opening_probability"] == 0.6
        assert legs["0x2027game1_yes"]["opening_captured_at"] is not None
        assert legs["0x2027game1_no"]["opening_probability"] == 0.4
        assert legs["0x2027game1_no"]["opening_captured_at"] is not None
        assert legs["0x2027game2_yes"]["opening_probability"] == 0.6
        assert stats.get("opening_refused_hindsight", 0) == 0

    async def test_one_closed_sub_market_refuses_only_its_own_legs(
        self, monkeypatch
    ):
        """Precision: the taint is per sub-market, not per event.

        CERT-3202 is why the PARENT-FIELD legs are asserted here and not only
        the decomposed pair. A Polymarket event stays open while its children
        settle one by one. This fixture is that state — event open, resolution
        months away, one child `closed=True` — and the parent-field writer used
        to pass `market=None`, so it saw only the open parent and banked the
        settled child's book as that child's opening line. The decomposed legs
        were refused and the parent leg beside them was not.

        Four assertions, two per child, and the mixed field is the point: the
        open child opens on BOTH paths and the closed child is refused on both.
        A repair that simply refused the whole event would red the first pair.
        """
        event = _parsed_game(
            closed=False,
            end_date="2026-12-01T00:00:00Z",
            price=0.6,
            second_market_closed=True,
        )
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)

        # The OPEN child: decomposed pair and parent-field leg all still open.
        assert legs["0x2027game1_yes"]["opening_probability"] == 0.6
        assert legs["0x2027game1_no"]["opening_probability"] == 0.4
        assert legs["0x2027game1"]["opening_probability"] == 0.6, (
            "the open child's parent-field leg lost its opening — the refusal "
            "went event-wide instead of per child"
        )

        # The CLOSED child: decomposed pair AND the parent-field leg refused.
        assert legs["0x2027game2_yes"]["opening_probability"] is None
        assert legs["0x2027game2_no"]["opening_probability"] is None
        assert legs["0x2027game2"]["opening_probability"] is None, (
            "CERT-3202: the closed child's PARENT-FIELD leg banked its settled "
            "book as an opening because the writer asked only the parent"
        )
        assert legs["0x2027game2"]["opening_captured_at"] is None

        # Two decomposed + one parent-field leg, each counting itself.
        assert stats.get("opening_refused_hindsight", 0) == 3

    async def test_a_closed_SOLE_child_under_an_open_parent_is_refused(
        self, monkeypatch
    ):
        """CERT-3202's named specimen, and the one the mixed case cannot cover.

        With a single child there is no open sibling, so every leg the event
        produces belongs to a settled market. That is the shape most likely to
        be read as "the event is live" — the parent's own `closed` flag is
        False and nothing else on the parent contradicts it — and the real
        writer stored the settled 0.99 as `opening_probability`.

        The current price is asserted present on purpose: this refuses the
        opening STAMP only. A repair that dropped the leg would be a different,
        worse change and would pass an assertion that only checked the opening.
        """
        event = _parsed_single_closed_child(price=0.99)
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)

        assert legs, "the writer never reached a leg — the fixture is inert"
        for external_id, leg in legs.items():
            assert leg["opening_probability"] is None, (
                f"{external_id}: a closed sole child under an open parent "
                f"stamped its settled book as the opening line"
            )
            assert leg["opening_captured_at"] is None
            assert leg["current_probability"] == 0.99, (
                f"{external_id}: the current price must still be written — "
                f"this refuses the opening stamp, not the leg"
            )
        assert stats.get("opening_refused_hindsight", 0) >= 1

    async def test_an_open_SOLE_child_under_an_open_parent_still_opens(
        self, monkeypatch
    ):
        """The non-vacuity twin of the case above.

        Same single-child shape, same open parent, same distant resolution —
        only `closed` differs. Without this, a repair that refused every
        sole-child event would pass the CERT-3202 specimen perfectly.
        """
        event = _parsed_single_closed_child(price=0.99, child_closed=False)
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)

        assert legs, "the writer never reached a leg — the fixture is inert"
        for external_id, leg in legs.items():
            assert leg["opening_probability"] == 0.99, (
                f"{external_id}: an OPEN sole child lost its opening — the "
                f"refusal is keyed on the shape, not on settlement"
            )
        assert stats.get("opening_refused_hindsight", 0) == 0

    async def test_a_venue_closed_game_is_refused_on_the_flag_alone(
        self, monkeypatch
    ):
        """The flag arm, isolated from the date arm.

        Resolution is months away and the date arm therefore says nothing —
        only `closed=True` does. Without this case the flag arm is carried
        entirely by the date arm's fixtures, which set both at once.
        """
        event = _parsed_game(
            closed=True,
            end_date="2026-12-01T00:00:00Z",
            price=0.99,
            sub_closed=False,
        )
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)
        assert legs["0x2027game1_yes"]["opening_probability"] is None
        assert legs["0x2027game1_no"]["opening_probability"] is None
        assert stats.get("opening_refused_hindsight", 0) >= 4
