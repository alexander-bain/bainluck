import XCTest
import SwiftUI
@testable import Bain_Luck

/// #8820 / #8425 — a chart gutter printed half a team name.
///
/// THE PHOTOGRAPHS: event 15310972, San Diego Wave FC @ Racing Louisville FC —
/// the Win Probability gutter read `SAN DIEGO WAVE…` / `RACING LOUISVIL…` under
/// a title reading `SDW vs RAC` (`artifacts/native-8793/after-sdwave.png`);
/// event 15292394, Real Madrid v Dubai Basketball — the Score Differential
/// gutter read `DUBAI BA…` while the Win Probability gutter above it held the
/// whole name (`artifacts-native-020/n323-after2-15292394.png`).
final class AChartGutterNeverCutsANameInHalf8820Tests: XCTestCase {

    /// The phone's Win Probability gutter: the phone chart, 8 pt padding, 11 pt.
    private let winProbRun = ChartGutter.run(chartHeight: OddsChartView.phoneChartHeight, verticalPadding: 8)
    private let winProbFont: CGFloat = 11
    /// The Score Differential gutter below it: shorter chart, 10 pt.
    private let diffRun = ChartGutter.run(
        chartHeight: ScoreDifferentialChartView.chartHeight, verticalPadding: 8)
    private let diffFont: CGFloat = 10

    private func nameRun(_ run: CGFloat) -> CGFloat {
        ChartGutter.nameRun(run: run, hasCrest: true)
    }

    // MARK: - The premise

    /// 🔴 If these names fit, the photographed ellipses had another cause and
    /// this fix is aimed wrong.
    func testTheSpecimenNamesOverflowTheirGutters() {
        XCTAssertGreaterThan(
            ChartGutter.nameWidth("San Diego Wave FC", fontSize: winProbFont), nameRun(winProbRun))
        XCTAssertGreaterThan(
            ChartGutter.nameWidth("Racing Louisville FC", fontSize: winProbFont), nameRun(winProbRun))
        XCTAssertGreaterThan(
            ChartGutter.nameWidth("Dubai Basketball", fontSize: diffFont), nameRun(diffRun))
    }

    // MARK: - The fix

    /// 🟢 #8820 — the Win Probability gutter reads the codes the title reads.
    func testTheNwslSpecimenGutterReadsTheTitlesCodes() {
        let sides = ChartGutter.sideLabels(
            away: "San Diego Wave FC", home: "Racing Louisville FC",
            fontSize: winProbFont, awayRun: nameRun(winProbRun), homeRun: nameRun(winProbRun))
        XCTAssertEqual(sides.away, "SDW")
        XCTAssertEqual(sides.home, "RAC")
    }

    /// 🟢 #8425 — the Score Differential gutter reads the title's codes too,
    /// and both of them fit.
    func testTheEuroLeagueSpecimenDifferentialGutterReadsTheTitlesCodes() {
        let away = "Dubai Basketball", home = "Real Madrid"
        let sides = ChartGutter.sideLabels(
            away: away, home: home,
            fontSize: diffFont, awayRun: nameRun(diffRun), homeRun: nameRun(diffRun))
        let title = EventNavTitle.scorelessCompact(away: away, home: home)
        XCTAssertEqual("\(sides.away) vs \(sides.home)", title)
        for code in [sides.away, sides.home] {
            XCTAssertLessThanOrEqual(ChartGutter.nameWidth(code, fontSize: diffFont), nameRun(diffRun), code)
        }
    }

    /// One side that does not fit is enough: both move together, so one axis
    /// never reads a code at the top and a name at the bottom.
    func testOneOverflowingSideMovesBothSides() {
        let short = "Orlando Pride"
        XCTAssertLessThanOrEqual(
            ChartGutter.nameWidth(TeamShortName.shortPair(away: short, home: "Racing Louisville FC").away,
                                  fontSize: winProbFont),
            nameRun(winProbRun), "premise: the away label fits on its own")
        let sides = ChartGutter.sideLabels(
            away: short, home: "Racing Louisville FC",
            fontSize: winProbFont, awayRun: nameRun(winProbRun), homeRun: nameRun(winProbRun))
        let codes = TeamShortName.abbreviationPair(away: short, home: "Racing Louisville FC")
        XCTAssertEqual(sides.away, codes.away)
        XCTAssertEqual(sides.home, codes.home)
    }

    /// The crest is laid out along the run, so a side that draws one has less
    /// of the run for its name — and a side whose crest failed has all of it.
    func testTheCrestIsChargedAgainstTheRun() {
        XCTAssertEqual(
            ChartGutter.nameRun(run: 64, hasCrest: true),
            64 - ChartGutterCrest.side - ChartGutter.crestSpacing, accuracy: 0.001)
        XCTAssertEqual(ChartGutter.nameRun(run: 64, hasCrest: false), 64, accuracy: 0.001)
        XCTAssertEqual(ChartGutter.nameRun(run: 5, hasCrest: true), 0, accuracy: 0.001)
    }

    // MARK: - The control

    /// 🔴 THE CONTROL — a label that fits is exactly the pair rule's label.
    /// Without this, "codes everywhere" passes every assertion above. The Win
    /// Probability gutter held the whole `DUBAI BASKETBALL` in the photograph —
    /// no crest drew beside it, so it had the whole run — and it keeps it;
    /// served codes, surnames and nicknames beside a crest too.
    func testEveryLabelThatFitsIsLeftAlone() {
        let cases: [(String, String, String?, String?, Bool)] = [
            ("Dubai Basketball", "Real Madrid", nil, nil, false),
            ("Los Angeles Rams", "San Francisco 49ers", "LAR", "SF", true),
            ("Aryna Sabalenka", "Jessica Pegula", nil, nil, true),
            ("Boston Red Sox", "New York Yankees", nil, nil, true),
            ("San Diego Wave FC", "Racing Louisville FC", "SDW", "LOU", true),
        ]
        for (a, h, aServed, hServed, crest) in cases {
            let run = ChartGutter.nameRun(run: winProbRun, hasCrest: crest)
            let before = TeamShortName.shortPair(
                away: a, home: h, awayServed: aServed, homeServed: hServed)
            for name in [before.away, before.home] {
                XCTAssertLessThanOrEqual(
                    ChartGutter.nameWidth(name, fontSize: winProbFont), run,
                    "premise: '\(name)' fits, so the control exercises the fits branch")
            }
            let after = ChartGutter.sideLabels(
                away: a, home: h, awayServed: aServed, homeServed: hServed,
                fontSize: winProbFont, awayRun: run, homeRun: run)
            XCTAssertEqual(after.away, before.away, "\(a) @ \(h)")
            XCTAssertEqual(after.home, before.home, "\(a) @ \(h)")
        }
    }

    /// The measurement is of the UPPERCASED name — what the gutter draws — so
    /// a lowercase name is not under-charged.
    func testTheWidthIsOfTheUppercasedName() {
        XCTAssertEqual(
            ChartGutter.nameWidth("dubai basketball", fontSize: diffFont),
            ChartGutter.nameWidth("DUBAI BASKETBALL", fontSize: diffFont), accuracy: 0.001)
    }

    // MARK: - The wiring

    /// The rule does nothing if a gutter still prints `homeShort`. The views'
    /// labels are private, so they are read from source: every gutter `Text`
    /// in both charts reads `gutter.`, and each gutter asks the rule for it.
    func testEveryGutterTakesItsNamesFromTheFitRule() throws {
        let odds = try code("Components/OddsChartView.swift")
        XCTAssertEqual(odds.components(separatedBy: "gutterLabels(run: run, fontSize: gutterFont)").count - 1, 2,
                       "the inline and the fullscreen gutter")
        XCTAssertEqual(odds.components(separatedBy: "Text(gutter.home.uppercased())").count - 1, 2)
        XCTAssertEqual(odds.components(separatedBy: "Text(gutter.away.uppercased())").count - 1, 2)
        XCTAssertFalse(odds.contains("Text(homeShort.uppercased())"))
        XCTAssertFalse(odds.contains("Text(awayShort.uppercased())"))

        let diff = try code("Components/ScoreDifferentialChartView.swift")
        XCTAssertEqual(diff.components(separatedBy: "gutterLabels(run: run, fontSize: gutterFont)").count - 1, 1)
        XCTAssertEqual(diff.components(separatedBy: "Text(gutter.home.uppercased())").count - 1, 1)
        XCTAssertEqual(diff.components(separatedBy: "Text(gutter.away.uppercased())").count - 1, 1)
        XCTAssertFalse(diff.contains("TeamShortName.shortPair("),
                       "a second side-name path would bring the half-name back")
    }

    private func code(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/\(relative)")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }
}
