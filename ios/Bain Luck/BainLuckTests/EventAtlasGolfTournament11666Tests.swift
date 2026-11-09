import SwiftUI
import XCTest
@testable import Bain_Luck

@MainActor
final class EventAtlasGolfTournament11666Tests: XCTestCase {
    private let refNow = Date(timeIntervalSince1970: 1_762_639_200) // 2025-11-08T22:00:00Z
    private let freshISO = "2025-11-08T21:50:00Z"
    private let staleISO = "2025-11-08T19:00:00Z"

    private func makeOutcome(
        id: Int,
        name: String,
        probability: Double?,
        openingProbability: Double? = nil,
        isWinner: Bool? = nil,
        resolutionSource: String? = nil,
        observedAt: String? = nil
    ) throws -> FuturesOutcome {
        var dict: [String: Any] = [
            "id": id,
            "name": name,
        ]
        if let probability { dict["probability"] = probability }
        if let openingProbability { dict["opening_probability"] = openingProbability }
        if let isWinner { dict["is_winner"] = isWinner }
        if let resolutionSource { dict["resolution_source"] = resolutionSource }
        if let observedAt { dict["observed_at"] = observedAt }
        let data = try JSONSerialization.data(withJSONObject: dict)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FuturesOutcome.self, from: data)
    }

    private func makeMarket(
        id: Int,
        name: String,
        status: String = "open",
        source: String = "datagolf",
        commenceTime: String? = "2025-11-06T12:00:00Z",
        updatedAt: String? = nil,
        outcomes: [FuturesOutcome]
    ) throws -> FuturesMarketDetail {
        let outcomeDicts: [[String: Any]] = outcomes.map { o in
            var d: [String: Any] = ["id": o.id, "name": o.name]
            if let p = o.probability { d["probability"] = p }
            if let op = o.openingProbability { d["opening_probability"] = op }
            if let w = o.isWinner { d["is_winner"] = w }
            if let rs = o.resolutionSource { d["resolution_source"] = rs }
            if let obs = o.observedAt { d["observed_at"] = obs }
            return d
        }
        var dict: [String: Any] = [
            "id": id,
            "name": name,
            "status": status,
            "source": source,
            "outcomes": outcomeDicts,
        ]
        if let commenceTime { dict["commence_time"] = commenceTime }
        if let updatedAt { dict["updated_at"] = updatedAt }
        let data = try JSONSerialization.data(withJSONObject: dict)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FuturesMarketDetail.self, from: data)
    }

    private func samplePresentation(
        scheduleStatus: String = "in_progress",
        commenceTime: String = "2025-11-06T12:00:00Z"
    ) throws -> GolfTournamentPresentation {
        let dict: [String: Any] = [
            "tournament": [
                "name": "The Masters",
                "slug": "the-masters",
                "key": "the_masters",
                "is_major": true,
                "start_date": "2025-11-06",
                "end_date": "2025-11-09",
                "venue": "Augusta National Golf Club",
                "location": "Augusta, GA",
                "schedule_status": scheduleStatus,
                "commence_time": commenceTime,
            ],
            "golfers": [
                [
                    "name": "Scottie Scheffler",
                    "probability": 0.24,
                    "opening_probability": 0.18,
                    "movement_24h": 0.035,
                    "rank": 1,
                ],
                [
                    "name": "Rory McIlroy",
                    "probability": 0.14,
                    "opening_probability": 0.11,
                    "movement_24h": 0.022,
                    "rank": 2,
                ],
                [
                    "name": "Ludvig Åberg",
                    "probability": 0.09,
                    "opening_probability": 0.10,
                    "movement_24h": -0.015,
                    "rank": 3,
                ],
                [
                    "name": "Collin Morikawa",
                    "probability": 0.07,
                    "opening_probability": 0.06,
                    "movement_24h": 0.008,
                    "rank": 4,
                ],
            ],
            "evolution_market_id": 9001,
            "markets": [
                ["type": "winner", "label": "Tournament Winner", "market_ids": [9001], "market_names": ["The Masters Winner"]],
                ["type": "top_5", "label": "Top 5 Finish", "market_ids": [9002], "market_names": ["The Masters Top 5"]],
                ["type": "top_10", "label": "Top 10 Finish", "market_ids": [9003], "market_names": ["The Masters Top 10"]],
                ["type": "top_20", "label": "Top 20 Finish", "market_ids": [9004], "market_names": ["The Masters Top 20"]],
                ["type": "make_cut", "label": "Make the Cut", "market_ids": [9005], "market_names": ["The Masters Make Cut"]],
            ],
            "round_top_groups": [
                [
                    "market_id": 9101,
                    "market_name": "End of Round 1 Leader",
                    "round": 1,
                    "kind": "leader",
                    "label": "Round Leader",
                    "source": "datagolf_model",
                    "settled": true,
                    "graded_winner": "Scottie Scheffler",
                    "outcomes": [
                        ["name": "Scottie Scheffler", "probability": 0.32, "opening_probability": 0.12],
                        ["name": "Rory McIlroy", "probability": 0.18, "opening_probability": 0.09],
                    ],
                ],
                [
                    "market_id": 9102,
                    "market_name": "End of Round 2 Leader",
                    "round": 2,
                    "kind": "leader",
                    "label": "Round Leader",
                    "source": "datagolf_model",
                    "settled": false,
                    "outcomes": [
                        ["name": "Scottie Scheffler", "probability": 0.28, "opening_probability": 0.15],
                        ["name": "Ludvig Åberg", "probability": 0.16, "opening_probability": 0.08],
                    ],
                ],
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: dict)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(GolfTournamentDetailResponse.self, from: data)
        return GolfTournamentPresentation(response: response)
    }

    func testFinishExpectationsIncludesFifthMakeCutSlotWhenMakeCutMarketPresentAndOmitsWhenAbsent() throws {
        let presentation = try samplePresentation()
        let winMarket = try makeMarket(
            id: 9001,
            name: "The Masters Winner",
            outcomes: [try makeOutcome(id: 1, name: "Scottie Scheffler", probability: 0.24, openingProbability: 0.18, observedAt: freshISO)]
        )
        let top5Market = try makeMarket(
            id: 9002,
            name: "The Masters Top 5",
            outcomes: [try makeOutcome(id: 2, name: "Scottie Scheffler", probability: 0.52, openingProbability: 0.44, observedAt: freshISO)]
        )
        let top10Market = try makeMarket(
            id: 9003,
            name: "The Masters Top 10",
            outcomes: [try makeOutcome(id: 3, name: "Scottie Scheffler", probability: 0.68, openingProbability: 0.61, observedAt: freshISO)]
        )
        let top20Market = try makeMarket(
            id: 9004,
            name: "The Masters Top 20",
            outcomes: [try makeOutcome(id: 4, name: "Scottie Scheffler", probability: 0.81, openingProbability: 0.76, observedAt: staleISO)]
        )
        let makeCutMarket = try makeMarket(
            id: 9005,
            name: "The Masters Make Cut",
            outcomes: [try makeOutcome(id: 5, name: "Scottie Scheffler", probability: 0.92, openingProbability: 0.89, observedAt: freshISO)]
        )

        let withMakeCut = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: winMarket,
            top5Market: top5Market,
            top10Market: top10Market,
            top20Market: top20Market,
            makeCutMarket: makeCutMarket
        )
        let input5 = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Scottie Scheffler",
            presentation: presentation,
            atlasData: withMakeCut,
            selectedFinish: "makeCut",
            now: refNow
        )
        XCTAssertEqual(input5.slots.count, 5)
        XCTAssertEqual(input5.slots.map(\.name), ["Win", "Top 5", "Top 10", "Top 20", "Make cut"])
        XCTAssertEqual(input5.beforeLabel, "Opened")
        XCTAssertEqual(input5.beforeColumnLabel, "Opened")
        XCTAssertEqual(input5.win.before?.text, "18%")
        XCTAssertEqual(input5.win.recorded?.text, "24%")
        XCTAssertEqual(input5.win.deltaText, "+6.0 pts since open")
        XCTAssertTrue(input5.accessibilityValue(for: input5.win).contains("Opened: 18%"))
        XCTAssertTrue(input5.accessibilityValue(for: input5.win).contains("+6.0 pts since open"))
        XCTAssertEqual(input5.makeCut?.before?.text, "89%")
        XCTAssertEqual(input5.makeCut?.recorded?.text, "92%")
        XCTAssertEqual(input5.makeCut?.deltaText, "+3.0 pts since open")
        // Stale quote (>30m old during play) ages to nil with "No recent probability"
        XCTAssertNil(input5.top20.recorded)
        XCTAssertEqual(input5.top20.recordedMissing, "No recent probability")
        XCTAssertEqual(input5.top20.before?.text, "76%")
        XCTAssertNil(input5.top20.deltaText)

        // Without makeCutMarket: exactly 4 slots
        let withoutMakeCut = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: winMarket,
            top5Market: top5Market,
            top10Market: top10Market,
            top20Market: top20Market,
            makeCutMarket: nil
        )
        let input4 = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Scottie Scheffler",
            presentation: presentation,
            atlasData: withoutMakeCut,
            now: refNow
        )
        XCTAssertEqual(input4.slots.count, 4)
        XCTAssertNil(input4.makeCut)
    }

    func testLoadAtlasDataRecordsFailedMarketFetchesAndSurfacesLoadFailureInsteadOfNotRecorded() async throws {
        let dict: [String: Any] = [
            "tournament": [
                "name": "The Masters",
                "slug": "the-masters",
                "key": "the_masters",
                "is_major": true,
                "start_date": "2025-11-06",
                "end_date": "2025-11-09",
                "schedule_status": "in_progress",
                "commence_time": "2025-11-06T12:00:00Z",
            ],
            "golfers": [
                ["name": "Scottie Scheffler", "probability": 0.24, "opening_probability": 0.18, "rank": 1],
            ],
            "evolution_market_id": 9001,
            "markets": [
                ["type": "winner", "label": "Tournament Winner", "market_ids": [9001], "market_names": ["The Masters Winner"]],
                ["type": "top_5", "label": "Top 5 Finish", "market_ids": [9002], "market_names": ["The Masters Top 5"]],
                ["type": "top_10", "label": "Top 10 Finish", "market_ids": [9003], "market_names": ["The Masters Top 10"]],
                ["type": "top_20", "label": "Top 20 Finish", "market_ids": [9004], "market_names": ["The Masters Top 20"]],
                ["type": "make_cut", "label": "Make the Cut", "market_ids": [9005], "market_names": ["The Masters Make Cut"]],
            ],
            "round_top_groups": [],
        ]
        let data = try JSONSerialization.data(withJSONObject: dict)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(GolfTournamentDetailResponse.self, from: data)
        let presentation = GolfTournamentPresentation(response: response)

        let winMarket = try makeMarket(
            id: 9001,
            name: "The Masters Winner",
            outcomes: [try makeOutcome(id: 1, name: "Scottie Scheffler", probability: 0.24, openingProbability: 0.18, observedAt: freshISO)]
        )

        struct SimulatedNetworkError: Error {}
        let loadedAtlas = await GolfTournamentViewModel.loadAtlasData(
            for: response,
            fetchMarket: { id in
                if id == 9001 { return winMarket }
                throw SimulatedNetworkError()
            },
            fetchTimeline: { _ in
                throw SimulatedNetworkError()
            }
        )

        XCTAssertTrue(loadedAtlas.winnerTimelineFailed)
        XCTAssertTrue(loadedAtlas.hasMakeCutMarket)
        XCTAssertEqual(loadedAtlas.failedMarketSlots, ["top5", "top10", "top20", "makeCut"])

        let input = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Scottie Scheffler",
            presentation: presentation,
            atlasData: loadedAtlas,
            selectedFinish: "top5",
            now: refNow
        )
        XCTAssertEqual(input.slots.count, 5, "Make cut slot must remain visible with load failure when its market fetch failed")
        XCTAssertEqual(input.win.recorded?.text, "24%")
        XCTAssertNil(input.top5.before)
        XCTAssertNil(input.top5.recorded)
        XCTAssertEqual(input.top5.beforeMissing, "Couldn’t load market")
        XCTAssertEqual(input.top5.recordedMissing, "Couldn’t load market")
        XCTAssertEqual(input.makeCut?.beforeMissing, "Couldn’t load market")
        XCTAssertEqual(input.makeCut?.recordedMissing, "Couldn’t load market")
    }

    func testBeforePhaseNeverReadsOpeningProbabilityAndFinalPhaseGradesStrictlyFromVenue() throws {
        let beforePresentation = try samplePresentation(
            scheduleStatus: "upcoming",
            commenceTime: "2025-11-10T12:00:00Z"
        )
        let stalePreMarket = try makeMarket(
            id: 9001,
            name: "The Masters Winner",
            commenceTime: "2025-11-10T12:00:00Z",
            outcomes: [try makeOutcome(id: 1, name: "Scottie Scheffler", probability: 0.22, openingProbability: 0.18, observedAt: staleISO)]
        )
        let beforeInput = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Scottie Scheffler",
            presentation: beforePresentation,
            atlasData: .init(winnerMarket: stalePreMarket),
            now: refNow
        )
        XCTAssertEqual(beforeInput.phase, .before)
        XCTAssertNil(beforeInput.win.before, "Stale pre-tournament quote must not fall back to openingProbability")
        XCTAssertEqual(beforeInput.win.beforeMissing, "No recent probability")

        // Final phase: confirmed win, confirmed loss, and unconfirmed (isWinner=false with nil resolutionSource)
        let finalPresentation = try samplePresentation(scheduleStatus: "completed")
        let settledWin = try makeMarket(
            id: 9001,
            name: "The Masters Winner",
            status: "settled",
            outcomes: [try makeOutcome(id: 1, name: "Scottie Scheffler", probability: 1.0, openingProbability: 0.18, isWinner: true, resolutionSource: "datagolf")]
        )
        let settledTop5 = try makeMarket(
            id: 9002,
            name: "The Masters Top 5",
            status: "settled",
            outcomes: [try makeOutcome(id: 2, name: "Scottie Scheffler", probability: 0.0, openingProbability: 0.44, isWinner: false, resolutionSource: "datagolf")]
        )
        let unconfirmedMakeCut = try makeMarket(
            id: 9005,
            name: "The Masters Make Cut",
            status: "settled",
            outcomes: [try makeOutcome(id: 5, name: "Scottie Scheffler", probability: 0.0, openingProbability: 0.89, isWinner: false, resolutionSource: nil)]
        )
        let finalInput = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Scottie Scheffler",
            presentation: finalPresentation,
            atlasData: .init(winnerMarket: settledWin, top5Market: settledTop5, makeCutMarket: unconfirmedMakeCut),
            now: refNow
        )
        XCTAssertEqual(finalInput.phase, .final)
        XCTAssertEqual(finalInput.win.actual, GolfFinishResult10868(text: "Won", mark: .success))
        XCTAssertEqual(finalInput.top5.actual, GolfFinishResult10868(text: "Outside Top 5", mark: .failure))
        XCTAssertEqual(finalInput.makeCut?.actual, GolfFinishResult10868(text: "Result not confirmed", mark: .unknown))
    }

    func testAmbiguousDuplicateGolferNameInMarketReturnsNilInsteadOfGuessing() throws {
        let dupMarket = try makeMarket(
            id: 9001,
            name: "The Masters Winner",
            outcomes: [
                try makeOutcome(id: 1, name: "Tom Kim", probability: 0.05, observedAt: freshISO),
                try makeOutcome(id: 2, name: "Tom Kim", probability: 0.04, observedAt: freshISO),
            ]
        )
        XCTAssertNil(EventAtlasGolfTournament11666.findOutcome(for: "Tom Kim", in: dupMarket))
    }

    func testJourneyYAxisCeilingAndChooserFiltering() throws {
        let presentation = try samplePresentation()
        let contenders = EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: presentation,
            atlasData: .init(),
            selectedGolferName: "Ludvig Aberg",
            now: refNow
        )
        XCTAssertEqual(contenders.count, 4)
        XCTAssertEqual(EventAtlasGolfTournament11666.yAxisCeiling(contenders: contenders, fullScale: false), 0.30)
        XCTAssertEqual(EventAtlasGolfTournament11666.yAxisCeiling(contenders: contenders, fullScale: true), 1.00)

        let movers = EventAtlasGolfTournament11666.filterAndSortField(
            field: presentation.field,
            mode: .movement,
            band: .all
        )
        XCTAssertEqual(movers.map(\.name), ["Scottie Scheffler", "Rory McIlroy", "Ludvig Åberg", "Collin Morikawa"])

        let mToR = EventAtlasGolfTournament11666.filterAndSortField(
            field: presentation.field,
            mode: .all,
            band: .mToR
        )
        XCTAssertEqual(mToR.map(\.name), ["Rory McIlroy", "Collin Morikawa"])
    }

    func testGolfTournamentAtlasSectionRendersSnapshots390px() throws {
        let presentation = try samplePresentation()
        let winMarket = try makeMarket(
            id: 9001,
            name: "The Masters Winner",
            outcomes: [
                try makeOutcome(id: 1, name: "Scottie Scheffler", probability: 0.24, openingProbability: 0.18, observedAt: freshISO),
                try makeOutcome(id: 2, name: "Rory McIlroy", probability: 0.14, openingProbability: 0.11, observedAt: freshISO),
                try makeOutcome(id: 3, name: "Ludvig Åberg", probability: 0.09, openingProbability: 0.10, observedAt: freshISO),
                try makeOutcome(id: 4, name: "Collin Morikawa", probability: 0.07, openingProbability: 0.06, observedAt: freshISO),
            ]
        )
        let top5Market = try makeMarket(
            id: 9002,
            name: "The Masters Top 5",
            outcomes: [try makeOutcome(id: 11, name: "Scottie Scheffler", probability: 0.52, openingProbability: 0.44, observedAt: freshISO)]
        )
        let top10Market = try makeMarket(
            id: 9003,
            name: "The Masters Top 10",
            outcomes: [try makeOutcome(id: 21, name: "Scottie Scheffler", probability: 0.68, openingProbability: 0.61, observedAt: freshISO)]
        )
        let top20Market = try makeMarket(
            id: 9004,
            name: "The Masters Top 20",
            outcomes: [try makeOutcome(id: 31, name: "Scottie Scheffler", probability: 0.81, openingProbability: 0.76, observedAt: freshISO)]
        )
        let makeCutMarket = try makeMarket(
            id: 9005,
            name: "The Masters Make Cut",
            outcomes: [try makeOutcome(id: 41, name: "Scottie Scheffler", probability: 0.92, openingProbability: 0.89, observedAt: freshISO)]
        )

        let timelineDict: [String: Any] = [
            "market_id": 9001,
            "market_name": "The Masters Winner",
            "hours": 72,
            "top": 10,
            "bucket_seconds": 3600,
            "timeline": [
                [
                    "timestamp": "2025-11-06T12:00:00Z",
                    "outcomes": ["Scottie Scheffler": 0.18, "Rory McIlroy": 0.11, "Ludvig Åberg": 0.10, "Collin Morikawa": 0.06],
                ],
                [
                    "timestamp": "2025-11-07T18:00:00Z",
                    "outcomes": ["Scottie Scheffler": 0.21, "Rory McIlroy": 0.13, "Ludvig Åberg": 0.08, "Collin Morikawa": 0.07],
                ],
                [
                    "timestamp": "2025-11-08T21:50:00Z",
                    "outcomes": ["Scottie Scheffler": 0.24, "Rory McIlroy": 0.14, "Ludvig Åberg": 0.09, "Collin Morikawa": 0.07],
                ],
            ],
            "outcomes": [
                ["id": 1, "name": "Scottie Scheffler", "current_probability": 0.24, "opening_probability": 0.18],
                ["id": 2, "name": "Rory McIlroy", "current_probability": 0.14, "opening_probability": 0.11],
                ["id": 3, "name": "Ludvig Åberg", "current_probability": 0.09, "opening_probability": 0.10],
                ["id": 4, "name": "Collin Morikawa", "current_probability": 0.07, "opening_probability": 0.06],
            ],
        ]
        let timelineData = try JSONSerialization.data(withJSONObject: timelineDict)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let timeline = try decoder.decode(ProbabilityTimelineResponse.self, from: timelineData)

        let atlasData = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: winMarket,
            winnerTimeline: timeline,
            top5Market: top5Market,
            top10Market: top10Market,
            top20Market: top20Market,
            makeCutMarket: makeCutMarket
        )

        let view = EventAtlasGolfTournamentSection11666(
            presentation: presentation,
            atlasData: atlasData,
            now: refNow
        )
        .padding(16)
        .frame(width: 390)
        .background(Color(UIColor.systemGroupedBackground))

        let defaultRenderer = rendererForMeasurement(view.environment(\.colorScheme, .light))
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1)

        let a11yRenderer = rendererForMeasurement(
            view.environment(\.colorScheme, .light),
            at: .accessibility3
        )
        a11yRenderer.scale = 1.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1)

        let png1 = try XCTUnwrap(defaultImage.pngData())
        let png2 = try XCTUnwrap(a11yImage.pngData())
        if let outDir = ProcessInfo.processInfo.environment["GOLF_ATLAS_SNAP_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try png1.write(to: dirURL.appendingPathComponent("golf-tournament-atlas-default-390px.png"))
            try png2.write(to: dirURL.appendingPathComponent("golf-tournament-atlas-a11y-390px.png"))
        }
    }
}
