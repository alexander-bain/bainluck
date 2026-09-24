"""Tests for prop-family detection (app.utils.prop_families).

Covers: family_key normalisation (Next Team, award, threshold ladder,
non-family -> None), entity extraction, group_prop_families requiring
>= 2 entities, cross-source duplicate collapse (bug a), and settled-prop
labelling (bug b).
"""

import json
from pathlib import Path

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


# ---------------------------------------------------------------------------
# #6630 — the venue writes the league as a PHRASE, and a family key is
# sport-scoped
# ---------------------------------------------------------------------------


def _award_market(mid, name, source, candidates, sport="basketball", status="open"):
    return {
        "market_id": mid,
        "name": name,
        "source": source,
        "group_id": None,
        "status": status,
        "sport": sport,
        "outcomes": [
            {"outcome_id": mid * 100 + i, "name": who, "probability": prob}
            for i, (who, prob) in enumerate(candidates)
        ],
    }


class TestLeaguePhrasePrefix6630:
    """Kalshi writes "Pro Basketball", not "NBA" — two tokens, so the
    single-token noise set could never pop it and the award split in two."""

    def test_the_celtics_sixth_man_pair_is_one_family(self):
        # The reader-visible defect: production markets 409 ("Sixth Man of
        # the Year Winner") and 58015765 ("Pro Basketball Sixth Man of the
        # Year Winner"), both Kalshi, both basketball, stacked as two cards
        # for one award on the Celtics page.
        assert (
            family_key("Pro Basketball Sixth Man of the Year Winner")
            == family_key("Sixth Man of the Year Winner")
            == "sixth man of the year"
        )

    def test_every_league_phrase_pairs_with_its_bare_award(self):
        # The guard for the CLASS, not for the four titles that were live:
        # one pair per league phrase in the venue's vocabulary, so a new
        # sport's awards cannot re-open this.
        for phrase in ("Pro Basketball", "Pro Football", "Pro Baseball", "Pro Hockey"):
            for award in (
                "Rookie of the Year",
                "Coach of the Year",
                "Defensive Player of the Year",
                "Sixth Man of the Year",
            ):
                assert family_key(f"{phrase} {award}") == family_key(award), (
                    f"{phrase} {award}"
                )

    def test_the_phrase_is_noise_only_at_the_front(self):
        # Negative control. "Pro Patria" is a real Italian CLUB with 8 live
        # rows, and a name can contain a league word — neither is a prefix,
        # so neither is stripped.
        assert family_key("Pro Patria Player of the Year") == (
            "pro patria player of the year"
        )
        assert family_key("PLL: 2026 Dave Pietramala Defensive Player of the Year") == (
            "dave pietramala defensive player of the year"
        )

    def test_the_womens_award_keeps_its_own_family(self):
        # 🔴 The control that matters most. Both the men's and women's
        # markets carry llm_sport_category='basketball', so the sport scope
        # CANNOT separate them — only the leading-anchored strip does, by
        # stopping at the "s" that the apostrophe leaves behind. If this ever
        # goes green-by-merging, the WNBA and NBA races share one card.
        mens = family_key("Pro Basketball Defensive Player of the Year Winner")
        womens = family_key("Women's Pro Basketball Defensive Player of the Year Winner")
        assert mens == "defensive player of the year"
        assert womens != mens

    def test_the_spelled_out_award_is_family_shaped(self):
        # Production: "MLS: 2026 Most Valuable Player", "WBC: Most Valuable
        # Player" and "PLL: 2026 Jim Brown Most Valuable Player" were not
        # family-shaped at all, so their candidates never grouped.
        assert family_key("Most Valuable Player") == "mvp"
        assert family_key("MLS: 2026 Most Valuable Player") == "mvp"
        assert family_key("WBC: Most Valuable Player") == "mvp"
        assert family_key("PLL: 2026 Jim Brown Most Valuable Player") == "mvp"
        assert family_key("Pro Football Most Valuable Player") == "mvp"

    def test_the_non_award_pro_namespace_is_untouched(self):
        # The 500+ "Pro X" rows that are NOT awards. _strip_noise_prefix is
        # reached only from the "of the year" arm, so none of these can move.
        for title in (
            "Pro Baseball: 105+ MPH Pitch",
            "Pro Baseball #1 Overall Pick",
            "Pro Baseball: 30/30 Season",
            "Pro Football: 2026-27 Regular Season Start Date",
        ):
            assert family_key(title) is None, title


class TestSportScopedFamilies6630:
    """A family key is the QUESTION SHAPE and carries no sport, so two
    sports' awards land on it. Production has six live markets keyed
    `defensive player of the year` across basketball, football and the WNBA."""

    def test_two_sports_do_not_share_one_family(self):
        # Kalshi 415 ("Defensive Player of the Year Winner", basketball) and
        # 53663 ("Defensive Player of the Year Winner?", football) key
        # identically. Merged, one card would mix an NBA and an NFL race.
        markets = [
            _award_market(415, "Defensive Player of the Year Winner", "kalshi",
                          [("Jaylen Brown", 0.2), ("Derrick White", 0.1)],
                          sport="basketball"),
            _award_market(53663, "Defensive Player of the Year Winner?", "kalshi",
                          [("Micah Parsons", 0.3), ("Myles Garrett", 0.25)],
                          sport="football"),
        ]
        families = group_prop_families(markets)
        assert len(families) == 2
        assert {f["sport"] for f in families} == {"basketball", "football"}
        # Same award, so the same reader-facing label; the KEY disambiguates,
        # because the page uses it as its React key and must not collide.
        assert {f["label"] for f in families} == {"Defensive Player Of The Year"}
        assert len({f["family_key"] for f in families}) == 2
        by_sport = {f["sport"]: f for f in families}
        assert {r["entity"] for r in by_sport["basketball"]["rows"]} == {
            "Jaylen Brown", "Derrick White",
        }
        assert {r["entity"] for r in by_sport["football"]["rows"]} == {
            "Micah Parsons", "Myles Garrett",
        }

    def test_one_sport_emits_the_bare_key_exactly_as_before(self):
        # The no-op case, which is every family on a team page. The scope may
        # not change the served key when there is nothing to disambiguate.
        markets = [
            _award_market(409, "Sixth Man of the Year Winner", "kalshi",
                          [("Payton Pritchard", 0.4), ("Sam Hauser", 0.01)]),
            _award_market(58015765, "Pro Basketball Sixth Man of the Year Winner",
                          "kalshi", [("Payton Pritchard", 0.38), ("Luke Kornet", 0.05)]),
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        assert families[0]["family_key"] == "sixth man of the year"
        assert families[0]["sport"] == "basketball"
        # Both venues' rows are in the one card, and the player named twice
        # is one row, not two.
        assert {r["entity"] for r in families[0]["rows"]} == {
            "Payton Pritchard", "Sam Hauser", "Luke Kornet",
        }

    def test_a_missing_sport_never_splits_a_family(self):
        # llm_sport_category is null on 793 of 541,777 served rows (0.15%).
        # An unconditional (sport, key) tuple would split every family that
        # straddled one of those nulls — this bug's mirror image.
        markets = [
            _award_market(409, "Sixth Man of the Year Winner", "kalshi",
                          [("Payton Pritchard", 0.4)], sport=None),
            _award_market(113146, "NBA Sixth Man of the Year Winner", "polymarket",
                          [("Sam Hauser", 0.02)], sport="basketball"),
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        assert families[0]["family_key"] == "sixth man of the year"

    def test_the_route_field_name_is_read(self):
        # The route serves the column as `sport`; `llm_sport_category` is the
        # fallback so a caller passing the raw row is scoped too.
        markets = [
            {**_award_market(1, "Rookie of the Year", "kalshi",
                             [("A", 0.3), ("B", 0.2)], sport=None),
             "llm_sport_category": "baseball"},
            _award_market(2, "Rookie of the Year", "kalshi",
                          [("C", 0.3), ("D", 0.2)], sport="hockey"),
        ]
        families = group_prop_families(markets)
        assert {f["sport"] for f in families} == {"baseball", "hockey"}


class TestKeyStabilityOverProduction6630:
    """The control the fix is actually gated on.

    The four titles in the issue cannot see the population this touches. So:
    score EVERY distinct production title the change could reach and assert
    that the only keys that moved are the ones named below.

    The fixture is the BEFORE, captured from master (9a07bf9cb) on
    2026-09-16 while the defect was live, and is never refreshed — a snapshot
    taken from the fixed tree contains no defect to guard.
    """

    #: The whole intended effect of #6630, title -> new key. Everything else
    #: in the fixture must key exactly as it did before.
    MOVED = {
        "Pro Basketball Coach of the Year Winner": "coach of the year",
        "Pro Basketball Defensive Player of the Year Winner": (
            "defensive player of the year"
        ),
        "Pro Basketball Rookie of the Year Winner": "rookie of the year",
        "Pro Basketball Sixth Man of the Year Winner": "sixth man of the year",
        "MLS: 2026 Most Valuable Player": "mvp",
        "PLL: 2026 Jim Brown Most Valuable Player": "mvp",
        # Verbatim from production, trailing space and all — the corpus is
        # the venue's bytes, not a tidied copy of them.
        "WBC: Most Valuable Player ": "mvp",
    }

    #: #8385 / #8386 / #7162 (2026-09-24), declared beside #6630's rather than
    #: by re-snapshotting the BEFORE: Polymarket's "AP" NFL awards join the
    #: venue-neutral key; a shortlist ("Finalists", "nominees", "Top 5 ...") is
    #: not the winner race; the Super Bowl MVP is not the season MVP. The
    #: Billboard title is a song name that only looked like an award.
    MOVED_8385 = {
        "AP College Football Player of the Year Winner": (
            "college football player of the year"
        ),
        "Pro Football: 2026-27 AP Coach of the Year Winner": "coach of the year",
        "Pro Football: 2026-27 AP Comeback Player of the Year Winner": (
            "comeback player of the year"
        ),
        "Pro Football: 2026-27 AP Defensive Player of the Year Winner": (
            "defensive player of the year"
        ),
        "Pro Football: 2026-27 AP Defensive Rookie of the Year Winner": (
            "defensive rookie of the year"
        ),
        "Pro Football: 2026-27 AP Offensive Player of the Year Winner": (
            "offensive player of the year"
        ),
        "Pro Football: 2026-27 AP Offensive Rookie of the Year Winner": (
            "offensive rookie of the year"
        ),
        "Coach of the Year Finalists": None,
        "Defensive Player of the Year Finalists": None,
        "Defensive Rookie of the Year Finalists": None,
        "Offensive Player of the Year Finalists": None,
        "Offensive Rookie of the Year Finalists": None,
        "Grammy nominees: Album of the Year": None,
        "Grammy nominees: Record of the Year": None,
        "Grammy nominees: Song of the Year": None,
        "Top 5 Pro Basketball Draft Pick Wins Rookie of the Year?": None,
        "Will It's The Most Wonderful Time Of The Year - Andy Williams be in "
        "the Billboard Top 10 for the week of January 3, 2026?": None,
        "Pro Football Championship MVP?": "championship game mvp",
    }

    @staticmethod
    def _fixture():
        path = (
            Path(__file__).parent
            / "fixtures"
            / "prop_family_keys_before_6630.json"
        )
        return json.loads(path.read_text())["keys"]

    def test_the_fixture_still_covers_the_populations_it_claims(self):
        # A control over a corpus is worth what the corpus is worth. If the
        # file is ever trimmed, the "nothing else moved" assertion below goes
        # quietly vacuous, so size and reach are asserted first.
        keys = self._fixture()
        assert len(keys) == 725
        assert sum(1 for t in keys if t.lower().startswith("pro ")) >= 500
        assert sum(1 for t in keys if "of the year" in t.lower()) >= 200
        assert set(self.MOVED) <= set(keys)
        assert set(self.MOVED_8385) <= set(keys)

    def test_only_the_named_titles_changed_key(self):
        keys = self._fixture()
        moved, drifted = [], []
        declared = {**self.MOVED, **self.MOVED_8385}
        for title, before in keys.items():
            now = family_key(title)
            if title in declared:
                if now != declared[title]:
                    moved.append((title, before, now))
            elif now != before:
                drifted.append((title, before, now))
        assert not drifted, f"{len(drifted)} title(s) re-keyed unintentionally: {drifted[:10]}"
        assert not moved, f"intended fold did not land: {moved}"

    def test_the_control_can_fail(self):
        # Strawman: the fixture holds the pre-fix keys, so the four folded
        # titles MUST disagree with it. If they did not, the corpus would be
        # an AFTER snapshot and would prove nothing.
        keys = self._fixture()
        declared = {**self.MOVED, **self.MOVED_8385}
        stale = [t for t in declared if keys[t] == declared[t]]
        assert not stale, f"fixture already carries the fixed key for {stale}"


class TestTheScopeReachesTheGrouper6630:
    """The route is the only caller, so the scope is only real if it
    survives the trip from the column to `group_prop_families`."""

    def test_the_scope_column_exists_on_the_model(self):
        # The route reads the column through `getattr(..., None)` so a test
        # double without it degrades instead of 500-ing. That default is only
        # safe while the column is really there — if it is ever renamed, the
        # scope silently becomes None for every row and this bug returns
        # without a single test going red. This is that test.
        from app.models.models import FuturesMarket

        assert hasattr(FuturesMarket, "llm_sport_category")

    def test_the_route_puts_the_scope_in_the_market_dict(self):
        # Reads the source rather than standing a route up: the assertion is
        # that the key the grouper looks for is the key the route writes.
        import inspect

        from app.routes import prop_families as route

        src = inspect.getsource(route)
        assert '"sport": getattr(market, "llm_sport_category", None)' in src

    def test_a_market_dict_without_a_sport_key_is_still_grouped(self):
        # Every other caller and every older fixture passes no sport at all.
        markets = [
            {
                "market_id": 1, "name": "LeBron James Next Team",
                "source": "kalshi", "group_id": None, "status": "open",
                "outcomes": [{"outcome_id": 1, "name": "Lakers", "probability": 0.6}],
            },
            {
                "market_id": 2, "name": "Kevin Durant Next Team",
                "source": "kalshi", "group_id": None, "status": "open",
                "outcomes": [{"outcome_id": 2, "name": "Suns", "probability": 0.5}],
            },
        ]
        families = group_prop_families(markets)
        assert len(families) == 1
        assert families[0]["family_key"] == "next team"
        assert families[0]["sport"] is None
