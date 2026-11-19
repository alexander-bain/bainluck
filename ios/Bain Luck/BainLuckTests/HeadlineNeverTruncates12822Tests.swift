import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12822 — Alex's TestFlight 5757 Magic at Celtics report:
/// 1. Before kickoff (`phase == .before`), `Chance` prints whole percents (`23%` / `77%`)
///    on every surface, including inside the pre-game streaming window (`numberStreams == true`).
///    During play (`phase == .during`), `Now` keeps its tenths (`25.7%` / `74.3%`).
/// 2. No headline number or column header ever truncates with `"…"` — every cell fits the
///    longest value it can print at the narrowest phone width (`320 pt`, `375 pt`, `390 pt`)
///    and largest Dynamic Type size (`.large`, `.xxxLarge`, `.accessibility5`), shrinking
///    rather than showing `"…"`.
@MainActor
final class HeadlineNeverTruncates12822Tests: XCTestCase {

    private let fixedBeforeTip = ISO8601DateFormatter().date(from: "2026-11-16T23:59:00Z")!
    private let fixedLive = ISO8601DateFormatter().date(from: "2026-11-17T00:29:00Z")!
    private let pacific = TimeZone(identifier: "America/Los_Angeles")!

    private func decodeEventDetail(_ json: String) throws -> EventDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeWidgetEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(json.utf8)
        )
    }

    // MARK: - Live Magic at Celtics Fixtures (from production event 15349708)

    private func magicAtCelticsBeforeTipJSON() -> String {
        """
        {
          "id": 15349708,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "scheduled",
          "commence_time": "2026-11-17T00:00:00Z",
          "away_team": "Orlando Magic",
          "home_team": "Boston Celtics",
          "away_team_data": {
            "abbreviation": "ORL",
            "primary_color": "#0150b5",
            "secondary_color": "#9ca0a3",
            "record": "5-7"
          },
          "home_team_data": {
            "abbreviation": "BOS",
            "primary_color": "#008348",
            "secondary_color": "#ffffff",
            "record": "11-2"
          },
          "espn": {
            "broadcast": "NBCSN"
          },
          "pregame_projection": {
            "projected_home_score": 110.8,
            "projected_away_score": 102.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-17T00:00:00Z",
            "earliest_captured_at": "2026-11-16T23:40:57Z",
            "latest_captured_at": "2026-11-16T23:56:42Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 17,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.235,
            "home_probability": 0.765,
            "away_rendered_percent": 23,
            "home_rendered_percent": 77,
            "projected_away_score": 102.0,
            "projected_home_score": 110.8,
            "bookmaker_count": 17
          },
          "hero_probability_observed_at": "2026-11-16T23:58:50Z"
        }
        """
    }

    private func magicAtCelticsDuringJSON(
        awayScore: Int = 12,
        homeScore: Int = 12,
        projAway: Double = 96.3,
        projHome: Double = 104.4,
        awayProb: Double = 0.256678,
        homeProb: Double = 0.743322
    ) -> String {
        """
        {
          "id": 15349708,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "live",
          "commence_time": "2026-11-17T00:00:00Z",
          "away_team": "Orlando Magic",
          "home_team": "Boston Celtics",
          "away_score": \(awayScore),
          "home_score": \(homeScore),
          "away_team_data": {
            "abbreviation": "ORL",
            "primary_color": "#0150b5",
            "secondary_color": "#9ca0a3",
            "record": "5-7"
          },
          "home_team_data": {
            "abbreviation": "BOS",
            "primary_color": "#008348",
            "secondary_color": "#ffffff",
            "record": "11-2"
          },
          "espn": {
            "game_clock": "3:11",
            "period": "3:11 - 1st Quarter",
            "broadcast": "NBCSN"
          },
          "prematch_odds": {
            "away_probability": 0.235,
            "home_probability": 0.765,
            "away_rendered_percent": 23,
            "home_rendered_percent": 77
          },
          "pregame_projection": {
            "projected_home_score": 110.8,
            "projected_away_score": 102.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-17T00:00:00Z",
            "earliest_captured_at": "2026-11-16T23:40:57Z",
            "latest_captured_at": "2026-11-16T23:56:42Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 17,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": \(awayProb),
            "home_probability": \(homeProb),
            "away_rendered_percent": \(Int((awayProb * 100).rounded())),
            "home_rendered_percent": \(Int((homeProb * 100).rounded())),
            "live_projection": {
              "projected_away_score": \(projAway),
              "projected_home_score": \(projHome),
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-17T00:00:00Z",
              "earliest_confirmed_at": "2026-11-17T00:25:27Z",
              "latest_captured_at": "2026-11-17T00:28:27Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 20,
              "unit": "points",
              "period": "full_game"
            }
          },
          "hero_probability_observed_at": "2026-11-17T00:28:49Z"
        }
        """
    }

    // MARK: - 1. Before Kickoff Prints Whole Percents Across Every Surface; During Play Keeps Tenths

    func testBeforeKickoffPrintsWholePercentsOnEverySurfaceAndDuringKeepsTenths() throws {
        let json = magicAtCelticsBeforeTipJSON()
        let pageEvent = try decodeEventDetail(json)
        let feedEvent = try decodeFeedEvent(json)
        let widgetEvent = try decodeWidgetEvent(json)

        // Game page headline: whole percents both when non-streaming AND 1 minute before tip when streaming!
        for streaming in [false, true] {
            let model = EventSportHeadlines12472.resolve(
                event: pageEvent,
                awayFullName: pageEvent.awayTeam,
                homeFullName: pageEvent.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: streaming,
                now: fixedBeforeTip
            )
            XCTAssertEqual(model.kind, .nbaBeforeGame)
            XCTAssertEqual(model.plainMetaText, "NBA · In 1m · NBCSN")
            XCTAssertEqual(model.columns.map(\.header), ["Proj.", "Chance"])
            XCTAssertEqual(model.rows[0].cells, ["102", "23%"], "streaming=\(streaming)")
            XCTAssertEqual(model.rows[1].cells, ["111", "77%"], "streaming=\(streaming)")
            XCTAssertFalse(model.away.winChanceText.contains("."), "Before kickoff must never print tenths")
            XCTAssertFalse(model.home.winChanceText.contains("."), "Before kickoff must never print tenths")
        }

        // Discover card: whole percents before kickoff
        let discoverModel = DiscoverSingleGameCard190C.build(event: feedEvent, prematch: nil)
        XCTAssertEqual(discoverModel.rows[0].primaryCell, .probability("23%"))
        XCTAssertEqual(discoverModel.rows[1].primaryCell, .probability("77%"))

        // Widget: whole percents before kickoff
        let widgetModel = SavedGameHeadlineWidgetModel12616.build(
            reading: SavedWidgetReadingRules10875.game(widgetEvent, side: nil, now: fixedBeforeTip),
            art: SavedWidgetArt12466.game(widgetEvent),
            clockFooter: nil,
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedBeforeTip,
            timeZone: pacific
        )
        XCTAssertEqual(widgetModel.away.figure, "23%")
        XCTAssertEqual(widgetModel.home.figure, "77%")

        // Watch tile: whole percents before kickoff
        let watchModel = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Boston Celtics",
                awayTeam: "Orlando Magic",
                homeServedAbbreviation: "BOS",
                awayServedAbbreviation: "ORL",
                sportKey: "basketball_nba",
                homeProbability: 0.765,
                awayProbability: 0.235,
                projectedHomeScore: 110.8,
                projectedAwayScore: 102.0,
                homePrimaryColor: "#008348",
                awayPrimaryColor: "#0150b5",
                commenceTime: ISO8601DateFormatter().date(from: "2026-11-17T00:00:00Z")
            ),
            now: fixedBeforeTip,
            timeZone: pacific
        )
        XCTAssertEqual(watchModel.heroFigureText, "77%")

        // During play: Now keeps tenths (`25.7%` / `74.3%`)
        let livePageEvent = try decodeEventDetail(magicAtCelticsDuringJSON())
        let liveModel = EventSportHeadlines12472.resolve(
            event: livePageEvent,
            awayFullName: livePageEvent.awayTeam,
            homeFullName: livePageEvent.homeTeam,
            liveStatusText: "Q1 · 3:11",
            hasScore: true,
            numberStreams: true,
            now: fixedLive
        )
        XCTAssertEqual(liveModel.kind, .nbaDuringGame)
        XCTAssertEqual(liveModel.columns.map(\.header), ["Score", "Proj.", "Now"])
        XCTAssertEqual(liveModel.rows[0].cells, ["12", "96", "25.7%"])
        XCTAssertEqual(liveModel.rows[1].cells, ["12", "104", "74.3%"])
    }

    // MARK: - 2. Pixel-Read OCR Rig + Negative Control + Guard Against Any `"…"` Across Widths & Sizes

    private func renderAndReadLines<V: View>(
        _ view: V,
        outerWidth: CGFloat,
        at size: DynamicTypeSize
    ) throws -> (image: UIImage, lines: [String]) {
        let cardContent = view
            .frame(width: outerWidth, alignment: .leading)
            .padding(.vertical, 6)
            .background(Color.white)
            .environment(\.colorScheme, .light)

        let measureHost = hostForMeasurement(cardContent, at: size)
        measureHost.overrideUserInterfaceStyle = .light
        let windowWidth = max(outerWidth, 390)

        let containerView = cardContent
            .frame(width: windowWidth, alignment: .leading)
            .background(Color.white)
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(containerView, at: size)
        host.overrideUserInterfaceStyle = .light
        let initialH = min(max(measureHost.sizeThatFits(in: CGSize(width: outerWidth, height: 2_400)).height + 24, 140), 2_400)
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: windowWidth, height: initialH))
        window.frame = CGRect(x: 0, y: 0, width: windowWidth, height: initialH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.22)
        repeat {
            let measured = host.sizeThatFits(in: CGSize(width: windowWidth, height: 2_400)).height + 80
            let nextH = min(max(measured, initialH), 2_400)
            if abs(nextH - window.frame.height) > 0.5 {
                window.frame = CGRect(x: 0, y: 0, width: windowWidth, height: nextH)
                host.view.frame = window.bounds
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let safeAreaTop = host.view.safeAreaInsets.top
        let cropRect = CGRect(x: 0, y: safeAreaTop, width: outerWidth, height: max(host.view.bounds.height - safeAreaTop, 80))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(size: cropRect.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(
                in: CGRect(x: 0, y: -safeAreaTop, width: host.view.bounds.width, height: host.view.bounds.height),
                afterScreenUpdates: true
            )
        }

        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        req.minimumTextHeight = 0.0
        let reqFast = VNRecognizeTextRequest()
        reqFast.recognitionLevel = .fast
        reqFast.usesLanguageCorrection = false
        reqFast.minimumTextHeight = 0.0
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req, reqFast])
        let accurateLines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let fastLines = (reqFast.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        var seen = Set<String>()
        let lines = (accurateLines + fastLines).filter { seen.insert($0).inserted }
        return (image, lines)
    }

    private func containsEllipsis(_ line: String) -> Bool {
        line.contains("…") || line.contains("...")
    }

    private func makeHeadlineCard(_ model: EventSportHeadlines12472.Model, awayHex: String = "#0150b5", homeHex: String = "#008348") -> some View {
        let colors = TeamTextContrast.cardColors(awayHex: awayHex, homeHex: homeHex, awaySecondaryHex: nil)
        return EventSportHeadlineCard12472(
            model: model,
            colors: colors,
            ekgTracker: EkgTracker(eventId: model.eventId),
            liveUpdateStatus: .hidden,
            displayAsOf: fixedLive,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
    }

    /// Negative control: proves our OCR rig detects the exact pre-#12822 truncation (`"23.5…"` / missing `%`)
    /// when `"23.5%"` at 32pt `.black .rounded` is squeezed into the old fixed 80pt `.chance` frame with `minimumScaleFactor(0.75)`.
    func testNegativeControlOld80PtFixedChanceCellTruncatesTenthsAtXXXL() throws {
        let brokenOldCell = HStack {
            Spacer()
            Text("23.5%")
                .font(HeadlineStyleTable199.now(.page, scaledSize: 32))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
                .frame(width: 80, alignment: .trailing)
        }
        .padding(14)

        let (_, lines) = try renderAndReadLines(brokenOldCell, outerWidth: 358, at: .xxxLarge)
        let joined = lines.joined(separator: " ")
        let sawEllipsisOrLostPercent = lines.contains(where: containsEllipsis) || !joined.contains("23.5%")
        XCTAssertTrue(
            sawEllipsisOrLostPercent,
            "Negative control must fail to read '23.5%' whole on the old 80pt / 0.75 floor cell, got: \(lines)"
        )
    }

    /// Guard test required by Fable (#12822): every cell fits the longest value it can print
    /// at the narrowest width (`320 pt` phone -> `288 pt` card width, `375 pt`, `390 pt`) and
    /// largest text sizes (`.large`, `.xxxLarge`, `.accessibility5`), with ZERO `"…"` anywhere.
    func testNoHeadlineNumberEverTruncatesAtNarrowestWidthAndLargestTextSizes() throws {
        // 1. Magic @ Celtics before tip (`102` / `111`, `23%` / `77%`) & worst-case `148` / `100%`
        let beforeEvent = try decodeEventDetail(magicAtCelticsBeforeTipJSON())
        var worstBeforeModel = EventSportHeadlines12472.resolve(
            event: beforeEvent,
            awayFullName: beforeEvent.awayTeam,
            homeFullName: beforeEvent.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: true,
            now: fixedBeforeTip
        )
        worstBeforeModel.rows[0] = EventSportHeadlines12472.CompetitorRow(
            role: .away, fullName: "Orlando Magic", opponentFullName: "Boston Celtics",
            shortName: "Magic", logoURL: nil, record: "15-17",
            cells: ["148", "100%"], rawProbability: 1.0, won: nil, abbreviation: "ORL", opponentAbbreviation: "BOS"
        )
        worstBeforeModel.rows[1] = EventSportHeadlines12472.CompetitorRow(
            role: .home, fullName: "Boston Celtics", opponentFullName: "Orlando Magic",
            shortName: "Celtics", logoURL: nil, record: "28-4",
            cells: ["145", ">99%"], rawProbability: 0.996, won: nil, abbreviation: "BOS", opponentAbbreviation: "ORL"
        )

        // 2. Worst-case live NBA (`Score 148`, `Proj. 154`, `Now 99.5%` / `0.5%`)
        let liveEvent = try decodeEventDetail(
            magicAtCelticsDuringJSON(
                awayScore: 145,
                homeScore: 148,
                projAway: 151.0,
                projHome: 154.0,
                awayProb: 0.005,
                homeProb: 0.995
            )
        )
        let worstLiveModel = EventSportHeadlines12472.resolve(
            event: liveEvent,
            awayFullName: liveEvent.awayTeam,
            homeFullName: liveEvent.homeTeam,
            liveStatusText: "OT2 · 1:04",
            hasScore: true,
            numberStreams: true,
            now: fixedLive
        )
        XCTAssertEqual(worstLiveModel.rows[0].cells, ["145", "151", "0.5%"])
        XCTAssertEqual(worstLiveModel.rows[1].cells, ["148", "154", "99.5%"])

        // 3. Worst-case finished NBA (`Pregame 100%` / `>99%`, `Final 148 ✓` / `145`)
        let finalEvent = try decodeEventDetail("""
        {
          "id": 15349799,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "completed",
          "commence_time": "2026-11-16T00:00:00Z",
          "away_team": "Orlando Magic",
          "home_team": "Boston Celtics",
          "away_score": 145,
          "home_score": 148,
          "hero_settled_result": "home",
          "away_team_data": { "abbreviation": "ORL", "primary_color": "#0150b5" },
          "home_team_data": { "abbreviation": "BOS", "primary_color": "#008348" },
          "prematch_odds": { "away_probability": 0.004, "home_probability": 0.996 }
        }
        """)
        var worstFinalModel = EventSportHeadlines12472.resolve(
            event: finalEvent,
            awayFullName: finalEvent.awayTeam,
            homeFullName: finalEvent.homeTeam,
            liveStatusText: nil,
            hasScore: true,
            numberStreams: false,
            now: fixedLive
        )
        worstFinalModel.rows[0] = EventSportHeadlines12472.CompetitorRow(
            role: .away, fullName: "Orlando Magic", opponentFullName: "Boston Celtics",
            shortName: "Magic", logoURL: nil, record: nil,
            cells: ["100%", "145"], rawProbability: nil, won: false, abbreviation: "ORL", opponentAbbreviation: "BOS"
        )
        worstFinalModel.rows[1] = EventSportHeadlines12472.CompetitorRow(
            role: .home, fullName: "Boston Celtics", opponentFullName: "Orlando Magic",
            shortName: "Celtics", logoURL: nil, record: nil,
            cells: [">99%", "148"], rawProbability: nil, won: true, abbreviation: "BOS", opponentAbbreviation: "ORL"
        )

        // 4. Worst-case 5-set tiebreak live tennis (`7` columns: `S1..S5 · TB · Now`)
        let fiveSetTennisModel = EventSportHeadlines12472.Model(
            eventId: 15999001,
            sportKey: "tennis_atp_wimbledon",
            kind: .tennisDuringGame,
            plainMetaText: nil,
            commenceTime: "2026-11-17T00:00:00Z",
            startIsTbd: false,
            broadcast: nil,
            eventStatus: "live",
            liveBadgeText: "LIVE · SET 5",
            leagueLabel: "ATP",
            columns: [
                .init(role: .setScore(index: 0), header: "S1"),
                .init(role: .setScore(index: 1), header: "S2"),
                .init(role: .setScore(index: 2), header: "S3"),
                .init(role: .setScore(index: 3), header: "S4"),
                .init(role: .setScore(index: 4), header: "S5"),
                .init(role: .gamePoints, header: "TB"),
                .init(role: .now, header: "Now"),
            ],
            rows: [
                .init(
                    role: .away, fullName: "Carlos Alcaraz", opponentFullName: "Jannik Sinner",
                    shortName: "Alcaraz", logoURL: nil, record: nil,
                    cells: ["7", "6", "7", "6", "6", "11", "99.5%"],
                    rawProbability: 0.995, won: nil,
                    emphasizedColumns: [0, 2, 4],
                    cellSuperscripts: [0: "7", 1: "4", 2: "12", 3: "8"]
                ),
                .init(
                    role: .home, fullName: "Jannik Sinner", opponentFullName: "Carlos Alcaraz",
                    shortName: "Sinner", logoURL: nil, record: nil,
                    cells: ["6", "7", "6", "7", "6", "10", "0.5%"],
                    rawProbability: 0.005, won: nil,
                    emphasizedColumns: [1, 3, 4],
                    cellSuperscripts: [0: "5", 1: "7", 2: "10", 3: "10"]
                ),
            ],
            bottomBar: .twoWay(awayShare: 0.995, homeShare: 0.005, pregameAwayMarker: 0.52),
            pregameColumnHeaders: nil,
            liveColumnHeaders: .init(score: "S1", pregame: nil, now: "Now"),
            finalColumnHeaders: nil,
            away: .init(fullName: "Carlos Alcaraz", opponentFullName: "Jannik Sinner", shortName: "Alcaraz", logoURL: nil, record: nil, projectedText: nil, pregameProjectedNumberText: nil, liveScore: nil, pregameChanceText: nil, winChanceText: "99.5%", rawProbability: 0.995),
            home: .init(fullName: "Jannik Sinner", opponentFullName: "Carlos Alcaraz", shortName: "Sinner", logoURL: nil, record: nil, projectedText: nil, pregameProjectedNumberText: nil, liveScore: nil, pregameChanceText: nil, winChanceText: "0.5%", rawProbability: 0.005),
            pregameAwayMarker: 0.52,
            livePregameSummary: .init(leadWord: "Pregame", bodyText: "Alcaraz 52%"),
            showsEkg: false,
            sourceMark: nil,
            confidenceTier: nil
        )

        let specimens: [(String, EventSportHeadlines12472.Model, [String])] = [
            ("before-worst", worstBeforeModel, ["148", "100%", "145"]),
            ("live-worst", worstLiveModel, ["145", "151", "0.5%", "148", "154", "99.5%"]),
            ("final-worst", worstFinalModel, ["100%", "145", "148"]),
            ("tennis-5set", fiveSetTennisModel, ["99.5%", "0.5%"]),
        ]

        // Card outer widths: 320pt narrowest screen (320 - 32 = 288pt), 375pt (343pt), 390pt (358pt)
        let widths: [(CGFloat, String)] = [(288, "320w"), (343, "375w"), (358, "390w")]
        let sizes: [(DynamicTypeSize, String)] = [
            (.large, "large"),
            (.xxxLarge, "xxxl"),
            (.accessibility5, "ax5"),
        ]

        for (specName, model, requiredTokens) in specimens {
            for (outerW, wLabel) in widths {
                for (dtSize, sLabel) in sizes {
                    let (_, lines) = try renderAndReadLines(makeHeadlineCard(model), outerWidth: outerW, at: dtSize)
                    let joined = lines.joined(separator: " ")
                    XCTAssertFalse(
                        lines.contains(where: containsEllipsis),
                        "\(specName) @ \(wLabel)/\(sLabel) must NEVER render '…', got: \(lines)"
                    )
                    for token in requiredTokens {
                        XCTAssertTrue(
                            joined.contains(token),
                            "\(specName) @ \(wLabel)/\(sLabel) must read '\(token)' whole, got: \(lines)"
                        )
                    }
                }
            }
        }

        // Also verify Sports feed card (EventCardView) on Magic @ Celtics before tip & 148-145 final at 390w & xxxLarge
        let pinManager = PinManager()
        let authManager = AuthManager()
        let navCoordinator = NavigationCoordinator()
        let feedBefore = try decodeFeedEvent(magicAtCelticsBeforeTipJSON())
        let feedCardBefore = EventCardView(event: feedBefore, reason: nil)
            .padding(.horizontal, 14)
            .environmentObject(pinManager)
            .environmentObject(authManager)
            .environmentObject(navCoordinator)
        let (_, cardLines) = try renderAndReadLines(feedCardBefore, outerWidth: 358, at: .xxxLarge)
        XCTAssertFalse(cardLines.contains(where: containsEllipsis), "EventCardView before @ xxxLarge: \(cardLines)")
        XCTAssertTrue(cardLines.joined(separator: " ").contains("23%"), "EventCardView whole 23%: \(cardLines)")
        XCTAssertTrue(cardLines.joined(separator: " ").contains("77%"), "EventCardView whole 77%: \(cardLines)")
    }

    // MARK: - 2B. Alex's Build-5760 Live Q4 3:16 Specimen (Magic 106 / Celtics 99, Proj. 112 / 108, Now 90.3% / 9.7%)

    func testMagicAtCelticsQ4_106_99_Proj112_108_Now90_3_NeverTruncatesHeadersOrScores() throws {
        let q4JSON = magicAtCelticsDuringJSON(
            awayScore: 106,
            homeScore: 99,
            projAway: 112.0,
            projHome: 108.0,
            awayProb: 0.903,
            homeProb: 0.097
        ).replacingOccurrences(of: "\"period\": \"3:11 - 1st Quarter\"", with: "\"period\": \"3:16 - 4th Quarter\"")
         .replacingOccurrences(of: "\"game_clock\": \"3:11\"", with: "\"game_clock\": \"3:16\"")

        let q4PageEvent = try decodeEventDetail(q4JSON)
        let q4Model = EventSportHeadlines12472.resolve(
            event: q4PageEvent,
            awayFullName: q4PageEvent.awayTeam,
            homeFullName: q4PageEvent.homeTeam,
            liveStatusText: "Q4 · 3:16",
            hasScore: true,
            numberStreams: true,
            now: fixedLive
        )
        XCTAssertEqual(q4Model.columns.map(\.header), ["Score", "Proj.", "Now"])
        XCTAssertEqual(q4Model.rows[0].cells, ["106", "112", "90.3%"])
        XCTAssertEqual(q4Model.rows[1].cells, ["99", "108", "9.7%"])

        // Screen widths -> card outer widths (screen - 32pt page horizontal padding):
        // 320pt (288), 375pt (343), 390pt (358), 393pt iPhone 16/17 (361), 402pt iPhone19,3 Pro (370)
        let phoneOuterWidths: [(CGFloat, String)] = [
            (288, "320w"),
            (343, "375w"),
            (358, "390w"),
            (361, "393w"),
            (370, "402w-iPhone19,3"),
        ]
        let typeSizes: [(DynamicTypeSize, String)] = [
            (.large, "large"),
            (.xLarge, "xl"),
            (.xxLarge, "xxl"),
            (.xxxLarge, "xxxl"),
            (.accessibility1, "ax1"),
            (.accessibility3, "ax3"),
            (.accessibility5, "ax5"),
        ]

        for (outerW, wLabel) in phoneOuterWidths {
            for (dtSize, sLabel) in typeSizes {
                let (_, lines) = try renderAndReadLines(makeHeadlineCard(q4Model), outerWidth: outerW, at: dtSize)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(
                    lines.contains(where: containsEllipsis),
                    "Q4 106-99 headline @ \(wLabel)/\(sLabel) must NEVER render '…' (headers included), got: \(lines)"
                )
                for token in ["Score", "106", "112", "90.3%", "99", "108", "9.7%"] {
                    XCTAssertTrue(
                        joined.contains(token),
                        "Q4 106-99 headline @ \(wLabel)/\(sLabel) must read '\(token)' whole, got: \(lines)"
                    )
                }
            }
        }

        // Also verify Sports feed card (EventCardView) and Discover card (DiscoverCompactSingleGameCard190C)
        // on the exact same Q4 106-99 state at .large, .xxLarge, and .xxxLarge on 390w and 402w (iPhone19,3).
        let pinManager = PinManager()
        let authManager = AuthManager()
        let navCoordinator = NavigationCoordinator()
        let q4FeedEvent = try decodeFeedEvent(q4JSON)
        let q4FeedCard = EventCardView(event: q4FeedEvent, reason: nil)
            .padding(.horizontal, 14)
            .environmentObject(pinManager)
            .environmentObject(authManager)
            .environmentObject(navCoordinator)
        let q4DiscoverCard = DiscoverCompactSingleGameCard190CView(
            event: q4FeedEvent,
            prematch: nil,
            awayColor: Color(hex: "#0150B5"),
            homeColor: Color(hex: "#008348")
        ) {
            EmptyView()
        } footerRow: {
            EmptyView()
        }

        for (outerW, wLabel) in [(358 as CGFloat, "390w"), (370 as CGFloat, "402w-iPhone19,3")] {
            for (dtSize, sLabel) in [(.large as DynamicTypeSize, "large"), (.xxLarge, "xxl"), (.xxxLarge, "xxxl")] {
                let showsInlineProj = CompactGameCard12616.liveInlinePregameFits(
                    awayShortName: "Magic",
                    homeShortName: "Celtics",
                    typeSize: dtSize
                )
                let expectedTokens = showsInlineProj
                    ? ["Score", "106", "112", "90.3%", "99", "108", "9.7%"]
                    : ["Score", "106", "90.3%", "99", "9.7%"]

                let (_, feedLines) = try renderAndReadLines(q4FeedCard, outerWidth: outerW, at: dtSize)
                let feedJoined = feedLines.joined(separator: " ")
                XCTAssertFalse(feedLines.contains(where: containsEllipsis), "EventCardView Q4 @ \(wLabel)/\(sLabel): \(feedLines)")
                for token in expectedTokens {
                    XCTAssertTrue(feedJoined.contains(token), "EventCardView Q4 @ \(wLabel)/\(sLabel) missing \(token): \(feedLines)")
                }

                let (_, discLines) = try renderAndReadLines(q4DiscoverCard, outerWidth: outerW, at: dtSize)
                let discJoined = discLines.joined(separator: " ")
                XCTAssertFalse(discLines.contains(where: containsEllipsis), "DiscoverCard Q4 @ \(wLabel)/\(sLabel): \(discLines)")
                for token in expectedTokens {
                    XCTAssertTrue(discJoined.contains(token), "DiscoverCard Q4 @ \(wLabel)/\(sLabel) missing \(token): \(discLines)")
                }
            }
        }

        // Export dedicated 390 px sheet of the exact Magic 106 / Celtics 99 Q4 3:16 state
        let imgPageDefault = try renderAndReadLines(makeHeadlineCard(q4Model), outerWidth: 358, at: .large).image
        let imgPageXXL = try renderAndReadLines(makeHeadlineCard(q4Model), outerWidth: 358, at: .xxLarge).image
        let imgPageXXXL = try renderAndReadLines(makeHeadlineCard(q4Model), outerWidth: 358, at: .xxxLarge).image
        let imgFeedXXXL = try renderAndReadLines(q4FeedCard, outerWidth: 358, at: .xxxLarge).image
        let imgDiscoverXXXL = try renderAndReadLines(q4DiscoverCard, outerWidth: 358, at: .xxxLarge).image

        func label(_ text: String) -> some View {
            Text(text)
                .font(.system(size: 11.5, weight: .bold))
                .foregroundStyle(Color(hex: "#475569"))
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }

        let q4Sheet = VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Magic 106 @ Celtics 99 (Q4 · 3:16) — Proj. 112/108 · Now 90.3%/9.7%")
                    .font(.system(size: 13.5, weight: .bold))
                    .foregroundStyle(Color(hex: "#0F172A"))
                Text("Build 5761 / 5763 (#12837) · Zero '…' on Score header, 106, Proj. 112/108, or Now 90.3%/9.7% (390 px)")
                    .font(.system(size: 10.5, weight: .medium))
                    .foregroundStyle(Color(hex: "#64748B"))
            }

            label("1. Game Page Headline — Default Text (.large)")
            Image(uiImage: imgPageDefault).resizable().aspectRatio(contentMode: .fit).frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            label("2. Game Page Headline — Larger Text (.xxLarge)")
            Image(uiImage: imgPageXXL).resizable().aspectRatio(contentMode: .fit).frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            label("3. Game Page Headline — Largest Non-AX Text (.xxxLarge)")
            Image(uiImage: imgPageXXXL).resizable().aspectRatio(contentMode: .fit).frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            label("4. Sports / My Stuff Feed Card (EventCardView) — .xxxLarge")
            Image(uiImage: imgFeedXXXL).resizable().aspectRatio(contentMode: .fit).frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            label("5. Discover Single-Game Card — .xxxLarge")
            Image(uiImage: imgDiscoverXXXL).resizable().aspectRatio(contentMode: .fit).frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(UIColor.systemGroupedBackground))
        .environment(\.colorScheme, .light)

        let host = hostForMeasurement(q4Sheet, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = min(max(host.sizeThatFits(in: CGSize(width: 390, height: 2_600)).height + 80, 400), 2_600)
        let targetFrame = CGRect(x: 0, y: 0, width: 390, height: fitting)
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: targetFrame)
        window.frame = targetFrame
        host.view.frame = targetFrame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.30)
        repeat {
            let nextH = min(max(host.sizeThatFits(in: CGSize(width: 390, height: 2_600)).height + 80, 400), 2_600)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: 390, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let topInset = host.view.safeAreaInsets.top
        let croppedSize = CGSize(width: 390, height: max(host.view.bounds.height - topInset, 300))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        let q4Image = UIGraphicsImageRenderer(size: croppedSize, format: fmt).image { _ in
            _ = host.view.drawHierarchy(
                in: CGRect(x: 0, y: -topInset, width: 390, height: host.view.bounds.height),
                afterScreenUpdates: true
            )
        }

        try attachPNG(q4Image, named: "12837-magic-celtics-q4-106-99-390")
    }

    // MARK: - 3. Export 390 px Render Sheet for Fable

    func testExportMagicCelticsHeadlineNoTruncationSheet390() throws {
        let beforeEvent = try decodeEventDetail(magicAtCelticsBeforeTipJSON())
        let beforeModel = EventSportHeadlines12472.resolve(
            event: beforeEvent,
            awayFullName: beforeEvent.awayTeam,
            homeFullName: beforeEvent.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: true,
            now: fixedBeforeTip
        )

        let liveEvent = try decodeEventDetail(magicAtCelticsDuringJSON())
        let liveModel = EventSportHeadlines12472.resolve(
            event: liveEvent,
            awayFullName: liveEvent.awayTeam,
            homeFullName: liveEvent.homeTeam,
            liveStatusText: "Q1 · 3:11",
            hasScore: true,
            numberStreams: true,
            now: fixedLive
        )

        let highScoreLiveEvent = try decodeEventDetail(
            magicAtCelticsDuringJSON(
                awayScore: 145,
                homeScore: 148,
                projAway: 151.0,
                projHome: 154.0,
                awayProb: 0.005,
                homeProb: 0.995
            )
        )
        let highScoreLiveModel = EventSportHeadlines12472.resolve(
            event: highScoreLiveEvent,
            awayFullName: highScoreLiveEvent.awayTeam,
            homeFullName: highScoreLiveEvent.homeTeam,
            liveStatusText: "OT2 · 1:04",
            hasScore: true,
            numberStreams: true,
            now: fixedLive
        )

        func sectionLabel(_ text: String) -> some View {
            Text(text)
                .font(.system(size: 11.5, weight: .bold))
                .foregroundStyle(Color(hex: "#475569"))
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }

        let imgBeforeLarge = try renderAndReadLines(makeHeadlineCard(beforeModel), outerWidth: 358, at: .large).image
        let imgBeforeXXXL = try renderAndReadLines(makeHeadlineCard(beforeModel), outerWidth: 358, at: .xxxLarge).image
        let imgLiveXXXL = try renderAndReadLines(makeHeadlineCard(liveModel), outerWidth: 358, at: .xxxLarge).image
        let imgHighScoreXXXL = try renderAndReadLines(makeHeadlineCard(highScoreLiveModel), outerWidth: 358, at: .xxxLarge).image
        let imgNarrow320XXXL = try renderAndReadLines(makeHeadlineCard(liveModel), outerWidth: 288, at: .xxxLarge).image

        let sheet = VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("#12822 — Whole Percents Before Tip & Zero-Truncation Headline Cells")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(Color(hex: "#0F172A"))
                Text("Magic at Celtics (15349708) · 390 px · Default (.large), Larger Text (.xxxLarge), and 320 pt narrow")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Color(hex: "#64748B"))
            }

            sectionLabel("1. Magic at Celtics — 1m Before Tip (Streaming ON · Default .large → Whole 23% / 77%)")
            Image(uiImage: imgBeforeLarge)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionLabel("2. Magic at Celtics — 1m Before Tip (Streaming ON · Larger Text .xxxLarge, Alex's setting)")
            Image(uiImage: imgBeforeXXXL)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionLabel("3. Magic at Celtics — Live Q1 3:11 (Now keeps tenths 25.7% / 74.3% · Larger Text .xxxLarge)")
            Image(uiImage: imgLiveXXXL)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionLabel("4. Worst-Case Live 3-Digit Scores + 99.5% Tenths (.xxxLarge, zero '…')")
            Image(uiImage: imgHighScoreXXXL)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 358)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionLabel("5. Narrowest 320 pt Screen Width (288 pt card) · Live Magic at Celtics (.xxxLarge)")
            Image(uiImage: imgNarrow320XXXL)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 288)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(UIColor.systemGroupedBackground))
        .environment(\.colorScheme, .light)

        let host = hostForMeasurement(sheet, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = min(max(host.sizeThatFits(in: CGSize(width: 390, height: 2_600)).height + 80, 400), 2_600)
        let targetFrame = CGRect(x: 0, y: 0, width: 390, height: fitting)
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: targetFrame)
        window.frame = targetFrame
        host.view.frame = targetFrame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.30)
        repeat {
            let nextH = min(max(host.sizeThatFits(in: CGSize(width: 390, height: 2_600)).height + 80, 400), 2_600)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: 390, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let topInset = host.view.safeAreaInsets.top
        let croppedSize = CGSize(width: 390, height: max(host.view.bounds.height - topInset, 300))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(size: croppedSize, format: fmt).image { _ in
            _ = host.view.drawHierarchy(
                in: CGRect(x: 0, y: -topInset, width: 390, height: host.view.bounds.height),
                afterScreenUpdates: true
            )
        }

        try attachPNG(image, named: "12822-headline-no-truncation-390")
    }

    private func attachPNG(_ image: UIImage, named name: String) throws {
        let png = try XCTUnwrap(image.pngData())
        XCTAssertFalse(png.isEmpty)
        let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
