import XCTest
@testable import Bain_Luck

/// #5723 — ONE RULE FOR A MARKET'S CATEGORY LABEL.
///
/// THE DEFECT, IN TWO HALVES.
///
/// **A — the shared helper's own fallback returned a lowercase label.**
/// `sportCategoryDisplayName` ended with
///
///     return properTitleCase(key.replacingOccurrences(of: "_", with: " "))
///
/// and `properTitleCase` is the wrong one of this codebase's two acronym-aware
/// formatters: it *repairs* acronyms inside an already-cased display string and
/// deliberately leaves unrecognised words alone. So every key that missed the
/// three maps above it arrived lowercase and left lowercase — `table_tennis` →
/// "table tennis", `rugby` → "rugby", `other` → "other" — on every surface that
/// had adopted the shared rule, including Alex's own futures card. That made
/// #1938's fix *worse* than the `.capitalized` it replaced for those keys:
/// "Rugby" became "rugby".
///
/// **B — three surfaces never adopted the helper.** Search rows, My Stuff rows
/// and the futures hero pill still shortened the job themselves, so searching
/// "ufc" returned ten rows labelled **`Mma`** — Alex's bug report 145, which
/// #1938 closed on 2026-09-08 after checking three call sites that did not
/// include this tab — and a table-tennis page's hero pill read **`TABLE_TENNIS`**,
/// the raw underscore enum `sportCategoryDisplayName`'s docstring exists to
/// prevent.
///
/// REACH, measured on production (`db-query`, 2026-09-12) over the 43,632
/// categorised **open** `futures_markets`: defect A reached 4,351 (10.0%),
/// defect B reached 2,864 (6.6%).
///
/// WHY A TREE SCAN SITS BESIDE THE UNIT TESTS. One label had four spellings
/// across the app at once (Browse, futures card, search row, hero pill), and
/// this is the third display rule in this codebase to be written more than
/// once — #3374 (team names, 39 copies), #5709 (widget and watch, 6 copies),
/// and this. The class is "somebody writes a fifth", so one assertion has to be
/// about the tree rather than about the lines that happened to be fixed.
final class SportCategoryLabelSingleSourceTests: XCTestCase {

    // MARK: - The corpus

    /// Every distinct `llm_sport_category` on an OPEN futures market, with its
    /// market count, read from production on 2026-09-12:
    ///
    ///     SELECT llm_sport_category, COUNT(*) FROM futures_markets
    ///     WHERE llm_sport_category IS NOT NULL AND status = 'open'
    ///     GROUP BY 1 ORDER BY 2 DESC
    ///
    /// A hand-picked list of keys would only prove the formatter agrees with
    /// whichever keys its author thought of; this is the population a reader can
    /// actually meet. The counts are carried so a failure can say how many
    /// markets it is about.
    private let openMarketCategories: [(key: String, markets: Int)] = [
        ("soccer", 12526), ("politics", 7413), ("football", 4943),
        ("table_tennis", 2635), ("economics", 2405), ("tennis", 2111),
        ("entertainment", 1636), ("other", 1467), ("tech", 1418),
        ("esports", 1386), ("baseball", 1314), ("weather", 971),
        ("cricket", 845), ("basketball", 735), ("geopolitics", 586),
        ("hockey", 336), ("mma", 228), ("motorsports", 109), ("legal", 81),
        ("golf", 73), ("health", 66), ("rugby", 55), ("boxing", 39),
        ("darts", 36), ("chess", 24), ("culture", 18), ("lacrosse", 12),
        ("cycling", 11), ("olympics", 11), ("handball", 10), ("crypto", 10),
        ("aussierules", 3), ("sailing", 3), ("pickleball", 2), ("auto", 2),
        ("watchmaking", 2), ("energy", 2), ("business", 1), ("real_estate", 1),
        ("retail", 1), ("adventure", 1), ("softball", 1), ("space", 1),
    ]

    /// Keys that reach the helper through a sport key rather than an
    /// `llm_sport_category`, which is the other half of what it is asked to map.
    private let sportKeyCorpus = [
        "americanfootball_nfl", "americanfootball_other", "basketball_nba",
        "baseball_mlb", "icehockey_nhl", "soccer_uefa_champs_league",
        "soccer_epl", "mma_mixed_martial_arts", "mma_other", "tennis_other",
        "golf_other", "soccer_other", "rugby_other",
    ]

    // MARK: - The label invariants

    /// The two things a reader must never be shown. Stated as invariants over
    /// the whole measured population rather than as expected strings, because
    /// the point is that no key — not even one nobody listed — escapes.
    func testNoOpenMarketCategoryRendersAnUnderscoreOrStaysLowercase() {
        var offenders: [String] = []
        for (key, markets) in openMarketCategories {
            let label = sportCategoryDisplayName(key)
            if label.contains("_") {
                offenders.append("\(key) -> \"\(label)\" (underscore; \(markets) open markets)")
            }
            // `label == label.lowercased()` is the test for "nothing was
            // capitalised at all". It is what defect A actually produced.
            if label == label.lowercased() {
                offenders.append("\(key) -> \"\(label)\" (all lowercase; \(markets) open markets)")
            }
            XCTAssertFalse(label.isEmpty, "\(key) rendered an empty label")
        }
        XCTAssertEqual(
            offenders, [],
            "a category label reached a reader as a raw key or an uncapitalised one"
        )
    }

    func testSportKeysAlsoResolveToALabelAndNotAKey() {
        for key in sportKeyCorpus {
            let label = sportCategoryDisplayName(key)
            XCTAssertFalse(label.contains("_"), "\(key) -> \"\(label)\" leaked an underscore")
            XCTAssertNotEqual(
                label, label.lowercased(),
                "\(key) -> \"\(label)\" was never capitalised"
            )
        }
    }

    /// The specific strings this issue is about, so a regression names itself
    /// rather than arriving as a generic invariant failure.
    func testTheReportedLabels() {
        // Alex, bug report 145 / #1938 — the half that was still live in Search.
        XCTAssertEqual(sportCategoryDisplayName("mma"), "MMA")
        // The hero pill and the search row on 2,635 open markets.
        XCTAssertEqual(sportCategoryDisplayName("table_tennis"), "Table Tennis")
        // Defect A's largest non-underscore contributor — 1,467 open markets.
        XCTAssertEqual(sportCategoryDisplayName("other"), "Other")
        XCTAssertEqual(sportCategoryDisplayName("rugby"), "Rugby")
        XCTAssertEqual(sportCategoryDisplayName("chess"), "Chess")
        XCTAssertEqual(sportCategoryDisplayName("real_estate"), "Real Estate")
        // Not moved by this change: the maps above the fallback still win.
        XCTAssertEqual(sportCategoryDisplayName("americanfootball_nfl"), "NFL")
        XCTAssertEqual(sportCategoryDisplayName("americanfootball_other"), "Football")
        XCTAssertEqual(sportCategoryDisplayName("politics"), "Politics")
        XCTAssertEqual(sportCategoryDisplayName("esports"), "Esports")
        // Nil is still the generic label, which is why the two rows that want
        // "Futures" map the optional themselves instead of passing it through.
        XCTAssertEqual(sportCategoryDisplayName(nil), "Market")
        XCTAssertEqual(sportCategoryDisplayName(""), "Market")
    }

    /// The fallback must be the raw-key formatter, not the repair-only one.
    /// This is the mechanism of defect A stated directly: if someone swaps it
    /// back, `properTitleCase` returns its input unchanged for these words and
    /// this fails, even if the invariants above were somehow satisfied.
    func testTheFallbackIsTheRawKeyFormatterNotTheRepairFormatter() {
        // What the repair-only formatter does with a raw key — unchanged.
        XCTAssertEqual(properTitleCase("table tennis"), "table tennis")
        XCTAssertEqual(properTitleCase("rugby"), "rugby")
        // What the fallback must therefore NOT be doing.
        XCTAssertEqual(sportCategoryDisplayName("table_tennis"), "Table Tennis")
        XCTAssertEqual(sportCategoryDisplayName("rugby"), "Rugby")
    }

    // MARK: - The tree scan

    /// The iOS project root — `ios/Bain Luck/` — walked from this test's own
    /// location, the idiom `TeamLabelSingleSourceAcrossTargetsTests` uses.
    private var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    /// Names that mean "this is the market's category vocabulary".
    private let categoryTokens = [
        "llmSportCategory", "llm_sport_category", "sportCategor",
    ]

    /// Casing operators that are wrong when applied to a raw category key.
    /// `.lowercased()` is absent on purpose: every use of it on this vocabulary
    /// in the tree is building a LOOKUP KEY, never a label.
    private let casingOperators = [".capitalized", ".uppercased()"]

    /// Files that still cased a raw category key themselves, with the reason.
    /// Empty today. Kept — with `testTheAllowlistDoesNotRot` below — so that a
    /// future deferral has a place to be recorded honestly instead of the scan
    /// being loosened to let it through.
    private let knownOutstanding: [String] = []

    private func swiftSources() throws -> [(path: String, text: String)] {
        let root = projectRoot
        let e = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        var out: [(String, String)] = []
        while let url = e?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            let rel = url.path.replacingOccurrences(of: root.path + "/", with: "")
            // This file quotes the defect in its own documentation.
            if rel.hasSuffix("SportCategoryLabelSingleSourceTests.swift") { continue }
            out.append((rel, try String(contentsOf: url, encoding: .utf8)))
        }
        return out
    }

    /// Every place a file cases something, as (0-based line index, line).
    ///
    /// COMMENTS ARE STRIPPED FIRST. #5709's scan failed on its first run against
    /// the very file it certified, because the fix's comment quoted the line it
    /// had deleted. A guard that cannot tell a defect from a description of one
    /// applies its pressure to the explanation, which is the part worth keeping.
    private func casedLabelSites(in text: String) -> [(index: Int, line: String)] {
        text.components(separatedBy: .newlines).enumerated().compactMap { i, raw in
            let code = raw.components(separatedBy: "//").first ?? raw
            guard casingOperators.contains(where: { code.contains($0) }) else { return nil }
            // The shared rule's own output is cased by four Discover cards and
            // the hero pill on purpose — that is the correct form, not a defect.
            guard !code.contains("sportCategoryDisplayName") else { return nil }
            return (i, code)
        }
    }

    /// A casing site is about the category vocabulary if that vocabulary is
    /// named nearby. A WINDOW rather than the line is required, and it is the
    /// difference between a guard that works and one that does not: the Search
    /// row this issue is about bound the key on one line and cased it on the
    /// next, so a line-local scan would have reported the tree clean while the
    /// defect it was written for sat two lines away.
    ///
    /// THE WINDOW COUNTS CODE LINES, NOT LINES, and that is not tidiness. The
    /// first draft counted raw lines and the mutation sweep caught it: reverting
    /// the Search row to `.capitalized` SURVIVED, because this ship's own
    /// four-line explanatory comment now sits between the binding and the cased
    /// line and had eaten the whole window. A guard measured in raw lines gets
    /// weaker every time someone documents a fix next to it — the same
    /// backwards incentive as a scan that cannot tell a defect from a
    /// description of one, and the reason comments are stripped there too.
    private func isAboutACategoryKey(
        _ lines: [String], _ index: Int, window: Int = 4
    ) -> Bool {
        func code(_ i: Int) -> String { lines[i].components(separatedBy: "//").first ?? lines[i] }

        var context = [code(index)]
        if index + 1 < lines.count { context.append(code(index + 1)) }
        var seen = 0
        var i = index - 1
        while i >= 0 && seen < window {
            let c = code(i)
            i -= 1
            guard !c.trimmingCharacters(in: .whitespaces).isEmpty else { continue }
            context.append(c)
            seen += 1
        }
        let joined = context.joined(separator: "\n")
        return categoryTokens.contains { joined.contains($0) }
    }

    // MARK: - Anti-vacuity

    /// If this fails, every scan below is examining an empty set and means
    /// nothing — the failure mode of every source scan.
    func testTheScanCanSeeTheTreeItIsAbout() throws {
        let sources = try swiftSources()
        XCTAssertGreaterThan(
            sources.count, 100,
            "the scan found far too few Swift files to be this project"
        )
        for control in [
            "Bain Luck/Utilities/SportDisplayNames.swift",
            "Bain Luck/Views/SearchView.swift",
            "Bain Luck/Views/FuturesDetailView.swift",
            "Bain Luck/Views/MyStuffView.swift",
            "Bain Luck/Components/FuturesBrowseComponents.swift",
        ] {
            XCTAssertTrue(
                sources.contains { $0.path == control },
                "the scan never reached \(control) — it is not walking the whole project"
            )
        }
    }

    /// The window logic is the load-bearing half of the scan, so it is tested
    /// against the exact two-line shape the Search row had before this fix,
    /// rather than trusted. A scan whose discriminator is never exercised is a
    /// scan that will pass over the next instance too.
    func testTheScanWouldHaveCaughtTheSearchRowsTwoLineShape() {
        let before = """
        HStack(spacing: 6) {
            if let category = market.llmSportCategory ?? market.category {
                Text(category.capitalized)
                    .font(.caption2)
            }
        }
        """
        let lines = before.components(separatedBy: .newlines)
        let sites = casedLabelSites(in: before)
        XCTAssertEqual(sites.count, 1, "the scan did not find the cased line at all")
        XCTAssertTrue(
            isAboutACategoryKey(lines, sites[0].index),
            "the scan found the cased line but did not tie it to the category key one line above"
        )

        // And the correct form must NOT be reported, or the scan is unusable.
        let after = """
        if let category = market.llmSportCategory ?? market.category {
            Text(sportCategoryDisplayName(category))
        }
        """
        XCTAssertEqual(
            casedLabelSites(in: after).count, 0,
            "the scan reports the shared rule's own output as a defect"
        )

        // The four Discover cards upper-case the shared rule deliberately.
        let deliberate = "sportCategoryDisplayName(data.sportName ?? data.llmSportCategory).uppercased()"
        XCTAssertEqual(casedLabelSites(in: deliberate).count, 0)
    }

    /// The regression the mutation sweep found in this scan's first draft: a
    /// later reader explains the fix in a comment, the comment sits between the
    /// binding and the label, and a window measured in raw lines stops reaching
    /// the binding. If this fails, documenting a fix disarms the guard on it.
    func testACommentBetweenTheBindingAndTheLabelDoesNotBlindTheScan() {
        let withComment = """
        if let category = market.llmSportCategory ?? market.category {
            // #5723: `.capitalized` printed the raw key — "ufc" returns
            // ten futures rows all labelled "Mma" (Alex, bug report 145,
            // the half #1938 closed without checking this tab), and a
            // table-tennis row read "Table_Tennis".
            Text(category.capitalized)
        }
        """
        let lines = withComment.components(separatedBy: .newlines)
        let sites = casedLabelSites(in: withComment)
        XCTAssertEqual(sites.count, 1)
        XCTAssertTrue(
            isAboutACategoryKey(lines, sites[0].index),
            "four comment lines were enough to hide the category key from the scan"
        )
    }

    // MARK: - The assertion

    func testNoFileCasesARawCategoryKeyItself() throws {
        var offenders: [String] = []
        for (path, text) in try swiftSources() {
            if knownOutstanding.contains(path) { continue }
            let lines = text.components(separatedBy: .newlines)
            for site in casedLabelSites(in: text)
            where isAboutACategoryKey(lines, site.index) {
                offenders.append(
                    "\(path):\(site.index + 1) — \(site.line.trimmingCharacters(in: .whitespaces))"
                )
            }
        }
        XCTAssertEqual(
            offenders, [],
            """
            a category key is being cased by hand instead of going through \
            sportCategoryDisplayName. That is how one label came to have four \
            spellings (#5723). Call the shared rule, or add the file to \
            knownOutstanding with the reason it cannot be fixed yet.
            """
        )
    }

    /// The other way to write a second rule for this label, and the one the
    /// casing scan above cannot see: calling the raw-key formatter that
    /// `sportCategoryDisplayName` delegates to, instead of the rule itself.
    /// Browse did exactly that in two places and was the fourth spelling.
    ///
    /// The discriminator is the FILE, not the line, and deliberately so: Browse
    /// bound the category into a local called `tag` a hundred lines above the
    /// formatter call, so nothing in that call's neighbourhood named the
    /// vocabulary. A file that handles `llmSportCategory` at all is a file whose
    /// labels belong to this rule.
    ///
    /// `SportDisplayNames.swift` is exempt without being listed, because it is
    /// the delegation itself and never names `llmSportCategory`. So is
    /// `CalibrationViewModel`, which owns a genuinely different vocabulary — the
    /// calibration cohort names, with their own map and their own normalisation
    /// (#1938, #3657) — and likewise never touches this field.
    func testAFileThatHandlesCategoriesUsesTheSharedRuleNotTheFormatterUnderIt() throws {
        var offenders: [String] = []
        for (path, text) in try swiftSources() {
            let lines = text.components(separatedBy: .newlines)
            let handlesCategories = lines.contains { line in
                let code = line.components(separatedBy: "//").first ?? line
                return code.contains("llmSportCategory")
            }
            guard handlesCategories else { continue }
            for (i, line) in lines.enumerated() {
                let code = line.components(separatedBy: "//").first ?? line
                // No trailing paren. `.map(toTitleCaseAcronymSafe)` passes the
                // function itself, and matching on "toTitleCaseAcronymSafe("
                // let exactly that form through — the Browse ROW survived its
                // mutant while the Browse CHIP, one call-shape away, died.
                guard code.contains("toTitleCaseAcronymSafe") else { continue }
                offenders.append("\(path):\(i + 1) — \(code.trimmingCharacters(in: .whitespaces))")
            }
        }
        XCTAssertEqual(
            offenders, [],
            """
            a file that renders market categories reaches past \
            sportCategoryDisplayName to the formatter underneath it. Both then \
            have to be kept in step by hand, which is how "mma" came to render \
            four different ways (#5723). Call the shared rule.
            """
        )
    }

    /// An allowlist must be able to expire. If an entry stops matching — the
    /// file was fixed, renamed or deleted — this fails and tells whoever fixed
    /// it to delete the line, so a deferred file cannot quietly become an
    /// unguarded one.
    func testTheAllowlistDoesNotRot() throws {
        let sources = try swiftSources()
        for path in knownOutstanding {
            guard let file = sources.first(where: { $0.path == path }) else {
                XCTFail("\(path) is on knownOutstanding but is not in the tree — delete the line")
                continue
            }
            let lines = file.text.components(separatedBy: .newlines)
            let stillBad = casedLabelSites(in: file.text)
                .contains { isAboutACategoryKey(lines, $0.index) }
            XCTAssertTrue(
                stillBad,
                "\(path) no longer cases a category key — delete it from knownOutstanding"
            )
        }
    }
}
