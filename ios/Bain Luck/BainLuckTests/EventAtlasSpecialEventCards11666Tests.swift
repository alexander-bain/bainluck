import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class EventAtlasSpecialEventCards11666Tests: XCTestCase {

    private let baseNow = ISO8601DateFormatter().date(from: "2026-11-09T12:00:00Z")!

    private func makeEvent(
        id: Int = 15600101,
        sport: String = "horse_racing",
        status: String = "live",
        commenceTime: String = "2026-11-09T11:30:00Z",
        homeTeam: String = "Fierceness",
        awayTeam: String = "Sierra Leone",
        homeScore: Int? = nil,
        awayScore: Int? = nil
    ) -> EventDetail {
        EventDetail(
            id: id,
            externalId: "evt-special-\(id)",
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

    private func makeHorseRacingMarkets(
        eventId: Int = 15600101,
        observedAt: String = "2026-11-09T11:50:00Z",
        source: String = "polymarket",
        firstIsWinner: Bool? = nil,
        secondIsWinner: Bool? = nil,
        thirdIsWinner: Bool? = nil,
        firstResolutionSource: String? = nil,
        secondResolutionSource: String? = nil,
        thirdResolutionSource: String? = nil,
        marginIsWinner: Bool? = nil,
        marginResolutionSource: String? = nil
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Fierceness",
            awayTeam: "Sierra Leone",
            status: "live",
            homeScore: nil,
            awayScore: nil,
            playerProps: [],
            spreads: [
                GameMarketOutcome(
                    _marketId: 960011,
                    marketName: "Winning Distance Over/Under 1.5 Lengths",
                    outcomeName: "Over",
                    probability: 0.56,
                    source: source,
                    threshold: 1.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: marginIsWinner,
                    resolutionSource: marginResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.49
                )
            ],
            totals: [],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 960010,
                    isWinner: firstIsWinner,
                    resolutionSource: firstResolutionSource,
                    marketName: "Breeders' Cup Classic Winner",
                    outcomeName: "Sierra Leone",
                    probability: 0.38,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.29
                ),
                GameMarketOther(
                    _marketId: 960010,
                    isWinner: secondIsWinner,
                    resolutionSource: secondResolutionSource,
                    marketName: "Breeders' Cup Classic Winner",
                    outcomeName: "Fierceness",
                    probability: 0.34,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.41
                ),
                GameMarketOther(
                    _marketId: 960010,
                    isWinner: thirdIsWinner,
                    resolutionSource: thirdResolutionSource,
                    marketName: "Breeders' Cup Classic Winner",
                    outcomeName: "Forever Young",
                    probability: 0.21,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.22
                )
            ],
            pace: nil
        )
    }

    private func makeOlympicsMarkets(
        eventId: Int = 15600202,
        observedAt: String = "2026-11-09T11:50:00Z"
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Canada",
            awayTeam: "Sweden",
            status: "completed",
            homeScore: 8,
            awayScore: 6,
            playerProps: [],
            spreads: [],
            totals: [
                GameMarketOutcome(
                    _marketId: 960021,
                    marketName: "Total Points Over/Under 12.5",
                    outcomeName: "Over 12.5",
                    probability: 0.64,
                    source: "kalshi",
                    threshold: 12.5,
                    overProbability: 0.64,
                    marketType: "totals",
                    movement: nil,
                    period: nil,
                    isWinner: true,
                    resolutionSource: "api_settlement",
                    observedAt: observedAt,
                    pregameMark: 0.51
                )
            ],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 960020,
                    isWinner: true,
                    resolutionSource: "api_settlement",
                    marketName: "Olympic Men's Curling Gold Medal Match",
                    outcomeName: "Canada",
                    probability: 0.62,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.57
                ),
                GameMarketOther(
                    _marketId: 960020,
                    isWinner: false,
                    resolutionSource: "api_settlement",
                    marketName: "Olympic Men's Curling Gold Medal Match",
                    outcomeName: "Sweden",
                    probability: 0.38,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.43
                )
            ],
            pace: nil
        )
    }

    private func makeEarningsAndWeatherMarkets(
        eventId: Int = 15600303,
        observedAt: String = "2026-11-09T11:50:00Z"
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "NVIDIA Q3 Beat",
            awayTeam: "NVIDIA Q3 Miss",
            status: "completed",
            homeScore: nil,
            awayScore: nil,
            playerProps: [],
            spreads: [],
            totals: [],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 960030,
                    isWinner: true,
                    resolutionSource: "api_settlement",
                    marketName: "NVIDIA Q3 Revenue Beat Consensus",
                    outcomeName: "Beat consensus",
                    probability: 0.78,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.74
                ),
                GameMarketOther(
                    _marketId: 960030,
                    isWinner: false,
                    resolutionSource: "api_settlement",
                    marketName: "NVIDIA Q3 Revenue Beat Consensus",
                    outcomeName: "Miss consensus",
                    probability: 0.22,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.26
                ),
                GameMarketOther(
                    _marketId: 960031,
                    isWinner: true,
                    resolutionSource: "api_settlement",
                    marketName: "Data Center Revenue Threshold Over/Under $30B",
                    outcomeName: "Over $30B",
                    probability: 0.69,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.61
                )
            ],
            pace: nil
        )
    }

    // MARK: - 1. Sport / Category Gating

    func testAppliesGatesHorseRacingOlympicsPokerCeremonyEarningsAndWeatherOnAtlasFlag() {
        let cases: [(String, EventAtlasSpecialEventCards11666.EventKind)] = [
            ("horse_racing", .horseRacing),
            ("horseracing", .horseRacing),
            ("horse_racing_kentucky_derby", .horseRacing),
            ("olympics", .olympics),
            ("curling_olympics", .olympics),
            ("fieldhockey_olympics", .olympics),
            ("poker", .poker),
            ("poker_wsop", .poker),
            ("wsop", .poker),
            ("ceremony", .ceremony),
            ("entertainment", .ceremony),
            ("awards_oscars", .ceremony),
            ("earnings", .earnings),
            ("economics", .earnings),
            ("finance_earnings", .earnings),
            ("weather", .weather),
            ("weather_temperature", .weather),
            ("climate", .weather)
        ]

        for (key, expectedKind) in cases {
            XCTAssertTrue(EventAtlasSpecialEventCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasSpecialEventCards11666.applies(sportKey: key, atlasEnabled: false), key)
            XCTAssertEqual(EventAtlasSpecialEventCards11666.eventKind(sportKey: key), expectedKind, key)
        }

        for other in ["basketball_nba", "rugby_union", "lacrosse_pll", "darts_pdc", "squash_psa", "", nil] {
            XCTAssertFalse(EventAtlasSpecialEventCards11666.applies(sportKey: other, atlasEnabled: true))
        }
    }

    // MARK: - 2. Decide 10-C Lifecycle (.before, .during, .final) & Decide 80-A Row Grades

    func testHorseRacingLifecycleObeysDecide10CAndDecide80APreservingMultiRunnerField() throws {
        let gm = makeHorseRacingMarkets()

        // 1. Before race (.before): shows ONLY live probability (38% / 34% / 21%) labelled "Current chance", never pregameMark (29% / 41% / 22%)
        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z"
        )
        let preCards = EventAtlasSpecialEventCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        XCTAssertEqual(preCards.count, 2)
        guard case .eventOutlook(let preOutlook) = preCards[0] else {
            return XCTFail("Expected eventOutlook first")
        }
        let preHeadlineModel = FieldHeadlineModel10868(preOutlook.headlineInput)
        XCTAssertEqual(preHeadlineModel.competitors.map { $0.slot.name }, ["Sierra Leone", "Fierceness", "Forever Young"])
        XCTAssertEqual(
            preHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["38%"], ["34%"], ["21%"]],
            "Decide 10-C: before start shows live quote (38%/34%/21%), never pregameMark (29%/41%/22%)"
        )
        XCTAssertEqual(
            preHeadlineModel.competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
            [["Current chance"], ["Current chance"], ["Current chance"]]
        )

        // 2. During race (.during): shows pregameMark ("Opening chance" 29%/41%/22%) beside live ("Live chance" 38%/34%/21%)
        let liveEvent = makeEvent(status: "live")
        let liveCards = EventAtlasSpecialEventCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        guard case .eventOutlook(let liveOutlook) = liveCards[0] else {
            return XCTFail("Expected eventOutlook first")
        }
        let liveHeadlineModel = FieldHeadlineModel10868(liveOutlook.headlineInput)
        XCTAssertEqual(
            liveHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["29%", "38%"], ["41%", "34%"], ["22%", "21%"]]
        )

        // 3. Final race (.final) with Decide 80-A:
        //    - Authoritative win (api_settlement, isWinner: true) prints "✓ Won"
        //    - Non-winning row (isWinner: false) never mints "✗ Lost"; prints "Result not confirmed"
        let finalEvent = makeEvent(status: "completed")
        let finalGM = makeHorseRacingMarkets(
            firstIsWinner: true,
            secondIsWinner: false,
            thirdIsWinner: nil,
            firstResolutionSource: "api_settlement",
            secondResolutionSource: "api_settlement",
            thirdResolutionSource: nil,
            marginIsWinner: false,
            marginResolutionSource: "api_settlement"
        )
        let finalCards = EventAtlasSpecialEventCards11666.buildCards(event: finalEvent, gameMarkets: finalGM, now: baseNow)
        guard case .eventOutlook(let finalOutlook) = finalCards[0] else {
            return XCTFail("Expected eventOutlook")
        }
        let finalHeadlineModel = FieldHeadlineModel10868(finalOutlook.headlineInput)
        XCTAssertEqual(
            finalHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["29%", "✓ Won"], ["41%"], ["22%"]],
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

    // MARK: - 3. Decide 80-A Non-Authoritative Resolution Sources & Single-Row Guard

    func testDecide80ARejectsNonAuthoritativeResolutionSourcesAndRequiresMultiOutcomeMarket() throws {
        let finalEvent = makeEvent(status: "completed")

        for nonAuthSource in ["binary_higher_wins", "multi_max_prob", "clean_resolution", "game_score", "box_score"] {
            let gm = makeHorseRacingMarkets(
                firstIsWinner: true,
                secondIsWinner: false,
                thirdIsWinner: false,
                firstResolutionSource: nonAuthSource,
                secondResolutionSource: nonAuthSource,
                thirdResolutionSource: nonAuthSource,
                marginIsWinner: true,
                marginResolutionSource: nonAuthSource
            )
            let cards = EventAtlasSpecialEventCards11666.buildCards(event: finalEvent, gameMarkets: gm, now: baseNow)
            guard case .eventOutlook(let outlook) = cards.first else {
                return XCTFail("Expected eventOutlook for \(nonAuthSource)")
            }
            let model = FieldHeadlineModel10868(outlook.headlineInput)
            for comp in model.competitors {
                let lastMetric = try XCTUnwrap(comp.metrics.last)
                XCTAssertNil(FieldChaseModel10868.figure(lastMetric), "Must not print '✓ Won' or '✗ Lost' for \(nonAuthSource)")
                XCTAssertEqual(FieldChaseModel10868.words(lastMetric), "Result not confirmed")
            }
        }

        // Single-row orphan market without a second outcome in the same marketId builds no outlook card.
        var orphanMarkets = makeHorseRacingMarkets()
        orphanMarkets.spreads = []
        orphanMarkets.other = [
            GameMarketOther(
                _marketId: 960099,
                isWinner: true,
                resolutionSource: "api_settlement",
                marketName: "Breeders' Cup Classic Winner",
                outcomeName: "Sierra Leone",
                probability: 0.38,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.29
            )
        ]
        let orphanCards = EventAtlasSpecialEventCards11666.buildCards(event: finalEvent, gameMarkets: orphanMarkets, now: baseNow)
        XCTAssertTrue(orphanCards.isEmpty, "A lone single-row market must not build a primary Event Outlook card")

        // Numbered partial-scope markets ("Heat 1 Winner", "Set 1 Winner") listed before the primary market are ignored.
        var partialMarkets = makeHorseRacingMarkets()
        partialMarkets.spreads = []
        partialMarkets.other = [
            GameMarketOther(
                _marketId: 960001,
                isWinner: nil,
                resolutionSource: nil,
                marketName: "Heat 1 Winner",
                outcomeName: "Sierra Leone",
                probability: 0.50,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.50
            ),
            GameMarketOther(
                _marketId: 960001,
                isWinner: nil,
                resolutionSource: nil,
                marketName: "Heat 1 Winner",
                outcomeName: "Fierceness",
                probability: 0.50,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.50
            )
        ] + (makeHorseRacingMarkets().other ?? [])
        let filteredCards = EventAtlasSpecialEventCards11666.buildCards(event: finalEvent, gameMarkets: partialMarkets, now: baseNow)
        guard case .eventOutlook(let filteredOutlook) = filteredCards.first else {
            return XCTFail("Expected primary eventOutlook card after skipping Heat 1 Winner")
        }
        XCTAssertEqual(filteredOutlook.marketId, 960010)
        let deckCard = NFLEventCard9483.specialEvent(.eventOutlook(filteredOutlook))
        XCTAssertEqual(deckCard.id, filteredOutlook.id)
        XCTAssertEqual(deckCard.title, filteredOutlook.title)
    }

    // MARK: - 4. 30-Minute Live Quote Aging (.before and .during)

    func testCurrentAtAgesLiveQuotesAfter30MinutesAndLeavesFinalUnchanged() {
        let gm = makeHorseRacingMarkets(observedAt: "2026-11-09T11:50:00Z")
        let laterNow = baseNow.addingTimeInterval(35 * 60)

        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z"
        )
        let preCards = EventAtlasSpecialEventCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        let agedPreCards = preCards.map { $0.current(at: laterNow) }
        guard case .eventOutlook(let agedPreOutlook) = agedPreCards[0] else {
            return XCTFail("Expected aged before-start horse racing card")
        }
        let agedPreHeadline = FieldHeadlineModel10868(agedPreOutlook.headlineInput)
        XCTAssertEqual(
            agedPreHeadline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
            [["No recent probability"], ["No recent probability"], ["No recent probability"]]
        )

        let liveEvent = makeEvent(status: "live")
        let liveCards = EventAtlasSpecialEventCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        let agedLiveCards = liveCards.map { $0.current(at: laterNow) }
        guard case .eventOutlook(let agedLiveOutlook) = agedLiveCards[0] else {
            return XCTFail("Expected aged live horse racing card")
        }
        let agedLiveHeadline = FieldHeadlineModel10868(agedLiveOutlook.headlineInput)
        XCTAssertEqual(
            agedLiveHeadline.competitors.map { FieldChaseModel10868.figure($0.metrics[0]) },
            ["29%", "41%", "22%"]
        )
        XCTAssertEqual(
            agedLiveHeadline.competitors.map { FieldChaseModel10868.words($0.metrics[1]) },
            ["No recent probability", "No recent probability", "No recent probability"]
        )
    }

    // MARK: - 5. Venue-Free Narrative Copy Guard

    func testNarrativeCopyContainsNoVenueNamesAcrossAllKnownSources() {
        let forbiddenVenues = ["Kalshi", "Polymarket", "DraftKings", "FanDuel", "BetMGM", "Caesars", "Pinnacle"]
        for source in ["kalshi", "polymarket", "draftkings", "fanduel", "betmgm"] {
            let event = makeEvent(status: "completed")
            let gm = makeHorseRacingMarkets(
                source: source,
                firstIsWinner: true,
                secondIsWinner: false,
                firstResolutionSource: "api_settlement",
                secondResolutionSource: "api_settlement"
            )
            let cards = EventAtlasSpecialEventCards11666.buildCards(event: event, gameMarkets: gm, now: baseNow)
            for card in cards {
                switch card {
                case .eventOutlook(let outlook):
                    let copy = outlook.headlineInput.copy
                    let narrative = [copy.eyebrow, copy.title, copy.graphicLabel, copy.beforeLabel, copy.recordedLabel]
                        .compactMap { $0 }
                        .joined(separator: " ")
                    for venue in forbiddenVenues {
                        XCTAssertFalse(narrative.localizedCaseInsensitiveContains(venue))
                    }
                case .thresholdOrTotal(let prop):
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
    func testRenderSpecialEventCards390pxDefaultAndAccessibility3Snapshots() throws {
        let horseEvent = makeEvent(status: "completed")
        let horseGM = makeHorseRacingMarkets(
            firstIsWinner: true,
            secondIsWinner: false,
            thirdIsWinner: false,
            firstResolutionSource: "api_settlement",
            secondResolutionSource: "api_settlement",
            thirdResolutionSource: "api_settlement",
            marginIsWinner: true,
            marginResolutionSource: "api_settlement"
        )
        let horseCards = EventAtlasSpecialEventCards11666.buildCards(event: horseEvent, gameMarkets: horseGM, now: baseNow)

        let olympicsEvent = makeEvent(
            id: 15600202,
            sport: "curling_olympics",
            status: "completed",
            homeTeam: "Canada",
            awayTeam: "Sweden",
            homeScore: 8,
            awayScore: 6
        )
        let olympicsGM = makeOlympicsMarkets()
        let olympicsCards = EventAtlasSpecialEventCards11666.buildCards(event: olympicsEvent, gameMarkets: olympicsGM, now: baseNow)

        let earningsEvent = makeEvent(
            id: 15600303,
            sport: "earnings",
            status: "completed",
            homeTeam: "NVIDIA Q3 Beat",
            awayTeam: "NVIDIA Q3 Miss"
        )
        let earningsGM = makeEarningsAndWeatherMarkets()
        let earningsCards = EventAtlasSpecialEventCards11666.buildCards(event: earningsEvent, gameMarkets: earningsGM, now: baseNow)

        let combinedCards = Array(horseCards.prefix(2)) + Array(olympicsCards.prefix(1)) + Array(earningsCards.prefix(2))
        XCTAssertEqual(combinedCards.count, 5)

        let stack = VStack(alignment: .leading, spacing: 16) {
            ForEach(combinedCards) { card in
                EventAtlasSpecialEventCardView11666(card: card)
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

        let outDir = URL(fileURLWithPath: "/tmp/special-event-cards-11666")
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        if let defaultPNG = defaultImage.pngData() {
            try? defaultPNG.write(to: outDir.appendingPathComponent("special-event-story-cards-default-390px.png"))
        }
        if let a11yPNG = a11yImage.pngData() {
            try? a11yPNG.write(to: outDir.appendingPathComponent("special-event-story-cards-a11y-390px.png"))
        }
    }
}
