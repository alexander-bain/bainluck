"""ux/1070 item 5 — the sports you follow that have no teams.

═══ THE DEFECT ═══

Alex shopped My Stuff signed in on 2026-09-04 at 7:00am PT. He follows PGA golf
at 1.0. The whole page held ONE golf market: "Golfers to win a PGA Tour major in
2027" — a market that resolves fourteen months out. This week's tournament grid
was in the database the whole time and none of it could reach him.

Not a data gap and not a ranking accident. My Stuff's futures half is a single
gate:

    if my_teams_only:
        if not matched_by_id and not matched_by_name:
            continue

`matched_by_id` is `outcome.team_id in user_team_ids`; `matched_by_name` is a
followed TEAM's name inside an outcome name. Golf has no teams, so a golf market
can satisfy neither, ever — and the two category filters above that gate are
worse than neutral: golf and tennis are not in `MY_STUFF_ALLOWED_SPORT_KEYS` or
`MY_STUFF_ALLOWED_CATEGORIES` at all, so they were being `continue`d before the
match was even attempted. A page whose promise is "the sports you follow" was
structurally incapable of showing an individual sport.

("Golfers to win a PGA Tour major in 2027" reached him because it carries no
sport FK and its category filter only fires `if not market_sport_key and
market.llm_sport_category` — it fell through both filters into the name match
against a followed team, which it lost, so it arrived by a different tier
entirely. The one golf market on the page was there by accident.)

═══ WHY A FOLLOW IS NOT A LOOSENING ═══

The fix admits a market on the SPORT follow alone — but only for a sport with no
team dimension. `_score_futures` subtracts `MY_STUFF_ALLOWED_CATEGORIES` from the
follow set before it ever reaches this predicate, so baseball, football,
basketball, hockey, soccer and MMA keep the team-match rule exactly as written.
Following the NBA does not put every NBA market on your page; following golf puts
this week's golf on it, because there is nothing else golf could mean.

The three bounds below are the whole of "this week's golf": followed, dated
inside the window, not an award. Each one has a defect behind it and each is
pinned here.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.personalization import (
    MY_STUFF_FOLLOW_WINDOW_DAYS,
    followed_sport_categories,
    my_stuff_admits_followed_sport,
)

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)

# The sports Alex follows that have no team to match on. This is what
# `_score_futures` hands the predicate: `followed_sport_categories(...) -
# MY_STUFF_ALLOWED_CATEGORIES`, i.e. golf and tennis and not baseball.
FOLLOWED = {"golf", "tennis"}


def admits(**overrides) -> bool:
    """The predicate with a this-week golf market as the default subject."""
    kwargs = {
        "category": "golf",
        "market_tier": 1,
        "resolution_date": NOW + timedelta(days=3),
        "followed_categories": FOLLOWED,
        "now": NOW,
    }
    kwargs.update(overrides)
    return my_stuff_admits_followed_sport(**kwargs)


class TestTheTournamentGridReachesTheFollower:
    """The five cards Alex could not see, and now can."""

    @pytest.mark.parametrize(
        "prop",
        ["Winner", "Top 5 Finish", "Top 10 Finish", "Top 20 Finish", "Make the Cut"],
    )
    def test_every_prop_in_this_weeks_grid_is_admitted(self, prop):
        """The grid is one tournament's five questions, not one headline.

        Parametrised over the prop NAMES on purpose even though the predicate
        never reads a name: the defect Alex reported was "only one golf card",
        and the fix is worthless if it admits the Winner and drops the other
        four. If the predicate ever grows a name-shaped condition, four of these
        five go red and say which.
        """
        assert admits(), f"the tournament's {prop} market is still unreachable"

    def test_tennis_is_admitted_on_the_same_footing(self):
        """Alex follows tennis too, and tennis has no teams either."""
        assert admits(category="tennis")

    def test_a_followed_sport_needs_no_team_and_no_name_match(self):
        """The point of the whole change.

        Nothing in the signature can carry a team or an outcome name, which is
        the assertion: admission is decided without either. A refactor that
        reintroduces a team requirement cannot do it through this function.
        """
        params = set(inspect.signature(my_stuff_admits_followed_sport).parameters)
        assert not {"team_ids", "team_names", "outcomes"} & params
        assert admits()


class TestFollowedMeansFollowed:
    def test_a_sport_you_do_not_follow_is_not_admitted(self):
        """Cycling and F1 are item 1's defect; this must not re-open it."""
        assert not admits(category="cycling")
        assert not admits(category="motorsports")

    def test_no_follows_admits_nothing(self):
        assert not admits(followed_categories=set())

    def test_an_uncategorised_market_is_not_a_followed_sport(self):
        """Absence of a label is not evidence of golf.

        `_score_futures` falls back to the sport FK's category, so a market
        reaching here with neither is genuinely unlabelled — and the safe
        reading of unlabelled on a page that promises only your sports is "not
        yours".
        """
        assert not admits(category=None)
        assert not admits(category="")

    def test_case_and_whitespace_are_not_a_different_sport(self):
        assert admits(category="Golf")
        assert admits(category="  GOLF  ")

    def test_the_follow_set_is_the_callers_narrowed_one(self):
        """Baseball is excluded by SUBTRACTION at the call site, not here.

        This function would happily admit baseball if handed it — which is why
        `TestTheRouteSubtractsTheTeamSports` below pins the subtraction on the
        line that does it. Recording the division of labour so a future reader
        does not "fix" it by adding a team-sport denylist in two places.
        """
        assert admits(category="baseball", followed_categories={"baseball"})


class TestTheWindowIsThisWeekNotThisDecade:
    def test_the_2027_major_market_is_not_this_week(self):
        """Verbatim the market that WAS on his page, dated as production has it.

        "Golfers to win a PGA Tour major in 2027" resolves fourteen months out.
        It is the one golf card Alex saw and the least useful golf card the site
        holds; admitting it under this rule would mean the fix changed the page
        by adding four props and keeping the noise.
        """
        assert not admits(resolution_date=datetime(2027, 11, 1, tzinfo=timezone.utc))

    def test_a_market_that_already_resolved_is_not_upcoming(self):
        assert not admits(resolution_date=NOW - timedelta(days=1))

    def test_an_undated_market_is_not_admitted(self):
        """A missing date is not evidence of imminence.

        The opposite reading — "no date, so show it" — is how a page fills with
        undated evergreen markets, which is the shape of the defect being fixed.
        """
        assert not admits(resolution_date=None)

    def test_the_window_holds_next_weeks_tournament_too(self):
        """Tour golf is weekly; a 7-day window shows an empty page on Monday.

        Sunday's final round resolves this week's markets, and the next
        tournament's grid opens days later. A window that ended before it opened
        would leave the section empty for part of every week.
        """
        assert MY_STUFF_FOLLOW_WINDOW_DAYS >= 10
        assert admits(resolution_date=NOW + timedelta(days=9))

    def test_the_boundaries_are_inclusive_and_do_not_run_long(self):
        edge = NOW + timedelta(days=MY_STUFF_FOLLOW_WINDOW_DAYS)
        assert admits(resolution_date=edge)
        assert admits(resolution_date=NOW)
        assert not admits(resolution_date=edge + timedelta(seconds=1))

    def test_the_window_is_measured_from_now_not_from_the_clock(self):
        """Gotcha #44: offset from the anchor, never branch on the real clock."""
        later = NOW + timedelta(days=200)
        assert not admits(now=later)
        assert admits(now=later, resolution_date=later + timedelta(days=2))


class TestAwardsAreNotSport:
    def test_the_pga_film_awards_do_not_ride_a_golf_follow(self):
        """The Producers Guild of America is also "PGA".

        Kalshi files "PGA Award for Best Animated Theatrical Motion Picture?"
        under `llm_sport_category = "golf"`. It is tier 3, it resolves in
        January — inside any sane window — and it is the single most embarrassing
        card this change could have put on a golf fan's page.
        """
        assert not admits(market_tier=3)

    def test_the_other_tiers_are_untouched(self):
        for tier in (1, 2, 4, 5, None):
            assert admits(market_tier=tier), f"tier {tier} was dropped"


class TestTheRouteSubtractsTheTeamSports:
    """The predicate stays green if `_score_futures` stops narrowing its input.

    Handed the raw follow set, this function admits every followed sport on a
    bare follow — which for baseball would mean every MLB market on the site,
    not the Red Sox. The subtraction is the only thing standing between the two
    behaviours, so it is pinned on the line that performs it.
    """

    @staticmethod
    def _feed_source() -> str:
        from app.routes import feed

        return inspect.getsource(feed)

    def test_the_follow_set_is_narrowed_to_sports_with_no_teams(self):
        src = self._feed_source()
        assert (
            "followed_sport_categories(ctx.sport_affinities)\n"
            "            - MY_STUFF_ALLOWED_CATEGORIES"
        ) in src, (
            "My Stuff's futures half no longer subtracts the team sports from "
            "the follow list — following the NBA now puts every NBA market on "
            "the page instead of your team's"
        )

    def test_the_narrowing_is_scoped_to_my_stuff(self):
        src = self._feed_source()
        assert (
            "    _my_stuff_follow_categories: set[str] = set()\n"
            "    if my_teams_only:"
        ) in src, (
            "the follow-admission set is no longer gated on my_teams_only; "
            "Discover and the category pages must not be filtered by it"
        )

    def test_the_predicate_is_actually_consulted(self):
        """UX-P176's lesson: a correct function nobody calls."""
        src = self._feed_source()
        assert "_followed_sport_market = my_stuff_admits_followed_sport(" in src
        assert "and not _followed_sport_market" in src, (
            "the team-match gate no longer exempts a followed-sport market — "
            "the admission is computed and then thrown away"
        )

    def test_the_category_filters_no_longer_run_first(self):
        """Golf never reached the match gate; it was `continue`d above it.

        Both category filters must sit under the exemption, or the fix is
        unreachable code: golf is in neither allowlist.
        """
        src = self._feed_source()
        assert (
            "                if not _followed_sport_market:\n"
            "                    # Skip Tier 3 sports"
        ) in src, (
            "the MY_STUFF_ALLOWED_* filters are no longer inside the "
            "followed-sport exemption; golf and tennis are dropped before the "
            "follow is ever consulted"
        )

    def test_the_resolution_date_is_normalised_before_comparison(self):
        """A naive/aware compare raises inside the scoring loop.

        Gotcha #42 means one such market would be caught and dropped rather than
        crashing the pass — so the failure mode is a silently empty section, not
        a 500. Pinned because that is the kind of bug nobody sees.
        """
        src = self._feed_source()
        assert "resolution_date=_utc(market.resolution_date)" in src


class TestAgainstAlexsOwnFollows:
    """End to end from the affinity payload production holds for his account."""

    ALEX_AFFINITIES = {
        "golf_pga": 1.0,
        "tennis_atp_us_open": 1.0,
        "baseball_mlb": 1.0,
        "football_nfl": 1.0,
        "motorsports_f1": 0.0,
        "cycling": 0.0,
        "tech": 1.0,
    }

    def _narrowed(self) -> set[str]:
        from app.routes.feed import MY_STUFF_ALLOWED_CATEGORIES

        return (
            followed_sport_categories(self.ALEX_AFFINITIES)
            - MY_STUFF_ALLOWED_CATEGORIES
        )

    def test_his_follows_narrow_to_exactly_golf_and_tennis(self):
        assert self._narrowed() == {"golf", "tennis"}

    def test_this_weeks_tournament_reaches_him(self):
        assert my_stuff_admits_followed_sport(
            category="golf",
            market_tier=1,
            resolution_date=NOW + timedelta(days=3),
            followed_categories=self._narrowed(),
            now=NOW,
        )

    def test_the_vuelta_and_the_grand_prix_still_do_not(self):
        for category in ("cycling", "motorsports"):
            assert not my_stuff_admits_followed_sport(
                category=category,
                market_tier=1,
                resolution_date=NOW + timedelta(days=3),
                followed_categories=self._narrowed(),
                now=NOW,
            ), f"{category} is back on a page that does not follow it"

    def test_a_random_mlb_market_still_needs_the_red_sox(self):
        """The narrowing proved against his real payload, not a fixture.

        He follows MLB at 1.0. If baseball survived the subtraction, every MLB
        market on the site would join his page — the exact inverse of item 1.
        """
        assert "baseball" not in self._narrowed()
        assert not my_stuff_admits_followed_sport(
            category="baseball",
            market_tier=1,
            resolution_date=NOW + timedelta(days=3),
            followed_categories=self._narrowed(),
            now=NOW,
        )
