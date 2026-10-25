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
///
/// lane1b's 2026-10-20 review of `dba9a21648` set two contracts this file now
/// pins: a finished series loses ONE result row (the last served, at exactly
/// 0 or 1), never earlier certainty; and the away side is chosen by the
/// source — the blend prints its exhaustive complement without a lookup, the
/// sportsbook consensus prints the side it supplied from exactly one row, and
/// nothing else invents one.
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
    /// and a second run. The third value is the away side a sportsbook
    /// consensus row supplies on its own; the blend's rows never carry one.
    private let rows: [(Double, Double, Double)] = [
        (-180, 0.5758, 0.4242), (-60, 0.5599, 0.4401), (0, 0.60, 0.35),
        (10, 0.62, 0.38), (20, 0.64, 0.36), (180, 0.90, 0.10), (190, 0.9772, 0.0227),
    ]

    private func decode(eventId: Int, history: String, aggregateLine: String?) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let line = aggregateLine.map { #","aggregate_line":[\#($0)]"# } ?? ""
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(eventId),"home_team":"Alexander Zverev","away_team":"Ben Shelton",
         "status":"live","history":[\(history)]\(line)}
        """.utf8))
    }

    /// The blend, production-shaped: an `aggregate_line` row is `{timestamp,
    /// home_probability}` only (events.py writes no away side).
    private func history(eventId: Int = 4242, rows: [(Double, Double, Double)]? = nil) throws -> EventHistoryResponse {
        let line = (rows ?? self.rows).map {
            #"{"timestamp":"\#(stamp($0.0))","home_probability":\#($0.1)}"#
        }.joined(separator: ",")
        return try decode(eventId: eventId, history: "", aggregateLine: line)
    }

    /// The sportsbook consensus: each `history` row carries the away side it
    /// aggregated apart from home (nil prints `null`), in the order given.
    private func consensusHistory(eventId: Int = 4242,
                                  rows: [(Double, Double, Double?)]) throws -> EventHistoryResponse {
        let served = rows.map { row -> String in
            let away = row.2.map { "\($0)" } ?? "null"
            return #"{"timestamp":"\#(stamp(row.0))","home_probability":\#(row.1),"away_probability":\#(away),"bookmaker_count":7}"#
        }.joined(separator: ",")
        return try decode(eventId: eventId, history: served, aggregateLine: nil)
    }

    private func series(points: [ChartDataPoint]? = nil, scheduledStart: Date?,
                        finished: Bool = false, eventId: Int = 4242, source: String = "aggregate",
                        history: EventHistoryResponse? = nil) throws -> TennisChartReading9483.Series {
        let drawn = points ?? rows.map { point($0.0, $0.1, source: source) }
        return try XCTUnwrap(TennisChartReading9483.series(
            eventId: eventId, points: drawn, source: source, scheduledStart: scheduledStart,
            gameStart: start, finished: finished, history: try history ?? self.history()))
    }

    private func consensus(rows: [(Double, Double, Double)]? = nil,
                           history: EventHistoryResponse? = nil) throws -> TennisChartReading9483.Series {
        let served = rows ?? self.rows
        return try series(points: served.map { point($0.0, $0.1, source: "consensus") }, scheduledStart: start,
                          source: "consensus",
                          history: try history ?? consensusHistory(rows: served.map { ($0.0, $0.1, $0.2) }))
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
        XCTAssertNil(baseline.away, "the blend's away side is printed as its complement, never looked up")
        XCTAssertEqual(TennisChartReading9483.labels(for: baseline).away, "44%")
        XCTAssertNotEqual(baseline.date, at(-180), "the baseline merged into the opening reading")
        // The sportsbook consensus baseline keeps the away side its row supplied.
        let supplied = try XCTUnwrap(try consensus().baseline)
        XCTAssertEqual(supplied.date, at(-60))
        XCTAssertEqual(supplied.away, 0.4401, "the supplied away side, not 1 − home")
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

    // MARK: - The away side, by the source's contract

    /// The sportsbook consensus aggregates away apart from home, so its pair is
    /// independent (60% / 35%) and prints as supplied.
    func testTheConsensusSuppliedSidePrintsAsSuppliedNotAsAComplement() throws {
        let s = try consensus()
        let first = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(0)))))
        XCTAssertEqual(first.away, 0.35)
        let printed = TennisChartReading9483.labels(for: first)
        XCTAssertEqual(printed.home, "60%")
        XCTAssertEqual(printed.away, "35%", "the away side was rewritten as 1 − home")
        XCTAssertEqual(first.date, at(0), "the reading keeps its own observation time")
    }

    /// A duplicate, a missing row or a null away side leaves the slot empty —
    /// never the old `1 − home` fallback.
    func testAConsensusSideThatCannotBeFoundExactlyOncePrintsNoAway() throws {
        let duplicated = try consensusHistory(rows: rows.map { ($0.0, $0.1, $0.2) } + [(0, 0.60, 0.35)])
        let twice = try consensus(history: duplicated)
        let atDuplicate = twice.reading(for: point(0, 0.60, source: "consensus"))
        XCTAssertNil(atDuplicate.away)
        XCTAssertEqual(TennisChartReading9483.labels(for: atDuplicate).away, "", "a duplicate printed 35%")
        let s = try consensus()
        let pushed = s.reading(for: point(21, 0.63, source: "consensus"))
        XCTAssertNil(pushed.away, "a time between rows borrowed a neighbour's away side")
        XCTAssertEqual(TennisChartReading9483.labels(for: pushed).away, "", "a missing row printed 37%")
        let nullAway = try consensus(history: try consensusHistory(rows: [(-60, 0.5599, nil), (0, 0.60, 0.35)]))
        let bare = nullAway.reading(for: point(-60, 0.5599, source: "consensus"))
        XCTAssertNil(bare.away)
        XCTAssertEqual(TennisChartReading9483.labels(for: bare).away, "", "a null away side printed 44%")
        // CONTROL — the same series finds the single row it does serve.
        XCTAssertEqual(TennisChartReading9483.labels(for: s.reading(for: point(0, 0.60, source: "consensus"))).away,
                       "35%")
    }

    func testConsensusRowsServedNewestFirstStillPrintTheSuppliedSide() throws {
        let h = try consensusHistory(rows: rows.reversed().map { ($0.0, $0.1, $0.2) })
        XCTAssertEqual(TennisChartReading9483.suppliedAway(at: at(20), source: "consensus", in: h), 0.36)
        XCTAssertEqual(TennisChartReading9483.suppliedAway(at: at(-180), source: "consensus", in: h), 0.4242)
        let s = try consensus(history: h)
        XCTAssertEqual(TennisChartReading9483.labels(for: try XCTUnwrap(s.baseline)).away, "44%")
        XCTAssertEqual(s.baseline?.away, 0.4401)
    }

    /// The blend serves no away side; its pair is the exhaustive binary
    /// complement the chart's readout already prints — on a served row and on a
    /// pushed frame with no row alike, and with no lookup either way.
    func testTheBlendPrintsItsComplementWithoutALookup() throws {
        let s = try series(scheduledStart: start)
        let served = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(0)))))
        XCTAssertNil(served.away)
        XCTAssertEqual(TennisChartReading9483.labels(for: served).home, "60%")
        XCTAssertEqual(TennisChartReading9483.labels(for: served).away, "40%")
        let pushed = s.reading(for: point(21, 0.63))
        XCTAssertNil(pushed.away)
        XCTAssertEqual(TennisChartReading9483.labels(for: pushed).away, "37%")
        XCTAssertNil(TennisChartReading9483.suppliedAway(at: at(20), source: "aggregate", in: try history()),
                     "the blend's away side was looked up")
    }

    /// A venue line decodes no away side, so none prints.
    func testAVenueSeriesPrintsNoAway() throws {
        let venue = try series(scheduledStart: start, source: "kalshi")
        let held = try XCTUnwrap(reading(venue.resolve(venue.inspect(at: at(0)))))
        XCTAssertEqual(held.source, "kalshi")
        XCTAssertNil(held.away)
        XCTAssertEqual(TennisChartReading9483.labels(for: held).home, "60%")
        XCTAssertEqual(TennisChartReading9483.labels(for: held).away, "", "a venue line invented 40%")
        XCTAssertNil(TennisChartReading9483.suppliedAway(at: at(20), source: "kalshi",
                                                         in: try consensusHistory(rows: rows.map { ($0.0, $0.1, $0.2) })))
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
        let held = try XCTUnwrap(try consensus().baseline)
        XCTAssertEqual(held.away, 0.4401, "fixture: the consensus row supplies its own away side")
        var corrected = rows
        corrected[1] = (-60, 0.5599, 0.4300)
        let after = try consensus(rows: corrected)
        XCTAssertEqual(after.resolve(.reading(held)), .unavailable)
        // CONTROL — the uncorrected consensus series still finds it.
        XCTAssertEqual(try consensus().resolve(.reading(held)), .reading(held, held: true))
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

    /// Only the ONE result row goes. Certainty recorded before it is a genuine
    /// reading, and a reader holding one keeps it when the match finishes.
    func testCertaintyRecordedBeforeTheResultRowStaysARecordedChance() throws {
        let live = rows.map { point($0.0, $0.1) } + [point(200, 0.98), point(205, 1.0)]
        let before = try series(points: live, scheduledStart: start)
        let held = try XCTUnwrap(reading(before.resolve(before.inspect(at: at(205)))))
        XCTAssertEqual(held.home, 1.0)
        let finished = try series(points: live + [point(210, 1.0)], scheduledStart: start, finished: true)
        XCTAssertEqual(finished.latest?.date, at(205), "genuine certainty before the result row was dropped")
        XCTAssertEqual(finished.resolve(.reading(held)), .reading(held, held: true))
        XCTAssertNil(finished.points.first { $0.date == at(210) }, "control: the result row itself is excluded")
    }

    /// The result row's minute can equal the last genuine row's (1% then 0% at
    /// one stamp). Served last, it is the one removed; the genuine reading stays
    /// unique and a held one resolves.
    func testAResultRowOnTheLastGenuineRowsTimeLeavesThatReadingHeld() throws {
        let live = rows.map { point($0.0, $0.1) } + [point(200, 0.01)]
        let before = try series(points: live, scheduledStart: start)
        let held = try XCTUnwrap(before.latest)
        XCTAssertEqual(held.home, 0.01)
        let finished = try series(points: live + [point(200, 0.0)], scheduledStart: start, finished: true)
        XCTAssertEqual(finished.points.filter { $0.date == at(200) }.count, 1)
        XCTAssertEqual(finished.latest, held, "the genuine reading at the result's time was lost")
        XCTAssertEqual(finished.resolve(.reading(held)), .reading(held, held: true))
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

    // MARK: - Design C1: both competitors' lines, by the source contract

    private func vertices(_ runs: [[PairedWinVertex9483]]) -> [[String]] {
        runs.map { $0.map { "\(Int(($0.date.timeIntervalSince(start) / 60).rounded()))@\($0.probability)" } }
    }

    /// The blend's second line is its exhaustive complement, vertex for
    /// vertex, in one run — the same number the panel prints for that side.
    func testTheBlendDrawsTheSecondCompetitorAsItsComplement() {
        let run = [point(0, 0.60), point(10, 0.62), point(20, 0.75)]
        let away = TennisChartReading9483.awayRuns(run, source: "aggregate", supplied: [:])
        XCTAssertEqual(away.count, 1, "the blend's second line broke a run it has no break in")
        XCTAssertEqual(away.first?.map(\.date), run.map(\.date))
        for (drawn, expected) in zip(away.first?.map(\.probability) ?? [], [0.40, 0.38, 0.25]) {
            XCTAssertEqual(drawn, expected, accuracy: 1e-12)
        }
        XCTAssertEqual(away.first?.count, 3)
    }

    /// The consensus draws ONLY the side it supplied, at exactly that time:
    /// a null away side or a duplicated row breaks the line there — never a
    /// neighbour, never `1 − home`, and never normalised against home.
    func testTheConsensusDrawsOnlyTheSideItSuppliedAndBreaksWhereItSuppliedNone() throws {
        let h = try consensusHistory(rows: [
            (-60, 0.5599, 0.4401), (0, 0.60, nil), (10, 0.62, 0.35), (20, 0.64, 0.33),
            (180, 0.90, 0.10), (180, 0.90, 0.12), (190, 0.9772, 0.0227),
        ])
        let supplied = TennisChartReading9483.suppliedAways(in: h)
        let run = [-60.0, 0, 10, 20, 180, 190].map { point($0, 0.5, source: "consensus") }
        let away = TennisChartReading9483.awayRuns(run, source: "consensus", supplied: supplied)
        XCTAssertEqual(vertices(away), [["-60@0.4401"], ["10@0.35", "20@0.33"], ["190@0.0227"]],
                       "the consensus line must print its supplied sides and break at a null and a duplicate")
        // CONTROL — the same run read as the blend is one unbroken complement,
        // so the breaks above are the consensus contract, not the run.
        XCTAssertEqual(TennisChartReading9483.awayRuns(run, source: "aggregate", supplied: supplied).count, 1)
    }

    func testAVenueSeriesDrawsNoSecondCompetitor() throws {
        let supplied = TennisChartReading9483.suppliedAways(in: try consensusHistory(rows: [(0, 0.60, 0.35)]))
        for venue in ["kalshi", "polymarket", "espn"] {
            XCTAssertEqual(TennisChartReading9483.awayRuns([point(0, 0.60, source: venue)], source: venue,
                                                           supplied: supplied).count, 0, venue)
        }
    }

    /// The live edge's away tail and its endpoint label are the blend's alone:
    /// no other source supplied a `1 − home` side to draw there.
    func testOnlyTheBlendDrawsTheAwayTail() {
        typealias R = TennisChartReading9483
        XCTAssertTrue(R.drawsAwayTail(source: "aggregate"))
        for other in ["consensus", "kalshi", "polymarket"] {
            XCTAssertFalse(R.drawsAwayTail(source: other), "\(other) would draw a complement it never supplied")
        }
    }

    /// The whole-line map is the one-time lookup's rule, read once: they agree
    /// at every served time, including a null side and a duplicate.
    func testTheSuppliedAwaysAgreeWithTheOneTimeLookup() throws {
        let served: [(Double, Double, Double?)] = [(-60, 0.5599, nil), (0, 0.60, 0.35), (10, 0.62, 0.38),
                                                   (10, 0.62, 0.38), (20, 0.64, 0.36)]
        let h = try consensusHistory(rows: Array(served.reversed()))
        let supplied = TennisChartReading9483.suppliedAways(in: h)
        for minutes in [-60.0, 0, 10, 20, 30] {
            XCTAssertEqual(supplied[at(minutes)],
                           TennisChartReading9483.suppliedAway(at: at(minutes), source: "consensus", in: h),
                           "\(minutes)")
        }
        XCTAssertEqual(supplied.count, 2, "only 0 and 20 supply exactly one away side")
        XCTAssertEqual(TennisChartReading9483.suppliedAways(in: nil), [:])
    }

    func testBothCompetitorsDrawOnlyOverOneSeriesWithAnAwayContract() throws {
        let points = [point(0, 0.60, source: "consensus"), point(10, 0.62, source: "consensus")]
        let supplying = TennisChartReading9483.suppliedAways(in: try consensusHistory(rows: [(0, 0.60, 0.35)]))
        let silent = TennisChartReading9483.suppliedAways(in: try consensusHistory(rows: [(0, 0.60, nil)]))
        typealias R = TennisChartReading9483
        XCTAssertTrue(R.drawsBothCompetitors(drawnSources: ["aggregate"], points: [point(0, 0.6)], supplied: [:]))
        XCTAssertTrue(R.drawsBothCompetitors(drawnSources: ["consensus"], points: points, supplied: supplying))
        XCTAssertFalse(R.drawsBothCompetitors(drawnSources: ["consensus"], points: points, supplied: silent),
                       "a consensus that supplied no away side would key a line that draws nothing")
        XCTAssertFalse(R.drawsBothCompetitors(drawnSources: ["consensus", "kalshi"], points: points, supplied: supplying),
                       "several unblended lines keep today's chart")
        XCTAssertFalse(R.drawsBothCompetitors(drawnSources: ["kalshi"], points: [point(0, 0.6, source: "kalshi")],
                                              supplied: supplying), "no opponent series is invented for a venue")
    }

    /// The held marker's second dot sits at the value the panel prints for
    /// that side, and nowhere the panel prints none.
    func testTheHeldMarkersSecondDotSitsWhereThePanelPrints() throws {
        let blend = try series(scheduledStart: start)
        let blended = try XCTUnwrap(reading(blend.resolve(blend.inspect(at: at(10)))))
        XCTAssertEqual(try XCTUnwrap(TennisChartReading9483.awayValue(for: blended)), 0.38, accuracy: 1e-12)
        let books = try consensus()
        let supplied = books.reading(for: point(0, 0.60, source: "consensus"))
        XCTAssertEqual(TennisChartReading9483.awayValue(for: supplied), 0.35, "not the 40% complement")
        XCTAssertNil(TennisChartReading9483.awayValue(for: books.reading(for: point(21, 0.63, source: "consensus"))))
        for r in [blended, supplied] {
            XCTAssertEqual(GamePlayCardView.printedLabels(home: r.home, away: TennisChartReading9483.awayValue(for: r)).away,
                           TennisChartReading9483.labels(for: r).away)
        }
    }

    // MARK: - Design C2: one compact comparison, Show latest after it

    func testTheComparisonNamesOnceThenTheTwoPairsThenShowLatest() throws {
        let s = try series(scheduledStart: start)
        let held = try XCTUnwrap(reading(s.resolve(s.inspect(at: at(180)))))
        let baseline = try XCTUnwrap(s.baseline)
        typealias R = TennisChartReading9483
        XCTAssertEqual(R.panelParts(shown: .reading(held, held: true), baseline: baseline, offersLatest: true),
                       [.names, .shown(.reading(held, held: true)), .baseline(baseline), .showLatest],
                       "the baseline must sit directly under the reading, with Show latest after both")
        XCTAssertEqual(R.panelParts(shown: .gap(at(100)), baseline: baseline, offersLatest: true),
                       [.names, .shown(.gap(at(100))), .baseline(baseline), .showLatest])
        XCTAssertEqual(R.panelParts(shown: .unavailable, baseline: nil, offersLatest: true),
                       [.shown(.unavailable), .showLatest], "no names head an empty table")
        XCTAssertEqual(R.panelParts(shown: .reading(baseline, held: true), baseline: baseline, offersLatest: false),
                       [.names, .shown(.reading(baseline, held: true))], "the same pair never prints twice")
    }

    /// A name breaks only at a space or after a hyphen or slash, so those are
    /// the pieces the columns must fit whole (lane1b R2).
    func testANameSplitsOnlyWhereALineMayBreak() {
        typealias R = TennisChartReading9483
        XCTAssertEqual(R.unbreakablePieces(of: "Medvedev"), ["Medvedev"])
        XCTAssertEqual(R.unbreakablePieces(of: "Granollers/Zeballos"), ["Granollers/", "Zeballos"])
        XCTAssertEqual(R.unbreakablePieces(of: "Auger-Aliassime"), ["Auger-", "Aliassime"])
        XCTAssertEqual(R.unbreakablePieces(of: "de Minaur"), ["de", "Minaur"])
        XCTAssertEqual(R.unbreakablePieces(of: "Davidovich Fokina / Carreño"),
                       ["Davidovich", "Fokina", "/", "Carreño"])
        XCTAssertEqual(R.unbreakablePieces(of: ""), [])
    }

    /// The column is the wider of the values' width and the widest name piece,
    /// rounded up so the piece is never a fraction too wide for it.
    func testAValueColumnWidensForALongNameAndNeverNarrowsBelowTheValues() {
        typealias R = TennisChartReading9483
        XCTAssertEqual(R.valueColumn(forValues: 52, widestNamePiece: 56.4), 57,
                       "a 52pt column cuts off Medvedev and Sabalenka")
        XCTAssertEqual(R.valueColumn(forValues: 52, widestNamePiece: 37.5), 52, "Zverev keeps the values' width")
        XCTAssertEqual(R.valueColumn(forValues: 64, widestNamePiece: 0), 64, "before the names are measured")
    }

    // MARK: - Design C3: the full-size header keeps the match and its result

    func testTheFullSizeHeaderNamesTheMatchAndItsFinalSetsResult() {
        typealias C = TennisMatchContext9483
        XCTAssertEqual(C.matchup(home: "Zverev", away: "Shelton"), "Zverev · Shelton")
        XCTAssertEqual(C.result(finished: true, homeScore: 3, awayScore: 1, sportKey: "tennis_atp_us_open"),
                       "Final · 3–1 sets", "the result is the scoreboard's, home first, named in sets")
        XCTAssertEqual(C.result(finished: true, homeScore: 1, awayScore: 3, sportKey: "tennis_wta_us_open"),
                       "Final · 1–3 sets")
        XCTAssertEqual(C.result(finished: true, homeScore: nil, awayScore: 1, sportKey: "tennis_atp_us_open"), "Final",
                       "a missing side is no result, never an invented one")
        XCTAssertNil(C.result(finished: false, homeScore: 2, awayScore: 1, sportKey: "tennis_atp_us_open"),
                     "a live match's state is the cover's live status, not a claimed result")
        // CONTROL — the unit is the scoreboard's own: a sport that counts what
        // its market quotes names none.
        XCTAssertEqual(C.result(finished: true, homeScore: 24, awayScore: 17, sportKey: "americanfootball_nfl"),
                       "Final · 24–17")
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
            "iflettennis{ifenlargedPlotFloor==nil{TennisScrubbedReadingPanel9483(selection:selection,panel:tennisPanel(tennis,expanded:true))}}elseifletcard=Self.fullscreenReadout("),
                      "the full-size chart lost the tennis reading, or it displaced other sports' card")
        // #10796 — enlarged finished tennis reads it below the plot instead.
        XCTAssertTrue(chart.contains(
            "momentCaption(moments)ifenlargedPlotFloor!=nil,lettennis{TennisScrubbedReadingPanel9483(selection:selection,panel:tennisPanel(tennis,expanded:true))}}.padding()"),
                      "an enlarged finished-tennis cover lost the reading below its plot")
        XCTAssertTrue(chart.contains(".frame(height:enlargedPlotFloor)legendView("),
                      "the enlarged plot no longer keeps the inline chart's height")
        XCTAssertTrue(chart.contains(".modifier(FullscreenOverflowScroll10796(scrolls:enlargedPlotFloor!=nil))"),
                      "the enlarged cover no longer scrolls")
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

    private let contextPath = "Bain Luck/Components/TennisMatchContext9483.swift"
    private let pagePath = "Bain Luck/Views/EventDetailView.swift"

    /// #11356 (Design's native single-trajectory brief, from the web chart
    /// accepted at 89f9ba03a2) supersedes Design C1's two tennis lines: every
    /// two-competitor chart draws ONE line — the primary series, in its own
    /// colour on both sides of 50% — and the two players are named as the
    /// axis's two DIRECTIONS outside the plot (the gutter poles, which now stay
    /// on), never as a second line. The tennis panel, its held reading and its
    /// marker are unchanged; the marker loses only the second dot it put on
    /// the second line. Unexecuted until Native's Apple run.
    func testTheChartDrawsOneLineAndNamesBothPlayersAsDirections() throws {
        let chart = try codeOnly(chartPath).filter { !$0.isWhitespace }
        for retired in ["tennisPairedLines(", "PairedWinLines9483.awayRun(", "PairedWinLines9483.awayTail(",
                        "TennisChartReading9483.awayRuns(", "TennisChartReading9483.suppliedAways(",
                        "pairedGutterHidden9483(", "pairedLegendKey(", "PairedAwayEndpointLabel9483("] {
            XCTAssertFalse(chart.contains(retired), "a second competitor line is drawn again: \(retired)")
        }
        XCTAssertTrue(chart.contains("TennisHeldReadingMarker9483(pin:tennisPin,selection:selection,series:tennis,"),
                      "control: the scan reads the held marker's call")
        XCTAssertTrue(chart.contains("awayColor:nil)"), "the held marker puts a dot on a line that is not drawn")
        XCTAssertEqual(chart.components(separatedBy: "ChartGutterDirection9483(rising:true,").count - 1, 2,
                       "both gutters name the home player as the line's upward direction")
        XCTAssertEqual(chart.components(separatedBy: "ChartGutterDirection9483(rising:false,").count - 1, 2,
                       "both gutters name the away player as its downward direction")
    }

    func testThePanelIsOneComparisonWithShowLatestAfterIt() throws {
        let helper = try codeOnly(helperPath)
        let flat = helper.filter { !$0.isWhitespace }
        XCTAssertTrue(flat.contains("letparts=TennisChartReading9483.panelParts(shown:shown,baseline:series.baseline,offersLatest:scrubDate==nil&&offersLatest(shown))"))
        XCTAssertFalse(helper.contains("Divider()"), "the comparison is one table, not two stacked blocks")
        XCTAssertEqual(helper.components(separatedBy: "TennisChartReading9483.showLatestText").count - 1, 1)
        XCTAssertTrue(flat.contains("case.showLatest:Button(TennisChartReading9483.showLatestText){pin.holdLatest(in:series)}.font(.caption).frame(minHeight:44,alignment:.leading)"),
                      "Show latest keeps its 44pt target, in its own row after the comparison")
        XCTAssertTrue(flat.contains(".font(prominent?.title3.bold():.subheadline.bold())"), "the values' type must not shrink")
    }

    /// The names head columns sized for them, shared with every value row,
    /// and wrap rather than truncate (lane1b R2).
    func testTheNameColumnsFitTheNamesAndTheValuesShareThem() throws {
        let helper = try codeOnly(helperPath)
        let flat = helper.filter { !$0.isWhitespace }
        XCTAssertTrue(flat.contains("TennisChartReading9483.valueColumn(forValues:expanded?prominentColumn:column,widestNamePiece:widestNamePiece)"),
                      "the value columns must widen for the names heading them")
        XCTAssertTrue(flat.contains(".background(nameWidths).onPreferenceChange(TennisNamePieceWidth9483.self){widestNamePiece=$0}"))
        XCTAssertTrue(flat.contains("TennisChartReading9483.unbreakablePieces(of:homeName)+TennisChartReading9483.unbreakablePieces(of:awayName)"))
        XCTAssertTrue(flat.contains("Text(text).font(.caption).foregroundStyle(.primary).fixedSize(horizontal:false,vertical:true).frame(width:valueColumn,alignment:.leading)"),
                      "a column head wraps whole, in the shared column")
        XCTAssertTrue(flat.contains(".monospacedDigit().foregroundStyle(color).frame(width:valueColumn,alignment:.leading)"),
                      "the values sit in the same column as their name")
        XCTAssertFalse(helper.contains(".lineLimit("), "no name in the panel may be truncated, at any text size")
    }

    func testTheFullSizeHeaderReadsTheScoreboardNeverAProjection() throws {
        let chart = try stripped(chartPath)
        XCTAssertTrue(chart.contains("ifTennisChartReading9483.applies(sportKey:sportKey){ToolbarItem(placement:.principal){tennisHeader}}"),
                      "the full-size header lost the match context, or it reached other sports")
        XCTAssertTrue(chart.contains("TennisMatchContext9483.result(finished:EventState.isFinished(status),homeScore:homeScore,awayScore:awayScore,sportKey:sportKey)"))
        XCTAssertTrue(try codeOnly(pagePath).filter { !$0.isWhitespace }
                        .contains("sportKey:event.sport,homeScore:event.homeScore,awayScore:event.awayScore,"),
                      "the page must hand the chart its own scoreboard")
        let context = try codeOnly(contextPath)
        for forbidden in ["rojected", "rojection", "robability", "games", "completedAt"] {
            XCTAssertFalse(context.contains(forbidden), forbidden)
        }
        XCTAssertTrue(context.contains("SportVocab.forSport(sportKey).scoreboardUnit"))
    }
}
