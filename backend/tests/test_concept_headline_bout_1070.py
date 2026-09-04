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

═══ WHAT IT READS, AND WHY THAT IS NOT THE MARKET ═══

The obvious spelling of "give me the two sides of market 7" is to re-select the
market with `selectinload(outcomes)`. That is a second read of
`futures_markets` inside the concept tier, and LAT-P094 collapsed that tier's
three 50,749-row scans of exactly that table into one and guards the count at
one (`test_feed_concept_single_scan.py`). So this reads the CHILD table under
its indexed `market_id`, and takes the third field it needs — the main event's
start — forward from the scan that already read it. The projection shape below
is that decision written down.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.utils.event_combat import _attach_headline_bouts


def _outcome(market_id, name, probability):
    """A row of the projection `_attach_headline_bouts` selects.

    `(market_id, name, current_probability)` — three columns of
    `futures_outcomes`, never a `FuturesMarket`.
    """
    return (market_id, name, probability)


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
                    _outcome(7, "Joshua Van", 0.38),
                    _outcome(7, "Alexandre Pantoja", 0.63),
                ]
            ),
            concepts,
            {7: datetime(2026, 9, 20, 3, 15, tzinfo=timezone.utc)},
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
            [_outcome(7, "Alexandre Pantoja", 0.63)],  # one side is not a bout
            [
                _outcome(7, "A", 0.4),
                _outcome(7, "B", 0.3),
                _outcome(7, "C", 0.3),
            ],  # three sides is not a bout either
            [_outcome(7, "Alexandre Pantoja", 0.63), _outcome(7, "Joshua Van", None)],
            [_outcome(7, "", 0.63), _outcome(7, "Joshua Van", 0.38)],
            [],  # the market has no priced outcomes at all
        ],
    )
    async def test_half_a_bout_is_not_a_bout(self, outcomes):
        concepts = [{"key": "event:ufc:26sep19", "main_event_id": 7}]
        await _attach_headline_bouts(_DB(outcomes), concepts)
        assert "headline_bout" not in concepts[0]

    async def test_another_cards_outcomes_are_not_this_cards_bout(self):
        """The read is batched across the page, so the rows arrive mixed.

        Grouping by `market_id` is what keeps them apart. Without it the two
        cards below hold four outcomes between them and each would claim a
        four-sided "bout" — or worse, two sides belonging to the other fight.
        """
        concepts = [
            {"key": "event:ufc:26sep19", "main_event_id": 7},
            {"key": "event:ufc:26sep26", "main_event_id": 8},
        ]
        await _attach_headline_bouts(
            _DB(
                [
                    _outcome(7, "Alexandre Pantoja", 0.63),
                    _outcome(8, "Ilia Topuria", 0.71),
                    _outcome(7, "Joshua Van", 0.38),
                    _outcome(8, "Charles Oliveira", 0.29),
                ]
            ),
            concepts,
        )
        assert [c["name"] for c in concepts[0]["headline_bout"]["competitors"]] == [
            "Alexandre Pantoja",
            "Joshua Van",
        ]
        assert [c["name"] for c in concepts[1]["headline_bout"]["competitors"]] == [
            "Ilia Topuria",
            "Charles Oliveira",
        ]

    async def test_a_bout_with_no_known_start_still_renders(self):
        """`commence_time` is carried, not read — so it can be absent.

        A missing start must cost the date, never the two fighters and their
        two numbers, which are the whole point of the archetype.
        """
        concepts = [{"key": "event:ufc:26sep19", "main_event_id": 7}]
        await _attach_headline_bouts(
            _DB([_outcome(7, "A", 0.6), _outcome(7, "B", 0.4)]), concepts
        )
        assert concepts[0]["headline_bout"]["commence_time"] is None
        assert len(concepts[0]["headline_bout"]["competitors"]) == 2

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
                    row
                    for i in range(1, 6)
                    for row in (_outcome(i, "A", 0.6), _outcome(i, "B", 0.4))
                ]
            ),
            concepts,
        )
        assert reads["n"] == 1
        assert all("headline_bout" in c for c in concepts)

    async def test_it_never_reads_futures_markets(self):
        """The LAT-P094 guard, pinned where the read is written.

        `test_feed_concept_single_scan.py` catches this too, but only through
        the whole tier — from there the failure reads as "the concept tier does
        two scans" and says nothing about which function added one. Here it
        names the line.
        """
        seen: list[str] = []

        class _SpyDB(_DB):
            async def execute(self, statement, *a, **k):
                seen.append(str(statement))
                return await super().execute(statement, *a, **k)

        await _attach_headline_bouts(
            _SpyDB([_outcome(7, "A", 0.6), _outcome(7, "B", 0.4)]),
            [{"key": "event:ufc:26sep19", "main_event_id": 7}],
        )
        assert seen and all("futures_outcomes" in s for s in seen)
        assert not any("FROM futures_markets" in s for s in seen), (
            "`_attach_headline_bouts` re-reads futures_markets — that is the "
            "concept tier's second 50,749-row scan coming back"
        )


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
