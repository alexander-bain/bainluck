import XCTest
import SwiftUI
@testable import Bain_Luck

/// #11422 — an iPhone Sports live card reads as one tidy card at normal text size.
///
/// Alex's rage #185 (1.0.4, Pacers @ Pelicans 15198502, Q4 8:50) photographed
/// three things on one live card:
///
/// 1. "Projected final" over "Indiana Pacers 117 · New Orleans / Pelicans 121":
///    three lines of full names under rows that already name both teams.
/// 2. "New Orleans Pelicans leading after starting at 44%" wrapped to three lines
///    inside a `Capsule`, whose half-height radius cut the first and last
///    letters off.
/// 3. "Opened 56%/44%" beside that sentence: the same kickoff price twice.
///
/// Each arm is asserted in both directions, so neither "print nothing" nor
/// "change nothing" passes.
@MainActor
final class LiveSportsCardTidy11422Tests: XCTestCase {

    private typealias Footer = EventCardView.EventCardFooter

    // MARK: - 3. One opening statement

    /// The served reason on the rage specimen, verbatim, and the other two live
    /// claim templates `feed_reasons.py` writes (#5868's NPB specimen for "rose").
    func testEveryLiveClaimTemplateStatesTheOpening() {
        XCTAssertTrue(Footer.reasonStatesTheOpening("New Orleans Pelicans leading after starting at 44%"))
        XCTAssertTrue(Footer.reasonStatesTheOpening("Hokkaido Nippon-Ham Fighters chance rose from 46% to 87%"))
        XCTAssertTrue(Footer.reasonStatesTheOpening("Real Betis chance fell from 52% to 31%"))
    }

    /// The caption stays wherever the reason does not carry the start.
    func testAReasonWithoutTheOpeningKeepsTheOpenedCaption() {
        XCTAssertFalse(Footer.reasonStatesTheOpening(nil))
        XCTAssertFalse(Footer.reasonStatesTheOpening(""))
        XCTAssertFalse(Footer.reasonStatesTheOpening("Virtually even"))
        XCTAssertFalse(Footer.reasonStatesTheOpening("Wild game"))
        XCTAssertFalse(Footer.reasonStatesTheOpening("Close matchup"))
    }

    /// A team name cannot switch the caption off: the template's words must sit
    /// around a percentage.
    func testANameAloneCannotForgeTheTemplate() {
        XCTAssertFalse(Footer.reasonStatesTheOpening("Starting Eleven FC chance rose sharply"))
        XCTAssertFalse(Footer.reasonStatesTheOpening("Rising Stars leading after starting slow"))
    }

    /// Stepping the caption aside never empties the footer: the reason is
    /// content on its own, so the sentence is still drawn once.
    func testTheFooterStillDrawsWhenTheCaptionStepsAside() {
        XCTAssertTrue(Footer.hasContent(
            reason: "New Orleans Pelicans leading after starting at 44%", isLive: true,
            awayOpening: 0.56, homeOpening: 0.44, sport: "basketball_nba"))
    }

    func testTheCaptionIsGatedOnTheReasonInTheView() throws {
        let code = try source("Components/EventCardView.swift")
        XCTAssertTrue(code.contains("privatevarfooterRow:someView{"), "anti-vacuity")
        XCTAssertEqual(
            occurrences("ifisLive,!EventCardFooter.reasonStatesTheOpening(reason),letopened=DrawPricedWinner.printablePair(", in: code), 1)
    }

    // MARK: - 2. The reason pill keeps every letter

    func testTheReasonPillIsNotClippedToACapsule() throws {
        let code = try source("Components/EventCardView.swift")
        guard let start = code.range(of: "privatefuncreasonBadge("),
              let end = code.range(of: "privatefuncreasonStyle(", range: start.upperBound..<code.endIndex)
        else { return XCTFail("reasonBadge not found") }
        let badge = String(code[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(badge.contains(".clipShape(RoundedRectangle(cornerRadius:8,style:.continuous))"), badge)
        XCTAssertFalse(badge.contains("Capsule()"), "a wrapped sentence loses its end letters to a Capsule")
    }

    // MARK: - 1. The projected final on one line

    private func printed(home: Int, away: Int, label: String = "Projected final")
        -> LiveProjectedFinalAdmission2920.Printed {
        let t = Date(timeIntervalSince1970: 1_792_700_000)
        return .init(
            label: label, home: home, away: away,
            admitted: .init(
                home: Double(home), away: Double(away),
                provenance: .init(
                    bookmakerCount: 3, scheduledStart: t, earliestConfirmedAt: t,
                    latestCapturedAt: t, unit: .points, period: .fullGame)))
    }

    func testTheVisiblePairUsesShortNamesOnTheirOwnSides() {
        XCTAssertEqual(
            LiveProjectedFinalLine2920.visiblePair(
                printed(home: 121, away: 117), awayName: "Indiana Pacers",
                homeName: "New Orleans Pelicans", sportKey: "basketball_nba"),
            "Pacers\u{00A0}117 · Pelicans\u{00A0}121")
        XCTAssertEqual(
            LiveProjectedFinalLine2920.visiblePair(
                printed(home: 106, away: 133), awayName: "Minnesota Timberwolves",
                homeName: "Miami Heat", sportKey: "basketball_nba"),
            "Timberwolves\u{00A0}133 · Heat\u{00A0}106")
    }

    func testVoiceOverKeepsTheFullNames() {
        XCTAssertEqual(
            LiveProjectedFinal2920.spokenText(
                printed(home: 121, away: 117), awayName: "Indiana Pacers", homeName: "New Orleans Pelicans"),
            "Projected final: Indiana Pacers 117, New Orleans Pelicans 121")
    }

    /// The line's inset width on a 393-pt iPhone Sports card (screen minus the
    /// list's and card's margins minus the 32-pt crest inset).
    private let cardLineWidth: CGFloat = 290

    private func height<V: View>(of view: V, width: CGFloat, at size: DynamicTypeSize = .large) -> CGFloat {
        let host = hostForMeasurement(view.frame(width: width), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2000))
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
    }

    private func oneCaptionLine(at size: DynamicTypeSize = .large) -> CGFloat {
        height(of: Text("Projected final").font(.caption), width: cardLineWidth, at: size)
    }

    func testBothRageSpecimensDrawOneLineAtNormalTextSize() {
        let line = oneCaptionLine()
        XCTAssertGreaterThan(line, 8, "anti-vacuity")
        for (away, home, a, h) in [("Indiana Pacers", "New Orleans Pelicans", 117, 121),
                                   ("Minnesota Timberwolves", "Miami Heat", 133, 106)] {
            let drawn = height(
                of: LiveProjectedFinalLine2920(
                    printed: printed(home: h, away: a), awayName: away, homeName: home,
                    sportKey: "basketball_nba"),
                width: cardLineWidth)
            XCTAssertEqual(drawn, line, accuracy: 1, "\(away) @ \(home) drew \(drawn) pt, one line is \(line)")
        }
    }

    /// At an accessibility size the one-line form does not fit, so the line
    /// stacks and wraps instead of truncating: taller than one line, every word
    /// kept.
    func testAnAccessibilitySizeStacksInsteadOfTruncating() {
        let size = DynamicTypeSize.accessibility3
        let line = oneCaptionLine(at: size)
        let drawn = height(
            of: LiveProjectedFinalLine2920(
                printed: printed(home: 121, away: 117), awayName: "Indiana Pacers",
                homeName: "New Orleans Pelicans", sportKey: "basketball_nba"),
            width: cardLineWidth, at: size)
        XCTAssertGreaterThan(drawn, line * 1.5, "the large-text line did not stack")
    }

    // MARK: - Source helpers

    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(path)
        let text = try String(contentsOf: url, encoding: .utf8)
        return text.split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func occurrences(_ needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }
}
