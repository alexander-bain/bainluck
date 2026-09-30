"""#9466 — the Sports strip stops ranking "Completed Match 98%" as a match's outcome.

WHAT A READER SAW. ``/sports`` at 390px, 2026-09-28 21:20Z, *Player Props &
Progressions*: "Jingshan (Doubles): Detiuc/Khromacheva vs Costoulas/Martins —
1 Completed Match 98% · 2 Detiuc/Khromacheva 69%", and four more cards like it.

The fixture rows are the production rows as read that evening: parent
``62786044`` (``polymarket:1091311``, ``event_id`` 15319942,
``mutually_exclusive`` false, ``market_type`` duel) whose two legs are the
``condition_id`` s of its sub-markets ``63086106`` (Completed Match) and
``62907384`` (the match winner), both rows on the same group. The control is
``63031562``, "Phillies vs. Braves - 1st Inning Winner", a one-winner board
(``mutually_exclusive`` true) served beside it, which must stay.

Driven through the real ``grouped_feed`` coroutine with a stub session, because
the defect is in the route's assembly: the verdict itself is search's (#8375)
and is that file's to test.
"""

import pytest

from app.routes.futures import grouped_feed

COMPLETED_COND = "0xbe933d1cb84a9716eeaf4349251abbb00d204365f8c9718b4a80904ffd2e0894"
WINNER_COND = "0xd9ef3f1307be591a631c427852033924687880a1c52ac31755d920ff577bf791"
GROUP = "polymarket:1091311"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Savepoint:
    def __init__(self, session):
        self._session = session

    async def commit(self):
        self._session.savepoint_log.append("commit")

    async def rollback(self):
        self._session.savepoint_log.append("rollback")


class _Session:
    """Canned reads in order; a read the fixture did not can fails loudly."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.savepoint_log = []

    async def begin_nested(self):
        self.savepoint_log.append("begin")
        return _Savepoint(self)

    async def execute(self, _stmt):
        self.calls += 1
        if not self._results:
            raise AssertionError(f"the route made read {self.calls}; none canned")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return _Result(result)


class _Outcome:
    def __init__(self, oid, name, probability, external_id):
        self.id = oid
        self.name = name
        self.probability = probability
        self.american_odds = None
        self.current_probability = probability
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.external_id = external_id


class _Market:
    def __init__(self, mid, name, group_id, outcomes, *, event_id, exclusive, market_type="duel", sport="tennis"):
        self.id = mid
        self.name = name
        self.source = "polymarket"
        self.category = "game_prop"
        self.llm_sport_category = sport
        self.status = "open"
        self.group_id = group_id
        self.group_type = "polymarket_sub_market"
        self.market_type = market_type
        self.outcomes = outcomes
        self.event_id = event_id
        self.mutually_exclusive = exclusive


def _specimen(event_id=15319942):
    return _Market(
        62786044,
        "Jingshan (Doubles): Detiuc/Khromacheva vs Costoulas/Martins",
        GROUP,
        [
            _Outcome(237916458, "Completed Match", 0.98, COMPLETED_COND),
            _Outcome(237203051, "Detiuc/Khromacheva", 0.69, WINNER_COND),
        ],
        event_id=event_id,
        exclusive=False,
    )


def _control():
    return _Market(
        63031562,
        "Philadelphia Phillies vs. Atlanta Braves - 1st Inning Winner",
        "polymarket:1097001",
        [
            _Outcome(1, "Draw", 0.60, "0xinning-draw"),
            _Outcome(2, "Atlanta Braves", 0.25, "0xinning-atl"),
            _Outcome(3, "Philadelphia Phillies", 0.17, "0xinning-phi"),
        ],
        event_id=None,
        exclusive=True,
        market_type="field",
        sport="baseball",
    )


#: ``(id, group_id, external_id)`` — the two sub-markets, as production holds them.
SIBLINGS = [(63086106, GROUP, COMPLETED_COND), (62907384, GROUP, WINNER_COND)]


async def _serve(session):
    return await grouped_feed(
        request=type("R", (), {"scope": {}})(),
        response=type("S", (), {"headers": {}})(),
        category=None,
        sport=None,
        sports_only=True,
        limit=20,
        db=session,
    )


def _card_ids(payload):
    return [c["market"]["id"] for c in payload["feed"] if c.get("type") == "market"]


def _outcome_names(payload):
    return [
        o["name"]
        for c in payload["feed"]
        if c.get("type") == "market"
        for o in c["market"]["outcomes"]
    ]


@pytest.mark.asyncio
async def test_the_specimen_container_is_withheld_and_the_control_stays():
    session = _Session([[_specimen(), _control()], SIBLINGS])
    payload = await _serve(session)
    assert 62786044 not in _card_ids(payload)
    assert "Completed Match" not in _outcome_names(payload)
    # The strip is still a strip: the one-winner board beside it survives.
    assert _card_ids(payload) == [63031562]
    assert session.savepoint_log == ["begin", "commit"]


@pytest.mark.asyncio
async def test_a_leg_that_names_no_sibling_row_keeps_the_parent():
    """#8375's rule: a parent whose sub-markets were never written as rows is the
    only place those markets exist, so it stays."""
    session = _Session([[_specimen(), _control()], SIBLINGS[:1]])
    payload = await _serve(session)
    assert 62786044 in _card_ids(payload)


@pytest.mark.asyncio
async def test_a_sibling_on_another_group_does_not_count():
    session = _Session(
        [[_specimen(), _control()], [(63086106, GROUP, COMPLETED_COND), (62907384, "polymarket:9", WINNER_COND)]]
    )
    payload = await _serve(session)
    assert 62786044 in _card_ids(payload)


@pytest.mark.asyncio
async def test_an_unlinked_board_is_not_a_candidate_and_costs_no_read():
    """The unlinked leg-copy boards are real questions (#8375's measurement);
    one canned read means a second would raise."""
    session = _Session([[_specimen(event_id=None), _control()]])
    payload = await _serve(session)
    assert session.calls == 1
    assert session.savepoint_log == []
    assert 62786044 in _card_ids(payload)


@pytest.mark.asyncio
async def test_a_pool_with_only_exclusive_boards_costs_no_read():
    session = _Session([[_control()]])
    payload = await _serve(session)
    assert session.calls == 1
    assert _card_ids(payload) == [63031562]


@pytest.mark.asyncio
async def test_a_failed_read_fails_open():
    session = _Session([[_specimen(), _control()], RuntimeError("statement timeout")])
    payload = await _serve(session)
    assert 62786044 in _card_ids(payload)
    assert session.savepoint_log == ["begin", "rollback"]
