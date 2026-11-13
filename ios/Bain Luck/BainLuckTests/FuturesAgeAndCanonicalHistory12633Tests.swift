import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12633 (Decision 170-A & Ruling 188) — Phone age display (`"As of 1:29 PM"`)
/// and canonical-history chart agreement on source-fallback futures markets (`108629`).
final class FuturesAgeAndCanonicalHistory12633Tests: XCTestCase {

    private let ptZone = TimeZone(identifier: "America/Los_Angeles")!
    /// 6:11:00 AM PT, Fri Nov 13, 2026 (`2026-11-13T14:11:00Z`) — exact moment of Builder B's
    /// public reproduction of Alex's build-5708 screenshot on market `108629`.
    private let governorCaptureNow = ISO8601DateFormatter().date(from: "2026-11-13T14:11:00Z")!

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func governorDetailFixture() throws -> FuturesMarketDetail {
        let dict: [String: Any] = [
            "id": 108629,
            "name": "Closest Governor race in 2026?",
            "category": "politics",
            "llm_sport_category": "politics",
            "status": "open",
            "source": "kalshi",
            "mutually_exclusive": true,
            "resolution_date": "2027-01-20T04:59:00Z",
            "bookmakers": ["kalshi"],
            "representation": "source",
            "representation_fallback": "not_a_title_question",
            "outcomes": [
                [
                    "id": 1594085,
                    "name": "Kansas",
                    "probability": 0.8891455,
                    "opening_probability": 0.85,
                    "probability_change_24h": 0.012,
                    "observed_at": "2026-11-13T12:10:07Z", // 4:10:07 AM PT (121 min old -> As of 4:10 AM)
                    "last_updated": "2026-11-13T12:10:07Z",
                ],
                [
                    "id": 235955686,
                    "name": "Georgia",
                    "probability": 0.03787529,
                    "opening_probability": 0.05,
                    "probability_change_24h": -0.008,
                    "observed_at": "2026-11-13T14:09:40Z", // 6:09:40 AM PT (1 min old -> fresh, nil)
                    "last_updated": "2026-11-13T14:09:40Z",
                ],
                [
                    "id": 235955685,
                    "name": "Alaska",
                    "probability": 0.02309469,
                    "opening_probability": 0.03,
                    "observed_at": "2026-11-13T13:57:58Z", // 5:57:58 AM PT (13 min old -> fresh, nil)
                    "last_updated": "2026-11-13T13:57:58Z",
                ],
                [
                    "id": 235955690,
                    "name": "Florida",
                    "probability": 0.01847575,
                    "opening_probability": 0.04,
                    "observed_at": "2026-11-13T00:52:57Z", // Nov 12, 4:52:57 PM PT (13h18m old -> As of Nov 12, 4:52 PM)
                    "last_updated": "2026-11-13T00:52:57Z",
                ],
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try makeDecoder().decode(FuturesMarketDetail.self, from: data)
    }

    // MARK: - 1. 170-A + 188 Phone Age Display (No Hard Limit, Never "stale" or "checked")

    func testGovernor108629ShowsKansas89PercentWithAsOfAndNeverHidesOldPricedRows() throws {
        let market = try governorDetailFixture()
        let page = FuturesAtlasPresentation11666.build(
            market: market,
            now: governorCaptureNow,
            timeZone: ptZone
        )

        // Headline shows Kansas 89% with its own clock ("As of 4:10 AM"), never "No recent probability"
        // and never attributing Florida's Nov 12, 4:52 PM clock in the card footer.
        XCTAssertEqual(page.header.selectedOutcomeId, 1594085)
        XCTAssertEqual(page.header.selectedOutcomeName, "Kansas")
        XCTAssertEqual(page.header.primaryDisplay.primaryLabel, "89%")
        XCTAssertEqual(page.header.primaryDisplay.asOfText, "As of 4:10 AM")
        XCTAssertNil(page.header.recordedAtText)
        XCTAssertEqual(page.detailsSheet.currentOrSettlementNote, "As of 4:10 AM")

        // Top 3 contender rows: Kansas (> 30m) gets "As of 4:10 AM"; Georgia (1m) and Alaska (13m) stay clean.
        XCTAssertEqual(page.body.primaryRows.map(\.name), ["Kansas", "Georgia", "Alaska"])
        XCTAssertEqual(page.body.primaryRows.map { $0.displayValue.primaryLabel }, ["89%", "4%", "2%"])
        XCTAssertEqual(page.body.primaryRows[0].displayValue.asOfText, "As of 4:10 AM")
        XCTAssertNil(page.body.primaryRows[1].displayValue.asOfText)
        XCTAssertNil(page.body.primaryRows[2].displayValue.asOfText)

        // Ruling 188: no hard limit for old priced numbers — Florida (13h18m old) keeps its 2% number
        // with "As of Nov 12, 4:52 PM" rather than being hidden.
        let floridaRow = try XCTUnwrap(page.body.allRows.first(where: { $0.id == 235955690 }))
        XCTAssertEqual(floridaRow.displayValue.primaryLabel, "2%")
        XCTAssertEqual(floridaRow.displayValue.asOfText, "As of Nov 12, 4:52 PM")

        // None of the priced outcomes are withheld from the chart's current column.
        let withheld = FuturesAtlasPresentation11666.withheldCurrentOutcomeIds(presentation: page)
        XCTAssertTrue(withheld.isEmpty)

        // Copy guard: no "stale" or "checked" anywhere in the built labels.
        let allStrings = [
            page.header.eyebrow,
            page.header.primaryDisplay.primaryLabel,
            page.header.primaryDisplay.asOfText,
            page.detailsSheet.currentOrSettlementNote,
        ].compactMap { $0 } + page.body.allRows.compactMap { $0.displayValue.asOfText }
        for text in allStrings {
            XCTAssertFalse(text.localizedCaseInsensitiveContains("stale"), "Unexpected 'stale' in \(text)")
            XCTAssertFalse(text.localizedCaseInsensitiveContains("checked"), "Unexpected 'checked' in \(text)")
        }
    }

    // MARK: - 2. Canonical-History Seam on Source-Fallback Venue-History Timeline (#12633)

    func testSourceTimelineWithRawVenueYesHistoryDrawsCanonicalHistoryAt88Point9Percent() throws {
        // Public `/api/futures/108629/probability-timeline?top=50&hours=168&representation=verified_title`:
        // falls back to `representation: "source"` and serves `venue_history` (`scale: "venue_yes_probability_raw"`,
        // `points_served: 519`) ending Kansas at `0.9625` (96.25%), while `outcomes[0].current_probability` is `0.8891455`.
        let timelineJSON = #"""
        {
          "market_id": 108629,
          "market_name": "Closest Governor race in 2026?",
          "sport_category": "politics",
          "source": "kalshi",
          "hours": 168,
          "top": 50,
          "bucket_seconds": 3600,
          "representation": "source",
          "timeline": [
            {"timestamp": "2026-11-13T12:00:00+00:00", "outcomes": {"Kansas": 0.955, "Georgia": 0.041, "Alaska": 0.025}},
            {"timestamp": "2026-11-13T14:00:00+00:00", "outcomes": {"Kansas": 0.9625, "Georgia": 0.041, "Alaska": 0.025}}
          ],
          "outcomes": [
            {"id": 1594085, "name": "Kansas", "current_probability": 0.8891455, "rank": 1, "probability_change_24h": 0.012, "opening_probability": 0.85},
            {"id": 235955686, "name": "Georgia", "current_probability": 0.03787529, "rank": 2, "probability_change_24h": -0.008, "opening_probability": 0.05},
            {"id": 235955685, "name": "Alaska", "current_probability": 0.02309469, "rank": 3, "probability_change_24h": 0.0, "opening_probability": 0.03}
          ],
          "coverage_hours": 2.0,
          "observation_times": 2,
          "venue_history": {
            "state": "warm",
            "tier": "cache",
            "points_served": 519,
            "outcomes_served": 24,
            "scale": "venue_yes_probability_raw"
          }
        }
        """#
        // Public `/api/futures/108629/history?hours=168&top_n=50`: refuses incomplete raw venue instants
        // (`exclusive_field_incomplete_at_venue_instant`) and serves canonical normalized capture history ending at `0.8891455`.
        let canonicalHistoryJSON = #"""
        {
          "market_id": 108629,
          "market_name": "Closest Governor race in 2026?",
          "hours": 168,
          "actual_hours": 168,
          "outcomes": [
            {
              "outcome_id": 1594085,
              "name": "Kansas",
              "history": [
                {"timestamp": "2026-11-13T10:01:30+00:00", "probability": 0.882, "bookmaker": "kalshi"},
                {"timestamp": "2026-11-13T14:01:30+00:00", "probability": 0.8891455, "bookmaker": "kalshi"}
              ]
            },
            {
              "outcome_id": 235955686,
              "name": "Georgia",
              "history": [
                {"timestamp": "2026-11-13T10:01:30+00:00", "probability": 0.04, "bookmaker": "kalshi"},
                {"timestamp": "2026-11-13T14:01:30+00:00", "probability": 0.03787529, "bookmaker": "kalshi"}
              ]
            },
            {
              "outcome_id": 235955685,
              "name": "Alaska",
              "history": [
                {"timestamp": "2026-11-13T10:01:30+00:00", "probability": 0.024, "bookmaker": "kalshi"},
                {"timestamp": "2026-11-13T14:01:30+00:00", "probability": 0.02309469, "bookmaker": "kalshi"}
              ]
            }
          ],
          "coverage_hours": 4.0,
          "observation_times": 2,
          "venue_history": {
            "state": "refused",
            "points_served": 0,
            "refusal_reason": "exclusive_field_incomplete_at_venue_instant",
            "scale": "venue_yes_probability_raw"
          }
        }
        """#

        let timeline = try makeDecoder().decode(ProbabilityTimelineResponse.self, from: Data(timelineJSON.utf8))
        let history = try makeDecoder().decode(FuturesHistoryResponse.self, from: Data(canonicalHistoryJSON.utf8))

        // Verified-title gate stays false on source fallback (#10244 contract untouched), while
        // `needsCanonicalHistory(for:)` detects the raw venue-yes timeline scale (#12633).
        XCTAssertFalse(
            VerifiedTitleHistory.drawsSourceHistory(detail: .source, response: timeline.effectiveRepresentation)
        )
        XCTAssertTrue(VerifiedTitleHistory.needsCanonicalHistory(for: timeline))

        // A source timeline with no raw venue-yes points served does NOT request `/history`.
        var noVenuePoints = timeline
        noVenuePoints.venueHistory = TimelineVenueHistory(
            state: "refused",
            pointsServed: 0,
            scale: "venue_yes_probability_raw",
            refusalReason: "exclusive_field_incomplete_at_venue_instant"
        )
        XCTAssertFalse(VerifiedTitleHistory.needsCanonicalHistory(for: noVenuePoints))

        // Overlaying `/history` replaces the 96.25% raw venue-yes tail with 88.91455% canonical history,
        // matching the detail headline (89%), contender row (89%), and chart `Prob` column (89%).
        let drawn = VerifiedTitleHistory.drawing(history, over: timeline)
        let kansasPoints = drawn.timeline.compactMap { $0.outcomes["Kansas"] }
        XCTAssertEqual(kansasPoints.last ?? 0, 0.8891455, accuracy: 0.000001)
        XCTAssertEqual(drawn.outcomes.first?.currentProbability ?? 0, 0.8891455, accuracy: 0.000001)
        XCTAssertEqual(drawn.coverageHours, 4.0)
        XCTAssertEqual(drawn.observationTimes, 2)
    }

    // MARK: - 3. 390pt Render Export for Visual Proof

    @MainActor
    func testRenderGovernor108629PhoneCardsAt390pt() throws {
        let market = try governorDetailFixture()
        let sameDayPage = FuturesAtlasPresentation11666.build(
            market: market,
            now: governorCaptureNow,
            timeZone: ptZone
        )
        let priorDayFloridaPage = FuturesAtlasPresentation11666.build(
            market: market,
            selectedOutcomeId: 235955690,
            now: governorCaptureNow,
            timeZone: ptZone
        )

        let canvas = VStack(alignment: .leading, spacing: 18) {
            FuturesAtlasHeaderCardView11666(
                header: sameDayPage.header,
                marketId: market.id,
                marketName: market.name,
                shareMessage: "Kansas at 89% — Closest Governor race in 2026? on Bain Luck",
                onShare: {},
                onOpenDetails: {}
            )
            FuturesAtlasBodyCardView11666(
                bodyModel: sameDayPage.body,
                selectedOutcomeId: sameDayPage.header.selectedOutcomeId,
                onSelectOutcome: { _ in },
                onOpenFullField: {}
            )
            FuturesAtlasHeaderCardView11666(
                header: priorDayFloridaPage.header,
                marketId: market.id,
                marketName: market.name,
                shareMessage: "Closest Governor race in 2026? on Bain Luck",
                onShare: {},
                onOpenDetails: {}
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(DS.trackBg)
        .environment(\.colorScheme, .light)
        .environment(\.dynamicTypeSize, .large)

        let renderer = rendererForMeasurement(canvas)
        let image = try XCTUnwrap(renderer.uiImage)
        XCTAssertEqual(Int(image.size.width), 390)
        XCTAssertGreaterThan(image.size.height, 450)

        let renderPath = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_12633"] ?? "/tmp/renders-12633"
        let outDir = URL(fileURLWithPath: renderPath, isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: outDir.appendingPathComponent("12633-governor-170a-390.png")
        )
    }
}
