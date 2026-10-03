import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10272 — a canceled game's scoring card stops being headed "Projected
/// scoring / Projected combined runs".
///
/// Specimen **15319530** — Orioles @ Yankees, Sep 27, `status=suspended`, hero
/// **Canceled**. #10149 made the margin map on that page read **Last quoted
/// margin**; the scoring card one scroll lower kept both headings in the
/// forward tense over a game that will never be played, because
/// `SpectrumTense` has no state for "not over and never will be" and the
/// headings never saw #4018's `canStillBeGraded`.
final class ACanceledGamesScoringCardIsNotProjected10272Tests: XCTestCase {

    // MARK: - The specimen

    /// 15319530 as the card sees it: no final, not settled, cannot be graded.
    func testTheCanceledSpecimenReadsLastQuotedInBothHeadings() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(
                finalTotal: nil, isSettled: false, canStillBeGraded: false),
            "Last quoted scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(
                finalTotal: nil, unit: "runs", isSettled: false, canStillBeGraded: false),
            "Last quoted combined runs"
        )
    }

    /// The card and the margin map above it speak one word for one state.
    func testTheScoringCardUsesTheMarginMapsWordForTheSameState() {
        let margin = MarketMapRail.fullMarginSubtitle(
            isDone: false, canStillBeGraded: false, hasDistribution: true)
        let scoring = MarketMapRail.spectrumSectionTitle(
            finalTotal: nil, isSettled: false, canStillBeGraded: false)
        XCTAssertTrue(margin.hasPrefix("Last quoted"), margin)
        XCTAssertTrue(scoring.hasPrefix("Last quoted"), scoring)
    }

    // MARK: - Controls: the gate moves only the case it names

    /// A scheduled or live game can still be graded and keeps its forecast.
    func testAGradeableUnsettledCardStaysProjected() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(
                finalTotal: nil, isSettled: false, canStillBeGraded: true),
            "Projected scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(
                finalTotal: nil, unit: "runs", isSettled: false, canStillBeGraded: true),
            "Projected combined runs"
        )
    }

    /// Settled and graded win over the gate in both directions — a finished
    /// game's `canStillBeGraded` is false, and that must not demote "Final".
    func testSettledAndFinalAreUnmovedByTheGate() {
        for gate in [true, false] {
            XCTAssertEqual(
                MarketMapRail.spectrumSectionTitle(
                    finalTotal: 9, isSettled: true, canStillBeGraded: gate),
                "Final scoring", "gate \(gate)"
            )
            XCTAssertEqual(
                MarketMapRail.spectrumSectionTitle(
                    finalTotal: nil, isSettled: true, canStillBeGraded: gate),
                "Settled scoring", "gate \(gate)"
            )
        }
    }

    /// The pre-#10272 call (no gate) is unchanged — every existing caller and
    /// `TotalPointsSpectrumTenseTests` read the gradeable default.
    func testTheDefaultIsTheGradeableCase() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: nil, isSettled: false),
            MarketMapRail.spectrumSectionTitle(
                finalTotal: nil, isSettled: false, canStillBeGraded: true)
        )
    }

    // MARK: - One card, one tense, now over the gate too

    func testTheTwoHeadingsNeverDifferInTenseAcrossTheGate() {
        for gate in [true, false] {
            for isSettled in [true, false] {
                for finalTotal: Int? in [nil, 0, 9] {
                    let tense = MarketMapRail.spectrumHeadingTense(
                        finalTotal: finalTotal, isSettled: isSettled, canStillBeGraded: gate)
                    let section = MarketMapRail.spectrumSectionTitle(
                        finalTotal: finalTotal, isSettled: isSettled, canStillBeGraded: gate)
                    let ladder = MarketMapRail.spectrumLadderTitle(
                        finalTotal: finalTotal, unit: "runs", isSettled: isSettled,
                        canStillBeGraded: gate)
                    let where_ = "final \(String(describing: finalTotal)), settled \(isSettled), gate \(gate)"
                    XCTAssertTrue(section.hasPrefix(tense + " "), "\(section) — \(where_)")
                    XCTAssertTrue(ladder.hasPrefix(tense + " "), "\(ladder) — \(where_)")
                }
            }
        }
    }

    // MARK: - The wiring, which no test of the rule can see

    /// The rule defaults to the gradeable case, so a view that stops passing
    /// its own gate compiles and silently re-prints "Projected" on 15319530.
    /// Both heading calls must hand over `canStillBeGraded`.
    func testTheViewPassesItsOwnGateToBothHeadings() throws {
        let code = try Self.strippedSource("Components/TotalPointsSpectrumView.swift")
        for call in ["spectrumSectionTitle(", "spectrumLadderTitle("] {
            guard let start = code.range(of: "MarketMapRail.\(call)") else {
                return XCTFail("TotalPointsSpectrumView no longer calls \(call)")
            }
            guard let close = code[start.upperBound...].range(of: "))") else {
                return XCTFail("could not find the end of \(call)")
            }
            let args = code[start.upperBound..<close.lowerBound]
            XCTAssertTrue(
                args.contains("canStillBeGraded: canStillBeGraded"),
                "\(call) is called without the view's own gate: \(args)"
            )
        }
    }

    // MARK: - Fit

    /// "Last quoted" is longer than "Projected", so this is measured, not
    /// assumed (#3552's class). Neither slot has a fixed frame; the section
    /// heading shares an HStack with a "N sources" chip. The bound is the
    /// narrowest phone card's content width less that chip's room.
    @MainActor
    func testTheLastQuotedHeadingsFitTheNarrowestCard() {
        // A 320 pt screen, less 16 pt page inset and the card's own 12 pt
        // padding per side, leaves 264 pt; the section slot also holds the
        // "N sources" chip, given ~70 pt.
        let card: CGFloat = 320 - 2 * 16 - 2 * 12
        let room: CGFloat = card - 70
        let section = MarketMapRail.spectrumSectionTitle(
            finalTotal: nil, isSettled: false, canStillBeGraded: false)
        let ladders = ["scoring", "runs", "points", "games"].map {
            MarketMapRail.spectrumLadderTitle(
                finalTotal: nil, unit: $0, isSettled: false, canStillBeGraded: false)
        }
        let sectionWidth = naturalWidth(of: section, font: TotalPointsSpectrumView.sectionTitleFont)
        XCTAssertLessThanOrEqual(sectionWidth, room, "'\(section)' is \(sectionWidth) pt")
        for ladder in ladders {
            let w = naturalWidth(of: ladder, font: TotalPointsSpectrumView.ladderTitleFont)
            XCTAssertLessThanOrEqual(w, card, "'\(ladder)' is \(w) pt")
        }
    }

    @MainActor
    private func naturalWidth(of string: String, font: Font) -> CGFloat {
        let host = hostForMeasurement(Text(string).font(font).lineLimit(1))
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }

    private static func strippedSource(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        return try String(
            contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }
}
