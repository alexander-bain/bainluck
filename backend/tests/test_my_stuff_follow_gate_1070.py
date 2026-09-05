"""ux/1070 item 1 — My Stuff shows what you follow, and nothing global.

═══ THE DEFECT ═══

Alex shopped My Stuff signed in on 2026-09-04 at 7:00am PT. Live Now held ONE
card: the Vuelta a España. Upcoming (23) mixed his Red Sox, Patriots and
Revolution with six UFC cards, a Formula 1 Grand Prix and a DP World Tour
tournament. He follows Boston teams, PGA golf and tennis. He does not follow
Formula 1 and he does not follow cycling — and there is no onboarding affinity
for either, so he could not have followed them if he wanted to.

Nothing leaked through a mapping. `GET /api/feed?my_teams_only=true` filters its
events half to the viewer's teams (`_score_events`) and its futures half to the
same (`_score_futures`), and then appends two more tiers to the SAME item list:

    _score_golf_tournaments(...)   -> feed_items.extend(tournament_items)
    _score_event_concepts(...)     -> feed_items.extend(concept_items)

Neither tier took `my_teams_only`, neither read `ctx`, and neither asked what
the viewer follows. Both are global by construction. Measured against
production the same morning, `event:cycling:vuelta-2026` and every
`event:ufc:*` / F1 concept on the site were eligible for every My Stuff page on
the site, for every signed-in viewer, regardless of a single follow.

═══ WHY THE DEFAULT FLIPS ═══

`concept_filter_for_tags` and `concept_filter_for_category` both treat silence
as "no constraint" — right, because a `sport:` tag and a `/categories/` slug
NARROW a tier that is legitimately global elsewhere. A follow list is not a
narrowing of My Stuff; it is the whole of My Stuff. So its sibling
`concept_filter_for_follows` treats silence as NOTHING: no followed sport, no
concept tier. Empty is the correct My Stuff, and the page already has an honest
empty state for it ("This page follows the teams you have saved").
"""

from __future__ import annotations

import inspect

import pytest

from app.utils.event_concept_population import (
    CONCEPT_SOURCES,
    concept_filter_for_follows,
    concept_sources_named,
)
from app.utils.personalization import (
    HIGH_AFFINITY_THRESHOLD,
    followed_sport_categories,
)

# The affinity payload production actually holds for the account Alex shopped
# (user 447, measured 2026-09-04 via /api/admin/db-query). Trimmed to the keys
# that matter here — every value is verbatim.
ALEX_AFFINITIES = {
    "cfb": 1.0,
    "tech": 1.0,
    "crypto": 0.0,
    "culture": 0.0,
    "weather": 0.0,
    "golf_liv": 1.0,
    "golf_pga": 1.0,
    "golf_dp_world": 1.0,
    "politics": 0.0,
    "economics": 1.0,
    "geopolitics": 1.0,
    "baseball_mlb": 0.3,
    "boxing_boxing": 0.3,
    "icehockey_nhl": 0.0,
    "basketball_nba": 0.3,
    "soccer_usa_mls": 0.0,
    "mma_mixed_martial_arts": 1.0,
    "americanfootball_nfl": 1.0,
    "tennis_atp_us_open": 0.0,
}


class TestWhatTheViewerFollows:
    def test_alex_follows_golf_mma_and_football_not_cycling_or_motorsports(self):
        followed = followed_sport_categories(ALEX_AFFINITIES)
        assert "golf" in followed
        assert "mma" in followed
        assert "football" in followed
        # The two that put a card on his page this morning:
        assert "cycling" not in followed
        assert "motorsports" not in followed

    def test_a_sometimes_is_not_a_follow(self):
        """0.3 is onboarding's "sometimes" and 0.1 its "if wild"."""
        followed = followed_sport_categories(ALEX_AFFINITIES)
        assert "baseball" not in followed  # baseball_mlb = 0.3
        assert "boxing" not in followed  # boxing_boxing = 0.3
        assert "basketball" not in followed  # basketball_nba = 0.3
        assert "hockey" not in followed  # icehockey_nhl = 0.0

    def test_non_sport_interests_are_not_sports(self):
        """`tech`/`economics`/`geopolitics` are Discover interests at 1.0 here."""
        followed = followed_sport_categories(ALEX_AFFINITIES)
        assert followed == {"golf", "mma", "football"}

    def test_no_affinities_follows_nothing(self):
        assert followed_sport_categories(None) == set()
        assert followed_sport_categories({}) == set()

    def test_the_cut_is_the_modules_own_positive_signal(self):
        just_under = {"mma_mixed_martial_arts": HIGH_AFFINITY_THRESHOLD - 0.01}
        exactly_at = {"mma_mixed_martial_arts": HIGH_AFFINITY_THRESHOLD}
        assert followed_sport_categories(just_under) == set()
        assert followed_sport_categories(exactly_at) == {"mma"}

    def test_a_junk_value_is_not_a_follow(self):
        assert followed_sport_categories({"mma_mixed_martial_arts": None}) == set()
        assert followed_sport_categories({"mma_mixed_martial_arts": "yes"}) == set()


class TestTheConceptTierIsClosedByDefaultOnMyStuff:
    def test_no_follows_means_no_concept_tier(self):
        skip, sport_filter = concept_filter_for_follows(set())
        assert skip is True
        assert sport_filter is None
        assert concept_filter_for_follows(None) == (True, None)

    def test_following_mma_admits_ufc_and_only_ufc(self):
        skip, sport_filter = concept_filter_for_follows({"mma"})
        assert skip is False
        assert concept_sources_named(sport_filter) == {"ufc"}

    def test_alexs_follows_admit_ufc_and_nothing_else(self):
        """The measured payload, end to end: UFC in, F1 and the Vuelta out."""
        skip, sport_filter = concept_filter_for_follows(
            followed_sport_categories(ALEX_AFFINITIES)
        )
        assert skip is False
        named = concept_sources_named(sport_filter)
        assert named == {"ufc"}
        assert "f1" not in named
        assert "cycling" not in named

    def test_following_only_sports_with_no_concept_source_skips_the_tier(self):
        """Golf and tennis are followed, and neither registers a concept source.

        Skipped, not built-and-discarded — the same discipline
        `concept_filter_for_category` applies to an economics page.
        """
        assert concept_filter_for_follows({"golf", "tennis", "baseball"}) == (
            True,
            None,
        )

    def test_it_is_derived_from_the_registry_not_from_a_list(self):
        """Every registered source's own category admits exactly that source.

        A fourth source registered tomorrow is reachable by its category with
        no edit here — which is the property `event_concept_population` exists
        to hold.
        """
        for source in CONCEPT_SOURCES:
            skip, sport_filter = concept_filter_for_follows({source.category})
            assert skip is False, source.label
            assert concept_sources_named(sport_filter) == {source.label}

    def test_case_and_whitespace_are_not_a_different_sport(self):
        skip, sport_filter = concept_filter_for_follows({" MMA "})
        assert skip is False
        assert concept_sources_named(sport_filter) == {"ufc"}


class TestTheRouteActuallyAppliesIt:
    """The pure functions above stay green if `get_feed` stops calling them.

    UX-P176's lesson, and this queue is a second instance of it: the tag filter
    was a perfectly correct function that the golf and concept tiers on My Stuff
    never consulted. Narrow NAMED pins on the three lines that do the work.
    """

    @staticmethod
    def _feed_source() -> str:
        from app.routes import feed

        return inspect.getsource(feed)

    def test_the_route_derives_the_viewers_follows(self):
        src = self._feed_source()
        assert "followed_sport_categories(ctx.sport_affinities)" in src, (
            "My Stuff no longer derives the viewer's followed sports — the "
            "concept and golf tiers are back to being global on a page whose "
            "contract is 'only what you follow'"
        )

    def test_the_golf_tier_is_gated_on_a_golf_follow(self):
        src = self._feed_source()
        assert 'if my_teams_only and "golf" not in _my_stuff_follows:' in src, (
            "the golf tier no longer asks whether the viewer follows golf; a "
            "DP World Tour card can return to a My Stuff page that follows none"
        )

    def test_the_concept_tier_is_gated_on_the_follow_list(self):
        src = self._feed_source()
        assert "concept_filter_for_follows(" in src, (
            "the concept tier no longer consults the follow list — the Vuelta "
            "and the Spanish Grand Prix are eligible for every My Stuff page"
        )
        assert "_follow_skip, _follow_filter = concept_filter_for_follows(" in src
        assert "if _follow_skip:" in src

    def test_the_follow_filter_reaches_the_builder(self):
        """The half UX-P177 was missing: gated AND filtered, not gated only."""
        src = self._feed_source()
        assert "_narrow_concept_filters(\n                    _concept_sport_filter, _follow_filter\n                )" in src, (
            "the follow-derived filter is computed and then not intersected "
            "into the filter the builder is given"
        )

    def test_the_gate_is_scoped_to_my_stuff(self):
        """Discover, /sports and every category page keep the global tier.

        Both gates are inside `if my_teams_only`; if that scoping is ever
        dropped the Vuelta disappears from the one surface it belongs on.
        """
        src = self._feed_source()
        assert "_my_stuff_follows: set[str] = set()\n        if my_teams_only:" in src


@pytest.mark.parametrize(
    "category",
    [s.category for s in CONCEPT_SOURCES],
)
def test_every_source_category_is_a_real_llm_category(category):
    """The comparison in `concept_filter_for_follows` is category-to-category.

    It only works because a source's `category` is the same vocabulary
    `followed_sport_categories` emits. Both sides are pinned here so a rename on
    either side fails loudly instead of quietly following nothing.
    """
    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

    assert category in set(SPORT_PREFIX_TO_LLM_CATEGORY.values()) | {"cycling"}
