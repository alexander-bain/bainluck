import XCTest
@testable import Bain_Luck

/// #9483 tennis — **a tennis reader inspects a dated recorded chance beside its
/// correctly labelled earlier baseline, opens the chart full size, and returns
/// to the same reading.**
///
/// The selected reference (`native-tennis-history-reader-v462`) called every
/// later point "Recorded in game" and its baseline "Last pre-match". Design's
/// 2026-10-20 finding: the app knows a SCHEDULED start at best, and an explicit
/// `commence_time_is_kickoff: false` makes the stored start Kalshi's expected
/// resolution. So the baseline exists only where `OddsChartView.sinceStartCut`
/// does and reads "Before scheduled start"; an inspected point is a "Recorded
/// chance" at its own time; a held reading that is no longer exactly there is
/// unavailable, never its neighbour.
@MainActor
final class TennisRecordedChanceBeforeScheduledStart9483Tests: XCTestCase {

    /// 2026-09-13T18:00:00Z — the scheduled start.
    private let start = Date(timeIntervalSince1970: 1_789_322_400)
    private let utc = TimeZone(identifier: "UTC")!
    private let us = Locale(identifier: "en_US")

    private func at(_ minutes: Double) -> Date { start.addingTimeInterval(minutes * 60) }

    private func point(_ minutes: Double, _ p: Double, source: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: at(minutes), probability: p, source: source)
    }

    private func stamp(_ minutes: Double) -> String {
        at(minutes).ISO8601Format()
    }

    /// Opening −180 min, last earlier −60, then a run from the start, a break of
    /// 160 min (the chart's own rule: > 600 s and > 15 × the 10-minute cadence),
    /// and a second run. Each served row carries its own away side.
    private let rows: [(Double, Double, Double)] = [
        (-180, 0.5758, 0.4242), (-60, 0.5599, 0.4401), (0, 0.60, 0.35),
        (10, 0.62, 0.38), (20, 0.64, 0.36), (180, 0.90, 0.10), (190, 0.9772, 0.0227),
    ]

    private func history(eventId: Int = 4242, rows: [(Double, Double, Double)]? = nil) throws -> EventHistoryResponse {
        let line = (rows ?? self.rows).map {
            #"{"timestamp":"\#(stamp($0.0))","home_probability":\#($0.1),"away_probability":\#($0.2)}"#
        }.joined(separator: ",")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(eventId),"home_team":"Alexander Zverev","away_team":"Ben Shelton",
         "status":"live","history":[],"aggregate_line":[\(line)]}
        """.utf8))
    }

    private func series(points: [ChartDataPoint]? = nil, scheduledStart: Date?,
                        finished: Bool = false, eventId: Int = 4242,
                        history: EventHistoryResponse? = nil) throws -> TennisChartReading9483.Series {
        let drawn = points ?? rows.map { point($0.0, $0.1) }
        return try XCTUnwrap(TennisChartReading9483.series(
            eventId: eventId, points: drawn, source: "aggregate", scheduledStart: scheduledStart,
            gameStart: start, finished: finished, history: try history ?? self.history()))
    }

    private func plain(_ s: String) -> String {
        s.replacingOccurrences(of: "\u{202F}", with: " ").replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    private func reading(_ shown: TennisChartReading9483.Shown) -> TennisChartReading9483.Reading? {
        if case .reading(let reading, _) = shown { return reading }
        return nil
    }

    // MARK: - The clock: a known resolution clock is never a start

    func testAnExplicitFalseStartFlagGivesNoBaselineAndNoBeforeStartWording() throws {
        let vetoed = OddsChartView.sinceStartCut(commenceTime: start, commenceTimeIsKickoff: false)
        let s = try series(scheduledStart: vetoed)
        XCTAssertNil(s.baseline, "a resolution clock minted a pre-start baseline")
        let early = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(-60)))))
        let heading = TennisChartReading9483.heading(for: early, scheduledStart: s.scheduledStart,
                                                     now: start, timeZone: utc, locale: us)
        XCTAssertEqual(plain(heading), "Recorded chance · 5:00 PM")
        // CONTROL — the same stored start, absent flag (the app's existing
        // scheduled fallback): a baseline exists, so the veto is what removed it.
        let scheduled = OddsChartView.sinceStartCut(commenceTime: start, commenceTimeIsKickoff: nil)
        XCTAssertNotNil(try series(scheduledStart: scheduled).baseline)
    }

    func testTheBaselineIsTheLastObservationBeforeTheScheduledStartAtItsOwnTime() throws {
        let s = try series(scheduledStart: start)
        let baseline = try XCTUnwrap(s.baseline)
        XCTAssertEqual(baseline.date, at(-60))
        XCTAssertEqual(baseline.home, 0.5599)
        XCTAssertEqual(baseline.away, 0.4401, "the served away side, not 1 − home")
        XCTAssertNotEqual(baseline.date, at(-180), "the baseline merged into the opening reading")
        XCTAssertEqual(plain(TennisChartReading9483.baselineHeading(for: baseline, now: start,
                                                                    timeZone: utc, locale: us)),
                       "Before scheduled start · 5:00 PM")
    }

    func testAnInspectedPointIsARecordedChanceNeverInGame() throws {
        let s = try series(scheduledStart: start)
        let late = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(190)))))
        let heading = plain(TennisChartReading9483.heading(for: late, scheduledStart: start,
                                                           now: start, timeZone: utc, locale: us))
        XCTAssertEqual(heading, "Recorded chance · 9:10 PM")
        let early = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(-180)))))
        XCTAssertEqual(plain(TennisChartReading9483.heading(for: early, scheduledStart: start,
                                                            now: start, timeZone: utc, locale: us)),
                       "Recorded chance before scheduled start · 3:00 PM")
    }

    /// An archived match's readings are dated, not just timed.
    func testAReadingFromAnotherDayCarriesItsDate() {
        let label = plain(TennisChartReading9483.time(at(190), now: start.addingTimeInterval(3 * 86_400),
                                                      timeZone: utc, locale: us))
        XCTAssertTrue(label.hasPrefix("Sep 13"), label)
        XCTAssertTrue(label.hasSuffix("9:10 PM"), label)
        XCTAssertEqual(plain(TennisChartReading9483.time(at(190), now: start, timeZone: utc, locale: us)),
                       "9:10 PM", "control: today prints the time alone")
    }

    // MARK: - Opening, baseline and inspected reading stay distinct

    func testTheSamePairNeverPrintsTwiceWhenTheReadingIsTheBaseline() throws {
        let s = try series(scheduledStart: start)
        let atBaseline = s.resolve(s.inspect(at: at(-60)))
        XCTAssertEqual(reading(atBaseline), s.baseline)
        XCTAssertNil(TennisChartReading9483.separateBaseline(s.baseline, shown: atBaseline))
        // CONTROL — any other reading keeps the baseline as its own block.
        let later = s.resolve(s.inspect(at: at(10)))
        XCTAssertEqual(TennisChartReading9483.separateBaseline(s.baseline, shown: later), s.baseline)
    }

    func testTheSuppliedSidesPrintAsSuppliedNotAsAComplement() throws {
        let s = try series(scheduledStart: start)
        let first = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(0)))))
        XCTAssertEqual(first.away, 0.35)
        let printed = TennisChartReading9483.labels(for: first)
        XCTAssertEqual(printed.home, "60%")
        XCTAssertEqual(printed.away, "35%", "the away side was rewritten as 1 − home")
        // CONTROL — a row with no away side prints the card's complement.
        let bare = TennisChartReading9483.Reading(eventId: 4242, source: "aggregate", date: at(0),
                                                  home: 0.60, away: nil)
        XCTAssertEqual(TennisChartReading9483.labels(for: bare).away, "40%")
    }

    func testAPushedFrameWithNoServedRowHasNoSuppliedAway() throws {
        let h = try history()
        XCTAssertEqual(TennisChartReading9483.suppliedAway(at: at(20), source: "aggregate", in: h), 0.36)
        XCTAssertNil(TennisChartReading9483.suppliedAway(at: at(21), source: "aggregate", in: h),
                     "a time between rows borrowed a neighbour's away side")
        XCTAssertNil(TennisChartReading9483.suppliedAway(at: at(20), source: "kalshi", in: h))
    }

    // MARK: - Gaps are never filled

    func testALiftInsideABreakHoldsTheBreakNotANeighbour() throws {
        let s = try series(scheduledStart: start)
        XCTAssertEqual(s.segments.count, 2, "fixture: the chart's own rule breaks the line once")
        XCTAssertEqual(s.inspect(at: at(100)), .gap(at(100)))
        XCTAssertEqual(s.resolve(.gap(at(100))), .gap(at(100)))
        // CONTROL — inside a run the nearest observation in that run is held.
        XCTAssertEqual(reading(s.resolve(s.inspect(at: at(13))))?.date, at(10))
        XCTAssertEqual(reading(s.resolve(s.inspect(at: at(186))))?.date, at(190))
        // Past either end the scrub reads that end, as `scrubbedDate` clamps.
        XCTAssertEqual(reading(s.resolve(s.inspect(at: at(-500))))?.date, at(-180))
        XCTAssertEqual(reading(s.resolve(s.inspect(at: at(500))))?.date, at(190))
    }

    // MARK: - Identity through arrivals: unavailable, never switched

    func testAHeldReadingSurvivesAnArrivalThatStillCarriesIt() throws {
        let before = try series(scheduledStart: start)
        let held = try XCTUnwrap(reading(before.resolve(before.inspect(at: at(10)))))
        var grown = rows
        grown.append((200, 0.99, 0.01))
        let after = try series(points: grown.map { point($0.0, $0.1) }, scheduledStart: start,
                               history: try history(rows: grown))
        XCTAssertEqual(after.resolve(.reading(held)), .reading(held, held: true))
        XCTAssertEqual(after.latest?.date, at(200), "control: the arrival did move the newest point")
    }

    func testACorrectedHeldReadingIsUnavailable() throws {
        let held = try XCTUnwrap(try series(scheduledStart: start).baseline)
        var corrected = rows
        corrected[1] = (-60, 0.5512, 0.4488)
        let after = try series(points: corrected.map { point($0.0, $0.1) }, scheduledStart: start,
                               history: try history(rows: corrected))
        XCTAssertEqual(after.resolve(.reading(held)), .unavailable)
    }

    func testAHeldReadingWhoseAwaySideAloneWasCorrectedIsUnavailable() throws {
        let held = try XCTUnwrap(try series(scheduledStart: start).baseline)
        var corrected = rows
        corrected[1] = (-60, 0.5599, 0.4300)
        let after = try series(points: corrected.map { point($0.0, $0.1) }, scheduledStart: start,
                               history: try history(rows: corrected))
        XCTAssertEqual(after.resolve(.reading(held)), .unavailable)
    }

    func testAMissingHeldReadingIsUnavailableNotItsNeighbour() throws {
        let held = try XCTUnwrap(try series(scheduledStart: start).baseline)
        let without = rows.filter { $0.0 != -60 }
        let after = try series(points: without.map { point($0.0, $0.1) }, scheduledStart: start,
                               history: try history(rows: without))
        XCTAssertEqual(after.resolve(.reading(held)), .unavailable)
        XCTAssertNotEqual(after.resolve(.reading(held)), after.resolve(nil),
                          "the held reading switched to the newest one")
    }

    func testADuplicatedHeldReadingIsUnavailable() throws {
        let held = try XCTUnwrap(try series(scheduledStart: start).baseline)
        let doubled = rows.map { point($0.0, $0.1) } + [point(-60, 0.5599)]
        let after = try series(points: doubled, scheduledStart: start)
        XCTAssertEqual(after.resolve(.reading(held)), .unavailable)
        XCTAssertNil(after.baseline, "an ambiguous baseline printed one of the two")
    }

    func testAnotherEventsReadingIsUnavailable() throws {
        let held = try XCTUnwrap(try series(scheduledStart: start).baseline)
        let other = try series(scheduledStart: start, eventId: 9999, history: try history(eventId: 9999))
        XCTAssertEqual(other.resolve(.reading(held)), .unavailable)
        // CONTROL — the same reading on its own event resolves.
        XCTAssertEqual(try series(scheduledStart: start).resolve(.reading(held)), .reading(held, held: true))
    }

    // MARK: - What is not a recorded chance

    func testASettledEndIsTheResultNotARecordedChance() throws {
        let points = rows.map { point($0.0, $0.1) } + [point(230, 1.0)]
        XCTAssertEqual(try series(points: points, scheduledStart: start, finished: true).latest?.date, at(190),
                       "a finished match's 100% end became the latest recorded chance")
        // CONTROL — an unfinished line keeps the same point.
        XCTAssertEqual(try series(points: points, scheduledStart: start, finished: false).latest?.date, at(230))
    }

    func testALiveEdgeReServeIsNotAReading() throws {
        var edge = point(240, 0.97)
        edge.isLiveEdge = true
        let s = try series(points: rows.map { point($0.0, $0.1) } + [edge], scheduledStart: start)
        XCTAssertEqual(s.latest?.date, at(190))
    }

    func testAnotherSeriesIsNotRead() throws {
        let mixed = rows.map { point($0.0, $0.1) } + [point(195, 0.40, source: "kalshi")]
        XCTAssertEqual(try series(points: mixed, scheduledStart: start).latest?.date, at(190))
    }

    // MARK: - The held reading

    func testOpeningFullSizeHoldsTheShownReadingAndAnArrivalDoesNotMoveIt() throws {
        let pin = TennisReadingPin9483()
        let s = try series(scheduledStart: start)
        pin.holdShown(s.resolve(pin.held))
        XCTAssertEqual(pin.held, .reading(try XCTUnwrap(s.latest)))
        var grown = rows
        grown.append((200, 0.99, 0.01))
        let after = try series(points: grown.map { point($0.0, $0.1) }, scheduledStart: start,
                               history: try history(rows: grown))
        XCTAssertEqual(reading(after.resolve(pin.held))?.date, at(190), "the return found a different reading")
    }

    func testOpeningFullSizeNeverReplacesAReadingAlreadyHeld() throws {
        let pin = TennisReadingPin9483()
        let s = try series(scheduledStart: start)
        pin.hold(s.inspect(at: at(10)))
        pin.holdShown(s.resolve(nil))
        XCTAssertEqual(reading(s.resolve(pin.held))?.date, at(10))
        // An unavailable reading is not replaced by opening either.
        pin.hold(.gap(at(100)))
        pin.holdShown(s.resolve(pin.held))
        XCTAssertEqual(pin.held, .gap(at(100)))
    }

    func testShowLatestIsTheReadersExplicitChoice() throws {
        let pin = TennisReadingPin9483()
        let s = try series(scheduledStart: start)
        pin.hold(.gap(at(100)))
        pin.holdLatest(in: s)
        XCTAssertEqual(pin.held, .reading(try XCTUnwrap(s.latest)))
    }

    // MARK: - Wiring (source scans; the behaviour above is worthless unasked)

    private func code(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func stripped(_ path: String) throws -> String {
        try code(path).filter { !$0.isWhitespace }
    }

    /// Code only: every `//` comment removed, so a rule cannot pass on prose.
    private func codeOnly(_ path: String) throws -> String {
        try code(path).split(separator: "\n", omittingEmptySubsequences: false).map { line -> String in
            guard let comment = line.range(of: "//") else { return String(line) }
            return String(line[..<comment.lowerBound])
        }.joined(separator: "\n")
    }

    private let chartPath = "Bain Luck/Components/OddsChartView.swift"
    private let helperPath = "Bain Luck/Components/TennisChartReading9483.swift"

    func testTheChartTakesItsScheduledStartFromTheExistingVetoedCut() throws {
        let chart = try stripped(chartPath)
        XCTAssertTrue(chart.contains(
            "Self.sinceStartCut(commenceTime:gameStartDate,commenceTimeIsKickoff:vm.history?.commenceTimeIsKickoff)"),
                      "the kickoff cut no longer honours the payload's veto")
        XCTAssertTrue(chart.contains("scheduledStart:kickoffDate,gameStart:gameStartDate,"),
                      "the tennis baseline reads a start other than the vetoed cut")
        XCTAssertTrue(chart.contains("guardTennisChartReading9483.applies(sportKey:sportKey),checkpoints==nilelse{returnnil}"),
                      "the tennis panel mounts over a checkpoint chart, whose scrub lands on checkpoints")
    }

    func testNoTennisReadingIsBadgedPregameAndOtherSportsKeepTheirCut() throws {
        let chart = try stripped(chartPath)
        XCTAssertTrue(chart.contains("ifTennisChartReading9483.applies(sportKey:sportKey){return.chart(playStart:nil,"))
        XCTAssertTrue(chart.contains("return.chart(playStart:sinceStartDate,gameFinished:EventState.isFinished(status),"),
                      "control: every other sport still reads the chart's own Since Start cut")
    }

    func testTheFullSizeChartShowsTheReadingAndTheLiftHoldsIt() throws {
        let chart = try stripped(chartPath)
        XCTAssertTrue(chart.contains(
            "iflettennis{TennisScrubbedReadingPanel9483(selection:selection,panel:tennisPanel(tennis,expanded:true))}elseifletcard=Self.fullscreenReadout("),
                      "the full-size chart lost the tennis reading, or it displaced other sports' card")
        XCTAssertTrue(chart.contains("iflettennis,letdate=selection.date{tennisPin.hold(tennis.inspect(at:date))}selection.end()"),
                      "a lifted finger must hold its reading before the selection clears")
        XCTAssertTrue(chart.contains("tennisPanel(tennis,expanded:false)"), "the page lost the held reading")
        XCTAssertTrue(chart.contains("TennisHeldReadingMarker9483(pin:tennisPin,selection:selection,series:tennis,"))
        XCTAssertTrue(chart.contains("@StateprivatevartennisPin=TennisReadingPin9483()"),
                      "the held reading must be the one the inline chart and its cover share")
        XCTAssertEqual(chart.components(separatedBy: "lettennis=tennisSeries(enriched:enrichedPoints,checkpoints:checkpoints)").count - 1, 2,
                       "inline and full size must read the same series")
    }

    func testThePanelMountsOnTheCoverAndHoldsWhatItShowsOnOpening() throws {
        let helper = try stripped(helperPath)
        XCTAssertTrue(helper.contains("ifexpanded||pin.held!=nil{content(shown).onAppear{ifexpanded{pin.holdShown(series.resolve(pin.held))}}}"))
    }

    /// The panel prints probabilities and clocks only: no score, no projected
    /// games, no finish clock. A completed result is the hero's, in sets.
    func testTheReadingNeverReadsScoresProjectionsOrAFinishClock() throws {
        let helper = try codeOnly(helperPath)
        for forbidden in ["homeScore", "awayScore", "projected", "Projected", "completedAt", "sets"] {
            XCTAssertFalse(helper.contains(forbidden), forbidden)
        }
    }

    func testTheReadingNeverClaimsPlay() throws {
        let helper = try codeOnly(helperPath)
        for claim in ["in game", "In game", "pre-match", "Pre-match", "Pregame", "pregame", "Last pre"] {
            XCTAssertFalse(helper.contains(claim), claim)
        }
        XCTAssertTrue(helper.contains("\"Recorded chance\""))
        XCTAssertTrue(helper.contains("\"Before scheduled start\""))
    }
}
