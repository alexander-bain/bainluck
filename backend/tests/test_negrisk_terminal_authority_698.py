"""#698 — the negRisk-parent arm grades only a payout the venue has verified.

THE DEFECT (source, bound at origin/master 946f6c42ee, blob bbe30d7d). The
negRisk-parent branch of ``_backfill_polymarket_winners_from_api``:

1. accepted ``venue_has_closed_the_leg`` as enough to read a result;
2. took ``outcomePrices[0]`` as the settlement price;
3. graded ``is_winner = price >= 0.90``;
4. wrote that price — possibly a frozen quote — to ``current_probability``;
5. wrote ``is_winner`` / ``api_settlement`` in a SECOND statement.

So a closed leg still quoting 0.006 was stamped Lost and one quoting 0.95 was
stamped Won, each over a price the reader contract (``settlement_display``)
correctly calls ``nonterminal_stored_price`` → Unknown.

THE FIX. ``venue_terminal_leg_result`` reads the existing verified-result
contract (``polymarket_ws.gamma_resolution_verdict``, #9418): ``closed is True``,
``umaResolutionStatus == "resolved"``, exactly one payout 1 and the rest 0. Only
then does ``gamma_leg_settle_stmt`` write grade, source and terminal 0/1 price in
one statement. Anything else is left exactly as stored.

WHAT THIS FILE DOES NOT CLAIM. No stored row is repaired; a prevention fix does
not clear grades already written. No production row is attributed to this
writer. Fixture: ``tests/fixtures/polymarket_resolved_zero_legs_5343/
gamma-event-106884.json`` — the venue's retained bytes, reused unedited; every
negative below is derived from one real leg by changing one field.
"""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.polymarket_api as poly_api_mod
import app.tasks.backfill_winners as bw
import app.tasks.redis_state as redis_state
from app.tasks.polymarket_ws import (
    WS_RESOLUTION_UNCONFIRMED,
    WS_RESOLUTION_VOID,
    WS_RESOLUTION_WINNER,
    gamma_resolution_verdict,
)
from app.utils.polymarket_settlement_scan import venue_terminal_leg_result

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_resolved_zero_legs_5343"
    / "gamma-event-106884.json"
)
SPECIMEN = json.loads(FIXTURE.read_bytes())
EVENT_ID = "106884"
PARENT_ID = 113883
SIBLING_CHILD_ID = 13792801

BY_TITLE = {m["groupItemTitle"]: m for m in SPECIMEN["markets"]}
#: A real closed leg: `closed: true`, `umaResolutionStatus: resolved`, ["0","1"].
SETTLED_LOSER = BY_TITLE["January Meeting"]


def _leg(**changes):
    """The real January leg with exactly the named fields changed."""
    leg = copy.deepcopy(SETTLED_LOSER)
    for k, v in changes.items():
        if v is _DROP:
            leg.pop(k, None)
        else:
            leg[k] = v
    return leg


_DROP = object()


def _prices(*p):
    return json.dumps([str(x) for x in p])


# --------------------------------------------------------------------------
# The pure contract
# --------------------------------------------------------------------------

#: (label, leg, expected) — expected is True (Yes won), False (lost) or None.
CASES = [
    ("retained settled loser", _leg(), False),
    ("verified winner", _leg(outcomePrices=_prices("1", "0")), True),
    ("verified winner, float form", _leg(outcomePrices=_prices("1.0", "0.0")), True),
    ("closed frozen dust quote", _leg(outcomePrices=_prices("0.006", "0.994")), None),
    ("closed frozen favourite quote", _leg(outcomePrices=_prices("0.95", "0.05")), None),
    ("closed near-certain quote", _leg(outcomePrices=_prices("0.999", "0.001")), None),
    ("closed payout, UMA absent", _leg(umaResolutionStatus=_DROP), None),
    ("closed payout, UMA None", _leg(umaResolutionStatus=None), None),
    ("closed payout, UMA proposed", _leg(umaResolutionStatus="proposed"), None),
    ("closed payout, UMA disputed", _leg(umaResolutionStatus="disputed"), None),
    ("open leg with a payout-shaped quote", _leg(closed=False), None),
    ("closed as a string", _leg(closed="true"), None),
    ("closed absent", _leg(closed=_DROP), None),
    ("prices absent", _leg(outcomePrices=_DROP), None),
    ("prices not JSON", _leg(outcomePrices="[0, 1"), None),
    ("prices not numbers", _leg(outcomePrices=_prices("a", "b")), None),
    ("one price only", _leg(outcomePrices=_prices("1")), None),
    ("empty prices", _leg(outcomePrices="[]"), None),
    ("two payouts of one", _leg(outcomePrices=_prices("1", "1")), None),
    ("no payout of one", _leg(outcomePrices=_prices("0", "0")), None),
    ("void", _leg(outcomePrices=_prices("0.5", "0.5")), None),
]


@pytest.mark.parametrize("label,leg,expected", CASES, ids=[c[0] for c in CASES])
def test_the_leg_contract(label, leg, expected):
    assert venue_terminal_leg_result(leg) is expected, label


@pytest.mark.parametrize(
    "prices", [_prices("1", "nan"), _prices("nan", "0"), _prices("1", "inf")]
)
def test_a_non_finite_payout_is_no_result(prices):
    # The one input on which this is deliberately stricter than the #9418
    # verdict: `abs(nan) >= 1e-9` is False, so a NaN would otherwise read as 0.
    assert venue_terminal_leg_result(_leg(outcomePrices=prices)) is None


@pytest.mark.parametrize("value", [None, [], "closed", 1, object()])
def test_a_payload_that_is_not_a_leg_is_no_result(value):
    assert venue_terminal_leg_result(value) is None


@pytest.mark.parametrize("label,leg,expected", CASES, ids=[c[0] for c in CASES])
def test_the_leg_contract_is_the_ws_verified_contract(label, leg, expected):
    """Parity: the same payload through #9418's verdict says the same thing.

    The leg's own ``clobTokenIds`` (index-aligned with ``outcomePrices``) map
    to two stand-in outcome ids; Yes winning is the first token winning.
    """
    tokens = json.loads(SETTLED_LOSER["clobTokenIds"])
    asset_to_outcome = {tokens[0]: 1, tokens[1]: 2}
    kind, owner = gamma_resolution_verdict(None, leg, [1, 2], asset_to_outcome)
    if expected is None:
        assert kind in (WS_RESOLUTION_UNCONFIRMED, WS_RESOLUTION_VOID), label
    else:
        assert kind == WS_RESOLUTION_WINNER, label
        assert (owner == 1) is expected, label


# --------------------------------------------------------------------------
# The single settling statement
# --------------------------------------------------------------------------


@pytest.mark.parametrize("won,price", [(True, "1.0"), (False, "0.0")])
def test_one_statement_carries_grade_source_and_terminal_price(won, price):
    sql = str(bw.gamma_leg_settle_stmt(won))
    assert sql.count("UPDATE futures_outcomes") == 1
    assert f"SET is_winner = {'true' if won else 'false'}," in sql
    assert "resolution_source = 'api_settlement'" in sql
    assert f"current_probability={price}," in sql
    assert "current_american_odds=NULL" in sql
    # #2024: the change stamp moves only on a real change.
    assert (
        f"WHEN fo.current_probability IS DISTINCT FROM CAST({price} AS numeric(7,6))"
        in sql
    )
    assert "last_updated = NOW()" in sql
    assert "WHERE fo.market_id = :mid" in sql and "AND fo.external_id = :cid" in sql
    # Q487: the shared duplicate-leg rule rides every external_id-keyed winner write.
    from app.utils.winner_field_coherence import DUPLICATE_CONDITION_LEG_SQL

    assert DUPLICATE_CONDITION_LEG_SQL in sql


@pytest.mark.parametrize("won", [True, False])
def test_the_settling_statement_moves_no_calibration_input(won):
    sql = str(bw.gamma_leg_settle_stmt(won))
    for col in ("opening_probability", "calibration_probability", "futures_odds_snapshots"):
        assert col not in sql, col


# --------------------------------------------------------------------------
# The rail
# --------------------------------------------------------------------------


class _Row:
    def __init__(self, id, external_id, group_type, poly_event_id):
        self.id = id
        self.external_id = external_id
        self.group_type = group_type
        self.poly_event_id = poly_event_id


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _Shape:
    legs = 30
    winners = 0
    held = 0


class _ShapeResult:
    def one(self):
        return _Shape()


class _FakeRedis:
    def get(self, key):
        return None

    def setex(self, key, ttl, value):
        return True

    def delete(self, key):
        return 0

    def sadd(self, key, *vals):
        return None

    def smembers(self, key):
        return set()

    def expire(self, key, ttl):
        return True


class _Rig:
    """Every outcome-touching statement the rail issues, per (market, cid)."""

    def __init__(self, stored):
        self.stored = set(stored)
        self.writes: dict = {}  # (mid, cid) -> [sql, ...]
        self.all_sql: list = []
        self.mint_reads: list = []

    def touched(self, mid=PARENT_ID):
        return {cid for (m, cid) in self.writes if m == mid}


def _install(monkeypatch, rig, *, rows, event):
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: _FakeRedis())

    async def _execute(stmt, params=None):
        p = params or {}
        if type(stmt).__name__ in ("Update", "Insert"):
            bound = stmt.compile().params
            key = (bound.get("market_id_1"), bound.get("external_id_1"))
            rig.all_sql.append(str(stmt))
            if key in rig.stored:
                rig.writes.setdefault(key, []).append(("orm", dict(bound)))
                return MagicMock(rowcount=1)
            return MagicMock(rowcount=0)
        sql = str(getattr(stmt, "text", stmt))
        rig.all_sql.append(sql)
        if "FROM futures_markets fm" in sql:
            picked = [r for r in rows if r.id > (p.get("last_id") or 0)]
            return _Result(picked[: (p.get("limit") or len(picked))])
        if "COUNT(*) FILTER (WHERE fo.is_winner)" in sql:
            rig.mint_reads.append(p.get("cid"))
            return _ShapeResult()
        if "UPDATE futures_outcomes" in sql:
            key = (p.get("mid"), p.get("cid"))
            if key in rig.stored:
                rig.writes.setdefault(key, []).append(("text", sql))
                return MagicMock(rowcount=1)
            return MagicMock(rowcount=0)
        return MagicMock(rowcount=0)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_market_by_condition(self, cid):
            return None

        async def get_event_by_id(self, eid):
            return event if str(eid) == EVENT_ID else None

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)


#: The derived event. Each named leg is one real leg of 106884 with one field
#: changed; the rest of the event is the venue's bytes.
WINNER = "January Meeting"          # → outcomePrices ["1","0"]: verified Won
LOSER = "March Meeting"             # unchanged: verified Lost
DUST = "April Meeting"              # → ["0.006","0.994"], still closed + resolved
FAVOURITE = "June Meeting"          # → ["0.95","0.05"], still closed + resolved
NO_UMA = "July Meeting"             # → umaResolutionStatus removed
BAD_PRICES = "September 2026 Meeting"  # → outcomePrices unparseable
OPEN = "October 2026 Meeting"       # unchanged: open at the venue

STORED = [WINNER, LOSER, DUST, FAVOURITE, NO_UMA, BAD_PRICES, OPEN]
CID = {t: BY_TITLE[t]["conditionId"] for t in BY_TITLE}
UNKNOWN = [DUST, FAVOURITE, NO_UMA, BAD_PRICES]


def _derived_event():
    event = copy.deepcopy(SPECIMEN)
    legs = {m["groupItemTitle"]: m for m in event["markets"]}
    legs[WINNER]["outcomePrices"] = _prices("1", "0")
    legs[DUST]["outcomePrices"] = _prices("0.006", "0.994")
    legs[FAVOURITE]["outcomePrices"] = _prices("0.95", "0.05")
    legs[NO_UMA].pop("umaResolutionStatus")
    legs[BAD_PRICES]["outcomePrices"] = "not json"
    return event


async def _run(monkeypatch, *, event=None, extra_rows=(), extra_stored=()):
    stored = {(PARENT_ID, CID[t]) for t in STORED} | set(extra_stored)
    rig = _Rig(stored)
    rows = [_Row(PARENT_ID, EVENT_ID, "negrisk", EVENT_ID), *extra_rows]
    _install(monkeypatch, rig, rows=rows, event=event or _derived_event())
    stats = await bw._backfill_polymarket_winners_from_api(limit=10)
    return stats, rig


def _grade_of(sqls):
    """(won, price) of the one settling statement, or None."""
    (kind, sql), = sqls
    assert kind == "text"
    won = "SET is_winner = true," in sql
    assert won or "SET is_winner = false," in sql
    price = 1.0 if "current_probability=1.0," in sql else 0.0
    return won, price


@pytest.mark.asyncio
class TestTheParentArm:
    async def test_a_verified_winner_and_loser_are_graded_with_terminal_prices(
        self, monkeypatch
    ):
        stats, rig = await _run(monkeypatch)
        assert _grade_of(rig.writes[(PARENT_ID, CID[WINNER])]) == (True, 1.0)
        assert _grade_of(rig.writes[(PARENT_ID, CID[LOSER])]) == (False, 0.0)
        assert stats["winners_set"] == 1 and stats["losers_set"] == 1, stats

    async def test_each_graded_leg_is_written_by_exactly_one_statement(
        self, monkeypatch
    ):
        # The old arm issued a price UPDATE and then a separate grade UPDATE.
        _st, rig = await _run(monkeypatch)
        for title in (WINNER, LOSER):
            writes = rig.writes[(PARENT_ID, CID[title])]
            assert len(writes) == 1, (title, writes)

    @pytest.mark.parametrize("title", UNKNOWN)
    async def test_a_closed_leg_without_a_verified_payout_is_left_as_stored(
        self, monkeypatch, title
    ):
        stats, rig = await _run(monkeypatch)
        assert CID[title] not in rig.touched(), rig.writes.get((PARENT_ID, CID[title]))
        assert stats["legs_closed_without_verified_result"] == len(UNKNOWN), stats

    async def test_the_open_leg_is_still_untouched(self, monkeypatch):
        stats, rig = await _run(monkeypatch)
        assert CID[OPEN] not in rig.touched()
        assert stats["legs_open_at_venue"] == 7, stats

    async def test_only_the_verified_legs_are_touched(self, monkeypatch):
        _st, rig = await _run(monkeypatch)
        assert rig.touched() == {CID[WINNER], CID[LOSER]}

    async def test_an_unverified_winner_looking_leg_is_never_minted(self, monkeypatch):
        # A closed 0.95 leg we do not hold: the old arm read it as Won, found no
        # row and asked the champion mint. It is not a result, so it asks nothing.
        event = _derived_event()
        legs = {m["groupItemTitle"]: m for m in event["markets"]}
        unheld = legs["January 2027 Meeting"]
        unheld["closed"] = True
        unheld["umaResolutionStatus"] = "resolved"
        unheld["outcomePrices"] = _prices("0.96", "0.04")
        stats, rig = await _run(monkeypatch, event=event)
        assert unheld["conditionId"] not in rig.mint_reads
        assert stats["champion_mint"] == {}, stats

    async def test_a_verified_winner_we_do_not_hold_still_reaches_the_mint(
        self, monkeypatch
    ):
        # Control for the test above: the mint path is gated, not removed.
        event = _derived_event()
        legs = {m["groupItemTitle"]: m for m in event["markets"]}
        unheld = legs["January 2027 Meeting"]
        unheld["closed"] = True
        unheld["umaResolutionStatus"] = "resolved"
        unheld["outcomePrices"] = _prices("1", "0")
        _st, rig = await _run(monkeypatch, event=event)
        assert unheld["conditionId"] in rig.mint_reads

    async def test_no_observation_or_calibration_input_is_written(self, monkeypatch):
        _st, rig = await _run(monkeypatch)
        for sql in rig.all_sql:
            if "UPDATE" in sql or "INSERT" in sql:
                for col in (
                    "futures_odds_snapshots",
                    "opening_probability",
                    "calibration_probability",
                ):
                    assert col not in sql, (col, sql[:200])

    async def test_an_unrelated_sibling_market_keeps_its_own_branch(self, monkeypatch):
        # A decomposed child row in the same run takes the single-market branch,
        # which this change does not touch: the closed January child still
        # grades through its own ORM update, exactly as before.
        child_cid = CID[LOSER]
        child = _Row(SIBLING_CHILD_ID, child_cid, None, EVENT_ID)
        _st, rig = await _run(
            monkeypatch,
            extra_rows=[child],
            extra_stored=[(SIBLING_CHILD_ID, child_cid)],
        )
        kinds = [k for k, _ in rig.writes[(SIBLING_CHILD_ID, child_cid)]]
        assert "orm" in kinds, rig.writes[(SIBLING_CHILD_ID, child_cid)]
        orm = [b for k, b in rig.writes[(SIBLING_CHILD_ID, child_cid)] if k == "orm"]
        assert orm[0]["is_winner"] is False
