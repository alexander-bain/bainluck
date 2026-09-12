import XCTest
@testable import Bain_Luck

/// #5780 — SEARCH'S TEAM ROW PRINTED THE SPORT KEY WITH THE FAMILY FILED OFF.
///
/// THE DEFECT. `SearchView.searchTeamRow` built its own label:
///
///     Text(sport.split(separator: "_").dropFirst().joined(separator: " ").uppercased())
///
/// so the grey line under a club's name was the database key, shouted:
/// `baseball_milb` → **"MILB"** directly under a filter pill the same screen
/// draws as "MiLB"; `icehockey_sweden_hockey_league` → **"SWEDEN HOCKEY
/// LEAGUE"** where the server's own name for it is "SHL";
/// `tennis_atp_queens_club_champ` → **"ATP QUEENS CLUB CHAMP"**, a truncation
/// that exists to fit a column, not to be read.
///
/// REACH, measured on production 2026-09-12 (`db-query`, `teams` ⋈ `sports`):
/// every one of the 100 largest sport keys carries a proper `sports.name` the
/// row was throwing away, and the biggest disagreements are the biggest groups
/// — `mma_mixed_martial_arts` (1,233 teams, served "MMA", printed "MIXED
/// MARTIAL ARTS"), `baseball_ncaa` (455, served "NCAA Baseball", printed
/// "NCAA"), `cricket_international_t20` (52, served "International Twenty20",
/// printed "INTERNATIONAL T20").
///
/// WHY THE FACET AND NOT A NEW MAP. The search payload already hands the app
/// `sports: [{key, name, count}]` — the filter pills are built from it, which
/// is why the pill and the row disagreed in the same screenshot. The served
/// name is therefore free and exact. It is also PARTIAL: measured over 18 real
/// production queries, 9 of 16 team rows had their key in the facet (the facet
/// lists the sports the RESULTS touch, and `?q=yank` returns a Yankees team
/// row with no events at all, so no facet). The other 9 fall through to
/// `sportCategoryDisplayName`, the rule #5723 made single-source — not to a
/// fifth private formatter.
final class SearchTeamRowSportLabelTests: XCTestCase {

    // MARK: - The corpus

    /// Production sport keys that reach a team row, with their team count and
    /// the name the server gives them (`SELECT s.key, s.name, COUNT(t.id) FROM
    /// teams t JOIN sports s ON s.id = t.sport_id GROUP BY 1,2`, 2026-09-12).
    /// The keys a hand-written list would never have contained — the Swedish
    /// hockey league, NCAA baseball, a truncated tour name — are the ones this
    /// ship is about, so the corpus is the table rather than a sample of it.
    private let corpus: [(key: String, served: String, teams: Int)] = [
        ("mma_mixed_martial_arts", "MMA", 1233),
        ("boxing_boxing", "Boxing", 915),
        ("soccer_usa_mls", "MLS", 697),
        ("baseball_ncaa", "NCAA Baseball", 455),
        ("basketball_ncaab", "NCAAB", 366),
        ("tennis_atp_queens_club_champ", "ATP Queen's Club Championships", 34),
        ("baseball_mlb", "MLB", 33),
        ("baseball_milb", "MiLB", 30),
        ("americanfootball_nfl", "NFL", 32),
        ("icehockey_sweden_hockey_league", "SHL", 20),
        ("cricket_international_t20", "International Twenty20", 52),
        ("soccer_germany_bundesliga2", "Bundesliga 2 - Germany", 22),
        ("soccer_spain_segunda_division", "La Liga 2 - Spain", 28),
        ("cricket_t20_blast", "T20 Blast", 18),
    ]

    /// The label the row printed before this ship, kept so the tests below can
    /// assert against the defect itself rather than against a description of
    /// it. This is the deleted line, verbatim in behaviour.
    private func shoutedKey(_ key: String) -> String {
        key.split(separator: "_").dropFirst().joined(separator: " ").uppercased()
    }

    private func facet(_ key: String, _ name: String) -> SportFacet {
        SportFacet(key: key, name: name, count: 1)
    }

    // MARK: - The served name wins

    func testTheServedFacetNameIsWhatTheRowPrints() {
        for row in corpus {
            let facets = [facet(row.key, row.served), facet("politics", "Politics")]
            XCTAssertEqual(
                sportKeyDisplayName(row.key, facets: facets), row.served,
                "\(row.key): the page was handed the name \"\(row.served)\" and printed something else"
            )
        }
    }

    /// The pill row and the team row read the same payload; before this ship
    /// they disagreed on the same screen. This is that screenshot as an
    /// assertion: Worcester Red Sox sat under a pill saying "MiLB" and said
    /// "MILB" itself.
    func testTheRowAndTheFilterPillAgreeOnOneName() {
        let facets = [facet("baseball_mlb", "MLB"), facet("baseball_milb", "MiLB")]
        let pillLabels = facets.map(\.name)
        let rowLabel = sportKeyDisplayName("baseball_milb", facets: facets)
        XCTAssertEqual(rowLabel, "MiLB")
        XCTAssertTrue(
            pillLabels.contains(rowLabel ?? ""),
            "the row printed \(rowLabel ?? "nil"), which is not one of the pills \(pillLabels) built from the same facet"
        )
        XCTAssertNotEqual(rowLabel, shoutedKey("baseball_milb"))
    }

    /// The served name is repaired, not reprinted. `tennis_atp` is served as
    /// "Tennis Atp", and the row it replaces printed the key's last token,
    /// "ATP" — so an unrepaired served name would have made that one row worse
    /// while making five others right (the Alcaraz screenshot has both).
    func testAGarbledServedAcronymIsRepairedAndACorrectOneIsLeftAlone() {
        XCTAssertEqual(
            sportKeyDisplayName("tennis_atp", facets: [facet("tennis_atp", "Tennis Atp")]),
            "Tennis ATP"
        )
        for (key, served) in [
            ("baseball_milb", "MiLB"),
            ("icehockey_sweden_hockey_league", "SHL"),
            ("tennis_atp_queens_club_champ", "ATP Queen's Club Championships"),
            ("cricket_international_t20", "International Twenty20"),
            ("soccer_germany_bundesliga2", "Bundesliga 2 - Germany"),
        ] {
            XCTAssertEqual(
                sportKeyDisplayName(key, facets: [facet(key, served)]), served,
                "the repair changed \"\(served)\", which was already right"
            )
        }
    }

    /// An empty or whitespace `name` is a served value too, and it must not win
    /// — a blank grey line is a worse answer than the shared rule's.
    func testABlankServedNameFallsThroughRatherThanPrintingNothing() {
        XCTAssertEqual(sportKeyDisplayName("baseball_mlb", facets: [facet("baseball_mlb", "")]), "MLB")
        XCTAssertEqual(sportKeyDisplayName("baseball_mlb", facets: [facet("baseball_mlb", "   ")]), "MLB")
    }

    // MARK: - The fallback, when the facet does not carry the key

    /// `?q=yank` is the case: one team row, zero events, therefore zero facets.
    /// Whatever the row prints then, it may not be the key.
    func testWithNoFacetTheLabelIsNeverAShortenedKey() {
        for row in corpus {
            let label = sportKeyDisplayName(row.key, facets: [])
            XCTAssertNotNil(label)
            let label2 = label ?? ""
            XCTAssertFalse(
                label2.contains("_"),
                "\(row.key) printed \"\(label2)\" — an underscore is the raw enum reaching a reader"
            )
            XCTAssertFalse(
                label2.isEmpty,
                "\(row.key) printed nothing; the row would draw a blank grey gap"
            )
        }
    }

    /// The exact fallback values, written out. A rule asserted only by its
    /// properties ("no underscore") passes for "Market" too.
    func testTheFallbackLabelsAreTheSharedRulesOwnAnswers() {
        let expected: [String: String] = [
            "mma_mixed_martial_arts": "MMA",
            "boxing_boxing": "Boxing",
            "soccer_usa_mls": "MLS",
            "baseball_ncaa": "Baseball",
            "basketball_ncaab": "NCAAB",
            "tennis_atp_queens_club_champ": "Tennis",
            "baseball_mlb": "MLB",
            "baseball_milb": "Baseball",
            "americanfootball_nfl": "NFL",
            "icehockey_sweden_hockey_league": "Hockey",
            "cricket_international_t20": "Cricket",
            "soccer_germany_bundesliga2": "Soccer",
            "soccer_spain_segunda_division": "Soccer",
            "cricket_t20_blast": "Cricket",
        ]
        for (key, want) in expected {
            XCTAssertEqual(
                sportKeyDisplayName(key, facets: []), want,
                "\(key) fell through to something other than the shared rule's answer"
            )
        }
    }

    /// ANTI-VACUITY. If the corpus no longer contains the defect, every
    /// assertion above is agreeing with itself. This is the red-before: the
    /// deleted line and the new rule must actually disagree, on most of it.
    func testTheCorpusStillContainsTheDefectTheOldLineProduced() {
        var disagreements = 0
        for row in corpus where shoutedKey(row.key) != row.served {
            disagreements += 1
        }
        XCTAssertGreaterThanOrEqual(
            disagreements, 10,
            "the corpus no longer disagrees with the shouted key — it has been refreshed from the fixed tree and proves nothing"
        )
        // And the three the issue was filed on, by name.
        XCTAssertEqual(shoutedKey("baseball_milb"), "MILB")
        XCTAssertEqual(shoutedKey("icehockey_sweden_hockey_league"), "SWEDEN HOCKEY LEAGUE")
        XCTAssertEqual(shoutedKey("tennis_atp_queens_club_champ"), "ATP QUEENS CLUB CHAMP")
    }

    // MARK: - The event row's fragment (the same defect, one function over)

    /// `sportDisplayName(for:)` kept the LAST token of an unknown key and
    /// shouted it, so search's EVENT rows were worse than its team rows: six
    /// Alcaraz matches on production, five labelled "OPEN" and one "ATP", under
    /// filter pills reading "ATP US Open" and "Tennis Atp"
    /// (`artifacts-native-020/n138-BEFORE-alcaraz.png`).
    func testAnUnknownKeyIsNeverPrintedAsItsLastToken() {
        let fragments: [(key: String, was: String)] = [
            ("tennis_atp_us_open", "OPEN"),
            ("tennis_atp_queens_club_champ", "CHAMP"),
            ("soccer_spain_segunda_division", "DIVISION"),
            ("icehockey_sweden_hockey_league", "LEAGUE"),
            ("cricket_t20_blast", "BLAST"),
            ("baseball_ncaa", "NCAA"),
        ]
        for case let (key, was) in fragments {
            // The deleted line, so this test is about the defect and not about
            // a sentence describing it.
            let lastToken = key.components(separatedBy: "_").last?.uppercased()
            XCTAssertEqual(lastToken, was, "the corpus no longer reproduces the old fallback")
            XCTAssertNotEqual(
                sportDisplayName(for: key), was,
                "\(key) still prints the fragment \"\(was)\""
            )
        }
        XCTAssertEqual(sportDisplayName(for: "tennis_atp_us_open"), "Tennis")
        XCTAssertEqual(sportDisplayName(for: "icehockey_sweden_hockey_league"), "Hockey")
    }

    /// The sixteen keys it does know must not have moved while its fallback did.
    func testTheLeagueAcronymsAreUnchanged() {
        let unchanged: [String: String] = [
            "americanfootball_nfl": "NFL", "americanfootball_ncaaf": "NCAAF",
            "basketball_nba": "NBA", "basketball_ncaab": "NCAAB",
            "basketball_wncaab": "WNCAAB", "basketball_wnba": "WNBA",
            "icehockey_nhl": "NHL", "baseball_mlb": "MLB", "soccer_epl": "EPL",
            "soccer_spain_la_liga": "La Liga", "soccer_germany_bundesliga": "Bundesliga",
            "soccer_italy_serie_a": "Serie A", "soccer_france_ligue_one": "Ligue 1",
            "soccer_usa_mls": "MLS", "soccer_uefa_champs_league": "UCL",
            "mma_mixed_martial_arts": "MMA",
        ]
        for (key, want) in unchanged {
            XCTAssertEqual(sportDisplayName(for: key), want)
            // And both public formatters answer the same thing for them, which
            // is the point of there being one map.
            XCTAssertEqual(sportCategoryDisplayName(key), want)
        }
        XCTAssertEqual(sportDisplayName(for: nil), "")
        XCTAssertEqual(sportDisplayName(for: ""), "")
    }

    /// The served name is only reachable from a row that asks for it, and
    /// `sportDisplayName(for:)` cannot: it takes a key and no facet. So both of
    /// search's rows have to call the facet-aware rule, and a revert to the
    /// key-only one would be silent — correct-but-coarse everywhere, with the
    /// server's "ATP US Open" and "MiLB" thrown away again.
    func testBothOfSearchsRowsAskForTheServedName() throws {
        let search = try appSources().first { $0.path == "Bain Luck/Views/SearchView.swift" }
        let text = try XCTUnwrap(search?.text, "the scan never reached SearchView")
        let asks = text.components(separatedBy: .newlines).filter {
            let code = $0.components(separatedBy: "//").first ?? $0
            return code.contains("sportKeyDisplayName(")
        }
        XCTAssertEqual(
            asks.count, 2,
            "search should ask for the served sport name on exactly two rows (the team row and the event row); found \(asks.count):\n" + asks.joined(separator: "\n")
        )
        for ask in asks {
            XCTAssertTrue(
                ask.contains("facets: viewModel.sportFacets"),
                "a row calls the facet-aware rule with no facets, which is the key-only rule with extra steps: \(ask)"
            )
        }
    }

    /// Onboarding carried two more private copies of that map — nine keys and
    /// eight keys — and the nine-key one SHADOWED the shared function, so a
    /// reader picking a team saw the fragment even after the shared rule was
    /// fixed. If either comes back, the label has six spellings again.
    func testOnboardingHasNoPrivateLeagueMap() throws {
        let onboarding = try appSources().first { $0.path == "Bain Luck/Views/OnboardingView.swift" }
        let text = try XCTUnwrap(onboarding?.text, "the scan never reached OnboardingView")
        for shadow in ["private func sportDisplayName(", "private func displayName("] {
            XCTAssertFalse(
                text.contains(shadow),
                "OnboardingView declares \(shadow) again — it shadows the shared rule"
            )
        }
    }

    // MARK: - Degenerate input

    func testNoKeyMeansNoLineRatherThanTheWordMarket() {
        XCTAssertNil(sportKeyDisplayName(nil, facets: []))
        XCTAssertNil(sportKeyDisplayName("", facets: []))
    }

    // MARK: - The tree scan

    /// The class here is "someone shortens a sport key by hand again" — #5723
    /// found the market-category label written four times, and its scan is
    /// keyed on the CATEGORY vocabulary (`llmSportCategory`, `sportCategor`),
    /// which is why the team row's `sportKey` shape walked past it. This scan
    /// is about the SHAPE instead: splitting a key on "_" and casing the
    /// result is not a label, wherever it appears.
    private var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    private func appSources() throws -> [(path: String, text: String)] {
        let root = projectRoot
        let e = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        var out: [(String, String)] = []
        while let url = e?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            let rel = url.path.replacingOccurrences(of: root.path + "/", with: "")
            guard !rel.hasPrefix("BainLuckTests/") else { continue }
            out.append((rel, try String(contentsOf: url, encoding: .utf8)))
        }
        return out
    }

    /// Lines that split a key on "_" AND shout the result. Comments are
    /// stripped first — #5709's scan went red on the very fix that documented
    /// the line it deleted, and a guard that cannot tell a defect from a
    /// description of one applies its pressure to the explanation.
    ///
    /// Walked line by line rather than matched with one screen-wide pattern:
    /// a regex spanning newlines across a 2,000-line view is the ReDoS CodeQL
    /// stopped #5760 for.
    private func shoutedKeySites(in text: String) -> [(index: Int, line: String)] {
        text.components(separatedBy: .newlines).enumerated().compactMap { i, raw in
            let code = raw.components(separatedBy: "//").first ?? raw
            guard code.contains("separatedBy: \"_\"") || code.contains("separator: \"_\"") else { return nil }
            guard code.contains(".uppercased()") || code.contains(".capitalized") else { return nil }
            // The shared rule's own last-resort arm is allowed to case a key:
            // that IS the single source this scan exists to funnel people into.
            guard !code.contains("toTitleCaseAcronymSafe") else { return nil }
            return (i, code)
        }
    }

    func testTheScanCanSeeTheTreeItIsAbout() throws {
        let sources = try appSources()
        XCTAssertGreaterThan(sources.count, 100, "far too few Swift files to be this project")
        for control in [
            "Bain Luck/Views/SearchView.swift",
            "Bain Luck/Views/OnboardingView.swift",
            "Bain Luck/Utilities/SportDisplayNames.swift",
        ] {
            XCTAssertTrue(
                sources.contains { $0.path == control },
                "the scan never reached \(control)"
            )
        }
    }

    func testTheScanWouldHaveCaughtTheLineThisShipDeleted() {
        let before = """
        if let sport = team.sportKey {
            Text(sport.split(separator: "_").dropFirst().joined(separator: " ").uppercased())
                .font(.caption2).foregroundStyle(.secondary)
        }
        """
        XCTAssertEqual(shoutedKeySites(in: before).count, 1, "the scan cannot see the shape it is about")

        let after = """
        if let sport = sportKeyDisplayName(team.sportKey, facets: viewModel.sportFacets) {
            Text(sport)
        }
        """
        XCTAssertEqual(shoutedKeySites(in: after).count, 0, "the scan reports the fixed form as a defect")

        // A key being lower-cased to look something up is not a label.
        XCTAssertEqual(shoutedKeySites(in: "let family = key.split(separator: \"_\").first?.lowercased()").count, 0)
    }

    func testNoAppFileShortensASportKeyIntoALabel() throws {
        var offenders: [String] = []
        for source in try appSources() {
            for site in shoutedKeySites(in: source.text) {
                offenders.append("\(source.path):\(site.index + 1) — \(site.line.trimmingCharacters(in: .whitespaces))")
            }
        }
        XCTAssertTrue(
            offenders.isEmpty,
            "a sport key is being shortened into a label again; route it through sportKeyDisplayName:\n" + offenders.joined(separator: "\n")
        )
    }

    /// Onboarding's variant row had the other shape of the same defect: the
    /// served name with the RAW key as its fallback, underscores and all. Its
    /// reach is unmeasured — the endpoint is behind a session, so this is the
    /// mechanism, not a claim that a reader has met it.
    func testOnboardingsVariantFallbackIsNotTheRawKey() {
        XCTAssertEqual(sportKeyDisplayName("baseball_milb", facets: []), "Baseball")
        XCTAssertNotEqual(sportKeyDisplayName("baseball_milb", facets: []), "baseball_milb")
    }
}
