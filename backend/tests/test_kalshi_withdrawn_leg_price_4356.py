"""#4356 — a leg the venue has WITHDRAWN stops quoting a price.

## the ship, stated as the reader sees it

The First Touchdown card for San Francisco vs Los Angeles stops opening with
**"No Touchdown 39%"** above every real player. Kalshi took that outcome back a
week before the game; the live one says 2%.

## what the venue actually said, because the filed diagnosis was not this

#4356 was filed as a NAMING collision — two rows both reading `No Touchdown`, at
39% and 2% — and asked why #4316's set-level namer had not reached them. It had
not, and that is a real gap, but it is not this defect and renaming is not the
repair. Read against the venue's own listing on 2026-09-09:

    KXNFLFIRSTTD-26SEP10SFLAR-LARNONE   status inactive   opened 23:15Z Sep 2
    KXNFLFIRSTTD-26SEP10SFLAR-NONE      status active     opened 23:50Z Sep 2

Byte-identical `rules_primary`, byte-identical `rules_secondary`, and the SAME
`custom_strike` — the same `football_player` and `football_team` UUIDs. They are
not two outcomes. They are ONE outcome the venue duplicated, then took back
thirty-five minutes later. Forcing the naming ladder to separate them would
have invented a distinction the venue explicitly denies, and left the wrong
number sitting at the top of the card.

## why it survived every pass, which is the part worth guarding

`_refresh_linked_game_books` fetches `status=None` (it must — a status filter
breaks the venue's pagination), so it SEES the withdrawn leg and repriced it on
every pass, stamping `last_updated` fresh. Its reprice branch could only ever
write a price UP: an unreadable book fell through to `else: continue`, which
FROZE the last value. `_poll_kalshi_markets` — the one path with a null-out
block — fetches `status="open"` (gotcha #33) and never saw the leg at all.

So the row looked freshly updated and carried a stale 0.390 forever. Declining
to write is what preserved the defect, which is why the repair CLEARS.

## the ladder of controls

The dangerous version of this fix is "refuse to price anything that is not
`active`". That would clear the final price of every `closed` / `settled` /
`finalized` leg — the closing lines calibration reads (gotcha #21). Measured
against the venue over 3,898 legs of six linked game series: `active` 663,
`finalized` 3,234, `inactive` **1**. The controls below pin that ratio as
behaviour: only `inactive` clears, and a graded row or a captured closing line
is never wiped even when it is.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.sql.elements import BindParameter, TextClause

from app.services.kalshi_api import KalshiAPIService
from app.tasks import kalshi as k

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


# --------------------------------------------------------------------------
# the harness
# --------------------------------------------------------------------------


class _Row:
    """One row of the pass's own selector."""

    def __init__(self, id_, series, external_id, name, newest_price=None):
        self.id = id_
        self.series = series
        self.external_id = external_id
        self.name = name
        #: `_linked_book_series_order` reads this to put the stalest series
        #: first. Present so the harness exercises the real ordering rather
        #: than a stub of it.
        self.newest_price = newest_price


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)

    def scalar_one(self):
        return 1

    def scalar(self):
        return 1


class _Session:
    """Answers the two reads by TYPE, records every write.

    Split on statement type rather than call order: the pass reads its selector
    once and then re-reads `existing` per market, so an order-based harness
    would answer the wrong question the moment a test uses two markets.
    """

    def __init__(self, selector_rows, existing):
        self._selector_rows = selector_rows
        #: `{external_id: is_winner}` already in the table.
        self._existing = existing
        self.writes: list[object] = []

    async def execute(self, stmt, *args, **kwargs):
        if isinstance(stmt, TextClause):
            return _Result(self._selector_rows)
        if isinstance(stmt, Select):
            return _Result([(eid, win) for eid, win in self._existing.items()])
        self.writes.append(stmt)
        return _Result(rowcount=1)

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _Service:
    """The venue, answered with RAW dicts through the REAL parser.

    Deliberately not hand-built `KalshiMarket`s: `status` reaching the predicate
    depends on `_parse_market` carrying it through verbatim, so the parser is
    part of what this file proves.
    """

    def __init__(self, raw):
        self._raw = raw
        self._real = KalshiAPIService()

    async def get_markets(self, **kwargs):
        return list(self._raw), None

    def parse_markets(self, raw):
        return self._real.parse_markets(raw)

    async def close(self):
        return None


def _leg(ticker, status, *, bid=0.10, ask=0.12, sub="No Touchdown"):
    return {
        "ticker": ticker,
        "event_ticker": "KXNFLFIRSTTD-26SEP10SFLAR",
        "title": f"{sub}: 1st Touchdown",
        "yes_sub_title": sub,
        "status": status,
        "yes_bid": bid,
        "yes_ask": ask,
    }


async def _run(monkeypatch, legs, existing):
    row = _Row(77, "KXNFLFIRSTTD", "KXNFLFIRSTTD-26SEP10SFLAR", "SF vs LAR: First Touchdown")
    session = _Session([row], existing)
    service = _Service(legs)

    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(k, "get_task_session", _fake_session)
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", lambda *a, **kw: service)
    stats = await k._refresh_linked_game_books()
    return stats, session


def _updates(session):
    return [s for s in session.writes if isinstance(s, Update)]


def _inserts(session):
    return [s for s in session.writes if not isinstance(s, Update)]


#: Sentinel for "this column was set to a SQL expression", e.g. `func.now()`.
#: Distinct from `None`, which is what a cleared price column holds — collapsing
#: the two is how the first draft of this file read every clear as a re-price
#: and passed its controls while failing its ship.
_EXPR = object()


def _values_of(stmt) -> dict:
    """Column name -> the literal Python value bound to it.

    `.values(x=None)` stores a `BindParameter` whose `.value` is `None`, not a
    bare `None`, so a naive `stmt._values` read never compares equal to `None`.
    """
    out = {}
    for col, val in stmt._values.items():
        if isinstance(val, BindParameter):
            out[col.name] = val.value
        else:
            out[col.name] = _EXPR
    return out


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


def _clears(session) -> list:
    """Updates that SET the price to NULL.

    Membership is tested before the value, so an update that never mentions
    `current_probability` cannot masquerade as a clear via `dict.get` -> None.
    """
    out = []
    for u in _updates(session):
        vals = _values_of(u)
        if "current_probability" in vals and vals["current_probability"] is None:
            out.append(u)
    return out


def _reprices(session) -> list:
    return [
        u
        for u in _updates(session)
        if _values_of(u).get("current_probability") not in (None, _EXPR)
    ]


# --------------------------------------------------------------------------
# 1. the predicate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["inactive", "INACTIVE", " Inactive "])
def test_withdrawn_statuses_are_recognised(status):
    assert k._is_withdrawn_leg(status) is True


@pytest.mark.parametrize(
    "status",
    # The whole ladder of NORMAL ends. Each of these keeps its final price:
    # it is the closing line, and clearing it is gotcha #21.
    ["active", "open", "closed", "settled", "finalized", "unopened", "", None],
)
def test_a_normal_lifecycle_status_is_not_a_withdrawal(status):
    assert k._is_withdrawn_leg(status) is False


def test_the_parser_carries_the_status_the_predicate_reads():
    """Without this the predicate is unreachable and every test below passes."""
    parsed = KalshiAPIService().parse_markets([_leg("KX-A-LARNONE", "inactive")])
    assert len(parsed) == 1
    assert parsed[0].status == "inactive"
    assert k._is_withdrawn_leg(parsed[0].status) is True


# --------------------------------------------------------------------------
# 2. the ship
# --------------------------------------------------------------------------


async def test_a_withdrawn_legs_stored_price_is_cleared(monkeypatch):
    """The specimen: `-LARNONE` withdrawn, `-NONE` live."""
    stats, session = await _run(
        monkeypatch,
        [
            _leg("KXNFLFIRSTTD-26SEP10SFLAR-LARNONE", "inactive"),
            _leg("KXNFLFIRSTTD-26SEP10SFLAR-NONE", "active", bid=0.01, ask=0.03),
        ],
        {
            "KXNFLFIRSTTD-26SEP10SFLAR-LARNONE": None,
            "KXNFLFIRSTTD-26SEP10SFLAR-NONE": None,
        },
    )

    assert stats["outcomes_withdrawn_cleared"] == 1
    cleared = _clears(session)
    assert len(cleared) == 1, "the withdrawn leg's price was not cleared"

    vals = _values_of(cleared[0])
    # Every price-shaped column goes, not just the headline one: a card that
    # renders a bid/ask would otherwise still print the withdrawn book.
    for col in (
        "current_probability",
        "current_american_odds",
        "current_yes_bid",
        "current_yes_ask",
        "probability_change_24h",
    ):
        assert vals[col] is None, f"{col} survived the clear"


async def test_the_live_leg_is_still_repriced(monkeypatch):
    """The control that matters most: withdrawal must not stop normal work."""
    stats, session = await _run(
        monkeypatch,
        [
            _leg("KXNFLFIRSTTD-26SEP10SFLAR-LARNONE", "inactive"),
            _leg("KXNFLFIRSTTD-26SEP10SFLAR-NONE", "active", bid=0.01, ask=0.03),
        ],
        {
            "KXNFLFIRSTTD-26SEP10SFLAR-LARNONE": None,
            "KXNFLFIRSTTD-26SEP10SFLAR-NONE": None,
        },
    )
    assert stats["outcomes_repriced"] == 1
    priced = _reprices(session)
    assert len(priced) == 1
    assert _values_of(priced[0])["current_probability"] == pytest.approx(0.02)


# --------------------------------------------------------------------------
# 3. the controls
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["closed", "settled", "finalized"])
async def test_a_finished_leg_keeps_its_closing_line(monkeypatch, status):
    """3,234 of the 3,898 legs measured were `finalized`.

    Clearing these is the version of this fix that would have destroyed
    calibration's evidence. It is a control precisely because the naive rule
    ("not active") passes every assertion in section 2.
    """
    stats, session = await _run(
        monkeypatch,
        [_leg("KXNFLFIRSTTD-26SEP10SFLAR-LARKW23", status, sub="Kyren Williams")],
        {"KXNFLFIRSTTD-26SEP10SFLAR-LARKW23": None},
    )
    assert stats["outcomes_withdrawn_cleared"] == 0
    assert _clears(session) == []


async def test_a_withdrawn_leg_we_do_not_hold_is_not_created(monkeypatch):
    """A row that can never be priced and can never resolve is not worth minting."""
    stats, session = await _run(
        monkeypatch,
        [_leg("KXNFLFIRSTTD-26SEP10SFLAR-LARNONE", "inactive")],
        {},  # we hold nothing
    )
    assert stats["outcomes_withdrawn_skipped"] == 1
    assert _inserts(session) == [], "minted a row for a leg the venue took back"
    assert stats["outcomes_created_priced"] == 0
    assert stats["outcomes_created_unpriced"] == 0


async def test_a_withdrawal_is_not_counted_as_an_unreadable_book(monkeypatch):
    """Two different facts. `books_unreadable` says the venue went quiet on us;
    a withdrawal says the venue answered and the answer was "this is gone"."""
    stats, _ = await _run(
        monkeypatch,
        [_leg("KXNFLFIRSTTD-26SEP10SFLAR-LARNONE", "inactive")],
        {"KXNFLFIRSTTD-26SEP10SFLAR-LARNONE": None},
    )
    assert stats["books_unreadable"] == 0
    assert stats["outcomes_withdrawn_cleared"] == 1


async def test_an_unreadable_book_is_still_counted_and_still_freezes(monkeypatch):
    """The control for the control: #3518's state is unchanged by this ship."""
    stats, session = await _run(
        monkeypatch,
        [_leg("KXNFLFIRSTTD-26SEP10SFLAR-LARKW23", "active", bid=None, ask=None)],
        {"KXNFLFIRSTTD-26SEP10SFLAR-LARKW23": None},
    )
    assert stats["books_unreadable"] == 1
    assert stats["outcomes_withdrawn_cleared"] == 0
    assert _updates(session) == [], "an unreadable book must still write nothing"


# --------------------------------------------------------------------------
# 4. the guards on the clear, read off the statement
# --------------------------------------------------------------------------


async def test_the_clear_refuses_a_graded_row_and_a_captured_closing_line(monkeypatch):
    """Gotcha #21, and calibration's evidence, as a WHERE clause.

    Asserted on the compiled statement because the protection IS the SQL — a
    behavioural assertion against a fake session would pass whatever the
    predicate said.
    """
    _, session = await _run(
        monkeypatch,
        [_leg("KXNFLFIRSTTD-26SEP10SFLAR-LARNONE", "inactive")],
        {"KXNFLFIRSTTD-26SEP10SFLAR-LARNONE": None},
    )
    cleared = _clears(session)
    assert len(cleared) == 1
    where = _sql(cleared[0]).lower()

    assert "is_winner is not true" in where, "a graded row could be wiped"
    assert "calibration_probability is null" in where, "a closing line could be wiped"
    # Idempotence: `last_updated` is a freshness gate other code reads, so a
    # leg already cleared must not be restamped on every subsequent pass.
    assert "current_probability is not null" in where, "the clear would restamp forever"


# --------------------------------------------------------------------------
# 5. CERT-2384's repair: the SECOND writer
# --------------------------------------------------------------------------
#
# Clearing the leg hourly in `_refresh_linked_game_books` is not the ship.
# `_poll_live_prediction_market_prices` runs every two minutes from T-3h — i.e.
# exactly while a reader is watching the game — fetches Kalshi with
# `status=None`, and used to recompute the withdrawn leg's stale one-sided book
# (0 / 0.39 / 0 -> 39% via the ask-only rung) and write it straight back.
#
# The stored-row round trip is
# `tests/integration/test_live_poll_kalshi_prices_real_postgres.py`
# (`TestTheLivePollerCannotRestoreAWithdrawnLeg`), run by CI's `search-recall`
# job — there is no local Postgres in the agent sandbox. These arms are the fast
# half: they execute the clear itself and pin the branch that reaches it.

import inspect as _inspect

from app.tasks import prediction_market_matching as pmm


class _OutcomeRow:
    """The three columns the clear reads, and the five it writes."""

    def __init__(self, prob=0.39, is_winner=None, calibration_probability=None):
        self.current_probability = prob
        self.current_american_odds = -160
        self.current_yes_bid = 0.0
        self.current_yes_ask = 0.39
        self.probability_change_24h = 0.02
        self.is_winner = is_winner
        self.calibration_probability = calibration_probability
        self.last_updated = "OLD"


def _clear(row):
    stats = {"kalshi_outcomes_withdrawn_cleared": 0}
    changed = pmm._clear_withdrawn_outcome(row, "NOW", stats)
    return changed, stats


def test_the_live_polls_clear_takes_every_price_column_off():
    row = _OutcomeRow()
    changed, stats = _clear(row)
    assert changed is True
    assert stats["kalshi_outcomes_withdrawn_cleared"] == 1
    for col in (
        "current_probability",
        "current_american_odds",
        "current_yes_bid",
        "current_yes_ask",
        "probability_change_24h",
    ):
        assert getattr(row, col) is None, f"{col} survived the clear"
    assert row.last_updated == "NOW"


def test_the_live_polls_clear_refuses_a_graded_row():
    """Gotcha #21 — never un-price a row the venue has called."""
    row = _OutcomeRow(is_winner=True)
    changed, stats = _clear(row)
    assert changed is False
    assert row.current_probability == 0.39
    assert stats["kalshi_outcomes_withdrawn_cleared"] == 0


def test_the_live_polls_clear_refuses_a_captured_closing_line():
    """Calibration's evidence outranks this repair."""
    row = _OutcomeRow(calibration_probability=0.41)
    changed, _ = _clear(row)
    assert changed is False
    assert row.current_probability == 0.39


def test_the_live_polls_clear_is_idempotent():
    """`last_updated` is a freshness gate (`routes/playoffs.py` drops a stale
    outcome from the grid), so a leg cleared once must not be restamped every
    two minutes for the rest of the day."""
    row = _OutcomeRow(prob=None)
    changed, stats = _clear(row)
    assert changed is False
    assert row.last_updated == "OLD", "restamped a row it did not change"
    assert stats["kalshi_outcomes_withdrawn_cleared"] == 0


def test_the_live_poller_asks_the_same_question_as_the_hourly_pass():
    """One definition of 'the venue took this leg back', imported not re-derived.

    Two writers that disagreed about which legs are real is the defect
    CERT-2384 blocked on; two writers with two predicates is the same defect
    waiting to come back.
    """
    src = _inspect.getsource(pmm._poll_live_prediction_market_prices)
    assert "_is_withdrawn_leg(km.status)" in src, (
        "the live poller no longer reads the venue's status through the shared "
        "predicate"
    )
    assert "from app.tasks.kalshi import _is_withdrawn_leg" in src, (
        "the predicate is re-derived locally instead of imported"
    )


def test_the_withdrawn_branch_returns_before_the_snapshot():
    """A chart point for a withdrawn leg outlives the cleared row.

    Pinned positionally: the withdrawn branch's `continue` must come BEFORE the
    Kalshi snapshot insert, or the clear lands and the chart keeps the fiction.
    """
    src = _inspect.getsource(pmm._poll_live_prediction_market_prices)
    clear_at = src.index("_clear_withdrawn_outcome(outcome, now, stats)")
    snapshot_at = src.index('bookmaker="kalshi"')
    assert clear_at < snapshot_at
    between = src[clear_at:snapshot_at]
    assert "continue" in between, (
        "the withdrawn branch falls through to the snapshot write"
    )


def test_the_withdrawn_branch_does_not_reuse_the_single_outcome_fallback():
    """The one way this repair could destroy a real price.

    The `len(market_outcomes) == 1` fallback exists to land a PRICE that has
    nowhere else to go. On the withdrawn path it would clear a row the venue
    named differently — and a market with exactly one outcome is the shape that
    triggers it. The withdrawn branch must resolve by ticker or do nothing.

    Pinned positionally rather than by grepping the whole function, because the
    fallback legitimately still exists a few lines below for the pricing path.
    """
    src = _inspect.getsource(pmm._poll_live_prediction_market_prices)
    branch_at = src.index("if withdrawn:")
    clear_at = src.index("_clear_withdrawn_outcome(outcome, now, stats)")
    branch = src[branch_at:clear_at]
    assert "market_outcomes" not in branch, (
        "the withdrawn branch reaches the single-outcome fallback; it can clear "
        "a row the venue never named"
    )
