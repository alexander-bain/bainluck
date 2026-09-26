"""#8923: searching "UFC" on fight night answers with tonight's card.

Specimen (390px, 20:36Z 9/26): `/search?q=UFC` served five championship futures
and `event_concepts: []` while `event:ufc:26sep26` (Fight Night: Rosas Jr vs
Barcelos, 82 markets, first bout 21:10Z) was the live card. The market-name path
cannot reach a card from the promotion's name — fight markets read "Will X win…"
and bouts carry fighter names — so the card has to come from the query.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.events import (
    _detect_query_names_ufc,
    _pick_ufc_card_concept,
    _search_concept_evidence,
    _upsert_search_query_derived_concept,
    search_events,
)
from app.utils.search_match_class import rank as _s_rank

_T0 = datetime(2026, 9, 26, 21, 10, tzinfo=timezone.utc)


def _card(key, name, status, opens_at, *, is_major=False):
    return {
        "key": key,
        "name": name,
        "domain": "ufc",
        "status": status,
        "is_major": is_major,
        "opens_at": opens_at,
        "latest_commence": opens_at + timedelta(hours=5) if opens_at else None,
    }


# The lister's own order on fight night: marquee first, so next month's numbered
# card sorts ahead of tonight's live fight night.
_UFC_332 = _card("event:ufc:26oct24", "UFC 332: Topuria vs Holloway", "upcoming",
                 _T0 + timedelta(days=28), is_major=True)
_TONIGHT = _card("event:ufc:26sep26", "Fight Night: Rosas Jr vs Barcelos", "live", _T0)
_NEXT_WEEK = _card("event:ufc:26oct03", "Fight Night: Vettori vs Dolidze", "upcoming",
                   _T0 + timedelta(days=7))
_LISTER_ORDER = [_UFC_332, _TONIGHT, _NEXT_WEEK]


class TestTheQueryNamesThePromotion:
    @pytest.mark.parametrize("q", [
        "UFC", "ufc", "UFC Fight Night", "ufc 332", "MMA", "mma tonight",
        "mixed martial arts",
    ])
    def test_fires(self, q):
        assert _detect_query_names_ufc(q)

    @pytest.mark.parametrize("q", [
        None, "", "Rosas", "fight night", "comma", "ufcw", "hummma", "yankees",
    ])
    def test_does_not_fire(self, q):
        assert not _detect_query_names_ufc(q)


class TestWhichCardLeads:
    def test_live_card_leads_over_the_listers_marquee_first_order(self):
        out = _pick_ufc_card_concept("UFC", _LISTER_ORDER)
        assert out["key"] == "event:ufc:26sep26"

    def test_with_nothing_live_the_soonest_opening_card_leads(self):
        tonight_done = [_UFC_332, _NEXT_WEEK]
        assert _pick_ufc_card_concept("UFC", tonight_done)["key"] == "event:ufc:26oct03"

    def test_an_upcoming_card_does_not_beat_a_live_one_by_opening_earlier(self):
        # A live card that opened hours ago still opens LATER than nothing; the
        # upcoming arm must never win on the clock alone.
        early_upcoming = _card("event:ufc:26sep20", "Fight Night: X vs Y", "upcoming",
                               _T0 - timedelta(days=6))
        assert _pick_ufc_card_concept("UFC", [early_upcoming, _TONIGHT])["key"] == (
            "event:ufc:26sep26"
        )

    def test_a_numbered_query_takes_only_that_card(self):
        assert _pick_ufc_card_concept("ufc 332", _LISTER_ORDER)["key"] == "event:ufc:26oct24"

    def test_a_numbered_query_with_no_such_card_prepends_nothing(self):
        assert _pick_ufc_card_concept("ufc 999", _LISTER_ORDER) is None

    def test_a_card_outside_live_or_upcoming_is_never_the_answer(self):
        done = _card("event:ufc:26sep19", "UFC 331: A vs B", "completed", _T0 - timedelta(days=7))
        assert _pick_ufc_card_concept("UFC", [done]) is None

    def test_no_cards_is_no_concept(self):
        assert _pick_ufc_card_concept("UFC", []) is None

    def test_the_row_is_the_search_concept_shape(self):
        assert _pick_ufc_card_concept("UFC", _LISTER_ORDER) == {
            "key": "event:ufc:26sep26",
            "name": "Fight Night: Rosas Jr vs Barcelos",
            "domain": "ufc",
            "market_id": None,
        }


class TestTheCardSurvivesTheScorer:
    def test_prepended_card_is_rankable_on_a_query_its_name_does_not_contain(self):
        # Ruling 041 drops DERIVED rows the query does not name. The card's name
        # does not say "UFC"; being query-gated is what makes it rankable, and the
        # upsert is how a row records that.
        concept = _pick_ufc_card_concept("UFC", _LISTER_ORDER)
        pool = _upsert_search_query_derived_concept([], set(), concept)
        survivors = _s_rank("UFC", [(_search_concept_evidence(c), c) for c in pool])
        assert [c["key"] for c in survivors] == ["event:ufc:26sep26"]

    def test_a_market_derived_twin_is_upgraded_not_left_derived(self):
        twin = {"key": "event:ufc:26sep26", "name": "Rosas Jr vs Barcelos",
                "domain": "ufc", "market_id": 7, "_derived": True}
        seen = {"event:ufc:26sep26"}
        concept = _pick_ufc_card_concept("UFC", _LISTER_ORDER)
        pool = _upsert_search_query_derived_concept([twin], seen, concept)
        assert len(pool) == 1 and pool[0]["_derived"] is False
        survivors = _s_rank("UFC", [(_search_concept_evidence(c), c) for c in pool])
        assert [c["key"] for c in survivors] == ["event:ufc:26sep26"]


class TestTheRouteWiresIt:
    _SRC = inspect.getsource(search_events)

    def test_the_prepend_runs_before_the_concept_scorer(self):
        pick = self._SRC.index("_pick_ufc_card_concept(")
        scorer = self._SRC.index("event_concepts = _search_rank_candidates(")
        assert pick < scorer

    def test_the_card_goes_through_the_shared_upsert(self):
        block = self._SRC[self._SRC.index("_pick_ufc_card_concept("):]
        block = block[: block.index("_mark(\"futures_format_concepts\")")]
        assert "_upsert_search_query_derived_concept(" in block

    def test_the_lister_read_is_inside_its_own_savepoint(self):
        start = self._SRC.index("_detect_query_names_ufc(")
        block = self._SRC[start: self._SRC.index("_pick_ufc_card_concept(")]
        assert "begin_nested()" in block
        assert block.index("begin_nested()") < block.index("_list_ufc_cards(db)")
        assert "_ufc_savepoint.rollback()" in block
