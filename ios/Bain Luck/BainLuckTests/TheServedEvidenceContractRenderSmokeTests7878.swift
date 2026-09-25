import SwiftUI
import XCTest
@testable import Bain_Luck

/// The camera for the phone half of #7878's contract consumer, because "the line
/// lifts where nobody read" is a claim about a picture.
///
/// Specimen: the real production payload for Mets @ Rangers, 15318166
/// (`Fixtures/event-15318166-history-7878-contract.20260925.json`). Two pairs:
///
/// 1. **Sources.** The phone draws a game's source lines whenever the payload
///    carries no blend (every Kalshi-only or Polymarket-only match), so this pair
///    drops `aggregate_line` and renders the same bytes with and without the
///    contract. BEFORE is exactly what the phone drew pre-consumer: the
///    contract-less payload takes the old path by construction. The MLB line
///    should lift at its five 6–8 minute holes; Kalshi and Polymarket should not
///    move (the short-gap control).
/// 2. **The blend.** With `aggregate_line` present the phone draws only the
///    blend, which the producer does not classify — so the two rasters must be
///    byte-identical. That is the "blend unchanged" clause, as a picture.
///
/// Byte counts are the tripwire, not the evidence; the artifact paths are
/// printed so a person reads the pictures (notice 4 / D48).
@MainActor
final class TheServedEvidenceContractRenderSmokeTests7878: XCTestCase {

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("event-15318166-history-7878-contract.20260925.json")
    }

    private func payload(contract: Bool, blend: Bool) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
        if !contract { object.removeValue(forKey: "evidence_contract") }
        if !blend { object.removeValue(forKey: "aggregate_line") }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    @discardableResult
    private func render(_ name: String, _ history: EventHistoryResponse) throws -> Data {
        let view = OddsChartView(
            eventId: 15318166,
            commenceTime: "2026-09-24T18:35:00+00:00",
            status: "completed",
            homeTeamName: "Texas Rangers",
            awayTeamName: "New York Mets",
            homeTeamAbbrev: "TEX",
            awayTeamAbbrev: "NYM",
            preloadedHistory: history
        )
        .frame(width: 390)

        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
            ?? FileManager.default.temporaryDirectory.path)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("7878-\(name).png")
        try png.write(to: url)
        print("#7878 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    func testTheSourceLinesLiftWhereTheContractSaysNobodyRead() throws {
        let before = try render("sources-before-no-contract", try payload(contract: false, blend: false))
        let after = try render("sources-after-contract", try payload(contract: true, blend: false))
        XCTAssertGreaterThan(before.count, 20_000, "the before arm must itself be a drawn chart")
        XCTAssertGreaterThan(after.count, 20_000, "the after arm must itself be a drawn chart")

        // Not `before != after`: the chip nondeterminism below would satisfy
        // that on its own. Assert what the chart draws per visible source.
        func runs(_ history: EventHistoryResponse) -> [String: Int] {
            let points = OddsChartView.chartPoints(from: history)
            var out: [String: Int] = [:]
            for source in OddsChartView.defaultVisibleSources(in: points) {
                out[source] = OddsChartView.observationSegments(
                    points.filter { $0.source == source },
                    gameStart: "2026-09-24T18:35:00+00:00".asDate
                ).count
            }
            return out
        }
        XCTAssertEqual(runs(try payload(contract: false, blend: false)),
                       ["kalshi": 1, "polymarket": 1, "espn": 1, "mlb": 1, "stat_model": 1])
        XCTAssertEqual(runs(try payload(contract: true, blend: false)),
                       ["kalshi": 1, "polymarket": 1, "espn": 1, "mlb": 6, "stat_model": 15])
    }

    /// The blend pair is rendered for a person to read, but its assertion is on
    /// what the chart DRAWS for the blend — its runs — not on raster bytes: the
    /// same contract-less payload renders two different rasters across opens on
    /// master, because the inning chips are taken first-seen across a Dictionary
    /// of sources whose iteration order is not stable (#8509; not
    /// this change). A byte comparison would be measuring that, not the blend.
    func testTheBlendIsTheSamePictureWithAndWithoutTheContract() throws {
        let without = try payload(contract: false, blend: true)
        let with = try payload(contract: true, blend: true)
        XCTAssertGreaterThan(try render("blend-before-no-contract", without).count, 20_000)
        try render("blend-after-contract", with)

        func blendRuns(_ history: EventHistoryResponse) -> [[Date]] {
            let points = OddsChartView.chartPoints(from: history)
            XCTAssertEqual(OddsChartView.defaultVisibleSources(in: points), ["aggregate"],
                           "with a blend the phone draws only the blend")
            return OddsChartView.observationSegments(
                points.filter { $0.source == "aggregate" },
                gameStart: "2026-09-24T18:35:00+00:00".asDate
            ).map { $0.map(\.date) }
        }
        let before = blendRuns(without)
        XCTAssertFalse(before.isEmpty)
        XCTAssertEqual(before, blendRuns(with), "the blend is not classified — its line must not move")
    }
}
