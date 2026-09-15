"""#6416 — Discover dealt one question as fourteen cards.

Kalshi runs "alternative data" series as one market shell repeated per brand:
"Costco Credit Card Spend in September", "Sephora Credit Card Spend in
September", "Shein Credit Card Spend in September", and so on. `family_key`
defaulted to the normalized market NAME, and `_normalized_text` already folds
the month to `<month>`, so the brand was the only token separating them — seven
families of one, and `diversify_quality_families(exact_family_cap=1)` never
fired.

Measured on production 2026-09-15 through the web client's OWN query
(`/api/feed?limit=20&offset=N&event_pct=0.15`, the pagination the page issues,
`has_more=True` throughout): 14 such cards at positions 37, 38, 60, 74, 75, 93,
95, 96, 101, 102, 105, 107, 115, 118 — adjacent at 37/38, 74/75, 95/96 and
101/102. 57 markets in the same three shells were `status='open'` at the time,
so which brands surface is only a function of that hour's scores.

Every name below is a real production row.
"""

import pytest

from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
)

# Real open rows, 2026-09-15. The seven credit-card and five app-download names
# are exactly the ones the paginated feed served, in served order.
CREDIT_CARD_SPEND = [
    "Costco Credit Card Spend in September",
    "Southwest Airlines Credit Card Spend in September",
    "Sephora Credit Card Spend in September",
    "Abercrombie & Fitch Credit Card Spend in September",
    "Shein Credit Card Spend in September",
    "Ulta Credit Card Spend in September",
    "Lowe's Credit Card Spend in September",
    # "Monthly" variant and a trailing year — both real, both must still fold.
    "BP Monthly Credit Card Spend in September",
    "Ro Monthly Credit Card Spend in September 2026",
]
APP_DOWNLOADS = [
    "FanDuel App Downloads in September",
    "Instacart App Downloads in September",
    "DraftKings App Downloads in September",
    "Grubhub App Downloads in September",
    "Paramount+ App Downloads in September",
    "Claude App Downloads in September",
]
AI_ADOPTION = [
    "Manufacturing AI adoption in September",
    "Hospitality AI adoption in September",
    "Finance AI adoption in September",
]

TEMPLATES = {
    "altdata:credit card spend in <month>": CREDIT_CARD_SPEND,
    "altdata:app downloads in <month>": APP_DOWNLOADS,
    "altdata:ai adoption in <month>": AI_ADOPTION,
}

# The threshold outcomes these markets really carry. They are what makes
# `is_ladder_or_bucket` True, which is the whole reason the fix has to be
# applied after the ladder branch.
THRESHOLD_OUTCOMES = ["Above 67", "Above 58", "Above 49", "Above 40", "Below 40"]


def _classify(name):
    return classify_market_quality(
        name, sport_category="economics", outcome_names=THRESHOLD_OUTCOMES
    )


class TestAltDataTemplatesShareOneFamily:
    @pytest.mark.parametrize(
        "expected_key,names",
        [(k, v) for k, v in TEMPLATES.items()],
        ids=list(TEMPLATES),
    )
    def test_every_brand_in_a_template_shares_one_family_key(self, expected_key, names):
        keys = {_classify(n).family_key for n in names}
        assert keys == {expected_key}, (
            f"{len(names)} brands collapsed to {len(keys)} families, not 1: {keys}"
        )

    def test_the_three_templates_stay_three_families(self):
        """Not one bucket: credit-card spend and app downloads are different
        questions about different things, and folding them together would hide
        a genuinely distinct card rather than a repeat."""
        keys = {
            _classify(n).family_key for names in TEMPLATES.values() for n in names
        }
        assert keys == set(TEMPLATES)

    def test_fixture_is_not_vacuous(self):
        """A single brand per template would make every assertion above pass
        for the wrong reason."""
        for key, names in TEMPLATES.items():
            assert len(names) >= 3, key
            assert len({n.split()[0] for n in names}) >= 3, key


class TestFoldSurvivesTheLadderRewrite:
    """The ordering is the load-bearing part of the fix.

    Every one of these markets carries numeric threshold outcomes, so
    `is_ladder_or_bucket` is True and the `if ladder_or_bucket:` branch
    reassigns `family_key` from `normalized` — which still carries the brand.
    An assignment placed BEFORE that branch is silently inert: these tests go
    red if anyone moves it back.
    """

    @pytest.mark.parametrize(
        "name", [n for names in TEMPLATES.values() for n in names]
    )
    def test_these_markets_really_are_ladders(self, name):
        assert _classify(name).is_ladder_or_bucket is True, (
            "if this is ever False the ordering hazard is gone and the comment "
            "in feed_market_quality.py should be revisited"
        )

    def test_ladder_rewrite_alone_would_not_have_folded_them(self):
        """Proves the ladder branch is not already doing this job — the numeric
        rewrite only touches numbers, and the brand is not a number."""
        import re

        from app.utils.feed_market_quality import _normalized_text

        ladder_keys = set()
        for name in CREDIT_CARD_SPEND:
            normalized = _normalized_text(name)
            key = re.sub(
                r"<num>(?:\s*(?:to|and|-)\s*<num>)+", "<range>", normalized
            )
            ladder_keys.add(re.sub(r"<num>", "<num>", key))
        assert len(ladder_keys) == len(CREDIT_CARD_SPEND), (
            "the ladder rewrite already folds these, so the fix is redundant"
        )


class TestUnrelatedMarketsKeepTheirOwnFamily:
    """Scope control. A regex for these three phrases followed by a month
    matched exactly 57 of 37,092 open futures markets — the ones above. These
    are the neighbours it must keep its hands off."""

    CONTROLS = [
        "Which party will win the U.S. House?",
        "Recession in 2027?",
        "Price of Dozen Eggs in September?",
        "Trump's approval rating on Sep 18, 2026?",
        "Will General Mills (GIS) beat quarterly earnings?",
        "Mississippi cotton production in 2027",
        "Poland rate decision in October",
        "#1 Free App in the US Apple App Store on September 18?",
        "Netflix (NFLX) closes week of Sep 14?",
    ]

    @pytest.mark.parametrize("name", CONTROLS)
    def test_control_market_is_not_given_an_altdata_family(self, name):
        assert not _classify(name).family_key.startswith("altdata:")

    def test_controls_stay_mutually_distinct(self):
        keys = {_classify(n).family_key for n in self.CONTROLS}
        assert len(keys) == len(self.CONTROLS)


class TestCapThinsTheServedFeed:
    """The end-to-end claim: the reader stops getting the wall."""

    @staticmethod
    def _feed_items(names_with_scores):
        items = []
        for name, score in names_with_scores:
            quality = _classify(name)
            items.append(
                {
                    "_name": name,
                    "score": score,
                    "_rank_score": score,
                    "_quality_family_key": quality.family_key,
                    "_quality_story_key": quality.story_key,
                }
            )
        return items

    # The 14 cards the paginated feed actually served, with their served
    # positions turned into descending scores.
    SERVED = [
        ("FanDuel App Downloads in September", 78),
        ("Instacart App Downloads in September", 77),
        ("DraftKings App Downloads in September", 68),
        ("Grubhub App Downloads in September", 63),
        ("Paramount+ App Downloads in September", 63),
        ("Costco Credit Card Spend in September", 57),
        ("Southwest Airlines Credit Card Spend in September", 56),
        ("Sephora Credit Card Spend in September", 56),
        ("Abercrombie & Fitch Credit Card Spend in September", 55),
        ("Shein Credit Card Spend in September", 55),
        ("Ulta Credit Card Spend in September", 54),
        ("Lowe's Credit Card Spend in September", 54),
        ("Manufacturing AI adoption in September", 53),
        ("Hospitality AI adoption in September", 52),
    ]

    def test_fourteen_cards_become_three(self):
        kept = diversify_quality_families(
            self._feed_items(self.SERVED), exact_family_cap=1, story_family_cap=5
        )
        assert len(kept) == 3, [i["_name"] for i in kept]
        assert {i["_quality_family_key"] for i in kept} == set(TEMPLATES)

    def test_the_survivor_is_the_highest_scoring_brand_not_an_arbitrary_one(self):
        """`diversify_quality_families` sorts by `_rank_score` descending and
        keeps the first per family, so the topic stays on the feed at its best
        score — the repetition is what goes, not the subject."""
        kept = diversify_quality_families(
            self._feed_items(self.SERVED), exact_family_cap=1, story_family_cap=5
        )
        assert {i["_name"] for i in kept} == {
            "FanDuel App Downloads in September",
            "Costco Credit Card Spend in September",
            "Manufacturing AI adoption in September",
        }

    def test_unrelated_cards_in_the_same_feed_are_untouched(self):
        """The cap must thin the flood without taking any bystander with it."""
        bystanders = [(n, 70) for n in TestUnrelatedMarketsKeepTheirOwnFamily.CONTROLS]
        kept = diversify_quality_families(
            self._feed_items(self.SERVED + bystanders),
            exact_family_cap=1,
            story_family_cap=5,
        )
        kept_names = {i["_name"] for i in kept}
        for name, _ in bystanders:
            assert name in kept_names, name
