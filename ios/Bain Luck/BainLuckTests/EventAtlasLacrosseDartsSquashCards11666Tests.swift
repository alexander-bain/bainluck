import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class EventAtlasLacrosseDartsSquashCards11666Tests: XCTestCase {

    private let baseNow = ISO8601DateFormatter().date(from: "2026-11-09T12:00:00Z")!

    private func makeEvent(
        id: Int = 15500101,
        sport: String = "lacrosse_pll",
        status: String = "live",
        commenceTime: String = "2026-11-09T11:30:00Z",
        homeTeam: String = "Boston Cannons",
        awayTeam: String = "New York Atlas",
        homeScore: Int? = 12,
        awayScore: Int? = 11
    ) -> EventDetail {
        EventDetail(
            id: id,
            externalId: "evt-lds-\(id)",
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

    private func makeLacrosseGameMarkets(
        eventId: Int = 15500101,
        observedAt: String = "2026-11-09T11:50:00Z",
        source: String = "polymarket",
        homeIsWinner: Bool? = nil,
        awayIsWinner: Bool? = nil,
        homeResolutionSource: String? = nil,
        awayResolutionSource: String? = nil,
        spreadIsWinner: Bool? = nil,
        spreadResolutionSource: String? = nil
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Boston Cannons",
            awayTeam: "New York Atlas",
            status: "live",
            homeScore: 12,
            awayScore: 11,
            playerProps: [],
            spreads: [
                GameMarketOutcome(
                    _marketId: 910011,
                    marketName: "Goal Spread: Boston Cannons (-1.5) vs New York Atlas (+1.5)",
                    outcomeName: "Boston Cannons -1.5",
                    probability: 0.48,
                    source: source,
                    threshold: -1.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: spreadIsWinner,
                    resolutionSource: spreadResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.54
                ),
                GameMarketOutcome(
                    _marketId: 910011,
                    marketName: "Goal Spread: Boston Cannons (-1.5) vs New York Atlas (+1.5)",
                    outcomeName: "New York Atlas +1.5",
                    probability: 0.52,
                    source: source,
                    threshold: 1.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: spreadIsWinner.map { !$0 },
                    resolutionSource: spreadResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.46
                )
            ],
            totals: [
                GameMarketOutcome(
                    _marketId: 910012,
                    marketName: "Total Goals Over/Under 23.5",
                    outcomeName: "Over 23.5",
                    probability: 0.61,
                    source: source,
                    threshold: 23.5,
                    overProbability: 0.61,
                    marketType: "totals",
                    movement: nil,
                    period: nil,
                    isWinner: spreadIsWinner,
                    resolutionSource: spreadResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.50
                )
            ],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 910010,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    marketName: "PLL Match Winner: Boston Cannons vs New York Atlas",
                    outcomeName: "Boston Cannons",
                    probability: 0.58,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.72
                ),
                GameMarketOther(
                    _marketId: 910010,
                    isWinner: awayIsWinner,
                    resolutionSource: awayResolutionSource,
                    marketName: "PLL Match Winner: Boston Cannons vs New York Atlas",
                    outcomeName: "New York Atlas",
                    probability: 0.42,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.28
                )
            ],
            pace: nil
        )
    }

    private func makeDartsGameMarkets(
        eventId: Int = 15500202,
        observedAt: String = "2026-11-09T11:50:00Z",
        source: String = "kalshi",
        homeIsWinner: Bool? = true,
        awayIsWinner: Bool? = false,
        homeResolutionSource: String? = "api_settlement",
        awayResolutionSource: String? = "api_settlement"
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Luke Littler",
            awayTeam: "Luke Humphries",
            status: "completed",
            homeScore: 7,
            awayScore: 4,
            playerProps: [],
            spreads: [
                GameMarketOutcome(
                    _marketId: 920021,
                    marketName: "Set Handicap: Luke Littler (-1.5) vs Luke Humphries (+1.5)",
                    outcomeName: "Luke Littler -1.5",
                    probability: 0.62,
                    source: source,
                    threshold: -1.5,
                    overProbability: nil,
                    marketType: "spreads",
                    movement: nil,
                    period: nil,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.55
                )
            ],
            totals: [
                GameMarketOutcome(
                    _marketId: 920022,
                    marketName: "Total 180s Over/Under 24.5",
                    outcomeName: "Over 24.5",
                    probability: 0.67,
                    source: source,
                    threshold: 24.5,
                    overProbability: 0.67,
                    marketType: "totals",
                    movement: nil,
                    period: nil,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    observedAt: observedAt,
                    pregameMark: 0.52
                )
            ],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 920020,
                    isWinner: homeIsWinner,
                    resolutionSource: homeResolutionSource,
                    marketName: "PDC World Championship Match Winner: Luke Littler vs Luke Humphries",
                    outcomeName: "Luke Littler",
                    probability: 0.64,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.56
                ),
                GameMarketOther(
                    _marketId: 920020,
                    isWinner: awayIsWinner,
                    resolutionSource: awayResolutionSource,
                    marketName: "PDC World Championship Match Winner: Luke Littler vs Luke Humphries",
                    outcomeName: "Luke Humphries",
                    probability: 0.36,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.44
                )
            ],
            pace: nil
        )
    }

    private func makeSquashGameMarkets(
        eventId: Int = 15500303,
        observedAt: String = "2026-11-09T11:50:00Z",
        source: String = "polymarket"
    ) -> GameMarketsResponse {
        GameMarketsResponse(
            eventId: eventId,
            homeTeam: "Ali Farag",
            awayTeam: "Paul Coll",
            status: "completed",
            homeScore: 3,
            awayScore: 2,
            playerProps: [],
            spreads: [],
            totals: [
                GameMarketOutcome(
                    _marketId: 930031,
                    marketName: "Total Games Over/Under 4.5",
                    outcomeName: "Over 4.5",
                    probability: 0.59,
                    source: source,
                    threshold: 4.5,
                    overProbability: 0.59,
                    marketType: "totals",
                    movement: nil,
                    period: nil,
                    isWinner: true,
                    resolutionSource: "api_settlement",
                    observedAt: observedAt,
                    pregameMark: 0.47
                )
            ],
            teamTotals: [],
            periodMarkets: [],
            other: [
                GameMarketOther(
                    _marketId: 930030,
                    isWinner: true,
                    resolutionSource: "api_settlement",
                    marketName: "PSA Match Winner: Ali Farag vs Paul Coll",
                    outcomeName: "Ali Farag",
                    probability: 0.68,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.63
                ),
                GameMarketOther(
                    _marketId: 930030,
                    isWinner: false,
                    resolutionSource: "api_settlement",
                    marketName: "PSA Match Winner: Ali Farag vs Paul Coll",
                    outcomeName: "Paul Coll",
                    probability: 0.32,
                    source: source,
                    observedAt: observedAt,
                    pregameMark: 0.37
                )
            ],
            pace: nil
        )
    }

    // MARK: - 1. Sport Gating

    func testAppliesGatesLacrosseDartsAndSquashSportsOnAtlasFlag() {
        let lacrosseKeys = ["lacrosse", "lacrosse_pll", "lacrosse_nll", "lacrosse_ncaa", "LACROSSE_PLL"]
        for key in lacrosseKeys {
            XCTAssertTrue(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: key, atlasEnabled: false), key)
            XCTAssertEqual(EventAtlasLacrosseDartsSquashCards11666.sportKind(sportKey: key), .lacrosse)
        }

        let dartsKeys = ["darts", "darts_pdc", "darts_wdf", "pdc_darts", "DARTS_PDC"]
        for key in dartsKeys {
            XCTAssertTrue(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: key, atlasEnabled: false), key)
            XCTAssertEqual(EventAtlasLacrosseDartsSquashCards11666.sportKind(sportKey: key), .darts)
        }

        let squashKeys = ["squash", "squash_psa", "psa_squash", "SQUASH_PSA"]
        for key in squashKeys {
            XCTAssertTrue(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: key, atlasEnabled: true), key)
            XCTAssertFalse(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: key, atlasEnabled: false), key)
            XCTAssertEqual(EventAtlasLacrosseDartsSquashCards11666.sportKind(sportKey: key), .squash)
        }

        for other in ["basketball_nba", "rugby_union", "aussierules_afl", "soccer_epl", "", nil] {
            XCTAssertFalse(EventAtlasLacrosseDartsSquashCards11666.applies(sportKey: other, atlasEnabled: true))
        }
    }

    // MARK: - 2. Decide 10-C Lifecycle (.before, .during, .final) & Decide 80-A Row Grades

    func testLacrosseLifecycleObeysDecide10CAndDecide80A() throws {
        let gm = makeLacrosseGameMarkets()

        // 1. Before match (.before): shows ONLY live probability (58% / 42%) labelled "Current chance", never pregameMark (72% / 28%)
        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z",
            homeScore: nil,
            awayScore: nil
        )
        let preCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        XCTAssertEqual(preCards.count, 3, "Before match builds Match Outlook + Goal Spread + Total Goals")
        guard case .matchOutlook(let preOutlook) = preCards[0] else {
            return XCTFail("Expected matchOutlook first")
        }
        let preHeadlineModel = FieldHeadlineModel10868(preOutlook.headlineInput)
        XCTAssertEqual(preHeadlineModel.competitors.map { $0.slot.name }, ["Boston Cannons", "New York Atlas"])
        XCTAssertEqual(
            preHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["58%"], ["42%"]],
            "Decide 10-C: before start shows live quote (58%/42%), never pregameMark (72%/28%)"
        )
        XCTAssertEqual(
            preHeadlineModel.competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
            [["Current chance"], ["Current chance"]]
        )

        // 2. During match (.during): shows pregameMark ("Pre-match chance" 72%/28%) beside live ("Live chance" 58%/42%)
        let liveEvent = makeEvent(status: "live", homeScore: 12, awayScore: 11)
        let liveCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        guard case .matchOutlook(let liveOutlook) = liveCards[0] else {
            return XCTFail("Expected matchOutlook first")
        }
        let liveHeadlineModel = FieldHeadlineModel10868(liveOutlook.headlineInput)
        XCTAssertEqual(
            liveHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["72%", "58%"], ["28%", "42%"]]
        )

        // 3. Final match (.final) with Decide 80-A:
        //    - Authoritative win (api_settlement, isWinner: true) prints "✓ Won"
        //    - Non-winning row (isWinner: false) never mints "✗ Lost"; prints "Result not confirmed"
        let finalEvent = makeEvent(status: "completed", homeScore: 14, awayScore: 12)
        let finalGM = makeLacrosseGameMarkets(
            homeIsWinner: true,
            awayIsWinner: false,
            homeResolutionSource: "api_settlement",
            awayResolutionSource: "api_settlement",
            spreadIsWinner: false,
            spreadResolutionSource: "api_settlement"
        )
        let finalCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: finalEvent, gameMarkets: finalGM, now: baseNow)
        XCTAssertEqual(finalCards.count, 3)
        guard case .matchOutlook(let finalOutlook) = finalCards[0] else {
            return XCTFail("Expected matchOutlook")
        }
        let finalHeadlineModel = FieldHeadlineModel10868(finalOutlook.headlineInput)
        XCTAssertEqual(
            finalHeadlineModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
            [["72%", "✓ Won"], ["28%"]],
            "Decide 80-A: only authoritative win becomes '✓ Won'; row grades never mint '✗ Lost'"
        )
        XCTAssertEqual(
            FieldChaseModel10868.words(finalHeadlineModel.competitors[1].metrics.last!),
            "Result not confirmed"
        )
    }

    // MARK: - 3. Decide 80-A Non-Authoritative Resolution Sources & Missing Market ID Guard

    func testDecide80ARejectsNonAuthoritativeResolutionSourcesAndDropsMissingMarketIDs() throws {
        let finalEvent = makeEvent(status: "completed", homeScore: 14, awayScore: 12)

        for nonAuthSource in ["binary_higher_wins", "multi_max_prob", "clean_resolution", "game_score", "box_score"] {
            let gm = makeLacrosseGameMarkets(
                homeIsWinner: true,
                awayIsWinner: false,
                homeResolutionSource: nonAuthSource,
                awayResolutionSource: nonAuthSource,
                spreadIsWinner: true,
                spreadResolutionSource: nonAuthSource
            )
            let cards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: finalEvent, gameMarkets: gm, now: baseNow)
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

        var missingIDMarkets = makeLacrosseGameMarkets()
        missingIDMarkets.other = [
            GameMarketOther(
                _marketId: nil,
                _marketIds: nil,
                isWinner: true,
                resolutionSource: "api_settlement",
                marketName: "PLL Match Winner: Boston Cannons vs New York Atlas",
                outcomeName: "Boston Cannons",
                probability: 0.58,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.72
            )
        ]
        missingIDMarkets.spreads = []
        missingIDMarkets.totals = []
        let droppedCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: finalEvent, gameMarkets: missingIDMarkets, now: baseNow)
        XCTAssertTrue(droppedCards.isEmpty, "Rows missing _marketId and _marketIds must be dropped")
    }

    // MARK: - 4. Single-Market Full-Match Scope & No Single-Row Fallback Guard

    func testWinnerExtractionIgnoresPartialScopeMarketsRequiresBothSidesAndAcceptsMoneyline() throws {
        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z",
            homeScore: nil,
            awayScore: nil
        )

        var gm = makeLacrosseGameMarkets()
        gm.spreads = []
        gm.totals = []
        gm.other = [
            GameMarketOther(
                _marketId: 910001,
                marketName: "First Half Winner: Boston Cannons vs New York Atlas",
                outcomeName: "Boston Cannons",
                probability: 0.15,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.15
            ),
            GameMarketOther(
                _marketId: 910001,
                marketName: "First Half Winner: Boston Cannons vs New York Atlas",
                outcomeName: "New York Atlas",
                probability: 0.85,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.85
            ),
            GameMarketOther(
                _marketId: 910005,
                marketName: "Match Winner: Boston Cannons",
                outcomeName: "Boston Cannons",
                probability: 0.25,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.25
            ),
            GameMarketOther(
                _marketId: 910010,
                marketName: "PLL: Boston Cannons vs New York Atlas — Moneyline",
                outcomeName: "Boston Cannons",
                probability: 0.58,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.72
            ),
            GameMarketOther(
                _marketId: 910010,
                marketName: "PLL: Boston Cannons vs New York Atlas — Moneyline",
                outcomeName: "New York Atlas",
                probability: 0.42,
                source: "polymarket",
                observedAt: "2026-11-09T11:50:00Z",
                pregameMark: 0.28
            )
        ]

        let cards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        XCTAssertEqual(cards.count, 1)
        guard case .matchOutlook(let outlook) = cards.first else {
            return XCTFail("Expected matchOutlook card")
        }
        XCTAssertEqual(outlook.marketId, 910010)
        XCTAssertTrue(outlook.rows.allSatisfy { $0.marketID == 910010 })

        var gmWithout910010 = gm
        gmWithout910010.other = gm.other?.filter { $0._marketId != 910010 }
        let cardsWithout910010 = EventAtlasLacrosseDartsSquashCards11666.buildCards(
            event: preEvent,
            gameMarkets: gmWithout910010,
            now: baseNow
        )
        XCTAssertTrue(
            cardsWithout910010.isEmpty,
            "Without a complete full-match market pricing both sides, no Match Outcome card is built"
        )
    }

    // MARK: - 5. 30-Minute Live Quote Aging (.before and .during)

    func testCurrentAtAgesLiveQuotesAfter30MinutesAndLeavesFinalUnchanged() {
        let gm = makeLacrosseGameMarkets(observedAt: "2026-11-09T11:50:00Z")
        let laterNow = baseNow.addingTimeInterval(35 * 60)

        let preEvent = makeEvent(
            status: "upcoming",
            commenceTime: "2026-11-09T14:00:00Z",
            homeScore: nil,
            awayScore: nil
        )
        let preCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: preEvent, gameMarkets: gm, now: baseNow)
        let agedPreCards = preCards.map { $0.current(at: laterNow) }
        guard case .matchOutlook(let agedPreOutlook) = agedPreCards[0],
              case .marginOrTotal(let agedPreProp) = agedPreCards[1] else {
            return XCTFail("Expected aged before-start lacrosse cards")
        }
        let agedPreHeadline = FieldHeadlineModel10868(agedPreOutlook.headlineInput)
        XCTAssertEqual(
            agedPreHeadline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
            [["No recent probability"], ["No recent probability"]]
        )
        let agedPrePropHeadline = FieldHeadlineModel10868(agedPreProp.headlineInput)
        XCTAssertEqual(
            agedPrePropHeadline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
            [["No recent probability"], ["No recent probability"]]
        )

        let liveEvent = makeEvent(status: "live", homeScore: 12, awayScore: 11)
        let liveCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: liveEvent, gameMarkets: gm, now: baseNow)
        let agedLiveCards = liveCards.map { $0.current(at: laterNow) }
        guard case .matchOutlook(let agedLiveOutlook) = agedLiveCards[0] else {
            return XCTFail("Expected aged live lacrosse outlook card")
        }
        let agedLiveHeadline = FieldHeadlineModel10868(agedLiveOutlook.headlineInput)
        XCTAssertEqual(
            agedLiveHeadline.competitors.map { FieldChaseModel10868.figure($0.metrics[0]) },
            ["72%", "28%"]
        )
        XCTAssertEqual(
            agedLiveHeadline.competitors.map { FieldChaseModel10868.words($0.metrics[1]) },
            ["No recent probability", "No recent probability"]
        )

        let finalEvent = makeEvent(status: "completed", homeScore: 14, awayScore: 12)
        let finalCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: finalEvent, gameMarkets: gm, now: baseNow)
        let finalAfterHours = finalCards.map { $0.current(at: baseNow.addingTimeInterval(7200)) }
        XCTAssertEqual(finalCards, finalAfterHours)
    }

    // MARK: - 6. Venue-Free Narrative Copy Guard

    func testNarrativeCopyContainsNoVenueNamesAcrossAllKnownSources() {
        let forbiddenVenues = ["Kalshi", "Polymarket", "DraftKings", "FanDuel", "BetMGM", "Caesars", "Pinnacle"]
        for source in ["kalshi", "polymarket", "draftkings", "fanduel", "betmgm"] {
            let event = makeEvent(status: "completed", homeScore: 14, awayScore: 12)
            let gm = makeLacrosseGameMarkets(
                source: source,
                homeIsWinner: true,
                awayIsWinner: false,
                homeResolutionSource: "api_settlement",
                awayResolutionSource: "api_settlement"
            )
            let cards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: event, gameMarkets: gm, now: baseNow)
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

    // MARK: - 7. 390 px Default & Accessibility3 Snapshots

    @MainActor
    func testRenderLacrosseDartsAndSquashCards390pxDefaultAndAccessibility3Snapshots() throws {
        let lacrosseEvent = makeEvent(status: "completed", homeScore: 14, awayScore: 12)
        let lacrosseGM = makeLacrosseGameMarkets(
            homeIsWinner: true,
            awayIsWinner: false,
            homeResolutionSource: "api_settlement",
            awayResolutionSource: "api_settlement",
            spreadIsWinner: false,
            spreadResolutionSource: "api_settlement"
        )
        let lacrosseCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: lacrosseEvent, gameMarkets: lacrosseGM, now: baseNow)

        let dartsEvent = makeEvent(
            id: 15500202,
            sport: "darts_pdc",
            status: "completed",
            homeTeam: "Luke Littler",
            awayTeam: "Luke Humphries",
            homeScore: 7,
            awayScore: 4
        )
        let dartsGM = makeDartsGameMarkets()
        let dartsCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: dartsEvent, gameMarkets: dartsGM, now: baseNow)

        let squashEvent = makeEvent(
            id: 15500303,
            sport: "squash_psa",
            status: "completed",
            homeTeam: "Ali Farag",
            awayTeam: "Paul Coll",
            homeScore: 3,
            awayScore: 2
        )
        let squashGM = makeSquashGameMarkets()
        let squashCards = EventAtlasLacrosseDartsSquashCards11666.buildCards(event: squashEvent, gameMarkets: squashGM, now: baseNow)

        let combinedCards = Array(lacrosseCards.prefix(2)) + Array(dartsCards.prefix(2)) + Array(squashCards.prefix(1))
        XCTAssertEqual(combinedCards.count, 5)

        let stack = VStack(alignment: .leading, spacing: 16) {
            ForEach(combinedCards) { card in
                EventAtlasLacrosseDartsSquashCardView11666(card: card)
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

        let outDir = URL(fileURLWithPath: "/tmp/lacrosse-darts-squash-cards-11666")
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        if let defaultPNG = defaultImage.pngData() {
            try? defaultPNG.write(to: outDir.appendingPathComponent("lacrosse-darts-squash-story-cards-default-390px.png"))
        }
        if let a11yPNG = a11yImage.pngData() {
            try? a11yPNG.write(to: outDir.appendingPathComponent("lacrosse-darts-squash-story-cards-a11y-390px.png"))
        }
    }
}
