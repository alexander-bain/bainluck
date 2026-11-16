import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Follow-up polish (Item 6, Sat Nov 14):
/// 1. A team's record is never larger than its name (e.g. "Fighting Illini" / "15-2" at 390 px).
/// 2. Both names in one card are the same size (e.g. "Trail Blazers" vs "Timberwolves" at AX5).
/// 3. No flat grey pulse line when nothing is streaming (before-game headlines, non-streaming live
///    headlines, pre-tournament golf, non-streaming futures).
/// 4. Golf "Finish expectations" uses the page's word ("Pregame" / "vs pregame" / "since pregame")
///    and minute-precision PT timestamps with no seconds ("Nov 14, 10:55 AM PT").
@MainActor
final class FollowUpPolishItem6Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T19:00:00Z")!
    private let freshISO = "2026-11-14T18:55:00Z"

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func makeNBAEvent(
        id: Int,
        status: String,
        awayTeam: String,
        awayRecord: String,
        awayColor: String,
        homeTeam: String,
        homeRecord: String,
        homeColor: String,
        awayScore: Int? = nil,
        homeScore: Int? = nil,
        sport: String = "basketball_nba"
    ) throws -> EventDetail {
        var dict: [String: Any] = [
            "id": id,
            "sport": sport,
            "home_team": homeTeam,
            "away_team": awayTeam,
            "commence_time": status == "scheduled" ? "2026-11-15T01:30:00Z" : "2026-11-14T17:30:00Z",
            "status": status,
            "current_odds": [
                "home_probability": 0.584,
                "away_probability": 0.416,
                "home_rendered_percent": 58,
                "away_rendered_percent": 42,
            ],
            "opening_odds": [
                "home_probability": 0.53,
                "away_probability": 0.47,
            ],
            "projected_home_score": 115.0,
            "projected_away_score": 109.0,
            "home_team_data": [
                "team_id": 101,
                "name": homeTeam,
                "short_name": homeTeam.components(separatedBy: " ").suffix(2).joined(separator: " "),
                "abbreviation": "HOM",
                "record": homeRecord,
                "primary_color": homeColor,
            ],
            "away_team_data": [
                "team_id": 102,
                "name": awayTeam,
                "short_name": awayTeam.components(separatedBy: " ").suffix(2).joined(separator: " "),
                "abbreviation": "AWY",
                "record": awayRecord,
                "primary_color": awayColor,
            ],
        ]
        if let homeScore { dict["home_score"] = homeScore }
        if let awayScore { dict["away_score"] = awayScore }
        if status == "live" {
            dict["espn"] = ["period": "Q3", "game_clock": "6:42"]
        }
        return try makeDecoder().decode(
            EventDetail.self,
            from: try JSONSerialization.data(withJSONObject: dict)
        )
    }

    // MARK: - 1 & 2. Shared Team Name Size + Record Never Larger Than Name

    func testRecordIsNeverLargerThanNameAndBothNamesMatchAcrossSizes() {
        // Live 3-column 390 px card leaves ~84 pt for team identity stack:
        // "Fighting Illini" shrinks to fit on one line, and its "15-2" record is strictly smaller.
        let illiniVsPurdueNameSize = CardTeamNameSizing.sharedSingleLineFontSize(
            names: ["Fighting Illini", "Boilermakers"],
            baseSize: 15,
            weight: .bold,
            availableWidth: 84,
            minimumScale: 0.58
        )
        let illiniRecordSize = CardTeamNameSizing.cappedRecordFontSize(
            baseRecordSize: 12,
            teamNameFontSize: illiniVsPurdueNameSize
        )
        XCTAssertLessThan(
            illiniRecordSize,
            illiniVsPurdueNameSize,
            "Record (\(illiniRecordSize) pt) must be strictly smaller than 'Fighting Illini' (\(illiniVsPurdueNameSize) pt)"
        )

        // Largest text (AX5, preferred .subheadline = 49 pt, preferred .caption1 = 40 pt):
        // "Trail Blazers" fits at 49 pt alone while "Timberwolves" needs scaling;
        // sharedSingleLineFontSize gives BOTH rows the smaller fitting scale, and record is capped below it.
        let ax5SharedNameSize = CardTeamNameSizing.sharedSingleLineFontSize(
            names: ["Trail Blazers", "Timberwolves"],
            baseSize: 49,
            weight: .bold,
            availableWidth: 286,
            minimumScale: 0.45
        )
        let timberwolvesAloneSize = CardTeamNameSizing.sharedSingleLineFontSize(
            names: ["Timberwolves"],
            baseSize: 49,
            weight: .bold,
            availableWidth: 286,
            minimumScale: 0.45
        )
        let blazersAloneSize = CardTeamNameSizing.sharedSingleLineFontSize(
            names: ["Trail Blazers"],
            baseSize: 49,
            weight: .bold,
            availableWidth: 286,
            minimumScale: 0.45
        )
        XCTAssertLessThan(timberwolvesAloneSize, blazersAloneSize)
        XCTAssertEqual(
            ax5SharedNameSize,
            min(timberwolvesAloneSize, blazersAloneSize),
            "Both rows must use the smaller of the two fitting scales so neither name towers over the other"
        )

        let ax5RecordSize = CardTeamNameSizing.cappedRecordFontSize(
            baseRecordSize: 40,
            teamNameFontSize: ax5SharedNameSize
        )
        XCTAssertLessThan(ax5RecordSize, ax5SharedNameSize)

        // Word-safe compact card sizing also shares one scale across both rows.
        let compactPairSize = CardTeamNameSizing.sharedWordSafeFontSize(
            names: ["Golden Hurricane", "Utes"],
            baseSize: 17,
            weight: .semibold,
            availableWidth: 96,
            minimumScale: 0.72
        )
        let compactLongOnly = CardTeamNameSizing.sharedWordSafeFontSize(
            names: ["Golden Hurricane"],
            baseSize: 17,
            weight: .semibold,
            availableWidth: 96,
            minimumScale: 0.72
        )
        XCTAssertEqual(compactPairSize, compactLongOnly)
    }

    // MARK: - 3. No Flat Grey Pulse Line When Nothing Is Streaming

    /// Counts non-white pulse pixels inside the top-right interior of the headline card's `topBar`
    /// (`y = 26..46 pt`, `x = 300..358 pt` at `390 pt` width), strictly inside the white card
    /// interior and above the column header row (`y >= 56 pt`).
    private func countTopBarPulsePixels(in image: UIImage) throws -> Int {
        let cg = try XCTUnwrap(image.cgImage)
        let scale = image.scale
        var bytes = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        return try bytes.withUnsafeMutableBytes { buffer in
            let ctx = try XCTUnwrap(
                CGContext(
                    data: buffer.baseAddress,
                    width: cg.width,
                    height: cg.height,
                    bitsPerComponent: 8,
                    bytesPerRow: cg.width * 4,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                )
            )
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
            let values = buffer.bindMemory(to: UInt8.self)
            let minY = max(0, Int(26 * scale))
            let maxY = min(cg.height, Int(46 * scale))
            let minX = max(0, Int(300 * scale))
            let maxX = min(cg.width, Int(358 * scale))
            var inkPixels = 0
            for y in minY..<maxY {
                for x in minX..<maxX {
                    let idx = (y * cg.width + x) * 4
                    let r = Int(values[idx])
                    let g = Int(values[idx + 1])
                    let b = Int(values[idx + 2])
                    if r + g + b < 750 {
                        inkPixels += 1
                    }
                }
            }
            return inkPixels
        }
    }

    private func renderToImage<V: View>(
        _ view: V,
        width: CGFloat = 390,
        typeSize: DynamicTypeSize = .large,
        settleDuration: TimeInterval = 0.25
    ) throws -> UIImage {
        let wrapped = view
            .frame(width: width)
            .background(Color(uiColor: .systemGroupedBackground))
            .environment(\.colorScheme, .light)
        let host = hostForMeasurement(wrapped, at: typeSize)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = .light
        let initialFitting = host.sizeThatFits(in: CGSize(width: width, height: 10_000))
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: width, height: max(initialFitting.height, 80)))

        let activeScene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
            ?? UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first

        let window: UIWindow
        if let activeScene {
            window = UIWindow(windowScene: activeScene)
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

        let until = Date().addingTimeInterval(settleDuration)
        repeat {
            let settled = host.sizeThatFits(in: CGSize(width: width, height: 10_000))
            let nextHeight = max(settled.height, 80)
            if abs(host.view.frame.height - nextHeight) > 0.5 {
                host.view.frame = CGRect(origin: .zero, size: CGSize(width: width, height: nextHeight))
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let finalFitting = host.sizeThatFits(in: CGSize(width: width, height: 10_000))
        let finalSize = CGSize(width: width, height: max(finalFitting.height, 80))
        host.view.frame = CGRect(origin: .zero, size: finalSize)
        window.frame = host.view.frame
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    func testHeadlineDrawsNoFlatGreyPulseLineWhenNotStreamingAndDrawsPulseWhenStreaming() throws {
        let beforeEvent = try makeNBAEvent(
            id: 601,
            status: "scheduled",
            awayTeam: "Portland Trail Blazers",
            awayRecord: "9-11",
            awayColor: "#E03A3E",
            homeTeam: "Minnesota Timberwolves",
            homeRecord: "14-6",
            homeColor: "#0C2340"
        )
        let beforeModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: beforeEvent,
                awayFullName: beforeEvent.awayTeam,
                homeFullName: beforeEvent.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        let colors = TeamTextContrast.cardColors(
            awayHex: beforeEvent.awayTeamData?.primaryColor,
            homeHex: beforeEvent.homeTeamData?.primaryColor
        )

        let beforeCard = EventSportHeadlineCard12472(
            model: beforeModel,
            colors: colors,
            ekgTracker: .empty,
            liveUpdateStatus: .awaitingUpdate,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
        .padding(16)

        let beforeImg = try renderToImage(beforeCard)
        // Top-right area of topBar has zero pulse ink when before-game / not streaming.
        XCTAssertEqual(try countTopBarPulsePixels(in: beforeImg), 0)

        let liveEvent = try makeNBAEvent(
            id: 602,
            status: "live",
            awayTeam: "Portland Trail Blazers",
            awayRecord: "9-11",
            awayColor: "#E03A3E",
            homeTeam: "Minnesota Timberwolves",
            homeRecord: "14-6",
            homeColor: "#0C2340",
            awayScore: 84,
            homeScore: 88
        )
        let liveModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: liveEvent,
                awayFullName: liveEvent.awayTeam,
                homeFullName: liveEvent.homeTeam,
                liveStatusText: "Q3 · 6:42",
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )

        let quietLiveCard = EventSportHeadlineCard12472(
            model: liveModel,
            colors: colors,
            ekgTracker: .empty,
            liveUpdateStatus: .autoRefresh,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: true,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
        .padding(16)

        let quietLiveImg = try renderToImage(quietLiveCard)
        XCTAssertEqual(try countTopBarPulsePixels(in: quietLiveImg), 0)

        // When venue updates ARE actively streaming, the green pulse draws in top-right!
        let activeTracker = EkgTracker.empty
            .stepped(
                EkgTracker.Observation(
                    eventId: 602,
                    transportOpen: true,
                    confirmedAt: fixedNow.addingTimeInterval(-10),
                    priceObservedAt: fixedNow.addingTimeInterval(-10)
                ),
                now: fixedNow.addingTimeInterval(-9)
            )
            .stepped(
                EkgTracker.Observation(
                    eventId: 602,
                    transportOpen: true,
                    confirmedAt: fixedNow.addingTimeInterval(-2),
                    priceObservedAt: fixedNow.addingTimeInterval(-2)
                ),
                now: fixedNow.addingTimeInterval(-2)
            )
        XCTAssertEqual(EkgHeartbeat.present(activeTracker, status: .live, now: fixedNow).mode, .beating)

        let streamingLiveModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: liveEvent,
                awayFullName: liveEvent.awayTeam,
                homeFullName: liveEvent.homeTeam,
                liveStatusText: "Q3 · 6:42",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        let streamingLiveCard = EventSportHeadlineCard12472(
            model: streamingLiveModel,
            colors: colors,
            ekgTracker: activeTracker,
            liveUpdateStatus: .live,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: true,
            lastReceivedAt: fixedNow,
            confirmedAt: fixedNow,
            revealForecast: nil
        )
        .padding(16)

        let streamingLiveImg = try renderToImage(streamingLiveCard, settleDuration: 0.70)
        XCTAssertGreaterThan(try countTopBarPulsePixels(in: streamingLiveImg), 15)
    }

    // MARK: - 4. Golf Finish Expectations ("Pregame" + Minute Timestamp Without Seconds) & 390px Renders

    func testGolfFinishExpectationsUsesPregameWordAndNoSecondsAndExports390Renders() throws {
        // Timestamp helper omits seconds ("10:55 AM PT", never "10:55:00 AM PT")
        let formatted = EventAtlasChartMarks11666.formatMinuteTimestampPT(try XCTUnwrap(freshISO.asDate))
        XCTAssertEqual(formatted, "Nov 14, 10:55 AM PT")
        XCTAssertFalse(formatted.contains(":00"))

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
            "golfers": [
                ["name": "Trace Crowe", "probability": 0.173, "opening_probability": 0.02, "movement_24h": 0.085, "rank": 1],
                ["name": "Blades Brown", "probability": 0.108, "opening_probability": 0.04, "movement_24h": 0.052, "rank": 2],
                ["name": "Max Greyserman", "probability": 0.078, "opening_probability": 0.03, "movement_24h": 0.031, "rank": 3],
                ["name": "Erik Van Rooyen", "probability": 0.059, "opening_probability": 0.02, "movement_24h": 0.024, "rank": 4],
            ],
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

        func makeMarket(
            id: Int,
            name: String,
            prob: Double,
            open: Double,
            createdAt: String? = "2026-11-11T12:00:00Z"
        ) throws -> FuturesMarketDetail {
            var d: [String: Any] = [
                "id": id,
                "name": name,
                "status": "open",
                "source": "datagolf",
                "commence_time": "2026-11-13T13:00:00Z",
                "updated_at": freshISO,
                "outcomes": [
                    ["id": id * 10 + 1, "name": "Trace Crowe", "probability": prob, "opening_probability": open, "observed_at": freshISO],
                    ["id": id * 10 + 2, "name": "Blades Brown", "probability": max(0.05, prob - 0.06), "opening_probability": open, "observed_at": freshISO],
                    ["id": id * 10 + 3, "name": "Max Greyserman", "probability": max(0.04, prob - 0.09), "opening_probability": open, "observed_at": freshISO],
                    ["id": id * 10 + 4, "name": "Erik Van Rooyen", "probability": max(0.03, prob - 0.11), "opening_probability": open, "observed_at": freshISO],
                ],
            ]
            if let createdAt {
                d["created_at"] = createdAt
            }
            return try makeDecoder().decode(FuturesMarketDetail.self, from: try JSONSerialization.data(withJSONObject: d))
        }

        let winMarket = try makeMarket(id: 9401, name: "Winner", prob: 0.173, open: 0.02)
        let top5Market = try makeMarket(id: 9402, name: "Top 5 Finish", prob: 0.44, open: 0.09)
        let top10Market = try makeMarket(id: 9403, name: "Top 10 Finish", prob: 0.62, open: 0.17)
        let top20Market = try makeMarket(id: 9404, name: "Top 20 Finish", prob: 0.79, open: 0.31)
        let makeCutMarket = try makeMarket(id: 9405, name: "Make the Cut", prob: 0.94, open: 0.68)

        let atlas = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: winMarket,
            top5Market: top5Market,
            top10Market: top10Market,
            top20Market: top20Market,
            makeCutMarket: makeCutMarket
        )

        let finishInput = EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: "Trace Crowe",
            presentation: presentation,
            atlasData: atlas,
            selectedFinish: "win",
            now: fixedNow
        )
        XCTAssertEqual(finishInput.beforeLabel, "Pregame")
        XCTAssertEqual(finishInput.beforeColumnLabel, "Pregame")
        XCTAssertEqual(finishInput.win.deltaText, "+15.3 pts since pregame")
        XCTAssertFalse(finishInput.finalBarsExplanation.localizedCaseInsensitiveContains("opened"))
        XCTAssertFalse(finishInput.finalFootnotePrefix.localizedCaseInsensitiveContains("opened"))
        XCTAssertTrue(finishInput.finalBarsExplanation.localizedCaseInsensitiveContains("pregame"))
        XCTAssertEqual(finishInput.context, "In play · latest recorded Nov 14, 10:55 AM PT · vs pregame")
        XCTAssertFalse(finishInput.context?.contains(":00") ?? false)
        for slot in finishInput.slots {
            XCTAssertFalse(
                slot.recorded?.accessibilityDetail.contains(":00 ") ?? false,
                "Must not print :00 seconds in \(slot.recorded?.accessibilityDetail ?? "")"
            )
        }

        // Markets first seen AFTER play began (`created_at >= firstTeeTime`) or with unknown creation
        // time (`created_at == nil`) NEVER label a mid-tournament reading "Pregame" — the cell stays empty.
        let midTournamentWin = try makeMarket(
            id: 9411,
            name: "Winner",
            prob: 0.173,
            open: 0.08,
            createdAt: "2026-11-13T16:00:00Z"
        )
        let unknownCreatedWin = try makeMarket(
            id: 9412,
            name: "Winner",
            prob: 0.173,
            open: 0.08,
            createdAt: nil
        )
        for nonPregameMarket in [midTournamentWin, unknownCreatedWin] {
            let nonPregameAtlas = EventAtlasGolfTournament11666.TournamentAtlasData(winnerMarket: nonPregameMarket)
            let nonPregameFinish = EventAtlasGolfTournament11666.buildFinishExpectations(
                selectedGolferName: "Trace Crowe",
                presentation: presentation,
                atlasData: nonPregameAtlas,
                selectedFinish: "win",
                now: fixedNow
            )
            XCTAssertNil(nonPregameFinish.win.before, "Never label a mid-tournament or undated baseline 'Pregame'")
            XCTAssertNil(nonPregameFinish.win.deltaText)
            XCTAssertFalse(nonPregameFinish.context?.contains("vs pregame") ?? false)

            let contenders = EventAtlasGolfTournament11666.buildJourneyContenders(
                presentation: presentation,
                atlasData: nonPregameAtlas,
                selectedGolferName: "Trace Crowe",
                now: fixedNow
            )
            XCTAssertTrue(contenders.allSatisfy { $0.openingProbability == nil }, "Headline Pregame cell must stay empty when market was first seen after tee-off or has no timestamp")
        }

        if let outDir = ProcessInfo.processInfo.environment["RENDER_OUTPUT_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            // 1. 390px Default (.large): Fighting Illini (15-2) vs Boilermakers (18-4) live + Trail Blazers vs Timberwolves pregame (no flat pulse!)
            let illiniLive = try makeNBAEvent(
                id: 701,
                status: "live",
                awayTeam: "Illinois Fighting Illini",
                awayRecord: "15-2",
                awayColor: "#E84A27",
                homeTeam: "Purdue Boilermakers",
                homeRecord: "18-4",
                homeColor: "#CEB888",
                awayScore: 68,
                homeScore: 71
            )
            let illiniModel = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: illiniLive,
                    awayFullName: "Fighting Illini",
                    homeFullName: "Boilermakers",
                    liveStatusText: "2H · 5:14",
                    hasScore: true,
                    numberStreams: false,
                    now: fixedNow
                )
            )
            // Construct explicit long-name TeamRowModels ("Fighting Illini" / "Boilermakers") to prove Fable's exact #12724 case
            let illiniExplicitModel = EventSportHeadlines12472.Model(
                eventId: illiniModel.eventId,
                sportKey: illiniModel.sportKey,
                kind: illiniModel.kind,
                plainMetaText: illiniModel.plainMetaText,
                commenceTime: illiniModel.commenceTime,
                startIsTbd: illiniModel.startIsTbd,
                broadcast: illiniModel.broadcast,
                eventStatus: illiniModel.eventStatus,
                liveBadgeText: "LIVE · 2H 5:14",
                leagueLabel: "NCAAB",
                pregameColumnHeaders: nil,
                liveColumnHeaders: illiniModel.liveColumnHeaders,
                finalColumnHeaders: nil,
                away: EventSportHeadlines12472.TeamRowModel(
                    fullName: "Illinois Fighting Illini",
                    opponentFullName: "Purdue Boilermakers",
                    shortName: "Fighting Illini",
                    logoURL: nil,
                    record: "15-2",
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: 68,
                    pregameChanceText: "47%",
                    winChanceText: "42%",
                    rawProbability: 0.42
                ),
                home: EventSportHeadlines12472.TeamRowModel(
                    fullName: "Purdue Boilermakers",
                    opponentFullName: "Illinois Fighting Illini",
                    shortName: "Boilermakers",
                    logoURL: nil,
                    record: "18-4",
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: 71,
                    pregameChanceText: "53%",
                    winChanceText: "58%",
                    rawProbability: 0.58
                ),
                pregameAwayMarker: 0.47,
                soccerThreeWay: nil,
                tennisScoreFirst: nil,
                showsEkg: true,
                stacksRecordUnderName: true,
                showsBottomBar: true,
                showsRowDivider: false,
                sourceMark: nil,
                confidenceTier: nil
            )
            let illiniColors = TeamTextContrast.cardColors(awayHex: "#E84A27", homeHex: "#0C2340")

            let blazersBefore = try makeNBAEvent(
                id: 702,
                status: "scheduled",
                awayTeam: "Portland Trail Blazers",
                awayRecord: "9-11",
                awayColor: "#E03A3E",
                homeTeam: "Minnesota Timberwolves",
                homeRecord: "14-6",
                homeColor: "#0C2340"
            )
            let blazersBeforeModel = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: blazersBefore,
                    awayFullName: blazersBefore.awayTeam,
                    homeFullName: blazersBefore.homeTeam,
                    liveStatusText: nil,
                    hasScore: false,
                    numberStreams: false,
                    now: fixedNow
                )
            )
            let blazersColors = TeamTextContrast.cardColors(awayHex: "#E03A3E", homeHex: "#0C2340")

            let sheet1 = VStack(alignment: .leading, spacing: 14) {
                EventSportHeadlineCard12472(
                    model: illiniExplicitModel,
                    colors: illiniColors,
                    ekgTracker: .empty,
                    liveUpdateStatus: .autoRefresh,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                EventSportHeadlineCard12472(
                    model: blazersBeforeModel,
                    colors: blazersColors,
                    ekgTracker: .empty,
                    liveUpdateStatus: .awaitingUpdate,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
            }
            .padding(16)

            if let png1 = try renderToImage(sheet1, width: 390, typeSize: .large).pngData() {
                try png1.write(to: dirURL.appendingPathComponent("followup-item6-390-default.png"))
            }

            // 2. 390px AX5 (largest text): Trail Blazers vs Timberwolves — both names exact same size!
            let blazersLive = try makeNBAEvent(
                id: 703,
                status: "live",
                awayTeam: "Portland Trail Blazers",
                awayRecord: "9-11",
                awayColor: "#E03A3E",
                homeTeam: "Minnesota Timberwolves",
                homeRecord: "14-6",
                homeColor: "#0C2340",
                awayScore: 84,
                homeScore: 88
            )
            let blazersLiveModel = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: blazersLive,
                    awayFullName: blazersLive.awayTeam,
                    homeFullName: blazersLive.homeTeam,
                    liveStatusText: "Q3 · 6:42",
                    hasScore: true,
                    numberStreams: false,
                    now: fixedNow
                )
            )
            let ax5Sheet = VStack(alignment: .leading, spacing: 14) {
                EventSportHeadlineCard12472(
                    model: illiniExplicitModel,
                    colors: illiniColors,
                    ekgTracker: .empty,
                    liveUpdateStatus: .autoRefresh,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                EventSportHeadlineCard12472(
                    model: blazersLiveModel,
                    colors: blazersColors,
                    ekgTracker: .empty,
                    liveUpdateStatus: .autoRefresh,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
            }
            .padding(16)

            if let png2 = try renderToImage(ax5Sheet, width: 390, typeSize: .accessibility5).pngData() {
                try png2.write(to: dirURL.appendingPathComponent("followup-item6-trailblazers-ax5-390.png"))
            }

            // 3. 390px Golf "Finish expectations" section ("Pregame", "+15.3 pts since pregame", "Nov 14, 10:55 AM PT")
            let golfSection = EventAtlasGolfTournamentSection11666(
                presentation: presentation,
                atlasData: atlas,
                now: fixedNow
            )
            .padding(16)

            if let png3 = try renderToImage(golfSection, width: 390, typeSize: .large).pngData() {
                try png3.write(to: dirURL.appendingPathComponent("followup-item6-golf-finish-expectations-390.png"))
            }

            // 4. 390px Golf mid-tournament-first-seen markets (`created_at >= firstTeeTime`): Pregame cells stay empty
            let midTop5 = try makeMarket(id: 9415, name: "Top 5 Finish", prob: 0.44, open: 0.25, createdAt: "2026-11-13T16:00:00Z")
            let midTop10 = try makeMarket(id: 9416, name: "Top 10 Finish", prob: 0.62, open: 0.39, createdAt: "2026-11-13T16:00:00Z")
            let midAtlas = EventAtlasGolfTournament11666.TournamentAtlasData(
                winnerMarket: midTournamentWin,
                top5Market: midTop5,
                top10Market: midTop10
            )
            let midGolfSection = EventAtlasGolfTournamentSection11666(
                presentation: presentation,
                atlasData: midAtlas,
                now: fixedNow
            )
            .padding(16)

            if let png4 = try renderToImage(midGolfSection, width: 390, typeSize: .large).pngData() {
                try png4.write(to: dirURL.appendingPathComponent("followup-item6-golf-mid-tournament-empty-pregame-390.png"))
            }
        }
    }
}
