import XCTest
@testable import Bain_Luck

/// #10549 — the native twin of web #10539 (Alex on 14781135): one projected
/// final-points chart that takes the Score Differential card's place on the
/// page's ONE decision, marks only observed game state, has no inspection
/// slider, and names its sportsbook where it is explained.
@MainActor
final class ProjectedPointsParity10549Tests: XCTestCase {
    private static let day = "2026-09-14"

    private func marker(_ time: String, _ period: String, source: String? = "espn_state",
                        precision: String = "boundary_observed") -> String {
        var fields = [#""timestamp":"\#(Self.day)T\#(time):00+00:00""#, #""period":"\#(period)""#,
                      #""precision":"\#(precision)""#, #""not_before":"\#(Self.day)T\#(time):00+00:00""#]
        if let source { fields.append(#""source":"\#(source)""#) }
        return "{" + fields.joined(separator: ",") + "}"
    }

    private func rec(_ minute: String, _ home: Double, _ away: Double) -> String {
        #"{"timestamp":"\#(Self.day)T\#(minute):00+00:00","home_probability":0.8,"projected_home_score":\#(home),"projected_away_score":\#(away),"kind":"recorded","observed_at":"\#(Self.day)T\#(minute):30.123456+00:00"}"#
    }

    /// Q1 is observed (first seen) at 00:20, so the score floor is 00:20.
    private func history(status: String, completedAt: String, markers: [String]) throws -> EventHistoryResponse {
        let json = """
        {"event_id":14781135,"home_team":"Home","away_team":"Away","status":"\(status)",
         "completed_at":\(completedAt),"history":[],
         "bookmaker_history":{"draftkings":[\(rec("00:10", 24, 20)),\(rec("01:00", 27, 21)),\(rec("02:30", 30, 24))]},
         "score_history":[{"timestamp":"\(Self.day)T00:50:00+00:00","home_score":7,"away_score":0}],
         "period_markers":[\(markers.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private var observedQ1: String { marker("00:20", "1st Quarter", precision: "first_seen") }

    private func finished(markers: [String]) throws -> (EventHistoryResponse, ProjectedFinalPointsSeries.Input) {
        let h = try history(status: "completed", completedAt: #""\#(Self.day)T03:30:00Z""#, markers: markers)
        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_nfl", eventStatus: "completed", history: h, finalHome: 30, finalAway: 24))
        return (h, input)
    }

    // MARK: - One decision

    func testTheProjectionReplacesTheDifferentialOnlyWhenAdmitted() throws {
        // `input` only admits a book whose series draws, so the helper's own
        // `build` check is a safety net; what this pins is that a refusal is nil.
        let (h, input) = try finished(markers: [observedQ1])
        XCTAssertTrue(ProjectedFinalPointsMount.replacesScoreDifferential(input))
        XCTAssertFalse(ProjectedFinalPointsMount.replacesScoreDifferential(nil),
                       "a refused mount keeps the Score Differential card")
        // Refusals keep the differential: a sport the series does not name (a
        // puck line is a fixed handicap, not a margin), and an NFL game with
        // no observed floor.
        XCTAssertFalse(ProjectedFinalPointsMount.replacesScoreDifferential(ProjectedFinalPointsMount.input(
            sportKey: "icehockey_nhl", eventStatus: "completed", history: h, finalHome: 30, finalAway: 24)))
        let noFloor = try history(status: "completed", completedAt: #""\#(Self.day)T03:30:00Z""#,
                                  markers: [marker("00:20", "1st Quarter", source: "estimated")])
        XCTAssertFalse(ProjectedFinalPointsMount.replacesScoreDifferential(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_nfl", eventStatus: "completed", history: noFloor, finalHome: 30, finalAway: 24)),
                       "an NFL page is never stripped of its differential on the sport alone")
    }

    func testThePageAsksOnceAndGatesBothCardsAndTheAbsenceNoteOnIt() throws {
        let page = try Self.source("Bain Luck/Views/EventDetailView.swift").filter { !$0.isWhitespace }
        XCTAssertEqual(page.components(separatedBy: "ProjectedFinalPointsMount.input(").count - 1, 1,
                       "one admission, read by both cards")
        XCTAssertTrue(page.contains("letprojectionReplacesDifferential=ProjectedFinalPointsMount.replacesScoreDifferential(projectedInput)"))
        XCTAssertTrue(page.contains("iflethistory=vm.history,(isLive||isFinished),!projectionReplacesDifferential{ScoreDifferentialChartView("),
                      "the differential steps aside on the shared decision")
        XCTAssertTrue(page.contains("ifprojectionReplacesDifferential,letprojectedInput{ProjectedFinalPointsChartView("))
        XCTAssertTrue(page.contains("letabsenceStatedAbove=!projectionReplacesDifferential&&vm.history.map{"),
                      "a differential that was not drawn stated nothing for the market maps")
    }

    // MARK: - Game-state markers

    func testOnlyObservedMarkersInsideTheSpanAreDrawnOncePerPeriod() throws {
        let (h, input) = try finished(markers: [
            marker("00:15", "2nd Quarter"),                               // in the span's pre-game hour, before the observed start
            observedQ1,
            marker("01:05", "2nd Quarter"),
            marker("01:10", "2nd Quarter", source: "statpal"),            // a second sighting of Q2
            marker("01:40", "Halftime"),
            marker("02:00", "3rd Quarter", source: "estimated"),          // arithmetic, seen by nobody
            marker("02:40", "4th Quarter", source: nil),                  // unknown source
            marker("03:45", "Overtime"),                                  // after the final
        ])
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        XCTAssertLessThan(series.start, "\(Self.day)T00:15:00Z".asDate!, "the pre-game marker is inside the drawn span")
        let drawn = ProjectedFinalPointsChartView.gameStateMarkers(h.periodMarkers, sportKey: "americanfootball_nfl", series: series,
                                                                  floor: input.scoreObservationStartAt)
        XCTAssertEqual(drawn.map(\.label), ["Q1", "Q2", "HT"])
        XCTAssertEqual(drawn.map(\.at), ["\(Self.day)T00:20:00Z".asDate!, "\(Self.day)T01:05:00Z".asDate!,
                                        "\(Self.day)T01:40:00Z".asDate!], "each at its own observed time, the earliest")
        XCTAssertEqual(drawn.map(\.boundaryObserved), [false, true, true])
        let spoken = ProjectedFinalPointsChartView.markersSpoken(drawn)
        XCTAssertTrue(spoken.hasPrefix("Game state marked on the chart: 1st quarter first seen in progress "), spoken)
        XCTAssertTrue(spoken.contains("2nd quarter began "), spoken)
        XCTAssertTrue(spoken.contains("Halftime began "), spoken)
        XCTAssertEqual(ProjectedFinalPointsChartView.markersSpoken([]), "")
    }

    func testNothingIsMarkedBeforeTheGameOrAfterTheReaderClock() throws {
        let markers = [observedQ1, marker("01:05", "2nd Quarter"), marker("01:40", "Halftime")]
        let scheduled = try history(status: "scheduled", completedAt: "null", markers: markers)
        let before = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_nfl", eventStatus: "scheduled", history: scheduled,
            finalHome: nil, finalAway: nil, asOf: "\(Self.day)T00:15:00Z".asDate))
        let beforeSeries = try XCTUnwrap(ProjectedFinalPointsSeries.build(before))
        XCTAssertEqual(beforeSeries.phase, .before)
        XCTAssertTrue(ProjectedFinalPointsChartView.gameStateMarkers(
            scheduled.periodMarkers, sportKey: "americanfootball_nfl", series: beforeSeries,
            floor: "\(Self.day)T00:00:00Z".asDate).isEmpty, "a scheduled page marks nothing, whatever floor it is handed")

        let live = try history(status: "live", completedAt: "null", markers: markers)
        let during = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_nfl", eventStatus: "live", history: live,
            finalHome: nil, finalAway: nil, asOf: "\(Self.day)T01:20:00Z".asDate))
        let duringSeries = try XCTUnwrap(ProjectedFinalPointsSeries.build(during))
        XCTAssertEqual(ProjectedFinalPointsChartView.gameStateMarkers(
            live.periodMarkers, sportKey: "americanfootball_nfl", series: duringSeries,
            floor: during.scoreObservationStartAt).map(\.label), ["Q1", "Q2"],
                       "a halftime the reader has not reached yet is not drawn")
    }

    func testSpokenPeriodsAreWords() {
        XCTAssertEqual(PeriodLabel.spoken("Q3"), "3rd quarter")
        XCTAssertEqual(PeriodLabel.spoken("HT"), "Halftime")
        XCTAssertEqual(PeriodLabel.spoken("OT"), "Overtime")
        XCTAssertEqual(PeriodLabel.spoken("OT2"), "2nd overtime")
    }

    // MARK: - Source, slider, room

    func testTheSportsbookIsNamedWhereItIsExplainedAsOneSource() throws {
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(try finished(markers: [observedQ1]).1))
        let text = ProjectedFinalPointsChartView.sourceExplanation(for: series)
        XCTAssertTrue(text.hasPrefix("Projection source: \(series.sourceName)."), text)
        XCTAssertTrue(text.contains("that one sportsbook"))
        XCTAssertTrue(text.contains("not an average of sources"))
        XCTAssertEqual(ProjectedFinalPointsChartView.readingLabel(for: series), "Last projection")
    }

    func testTheChartHasNoSliderNoInspectionAndMoreRoom() throws {
        let view = try Self.source("Bain Luck/Components/ProjectedFinalPointsChartView.swift")
        XCTAssertFalse(view.contains("Slider("), "the horizontal slider is gone")
        XCTAssertFalse(view.contains("chartXSelection"), "no drag-only selection left without a spoken equivalent")
        XCTAssertFalse(view.contains("Recorded captures"), "no bare source branding under the heading")
        XCTAssertTrue(view.contains(#"DisclosureGroup("How to read this""#))
        XCTAssertTrue(view.contains(#"Button("Done") { expanded = false }"#), "full screen still returns")
        // Opening the details in full screen must not grow the card behind the sheet.
        XCTAssertTrue(view.contains("height: Self.inlinePlotHeight, details: $detailsShown"), "the card owns its details")
        XCTAssertTrue(view.contains("height: Self.expandedPlotHeight, details: $expandedDetailsShown"), "the sheet owns its own")
        XCTAssertTrue(view.contains(".dynamicTypeSize(...Self.axisTypeCeiling)"), "axis labels stop growing before they truncate")
        XCTAssertFalse(ProjectedFinalPointsChartView.axisTypeCeiling.isAccessibilitySize)
        XCTAssertGreaterThan(ProjectedFinalPointsChartView.inlinePlotHeight, 210)
        XCTAssertGreaterThan(ProjectedFinalPointsChartView.expandedPlotHeight, 330)
    }

    private static func source(_ relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        return try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
    }
}
