import XCTest
@testable import Bain_Luck

/// #10868 — the football screen's win probability history is the accepted
/// hockey history adapter's (H2, `HockeyJourneyHistoryAdapter10868`), called
/// rather than copied, on RETAINED REAL bodies (`FootballRetained10868`).
/// Football changes only the full-chart control's spoken name.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
/// The live history is a reduced verbatim subset, so its series are the
/// SUBSET's runs; equality with H2 on the same subset is what is proved.
@MainActor
final class FootballHistoryAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias H = FootballHistoryAdapter10868
    private typealias H2 = HockeyJourneyHistoryAdapter10868

    private func assertSameExceptExpandWords(_ football: FieldHistoryInput10868, _ hockey: FieldHistoryInput10868,
                                             file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(football.title, hockey.title, file: file, line: line)
        XCTAssertEqual(football.caption, hockey.caption, file: file, line: line)
        XCTAssertEqual(football.series, hockey.series, file: file, line: line)
        XCTAssertEqual(football.selection, hockey.selection, file: file, line: line)
        XCTAssertEqual(football.domain, hockey.domain, file: file, line: line)
        XCTAssertEqual(football.xTicks, hockey.xTicks, file: file, line: line)
        XCTAssertEqual(football.breaks, hockey.breaks, file: file, line: line)
        XCTAssertEqual(football.readout, hockey.readout, file: file, line: line)
        XCTAssertEqual(football.notes, hockey.notes, file: file, line: line)
        XCTAssertEqual(football.summary, hockey.summary, file: file, line: line)
        XCTAssertEqual(football.details, hockey.details, file: file, line: line)
        XCTAssertEqual(football.inspect, hockey.inspect, file: file, line: line)
        XCTAssertEqual(football.plotAbsence, hockey.plotAbsence, file: file, line: line)
        XCTAssertEqual(football.expand?.id, hockey.expand?.id, file: file, line: line)
        XCTAssertEqual(football.expand?.label, hockey.expand?.label, file: file, line: line)
        XCTAssertEqual(football.expand?.isAvailable, hockey.expand?.isAvailable, file: file, line: line)
    }

    func testTheLiveHistoryIsH2sWithFootballsExpandWords() throws {
        let event = try F.detail(F.liveDetail)
        let response = try F.history(F.liveHistory)
        let football = H.history(response, event: event, phase: .live, host: F.historyHost(F.liveNow))
        let hockey = H2.history(response, event: event, phase: .live, host: F.historyHost(F.liveNow))

        assertSameExceptExpandWords(football, hockey)
        XCTAssertEqual(football.expand?.id, H2.expandActionID)
        XCTAssertEqual(football.expand?.spokenLabel, "Expand football probability history")
    }

    func testTheFinalHistoryIsH2sWithFootballsExpandWords() throws {
        let event = try F.detail(F.packersDetail)
        let response = try F.history(F.packersHistory)
        let football = H.history(response, event: event, phase: .final, host: F.historyHost(F.packersNow),
                                 inGameStart: .observedPlayStart)
        let hockey = H2.history(response, event: event, phase: .final, host: F.historyHost(F.packersNow),
                                inGameStart: .observedPlayStart)
        assertSameExceptExpandWords(football, hockey)
    }

    func testNoHistoryResponseIsTheHonestUnavailableSlot() throws {
        let event = try F.detail(F.liveDetail)
        let football = H.unavailable(event: event, phase: .live)
        XCTAssertEqual(football, H2.unavailable(event: event, phase: .live))
        XCTAssertEqual(football.summary, "History unavailable")
        XCTAssertTrue(football.series.allSatisfy { $0.runs.isEmpty })
    }
}
