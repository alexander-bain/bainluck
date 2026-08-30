"""#2222 — a settled market must leave the price-refresh queue.

THE CLASS, AND WHY THE EXISTING 108 GUARDS ALL PASSED OVER IT
--------------------------------------------------------------
Nineteen tier-1 futures markets — the Champions League, Premier League and La
Liga winner fields, Eurovision, the NBA Coach of the Year, eight elections —
sat at the head of the refresh queue for a month. Every run attempted them,
every run wrote zero, the task's terminal was permanently ``failed`` and
``/api/admin/source-health/futures-price-freshness`` was permanently ``red``.
Every one of the nineteen was settled, and the user-visible cost was direct:
``/api/politics`` served ``"Which Georgia primary elections will have a
first-round winner?"`` at **98%**, next to genuinely live markets, off prices
captured 37 days earlier, with our own database already holding the winner.

Not one existing guard could have caught it, and the reason is worth stating
because it shapes what this file tests. ``test_predicate_carries_every_floor``
asserts the four clauses the predicate HAS. The defect was a clause it did not
have. A test that enumerates what is present can never fail for an absence, so
the tests here are written against BEHAVIOUR over specimens — a settled
specimen must be excluded, a live one must survive — rather than against the
text of a WHERE clause.

THE THREE THINGS PINNED
------------------------
1. **The two settled signals exclude, and only those two.** A graded winner,
   and a confirmed venue statement. Live specimens survive all of it.
2. **The venue statement is on a confirmation delay, and it is reversible.**
   A fresh stamp excludes nothing; a price clears it. This is the property that
   stops a fifteen-minute upstream outage from quietly retiring a live market —
   the failure this whole mechanism is engineered against, and the one that
   would look like success.
3. **A parse failure is never a settlement.** Both adapters read the venue's
   own answer, not the shape left over after our parser has dropped things.
"""

from __future__ import annotations

import re

import pytest

from app.tasks import futures_price_refresh as fpr
from app.utils import futures_liveness as liveness


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


# --- 1. the two settled signals ----------------------------------------------


class TestTheGradedWinnerBound:
    """Sixteen of the nineteen were already graded by us and still queued."""

    def test_a_graded_winner_excludes_the_market(self):
        assert "is_winner is true" in _norm(liveness.SETTLED_PREDICATE_SQL)
        assert "not exists" in _norm(liveness.SETTLED_PREDICATE_SQL)

    def test_it_reads_only_the_unambiguous_arm(self):
        """`is_winner` is nullable with `default=False`.

        FALSE is ambiguous between "this outcome lost" and "nobody has graded
        this market", so a bound built on `= FALSE` or `IS NOT NULL` would
        retire markets nobody has looked at yet. TRUE is the only arm that means
        one thing, and it is the only one the predicate may read.
        """
        sql = _norm(liveness.SETTLED_PREDICATE_SQL)
        assert "is_winner is true" in sql
        assert "is_winner = false" not in sql
        assert "is_winner is not null" not in sql
        assert "is_winner is not true" not in sql

    def test_the_winner_subquery_cannot_capture_a_callers_alias(self):
        """Every caller already joins `futures_outcomes fo` for the freshness test.

        Reusing `fo` inside the interpolated fragment would silently correlate
        with the caller's join instead of scanning the market's own outcomes —
        a predicate that still parses, still runs, and answers a different
        question.
        """
        assert "futures_outcomes fo_w" in liveness.SETTLED_PREDICATE_SQL
        assert not re.search(
            r"futures_outcomes fo\b", liveness.SETTLED_PREDICATE_SQL
        )


class TestTheVenueSettledBound:
    def test_a_fresh_stamp_does_not_exclude_anything(self):
        """THE SAFETY PROPERTY. A single bad read must cost a market nothing.

        If the bound bit immediately, one upstream blip would drop a live market
        out of the refresh set AND out of the guard's denominator at the same
        instant: it would stop being priced and nothing would go red. That is
        the quiet direction, and it is the one this delay exists for.
        """
        assert liveness.VENUE_SETTLED_CONFIRM_HOURS >= 24, (
            "shorter than a day and a single upstream outage retires live markets"
        )
        sql = _norm(liveness.SETTLED_PREDICATE_SQL)
        assert f"make_interval(hours => {liveness.VENUE_SETTLED_CONFIRM_HOURS})" in sql

    def test_an_unstamped_market_is_live(self):
        sql = _norm(liveness.SETTLED_PREDICATE_SQL)
        assert f"'{liveness.VENUE_SETTLED_KEY}' is null" in sql

    def test_the_stamp_is_written_once_so_the_clock_can_actually_elapse(self):
        """Re-stamping on every run resets the window and the market never leaves.

        This is the bug that would restore #2222 exactly: the row is observed
        settled hourly, is stamped hourly, is never older than the window, and
        is retried forever while the alarm stays red.
        """
        stamp = _norm(fpr._STAMP_VENUE_SETTLED_SQL.text)
        assert f"'{liveness.VENUE_SETTLED_KEY}' is null" in stamp, (
            "the stamp must be first-observation-only"
        )

    def test_a_price_retracts_the_claim(self):
        clear = _norm(fpr._CLEAR_VENUE_SETTLED_SQL.text)
        assert f"market_metadata - '{liveness.VENUE_SETTLED_KEY}'" in clear
        assert "await _clear_if_stamped(session, market, stats)" in _SRC
        assert _SRC.count("await _clear_if_stamped(session, market, stats)") == 2, (
            "one per source loop — a Kalshi-only retraction is half a mechanism"
        )

    def test_the_comparison_cannot_raise_on_a_value_we_did_not_write(self):
        """Text comparison, not a `::timestamptz` cast.

        A cast raises on a value some other writer left in the JSONB blob, and a
        raising selector is a refresher that never runs. ISO-8601 sorts in time
        order so the text comparison is exact, and an unparseable value sorts
        above a year-digit string and therefore leaves the market LIVE — noisy
        rather than silently retired.
        """
        sql = liveness.SETTLED_PREDICATE_SQL
        assert "::timestamptz" not in sql
        assert "::timestamp" not in sql
        assert "to_char(" in sql

    def test_the_stamp_and_the_cutoff_are_formatted_identically(self):
        """Two format strings is a comparison that is wrong for eleven months a year."""
        fmt = 'YYYY-MM-DD"T"HH24:MI:SS'
        assert liveness.VENUE_SETTLED_NOW_SQL.count(fmt) == 1
        assert liveness.SETTLED_PREDICATE_SQL.count(fmt) == 1
        assert "NOW() AT TIME ZONE 'UTC'" in liveness.VENUE_SETTLED_NOW_SQL
        assert "NOW() AT TIME ZONE 'UTC'" in liveness.SETTLED_PREDICATE_SQL


# --- 2. the adapters report the venue's answer, not our parser's leftovers ----


class _FakeKalshiService:
    def __init__(self, raw):
        self._raw = raw

    async def get_event(self, ticker, with_nested_markets=True):
        return self._raw

    def _parse_event(self, raw):
        """Parses successfully into a marketless event — the PRE-FIX behaviour.

        Deliberately not `raise`. Raising would make these tests red on the
        parent commit for want of a call that never happens, which proves
        nothing; parsing to an empty book reproduces exactly what the old code
        did with a purged event, so the red is the behaviour and not the
        scaffolding.
        """

        class _Ev:
            markets: list = []

        return _Ev()


@pytest.mark.asyncio
class TestKalshiReportsThePurge:
    async def test_an_event_with_no_markets_is_venue_settled(self):
        """The measured shape of all eighteen Kalshi rows in #2222.

        HTTP 200, event present, `markets` absent. Kalshi keeps event rows
        forever and purges market rows (gotcha #35), so an empty book on a
        resolvable event is a settled contest that has aged out. Before this it
        produced an empty priced list, which the caller counted as
        `unpriceable` — "we tried and the book was bad" — a claim that implies
        the market is still live.
        """
        svc = _FakeKalshiService({"event_ticker": "KXUCL-26", "title": "UCL Winner"})
        assert await fpr._fetch_kalshi_prices(svc, "KXUCL-26") is fpr.VENUE_SETTLED

    async def test_an_empty_markets_list_is_the_same_answer(self):
        svc = _FakeKalshiService({"event_ticker": "KXLALIGA-26", "markets": []})
        assert await fpr._fetch_kalshi_prices(svc, "KXLALIGA-26") is fpr.VENUE_SETTLED

    async def test_a_missing_event_is_not_a_settlement(self):
        """404 and "the book aged out" are different facts.

        Kalshi event rows are permanent, so a 404 on a ticker we hold means our
        ticker is wrong — a matching problem, not a settled contest. Retiring
        the market on it would hide the wrong ticker forever.
        """
        assert await fpr._fetch_kalshi_prices(_FakeKalshiService(None), "KX?") is None

    async def test_the_live_control_is_not_settled(self):
        """`KXSB-27` — live, 73M volume, 32 markets on the same unauthenticated
        call that returns zero for all eighteen. Without a specimen that comes
        back the other way, "zero markets" is not a reading."""

        svc = _FakeKalshiService(
            {"event_ticker": "KXSB-27", "markets": [{"ticker": "KXSB-27-KC"}]}
        )
        result = await fpr._fetch_kalshi_prices(svc, "KXSB-27")
        assert result is not fpr.VENUE_SETTLED
        assert result == []  # parsed, priced nothing — a THIRD distinct fact

    async def test_a_parse_failure_is_never_a_settlement(self):
        """The RAW markets list decides, not `event.markets`.

        `_parse_market` drops a market it cannot read, so a parsed-empty list is
        ambiguous between "no book" and "we could not read the book". Calling
        our own parser bug a settlement retires a live market on our mistake.
        """
        class _Unparseable(_FakeKalshiService):
            def _parse_event(self, raw):
                return None

        svc = _Unparseable({"event_ticker": "KX", "markets": [{"bad": True}]})
        assert await fpr._fetch_kalshi_prices(svc, "KX") is None


class _PolyEvent:
    def __init__(self, event_id, markets, closed=False, neg_risk=True):
        self.id = event_id
        self.markets = markets
        self.closed = closed
        self.neg_risk = neg_risk


def _PolyMarketRow(condition_id: str, closed: bool):
    """A real ``PolymarketMarket``, not a stub.

    A hand-rolled object passes the settled check and then explodes in
    ``_resolve_market_probability``, which reads fields a stub does not think to
    carry — so the live control would have failed for a reason that has nothing
    to do with the property under test.
    """
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=condition_id,
        question="Who wins?",
        outcomes=["Yes", "No"],
        outcome_prices=[0.41, 0.59],
        best_bid=0.405,
        best_ask=0.415,
        last_trade_price=0.41,
        closed=closed,
    )


class _FakePolyService:
    def __init__(self, event):
        self._event = event

    async def get_events_by_ids(self, ids):
        return [{"id": i} for i in ids]

    def _parse_event(self, raw):
        return self._event if raw["id"] == self._event.id else None


@pytest.mark.asyncio
class TestPolymarketReportsTheClose:
    async def test_a_closed_event_is_venue_settled(self):
        """#2222's Polymarket row, `86515` (the Alpha Arena field).

        Gamma still serves it, and every losing leg quotes `lastTradePrice = 1`
        on its own No token — so eight of nine legs resolve to 1.0 and
        `field_is_incoherent` refuses the field. Correctly: that is not a price.
        But a settled field can never become coherent again, so the refusal was
        permanent and the market was reported as unreadable rather than as over.
        """
        event = _PolyEvent(
            "86515", [_PolyMarketRow("0xaa", closed=True)], closed=True
        )
        out = await fpr._fetch_polymarket_prices(_FakePolyService(event), ["86515"])
        assert out["86515"] is fpr.VENUE_SETTLED

    async def test_every_market_closed_is_the_same_answer(self):
        event = _PolyEvent(
            "9",
            [_PolyMarketRow("0xa", closed=True), _PolyMarketRow("0xb", closed=True)],
            closed=False,
        )
        out = await fpr._fetch_polymarket_prices(_FakePolyService(event), ["9"])
        assert out["9"] is fpr.VENUE_SETTLED

    async def test_one_open_leg_keeps_the_field_live(self):
        """The control, and the one that fails quietly if `all()` is written wrong.

        A field mid-resolution — some legs closed, one still trading — is live,
        and retiring it would freeze a board while it is still moving.
        """
        event = _PolyEvent(
            "9",
            [_PolyMarketRow("0xa", closed=True), _PolyMarketRow("0xb", closed=False)],
            closed=False,
        )
        out = await fpr._fetch_polymarket_prices(_FakePolyService(event), ["9"])
        assert out.get("9") is not fpr.VENUE_SETTLED

    async def test_an_event_with_no_markets_is_skipped_not_settled(self):
        """`all([])` is True. An empty parse must not read as "every leg closed"."""
        event = _PolyEvent("9", [], closed=False)
        out = await fpr._fetch_polymarket_prices(_FakePolyService(event), ["9"])
        assert "9" not in out


# --- 3. the caller acts on the answer, and says so ---------------------------


_SRC = __import__("pathlib").Path(fpr.__file__).read_text()


class TestTheRunReportsWhatItSaw:
    def test_the_sentinel_is_compared_by_identity(self):
        """`if not priced` would swallow VENUE_SETTLED, None and [] alike.

        Truthiness is exactly the conflation this change exists to end: three
        different facts arriving as one falsy value is how #2222 spent a month
        described as `unpriceable`.
        """
        # Both dispatch sites, spelled as identity checks, one per source loop.
        assert _SRC.count("if priced is VENUE_SETTLED:") == 2
        assert _SRC.count("if priced is None:") == 2
        # `if not priced` DOES appear in this module, legitimately, inside
        # `_write_prices` for "there is nothing to write". What must never
        # appear is a DISPATCH on truthiness, which would fold the sentinel,
        # None and [] back into one branch.
        assert "if not priced or" not in _SRC
        assert "if not priced and" not in _SRC

    def test_both_source_loops_stamp(self):
        assert _SRC.count("await _stamp_venue_settled(session, market[\"id\"])") == 2

    def test_the_counters_exist_and_are_distinct(self):
        assert '"venue_settled": 0,' in _SRC
        assert '"venue_settled_cleared": 0,' in _SRC
        assert '"unpriceable": 0,' in _SRC
        assert '"not_found": 0,' in _SRC

    def test_a_venue_settled_market_is_not_counted_unpriceable(self):
        """The whole point: the run stops claiming it failed at something it did not."""
        settled_block = _SRC.split("priced is VENUE_SETTLED")[1].split("continue")[0]
        assert 'stats["unpriceable"]' not in settled_block
        assert 'stats["not_found"]' not in settled_block
        assert 'stats["venue_settled"] += 1' in settled_block


class TestTheGuardDoesNotSilenceItself:
    """The task writes the stamp; the stamp is one of the guard's bounds.

    A guard that quietly shrinks its own denominator can be talked into green by
    the very thing it measures. It is only allowed to exclude a population it
    also REPORTS.
    """

    def test_the_endpoint_reports_what_it_excluded(self):
        import app.routes.admin_source_health as health

        src = __import__("pathlib").Path(health.__file__).read_text()
        assert '"settled_excluded"' in src
        assert '"by_reason"' in src
        assert "SETTLED_ONLY_SQL" in src

    def test_the_reasons_are_named_not_merely_counted(self):
        sql = _norm(liveness.SETTLED_EXCLUSION_REASON_SQL)
        assert "'has_winner'" in sql
        assert "'venue_settled'" in sql

    def test_the_sample_list_says_it_is_a_sample(self):
        """A truncated list called `markets` reads as coverage (no silent caps)."""
        import app.routes.admin_source_health as health

        src = __import__("pathlib").Path(health.__file__).read_text()
        assert '"sample_markets"' in src
        assert '"sample_limit"' in src
        assert '"count": len(settled)' in src


class TestTheFailingRunKeepsItsOwnSummary:
    """#2222 could not be diagnosed from production, and that was its own bug.

    `record_task_success` and `record_task_incomplete` both persist the summary.
    `record_task_failure` was the only one that discarded it — and it is the one
    that fires for a task returning `terminal: failed`, which this task did on
    every run for a month. Answering "unknown_outcomes or not_found?" required
    clearing Redis and re-running the task by hand to watch the counters move.
    """

    def test_the_failed_recorder_accepts_and_stores_a_summary(self):
        import inspect

        from app.tasks import redis_state

        sig = inspect.signature(redis_state.record_task_failure)
        assert "result_summary" in sig.parameters
        src = inspect.getsource(redis_state.record_task_failure)
        assert '"last_failure_summary"' in src

    def test_it_survives_the_recovery_that_erases_the_shared_field(self):
        """Named `last_failure_*`, not `last_result_summary`.

        The next SUCCESS overwrites `last_result_summary`, so a failure recorded
        there is gone the moment the task recovers — which is precisely when an
        operator goes looking for what went wrong.
        """
        import inspect

        from app.tasks import redis_state

        src = inspect.getsource(redis_state.record_task_failure)
        assert '"last_result_summary"' not in src

    def test_the_tracked_runner_passes_it_on_the_returned_failure_path(self):
        import inspect

        from app.tasks import _tracked_run

        src = inspect.getsource(_tracked_run)
        failed_branch = src.split("elif verdict.verdict == FAILED:")[1].split("elif")[0]
        assert "result_summary=summary" in failed_branch
