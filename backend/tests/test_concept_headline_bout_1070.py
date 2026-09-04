"""ux/1070 item 2 — a fight card's hero is its MAIN EVENT, not an outright.

═══ THE DEFECT ═══

The concept card's hero came from `_resolve_concept_leader`, which returns the
top entry of a concept's whole competitor list. For a grand tour or a golf major
that IS the answer: one field, one favourite. A fight card is not a field — it
is a container of two-sided bouts (`primary.kind == "co_equal_list"`), and its
"leader" is therefore the most lopsided fight of the night.

Measured on production 2026-09-04, `GET /api/feed?tags=["sport:mma"]`:

    event:ufc:26sep10  "Alexandre Pantoja vs Joshua Van"   leader: Tai Tuivasa 84%
    event:ufc:26sep05  "Fight Night: Hooker vs Parnasse"   leader: Salahdine Parnasse 82%

The first names one bout in its title and prices a different one. Alex read the
second as "a two-fighter bout rendered as a one-line outright card" — which is
exactly what it is.

So a combat concept now carries `headline_bout`: the two sides of its main
event, from that ONE two-sided market, so the pair is a market's own pair (it
cannot be assembled out of two sources into a sum that is not 100 — #2582) and
the card can render the game archetype: two participants, two numbers, a date.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import _attach_headline_bouts


def _outcome(name, probability):
    return SimpleNamespace(name=name, current_probability=probability)


def _market(mid, outcomes, commence=None):
    return SimpleNamespace(id=mid, outcomes=outcomes, commence_time=commence)


class _Result:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _DB:
    def __init__(self, markets):
        self._markets = list(markets)

    async def execute(self, *_a, **_k):
        return _Result(self._markets)


class _AngryDB:
    async def execute(self, *_a, **_k):
        raise RuntimeError("outcomes read failed")


@pytest.mark.asyncio
class TestAttachHeadlineBouts:
    async def test_the_main_event_arrives_as_two_sides(self):
        concepts = [{"key": "event:ufc:26sep19", "main_event_id": 7}]
        await _attach_headline_bouts(
            _DB(
                [
                    _market(
                        7,
                        [
                            _outcome("Joshua Van", 0.38),
                            _outcome("Alexandre Pantoja", 0.63),
                        ],
                        datetime(2026, 9, 20, 3, 15, tzinfo=timezone.utc),
                    )
                ]
            ),
            concepts,
        )
        bout = concepts[0]["headline_bout"]
        # Favourite first — the renderer's leading row is a decision made here,
        # once, rather than in each of the two renderers.
        assert [c["name"] for c in bout["competitors"]] == [
            "Alexandre Pantoja",
            "Joshua Van",
        ]
        assert [c["probability"] for c in bout["competitors"]] == [0.63, 0.38]
        assert bout["commence_time"] == "2026-09-20T03:15:00+00:00"

    async def test_a_card_with_no_kalshi_main_event_is_untouched(self):
        """An events-only card (T-5, before Kalshi lists it) keeps its leader."""
        concepts = [{"key": "event:ufc:26sep19", "main_event_id": None}]
        await _attach_headline_bouts(_AngryDB(), concepts)
        assert "headline_bout" not in concepts[0]

    @pytest.mark.parametrize(
        "outcomes",
        [
            [_outcome("Alexandre Pantoja", 0.63)],  # one side is not a bout
            [
                _outcome("A", 0.4),
                _outcome("B", 0.3),
                _outcome("C", 0.3),
            ],  # three sides is not a bout either
            [_outcome("Alexandre Pantoja", 0.63), _outcome("Joshua Van", None)],
            [_outcome("", 0.63), _outcome("Joshua Van", 0.38)],
        ],
    )
    async def test_half_a_bout_is_not_a_bout(self, outcomes):
        concepts = [{"key": "event:ufc:26sep19", "main_event_id": 7}]
        await _attach_headline_bouts(_DB([_market(7, outcomes)]), concepts)
        assert "headline_bout" not in concepts[0]

    async def test_a_failed_read_never_costs_the_tier(self):
        concepts = [{"key": "event:ufc:26sep19", "main_event_id": 7}]
        await _attach_headline_bouts(_AngryDB(), concepts)  # must not raise
        assert "headline_bout" not in concepts[0]

    async def test_it_is_one_read_for_the_whole_page(self):
        """Not one per card: the concept tier is a cold-build latency budget."""
        reads = {"n": 0}

        class _CountingDB(_DB):
            async def execute(self, *a, **k):
                reads["n"] += 1
                return await super().execute(*a, **k)

        concepts = [
            {"key": f"event:ufc:2{i}", "main_event_id": i} for i in range(1, 6)
        ]
        await _attach_headline_bouts(
            _CountingDB(
                [
                    _market(i, [_outcome("A", 0.6), _outcome("B", 0.4)])
                    for i in range(1, 6)
                ]
            ),
            concepts,
        )
        assert reads["n"] == 1
        assert all("headline_bout" in c for c in concepts)


class TestTheFeedServesIt:
    @staticmethod
    def _feed_source() -> str:
        from app.routes import feed

        return inspect.getsource(feed)

    def test_the_payload_carries_the_bout(self):
        src = self._feed_source()
        assert '**({"headline_bout": _headline_bout} if _headline_bout else {})' in src, (
            "the concept payload no longer carries the main event — the card is "
            "back to leading with the most lopsided fight of the night"
        )

    def test_a_bout_is_enough_to_render(self):
        """Q407 Item 3's gate must not drop a card that CAN answer."""
        src = self._feed_source()
        assert "_concept_can_render = bool(_leader) or bool(_headline_bout)" in src

    def test_a_settled_card_still_leads_with_its_result(self):
        """Exclusivity is enforced where both are resolved, as `_champion` is."""
        src = self._feed_source()
        assert (
            '_headline_bout = c.get("headline_bout") if not _is_whathit else None'
            in src
        )

    def test_the_lister_attaches_it(self):
        from app.utils import event_combat

        assert "_attach_headline_bouts(" in inspect.getsource(
            event_combat.list_card_concepts
        )
