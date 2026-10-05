"""#10559 — a UFC card's date line named a different day than its own chip.

Production, 2026-10-05 21:21Z, `/api/feed?mode=sports`: `event:ufc:26oct05`
("Contender Series: Onley vs Bierley") served `headline:"Tomorrow"` and
`start_date 2026-10-06T22:00Z`, while `headline_bout.commence_time` was
`2026-10-06T06:20Z`, which is Kalshi's `expected_expiration_time` for
`KXUFCFIGHT-26OCT05ONLBIE`. The web date line reads
`headline_bout.commence_time ?? start_date`, so a Pacific reader saw
"Tomorrow … Mon, Oct 5". ESPN puts the card at 2026-10-06T23:00Z.

The rule: a main event cannot begin before its own card opens. A bout stamp
earlier than the concept's `opens_at` is withheld (`None`), and the renderer
falls back to `start_date`, the clock the chip already counts (#6747).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.event_combat import _attach_headline_bouts


class _Result:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _DB:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    async def execute(self, *_a, **_k):
        return _Result(self._outcomes)


_OUTCOMES = [
    (64389311, "Summer Onley", 0.685, None, None),
    (64389311, "Alivia Bierley", 0.315, None, None),
]
_OPENS = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc)


def _card(opens_at):
    return {
        "key": "event:ufc:26oct05",
        "main_event_id": 64389311,
        "start_date": opens_at.isoformat() if opens_at else None,
        "opens_at": opens_at,
    }


@pytest.mark.asyncio
class TestBoutBeforeCardOpens:
    async def test_the_specimen_withholds_the_expiry_estimate(self):
        concepts = [_card(_OPENS)]
        await _attach_headline_bouts(
            _DB(_OUTCOMES),
            concepts,
            {64389311: datetime(2026, 10, 6, 6, 20, tzinfo=timezone.utc)},
        )
        bout = concepts[0]["headline_bout"]
        # The bout itself still attaches: two names, two numbers.
        assert [c["name"] for c in bout["competitors"]] == [
            "Summer Onley",
            "Alivia Bierley",
        ]
        assert bout["commence_time"] is None

    @pytest.mark.parametrize(
        "commence",
        [
            datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc),  # opens with the card
            datetime(2026, 10, 7, 3, 15, tzinfo=timezone.utc),  # main event, later
        ],
    )
    async def test_a_main_event_at_or_after_the_opening_keeps_its_time(self, commence):
        concepts = [_card(_OPENS)]
        await _attach_headline_bouts(_DB(_OUTCOMES), concepts, {64389311: commence})
        assert concepts[0]["headline_bout"]["commence_time"] == commence.isoformat()

    async def test_a_card_with_no_opening_keeps_the_bout_time(self):
        commence = datetime(2026, 10, 6, 6, 20, tzinfo=timezone.utc)
        concepts = [_card(None)]
        await _attach_headline_bouts(_DB(_OUTCOMES), concepts, {64389311: commence})
        assert concepts[0]["headline_bout"]["commence_time"] == commence.isoformat()

    async def test_an_uncomparable_pair_changes_nothing(self):
        naive = datetime(2026, 10, 6, 6, 20)
        concepts = [_card(_OPENS)]
        await _attach_headline_bouts(_DB(_OUTCOMES), concepts, {64389311: naive})
        assert concepts[0]["headline_bout"]["commence_time"] == naive.isoformat()
