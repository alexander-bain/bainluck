import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11449 — the soccer headline's three named outcomes show the owner's strings
/// exactly, in home / Draw / away order, and never borrow a value from the other
/// reading or invent one.
///
/// Hull City–Everton (Oct 11) values are ARCHIVED reference strings from the
/// v463 native soccer history reader: last pre-match 22.5% / 28.5% / 49.5% and
/// recorded after kickoff 1% / 99% / 1%. They are Kalshi-only, independently
/// recorded readings — not a blend and not a current event — and they sum to
/// 101% on purpose. Every other value here is CONSTRUCTED.
final class SoccerThreeOutcomeHeadline11449Tests: XCTestCase {

    private let homeColor = Color(red: 0.145, green: 0.302, blue: 0.851)
    private let awayColor = Color(red: 0.020, green: 0.478, blue: 0.439)

    /// The two missing-reading defaults differ on purpose, so a message that
    /// crossed to the other reading would show up in any assertion.
    private func slot(_ label: String, _ color: Color = .primary, primary: String?, comparison: String? = nil,
                      primaryUnavailable: String = "Primary unavailable",
                      comparisonUnavailable: String = "Comparison unavailable") -> SoccerOutcomeSlot11449 {
        SoccerOutcomeSlot11449(label: label, color: color, primary: primary, comparison: comparison,
                               primaryUnavailable: primaryUnavailable, comparisonUnavailable: comparisonUnavailable)
    }

    private var afterKickoff: SoccerReadingHeading11449 {
        SoccerReadingHeading11449(title: "Recorded after kickoff", context: "Oct 11, 7:57 AM · Kalshi only")
    }

    private var lastPreMatch: SoccerReadingHeading11449 {
        SoccerReadingHeading11449(title: "Last pre-match", context: "Oct 11, 5:59 AM · Kalshi only")
    }

    /// The archived Hull–Everton live composition: after-kickoff primary,
    /// last pre-match comparison.
    private var archivedLive: SoccerThreeOutcomeHeadlineInput11449 {
        SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Hull win", homeColor, primary: "1%", comparison: "22.5%"),
            draw: slot("Draw", primary: "99%", comparison: "28.5%"),
            away: slot("Everton win", awayColor, primary: "1%", comparison: "49.5%"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
    }

    func testThreeOutcomesKeepTheirOwnIdentityInFixedOrder() {
        let input = archivedLive
        XCTAssertEqual(input.outcomes.map(\.label), ["Hull win", "Draw", "Everton win"])
        XCTAssertEqual(input.outcomes.map(\.color), [homeColor, .primary, awayColor])
        // Equal primary values on home and away stay two separate outcomes.
        XCTAssertEqual(input.primaryText(for: input.home), .value("1%"))
        XCTAssertEqual(input.primaryText(for: input.away), .value("1%"))
        XCTAssertNotEqual(input.accessibilityLabel(for: input.home), input.accessibilityLabel(for: input.away))
    }

    func testArchivedHullEvertonTriplesArePreservedExactly() {
        let input = archivedLive
        XCTAssertEqual(input.outcomes.map { input.primaryText(for: $0) },
                       [.value("1%"), .value("99%"), .value("1%")])
        XCTAssertEqual(input.outcomes.map { input.comparisonText(for: $0) },
                       [.value("22.5%"), .value("28.5%"), .value("49.5%")])
        XCTAssertEqual(input.accessibilityElements, [
            "Recorded after kickoff: Oct 11, 7:57 AM · Kalshi only. Last pre-match: Oct 11, 5:59 AM · Kalshi only",
            "Hull win. Recorded after kickoff: 1%. Last pre-match: 22.5%",
            "Draw. Recorded after kickoff: 99%. Last pre-match: 28.5%",
            "Everton win. Recorded after kickoff: 1%. Last pre-match: 49.5%",
        ])
    }

    func testSuppliedPrecisionAndInequalityGuardsAreUnchanged() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: "<1%", comparison: "22.50%"),
            draw: slot("Draw", primary: "≥ 99%", comparison: "28.5% · thin market"),
            away: slot("Away win", primary: "0.4%", comparison: "49%"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
        XCTAssertEqual(input.outcomes.map { input.primaryText(for: $0) },
                       [.value("<1%"), .value("≥ 99%"), .value("0.4%")])
        XCTAssertEqual(input.outcomes.map { input.comparisonText(for: $0) },
                       [.value("22.50%"), .value("28.5% · thin market"), .value("49%")])
    }

    func testMissingPrimaryDoesNotBorrowTheComparison() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: nil, comparison: "22.5%", primaryUnavailable: "No reading after kickoff"),
            draw: slot("Draw", primary: "99%", comparison: "28.5%"),
            away: slot("Away win", primary: "1%", comparison: "49.5%"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
        XCTAssertEqual(input.primaryText(for: input.home), .unavailable("No reading after kickoff"))
        XCTAssertEqual(input.comparisonText(for: input.home), .value("22.5%"))
        XCTAssertEqual(input.accessibilityLabel(for: input.home),
                       "Home win. Recorded after kickoff: No reading after kickoff. Last pre-match: 22.5%")
    }

    func testMissingComparisonDoesNotBorrowThePrimary() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: "1%", comparison: "22.5%"),
            draw: slot("Draw", primary: "99%", comparison: nil, comparisonUnavailable: "No pre-match reading"),
            away: slot("Away win", primary: "1%", comparison: "49.5%"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
        XCTAssertEqual(input.primaryText(for: input.draw), .value("99%"))
        XCTAssertEqual(input.comparisonText(for: input.draw), .unavailable("No pre-match reading"))
    }

    func testAllUnavailableSlotsStayNamed() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: nil, primaryUnavailable: "Unavailable"),
            draw: slot("Draw", primary: nil, primaryUnavailable: "Unavailable"),
            away: slot("Away win", primary: nil, primaryUnavailable: "Unavailable"),
            primaryHeading: SoccerReadingHeading11449(title: "Pre-match", context: nil),
            comparisonHeading: nil)
        XCTAssertEqual(input.accessibilityElements, [
            "Pre-match",
            "Home win. Pre-match: Unavailable",
            "Draw. Pre-match: Unavailable",
            "Away win. Pre-match: Unavailable",
        ])
    }

    func testEqualValuesFromDifferentObservationsAreNotCollapsed() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: "40%", comparison: "40%"),
            draw: slot("Draw", primary: "28.5%", comparison: "28.5%"),
            away: slot("Away win", primary: "32%", comparison: "32%"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
        XCTAssertEqual(input.outcomes.map { input.comparisonText(for: $0) },
                       [.value("40%"), .value("28.5%"), .value("32%")])
        XCTAssertEqual(input.accessibilityLabel(for: input.draw),
                       "Draw. Recorded after kickoff: 28.5%. Last pre-match: 28.5%")
    }

    func testOmittedComparisonSuppressesTheRow() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: "40%", comparison: "38%"),
            draw: slot("Draw", primary: "28.5%", comparisonUnavailable: "No pre-match reading"),
            away: slot("Away win", primary: "32%", comparisonUnavailable: "No pre-match reading"),
            primaryHeading: SoccerReadingHeading11449(title: "Pre-match", context: "Oct 11, 5:59 AM"),
            comparisonHeading: nil)
        // A comparison value or missing message without a heading is not shown.
        XCTAssertTrue(input.outcomes.allSatisfy { input.comparisonText(for: $0) == nil })
        XCTAssertEqual(input.accessibilityLabel(for: input.home), "Home win. Pre-match: 40%")
        XCTAssertEqual(input.accessibilityLabel(for: input.draw), "Draw. Pre-match: 28.5%")
    }

    func testBothReadingsMissingKeepTheirOwnExplanations() {
        // CONSTRUCTED: neither reading exists, and the owner explains each
        // absence differently. The primary's qualifier is not the reason the
        // pre-match baseline is missing.
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: nil, comparison: nil,
                       primaryUnavailable: "No recent observation",
                       comparisonUnavailable: "No pre-match reading was recorded"),
            draw: slot("Draw", primary: "28.5%", comparison: "30%"),
            away: slot("Away win", primary: "32%", comparison: "31%"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
        XCTAssertEqual(input.primaryText(for: input.home), .unavailable("No recent observation"))
        XCTAssertEqual(input.comparisonText(for: input.home), .unavailable("No pre-match reading was recorded"))
        XCTAssertEqual(input.primaryText(for: input.home).spoken, "No recent observation")
        XCTAssertEqual(input.comparisonText(for: input.home)?.spoken, "No pre-match reading was recorded")
        let label = input.accessibilityLabel(for: input.home)
        XCTAssertEqual(label,
                       "Home win. Recorded after kickoff: No recent observation. "
                           + "Last pre-match: No pre-match reading was recorded")
        XCTAssertEqual(label.components(separatedBy: "No recent observation").count - 1, 1)
        XCTAssertEqual(input.accessibilityElements[1], label)
    }

    func testEnabledComparisonWithEveryValueMissingKeepsTheRow() {
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Home win", primary: "40%", comparisonUnavailable: "Not recorded"),
            draw: slot("Draw", primary: "28.5%", comparisonUnavailable: "Not recorded"),
            away: slot("Away win", primary: "32%", comparisonUnavailable: "Not recorded"),
            primaryHeading: afterKickoff,
            comparisonHeading: lastPreMatch)
        XCTAssertEqual(input.outcomes.map { input.comparisonText(for: $0) },
                       Array(repeating: .unavailable("Not recorded"), count: 3))
        XCTAssertEqual(input.accessibilityLabel(for: input.away),
                       "Away win. Recorded after kickoff: 32%. Last pre-match: Not recorded")
    }

    func testFinalCompositionInventsNoTerminalCertainty() {
        // Final: the owner passes only the pre-match triple; the surrounding
        // header carries the actual result.
        let input = SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Hull win", homeColor, primary: "22.5%"),
            draw: slot("Draw", primary: "28.5%"),
            away: slot("Everton win", awayColor, primary: "49.5%"),
            primaryHeading: lastPreMatch,
            comparisonHeading: nil)
        XCTAssertEqual(input.accessibilityElements, [
            "Last pre-match: Oct 11, 5:59 AM · Kalshi only",
            "Hull win. Last pre-match: 22.5%",
            "Draw. Last pre-match: 28.5%",
            "Everton win. Last pre-match: 49.5%",
        ])
    }

    func testContextIsReadOnceAheadOfTheOutcomes() {
        let input = archivedLive
        let elements = input.accessibilityElements
        XCTAssertEqual(elements.count, 4)
        XCTAssertEqual(elements.first, input.accessibilityContext)
        for label in elements.dropFirst() {
            XCTAssertFalse(label.contains("Oct 11"))
        }
    }
}
