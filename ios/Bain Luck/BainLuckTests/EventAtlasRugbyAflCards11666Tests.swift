import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class EventAtlasRugbyAflCards11666Tests: XCTestCase {

    private let baseNow = ISO8601DateFormatter().date(from: "2026-11-09T12:00:00Z")!

    private func makeEvent(
        id: Int = 15400101,
        sport: String = "rugby_union",
        status: String = "live",
        commenceTime: String = "2026-11-09T11:30:00Z",
        homeTeam: String = "France",
        awayTeam: String = "England",
        homeScore: Int? = 24,
        awayScore: Int? = 21
    ) -> EventDetail {
        EventDetail(
            id: id,
            externalId: "evt-rugby-afl-\(id)",
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

    private func makeRugbyGameMarkets(
        eventId: Int = 15400101,
        observedAt: String = "2026-11-09T11:50:00Z",
        source: String = "polymarket",
        homeIsWinner: Bool? = nil,
        awayIsWinner: Bool? = nil,
        drawIsWinner: Bool? = nil,
        homeResolutionSource: String? = nil,
        awayResolutionSource: String? = nil,
        drawResolutionSource: String? = nil,
        spreadIsWinner: Bool? = nil,
        spreadResolutionSource: String? = nil
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "France",
            awayTeam: "England",
            status: "live",
            homeScore: 24,
            awayScore: 21,
            playerProps: [],
            spreads: [
                GameMarketOutcome(
                    _marketId: 770011,
                    marketName: "Point Handicap: France (-6.5) vs England (+6.5)",
                    outcomeName: "France -6.5",
                    probability: 0.44,
                    source: source,
                    threshold: -6.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: spreadIsWinner,
                    resolutionSource: spreadResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.52
                ),
                GameMarketOutcome(
                    _marketId: 770011,
                    marketName: "Point Handicap: France (-6.5) vs England (+6.5)",
                    outcomeName: "England +6.5",
                    probability: 0.56,
                    source: source,
                    threshold: 6.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: spreadIsWinner.map { !$0 },
                    resolutionSource: spreadResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.48
                )
            ],
            totals: [
                GameMarketOutcome(
                    _marketId: 770012,
                    marketName: "Total Match Points Over/Under 46.5",
                    outcomeName: "Over 46.5",
                    probability: 0.63,
                    source: source,
                    threshold: 46.5,
                    overProbability: 0.63,
                    marketType: "totals",
                    movement: nil,
                    period: nil,
                    isWinner: spreadIsWinner,
                    resolutionSource: spreadResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.51
                )
            ],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 770010,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    marketName: "Six Nations: France vs England Match Result",
                    outcomeName: "France",
                    probability: 0.64,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.81
                ),
                GameMarketOther(
                    _marketId: 770010,
                    isWinner: awayIsWinner,
                    resolutionSource: awayResolutionSource,
                    marketName: "Six Nations: France vs England Match Result",
                    outcomeName: "England",
                    probability: 0.33,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.16
                ),
                GameMarketOther(
                    _marketId: 770010,
                    isWinner: drawIsWinner,
                    resolutionSource: drawResolutionSource,
                    marketName: "Six Nations: France vs England Match Result",
                    outcomeName: "Draw",
                    probability: 0.05,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.03
                )
            ],
            pace: nil
        )
    }

    private func makeAflGameMarkets(
        eventId: Int = 15400202,
        observedAt: String = "2026-11-09T11:50:00Z",
        source: String = "kalshi",
        homeIsWinner: Bool? = true,
        awayIsWinner: Bool? = false,
        homeResolutionSource: String? = "api_settlement",
        awayResolutionSource: String? = "api_settlement"
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Brisbane Lions",
            awayTeam: "Collingwood Magpies",
            status: "completed",
            homeScore: 98,
            awayScore: 86,
            playerProps: [],
            spreads: [
                GameMarketOutcome(
                    _marketId: 880021,
                    marketName: "AFL Line: Brisbane Lions (-11.5) vs Collingwood (+11.5)",
                    outcomeName: "Brisbane Lions -11.5",
                    probability: 0.58,
                    source: source,
                    threshold: -11.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.52
                )
            ],
            totals: [],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 880020,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    marketName: "AFL Premiership: Brisbane Lions vs Collingwood Magpies",
                    outcomeName: "Brisbane Lions",
                    probability: 0.34,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.62
                ),
                GameMarketOther(
                    _marketId: 880020,
                    isWinner: awayIsWinner,
                    resolutionSource: awayResolutionSource,
                    marketName: "AFL Premiership: Brisbane Lions vs Collingwood Magpies",
                    outcomeName: "Collingwood Magpies",
                    probability: 0.66,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.38
                )
            ],
            pace: nil
        )
    }

    // MARK: - 1. Sport Gating

    func testAppliesGatesRugbyAndAflSportsOnAtlasFlag() {
        let rugbyKeys = ["rugby", "rugby_union", "rugby_league", "rugby_sevens", "RUGBY_UNION"]
        for key in rugbyKeys {
            XCTAssertTrue(EventAtlasRugbyAflCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasRugbyAflCards11666.applies(sportKey: key, atlasEnabled: false), key)
            XCTAssertEqual(EventAtlasRugbyAflCards11666.sportKind(sportKey: key), .rugby)
        }

        let aflKeys = ["afl", "aflw", "aussierules", "aussierules_afl", "aussierules_aflw", "AUSSIERULES_AFL"]
        for key in aflKeys {
            XCTAssertTrue(EventAtlasRugbyAflCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasRugbyAflCards11666.applies(sportKey: key, atlasEnabled: false), key)
            XCTAssertEqual(EventAtlasRugbyAflCards11666.sportKind(sportKey: key), .afl)
        }

        for other in ["basketball_nba", "esports_csgo", "cricket_t20", "soccer_epl", "", nil] {
            XCTAssertFalse(EventAtlasRugbyAflCards11666.applies(sportKey: other, atlasEnabled: true))
        }
    }

    // MARK: - 2. Decide 10-C Lifecycle (.before, .during, .final), Decide 80-A Grades & 3-Way Unscaled Probabilities

    func testRugbyLifecycleObeysDecide10CAndDecide80APreservingThreeWayUnscaledProbabilities() throws {
        let gm = makeRugbyGameMarkets()

        // 1. Before match (.before): shows ONLY live probability (0.64 / 0.33 / 0.05 -> 64% / 33% / 5%)
        //    labelled "Current chance", never pregameMark (0.81 / 0.16 / 0.03)
        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z",
            homeScore: nil,
            awayScore: nil
        )
        let preCards = EventAtlasRugbyAflCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        XCTAssertEqual(preCards.count, 3, "Before match builds Match Outlook + Handicap + Total Points")
        guard case .matchOutlook(let preOutlook) = preCards[0] else {
            return XCTFail("Expected matchOutlook first")
        }
        let preHeadlineModel = FieldHeadlineModel10868(preOutlook.headlineInput)
        XCTAssertEqual(preHeadlineModel.competitors.map { $0.slot.name }, ["France", "England", "Draw"])
        XCTAssertEqual(
            preHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["64%"], ["33%"], ["5%"]],
            "Decide 10-C: before start shows live quote (64%/33%/5%), never pregameMark (81%/16%/3%)"
        )
        XCTAssertEqual(
            preHeadlineModel.competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
            [["Current chance"], ["Current chance"], ["Current chance"]]
        )
        let rawBarSum = try XCTUnwrap(preOutlook.outlookInput).chances.compactMap(\.probability).reduce(0, +)
        XCTAssertEqual(rawBarSum, 1.02, accuracy: 1e-9, "3-way raw chances (0.64 + 0.33 + 0.05 = 1.02) are never rescaled to 1.0")

        // 2. During match (.during): shows pregameMark ("Pre-match chance" 81%/16%/3%) beside live ("Live chance" 64%/33%/5%)
        let liveEvent = makeEvent(status: "live", homeScore: 24, awayScore: 21)
        let liveCards = EventAtlasRugbyAflCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        guard case .matchOutlook(let liveOutlook) = liveCards[0] else {
            return XCTFail("Expected matchOutlook first")
        }
        let liveHeadlineModel = FieldHeadlineModel10868(liveOutlook.headlineInput)
        XCTAssertEqual(
            liveHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["81%", "64%"], ["16%", "33%"], ["3%", "5%"]]
        )

        // 3. Final match (.final) with Decide 80-A:
        //    - Authoritative win (api_settlement, isWinner: true) prints "✓ Won"
        //    - Non-winning row (isWinner: false) never mints "✗ Lost"; prints "Result not confirmed"
        //    - Unsettled row (isWinner: nil) prints "Result not confirmed"
        let finalEvent = makeEvent(status: "completed", homeScore: 48, awayScore: 46)
        let finalGM = makeRugbyGameMarkets(
            homeIsWinner: true,
            awayIsWinner: false,
            drawIsWinner: nil,
            homeResolutionSource: "api_settlement",
            awayResolutionSource: "api_settlement",
            drawResolutionSource: nil,
            spreadIsWinner: false,
            spreadResolutionSource: "api_settlement"
        )
        let finalCards = EventAtlasRugbyAflCards11666.buildCards(event: finalEvent, gameMarkets: finalGM, now: baseNow)
        XCTAssertEqual(finalCards.count, 3, "Final match mounts Match Outlook + Handicap + Total")
        guard case .matchOutlook(let finalOutlook) = finalCards[0] else {
            return XCTFail("Expected matchOutlook")
        }
        let finalHeadlineModel = FieldHeadlineModel10868(finalOutlook.headlineInput)
        XCTAssertEqual(
            finalHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["81%", "✓ Won"], ["16%"], ["3%"]],
            "Decide 80-A: only authoritative win becomes '✓ Won'; row grades never mint '✗ Lost'"
        )
        XCTAssertEqual(
            FieldChaseModel10868.words(finalHeadlineModel.competitors[1].metrics.last!),
            "Result not confirmed"
        )
        XCTAssertEqual(
            FieldChaseModel10868.words(finalHeadlineModel.competitors[2].metrics.last!),
            "Result not confirmed"
        )
    }

    // MARK: - 3. Decide 80-A Non-Authoritative Resolution Sources & Missing Market ID Guard

    func testDecide80ARejectsNonAuthoritativeResolutionSourcesAndDropsMissingMarketIDs() throws {
        let finalEvent = makeEvent(status: "completed", homeScore: 24, awayScore: 21)

        // Price guesses (binary_higher_wins, multi_max_prob), soft closes (clean_resolution),
        // and score reads (game_score, box_score) must never become .won or .lost under Decide 80-A.
        for nonAuthSource in ["binary_higher_wins", "multi_max_prob", "clean_resolution", "game_score", "box_score"] {
            let gm = makeRugbyGameMarkets(
                homeIsWinner: true,
                awayIsWinner: false,
                drawIsWinner: false,
                homeResolutionSource: nonAuthSource,
                awayResolutionSource: nonAuthSource,
                drawResolutionSource: nonAuthSource,
                spreadIsWinner: true,
                spreadResolutionSource: nonAuthSource
            )
            let cards = EventAtlasRugbyAflCards11666.buildCards(event: finalEvent, gameMarkets: gm, now: baseNow)
            guard case .matchOutlook(let outlook) = cards.first else {
                return XCTFail("Expected matchOutlook for \(nonAuthSource)")
            }
            let model = FieldHeadlineModel10868(outlook.headlineInput)
            for comp in model.competitors {
                let lastMetric = try XCTUnwrap(comp.metrics.last)
                XCTAssertNil(FieldChaseModel10868.figure(lastMetric), "Must not print '✓ Won' or '✗ Lost' for \(nonAuthSource)")
                XCTAssertEqual(FieldChaseModel10868.words(lastMetric), "Result not confirmed")
            }
        }

        // Rows without _marketId or _marketIds are dropped instead of inventing fallback IDs.
        var missingIDMarkets = makeRugbyGameMarkets()
        missingIDMarkets.other = [
            GameMarketOther(
                _marketId: nil,
                _marketIds: nil,
                isWinner: true,
                resolutionSource: "api_settlement",
                marketName: "Six Nations: France vs England Match Result",
                outcomeName: "France",
                probability: 0.64,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.81
            )
        ]
        missingIDMarkets.spreads = [
            GameMarketOutcome(
                _marketId: nil,
                _marketIds: nil,
                marketName: "Point Handicap",
                outcomeName: "France -6.5",
                probability: 0.44,
                source: "polymarket",
                threshold: -6.5,
                overProbability: nil,
                marketType: "spreads",
                movement: nil,
                period: nil,
                isWinner: nil,
                resolutionSource: nil,
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.52
            )
        ]
        missingIDMarkets.totals = []
        let droppedCards = EventAtlasRugbyAflCards11666.buildCards(event: finalEvent, gameMarkets: missingIDMarkets, now: baseNow)
        XCTAssertTrue(droppedCards.isEmpty, "Rows missing _marketId and _marketIds must be dropped, never given invented IDs")
    }

    // MARK: - 4. 30-Minute Live Quote Aging (.before and .during)

    func testCurrentAtAgesLiveQuotesAfter30MinutesAndLeavesFinalUnchanged() {
        let gm = makeRugbyGameMarkets(observedAt: "2026-11-09T11:50:00Z")
        let laterNow = baseNow.addingTimeInterval(35 * 60)

        // 1. Before start (.before): reading older than 30 minutes ages to "No recent probability"
        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z",
            homeScore: nil,
            awayScore: nil
        )
        let preCards = EventAtlasRugbyAflCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        let agedPreDeck = preCards.map { NFLEventCard9483.rugbyAfl($0).current(at: laterNow) }
        guard case .rugbyAfl(.matchOutlook(let agedPreOutlook)) = agedPreDeck[0],
              case .rugbyAfl(.marginOrTotal(let agedPreProp)) = agedPreDeck[1] else {
            return XCTFail("Expected aged before-start rugby cards")
        }
        let agedPreHeadline = FieldHeadlineModel10868(agedPreOutlook.headlineInput)
        XCTAssertEqual(
            agedPreHeadline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
            [["No recent probability"], ["No recent probability"], ["No recent probability"]]
        )
        let agedPrePropHeadline = FieldHeadlineModel10868(agedPreProp.headlineInput)
        XCTAssertEqual(
            agedPrePropHeadline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
            [["No recent probability"], ["No recent probability"]]
        )

        // 2. During play (.during): live reading ages after 30 minutes while pregameMark baseline stays intact
        let liveEvent = makeEvent(status: "live", homeScore: 24, awayScore: 21)
        let liveCards = EventAtlasRugbyAflCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        let agedLiveDeck = liveCards.map { NFLEventCard9483.rugbyAfl($0).current(at: laterNow) }
        guard case .rugbyAfl(.matchOutlook(let agedLiveOutlook)) = agedLiveDeck[0] else {
            return XCTFail("Expected aged live rugby outlook card")
        }
        let agedLiveHeadline = FieldHeadlineModel10868(agedLiveOutlook.headlineInput)
        XCTAssertEqual(
            agedLiveHeadline.competitors.map { FieldChaseModel10868.figure($0.metrics[0]) },
            ["81%", "16%", "3%"],
            "Pregame baseline remains intact when live quote ages out"
        )
        XCTAssertEqual(
            agedLiveHeadline.competitors.map { FieldChaseModel10868.words($0.metrics[1]) },
            ["No recent probability", "No recent probability", "No recent probability"]
        )

        // 3. Final cards never expire
        let finalEvent = makeEvent(status: "completed", homeScore: 48, awayScore: 46)
        let finalCards = EventAtlasRugbyAflCards11666.buildCards(event: finalEvent, gameMarkets: gm, now: baseNow)
        let finalAfterHours = finalCards.map { $0.current(at: baseNow.addingTimeInterval(7200)) }
        XCTAssertEqual(finalCards, finalAfterHours)
    }

    // MARK: - 5. Venue-Free Narrative Copy Guard

    func testNarrativeCopyContainsNoVenueNamesAcrossAllKnownSources() {
        let forbiddenVenues = ["Kalshi", "Polymarket", "DraftKings", "FanDuel", "BetMGM", "Caesars", "Pinnacle"]
        for source in ["kalshi", "polymarket", "draftkings", "fanduel", "betmgm"] {
            let event = makeEvent(status: "completed", homeScore: 48, awayScore: 46)
            let gm = makeRugbyGameMarkets(
                source: source,
                homeIsWinner: true,
                awayIsWinner: false,
                homeResolutionSource: "api_settlement",
                awayResolutionSource: "api_settlement"
            )
            let cards = EventAtlasRugbyAflCards11666.buildCards(event: event, gameMarkets: gm, now: baseNow)
            for card in cards {
                switch card {
                case .matchOutlook(let outlook):
                    let copy = outlook.headlineInput.copy
                    let narrative = [copy.eyebrow, copy.title, copy.graphicLabel, copy.beforeLabel, copy.recordedLabel]
                        .compactMap { $0 }
                        .joined(separator: " ")
                    for venue in forbiddenVenues {
                        XCTAssertFalse(narrative.localizedCaseInsensitiveContains(venue))
                    }
                case .marginOrTotal(let prop):
                    let copy = prop.headlineInput.copy
                    let narrative = [copy.eyebrow, copy.title, copy.graphicLabel]
                        .compactMap { $0 }
                        .joined(separator: " ")
                    for venue in forbiddenVenues {
                        XCTAssertFalse(narrative.localizedCaseInsensitiveContains(venue))
                    }
                }
            }
        }
    }

    // MARK: - 6. 390 px Default & Accessibility3 Snapshots

    @MainActor
    func testRenderRugbyAndAflCards390pxDefaultAndAccessibility3Snapshots() throws {
        let rugbyEvent = makeEvent(status: "completed", homeScore: 48, awayScore: 46)
        let rugbyGM = makeRugbyGameMarkets(
            homeIsWinner: true,
            awayIsWinner: false,
            drawIsWinner: false,
            homeResolutionSource: "api_settlement",
            awayResolutionSource: "api_settlement",
            drawResolutionSource: "api_settlement",
            spreadIsWinner: false,
            spreadResolutionSource: "api_settlement"
        )
        let rugbyCards = EventAtlasRugbyAflCards11666.buildCards(event: rugbyEvent, gameMarkets: rugbyGM, now: baseNow)

        let aflEvent = makeEvent(
            id: 15400202,
            sport: "aussierules_afl",
            status: "completed",
            homeTeam: "Brisbane Lions",
            awayTeam: "Collingwood Magpies",
            homeScore: 98,
            awayScore: 86
        )
        let aflGM = makeAflGameMarkets()
        let aflCards = EventAtlasRugbyAflCards11666.buildCards(event: aflEvent, gameMarkets: aflGM, now: baseNow)

        let combinedCards = Array(rugbyCards.prefix(2)) + Array(aflCards.prefix(2))
        XCTAssertEqual(combinedCards.count, 4)

        let stack = VStack(alignment: .leading, spacing: 16) {
            ForEach(combinedCards) { card in
                EventAtlasRugbyAflCardView11666(card: card)
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

        let outDir = URL(fileURLWithPath: "/tmp/rugby-afl-cards-11666")
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        if let defaultPNG = defaultImage.pngData() {
            try? defaultPNG.write(to: outDir.appendingPathComponent("rugby-afl-story-cards-default-390px.png"))
        }
        if let a11yPNG = a11yImage.pngData() {
            try? a11yPNG.write(to: outDir.appendingPathComponent("rugby-afl-story-cards-a11y-390px.png"))
        }
    }
}
