import XCTest
import SwiftUI
import UIKit
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
    func testRefusesTwoWayMarketAndScalesThreeWayFieldUnderRuling49A() throws {
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

        // 2. Ruling 49-A: three-way market with raw total >= 90% (0.48 + 0.28 + 0.27 = 1.03)
        // scales legs to 100%, prints what the card is ("Home, draw and away are three real outcomes")
        // rather than the overround sum, and keeps the raw sum in the details sheet's raw fields at most.
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
        XCTAssertEqual(card.reason, "Home, draw and away are three real outcomes")
        XCTAssertFalse(card.reason.contains("%"))
        XCTAssertFalse(card.reason.lowercased().contains("normalization"))
        XCTAssertEqual(card.legs.map(\.label), ["Arsenal", "Draw", "Chelsea"])
        XCTAssertEqual(card.legs[0].quotedChance ?? 0, 0.48 / 1.03, accuracy: 1e-6)
        XCTAssertEqual(card.legs[1].quotedChance ?? 0, 0.28 / 1.03, accuracy: 1e-6)
        XCTAssertEqual(card.legs[2].quotedChance ?? 0, 0.27 / 1.03, accuracy: 1e-6)
        let scaledSum = card.legs.compactMap(\.quotedChance).reduce(0.0, +)
        XCTAssertEqual(scaledSum, 1.0, accuracy: 1e-6)
        XCTAssertEqual(card.quotedSum ?? 0, 1.03, accuracy: 1e-6)
        let sheet = EventAtlasSoccerCards11666.detailsModel(for: card.legs[0], card: card)
        XCTAssertEqual(sheet.primaryReadingValue, "47%")
        XCTAssertEqual(sheet.statusSummary, "Raw 3-way sum 103%")

        // 3. Ruling 49-A scales both ways when raw total >= 90% and < 100% (0.45 + 0.25 + 0.25 = 0.95)
        let under100JSON = """
        [
            {"_market_id": 503, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.45, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"},
            {"_market_id": 503, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.25, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"},
            {"_market_id": 503, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.25, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"}
        ]
        """
        let under100Rows = try decoder.decode([GameMarketOther].self, from: Data(under100JSON.utf8))
        let under100Card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: under100Rows,
                status: "scheduled",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertEqual(under100Card.legs[0].quotedChance ?? 0, 0.45 / 0.95, accuracy: 1e-6)
        XCTAssertEqual(under100Card.legs[1].quotedChance ?? 0, 0.25 / 0.95, accuracy: 1e-6)
        XCTAssertEqual(under100Card.legs[2].quotedChance ?? 0, 0.25 / 0.95, accuracy: 1e-6)

        // 4. Ruling 49-A withholds all leg numbers when raw total < 90% (0.30 + 0.25 + 0.20 = 0.75)
        // or when the field is partial (one leg stale/missing).
        let below90JSON = """
        [
            {"_market_id": 504, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.30, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"},
            {"_market_id": 504, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.25, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"},
            {"_market_id": 504, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.20, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"}
        ]
        """
        let below90Rows = try decoder.decode([GameMarketOther].self, from: Data(below90JSON.utf8))
        let below90Card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: below90Rows,
                status: "scheduled",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertTrue(below90Card.legs.allSatisfy { $0.quotedChance == nil && $0.pregameChance == nil })
        let withheldSheet = EventAtlasSoccerCards11666.detailsModel(for: below90Card.legs[0], card: below90Card)
        XCTAssertEqual(withheldSheet.primaryReadingValue, "No recent probability")
        XCTAssertEqual(withheldSheet.statusSummary, "Raw 3-way sum 75%")
        XCTAssertEqual(withheldSheet.statusLabel, "Raw quotes")

        let partialJSON = """
        [
            {"_market_id": 505, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.50, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"},
            {"_market_id": 505, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.28, "observed_at": "2026-11-06T16:00:00Z", "source": "kalshi"},
            {"_market_id": 505, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.25, "observed_at": "2026-11-06T17:55:00Z", "source": "kalshi"}
        ]
        """
        let partialRows = try decoder.decode([GameMarketOther].self, from: Data(partialJSON.utf8))
        let partialCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: partialRows,
                status: "scheduled",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertTrue(partialCard.legs.allSatisfy { $0.quotedChance == nil && $0.pregameChance == nil })
        XCTAssertNil(partialCard.quotedSum)
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

    @MainActor
    func testThreeWayBlendedPreferenceAndMultiSourceWithholdingWithDisagreementPending() throws {
        let now = try XCTUnwrap("2026-11-06T22:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Blended row is preferred over single-venue rows when present
        let blendedJSON = """
        [
            {"_market_id": 701, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.50, "pregame_mark": 0.50, "observed_at": "2026-11-06T21:55:00Z", "source": "kalshi"},
            {"_market_id": 701, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.25, "pregame_mark": 0.25, "observed_at": "2026-11-06T21:55:00Z", "source": "kalshi"},
            {"_market_id": 701, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.25, "pregame_mark": 0.25, "observed_at": "2026-11-06T21:55:00Z", "source": "kalshi"},
            {"_market_id": 702, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.54, "pregame_mark": 0.54, "observed_at": "2026-11-06T21:55:00Z", "source": "blended"},
            {"_market_id": 702, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.24, "pregame_mark": 0.24, "observed_at": "2026-11-06T21:55:00Z", "source": "blended"},
            {"_market_id": 702, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.22, "pregame_mark": 0.22, "observed_at": "2026-11-06T21:55:00Z", "source": "blended"}
        ]
        """
        let blendedRows = try decoder.decode([GameMarketOther].self, from: Data(blendedJSON.utf8))
        let blendedCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: blendedRows,
                status: "scheduled",
                commenceTime: "2026-11-06T23:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertEqual(blendedCard.source, "blended")
        XCTAssertEqual(blendedCard.sourceCount, 1)
        XCTAssertEqual(blendedCard.legs[0].quotedChance ?? 0, 0.54, accuracy: 1e-6)
        let blendedSheet = EventAtlasSoccerCards11666.detailsModel(for: blendedCard.legs[0], card: blendedCard)
        XCTAssertEqual(blendedSheet.sourceLabel, "Blended")

        // 2. Multiple unblended sources without a blended row withhold probabilities and grade disagreement as Pending
        let multiDisagreeJSON = """
        [
            {"_market_id": 710, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.50, "pregame_mark": 0.50, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": true, "resolution_source": "kalshi"},
            {"_market_id": 710, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.25, "pregame_mark": 0.25, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "kalshi"},
            {"_market_id": 710, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.25, "pregame_mark": 0.25, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "kalshi"},
            {"_market_id": 711, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.56, "pregame_mark": 0.56, "observed_at": "2026-11-06T19:55:00Z", "source": "polymarket", "is_winner": false, "resolution_source": "polymarket"},
            {"_market_id": 711, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.22, "pregame_mark": 0.22, "observed_at": "2026-11-06T19:55:00Z", "source": "polymarket", "is_winner": true, "resolution_source": "polymarket"},
            {"_market_id": 711, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.22, "pregame_mark": 0.22, "observed_at": "2026-11-06T19:55:00Z", "source": "polymarket", "is_winner": false, "resolution_source": "polymarket"}
        ]
        """
        let multiDisagreeRows = try decoder.decode([GameMarketOther].self, from: Data(multiDisagreeJSON.utf8))
        let multiCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: multiDisagreeRows,
                status: "completed",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertNil(multiCard.source)
        XCTAssertEqual(multiCard.sourceCount, 2)
        for leg in multiCard.legs {
            XCTAssertNil(leg.pregameChance, "Unblended multi-source probabilities must be withheld")
            XCTAssertNil(leg.quotedChance)
        }
        // Arsenal and Draw had disagreeing verdicts across Kalshi and Polymarket -> nil result -> "Pending" in sheet
        XCTAssertNil(multiCard.legs[0].result)
        XCTAssertNil(multiCard.legs[1].result)
        // Chelsea was agreed .lost across both venues
        XCTAssertEqual(multiCard.legs[2].result, .lost)

        let pendingSheet = EventAtlasSoccerCards11666.detailsModel(for: multiCard.legs[0], card: multiCard)
        XCTAssertEqual(pendingSheet.primaryReadingLabel, "Result")
        XCTAssertEqual(pendingSheet.primaryReadingValue, "Pending")
        XCTAssertEqual(pendingSheet.sourceLabel, "2 sources, not blended")
    }

    @MainActor
    func testSettledDrawAndLiveThreeWayAgingBehavior() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Settled Draw: Draw leg is .won, home/away legs are .lost, title reflects finished level
        let settledDrawJSON = """
        [
            {"_market_id": 720, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.01, "pregame_mark": 0.45, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
            {"_market_id": 720, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.99, "pregame_mark": 0.28, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": true, "resolution_source": "official_score"},
            {"_market_id": 720, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.01, "pregame_mark": 0.27, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"}
        ]
        """
        let settledDrawRows = try decoder.decode([GameMarketOther].self, from: Data(settledDrawJSON.utf8))
        let settledDrawCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: settledDrawRows,
                status: "completed",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: try XCTUnwrap("2026-11-06T22:00:00Z".asDate)
            )
        )
        XCTAssertEqual(settledDrawCard.phase, .after)
        XCTAssertEqual(settledDrawCard.title, "Finished level — a draw was the third outcome")
        XCTAssertEqual(settledDrawCard.legs[0].result, .lost)
        XCTAssertEqual(settledDrawCard.legs[1].result, .won)
        XCTAssertEqual(settledDrawCard.legs[2].result, .lost)

        // 2. Live (.during) three-way card with both pregameChance and quotedChance, plus current(at:) aging past 30m
        let liveNow = try XCTUnwrap("2026-11-06T20:30:00Z".asDate)
        let liveJSON = """
        [
            {"_market_id": 730, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.62, "pregame_mark": 0.48, "observed_at": "2026-11-06T20:25:00Z", "source": "kalshi"},
            {"_market_id": 730, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.22, "pregame_mark": 0.27, "observed_at": "2026-11-06T20:25:00Z", "source": "kalshi"},
            {"_market_id": 730, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.16, "pregame_mark": 0.25, "observed_at": "2026-11-06T20:25:00Z", "source": "kalshi"}
        ]
        """
        let liveRows = try decoder.decode([GameMarketOther].self, from: Data(liveJSON.utf8))
        let liveCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildThreeWayCard(
                matrix: nil,
                otherMarkets: liveRows,
                status: "live",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: liveNow
            )
        )
        XCTAssertEqual(liveCard.phase, .during)
        XCTAssertEqual(liveCard.legs[0].pregameChance ?? 0, 0.48, accuracy: 1e-6)
        XCTAssertEqual(liveCard.legs[0].quotedChance ?? 0, 0.62, accuracy: 1e-6)

        // Age past the 30-minute bound: quotedChance drops to nil while pregameChance stays pinned
        let staleNow = try XCTUnwrap("2026-11-06T21:00:00Z".asDate)
        let agedCard = liveCard.current(at: staleNow)
        XCTAssertNil(agedCard.legs[0].quotedChance)
        XCTAssertEqual(agedCard.legs[0].pregameChance ?? 0, 0.48, accuracy: 1e-6)
    }

    @MainActor
    func testExactScore49CellGridKeepsWinningCellAndHighestProbabilityCellsVisible() throws {
        let now = try XCTUnwrap("2026-11-06T22:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        var jsonItems: [String] = []
        for h in 0...6 {
            for a in 0...6 {
                let isWinner = (h == 3 && a == 2)
                let pregame: Double
                if h == 1 && a == 1 {
                    pregame = 0.16
                } else if h == 2 && a == 1 {
                    pregame = 0.14
                } else if h == 3 && a == 2 {
                    pregame = 0.04
                } else {
                    pregame = 0.01
                }
                let outcomeName = h == a
                    ? "Draw \(h)-\(a)"
                    : (h > a ? "Arsenal wins \(h)-\(a)" : "Chelsea wins \(a)-\(h)")
                jsonItems.append("""
                {
                    "_market_id": 801,
                    "market_name": "Exact Score",
                    "outcome_name": "\(outcomeName)",
                    "probability": \(isWinner ? 0.99 : 0.01),
                    "pregame_mark": \(pregame),
                    "observed_at": "2026-11-06T19:55:00Z",
                    "source": "kalshi",
                    "is_winner": \(isWinner ? "true" : "false"),
                    "resolution_source": "official_score"
                }
                """)
            }
        }
        let rows = try decoder.decode([GameMarketOther].self, from: Data("[\(jsonItems.joined(separator: ","))]".utf8))
        let card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: rows,
                status: "completed",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertEqual(card.cells.count, 49)
        XCTAssertEqual(card.defaultSelectedKey, "3-2")
        let visible12 = Array(card.cells.prefix(12))
        XCTAssertEqual(visible12[0].key, "3-2", "Winning cell 3-2 must sit first in the visible 12-cell slice")
        XCTAssertEqual(visible12[0].result, .won)
        XCTAssertEqual(visible12[1].key, "1-1", "Highest-probability cell 1-1 must follow immediately")
        XCTAssertEqual(visible12[2].key, "2-1", "Second-highest-probability cell 2-1 must follow next")
    }

    @MainActor
    func testCardsDeckBuilderSlotOrderAndFlagOffNoOp() throws {
        let now = try XCTUnwrap("2026-11-06T22:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let gmJSON = """
        {
            "event_id": 15305495,
            "spread": [],
            "totals": [],
            "player_props": [],
            "game_question_matrix": {
                "contract": "10238.v1",
                "display_scope": "game",
                "questions": [
                    {
                        "question_key": "q:goals:1.5",
                        "label": "Total Goals O/U 1.5",
                        "market_name": "Total Goals",
                        "typing": {"state": "typed"},
                        "kind": "count_threshold",
                        "period": {"key": "full_game"},
                        "subject": {"side": "game"},
                        "quantity": {"key": "goals"},
                        "predicate": {"relation": "ge", "line": 1.5},
                        "options": [
                            {
                                "option_key": "over:1.5",
                                "label": "Over 1.5 goals",
                                "side": "over",
                                "contributor_outcome_ids": [9100],
                                "published": {"value_state": "not_quoted", "source": "kalshi"},
                                "pregame_reading": {"state": "available", "basis": "pregame_pin", "outcome_id": 9100, "probability": 0.78, "observed_at": "2026-11-06T19:50:00Z"},
                                "result": {"state": "won"}
                            }
                        ]
                    },
                    {
                        "question_key": "q:goals:2.5",
                        "label": "Total Goals O/U 2.5",
                        "market_name": "Total Goals",
                        "typing": {"state": "typed"},
                        "kind": "count_threshold",
                        "period": {"key": "full_game"},
                        "subject": {"side": "game"},
                        "quantity": {"key": "goals"},
                        "predicate": {"relation": "ge", "line": 2.5},
                        "options": [
                            {
                                "option_key": "over:2.5",
                                "label": "Over 2.5 goals",
                                "side": "over",
                                "contributor_outcome_ids": [9101],
                                "published": {"value_state": "not_quoted", "source": "kalshi"},
                                "pregame_reading": {"state": "available", "basis": "pregame_pin", "outcome_id": 9101, "probability": 0.58, "observed_at": "2026-11-06T19:50:00Z"},
                                "result": {"state": "won"}
                            }
                        ]
                    },
                    {
                        "question_key": "q:goals:3.5",
                        "label": "Total Goals O/U 3.5",
                        "market_name": "Total Goals",
                        "typing": {"state": "typed"},
                        "kind": "count_threshold",
                        "period": {"key": "full_game"},
                        "subject": {"side": "game"},
                        "quantity": {"key": "goals"},
                        "predicate": {"relation": "ge", "line": 3.5},
                        "options": [
                            {
                                "option_key": "over:3.5",
                                "label": "Over 3.5 goals",
                                "side": "over",
                                "contributor_outcome_ids": [9102],
                                "published": {"value_state": "not_quoted", "source": "kalshi"},
                                "pregame_reading": {"state": "available", "basis": "pregame_pin", "outcome_id": 9102, "probability": 0.34, "observed_at": "2026-11-06T19:50:00Z"},
                                "result": {"state": "lost"}
                            }
                        ]
                    }
                ]
            },
            "other": [
                {"_market_id": 901, "market_name": "Match Winner", "outcome_name": "Arsenal FC", "probability": 0.99, "pregame_mark": 0.52, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": true, "resolution_source": "official_score"},
                {"_market_id": 901, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.01, "pregame_mark": 0.26, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
                {"_market_id": 901, "market_name": "Match Winner", "outcome_name": "Chelsea FC", "probability": 0.01, "pregame_mark": 0.22, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
                {"_market_id": 902, "market_name": "Exact Score", "outcome_name": "Draw 0-0", "probability": 0.01, "pregame_mark": 0.09, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
                {"_market_id": 902, "market_name": "Exact Score", "outcome_name": "Arsenal wins 1-0", "probability": 0.01, "pregame_mark": 0.14, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
                {"_market_id": 902, "market_name": "Exact Score", "outcome_name": "Draw 1-1", "probability": 0.01, "pregame_mark": 0.12, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
                {"_market_id": 902, "market_name": "Exact Score", "outcome_name": "Arsenal wins 2-1", "probability": 0.99, "pregame_mark": 0.11, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": true, "resolution_source": "official_score"}
            ]
        }
        """
        let gm = try decoder.decode(GameMarketsResponse.self, from: Data(gmJSON.utf8))

        let flagOffDeck = EventAtlasSoccerCards11666.cards(
            sportKey: "soccer_epl",
            atlasEnabled: false,
            status: "completed",
            commenceTime: "2026-11-06T20:00:00Z".asDate,
            homeTeam: "Arsenal FC",
            awayTeam: "Chelsea FC",
            homeShort: "Arsenal",
            awayShort: "Chelsea",
            homeScore: 2,
            awayScore: 1,
            gameMarkets: gm,
            now: now
        )
        XCTAssertTrue(flagOffDeck.isEmpty, "Flag-off soccer deck must return empty")

        let flagOnDeck = EventAtlasSoccerCards11666.cards(
            sportKey: "soccer_epl",
            atlasEnabled: true,
            status: "completed",
            commenceTime: "2026-11-06T20:00:00Z".asDate,
            homeTeam: "Arsenal FC",
            awayTeam: "Chelsea FC",
            homeShort: "Arsenal",
            awayShort: "Chelsea",
            homeScore: 2,
            awayScore: 1,
            gameMarkets: gm,
            now: now
        )
        XCTAssertEqual(flagOnDeck.map(\.id), ["soccer:threeWay", "soccer:exactScore", "total"])
        if case .ladder(let goalTotalLadder) = flagOnDeck[2] {
            XCTAssertEqual(goalTotalLadder.unit, "goals")
            XCTAssertEqual(goalTotalLadder.startWord, "kickoff")
            XCTAssertEqual(goalTotalLadder.caption, "Chance before kickoff of finishing above each line")
        } else {
            XCTFail("Expected third card in soccer deck to be the goals total ladder")
        }
    }

    @MainActor
    func testResolveSoccerSideDistinguishesSharedCityClubsManchesterUnitedAndManchesterCity() throws {
        XCTAssertEqual(
            EventAtlasSoccerCards11666.resolveSoccerSide(
                candidate: "Manchester United",
                homeTeam: "Manchester United",
                awayTeam: "Manchester City",
                homeShort: "Man United",
                awayShort: "Man City"
            ),
            .home
        )
        XCTAssertEqual(
            EventAtlasSoccerCards11666.resolveSoccerSide(
                candidate: "Manchester City",
                homeTeam: "Manchester United",
                awayTeam: "Manchester City",
                homeShort: "Man United",
                awayShort: "Man City"
            ),
            .away
        )
        XCTAssertNil(
            EventAtlasSoccerCards11666.resolveSoccerSide(
                candidate: "Manchester",
                homeTeam: "Manchester United",
                awayTeam: "Manchester City",
                homeShort: "Man United",
                awayShort: "Man City"
            ),
            "Ambiguous shared-city token alone must return nil"
        )
    }

    @MainActor
    func testExactScoreReadsQuestionMatrixAndAnyOtherScoreBucket() throws {
        let now = try XCTUnwrap("2026-11-06T22:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Exact score from gameMarkets.other with "Any other score" winning bucket
        let otherJSON = """
        [
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Draw 0-0", "probability": 0.01, "pregame_mark": 0.08, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Arsenal wins 1-0", "probability": 0.01, "pregame_mark": 0.14, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Draw 1-1", "probability": 0.01, "pregame_mark": 0.12, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Chelsea wins 2-1", "probability": 0.01, "pregame_mark": 0.09, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "official_score"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Any other score", "probability": 0.99, "pregame_mark": 0.04, "observed_at": "2026-11-06T19:55:00Z", "source": "kalshi", "is_winner": true, "resolution_source": "official_score"}
        ]
        """
        let otherRows = try decoder.decode([GameMarketOther].self, from: Data(otherJSON.utf8))
        let settledCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: otherRows,
                status: "completed",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        let otherCell = try XCTUnwrap(settledCard.otherCell)
        XCTAssertEqual(otherCell.outcomeLabel, "Any other score")
        XCTAssertEqual(otherCell.chance ?? 0, 0.04, accuracy: 1e-6)
        XCTAssertEqual(otherCell.result, .won)
        XCTAssertEqual(settledCard.defaultSelectedKey, "other")

        let otherSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: otherCell.id,
                cards: [.soccerExactScore(settledCard)],
                rows: [:],
                awayName: "Chelsea FC",
                homeName: "Arsenal FC"
            )
        )
        XCTAssertEqual(otherSheet.outcomeTitle, "Any other score")
        XCTAssertEqual(otherSheet.primaryReadingLabel, "Result")
        XCTAssertEqual(otherSheet.primaryReadingValue, "✓ Won")
        XCTAssertEqual(otherSheet.pregameBaseline, "4%")

        // 2. Exact score read directly from EventQuestionMatrix (10238.v1) when gameMarkets.other is empty
        let matrixJSON = """
        {
            "contract": "10238.v1",
            "event_id": 951,
            "questions": [
                {
                    "question_key": "q:exact_score",
                    "kind": "named_options",
                    "label": "Exact Score",
                    "market_name": "Exact Score",
                    "typing": {"state": "typed"},
                    "options": [
                        {
                            "option_key": "0-0",
                            "label": "Draw 0-0",
                            "contributor_outcome_ids": [9501],
                            "published": {"value_state": "quoted", "value": 0.10, "observed_at": "2026-11-06T21:55:00Z", "source": "polymarket"}
                        },
                        {
                            "option_key": "1-0",
                            "label": "Arsenal wins 1-0",
                            "contributor_outcome_ids": [9502],
                            "published": {"value_state": "quoted", "value": 0.16, "observed_at": "2026-11-06T21:55:00Z", "source": "polymarket"}
                        },
                        {
                            "option_key": "1-1",
                            "label": "Draw 1-1",
                            "contributor_outcome_ids": [9503],
                            "published": {"value_state": "quoted", "value": 0.13, "observed_at": "2026-11-06T21:55:00Z", "source": "polymarket"}
                        },
                        {
                            "option_key": "0-1",
                            "label": "Chelsea wins 1-0",
                            "contributor_outcome_ids": [9504],
                            "published": {"value_state": "quoted", "value": 0.09, "observed_at": "2026-11-06T21:55:00Z", "source": "polymarket"}
                        },
                        {
                            "option_key": "other",
                            "label": "Any other score",
                            "contributor_outcome_ids": [9505],
                            "published": {"value_state": "quoted", "value": 0.06, "observed_at": "2026-11-06T21:55:00Z", "source": "polymarket"}
                        }
                    ]
                }
            ]
        }
        """
        let matrix = try decoder.decode(EventQuestionMatrix.self, from: Data(matrixJSON.utf8))
        let matrixCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildExactScoreCard(
                matrix: matrix,
                otherMarkets: [],
                status: "scheduled",
                commenceTime: "2026-11-06T23:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: now
            )
        )
        XCTAssertEqual(matrixCard.cells.count, 4)
        XCTAssertEqual(matrixCard.defaultSelectedKey, "1-0")
        XCTAssertEqual(matrixCard.otherCell?.chance ?? 0, 0.06, accuracy: 1e-6)
        XCTAssertEqual(matrixCard.source, "polymarket")
    }

    @MainActor
    func testExactScoreCardLiveQuoteAgingBehaviorThroughDeckAndRenders390px() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let liveExactJSON = """
        [
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Draw 0-0", "probability": 0.22, "pregame_mark": 0.10, "observed_at": "2026-11-06T20:10:00Z", "source": "kalshi"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Arsenal wins 1-0", "probability": 0.28, "pregame_mark": 0.15, "observed_at": "2026-11-06T20:10:00Z", "source": "kalshi"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Draw 1-1", "probability": 0.16, "pregame_mark": 0.12, "observed_at": "2026-11-06T20:10:00Z", "source": "kalshi"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Arsenal wins 2-1", "probability": 0.11, "observed_at": "2026-11-06T20:10:00Z", "source": "kalshi"},
            {"_market_id": 950, "market_name": "Exact Score", "outcome_name": "Any other score", "probability": 0.08, "pregame_mark": 0.05, "observed_at": "2026-11-06T20:10:00Z", "source": "kalshi"}
        ]
        """
        let rows = try decoder.decode([GameMarketOther].self, from: Data(liveExactJSON.utf8))
        let freshNow = try XCTUnwrap("2026-11-06T20:12:00Z".asDate)
        let staleNow = try XCTUnwrap("2026-11-06T22:45:00Z".asDate)

        // 1. During play: fresh live quotes show quotedChance + "Recorded" mark key + "Last quote" in details
        let liveCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: rows,
                status: "in_progress",
                commenceTime: "2026-11-06T20:00:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: freshNow
            )
        )
        XCTAssertEqual(liveCard.phase, .during)
        XCTAssertEqual(
            EventAtlasSoccerCards11666.exactScoreMarkKey(for: liveCard).map(\.label),
            ["Pregame", "Recorded"]
        )
        let freshCell10 = try XCTUnwrap(liveCard.cells.first(where: { $0.key == "1-0" }))
        XCTAssertEqual(freshCell10.quotedChance ?? -1, 0.28, accuracy: 1e-6)
        XCTAssertEqual(freshCell10.chance ?? -1, 0.28, accuracy: 1e-6)
        XCTAssertEqual(freshCell10.pregameChance ?? -1, 0.15, accuracy: 1e-6)
        let freshDetails10 = EventAtlasSoccerCards11666.detailsModel(for: freshCell10, card: liveCard)
        XCTAssertEqual(freshDetails10.primaryReadingLabel, "Last quote")
        XCTAssertEqual(freshDetails10.primaryReadingValue, "28%")
        XCTAssertEqual(freshDetails10.pregameBaseline, "15%")

        let freshOther = try XCTUnwrap(liveCard.otherCell)
        XCTAssertEqual(freshOther.quotedChance ?? -1, 0.08, accuracy: 1e-6)
        XCTAssertEqual(freshOther.chance ?? -1, 0.08, accuracy: 1e-6)
        XCTAssertEqual(freshOther.pregameChance ?? -1, 0.05, accuracy: 1e-6)

        // 2. When live quote ages out via NFLEventCard9483.current(at:), quotedChance drops to nil,
        // cells with pregameMark fall back to pregameChance, cells without pregameMark become nil ("No recent price"),
        // and "Recorded" disappears from the mark-grammar key.
        guard case .soccerExactScore(let agedLiveCard) = NFLEventCard9483.soccerExactScore(liveCard).current(at: staleNow) else {
            return XCTFail("Expected .soccerExactScore from current(at:)")
        }
        XCTAssertEqual(
            EventAtlasSoccerCards11666.exactScoreMarkKey(for: agedLiveCard).map(\.label),
            ["Pregame"]
        )
        let agedCell10 = try XCTUnwrap(agedLiveCard.cells.first(where: { $0.key == "1-0" }))
        XCTAssertNil(agedCell10.quotedChance)
        XCTAssertEqual(agedCell10.chance ?? -1, 0.15, accuracy: 1e-6)
        XCTAssertEqual(agedCell10.pregameChance ?? -1, 0.15, accuracy: 1e-6)
        let agedDetails10 = EventAtlasSoccerCards11666.detailsModel(for: agedCell10, card: agedLiveCard)
        XCTAssertEqual(agedDetails10.primaryReadingLabel, "Pregame baseline")
        XCTAssertEqual(agedDetails10.primaryReadingValue, "15%")

        let agedCell21 = try XCTUnwrap(agedLiveCard.cells.first(where: { $0.key == "2-1" }))
        XCTAssertNil(agedCell21.quotedChance)
        XCTAssertNil(agedCell21.pregameChance)
        XCTAssertNil(agedCell21.chance)
        let agedDetails21 = EventAtlasSoccerCards11666.detailsModel(for: agedCell21, card: agedLiveCard)
        XCTAssertEqual(agedDetails21.primaryReadingLabel, "Reading")
        XCTAssertEqual(agedDetails21.primaryReadingValue, EventAtlasStates11666.noRecentPrice)

        let agedOther = try XCTUnwrap(agedLiveCard.otherCell)
        XCTAssertNil(agedOther.quotedChance)
        XCTAssertEqual(agedOther.chance ?? -1, 0.05, accuracy: 1e-6)
        let agedOtherDetails = EventAtlasSoccerCards11666.detailsModel(for: agedOther, card: agedLiveCard)
        XCTAssertEqual(agedOtherDetails.primaryReadingLabel, "Pregame baseline")
        XCTAssertEqual(agedOtherDetails.primaryReadingValue, "5%")

        // 3. Before kickoff: aging out drops both quotedChance and pregameChance to nil
        let pregameCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: rows,
                status: "scheduled",
                commenceTime: "2026-11-06T23:30:00Z".asDate,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "Arsenal",
                awayShort: "Chelsea",
                now: freshNow
            )
        )
        let agedPregameCard = pregameCard.current(at: staleNow)
        for cell in agedPregameCard.cells {
            XCTAssertNil(cell.quotedChance)
            XCTAssertNil(cell.pregameChance)
            XCTAssertNil(cell.chance)
        }
        XCTAssertNil(agedPregameCard.otherCell?.quotedChance)
        XCTAssertNil(agedPregameCard.otherCell?.pregameChance)
        XCTAssertNil(agedPregameCard.otherCell?.chance)

        // 4. Render 390px captures of fresh live vs aged live Exact Score card
        let state = NFLCardDeckState9483()
        let freshView = EventAtlasSoccerExactScoreCardView11666(
            card: liveCard,
            state: state
        )
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let agedView = EventAtlasSoccerExactScoreCardView11666(
            card: agedLiveCard,
            state: state
        )
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let r1 = ImageRenderer(content: freshView)
        r1.scale = 2.0
        let img1 = try XCTUnwrap(r1.uiImage)
        XCTAssertEqual(Int(img1.size.width), 390)

        let r2 = ImageRenderer(content: agedView)
        r2.scale = 2.0
        let img2 = try XCTUnwrap(r2.uiImage)
        XCTAssertEqual(Int(img2.size.width), 390)

        if let outDir = ProcessInfo.processInfo.environment["ATLAS_SOCCER_EXACT_SCORE_AGING_SCREENSHOT_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try XCTUnwrap(img1.pngData()).write(to: dirURL.appendingPathComponent("soccer-exact-score-live-fresh-390px.png"))
            try XCTUnwrap(img2.pngData()).write(to: dirURL.appendingPathComponent("soccer-exact-score-live-aged-390px.png"))
        }
    }
}
