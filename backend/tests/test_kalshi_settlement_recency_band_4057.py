"""#4057: what settled tonight is asked about tonight, not in nine days.

## the defect this file guards

`_backfill_kalshi_winners` — the `kalshi_api` phase of `backfill_winners`, four
cycles a day — used to pick its work with one query:

    WHERE fm.source='kalshi' AND fm.status='resolved' AND fm.external_id > :cursor
      AND EXISTS (an outcome whose resolution_source is not authoritative)
    ORDER BY fm.external_id ASC LIMIT 2000

An **alphabetical cursor**. Measured on production 2026-09-10 11:05Z, the
population matching that predicate is **71,389 distinct event tickers**, so at
2,000 a cycle one full wrap takes **~8.9 days** — and a market that settles
*below* the cursor's current position is not asked about at the next cycle at
all. It waits for the wrap. That is roughly half of everything that settles.

The specimen, same measurement: the 03:45Z cycle wrote `api_settlement` for
tickers spanning `KXATPCHALLENGERMATCH-26SEP08CARRIT` ->
`KXMLBHRR-26SEP091610WSHSD`; `KXMLBHIT-26SEP092210CINLAD` ("Cincinnati vs Los
Angeles D: Hits", 18 outcomes, 17 priced) sorts INSIDE that span and settled at
05:04Z, after the cursor had gone past. At 11:08Z Kalshi's own
`GET /events/KXMLBHIT-26SEP092210CINLAD?with_nested_markets=true` returned 66
markets, `status: finalized`, results `yes`/`no` per leg. Six hours after the
venue finalized it the reader saw a settled market with no result — not because
a grader failed, but because no grader looked.

## what is covered WHERE, and why it is split that way

**The two WHERE clauses that decide which rows a cycle asks about are NOT
covered here.** A fake session that answers "any statement mentioning
`futures_markets`" with a canned list agrees with itself: delete the recency
floor, the `NOT EXISTS` blank test or the `ungradeable_result` exclusion and
every assertion in this file still passes. They are executed against a real
server in `tests/integration/test_kalshi_settlement_recency_band_pg.py`, which
CI runs in the `search-recall` job.

This file covers the part a server cannot see, because it is not in the SQL:

* the **budget split** — the two bands sum to the caller's `limit`, so the fix
  buys reach without buying wall-clock (`backfill_winners` already dies on its
  budget, #4740);
* the **cursor** advancing from the tail band ALONE — a recency ticker can sort
  anywhere in the alphabet, and parking the cursor on one would skip every tail
  ticker in between: the same reach bug, re-introduced from the other end;
* the **empty-tail wrap**, where the old code's early return would have thrown
  away a recency band that had work in it;
* the **dedup**, so a ticker in both bands costs one venue fetch, not two;
* the **`fresh_graded` counter**, which is the only number that can answer "did
  the thing that settled tonight get graded tonight" — the shared
  `winners_set`/`losers_set` counters are dominated by the 71k-ticker tail.
"""

from __future__ import annotations

import pytest

import app.tasks.backfill_winners as bw


# ---------------------------------------------------------------------------
# the budget rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("limit", [2, 5, 10, 100, 1999, 2000, 2001, 100000])
def test_the_two_bands_sum_to_exactly_the_cycle_budget(limit):
    """Cost-neutral by construction, not by inspection.

    The ship is reach, and the one thing it must not buy reach with is wall
    clock: `prob_and_datagolf` already overruns the 840s wall (#4740). If the
    recency band were ADDED to `limit` instead of carved out of it, this is the
    assertion that would go red.
    """
    fresh, tail = bw._fresh_settlement_budget(limit)
    assert fresh + tail == limit
    assert fresh >= 0 and tail >= 0


def test_the_recency_band_is_capped_so_a_big_cycle_still_drains_the_tail():
    """A share AND a ceiling. Only the share would hand a huge cycle to the band."""
    fresh, tail = bw._fresh_settlement_budget(100000)
    assert fresh == bw._FRESH_SETTLEMENT_MAX_TICKERS
    assert tail == 100000 - bw._FRESH_SETTLEMENT_MAX_TICKERS


def test_the_production_cycle_keeps_most_of_its_budget_on_the_tail():
    """2,000 is what the beat passes. 400/1,600 is the split it must produce.

    Pinned as a NUMBER, not a formula: a later edit that raises the share to
    half a cycle would still satisfy every structural assertion above while
    tripling the tail's wrap time.
    """
    assert bw._fresh_settlement_budget(2000) == (400, 1600)


@pytest.mark.parametrize("limit", [0, 1])
def test_a_degenerate_budget_spends_nothing_on_the_recency_band(limit):
    fresh, tail = bw._fresh_settlement_budget(limit)
    assert fresh == 0
    assert tail == max(limit, 0)


# ---------------------------------------------------------------------------
# the drive: fakes for redis, the venue and the write session
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self, cursor: str = ""):
        self.store = {"bainluck:kalshi_winner_backfill_cursor": cursor} if cursor else {}
        self.setex_calls: list[tuple[str, int, str]] = []
        self.deleted: list[str] = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)


class _Result:
    """Answers the loop's SELECT with nothing and its UPDATE with one row."""

    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount

    def all(self):
        return []


class _LoopSession:
    def __init__(self, update_rowcount: int = 1):
        self._rowcount = update_rowcount
        self.commits = 0

    async def execute(self, stmt, params=None):
        if "UPDATE" in str(stmt).upper():
            return _Result(self._rowcount)
        return _Result(0)

    async def commit(self):
        self.commits += 1
        return None

    async def rollback(self):
        return None


class _SessionCM:
    def __init__(self, session):
        self._session = session

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


class _FakeKalshi:
    """The venue. Records what was asked, answers with a finalized YES leg."""

    def __init__(self, answers: dict[str, object] | None = None):
        self.asked: list[str] = []
        self._answers = answers or {}

    async def get_event(self, ticker):
        self.asked.append(ticker)
        return self._answers.get(ticker)

    async def close(self):
        return None


def _finalized_event(leg_ticker: str) -> dict:
    return {
        "markets": [
            {"ticker": leg_ticker, "status": "finalized", "result": "yes"},
        ]
    }


async def _drive(monkeypatch, *, fresh, tail, cursor="", answers=None, limit=2000):
    """Run the real `_backfill_kalshi_winners` with the SELECTION stubbed.

    The selection's SQL is deliberately not exercised here — see the module
    docstring. Everything downstream of it is the real code path.
    """
    async def _fake_select(session, limit_, cursor_):
        _fake_select.seen = {"limit": limit_, "cursor": cursor_}
        return list(fresh), list(tail)

    rc = _FakeRedis(cursor)
    session = _LoopSession()
    venue = _FakeKalshi(answers)

    monkeypatch.setattr(bw, "_select_kalshi_settlement_tickers", _fake_select)
    monkeypatch.setattr(bw, "get_task_session", _SessionCM(session))
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: rc
    )
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: venue
    )

    stats = await bw._backfill_kalshi_winners(limit=limit)
    return stats, rc, venue, _fake_select


@pytest.mark.asyncio
async def test_a_ticker_that_settled_below_the_cursor_is_asked_about_this_cycle(
    monkeypatch,
):
    """The ship, in one assertion.

    `KXMLBHIT-…` sorts below where the cursor already is, so the tail band never
    offers it. Before this change the venue was not asked; now it is, in the
    same cycle.
    """
    stats, _rc, venue, _ = await _drive(
        monkeypatch,
        fresh=["KXMLBHIT-26SEP092210CINLAD"],
        tail=["KXNEWGLENN-262", "KXRAIN-26SEP09"],
        cursor="KXN",
    )
    assert "KXMLBHIT-26SEP092210CINLAD" in venue.asked
    assert stats["fresh_selected"] == 1
    assert stats["tail_selected"] == 2
    assert stats["tickers_queried"] == 3


@pytest.mark.asyncio
async def test_the_cursor_is_advanced_from_the_tail_band_and_never_from_a_fresh_ticker(
    monkeypatch,
):
    """A recency ticker sorts anywhere. Parking the cursor on one skips the gap.

    Here the recency band holds `ZZZ…`, alphabetically past everything. If the
    cursor were taken from the merged list's tail-of-list — or from the recency
    band — the next cycle would resume past `ZZZ` and never look at the ~40k
    tickers between `KXNEWGLENN` and there.
    """
    _stats, rc, _venue, _ = await _drive(
        monkeypatch,
        fresh=["ZZZTOPOFTHEALPHABET-26SEP10"],
        tail=["KXNEWGLENN-262"],
        cursor="KXN",
    )
    assert [c[2] for c in rc.setex_calls] == ["KXNEWGLENN-262"]


@pytest.mark.asyncio
async def test_an_exhausted_tail_wraps_the_cursor_and_still_runs_the_recency_band(
    monkeypatch,
):
    """The old code returned "nothing to do" the moment the tail came back empty.

    A wrapped cursor is the ONE state in which the tail is empty while fresh
    settlements are piling up, so the early return threw away exactly the work
    this ship exists to do.
    """
    stats, rc, venue, _ = await _drive(
        monkeypatch,
        fresh=["KXMLBHIT-26SEP092210CINLAD"],
        tail=[],
        cursor="ZZZ",
    )
    assert rc.deleted == ["bainluck:kalshi_winner_backfill_cursor"]
    assert rc.setex_calls == []
    assert venue.asked == ["KXMLBHIT-26SEP092210CINLAD"]
    assert stats["tickers_queried"] == 1


@pytest.mark.asyncio
async def test_a_ticker_in_both_bands_costs_one_venue_fetch(monkeypatch):
    """Dedup. The two bands are selected independently and can overlap."""
    stats, _rc, venue, _ = await _drive(
        monkeypatch,
        fresh=["KXRAIN-26SEP09"],
        tail=["KXRAIN-26SEP09", "KXSNOW-26SEP09"],
    )
    assert venue.asked == ["KXRAIN-26SEP09", "KXSNOW-26SEP09"]
    assert stats["tickers_queried"] == 2
    # The bands still REPORT what each of them selected — the dedup is a fetch
    # economy, not a re-statement of what the two queries returned.
    assert (stats["fresh_selected"], stats["tail_selected"]) == (1, 2)


@pytest.mark.asyncio
async def test_the_recency_bands_grades_are_counted_apart_from_the_tails(monkeypatch):
    """`fresh_graded` is the receipt the shared counters cannot give.

    `winners_set`/`losers_set` are dominated by the 1,600-ticker tail, so a
    cycle where the recency band graded NOTHING and one where it graded fifty
    markets look identical in them. Post-deploy this is the number that says
    whether tonight's settlements were graded tonight.
    """
    stats, _rc, _venue, _ = await _drive(
        monkeypatch,
        fresh=["KXMLBHIT-26SEP092210CINLAD"],
        tail=["KXNEWGLENN-262"],
        answers={
            "KXMLBHIT-26SEP092210CINLAD": _finalized_event(
                "KXMLBHIT-26SEP092210CINLAD-CINEDELACRUZ44-1"
            ),
            "KXNEWGLENN-262": _finalized_event("KXNEWGLENN-262-B"),
        },
    )
    # Both were graded — the shared counter sees two...
    assert stats["winners_set"] == 2
    # ...and only the recency band's own counter separates them.
    assert stats["fresh_graded"] == 1


@pytest.mark.asyncio
async def test_the_selection_is_handed_the_whole_cycle_budget_not_a_pre_split_one(
    monkeypatch,
):
    """The split lives in ONE place.

    `_backfill_kalshi_winners` passes `limit` through untouched and
    `_select_kalshi_settlement_tickers` applies `_fresh_settlement_budget`. A
    caller that pre-split it would halve the cycle silently.
    """
    _stats, _rc, _venue, sel = await _drive(
        monkeypatch, fresh=[], tail=["KXA-1"], cursor="", limit=2000
    )
    assert sel.seen == {"limit": 2000, "cursor": ""}
