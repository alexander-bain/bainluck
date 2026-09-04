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

The five bounds below are the whole of "this week's golf": followed, dated inside
the window, not an award, a FIELD rather than one match, and PRICED RECENTLY.
Each one has a measured defect behind it and each is pinned here. The last two
were both found by measuring the section this queue had already built — the first
three alone admit 4,039 markets, and 11 of the 23 that survive the fourth carry
prices between four and forty-three days old.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.personalization import (
    MY_STUFF_FOLLOW_WINDOW_DAYS,
    MY_STUFF_MAX_PRICE_AGE_HOURS,
    followed_sport_categories,
    my_stuff_admits_followed_sport,
)

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)

# The sports Alex follows that have no team to match on. This is what
# `_score_futures` hands the predicate: `followed_sport_categories(...) -
# MY_STUFF_ALLOWED_CATEGORIES`, i.e. golf and tennis and not baseball.
FOLLOWED = {"golf", "tennis"}


def admits(**overrides) -> bool:
    """The predicate with a this-week golf market as the default subject.

    Defaults are the Omega European Masters Winner as production holds it:
    tier 1, resolving Sunday, 193 golfers in the field.
    """
    kwargs = {
        "category": "golf",
        "market_tier": 1,
        "resolution_date": NOW + timedelta(days=3),
        "followed_categories": FOLLOWED,
        "now": NOW,
        "name": "Omega European Masters - Winner",
        "outcome_count": 193,
        "priced_at": NOW,
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

        Every name is verbatim from production (2026-09-04): the predicate DOES
        read the name now, so the five are checked one at a time. The defect
        Alex reported was "only one golf card", and the fix is worthless if it
        admits the Winner and drops the other four.
        """
        assert admits(
            name=f"Omega European Masters - {prop}"
        ), f"the tournament's {prop} market is still unreachable"

    @pytest.mark.parametrize(
        "name",
        [
            "2026 Women’s US Open Winner (Tennis)",
            "2026 Men’s US Open Winner (Tennis)",
            "US Open 2026: To Reach Quarterfinals (Men's Singles)",
            "US Open 2026: To Reach Semifinals (Women's Singles)",
            "US Open 2026: To Reach the Final (Men's Singles)",
            "US Open 2026: To Reach Round of 16 (Women's Singles)",
        ],
    )
    def test_tennis_is_admitted_on_the_same_footing(self, name):
        """Alex follows tennis too, and tennis has no teams either.

        The curly apostrophe in the two Winner names is production's own — a
        normalisation that assumed ASCII would drop both.
        """
        assert admits(category="tennis", name=name, outcome_count=44)

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
        # `priced_at` moves with the clock too — otherwise this asserts the
        # freshness bound by accident and stops testing the window at all.
        assert not admits(now=later, priced_at=later)
        assert admits(
            now=later, resolution_date=later + timedelta(days=2), priced_at=later
        )


class TestAFieldIsNotAMatch:
    """The bound that decides whether this change is an improvement at all.

    Measured on production 2026-09-04, the followed + windowed + not-an-award
    rules alone admit 4,039 markets for someone who follows golf and tennis, and
    3,802 of them are two-sided ITF satellite props. A page of those is worse
    than the page Alex complained about.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "Set 1 Winner: Stolarik vs Januchowski",
            "Set 2 Winner: Potapova vs Semenistaja",
            "Set 3 Winner: Jodar vs Bu",
            "M15 Wuning: Zijiang Yang vs Yue Xia",
        ],
    )
    def test_the_itf_set_props_that_would_have_flooded_the_page(self, name):
        assert not admits(category="tennis", name=name, outcome_count=2)

    @pytest.mark.parametrize(
        "name",
        [
            "US Open ATP: Daniil Medvedev vs Arthur Rinderknech",
            "US Open ATP: Ben Shelton vs Denis Shapovalov",
            "US Open ATP: Alexander Bublik vs Tommy Paul",
        ],
    )
    def test_a_match_with_many_outcomes_is_still_one_match(self, name):
        """Why the count alone cannot be the rule.

        These are per-match correct-score markets: 14 to 18 outcomes each, every
        one of them about a single match between two named players. A pure
        outcome-count bound admits all 208 of them. Both halves are needed, and
        this is the half that is easy to drop as redundant.
        """
        assert not admits(category="tennis", name=name, outcome_count=18)

    def test_a_bout_belongs_with_the_games_not_the_fields(self):
        """ux/1070 item 2's ruling, applied to the other half of the page.

        Two participants, two numbers and a date is the GAME archetype. It has a
        home on My Stuff — Live Now and Upcoming — and it is not this section.
        """
        assert not admits(category="mma", name="Fight Night: Hooker vs Parnasse")

    @pytest.mark.parametrize("form", ["vs", "vs.", "v.", "def.", "beats"])
    def test_every_way_of_naming_two_participants(self, form):
        assert not admits(name=f"Some Event: Alpha {form} Bravo")

    def test_the_empty_shells_are_dropped(self):
        """Six of the eighteen in-window golf markets have NO outcomes.

        "DP World Tour: European Masters Winner" is the same tournament as
        "Omega European Masters - Winner" from a second source, and it carries
        zero outcomes — it renders as a card with a title and nothing under it
        (the empty-card class, L2215). The grid Alex wants is the populated one.
        """
        assert not admits(
            name="DP World Tour: European Masters Winner", outcome_count=0
        )
        assert not admits(
            name="DP World Tour: European Masters Top 10", outcome_count=0
        )

    def test_two_entrants_is_a_match_however_it_is_named(self):
        """The count catches what the name misses.

        A two-outcome market that never says "vs" is still not a field, and the
        section's promise is "who, out of everyone" — a question with two
        possible answers is a different question.
        """
        assert not admits(outcome_count=2)
        assert not admits(outcome_count=1)

    def test_a_small_field_is_still_a_field(self):
        """Three is the floor, not a preference for big draws.

        "DP World Tour: European Masters First Round Leader" carries five, and a
        final-day leaderboard shortlist is exactly the kind of card that should
        be on the page on Sunday morning.
        """
        assert admits(name="European Masters First Round Leader", outcome_count=3)
        assert admits(name="European Masters First Round Leader", outcome_count=5)

    def test_an_unnamed_market_is_judged_on_its_field(self):
        """A missing name is not evidence of a matchup, and not evidence against.

        The name test can only ever exclude; with nothing to read it excludes
        nothing, and the outcome count still has to be satisfied.
        """
        assert admits(name=None)
        assert not admits(name=None, outcome_count=2)


class TestThePriceIsFromThisWeekToo:
    """The bound I missed on the first pass, found by measuring my own ship.

    The field bound got the section to 23 markets. Measured again for FRESHNESS,
    11 of those 23 were not current — on a page headed "what is on this week",
    during a live US Open. Every age below is production, 2026-09-04.
    """

    @pytest.mark.parametrize(
        "name,hours",
        [
            ("US Open 2026: To Reach Quarterfinals (Men's Singles)", 239.9),
            ("US Open 2026: To Reach the Final (Men's Singles)", 239.9),
            ("US Open 2026: To Reach Round of 16 (Women's Singles)", 239.9),
            ("US Open 2026: To Reach Semifinals (Women's Singles)", 237.8),
        ],
    )
    def test_a_ten_day_old_bracket_during_the_tournament(self, name, hours):
        """The worst of the eleven, because the answer has visibly changed.

        These fields were priced before the tournament reached this round, so
        they list players who have since been knocked out as live chances to
        reach it. Not merely stale — contradicted by the scoreboard on the same
        page.
        """
        assert not admits(
            category="tennis",
            name=name,
            outcome_count=44,
            priced_at=NOW - timedelta(hours=hours),
        )

    def test_the_forty_three_day_old_golf_prop(self):
        """"Scottie Scheffler: Next Tournament Win", 1023.3h, never moved."""
        assert not admits(
            name="Scottie Scheffler: Next Tournament Win",
            outcome_count=13,
            priced_at=NOW - timedelta(hours=1023.3),
        )

    def test_a_first_round_leader_market_in_the_third_round(self):
        """92.9h old, and the round it asks about finished days ago."""
        assert not admits(
            name="DP World Tour: European Masters First Round Leader",
            outcome_count=5,
            priced_at=NOW - timedelta(hours=92.9),
        )

    def test_the_live_tournament_grid_is_admitted(self):
        """The other side: DataGolf polls the Omega grid live, 0.0h."""
        assert admits(priced_at=NOW)

    def test_the_us_open_winner_fields_are_admitted(self):
        """5.3h and 5.7h — a real poll cadence, not a stale row."""
        for hours in (5.3, 5.7):
            assert admits(
                category="tennis",
                name="2026 Men’s US Open Winner (Tennis)",
                outcome_count=41,
                priced_at=NOW - timedelta(hours=hours),
            )

    def test_an_unpriced_market_is_not_a_fresh_one(self):
        """Absent evidence excludes, the same direction as every other bound."""
        assert not admits(priced_at=None)

    def test_the_cut_sits_in_the_measured_gap(self):
        """Not knife-edge, and this is the assertion that says why.

        The observed populations were 0.0–5.7h and 92.9h+. Nothing in between,
        so a late poll cannot flap a card in and out of the section. If someone
        tightens this below the real poll cadence, the live cards start
        disappearing intermittently — which is why the floor is asserted and not
        just the ceiling.
        """
        assert 6 < MY_STUFF_MAX_PRICE_AGE_HOURS < 92
        assert admits(priced_at=NOW - timedelta(hours=MY_STUFF_MAX_PRICE_AGE_HOURS))
        assert not admits(
            priced_at=NOW - timedelta(hours=MY_STUFF_MAX_PRICE_AGE_HOURS, seconds=1)
        )

    def test_a_future_timestamp_does_not_crash_or_admit_wrongly(self):
        """Clock skew between the dyno and a provider is not a fresh price.

        It is fresher than fresh, so it passes — deliberately. The alternative
        (rejecting it) would blank the section on a clock wobble, which is a
        worse failure than showing a price that is at worst seconds early.
        """
        assert admits(priced_at=NOW + timedelta(minutes=5))


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

    def test_the_field_arguments_are_actually_passed(self):
        """Both default to admitting nothing, so omitting them empties the page.

        A silent empty section is the failure this pins: the route would still
        compile, the predicate would still be correct, and the ship would be
        invisible.

        Anchored on the CALL rather than on the argument text. `name=market.name`
        appears twenty times in this module and `market_name=market.name`
        contains it as a substring, so the obvious pin is satisfied by lines
        that have nothing to do with this one (gotcha: a residue scan matching a
        substring of an unrelated call).
        """
        src = self._feed_source()
        start = src.find("_followed_sport_market = my_stuff_admits_followed_sport(")
        assert start != -1, "the predicate is not called at all"
        # The call's OWN closing paren: the one at its statement indentation.
        # `find(")")` lands inside `len(market.outcomes or [])` instead and cuts
        # the slice mid-argument, which is a test that fails on correct code.
        end = src.find("\n                )", start)
        assert end != -1, "the call's argument list is not where it was"
        call = src[start:end]
        assert "name=market.name," in call, (
            "the followed-sport admission no longer reads the market's name — "
            "every two-sided match prop in the sport is back on the page"
        )
        # Anchored on the line START, not on `priced_at=` as a bare substring:
        # `_unused_priced_at=` contains that, so the loose pin survives the kwarg
        # being renamed out of the call. Second instance of this collision in
        # this file — see the note above about `market_name=market.name`.
        assert "\n                    priced_at=_utc(market.updated_at)," in call, (
            "the followed-sport admission no longer reads the price age — the "
            "ten-day-old US Open bracket is back on a page headed 'this week'"
        )
        assert "outcome_count=len(market.outcomes or [])," in call, (
            "the followed-sport admission no longer reads the field size — the "
            "empty-shell cards are back and the section renders titles with "
            "nothing under them"
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
            name="Omega European Masters - Winner",
            outcome_count=193,
            priced_at=NOW,
        )

    def test_the_field_bound_defaults_to_admitting_nothing(self):
        """A caller that forgets to pass the field shows an empty section.

        Not a footgun — the direction of the default is the decision. Fail-open
        here means 3,802 ITF set props on his page; fail-closed means a section
        that is missing, which the page renders as absence rather than as noise.
        """
        assert not my_stuff_admits_followed_sport(
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
                name="Vuelta a España - Winner",
                outcome_count=176,
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
            name="AL Pennant Winner",
            outcome_count=15,
        )
