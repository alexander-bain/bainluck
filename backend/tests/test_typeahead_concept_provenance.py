"""A dedup guard must not decide provenance — the v3800 concept regression.

Ruling 041 made derived-only evidence UNRANKABLE, which correctly killed the
Emmys family (`super bowl` answering `concept:event:awards:emmys`). Measured on
production v3800 it also killed four concepts that were RIGHT, and the cause was
not the ruling: it was the dedup guard in front of it.

`/typeahead` fills its concept pool twice. The first loop derives a concept from
each matched MARKET and flags it `_derived`. The second pass runs the
`_detect_query_*` detectors, which match the QUERY itself and are therefore
rankable. Both mint the same key — "Grammy Winner: Best New Artist" derives
`event:awards:grammys`, and so does `_detect_query_awards_concept("grammys")` —
and the guard was `key not in seen`, so the rankable twin was skipped and only
the UNRANKABLE copy reached the scorer.

Measured 2026-08-13 on v3800: `grammys`, `oscars` and `world cup` each returned
five markets and ZERO concepts, where v3798 returned the concept at rank 1.

These tests pin the upgrade semantics and the collision that produced it.
"""

import pytest

from app.routes.events import (
    _detect_query_awards_concept,
    _detect_query_world_cup_concept,
    _upsert_query_derived_concept,
)
from app.utils.event_awards import derive_awards_concept
from app.utils.event_soccer import derive_soccer_concept
from app.utils.search_match_class import UNRANKABLE, Evidence, match_class


def _market_derived(key: str, text: str = "derived name") -> dict:
    """A concept row exactly as the market-derived loop leaves it."""
    return {
        "type": "event_concept",
        "text": text,
        "event_key": key,
        "sport_key": "awards",
        "_derived": True,
    }


class TestKeyCollisionIsReal:
    """The two paths mint identical keys — the premise of the whole bug."""

    def test_grammys_query_and_market_derive_the_same_key(self):
        from_query = _detect_query_awards_concept("grammys")
        from_market = derive_awards_concept(None, "Grammy Winner: Best New Artist")
        assert from_query is not None and from_market is not None
        assert from_query["key"] == from_market["key"] == "event:awards:grammys"

    def test_world_cup_query_and_market_derive_the_same_key(self):
        from_query = _detect_query_world_cup_concept("world cup")
        from_market = derive_soccer_concept(None, "2030 FIFA World Cup Champion", "soccer")
        assert from_query is not None and from_market is not None
        assert from_query["key"] == from_market["key"]


class TestUpsertUpgradesRatherThanSkips:
    def test_colliding_key_is_upgraded_in_place_not_skipped(self):
        pool = [_market_derived("event:awards:grammys")]
        seen = {"event:awards:grammys"}

        out = _upsert_query_derived_concept(
            pool, seen,
            name="The Grammys", key="event:awards:grammys", sport_key="awards",
        )

        assert len(out) == 1, "an upgrade must not duplicate the row"
        assert out[0]["_derived"] is False, "the upgraded row must be rankable"
        assert out[0]["text"] == "The Grammys", "canonical query-derived name wins"

    def test_upgraded_row_moves_to_the_front(self):
        pool = [
            _market_derived("event:awards:emmys"),
            _market_derived("event:awards:grammys"),
        ]
        seen = {"event:awards:emmys", "event:awards:grammys"}

        out = _upsert_query_derived_concept(
            pool, seen,
            name="The Grammys", key="event:awards:grammys", sport_key="awards",
        )

        assert out[0]["event_key"] == "event:awards:grammys"
        assert len(out) == 2

    def test_the_unrelated_derived_sibling_stays_derived(self):
        """Upgrading Grammys must not make the Emmys row rankable too."""
        pool = [
            _market_derived("event:awards:emmys"),
            _market_derived("event:awards:grammys"),
        ]
        out = _upsert_query_derived_concept(
            pool, set(),
            name="The Grammys", key="event:awards:grammys", sport_key="awards",
        )
        emmys = [c for c in out if c["event_key"] == "event:awards:emmys"]
        assert emmys and emmys[0]["_derived"] is True

    def test_absent_key_is_inserted_at_the_front_and_rankable(self):
        pool = [_market_derived("event:awards:emmys")]
        seen = {"event:awards:emmys"}

        out = _upsert_query_derived_concept(
            pool, seen,
            name="The Masters", key="event:golf:the-masters", sport_key="golf",
        )

        assert out[0]["event_key"] == "event:golf:the-masters"
        assert out[0].get("_derived") is not True
        assert "event:golf:the-masters" in seen

    def test_no_duplicate_keys_after_upsert(self):
        pool = [_market_derived("event:awards:grammys")]
        out = _upsert_query_derived_concept(
            pool, set(),
            name="The Grammys", key="event:awards:grammys", sport_key="awards",
        )
        keys = [c["event_key"] for c in out]
        assert len(keys) == len(set(keys))

    def test_limit_is_respected(self):
        pool = [_market_derived(f"event:awards:c{i}") for i in range(3)]
        out = _upsert_query_derived_concept(
            pool, set(),
            name="The Grammys", key="event:awards:grammys",
            sport_key="awards", limit=3,
        )
        assert len(out) == 3
        assert out[0]["event_key"] == "event:awards:grammys"

    def test_repeated_upsert_is_idempotent(self):
        pool = [_market_derived("event:awards:grammys")]
        seen: set = set()
        for _ in range(3):
            pool = _upsert_query_derived_concept(
                pool, seen,
                name="The Grammys", key="event:awards:grammys", sport_key="awards",
            )
        assert len(pool) == 1
        assert pool[0]["_derived"] is False


class TestTheScorerAgrees:
    """The upgrade is only worth anything if it changes the match class."""

    @staticmethod
    def _evidence(row: dict) -> Evidence:
        return Evidence(
            name=row["text"],
            aliases=(),
            outcomes=(),
            kind=row["type"],
            derived=bool(row.get("_derived")),
            sport_key=row.get("sport_key"),
        )

    def test_market_derived_concept_is_unrankable(self):
        row = _market_derived("event:awards:grammys", text="The Grammys")
        assert match_class("grammys", self._evidence(row)) is UNRANKABLE

    def test_upgraded_concept_is_rankable(self):
        pool = _upsert_query_derived_concept(
            [_market_derived("event:awards:grammys")], set(),
            name="The Grammys", key="event:awards:grammys", sport_key="awards",
        )
        assert match_class("grammys", self._evidence(pool[0])) is not UNRANKABLE

    def test_upgraded_concept_outranks_the_market_that_derived_it(self):
        """The v3800 failure, end to end: concept beats 'Grammy Winner: ...'."""
        pool = _upsert_query_derived_concept(
            [_market_derived("event:awards:grammys")], set(),
            name="The Grammys", key="event:awards:grammys", sport_key="awards",
        )
        concept_mc = match_class("grammys", self._evidence(pool[0]))
        market_mc = match_class("grammys", Evidence(
            name="Grammy Winner: Best New Artist", aliases=(), outcomes=(),
            kind="futures", derived=False, sport_key="entertainment",
        ))
        assert concept_mc is not UNRANKABLE
        # Lower class is better; a tie is broken by kind (concept above market).
        assert market_mc is UNRANKABLE or concept_mc <= market_mc

    def test_emmys_stays_dead_on_an_unrelated_query(self):
        """Ruling 041's win must survive the repair."""
        row = _market_derived("event:awards:emmys", text="The Emmys")
        assert match_class("super bowl", self._evidence(row)) is UNRANKABLE
        # And no query detector resurrects it.
        assert _detect_query_awards_concept("super bowl") is None


@pytest.mark.parametrize("query,expected_key", [
    ("grammys", "event:awards:grammys"),
    ("oscars", "event:awards:oscars"),
])
def test_regressed_gold_probes_now_produce_a_rankable_concept(query, expected_key):
    """The named probes from the v3800 read."""
    detected = _detect_query_awards_concept(query)
    assert detected is not None and detected["key"] == expected_key

    pool = _upsert_query_derived_concept(
        [_market_derived(expected_key)], set(),
        name=detected["name"], key=detected["key"], sport_key="awards",
    )
    assert pool[0]["_derived"] is False
    assert pool[0]["event_key"] == expected_key
