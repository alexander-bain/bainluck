"""The gap-create backfill dates a settled game when it was PLAYED (#3511).

`_create_settled_market` was the THIRD commence writer in `app/tasks/kalshi.py`
and the last one still deriving its own date::

    site                                        derivation
    ------------------------------------------------------------------
    `_poll_kalshi_markets`, single-market        `_kalshi_commence_time`   (#3433)
    `_poll_kalshi_markets`, multi-market         `_kalshi_commence_time`   (#3433)
    `_create_settled_market`  (gap-create)       `min(close_times)`        <- this

#3433 replaced exactly that `min(close_times)` in the two poll branches with the
helper, which prefers the venue's own `occurrence_datetime` — when the thing
happens — bounded by `occ <= close` and gated on `is_game or is_dated_fixture`.
Gap-create kept the pre-#3433 shape, so every settled row it minted was dated by
when Kalshi PAID OUT.

## the size of it, measured at the venue rather than assumed

Notice 26a, 2026-09-06: `/events?status=settled&series_ticker=…&with_nested_
markets=true`, which carries `occurrence_datetime` on every nested market. Over a
random 24-row sample of this path's own recent production output, replaying the
helper against the venue's answer: **8 move earlier, by 9 minutes to 32.7 hours,
and none move later.** `KXATPEXACTMATCH-26AUG24NARCIN` is stored at
2026-08-26 01:40Z for a match the venue times at 2026-08-24 17:00Z — two days
wrong. The path is live: 5,292 rows, the newest minted the morning this was
written.

It reaches a reader because the market's date propagates: 260 of the 1,488
linked gap-created rows have an Event whose own `commence_time` is this exact
instant.

## why this file exists beside the real-Postgres one

The round trip lives in
`tests/integration/test_kalshi_game_commence_wiring_real_postgres.py`, whose
"THE GAP-CREATE BRANCH" section is this issue's named acceptance. That file
needs a server and therefore only runs in CI's `search-recall` job.

This one runs everywhere in milliseconds, because `_create_settled_market` takes
`pg_insert` as a PARAMETER: hand it a recorder and the values the statement is
built with can be read directly, with no database and no mock session pretending
to be one. It is the arm that fails on a laptop the moment the derivation is
reverted, rather than twenty minutes later in CI.

What it cannot prove is that the built statement is what the server stores — an
INSERT arm and an `on_conflict` arm can disagree, and only a round trip
distinguishes "the task built a dict" from "the row holds the right instant".
That is the other file's job, deliberately.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.kalshi_api import KalshiEvent, KalshiMarket
from app.tasks.kalshi import _create_settled_market, _GAP_CREATE_START
from app.utils.market_label_normalization import compute_market_tier

# A kickoff inside the gap window, and the venue's settlement close after it.
KICKOFF = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
CLOSE = KICKOFF + timedelta(hours=3, minutes=41)

# A value no fixture carries, so a recorded value can only have come from the
# helper's return.
SENTINEL = datetime(2031, 3, 3, 3, 3, 3, tzinfo=timezone.utc)

# Fixture premises, asserted where they are stated: without these the arms below
# would agree with any derivation at all.
assert KICKOFF < CLOSE, "the occurrence must differ from the close"
assert CLOSE > _GAP_CREATE_START, "a close before the freeze window returns 'pre_gap'"
assert SENTINEL not in (KICKOFF, CLOSE), "the sentinel must match no fixture value"


class _Recorder:
    """A stand-in for `pg_insert` that keeps the values each statement is built with.

    Every builder method returns `self`, so the real call chain
    (`.values(...).on_conflict_do_nothing(...).returning(...)`) runs unchanged and
    the task cannot tell the difference.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, table):
        self._table = getattr(table, "__name__", str(table))
        return self

    def values(self, **kw):
        self.calls.append((self._table, kw))
        return self

    def on_conflict_do_nothing(self, **kw):
        return self

    def on_conflict_do_update(self, **kw):
        return self

    def returning(self, *a):
        return self

    def market_values(self):
        """The values dict of the one FuturesMarket insert."""
        rows = [kw for table, kw in self.calls if table == "FuturesMarket"]
        assert len(rows) == 1, f"expected one market insert, recorded {len(rows)}"
        return rows[0]


def _settled_market(event_ticker, suffix, name, price, *, occurrence, close=CLOSE):
    """One settled market of the shape the settled-events scan returns."""
    return KalshiMarket(
        ticker=f"{event_ticker}-{suffix}",
        event_ticker=event_ticker,
        title=name,
        yes_sub_title=name,
        status="finalized",
        result="yes",
        close_time=close,
        occurrence_datetime=occurrence,
        last_price=price,
        volume=1500,
    )


def _event(ticker, title, category, *, occurrence, close=CLOSE, markets=None):
    return KalshiEvent(
        event_ticker=ticker,
        title=title,
        category=category,
        mutually_exclusive=True,
        markets=markets
        or [_settled_market(ticker, "A", "Home", 0.62, occurrence=occurrence, close=close)],
    )


async def _run(event, *, commence_patch=None):
    """Drive the REAL `_create_settled_market` with a recorded `pg_insert`."""
    svc = MagicMock()
    svc._parse_event = MagicMock(return_value=event)

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=7))
    )

    rec = _Recorder()
    stats = {"markets_created": 0, "outcomes_created": 0}

    ctx = (
        patch("app.tasks.kalshi._kalshi_commence_time", commence_patch)
        if commence_patch is not None
        else None
    )
    if ctx is None:
        outcome = await _create_settled_market(
            session, svc, {}, rec,
            MagicMock(__name__="FuturesMarket"), MagicMock(__name__="FuturesOutcome"),
            compute_market_tier, stats,
        )
    else:
        with ctx:
            outcome = await _create_settled_market(
                session, svc, {}, rec,
                MagicMock(__name__="FuturesMarket"), MagicMock(__name__="FuturesOutcome"),
                compute_market_tier, stats,
            )

    # Three non-exception exits, two of which write nothing: an unasserted
    # "pre_gap"/"skip" would read as a passing arm about a statement that was
    # never built (gotcha #53).
    assert outcome == "created", f"gap-create returned {outcome!r}, not 'created'"
    return rec


@pytest.mark.asyncio
async def test_a_settled_game_is_dated_by_its_occurrence_not_its_settlement():
    rec = await _run(_event("KXNFLGAME-26SEP13BUFNYJ", "Bills at Jets", "Football",
                            occurrence=KICKOFF))
    stored = rec.market_values()["commence_time"]
    assert stored == KICKOFF, (
        f"gap-create built the insert with commence_time={stored}, expected the "
        f"occurrence {KICKOFF}. {CLOSE} means it is back on `min(close_times)` and "
        "every settled row it mints is dated by when Kalshi paid out (#3511)."
    )


@pytest.mark.asyncio
async def test_a_dated_fixture_that_is_not_a_game_ticker_is_covered_too():
    """`KXLIGUE1GAME` is `is_game=None`, `is_dated_fixture=True` (#3562).

    A call site passing only `is_game` — the obvious half-repair — stores the
    close here and passes every other arm in this file.
    """
    rec = await _run(_event("KXLIGUE1GAME-26SEP20OLMPSG", "Marseille vs PSG", "Soccer",
                            occurrence=KICKOFF))
    stored = rec.market_values()["commence_time"]
    assert stored == KICKOFF, (
        f"a dated fixture was built with {stored}, expected {KICKOFF} — gap-create "
        "is passing is_game only, so the 80 series #3562 measured stay on their "
        "settlement instant"
    )


@pytest.mark.asyncio
async def test_the_helpers_return_is_what_the_statement_carries():
    """The wiring claim, stated directly, plus which gates the call opens."""
    spy = MagicMock(return_value=SENTINEL)
    rec = await _run(
        _event("KXNFLGAME-26SEP13WIRE", "Bills at Jets", "Football", occurrence=KICKOFF),
        commence_patch=spy,
    )

    stored = rec.market_values()["commence_time"]
    assert stored == SENTINEL, (
        f"the statement carries {stored}, not the helper's return {SENTINEL} — "
        "gap-create calls `_kalshi_commence_time` and discards it, or derives the "
        "date itself again"
    )

    assert spy.call_count == 1, f"expected one helper call, got {spy.call_count}"
    markets, kwargs = spy.call_args.args[0], spy.call_args.kwargs
    assert len(markets) == 1, (
        f"gap-create passed {len(markets)} markets — it must hand the helper the "
        "event's own list, or the earliest-start rule runs over the wrong set"
    )
    assert kwargs.get("is_game") is True, (
        f"called with is_game={kwargs.get('is_game')!r} for a KXNFLGAME ticker"
    )
    assert kwargs.get("is_dated_fixture") is True, (
        "is_dated_fixture was not passed — the second gate is what reaches every "
        "fixture that is not a game ticker"
    )


@pytest.mark.asyncio
async def test_an_occurrence_after_its_own_close_keeps_the_close():
    """The control only a SETTLED fixture motivates.

    On a settled event the close has collapsed to the settlement instant and the
    occurrence has NOT, so the occurrence can land after its own close — at the
    venue, `KXLOLGAME-26AUG231900FLYDIG` reports occ 03:00Z against a 00:19Z
    close. The helper's `occ <= close` bound keeps those on the close; without
    this arm the file passes against "on a settled event, always take the
    occurrence", which moves that row 2h41m the WRONG way.
    """
    late = CLOSE + timedelta(hours=2, minutes=41)
    rec = await _run(_event("KXLOLGAME-26AUG231900FLYDIG", "FlyQuest vs. Dignitas",
                            "Esports", occurrence=late))
    stored = rec.market_values()["commence_time"]
    assert stored == CLOSE, (
        f"an occurrence after its own close was built with {stored}, expected the "
        f"close {CLOSE} — the `occ <= close` bound is gone and a settled row can "
        "now be dated after it settled"
    )


@pytest.mark.asyncio
async def test_a_settled_outright_keeps_its_close_time():
    """The scope control: `occurrence_datetime` means something else on outrights."""
    rec = await _run(_event("KXECONGDP-26SEP", "US GDP growth above 3% in Q3",
                            "Economics", occurrence=KICKOFF))
    stored = rec.market_values()["commence_time"]
    assert stored == CLOSE, (
        f"a settled outright was built with {stored}, expected its close {CLOSE} — "
        "the is_game/is_dated_fixture scope has been dropped at this site and every "
        "outright is being re-timed onto a field that does not mean kick-off"
    )


@pytest.mark.asyncio
async def test_the_earliest_start_across_an_events_markets_wins():
    """Multi-market settled events exist here too; the min must be over all legs."""
    ticker = "KXNFLGAME-26SEP13MULTI"
    markets = [
        _settled_market(ticker, "KC", "Chiefs", 0.62, occurrence=KICKOFF + timedelta(minutes=20)),
        _settled_market(ticker, "DEN", "Broncos", 0.51, occurrence=KICKOFF),
        _settled_market(ticker, "TIE", "Tie", 0.20, occurrence=KICKOFF + timedelta(minutes=10)),
    ]
    rec = await _run(_event(ticker, "Chiefs at Broncos", "Football",
                            occurrence=KICKOFF, markets=markets))
    stored = rec.market_values()["commence_time"]
    assert stored == KICKOFF, (
        f"a three-leg settled event was built with {stored}, expected the earliest "
        f"occurrence {KICKOFF} — the helper is being handed one market rather than "
        "the event"
    )
