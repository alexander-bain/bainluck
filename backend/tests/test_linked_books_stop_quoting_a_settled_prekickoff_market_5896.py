"""#5896 — the hourly pass stops writing a settlement back onto a game that
has not kicked off, and withdraws what it already wrote.

WHAT A READER SAW
-----------------
`bainluck.com/events/15298075` — Racing Santander v Alavés, header "Starts in
7h 53m", hero **99% – 1%**. Three siblings in the same state at 12:25Z on
2026-09-13: `15298076` (Athletic Bilbao v Elche), `15298079` (Osasuna v
Espanyol), `15299310` (Coritiba v Atlético Paranaense). Every one `scheduled`
with a kick-off in the future, every one serving a Kalshi settlement as a live
price.

WHY #5771 DID NOT FIX IT, AND WHY THAT IS A REACH BUG AND NOT A LOGIC BUG
--------------------------------------------------------------------------
#5771 taught `futures_price_refresh` to recognise the shape (`venue_answered`)
and to withdraw the rows (`_KALSHI_WITHDRAW_PRE_KICKOFF_SQL` +
`_KALSHI_WITHDRAW_EVENT_HERO_SQL`). Its gate half works — `venue_settled` went
5 → 21 on the first heavy run carrying it. Its withdrawal half reported
`pre_kickoff_quotes_withdrawn: 0` on that same run while all four pages kept
serving 99%, because `_CANDIDATE_SQL` ends in a six-hour price-silence
anti-join and **this** pass re-prices every linked game market hourly at :20.
A market this pass keeps writing can never go six hours silent, so it can never
enter that batch. Measured on the specimen: `last_updated` 12:21:16Z against a
12:20:00Z snapshot — one minute after this pass's own beat.

So the refusal has to live in the writer that owns the row. Both writers have
to agree, which is the same conclusion `_poll_live_prediction_market_prices`
reached about #4356.

THE VENUE'S OWN WORD, READ THROUGH THE ENDPOINT THIS PASS USES
---------------------------------------------------------------
`/trade-api/v2/markets?event_ticker=…`, 2026-09-13 12:31–12:32Z, all 36
pre-kick-off markets whose stored legs carried a probability >= 0.99:

* **27 ALL_ANSWERED** — `finalized` (23) or `determined` (3) or a mix, every
  leg carrying a declared `result`. The defect.
* **8 NONE_ANSWERED** — `active`, `result` the empty string. The controls, and
  they are not a hypothetical: they are the NFL team-total ladders
  (`KXNFLTEAMTOTAL-26SEP13TBCIN`, 28 legs, whose lowest rung is honestly at
  0.99) and `KXNCAAFGAME-26SEP19KENTOSU`, live/198's control, which reads
  `active` / `result ''` and must keep its 99.5%.
* **1 MIXED** — `KXEREDIVISIETOTAL-26SEP13EXCFCU`.

Which is why the test below is the venue's `result` and never "the ladder looks
extreme" or a status allowlist: a rule written against the statuses known that
morning would have missed every `determined` one.
"""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.sql.elements import BindParameter, TextClause

from app.models.models import FuturesOddsSnapshot, FuturesOutcome
from app.services.kalshi_api import KalshiAPIService
from app.tasks import kalshi as k
from app.tasks.futures_price_refresh import (
    _KALSHI_WITHDRAW_EVENT_HERO_SQL,
    _KALSHI_WITHDRAW_PRE_KICKOFF_SQL,
)
from app.utils import futures_liveness as liveness

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


# --------------------------------------------------------------------------
# the harness
# --------------------------------------------------------------------------


class _Row:
    def __init__(self, id_, series, external_id, name, *, pre_kickoff):
        self.id = id_
        self.series = series
        self.external_id = external_id
        self.name = name
        self.newest_price = None
        self.pre_kickoff = pre_kickoff


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
    """Records every write, and answers the text statements BY IDENTITY.

    The pass now runs three different `text()` statements — its own selector
    and the two it imports from #5771 — so a harness that answers "any
    TextClause" with the selector rows (which is what the #4356 band does, and
    correctly, because there it is the only one) would feed market rows back
    into the withdrawal's `fetchall` and the counters would report nonsense.
    Identity is also the assertion: a copy of the statement pasted into
    `kalshi.py` would not be `is` these objects and every test here would say
    so.
    """

    def __init__(self, selector_rows, existing, *, withdrawn_rows, hero_rows):
        self._selector_rows = selector_rows
        self._existing = existing
        self._withdrawn_rows = withdrawn_rows
        self._hero_rows = hero_rows
        self.writes: list[object] = []
        #: (statement, params) in execution order, for the text statements.
        self.text_calls: list[tuple[object, dict]] = []

    async def execute(self, stmt, *args, **kwargs):
        if isinstance(stmt, TextClause):
            params = args[0] if args else kwargs.get("params") or {}
            self.text_calls.append((stmt, params))
            if stmt is _KALSHI_WITHDRAW_PRE_KICKOFF_SQL:
                return _Result(self._withdrawn_rows)
            if stmt is _KALSHI_WITHDRAW_EVENT_HERO_SQL:
                return _Result(self._hero_rows)
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

    `result` reaching the predicate depends on `_parse_market` carrying it
    through verbatim, so the parser is part of what this file proves — the same
    reason the #4356 band refuses hand-built `KalshiMarket`s.
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


#: The specimen, verbatim from the venue read of 2026-09-13 12:31Z: three legs,
#: `finalized`, results `no` / `no` / `yes`, and NO readable book — the cent
#: keys the venue stopped emitting (#3569) are absent, so the price such a leg
#: gets comes out of `last_price`, which is the settlement artifact 0.99.
def _leg(ticker, status, result, *, bid=None, ask=None, last=None, sub="Santander"):
    return {
        "ticker": ticker,
        "event_ticker": "KXLALIGAGAME-26SEP13SANALA",
        "title": "Racing Santander vs Alaves",
        "yes_sub_title": sub,
        "status": status,
        "result": result,
        "yes_bid": bid,
        "yes_ask": ask,
        "last_price": last,
    }


_SAN = "KXLALIGAGAME-26SEP13SANALA-SAN"
_ALA = "KXLALIGAGAME-26SEP13SANALA-ALA"


def _settled_book():
    return [
        _leg(_SAN, "finalized", "yes", last=0.99, sub="Santander"),
        _leg(_ALA, "finalized", "no", last=0.01, sub="Alaves"),
    ]


def _live_book():
    """The KENTOSU control's shape: active, `result` the EMPTY STRING."""
    return [
        _leg(_SAN, "active", "", bid=0.99, ask=0.996, sub="Santander"),
        _leg(_ALA, "active", "", bid=0.004, ask=0.01, sub="Alaves"),
    ]


async def _run(
    monkeypatch,
    legs,
    existing,
    *,
    pre_kickoff,
    withdrawn_rows=((1,), (2,), (3,)),
    hero_rows=((15298075,),),
):
    row = _Row(
        60482103,
        "KXLALIGAGAME",
        "KXLALIGAGAME-26SEP13SANALA",
        "Racing Santander vs Alaves",
        pre_kickoff=pre_kickoff,
    )
    session = _Session(
        [row],
        existing,
        withdrawn_rows=list(withdrawn_rows),
        hero_rows=list(hero_rows),
    )
    service = _Service(legs)

    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(k, "get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **kw: service
    )
    stats = await k._refresh_linked_game_books()
    return stats, session


def _updates(session):
    return [s for s in session.writes if isinstance(s, Update)]


def _values_of(stmt) -> dict:
    out = {}
    for col, val in stmt._values.items():
        out[col.name] = val.value if isinstance(val, BindParameter) else object()
    return out


def _price_writes(session) -> list:
    """Every statement that puts a NUMBER into `current_probability`.

    Covers the UPDATE and the INSERT arms both, because "this pass stopped
    writing the artifact" is false if it merely stopped taking one of the two
    roads to it.
    """
    out = []
    for s in session.writes:
        table = getattr(s, "table", None)
        if table is not None and table.name != FuturesOutcome.__tablename__:
            continue
        vals = _values_of(s)
        prob = vals.get("current_probability")
        if isinstance(prob, (int, float)):
            out.append(s)
    return out


def _snapshot_writes(session) -> list:
    return [
        s
        for s in session.writes
        if getattr(getattr(s, "table", None), "name", None)
        == FuturesOddsSnapshot.__tablename__
    ]


def _text_of(session, statement) -> list[dict]:
    return [params for stmt, params in session.text_calls if stmt is statement]


# --------------------------------------------------------------------------
# 1. one predicate, one home, two writers
# --------------------------------------------------------------------------


def test_both_writers_read_the_same_function_object():
    """Not "the same rule" — the same object. A copy is how the two writers
    end up disagreeing about what a settlement is six months from now."""
    from app.tasks import futures_price_refresh as fpr

    assert k.venue_answered is liveness.venue_answered
    assert fpr.venue_answered is liveness.venue_answered


def test_the_empty_string_a_live_market_sends_is_not_an_answer():
    assert liveness.venue_answered("") is False
    assert liveness.venue_answered("   ") is False
    assert liveness.venue_answered(None) is False


def test_the_venues_two_verdicts_are_both_answers():
    assert liveness.venue_answered("yes") is True
    assert liveness.venue_answered("no") is True


def test_the_parser_carries_the_result_the_predicate_reads():
    """The whole chain is only as good as `_parse_market` keeping the field."""
    parsed = KalshiAPIService().parse_markets(_settled_book())
    assert [m.result for m in parsed] == ["yes", "no"]
    assert all(liveness.venue_answered(m.result) for m in parsed)


# --------------------------------------------------------------------------
# 2. the ship
# --------------------------------------------------------------------------


async def test_a_settled_book_before_kickoff_is_withdrawn_not_repriced(monkeypatch):
    stats, session = await _run(
        monkeypatch, _settled_book(), {_SAN: None, _ALA: None}, pre_kickoff=True
    )

    assert stats["pre_kickoff_settled_markets"] == 1
    assert stats["pre_kickoff_quotes_withdrawn"] == 3
    assert stats["pre_kickoff_heroes_cleared"] == 1
    assert _price_writes(session) == [], "wrote the settlement back as a price"
    # The market-level `continue` is load-bearing beyond the price write: a
    # withdrawn market must not ALSO be counted leg-by-leg as a mixed book's
    # skip, or the counter that measures the residual measures the ship
    # instead. Dropping the `continue` survives every assertion above,
    # because the per-leg skip catches the same legs one line later — this
    # pair is the only thing that tells the two paths apart.
    assert stats["pre_kickoff_settled_legs_skipped"] == 0
    assert stats["pre_kickoff_settled_mixed"] == 0
    assert session.writes == [], "a fully withdrawn market writes nothing at all"


async def test_it_runs_the_two_statements_5771_already_owns(monkeypatch):
    """Imported, not re-written. A second copy of a statement whose safety is
    its scope is a second opinion about when withdrawing a quote is safe."""
    _, session = await _run(
        monkeypatch, _settled_book(), {_SAN: None}, pre_kickoff=True
    )

    assert _text_of(session, _KALSHI_WITHDRAW_PRE_KICKOFF_SQL) == [
        {"market_id": 60482103}
    ]
    assert _text_of(session, _KALSHI_WITHDRAW_EVENT_HERO_SQL) == [
        {"market_id": 60482103}
    ]


async def test_the_quote_goes_before_the_hero(monkeypatch):
    """CERT-2772's ordering argument: the hero statement asks whether any
    Kalshi price is still standing on this event, so the legs withdrawn above
    must already be excluded when it asks."""
    _, session = await _run(
        monkeypatch, _settled_book(), {_SAN: None}, pre_kickoff=True
    )
    order = [
        stmt
        for stmt, _ in session.text_calls
        if stmt in (_KALSHI_WITHDRAW_PRE_KICKOFF_SQL, _KALSHI_WITHDRAW_EVENT_HERO_SQL)
    ]
    assert order == [_KALSHI_WITHDRAW_PRE_KICKOFF_SQL, _KALSHI_WITHDRAW_EVENT_HERO_SQL]


async def test_a_withdrawn_market_writes_no_chart_point(monkeypatch):
    """A chart point for a price we have just taken back is the same fiction
    as the price — the rule #4356's withdrawn branch already follows."""
    _, session = await _run(
        monkeypatch, _settled_book(), {_SAN: None, _ALA: None}, pre_kickoff=True
    )
    assert _snapshot_writes(session) == []


async def test_a_leg_we_do_not_hold_is_not_minted_from_a_settled_book(monkeypatch):
    """The market-level `continue` is what makes this true: the INSERT arm is
    never reached, so a settlement cannot mint a brand-new priced row."""
    _, session = await _run(monkeypatch, _settled_book(), {}, pre_kickoff=True)
    assert session.writes == []


@pytest.mark.parametrize("status", ["finalized", "determined", "closed", "settled"])
async def test_the_status_vocabulary_is_open_and_the_result_decides(
    monkeypatch, status
):
    """Three of the 27 settled specimens read `determined`, not `finalized`.
    A status allowlist written on 2026-09-13 would have missed them."""
    stats, _ = await _run(
        monkeypatch,
        [
            _leg(_SAN, status, "yes", last=0.99),
            _leg(_ALA, status, "no", last=0.01),
        ],
        {_SAN: None, _ALA: None},
        pre_kickoff=True,
    )
    assert stats["pre_kickoff_settled_markets"] == 1


# --------------------------------------------------------------------------
# 3. the controls — each one is a real row that must not move
# --------------------------------------------------------------------------


async def test_the_kentosu_control_is_priced_exactly_as_before(monkeypatch):
    """`KXNCAAFGAME-26SEP19KENTOSU` reads `active` / `result ''` at the venue
    and its page is honestly at 99.5%. If this ship touches it, the ship is
    "the ladder looks extreme" and not "the venue answered"."""
    stats, session = await _run(
        monkeypatch, _live_book(), {_SAN: None, _ALA: None}, pre_kickoff=True
    )

    assert stats["pre_kickoff_settled_markets"] == 0
    assert stats["pre_kickoff_quotes_withdrawn"] == 0
    assert stats["pre_kickoff_heroes_cleared"] == 0
    assert _text_of(session, _KALSHI_WITHDRAW_PRE_KICKOFF_SQL) == []
    assert len(_price_writes(session)) == 2, "stopped pricing a live book"


async def test_after_kickoff_a_settled_book_keeps_its_closing_line(monkeypatch):
    """SETTLED MEANS SETTLED. A finished contest SHOULD carry its terminal
    number, and that closing line is calibration's evidence (gotcha #21). The
    event's own clock is the entire scope of this ship, exactly as it is the
    entire scope of the statement it calls."""
    stats, session = await _run(
        monkeypatch, _settled_book(), {_SAN: None, _ALA: None}, pre_kickoff=False
    )

    assert stats["pre_kickoff_settled_markets"] == 0
    assert stats["pre_kickoff_quotes_withdrawn"] == 0
    assert stats["pre_kickoff_settled_legs_skipped"] == 0
    assert _text_of(session, _KALSHI_WITHDRAW_PRE_KICKOFF_SQL) == []
    assert len(_price_writes(session)) == 2, "stopped writing a finished game's line"


async def test_a_finalized_status_without_a_result_is_not_an_answer(monkeypatch):
    """The #4356 band's 3,234 `finalized` legs carry no `result` in its
    fixtures and must stay untouched — restated here because THIS file is
    where someone would be tempted to widen the test to the status."""
    stats, session = await _run(
        monkeypatch,
        [
            _leg(_SAN, "finalized", None, bid=0.40, ask=0.42),
            _leg(_ALA, "finalized", "", bid=0.58, ask=0.60),
        ],
        {_SAN: None, _ALA: None},
        pre_kickoff=True,
    )
    assert stats["pre_kickoff_settled_markets"] == 0
    assert len(_price_writes(session)) == 2


# --------------------------------------------------------------------------
# 4. the mixed book, and the residual it leaves
# --------------------------------------------------------------------------


async def test_a_mixed_book_prices_the_live_leg_and_skips_the_answered_one(
    monkeypatch,
):
    """Kalshi settles a game's legs together, so this is rare — one of the 36
    candidates. The withdrawal statement is market-grain, so spending it here
    would take a trading leg's real price down; the answered leg is skipped
    instead, and the residual (its stored artifact survives until the venue
    answers the whole book) is counted rather than hidden."""
    stats, session = await _run(
        monkeypatch,
        [
            _leg(_SAN, "finalized", "yes", last=0.99),
            _leg(_ALA, "active", "", bid=0.40, ask=0.42),
        ],
        {_SAN: None, _ALA: None},
        pre_kickoff=True,
    )

    assert stats["pre_kickoff_settled_markets"] == 0
    assert stats["pre_kickoff_settled_mixed"] == 1
    assert stats["pre_kickoff_settled_legs_skipped"] == 1
    assert stats["pre_kickoff_quotes_withdrawn"] == 0
    assert len(_price_writes(session)) == 1, "the live leg must still be priced"


async def test_a_mixed_book_after_kickoff_prices_both_legs(monkeypatch):
    """The per-leg skip is scoped by the same clock as everything else here."""
    stats, session = await _run(
        monkeypatch,
        [
            _leg(_SAN, "finalized", "yes", last=0.99),
            _leg(_ALA, "active", "", bid=0.40, ask=0.42),
        ],
        {_SAN: None, _ALA: None},
        pre_kickoff=False,
    )
    assert stats["pre_kickoff_settled_legs_skipped"] == 0
    assert len(_price_writes(session)) == 2


async def test_a_skipped_leg_is_not_counted_as_an_unreadable_book(monkeypatch):
    """Two different facts. `books_unreadable` is the gauge that says the venue
    went quiet on us; this says the venue answered."""
    stats, _ = await _run(
        monkeypatch,
        [
            _leg(_SAN, "finalized", "yes", last=0.99),
            _leg(_ALA, "active", "", bid=0.40, ask=0.42),
        ],
        {_SAN: None, _ALA: None},
        pre_kickoff=True,
    )
    assert stats["books_unreadable"] == 0


# --------------------------------------------------------------------------
# 5. the instrument
# --------------------------------------------------------------------------


async def test_the_counters_are_reported_even_when_nothing_fires(monkeypatch):
    """#5896 exists because a run reported `terminal: complete` over four wrong
    pages. A key that appears only when the branch fires cannot tell "withdrew
    nothing" from "shipped without the branch"."""
    stats, _ = await _run(
        monkeypatch, _live_book(), {_SAN: None, _ALA: None}, pre_kickoff=True
    )
    for key in (
        "pre_kickoff_settled_markets",
        "pre_kickoff_quotes_withdrawn",
        "pre_kickoff_heroes_cleared",
        "pre_kickoff_settled_mixed",
        "pre_kickoff_settled_legs_skipped",
    ):
        assert stats[key] == 0, key


async def test_the_two_counters_are_rows_and_the_third_is_the_decision(monkeypatch):
    """`markets` counts what we decided; `quotes` and `heroes` count what the
    database actually changed. Collapsing them would report a decision as an
    effect — the exact reading that made #5771 look done."""
    stats, _ = await _run(
        monkeypatch,
        _settled_book(),
        {_SAN: None},
        pre_kickoff=True,
        withdrawn_rows=[],
        hero_rows=[],
    )
    assert stats["pre_kickoff_settled_markets"] == 1
    assert stats["pre_kickoff_quotes_withdrawn"] == 0
    assert stats["pre_kickoff_heroes_cleared"] == 0


# --------------------------------------------------------------------------
# 6. the selector carries the clock the statements are scoped by
# --------------------------------------------------------------------------


def test_the_selector_reads_the_same_two_clauses_the_statements_enforce():
    """The Python branch and the SQL scope must be one question. The
    statements below are the ones actually executed, so this is not a
    restatement of a constant: it is the agreement between the column that
    decides whether to ASK and the WHERE that decides whether to ACT."""
    selector = str(k._LINKED_GAME_BOOKS_SQL)
    for sql in (
        str(_KALSHI_WITHDRAW_PRE_KICKOFF_SQL),
        str(_KALSHI_WITHDRAW_EVENT_HERO_SQL),
    ):
        assert "e.status = 'scheduled'" in sql
        assert "e.commence_time > NOW()" in sql

    # 🔴 THE COLUMN IS ASSERTED WHOLE, AND THAT IS NOT FUSSINESS.
    # The two substrings above are VACUOUS against this statement: its own
    # WHERE already carries `e.commence_time > NOW() - make_interval(...)`
    # for the lookback window, so `"e.commence_time > NOW()" in selector` is
    # true no matter what the new column says — inverting the column to
    # `< NOW()` survived exactly that assertion. The expression is the claim,
    # so the expression is what gets asserted.
    assert (
        "(e.status = 'scheduled' AND e.commence_time > NOW()) AS pre_kickoff"
        in selector
    )
