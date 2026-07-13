"""B7 up-link resolver — L2-91. Tests the shared server-side market -> concept/hub
resolver (`app/utils/concept_links.py`) that the futures-detail response attaches."""

from app.utils.concept_links import (
    derive_market_concept_key,
    derive_market_hub_slug,
)


class TestConceptKey:
    def test_ufc_fight_ticker_to_card_concept(self):
        # KXUFCFIGHT-<YYMONDD><FIGHTERS> -> event:ufc:<date-token>.
        assert (
            derive_market_concept_key(
                "kalshi:KXUFCFIGHT-26JUL11MCGHOL", "McGregor vs. Holloway", "mma", 2
            )
            == "event:ufc:26jul11"
        )

    def test_boxing_fight_ticker_to_card_concept(self):
        assert (
            derive_market_concept_key(
                "KXBOXING-26JUL04MASONBELL", "Mason vs Bell", "boxing", 2
            )
            == "event:boxing:26jul04"
        )

    def test_combat_prop_ticker_gets_no_concept(self):
        # A method-of-victory prop ticker is NOT a fight ticker -> no card concept
        # (falls back to the hub link).
        assert (
            derive_market_concept_key(
                "KXUFCMOV-26JUL11MCG", "Method of victory", "mma", 3
            )
            is None
        )

    def test_tennis_winner_field(self):
        assert (
            derive_market_concept_key(
                "kalshi:KXWTAMATCH-...", "2026 Women's Wimbledon Winner", "tennis", 128
            )
            == "event:tennis:2026-women-s-wimbledon-winner"
        )

    def test_tennis_matchup_gets_no_concept(self):
        assert (
            derive_market_concept_key(None, "Gauff vs Sabalenka", "tennis", 2) is None
        )

    def test_f1_gp_winner_field(self):
        assert (
            derive_market_concept_key(
                "KXF1RACE-BRIGP26", "British Grand Prix Winner", "motorsports", 20
            )
            == "event:f1:british-grand-prix-winner"
        )

    def test_f1_submarket_gets_no_concept(self):
        # Sprint / qualifying / pole are children, not the GP winner field.
        assert (
            derive_market_concept_key(
                "KXF1SPRINT-BRIGP26", "British Grand Prix Sprint Winner", "motorsports", 20
            )
            is None
        )

    def test_motorsports_non_gp_gets_no_concept(self):
        # A motorsports-miscategorized non-race "winner" market must not leak a
        # nonsense F1 concept (guard: requires "grand prix").
        assert (
            derive_market_concept_key(
                "KXWCGROUPPTS-...", "Any Group Winner to Advance", "motorsports", 8
            )
            is None
        )

    def test_golf_major_winner_to_tournament(self):
        # A golf MAJOR resolves to the canonical tournament slug get_golf_tournament
        # matches (via _normalize_tournament -> display -> clean_slug).
        assert (
            derive_market_concept_key(
                "kalshi:KXGOLF-...", "The Open Championship Winner", "golf", 156
            )
            == "event:golf:the-open-championship"
        )

    def test_golf_all_four_majors_resolve(self):
        assert derive_market_concept_key(None, "Masters Tournament Winner", "golf", 90) == "event:golf:the-masters"
        assert derive_market_concept_key(None, "PGA Championship Winner", "golf", 90) == "event:golf:pga-championship"
        assert derive_market_concept_key(None, "U.S. Open: Top 10 Finishers", "golf", 90) == "event:golf:u-s-open"

    def test_golf_miscategorized_boxoffice_gets_no_wrong_major(self):
        # A movie box-office market wrongly tagged golf must NOT link to The Masters.
        assert (
            derive_market_concept_key(
                "KXBOX-...", '"Masters of the Universe" Opening Weekend Box Office', "golf", 3
            )
            is None
        )

    def test_golf_non_major_gets_no_concept(self):
        # Non-major tour events fall back to the hub (golf slug matching is EXACT,
        # so we don't risk a dead concept link).
        assert (
            derive_market_concept_key(
                "kalshi:KXGOLF-...", "Some Random Open Winner", "golf", 100
            )
            is None
        )

    def test_awards_ceremony_by_ticker(self):
        assert (
            derive_market_concept_key("KXOSCARPIC-27", "Best Picture", "entertainment", 10)
            == "event:awards:oscars"
        )

    def test_non_concept_category(self):
        assert derive_market_concept_key(None, "Fed Rate Decision", "economics", 3) is None

    # L2-93 (B6): elections — the civic §6 sibling up-link. Genuine general-election
    # races breadcrumb to the election-night concept; novelties/primaries/other editions
    # do not (mirrors the awards up-link + the ElectionEventAdapter's own classification).
    def test_election_governor_race_to_concept(self):
        assert (
            derive_market_concept_key("KXGOVCA-26", "California Governor winner?", "politics", 25)
            == "event:election:2026-midterms"
        )

    def test_election_governor_party_race_to_concept(self):
        assert (
            derive_market_concept_key(
                "KXGOVPARTYAK-26", "Alaska Governor winner? (Party)", "politics", 2
            )
            == "event:election:2026-midterms"
        )

    def test_election_margin_of_victory_gets_no_concept(self):
        # KXMIDTERM* isn't an election-race stem AND MOV is a novelty by name.
        assert (
            derive_market_concept_key(
                "KXMIDTERMMOV-MO05D", "Missouri's 5th District margin of victory", "politics", 5
            )
            is None
        )

    def test_election_other_edition_gets_no_concept(self):
        # 2028 Senate is a different edition than the 2026 midterms concept.
        assert (
            derive_market_concept_key("SENATEOR-28", "Oregon Senate winner? (2028)", "politics", 5)
            is None
        )

    def test_election_govt_shutdown_false_friend_gets_no_concept(self):
        # KXGOVT* (shutdown) shares the "kxgov" stem but is a novelty, not a race.
        assert (
            derive_market_concept_key(
                "KXGOVTSHUTDOWN-26", "Government shutdown before 2027?", "politics", 2
            )
            is None
        )

    def test_election_primary_gets_no_concept_up_link(self):
        # Primaries live ON the concept page but are ticker-name ambiguous, so the
        # up-link stays race-only (honest gap) — a "nominee -26" market never mis-links.
        assert (
            derive_market_concept_key(
                "KXSENATEPRIMARYOH-26", "Republican Senate nominee (Ohio)?", "politics", 4
            )
            is None
        )


class TestHubSlug:
    def test_mapped_categories(self):
        assert derive_market_hub_slug("mma") == "mma"
        assert derive_market_hub_slug("boxing") == "boxing"
        assert derive_market_hub_slug("golf") == "golf"
        assert derive_market_hub_slug("tennis") == "tennis"

    def test_esports_hub(self):
        # L2-92 (B4): esports futures markets up-link to the /hub/esports landing.
        assert derive_market_hub_slug("esports") == "esports"
        assert derive_market_hub_slug("Esports") == "esports"

    def test_case_insensitive(self):
        assert derive_market_hub_slug("Golf") == "golf"

    def test_no_hub_for_unmapped(self):
        assert derive_market_hub_slug("nba") is None
        assert derive_market_hub_slug("economics") is None
        assert derive_market_hub_slug(None) is None
