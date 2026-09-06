import SwiftUI
import XCTest
@testable import Bain_Luck

/// #3410 — a section with nothing to say stops building a frame to say it in.
///
/// Photographed 2026-09-06 on a live esports match (`15305748`) and on the live
/// Chimaev–Whittaker fight (`15305758`), both in `artifacts-native-033/`: a
/// "Win Probability ● Live" heading, a live dot, an All / Since Start picker, a
/// fullscreen button and a "View Probability Models" link — roughly 260pt of the
/// phone — over a payload whose `points` is 0 and whose `history`,
/// `espn_history`, `win_prob_history`, `bookmaker_history` and `win_prob_sources`
/// are ALL empty. Verified against production before building, not taken from the
/// issue text.
///
/// #3278 made the middle of that frame say something true, and its tests pass on
/// these payloads because they assert the SENTENCE. They cannot see the chrome
/// around it. Chrome is a promise — a range picker says there is a range worth
/// picking, a live dot says a number is moving — and one line further down the
/// same page a game with no markets already says so in a single sentence and
/// draws nothing else. That is the grammar (ruling 027).
///
/// The layout claim is proven as a RASTER, because that is the only thing that
/// can see a frame being drawn. The unit assertions pin the decision; the render
/// pins that the decision reaches the screen.
@MainActor
final class OddsChartNoReadingsTests: XCTestCase {

    private static let commence = "2026-09-05T17:55:03Z"

    private func history(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// The measured shape of 15305748 and 15305758: every field present, every
    /// field empty. Not a stripped-down fixture — the emptiness is the subject, so
    /// the fields it must be empty IN are written out.
    private func emptyPayload() throws -> EventHistoryResponse {
        try history("""
        {"event_id": 15305748, "home_team": "Isurus", "away_team": "wachoskys",
         "status": "live", "history": [], "espn_history": [], "score_history": [],
         "win_prob_history": {}, "bookmaker_history": {}, "win_prob_sources": {},
         "moments": [], "scoring_plays": [], "period_markers": [], "points": 0,
         "snapshot_count": 0, "espn_snapshot_count": 0}
        """)
    }

    /// The control: the same view, the same size, one reading short of drawable.
    /// #3278's state — which must KEEP its frame, because a payload with readings
    /// has a range worth picking even when the current one cannot join a line.
    private func oneReadingPayload() throws -> EventHistoryResponse {
        try history("""
        {"event_id": 15305748, "home_team": "Isurus", "away_team": "wachoskys",
         "status": "live",
         "history": [{"timestamp": "2026-09-05T17:58:00Z", "home_probability": 0.62}]}
        """)
    }

    private func drawablePayload() throws -> EventHistoryResponse {
        try history("""
        {"event_id": 15305748, "home_team": "Isurus", "away_team": "wachoskys",
         "status": "live",
         "history": [{"timestamp": "2026-09-05T17:58:00Z", "home_probability": 0.62},
                     {"timestamp": "2026-09-05T18:03:00Z", "home_probability": 0.71}]}
        """)
    }

    @discardableResult
    private func render(_ name: String, _ payload: EventHistoryResponse) throws -> Data {
        let view = OddsChartView(
            eventId: 15305748,
            commenceTime: Self.commence,
            status: "live",
            homeTeamName: "Isurus",
            awayTeamName: "wachoskys",
            preloadedHistory: payload
        )
        .frame(width: 390)

        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("odds-noreadings-\(name).png")
        try? png.write(to: url)
        print("No-readings render artifact [\(name)]: \(url.path) "
              + "(\(png.count) bytes, \(Int(image.size.height))pt tall)")
        return png
    }

    private func renderedHeight(_ name: String, _ payload: EventHistoryResponse) throws -> CGFloat {
        let view = OddsChartView(
            eventId: 15305748,
            commenceTime: Self.commence,
            status: "live",
            homeTeamName: "Isurus",
            awayTeamName: "wachoskys",
            preloadedHistory: payload
        )
        .frame(width: 390)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        return image.size.height
    }

    // MARK: The decision

    func testAPayloadWithNothingInItHasNoReadings() {
        XCTAssertTrue(OddsChartView.hasNoReadings(in: []))
    }

    func testASinglePointIsStillAReading() {
        // The boundary that separates this from #3278: ONE point is not drawable
        // but it IS a reading, and the section keeps its frame. If this inverted,
        // #3278's own state would silently lose its picker.
        let point = ChartDataPoint(date: Date(), probability: 0.62, source: "betting")
        XCTAssertFalse(OddsChartView.hasNoReadings(in: [point]))
    }

    // MARK: The layout, as a raster

    /// The claim, measured the only way a layout claim can be: the empty payload
    /// must render DRAMATICALLY shorter than the one-reading payload, because the
    /// latter still builds a header, a picker and a full-height plot area.
    func testAnEmptyPayloadCollapsesInsteadOfBuildingAFrame() throws {
        let empty = try renderedHeight("empty", try emptyPayload())
        let framed = try renderedHeight("one-reading", try oneReadingPayload())
        XCTAssertLessThan(
            empty, framed / 2,
            "the empty payload rendered \(empty)pt against \(framed)pt for a payload "
            + "that keeps its frame — the chrome is probably still being drawn")
    }

    /// Bytes as well as height: a shorter raster that is somehow just as heavy
    /// would mean the frame moved rather than went.
    func testAnEmptyPayloadRastersFarLighterThanAFramedOne() throws {
        let empty = try render("empty", try emptyPayload())
        let framed = try render("one-reading", try oneReadingPayload())
        XCTAssertLessThan(empty.count, framed.count)
    }

    // MARK: The other direction — everything that still has readings keeps its frame

    /// Without this, deleting the whole section passes every assertion above.
    func testADrawablePayloadStillRendersItsChart() throws {
        let chart = try render("control-drawable", try drawablePayload())
        XCTAssertGreaterThan(
            chart.count, 20_000,
            "the drawable chart render is suspiciously empty — the collapse is firing too widely")
    }

    /// #3278's state keeps its full-height frame AND its sentence. This is the
    /// control that tells "I collapsed the empty section" apart from "I collapsed
    /// every section that cannot draw a line", which would be a regression of
    /// #3278 wearing this fix's clothes.
    func testTheNotDrawableButNotEmptyStateKeepsItsFrame() throws {
        let empty = try renderedHeight("empty-frame", try emptyPayload())
        let framed = try renderedHeight("one-reading-frame", try oneReadingPayload())
        let drawable = try renderedHeight("drawable-frame", try drawablePayload())

        // Not equal to the drawn chart — a drawn chart also carries the legend row
        // under the plot, which the sentence state has never had (measured 325.3pt
        // against 348.7pt, both unchanged by this fix). The property is that the
        // sentence state still reserves a FULL frame: close to the drawn chart, and
        // nowhere near the collapse.
        XCTAssertGreaterThan(
            framed, drawable * 0.85,
            "a payload with one reading (\(framed)pt) no longer reserves a frame "
            + "comparable to a drawn chart (\(drawable)pt) — #3278's honest empty "
            + "frame has been collapsed by mistake")
        XCTAssertGreaterThan(
            framed, empty * 5,
            "the one-reading state collapsed with the empty one — the fix is firing "
            + "on 'cannot draw a line' instead of 'has nothing at all'")
    }

    /// The sentence #3278 owns is untouched on the payload it owns.
    func testTheNotDrawableMessageIsUnchanged() {
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(
                range: .sinceStart, hasAnyPointInRange: true, allIsDrawable: false),
            "Not enough readings since the start to draw a line yet.")
    }
}

/// #3410, second half — the "View Probability Models" link is a promise too.
///
/// With the chart collapsed and `sourcesToggle` already self-hiding on a game
/// with no sources, this link was the only thing left in the card, and it points
/// at THIS event's model breakdown — a page that is itself empty for a game with
/// no readings. Photographed stranded between the two honest sentences on
/// `artifacts-native-033/FIXED-esports-15305748.png`.
///
/// The gate is deliberately GENEROUS, so these tests are mostly about the
/// direction that would do damage: every shape that has any evidence at all
/// keeps its link.
final class EventModelsLinkGateTests: XCTestCase {

    private func event(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func history(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func bareEvent() throws -> EventDetail {
        try event("""
        {"id": 15305748, "home_team": "Isurus", "away_team": "wachoskys",
         "commence_time": "2026-09-05T17:55:03Z", "status": "live",
         "win_probability_sources": {}, "bookmaker_odds": []}
        """)
    }

    private func emptyHistory() throws -> EventHistoryResponse {
        try history("""
        {"event_id": 15305748, "home_team": "Isurus", "away_team": "wachoskys",
         "status": "live", "history": [], "espn_history": [],
         "win_prob_history": {}, "bookmaker_history": {}, "win_prob_sources": {}}
        """)
    }

    /// The photographed state: nothing, from any angle.
    func testAGameWithNoEvidenceAnywhereLosesTheLink() throws {
        XCTAssertFalse(EventDetailView.hasAnyProbabilityEvidence(
            event: try bareEvent(), history: try emptyHistory()))
    }

    // MARK: The direction that would do damage

    func testANamedSourceKeepsTheLink() throws {
        let withSource = try event("""
        {"id": 1, "home_team": "A", "away_team": "B",
         "commence_time": "2026-09-05T17:55:03Z", "status": "live",
         "win_probability_sources": {"espn": {"home_probability": 0.61}}}
        """)
        XCTAssertTrue(EventDetailView.hasAnyProbabilityEvidence(
            event: withSource, history: try emptyHistory()))
    }

    func testASingleHistoryPointKeepsTheLink() throws {
        let withPoint = try history("""
        {"event_id": 1, "home_team": "A", "away_team": "B", "status": "live",
         "history": [{"timestamp": "2026-09-05T17:58:00Z", "home_probability": 0.62}]}
        """)
        XCTAssertTrue(EventDetailView.hasAnyProbabilityEvidence(
            event: try bareEvent(), history: withPoint))
    }

    func testEspnHistoryAloneKeepsTheLink() throws {
        let espnOnly = try history("""
        {"event_id": 1, "home_team": "A", "away_team": "B", "status": "live",
         "history": [],
         "espn_history": [{"timestamp": "2026-09-05T17:58:00Z", "home_probability": 0.62}]}
        """)
        XCTAssertTrue(EventDetailView.hasAnyProbabilityEvidence(
            event: try bareEvent(), history: espnOnly))
    }

    /// A page that has not loaded yet must not flicker the link away and back.
    func testTheLinkIsKeptWhileHistoryIsStillNil() throws {
        XCTAssertTrue(EventDetailView.hasAnyProbabilityEvidence(
            event: try bareEvent(), history: nil))
    }
}
