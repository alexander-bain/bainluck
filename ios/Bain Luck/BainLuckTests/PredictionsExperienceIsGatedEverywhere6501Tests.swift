import XCTest
@testable import Bain_Luck

/// #6501 — THE SIGN-IN WALL WAS STILL SELLING THE FEATURE THE SAME BUILD HID.
///
/// #6445 put the Higher/Lower experience behind
/// `ReleaseSurfaces.predictionsExperienceEnabled` and converted three call
/// sites: Discover's challenge card, Discover's resolution digest, and My
/// Stuff's accuracy/streak summary. It shipped with NO test. On build 13
/// (master `2ede802a7`, iPhone 17 simulator, `bainluck://my-stuff` signed out,
/// `artifacts-native-020/b4-mystuff.png`) two more call sites were still live:
///
///   * the signed-out wall's headline, "Your Predictions, Your Teams", set in
///     largeTitle black — the loudest type on the screen — and two of its four
///     benefit cards, "Prediction streaks" and "Prediction history". Half the
///     app's pitch for signing in was a feature the same binary switched off.
///     A reader who signed in on the strength of those rows found neither.
///   * `b4-discover-toolbar.png`: a "Stats" button in Discover's navigation
///     bar, top-right of the FIRST screen, linking `Route.predictionStats` —
///     the very destination #6445 hid. #6445 emptied the feed BODY and left an
///     advertised tap target in the chrome above it.
///
/// ## Why this test is a reachability scan and not four string assertions
///
/// 🔴 The bug was not two views. It was that `ReleaseSurfaces` DOCUMENTED a
/// closed class — "turning this back on is the whole restore: no other edit is
/// needed" — while two members of that class were unconverted. A guard that
/// pins the five known sites passes the moment someone adds a sixth, which is
/// exactly how 4 and 5 arrived. So the invariant asserted here is general:
///
///     no reference to the predictions experience exists outside a
///     `ReleaseSurfaces.predictionsExperienceEnabled` block
///
/// enforced by brace-matching from the flag, so a new NavigationLink anywhere
/// in these views fails without anyone updating this file. `Route.predictionStats`
/// is the load-bearing needle: it is the one token every entry point must
/// contain, and it cannot be typed inline the way a caption can.
///
/// A scan and not a behaviour test because the routing lives in `View` bodies
/// no test can instantiate headlessly, and CI compiles no Swift (#4302).
/// Comments are stripped first so the prose this fix just wrote — which names
/// every string below — cannot satisfy a claim about code.
final class PredictionsExperienceIsGatedEverywhere6501Tests: XCTestCase {

    // MARK: - Reading the two views

    private func source(_ view: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent(view)
        return try Self.stripped(String(contentsOf: url, encoding: .utf8))
    }

    /// Line comments removed, then ALL whitespace, so an expectation never
    /// encodes where the author happened to wrap a line.
    static func stripped(_ text: String) -> String {
        text
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// Internal, not private, because `InlineGuessSlotsAreGated7075Tests` runs
    /// the same scan against a different needle (#7075) and a second copy of
    /// the brace matcher is the duplication this repo keeps paying for.
    static let flag = "ifReleaseSurfaces.predictionsExperienceEnabled"

    /// Every character index covered by a gated block.
    ///
    /// From each occurrence of the flag, scan forward to the block's opening
    /// brace and brace-match to its close. Written to tolerate BOTH real gate
    /// shapes in the tree: the bare `if flag {` of Discover, and the
    /// comma-condition `if flag, let stats = …, stats.total > 0 {` of My
    /// Stuff's summary. Anything before the first `{` is a condition list, so
    /// braces are only counted once the body has been entered.
    ///
    /// `needle` defaults to this file's flag; #7075 passes its own guard token,
    /// which has the identical comma-condition shape.
    static func gatedRanges(in code: String, from needle: String = flag) -> [Range<String.Index>] {
        var ranges: [Range<String.Index>] = []
        var cursor = code.startIndex
        while let hit = code.range(of: needle, range: cursor..<code.endIndex) {
            guard let open = code[hit.upperBound...].firstIndex(of: "{") else { break }
            var depth = 0
            var i = open
            var close: String.Index?
            while i < code.endIndex {
                if code[i] == "{" { depth += 1 }
                if code[i] == "}" {
                    depth -= 1
                    if depth == 0 { close = i; break }
                }
                i = code.index(after: i)
            }
            guard let end = close else { break }
            ranges.append(hit.lowerBound..<code.index(after: end))
            cursor = code.index(after: end)
        }
        return ranges
    }

    private static func occurrences(
        of needle: String, in code: String
    ) -> [Range<String.Index>] {
        var found: [Range<String.Index>] = []
        var cursor = code.startIndex
        while let hit = code.range(of: needle, range: cursor..<code.endIndex) {
            found.append(hit)
            cursor = hit.upperBound
        }
        return found
    }

    /// Every occurrence of `needle` that no gated block contains.
    private func ungated(_ needle: String, in code: String) -> Int {
        let gates = Self.gatedRanges(in: code)
        return Self.occurrences(of: needle, in: code).filter { hit in
            !gates.contains { $0.lowerBound <= hit.lowerBound && hit.upperBound <= $0.upperBound }
        }.count
    }

    // MARK: - Anti-vacuity: the scan reads real files and the matcher works

    /// Without this, every assertion below passes on an empty string.
    func testTheScanReadsBothViewsAndFindsTheFlagInEach() throws {
        let myStuff = try source("MyStuffView.swift")
        let discover = try source("DiscoverView.swift")

        XCTAssertTrue(myStuff.contains("privatevarsignInView:someView"),
                      "the scan is not reading MyStuffView.swift")
        XCTAssertTrue(discover.contains("navigationTitle(\"Discover\")"),
                      "the scan is not reading DiscoverView.swift")

        XCTAssertFalse(Self.gatedRanges(in: myStuff).isEmpty,
                       "no gated block found in MyStuffView — the matcher is broken")
        XCTAssertFalse(Self.gatedRanges(in: discover).isEmpty,
                       "no gated block found in DiscoverView — the matcher is broken")
    }

    /// The matcher must be able to say NO. A synthetic pair proves it reports
    /// an ungated occurrence as ungated and a gated one as gated — otherwise
    /// `ungated(...) == 0` below would be true of any input.
    func testTheMatcherDistinguishesGatedFromUngated() {
        let gated = Self.stripped("""
        if ReleaseSurfaces.predictionsExperienceEnabled {
            NavigationLink(value: Route.predictionStats) { Text("x") }
        }
        """)
        let loose = Self.stripped("""
        NavigationLink(value: Route.predictionStats) { Text("x") }
        """)
        XCTAssertEqual(ungated("Route.predictionStats", in: gated), 0,
                       "a gated link was reported ungated")
        XCTAssertEqual(ungated("Route.predictionStats", in: loose), 1,
                       "an ungated link was reported gated — the scan can only say yes")
    }

    /// The comma-condition shape must brace-match too: My Stuff's summary gate
    /// carries two more conditions before its body, and a matcher that took the
    /// first `{` as the body's would close on the wrong brace.
    func testTheMatcherHandlesTheCommaConditionGate() {
        let code = Self.stripped("""
        if ReleaseSurfaces.predictionsExperienceEnabled,
           let stats = predictionStats, stats.total > 0 {
            Section { NavigationLink(value: Route.predictionStats) { Text("x") } }
        }
        NavigationLink(value: Route.predictionStats) { Text("outside") }
        """)
        XCTAssertEqual(ungated("Route.predictionStats", in: code), 1,
                       """
                       expected exactly the trailing link to read as ungated: \
                       the comma-condition gate must cover its nested Section \
                       and must not swallow what follows it.
                       """)
    }

    // MARK: - The invariant

    /// The general rule. A sixth entry point fails here with no edit to this file.
    func testNoNavigationToPredictionStatsEscapesTheFlag() throws {
        for view in ["MyStuffView.swift", "DiscoverView.swift"] {
            let code = try source(view)
            XCTAssertEqual(
                ungated("Route.predictionStats", in: code), 0,
                """
                \(view) navigates to PredictionStatsView outside \
                ReleaseSurfaces.predictionsExperienceEnabled. On build 13 this \
                was DiscoverView's top-right "Stats" toolbar button, left in the \
                navigation bar when #6445 emptied the feed body beneath it. \
                Every entry point to a hidden surface reads the flag, or the \
                flag does not hide the surface.
                """
            )
        }
    }

    /// The wall's two prediction perks. They carry no `Route`, so the rule
    /// above cannot see them: what they promote is the feature, not a link.
    func testTheSignedOutWallDoesNotSellTheHiddenExperience() throws {
        let code = try source("MyStuffView.swift")
        for perk in ["\"Predictionstreaks\"", "\"Predictionhistory\""] {
            XCTAssertEqual(
                ungated(perk, in: code), 0,
                """
                the signed-out wall advertises \(perk) unconditionally. While \
                this was true, two of the four reasons the app gave a reader to \
                sign in were features that same build hid.
                """
            )
        }
    }

    /// The perks must still be REACHABLE — the flag hides the surface, it does
    /// not delete it (`ReleaseSurfaces`: "a flag and not a deletion"). A sweep
    /// that removed the two rows outright would pass the test above and would
    /// make restoring the experience a re-implementation, which is the one
    /// thing #6445 forbids.
    func testThePerksSurviveBehindTheFlagRatherThanBeingDeleted() throws {
        let code = try source("MyStuffView.swift")
        for perk in ["\"Predictionstreaks\"", "\"Predictionhistory\""] {
            XCTAssertTrue(
                code.contains(perk),
                """
                \(perk) is gone from the wall entirely. Flipping \
                predictionsExperienceEnabled back on must restore the pitch \
                with the feature; it cannot if the row was deleted.
                """
            )
        }
    }

    /// Same argument for the toolbar button: gated, not deleted. Both of
    /// Discover's links to the stats page must still be in the file, or
    /// flipping the flag restores a Discover with no way to reach it.
    func testBothDiscoverEntryPointsSurviveBehindTheFlag() throws {
        let code = try source("DiscoverView.swift")
        XCTAssertEqual(
            Self.occurrences(of: "Route.predictionStats", in: code).count, 2,
            """
            Discover should hold exactly two links to the stats page — the \
            resolution digest and the toolbar button — both gated. A count of \
            1 means one was deleted rather than hidden; 3 or more means a new \
            entry point arrived and this file has not reasoned about it.
            """
        )
        XCTAssertTrue(
            code.contains("Label(\"Stats\",systemImage:\"chart.bar.fill\")"),
            "the toolbar button was deleted rather than gated"
        )
    }

    /// The headline is the largest type on the wall and it led with the hidden
    /// half. Asserted as the exact ternary because both arms must exist: one
    /// string swapped for another would leave the restore incomplete again.
    func testTheHeadlineTracksTheFlagInBothDirections() throws {
        let code = try source("MyStuffView.swift")
        XCTAssertTrue(
            code.contains(
                "Text(ReleaseSurfaces.predictionsExperienceEnabled"
                + "?\"YourPredictions,\\nYourTeams\""
                + ":\"YourTeams,\\nYourFeed\")"),
            """
            the wall's headline does not read the flag. Before #6501 it was a \
            constant "Your Predictions,\\nYour Teams" — largeTitle black, above \
            two perks that no longer exist in this build.
            """
        )
    }
}
