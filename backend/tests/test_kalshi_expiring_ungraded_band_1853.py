"""#1853: a settled Kalshi question is asked about while the venue still has its answer.

## the defect this file guards

`_backfill_kalshi_winners` asks the venue about resolved Kalshi markets in two
budgeted bands (#4057): what settled in the last three days, newest first, and an
ALPHABETICAL tail over every market still lacking an authoritative grade. Neither
of them knows how old a market is. The tail's population never shrinks at its old
end — a market past Kalshi's purge bound can never be answered, so it never
leaves — which means its wrap only grows, and a never-graded market whose answer
is about to be purged waits its alphabetical turn exactly like one that settled
last week. Past the purge it is a blank result (or the column default's false
"Lost") that nobody can ever prove.

Band 7 is gotcha #41's two bounds over the cohort #1853 names: markets with a
leg NO grader has ever touched (`resolution_source IS NULL`), whose venue
settlement is past band 1's floor and still inside the retrievable window
(`PROVABLY_PURGED_AGE_DAYS`), walked OLDEST FIRST on a cursor of its own.

## what is covered WHERE

The WHERE clause and its ordering are executed against a real server in
`tests/integration/test_kalshi_settlement_recency_band_pg.py` (the `#1853` arms):
a fake session agrees with itself. This file covers what is not in the SQL —
the budget split, the band's own cursor lifecycle, its absence from the fast
lane, its place in the fetch order, its receipt, and that its tickers reach the
SAME refusing writer as every other band.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.backfill_winners as bw
from tests import _kalshi_service_fake as kalshi_service_fake
from tests.test_kalshi_settlement_recency_band_4057 import (
    _FakeKalshi,
    _FakeRedis,
    _LoopSession,
    _SessionCM,
    _finalized_event,
)

UTC = timezone.utc
_KEY = "bainluck:kalshi_winner_expiring_ungraded_cursor"
_TAIL_KEY = "bainluck:kalshi_winner_backfill_cursor"
_OLD = datetime(2026, 7, 20, 4, 0, tzinfo=UTC)
_MID = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# the budget: carved out of the tail, never added to the cycle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("limit", [0, 1, 2, 5, 9, 10, 11, 100, 1999, 2000, 2001, 100000])
def test_the_three_bands_sum_to_exactly_the_cycle_budget(limit):
    """Cost-neutral by construction. `kalshi_api` already spends most of the
    phase's wall (#4740); a band ADDED to `limit` would buy reach with time."""
    fresh, expiring, tail = bw._settlement_band_budgets(limit)
    assert fresh + expiring + tail == max(limit, 0)
    assert min(fresh, expiring, tail) >= 0


def test_the_production_cycle_split_is_pinned_as_numbers():
    """2,000 is what the omnibus passes. Pinned as numbers, not a formula, so a
    later edit that hands this band half the tail is a red line, not a drift."""
    assert bw._settlement_band_budgets(2000) == (400, 200, 1400)


def test_the_recency_band_is_unchanged_by_the_new_split():
    """Band 1's slice is taken FIRST and is exactly what it was — the fast lane
    asks about the same fresh tickers it always did."""
    for limit in (2, 5, 10, 100, 2000, 100000):
        assert bw._settlement_band_budgets(limit)[0] == bw._fresh_settlement_budget(limit)[0]


@pytest.mark.parametrize("limit", [2, 3, 5, 10, 11, 2000])
def test_the_tail_always_keeps_at_least_one_slot(limit):
    """An empty tail SELECT deletes band 2's cursor (its wrap arm). A split that
    left band 2 zero slots would reset the 71k-ticker walk to 'A' every cycle."""
    assert bw._settlement_band_budgets(limit)[2] >= 1


def test_a_huge_cycle_caps_the_band():
    _fresh, expiring, _tail = bw._settlement_band_budgets(100000)
    assert expiring == bw._EXPIRING_UNGRADED_MAX_TICKERS


def test_the_window_reads_the_measured_retention_constant_not_a_number():
    """The upper bound is the SKIP-WORK horizon (`kalshi_retention`), fail-open:
    only a provably purged market is left out of the priority band."""
    from app.utils import kalshi_retention

    assert bw._EXPIRING_UNGRADED_PURGE_DAYS is kalshi_retention.PROVABLY_PURGED_AGE_DAYS
    assert bw._EXPIRING_UNGRADED_FLOOR_DAYS is bw._FRESH_SETTLEMENT_FLOOR_DAYS


def test_the_tail_selection_spends_only_what_the_split_leaves_it():
    """The selector applies the SAME split, so the tail statement's LIMIT shrinks
    by exactly band 7's slice."""
    import inspect

    src = inspect.getsource(bw._select_kalshi_settlement_tickers)
    assert "_settlement_band_budgets(limit)" in src


# ---------------------------------------------------------------------------
# the drive
# ---------------------------------------------------------------------------

async def _drive(
    monkeypatch,
    *,
    fresh=(),
    tail=(),
    expiring=(),
    cursor="",
    expiring_cursor=None,
    answers=None,
    limit=2000,
    fast_lane_only=False,
    session=None,
    venue=None,
):
    """The real `_backfill_kalshi_winners`, every selection stubbed.

    `expiring` is a list of (ticker, venue_age_key). The band-7 stub records the
    limit and the cursor it was HANDED: that is the only way to prove the caller
    read band 7's own key, not band 2's.
    """
    seen: dict[str, object] = {"expiring_calls": 0}

    async def _fake_select(session_, limit_, cursor_, *, include_tail=True):
        seen["select"] = {"limit": limit_, "cursor": cursor_, "include_tail": include_tail}
        return list(fresh), (list(tail) if include_tail else [])

    async def _fake_expiring(session_, limit_, cursor_):
        seen["expiring_calls"] += 1
        seen["expiring"] = {"limit": limit_, "cursor": cursor_}
        return list(expiring)

    async def _empty(*_a, **_k):
        return []

    rc = _FakeRedis(cursor)
    if expiring_cursor is not None:
        rc.store[_KEY] = expiring_cursor
    session = session or _LoopSession()
    venue = venue or _FakeKalshi(answers)

    monkeypatch.setattr(bw, "_select_kalshi_settlement_tickers", _fake_select)
    monkeypatch.setattr(bw, "_select_kalshi_expiring_ungraded_tickers", _fake_expiring)
    for name in (
        "_select_kalshi_early_settled_tickers",
        "_select_kalshi_early_settled_longdated_tickers",
        "_select_kalshi_status_sync_tickers",
        "_select_kalshi_retracted_open_tickers",
    ):
        monkeypatch.setattr(bw, name, _empty)
    monkeypatch.setattr(bw, "get_task_session", _SessionCM(session))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: rc)
    fake_service = kalshi_service_fake.install(monkeypatch, venue)

    stats = await bw._backfill_kalshi_winners(limit=limit, fast_lane_only=fast_lane_only)
    kalshi_service_fake.assert_not_captured(fake_service)
    return stats, rc, venue, seen


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_market_nearing_the_purge_is_asked_about_this_cycle(monkeypatch):
    """The ship in one assertion: the tail never offered it this cycle, band 7
    did, and the venue was asked."""
    stats, _rc, venue, seen = await _drive(
        monkeypatch,
        tail=["KXZZZ-26SEP20"],
        expiring=[("KXATPMATCH-26JUL20OLD", _OLD)],
        answers={"KXATPMATCH-26JUL20OLD": _finalized_event("KXATPMATCH-26JUL20OLD-A")},
    )
    assert "KXATPMATCH-26JUL20OLD" in venue.asked
    assert stats["expiring_selected"] == 1
    assert stats["expiring_graded"] == 1
    # Handed the split's own slice, not the whole cycle and not the tail's.
    assert seen["expiring"]["limit"] == bw._settlement_band_budgets(2000)[1]


@pytest.mark.asyncio
async def test_band_seven_is_fetched_before_the_tail(monkeypatch):
    """A phase that dies on its wall (#4740) loses the END of the list. The
    tickers about to expire must not be the ones it loses."""
    _stats, _rc, venue, _seen = await _drive(
        monkeypatch,
        fresh=["KXFRESH-26OCT13"],
        tail=["KXAAA-26SEP20", "KXBBB-26SEP21"],
        expiring=[("KXOLD-26JUL20", _OLD)],
    )
    assert venue.asked == ["KXFRESH-26OCT13", "KXOLD-26JUL20", "KXAAA-26SEP20", "KXBBB-26SEP21"]


@pytest.mark.asyncio
async def test_a_fresh_settlement_keeps_its_place_and_its_receipt(monkeypatch):
    """Control: band 1 is still first and still counted apart. Band 7's ticker
    is graded too, and lands in band 7's receipt, not band 1's."""
    stats, _rc, venue, _seen = await _drive(
        monkeypatch,
        fresh=["KXMLBHIT-26OCT12CINLAD"],
        expiring=[("KXOLD-26JUL20", _OLD)],
        answers={
            "KXMLBHIT-26OCT12CINLAD": _finalized_event("KXMLBHIT-26OCT12CINLAD-X"),
            "KXOLD-26JUL20": _finalized_event("KXOLD-26JUL20-Y"),
        },
    )
    assert venue.asked[0] == "KXMLBHIT-26OCT12CINLAD"
    assert stats["winners_set"] == 2
    assert stats["fresh_graded"] == 1
    assert stats["expiring_graded"] == 1


@pytest.mark.asyncio
async def test_a_ticker_in_two_bands_costs_one_fetch(monkeypatch):
    """The tail can hold a band-7 ticker; the dedup makes it one venue call.
    Band 7 still REPORTS what it selected."""
    stats, _rc, venue, _seen = await _drive(
        monkeypatch,
        tail=["KXOLD-26JUL20", "KXZZZ-26SEP20"],
        expiring=[("KXOLD-26JUL20", _OLD)],
    )
    assert venue.asked == ["KXOLD-26JUL20", "KXZZZ-26SEP20"]
    assert (stats["expiring_selected"], stats["tail_selected"]) == (1, 2)


# ---------------------------------------------------------------------------
# the refusals: band 7 changes WHEN a market is asked about, never what is written
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,result,counter",
    [
        ("finalized", "", "no_result"),
        ("finalized", None, "no_result"),
        ("finalized", "scalar", "ungradeable_result"),
        ("finalized", "void", "ungradeable_result"),
        ("closed", "yes", "ungradeable_result"),
    ],
)
async def test_an_answer_with_no_mappable_winner_writes_no_grade(
    monkeypatch, status, result, counter
):
    """No-result, void, scalar, and a `closed` market's stray value: none is a
    loss. The writer's three-state refusal (CAL-P053 / #1852) holds for band 7's
    tickers because they reach the identical writer."""
    ticker = "KXOLD-26JUL20"
    stats, _rc, _venue, _seen = await _drive(
        monkeypatch,
        expiring=[(ticker, _OLD)],
        answers={ticker: {"markets": [{"ticker": f"{ticker}-A", "status": status, "result": result}]}},
    )
    assert stats["winners_set"] == stats["losers_set"] == 0
    assert stats["expiring_graded"] == 0
    assert stats.get(counter, 0) == 1


@pytest.mark.asyncio
async def test_a_venue_miss_writes_nothing(monkeypatch):
    stats, _rc, _venue, _seen = await _drive(
        monkeypatch, expiring=[("KXGONE-26JUL20", _OLD)], answers={}
    )
    assert stats["api_miss"] == 1
    assert stats["expiring_graded"] == 0


# ---------------------------------------------------------------------------
# the cursor: its OWN key, a full batch advances it, a short batch wraps it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_full_batch_advances_band_sevens_own_key_and_not_the_tails(monkeypatch):
    budget = bw._settlement_band_budgets(20)[1]
    rows = [(f"KXOLD{i:02d}-26JUL20", _OLD) for i in range(budget - 1)] + [("KXMID-26SEP01", _MID)]
    _stats, rc, _venue, _seen = await _drive(
        monkeypatch, limit=20, tail=["KXT-1"], expiring=rows
    )
    assert rc.store[_KEY] == bw._encode_expiring_cursor(_MID, "KXMID-26SEP01")
    # Band 2's cursor moved on band 2's own ticker, never on band 7's.
    assert rc.store[_TAIL_KEY] == "KXT-1"


@pytest.mark.asyncio
async def test_band_seven_reads_its_own_cursor_back(monkeypatch):
    stored = bw._encode_expiring_cursor(_MID, "KXMID-26SEP01")
    _stats, _rc, _venue, seen = await _drive(
        monkeypatch, cursor="KXTAIL", expiring_cursor=stored, tail=["KXT-1"]
    )
    assert seen["expiring"]["cursor"] == (_MID, "KXMID-26SEP01")
    assert seen["select"]["cursor"] == "KXTAIL"


@pytest.mark.asyncio
async def test_a_short_batch_wraps_so_the_next_cycle_restarts_at_the_oldest(monkeypatch):
    """Fewer rows than the budget means the walk reached the young edge of the
    window; the next cycle starts again from the market nearest its purge."""
    stored = bw._encode_expiring_cursor(_OLD, "KXOLD-26JUL20")
    _stats, rc, _venue, _seen = await _drive(
        monkeypatch, expiring_cursor=stored, expiring=[("KXMID-26SEP01", _MID)]
    )
    assert _KEY not in rc.store
    assert _KEY in rc.deleted


@pytest.mark.asyncio
async def test_a_cold_empty_band_deletes_nothing(monkeypatch):
    _stats, rc, _venue, _seen = await _drive(monkeypatch, tail=["KXT-1"], expiring=[])
    assert _KEY not in rc.deleted


# ---------------------------------------------------------------------------
# the cursor moves only past rows whose fetch FINISHED (review HOLD on 586e7fa81b)
# ---------------------------------------------------------------------------

class _FailingKalshi(_FakeKalshi):
    """The venue, failing on one ticker with the exception the caller chooses."""

    def __init__(self, fail_on: str, exc: BaseException):
        super().__init__()
        self._fail_on, self._exc = fail_on, exc

    async def get_event(self, ticker):
        self.asked.append(ticker)
        if ticker == self._fail_on:
            raise self._exc
        return None


def _full_rows(n: int) -> list[tuple[str, datetime]]:
    """n band-7 rows, oldest first, distinct ages so each cursor is unique."""
    return [(f"KXEXP{i:03d}-26JUL", _OLD + timedelta(hours=i)) for i in range(n)]


_PROD_BAND = bw._settlement_band_budgets(2000)[1]  # 200: two fetch batches of 100


@pytest.mark.asyncio
async def test_a_venue_error_on_the_first_fetch_leaves_band_sevens_cursor_where_it_was(monkeypatch):
    """A full selection, then the first venue call raises (swallowed by the
    loop's `except`). Not one of the 200 near-purge markets was asked about, so
    the next cycle must select them again — the cursor stays put."""
    stored = bw._encode_expiring_cursor(_OLD - timedelta(days=1), "KXBEFORE")
    rows = _full_rows(_PROD_BAND)
    stats, rc, _venue, _seen = await _drive(
        monkeypatch,
        expiring=rows,
        expiring_cursor=stored,
        venue=_FailingKalshi(rows[0][0], RuntimeError("venue 500")),
    )
    assert stats["errors"], "the failure must be recorded, not silently absorbed"
    assert rc.store[_KEY] == stored
    assert not any(k == _KEY for k, _t, _v in rc.setex_calls)
    assert _KEY not in rc.deleted


@pytest.mark.asyncio
async def test_a_cancelled_phase_leaves_band_sevens_cursor_where_it_was(monkeypatch):
    """The phase wall (#4740) CANCELS rather than raises: CancelledError is not
    an Exception, so it escapes the loop. The cursor must not have moved."""
    rows = _full_rows(_PROD_BAND)
    venue = _FailingKalshi(rows[0][0], asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await _drive(monkeypatch, expiring=rows, venue=venue)
    import app.tasks.redis_state as rs

    rc = rs.get_redis_client()  # the drive's fake, still patched in
    assert _KEY not in rc.store
    assert not any(k == _KEY for k, _t, _v in rc.setex_calls)


@pytest.mark.asyncio
async def test_a_failure_in_the_second_batch_keeps_its_rows_reachable(monkeypatch):
    """Rows 0-99 were fetched and committed; row 150 raises. The cursor steps to
    row 99 and no further, so rows 100-199 head the next cycle's selection."""
    rows = _full_rows(_PROD_BAND)
    _stats, rc, venue, _seen = await _drive(
        monkeypatch,
        expiring=rows,
        venue=_FailingKalshi(rows[150][0], RuntimeError("venue 500")),
    )
    assert rows[150][0] in venue.asked
    assert rc.store[_KEY] == bw._encode_expiring_cursor(rows[99][1], rows[99][0])


@pytest.mark.asyncio
async def test_a_clean_multi_batch_cycle_advances_to_the_last_row(monkeypatch):
    """Control for the three arms above: when every fetch finishes, the cursor
    lands on the last selected row exactly as before, across two batches."""
    rows = _full_rows(_PROD_BAND)
    _stats, rc, venue, _seen = await _drive(monkeypatch, expiring=rows)
    assert len(venue.asked) == _PROD_BAND
    assert rc.store[_KEY] == bw._encode_expiring_cursor(rows[-1][1], rows[-1][0])
    # Stepped once per batch, never past an unfetched row.
    steps = [v for k, _t, v in rc.setex_calls if k == _KEY]
    assert steps == [
        bw._encode_expiring_cursor(rows[99][1], rows[99][0]),
        bw._encode_expiring_cursor(rows[-1][1], rows[-1][0]),
    ]


@pytest.mark.asyncio
async def test_a_short_batch_that_fails_does_not_wrap(monkeypatch):
    """A short selection wraps only once every row was asked about; a failure
    first keeps the stored position so the unasked rows are not skipped."""
    stored = bw._encode_expiring_cursor(_OLD, "KXOLD-26JUL20")
    rows = [("KXMID-26SEP01", _MID)]
    _stats, rc, _venue, _seen = await _drive(
        monkeypatch,
        expiring_cursor=stored,
        expiring=rows,
        venue=_FailingKalshi(rows[0][0], RuntimeError("venue 500")),
    )
    assert rc.store[_KEY] == stored
    assert _KEY not in rc.deleted


@pytest.mark.asyncio
async def test_a_row_shared_with_band_one_is_counted_where_it_was_fetched(monkeypatch):
    """Band 7's row 150 is also a fresh ticker, so it is fetched FIRST, in band
    1's slot. The first batch then holds it plus rows 0-98; a failure on row 120
    must leave the cursor at row 98 — row 150 being done does not make 99-149
    done."""
    rows = _full_rows(_PROD_BAND)
    _stats, rc, venue, _seen = await _drive(
        monkeypatch,
        fresh=[rows[150][0]],
        expiring=rows,
        venue=_FailingKalshi(rows[120][0], RuntimeError("venue 500")),
    )
    assert venue.asked[0] == rows[150][0]
    assert rc.store[_KEY] == bw._encode_expiring_cursor(rows[98][1], rows[98][0])


def test_the_cursor_round_trips_and_a_garbled_key_reads_as_cold():
    enc = bw._encode_expiring_cursor(_MID, "KXMID-26SEP01")
    assert bw._decode_expiring_cursor(enc) == (_MID, "KXMID-26SEP01")
    assert bw._decode_expiring_cursor(enc.encode()) == (_MID, "KXMID-26SEP01")
    assert bw._decode_expiring_cursor(None) is None
    assert bw._decode_expiring_cursor("") is None
    assert bw._decode_expiring_cursor("not-a-cursor") is None


# ---------------------------------------------------------------------------
# the fast lane never runs band 7
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_fast_lane_neither_selects_nor_moves_band_seven(monkeypatch):
    """48 cycles a day of 200 extra lookups is not inside any existing budget,
    and the fast lane exists for what a reader is looking at NOW. It must not
    select band 7, and must not touch its key — including the wrap delete."""
    stored = bw._encode_expiring_cursor(_MID, "KXMID-26SEP01")
    stats, rc, _venue, seen = await _drive(
        monkeypatch,
        fast_lane_only=True,
        fresh=["KXFRESH-1"],
        expiring_cursor=stored,
        expiring=[("KXOLD-26JUL20", _OLD)],
    )
    assert seen["expiring_calls"] == 0
    assert stats["expiring_selected"] == 0
    assert rc.store[_KEY] == stored
    assert _KEY not in rc.deleted
    assert not any(k == _KEY for k, _t, _v in rc.setex_calls)


@pytest.mark.asyncio
async def test_the_omnibus_runs_band_seven(monkeypatch):
    """Control for the arm above: without it, a build that never ran band 7 at
    all would pass every fast-lane assertion."""
    _stats, _rc, _venue, seen = await _drive(monkeypatch, expiring=[])
    assert seen["expiring_calls"] == 1
