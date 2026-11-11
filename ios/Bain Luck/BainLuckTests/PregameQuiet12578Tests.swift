import XCTest
@testable import Bain_Luck

/// #12578 — Alex, TestFlight 1.0.6 (5704), Patriots at Lions, pre-game: the
/// Kalshi pill beside Player Props read like a sponsor, the projection block
/// carried "tons of grey text", and in a started game the chart should open at
/// kickoff with the kickoff projection marked; the readout follows the title.
@MainActor
final class PregameQuiet12578Tests: XCTestCase {
    private typealias Series = ProjectedFinalPointsSeries
    private let epoch = Date(timeIntervalSince1970: 1_790_000_000)
    private func t(_ seconds: Double) -> Date { epoch.addingTimeInterval(seconds) }
    private func pair(_ seconds: Double, _ home: Double = 27, _ away: Double = 20) -> Series.Pair {
        .init(at: t(seconds), home: home, away: away, homeProbability: 0.6, kind: .recorded)
    }
    private func input(_ pairs: [Series.Pair], actuals: [Series.Actual] = [],
                       floor: Double? = 0, final: Double? = nil, now: Double = 1800) -> Series.Input {
        .init(sportKey: "americanfootball_nfl", sourceKey: "draftkings", basis: .sameBookSameCaptureFullGameSpreadAndTotal,
              pairs: pairs, actuals: actuals, kickoffAt: nil, scoreObservationStartAt: floor.map(t),
              finalAt: final.map(t), asOf: t(now), windowStartAt: nil, requestCutoffAt: nil)
    }

    // MARK: - 1. A quiet source credit

    func testThePropsSourceIsAQuietCreditNotAPill() throws {
        XCTAssertEqual(PlayerPropsCardView.sourceCredit12578("Kalshi"), "from Kalshi")
        let source = try Self.source("Bain Luck/Components/PlayerPropsCardView.swift")
        let at = try XCTUnwrap(source.range(of: "Text(Self.sourceCredit12578(src))"))
        let chain = String(source[at.upperBound...].prefix(160))
        XCTAssertTrue(chain.contains(".font(.caption)"))
        XCTAssertTrue(chain.contains(".foregroundStyle(.secondary)"))
        for pill in ["Capsule", ".heavy", "Color.blue", ".background("] {
            XCTAssertFalse(chain.contains(pill), "the credit has no \(pill)")
        }
    }

    // MARK: - 2. One grey line

    func testTheRecordedLineIsOneLineWithTheScoreTimeAfterADot() throws {
        let before = try XCTUnwrap(Series.build(input([pair(-600)], floor: nil, now: 0)))
        XCTAssertTrue(ProjectedFinalPointsChartView.recordedLine(for: before).hasPrefix("Latest projection recorded "))
        XCTAssertFalse(ProjectedFinalPointsChartView.recordedLine(for: before).contains("score"))
        let during = try XCTUnwrap(Series.build(input([pair(-600), pair(600)],
                                                      actuals: [.init(at: t(900), home: 7, away: 3)], now: 1200)))
        let line = ProjectedFinalPointsChartView.recordedLine(for: during)
        XCTAssertTrue(line.contains(" · score "), line)
    }

    func testTheMethodNotesLiveBehindHowToReadThis() throws {
        let source = try Self.source("Bain Luck/Components/ProjectedFinalPointsChartView.swift")
        let disclosure = try XCTUnwrap(source.range(of: "DisclosureGroup(\"How to read this\""))
        let card = String(source[..<disclosure.lowerBound])
        let inside = String(source[disclosure.upperBound...].prefix(900))
        XCTAssertFalse(card.contains("Text(Self.legend(for: full))"), "the legend is not on the card itself")
        XCTAssertTrue(inside.contains("Text(Self.legend(for: full))"))
        XCTAssertTrue(inside.contains("Latest interval unavailable. Last recorded projection shown."))
        XCTAssertFalse(card.contains("Text(\"Latest interval unavailable"), "nor the interval note")
        XCTAssertFalse(source.contains("Text(\"Score recorded"), "the score time joins the one recorded line")
    }

    // MARK: - 3. The chart opens at kickoff, the kickoff projection marked

    func testAStartedGameOpensAtKickoffWithTheProjectionThatWasHolding() throws {
        // A pregame reading 40 min before kickoff, then in-game readings.
        let series = try XCTUnwrap(Series.build(input([pair(-2400, 24, 21), pair(1200, 30, 17)], now: 1800)))
        XCTAssertEqual(series.start, t(-2400), "the series keeps the reading before kickoff for the cards that use it")
        let kickoff = try XCTUnwrap(series.kickoffProjection)
        XCTAssertEqual(kickoff.at, t(0))
        XCTAssertEqual(kickoff.home, 24)
        XCTAssertEqual(kickoff.away, 21)
        XCTAssertEqual(ProjectedFinalPointsChartView.windowStart(series), t(0), "the chart opens at kickoff")
    }

    func testBeforeAGameTheChartKeepsItsWindowAndMarksNothing() throws {
        let series = try XCTUnwrap(Series.build(input([pair(-5400), pair(-600)], floor: nil, now: 0)))
        XCTAssertNil(series.kickoffProjection)
        XCTAssertEqual(ProjectedFinalPointsChartView.windowStart(series), series.start)
    }

    func testNoProjectionHoldingAtKickoffMarksNothing() throws {
        // The last pregame reading is more than the capture gap before kickoff, so
        // its line stops; nothing was holding at kickoff.
        let series = try XCTUnwrap(Series.build(input([pair(-5000), pair(1200)], now: 1800)))
        XCTAssertNil(series.kickoffProjection)
        XCTAssertEqual(ProjectedFinalPointsChartView.windowStart(series), series.start)
    }

    func testTheKickoffMarkIsDrawnAsAnOpenDot() throws {
        let source = try Self.source("Bain Luck/Components/ProjectedFinalPointsChartView.swift").filter { !$0.isWhitespace }
        XCTAssertTrue(source.contains("ifletkickoff=series.kickoffProjection{"))
        XCTAssertTrue(source.contains(".strokeBorder(side==0?homeColor:awayColor,lineWidth:2)"))
        XCTAssertTrue(source.contains(".chartXScale(domain:Self.windowStart(series)..."))
        XCTAssertTrue(source.contains("ForEach(Array(Self.drawnSegments(series).enumerated())"), "the plot draws the window's runs")
    }

    func testNothingBeforeKickoffIsDrawnAndTheLineStartsAtTheKickoffProjection() throws {
        let series = try XCTUnwrap(Series.build(input([pair(-2400, 24, 21), pair(-600, 25, 21), pair(1200, 30, 17)], now: 1800)))
        let runs = ProjectedFinalPointsChartView.drawnSegments(series)
        let first = try XCTUnwrap(runs.first?.first)
        XCTAssertEqual(first.at, t(0), "the drawn line begins at kickoff")
        XCTAssertEqual(first.home, 25, "with the projection holding at kickoff")
        XCTAssertFalse(runs.joined().contains { $0.at < t(0) }, "no point before kickoff is drawn")
        XCTAssertTrue(runs.joined().contains { $0.at == t(1200) }, "in-game points are kept")
    }

    // MARK: - 4. The readout follows the title

    func testTheReadoutListsTheAwayTeamFirstLikeTheTitle() throws {
        let source = try Self.source("Bain Luck/Components/ProjectedFinalPointsChartView.swift")
        let away = try XCTUnwrap(source.range(of: "teamReadout(awayTeam,"))
        let home = try XCTUnwrap(source.range(of: "teamReadout(homeTeam,"))
        XCTAssertLessThan(away.lowerBound, home.lowerBound)
    }

    private static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
