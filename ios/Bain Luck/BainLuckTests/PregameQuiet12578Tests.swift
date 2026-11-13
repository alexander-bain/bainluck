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

    // MARK: - 1. No venue name in the header (137-A)

    func testThePropsHeaderNamesNoVenue() throws {
        let source = try Self.source("Bain Luck/Components/PlayerPropsCardView.swift")
        let header = try XCTUnwrap(source.range(of: "Text(\"Player Props\")"))
        let chain = String(source[header.upperBound...].prefix(220))
        XCTAssertTrue(chain.contains("Spacer()"), chain)
        for venue in ["SourceLabels", "sources.first", "from \\(", "Kalshi", "Capsule"] {
            XCTAssertFalse(chain.contains(venue), "the header carries no \(venue)")
        }
        XCTAssertFalse(source.contains("sourceCredit12578"))
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
        XCTAssertTrue(inside.contains("Text(Self.recordedLine(for: full))"), "the recorded times are behind the disclosure")
        XCTAssertEqual(source.components(separatedBy: "Text(Self.recordedLine(").count, 2, "and nowhere else")
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

/// #11220 follow-up on #12578 — a finished period prints no clock. Production
/// served `period: "Final"` with `game_clock: "12:00"` for event 15344868 (Lakers
/// at Hawks), and the title read "LAL 124 - ATL 114 • Final 12:00".
final class FinishedPeriodClock12578Tests: XCTestCase {
    func testAFinalWithAResetClockSaysFinalAlone() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "Final", gameClock: "12:00"), "Final")
    }

    func testEveryFinishedPeriodDropsItsClock() {
        // Non-zero clocks throughout, so the spent-clock rule can't be what drops them
        // (Builder C's review: "End of 4th Quarter" + "0:00" passed for that reason).
        for (period, clock) in [("Final/OT", "5:00"), ("FT", "90'"), ("Full Time", "45:00"), ("AET", "120'"),
                                ("End of 4th Quarter", "12:00"), ("End of 1st Half", "20:00"),
                                ("final", "12:00"), ("Ended", "3:10"), ("Game Over", "1:00")] {
            let text = PeriodLabel.liveStatusText(period: period, gameClock: clock) ?? ""
            XCTAssertFalse(text.contains(clock), "\(period) + \(clock) printed \(text)")
        }
    }

    func testALivePeriodKeepsItsClock() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "2nd Quarter", gameClock: "5:11"), "Q2 5:11")
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "4th Quarter", gameClock: "12:00"), "Q4 12:00",
                       "a live period's 12:00 is a real clock")
        XCTAssertFalse(PeriodLabel.isFinishedPeriod("Overtime"))
        XCTAssertFalse(PeriodLabel.isFinishedPeriod("Halftime"), "halftime is its own label, not a finished game")
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "End of 4th Quarter", gameClock: "12:00"), "Q4",
                       "the raw period says the quarter is over, though its label reads Q4")
    }
}

/// #12578 — three more on the core game page, each checked on build 5704 first.
final class GamePageOrderAndNames12578Tests: XCTestCase {
    private static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// #11547 — Alex, build 82: "What the heck is a 'question'?!"
    func testNoRelatedMarketsTabIsCalledAQuestion() {
        for name in Array(RelatedMarketsCatalog.familyNames.values) + RelatedMarketsCatalog.familyOrder + [RelatedMarketsCatalog.fallbackFamily] {
            XCTAssertFalse(name.lowercased().contains("question"), "a tab reads \"\(name)\"")
        }
        XCTAssertEqual(RelatedMarketsCatalog.fallbackFamily, "Other markets")
    }

    /// The props filter follows the title: away first.
    func testThePropsTeamFilterListsAwayBeforeHome() throws {
        let source = try Self.source("Bain Luck/Components/PlayerPropsCardView.swift")
        let away = try XCTUnwrap(source.range(of: "filterButton(awayAbbr, value: \"away\")"))
        let home = try XCTUnwrap(source.range(of: "filterButton(homeAbbr, value: \"home\")"))
        XCTAssertLessThan(away.lowerBound, home.lowerBound)
    }

    /// #11546 — Totals read 56+, 58+, then 36+: the ladder is drawn low to high.
    func testATotalsLadderServedOutOfOrderIsDrawnLowToHigh() throws {
        func rung(_ bound: Int, period: String = "full_game", side: String = "game", key: String? = nil) -> String {
            #"{"question_key":"\#(key ?? "q:\(period)|\(side)|ge:\(bound)")","kind":"count_threshold","label":"\#(bound)+ points","display_scope":"game","#
                + #""quantity":{"key":"points"},"period":{"key":"\#(period)"},"subject":{"side":"\#(side)"},"#
                + #""predicate":{"relation":"ge","bound":\#(bound),"line":\#(Double(bound) - 0.5)},"options":[]}"#
        }
        let named = #"{"question_key":"q:winner","kind":"named_options","label":"Winner","display_scope":"game","options":[]}"#
        let served = [rung(56), rung(58), named, rung(36), rung(40), rung(10, period: "q1"), rung(38), rung(2, period: "q1")]
        let json = #"{"display_scope":"game","questions":["# + served.joined(separator: ",") + "]}"
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let matrix = try decoder.decode(EventQuestionMatrix.self, from: Data(json.utf8))
        let keys = EventQuestionMatrixAdapter.ladderOrdered(matrix.questions).map(\.questionKey)
        XCTAssertEqual(keys, ["q:full_game|game|ge:36", "q:full_game|game|ge:38", "q:winner", "q:full_game|game|ge:40",
                              "q:full_game|game|ge:56", "q:q1|game|ge:2", "q:full_game|game|ge:58", "q:q1|game|ge:10"],
                       "each ladder sorts inside its own slots; the winner question and the quarter ladder keep their places")
    }
}
