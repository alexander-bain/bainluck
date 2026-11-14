import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class AmazingHeadlinesOvernight4Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T08:00:00Z")!

    private struct StubEventDetailProvider: EventDetailProviding {
        let detail: EventDetail
        let history: EventHistoryResponse
        var markets: GameMarketsResponse? = nil

        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                RelatedFuturesResponse.self,
                from: Data(#"{"event_id":\#(eventId),"markets":[]}"#.utf8)
            )
        }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
            try JSONDecoder().decode(TeamProgressionResponse.self, from: Data(#"{"home":null,"away":null}"#.utf8))
        }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse {
            if let markets { return markets }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                GameMarketsResponse.self,
                from: Data(#"{"event_id":\#(eventId),"player_props":[],"period_markets":[],"other_markets":[]}"#.utf8)
            )
        }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse {
            LineMovementResponse(
                eventId: eventId,
                movements: [],
                explanation: nil,
                disagreementExplanation: nil,
                disagreementData: nil,
                context: nil,
                cached: nil,
                createdAt: nil
            )
        }
    }

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func decodeGameMarkets(_ json: String) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    private func soccerBeforeFixture(
        commenceTime: String = "2026-11-15T16:30:00Z",
        homeProb: Double = 0.52,
        drawProb: Double? = 0.25,
        awayProb: Double? = 0.23
    ) throws -> EventDetail {
        let drawField = drawProb.map { #""draw_probability": \#($0),"# } ?? ""
        let awayField = awayProb.map { #""away_probability": \#($0),"# } ?? #""away_probability": null,"#
        return try decodeEvent("""
        {
          "id": 9127041,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "home_team": "Arsenal",
          "away_team": "Chelsea",
          "commence_time": "\(commenceTime)",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "ARS",
            "primary_color": "#EF0107",
            "record": "7-2-2"
          },
          "away_team_data": {
            "abbreviation": "CHE",
            "primary_color": "#034694",
            "record": "6-3-2"
          },
          "current_odds": {
            "home_probability": \(homeProb),
            \(drawField)
            \(awayField)
            "updated_at": "2026-11-14T07:58:00Z"
          },
          "opening_odds": {
            "home_probability": 0.50,
            "away_probability": 0.24
          },
          "hero_probability": \(homeProb),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T07:58:00Z",
          "win_probability_sources": {
            "betting": { "value": 0.52, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.51, "display_name": "Kalshi" },
            "polymarket": { "value": 0.53, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.51, "observed_at": "2026-11-14T07:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.53, "observed_at": "2026-11-14T07:57:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.52, "count": 6, "observed_at": "2026-11-14T07:56:00Z" }
            ]
          }
        }
        """)
    }

    private func soccerAfterFixture(
        homeScore: Int = 2,
        awayScore: Int = 1,
        settledResult: String = "home",
        includeThreeWayPrematch: Bool = true
    ) throws -> EventDetail {
        let prematchJSON = includeThreeWayPrematch ? """
          "prematch_odds": {
            "home_probability": 0.64,
            "draw_probability": 0.21,
            "away_probability": 0.15,
            "source": "polymarket"
          },
        """ : ""
        return try decodeEvent("""
        {
          "id": 9127042,
          "sport": "soccer_mexico_ligamx",
          "sport_name": "Liga MX",
          "home_team": "Monterrey",
          "away_team": "Querétaro",
          "commence_time": "2026-11-10T19:00:00Z",
          "completed_at": "2026-11-10T20:55:00Z",
          "status": "completed",
          "home_score": \(homeScore),
          "away_score": \(awayScore),
          "final_score_period": "regulation",
          "hero_settled_result": "\(settledResult)",
          "home_team_data": {
            "abbreviation": "MTY",
            "primary_color": "#0F2B5B",
            "record": "9-4-4"
          },
          "away_team_data": {
            "abbreviation": "QRO",
            "primary_color": "#1E40AF",
            "record": "3-3-11"
          },
          \(prematchJSON)
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "polymarket", "name": "Polymarket", "probability": 0.64, "observed_at": "2026-11-10T18:59:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.63, "count": 5, "observed_at": "2026-11-10T18:58:00Z" }
            ]
          }
        }
        """)
    }

    private func badgeFileURLString(letters: String, hex: String) -> String {
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let img = UIGraphicsImageRenderer(size: CGSize(width: 28, height: 28), format: fmt).image { _ in
            let resolvedHex = TeamTextContrast.textHexOnCard(hex, fallback: "#1E293B")
            let tint = UIColor(Color(hex: resolvedHex))
            tint.withAlphaComponent(0.18).setFill()
            UIBezierPath(ovalIn: CGRect(x: 0, y: 0, width: 28, height: 28)).fill()
            let p = NSMutableParagraphStyle()
            p.alignment = .center
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 9.5, weight: .bold),
                .foregroundColor: tint,
                .paragraphStyle: p,
            ]
            let s = letters as NSString
            let sz = s.size(withAttributes: attrs)
            s.draw(in: CGRect(x: 0, y: (28 - sz.height) / 2, width: 28, height: sz.height), withAttributes: attrs)
        }
        guard let png = img.pngData() else { return "" }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("bl-test-badge-\(letters).png")
        try? png.write(to: url)
        return url.absoluteString
    }

    private func nhlDuringFixture(
        homeProb: Double = 0.516
    ) throws -> EventDetail {
        let awayProb = ((1.0 - homeProb) * 1_000_000).rounded() / 1_000_000
        let anaLogo = badgeFileURLString(letters: "ANA", hex: "#CF4520")
        let nshLogo = badgeFileURLString(letters: "NSH", hex: "#B48500")
        return try decodeEvent("""
        {
          "id": 9127043,
          "sport": "icehockey_nhl",
          "home_team": "Anaheim Ducks",
          "away_team": "Nashville Predators",
          "commence_time": "2026-11-14T06:30:00Z",
          "status": "live",
          "home_score": 2,
          "away_score": 2,
          "home_team_data": {
            "abbreviation": "ANA",
            "primary_color": "#CF4520",
            "logo_large": "\(anaLogo)",
            "record": "16-16-4"
          },
          "away_team_data": {
            "abbreviation": "NSH",
            "primary_color": "#B48500",
            "logo_large": "\(nshLogo)",
            "record": "18-14-3"
          },
          "current_odds": {
            "home_probability": \(homeProb),
            "away_probability": \(awayProb),
            "home_rendered_percent": 52,
            "away_rendered_percent": 48,
            "updated_at": "2026-11-14T07:59:45Z"
          },
          "prematch_odds": {
            "home_probability": 0.54,
            "away_probability": 0.46,
            "home_rendered_percent": 54,
            "away_rendered_percent": 46,
            "source": "kalshi"
          },
          "opening_odds": {
            "home_probability": 0.54,
            "away_probability": 0.46
          },
          "hero_probability": \(homeProb),
          "hero_probability_away": \(awayProb),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T07:59:45Z",
          "espn": {
            "period": "2nd Period",
            "game_clock": "08:14",
            "broadcast": "ESPN+"
          },
          "win_probability_sources": {
            "betting": { "value": 0.52, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.51, "display_name": "Kalshi" },
            "polymarket": { "value": 0.52, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.51, "observed_at": "2026-11-14T07:59:45Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.52, "observed_at": "2026-11-14T07:59:30Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.52, "count": 5, "observed_at": "2026-11-14T07:59:15Z" }
            ]
          }
        }
        """)
    }

    private func resolveHeadline(
        _ event: EventDetail,
        hasScore: Bool,
        numberStreams: Bool,
        gameMarkets: GameMarketsResponse? = nil
    ) -> EventSportHeadlines12472.Model? {
        EventSportHeadlines12472.resolve(
            event: event,
            awayFullName: event.awayTeam,
            homeFullName: event.homeTeam,
            liveStatusText: PeriodLabel.liveStatusText(
                period: event.espn?.period,
                gameClock: event.espn?.gameClock
            ),
            hasScore: hasScore,
            numberStreams: numberStreams,
            gameMarkets: gameMarkets,
            now: fixedNow
        )
    }

    // MARK: - 1. Soccer Before Match Rules

    func testSoccerBeforeMatchUsesThreeWayBoxesNeverInventsDrawAndShowsTenthsOnlyWhenStreaming() throws {
        let match = try soccerBeforeFixture(homeProb: 0.524, drawProb: 0.248, awayProb: 0.228)
        XCTAssertEqual(EventSportHeadlines12472.kind(for: match, now: fixedNow), .soccerBeforeGame)

        let nonStreaming = try XCTUnwrap(resolveHeadline(match, hasScore: false, numberStreams: false))
        XCTAssertTrue(nonStreaming.showsEkg)
        let meta = try XCTUnwrap(nonStreaming.plainMetaText)
        XCTAssertTrue(meta.hasPrefix("Premier League · "), meta)
        XCTAssertFalse(meta.localizedCaseInsensitiveContains("as of"))
        XCTAssertFalse(meta.localizedCaseInsensitiveContains("venue"))
        XCTAssertFalse(meta.localizedCaseInsensitiveContains("open"))
        XCTAssertFalse(meta.localizedCaseInsensitiveContains("settled"))

        let threeWay = try XCTUnwrap(nonStreaming.soccerThreeWay)
        XCTAssertEqual(threeWay.centerTagText, "90' Reg.")
        XCTAssertFalse(threeWay.isScorePill)
        XCTAssertTrue(threeWay.showsBottomBar)
        XCTAssertNil(threeWay.pregameHeader)
        XCTAssertEqual(threeWay.homeBox.headerLabel, "ARS WIN")
        XCTAssertEqual(threeWay.drawBox.headerLabel, "DRAW")
        XCTAssertEqual(threeWay.awayBox.headerLabel, "CHE WIN")
        XCTAssertEqual(threeWay.homeBox.mainText, "52%")
        XCTAssertEqual(threeWay.drawBox.mainText, "25%")
        XCTAssertEqual(threeWay.awayBox.mainText, "23%")

        let streaming = try XCTUnwrap(resolveHeadline(match, hasScore: false, numberStreams: true))
        let streamingThreeWay = try XCTUnwrap(streaming.soccerThreeWay)
        XCTAssertEqual(streamingThreeWay.homeBox.mainText, "52.4%")
        XCTAssertEqual(streamingThreeWay.drawBox.mainText, "24.8%")
        XCTAssertEqual(streamingThreeWay.awayBox.mainText, "22.8%")

        // Countdown inside last hour (182-A)
        let withinHour = try soccerBeforeFixture(commenceTime: "2026-11-14T08:35:00Z")
        let countdownModel = try XCTUnwrap(resolveHeadline(withinHour, hasScore: false, numberStreams: false))
        XCTAssertEqual(countdownModel.plainMetaText, "Premier League · In 35m")

        // Never invent a draw when only home/away (no explicit drawProbability and no 3-way gameMarkets)
        let twoWayOnly = try soccerBeforeFixture(homeProb: 0.52, drawProb: nil, awayProb: 0.48)
        XCTAssertNil(EventSportHeadlines12472.kind(for: twoWayOnly, now: fixedNow))

        // Fallback to gameMarkets.other explicit 3-way rows when currentOdds omits drawProbability
        let gm = try decodeGameMarkets("""
        {
          "event_id": 9127041,
          "player_props": [],
          "period_markets": [],
          "other": [
            { "_market_id": 701, "market_name": "Match Winner", "outcome_name": "Arsenal", "probability": 0.52, "source": "blend", "observed_at": "2026-11-14T07:55:00Z" },
            { "_market_id": 701, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.25, "source": "blend", "observed_at": "2026-11-14T07:55:00Z" },
            { "_market_id": 701, "market_name": "Match Winner", "outcome_name": "Chelsea", "probability": 0.23, "source": "blend", "observed_at": "2026-11-14T07:55:00Z" }
          ]
        }
        """)
        let viaMarkets = try XCTUnwrap(resolveHeadline(twoWayOnly, hasScore: false, numberStreams: false, gameMarkets: gm))
        XCTAssertEqual(viaMarkets.soccerThreeWay?.homeBox.mainText, "52%")
        XCTAssertEqual(viaMarkets.soccerThreeWay?.drawBox.mainText, "25%")
        XCTAssertEqual(viaMarkets.soccerThreeWay?.awayBox.mainText, "23%")
    }

    // MARK: - 2. Soccer After Match Rules

    func testSoccerAfterMatchShowsFullTimePillGradedBoxesAndSinglePregameHeader() throws {
        let finished = try soccerAfterFixture(homeScore: 2, awayScore: 1, settledResult: "home")
        XCTAssertEqual(EventSportHeadlines12472.kind(for: finished, now: fixedNow), .soccerAfterGame)

        let model = try XCTUnwrap(resolveHeadline(finished, hasScore: true, numberStreams: false))
        XCTAssertFalse(model.showsEkg, "finished matches do not pulse a live EKG")
        let meta = try XCTUnwrap(model.plainMetaText)
        XCTAssertTrue(meta.hasPrefix("Liga MX · Final · "), meta)
        XCTAssertFalse(meta.localizedCaseInsensitiveContains("settled"))
        XCTAssertFalse(meta.localizedCaseInsensitiveContains("open"))

        let threeWay = try XCTUnwrap(model.soccerThreeWay)
        XCTAssertEqual(threeWay.centerTagText, "2 \u{2013} 1")
        XCTAssertTrue(threeWay.isScorePill)
        XCTAssertFalse(threeWay.showsBottomBar)
        XCTAssertEqual(threeWay.homeBox.mainText, "\u{2713} Won")
        XCTAssertEqual(threeWay.homeBox.boxTone, .wonOutcome)
        XCTAssertEqual(threeWay.drawBox.mainText, "\u{2014}")
        XCTAssertEqual(threeWay.drawBox.boxTone, .mutedDash)
        XCTAssertEqual(threeWay.awayBox.mainText, "Lost")
        XCTAssertEqual(threeWay.awayBox.boxTone, .lostOutcome)

        // Single "Pregame" header — NEVER repeated inside each box, NEVER "Opened"
        XCTAssertEqual(threeWay.pregameHeader, "Pregame")
        XCTAssertEqual(threeWay.homeBox.pregameChanceText, "64%")
        XCTAssertEqual(threeWay.drawBox.pregameChanceText, "21%")
        XCTAssertEqual(threeWay.awayBox.pregameChanceText, "15%")
        for box in [threeWay.homeBox, threeWay.drawBox, threeWay.awayBox] {
            XCTAssertFalse(box.pregameChanceText?.localizedCaseInsensitiveContains("pregame") ?? false)
            XCTAssertFalse(box.pregameChanceText?.localizedCaseInsensitiveContains("open") ?? false)
        }

        // #4915: level draw finish grades Draw as won and marks NEITHER club as Lost
        let levelDraw = try soccerAfterFixture(homeScore: 1, awayScore: 1, settledResult: "draw")
        let drawModel = try XCTUnwrap(resolveHeadline(levelDraw, hasScore: true, numberStreams: false))
        let drawThreeWay = try XCTUnwrap(drawModel.soccerThreeWay)
        XCTAssertEqual(drawThreeWay.centerTagText, "1 \u{2013} 1")
        XCTAssertEqual(drawThreeWay.homeBox.mainText, "\u{2014}")
        XCTAssertEqual(drawThreeWay.drawBox.mainText, "\u{2713} Draw")
        XCTAssertEqual(drawThreeWay.awayBox.mainText, "\u{2014}")
    }

    // MARK: - 3. NHL During a Game Rules

    func testNHLDuringGameUsesScorePregameNowHeadersStackedRecordsAndStreamingTenths() throws {
        let nhl = try nhlDuringFixture(homeProb: 0.516)
        XCTAssertEqual(EventSportHeadlines12472.kind(for: nhl, now: fixedNow), .nhlDuringGame)

        let model = try XCTUnwrap(resolveHeadline(nhl, hasScore: true, numberStreams: true))
        XCTAssertEqual(model.liveBadgeText, "LIVE · P2 08:14")
        XCTAssertEqual(model.leagueLabel, "NHL")
        XCTAssertTrue(model.showsEkg)
        XCTAssertTrue(model.stacksRecordUnderName)
        XCTAssertEqual(
            model.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: "Score", pregame: "Pregame", now: "Now")
        )
        XCTAssertEqual(model.away.shortName, "Predators")
        XCTAssertEqual(model.away.record, "18-14-3")
        XCTAssertEqual(model.away.liveScore, 2)
        XCTAssertEqual(model.away.pregameChanceText, "46%")
        XCTAssertEqual(model.away.winChanceText, "48.4%")

        XCTAssertEqual(model.home.shortName, "Ducks")
        XCTAssertEqual(model.home.record, "16-16-4")
        XCTAssertEqual(model.home.liveScore, 2)
        XCTAssertEqual(model.home.pregameChanceText, "54%")
        XCTAssertEqual(model.home.winChanceText, "51.6%")
        XCTAssertEqual(model.pregameAwayMarker ?? 0, 0.46, accuracy: 0.0001)

        XCTAssertFalse(model.away.pregameChanceText?.localizedCaseInsensitiveContains("pregame") ?? false)
        XCTAssertFalse(model.home.pregameChanceText?.localizedCaseInsensitiveContains("pregame") ?? false)
        XCTAssertFalse(model.away.pregameChanceText?.localizedCaseInsensitiveContains("open") ?? false)
        XCTAssertFalse(model.home.pregameChanceText?.localizedCaseInsensitiveContains("open") ?? false)
    }

    // MARK: - 4. 390x852 First-Screen Fit & PNG Renders

    func testFirstScreenFitsAndExports390pxRenders() async throws {
        let soccerBefore = try soccerBeforeFixture()
        let soccerAfter = try soccerAfterFixture()
        let nhlDuring = try nhlDuringFixture()

        let soccerBeforeModel = try XCTUnwrap(resolveHeadline(soccerBefore, hasScore: false, numberStreams: false))
        let soccerAfterModel = try XCTUnwrap(resolveHeadline(soccerAfter, hasScore: true, numberStreams: false))
        let nhlDuringModel = try XCTUnwrap(resolveHeadline(nhlDuring, hasScore: true, numberStreams: true))

        let beatingTracker = EkgTracker(
            eventId: 9127043,
            lastSignalAt: fixedNow.addingTimeInterval(-2),
            beatAt: fixedNow.addingTimeInterval(-2),
            beats: 1
        )

        let sbColors = TeamTextContrast.cardColors(
            awayHex: soccerBefore.awayTeamData?.primaryColor,
            homeHex: soccerBefore.homeTeamData?.primaryColor
        )
        let saColors = TeamTextContrast.cardColors(
            awayHex: soccerAfter.awayTeamData?.primaryColor,
            homeHex: soccerAfter.homeTeamData?.primaryColor
        )
        let nhlColors = TeamTextContrast.cardColors(
            awayHex: nhlDuring.awayTeamData?.primaryColor,
            homeHex: nhlDuring.homeTeamData?.primaryColor
        )

        let sbCard = EventSportHeadlineCard12472(
            model: soccerBeforeModel,
            colors: sbColors,
            ekgTracker: .empty,
            liveUpdateStatus: .awaitingUpdate,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: true,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
        .frame(width: 358)

        let saCard = EventSportHeadlineCard12472(
            model: soccerAfterModel,
            colors: saColors,
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
        .frame(width: 358)

        let nhlCard = EventSportHeadlineCard12472(
            model: nhlDuringModel,
            colors: nhlColors,
            ekgTracker: beatingTracker,
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
        .frame(width: 358)

        for (label, card) in [
            ("soccerBefore", AnyView(sbCard)),
            ("soccerAfter", AnyView(saCard)),
            ("nhlDuring", AnyView(nhlCard)),
        ] {
            let host = hostForMeasurement(card, at: .large)
            let size = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
            XCTAssertLessThanOrEqual(size.width, 358.5, "\(label) width")
            XCTAssertLessThanOrEqual(size.height, 200, "\(label) height (\(size.height)pt) keeps chart above 852pt fold")

            let a11yHost = hostForMeasurement(card, at: .accessibility2)
            let a11ySize = a11yHost.sizeThatFits(in: CGSize(width: 358, height: 2000))
            XCTAssertLessThanOrEqual(a11ySize.width, 358.5, "\(label) accessibility2 width")
        }

        if let exportDir = ProcessInfo.processInfo.environment["BL_EXPORT_OVERNIGHT4_DIR"], !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            let sbHistory = try decodeHistory("""
            {
              "event_id": 9127041,
              "home_team": "Arsenal",
              "away_team": "Chelsea",
              "history": [
                { "timestamp": "2026-11-12T12:00:00Z", "home_probability": 0.48, "away_probability": 0.26, "source": "aggregate" },
                { "timestamp": "2026-11-13T06:00:00Z", "home_probability": 0.50, "away_probability": 0.25, "source": "aggregate" },
                { "timestamp": "2026-11-13T18:00:00Z", "home_probability": 0.51, "away_probability": 0.24, "source": "aggregate" },
                { "timestamp": "2026-11-14T07:58:00Z", "home_probability": 0.52, "away_probability": 0.23, "source": "aggregate" }
              ]
            }
            """)

            let saHistory = try decodeHistory("""
            {
              "event_id": 9127042,
              "home_team": "Monterrey",
              "away_team": "Querétaro",
              "history": [
                { "timestamp": "2026-11-10T18:30:00Z", "home_probability": 0.64, "away_probability": 0.15, "source": "aggregate" },
                { "timestamp": "2026-11-10T19:30:00Z", "home_probability": 0.72, "away_probability": 0.12, "source": "aggregate" },
                { "timestamp": "2026-11-10T20:15:00Z", "home_probability": 0.55, "away_probability": 0.20, "source": "aggregate" },
                { "timestamp": "2026-11-10T20:52:00Z", "home_probability": 0.94, "away_probability": 0.02, "source": "aggregate" }
              ]
            }
            """)

            let nhlHistory = try decodeHistory("""
            {
              "event_id": 9127043,
              "home_team": "Anaheim Ducks",
              "away_team": "Nashville Predators",
              "history": [
                { "timestamp": "2026-11-14T06:30:00Z", "home_probability": 0.54, "away_probability": 0.46, "source": "aggregate" },
                { "timestamp": "2026-11-14T07:00:00Z", "home_probability": 0.39, "away_probability": 0.61, "source": "aggregate" },
                { "timestamp": "2026-11-14T07:30:00Z", "home_probability": 0.57, "away_probability": 0.43, "source": "aggregate" },
                { "timestamp": "2026-11-14T07:59:45Z", "home_probability": 0.516, "away_probability": 0.484, "source": "aggregate" }
              ]
            }
            """)

            let sbVM = EventDetailViewModel(
                eventId: soccerBefore.id,
                client: StubEventDetailProvider(detail: soccerBefore, history: sbHistory)
            )
            await sbVM.load()
            sbVM.stopRefresh()

            let saVM = EventDetailViewModel(
                eventId: soccerAfter.id,
                client: StubEventDetailProvider(detail: soccerAfter, history: saHistory)
            )
            await saVM.load()
            saVM.stopRefresh()

            let nhlVM = EventDetailViewModel(
                eventId: nhlDuring.id,
                client: StubEventDetailProvider(detail: nhlDuring, history: nhlHistory)
            )
            await nhlVM.load()
            nhlVM.stopRefresh()

            func writeHostedPagePNG<V: View>(
                _ view: V,
                size: CGSize,
                at dt: DynamicTypeSize,
                to url: URL
            ) async throws {
                let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: dt)
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
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                try await Task.sleep(nanoseconds: 150_000_000)
                let until = Date().addingTimeInterval(0.25)
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

            let sbPage = NavigationStack {
                EventDetailView(eventId: soccerBefore.id)
                    .withLoadedEventForTest12278(soccerBefore, viewModel: sbVM)
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .frame(width: 390, height: 852)
            .background(Color(uiColor: .systemGroupedBackground))

            let saPage = NavigationStack {
                EventDetailView(eventId: soccerAfter.id)
                    .withLoadedEventForTest12278(soccerAfter, viewModel: saVM)
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .frame(width: 390, height: 852)
            .background(Color(uiColor: .systemGroupedBackground))

            let nhlPage = NavigationStack {
                EventDetailView(eventId: nhlDuring.id)
                    .withLoadedEventForTest12278(nhlDuring, viewModel: nhlVM)
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .frame(width: 390, height: 852)
            .background(Color(uiColor: .systemGroupedBackground))

            try await writeHostedPagePNG(
                sbPage,
                size: CGSize(width: 390, height: 852),
                at: .large,
                to: dirURL.appendingPathComponent("overnight4-soccer-before-390x852.png")
            )
            try await writeHostedPagePNG(
                saPage,
                size: CGSize(width: 390, height: 852),
                at: .large,
                to: dirURL.appendingPathComponent("overnight4-soccer-after-390x852.png")
            )
            try await writeHostedPagePNG(
                nhlPage,
                size: CGSize(width: 390, height: 852),
                at: .large,
                to: dirURL.appendingPathComponent("overnight4-nhl-during-390x852.png")
            )

            let comparisonSheet = VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Soccer Before · 3-Way + EKG + 90' Reg.")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    sbCard
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Soccer After · Graded 3-Way + 'Pregame' Header")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    saCard
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("NHL During · Score · Pregame · Now + Tenths")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    nhlCard
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let compHost = hostForMeasurement(comparisonSheet.environment(\.colorScheme, .light), at: .large)
            let compHeight = ceil(compHost.sizeThatFits(in: CGSize(width: 390, height: 2000)).height)
            try await writeHostedPagePNG(
                comparisonSheet,
                size: CGSize(width: 390, height: compHeight),
                at: .large,
                to: dirURL.appendingPathComponent("overnight4-amazing-headlines-comparison-390.png")
            )
        }
    }
}
