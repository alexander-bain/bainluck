#if os(iOS)
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13535 — A settled golf tournament must read as `FINAL` with its confirmed winner
/// ranked #1 (`✓ Won`) and non-winners shown as settled (`Lost` / `Not won`),
/// never stuck in `LIVE` or `"No recent probability"`, even when:
///   A. A fallback winner market (`Polymarket`) is still `open` while field rows carry settled `source_mark`
///      (`Won`/`Lost`) or `is_winner` flags and pre-settlement probabilities put losers above the winner, or
///   B. Builder B's server fix settles `schedule_status: "completed"`,
///      Marco Penge (`is_winner: true, won: true`) and runners-up (`is_winner: null, won: false`).
@MainActor
final class GolfSettledTournament13535Tests: XCTestCase {
    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-23T20:10:00Z")!

    private func decodeSnake<T: Decodable>(_ type: T.Type, from obj: Any) throws -> T {
        let data = try JSONSerialization.data(withJSONObject: obj)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }

    private func captureScrollableSection(
        presentation: GolfTournamentPresentation,
        atlasData: EventAtlasGolfTournament11666.TournamentAtlasData,
        scheme: ColorScheme
    ) throws -> UIImage {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let root = NavigationStack {
            ScrollView {
                EventAtlasGolfTournamentSection11666(
                    presentation: presentation,
                    atlasData: atlasData,
                    now: fixedNow
                )
                .padding(.horizontal, 16)
                .padding(.top, 8)
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle(presentation.name)
            .navigationBarTitleDisplayMode(.inline)
        }
        .frame(width: 390, height: 1120)
        .environment(\.colorScheme, scheme)

        let host = hostForMeasurement(root, at: .large)
        host.overrideUserInterfaceStyle = style
        let size = CGSize(width: 390, height: 1120)
        host.view.frame = CGRect(origin: .zero, size: size)
        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: CGRect(origin: .zero, size: size))
        }
        window.frame = CGRect(origin: .zero, size: size)
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrText(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testSettledPayloadWithLowProbabilityWinnerAndOpenFallbackMarketRanksWinnerFirstAndRendersFinal() throws {
        // Matches #13535 partial-settlement failure shape: schedule_status lagged as "in-progress",
        // field rows settled via ESPN source_mark, and winnerMarket points to an open Polymarket market.
        let detailDict: [String: Any] = [
            "tournament": [
                "name": "The RSM Classic",
                "slug": "the-rsm-classic",
                "key": "the_rsm_classic",
                "is_major": false,
                "tour": "pga",
                "tour_label": "PGA Tour",
                "start_date": "2026-11-19T00:00:00+00:00",
                "end_date": "2026-11-22T00:00:00+00:00",
                "venue": "Sea Island Golf Club (Seaside Course), Sea Island Golf Club (Plantation Course)",
                "location": "Sea Island, GA",
                "schedule_status": "in-progress",
                "commence_time": "2026-11-19T00:00:00+00:00",
            ],
            "golfers": [
                [
                    "name": "Max Greyserman",
                    "rank": 1,
                    "probability": 0.456,
                    "source_mark": ["state": "settled", "sources": [], "settled": ["source": "espn", "result": "Lost"]],
                ],
                [
                    "name": "Rasmus Hojgaard",
                    "rank": 2,
                    "probability": 0.203,
                    "source_mark": ["state": "settled", "sources": [], "settled": ["source": "espn", "result": "Lost"]],
                ],
                [
                    "name": "Hao-Tong Li",
                    "rank": 3,
                    "probability": 0.177,
                    "source_mark": ["state": "settled", "sources": [], "settled": ["source": "espn", "result": "Lost"]],
                ],
                [
                    "name": "Marco Penge",
                    "rank": 8,
                    "probability": 0.013,
                    "source_mark": ["state": "settled", "sources": [], "settled": ["source": "espn", "result": "Won"]],
                ],
            ],
            "evolution_market_id": 70502669,
            "markets": [
                ["type": "winner", "label": "Winner", "market_ids": [70502669], "market_names": ["PGA Tour: The RSM Classic Winner"]],
            ],
            "round_top_groups": [],
        ]
        let response: GolfTournamentDetailResponse = try decodeSnake(GolfTournamentDetailResponse.self, from: detailDict)
        let presentation = GolfTournamentPresentation(response: response)

        XCTAssertEqual(presentation.field.first?.name, "Marco Penge")
        XCTAssertEqual(presentation.field.first?.position, 1)
        XCTAssertEqual(presentation.field.first?.isWinner, true)
        XCTAssertEqual(presentation.field[1].name, "Max Greyserman")
        XCTAssertEqual(presentation.field[1].isWinner, false)

        let openPolyMarket: FuturesMarketDetail = try decodeSnake(FuturesMarketDetail.self, from: [
            "id": 70502669,
            "name": "PGA Tour: The RSM Classic Winner",
            "status": "open",
            "source": "polymarket",
            "outcomes": [
                ["id": 1, "name": "Max Greyserman", "probability": 0.456],
                ["id": 2, "name": "Rasmus Hojgaard", "probability": 0.203],
                ["id": 3, "name": "Hao-Tong Li", "probability": 0.177],
                ["id": 4, "name": "Marco Penge", "probability": 0.013],
            ],
        ])

        let phase = EventAtlasGolfTournament11666.resolvePhase(
            scheduleStatus: presentation.scheduleStatus,
            commenceTime: presentation.commenceTime,
            winnerMarket: openPolyMarket,
            field: presentation.field,
            now: fixedNow
        )
        XCTAssertEqual(phase, .final)

        let contenders = EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: presentation,
            atlasData: .init(winnerMarket: openPolyMarket),
            selectedGolferName: nil,
            now: fixedNow
        )
        XCTAssertEqual(contenders.map(\.name), ["Marco Penge", "Max Greyserman", "Rasmus Hojgaard", "Hao-Tong Li"])
        XCTAssertEqual(contenders[0].finalVerdict, .won)
        XCTAssertEqual(contenders[1].finalVerdict, .lost)
        XCTAssertEqual(contenders[2].finalVerdict, .lost)
        XCTAssertEqual(contenders[3].finalVerdict, .lost)
        XCTAssertEqual(EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[0], phase: .final), "Penge ✓")

        let finish = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Marco Penge",
            presentation: presentation,
            atlasData: .init(winnerMarket: openPolyMarket),
            now: fixedNow
        )
        XCTAssertEqual(finish.phase, .final)
        XCTAssertEqual(finish.win.actual, GolfFinishResult10868(text: "Won", mark: .success))

        let lightImg = try captureScrollableSection(
            presentation: presentation,
            atlasData: .init(winnerMarket: openPolyMarket),
            scheme: .light
        )
        let lines = try ocrText(lightImg)
        let joined = lines.joined(separator: "\n")
        XCTAssertTrue(joined.contains("FINAL"), "Expected FINAL pill in OCR, got: \(lines)")
        XCTAssertTrue(joined.contains("Marco Penge"), "Expected Marco Penge in OCR, got: \(lines)")
        XCTAssertFalse(joined.contains("No recent probability"), "Settled page must never print No recent probability: \(lines)")
        XCTAssertFalse(joined.contains("LIVE"), "Settled page must never print LIVE: \(lines)")

        if let outDir = ProcessInfo.processInfo.environment["GOLF_13535_RENDER_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            if let png = lightImg.pngData() {
                try png.write(to: dirURL.appendingPathComponent("rsm-partial-settled-390-light.png"))
            }
            let darkImg = try captureScrollableSection(
                presentation: presentation,
                atlasData: .init(winnerMarket: openPolyMarket),
                scheme: .dark
            )
            if let png = darkImg.pngData() {
                try png.write(to: dirURL.appendingPathComponent("rsm-partial-settled-390-dark.png"))
            }
        }
    }

    func testCompletedServerFixWithWonFalseOnLosersAndWinnerFirst() throws {
        // Matches live /api/golf/tournaments/the-rsm-classic shape after Builder B's server fix:
        // Marco Penge has is_winner=true, won=true; runners-up have is_winner=null, won=false.
        let detailDict: [String: Any] = [
            "tournament": [
                "name": "The RSM Classic",
                "slug": "the-rsm-classic",
                "key": "the_rsm_classic",
                "start_date": "2026-11-19T00:00:00+00:00",
                "end_date": "2026-11-22T00:00:00+00:00",
                "venue": "Sea Island Golf Club (Seaside Course), Sea Island Golf Club (Plantation Course)",
                "schedule_status": "completed",
                "commence_time": "2026-11-19T00:00:00+00:00",
            ],
            "golfers": [
                ["name": "Marco Penge", "rank": 1, "probability": 1.0, "is_winner": true, "won": true],
                ["name": "Michael Thorbjornsen", "rank": 2, "probability": 0.0, "won": false],
                ["name": "Rasmus Neergaard-Petersen", "rank": 3, "probability": 0.0, "won": false],
                ["name": "Ricky Castillo", "rank": 4, "probability": 0.0, "won": false],
            ],
            "evolution_market_id": 70709343,
            "markets": [
                ["type": "winner", "label": "Winner", "market_ids": [70709343], "market_names": ["The RSM Classic Winner"]],
            ],
            "round_top_groups": [],
        ]
        let response: GolfTournamentDetailResponse = try decodeSnake(GolfTournamentDetailResponse.self, from: detailDict)
        let presentation = GolfTournamentPresentation(response: response)

        XCTAssertEqual(presentation.field.map(\.isWinner), [true, false, false, false])

        let contenders = EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: presentation,
            atlasData: .init(),
            selectedGolferName: nil,
            now: fixedNow
        )
        XCTAssertEqual(contenders.map(\.finalVerdict), [.won, .lost, .lost, .lost])

        if let outDir = ProcessInfo.processInfo.environment["GOLF_13535_RENDER_DIR"], !outDir.isEmpty {
            let atlasData = EventAtlasGolfTournament11666.TournamentAtlasData(
                winnerMarket: try decodeSnake(FuturesMarketDetail.self, from: [
                    "id": 70709343,
                    "name": "The RSM Classic Winner",
                    "status": "resolved",
                    "source": "kalshi",
                    "outcomes": [
                        ["id": 1, "name": "Marco Penge", "probability": 1.0, "is_winner": true, "resolution_source": "api_settlement"],
                        ["id": 2, "name": "Michael Thorbjornsen", "probability": 0.0, "is_winner": false, "resolution_source": "api_settlement"],
                        ["id": 3, "name": "Rasmus Neergaard-Petersen", "probability": 0.0, "is_winner": false, "resolution_source": "api_settlement"],
                        ["id": 4, "name": "Ricky Castillo", "probability": 0.0, "is_winner": false, "resolution_source": "api_settlement"],
                    ],
                ])
            )
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            for scheme in [ColorScheme.light, .dark] {
                let suffix = scheme == .dark ? "dark" : "light"
                let img = try captureScrollableSection(
                    presentation: presentation,
                    atlasData: atlasData,
                    scheme: scheme
                )
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("rsm-completed-390-\(suffix).png"))
                }
            }
        }
    }

    func testInProgressMissedCutLostSourceMarkWithoutWinnerStaysLiveSortedByProbability() throws {
        // Guards #13391: missed-cut golfers with source_mark.settled.result == "Lost"
        // during an in-progress tournament MUST NOT flip the page to .final.
        let detailDict: [String: Any] = [
            "tournament": [
                "name": "The RSM Classic",
                "slug": "the-rsm-classic",
                "schedule_status": "in-progress",
                "commence_time": "2026-11-19T00:00:00+00:00",
            ],
            "golfers": [
                ["name": "Michael Thorbjornsen", "rank": 1, "probability": 0.162],
                ["name": "Marco Penge", "rank": 2, "probability": 0.080],
                [
                    "name": "Daniel Berger",
                    "rank": 90,
                    "probability": 0.0,
                    "source_mark": ["state": "settled", "sources": [], "settled": ["source": "espn", "result": "Lost"]],
                ],
            ],
            "markets": [],
            "round_top_groups": [],
        ]
        let response: GolfTournamentDetailResponse = try decodeSnake(GolfTournamentDetailResponse.self, from: detailDict)
        let presentation = GolfTournamentPresentation(response: response)
        XCTAssertEqual(presentation.field.map(\.name), ["Michael Thorbjornsen", "Marco Penge", "Daniel Berger"])
        let phase = EventAtlasGolfTournament11666.resolvePhase(
            scheduleStatus: presentation.scheduleStatus,
            commenceTime: presentation.commenceTime,
            winnerMarket: nil,
            field: presentation.field,
            now: fixedNow
        )
        XCTAssertEqual(phase, .recorded)
    }

    func testStringEncodedOpeningProbabilityDoesNotWipeGolfersArrayOrHideWinner() throws {
        // Live regression caught on /api/golf/tournaments/the-rsm-classic (#13535):
        // opening_probability serialized as Decimal string "0.018400" must decode cleanly
        // and never wipe the entire golfers list to "No odds yet".
        let liveLikeJSON = Data("""
        {
          "tournament": {
            "name": "The Rsm Classic",
            "slug": "the-rsm-classic",
            "key": "the_rsm_classic",
            "schedule_status": "completed",
            "commence_time": "2026-11-19T00:00:00+00:00"
          },
          "golfers": [
            {"name": "Marco Penge", "rank": 1, "probability": 1.0, "opening_probability": "0.018400", "is_winner": true, "won": true},
            {"name": "Michael Thorbjornsen", "rank": 2, "probability": 0.0, "opening_probability": "0.022700", "is_winner": null, "won": false}
          ],
          "overflow_outcomes": null,
          "evolution_market_id": 70709343,
          "markets": [],
          "round_top_groups": []
        }
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(GolfTournamentDetailResponse.self, from: liveLikeJSON)
        XCTAssertEqual(response.golfers.count, 2)
        XCTAssertEqual(response.golfers[0].openingProbability ?? 0, 0.0184, accuracy: 0.0001)
        XCTAssertEqual(response.golfers[1].openingProbability ?? 0, 0.0227, accuracy: 0.0001)

        let presentation = GolfTournamentPresentation(response: response)
        XCTAssertEqual(presentation.field.first?.name, "Marco Penge")
        XCTAssertEqual(presentation.field.first?.isWinner, true)
        XCTAssertEqual(presentation.field[1].isWinner, false)
    }
}
#endif
