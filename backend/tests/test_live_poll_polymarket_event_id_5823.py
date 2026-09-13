"""The live poll asks Gamma the question Gamma can answer (#5823).

## the ship

A live match's Polymarket prices keep arriving, and they stop costing the
second venue its guaranteed share of the fetch window to do it. Measured on
production 2026-09-13 05:08Z and 05:12Z, `prediction_market_live`'s own
`last_result_summary`: **`polymarket_fetched` 30, `session_recoveries` 59,
`terminal` "partial"** — on both passes, with `incompletes_24h` sitting at 18.
Every one of those 59 was a Polymarket 422 and nothing else; the error list is
59 lines of

    polymarket_0x…: Client error '422 Unprocessable Entity' for url
    'https://gamma-api.polymarket.com/events/0x…'

## the defect these arms are pointed at

`_poll_live_prediction_market_prices` addressed Gamma's `/events/{id}` with
`market.external_id`. On a DECOMPOSED SUB-MARKET that column holds the
**condition id**, not the event id — `sub_market_metadata` in
`app/tasks/polymarket.py` mints it that way deliberately and stamps
`polymarket_event_id` beside it. Gamma answers a bare hex condition id with
422. Measured over the 9,165 linked open Polymarket rows on production
2026-09-13: **3,004 carry a `0x…` external_id**; 2,856 of those have the event
id in metadata and the remaining 159 all have it in `group_id`.

Two consequences, and the second is why the first is not the whole story:

* those calls could never return anything, and
* even if one HAD returned, it could not have written anything. The apply loop
  resolves outcomes as `(market_id, conditionId)`, and a sub-market's outcomes
  are keyed `<conditionId>_yes` / `<conditionId>_no` (measured: market 60911044
  on production), so the lookup misses by construction. The prices those rows
  do carry come from elsewhere.

So the cost was never missing prices — it was **~59 wasted venue calls a
pass**, charged to the window the #5767 floor exists to ration; **~59 needless
recoveries**, each a rollback, an `expunge_all` and a full population re-read
performed for an error that touched no transaction; and a `terminal` that read
`partial` on every pass because `session_recoveries` was never 0.

## how the harness discriminates

`_PolyService` JOURNALS the id it was asked for and raises the production 422
for any id that is not a Gamma event id in its payload table — so an arm cannot
pass by fetching the wrong key and getting away with it, which is exactly what
production was doing. The fakes are local to this file rather than imported
from `test_live_poll_commit_boundary_5682.py`: a shared fixture edited for one
suite's needs silently re-aims the other's arms.

The sleep fake COUNTS rather than discards, because "did this beat rate-limit
itself against its own cache" is not observable any other way.

Mutation-tested, each of these kills at least one arm below:

* restoring `market.external_id` as the key — kills the ship arm and the
  recovery-count arm;
* SKIPPING a repeat instead of caching the fetch (the tempting wrong repair) —
  kills `test_the_parent_is_priced_when_a_sub_market_is_iterated_first`;
* not caching a FAILED fetch — kills `test_a_dead_event_is_asked_once`;
* dropping the `group_id` rung — kills the 159-row arm;
* dropping the `external_id` rung — kills the no-metadata-no-group arm;
* sleeping unconditionally — kills the rate-limit arm;
* returning the `group_id` tail without the digit test — kills the
  foreign-scheme arm.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.sql.elements import TextClause

from app.tasks import prediction_market_matching as pmm

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.

#: The production error verbatim enough that an arm cannot pass by raising
#: something Gamma would never say. Gotcha #44 applies to the clock, not to
#: this, but the same instinct does: a generic RuntimeError here would let the
#: "we stopped asking the wrong question" arms pass on a beat that was merely
#: failing differently.
GAMMA_422 = (
    "Client error '422 Unprocessable Entity' for url "
    "'https://gamma-api.polymarket.com/events/{id}'"
)


def _now() -> datetime:
    """Never a module-level clock. See gotcha #44 and the sibling file's note:
    an anchor frozen at import is minutes stale by the time CI reaches it."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# the rows — shaped like production, including the part that surprises
# --------------------------------------------------------------------------


class _Outcome:
    def __init__(self, oid: int, market_id: int, external_id: str, name: str):
        self.id = oid
        self.market_id = market_id
        self.external_id = external_id
        self.name = name
        self.rank = 1
        self.current_probability = None
        self.current_american_odds = None
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.probability_change_24h = None
        self.is_winner = None
        self.calibration_probability = None
        self.last_updated = None


class _Market:
    def __init__(
        self,
        mid: int,
        external_id: str,
        *,
        metadata=None,
        group_id=None,
        source: str = "polymarket",
    ):
        self.id = mid
        self.source = source
        self.external_id = external_id
        self.name = f"market {mid}"
        self.market_type = "game_winner"
        self.market_metadata = metadata
        self.group_id = group_id


class _Event:
    def __init__(self, eid: int, status="live"):
        self.id = eid
        self.status = status
        self.home_team_name = "Johor Darul Ta'zim"
        self.away_team_name = "Buriram United"
        # Outside `_PREGAME_MARK_LEAD_MINUTES` by any clock, so the pregame pin
        # is not quietly also under test here.
        self.commence_time = _now() + timedelta(hours=2, minutes=30)


@dataclass
class _Population:
    rows: list
    outcomes: list


# --------------------------------------------------------------------------
# the session
# --------------------------------------------------------------------------


def _classify(stmt) -> str:
    if isinstance(stmt, TextClause):
        return "text"
    if isinstance(stmt, Select):
        names = [c.get("name") for c in stmt.column_descriptions]
        if "FuturesMarket" in names:
            return "population"
        if names == ["FuturesOutcome"]:
            return "outcomes"
        return "select:" + ",".join(str(n) for n in names)
    if isinstance(stmt, Update):
        return "update"
    return "insert"


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)
        self.rowcount = len(self._rows)

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def __iter__(self):
        return iter(self._rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Answers reads by statement TYPE, and aborts like a real transaction.

    The abort behaviour is carried over from the #5682 harness deliberately:
    this file's recovery-count arms are only meaningful if a recovery is as
    expensive here as it is in Postgres.
    """

    def __init__(self, population: _Population, *, journal=None):
        self._population = population
        self.journal = journal if journal is not None else []
        self.aborted = False
        self.expunged = 0
        self.reloads = 0

    async def execute(self, stmt, params=None):
        kind = _classify(stmt)
        if self.aborted:
            raise RuntimeError("current transaction is aborted, commands ignored")
        self.journal.append(("execute", kind))
        if kind == "population":
            self.reloads += 1
            return _Result(self._population.rows)
        if kind == "outcomes":
            return _Result(self._population.outcomes)
        return _Result()

    async def commit(self):
        if self.aborted:
            raise RuntimeError("this session is in 'prepared' state")
        self.journal.append(("commit", None))

    async def rollback(self):
        self.aborted = False
        self.journal.append(("rollback", None))

    def expunge_all(self):
        self.expunged += 1

    def add(self, obj):
        return None


# --------------------------------------------------------------------------
# the venue
# --------------------------------------------------------------------------


def _gamma_event(*condition_ids: str, price: str = "0.78") -> dict:
    """One Gamma `/events/{id}` body carrying a market per condition id."""
    under = f"{1 - float(price):.2f}"
    return {
        "markets": [
            {
                "conditionId": cid,
                "outcomePrices": f'["{price}", "{under}"]',
                "outcomes": '["Yes", "No"]',
                "lastTradePrice": float(price),
                "bestBid": float(price) - 0.01,
                "bestAsk": float(price) + 0.01,
            }
            for cid in condition_ids
        ]
    }


class _PolyService:
    """Gamma, which answers 422 to anything that is not one of its event ids.

    This is the discriminator. A recorder that returned the payload for
    whatever key it was handed would let the pre-repair code pass every arm in
    this file, because the pre-repair code's mistake is precisely WHICH KEY it
    sends.
    """

    def __init__(self, events: dict, journal: list, dead: tuple = ()):
        self._events = events
        self._journal = journal
        self._dead = set(dead)

    async def get_event_by_id(self, event_id):
        self._journal.append(("fetch", event_id))
        if event_id in self._dead:
            raise Exception(GAMMA_422.format(id=event_id))
        if event_id not in self._events:
            raise Exception(GAMMA_422.format(id=event_id))
        return self._events[event_id]

    async def close(self):
        return None


# --------------------------------------------------------------------------
# the runner
# --------------------------------------------------------------------------


async def _run(monkeypatch, session, poly, *, sleeps=None):
    @asynccontextmanager
    async def _fake_session():
        yield session

    async def _record_sleep(seconds):
        if sleeps is not None:
            sleeps.append(seconds)
        return None

    monkeypatch.setattr(pmm, "get_task_session", _fake_session)
    monkeypatch.setattr(asyncio, "sleep", _record_sleep)
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda *a, **kw: poly
    )
    # The blend is a different stage with its own guards; leaving it on would
    # give a passing arm here a second possible reason.
    monkeypatch.setattr(pmm, "_select_primary_market", lambda group: None)
    return await pmm._poll_live_prediction_market_prices()


def _fetches(journal) -> list:
    return [t for kind, t in journal if kind == "fetch"]


#: The production specimen, by its ids: Gamma event 1014623, Johor Darul Ta'zim
#: vs Buriram United, live at 2026-09-13 05:0xZ. The parent row 60911042 holds
#: one outcome per derivative keyed by BARE condition id; the sub-market rows
#: hold two outcomes each, keyed with the `_yes`/`_no` suffix.
EVENT_ID = "1014623"
COND_A = "0xe0229e82d892fc77ac3b7660461f44332f1bc6be93b1817eb1998f74fd8ef1b0"
COND_B = "0xf635d88a0486ac41440d2390001ef09040c4b4df988a338158ec4ee97b92197f"


def _production_shaped_beat() -> _Population:
    """The parent plus its two sub-markets, exactly as production stores them."""
    parent = _Market(1, EVENT_ID, metadata={"polymarket_event_id": EVENT_ID})
    sub_a = _Market(2, COND_A, metadata={"polymarket_event_id": EVENT_ID})
    sub_b = _Market(3, COND_B, metadata={"polymarket_event_id": EVENT_ID})
    event = _Event(900)
    return _Population(
        [(parent, event), (sub_a, event), (sub_b, event)],
        [
            # The parent's outcomes: bare condition ids. These are the rows a
            # reader's derivative prices actually come from.
            _Outcome(10, 1, COND_A, "O/U 1.5"),
            _Outcome(11, 1, COND_B, "O/U 2.5"),
            # The sub-markets' outcomes: suffixed, and therefore unreachable by
            # the `(market_id, conditionId)` lookup whatever we fetch.
            _Outcome(20, 2, f"{COND_A}_yes", "Over"),
            _Outcome(21, 2, f"{COND_A}_no", "Under"),
            _Outcome(30, 3, f"{COND_B}_yes", "Over"),
            _Outcome(31, 3, f"{COND_B}_no", "Under"),
        ],
    )


# --------------------------------------------------------------------------
# 1. the ship
# --------------------------------------------------------------------------


class TestTheBeatStopsAskingGammaForConditionIds:
    async def test_one_event_costs_one_fetch_and_no_recoveries(self, monkeypatch):
        """The production specimen, 1/1: three rows, one call, zero 422s.

        Before the repair this fetched three times — `1014623` (fine) and two
        bare hex ids, each 422, each a full `_recover`. That is the 59-per-pass
        number reduced to its smallest reproducing case.
        """
        journal = []
        session = _Session(_production_shaped_beat(), journal=journal)
        poly = _PolyService({EVENT_ID: _gamma_event(COND_A, COND_B)}, journal)

        stats = await _run(monkeypatch, session, poly)

        assert _fetches(journal) == [EVENT_ID], (
            "the beat asked Gamma for something other than the event id exactly "
            f"once: {_fetches(journal)}"
        )
        assert stats["session_recoveries"] == 0
        assert stats["errors"] == []
        assert stats["terminal"] == "complete", (
            "a pass with nothing wrong with it still reported partial"
        )
        assert stats["polymarket_fetched"] == 1

    async def test_the_parent_is_priced_when_a_sub_market_is_iterated_first(
        self, monkeypatch
    ):
        """CACHE, do not SKIP — the arm that kills the tempting wrong repair.

        Rows sharing an event id are not interchangeable: the apply loop
        resolves `(market_id, conditionId)`, so it only ever reaches the
        outcomes of the row it is standing on. A dedupe that skipped the second
        and third rows would therefore leave the PARENT — the row carrying every
        derivative price under a bare-conditionId key — unpriced whenever a
        sub-market sorted first, which is a straight regression on the prices a
        reader sees.
        """
        journal = []
        beat = _production_shaped_beat()
        # Sub-market first, parent last: the order the old dict never had to
        # survive, because its keys were distinct.
        beat.rows = [beat.rows[1], beat.rows[2], beat.rows[0]]
        session = _Session(beat, journal=journal)
        poly = _PolyService({EVENT_ID: _gamma_event(COND_A, COND_B)}, journal)

        stats = await _run(monkeypatch, session, poly)

        assert _fetches(journal) == [EVENT_ID], "still exactly one call"
        parent_outcomes = [o for o in beat.outcomes if o.market_id == 1]
        assert [o.current_probability for o in parent_outcomes] == [0.78, 0.78], (
            "the parent's derivative prices were skipped because a sibling row "
            "had already fetched their event"
        )
        assert stats["outcomes_updated"] == 2

    async def test_a_dead_event_is_asked_once_not_once_per_row(self, monkeypatch):
        """A failed fetch is cached as None.

        Otherwise the repair trades 422-per-sub-market for
        one-real-failure-per-sub-market, which is the same waste by the other
        road — and it is the recovery count, not the call count, that makes it
        expensive.
        """
        journal = []
        session = _Session(_production_shaped_beat(), journal=journal)
        poly = _PolyService({}, journal, dead=(EVENT_ID,))

        stats = await _run(monkeypatch, session, poly)

        assert _fetches(journal) == [EVENT_ID], (
            f"a dead event was re-asked once per row it owns: {_fetches(journal)}"
        )
        assert stats["session_recoveries"] == 1, (
            "three rows paid three rollbacks for one dead event"
        )
        assert len(stats["errors"]) == 1
        assert "422" in stats["errors"][0]

    async def test_a_cache_hit_does_not_rate_limit_the_beat_against_itself(
        self, monkeypatch
    ):
        """0.3 s is owed to Polymarket per REQUEST, not per row.

        With three rows on one event, sleeping unconditionally spends 0.6 s of
        the fetch window on courtesy for calls that were never made — and the
        window is the thing #5767's floor rations.
        """
        journal = []
        sleeps: list = []
        session = _Session(_production_shaped_beat(), journal=journal)
        poly = _PolyService({EVENT_ID: _gamma_event(COND_A, COND_B)}, journal)

        await _run(monkeypatch, session, poly, sleeps=sleeps)

        assert sleeps.count(0.3) == 1, (
            f"one request, {sleeps.count(0.3)} rate-limit sleeps: {sleeps}"
        )


# --------------------------------------------------------------------------
# 2. the controls — the 6,150 rows this must not touch
# --------------------------------------------------------------------------


class TestTheRowsThatWereAlreadyRight:
    async def test_a_parent_only_beat_fetches_exactly_as_before(self, monkeypatch):
        """6,150 of 9,165 rows have `polymarket_event_id == external_id`.

        For every one of them the new cascade returns the old value, so this
        arm is the claim that the repair is a no-op where nothing was broken.
        """
        journal = []
        event = _Event(901)
        rows = [
            (_Market(i, f"10146{i}", metadata={"polymarket_event_id": f"10146{i}"}),
             event)
            for i in (1, 2, 3)
        ]
        beat = _Population(
            rows, [_Outcome(100 + i, i, f"cond-{i}", "Home") for i in (1, 2, 3)]
        )
        session = _Session(beat, journal=journal)
        poly = _PolyService(
            {f"10146{i}": _gamma_event(f"cond-{i}") for i in (1, 2, 3)}, journal
        )

        stats = await _run(monkeypatch, session, poly)

        assert _fetches(journal) == ["101461", "101462", "101463"]
        assert stats["polymarket_fetched"] == 3
        assert stats["outcomes_updated"] == 3
        assert stats["session_recoveries"] == 0

    async def test_two_different_events_are_two_fetches(self, monkeypatch):
        """The dedupe must collapse siblings, never distinct events.

        A cascade that returned a constant — or fell through to a shared
        `group_id` prefix — would pass every arm above and silently stop
        pricing every event after the first.
        """
        journal = []
        event_x, event_y = _Event(902), _Event(903)
        beat = _Population(
            [
                (_Market(1, "5001", metadata={"polymarket_event_id": "5001"}), event_x),
                (_Market(2, COND_A, metadata={"polymarket_event_id": "5002"}), event_y),
            ],
            [_Outcome(200, 1, "cond-x", "Home"), _Outcome(201, 2, "cond-y", "Home")],
        )
        session = _Session(beat, journal=journal)
        poly = _PolyService(
            {"5001": _gamma_event("cond-x"), "5002": _gamma_event("cond-y")}, journal
        )

        stats = await _run(monkeypatch, session, poly)

        assert sorted(_fetches(journal)) == ["5001", "5002"]
        assert stats["outcomes_updated"] == 2


# --------------------------------------------------------------------------
# 3. the cascade, rung by rung
# --------------------------------------------------------------------------


class TestGammaEventIdCascade:
    def test_the_minted_key_wins(self):
        market = _Market(1, COND_A, metadata={"polymarket_event_id": EVENT_ID})
        assert pmm._polymarket_gamma_event_id(market) == EVENT_ID

    def test_group_id_carries_the_159_rows_with_no_minted_key(self):
        """Measured: every one of the 159 no-metadata rows has a numeric
        `group_id` tail, and `polymarket.py`'s own docstring names this the
        established fallback."""
        market = _Market(1, COND_A, group_id=f"polymarket:{EVENT_ID}")
        assert pmm._polymarket_gamma_event_id(market) == EVENT_ID

    def test_a_group_id_from_another_scheme_is_not_an_event_id(self):
        """The digit test is the reason this rung sits BELOW the contract:
        `group_id` is a column that happens to hold the id, not a promise."""
        market = _Market(1, "1014623", group_id="kalshi:KXNFLGAME-EVT1")
        assert pmm._polymarket_gamma_event_id(market) == "1014623", (
            "a foreign group_id scheme contributed its tail as if it were a "
            "Gamma event id"
        )

    def test_external_id_is_the_last_resort_not_a_skip(self):
        """A row this code has not seen keeps the OLD behaviour. Returning
        None here would turn an unknown shape into an unpriced market."""
        market = _Market(1, "1014623")
        assert pmm._polymarket_gamma_event_id(market) == "1014623"

    def test_a_row_with_no_id_at_all_resolves_to_nothing(self):
        market = _Market(1, "")
        assert pmm._polymarket_gamma_event_id(market) is None

    @pytest.mark.parametrize("metadata", [None, {}, {"polymarket_event_id": ""},
                                          {"polymarket_event_id": None},
                                          "not-a-dict"])
    def test_an_absent_or_empty_minted_key_falls_through(self, metadata):
        """`sub_market_metadata` stamps NOTHING rather than a placeholder when
        it has no id (its docstring calls a placeholder "gotcha #53 made on
        purpose"), so every one of these shapes is a real production shape."""
        market = _Market(1, COND_A, metadata=metadata,
                         group_id=f"polymarket:{EVENT_ID}")
        assert pmm._polymarket_gamma_event_id(market) == EVENT_ID
