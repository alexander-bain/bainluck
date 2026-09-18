import XCTest
@testable import Bain_Luck

/// #6445 — BROWSE WAS STILL PROMOTING THE EXPERIENCE TWO SWEEPS HAD HIDDEN.
///
/// Alex, on the phone on 2026-09-16: "hide Daily Challenge until good". He had
/// already said it on 15 September, and the app had already been swept twice:
///
///   * #6445 gated Discover's "Today's Challenge" card, Discover's resolution
///     digest and My Stuff's accuracy/streak summary.
///   * #6501 found two more — the signed-out wall's two prediction perks and
///     Discover's top-right "Stats" toolbar button — and wrote
///     `PredictionsExperienceIsGatedEverywhere6501Tests`, whose stated invariant
///     is the general one: *no reference to the predictions experience exists
///     outside a `ReleaseSurfaces.predictionsExperienceEnabled` block.*
///
/// Browse's "Daily Challenge / Five probability calls" tile survived both.
///
/// ## Why the general guard did not generalise
///
/// 🔴 A scan enforces its invariant over the needles it looks for, in the files
/// it reads — and #6501's scan is `Route.predictionStats` across
/// `DiscoverView.swift` and `MyStuffView.swift`. Every one of the five sites it
/// converted happens to navigate the STATS page, so `Route.predictionStats` read
/// as "the one token every entry point must contain". Browse navigates
/// `Route.dailyChallenge`, from `LeaguesView.swift`. Wrong needle, wrong file:
/// the sixth site was invisible to the guard written to make a sixth impossible.
///
/// So this file does not pin Browse's tile, and it does not swap one fixed file
/// list for a slightly longer one — that is the same shape of guard, one entry
/// further along, and it is what let Browse through. It WALKS the app source
/// and asks, of every Swift file in it, whether any navigation to either route
/// escapes the flag. A seventh entry point fails here whichever door it uses and
/// whichever file it lands in, with no edit to this file.
///
/// The matcher itself is #6501's, reused rather than rewritten: two
/// differently-worded detectors of one rule is how two surfaces come to
/// disagree.
///
/// ## The one path excluded, and the two that need no excluding
///
/// `Services/NavigationCoordinator.swift` resolves `bainluck://` deep links and
/// calls `navigate(to: .dailyChallenge, tab: .discover)`. That is not a
/// promotion — it is what makes a link ALREADY IN THE WILD still land, which
/// `ReleaseSurfaces` requires ("the destination views stay reachable by route so
/// nothing already linked 404s"). Excluded by path, with this sentence, rather
/// than by a pattern subtle enough to tell a resolution from a promotion — a
/// pattern that subtle is a pattern subtle enough to miss a promotion.
///
/// `Views/Route.swift` (`case .dailyChallenge: DailyChallengeView()`) and
/// `Views/BugReportView.swift` (the case → "Daily Challenge" page-name map) need
/// no exclusion: neither spells a NAVIGATION, so no needle reaches them. The
/// destination table is separately required to survive, by
/// `testTheDestinationStaysRegistered` — hiding a promotion must not orphan the
/// screen.
///
/// A source scan and not a behaviour test because the routing lives in `View`
/// bodies no test can instantiate headlessly, and CI compiles no Swift (#4302).
/// Comments are stripped first, so the prose above — which names every needle
/// below — cannot satisfy a claim about code.
final class BrowseHidesTheChallengeTile6445Tests: XCTestCase {

    // MARK: - Reading the views

    /// `ios/Bain Luck/Bain Luck` — the phone/iPad/Mac app's own source. The
    /// watch app is a sibling target with no reference to either route.
    /// Symlink-resolved via `ProjectTree` — see that file for why a worktree
    /// under `/tmp` turned every relative path here into `/privateViews/…`.
    private static var appRoot: URL {
        ProjectTree.root().appendingPathComponent("Bain Luck")
    }

    /// #6501's stripper: line comments removed, then all whitespace.
    private func source(_ relativePath: String) throws -> String {
        let url = Self.appRoot.appendingPathComponent(relativePath)
        return try PredictionsExperienceIsGatedEverywhere6501Tests
            .stripped(String(contentsOf: url, encoding: .utf8))
    }

    /// Every `.swift` file under the app source, as (path-relative-to-appRoot,
    /// url), in a stable order.
    ///
    /// THROWS rather than returning `[]` when the walk fails — `testTheWalk…`
    /// below names that failure mode ("an `offences == []` is also what a walk
    /// returns when it enumerated nothing") and the old `guard … else
    /// { return [] }` was it. The relative path now comes from `ProjectTree`,
    /// which refuses a file that is not under the root instead of deforming it.
    private static func appSwiftFiles() throws -> [(path: String, url: URL)] {
        try ProjectTree.swiftFiles(under: appRoot, minimumFiles: 100)
    }

    private static func occurrences(of needle: String, in code: String) -> Int {
        var count = 0
        var cursor = code.startIndex
        while let hit = code.range(of: needle, range: cursor..<code.endIndex) {
            count += 1
            cursor = hit.upperBound
        }
        return count
    }

    /// Occurrences of `needle` that no `predictionsExperienceEnabled` block contains.
    private func ungated(_ needle: String, in code: String) -> Int {
        let gates = PredictionsExperienceIsGatedEverywhere6501Tests.gatedRanges(in: code)
        var loose = 0
        var cursor = code.startIndex
        while let hit = code.range(of: needle, range: cursor..<code.endIndex) {
            let covered = gates.contains {
                $0.lowerBound <= hit.lowerBound && hit.upperBound <= $0.upperBound
            }
            if !covered { loose += 1 }
            cursor = hit.upperBound
        }
        return loose
    }

    /// Both doors into the predictions experience. `predictionStats` is
    /// #6501's; `dailyChallenge` is the one Browse used, which no guard had ever
    /// named.
    private static let routeCases = ["predictionStats", "dailyChallenge"]

    /// The ways a Swift call site spells "go to this route", stripped of
    /// whitespace. `%@` is the case name. Each is a real spelling in this tree:
    /// `NavigationLink(value: Route.x)`, `BrowseFeatureCard(route: .x)` and
    /// `navigate(to: .x, tab:)` — the third is the one that would have let a
    /// promotion sidestep the first two.
    private static let navigationSpellings = [
        "Route.%@", "route:.%@", "value:.%@", "to:.%@",
    ]

    private static func needles(for routeCase: String) -> [String] {
        navigationSpellings.map { $0.replacingOccurrences(of: "%@", with: routeCase) }
    }

    /// See the class docstring: deep-link RESOLUTION, not promotion.
    private static let deepLinkResolver = "Services/NavigationCoordinator.swift"

    // MARK: - Anti-vacuity: the scan reads the real file and the matcher works

    /// Without this, every assertion below passes on an empty string. The
    /// tokens are ones only the real file carries.
    func testTheScanReadsBrowseAndFindsItsGate() throws {
        let browse = try source("Views/LeaguesView.swift")

        XCTAssertTrue(browse.contains("navigationTitle(\"Browse\")"),
                      "the scan is not reading LeaguesView.swift")
        XCTAssertTrue(browse.contains("title:\"FuturesMarkets\""),
                      "the scan is not reading LeaguesView's featured grid")
        XCTAssertFalse(
            PredictionsExperienceIsGatedEverywhere6501Tests.gatedRanges(in: browse).isEmpty,
            "no gated block found in LeaguesView — the tile is not behind the flag"
        )
    }

    /// The matcher must be able to say NO on THIS needle. #6501 proved it for
    /// `Route.predictionStats`; a control measured on one needle does not
    /// transfer to a second the matcher has never been run against.
    func testTheMatcherDistinguishesGatedFromUngatedOnTheChallengeRoute() {
        let gated = PredictionsExperienceIsGatedEverywhere6501Tests.stripped("""
        if ReleaseSurfaces.predictionsExperienceEnabled {
            BrowseFeatureCard(title: "Daily Challenge", route: .dailyChallenge)
        }
        """)
        let loose = PredictionsExperienceIsGatedEverywhere6501Tests.stripped("""
        BrowseFeatureCard(title: "Daily Challenge", route: .dailyChallenge)
        """)
        // The stripped call site reads `route:.dailyChallenge`, not
        // `Route.dailyChallenge` — the invariant below scans for both spellings
        // of the same case, so the control exercises the spelling Browse uses.
        XCTAssertEqual(ungated("route:.dailyChallenge", in: gated), 0,
                       "a gated tile was reported ungated")
        XCTAssertEqual(ungated("route:.dailyChallenge", in: loose), 1,
                       "an ungated tile was reported gated — the scan can only say yes")
    }

    // MARK: - The invariant, on both axes

    /// The general rule. Every Swift file in the app, both routes, four
    /// spellings each. A seventh entry point fails here with no edit to this
    /// file, whichever door it uses and whichever file it lands in.
    func testNoEntryPointToThePredictionsExperienceEscapesTheFlag() throws {
        var offences: [String] = []

        for (relative, file) in try Self.appSwiftFiles() {
            if relative == Self.deepLinkResolver { continue }

            let code = try PredictionsExperienceIsGatedEverywhere6501Tests
                .stripped(String(contentsOf: file, encoding: .utf8))

            for routeCase in Self.routeCases {
                for needle in Self.needles(for: routeCase) where ungated(needle, in: code) > 0 {
                    offences.append("\(relative): \(needle)")
                }
            }
        }

        XCTAssertEqual(
            offences, [],
            """
            these navigate to the predictions experience outside \
            ReleaseSurfaces.predictionsExperienceEnabled. On the 2026-09-16 \
            phone build the offence was Browse's "Daily Challenge / Five \
            probability calls" tile in LeaguesView, which survived both #6445 \
            and #6501 because their guard scanned ONE route in TWO named \
            files. Every entry point to a hidden surface reads the flag, or \
            the flag does not hide the surface.
            """
        )
    }

    /// The walk must actually reach the whole app, and must find the call sites
    /// it is judging. An `offences == []` above is also what a walk returns when
    /// it enumerated nothing — the unrunnable-check failure mode.
    func testTheWalkReachesTheWholeAppAndFindsEveryKnownCallSite() throws {
        let files = try Self.appSwiftFiles()
        XCTAssertGreaterThan(files.count, 50, "the walk is not seeing the app tree")

        var found: [String: Int] = [:]
        for (relative, file) in files {
            let code = try PredictionsExperienceIsGatedEverywhere6501Tests
                .stripped(String(contentsOf: file, encoding: .utf8))
            for routeCase in Self.routeCases {
                for needle in Self.needles(for: routeCase) {
                    let hits = Self.occurrences(of: needle, in: code)
                    if hits > 0 { found[relative, default: 0] += hits }
                }
            }
        }

        // The four navigations that exist today. Deleting one, or moving it to
        // a file this list does not name, is a change someone has to look at.
        XCTAssertEqual(
            found,
            [
                "Views/DiscoverView.swift": 2,   // resolution digest, Stats toolbar button
                "Views/MyStuffView.swift": 1,    // accuracy/streak summary
                "Views/LeaguesView.swift": 1,    // Browse's tile — this fix
                "Services/NavigationCoordinator.swift": 1,  // deep-link resolution, excluded above
            ],
            """
            the census of navigations to the predictions experience has moved. \
            A count that FELL means an entry point was deleted rather than \
            gated, and flipping predictionsExperienceEnabled back on no longer \
            restores the surface. A count that ROSE, or a new file, means a new \
            promotion arrived — check it is inside the flag, then update this \
            list deliberately.
            """
        )
    }

    // MARK: - Hidden, not deleted

    /// The tile must still be IN the file. `ReleaseSurfaces` is "a flag and not
    /// a deletion": flipping `predictionsExperienceEnabled` back on has to
    /// restore Browse's entry point along with Discover's and My Stuff's. A
    /// sweep that removed the tile outright would pass the invariant above and
    /// would make restoring it a re-implementation.
    func testTheTileSurvivesBehindTheFlagRatherThanBeingDeleted() throws {
        let browse = try source("Views/LeaguesView.swift")
        XCTAssertEqual(
            Self.occurrences(of: "route:.dailyChallenge", in: browse), 1,
            """
            Browse should hold exactly one link to the Daily Challenge — gated. \
            A count of 0 means the tile was deleted rather than hidden; 2 or \
            more means a second promotion arrived and this file has not \
            reasoned about it.
            """
        )
        XCTAssertTrue(
            browse.contains("title:\"DailyChallenge\",subtitle:\"Fiveprobabilitycalls\""),
            "the tile's own copy is gone — the restore would be a rewrite"
        )
    }

    /// And the destination stays registered. The flag hides a promotion; it must
    /// not orphan the screen, or a saved link — or the flag flip itself — lands
    /// on nothing. This is the positive half the walk above cannot supply: a
    /// destination table that no longer resolves the case draws no navigation,
    /// so it passes every refusal assertion by having nothing to refuse.
    func testTheDestinationStaysRegistered() throws {
        let routes = try source("Views/Route.swift")
        XCTAssertTrue(
            routes.contains("case.dailyChallenge:DailyChallengeView()"),
            """
            Route.swift no longer resolves .dailyChallenge. Hiding the Browse \
            tile must not unregister the screen: #6445 forbids deleting the \
            experience, and bainluck:// links already in the wild resolve here.
            """
        )
    }
}
