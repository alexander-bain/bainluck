"""#1927, Brief24A — Discover's editorial chain judges ELIGIBILITY on the
admission number, never on a penalised rank.

The unit half of ``tests/integration/test_feed_negative_rank_keeps_discover_
eligibility_1927a_pg.py``: the same contract at the three helpers that make the
decision — ``_discover_event_excitement_score`` (what the exception reads),
``_demote_non_exceptional_discover_events`` (the cap) and
``_filter_discover_event_noise`` (the deletion) — with hand-built items, so the
contract is pinned without a database and the fallback for items that carry
no ``_admission_score`` is pinned too.
"""

from __future__ import annotations

import copy

import pytest

from app.routes.feed import (
    _demote_non_exceptional_discover_events,
    _discover_event_excitement_score,
    _filter_discover_event_noise,
    _is_discover_event_demotion_exception,
)


def _live_game(score: int, *, admission: int | None, media: bool, sport="baseball_mlb"):
    data = {
        "id": 1,
        "sport": sport,
        "status": "live",
        "home_team": "Rockies",
        "away_team": "Marlins",
        "event_tags": [],
        "highlight": {"label": "Coin flip"},
    }
    if media:
        data["home_team_data"] = {"primary_color": "#0C2340"}
    item = {"type": "event", "score": score, "_rank_score": float(score), "data": data}
    if admission is not None:
        item["_admission_score"] = admission
    return item


class TestTheExcitementReadingIsTheAdmissionNumber:
    def test_an_unsettled_game_reads_admission_when_stamped(self):
        # the Nah reader's shape: 97 base, 38 rank, admission 97
        assert _discover_event_excitement_score(_live_game(38, admission=97, media=False)) == 97.0

    def test_it_falls_back_to_score_when_nothing_is_stamped(self):
        """A fixture built by hand, a page base published before this ship:
        exactly the pre-Brief24A reading."""
        assert _discover_event_excitement_score(_live_game(38, admission=None, media=False)) == 38.0

    def test_a_malformed_stamp_falls_back_too(self):
        item = _live_game(38, admission=None, media=False)
        item["_admission_score"] = "n/a"
        assert _discover_event_excitement_score(item) == 38.0

    def test_a_settled_game_still_reads_ei_not_either_score(self):
        item = _live_game(38, admission=97, media=False)
        item["data"]["status"] = "completed"
        item["data"]["ei"] = {"score": 91}
        assert _discover_event_excitement_score(item) == pytest.approx(91.0)

    def test_the_exception_answers_the_negative_reader_as_it_answers_the_neutral_one(self):
        neutral = _live_game(97, admission=97, media=False)
        nah = _live_game(38, admission=97, media=False)
        swiped = _live_game(19, admission=97, media=False)
        assert _is_discover_event_demotion_exception(neutral)
        assert _is_discover_event_demotion_exception(nah)
        assert _is_discover_event_demotion_exception(swiped)

    def test_a_positive_boost_still_lifts_a_game_into_the_exception(self):
        """base_score was NOT substituted: a loved sport's boost is inside the
        admission number, so a 60-point routine game the reader loves (×1.5 →
        90) is exceptional for that reader, exactly as before this ship."""
        loved = _live_game(90, admission=90, media=False)
        neutral = _live_game(60, admission=60, media=False)
        assert _is_discover_event_demotion_exception(loved)
        assert not _is_discover_event_demotion_exception(neutral)

    def test_if_its_wild_keeps_its_higher_bar(self):
        """`sport_suppress` is inside the admission multiplier on purpose:
        97 × 0.7 = 67 is not exceptional for the "only if it's wild" reader."""
        assert not _is_discover_event_demotion_exception(_live_game(67, admission=67, media=False))


class TestTheChainKeepsTheNegativeReadersEligibleGame:
    def _chain(self, items):
        items = copy.deepcopy(items)
        _demote_non_exceptional_discover_events(items)
        return _filter_discover_event_noise(items)

    def test_the_no_media_live_game_survives_for_the_nah_reader_and_keeps_its_rank(self):
        nah = _live_game(38, admission=97, media=False)
        out = self._chain([nah])
        assert len(out) == 1, "the Nah reader's eligible game was deleted"
        # not capped: the exception held, so the penalised rank is served as-is
        assert out[0]["score"] == 38 and out[0]["_rank_score"] == 38.0

    def test_the_same_game_is_deleted_without_the_stamp_which_is_the_brief24_defect(self):
        """The red, in one line: the identical item minus `_admission_score`
        reads 38, is capped to 35, and is removed for lacking media."""
        assert self._chain([_live_game(38, admission=None, media=False)]) == []

    def test_a_genuinely_non_exceptional_no_media_game_is_deleted_for_everyone(self):
        neutral = _live_game(60, admission=60, media=False)
        nah = _live_game(24, admission=60, media=False)
        assert self._chain([neutral]) == []
        assert self._chain([nah]) == []

    def test_a_non_exceptional_media_game_is_capped_and_kept_for_both(self):
        for item in (_live_game(60, admission=60, media=True), _live_game(24, admission=60, media=True)):
            out = self._chain([item])
            assert len(out) == 1 and out[0]["score"] <= 35

    def test_the_negative_term_is_still_observable_in_the_ordering(self):
        neutral = _live_game(97, admission=97, media=False)
        nah = _live_game(38, admission=97, media=False)
        nah["data"]["id"] = 2
        out = self._chain([nah, neutral])
        assert {it["data"]["id"] for it in out} == {1, 2}
        by_id = {it["data"]["id"]: it["score"] for it in out}
        assert by_id[2] < by_id[1]
