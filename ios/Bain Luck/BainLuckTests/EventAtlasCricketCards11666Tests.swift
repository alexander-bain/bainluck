import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class EventAtlasCricketCards11666Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-11-08T22:00:00Z")!

    // MARK: - 1. Sport & Format Gating

    func testAppliesGatedByAtlasAndCricketSportKey() {
        let t20Sport = "cricket_international_t20"
        let testSport = "cricket_test_match"
        let mmaSport = "mma_mixed_martial_arts"
        let mlbSport = "baseball_mlb"
        let iplSport = "cricket_ipl"
        let odiSport = "cricket_odi"
        XCTAssertTrue(EventAtlasCricketCards11666.applies(sportKey: t20Sport, atlasEnabled: true))
        XCTAssertTrue(EventAtlasCricketCards11666.applies(sportKey: "cricket_t20", atlasEnabled: true))
        XCTAssertTrue(EventAtlasCricketCards11666.applies(sportKey: iplSport, atlasEnabled: true))
        XCTAssertTrue(EventAtlasCricketCards11666.applies(sportKey: testSport, atlasEnabled: true))
        XCTAssertTrue(EventAtlasCricketCards11666.applies(sportKey: odiSport, atlasEnabled: true))
        XCTAssertTrue(EventAtlasCricketCards11666.applies(sportKey: "cricket", atlasEnabled: true))

        XCTAssertFalse(EventAtlasCricketCards11666.applies(sportKey: t20Sport, atlasEnabled: false))
        XCTAssertFalse(EventAtlasCricketCards11666.applies(sportKey: mlbSport, atlasEnabled: true))
        XCTAssertFalse(EventAtlasCricketCards11666.applies(sportKey: mmaSport, atlasEnabled: true))
        XCTAssertFalse(EventAtlasCricketCards11666.applies(sportKey: nil, atlasEnabled: true))

        XCTAssertEqual(EventAtlasCricketCards11666.resolveFormat(sportKey: testSport), .test)
        XCTAssertEqual(EventAtlasCricketCards11666.resolveFormat(sportKey: odiSport), .odi)
        XCTAssertEqual(EventAtlasCricketCards11666.resolveFormat(sportKey: t20Sport), .t20)
    }

    // MARK: - 2. Before-Play Pregame Story & Chase Cards

    func testBuildsBeforePlayPregameOutlookAndChaseCardsWithThreeOutcomes() throws {
        let event = makeCricketEvent(
            sport: "cricket_test_match",
            status: "scheduled",
            commenceTime: "2026-11-09T04:00:00Z"
        )
        let markets = makeCricketGameMarkets(
            observedAt: "2026-11-08T21:55:00Z",
            settled: false,
            includeDraw: true
        )

        let cards = EventAtlasCricketCards11666.buildCards(
            event: event,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        XCTAssertEqual(cards.count, 2)

        guard case .pregame(let pregameCard) = cards[0],
              case .chase(let chaseCard) = cards[1] else {
            return XCTFail("Expected .pregame and .chase cards before play")
        }

        XCTAssertEqual(pregameCard.format, .test)
        XCTAssertEqual(pregameCard.rows.map(\.subject), ["India", "Australia", "Draw / tie"])
        let pregameInput = pregameCard.presentationInput(now: now)
        XCTAssertTrue(pregameInput.isVisible)
        XCTAssertEqual(pregameInput.rows[0].before.observation?.text, "54%")
        XCTAssertEqual(pregameInput.rows[1].before.observation?.text, "34%")
        XCTAssertEqual(pregameInput.rows[2].before.observation?.text, "12%")

        let chaseInput = chaseCard.presentationInput(now: now)
        XCTAssertEqual(chaseInput.phase, .before)
        if case .observed(let fig) = chaseInput.pregame {
            XCTAssertEqual(fig.text, "58%")
        } else {
            XCTFail("Expected observed pregame chase figure")
        }
    }

    // MARK: - 3. 30-Minute Staleness Rule (.before vs .during)

    func testBeforeMatchAgesStaleReadingToNoRecentProbabilityAndDuringPreservesPregameBaseline() throws {
        // Phase A: `.before` — reading > 30m old is withheld as "No recent probability"
        let scheduledEvent = makeCricketEvent(
            sport: "cricket_international_t20",
            status: "scheduled",
            commenceTime: "2026-11-09T04:00:00Z"
        )
        let staleMarkets = makeCricketGameMarkets(
            observedAt: "2026-11-08T21:10:00Z",
            settled: false,
            includeDraw: false
        )
        let beforeCards = EventAtlasCricketCards11666.buildCards(
            event: scheduledEvent,
            gameMarkets: staleMarkets,
            now: now,
            atlasEnabled: true
        )
        guard case .pregame(let pregameCard) = beforeCards[0],
              case .chase(let beforeChase) = beforeCards[1] else {
            return XCTFail("Expected pregame and chase cards")
        }
        let pregameInput = pregameCard.presentationInput(now: now)
        XCTAssertEqual(pregameInput.rows[0].before, .withheld("No recent probability"))
        let beforeChaseInput = beforeChase.presentationInput(now: now)
        XCTAssertEqual(beforeChaseInput.pregame, .withheld("No recent probability"))

        // Phase B: `.during` — fresh at 21:56 UTC (4m old), then aged at +32m (`later`)
        let liveEvent = makeCricketEvent(
            sport: "cricket_international_t20",
            status: "live",
            commenceTime: "2026-11-08T20:00:00Z",
            homeScore: 142,
            awayScore: 185
        )
        let freshMarkets = makeCricketGameMarkets(
            observedAt: "2026-11-08T21:56:00Z",
            settled: false,
            includeDraw: false
        )
        let liveCards = EventAtlasCricketCards11666.buildCards(
            event: liveEvent,
            gameMarkets: freshMarkets,
            now: now,
            atlasEnabled: true
        )
        guard case .outlook(let outlookCard) = liveCards[0],
              case .chase(let liveChase) = liveCards[1] else {
            return XCTFail("Expected outlook and chase cards during play")
        }

        // Fresh at `now`
        let freshOutlook = outlookCard.presentationInput(selectedRowID: nil, now: now)
        XCTAssertEqual(freshOutlook.rows[0].before.observation?.text, "48%")
        XCTAssertEqual(freshOutlook.rows[0].comparison.observation?.text, "54%")
        XCTAssertEqual(freshOutlook.rows[0].movement?.text, "↑ 6 points")

        // Advance clock by 32 minutes -> 36 minutes old (> 30m limit)
        let later = now.addingTimeInterval(32 * 60)
        let agedOutlook = outlookCard.presentationInput(selectedRowID: nil, now: later)
        // Pregame baseline stays fixed ("48%") while comparison is withheld as "No recent probability"
        XCTAssertEqual(agedOutlook.rows[0].before.observation?.text, "48%")
        XCTAssertEqual(agedOutlook.rows[0].comparison, .withheld("No recent probability"))
        XCTAssertNil(agedOutlook.rows[0].movement)

        let agedChase = liveChase.presentationInput(now: later)
        if case .observed(let preFig) = agedChase.pregame {
            XCTAssertEqual(preFig.text, "52%")
        } else {
            XCTFail("Expected preserved pregame chase baseline during play")
        }
        XCTAssertEqual(agedChase.comparison, .withheld("No recent probability"))
    }

    // MARK: - 4. Final Settlement Grading & Unconfirmed Truthfulness

    func testFinalMatchGradesOfficialWinnerAndNeverFabricatesLostWhenResultUnknown() throws {
        let finalEvent = makeCricketEvent(
            sport: "cricket_test_match",
            status: "completed",
            commenceTime: "2026-11-08T16:00:00Z",
            homeScore: 240,
            awayScore: 212
        )
        let settledMarkets = makeCricketGameMarkets(
            observedAt: "2026-11-08T21:40:00Z",
            settled: true,
            includeDraw: true
        )
        let cards = EventAtlasCricketCards11666.buildCards(
            event: finalEvent,
            gameMarkets: settledMarkets,
            now: now,
            atlasEnabled: true
        )
        guard case .outlook(let outlookCard) = cards[0],
              case .chase(let chaseCard) = cards[1] else {
            return XCTFail("Expected outlook and chase cards at final")
        }

        let outlookInput = outlookCard.presentationInput(selectedRowID: nil, now: now)
        XCTAssertEqual(outlookInput.rows[0].finish?.outcome.word?.text, "✓ Won")
        XCTAssertEqual(outlookInput.rows[1].finish?.outcome.word?.text, "✗ Lost")
        XCTAssertEqual(outlookInput.rows[2].finish?.outcome.word?.text, "No draw / tie")

        let chaseInput = chaseCard.presentationInput(now: now)
        if case .graded(let fig) = chaseInput.contractResult {
            XCTAssertEqual(fig.text, "✓ Won")
        } else {
            XCTFail("Expected graded chase contract result")
        }

        // Unconfirmed markets on a completed match must yield "Result not confirmed", never "✗ Lost"
        let unconfirmedMarkets = makeCricketGameMarkets(
            observedAt: "2026-11-08T21:40:00Z",
            settled: false,
            includeDraw: true
        )
        let unconfirmedCards = EventAtlasCricketCards11666.buildCards(
            event: finalEvent,
            gameMarkets: unconfirmedMarkets,
            now: now,
            atlasEnabled: true
        )
        guard case .outlook(let unconfirmedOutlook) = unconfirmedCards[0],
              case .chase(let unconfirmedChase) = unconfirmedCards[1] else {
            return XCTFail("Expected unconfirmed outlook and chase cards")
        }
        let unconfirmedInput = unconfirmedOutlook.presentationInput(selectedRowID: nil, now: now)
        XCTAssertTrue(
            unconfirmedInput.rows.allSatisfy {
                $0.finish?.outcome == .unavailable("Result not confirmed")
            }
        )
        XCTAssertEqual(
            unconfirmedChase.presentationInput(now: now).contractResult,
            .unconfirmed("Result not confirmed")
        )
    }

    // MARK: - 5. Whole-Point Movement, Venue-Neutral Provenance & Silent Skip

    func testWholePointMovementVenueNeutralProvenanceAndSilentSkipGuards() {
        XCTAssertEqual(
            EventAtlasCricketCards11666.formatOutlookMovement(before: 0.40, current: 0.484).text,
            "↑ 8 points"
        )
        XCTAssertEqual(
            EventAtlasCricketCards11666.formatOutlookMovement(before: 0.40, current: 0.389).text,
            "↓ 1 point"
        )
        XCTAssertEqual(
            EventAtlasCricketCards11666.formatOutlookMovement(before: 0.40, current: 0.403).text,
            "No change"
        )

        let provenance = EventAtlasCricketCards11666.formatSourceDetail(
            rawSource: "polymarket",
            sourceCount: 1,
            observedAt: now,
            isStaleLive: false,
            phase: .during,
            now: now
        )
        XCTAssertFalse(provenance.lowercased().contains("kalshi"))
        XCTAssertFalse(provenance.lowercased().contains("polymarket"))

        let event = makeCricketEvent(
            sport: "cricket_international_t20",
            status: "scheduled",
            commenceTime: "2026-11-09T04:00:00Z"
        )
        let emptyMarkets = GameMarketsResponse(
            eventId: event.id,
            homeTeam: event.homeTeam,
            awayTeam: event.awayTeam,
            status: event.status,
            homeScore: nil,
            awayScore: nil,
            playerProps: [],
            spreads: [],
            totals: [],
            teamTotals: [],
            periodMarkets: [],
            other: [],
            pace: nil
        )
        XCTAssertTrue(
            EventAtlasCricketCards11666.buildCards(
                event: event,
                gameMarkets: emptyMarkets,
                now: now,
                atlasEnabled: true
            ).isEmpty
        )
    }

    // MARK: - 6. 390 px Snapshot Verification (Default + AX3)

    @MainActor
    func testRenders390pxCricketCardsSnapshotsAtDefaultAndAccessibility3() throws {
        let liveEvent = makeCricketEvent(
            sport: "cricket_international_t20",
            status: "live",
            commenceTime: "2026-11-08T20:00:00Z",
            homeScore: 142,
            awayScore: 185
        )
        let markets = makeCricketGameMarkets(
            observedAt: "2026-11-08T21:56:00Z",
            settled: false,
            includeDraw: true
        )
        let liveCards = EventAtlasCricketCards11666.buildCards(
            event: liveEvent,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        guard case .outlook(let outlookCard) = liveCards[0],
              case .chase(let chaseCard) = liveCards[1] else {
            return XCTFail("Expected outlook and chase cards")
        }

        let scheduledEvent = makeCricketEvent(
            sport: "cricket_international_t20",
            status: "scheduled",
            commenceTime: "2026-11-09T04:00:00Z"
        )
        let beforeCards = EventAtlasCricketCards11666.buildCards(
            event: scheduledEvent,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        guard case .pregame(let pregameCard) = beforeCards[0] else {
            return XCTFail("Expected pregame card")
        }

        let defaultStack = VStack(spacing: 16) {
            EventAtlasCricketPregameCardView11666(card: pregameCard, now: now)
            EventAtlasCricketOutlookCardView11666(card: outlookCard, now: now)
            EventAtlasCricketChaseCardView11666(card: chaseCard, now: now)
        }
        .padding(16)
        .frame(width: 390)
        .background(Color.systemBackground)
        .environment(\.colorScheme, .light)

        let defaultRenderer = rendererForMeasurement(defaultStack)
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(defaultImage.size.height, 500)

        let a11yStack = VStack(spacing: 16) {
            EventAtlasCricketOutlookCardView11666(card: outlookCard, now: now)
            EventAtlasCricketChaseCardView11666(card: chaseCard, now: now)
        }
        .padding(16)
        .frame(width: 390)
        .background(Color.systemBackground)
        .environment(\.colorScheme, .light)

        let a11yRenderer = rendererForMeasurement(a11yStack, at: .accessibility3)
        a11yRenderer.scale = 1.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(a11yImage.size.height, 500)

        if let dir = ProcessInfo.processInfo.environment["CRICKET_CARDS_SNAPSHOT_DIR"], !dir.isEmpty {
            let dirURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try XCTUnwrap(defaultImage.pngData()).write(
                to: dirURL.appendingPathComponent("cricket-story-cards-default-390px.png")
            )
            try XCTUnwrap(a11yImage.pngData()).write(
                to: dirURL.appendingPathComponent("cricket-story-cards-a11y-390px.png")
            )
        }
    }

    // MARK: - Fixtures

    private func makeCricketEvent(
        sport: String,
        status: String,
        commenceTime: String,
        homeTeam: String = "India",
        awayTeam: String = "Australia",
        homeScore: Int? = nil,
        awayScore: Int? = nil
    ) -> EventDetail {
        EventDetail(
            id: 88201,
            externalId: "cricket-ind-aus-88201",
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

    private func makeCricketGameMarkets(
        observedAt: String,
        settled: Bool,
        includeDraw: Bool
    ) -> GameMarketsResponse {
        let resSource: String? = settled ? "api_settlement" : nil
        var otherRows: [GameMarketOther] = [
            GameMarketOther(
                _marketId: 701,
                isWinner: settled ? true : nil,
                resolutionSource: resSource,
                marketName: "Match Winner",
                outcomeName: "India",
                probability: 0.54,
                source: "kalshi",
                observedAt: observedAt,
                pregameMark: 0.48
            ),
            GameMarketOther(
                _marketId: 701,
                isWinner: settled ? false : nil,
                resolutionSource: resSource,
                marketName: "Match Winner",
                outcomeName: "Australia",
                probability: 0.34,
                source: "polymarket",
                observedAt: observedAt,
                pregameMark: 0.40
            ),
        ]
        if includeDraw {
            otherRows.append(
                GameMarketOther(
                    _marketId: 701,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Match Result — Draw",
                    outcomeName: "Draw",
                    probability: 0.12,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.12
                )
            )
        }
        return GameMarketsResponse(
            eventId: 88201,
            homeTeam: "India",
            awayTeam: "Australia",
            status: settled ? "completed" : "live",
            homeScore: 142,
            awayScore: 185,
            playerProps: [],
            spreads: [],
            totals: [],
            teamTotals: [
                GameMarketOutcome(
                    _marketId: 702,
                    marketName: "India 2nd Innings Target Runs",
                    outcomeName: "Over",
                    probability: 0.58,
                    source: "kalshi",
                    threshold: 186.0,
                    overProbability: 0.58,
                    marketType: "team_total",
                    movement: nil,
                    period: nil,
                    isWinner: settled ? true : nil,
                    resolutionSource: resSource,
                    observedAt: observedAt,
                    pregameMark: 0.52
                )
            ],
            periodMarkets: [],
            other: otherRows,
            pace: nil
        )
    }
}
