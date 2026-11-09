import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class EventAtlasEsportsCards11666Tests: XCTestCase {

    private let baseNow = ISO8601DateFormatter().date(from: "2026-11-09T12:00:00Z")!

    private func makeEvent(
        id: Int = 15322123,
        sport: String = "esports_csgo",
        status: String = "live",
        commenceTime: String = "2026-11-09T11:30:00Z",
        homeTeam: String = "Natus Vincere",
        awayTeam: String = "FaZe Clan",
        homeScore: Int? = 1,
        awayScore: Int? = 0
    ) -> EventDetail {
        EventDetail(
            id: id,
            externalId: "evt-esports-\(id)",
            sport: sport,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            commenceTime: commenceTime,
            startIsTbd: false,
            status: status,
            homeScore: homeScore,
            awayScore: awayScore,
            homeTeamData: nil,
            awayTeamData: nil,
            metadata: nil,
            standingsContext: nil,
            currentOdds: nil,
            openingOdds: nil,
            prematchOdds: nil,
            bookmakerOdds: nil,
            highlight: nil,
            espn: nil,
            winProbabilitySources: nil,
            ei: nil,
            pulse: nil,
            eventTags: nil,
            heroSettledResult: nil,
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: nil,
            boxScoreData: nil
        )
    }

    private func makeGameMarkets(
        eventId: Int = 15322123,
        observedAt: String = "2026-11-09T11:50:00Z",
        winnerSource: String = "polymarket",
        homeWinnerIsWinner: Bool? = nil,
        awayWinnerIsWinner: Bool? = nil,
        homeWinnerResolutionSource: String? = nil,
        awayWinnerResolutionSource: String? = nil,
        marginHandicapLabel: String = "Natus Vincere (-6.5)",
        marginMarketName: String = "Map 1 Rounds Handicap: Natus Vincere (-6.5) vs FaZe Clan (+6.5)",
        marginIsWinner: Bool? = nil,
        marginResolutionSource: String? = nil
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Natus Vincere",
            awayTeam: "FaZe Clan",
            status: "live",
            homeScore: 1,
            awayScore: 0,
            playerProps: [],
            spreads: [
                GameMarketOutcome(
                    _marketId: 63664403,
                    marketName: marginMarketName,
                    outcomeName: marginHandicapLabel,
                    probability: 0.62,
                    source: winnerSource,
                    threshold: -6.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: marginIsWinner,
                    resolutionSource: marginResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.54
                ),
                GameMarketOutcome(
                    _marketId: 63664403,
                    marketName: marginMarketName,
                    outcomeName: "FaZe Clan (+6.5)",
                    probability: 0.38,
                    source: winnerSource,
                    threshold: 6.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: nil,
                    resolutionSource: nil,
                    observedAt: observedAt,
                    pregameMark: 0.46
                )
            ],
            totals: [],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 63403921,
                    isWinner: homeWinnerIsWinner,
                    resolutionSource: homeWinnerResolutionSource,
                    marketName: "Counter-Strike: FaZe Clan vs Natus Vincere (BO1)",
                    outcomeName: "Natus Vincere",
                    probability: 0.798,
                    source: winnerSource,
                    observedAt: observedAt,
                    pregameMark: 0.765
                ),
                GameMarketOther(
                    _marketId: 63403921,
                    isWinner: awayWinnerIsWinner,
                    resolutionSource: awayWinnerResolutionSource,
                    marketName: "Counter-Strike: FaZe Clan vs Natus Vincere (BO1)",
                    outcomeName: "FaZe Clan",
                    probability: 0.215,
                    source: winnerSource,
                    observedAt: observedAt,
                    pregameMark: 0.220
                )
            ],
            pace: nil
        )
    }

    // MARK: - 1. Sport Gating & Title Kind

    func testAppliesGatesEsportsSportsOnAtlasFlag() {
        for key in ["esports", "esports_csgo", "esports_lol", "esports_dota2", "esports_valorant", "ESPORTS_CSGO"] {
            XCTAssertTrue(EventAtlasEsportsCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasEsportsCards11666.applies(sportKey: key, atlasEnabled: false), key)
        }
        for nonEsports in ["basketball_nba", "cricket_t20", "mma_mixed_martial_arts", "", nil] {
            XCTAssertFalse(EventAtlasEsportsCards11666.applies(sportKey: nonEsports, atlasEnabled: true))
        }
        let csgo = "esports_csgo"
        let lol = "esports_lol"
        let dota2 = "esports_dota2"
        let valorant = "esports_valorant"
        XCTAssertEqual(EventAtlasEsportsCards11666.resolveTitleKind(sportKey: csgo), .csgo)
        XCTAssertEqual(EventAtlasEsportsCards11666.resolveTitleKind(sportKey: lol), .lol)
        XCTAssertEqual(EventAtlasEsportsCards11666.resolveTitleKind(sportKey: dota2), .dota2)
        XCTAssertEqual(EventAtlasEsportsCards11666.resolveTitleKind(sportKey: valorant), .valorant)
    }

    // MARK: - 2. Winner Story Card Lifecycle & Unscaled Rings

    func testWinnerCardPregameInPlayAndFinalLifecycleWithUnscaledRings() throws {
        // 1. Before match
        let preEvent = makeEvent(status: "upcoming", commenceTime: "2026-11-09T14:00:00Z", homeScore: nil, awayScore: nil)
        let gm = makeGameMarkets()
        let preCards = EventAtlasEsportsCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        XCTAssertEqual(preCards.count, 2)
        guard case .winner(let preWinner) = preCards[0] else {
            return XCTFail("Expected winner card first")
        }
        let preModel = preWinner.toWinnerModel()
        XCTAssertEqual(preModel.sides.map { $0.side.name }, ["Natus Vincere", "FaZe Clan"])
        XCTAssertEqual(preModel.sides.compactMap { $0.ring }.reduce(0, +), 0.985, accuracy: 1e-9,
                       "Original pre-match chances (0.765 + 0.220) are never rescaled to 1.0")
        XCTAssertEqual(preModel.sides.map { $0.readings.count }, [1, 1])
        XCTAssertTrue(preModel.sides.allSatisfy { $0.report == nil && $0.settlement == nil })

        // 2. During match
        let liveEvent = makeEvent(status: "live", homeScore: 8, awayScore: 4)
        let liveCards = EventAtlasEsportsCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        guard case .winner(let liveWinner) = liveCards[0] else {
            return XCTFail("Expected winner card first")
        }
        let liveModel = liveWinner.toWinnerModel()
        XCTAssertEqual(
            liveModel.sides.map { $0.readings.map { $0.role } },
            [
                [EsportsStoryRole10868.before, .later],
                [EsportsStoryRole10868.before, .later]
            ]
        )
        XCTAssertEqual(liveModel.sides.map { $0.readings.last?.text }, ["80%", "22%"])
        XCTAssertTrue(liveModel.sides.allSatisfy { $0.report == nil && $0.settlement == nil })

        // 3. Final match: home unconfirmed (nil), away confirmed Lost (false + api_settlement)
        let finalEvent = makeEvent(status: "completed", homeScore: 13, awayScore: 1)
        let finalGM = makeGameMarkets(
            homeWinnerIsWinner: nil,
            awayWinnerIsWinner: false,
            awayWinnerResolutionSource: "api_settlement",
            marginIsWinner: true,
            marginResolutionSource: "api_settlement"
        )
        let finalCards = EventAtlasEsportsCards11666.buildCards(event: finalEvent, gameMarkets: finalGM, now: baseNow)
        guard case .winner(let finalWinner) = finalCards[0] else {
            return XCTFail("Expected winner card first")
        }
        let finalModel = finalWinner.toWinnerModel()
        XCTAssertEqual(
            finalModel.sides.map { $0.readings.map { $0.role } },
            [[EsportsStoryRole10868.before], [EsportsStoryRole10868.before]],
            "Final drops live quotes and keeps pre-match expectation only"
        )
        XCTAssertEqual(finalModel.sides.map { $0.report?.outcome }, ["Won match", "Lost match"])
        XCTAssertEqual(finalModel.sides.map { $0.report?.figure }, ["13", "1"])
        XCTAssertEqual(finalModel.sides.map { $0.report?.unit }, ["rounds", "round"])
        XCTAssertEqual(finalModel.sides[0].settlement?.text, "Result not confirmed",
                       "Unconfirmed contract never fabricates Won or Lost from scoreboard")
        XCTAssertEqual(finalModel.sides[0].settlement?.isValue, false)
        XCTAssertEqual(finalModel.sides[1].settlement?.text, "✗ Lost")
        XCTAssertEqual(finalModel.sides[1].settlement?.isValue, true)
    }

    // MARK: - 3. Margin Story Card Geometry & Blocks

    func testMarginCardGeometryThresholdsAndFinalActualBlocks() throws {
        let finalEvent = makeEvent(status: "completed", homeScore: 13, awayScore: 1)
        let finalGM = makeGameMarkets(
            marginHandicapLabel: "Natus Vincere (-6.5)",
            marginMarketName: "Map 1 Rounds Handicap: Natus Vincere (-6.5) vs FaZe Clan (+6.5)",
            marginIsWinner: true,
            marginResolutionSource: "api_settlement"
        )
        let cards = EventAtlasEsportsCards11666.buildCards(event: finalEvent, gameMarkets: finalGM, now: baseNow)
        guard cards.count == 2, case .margin(let marginRecord) = cards[1] else {
            return XCTFail("Expected margin card second")
        }
        let model = marginRecord.toMarginModel()
        XCTAssertEqual(model.blocks.count, 14)
        XCTAssertEqual(model.blocks.filter { $0.isFilled }.count, 12)
        XCTAssertEqual(model.blocks.filter { $0.meetsMinimum }.map { $0.index }, Array(7..<14))
        XCTAssertEqual(model.minimumFraction, 0.5)
        XCTAssertEqual(try XCTUnwrap(model.actualFraction), 12.0 / 14.0, accuracy: 1e-9)
        XCTAssertEqual(model.delta, "7 needed · 5 beyond the minimum")
        XCTAssertEqual(model.score, "Natus Vincere 13–1 FaZe Clan")
        XCTAssertEqual(model.result?.text, "✓ Won")
    }

    // MARK: - 4. 30-Minute Live Quote Aging

    func testCurrentAtAgesLiveQuotesAfter30MinutesAndLeavesFinalUnchanged() {
        let liveEvent = makeEvent(status: "live", homeScore: 6, awayScore: 5)
        let gm = makeGameMarkets(observedAt: "2026-11-09T11:50:00Z")
        let cards = EventAtlasEsportsCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        XCTAssertEqual(cards.count, 2)

        // Advance clock by 35 minutes (> 30 min max age)
        let laterNow = baseNow.addingTimeInterval(35 * 60)
        let agedDeck = cards.map { NFLEventCard9483.esports($0).current(at: laterNow) }

        guard case .esports(.winner(let agedWinner)) = agedDeck[0],
              case .esports(.margin(let agedMargin)) = agedDeck[1] else {
            return XCTFail("Expected aged esports cards")
        }
        let winnerModel = agedWinner.toWinnerModel()
        XCTAssertEqual(
            winnerModel.sides.map { $0.readings.last?.text },
            ["No recent probability", "No recent probability"]
        )
        XCTAssertEqual(
            winnerModel.sides.map { $0.readings.first?.text },
            ["77%", "22%"],
            "Pregame baseline remains intact when live quote ages out"
        )
        let marginModel = agedMargin.toMarginModel()
        XCTAssertEqual(marginModel.readings.last?.text, "No recent probability")

        // Final cards never expire
        let finalEvent = makeEvent(status: "completed", homeScore: 13, awayScore: 1)
        let finalCards = EventAtlasEsportsCards11666.buildCards(event: finalEvent, gameMarkets: gm, now: baseNow)
        let finalAfterHours = finalCards.map { $0.current(at: baseNow.addingTimeInterval(7200)) }
        XCTAssertEqual(finalCards, finalAfterHours)
    }

    // MARK: - 5. Venue-Free Narrative Copy Guard

    func testNarrativeCopyContainsNoVenueNamesAcrossAllKnownSources() {
        let forbiddenVenues = ["Kalshi", "Polymarket", "DraftKings", "FanDuel", "BetMGM", "Caesars", "Pinnacle"]
        for source in ["kalshi", "polymarket", "draftkings", "fanduel", "betmgm"] {
            let event = makeEvent(status: "completed", homeScore: 13, awayScore: 1)
            let gm = makeGameMarkets(winnerSource: source)
            let cards = EventAtlasEsportsCards11666.buildCards(event: event, gameMarkets: gm, now: baseNow)
            for card in cards {
                switch card {
                case .winner(let record):
                    let copy = record.toWinnerModel().copy
                    let narrative = [copy.title, copy.eyebrow, copy.explanation, copy.reportCaption, copy.graphicLabel]
                        .compactMap { $0 }
                        .joined(separator: " ")
                    for venue in forbiddenVenues {
                        XCTAssertFalse(narrative.localizedCaseInsensitiveContains(venue),
                                       "Found venue \(venue) in winner narrative: \(narrative)")
                    }
                case .margin(let record):
                    let copy = record.toMarginModel().copy
                    let narrative = [copy.title, copy.eyebrow, copy.graphicLabel, copy.blockMeaning, copy.delta, copy.score]
                        .compactMap { $0 }
                        .joined(separator: " ")
                    for venue in forbiddenVenues {
                        XCTAssertFalse(narrative.localizedCaseInsensitiveContains(venue),
                                       "Found venue \(venue) in margin narrative: \(narrative)")
                    }
                }
            }
        }
    }

    // MARK: - 6. 390 px Default & Accessibility3 Snapshots

    @MainActor
    func testRenderEsportsCards390pxDefaultAndAccessibility3Snapshots() throws {
        let finalEvent = makeEvent(status: "completed", homeScore: 13, awayScore: 1)
        let finalGM = makeGameMarkets(
            homeWinnerIsWinner: true,
            awayWinnerIsWinner: false,
            homeWinnerResolutionSource: "api_settlement",
            awayWinnerResolutionSource: "api_settlement",
            marginIsWinner: true,
            marginResolutionSource: "api_settlement"
        )
        let cards = EventAtlasEsportsCards11666.buildCards(event: finalEvent, gameMarkets: finalGM, now: baseNow)
        XCTAssertEqual(cards.count, 2)

        let stack = VStack(alignment: .leading, spacing: 16) {
            ForEach(cards) { card in
                EventAtlasEsportsCardView11666(card: card)
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(Color.systemBackground)
        .environment(\.colorScheme, .light)

        let defaultRenderer = rendererForMeasurement(stack)
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(defaultImage.size.height, 400)

        let a11yRenderer = rendererForMeasurement(stack, at: .accessibility3)
        a11yRenderer.scale = 1.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(a11yImage.size.height, defaultImage.size.height)

        let outDir = URL(fileURLWithPath: "/tmp/esports-cards-11666")
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        if let defaultPNG = defaultImage.pngData() {
            try? defaultPNG.write(to: outDir.appendingPathComponent("esports-story-cards-default-390px.png"))
        }
        if let a11yPNG = a11yImage.pngData() {
            try? a11yPNG.write(to: outDir.appendingPathComponent("esports-story-cards-a11y-390px.png"))
        }
    }
}
