import XCTest
@testable import Bain_Luck

/// #7532 — the Accuracy screen's niche card told a reader that **Football,
/// Hockey and Soccer are still accumulating**, two inches under a table
/// publishing Football 29.2K, Hockey 15.6K and Soccer 118.2K.
///
/// The chips read
/// `Football 847 · Lacrosse NCAA 829 · Chess 809 · Hockey 730 · Football 707 ·
/// Football 682 · Soccer 613 · Football 593` — four of eight saying "Football",
/// which reads as one category listed four times, and three of eight naming a
/// category the table above grades.
///
/// ## The assertion that is the ship
///
/// `testNoChipEverPrintsAPublishedParentsName`. The sample gate is applied by
/// the server to the RAW league key and the label was applied by the client to
/// the NORMALISED key, so the two were answering about different rows. Anything
/// that reintroduces a normalise-then-look-up — including a well-meant "fall
/// back to the parent when we have no specific name" — fails it.
///
/// ## Why the older guards passed
///
/// `CalibrationDisplayNameTests` asserts `nicheDisplayName` never returns a raw
/// lowercase/underscored key, which it never did. Nothing compared a chip's
/// label against the labels of the rows the Category Breakdown publishes, and
/// that comparison is the whole defect.
@MainActor
final class CalibrationNicheChipLabelTests: XCTestCase {

    // MARK: - Fixtures, measured rather than imagined

    /// Every `small_sample_categories` key production served on 2026-09-20 at
    /// 18:45Z, `min_category_outcomes` 1000, in payload order. Re-measure with:
    ///
    /// ```
    /// curl -s "$BAINLUCK_API/api/calibration" \
    ///   | python3 -c "import json,sys; print([c['category'] for c in json.load(sys.stdin)['small_sample_categories']])"
    /// ```
    ///
    /// Frozen on purpose: it is a record of one real response. The rows below it
    /// move — the issue quoted 8 chips, this list is 109 — so a claim about "how
    /// many collapse" is quoted with its date or not at all.
    private static let servedParkedCategories = [
        "americanfootball_cfl", "lacrosse_ncaa", "chess", "icehockey_sweden_hockey_league",
        "americanfootball_nfl_preseason", "americanfootball_ncaaf_fcs", "soccer_usa_mls",
        "americanfootball_ufl", "soccer_argentina_primera_division", "lacrosse_pll",
        "soccer_england_league1", "soccer_england_league2", "soccer_efl_champ",
        "soccer_brazil_serie_b", "soccer_brazil_campeonato", "soccer_spain_segunda_division",
        "americanfootball_nfl", "soccer_china_superleague", "tennis_wta_monterrey_open",
        "soccer_spain_la_liga", "soccer_italy_serie_b", "soccer_germany_liga3", "rugby",
        "soccer_poland_ekstraklasa", "soccer_mexico_ligamx", "tennis_atp_washington_open",
        "icehockey_sweden_allsvenskan", "soccer_japan_j_league", "soccer_italy_serie_a",
        "soccer_belgium_first_div", "soccer_chile_campeonato", "soccer_sweden_superettan",
        "soccer_netherlands_eredivisie", "soccer_portugal_primeira_liga", "soccer_epl",
        "soccer_germany_bundesliga2", "soccer_france_ligue_two", "soccer_turkey_super_league",
        "boxing", "soccer_sweden_allsvenskan", "tennis_wta_washington_open",
        "soccer_norway_eliteserien", "soccer_france_ligue_one", "lacrosse",
        "soccer_conmebol_copa_libertadores", "soccer_russia_premier_league",
        "soccer_germany_bundesliga", "soccer_korea_kleague1",
        "soccer_conmebol_copa_sudamericana", "soccer_league_of_ireland",
        "soccer_finland_veikkausliiga", "soccer_switzerland_superleague",
        "soccer_austria_bundesliga", "soccer_greece_super_league", "soccer_denmark_superliga",
        "soccer_spl", "basketball_nbl", "soccer_fifa_world_cup", "pickleball",
        "soccer_uefa_champs_league_qualification", "soccer_australia_aleague", "uncategorized",
        "soccer_concacaf_leagues_cup", "aussierules", "soccer_england_efl_cup", "health",
        "soccer_uefa_europa_conference_league", "rodeo", "soccer_uefa_champs_league", "crypto",
        "tennis_wta_guadalajara_open", "soccer_uefa_europa_league", "cycling", "darts",
        "soccer_fa_cup", "soccer_uefa_champs_league_women", "legal", "skateboarding", "culture",
        "ai_safety", "olympics", "commodities", "soccer_germany_dfb_pokal",
        "soccer_fifa_world_cup_qualifiers_europe", "soccer_italy_coppa_italia", "energy",
        "softball", "sailing", "surfing", "bmx", "climbing", "poker", "weightlifting",
        "horse_racing", "wrestling", "squash", "bull_riding", "handball", "xgames", "mlb",
        "soccer_uefa_nations_league", "auto_industry", "extreme_sports", "figure_skating",
        "real_estate", "soccer_spain_copa_del_rey", "track_and_field", "transportation",
        "word_games",
    ]

    /// The parent categories the Category Breakdown published in the SAME
    /// response, with the outcome counts it drew beside them. Without this the
    /// collapse assertion below could pass vacuously — "no chip names a
    /// published parent" is free if nothing is published.
    private static let publishedParents: [String: Int] = [
        "soccer": 118_226, "basketball": 69_121, "tennis": 53_464,
        "football": 29_215, "hockey": 15_641,
    ]

    /// The eight chips a reader actually sees (`nicheSection` takes
    /// `prefix(8)` of the payload order), with the label each must now carry.
    private static let visibleChips: [(key: String, outcomes: Int, label: String)] = [
        ("americanfootball_cfl", 847, "CFL"),
        ("lacrosse_ncaa", 829, "NCAA Lacrosse"),
        ("chess", 809, "Chess"),
        ("icehockey_sweden_hockey_league", 730, "SHL"),
        ("americanfootball_nfl_preseason", 707, "NFL Preseason"),
        ("americanfootball_ncaaf_fcs", 682, "NCAAF FCS"),
        ("soccer_usa_mls", 613, "MLS"),
        ("americanfootball_ufl", 593, "UFL"),
    ]

    /// The rule as it stood before this ship, reproduced here so the suite can
    /// prove it fails what the fix passes. A guard that cannot be shown failing
    /// against the defect it names is a guard nobody can trust later.
    private static func legacyNicheDisplayName(_ raw: String) -> String {
        let parent = CalibrationViewModel.normalizedCategory(raw)
        let mapped = CalibrationViewModel.categoryDisplayName(parent)
        // `categoryDisplayName` title-cases anything the map does not carry, so
        // "was this a MAP hit" is the discriminator the old code branched on.
        return parent == raw ? toTitleCaseAcronymSafe(raw) : mapped
    }

    // MARK: - 1. The ship

    /// No chip may print the display name of a DIFFERENT category that the
    /// table above is publishing. This is L2-103 Item 3b (Alex D5) as an
    /// assertion, over the whole served population rather than the visible 8.
    func testNoChipEverPrintsAPublishedParentsName() {
        for key in Self.servedParkedCategories {
            let parent = CalibrationViewModel.normalizedCategory(key)
            guard parent != key else { continue }
            let parentLabel = CalibrationViewModel.categoryDisplayName(parent)
            XCTAssertNotEqual(
                CalibrationViewModel.nicheDisplayName(key), parentLabel,
                "'\(key)' is parked below the bar and printed '\(parentLabel)', which the "
                    + "Category Breakdown publishes with \(Self.publishedParents[parent] ?? -1) "
                    + "outcomes — the chip says that category is still accumulating"
            )
        }
    }

    /// The same sweep against the OLD rule, which must fail it. 67 of the 109
    /// keys collapsed onto a published parent on this payload — 55 "Soccer",
    /// 5 "Football", 4 "Tennis", 2 "Hockey", 1 "Basketball". If a future edit
    /// makes this number 0, the legacy reproduction has drifted and the test
    /// above has stopped proving anything.
    func testTheOldRuleCollapsedSixtySevenOfTheHundredAndNine() {
        let collapsed = Self.servedParkedCategories.filter { key in
            let parent = CalibrationViewModel.normalizedCategory(key)
            guard parent != key else { return false }
            return Self.legacyNicheDisplayName(key)
                == CalibrationViewModel.categoryDisplayName(parent)
        }
        XCTAssertEqual(collapsed.count, 67,
                       "the defect this suite guards is not reproducible any more")
        XCTAssertEqual(
            Set(collapsed.map { CalibrationViewModel.categoryDisplayName(
                CalibrationViewModel.normalizedCategory($0)) }),
            ["Soccer", "Football", "Tennis", "Hockey", "Basketball"]
        )
    }

    /// Every parent the collapse assertion protects must really have been
    /// published in that response — otherwise the assertion is about nothing.
    func testThePublishedParentsClearedTheBarTheCardQuotes() {
        for (parent, outcomes) in Self.publishedParents {
            XCTAssertGreaterThanOrEqual(outcomes, 1000,
                                        "'\(parent)' would be parked, not published")
            // …and it is a category at least one parked key rolls up to, so the
            // collapse assertion has a real pair to be about.
            XCTAssertTrue(
                Self.servedParkedCategories.contains {
                    CalibrationViewModel.normalizedCategory($0) == parent && $0 != parent
                },
                "no parked key rolls up to '\(parent)' any more — the fixture has drifted"
            )
        }
    }

    // MARK: - 2. What the reader sees

    /// The eight visible chips, end to end: real payload bytes → the real
    /// decoder → the real view-model ordering → the label the card prints. A
    /// test at any single link passes while a reader still sees "Football".
    func testTheEightVisibleChipsNameTheirOwnLeague() throws {
        let rows = Self.visibleChips
            .map { """
            {"category": "\($0.key)", "outcomes": \($0.outcomes), "ece": 1.0,
             "disposition": "parked_below_publish_bar", "publish_bar": 1000}
            """ }
            .joined(separator: ",")
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let data = try dec.decode(
            CalibrationData.self,
            from: Data("""
            {"buckets": [], "total_markets": 0, "total_outcomes": 0,
             "min_category_outcomes": 1000, "small_sample_categories": [\(rows)]}
            """.utf8))
        let vm = CalibrationViewModel(preloaded: data)

        let drawn = vm.smallSampleCategories.prefix(8)
            .map { CalibrationViewModel.nicheDisplayName($0.category) }
        XCTAssertEqual(drawn, Self.visibleChips.map(\.label))
        XCTAssertEqual(Set(drawn).count, drawn.count,
                       "two chips share a label, which reads as one category listed twice: \(drawn)")
    }

    /// Nothing in the served population may reach a reader as a raw key, an
    /// underscore, a lowercase opening or an empty chip.
    func testEveryServedKeyRendersCleanly() {
        for key in Self.servedParkedCategories {
            let label = CalibrationViewModel.nicheDisplayName(key)
            XCTAssertFalse(label.isEmpty, "'\(key)' rendered an empty chip")
            XCTAssertFalse(label.contains("_"), "'\(key)' rendered a raw key: '\(label)'")
            let initial = String(label.prefix(1))
            XCTAssertEqual(initial, initial.uppercased(),
                           "'\(key)' rendered lowercase-initial: '\(label)'")
        }
    }

    // MARK: - 3. The rule's own clauses

    /// The sport prefix is dropped by MEMBERSHIP of a known sport family, never
    /// by position — web's UX-P189 finding, ported with the ship. Dropping
    /// segment 0 blindly is what turned `track_and_field` into "And Field" and
    /// `horse_racing` into "Racing" over there.
    func testAPrefixIsDroppedOnlyWhenItNamesASportOfOurs() {
        XCTAssertEqual(nicheCategoryLabel("americanfootball_nfl_preseason"), "NFL Preseason")
        XCTAssertEqual(nicheCategoryLabel("tennis_wta_monterrey_open"), "WTA Monterrey Open")
        // Not sports: every token survives.
        XCTAssertEqual(nicheCategoryLabel("track_and_field"), "Track and Field")
        XCTAssertEqual(nicheCategoryLabel("horse_racing"), "Horse Racing")
        XCTAssertEqual(nicheCategoryLabel("figure_skating"), "Figure Skating")
        XCTAssertEqual(nicheCategoryLabel("table_tennis"), "Table Tennis")
        // A single token is never a prefix, so a bare sport keeps its own name.
        XCTAssertEqual(nicheCategoryLabel("boxing"), "Boxing")
        XCTAssertEqual(nicheCategoryLabel("lacrosse"), "Lacrosse")
    }

    /// A curated league name is an opinion and comes back verbatim — re-casing
    /// one is how web's own "NCAAF" became "Ncaaf" before UX-P189.
    func testACuratedLeagueNameIsReturnedVerbatim() {
        XCTAssertEqual(nicheCategoryLabel("icehockey_sweden_hockey_league"), "SHL")
        XCTAssertEqual(nicheCategoryLabel("icehockey_sweden_allsvenskan"), "Allsvenskan")
        XCTAssertEqual(nicheCategoryLabel("soccer_spain_la_liga"), "La Liga")
        XCTAssertEqual(nicheCategoryLabel("soccer_uefa_champs_league"), "UCL")
        // …and where the app already has an opinion, the chip reads THAT one
        // rather than keeping a second copy of it.
        XCTAssertEqual(nicheCategoryLabel("americanfootball_nfl"), leagueAcronyms["americanfootball_nfl"])
    }

    /// The four chip-only league names must NOT leak into the shared
    /// vocabulary. #5780 ruled that search's Teams row answers COARSE when the
    /// served facet is missing — "Hockey", not "SHL" — and the first draft of
    /// this ship broke that by adding the names to `leagueAcronyms`, which
    /// `SearchTeamRowSportLabelTests` caught. Pinning both answers here so the
    /// next person to reach for the shared map meets the reason first.
    func testTheChipOnlyNamesDoNotChangeWhatOtherSurfacesCallTheseLeagues() {
        XCTAssertEqual(nicheCategoryLabel("icehockey_sweden_hockey_league"), "SHL")
        XCTAssertEqual(sportDisplayName(for: "icehockey_sweden_hockey_league"), "Hockey")
        XCTAssertEqual(sportCategoryDisplayName("icehockey_sweden_allsvenskan"), "Hockey")
        XCTAssertNil(leagueAcronyms["lacrosse_pll"],
                     "a chip-only name has been promoted into the shared map")
    }

    /// Acronyms and small words. The acronym half is what keeps "CFL" from
    /// arriving as "Cfl"; the small-word half is what keeps "League of Ireland"
    /// from arriving as "League Of Ireland" — and `la` is deliberately not a
    /// small word, so "Spain La Liga" does not invert into "Spain la Liga".
    func testAcronymsAreShoutedAndSmallWordsAreNot() {
        XCTAssertEqual(nicheCategoryLabel("americanfootball_cfl"), "CFL")
        XCTAssertEqual(nicheCategoryLabel("soccer_fa_cup"), "FA Cup")
        XCTAssertEqual(nicheCategoryLabel("soccer_germany_dfb_pokal"), "Germany DFB Pokal")
        XCTAssertEqual(nicheCategoryLabel("soccer_conmebol_copa_libertadores"),
                       "CONMEBOL Copa Libertadores")
        XCTAssertEqual(nicheCategoryLabel("ai_safety"), "AI Safety")
        XCTAssertEqual(nicheCategoryLabel("soccer_league_of_ireland"), "League of Ireland")
        XCTAssertEqual(nicheCategoryLabel("soccer_spain_copa_del_rey"), "Spain Copa del Rey")
        // A small word that LEADS is capitalised like any other first word.
        XCTAssertEqual(nicheCategoryLabel("the_masters"), "The Masters")
    }

    /// The label is built from the key's own tokens, so the parent map is not
    /// even consulted. Pinning that structurally: a key whose parent IS a
    /// published category still comes back named after itself.
    func testTheParentMapIsNeverConsulted() {
        for key in ["soccer_brazil_serie_b", "tennis_atp_washington_open",
                    "basketball_nbl", "americanfootball_ufl"] {
            let parent = CalibrationViewModel.normalizedCategory(key)
            XCTAssertTrue(Self.publishedParents.keys.contains(parent),
                          "fixture drift: '\(key)' no longer rolls up to a published parent")
            XCTAssertNotEqual(nicheCategoryLabel(key),
                              CalibrationViewModel.categoryDisplayName(parent))
        }
    }

    /// Degenerate input never produces an empty chip beside a live number.
    func testDegenerateKeysKeepSomethingToRead() {
        XCTAssertEqual(nicheCategoryLabel(""), "")
        XCTAssertEqual(nicheCategoryLabel("soccer"), "Soccer")
        XCTAssertEqual(nicheCategoryLabel("soccer_"), "Soccer")
        XCTAssertEqual(nicheCategoryLabel("_"), "_")
    }
}
