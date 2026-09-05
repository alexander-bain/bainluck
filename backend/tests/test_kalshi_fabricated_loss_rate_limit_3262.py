"""CAL-P1014 (#3262) — a venue rate refusal is a budget stop, never a verdict.

THE DEFECT, measured against production on 2026-09-05 through the shipping
endpoint. Every one of these calls is the same rail at the same point in the
sort; only ``limit`` changes:

    POST …/kalshi-fabricated-loss?apply=false&limit=10  ->  {"answered": 10}
    POST …/kalshi-fabricated-loss?apply=false&limit=20  ->  {"answered": 14, "unknown": 6}
    POST …/kalshi-fabricated-loss?apply=false&limit=40  ->  {"answered": 25, "unknown": 15}

and all 12 sampled ``unknown`` rows carried ``lookup: lookup_failed:429``. The
count tracked the PAGE SIZE, not the market age — an identical 6-of-20 at every
probe from 86 days down to 10 — and the refusals were always the page's tail.
``KalshiAPIService.get_markets`` is the one method on that client with no 429
handling at all (its sibling ``get_market`` retries three times with backoff),
so the drain walked into the venue's limit and the exception arrived here.

Why that was worse than a wasted call: ``unknown`` is a per-market verdict, the
row counted as EXAMINED, and ``keyset_after`` resumes at the last examined row.
So a linear paged drain at the real ``APPLY_MARKET_CAP`` of 40 stepped its
cursor past 15 markets per page that nobody had asked the venue about, and no
resume ever came back for them. On the ~7,000 answerable markets in this
population that is ~2,600 silently abandoned — while the rail reported success.

The fix keeps gotcha #36 intact (404 and transport failure are still
indistinguishable, still ``unknown``) and splits out only the one case the next
call would answer differently. These tests are the class guard: **the cursor
must never advance past a market the venue was not actually asked about.**
"""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _venue_specimens() -> dict:
    return json.loads(
        (FIXTURES / "kalshi_fabricated_loss_specimens_p056.json").read_text()
    )


def _stored_legs() -> dict:
    return json.loads(
        (FIXTURES / "kalshi_fabricated_loss_stored_legs_p058.json").read_text()
    )


# ---------------------------------------------------------------------------
# A minimal driver for the SHIPPING `_dry_run`, so these assertions are about
# the rail and not about a model of it.
# ---------------------------------------------------------------------------


class _Rate429(Exception):
    """What httpx raises through `raise_for_status` on a 429."""

    def __init__(self):
        super().__init__("429 Too Many Requests")
        self.response = SimpleNamespace(status_code=429)


class _NotFound(Exception):
    def __init__(self):
        super().__init__("404")
        self.response = SimpleNamespace(status_code=404)


def _work_row(order: int, ticker: str):
    """One row of `_WORK_SQL`, in the sort position the walk sees it.

    `resolution_date` ascends with `order` and the id does NOT, deliberately:
    the rail's sort key is `(resolution_date, id)` and a fixture whose two
    orders agree cannot catch a cursor that compares on the wrong one.
    """
    from datetime import datetime, timedelta, timezone

    return SimpleNamespace(
        market_id=9_500_000 - order,
        event_ticker=ticker,
        mutex=True,
        sport="soccer",
        our_status="open",
        resolution_date=datetime(2026, 7, 1, tzinfo=timezone.utc)
        + timedelta(days=order),
        age_days=60.0 - order,
    )


class _Session:
    """Answers `_WORK_SQL` and `_legs`, and nothing else."""

    def __init__(self, rows, legs_by_market):
        self._rows = rows
        self._legs = legs_by_market
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "statement_timeout" in sql:
            return SimpleNamespace(all=lambda: [])
        if "FROM futures_outcomes" in sql and "market_id = :mid" in sql:
            legs = self._legs.get(params["mid"], [])
            return SimpleNamespace(all=lambda: legs)
        return SimpleNamespace(all=lambda: list(self._rows))

    async def rollback(self):  # pragma: no cover - only on a select failure
        pass


def _drive(monkeypatch, *, venue_by_ticker, rows, legs_by_market, **kwargs):
    """Run the shipping `_dry_run` against a scripted venue."""
    import app.services.kalshi_api as kalshi_api

    calls: list[str] = []

    class _Service:
        async def get_markets(self, *, event_ticker=None, **_):
            calls.append(event_ticker)
            answer = venue_by_ticker[event_ticker]
            if isinstance(answer, Exception):
                raise answer
            return answer, None

        async def close(self):
            pass

    monkeypatch.setattr(kalshi_api, "KalshiAPIService", _Service)

    async def _no_bank(plan):
        return True, "test: not banked"

    monkeypatch.setattr(rail, "_save_plan", _no_bank)

    import time

    session = _Session(rows, legs_by_market)
    coro = rail._dry_run(
        session,
        kwargs.pop("limit", 40),
        kwargs.pop("after_id", None),
        kwargs.pop("after_date", None),
        kwargs.pop("sport", None),
        time.monotonic(),
    )
    return coro, calls


async def _run(monkeypatch, **kwargs):
    coro, calls = _drive(monkeypatch, **kwargs)
    return await coro, calls


# ---------------------------------------------------------------------------


class TestTheBoundaryTellsRateFromContent:
    @pytest.mark.asyncio
    async def test_a_429_is_reported_as_rate_limited_not_as_a_lookup_failure(self):
        class _Limited:
            async def get_markets(self, **_):
                raise _Rate429()

        collected, note = await rail._fetch_venue(_Limited(), "KX-X")
        assert collected is None
        assert rail.venue_rate_limited(note)

    @pytest.mark.asyncio
    async def test_a_404_stays_unknown_because_gotcha_36_still_holds(self):
        class _Missing:
            async def get_markets(self, **_):
                raise _NotFound()

        collected, note = await rail._fetch_venue(_Missing(), "KX-X")
        assert collected is None
        assert note.startswith("lookup_failed")
        assert not rail.venue_rate_limited(note)

    @pytest.mark.asyncio
    async def test_a_transport_error_stays_unknown_too(self):
        class _Broken:
            async def get_markets(self, **_):
                raise RuntimeError("boom")

        collected, note = await rail._fetch_venue(_Broken(), "KX-X")
        assert collected is None
        assert not rail.venue_rate_limited(note)

    def test_the_predicate_refuses_an_absent_note(self):
        assert not rail.venue_rate_limited(None)
        assert not rail.venue_rate_limited("")
        assert not rail.venue_rate_limited("ok")


class TestTheCatchingTest:
    """THE named catching test: the cursor may not step over an unasked market.

    Three markets in sort order. The venue answers the first, then refuses the
    second for rate. Before the fix the second was classified `unknown`, counted
    as examined, and the cursor advanced to it — so a resume began at the THIRD
    market and the second was never asked again by anything.
    """

    def _fixture(self):
        venue = _venue_specimens()
        legs = _stored_legs()
        answered = "KXUSLGAME-26JUL24BIRNEW"
        rows = [
            _work_row(0, answered),
            _work_row(1, "KX-REFUSED-FOR-RATE"),
            _work_row(2, "KXRDDT-26JULDAU"),
        ]
        legs_by_market = {
            rows[0].market_id: [SimpleNamespace(**r) for r in legs[answered]],
            rows[2].market_id: [
                SimpleNamespace(**r) for r in legs["KXRDDT-26JULDAU"]
            ],
        }
        venue_by_ticker = {
            answered: venue[answered],
            "KX-REFUSED-FOR-RATE": _Rate429(),
            "KXRDDT-26JULDAU": venue["KXRDDT-26JULDAU"],
        }
        return rows, legs_by_market, venue_by_ticker

    @pytest.mark.asyncio
    async def test_the_cursor_stops_before_the_market_the_venue_refused(
        self, monkeypatch
    ):
        rows, legs_by_market, venue_by_ticker = self._fixture()

        out, calls = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
        )

        assert out["stopped_on_venue_rate_limit"] is True
        assert out["examined"] == 1, "the refused market was NOT examined"
        assert out["next_cursor"]["after_id"] == rows[0].market_id, (
            "the cursor must name the last market the venue actually answered, "
            "so the resume asks the refused one again"
        )
        assert calls == [rows[0].event_ticker, rows[1].event_ticker], (
            "the page stops at the refusal rather than spending the rest of "
            "its lookups against a limit the venue has already asserted"
        )

    @pytest.mark.asyncio
    async def test_the_refused_market_gets_no_verdict_at_all(self, monkeypatch):
        rows, legs_by_market, venue_by_ticker = self._fixture()

        out, _ = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
        )

        assert "unknown" not in out["market_verdicts"], (
            "a rate refusal is not a fact about the market; recording one is "
            "how 15 of every 40 rows became a verdict nobody measured"
        )
        assert "unknown" not in out["declared_exclusions"]
        assert sum(out["market_verdicts"].values()) == out["examined"]

    @pytest.mark.asyncio
    async def test_the_page_does_not_report_itself_exhausted(self, monkeypatch):
        """A short page the venue cut off has finished nothing (gotcha #53)."""
        rows, legs_by_market, venue_by_ticker = self._fixture()

        out, _ = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
            limit=40,
        )

        assert len(rows) < 40, "the fixture is a short page, as the walk's tail is"
        assert out["exhausted"] is False
        assert out["rate_limit_note"]

    @pytest.mark.asyncio
    async def test_the_contract_does_not_call_it_a_cursor_skip(self, monkeypatch):
        rows, legs_by_market, venue_by_ticker = self._fixture()

        out, _ = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
        )

        assert out["cursor_contract"]["reason_codes"] == []
        assert out["success"] is True


class TestAPageThatMakesNoProgressIsStillAResume:
    """The zero-progress case, which is the one that loses an operator.

    If the venue refuses the page's FIRST lookup, nothing is examined and
    `keyset_after` has no position to give. Handing back `null` would be read as
    "start over" by this rail's own documented contract (omitting `after_id`
    starts a fresh walk) — throwing the operator back to the head of the sort,
    597 measured-dead markets behind where they were.
    """

    def _fixture(self):
        rows = [_work_row(0, "KX-REFUSED-FOR-RATE"), _work_row(1, "KX-NEVER-ASKED")]
        return rows, {}, {"KX-REFUSED-FOR-RATE": _Rate429()}

    @pytest.mark.asyncio
    async def test_the_inbound_cursor_is_echoed_rather_than_nulled(self, monkeypatch):
        rows, legs_by_market, venue_by_ticker = self._fixture()

        out, _ = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
            after_id=4242,
            after_date="2026-06-16T12:27:30Z",
        )

        assert out["examined"] == 0
        assert out["stopped_on_venue_rate_limit"] is True
        assert out["next_cursor"] == {
            "after_date": "2026-06-16T12:27:30Z",
            "after_id": 4242,
        }

    @pytest.mark.asyncio
    async def test_the_echo_does_not_make_the_walk_refuse_itself(self, monkeypatch):
        """The echoed id must not reach `cursor_skips_unprocessed`.

        That check compares `next_after_id` against the ids this page did not
        process, but the sort key is `(resolution_date, id)` and id order is NOT
        date order — `_work_row` builds the fixture that way on purpose. Scoring
        the contract on an echoed inbound id would refuse the walk with
        CURSOR_SKIP for standing still.
        """
        rows, legs_by_market, venue_by_ticker = self._fixture()
        assert rows[0].market_id > rows[1].market_id, "id order opposes date order"

        out, _ = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
            after_id=9_999_999,
            after_date="2026-06-16T12:27:30Z",
        )

        assert out["cursor_contract"]["reason_codes"] == []
        assert out["next_cursor"]["after_id"] == 9_999_999

    @pytest.mark.asyncio
    async def test_a_fresh_walk_refused_at_row_one_hands_back_no_cursor(
        self, monkeypatch
    ):
        """With no inbound cursor there is nothing to echo, and `null` is then
        the honest answer: the head of the sort IS where the operator was."""
        rows, legs_by_market, venue_by_ticker = self._fixture()

        out, _ = await _run(
            monkeypatch,
            venue_by_ticker=venue_by_ticker,
            rows=rows,
            legs_by_market=legs_by_market,
        )

        assert out["examined"] == 0
        assert out["next_cursor"] is None
        assert out["stopped_on_venue_rate_limit"] is True


class TestTheOrdinaryPageIsUnchanged:
    @pytest.mark.asyncio
    async def test_no_refusal_means_no_stop_and_no_new_field_noise(
        self, monkeypatch
    ):
        venue = _venue_specimens()
        legs = _stored_legs()
        answered = "KXUSLGAME-26JUL24BIRNEW"
        rows = [_work_row(0, answered)]

        out, calls = await _run(
            monkeypatch,
            venue_by_ticker={answered: venue[answered]},
            rows=rows,
            legs_by_market={
                rows[0].market_id: [SimpleNamespace(**r) for r in legs[answered]]
            },
        )

        assert out["stopped_on_venue_rate_limit"] is False
        assert out["rate_limit_note"] is None
        assert out["examined"] == 1
        assert out["market_verdicts"] == {"answered": 1}
        assert out["next_cursor"]["after_id"] == rows[0].market_id
        assert calls == [answered]
