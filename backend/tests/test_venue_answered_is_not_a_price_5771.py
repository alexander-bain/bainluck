"""#5771 — a market the venue has ANSWERED stops being priced as if it were live.

A Kalshi market that has settled quotes ``yes_bid 0.0000 / yes_ask 1.0000``, and
``_kalshi_yes_probability`` falls THROUGH that empty book to the last trade on
purpose (``kalshi_resolution_sweep`` depends on the fall-through). So the
settlement artifact ``0.0100`` / ``0.9900`` reaches the price writer wearing the
shape of a quote, and bainluck.com/events/15298125 served **99% – 1%** for a
Sevilla vs Valencia match that had not kicked off.

🔴 THE FIXTURES ARE VERBATIM PRODUCTION PAYLOAD, READ FROM THE VENUE'S OWN API
(``api.elections.kalshi.com/trade-api/v2/markets``) on 2026-09-12 22:2xZ. A test
about "what a settled Kalshi market looks like" that invents the payload is a
test agreeing with itself; these dicts carry the venue's real key names, its
decimal-string dollar format, and — the load-bearing one — ``result: ""`` on a
market that is still trading, which is why the refusal test is truthiness after
a strip and never ``is not None``.

The parse is the REAL ``KalshiAPIService._parse_event``, not a stub, so a change
to how ``result`` or the ``*_dollars`` pair is read fails here.
"""

import asyncio

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks import futures_price_refresh as fpr


# --- the venue's payload, verbatim ------------------------------------------

#: `KXNCAAFGAME-26SEP12LTLSU` — THE CONTROL. LSU 99.5% over Louisiana Tech is a
#: genuine blowout line: `status active`, `result ''`, a two-sided book and
#: 30,070 / 123,869 in 24h volume. It sits at the same extreme as the defect and
#: must be priced exactly as before, which is the whole reason the refusal is
#: keyed on `result` and not on how extreme the ladder looks.
#:
#: Note its book is bid 0.9900 / ask 1.0000 — an ask of 1.00 is NOT the empty
#: book, so a refusal written against `yes_ask == 1.0` would blank this control.
NCAAF_ACTIVE = {
    "event_ticker": "KXNCAAFGAME-26SEP12LTLSU",
    "title": "Louisiana Tech at LSU",
    "markets": [
        {
            "ticker": "KXNCAAFGAME-26SEP12LTLSU-LSU",
            "status": "active",
            "result": "",
            "yes_bid_dollars": "0.9900",
            "yes_ask_dollars": "1.0000",
            "last_price_dollars": "0.9900",
            "close_time": "2026-09-14T23:30:00Z",
        },
        {
            "ticker": "KXNCAAFGAME-26SEP12LTLSU-LT",
            "status": "active",
            "result": "",
            "yes_bid_dollars": "0.0100",
            "yes_ask_dollars": "0.0200",
            "last_price_dollars": "0.0200",
            "close_time": "2026-09-14T23:30:00Z",
        },
    ],
}

#: `KXLALIGAGAME-26SEP13SEVVCF` — THE DEFECT. Settled 2026-09-11T21:34:08Z, two
#: days before the kickoff its own rules call "originally scheduled for Sep 13,
#: 2026". Every rung: bid 0.0000 / ask 1.0000, a declared `result`, and a
#: `last_price_dollars` that is the settlement value.
LALIGA_FINALIZED = {
    "event_ticker": "KXLALIGAGAME-26SEP13SEVVCF",
    "title": "Sevilla vs Valencia",
    "markets": [
        {
            "ticker": "KXLALIGAGAME-26SEP13SEVVCF-VCF",
            "status": "finalized",
            "result": "no",
            "yes_bid_dollars": "0.0000",
            "yes_ask_dollars": "1.0000",
            "last_price_dollars": "0.0100",
            "close_time": "2026-09-11T21:32:31Z",
        },
        {
            "ticker": "KXLALIGAGAME-26SEP13SEVVCF-SEV",
            "status": "finalized",
            "result": "yes",
            "yes_bid_dollars": "0.0000",
            "yes_ask_dollars": "1.0000",
            "last_price_dollars": "0.9900",
            "close_time": "2026-09-11T21:32:31Z",
        },
        {
            "ticker": "KXLALIGAGAME-26SEP13SEVVCF-TIE",
            "status": "finalized",
            "result": "no",
            "yes_bid_dollars": "0.0000",
            "yes_ask_dollars": "1.0000",
            "last_price_dollars": "0.0100",
            "close_time": "2026-09-11T21:32:31Z",
        },
    ],
}


def _mixed():
    """One answered leg beside one still trading, on one event ticker.

    Kalshi settles a game's three legs together, so this shape is a SERIES
    event, not a game — but the per-leg refusal is what makes the class safe
    either way, and CERT-751 is on record for what happens when a parent is
    retired on the strength of one settled child.
    """
    return {
        "event_ticker": "KXMIXED-26",
        "title": "mixed",
        "markets": [
            dict(LALIGA_FINALIZED["markets"][1]),  # answered, last 0.9900
            dict(NCAAF_ACTIVE["markets"][1]),  # trading, bid 0.01 / ask 0.02
        ],
    }


class _Venue:
    """`get_event` over a fixed payload; the PARSER is the real one."""

    def __init__(self, raw):
        self._raw = raw
        self._svc = KalshiAPIService(api_key=None)

    async def get_event(self, ticker, with_nested_markets=True):
        return self._raw

    def _parse_event(self, raw):
        return self._svc._parse_event(raw)


def _fetch(raw):
    return asyncio.run(fpr._fetch_kalshi_prices(_Venue(raw), "T"))


# --- 1. the answered test itself --------------------------------------------


class TestTheAnsweredTest:
    def test_the_empty_string_kalshi_sends_on_a_live_market_is_not_an_answer(self):
        """The trap this helper exists for.

        Kalshi sends `result: ""` while a contract trades — not `None`. So
        `result is not None` is TRUE of every active market on the venue, and a
        refusal written that way blanks the entire book.
        """
        assert fpr._venue_answered("") is False
        assert fpr._venue_answered("   ") is False
        assert fpr._venue_answered(None) is False

    def test_the_venues_two_verdicts_are_both_answers(self):
        assert fpr._venue_answered("yes") is True
        assert fpr._venue_answered("no") is True

    def test_a_losing_verdict_counts_exactly_as_much_as_a_winning_one(self):
        """`no` is the majority of a settled field and the half a `is_winner`
        test would miss — the same asymmetry #5246 was missing."""
        answered = [m["result"] for m in LALIGA_FINALIZED["markets"]]
        assert answered.count("no") == 2
        assert all(fpr._venue_answered(r) for r in answered)


# --- 2. the control must not move -------------------------------------------


class TestTheGenuineBlowoutIsUntouched:
    def test_the_ncaaf_control_is_priced_exactly_as_before(self):
        """LSU 99.5% is a real line. If this moves, the ship is a regression.

        0.995 is the midpoint of the venue's own bid 0.9900 / ask 1.0000 — the
        tight-book arm of `_kalshi_yes_probability`, unchanged by this ship.
        """
        priced = _fetch(NCAAF_ACTIVE)
        assert priced is not fpr.VENUE_SETTLED
        by_ticker = {p["external_id"]: p["probability"] for p in priced}
        assert by_ticker["KXNCAAFGAME-26SEP12LTLSU-LSU"] == pytest.approx(0.995)
        assert by_ticker["KXNCAAFGAME-26SEP12LTLSU-LT"] == pytest.approx(0.015)

    def test_an_ask_of_one_dollar_is_not_by_itself_a_settlement(self):
        """The mutant that reads the BOOK instead of the venue's word.

        The control's ask is 1.0000 — the same ask the settled market quotes.
        Only the bid and the `result` differ, and a refusal keyed on the ask
        alone would blank a live 99.5% favourite.
        """
        asks = {m["yes_ask_dollars"] for m in NCAAF_ACTIVE["markets"]}
        assert "1.0000" in asks
        assert _fetch(NCAAF_ACTIVE) is not fpr.VENUE_SETTLED


# --- 3. the defect ----------------------------------------------------------


class TestAnAnsweredEventIsSettled:
    def test_the_sevilla_event_is_venue_settled_and_prices_nothing(self):
        assert _fetch(LALIGA_FINALIZED) is fpr.VENUE_SETTLED

    def test_before_this_ship_it_returned_the_settlement_as_a_price(self):
        """Non-vacuity: the artifact really is priceable, so the refusal has work.

        Driving the venue's own numbers through the untouched price helper
        reproduces exactly the 0.99 / 0.01 ladder production served — if this
        went `None` the refusal above would be passing on an empty input.
        """
        from app.tasks.kalshi import _kalshi_yes_probability

        sev = LALIGA_FINALIZED["markets"][1]
        assert _kalshi_yes_probability(0.0, 1.0, 0.99) == pytest.approx(0.99)
        assert sev["last_price_dollars"] == "0.9900"

    def test_a_mixed_event_prices_the_live_leg_and_skips_the_answered_one(self):
        priced = _fetch(_mixed())
        assert priced is not fpr.VENUE_SETTLED
        assert [p["external_id"] for p in priced] == [
            "KXNCAAFGAME-26SEP12LTLSU-LT"
        ]

    def test_the_whole_event_verdict_is_taken_over_the_RAW_markets(self):
        """A market our parser DROPS must not turn a live event into a settlement.

        `_parse_market` returns None on anything that raises — here a `volume`
        arriving as a non-numeric string — so deciding "every market is
        answered" over the PARSED subset lets one unreadable LIVE market flip
        the verdict and retire a market on our own parser bug. The dropped row
        below is the only live one, so the two readings disagree: raw says
        mixed, parsed says settled.
        """
        unreadable_but_live = {
            "ticker": "KXPARTIAL-26-LIVE",
            "status": "active",
            "result": "",
            "volume": "not-a-number",
            "yes_bid_dollars": "0.4000",
            "yes_ask_dollars": "0.4200",
        }
        svc = KalshiAPIService(api_key=None)
        assert svc._parse_market(unreadable_but_live) is None  # the premise

        raw = {
            "event_ticker": "KXPARTIAL-26",
            "markets": [dict(LALIGA_FINALIZED["markets"][1]), unreadable_but_live],
        }
        assert svc._parse_event(raw) is not None
        assert len(svc._parse_event(raw).markets) == 1  # parsed list IS all-answered
        assert _fetch(raw) is not fpr.VENUE_SETTLED

    def test_a_purged_book_is_still_settled_and_a_404_still_is_not(self):
        """The two pre-existing verdicts survive the new branch (#2222)."""
        assert _fetch({"event_ticker": "KXUCL-26"}) is fpr.VENUE_SETTLED
        assert asyncio.run(fpr._fetch_kalshi_prices(_Venue(None), "KX?")) is None


# --- 4. the withdrawal half -------------------------------------------------


class TestTheWithdrawalStatement:
    """A gate that only refuses to write freezes the number already on the row.

    These assert the statement's SCOPE, which is the only thing that makes the
    write safe: it is the event's own clock, and nothing else.
    """

    SQL = str(fpr._KALSHI_WITHDRAW_PRE_KICKOFF_SQL)

    def test_it_is_scoped_to_an_event_that_has_not_started(self):
        assert "e.status = 'scheduled'" in self.SQL
        assert "e.commence_time > NOW()" in self.SQL

    def test_it_does_not_borrow_the_crowned_refusal_from_its_sibling(self):
        """SEVVCF's 99% IS the crowned leg — excluding it leaves the hero wrong
        and withdraws only the two 1% rungs beside it."""
        assert "is_winner" not in self.SQL
        assert "is_winner IS NOT TRUE" in str(fpr._KALSHI_RETIRE_DELISTED_SQL)

    def test_it_withdraws_the_quote_and_never_the_grade_or_the_opening(self):
        assert "current_probability = NULL" in self.SQL
        assert "current_american_odds = NULL" in self.SQL
        assert "opening_probability" not in self.SQL
        assert "last_updated" not in self.SQL

    def test_it_only_touches_the_market_it_was_handed(self):
        assert "fo.market_id = :market_id" in self.SQL
        assert "fm.id = :market_id" in self.SQL


# --- 5. the wiring: the statement actually RUNS on a settled market ----------


class _Result:
    def __init__(self, rows=(), scalar=0):
        self._rows = list(rows)
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _RecordingSession:
    """Records the statement OBJECTS, so a renamed constant cannot pass.

    The pool arm hands back one Kalshi market; everything else is inert. The
    identity of `_KALSHI_WITHDRAW_PRE_KICKOFF_SQL` is what the assertions read,
    not a substring of the SQL — a test that greps the executed text would go
    green against any statement that happened to mention `commence_time`.
    """

    KALSHI_ROW = (60482102, "kalshi", "KXLALIGAGAME-26SEP13SEVVCF", 924_270, None, None, 1, 1)

    def __init__(self):
        self.statements = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.statements.append((statement, params))
        sql = str(statement)
        if "pool AS MATERIALIZED" in sql:
            if "COUNT(*)" in sql:
                return _Result(scalar=0)
            return _Result([self.KALSHI_ROW])
        if statement is fpr._KALSHI_WITHDRAW_PRE_KICKOFF_SQL:
            # Three rungs, the shape production holds for SEVVCF.
            return _Result([(1,), (2,), (3,)])
        if statement is fpr._KALSHI_WITHDRAW_EVENT_HERO_SQL:
            # One event — the specimen's — cleared of its Kalshi blend key.
            return _Result([(924_270,)])
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


async def _drive(monkeypatch, session, *, verdict):
    import contextlib

    @contextlib.asynccontextmanager
    async def _fake_session(**_kw):
        yield session

    class _Svc:
        async def close(self):
            return None

    monkeypatch.setenv("KALSHI_API_KEY", "test-key")
    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.utils.tournament_register.registered_market_ids", lambda: set()
    )
    from app.utils.feed_served_markets import SERVED_UNAVAILABLE, ServedSignal

    monkeypatch.setattr(
        "app.utils.feed_served_markets.served_signal",
        lambda: ServedSignal(state=SERVED_UNAVAILABLE, ids=[]),
    )
    monkeypatch.setattr(
        "app.utils.feed_served_markets.note_served_signal_healthy", lambda *a, **k: None
    )
    monkeypatch.setattr(fpr, "_load_attempt_skips", lambda ids: set())
    monkeypatch.setattr(fpr, "_mark_attempted", lambda ids, ttl_seconds: None)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", lambda: _Svc())
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", lambda: _Svc())

    async def _scan(_session, _ids):
        return {}

    async def _reach(*a, **kw):
        return None

    async def _fetch(_service, _external_id):
        return verdict

    monkeypatch.setattr(fpr, "_scan_kalshi_frozen_certain", _scan)
    monkeypatch.setattr(fpr, "_kalshi_reach_arm", _reach)
    monkeypatch.setattr(fpr, "_fetch_kalshi_prices", _fetch)
    return await fpr._refresh_stale_futures_prices()


class TestTheRunWithdrawsAndCounts:
    def test_a_venue_settled_market_runs_the_withdrawal_and_reports_it(self, monkeypatch):
        session = _RecordingSession()
        stats = asyncio.run(_drive(monkeypatch, session, verdict=fpr.VENUE_SETTLED))

        run = [
            params
            for stmt, params in session.statements
            if stmt is fpr._KALSHI_WITHDRAW_PRE_KICKOFF_SQL
        ]
        assert run == [{"market_id": 60482102}]
        assert stats["venue_settled"] == 1
        assert stats["pre_kickoff_quotes_withdrawn"] == 3

    def test_it_does_not_run_when_the_venue_still_has_a_book(self, monkeypatch):
        """The other direction. A live event must not have its quotes withdrawn."""
        session = _RecordingSession()
        stats = asyncio.run(_drive(monkeypatch, session, verdict=[]))

        assert not [
            1
            for stmt, _ in session.statements
            if stmt is fpr._KALSHI_WITHDRAW_PRE_KICKOFF_SQL
        ]
        assert stats["pre_kickoff_quotes_withdrawn"] == 0

    def test_the_counter_is_reported_even_when_nothing_is_withdrawn(self, monkeypatch):
        """`venue_settled` without its companion cannot be read: a pass that
        found nothing frozen and a pass whose statement matched nothing both
        arrive as silence otherwise."""
        session = _RecordingSession()
        stats = asyncio.run(_drive(monkeypatch, session, verdict=None))
        assert "pre_kickoff_quotes_withdrawn" in stats


# --- 6. CERT-2772's repair: the statement that clears the PAGE ---------------


class TestTheHeroStatement:
    """The leg and the number a reader sees are two different rows.

    CERT-2772: the withdrawal above made `futures_outcomes.current_probability`
    NULL and `bainluck.com/events/15298125` went on serving 99%, because the
    hero and the chart read `Event.win_probability_sources` — stamped by the
    15-minute matcher and never re-derived when its source row goes quiet.
    These assert the scope of the statement that repairs it; the SERVED number
    itself is proved against real rows in
    `tests/integration/test_futures_price_refresh_writes_pg.py::TestTheVenueAnsweredAndThePageHasToStopSayingNinetyNine`,
    because a recording double cannot observe a page.
    """

    SQL = str(fpr._KALSHI_WITHDRAW_EVENT_HERO_SQL)

    def test_it_is_scoped_to_an_event_that_has_not_started(self):
        """Settled means settled: a finished contest SHOULD carry its terminal
        number, and this must be inert there by construction."""
        assert "e.status = 'scheduled'" in self.SQL
        assert "e.commence_time > NOW()" in self.SQL

    def test_it_removes_the_key_rather_than_zeroing_it(self):
        """The blend's vocabulary is membership — `compute_aggregate_probability`
        weighs the keys that are present. Any value we could write there would
        be a number we do not have."""
        assert "SET win_probability_sources = e.win_probability_sources - 'kalshi'" in (
            " ".join(self.SQL.split())
        )
        # It READS `current_probability` in its second arm and must never WRITE
        # one: the assertion is on the assignment, not on the word.
        assert "current_probability =" not in self.SQL
        assert "opening_home_probability" not in self.SQL

    def test_it_speaks_only_for_kalshi(self):
        """Polymarket, the sportsbook blend and the card's metadata key are not
        collateral: nothing here has read anything about them."""
        assert "polymarket" not in self.SQL
        assert "betting" not in self.SQL
        assert "espn" not in self.SQL

    def test_it_has_both_arms_and_they_are_not_the_same_arm(self):
        """Arm 1 is attribution — the stored entry names the market that wrote
        it, so a DIFFERENT valid Kalshi speaker is untouched. Arm 2 is the
        pre-attribution shape, where the only safe test is that no Kalshi price
        survives on the event at all."""
        assert "'{kalshi,eligibility,market_id}'" in self.SQL
        assert "NOT EXISTS" in self.SQL
        assert "fo2.current_probability IS NOT NULL" in self.SQL

    def test_it_only_speaks_for_the_market_it_was_handed(self):
        assert "fm.id = :market_id" in self.SQL
        assert "e.id = fm.event_id" in self.SQL


class TestTheRunClearsTheHero:
    def test_the_hero_statement_runs_and_is_counted(self, monkeypatch):
        session = _RecordingSession()
        stats = asyncio.run(_drive(monkeypatch, session, verdict=fpr.VENUE_SETTLED))

        run = [
            params
            for stmt, params in session.statements
            if stmt is fpr._KALSHI_WITHDRAW_EVENT_HERO_SQL
        ]
        assert run == [{"market_id": 60482102}]
        assert stats["pre_kickoff_heroes_cleared"] == 1

    def test_it_runs_after_the_quote_withdrawal_and_before_the_commit(
        self, monkeypatch
    ):
        """The ORDER is the argument, not a style point.

        Arm 2 asks whether any Kalshi price is still standing on the event. Run
        BEFORE the quote withdrawal, that question answers itself with the legs
        we are in the middle of retiring, and the key would survive on every
        single-market event — the exact case the specimen is. Run in a separate
        transaction, a page could be left serving 99% while the "don't look
        again" stamp survived.
        """
        session = _RecordingSession()
        asyncio.run(_drive(monkeypatch, session, verdict=fpr.VENUE_SETTLED))

        order = [stmt for stmt, _ in session.statements]
        quote = order.index(fpr._KALSHI_WITHDRAW_PRE_KICKOFF_SQL)
        hero = order.index(fpr._KALSHI_WITHDRAW_EVENT_HERO_SQL)
        assert quote < hero, "the hero arm would read the legs we are retiring"
        assert session.commits >= 1

    def test_a_live_venue_clears_nothing(self, monkeypatch):
        session = _RecordingSession()
        stats = asyncio.run(_drive(monkeypatch, session, verdict=[]))

        assert not [
            1
            for stmt, _ in session.statements
            if stmt is fpr._KALSHI_WITHDRAW_EVENT_HERO_SQL
        ]
        assert stats["pre_kickoff_heroes_cleared"] == 0

    def test_the_counter_is_reported_even_when_nothing_is_cleared(self, monkeypatch):
        """`pre_kickoff_quotes_withdrawn` without its companion cannot be read:
        quotes withdrawn and no hero cleared is FINE (no blend key, or a second
        speaker still standing), a hero cleared with no quote withdrawn is worth
        reading about, and one number says neither."""
        session = _RecordingSession()
        stats = asyncio.run(_drive(monkeypatch, session, verdict=None))
        assert "pre_kickoff_heroes_cleared" in stats
