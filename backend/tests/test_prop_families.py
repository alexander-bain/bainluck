"""Tests for prop-family detection (app.utils.prop_families).

Covers: family_key normalisation (Next Team, award, threshold ladder,
non-family -> None), entity extraction, group_prop_families requiring
>= 2 entities, cross-source duplicate collapse (bug a), and settled-prop
labelling (bug b).
"""

from app.utils.prop_families import (
    family_key,
    extract_entity,
    group_prop_families,
    resolve_family_key,
)


# ---------------------------------------------------------------------------
# family_key normalisation
# ---------------------------------------------------------------------------


class TestFamilyKey:
    def test_next_team_family(self):
        assert family_key("LeBron James Next Team") == "next team"
        assert family_key("Kevin Durant Next Team") == "next team"
        # Both collapse to the SAME key regardless of the player.
        assert family_key("LeBron James Next Team") == family_key("Kevin Durant Next Team")

    def test_new_team_variant(self):
        assert family_key("Luka Doncic New Team") == "next team"

    def test_award_standalone_mvp(self):
        assert family_key("NBA MVP") == "mvp"
        assert family_key("NBA MVP 2026") == "mvp"

    def test_award_of_the_year(self):
        assert family_key("Rookie of the Year") == "rookie of the year"
        assert family_key("NBA Defensive Player of the Year") == "defensive player of the year"
        # League prefix stripped -> same key with or without "NBA".
        assert family_key("Defensive Player of the Year") == "defensive player of the year"

    def test_award_win_shape(self):
        # A per-candidate award market still resolves to the award family.
        assert family_key("Will Nikola Jokic win MVP?") == "mvp"
        assert family_key("Nikola Jokic to win Rookie of the Year") == "rookie of the year"

    def test_threshold_ladder_collapses_thresholds(self):
        a = family_key("Player X to score 30+ points")
        b = family_key("Player X to score 40+ points")
        assert a == "to score points"
        assert a == b

    def test_threshold_over_under(self):
        # Over/Under threshold ladder collapses the number.
        assert family_key("Jayson Tatum Over 27.5 points") == family_key(
            "Jayson Tatum Under 27.5 points"
        )

    def test_non_family_returns_none(self):
        assert family_key("Los Angeles Lakers") is None
        assert family_key("NBA Championship 2025-26") is None
        assert family_key("") is None
        assert family_key("Boston Celtics") is None


# ---------------------------------------------------------------------------
# extract_entity
# ---------------------------------------------------------------------------


class TestExtractEntity:
    def test_entity_from_next_team_title(self):
        assert extract_entity("LeBron James Next Team") == "LeBron James"

    def test_entity_from_to_win_title(self):
        assert extract_entity("Nikola Jokic to win MVP") == "Nikola Jokic"

    def test_entity_from_threshold_title(self):
        assert extract_entity("Jayson Tatum to score 30+ points") == "Jayson Tatum"

    def test_entity_falls_back_to_outcome_for_multi_candidate(self):
        # "NBA MVP" names no subject in the title -> use the outcome name.
        assert extract_entity("NBA MVP", "Shai Gilgeous-Alexander") == "Shai Gilgeous-Alexander"

    def test_entity_ignores_generic_outcome(self):
        assert extract_entity("NBA MVP", "Yes") == "NBA MVP"


# ---------------------------------------------------------------------------
# group_prop_families — requires >= 2 distinct entities
# ---------------------------------------------------------------------------


def _next_team_market(mid, player, source="kalshi", group_id=None, top_team="Lakers", prob=0.4):
    return {
        "market_id": mid,
        "name": f"{player} Next Team",
        "source": source,
        "group_id": group_id,
        "status": "open",
        "outcomes": [
            {"outcome_id": mid * 10 + 1, "name": top_team, "probability": prob},
            {"outcome_id": mid * 10 + 2, "name": "Warriors", "probability": 0.2},
        ],
    }


class TestGroupPropFamilies:
    def test_two_entities_form_a_family(self):
        markets = [
            _next_team_market(1, "LeBron James"),
            _next_team_market(2, "Kevin Durant"),
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        fam = families[0]
        assert fam["family_key"] == "next team"
        assert fam["label"] == "Next Team"
        assert fam["entity_count"] == 2
        entities = {r["entity"] for r in fam["rows"]}
        assert entities == {"LeBron James", "Kevin Durant"}

    def test_single_market_is_not_a_family(self):
        families = group_prop_families([_next_team_market(1, "LeBron James")])
        assert families == []

    def test_non_family_markets_are_ignored(self):
        markets = [
            {"market_id": 1, "name": "Los Angeles Lakers", "source": "kalshi",
             "group_id": None, "status": "open", "outcomes": []},
            {"market_id": 2, "name": "Boston Celtics", "source": "kalshi",
             "group_id": None, "status": "open", "outcomes": []},
        ]
        assert group_prop_families(markets) == []

    def test_award_race_one_row_per_candidate(self):
        markets = [
            {
                "market_id": 5,
                "name": "NBA MVP",
                "source": "polymarket",
                "group_id": "poly:mvp",
                "status": "open",
                "outcomes": [
                    {"outcome_id": 51, "name": "Nikola Jokic", "probability": 0.45},
                    {"outcome_id": 52, "name": "Shai Gilgeous-Alexander", "probability": 0.30},
                    {"outcome_id": 53, "name": "Luka Doncic", "probability": 0.10},
                ],
            }
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        assert families[0]["family_key"] == "mvp"
        assert families[0]["entity_count"] == 3


# ---------------------------------------------------------------------------
# Bug (a): cross-source duplicate collapse
# ---------------------------------------------------------------------------


class TestCrossSourceCollapse:
    def test_same_entity_across_sources_collapses_to_one_row(self):
        markets = [
            _next_team_market(1, "LeBron James", source="kalshi", prob=0.42),
            _next_team_market(2, "LeBron James", source="polymarket", group_id="poly:lbj", prob=0.38),
            _next_team_market(3, "Kevin Durant", source="kalshi", prob=0.5),
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        fam = families[0]
        # LeBron collapses into ONE row despite two sources.
        assert fam["entity_count"] == 2
        lebron = [r for r in fam["rows"] if r["entity"] == "LeBron James"]
        assert len(lebron) == 1
        assert set(lebron[0]["sources"]) == {"kalshi", "polymarket"}
        assert set(lebron[0]["cross_source"].keys()) == {"kalshi", "polymarket"}

    def test_two_sources_same_entity_alone_is_not_a_family(self):
        # Duplicate sources for ONE entity must not fake a 2-entity family.
        markets = [
            _next_team_market(1, "LeBron James", source="kalshi"),
            _next_team_market(2, "LeBron James", source="polymarket", group_id="poly:lbj"),
        ]
        assert group_prop_families(markets) == []


# ---------------------------------------------------------------------------
# Bug (b): settled props labelled settled, not live
# ---------------------------------------------------------------------------


class TestSettledLabelling:
    def test_settled_award_labels_winner_and_loser(self):
        markets = [
            {
                "market_id": 9,
                "name": "NBA MVP",
                "source": "kalshi",
                "group_id": "kalshi:mvp",
                "status": "resolved",
                "outcomes": [
                    {"outcome_id": 91, "name": "Nikola Jokic", "probability": 1.0, "is_winner": True},
                    {"outcome_id": 92, "name": "Joel Embiid", "probability": 0.0, "is_winner": False},
                ],
            }
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        rows = {r["entity"]: r for r in families[0]["rows"]}

        jokic = rows["Nikola Jokic"]
        assert jokic["settled"] is True
        assert jokic["status"] == "settled"
        assert jokic["result"] == "won"

        embiid = rows["Joel Embiid"]
        assert embiid["settled"] is True
        assert embiid["status"] == "settled"
        assert embiid["result"] == "lost"

    def test_winner_outcome_not_shown_as_live(self):
        # A graded is_winner outcome on an otherwise-open market is settled,
        # never a live 100% row.
        markets = [
            {
                "market_id": 10,
                "name": "Connor McDavid to win the Hart Trophy",
                "source": "kalshi",
                "group_id": None,
                "status": "open",
                "outcomes": [
                    {"outcome_id": 101, "name": "Yes", "probability": 1.0, "is_winner": True},
                    {"outcome_id": 102, "name": "No", "probability": 0.0},
                ],
            },
            {
                "market_id": 11,
                "name": "Nathan MacKinnon to win the Hart Trophy",
                "source": "kalshi",
                "group_id": None,
                "status": "open",
                "outcomes": [
                    {"outcome_id": 111, "name": "Yes", "probability": 0.0, "is_winner": False},
                    {"outcome_id": 112, "name": "No", "probability": 1.0},
                ],
            },
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        rows = {r["entity"]: r for r in families[0]["rows"]}
        mcdavid = rows["Connor McDavid"]
        assert mcdavid["settled"] is True
        assert mcdavid["status"] == "settled"
        assert mcdavid["result"] == "won"


# ---------------------------------------------------------------------------
# Optional cached-LLM family-key hint
# ---------------------------------------------------------------------------


class TestCachedLLMHint:
    def test_metadata_hint_overrides_pattern(self):
        market = {
            "market_id": 1,
            "name": "Some inscrutable title the regex misses",
            "market_metadata": {"prop_family": {"family_key": "surprise award"}},
        }
        assert resolve_family_key(market) == "surprise award"

    def test_absent_hint_falls_back_to_pattern(self):
        market = {"market_id": 1, "name": "LeBron James Next Team"}
        assert resolve_family_key(market) == "next team"

    def test_hint_lets_non_pattern_markets_group(self):
        markets = [
            {"market_id": 1, "name": "cryptic one", "source": "kalshi",
             "group_id": None, "status": "open",
             "market_metadata": {"prop_family": {"family_key": "special race"}},
             "outcomes": [{"outcome_id": 11, "name": "Alice", "probability": 0.6}]},
            {"market_id": 2, "name": "cryptic two", "source": "kalshi",
             "group_id": None, "status": "open",
             "market_metadata": {"prop_family": {"family_key": "special race"}},
             "outcomes": [{"outcome_id": 21, "name": "Bob", "probability": 0.4}]},
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        assert families[0]["family_key"] == "special race"
        assert families[0]["entity_count"] == 2


# ---------------------------------------------------------------------------
# #6622 — the entity is the SUBJECT, not the market title
#
# Every title below is a real production ``futures_markets.name``.  Before
# this guard, branch 1 title-cased the whole matched span: the venue's
# category prefix became part of the player's name ("Nba Free Agency:
# Mitchell Robinson"), the possessive survived and ``str.title()``
# upper-cased after the apostrophe ("Jaylen Brown'S"), and correct venue
# casing was destroyed ("LeBron" -> "Lebron", "CJ" -> "Cj", "III" -> "Iii").
# That string is the cross-source fold's key, so the fold missed: NOT ONE of
# the 163 next-team markets in production folded across venues.
# ---------------------------------------------------------------------------


class TestEntityIsTheSubject6622:
    def test_category_qualifier_is_not_part_of_the_name(self):
        assert extract_entity("NBA Free Agency: Mitchell Robinson Next Team") == "Mitchell Robinson"
        assert extract_entity("NBA: Jaylen Brown Next Team") == "Jaylen Brown"
        assert extract_entity("MLB: Mike Trout Next Team") == "Mike Trout"
        assert extract_entity("VALORANT Offseason: Chronicle Next Team") == "Chronicle"

    def test_a_sentence_before_a_colon_is_not_a_qualifier(self):
        # Negative control: the head is seven words, longer than a category
        # prefix, so it is left alone — the strip must not eat a clause.
        # Asserted casing-blind so this control passes on BOTH sides of the
        # change and isolates the strip alone.
        entity = extract_entity("Who will be the first to announce: LeBron James Next Team")
        assert entity != "LeBron James"
        assert "announce" in entity.lower()

    def test_possessive_is_dropped_both_spellings(self):
        assert extract_entity("Jaylen Brown's Next Team") == "Jaylen Brown"
        assert extract_entity("Austin Reaves' Next Team") == "Austin Reaves"
        assert extract_entity("Kirk Cousins's Next Team") == "Kirk Cousins"
        assert extract_entity("Bronny James' Next Team Before Oct 23, 2026") == "Bronny James"

    def test_a_name_that_merely_ends_in_s_is_untouched(self):
        # Negative control for the possessive strip: no apostrophe, no strip.
        assert extract_entity("Anfernee Simons Next Team") == "Anfernee Simons"

    def test_venue_casing_survives(self):
        assert extract_entity("LeBron James Next Team") == "LeBron James"
        assert extract_entity("CJ Abrams Next Team") == "CJ Abrams"
        assert extract_entity("J.J. McCarthy Next Team") == "J.J. McCarthy"
        assert extract_entity("NBA Free Agency: Robert Williams III Next Team") == "Robert Williams III"
        assert extract_entity("De'Aaron Fox's Next Team") == "De'Aaron Fox"

    def test_an_uncased_title_is_still_title_cased(self):
        # The source told us nothing, so we case it ourselves.
        assert extract_entity("kevin durant next team") == "Kevin Durant"
        assert extract_entity("KEVIN DURANT NEXT TEAM") == "Kevin Durant"

    def test_family_key_does_not_move(self):
        # Control: this change is about the entity, never the family.
        for title in (
            "NBA Free Agency: Mitchell Robinson Next Team",
            "Jaylen Brown's Next Team",
            "CJ Abrams Next Team",
            "kevin durant next team",
        ):
            assert family_key(title) == "next team"

    def test_the_real_jaylen_brown_pair_folds_to_one_settled_row(self):
        # Production specimens: Kalshi 15728530 and Polymarket 54697891, one
        # question, both graded won on Philadelphia, rendered as two rows at
        # 99% and 100% on the Celtics page.
        markets = [
            {
                "market_id": 15728530, "name": "Jaylen Brown's Next Team",
                "source": "kalshi", "group_id": None, "status": "resolved",
                "outcomes": [
                    {"outcome_id": 1, "name": "Philadelphia", "probability": 0.99, "is_winner": True},
                ],
            },
            {
                "market_id": 54697891, "name": "NBA: Jaylen Brown Next Team",
                "source": "polymarket", "group_id": "poly:jb", "status": "resolved",
                "outcomes": [
                    {"outcome_id": 2, "name": "Philadelphia 76ers", "probability": 1.0, "is_winner": True},
                ],
            },
            {
                "market_id": 55686465, "name": "Nikola Jokic's Next Team",
                "source": "kalshi", "group_id": None, "status": "open",
                "outcomes": [
                    {"outcome_id": 3, "name": "Denver", "probability": 0.8},
                ],
            },
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        rows = families[0]["rows"]
        brown = [r for r in rows if r["entity"] == "Jaylen Brown"]
        assert len(brown) == 1, [r["entity"] for r in rows]
        assert set(brown[0]["sources"]) == {"kalshi", "polymarket"}
        assert brown[0]["settled"] is True and brown[0]["result"] == "won"
        # A settled winner does not print 99%: among rows that agree it is
        # won, the coherent field wins, not whichever source came first.
        assert brown[0]["probability"] == 1.0
        assert families[0]["entity_count"] == 2
