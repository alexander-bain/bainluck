import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Saturday Item 2f (#12472, Atlas Pass 4 Sheet 4):
/// Golf during a tournament (`PGA Live Leaderboard`) — compact 192-A headline card with
/// `LIVE · R2` badge, concise tour label, `POS · GOLFER · PAR · PREGAME · NOW` columns,
/// live strokes-to-par (`−10`, `−7`, `−8`, `E`, `+2`), whole-percent `PREGAME` (`2%`, `4%`),
/// streaming-tenths `NOW` (`17.3%`, `10.8%`, `7.8%`, `5.9%`), and `"Round 1 tee-off → Round 2 live"`
/// journey footer caption.
@MainActor
final class GolfLiveHeadlineSat2FTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T19:00:00Z")!
    private let freshISO = "2026-11-14T18:55:00Z"

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func makeAustinLiveFixture(fieldSize: Int = 120) throws -> (
        response: GolfTournamentDetailResponse,
        presentation: GolfTournamentPresentation,
        winMarket: FuturesMarketDetail,
        timeline: ProbabilityTimelineResponse,
        leaderboard: GolfLeaderboardResponse
    ) {
        let topFour: [[String: Any]] = [
            ["name": "Trace Crowe", "probability": 0.173, "opening_probability": 0.02, "movement_24h": 0.085, "rank": 1],
            ["name": "Blades Brown", "probability": 0.108, "opening_probability": 0.04, "movement_24h": 0.052, "rank": 2],
            ["name": "Max Greyserman", "probability": 0.078, "opening_probability": 0.03, "movement_24h": 0.031, "rank": 3],
            ["name": "Erik Van Rooyen", "probability": 0.059, "opening_probability": 0.02, "movement_24h": 0.024, "rank": 4],
        ]
        var golfers = topFour
        for idx in 5...max(4, fieldSize) {
            golfers.append([
                "name": "Player \(idx) Contender",
                "probability": max(0.002, 0.05 / Double(idx)),
                "opening_probability": 0.01,
                "movement_24h": 0.0,
                "rank": idx,
            ])
        }

        let detailDict: [String: Any] = [
            "tournament": [
                "name": "Austin Championship",
                "slug": "austin-championship",
                "key": "austin_championship",
                "is_major": false,
                "tour": "pga",
                "tour_label": "PGA Tour",
                "start_date": "2026-11-13",
                "end_date": "2026-11-16",
                "venue": "Austin Country Club",
                "location": "Austin, TX",
                "schedule_status": "in_progress",
                "commence_time": "2026-11-13T13:00:00Z",
            ],
            "golfers": golfers,
            "evolution_market_id": 9401,
            "markets": [
                ["type": "winner", "label": "Tournament Winner", "market_ids": [9401], "market_names": ["Austin Championship Winner"]],
            ],
            "round_top_groups": [],
        ]
        let response = try makeDecoder().decode(
            GolfTournamentDetailResponse.self,
            from: try JSONSerialization.data(withJSONObject: detailDict)
        )
        let presentation = GolfTournamentPresentation(response: response)

        let marketDict: [String: Any] = [
            "id": 9401,
            "name": "Austin Championship Winner",
            "status": "open",
            "source": "datagolf",
            "commence_time": "2026-11-13T13:00:00Z",
            "updated_at": freshISO,
            "outcomes": [
                ["id": 1, "name": "Trace Crowe", "probability": 0.173, "opening_probability": 0.02, "observed_at": freshISO],
                ["id": 2, "name": "Blades Brown", "probability": 0.108, "opening_probability": 0.04, "observed_at": freshISO],
                ["id": 3, "name": "Max Greyserman", "probability": 0.078, "opening_probability": 0.03, "observed_at": freshISO],
                ["id": 4, "name": "Erik Van Rooyen", "probability": 0.059, "opening_probability": 0.02, "observed_at": freshISO],
            ],
        ]
        let winMarket = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: marketDict)
        )

        let timelineDict: [String: Any] = [
            "market_id": 9401,
            "market_name": "Austin Championship Winner",
            "sport_category": "golf",
            "source": "datagolf",
            "hours": 168,
            "top": 20,
            "bucket_seconds": 3600,
            "representation": "source",
            "timeline": [
                ["timestamp": "2026-11-13T13:00:00Z", "outcomes": ["Trace Crowe": 0.02, "Blades Brown": 0.04, "Max Greyserman": 0.03, "Erik Van Rooyen": 0.02]],
                ["timestamp": "2026-11-13T21:00:00Z", "outcomes": ["Trace Crowe": 0.06, "Blades Brown": 0.06, "Max Greyserman": 0.045, "Erik Van Rooyen": 0.035]],
                ["timestamp": "2026-11-14T14:00:00Z", "outcomes": ["Trace Crowe": 0.135, "Blades Brown": 0.092, "Max Greyserman": 0.064, "Erik Van Rooyen": 0.048]],
                ["timestamp": freshISO, "outcomes": ["Trace Crowe": 0.173, "Blades Brown": 0.108, "Max Greyserman": 0.078, "Erik Van Rooyen": 0.059]],
            ],
            "outcomes": [
                ["id": 1, "name": "Trace Crowe", "current_probability": 0.173, "rank": 1, "opening_probability": 0.02],
                ["id": 2, "name": "Blades Brown", "current_probability": 0.108, "rank": 2, "opening_probability": 0.04],
                ["id": 3, "name": "Max Greyserman", "current_probability": 0.078, "rank": 3, "opening_probability": 0.03],
                ["id": 4, "name": "Erik Van Rooyen", "current_probability": 0.059, "rank": 4, "opening_probability": 0.02],
            ],
            "coverage_hours": 30.0,
            "observation_times": 4,
        ]
        let timeline = try makeDecoder().decode(
            ProbabilityTimelineResponse.self,
            from: try JSONSerialization.data(withJSONObject: timelineDict)
        )

        let lbDict: [String: Any] = [
            "status": "live",
            "event_name": "Austin Championship",
            "current_round": 2,
            "last_updated": freshISO,
            "tour": "pga",
            "player_count": 120,
            "has_snapshot": true,
            "players": [
                [
                    "position": "1",
                    "name": "Trace Crowe",
                    "score": "-10",
                    "total_score_raw": -10,
                    "today": "-5",
                    "today_raw": -5,
                    "thru": "14",
                    "hole": "15",
                    "win_prob": 0.173,
                    "current_round": 2,
                ],
                [
                    "position": "T2",
                    "name": "Max Greyserman",
                    "score": "-8",
                    "total_score_raw": -8,
                    "today": "-4",
                    "today_raw": -4,
                    "thru": "16",
                    "hole": "17",
                    "win_prob": 0.078,
                    "current_round": 2,
                ],
                [
                    "position": "T2",
                    "name": "Erik Van Rooyen",
                    "score": "-8",
                    "total_score_raw": -8,
                    "today": "-3",
                    "today_raw": -3,
                    "thru": "F",
                    "hole": "F",
                    "win_prob": 0.059,
                    "current_round": 2,
                ],
                [
                    "position": "4",
                    "name": "Blades Brown",
                    "score": "-7",
                    "total_score_raw": -7,
                    "today": "-6",
                    "today_raw": -6,
                    "thru": "12",
                    "hole": "13",
                    "win_prob": 0.108,
                    "current_round": 2,
                ],
            ],
        ]
        let leaderboard = try makeDecoder().decode(
            GolfLeaderboardResponse.self,
            from: try JSONSerialization.data(withJSONObject: lbDict)
        )
        return (response, presentation, winMarket, timeline, leaderboard)
    }

    func testLoadAtlasDataAttachesMatchingLiveLeaderboardAndRejectsMismatchedTournament() async throws {
        let fixture = try makeAustinLiveFixture()
        let atlas = await GolfTournamentViewModel.loadAtlasData(
            for: fixture.response,
            fetchMarket: { _ in fixture.winMarket },
            fetchTimeline: { _ in fixture.timeline },
            fetchLeaderboard: { tour in
                XCTAssertEqual(tour, "pga")
                return fixture.leaderboard
            }
        )

        let live = try XCTUnwrap(atlas.liveLeaderboard)
        XCTAssertEqual(live.currentRound, 2)
        XCTAssertEqual(live.selectedRow(named: "Trace Crowe")?.position, "1")
        XCTAssertEqual(live.selectedRow(named: "Trace Crowe")?.parDisplay, "−10")
        XCTAssertEqual(live.selectedRow(named: "Blades Brown")?.position, "4")
        XCTAssertEqual(live.selectedRow(named: "Blades Brown")?.parDisplay, "−7")
        XCTAssertEqual(live.selectedRow(named: "Max Greyserman")?.position, "T2")
        XCTAssertEqual(live.selectedRow(named: "Max Greyserman")?.parDisplay, "−8")
        XCTAssertEqual(live.selectedRow(named: "Erik Van Rooyen")?.position, "T2")
        XCTAssertEqual(live.selectedRow(named: "Erik Van Rooyen")?.parDisplay, "−8")

        // Sponsor-suffixed tournament name matches cleanly
        XCTAssertTrue(
            EventAtlasGolfTournament11666.matchesTournamentIdentity(
                tournamentName: "Arnold Palmer Invitational presented by Mastercard",
                slug: "arnold-palmer-invitational",
                leaderboardEventName: "Arnold Palmer Invitational"
            )
        )

        // Different tournament sharing only a generic word ("Open" / "Championship") NEVER matches
        XCTAssertFalse(
            EventAtlasGolfTournament11666.matchesTournamentIdentity(
                tournamentName: "The Masters",
                slug: "the-masters",
                leaderboardEventName: "Austin Championship"
            )
        )
        XCTAssertFalse(
            EventAtlasGolfTournament11666.matchesTournamentIdentity(
                tournamentName: "U.S. Open",
                slug: "us-open",
                leaderboardEventName: "Genesis Scottish Open"
            )
        )
    }

    func testLiveGolfHeadlineFormatsWholePregameStreamingTenthsNowAndRenders390px() async throws {
        XCTAssertEqual(EventAtlasGolfTournament11666.wholePercentProbabilityText(0.02), "2%")
        XCTAssertEqual(EventAtlasGolfTournament11666.wholePercentProbabilityText(0.04), "4%")
        XCTAssertEqual(EventAtlasGolfTournament11666.wholePercentProbabilityText(0.184), "18%")
        XCTAssertEqual(EventAtlasGolfTournament11666.liveStreamingProbabilityText(0.173), "17.3%")
        XCTAssertEqual(EventAtlasGolfTournament11666.liveStreamingProbabilityText(0.108), "10.8%")
        XCTAssertEqual(EventAtlasGolfTournament11666.liveStreamingProbabilityText(0.078), "7.8%")
        XCTAssertEqual(EventAtlasGolfTournament11666.liveStreamingProbabilityText(0.059), "5.9%")

        let fixture = try makeAustinLiveFixture()
        let atlas = await GolfTournamentViewModel.loadAtlasData(
            for: fixture.response,
            fetchMarket: { _ in fixture.winMarket },
            fetchTimeline: { _ in fixture.timeline },
            fetchLeaderboard: { _ in fixture.leaderboard }
        )
        let contenders = EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: fixture.presentation,
            atlasData: atlas,
            selectedGolferName: nil,
            now: fixedNow
        )
        XCTAssertEqual(contenders.count, 4)
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[0], phase: .recorded),
            "Crowe 17%"
        )
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[1], phase: .recorded),
            "Brown 11%"
        )
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[2], phase: .recorded),
            "Greyserman 8%"
        )
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: contenders[3], phase: .recorded),
            "Van Rooyen 6%"
        )

        let sectionView = EventAtlasGolfTournamentSection11666(
            presentation: fixture.presentation,
            atlasData: atlas,
            now: fixedNow
        )
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(width: 390)
        .background(Color(uiColor: .systemGroupedBackground))

        for sizeCat in [DynamicTypeSize.large, .accessibility2] {
            let host = hostForMeasurement(sectionView.environment(\.colorScheme, .light), at: sizeCat)
            let measured = host.sizeThatFits(in: CGSize(width: 390, height: 2400))
            XCTAssertLessThanOrEqual(measured.width, 390.5)
            XCTAssertGreaterThan(measured.height, 420)
        }

        if let outDir = ProcessInfo.processInfo.environment["SAT2F_RENDER_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            func writeHostedPNG<V: View>(_ root: V, size: CGSize, to url: URL) throws {
                let host = hostForMeasurement(root.environment(\.colorScheme, .light), at: .large)
                host.overrideUserInterfaceStyle = .light
                host.view.frame = CGRect(origin: .zero, size: size)
                let window: UIWindow
                if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                    window = UIWindow(windowScene: scene)
                } else {
                    window = UIWindow(frame: host.view.frame)
                }
                window.frame = host.view.frame
                window.overrideUserInterfaceStyle = .light
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
                fmt.scale = 3.0
                let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                    _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
                }
                if let png = img.pngData() {
                    try png.write(to: url)
                }
            }

            let fullScreen = NavigationStack {
                ScrollView {
                    EventAtlasGolfTournamentSection11666(
                        presentation: fixture.presentation,
                        atlasData: atlas,
                        now: fixedNow
                    )
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                }
                .background(Color(uiColor: .systemGroupedBackground))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        HStack(spacing: 4) {
                            Image(systemName: "chevron.left")
                                .font(.subheadline.weight(.semibold))
                            Text("Golf")
                                .font(.body)
                        }
                        .foregroundStyle(DS.blueReadable)
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        HStack(spacing: 12) {
                            HStack(spacing: 4) {
                                Image(systemName: "bookmark")
                                Text("Pin")
                            }
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.primary)
                            Image(systemName: "square.and.arrow.up")
                                .font(.subheadline)
                                .foregroundStyle(.primary)
                        }
                    }
                }
            }
            .frame(width: 390, height: 852)

            try writeHostedPNG(
                fullScreen,
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2f-golf-during-390x852.png")
            )

            let sheet = VStack(alignment: .leading, spacing: 10) {
                Text("Golf During a Tournament · LIVE · R2, Par, Whole Pregame %, Streaming Tenths Now")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                EventAtlasGolfHeadlineCardView192A(
                    presentation: fixture.presentation,
                    contenders: contenders,
                    closingRound: nil,
                    liveLeaderboard: atlas.liveLeaderboard,
                    phase: .recorded,
                    onOpenFullField: {},
                    onOpenDetails: {}
                )
                EventAtlasGolfJourneyCardView11666(
                    contenders: contenders,
                    phase: .recorded,
                    fieldCount: fixture.presentation.field.count,
                    liveRound: atlas.liveLeaderboard?.currentRound,
                    timelineLoadFailed: false,
                    onOpenFullscreenChart: {},
                    onOpenFullField: {}
                )
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let sheetHost = hostForMeasurement(sheet.environment(\.colorScheme, .light), at: .large)
            let sheetHeight = ceil(sheetHost.sizeThatFits(in: CGSize(width: 390, height: 2200)).height)
            try writeHostedPNG(
                sheet,
                size: CGSize(width: 390, height: sheetHeight),
                to: dirURL.appendingPathComponent("sat2f-golf-live-headline-sheet-390.png")
            )
        }
    }
}
