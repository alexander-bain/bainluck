import XCTest
@testable import Bain_Luck

/// #10141 (Alex, build 34, report 166): *Will the Iranian regime fall before 2027?*
/// (113200) served 168 venue prices in the week, every one 6.5%, and the iPhone chart
/// drew one flat line that read as "no data points for 7 days". An observed constant
/// series now says so in one line; nothing is smoothed or invented.
final class AHeldSteadyChartSaysUnchanged10141Tests: XCTestCase {
    private let week = EvolutionChartView.windowWord(for: .week)

    func testTheReportedWeekOfIdenticalPricesSaysUnchanged() {
        let specimen = Array(repeating: 6.5, count: 168)
        XCTAssertEqual(
            EvolutionChartView.heldSteadyNote(series: ["Yes": specimen], windowInstants: 168, windowWord: week),
            "Unchanged in the last 7 days")
        XCTAssertEqual(
            EvolutionChartView.heldSteadyNote(
                series: ["Yes": [6.5, 6.5, 6.5, 6.5]],
                windowInstants: 4, windowWord: EvolutionChartView.windowWord(for: .today)),
            "Unchanged today")
    }

    func testOneMovedPriceIsNotUnchanged() {
        var moved = Array(repeating: 6.5, count: 168)
        moved[80] = 7.5
        XCTAssertNil(EvolutionChartView.heldSteadyNote(series: ["Yes": moved], windowInstants: 168, windowWord: week))
    }

    func testEveryPlottedLineMustHoldNotJustOne() {
        let flat = Array(repeating: 40.0, count: 10)
        let moving = (0..<10).map { 30.0 + Double($0) }
        XCTAssertNil(EvolutionChartView.heldSteadyNote(
            series: ["A": flat, "B": moving], windowInstants: 10, windowWord: week))
        XCTAssertEqual(EvolutionChartView.heldSteadyNote(
            series: ["A": flat, "B": Array(repeating: 60.0, count: 10)], windowInstants: 10, windowWord: week),
            "Unchanged in the last 7 days")
    }

    func testTooFewPricesIsNotEvidenceOfHoldingSteady() {
        // Three instants is the "Only 3 prices seen so far" sentence's territory.
        XCTAssertNil(EvolutionChartView.heldSteadyNote(
            series: ["Yes": [6.5, 6.5, 6.5]], windowInstants: 3, windowWord: week))
        // A line whose own window holds one price is a dot, not a held line.
        XCTAssertNil(EvolutionChartView.heldSteadyNote(
            series: ["Yes": [6.5, 6.5, 6.5, 6.5], "No": [93.5]], windowInstants: 4, windowWord: week))
        XCTAssertNil(EvolutionChartView.heldSteadyNote(series: [:], windowInstants: 50, windowWord: week))
    }

    /// The coverage sentence keeps priority: "Prices only go back 2d" is the more
    /// important truth when the window is mostly empty.
    func testTheCardAsksForTheNoteOnlyAfterTheCoverageSentence() throws {
        let source = try String(contentsOf: Self.repoFile("ios/Bain Luck/Bain Luck/Components/EvolutionChartView.swift"), encoding: .utf8)
        let coverage = try XCTUnwrap(source.range(of: "if let note = Self.coverageNote("))
        let tail = String(source[coverage.upperBound...].prefix(400))
        XCTAssertTrue(tail.contains(") ?? Self.heldSteadyNote("), "the card never asks for the Unchanged line")
        XCTAssertTrue(tail.contains("series: plottedSeries"))
    }

    private static func repoFile(_ path: String) -> URL {
        var url = URL(fileURLWithPath: #filePath)
        while url.path != "/" && !FileManager.default.fileExists(atPath: url.appendingPathComponent("ios").path) {
            url.deleteLastPathComponent()
        }
        return url.appendingPathComponent(path)
    }
}
