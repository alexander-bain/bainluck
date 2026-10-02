"""#10064 — the /sports props strip stops serving props on finished matches, and
stops showing a threshold question twice.

THE DEFECT. Production, 2026-10-01 12:10Z, ``/sports`` at 390px, "Player Props
& Progressions (18)": 8 of 18 cards were about tennis matches that had already
finished, priced as if still to be played — "Roman Safiullin vs Flavio Cobolli:
Total Games" ≥18.5 61% / ≥23.5 47% / ≥28.5 36%, served 4.5 h after event
15321019 went ``completed``. Two of the eight were the SAME question twice: the
ladder card and, lower down, the plain market card it was built from.

THE SPECIMENS BELOW ARE THE STORED ROWS, read 2026-10-01 ~12:15Z via
``/api/admin/db-query``: market 63153133 ``status='open'``, ``resolution_date``
2026-10-14 02:00Z, ``event_id`` 15321019 (``completed``, ``completed_at``
07:43Z). Neither #9899 clause can reach it: the resolution date is two weeks
out and no leg is past 99%.

TWO RULES. (1) The pool query refuses a market whose linked event is in
``settled_hero.FINISHED_STATUSES`` — in the SQL, above the ``limit * 5`` slice,
so a refused row's slot backfills. (2) A threshold group claims its markets'
ids, as the exact-score group already does (#9844).
"""

import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.settled_hero import FINISHED_STATUSES
from tests._grouped_feed_slate import NO_SLATE, is_slate_read


def leg(prob, name, oid):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=Decimal(str(prob)),
        current_yes_bid=None,
        current_yes_ask=None,
        probability=Decimal(str(prob)),
        american_odds=None,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, stmt):
        if is_slate_read(stmt):  # #10208: no slate in this pool
            return NO_SLATE
        self.statements.append(stmt)
        if len(self.statements) > 1:
            raise AssertionError("second read: this pool has nothing to fold")
        return _Result(self._rows)


class _Market:
    def __init__(self, mid, name, outcomes):
        self.id = mid
        self.name = name
        self.source = "kalshi"
        self.category = "game_prop"
        self.llm_sport_category = "tennis"
        self.status = "open"
        self.group_id = None
        self.group_type = None
        self.market_type = None
        self.outcomes = outcomes


class _Request:
    scope: dict = {}


class _Response:
    def __init__(self):
        self.headers = {}


async def _serve(markets, limit=20):
    from app.routes.futures import grouped_feed

    session = _Session(markets)
    payload = await grouped_feed(
        request=_Request(), response=_Response(), category=None, sport=None,
        sports_only=True, limit=limit, db=session,
    )
    return payload, session


#: Market 63153133 as stored — the three rungs verbatim.
TOTAL_GAMES = (
    63153133,
    "Roman Safiullin vs Flavio Cobolli: Total Games",
    [(0.605, "Over 18.5 games", 238112739),
     (0.465, "Over 23.5 games", 238112740),
     (0.36, "Over 28.5 games", 238112741)],
)

#: A plain two-way market that groups with nothing — the control.
MATCH_WINNER = (
    63600416,
    "Japan Open Tennis Championships: Carlos Alcaraz vs Matteo Arnaldi",
    [(0.88, "Carlos Alcaraz", 238900001), (0.12, "Matteo Arnaldi", 238900002)],
)


def _market(spec):
    mid, name, legs = spec
    return _Market(mid, name, [leg(p, n, oid) for p, n, oid in legs])


def _where(session):
    sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    return sql.split("WHERE", 1)[1]


@pytest.mark.asyncio
class TestFinishedMatchIsNotLoaded:
    async def test_the_pool_query_refuses_a_market_on_a_finished_event(self):
        _, session = await _serve([])
        where = _where(session)
        assert re.search(
            r"futures_markets\.event_id IS NULL OR \(?NOT \(EXISTS \(SELECT \*\s+FROM events\s+"
            r"WHERE events\.id = futures_markets\.event_id AND events\.status IN \(([^)]*)\)",
            where,
        ), where

    async def test_the_refused_statuses_are_exactly_the_finished_set(self):
        _, session = await _serve([])
        m = re.search(r"events\.status IN \(([^)]*)\)", _where(session))
        assert m, _where(session)
        assert {s.strip(" '") for s in m.group(1).split(",")} == set(FINISHED_STATUSES)

    async def test_a_playable_event_is_not_in_the_refused_set(self):
        """`suspended` is a rain delay and `voided`/`merged` markets may await a
        relink — withholding their props would empty live cards."""
        for status in ("scheduled", "live", "suspended", "voided", "merged"):
            assert status not in FINISHED_STATUSES

    async def test_a_market_with_no_event_is_still_admitted(self):
        """The clause is an OR on `event_id IS NULL` — a futures market with no
        game is never refused by it."""
        _, session = await _serve([])
        assert "futures_markets.event_id IS NULL OR" in _where(session)


@pytest.mark.asyncio
class TestThresholdQuestionShownOnce:
    async def test_the_ladder_consumes_its_market(self):
        payload, _ = await _serve([_market(TOTAL_GAMES), _market(MATCH_WINNER)])
        ladders = [c for c in payload["feed"] if c["type"] == "threshold"]
        plain = [c["market"]["id"] for c in payload["feed"] if c["type"] == "market"]
        assert [c["title"] for c in ladders] == [TOTAL_GAMES[1]]
        assert [p["probability"] for p in ladders[0]["points"]] == [
            Decimal("0.605"), Decimal("0.465"), Decimal("0.36")]
        assert TOTAL_GAMES[0] not in plain, payload["feed"]

    async def test_an_ungrouped_market_still_ships(self):
        """Control: claiming the ladder's market must not claim its neighbours."""
        payload, _ = await _serve([_market(TOTAL_GAMES), _market(MATCH_WINNER)])
        plain = [c["market"]["id"] for c in payload["feed"] if c["type"] == "market"]
        assert plain == [MATCH_WINNER[0]]

    async def test_every_question_appears_once(self):
        """The reader's sentence: no title is printed twice on the strip."""
        payload, _ = await _serve([_market(TOTAL_GAMES), _market(MATCH_WINNER)])
        titles = [c.get("title") or c["market"]["name"] for c in payload["feed"]]
        assert len(titles) == len(set(titles)), titles
