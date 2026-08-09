"""Discover leads with tonight's games (Alex ruling 2026-08-08(d)(1)).

The finding: `bainluck.com` returned 55 cards with ZERO game events, led by
aliens and hantavirus, while games were on.

These tests lean hard on the BOTH-DIRECTIONS guard, because this touches feed
ordering and #1091 is the standing lesson that a feed change is exactly how the
Sports tab got emptied. The pass is a pure stable reorder — it must be provably
incapable of dropping anything.

Clock is injected everywhere; nothing is seeded off `datetime.now()` (gotcha #44).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tonights_games import (
    MAX_LEAD,
    lead_with_tonights_games,
    select_tonights_games,
)

NOW = datetime(2026, 8, 8, 23, 0, 0, tzinfo=timezone.utc)  # 4pm PT

MEDIA = {"home_team_data": {"logo_small": "x"}, "away_team_data": {"logo_small": "y"}}


def game(name, status="live", starts_in_hours=None, score=30, media=True, **extra):
    data = {"status": status, "id": name, **({} if not media else MEDIA), **extra}
    if starts_in_hours is not None:
        data["commence_time"] = (NOW + timedelta(hours=starts_in_hours)).isoformat()
    return {"type": "event", "score": score, "_rank_score": float(score), "data": data}


def future(name, score=90):
    return {"type": "futures", "score": score, "_rank_score": float(score),
            "data": {"id": name, "title": name}}


def ids(items):
    return [it["data"]["id"] for it in items]


class TestTheReportedCase:
    def test_a_live_game_leads_a_deck_of_futures(self):
        feed = [future("aliens"), future("hantavirus"), future("oscars"),
                game("sox-vs-as", status="live")]
        assert ids(lead_with_tonights_games(feed, NOW))[0] == "sox-vs-as"

    def test_the_discover_mix_stays_below_in_its_original_order(self):
        feed = [future("aliens"), future("hantavirus"), future("oscars"),
                game("sox-vs-as", status="live")]
        assert ids(lead_with_tonights_games(feed, NOW)) == [
            "sox-vs-as", "aliens", "hantavirus", "oscars",
        ]

    def test_a_game_starting_soon_also_leads(self):
        feed = [future("aliens"), game("tonight", status="scheduled", starts_in_hours=2)]
        assert ids(lead_with_tonights_games(feed, NOW))[0] == "tonight"


class TestItCannotEmptyOrDropAnything:
    """#1091's lesson. A reorder that can drop is not a reorder."""

    def test_nothing_is_ever_removed(self):
        feed = [future("a"), game("live1"), future("b"),
                game("done", status="completed"), game("nomedia", media=False)]
        out = lead_with_tonights_games(feed, NOW)
        assert len(out) == len(feed)
        assert set(ids(out)) == set(ids(feed))

    def test_no_eligible_game_is_a_pure_no_op(self):
        feed = [future("a"), future("b"), game("done", status="completed")]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_out_of_season_is_a_no_op_without_consulting_any_calendar(self):
        # "During a live season" self-answers: no live or imminent game, no lead.
        feed = [future("a"), game("in_3_days", status="scheduled", starts_in_hours=72)]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_empty_feed_survives(self):
        assert lead_with_tonights_games([], NOW) == []

    def test_a_feed_of_only_games_is_reordered_not_truncated(self):
        feed = [game(f"g{i}", status="live") for i in range(8)]
        out = lead_with_tonights_games(feed, NOW)
        assert len(out) == 8
        assert set(ids(out)) == set(ids(feed))

    def test_malformed_items_do_not_raise(self):
        feed = [{"type": "event"}, {"type": "event", "data": None},
                {"type": "event", "data": {"status": None}}, future("ok")]
        out = lead_with_tonights_games(feed, NOW)
        assert len(out) == len(feed)


class TestNotAScoreboard:
    def test_at_most_MAX_LEAD_games_are_promoted(self):
        feed = [game(f"g{i}", status="live") for i in range(6)] + [future("a")]
        out = lead_with_tonights_games(feed, NOW)
        # The 4th live game must fall back behind the lead block.
        assert len(select_tonights_games(feed, NOW)) == MAX_LEAD

    def test_the_cap_is_configurable(self):
        feed = [game(f"g{i}", status="live") for i in range(5)]
        assert len(select_tonights_games(feed, NOW, max_lead=2)) == 2

    def test_a_game_with_no_team_media_never_leads(self):
        # The "Lehigh Valley IronPigs at Worcester Red Sox above the actual MLB
        # game" failure, in feed form.
        feed = [future("aliens"), game("minor_league", status="live", media=False)]
        assert lead_with_tonights_games(feed, NOW) == feed


class TestWhatCountsAsTonight:
    @pytest.mark.parametrize("status", ["completed", "closed", "postponed", "cancelled"])
    def test_a_finished_or_dead_game_never_leads(self, status):
        feed = [future("a"), game("g", status=status)]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_a_game_just_inside_the_window_leads(self):
        feed = [future("a"), game("g", status="scheduled", starts_in_hours=3.9)]
        assert ids(lead_with_tonights_games(feed, NOW))[0] == "g"

    def test_a_game_just_outside_the_window_does_not(self):
        feed = [future("a"), game("g", status="scheduled", starts_in_hours=4.1)]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_a_scheduled_game_whose_start_has_passed_does_not_lead(self):
        # A lagging status, not an imminent game.
        feed = [future("a"), game("g", status="scheduled", starts_in_hours=-2)]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_a_scheduled_game_with_no_commence_time_does_not_lead(self):
        feed = [future("a"), game("g", status="scheduled")]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_unparseable_commence_time_does_not_raise_or_lead(self):
        item = game("g", status="scheduled")
        item["data"]["commence_time"] = "not a date"
        feed = [future("a"), item]
        assert lead_with_tonights_games(feed, NOW) == feed

    def test_naive_commence_time_is_treated_as_utc(self):
        item = game("g", status="scheduled")
        item["data"]["commence_time"] = (NOW + timedelta(hours=1)).replace(tzinfo=None).isoformat()
        feed = [future("a"), item]
        assert ids(lead_with_tonights_games(feed, NOW))[0] == "g"


class TestLeadOrdering:
    def test_live_games_come_before_upcoming_ones(self):
        feed = [game("soon", status="scheduled", starts_in_hours=1),
                game("live", status="live")]
        assert ids(select_tonights_games(feed, NOW)) == ["live", "soon"]

    def test_among_upcoming_games_the_soonest_leads(self):
        feed = [game("later", status="scheduled", starts_in_hours=3),
                game("sooner", status="scheduled", starts_in_hours=1)]
        assert ids(select_tonights_games(feed, NOW)) == ["sooner", "later"]

    def test_among_live_games_the_existing_rank_order_is_kept(self):
        # This pass re-orders; it does not re-judge. A marquee live game still
        # beats a routine one because scoring already said so.
        feed = [game("routine", status="live", score=20),
                game("marquee", status="live", score=34)]
        assert ids(select_tonights_games(feed, NOW)) == ["marquee", "routine"]


class TestScoresAreUntouched:
    def test_no_score_is_modified(self):
        feed = [future("a", score=90), game("g", status="live", score=30)]
        before = [(it["score"], it["_rank_score"]) for it in feed]
        lead_with_tonights_games(feed, NOW)
        assert [(it["score"], it["_rank_score"]) for it in feed] == before

    def test_the_promoted_game_keeps_its_demoted_score(self):
        # Leading the deck is a placement decision, not a re-scoring one — the
        # demotion stays intact for every other consumer of `score`.
        feed = [future("a", score=90), game("g", status="live", score=35)]
        out = lead_with_tonights_games(feed, NOW)
        assert out[0]["score"] == 35
