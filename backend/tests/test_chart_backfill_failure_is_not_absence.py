"""live/042 — CERT-753's two false-`drained` paths.

The cert blocked live/039's 30-day drain on two ways it could report `drained`
while match pages stayed thin, and both are the same disease in two places: a
FAILURE that is indistinguishable from an ABSENCE (gotcha #53, standing notice
7 — the same shape as ESPN's `[]`).

  1. `get_prices_history()` converted every transport and HTTP failure into an
     empty list. `fetch_polymarket_series` then counted it as `api_empty`, the
     drain counted that as "this event genuinely has nothing", and the runner
     advanced a PERMANENT per-tier checkpoint past an event it had never once
     managed to fetch. The event is thin, will stay thin, and the verdict says
     `drained`.

  2. `select_thirty_day_page` inferred exhaustion from the SQL result length
     (`len(rows) < scan`) AFTER a Python loop that stops early at `limit`. With
     250 thin rows and limit=200 the query returned 250 (< the 800 scan), the
     loop broke at 200, and the tier was marked permanently done over 50 rows
     that were never judged.

Every test here is written to FAIL against `28468003`, the blocked subject.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks.chart_backfill_thirty_day import (
    THIRTY_DAY_THIN_POINTS,
    DrainPage,
    _new_summary,
    _tally,
    _verdict,
    select_thirty_day_page,
)
from app.tasks.event_chart_backfill import (
    fetch_kalshi_series,
    fetch_polymarket_series,
)

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _drain():
    """The drain module, resolved LAZILY inside each test.

    🔴 Deliberate, and it is a guard-design rule, not a style choice: a
    module-level import of a symbol the pre-fix tree does not carry
    (`_settle_tier`, `DONE_WITH_FAILURES`, `PolymarketHistoryUnavailable`)
    collapses this whole file into ONE collection error when the repair is
    reverted. A collection error is red for the wrong reason — it proves nothing
    about any individual guard. Resolved here, each test fails on its own claim.
    """
    import app.tasks.chart_backfill_thirty_day as module

    return module


def _unavailable():
    from app.services.polymarket_api import PolymarketHistoryUnavailable

    return PolymarketHistoryUnavailable


# ---------------------------------------------------------------------------
# 1a. The client — an error must not be spelled the same way as "no data"
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, payload, *, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._payload


def _service_whose_clob(*, get):
    service = PolymarketAPIService()
    service.clob_client = MagicMock()
    service.clob_client.get = AsyncMock(side_effect=get)
    return service


async def test_a_transport_failure_raises_rather_than_reading_as_no_history():
    """🔴 THE DEFECT. A timeout and a token with no series returned the SAME
    value, so no caller could ever tell an outage from a data gap."""
    import httpx

    async def boom(*_a, **_k):
        raise httpx.ConnectTimeout("clob.polymarket.com timed out")

    service = _service_whose_clob(get=boom)
    with pytest.raises(_unavailable()):
        await service.get_prices_history(token_id="tok", fidelity=1)


async def test_an_http_error_status_raises_too():
    import httpx

    async def rate_limited(*_a, **_k):
        return _Response(
            None,
            status_error=httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock()
            ),
        )

    service = _service_whose_clob(get=rate_limited)
    with pytest.raises(_unavailable()):
        await service.get_prices_history(token_id="tok", fidelity=1)


async def test_a_body_that_is_not_the_documented_shape_raises():
    """A 200 we cannot read is not an answer either."""

    async def nonsense(*_a, **_k):
        return _Response({"history": "not a list"})

    service = _service_whose_clob(get=nonsense)
    with pytest.raises(_unavailable()):
        await service.get_prices_history(token_id="tok", fidelity=1)


async def test_a_real_empty_answer_is_still_an_empty_list():
    """THE CONTROL, and it is the point: an empty list must keep meaning
    "asked, and the venue holds nothing". If this went red the repair would have
    replaced one conflation with another."""

    async def empty(*_a, **_k):
        return _Response({"history": []})

    service = _service_whose_clob(get=empty)
    assert await service.get_prices_history(token_id="tok", fidelity=1) == []


async def test_a_real_series_still_comes_back():
    async def series(*_a, **_k):
        return _Response({"history": [{"t": 1, "p": 0.5}]})

    service = _service_whose_clob(get=series)
    assert await service.get_prices_history(token_id="tok", fidelity=1) == [
        {"t": 1, "p": 0.5}
    ]


# ---------------------------------------------------------------------------
# 1b. The fetcher — fetch_failed, and it is NOT api_empty
# ---------------------------------------------------------------------------


def _pm_market():
    market = MagicMock()
    market.market_metadata = {"clob_token_ids": ["tok-yes", "tok-no"]}
    market.group_id = "polymarket:1"
    market.external_id = "1"
    return market


def _pm_outcome():
    outcome = MagicMock()
    outcome.rank = 1
    outcome.external_id = "0xcond"
    outcome.name = "Ben Shelton"
    return outcome


async def test_every_fidelity_failing_is_fetch_failed_not_api_empty():
    """🔴 THE DEFECT, one layer up. This is the count the drain reads."""
    service = MagicMock()
    service.get_prices_history = AsyncMock(
        side_effect=_unavailable()("502 Bad Gateway")
    )

    stats: dict = {}
    out = await fetch_polymarket_series(
        service, _pm_market(), _pm_outcome(), stats=stats
    )

    assert out == []
    assert stats["status"] == "fetch_failed"
    assert stats.get("api_empty", 0) == 0, (
        "an outage counted as api_empty is what advanced the checkpoint"
    )
    assert stats["fetch_errors"] == 2, "both fidelities were tried and both failed"


async def test_a_genuinely_silent_token_is_still_api_empty():
    """THE CONTROL. Both fidelities ANSWERED, and answered nothing — that is a
    real absence and must stay one, or the drain would lap forever."""
    service = MagicMock()
    service.get_prices_history = AsyncMock(return_value=[])

    stats: dict = {}
    await fetch_polymarket_series(service, _pm_market(), _pm_outcome(), stats=stats)

    assert stats["api_empty"] == 1
    assert stats.get("status") != "fetch_failed"


async def test_a_failing_fidelity_still_falls_through_to_the_other_one():
    """Half the point of the 1→60 fallback is that ONE token/fidelity pair can
    misbehave on its own. An error on fidelity 1 must not skip fidelity 60."""
    calls: list[int] = []

    async def flaky(*, token_id, interval, fidelity):
        calls.append(fidelity)
        if fidelity == 1:
            raise _unavailable()("timeout")
        return [{"t": 1, "p": 0.6}]

    service = MagicMock()
    service.get_prices_history = AsyncMock(side_effect=flaky)

    stats: dict = {}
    out = await fetch_polymarket_series(
        service, _pm_market(), _pm_outcome(), stats=stats
    )

    assert calls == [1, 60]
    assert out == [{"t": 1, "yes_price": 0.6}]
    assert stats["fetch_errors"] == 1
    assert stats.get("status") != "fetch_failed", (
        "we got the series in the end — this event is filled, not failed"
    )


async def test_one_fidelity_erroring_and_the_other_answering_empty_is_an_absence():
    """The boundary case between the two tests above: the venue DID answer once,
    with nothing. Not every attempt failed, so this is not retryable."""

    async def mixed(*, token_id, interval, fidelity):
        if fidelity == 1:
            raise _unavailable()("timeout")
        return []

    service = MagicMock()
    service.get_prices_history = AsyncMock(side_effect=mixed)

    stats: dict = {}
    await fetch_polymarket_series(service, _pm_market(), _pm_outcome(), stats=stats)

    assert stats["api_empty"] == 1
    assert stats.get("status") != "fetch_failed"


async def test_kalshi_windows_that_all_error_are_fetch_failed_not_api_empty():
    """The same disease on the other venue. An existence lookup cannot rescue a
    fetch that never happened — the series may be entirely inside the chunks we
    never got."""
    service = MagicMock()
    service.get_market_candlesticks_raw = AsyncMock(
        side_effect=RuntimeError("503 Service Unavailable")
    )
    service.get_market = AsyncMock(return_value={"ticker": "X"})

    stats: dict = {}
    out = await fetch_kalshi_series(
        service, "T", start=BASE, end=BASE + timedelta(days=1), stats=stats
    )

    assert out == []
    assert stats["status"] == "fetch_failed"
    assert stats.get("api_empty", 0) == 0
    assert service.get_market.await_count == 0, (
        "an existence check cannot turn an unfetched market into 'no data'"
    )


# ---------------------------------------------------------------------------
# 1c. The drain's census — three outcomes, and only one of them retries
# ---------------------------------------------------------------------------


def _verdict_with(source_stats: dict) -> dict:
    return {"status": "ok", "sources": source_stats, "points_written": 0, "errors": []}


def test_a_fetch_failure_lands_in_failed_not_in_empty():
    summary = _new_summary()
    _tally(summary, _verdict_with({"polymarket": {"status": "fetch_failed"}}))

    assert summary["failed"] == 1
    assert summary["empty_with_no_history"] == 0


def test_a_genuine_absence_lands_in_empty_not_in_failed():
    summary = _new_summary()
    _tally(summary, _verdict_with({"polymarket": {"status": "no_history",
                                                  "api_empty": 1}}))

    assert summary["empty_with_no_history"] == 1
    assert summary["failed"] == 0


def test_a_source_that_threw_is_failed():
    summary = _new_summary()
    _tally(summary, _verdict_with({"kalshi": {"status": "error"}}))

    assert summary["failed"] == 1


def test_a_filled_event_whose_other_source_failed_is_both():
    """Half a chart is not a drained event: the missing half is worth another
    attempt, and the tier must not close over it."""
    summary = _new_summary()
    _tally(summary, _verdict_with({
        "kalshi": {"status": "written", "points_written": 40},
        "polymarket": {"status": "fetch_failed"},
    }))

    assert summary["filled"] == 1
    assert summary["failed"] == 1
    assert summary["empty_with_no_history"] == 0


# ---------------------------------------------------------------------------
# 2. Exhaustion — the loop, not the query
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, event_id, commence_time, point_count):
        self.event_id = event_id
        self.commence_time = commence_time
        self.point_count = point_count


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.params = None

    async def execute(self, _statement, params=None):
        self.params = params
        return _Result(self._rows)


async def test_the_certs_exact_head_reproduction_does_not_strand_its_tail():
    """🔴 CERT-753's repro, to the number. 250 thin rows, limit 200: the scan
    (200 × 4 = 800) came back short, so `len(rows) < scan` was True and the tier
    was marked PERMANENTLY done — over 50 rows the loop broke before judging."""
    rows = [_Row(i, BASE + timedelta(minutes=i), 0) for i in range(250)]

    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=200)

    assert len(page.event_ids) == 200
    assert page.exhausted is False, (
        "50 rows were never judged — this tier is not finished"
    )
    assert page.scanned == 200, "scanned must mean JUDGED, which is what the "\
        "cursor covers"


async def test_the_cursor_stops_at_the_last_row_actually_judged():
    """The other half of the same guarantee: the next page must resume ON the
    tail, not past it."""
    rows = [_Row(i, BASE + timedelta(minutes=i), 0) for i in range(250)]

    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=200)

    assert page.next_cursor == (BASE + timedelta(minutes=199), 199)


async def test_a_short_page_that_the_loop_finished_is_still_exhausted():
    """THE CONTROL. Without it the repair could just answer False forever and
    the drain would never be able to finish."""
    rows = [_Row(i, BASE + timedelta(minutes=i), 0) for i in range(5)]

    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=200)

    assert page.exhausted is True


async def test_a_break_on_the_very_last_row_is_still_exhaustion():
    """The boundary: the loop stopped early, but there was nothing after it."""
    rows = [_Row(i, BASE + timedelta(minutes=i), 0) for i in range(3)]

    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=3)

    assert page.event_ids == [0, 1, 2]
    assert page.exhausted is True


async def test_thick_rows_past_the_break_do_not_count_as_judged_either():
    """A thick row the loop never reached is still a row the cursor never
    passed, so exhaustion is just as wrong there."""
    rows = [_Row(i, BASE + timedelta(minutes=i), 0) for i in range(2)]
    rows += [_Row(9, BASE + timedelta(minutes=9), THIRTY_DAY_THIN_POINTS + 1)]

    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=2)

    assert page.exhausted is False
    assert page.next_cursor == (BASE + timedelta(minutes=1), 1)


# ---------------------------------------------------------------------------
# 3. A FAILED event is retried, not marked done
# ---------------------------------------------------------------------------


def _finished_page() -> DrainPage:
    return DrainPage([1, 2], (BASE, 2), True, 2)


def test_a_tier_that_ended_its_scan_owing_retries_is_not_marked_done():
    """🔴 The whole point. Reaching the end of the scan is not finishing when
    part of the population was never reachable."""
    drain = _drain()
    report: dict = {}
    drain._settle_tier(
        "us_open", _finished_page(), report,
        owed={9001: 1, 9002: 2}, gave_up=0, dry_run=True,
    )

    assert report["status"] == "awaiting_retries"
    assert report["status"] != drain.DONE_CLEAN
    assert report["owed_retries"] == 2


def test_a_clean_finish_is_still_drained():
    """THE CONTROL: the drain must remain able to finish."""
    drain = _drain()
    report: dict = {}
    drain._settle_tier("us_open", _finished_page(), report,
                       owed={}, gave_up=0, dry_run=True)

    assert report["status"] == drain.DONE_CLEAN


def test_giving_up_on_an_event_ends_the_tier_by_naming_it():
    """An event that can never be fetched must not hold the tier open forever —
    but the end state has to SAY so rather than looking finished."""
    drain = _drain()
    report: dict = {}
    drain._settle_tier("us_open", _finished_page(), report,
                       owed={}, gave_up=4, dry_run=True)

    assert report["status"] == drain.DONE_WITH_FAILURES
    assert report["gave_up"] == 4


def test_an_unfinished_page_is_in_progress_whatever_it_owes():
    drain = _drain()
    report: dict = {}
    drain._settle_tier("us_open", DrainPage([1], (BASE, 1), False, 1), report,
                       owed={7: 1}, gave_up=0, dry_run=True)

    assert report["status"] == "in_progress"


def test_a_settle_never_marks_done_while_a_retry_is_owed():
    """The persistence half, not just the report: no `done` key may be written
    while the tier still owes an event."""
    drain = _drain()
    calls: list[tuple] = []
    client = MagicMock()
    client.delete = lambda key: calls.append(("delete", key))
    client.set = lambda key, value: calls.append(("set", key, value))

    original = drain._with_redis
    drain._with_redis = lambda tier, apply: apply(client)
    try:
        drain._settle_tier("us_open", _finished_page(), {},
                           owed={42: 1}, gave_up=0, dry_run=False)
    finally:
        drain._with_redis = original

    assert not any(
        c[0] == "set" and c[1] == "chart_backfill_30d:done:us_open" for c in calls
    ), "marking the tier done is exactly what stranded the failures"


def test_a_dry_run_persists_nothing():
    drain = _drain()
    touched: list = []
    original = drain._with_redis
    drain._with_redis = lambda tier, apply: touched.append(tier)
    try:
        drain._settle_tier("us_open", _finished_page(), {},
                           owed={1: 1}, gave_up=0, dry_run=True)
        drain._settle_tier("us_open", _finished_page(), {},
                           owed={}, gave_up=0, dry_run=True)
    finally:
        drain._with_redis = original

    assert touched == []


# ---------------------------------------------------------------------------
# 3b. The retry hash — the event is remembered BY ID, not re-found by re-walking
# ---------------------------------------------------------------------------


def _record(drain, attempted, failed, prior):
    """Run `_record_attempts` against a recording fake client."""
    calls: list[tuple] = []
    client = MagicMock()
    client.hdel = lambda key, *ids: calls.append(("hdel", key, ids))
    client.hset = lambda key, mapping=None: calls.append(("hset", key, mapping))
    client.incrby = lambda key, n: calls.append(("incrby", key, n))

    original = drain._with_redis
    drain._with_redis = lambda tier, apply: apply(client)
    try:
        result = drain._record_attempts("us_open", attempted, failed, prior)
    finally:
        drain._with_redis = original
    return result, calls


def test_a_failed_event_is_remembered_by_id():
    drain = _drain()
    owed, calls = _record(drain, attempted=[1, 2], failed=[2], prior={})

    assert owed == {2: 1}
    assert ("hset", "chart_backfill_30d:retry:us_open", {"2": "1"}) in calls


def test_an_event_that_stops_failing_is_forgotten():
    """THE CONTROL for the mechanism: the hash must be able to empty, or the
    tier could never be marked done."""
    drain = _drain()
    owed, calls = _record(drain, attempted=[5], failed=[], prior={5: 2})

    assert owed == {}
    assert ("hdel", "chart_backfill_30d:retry:us_open", ("5",)) in calls


def test_attempts_accumulate_across_triggers():
    drain = _drain()
    owed, _ = _record(drain, attempted=[5], failed=[5], prior={5: 1})

    assert owed == {5: 2}


def test_an_event_that_blows_its_budget_is_dropped_and_counted():
    """It leaves the hash — otherwise it holds the tier open forever — but the
    give-up is COUNTED, and that count is what makes the ending
    `drained_with_failures` rather than `drained`."""
    drain = _drain()
    owed, calls = _record(
        drain, attempted=[5], failed=[5], prior={5: drain.MAX_EVENT_RETRIES - 1},
    )

    assert owed == {}
    assert ("incrby", "chart_backfill_30d:gaveup:us_open", 1) in calls


def test_an_untouched_event_keeps_its_place_in_the_queue():
    """A budget that only reached half the owed ids must not forget the rest."""
    drain = _drain()
    owed, _ = _record(drain, attempted=[1], failed=[], prior={1: 1, 2: 1, 3: 2})

    assert owed == {2: 1, 3: 2}


# ---------------------------------------------------------------------------
# 3c. The wiring — the id actually reaches the retry hash
# ---------------------------------------------------------------------------


class _EventRow:
    def __init__(self, event_id):
        self.id = event_id


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _EventSession:
    def __init__(self, present):
        self._present = set(present)
        self.commits = 0

    async def execute(self, statement):
        # The only query `_drain_events` runs is the per-id Event lookup, and the
        # id it binds is the one we care about.
        for param in statement.compile().params.values():
            if param in self._present:
                return _ScalarResult(_EventRow(param))
        return _ScalarResult(None)

    async def commit(self):
        self.commits += 1


async def test_a_fetch_failed_source_makes_the_drain_report_that_event_id(
    monkeypatch,
):
    """🔴 The wiring, end to end within the batch: `fetch_failed` -> `_tally`
    -> `DrainPass.failed` -> the retry hash. Without the id coming back out here,
    every layer below could be right and the event would still be stranded."""
    import app.tasks.event_chart_backfill as engine

    async def verdicts(session, event, **_kw):
        source = "fetch_failed" if event.id == 202 else "no_history"
        return {
            "status": "no_new_points",
            "sources": {"polymarket": {"status": source}},
            "points_written": 0,
            "errors": [],
        }

    monkeypatch.setattr(engine, "backfill_event_chart", verdicts)
    monkeypatch.setattr(
        "app.tasks.chart_backfill_thirty_day.INTER_EVENT_SLEEP_SECONDS", 0
    )

    drain = _drain()
    summary = _new_summary()
    result = await drain._drain_events(
        _EventSession([201, 202]), [201, 202, 203],
        kalshi_service=None, polymarket_service=None,
        min_period_minutes=None, dry_run=True, summary=summary,
    )

    assert result.attempted == [201, 202], "203 has no row — it was never attempted"
    assert result.failed == [202], "only the unreachable one is owed a retry"
    assert result.missing == [203]
    assert summary["empty_with_no_history"] == 1
    assert summary["failed"] == 1
    assert summary["not_found"] == 1


async def test_an_owed_retry_whose_event_row_is_gone_is_dropped_not_held_forever(
    monkeypatch,
):
    """🔴 The false-`drained` defect wearing its OPPOSITE face. An id in the
    retry hash whose event row has since been deleted is never attempted, so
    without reporting it separately it would never be settled — and its tier
    would sit at `awaiting_retries` forever, unable to finish."""
    monkeypatch.setattr(
        "app.tasks.chart_backfill_thirty_day.INTER_EVENT_SLEEP_SECONDS", 0
    )
    drain = _drain()
    summary = _new_summary()
    result = await drain._drain_events(
        _EventSession([]), [404404],
        kalshi_service=None, polymarket_service=None,
        min_period_minutes=None, dry_run=True, summary=summary,
    )

    assert result.attempted == []
    assert result.missing == [404404]

    owed, _ = _record(
        drain, attempted=result.attempted + result.missing,
        failed=result.failed, prior={404404: 1},
    )
    assert owed == {}, "a deleted event owes nothing — it can never be answered"


# ---------------------------------------------------------------------------
# 4. The verdict must not spell the two endings the same way
# ---------------------------------------------------------------------------


def test_a_tier_still_relapping_holds_the_whole_verdict_open():
    drain = _drain()
    summary = {"tiers": {
        "us_open": {"status": "relap_for_failures"},
        "reachable": {"status": drain.DONE_CLEAN},
        "remainder": {"status": drain.DONE_CLEAN},
    }}
    assert _verdict(summary, only_tier=None) == "in_progress"


def test_giving_up_with_failures_is_terminal_but_is_not_drained():
    drain = _drain()
    summary = {"tiers": {
        "us_open": {"status": drain.DONE_WITH_FAILURES},
        "reachable": {"status": drain.DONE_CLEAN},
        "remainder": {"status": drain.DONE_CLEAN},
    }}
    assert _verdict(summary, only_tier=None) == drain.DONE_WITH_FAILURES


def test_all_clean_is_still_plain_drained():
    drain = _drain()
    summary = {"tiers": {t: {"status": drain.DONE_CLEAN}
                         for t in ("us_open", "reachable", "remainder")}}
    assert _verdict(summary, only_tier=None) == drain.DONE_CLEAN
