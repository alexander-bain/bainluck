import XCTest
@testable import Bain_Luck

/// #11666 Step E6c — Native Event-page Atlas Soccer story cards (`soccer_*`),
/// mirroring web `#11974` Step E6c (`frontend/lib/soccerEventCards.ts`), gated behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasSoccerCardsE6c_11666Tests: XCTestCase {

    func testGatesSoccerAtlasCardsStrictlyOnAtlasEnabledAndSoccerSportPrefix() {
        XCTAssertFalse(EventAtlasSoccerCards11666.applies(sportKey: "soccer_epl", atlasEnabled: false))
        XCTAssertTrue(EventAtlasSoccerCards11666.applies(sportKey: "soccer_epl", atlasEnabled: true))
        XCTAssertTrue(EventAtlasSoccerCards11666.applies(sportKey: "soccer_uefa_champs_league", atlasEnabled: true))
        XCTAssertFalse(EventAtlasSoccerCards11666.applies(sportKey: "icehockey_nhl", atlasEnabled: true))
        XCTAssertFalse(EventAtlasSoccerCards11666.applies(sportKey: nil, atlasEnabled: true))
    }

    @MainActor
    func testRefusesTwoWayMarketAndPreservesRawThreeWayQuotesWithoutNormalization() throws {
        let now = try XCTUnwrap("2026-11-06T18:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Two-way market without Draw leg must be refused
        let twoWayJSON = """
        [
            {
                "_market_id": 501,
                "market_name": "Match Result",
                "outcome_name": "Arsenal FC",
                "probability": 0.60,
                "observed_at": "2026-11-06T17:55:00Z",
                "source": "kalshi"
            },
            {
                "_market_id": 501,
                "market_name": "Match Result",
                "outcome_name": "Chelsea FC",
                "probability": 0.40,
                "observed_at": "2026-11-06T17:55:00Z",
                "source": "kalshi"
            }
        ]
        """
        let twoWayRows = try decoder.decode([GameMarketOther].self, from: Data(twoWayJSON.utf8))
        XCTAssertNil(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: twoWayRows,
                status: "scheduled",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )

        // 2. Three-way market preserves raw quotes (e.g. 0.48 + 0.28 + 0.27 = 1.03) without normalizing
        let threeWayJSON = """
        [
            {
                "_market_id": 502,
                "market_name": "Match Winner",
                "outcome_name": "Arsenal FC",
                "probability": 0.48,
                "observed_at": "2026-11-06T17:55:00Z",
                "source": "kalshi"
            },
            {
                "_market_id": 502,
                "market_name": "Match Winner",
                "outcome_name": "Draw",
                "probability": 0.28,
                "observed_at": "2026-11-06T17:55:00Z",
                "source": "kalshi"
            },
            {
                "_market_id": 502,
                "market_name": "Match Winner",
                "outcome_name": "Chelsea FC",
                "probability": 0.27,
                "observed_at": "2026-11-06T17:55:00Z",
                "source": "kalshi"
            }
        ]
        """
        let threeWayRows = try decoder.decode([GameMarketOther].self, from: Data(threeWayJSON.utf8))
        let card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: threeWayRows,
                status: "scheduled",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertEqual(card.title, "A draw is a real third outcome")
        XCTAssertEqual(card.legs.map(\.label), ["Arsenal", "Draw", "Chelsea"])
        XCTAssertEqual(card.legs[0].quotedChance ?? 0, 0.48, accuracy: 1e-6)
        XCTAssertEqual(card.legs[1].quotedChance ?? 0, 0.28, accuracy: 1e-6)
        XCTAssertEqual(card.legs[2].quotedChance ?? 0, 0.27, accuracy: 1e-6)
        XCTAssertEqual(card.quotedSum ?? 0, 1.03, accuracy: 1e-6)
        XCTAssertEqual(card.reason, "Recorded three-way quotes total 103% · no normalization or invented draw")
    }

    @MainActor
    func testParsesExactScoreOutcomesAndBuildsExactScoreCardAndDetailsSheet() throws {
        XCTAssertEqual(
            EventAtlasSoccerCards11666.parseExactScoreOutcome(
                outcomeLabel: "Draw 1-1",
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea"
            ),
            .score(homeGoals: 1, awayGoals: 1)
        )
        XCTAssertEqual(
            EventAtlasSoccerCards11666.parseExactScoreOutcome(
                outcomeLabel: "Chelsea wins 2-1",
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea"
            ),
            .score(homeGoals: 1, awayGoals: 2)
        )

        let now = try XCTUnwrap("2026-11-06T22:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let exactJSON = """
        [
            {
                "_market_id": 601,
                "market_name": "Exact Score",
                "outcome_name": "Draw 0-0",
                "probability": 0.01,
                "pregame_mark": 0.09,
                "observed_at": "2026-11-06T19:55:00Z",
                "source": "kalshi",
                "is_winner": false,
                "resolution_source": "official_score"
            },
            {
                "_market_id": 601,
                "market_name": "Exact Score",
                "outcome_name": "Arsenal wins 1-0",
                "probability": 0.01,
                "pregame_mark": 0.14,
                "observed_at": "2026-11-06T19:55:00Z",
                "source": "kalshi",
                "is_winner": false,
                "resolution_source": "official_score"
            },
            {
                "_market_id": 601,
                "market_name": "Exact Score",
                "outcome_name": "Draw 1-1",
                "probability": 0.99,
                "pregame_mark": 0.12,
                "observed_at": "2026-11-06T19:55:00Z",
                "source": "kalshi",
                "is_winner": true,
                "resolution_source": "official_score"
            },
            {
                "_market_id": 601,
                "market_name": "Exact Score",
                "outcome_name": "Arsenal wins 2-1",
                "probability": 0.01,
                "pregame_mark": 0.10,
                "observed_at": "2026-11-06T19:55:00Z",
                "source": "kalshi",
                "is_winner": false,
                "resolution_source": "official_score"
            }
        ]
        """
        let exactRows = try decoder.decode([GameMarketOther].self, from: Data(exactJSON.utf8))
        let exactCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: exactRows,
                status: "completed",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertEqual(exactCard.title, "The exact-score landscape")
        XCTAssertEqual(exactCard.cells.count, 4)
        XCTAssertEqual(exactCard.defaultSelectedKey, "1-1")

        let winnerCell = try XCTUnwrap(exactCard.cells.first(where: { $0.key == "1-1" }))
        XCTAssertEqual(winnerCell.result, .won)
        XCTAssertEqual(winnerCell.chance ?? 0, 0.12, accuracy: 1e-6)

        let details = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: winnerCell.id,
                cards: [.soccerExactScore(exactCard)],
                rows: [:],
                awayName: "Chelsea",
                homeName: "Arsenal"
            )
        )
        XCTAssertEqual(details.outcomeTitle, "Arsenal 1 – 1 Chelsea")
        XCTAssertEqual(details.primaryReadingLabel, "Result")
        XCTAssertEqual(details.primaryReadingValue, "✓ Won")
        XCTAssertEqual(details.pregameBaseline, "12%")
        XCTAssertEqual(details.sourceLabel, "Kalshi")
    }
}
