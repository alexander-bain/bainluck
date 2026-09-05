import SwiftUI
import XCTest
@testable import Bain_Luck

/// A camera on the #3278 state, because the bug was only ever visible as a raster.
///
/// #3278 is a LAYOUT claim — "the frame renders in full around no line" — and no
/// assertion about point counts can see it. The state is also transient: it exists
/// for roughly the first ten to twenty minutes of a live match, so photographing it
/// on production means catching a specific match inside a specific window. This
/// renders the real `OddsChartView` from a real payload through `ImageRenderer`
/// instead (the camera native/025 built for `ScoreDifferentialChartRenderSmokeTests`).
///
/// `ImageRenderer` DOES run the view's `.task`, checked on the raster: the picker
/// draws with "Since Start" selected, which only the task sets. So these rasterise
/// the real default a live match gets, not a `.all` stand-in.
///
/// What a byte count can and cannot say: it is a weak automatic signal that the
/// gridlines, the rotated gutter labels, the axis and the legend stopped being
/// drawn. The artifact paths are printed so a human reads the actual picture — that
/// judgement is the evidence, this is the tripwire.
@MainActor
final class OddsChartEmptyStateRenderSmokeTests: XCTestCase {

    private static let commence = "2026-09-05T17:55:03Z"

    private func history(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func payload(_ readings: [String]) throws -> EventHistoryResponse {
        try history("""
        {"event_id": 15302923, "home_team": "Iga Swiatek", "away_team": "Marie Bouzkova",
         "status": "live", "history": [\(readings.joined(separator: ","))]}
        """)
    }

    private func reading(_ timestamp: String, _ probability: Double) -> String {
        "{\"timestamp\": \"\(timestamp)\", \"home_probability\": \(probability)}"
    }

    /// The reported payload: 15302923 five minutes after the first ball, one
    /// snapshot since it, and — as measured in #3278 — nothing before it either.
    private func oneReading() throws -> EventHistoryResponse {
        try payload([reading("2026-09-05T17:58:00Z", 0.88)])
    }

    /// The same match a poll later — the control. If this stopped drawing, the fix
    /// would have bought an honest empty state by breaking every working chart.
    private func twoReadings() throws -> EventHistoryResponse {
        try payload([reading("2026-09-05T17:58:00Z", 0.88),
                     reading("2026-09-05T18:03:00Z", 0.91)])
    }

    /// The fuller production shape #3278 describes: 29 pre-match quotes exist, and
    /// exactly one landed since the first ball. "Since Start" cannot draw, "All"
    /// can — the only state in which the sentence offers the reader somewhere to go.
    private func pregameThenOneReading() throws -> EventHistoryResponse {
        let start = Self.commence.asDate!
        let iso = ISO8601DateFormatter()
        var readings = (0..<29).map { step -> String in
            let at = iso.string(from: start.addingTimeInterval(Double(step - 29) * 600))
            return reading(at, 0.80 + Double(step) * 0.002)
        }
        readings.append(reading("2026-09-05T17:58:00Z", 0.88))
        return try payload(readings)
    }

    @discardableResult
    private func render(_ name: String, _ payload: EventHistoryResponse) throws -> Data {
        let view = OddsChartView(
            eventId: 15302923,
            commenceTime: Self.commence,
            status: "live",
            homeTeamName: "Iga Swiatek",
            awayTeamName: "Marie Bouzkova",
            homeTeamAbbrev: "SWI",
            awayTeamAbbrev: "BOU",
            preloadedHistory: payload
        )
        .frame(width: 390)

        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("odds-empty-\(name).png")
        try? png.write(to: url)
        print("Odds chart render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    /// The state #3278 reported, rasterised beside the state one poll later. Same
    /// view, same size, same fixture but for a single extra snapshot — so a strictly
    /// lighter raster is the frame's gridlines, axis and legend no longer being
    /// drawn, and nothing else.
    func testTheFirstMinutesRenderLighterThanADrawnChart() throws {
        let sentence = try render("one-reading", try oneReading())
        let chart = try render("two-readings", try twoReadings())
        XCTAssertLessThan(
            sentence.count, chart.count,
            "the non-drawable payload rasterised no lighter than a drawn chart — "
            + "the empty frame is probably still being rendered")
    }

    /// The control drew something substantial. Without this the comparison above
    /// passes just as well when BOTH renders collapse to nothing.
    func testADrawablePayloadStillRendersAChart() throws {
        let chart = try render("control", try twoReadings())
        XCTAssertGreaterThan(chart.count, 20_000, "the drawable chart render is suspiciously empty")
    }

    /// The variant that offers "All", rasterised for the same human read. Pinned
    /// here as well as in the unit tests because the suggestion is only honest if
    /// the range it names really does have a line — see `testNeverPointsAtAllWhenAllIsAlsoEmpty`.
    func testTheOfferOfAllRasterises() throws {
        let full = try pregameThenOneReading()
        XCTAssertTrue(OddsChartView.hasDrawableLine(in: OddsChartView.chartPoints(from: full)),
                      "precondition: All must genuinely be drawable for the offer to be honest")
        try render("offers-all", full)
    }

    /// Nothing in this path reads a clock or the network, so the same payload
    /// rasterises identically — which is what makes the size comparison above a
    /// measurement rather than a coincidence.
    func testRenderingIsDeterministic() throws {
        XCTAssertEqual(try render("determinism-a", try oneReading()),
                       try render("determinism-b", try oneReading()))
    }
}
