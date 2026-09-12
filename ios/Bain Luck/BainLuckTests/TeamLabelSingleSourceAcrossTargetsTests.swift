import XCTest
@testable import Bain_Luck

/// #5709 — ONE RULE FOR A TEAM'S SHORT LABEL, ACROSS EVERY TARGET.
///
/// THE DEFECT. The widget and the watch each derived a club's label themselves:
///
///     event.homeTeamData?.abbreviation
///         ?? String(event.homeTeam.split(separator: " ").last ?? "")
///
/// which labels a club with the kind of club it is whenever the server sends no
/// abbreviation — `Girona FC` → **FC**, `Cádiz CF` → **CF**, `Real Sociedad B` →
/// **B**, straight onto a home screen. Measured on the widget's own endpoint
/// (`/api/feed?limit=100`, 2026-09-12): 186 team slots, 103 with no served
/// abbreviation so the fallback fires, 8 of those rendering 1–2 glyphs.
///
/// WHY A TREE SCAN AND NOT A UNIT TEST ON THE TWO LINES. This is the FOURTH
/// independent implementation of one rule — the phone (#5651), the web hero, the
/// web chart axis (#4285) and these targets — and ux/1218 and native/134 found
/// their halves on the same day without either fix reaching the other's surface.
/// The class is "somebody writes a fifth", so the assertion has to be about the
/// tree, not about the lines we happened to fix. This is #5709's own acceptance
/// item 3 and mirrors #4285's suggested-scope item 2 on the web side.
///
/// The widget target cannot be reached from `BainLuckTests` (separate target,
/// and `TeamShortName`'s behaviour is already covered by `TeamShortNameTests`
/// and `TeamShortNamePairTests`), so what is testable here is the *source*: does
/// any target still shorten a team name by hand.
final class TeamLabelSingleSourceAcrossTargetsTests: XCTestCase {

    /// The iOS project root — `ios/Bain Luck/` — walked from this test's own
    /// location, the idiom `MarketMapColumnHeaders5656Tests` established.
    private var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    /// Deriving a team's short label by taking the last whitespace-separated
    /// token. Every known instance of this bug is spelled one of these two ways.
    private let handRolledShorteners = [
        ".split(separator: \" \").last",
        ".components(separatedBy: \" \").last",
    ]

    /// Files that STILL carry the defect, with the reason each is not fixed yet.
    ///
    /// This is an allowlist that expires: `testTheAllowlistDoesNotRot` fails if
    /// an entry stops matching, so whoever fixes the watch half is told to delete
    /// its line rather than leaving a guard that silently protects nothing.
    ///
    /// The watchOS platform SDK is not installed on the build machines:
    /// `xcodebuild -scheme "BainLuckWatch Watch App"` fails with *"watchOS 26.5
    /// is not installed"*, so the watch PRODUCT cannot be built or run here, and
    /// `TeamShortName` is not a member of the watch targets the way it now is of
    /// `BainLuckWidget`.
    ///
    /// These sources are NOT invisible, though, and the distinction cost a wrong
    /// claim before it was measured: they compile as members of **`BainLuckTests`**
    /// (`SwiftCompile … WatchFeedModels.swift (in target 'BainLuckTests')`), which
    /// is exactly how the M5 mutant below was caught type-checking. So a watch fix
    /// would be type-checked, but could not be exercised on a watch by anyone
    /// here, and would need membership added to targets no gate can build.
    /// That is the reason for the deferral — not invisibility. Tracked on #5709.
    private let knownOutstanding = [
        "BainLuckWatch Watch App/WatchFeedModels.swift",
        "BainLuckWatch Watch App/WatchLiveView.swift",
        "BainLuckWatch Watch App/BainLuckComplication.swift",
    ]

    /// Every Swift file in the project, as (path-relative-to-root, contents).
    private func swiftSources() throws -> [(String, String)] {
        let root = projectRoot
        let e = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        var out: [(String, String)] = []
        while let url = e?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            let rel = url.path.replacingOccurrences(of: root.path + "/", with: "")
            // This file quotes the defect in its own documentation.
            if rel.hasSuffix("TeamLabelSingleSourceAcrossTargetsTests.swift") { continue }
            out.append((rel, try String(contentsOf: url, encoding: .utf8)))
        }
        return out
    }

    /// A team-label derivation, as opposed to a player's surname or initials —
    /// which are a different question entirely (#4623/#4624) and are NOT in
    /// scope. The discriminator is the variable being shortened.
    ///
    /// COMMENTS ARE STRIPPED FIRST, and that is not a nicety. On its very first
    /// run this scan failed on `WidgetAPIClient.swift` — the file it had just
    /// been written to certify — because the fix's own comment QUOTES the line
    /// it removed, so that a later reader can see what was wrong. A guard that
    /// cannot tell a defect from a description of a defect punishes documenting
    /// the fix, and the pressure it applies is to delete the explanation.
    private func shortensATeamName(_ line: String) -> Bool {
        let code = line.components(separatedBy: "//").first ?? line
        guard handRolledShorteners.contains(where: { code.contains($0) }) else { return false }
        let lower = code.lowercased()
        return lower.contains("team") && !lower.contains("player")
    }

    // MARK: - Anti-vacuity

    /// If this fails, every assertion below is scanning an empty set and means
    /// nothing — the failure mode of every source scan.
    func testTheScanCanSeeTheTreeItIsAbout() throws {
        let sources = try swiftSources()
        XCTAssertGreaterThan(sources.count, 100, "the scan found far too few Swift files to be this project")
        // Control: files that certainly exist, one per target the scan must reach.
        for control in [
            "Bain Luck/Utilities/TeamShortName.swift",
            "BainLuckWidget/WidgetAPIClient.swift",
            "BainLuckWatch Watch App/WatchFeedModels.swift",
        ] {
            XCTAssertTrue(
                sources.contains { $0.0 == control },
                "the scan never reached \(control) — it is not walking the whole project"
            )
        }
        // Control on the PATTERN, not just the files: the matcher must actually
        // fire on the known defect, or a typo in it would pass everything.
        let watch = try XCTUnwrap(sources.first { $0.0 == "BainLuckWatch Watch App/WatchFeedModels.swift" })
        XCTAssertTrue(
            watch.1.split(separator: "\n").contains { shortensATeamName(String($0)) },
            "the matcher no longer recognises the defect it was written for"
        )
    }

    // MARK: - The rule

    func testNoTargetShortensATeamNameByHand() throws {
        var offenders: [String] = []
        for (path, contents) in try swiftSources() {
            guard !knownOutstanding.contains(path) else { continue }
            for (i, line) in contents.split(separator: "\n", omittingEmptySubsequences: false).enumerated()
            where shortensATeamName(String(line)) {
                offenders.append("\(path):\(i + 1)")
            }
        }
        XCTAssertEqual(
            offenders, [],
            """
            A target is deriving a team's short label itself instead of calling \
            TeamShortName. That is how 'Girona FC' becomes 'FC' — see #5709, \
            #5651 and #4285, which are the same rule written four times. Call \
            TeamShortName.abbreviationPair / shortPair, and add the file to that \
            target's membershipExceptions in project.pbxproj if it cannot see it.
            """
        )
    }

    func testTheWidgetAsksTheSharedRule() throws {
        let sources = try swiftSources()
        let client = try XCTUnwrap(sources.first { $0.0 == "BainLuckWidget/WidgetAPIClient.swift" }).1
        XCTAssertTrue(
            client.contains("TeamShortName.abbreviationPair"),
            "the widget stopped asking TeamShortName for its labels — #5709"
        )
        // The pair form specifically: a single-name call would fix the visible
        // half of this bug and silently keep #3430's (both sides of a derby
        // drawing the same label).
        XCTAssertTrue(
            client.contains("awayServed:") && client.contains("homeServed:"),
            "the widget stopped passing the SERVED abbreviations, so it now overrides them — #5709"
        )
    }

    /// `TeamShortName` can only be called from the widget if it is a member of
    /// that target. Xcode 16 synchronized groups make filesystem presence the
    /// membership rule, so a file living under the app folder needs an explicit
    /// exception — and deleting that line is a silent way to break the build's
    /// premise.
    func testTeamShortNameIsAMemberOfTheWidgetTarget() throws {
        let pbxproj = try String(
            contentsOf: projectRoot.appendingPathComponent("Bain Luck.xcodeproj/project.pbxproj"),
            encoding: .utf8
        )
        guard let widgetBlock = pbxproj.range(of: "Exceptions for \"Bain Luck\" folder in \"BainLuckWidget\" target"),
              let end = pbxproj.range(of: ");", range: widgetBlock.upperBound..<pbxproj.endIndex) else {
            return XCTFail("could not find the BainLuckWidget membership exception set in project.pbxproj")
        }
        let block = String(pbxproj[widgetBlock.upperBound..<end.lowerBound])
        XCTAssertTrue(
            block.contains("Utilities/TeamShortName.swift"),
            "TeamShortName is no longer a member of BainLuckWidget, so the widget cannot call it — #5709"
        )
    }

    // MARK: - What the widget will actually draw

    /// The eight production specimens, through the exact call the widget makes.
    ///
    /// A widget cannot be photographed by `tools/native-shoot.sh` — the rig
    /// drives the app, and there is no production URL for a home screen — so
    /// this is the rendered-output check that stands in for the LOOK: the string
    /// on the left is what `Text(game.awayAbbrev)` printed before, the string on
    /// the right is what it prints now. Every one of these was observed on
    /// `/api/feed?limit=100` on 2026-09-12 with no served abbreviation.
    func testTheEightMeasuredSpecimensStopNamingTheClubType() {
        let cases: [(name: String, opponent: String, wasDrawn: String, nowDrawn: String)] = [
            ("Girona FC",           "Real Madrid",      "FC", "GIR"),
            ("Grazer AK",           "Rheindorf Altach", "AK", "GRA"),
            ("Chesterfield FC",     "Barnet",           "FC", "CHE"),
            ("Stockport County FC", "Wigan Athletic",   "FC", "STO"),
            ("Cádiz CF",            "Almeria",          "CF", "CÁD"),
            ("Andorra CF",          "Real Sociedad B",  "CF", "AND"),
            ("Real Sociedad B",     "Andorra CF",       "B",  "REA"),
            ("Västerås SK",         "Örgryte IS",       "SK", "VÄS"),
        ]
        for c in cases {
            let drawn = TeamShortName.abbreviationPair(away: c.name, home: c.opponent).away
            XCTAssertEqual(drawn, c.nowDrawn, "\(c.name) draws the wrong label on the widget")
            XCTAssertNotEqual(drawn, c.wasDrawn, "\(c.name) is still drawn as \(c.wasDrawn) — #5709")
            // The point of the ship, stated independently of the expected value:
            // no reader is handed one or two glyphs for a club again.
            XCTAssertGreaterThanOrEqual(
                drawn.count, 3,
                "\(c.name) still renders \(drawn.count) glyph(s) on a home screen"
            )
        }
    }

    /// A served abbreviation still wins. The ship must not start overriding the
    /// server on the 83 of 186 measured slots that carry one.
    func testAServedAbbreviationIsStillPreferred() {
        let pair = TeamShortName.abbreviationPair(
            away: "Girona FC",
            home: "Real Madrid",
            awayServed: "GIR",
            homeServed: "RMA"
        )
        XCTAssertEqual(pair.away, "GIR")
        XCTAssertEqual(pair.home, "RMA")
    }

    // MARK: - The allowlist must expire

    func testTheAllowlistDoesNotRot() throws {
        let sources = try swiftSources()
        for path in knownOutstanding {
            let file = try XCTUnwrap(
                sources.first { $0.0 == path },
                "allowlisted file \(path) no longer exists — delete its entry"
            )
            let stillBroken = file.1
                .split(separator: "\n", omittingEmptySubsequences: false)
                .contains { shortensATeamName(String($0)) }
            XCTAssertTrue(
                stillBroken,
                """
                \(path) no longer derives a team name by hand — good. Delete it \
                from `knownOutstanding` so this guard starts protecting it, and \
                close #5709 when the list is empty.
                """
            )
        }
    }
}
