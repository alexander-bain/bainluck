"""#4000, second attempt: the withdrawal has to live on the task that REACHES them.

The first attempt shipped, deployed, ran to a clean success on every pass, and
retired nothing — 0 of 2,542 rows across 104 markets. Nothing was wrong with the
retirement. ``_unpriced_leg_external_ids`` returned exactly the right 76 condition
ids for event 31552 against live Gamma, and ``_retire_unpriced_legs`` nulled
exactly the right rows. Both were mounted on ``_poll_polymarket_markets``, and
that task cannot see these markets at all.

**Measured on production 2026-09-09, three ways that do not share a method:**

* *Venue-side.* Since #219E the discovery poll paginates NEWEST-FIRST under a hard
  2,000-event cap (``order=startDate&ascending=false``, ``max_pages = 20``).
  Offsets 0–1999 spanned ``2026-09-09T06:13Z`` back to ``2026-09-08T19:59Z`` — a
  window ten hours wide. All 104 affected events carry startDates between 2025-07
  and 2026-07. **0 of 104 were inside it.**
* *Our own writes, one pass.* The 06:15:49Z pass ran the new code to completion,
  49.7s, thousands of rows written. It touched **0 of the 104**.
* *Our own writes, 24 hours.* Bucketing the cohort's ``last_updated`` by
  minute-of-hour: the ``:10–:19`` bucket, where the poll runs, holds **0 rows**.
  1,168 rows across 83 of the 104 markets land at ``:50`` — this task.

So the lesson is not about prices at all:

    A pure function proved against a venue payload proves nothing about the
    call site's reach. A discovery pass ordered newest-first has a TIME HORIZON,
    not a coverage guarantee — and the population that goes stale is, by
    construction, the population outside it.

``futures_price_refresh`` reaches them because it does not paginate: it addresses
known markets by id through ``get_events_by_ids``, added under #2199 for exactly
this reason. The tests below drive the REAL entry point rather than the helper,
because "the helper works" was already true when the ship was inert.
"""

import pytest

from app.tasks import futures_price_refresh as fpr

pytestmark = pytest.mark.asyncio


# --- specimens ---------------------------------------------------------------


def _leg(condition_id: str, *, yes=None, bid=None, ask=None, last=None, volume_24h=None):
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=condition_id,
        question=f"Will {condition_id} win?",
        outcomes=["Yes", "No"],
        outcome_prices=[yes, 1.0 - yes] if yes is not None else [],
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        volume_24h=volume_24h,
    )


def _resolves_to_nothing(market) -> bool:
    """Does the resolver actually refuse this leg?

    Asserted at the head of every "refused, not absent" specimen. Both guards
    below sit AFTER ``_resolve_market_probability`` returns None, so a specimen
    the resolver happily prices skips them entirely and the test passes on a
    branch it never entered — a vacuous green that survived deleting the guard.
    """
    from app.tasks.polymarket import _resolve_market_probability

    return _resolve_market_probability(market) is None


def _priced_leg(condition_id: str, yes: float):
    """A leg the venue is quoting, tight-booked — never a retirement candidate."""
    return _leg(condition_id, yes=yes, bid=yes - 0.005, ask=yes + 0.005, last=yes)


def _dead_leg(condition_id: str):
    """The measured shape of a tombstone, copied from live Gamma for event 31552:

    ``active=false  outcomePrices=None  bestBid=0  bestAsk=1  lastTradePrice=0``.
    """
    return _leg(condition_id, yes=None, bid=0.0, ask=1.0, last=0.0)


def _field(event_id: str, legs: list, *, neg_risk=True, closed=False):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(
        id=event_id,
        title="Presidential Election Winner 2028",
        neg_risk=neg_risk,
        closed=closed,
        markets=legs,
    )


class _FakePolyService:
    def __init__(self, *events):
        self._by_id = {e.id: e for e in events}
        self.closed = False

    async def get_events_by_ids(self, event_ids):
        return [{"id": eid} for eid in event_ids if eid in self._by_id]

    def _parse_event(self, raw):
        return self._by_id.get(raw["id"])

    async def close(self):
        self.closed = True


# --- 1. the selection, through THIS task's fetch ------------------------------


class TestTheFetchNamesTheLegsTheVenueQuotesNothingFor:
    async def test_dead_legs_come_back_as_retirement_ids(self):
        event = _field(
            "31552",
            [_priced_leg("0xvance", 0.241), _priced_leg("0xaoc", 0.084),
             _dead_leg("0xperson_bg"), _dead_leg("0xperson_cq")],
        )
        priced, unpriced = await fpr._fetch_polymarket_prices(
            _FakePolyService(event), ["31552"]
        )
        assert [p["external_id"] for p in priced["31552"]] == ["0xvance", "0xaoc"]
        assert unpriced["31552"] == ["0xperson_bg", "0xperson_cq"]

    async def test_a_leg_with_a_bid_is_refused_not_absent(self):
        """The distinction the whole retirement rests on.

        ``_resolve_market_probability`` returns ``None`` both for a leg the venue
        does not quote AND for a quote we merely distrust (#151's evidence gate,
        #1578's fabricated midpoint, Q428's volume bound). Retiring the second
        kind un-prices a live market. A standing bid is the venue speaking, so
        the leg stays.

        The specimen quotes NOTHING and has never traded, so the resolver
        refuses it — but it carries a standing 0.11 bid, and the bid alone has to
        be enough. Q432's untraded wide book (``[0.32, 0.68]`` over 0.11/0.53,
        last 0.53) is the more famous shape and was this test's first draft; it
        is the wrong specimen here, because its 0.53 last trade means the TRADE
        guard holds the line and deleting the bid guard leaves the test green.
        Two guards, two specimens, or one of them is untested.
        """
        refused = _leg("0xwide", yes=None, bid=0.11, ask=1.0, last=None)
        assert _resolves_to_nothing(refused), "specimen never reaches the guard"
        assert not refused.last_trade_price, (
            "the trade guard must not be what passes this"
        )

        event = _field("31552", [_priced_leg("0xvance", 0.241), refused])
        _, unpriced = await fpr._fetch_polymarket_prices(
            _FakePolyService(event), ["31552"]
        )
        assert unpriced["31552"] == []

    async def test_a_leg_that_has_traded_is_refused_not_absent(self):
        """The trade guard on its own, with the bid at zero so the bid guard
        cannot be what holds the line. A placeholder 50/50 over a dead book is
        refused by ``_is_placeholder_outcome``, but the leg has traded at 0.53 —
        that is evidence, not an absence.
        """
        refused = _leg("0xtraded", yes=0.5, bid=0.0, ask=1.0, last=0.53)
        assert _resolves_to_nothing(refused), "specimen never reaches the guard"
        assert refused.best_bid == 0.0, "the bid guard must not be what passes this"

        event = _field("31552", [_priced_leg("0xvance", 0.241), refused])
        _, unpriced = await fpr._fetch_polymarket_prices(
            _FakePolyService(event), ["31552"]
        )
        assert unpriced["31552"] == []

    async def test_a_non_negrisk_event_retires_nothing(self):
        """The scope gate. Only single-winner fields were measured, and the other
        shapes price through gates whose refusals mean different things."""
        event = _field(
            "31552",
            [_priced_leg("0xa", 0.6), _dead_leg("0xb")],
            neg_risk=False,
        )
        _, unpriced = await fpr._fetch_polymarket_prices(
            _FakePolyService(event), ["31552"]
        )
        assert unpriced["31552"] == []


# --- 2. the safety properties -------------------------------------------------


class TestNothingRetiresWithoutAPriceBesideIt:
    async def test_a_field_nobody_quotes_at_all_retires_nothing(self):
        """🔴 THE SAFETY PROPERTY, and stricter than the discovery poll's.

        A by-id refresh cannot otherwise tell a dark venue from a dead leg —
        both arrive as "no price" down the same wire. One live quote on the same
        event is the venue answering, which makes silence on a sibling leg a
        statement about the LEG. With no quote anywhere, this task says nothing
        rather than blanking a whole board on one bad read.
        """
        event = _field("31552", [_dead_leg("0xa"), _dead_leg("0xb")])
        priced, unpriced = await fpr._fetch_polymarket_prices(
            _FakePolyService(event), ["31552"]
        )
        assert priced == {}
        assert unpriced == {}, f"retired legs with no price beside them: {unpriced}"

    async def test_a_settled_event_retires_nothing(self):
        """#2222's shape. A settled field is stamped, not repriced — and a
        settlement's last price is not a quote we should be withdrawing."""
        event = _field(
            "86515", [_dead_leg("0xa"), _priced_leg("0xb", 0.5)], closed=True
        )
        priced, unpriced = await fpr._fetch_polymarket_prices(
            _FakePolyService(event), ["86515"]
        )
        assert priced["86515"] is fpr.VENUE_SETTLED
        assert "86515" not in unpriced

    async def test_every_retirement_key_names_an_event_we_priced(self):
        """The invariant behind both tests above, asserted over a mixed batch so
        it cannot pass by there being only one event in play."""
        events = _FakePolyService(
            _field("1", [_priced_leg("0xa", 0.4), _dead_leg("0xb")]),
            _field("2", [_dead_leg("0xc")]),
            _field("3", [_dead_leg("0xd"), _priced_leg("0xe", 0.9)], closed=True),
        )
        priced, unpriced = await fpr._fetch_polymarket_prices(
            events, ["1", "2", "3"]
        )
        assert set(unpriced) == {"1"}
        for event_id in unpriced:
            assert priced.get(event_id) not in (None, fpr.VENUE_SETTLED)


# --- 3. the reach: the real entry point, on the by-id path --------------------


class _Result:
    def __init__(self, rows=(), scalar=0, rowcount=0):
        self._rows = list(rows)
        self._scalar = scalar
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _RetirementHarness:
    """Runs ``_refresh_stale_futures_prices`` against a fake session.

    The point of going through the entry point rather than calling the helper is
    the whole of this file: the helpers passed 15 tests and the ship still
    retired nothing, because nothing tested that the task holding them ever sees
    a market like this. Here the candidate scan hands back a real Polymarket row
    addressed BY ID, exactly as production's ``:50`` pass does.
    """

    #: one tier-1 polymarket field, addressable: (id, source, external_id, volume,
    #: poly_event_id, venue_settled_since)
    CLASS_ROWS = [(112897, "polymarket", "0xfield", 703_977_358, "31552", None)]

    def __init__(self, event):
        self.event = event
        self.service = _FakePolyService(event)
        self.retirement_updates: list[dict] = []
        self.priced_writes: list[float] = []

    class _Session:
        def __init__(self, outer):
            self.outer = outer

        async def execute(self, statement, params=None):
            sql = str(statement)
            if "WITH pool AS MATERIALIZED" in sql:
                if "COUNT(*)" in sql:
                    return _Result(scalar=0)
                return _Result(self.outer.CLASS_ROWS)
            if "SELECT id, external_id FROM futures_outcomes" in sql:
                return _Result(
                    [(11, "0xvance"), (12, "0xaoc"),
                     (13, "0xperson_bg"), (14, "0xperson_cq")]
                )
            if sql.lstrip().upper().startswith("INSERT INTO FUTURES_ODDS_SNAPSHOTS"):
                self.outer.priced_writes.append(
                    float(statement.compile().params["probability"])
                )
                return _Result()
            if sql.lstrip().upper().startswith("UPDATE FUTURES_OUTCOMES"):
                params_ = statement.compile().params
                if "current_probability" in params_ and (
                    params_["current_probability"] is None
                ):
                    self.outer.retirement_updates.append(dict(params_))
                    # rowcount is DERIVED from the ids the statement carries, not
                    # a constant: a fake that always answers "2" would let the
                    # `legs_retired` assertions pass on a statement naming one leg
                    # or none, which is the same vacuous pass this file is about.
                    named = params_.get("external_id_1") or []
                    return _Result(rowcount=len(named))
                return _Result(rowcount=1)
            if "fm.id = ANY(:market_ids)" in sql:
                return _Result([], scalar=0)
            return _Result()

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def run(self, monkeypatch):
        import contextlib

        session = self._Session(self)

        @contextlib.asynccontextmanager
        async def _fake_session(**_budget):
            # #4482: statement/lock budgets arrive as kwargs on
            # `get_task_session` rather than as `SET`s on the session.
            yield session

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        # `set`, not `lambda: set()` — CodeQL flags the wrapper as an unnecessary
        # lambda (note-level) and it is right: calling `set` IS the empty set.
        monkeypatch.setattr(
            "app.utils.tournament_register.registered_market_ids", set
        )
        from app.utils.feed_served_markets import SERVED_EMPTY, ServedSignal

        monkeypatch.setattr(
            "app.utils.feed_served_markets.served_signal",
            lambda: ServedSignal(state=SERVED_EMPTY, ids=[], shapes=2),
        )
        monkeypatch.setattr(
            "app.utils.feed_served_markets.note_served_signal_healthy",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(fpr, "_load_attempt_skips", lambda ids: set())
        monkeypatch.setattr(fpr, "_mark_attempted", lambda ids, ttl_seconds: None)
        monkeypatch.setattr(
            "app.services.polymarket_api.PolymarketAPIService", lambda: self.service
        )
        return await fpr._refresh_stale_futures_prices()


class TestTheHourlyByIdRefreshActuallyRetires:
    """🔴 The test that would have caught the first attempt shipping inert."""

    async def test_the_run_withdraws_the_dead_legs_and_says_how_many(
        self, monkeypatch
    ):
        harness = _RetirementHarness(
            _field(
                "31552",
                [_priced_leg("0xvance", 0.241), _priced_leg("0xaoc", 0.084),
                 _dead_leg("0xperson_bg"), _dead_leg("0xperson_cq")],
            )
        )
        summary = await harness.run(monkeypatch)

        assert harness.retirement_updates, (
            "the by-id refresh priced the field and withdrew nothing — this is "
            "the exact state production was in after the first #4000 ship"
        )
        assert summary["legs_retired"] == 2
        # and the live legs were still refreshed by the same pass
        assert sorted(harness.priced_writes) == pytest.approx([0.084, 0.241])

    async def test_a_field_with_no_dead_legs_reports_zero_not_nothing(
        self, monkeypatch
    ):
        """Gotcha #53. The stat is reported unconditionally so "nothing to retire"
        and "the retirement never ran" stop arriving as the same empty summary —
        which is precisely how the first attempt read green for two passes."""
        harness = _RetirementHarness(
            _field("31552", [_priced_leg("0xvance", 0.241), _priced_leg("0xaoc", 0.084)])
        )
        summary = await harness.run(monkeypatch)

        assert harness.retirement_updates == []
        assert "legs_retired" in summary
        assert summary["legs_retired"] == 0

    async def test_the_retirement_never_touches_a_leg_the_pass_repriced(
        self, monkeypatch
    ):
        """Ordering, not coincidence: the withdrawal runs AFTER the write, so a
        leg that regained a price this pass has already been rewritten and is not
        in the unpriced list. Asserted as the absence of overlap rather than as
        an ordering of calls, because the ordering is only a means to it."""
        harness = _RetirementHarness(
            _field(
                "31552",
                [_priced_leg("0xvance", 0.241), _dead_leg("0xperson_bg")],
            )
        )
        summary = await harness.run(monkeypatch)

        retired_ids = {
            eid
            for u in harness.retirement_updates
            for eid in (u.get("external_id_1") or [])
        }
        # The positive half first. "0xvance was not retired" is true of a run
        # that retired nothing at all, which is the state this whole file exists
        # to catch — the exclusion only means something once something WAS
        # excluded from.
        assert summary["legs_retired"] == 1
        assert "0xperson_bg" in retired_ids
        assert "0xvance" not in retired_ids
