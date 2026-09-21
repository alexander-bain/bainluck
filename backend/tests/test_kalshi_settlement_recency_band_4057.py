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
    def __init__(self, cursor: str = "", longdated_cursor: str = ""):
        self.store = {"bainluck:kalshi_winner_backfill_cursor": cursor} if cursor else {}
        if longdated_cursor:
            self.store["bainluck:kalshi_winner_longdated_cursor"] = longdated_cursor
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


async def _drive(
    monkeypatch,
    *,
    fresh,
    tail,
    cursor="",
    answers=None,
    limit=2000,
    fast_lane_only=False,
    longdated=None,
    longdated_cursor="",
):
    """Run the real `_backfill_kalshi_winners` with the SELECTION stubbed.

    The selection's SQL is deliberately not exercised here — see the module
    docstring. Everything downstream of it is the real code path.

    `fast_lane_only` drives the #1121-residual half-hourly beat. The stub honours
    `include_tail` rather than trusting the caller to pass `tail=[]`: the whole
    hazard is a tail that is empty BY CONSTRUCTION, so a test that hand-fed the
    emptiness would be asserting its own fixture.
    """
    async def _fake_select(session, limit_, cursor_, *, include_tail=True):
        _fake_select.seen = {
            "limit": limit_,
            "cursor": cursor_,
            "include_tail": include_tail,
        }
        return list(fresh), (list(tail) if include_tail else [])

    # #7857 — band 4's stub. Records the cursor it was HANDED, which is the only
    # way to prove the caller read band 4's own key and not band 2's.
    async def _fake_longdated(session, limit_, cursor_):
        _fake_longdated.seen = {"limit": limit_, "cursor": cursor_}
        return list(longdated or [])

    rc = _FakeRedis(cursor, longdated_cursor=longdated_cursor)
    session = _LoopSession()
    venue = _FakeKalshi(answers)

    monkeypatch.setattr(
        bw, "_select_kalshi_early_settled_longdated_tickers", _fake_longdated
    )
    monkeypatch.setattr(bw, "_select_kalshi_settlement_tickers", _fake_select)
    monkeypatch.setattr(bw, "get_task_session", _SessionCM(session))
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: rc
    )
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: venue
    )

    stats = await bw._backfill_kalshi_winners(
        limit=limit, fast_lane_only=fast_lane_only
    )
    return stats, rc, venue, _fake_select, _fake_longdated


@pytest.mark.asyncio
async def test_a_ticker_that_settled_below_the_cursor_is_asked_about_this_cycle(
    monkeypatch,
):
    """The ship, in one assertion.

    `KXMLBHIT-…` sorts below where the cursor already is, so the tail band never
    offers it. Before this change the venue was not asked; now it is, in the
    same cycle.
    """
    stats, _rc, venue, _, _ld = await _drive(
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
    _stats, rc, _venue, _, _ld = await _drive(
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
    stats, rc, venue, _, _ld = await _drive(
        monkeypatch,
        fresh=["KXMLBHIT-26SEP092210CINLAD"],
        tail=[],
        cursor="ZZZ",
    )
    assert rc.deleted == ["bainluck:kalshi_winner_backfill_cursor"]
    assert rc.setex_calls == []
    assert venue.asked == ["KXMLBHIT-26SEP092210CINLAD"]
    assert stats["tickers_queried"] == 1


# ---------------------------------------------------------------------------
# #1121 residual — the half-hourly fast lane (`grade_fresh_kalshi_settlements`)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_fast_lane_never_touches_the_tail_cursor(monkeypatch):
    """THE TRAP, and the reason `fast_lane_only` is a branch and not a `tail=[]`.

    The fast lane's tail is empty on EVERY run by construction. The wrap branch
    directly above reads an empty tail as "the alphabet is exhausted, start over"
    and DELETEs the cursor — a reading that is correct for the 6-hourly omnibus
    and catastrophic here: at `:09` and `:39` it would reset the 71k-ticker walk
    to 'A' forever, starving band 2 through the one band the fast lane was
    supposed to leave alone (gotcha #34).

    An emptiness that is structural must never be read as an emptiness that is
    informative.
    """
    _stats, rc, _venue, _, _ld = await _drive(
        monkeypatch,
        fresh=["KXNFLRECYDS-26SEP13DALNYG"],
        tail=["KXNEWGLENN-262"],
        cursor="ZZZ",
        fast_lane_only=True,
    )
    assert rc.deleted == []
    assert rc.setex_calls == []


@pytest.mark.asyncio
async def test_the_omnibus_still_wraps_on_the_same_inputs(monkeypatch):
    """The arm above is two-sided, or it proves nothing.

    Identical inputs, `fast_lane_only=False`: the delete MUST fire. Without this
    the test above passes just as happily against a build where the wrap branch
    was deleted outright — which would be a real regression of #4057.
    """
    _stats, rc, _venue, _, _ld = await _drive(
        monkeypatch,
        fresh=["KXNFLRECYDS-26SEP13DALNYG"],
        tail=[],
        cursor="ZZZ",
        fast_lane_only=False,
    )
    assert rc.deleted == ["bainluck:kalshi_winner_backfill_cursor"]


@pytest.mark.asyncio
async def test_the_fast_lane_does_not_read_the_cursor_either(monkeypatch):
    """It passes `""`, not the stored value.

    Band 2 does not run, so the cursor is not merely ignored — there is no
    statement for it to be an input to. Passing the real value would be a live
    coupling to a band this caller has no business observing.
    """
    _stats, _rc, _venue, sel, _ld = await _drive(
        monkeypatch,
        fresh=["KXNFLRECYDS-26SEP13DALNYG"],
        tail=["KXNEWGLENN-262"],
        cursor="KXN",
        fast_lane_only=True,
    )
    assert sel.seen == {"limit": 2000, "cursor": "", "include_tail": False}


@pytest.mark.asyncio
async def test_the_fast_lane_asks_the_venue_about_the_same_fresh_tickers(monkeypatch):
    """The same rows, sooner — never different rows.

    The budget is the SAME `_fresh_settlement_budget(limit)` the omnibus uses, so
    band 1 is character-for-character the set `:45` would have asked about. What
    the fast lane drops is band 2, and only band 2.
    """
    stats, _rc, venue, _, _ld = await _drive(
        monkeypatch,
        fresh=["KXNFLRECYDS-26SEP13DALNYG", "KXNFLREC-26SEP13DALNYG"],
        tail=["KXNEWGLENN-262", "KXRAIN-26SEP09"],
        cursor="KXN",
        fast_lane_only=True,
    )
    assert venue.asked == ["KXNFLRECYDS-26SEP13DALNYG", "KXNFLREC-26SEP13DALNYG"]
    assert (stats["fresh_selected"], stats["tail_selected"]) == (2, 0)


@pytest.mark.asyncio
async def test_a_ticker_in_both_bands_costs_one_venue_fetch(monkeypatch):
    """Dedup. The two bands are selected independently and can overlap."""
    stats, _rc, venue, _, _ld = await _drive(
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
    stats, _rc, _venue, _, _ld = await _drive(
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
    _stats, _rc, _venue, sel, _ld = await _drive(
        monkeypatch, fresh=[], tail=["KXA-1"], cursor="", limit=2000
    )
    # `include_tail` is asserted here too, not omitted: the omnibus is the caller
    # that must ask for BOTH bands, and it is the only one that advances the
    # cursor. #1121's fast lane is the other side of this pair.
    assert sel.seen == {"limit": 2000, "cursor": "", "include_tail": True}


# ---------------------------------------------------------------------------
# #1121 residual — the TASK CONTRACT, asserted directly.
#
# CERT-2851 granted the ship's token and named this gap: every arm above proves
# what `_backfill_kalshi_winners(fast_lane_only=True)` DOES, and the wiring
# suite proves the beat NAME is registered, but nothing asserted that the
# registered beat actually reaches that argument. Those are two different
# claims, and only the second one is what a reader waits on. A wrapper that
# dropped the keyword, or a beat re-pointed at `background` or re-timed onto a
# multiple of five, would leave this whole file green while the half-hour
# grading cadence quietly stopped existing.
#
# Asserted behaviourally — the call is driven and its kwargs captured — rather
# than by scanning the source for the literal `fast_lane_only=True`. A grep
# guard passes on a commented-out line and on a second call site that overrides
# it, so it is a test of the file's text and not of the task.
# ---------------------------------------------------------------------------


def test_the_fast_lane_beat_reaches_the_fast_lane_argument(monkeypatch):
    """The registered task passes `fast_lane_only=True`, and nothing else does.

    The omnibus is the control: the SAME assertion run against
    `backfill_winners` must see the flag absent or False, otherwise this arm
    would pass on a build where `fast_lane_only` defaulted to True and band 2
    had stopped being walked at all.
    """
    import app.tasks as tasks

    seen: dict[str, object] = {}

    async def _noop():
        return {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return _noop()

    monkeypatch.setattr(bw, "_backfill_kalshi_winners", _capture)
    monkeypatch.setattr(tasks, "_tracked_run", lambda _label, coro: coro.close())

    tasks.grade_fresh_kalshi_settlements.run(limit=2000)

    assert seen == {"limit": 2000, "fast_lane_only": True}


def test_the_omnibus_still_asks_for_both_bands(monkeypatch):
    """The control for the arm above — the pair is what makes either falsifiable.

    If `fast_lane_only` ever became True by default, the fast-lane assertion
    would still pass and band 2 — the 71k-ticker alphabetical tail — would stop
    being walked with no test anywhere going red.

    Resolved through the CELERY REGISTRY, and that is not a stylistic choice.
    `app.tasks.backfill_winners` is BOTH a submodule and a task defined in the
    package `__init__`, and the submodule wins the attribute lookup — so the
    obvious `app.tasks.backfill_winners.run()` raises `AttributeError: module
    ... has no attribute 'run'`. A future arm that reached for the task by
    attribute would silently be testing the wrong object if the module ever
    grew a callable of that name.

    THE EFFECTIVE VALUE, NOT THE PASSED ONE, and the first version of this arm
    got that wrong. It read `seen.get("fast_lane_only", False)` — which asks
    what the omnibus PASSES. The omnibus passes nothing, so the arm could not
    see the one mutation it exists to catch: flipping the DEFAULT on
    `_backfill_kalshi_winners` to True survived it (mutation run, exit 0, 25
    passed) while band 2 stopped being walked everywhere. Binding the captured
    kwargs against the real signature materialises the default, so the arm now
    asserts what the callee will actually do rather than what the caller
    happened to spell out.
    """
    import inspect

    import app.tasks as tasks

    original = bw._backfill_kalshi_winners
    seen: dict[str, object] = {}

    async def _noop():
        return {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return _noop()

    monkeypatch.setattr(bw, "_backfill_kalshi_winners", _capture)
    monkeypatch.setattr(tasks, "_tracked_run", lambda _label, coro: coro.close())

    tasks.celery_app.tasks["app.tasks.backfill_winners"].run()

    bound = inspect.signature(original).bind(**seen)
    bound.apply_defaults()
    assert bound.arguments["fast_lane_only"] is False


def test_the_fast_lane_beat_keeps_its_minutes_queue_and_expiry():
    """`:09/:39`, `realtime`, `expires` at exactly one period.

    Each of the three is load-bearing and each was chosen against a measurement
    recorded beside the entry, so each is worth a red line rather than a silent
    drift:

    * the MINUTES avoid both every `*/5`-family beat and the `:45`-`:59` window
      `backfill_winners` actually occupies (818s measured, not the instant its
      crontab names);
    * the QUEUE is `realtime` because `background` runs `task_acks_late=False`,
      so a release destroys a reserved message leaving no trace — a failure mode
      a latency bar cannot survive;
    * `expires` is one period, so a run the lane could not serve is dropped
      rather than queued behind its own successor.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["grade-fresh-kalshi-settlements"]

    assert entry["task"] == "app.tasks.grade_fresh_kalshi_settlements"
    assert entry["schedule"].minute == {9, 39}
    assert entry["options"]["queue"] == "realtime"
    assert entry["options"]["expires"] == 1800

    # The minutes are not merely "these two": they must miss the omnibus window.
    # `backfill_winners` starts at :45 and ran 818s on 2026-09-14, so :45-:59 is
    # occupied, and the fast lane's own 240s soft limit extends each fire by 4.
    for minute in entry["schedule"].minute:
        assert minute + 4 < 45, (
            f"a :{minute:02d} fire can still be running when the omnibus starts "
            "at :45 and writes is_winner across every source"
        )
        assert minute % 5 != 0, (
            f":{minute:02d} is a multiple of five, where every */5, */10, */15 "
            "and */30 beat in this schedule fires"
        )


# ---------------------------------------------------------------------------
# #7857 — band 4's CALLER wiring: its own key, its own advance, its own wrap
# ---------------------------------------------------------------------------
#
# The PG gate proves the STATEMENT selects the right rows. None of it touches the
# caller, and the caller is where the cursor lives — which is where the damage
# would be. `bainluck:kalshi_winner_longdated_cursor` and
# `bainluck:kalshi_winner_backfill_cursor` are one typo apart, and a band 4 that
# advanced band 2's key would reset a 71k-ticker alphabetical walk on every cycle
# while looking entirely healthy (gotcha #34).

_LD_KEY = "bainluck:kalshi_winner_longdated_cursor"
_TAIL_KEY = "bainluck:kalshi_winner_backfill_cursor"


@pytest.mark.asyncio
async def test_band_four_is_asked_about_and_reaches_the_venue(monkeypatch):
    """The ship end-to-end through the caller: selected → asked → graded.

    The venue answers `finalized`/`yes`, which is what production says about the
    specimen's three rungs, so this also pins that the long-dated band's tickers
    flow into the SAME grader as every other band rather than a parallel one.
    """
    stats, _rc, venue, _sel, _ld = await _drive(
        monkeypatch,
        fresh=[],
        tail=[],
        longdated=["FEDHIKE"],
        answers={"FEDHIKE": _finalized_event("FEDHIKE-27DEC31")},
    )

    assert "FEDHIKE" in venue.asked
    assert stats["longdated_selected"] == 1
    assert stats["winners_set"] == 1, (
        "the long-dated band selected the ticker but no grade was written — the "
        "band is decorative unless its tickers reach the writer"
    )


@pytest.mark.asyncio
async def test_band_four_advances_its_OWN_key_and_never_the_tail_cursor(monkeypatch):
    """gotcha #34, and the one-typo failure this file exists to catch.

    The tail is deliberately NON-empty. With `tail=[]` band 2 wraps itself — its
    own correct behaviour — and the delete it issues would be indistinguishable
    from band 4 having stamped on its key. Both bands must be live for this arm
    to be about band 4 at all.
    """
    _stats, rc, _venue, _sel, _ld = await _drive(
        monkeypatch,
        fresh=[],
        tail=["T-26SEP10"],
        cursor="KXN",
        longdated=["AAA-28JAN01", "BBB-28JAN01"],
    )

    assert (_LD_KEY, 86400 * 14, "BBB-28JAN01") in rc.setex_calls
    # Band 2 still advances to its OWN last ticker, and no band-4 value ever
    # lands on its key — the two halves of "they do not share a counter".
    assert (_TAIL_KEY, 86400 * 14, "T-26SEP10") in rc.setex_calls
    assert not [
        c for c in rc.setex_calls if c[0] == _TAIL_KEY and c[2].startswith("BBB")
    ], (
        "band 4's cursor value landed on band 2's key — a 71k-ticker walk would "
        "restart from wherever band 4 happened to stop"
    )
    assert rc.deleted == []


@pytest.mark.asyncio
async def test_band_four_reads_its_own_cursor_back(monkeypatch):
    """A cursor that is written and never read is a cursor that does not exist.

    Without this arm the band re-serves page one for ever and the sweep the whole
    design rests on never happens — and every other arm here still passes.
    """
    _stats, _rc, _venue, _sel, ld = await _drive(
        monkeypatch,
        fresh=[],
        tail=[],
        longdated_cursor="KXFEDHIKE",
        longdated=["L-28JAN01"],
    )

    assert ld.seen["cursor"] == "KXFEDHIKE"
    assert ld.seen["limit"] == bw._EARLY_SETTLED_LONGDATED_MAX_TICKERS


@pytest.mark.asyncio
async def test_an_exhausted_band_four_wraps_its_own_key(monkeypatch):
    """Empty sweep + a cursor = the population is done; restart at 'A' next time.

    Without the wrap the band walks to Z once and then asks about nothing for
    ever, which reads exactly like a healthy idle band.
    """
    _stats, rc, _venue, _sel, _ld = await _drive(
        monkeypatch,
        fresh=[],
        tail=[],
        longdated_cursor="ZZZZ",
        longdated=[],
    )

    assert _LD_KEY in rc.deleted
    assert _TAIL_KEY not in rc.deleted


@pytest.mark.asyncio
async def test_a_cold_band_four_does_not_delete_a_key_it_never_had(monkeypatch):
    """The control for the arm above — `elif`, not `else`.

    An empty sweep on a cold cursor is the ordinary steady state once the
    population is drained; issuing a DELETE on every such cycle would be a
    pointless write and would mask a real wrap in the logs.
    """
    _stats, rc, _venue, _sel, _ld = await _drive(
        monkeypatch, fresh=[], tail=[], longdated=[]
    )

    assert rc.deleted == []


@pytest.mark.asyncio
async def test_the_fast_lane_runs_band_four_because_its_emptiness_is_measured(
    monkeypatch,
):
    """The distinction that makes band 4's wrap safe where band 2's would not be.

    Band 2's statement does not RUN in the fast lane, so its empty tail is
    structural and deleting on it would reset the walk every half hour. Band 4's
    statement runs on every cycle of both lanes, so its emptiness is a
    measurement. This arm pins that band 4 really is asked in the fast lane — if
    it were ever gated on `_use_tail_cursor` the wrap would become the same trap.
    """
    _stats, rc, _venue, _sel, ld = await _drive(
        monkeypatch,
        fresh=[],
        tail=["T-26SEP10"],
        cursor="KXN",
        fast_lane_only=True,
        longdated=["L-28JAN01"],
    )

    assert ld.seen["cursor"] == ""
    assert (_LD_KEY, 86400 * 14, "L-28JAN01") in rc.setex_calls
    # ... and band 2's cursor is still untouched in the fast lane (#1121).
    assert not [c for c in rc.setex_calls if c[0] == _TAIL_KEY]
    assert _TAIL_KEY not in rc.deleted


@pytest.mark.asyncio
async def test_band_four_is_deduped_against_the_bands_above_it(monkeypatch):
    """The four bands are selected independently and may name the same ticker.

    Asking the venue twice in one cycle is wasted quota, and `tickers_queried`
    would over-report the band's reach.
    """
    stats, _rc, venue, _sel, _ld = await _drive(
        monkeypatch,
        fresh=["DUP-26SEP10"],
        tail=[],
        longdated=["DUP-26SEP10"],
        answers={"DUP-26SEP10": _finalized_event("DUP-26SEP10-LEG")},
    )

    assert venue.asked.count("DUP-26SEP10") == 1
    assert stats["longdated_selected"] == 1, (
        "the dedup must not rewrite the band's own receipt — selection and "
        "querying are different counts"
    )
