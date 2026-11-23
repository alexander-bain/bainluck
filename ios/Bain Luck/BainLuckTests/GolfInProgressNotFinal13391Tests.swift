import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13391 — A golf tournament whose server `schedule_status` is `"in-progress"`
/// (including Saturday evening between rounds, when eliminated/missed-cut golfers carry
/// `is_winner: false, resolution_source: "api_settlement"` on the winner futures market)
/// must NEVER flip to `.final` or say `"FINAL"` / `"confirmed results"`. Its chart end
/// labels, finish expectations `Win` slot, and headline card must match Discover and the
/// field chooser, and dual-course venue names must render whole without ellipsis.
@MainActor
final class GolfInProgressNotFinal13391Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-22T03:00:00Z")!
    private let freshISO = "2026-11-22T02:55:00Z"
    private let fullVenue = "Sea Island Golf Club (Seaside Course), Sea Island Golf Club (Plantation Course)"

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func makeRSMBetweenRoundsFixture() throws -> (
        response: GolfTournamentDetailResponse,
        presentation: GolfTournamentPresentation,
        winMarket: FuturesMarketDetail,
        timeline: ProbabilityTimelineResponse,
        discoverCard: FeedTournamentData
    ) {
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
                "venue": fullVenue,
                "location": "Sea Island, GA",
                "schedule_status": "in-progress",
                "commence_time": "2026-11-14T17:04:00+00:00",
                "resolution_date": "2026-11-22T00:00:00+00:00",
            ],
            "golfers": [
                ["name": "Michael Thorbjornsen", "probability": 0.162, "movement_24h": 0.005, "rank": 1],
                ["name": "Rasmus Neergaard-Petersen", "probability": 0.093, "movement_24h": 0.011, "rank": 2],
                ["name": "Marco Penge", "probability": 0.080, "movement_24h": 0.004, "rank": 3],
                ["name": "Ricky Castillo", "probability": 0.056, "movement_24h": -0.003, "rank": 4],
            ],
            "evolution_market_id": 70709343,
            "markets": [
                ["type": "winner", "label": "Winner", "market_ids": [70709343], "market_names": ["The RSM Classic Winner"]],
            ],
            "round_top_groups": [],
        ]
        let response = try makeDecoder().decode(
            GolfTournamentDetailResponse.self,
            from: try JSONSerialization.data(withJSONObject: detailDict)
        )
        let presentation = GolfTournamentPresentation(response: response)

        // Live Winner market has missed-cut golfers settled (`is_winner: false`,
        // `resolution_source: "api_settlement"`) while tournament remains `in-progress`
        // and market remains `open`. Single-source probability (0.1549) also differs
        // from the blended tournament row (0.162).
        let marketDict: [String: Any] = [
            "id": 70709343,
            "name": "The RSM Classic Winner",
            "status": "open",
            "source": "kalshi",
            "commence_time": "2026-11-14T17:04:00Z",
            "created_at": "2026-11-16T10:00:00Z",
            "updated_at": freshISO,
            "outcomes": [
                ["id": 1, "name": "Michael Thorbjornsen", "probability": 0.15486726, "observed_at": freshISO],
                ["id": 2, "name": "Rasmus Neergaard-Petersen", "probability": 0.08053097, "observed_at": freshISO],
                ["id": 3, "name": "Marco Penge", "probability": 0.07389381, "observed_at": freshISO],
                ["id": 4, "name": "Ricky Castillo", "probability": 0.04823009, "observed_at": freshISO],
                ["id": 5, "name": "Kyoung-Hoon Lee", "probability": 0.0, "is_winner": false, "resolution_source": "api_settlement", "observed_at": freshISO],
                ["id": 6, "name": "Daniel Berger", "probability": 0.0, "is_winner": false, "resolution_source": "api_settlement", "observed_at": freshISO],
            ],
        ]
        let winMarket = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: marketDict)
        )

        // Single-venue timeline ends at 0.175 (18%) and 0.0545 (5%), matching
        // what the broken `.final` branch previously printed on the chart legend.
        let timelineDict: [String: Any] = [
            "market_id": 70709343,
            "market_name": "The RSM Classic Winner",
            "sport_category": "golf",
            "source": "kalshi",
            "hours": 168,
            "top": 20,
            "bucket_seconds": 3600,
            "representation": "source",
            "timeline": [
                ["timestamp": "2026-11-20T18:00:00Z", "outcomes": [
                    "Michael Thorbjornsen": 0.08, "Rasmus Neergaard-Petersen": 0.05,
                    "Marco Penge": 0.06, "Ricky Castillo": 0.04,
                ]],
                ["timestamp": "2026-11-21T20:00:00Z", "outcomes": [
                    "Michael Thorbjornsen": 0.14, "Rasmus Neergaard-Petersen": 0.075,
                    "Marco Penge": 0.07, "Ricky Castillo": 0.05,
                ]],
                ["timestamp": "2026-11-22T02:45:00Z", "outcomes": [
                    "Michael Thorbjornsen": 0.175, "Rasmus Neergaard-Petersen": 0.091,
                    "Marco Penge": 0.0835, "Ricky Castillo": 0.0545,
                ]],
            ],
            "outcomes": [
                ["id": 1, "name": "Michael Thorbjornsen", "current_probability": 0.15486726, "rank": 1],
                ["id": 2, "name": "Rasmus Neergaard-Petersen", "current_probability": 0.08053097, "rank": 2],
                ["id": 3, "name": "Marco Penge", "current_probability": 0.07389381, "rank": 3],
                ["id": 4, "name": "Ricky Castillo", "current_probability": 0.04823009, "rank": 4],
            ],
            "coverage_hours": 32.0,
            "observation_times": 3,
        ]
        let timeline = try makeDecoder().decode(
            ProbabilityTimelineResponse.self,
            from: try JSONSerialization.data(withJSONObject: timelineDict)
        )

        let cardDict: [String: Any] = [
            "key": "the_rsm_classic",
            "name": "The RSM Classic",
            "slug": "the-rsm-classic",
            "tour": "pga",
            "tour_label": "PGA Tour",
            "is_major": false,
            "venue": fullVenue,
            "location": "Sea Island, GA",
            "start_date": "2026-11-19T00:00:00+00:00",
            "end_date": "2026-11-22T00:00:00+00:00",
            "schedule_status": "in-progress",
            "commence_time": "2026-11-14T17:04:00+00:00",
            "resolution_date": "2026-11-22T00:00:00+00:00",
            "golfers": [
                ["name": "Michael Thorbjornsen", "probability": 0.162, "rank": 1, "movement_24h": 0.005],
                ["name": "Rasmus Neergaard-Petersen", "probability": 0.093, "rank": 2, "movement_24h": 0.011],
                ["name": "Marco Penge", "probability": 0.080, "rank": 3, "movement_24h": 0.004],
                ["name": "Ricky Castillo", "probability": 0.056, "rank": 4, "movement_24h": -0.003],
            ],
            "marquee_whathit": false,
        ]
        let discoverCard = try makeDecoder().decode(
            FeedTournamentData.self,
            from: try JSONSerialization.data(withJSONObject: cardDict)
        )

        return (response, presentation, winMarket, timeline, discoverCard)
    }

    func testSaturdayEveningBetweenRoundsTournamentStaysInProgressAndAgreesWithDiscover() throws {
        let fixture = try makeRSMBetweenRoundsFixture()
        let atlasData = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: fixture.winMarket,
            winnerTimeline: fixture.timeline,
            liveLeaderboard: nil
        )

        let phase = EventAtlasGolfTournament11666.resolvePhase(
            scheduleStatus: fixture.presentation.scheduleStatus,
            commenceTime: fixture.presentation.commenceTime,
            winnerMarket: fixture.winMarket,
            field: fixture.presentation.field,
            now: fixedNow
        )
        XCTAssertEqual(phase, .recorded, "In-progress tournament with missed-cut is_winner=false outcomes must stay .recorded")
        XCTAssertFalse(EventAtlasGolfTournament11666.isMarketResolved(fixture.winMarket))

        let contenders = EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: fixture.presentation,
            atlasData: atlasData,
            selectedGolferName: nil,
            now: fixedNow
        )
        XCTAssertEqual(contenders.count, 4)
        XCTAssertEqual(contenders[0].currentProbability ?? 0, 0.162, accuracy: 0.0001)
        XCTAssertEqual(contenders[0].points.last?.probability ?? 0, 0.162, accuracy: 0.001)
        XCTAssertEqual(contenders[3].currentProbability ?? 0, 0.056, accuracy: 0.0001)
        XCTAssertEqual(contenders[3].points.last?.probability ?? 0, 0.056, accuracy: 0.001)
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[0], phase: phase),
            "Thorbjornsen 16%"
        )
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[3], phase: phase),
            "Castillo 6%"
        )

        let finish = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Michael Thorbjornsen",
            presentation: fixture.presentation,
            atlasData: atlasData,
            now: fixedNow
        )
        XCTAssertEqual(finish.phase, .recorded)
        XCTAssertEqual(finish.win.recorded?.text, "16%")
        XCTAssertNotNil(finish.context)
        XCTAssertFalse(finish.context?.localizedCaseInsensitiveContains("Final") == true)
        XCTAssertFalse(finish.context?.localizedCaseInsensitiveContains("confirmed results") == true)
    }

    func testConfirmedResultsAppearsOnlyWhenServerConfirmsAResult() throws {
        let fixture = try makeRSMBetweenRoundsFixture()

        // Completed tournament where outcomes still lack confirmed resolution_source / winner.
        let unconfirmedDict: [String: Any] = [
            "tournament": [
                "name": "The RSM Classic",
                "slug": "the-rsm-classic",
                "key": "the_rsm_classic",
                "tour": "pga",
                "tour_label": "PGA Tour",
                "schedule_status": "completed",
                "commence_time": "2026-11-19T13:00:00Z",
            ],
            "golfers": [
                ["name": "Michael Thorbjornsen", "probability": 0.162, "rank": 1],
            ],
            "evolution_market_id": 70709343,
            "markets": [],
            "round_top_groups": [],
        ]
        let unconfirmedPresentation = GolfTournamentPresentation(
            response: try makeDecoder().decode(
                GolfTournamentDetailResponse.self,
                from: try JSONSerialization.data(withJSONObject: unconfirmedDict)
            )
        )
        let unconfirmedMarketDict: [String: Any] = [
            "id": 70709343,
            "name": "The RSM Classic Winner",
            "status": "closed",
            "source": "kalshi",
            "outcomes": [
                ["id": 1, "name": "Michael Thorbjornsen", "probability": 0.50, "is_winner": false],
            ],
        ]
        let unconfirmedMarket = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: unconfirmedMarketDict)
        )
        let pendingFinish = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Michael Thorbjornsen",
            presentation: unconfirmedPresentation,
            atlasData: .init(winnerMarket: unconfirmedMarket),
            now: fixedNow
        )
        XCTAssertEqual(pendingFinish.phase, .final)
        XCTAssertFalse(pendingFinish.context?.localizedCaseInsensitiveContains("confirmed results") == true)
        XCTAssertEqual(pendingFinish.context, "Final · results pending")

        // Server confirms winner (`is_winner: true`, `resolution_source: "datagolf"`).
        let confirmedMarketDict: [String: Any] = [
            "id": 70709343,
            "name": "The RSM Classic Winner",
            "status": "settled",
            "source": "datagolf",
            "outcomes": [
                ["id": 1, "name": "Michael Thorbjornsen", "probability": 1.0, "is_winner": true, "resolution_source": "datagolf"],
            ],
        ]
        let confirmedMarket = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: confirmedMarketDict)
        )
        let confirmedFinish = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Michael Thorbjornsen",
            presentation: fixture.presentation,
            atlasData: .init(winnerMarket: confirmedMarket),
            now: fixedNow
        )
        XCTAssertEqual(confirmedFinish.phase, .final)
        XCTAssertEqual(confirmedFinish.context, "Final · confirmed results")
    }

    func testGolfPageAndDiscoverCardRenderWithoutFinalOrCourseCutoffWhenEnvRequested() throws {
        let fixture = try makeRSMBetweenRoundsFixture()
        let atlasData = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: fixture.winMarket,
            winnerTimeline: fixture.timeline,
            liveLeaderboard: nil
        )

        let pageSection = EventAtlasGolfTournamentSection11666(
            presentation: fixture.presentation,
            atlasData: atlasData,
            now: fixedNow
        )

        for width in [CGFloat(390), CGFloat(440)] {
            let pageRoot = NavigationStack {
                ScrollView {
                    pageSection
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                }
                .background(Color(uiColor: .systemGroupedBackground))
                .navigationTitle(fixture.presentation.name)
                .navigationBarTitleDisplayMode(.inline)
            }
            let measured = hostForMeasurement(pageRoot, at: .large)
                .sizeThatFits(in: CGSize(width: width, height: 2400))
            XCTAssertLessThanOrEqual(measured.width, width + 0.5)
            XCTAssertGreaterThan(measured.height, 420)
        }

        for cardWidth in [CGFloat(390), CGFloat(350)] {
            let cardRoot = NativeTournamentDiscoverCard(
                data: fixture.discoverCard,
                feedContext: "PGA Tour: Michael Thorbjornsen leads at 16.2%",
                navigationPath: .constant(NavigationPath())
            )
            .padding(16)
            .frame(width: cardWidth)
            let measured = hostForMeasurement(cardRoot, at: .large)
                .sizeThatFits(in: CGSize(width: cardWidth, height: 1200))
            XCTAssertLessThanOrEqual(measured.width, cardWidth + 0.5)
            XCTAssertGreaterThan(measured.height, 140)
        }

        guard let outDir = ProcessInfo.processInfo.environment["GOLF_13391_RENDER_DIR"], !outDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        func writeHostedPNG<V: View>(
            _ root: V,
            size: CGSize,
            scheme: ColorScheme,
            to filename: String
        ) throws {
            let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let host = hostForMeasurement(root.environment(\.colorScheme, scheme), at: .large)
            host.overrideUserInterfaceStyle = style
            host.view.frame = CGRect(origin: .zero, size: size)
            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
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
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            if let png = img.pngData() {
                try png.write(to: dirURL.appendingPathComponent(filename))
            }
        }

        for scheme in [ColorScheme.light, .dark] {
            let suffix = scheme == .dark ? "dark" : "light"
            for width in [390, 440] {
                let pageRoot = NavigationStack {
                    ScrollView {
                        pageSection
                            .padding(.horizontal, 16)
                            .padding(.top, 8)
                    }
                    .background(Color(uiColor: .systemGroupedBackground))
                    .navigationTitle(fixture.presentation.name)
                    .navigationBarTitleDisplayMode(.inline)
                }
                .frame(width: CGFloat(width), height: 1120)

                try writeHostedPNG(
                    pageRoot,
                    size: CGSize(width: CGFloat(width), height: 1120),
                    scheme: scheme,
                    to: "rsm-tournament-\(width)-\(suffix).png"
                )
            }

            for (label, cardWidth) in [("390", CGFloat(390)), ("ipad350", CGFloat(350))] {
                let cardView = ScrollView {
                    NativeTournamentDiscoverCard(
                        data: fixture.discoverCard,
                        feedContext: "PGA Tour: Michael Thorbjornsen leads at 16.2%",
                        navigationPath: .constant(NavigationPath())
                    )
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(16)
                }
                .frame(width: cardWidth)
                .background(Color(uiColor: .systemGroupedBackground))

                let measureCard = NativeTournamentDiscoverCard(
                    data: fixture.discoverCard,
                    feedContext: "PGA Tour: Michael Thorbjornsen leads at 16.2%",
                    navigationPath: .constant(NavigationPath())
                )
                .fixedSize(horizontal: false, vertical: true)
                .padding(16)
                .frame(width: cardWidth)

                let host = hostForMeasurement(measureCard.environment(\.colorScheme, scheme), at: .large)
                let h = ceil(host.sizeThatFits(in: CGSize(width: cardWidth, height: 1200)).height) + 120
                try writeHostedPNG(
                    cardView,
                    size: CGSize(width: cardWidth, height: h),
                    scheme: scheme,
                    to: "rsm-discover-\(label)-\(suffix).png"
                )
            }
        }
    }
}
