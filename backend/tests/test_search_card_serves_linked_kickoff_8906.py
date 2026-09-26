"""A SEARCH ANSWER ABOUT A GAME IS DATED BY THE GAME. #8906 (producer half).

`/search?q=chiefs` at 390px, 2026-09-26 19:40Z: the ANSWERS card printed
`KC Chiefs vs MIA Dolphins: Spread … · Sep 29` while the GAMES row above it read
`Tomorrow 10:00 AM` (Sep 27). Markets 61806201 / 61970727 are linked to event
14781701 (`commence_time 2026-09-27 17:00Z`); their `resolution_date` is Kalshi's
settlement, 2026-09-29 17:00Z. The search card served no link and no kickoff.

The producer serves `event_commence_time` on a linked card; an unlinked card
gets no key; `resolution_date` is unmoved everywhere. ux prints it (half 2).
"""

from datetime import datetime, timezone

import pytest

from app.routes.events import _stamp_linked_event_kickoff


UTC = timezone.utc
KICKOFF = datetime(2026, 9, 27, 17, 0, tzinfo=UTC)
SETTLES = "2026-09-29T17:00:00+00:00"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Answers the one keyed read of `events` from a fixed table."""

    def __init__(self, events: dict[int, datetime | None]):
        self.events = events
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        (ids,) = stmt.compile().params.values()  # the single IN list
        return _Result([(eid, ct) for eid, ct in self.events.items() if eid in ids])


def _card(mid: int) -> dict:
    return {"id": mid, "resolution_date": SETTLES}


@pytest.mark.asyncio
async def test_linked_prop_serves_its_games_kickoff():
    cards = {61806201: _card(61806201), 61970727: _card(61970727)}
    facts = [(61806201, "KXNFLSPREAD-X", 14781701), (61970727, "KXNFLTOTAL-X", 14781701)]
    db = _FakeDB({14781701: KICKOFF})

    assert await _stamp_linked_event_kickoff(db, cards, facts) == 2

    for mid in cards:
        assert cards[mid]["event_commence_time"] == "2026-09-27T17:00:00+00:00"
        assert cards[mid]["resolution_date"] == SETTLES  # unmoved
    assert db.calls == 1  # one IN for the page, not one per card


@pytest.mark.asyncio
async def test_unlinked_card_gets_no_key_and_no_query():
    cards = {112938: _card(112938)}
    db = _FakeDB({14781701: KICKOFF})

    assert await _stamp_linked_event_kickoff(db, cards, [(112938, None, None)]) == 0

    assert "event_commence_time" not in cards[112938]
    assert db.calls == 0


@pytest.mark.asyncio
async def test_mixed_page_stamps_only_the_linked_card():
    cards = {61806201: _card(61806201), 112938: _card(112938)}
    facts = [(61806201, "KXNFLSPREAD-X", 14781701), (112938, None, None)]

    await _stamp_linked_event_kickoff(_FakeDB({14781701: KICKOFF}), cards, facts)

    assert cards[61806201]["event_commence_time"] == "2026-09-27T17:00:00+00:00"
    assert "event_commence_time" not in cards[112938]


@pytest.mark.asyncio
async def test_link_to_a_missing_or_undated_event_serves_nothing():
    cards = {1: _card(1), 2: _card(2)}
    facts = [(1, None, 999), (2, None, 14781701)]

    assert await _stamp_linked_event_kickoff(_FakeDB({14781701: None}), cards, facts) == 0

    assert "event_commence_time" not in cards[1]
    assert "event_commence_time" not in cards[2]


@pytest.mark.asyncio
async def test_facts_for_cards_not_served_are_ignored():
    """`facts` covers deduped + promoted rows; only served cards are stamped."""
    cards = {61806201: _card(61806201)}
    facts = [(61806201, None, 14781701), (777, None, 14781701)]

    await _stamp_linked_event_kickoff(_FakeDB({14781701: KICKOFF}), cards, facts)

    assert set(cards) == {61806201}
