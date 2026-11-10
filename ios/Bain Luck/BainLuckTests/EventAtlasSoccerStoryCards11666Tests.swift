import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class EventAtlasSoccerStoryCards11666Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-11-08T20:00:00Z")!
    private let commenceFuture = ISO8601DateFormatter().date(from: "2026-11-08T22:00:00Z")!
    private let commencePast = ISO8601DateFormatter().date(from: "2026-11-08T18:30:00Z")!

    private func makeOtherRow(
        marketName: String,
        outcomeName: String,
        probability: Double,
        pregameMark: Double? = nil,
        observedAt: String? = "2026-11-08T19:55:00Z",
        result: Bool? = nil,
        resolutionSource: String? = nil,
        source: String? = "kalshi",
        marketId: Int? = 501
    ) throws -> GameMarketOther {
        var dict: [String: Any] = [
            "market_name": marketName,
            "outcome_name": outcomeName,
            "probability": probability
        ]
        if let pregameMark { dict["pregame_mark"] = pregameMark }
        if let observedAt { dict["observed_at"] = observedAt }
        if let result {
            dict["is_winner"] = result
            dict["resolution_source"] = resolutionSource ?? "api_settlement"
        }
        if let source { dict["source"] = source }
        if let marketId { dict["_market_id"] = marketId }
        let data = try JSONSerialization.data(withJSONObject: dict)
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(GameMarketOther.self, from: data)
    }

    func testBothTeamsToScoreCardPreservesIndependentYesNoQuotesAndGoalsSummaryWithoutSelfGrading() throws {
        let rows: [GameMarketOther] = [
            try makeOtherRow(
                marketName: "Both Teams to Score",
                outcomeName: "Yes",
                probability: 0.62,
                pregameMark: 0.55,
                marketId: 701
            ),
            try makeOtherRow(
                marketName: "Both Teams to Score",
                outcomeName: "No",
                probability: 0.41,
                pregameMark: 0.46,
                marketId: 701
            ),
            // Half-scoped BTTS must be ignored by full-game BTTS builder
            try makeOtherRow(
                marketName: "1st Half Both Teams to Score",
                outcomeName: "Yes",
                probability: 0.25,
                pregameMark: 0.22,
                marketId: 702
            ),
            try makeOtherRow(
                marketName: "1st Half Both Teams to Score",
                outcomeName: "No",
                probability: 0.75,
                pregameMark: 0.78,
                marketId: 702
            )
        ]

        let card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildBothTeamsToScoreCard(
                matrix: nil,
                otherMarkets: rows,
                status: "live",
                commenceTime: commencePast,
                homeShort: "ARS",
                awayShort: "CHE",
                homeScore: 1,
                awayScore: 1,
                now: now
            )
        )

        XCTAssertEqual(card.id, "soccer:bothTeamsToScore")
        XCTAssertEqual(card.phase, .during)
        XCTAssertEqual(card.legs.count, 2)
        // Independent probabilities preserved (0.62 + 0.41 = 1.03, never normalized)
        XCTAssertEqual(card.legs[0].role, .yes)
        XCTAssertEqual(card.legs[0].quotedChance ?? -1, 0.62, accuracy: 0.0001)
        XCTAssertEqual(card.legs[0].pregameChance ?? -1, 0.55, accuracy: 0.0001)
        // Even though both teams have scored (1-1), in-play result is nil (never self-graded)
        XCTAssertNil(card.legs[0].result)
        XCTAssertEqual(card.legs[1].role, .no)
        XCTAssertEqual(card.legs[1].quotedChance ?? -1, 0.41, accuracy: 0.0001)
        XCTAssertEqual(card.legs[1].pregameChance ?? -1, 0.46, accuracy: 0.0001)
        XCTAssertNil(card.legs[1].result)
        XCTAssertEqual(
            card.scoring?.summaryText,
            "Goals so far: ARS 1 (Has scored) · CHE 1 (Has scored)"
        )

        // Aging past 30 minutes clears live quote while keeping pregame mark
        let later = now.addingTimeInterval(40 * 60)
        let aged = card.current(at: later)
        XCTAssertNil(aged.legs[0].quotedChance)
        XCTAssertEqual(aged.legs[0].pregameChance ?? -1, 0.55, accuracy: 0.0001)

        // A single-leg BTTS market is refused (never complements No = 1 - Yes)
        let oneLegOnly = [rows[0]]
        XCTAssertNil(
            EventAtlasSoccerCards11666.buildBothTeamsToScoreCard(
                matrix: nil,
                otherMarkets: oneLegOnly,
                status: "live",
                commenceTime: commencePast,
                homeShort: "ARS",
                awayShort: "CHE",
                homeScore: 1,
                awayScore: 0,
                now: now
            )
        )
    }

    func testBothTeamsToScoreSettledVerdictsAndPreKickoffDetailsOmitDuplicatePregameRow() throws {
        let pregameRows: [GameMarketOther] = [
            try makeOtherRow(
                marketName: "Both Teams to Score",
                outcomeName: "Yes",
                probability: 0.56,
                pregameMark: 0.54,
                source: "kalshi",
                marketId: 710
            ),
            try makeOtherRow(
                marketName: "Both Teams to Score",
                outcomeName: "No",
                probability: 0.45,
                pregameMark: 0.47,
                source: "polymarket",
                marketId: 710
            )
        ]

        let pregameCard = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildBothTeamsToScoreCard(
                matrix: nil,
                otherMarkets: pregameRows,
                status: "scheduled",
                commenceTime: commenceFuture,
                homeShort: "ARS",
                awayShort: "CHE",
                homeScore: nil,
                awayScore: nil,
                now: now
            )
        )
        XCTAssertEqual(pregameCard.phase, .before)
        XCTAssertNil(pregameCard.scoring)
        let pregameDetails = EventAtlasSoccerCards11666.detailsModel(
            for: pregameCard.legs[0],
            card: pregameCard
        )
        XCTAssertEqual(pregameDetails.primaryReadingLabel, "Last quote")
        XCTAssertEqual(pregameDetails.primaryReadingValue, "56%")
        XCTAssertNil(pregameDetails.pregameBaseline)

        // Multi-source card with nil leg source reports "2 sources, not blended"
        let multiSourceCard = EventAtlasSoccerCards11666.BothTeamsToScoreCard(
            phase: .after,
            legs: [
                EventAtlasSoccerCards11666.BTTSLeg(
                    role: .yes,
                    label: "Yes",
                    rawOutcomeLabel: "Yes",
                    quotedChance: nil,
                    pregameChance: 0.55,
                    observedAt: "2026-11-08T18:25:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: .won,
                    source: nil
                ),
                EventAtlasSoccerCards11666.BTTSLeg(
                    role: .no,
                    label: "No",
                    rawOutcomeLabel: "No",
                    quotedChance: nil,
                    pregameChance: 0.45,
                    observedAt: "2026-11-08T18:25:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: nil,
                    source: nil
                )
            ],
            scoring: .final(homeShort: "ARS", homeGoals: 2, awayShort: "CHE", awayGoals: 1),
            marketTitle: "Both Teams to Score",
            source: nil,
            sourceCount: 2
        )
        let yesDetails = EventAtlasSoccerCards11666.detailsModel(for: multiSourceCard.legs[0], card: multiSourceCard)
        XCTAssertEqual(yesDetails.primaryReadingValue, EventAtlasStates11666.wonWithCheck)
        XCTAssertEqual(yesDetails.pregameBaseline, "55%")
        XCTAssertEqual(yesDetails.sourceLabel, "2 sources, not blended")

        let noDetails = EventAtlasSoccerCards11666.detailsModel(for: multiSourceCard.legs[1], card: multiSourceCard)
        XCTAssertEqual(noDetails.primaryReadingValue, EventAtlasStates11666.resultNotConfirmed)

        // Decide 80-A (#12449): tier 0 (binary_higher_wins), tier 1 (clean_resolution), and
        // tier 2 (game_score) rows with is_winner: false at the final read "Result not confirmed",
        // and an authoritative winner reads "✓ Won" across BTTS, First Team, and Halves cards.
        for nonAuthSource in ["binary_higher_wins", "clean_resolution", "game_score"] {
            let finalRows: [GameMarketOther] = [
                try makeOtherRow(
                    marketName: "Both Teams to Score",
                    outcomeName: "Yes",
                    probability: 0.99,
                    pregameMark: 0.55,
                    result: true,
                    resolutionSource: "api_settlement",
                    marketId: 750
                ),
                try makeOtherRow(
                    marketName: "Both Teams to Score",
                    outcomeName: "No",
                    probability: 0.01,
                    pregameMark: 0.45,
                    result: false,
                    resolutionSource: nonAuthSource,
                    marketId: 750
                ),
                try makeOtherRow(
                    marketName: "First Team to Score",
                    outcomeName: "Arsenal FC",
                    probability: 0.99,
                    pregameMark: 0.48,
                    result: true,
                    resolutionSource: "api_settlement",
                    marketId: 751
                ),
                try makeOtherRow(
                    marketName: "First Team to Score",
                    outcomeName: "Chelsea FC",
                    probability: 0.01,
                    pregameMark: 0.37,
                    result: false,
                    resolutionSource: nonAuthSource,
                    marketId: 751
                ),
                try makeOtherRow(
                    marketName: "First Team to Score",
                    outcomeName: "No goal",
                    probability: 0.01,
                    pregameMark: 0.15,
                    result: false,
                    resolutionSource: nonAuthSource,
                    marketId: 751
                ),
                try makeOtherRow(
                    marketName: "1st Half Result",
                    outcomeName: "Arsenal FC",
                    probability: 0.99,
                    pregameMark: 0.40,
                    result: true,
                    resolutionSource: "api_settlement",
                    marketId: 752
                ),
                try makeOtherRow(
                    marketName: "1st Half Result",
                    outcomeName: "Draw",
                    probability: 0.01,
                    pregameMark: 0.36,
                    result: false,
                    resolutionSource: nonAuthSource,
                    marketId: 752
                ),
                try makeOtherRow(
                    marketName: "1st Half Result",
                    outcomeName: "Chelsea FC",
                    probability: 0.01,
                    pregameMark: 0.24,
                    result: false,
                    resolutionSource: nonAuthSource,
                    marketId: 752
                )
            ]

            let bttsFinal = try XCTUnwrap(
                EventAtlasSoccerCards11666.buildBothTeamsToScoreCard(
                    matrix: nil,
                    otherMarkets: finalRows,
                    status: "completed",
                    commenceTime: commencePast,
                    homeShort: "ARS",
                    awayShort: "CHE",
                    homeScore: 2,
                    awayScore: 1,
                    now: now
                )
            )
            XCTAssertEqual(
                EventAtlasSoccerCards11666.detailsModel(for: bttsFinal.legs[0], card: bttsFinal).primaryReadingValue,
                "✓ Won"
            )
            XCTAssertEqual(
                EventAtlasSoccerCards11666.detailsModel(for: bttsFinal.legs[1], card: bttsFinal).primaryReadingValue,
                "Result not confirmed",
                "Tier 0/1/2 source \(nonAuthSource) with is_winner: false must read 'Result not confirmed'"
            )

            let firstTeamFinal = try XCTUnwrap(
                EventAtlasSoccerCards11666.buildFirstTeamToScoreCard(
                    matrix: nil,
                    otherMarkets: finalRows,
                    status: "completed",
                    commenceTime: commencePast,
                    homeTeam: "Arsenal FC",
                    awayTeam: "Chelsea FC",
                    homeShort: "ARS",
                    awayShort: "CHE",
                    now: now
                )
            )
            XCTAssertEqual(
                EventAtlasSoccerCards11666.detailsModel(for: firstTeamFinal.legs[0], card: firstTeamFinal).primaryReadingValue,
                "✓ Won"
            )
            XCTAssertEqual(
                EventAtlasSoccerCards11666.detailsModel(for: firstTeamFinal.legs[1], card: firstTeamFinal).primaryReadingValue,
                "Result not confirmed",
                "Tier 0/1/2 source \(nonAuthSource) with is_winner: false must read 'Result not confirmed'"
            )

            let halvesFinal = try XCTUnwrap(
                EventAtlasSoccerCards11666.buildHalvesCard(
                    matrix: nil,
                    otherMarkets: finalRows,
                    status: "completed",
                    commenceTime: commencePast,
                    homeTeam: "Arsenal FC",
                    awayTeam: "Chelsea FC",
                    homeShort: "ARS",
                    awayShort: "CHE",
                    now: now
                )
            )
            let halfSection = try XCTUnwrap(halvesFinal.sections.first)
            XCTAssertEqual(
                EventAtlasSoccerCards11666.detailsModel(for: halfSection.legs[0], section: halfSection, card: halvesFinal).primaryReadingValue,
                "✓ Won"
            )
            XCTAssertEqual(
                EventAtlasSoccerCards11666.detailsModel(for: halfSection.legs[1], section: halfSection, card: halvesFinal).primaryReadingValue,
                "Result not confirmed",
                "Tier 0/1/2 source \(nonAuthSource) with is_winner: false must read 'Result not confirmed'"
            )
        }
    }

    func testFirstTeamToScoreCardPreservesHomeAwayNoGoalAndObservedScoreCheckpoints() throws {
        let rows: [GameMarketOther] = [
            try makeOtherRow(
                marketName: "First Team to Score",
                outcomeName: "Arsenal FC",
                probability: 0.52,
                pregameMark: 0.48,
                marketId: 801
            ),
            try makeOtherRow(
                marketName: "First Team to Score",
                outcomeName: "Chelsea FC",
                probability: 0.36,
                pregameMark: 0.39,
                marketId: 801
            ),
            try makeOtherRow(
                marketName: "First Team to Score",
                outcomeName: "No goal",
                probability: 0.14,
                pregameMark: 0.15,
                marketId: 801
            )
        ]

        let historyJSON = """
        [
            {"timestamp": "2026-11-08T18:35:00Z", "home_score": 0, "away_score": 0},
            {"timestamp": "2026-11-08T18:40:00Z", "home_score": 0, "away_score": 0},
            {"timestamp": "2026-11-08T19:02:00Z", "home_score": 1, "away_score": 0},
            {"timestamp": "2026-11-08T19:41:00Z", "home_score": 1, "away_score": 1}
        ]
        """.data(using: .utf8)!
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let scorePoints = try dec.decode([ScoreHistoryPoint].self, from: historyJSON)

        let card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildFirstTeamToScoreCard(
                matrix: nil,
                otherMarkets: rows,
                scoreHistory: scorePoints,
                status: "live",
                commenceTime: commencePast,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "ARS",
                awayShort: "CHE",
                now: now
            )
        )

        XCTAssertEqual(card.id, "soccer:firstTeamToScore")
        XCTAssertEqual(card.legs.map(\.role), [.home, .away, .noGoal])
        XCTAssertEqual(card.legs.map(\.label), ["ARS", "CHE", "No goal"])
        XCTAssertEqual(card.legs[2].quotedChance ?? -1, 0.14, accuracy: 0.0001)
        // Consecutive duplicate (0-0) collapsed into 3 distinct observed score checkpoints
        XCTAssertEqual(card.checkpoints.count, 3)
        XCTAssertEqual(card.checkpoints.map(\.scoreText), ["ARS 0 – 0 CHE", "ARS 1 – 0 CHE", "ARS 1 – 1 CHE"])
        // Never infers a winner from score checkpoints during play
        XCTAssertTrue(card.legs.allSatisfy { $0.result == nil })
    }

    func testHalvesCardBuildsFirstAndSecondHalfThreeWayAndRefusesTwoWayOrNonThreeWayHalfMarkets() throws {
        let rows: [GameMarketOther] = [
            try makeOtherRow(marketName: "1st Half Result", outcomeName: "Arsenal FC", probability: 0.42, pregameMark: 0.40, marketId: 901),
            try makeOtherRow(marketName: "1st Half Result", outcomeName: "Draw", probability: 0.35, pregameMark: 0.37, marketId: 901),
            try makeOtherRow(marketName: "1st Half Result", outcomeName: "Chelsea FC", probability: 0.25, pregameMark: 0.24, marketId: 901),
            try makeOtherRow(marketName: "2nd Half Result", outcomeName: "Arsenal FC", probability: 0.44, pregameMark: 0.43, marketId: 902),
            try makeOtherRow(marketName: "2nd Half Result", outcomeName: "Draw", probability: 0.31, pregameMark: 0.32, marketId: 902),
            try makeOtherRow(marketName: "2nd Half Result", outcomeName: "Chelsea FC", probability: 0.27, pregameMark: 0.26, marketId: 902),
            // 2-way half market (missing Draw) must be refused
            try makeOtherRow(marketName: "1st Half Draw No Bet", outcomeName: "Arsenal FC", probability: 0.62, pregameMark: 0.60, marketId: 903),
            try makeOtherRow(marketName: "1st Half Draw No Bet", outcomeName: "Chelsea FC", probability: 0.38, pregameMark: 0.40, marketId: 903)
        ]

        let boxJSON = """
        {
            "home_period_scores": [1, 1],
            "away_period_scores": [0, 1]
        }
        """.data(using: .utf8)!
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let box = try dec.decode(EventBoxScoreData.self, from: boxJSON)

        let card = try XCTUnwrap(
            EventAtlasSoccerCards11666.buildHalvesCard(
                matrix: nil,
                otherMarkets: rows,
                boxScoreData: box,
                status: "live",
                commenceTime: commencePast,
                homeTeam: "Arsenal FC",
                awayTeam: "Chelsea FC",
                homeShort: "ARS",
                awayShort: "CHE",
                now: now
            )
        )

        XCTAssertEqual(card.id, "soccer:halves")
        XCTAssertEqual(card.sections.map(\.period), [.firstHalf, .secondHalf])
        XCTAssertEqual(card.sections[0].homeGoals, 1)
        XCTAssertEqual(card.sections[0].awayGoals, 0)
        XCTAssertEqual(card.sections[0].legs.map(\.role), [.home, .draw, .away])
        XCTAssertEqual(card.sections[1].homeGoals, 1)
        XCTAssertEqual(card.sections[1].awayGoals, 1)
    }

    func testCompleteSoccerDeckOrderAndDetailsRouting() throws {
        let rows: [GameMarketOther] = [
            try makeOtherRow(marketName: "Match Winner", outcomeName: "Arsenal FC", probability: 0.48, pregameMark: 0.45, marketId: 601),
            try makeOtherRow(marketName: "Match Winner", outcomeName: "Draw", probability: 0.27, pregameMark: 0.28, marketId: 601),
            try makeOtherRow(marketName: "Match Winner", outcomeName: "Chelsea FC", probability: 0.25, pregameMark: 0.27, marketId: 601),
            try makeOtherRow(marketName: "Both Teams to Score", outcomeName: "Yes", probability: 0.58, pregameMark: 0.55, marketId: 602),
            try makeOtherRow(marketName: "Both Teams to Score", outcomeName: "No", probability: 0.43, pregameMark: 0.46, marketId: 602),
            try makeOtherRow(marketName: "First Team to Score", outcomeName: "Arsenal FC", probability: 0.50, pregameMark: 0.48, marketId: 603),
            try makeOtherRow(marketName: "First Team to Score", outcomeName: "Chelsea FC", probability: 0.36, pregameMark: 0.37, marketId: 603),
            try makeOtherRow(marketName: "First Team to Score", outcomeName: "No goal", probability: 0.14, pregameMark: 0.15, marketId: 603),
            try makeOtherRow(marketName: "1st Half Result", outcomeName: "Arsenal FC", probability: 0.40, pregameMark: 0.39, marketId: 604),
            try makeOtherRow(marketName: "1st Half Result", outcomeName: "Draw", probability: 0.36, pregameMark: 0.37, marketId: 604),
            try makeOtherRow(marketName: "1st Half Result", outcomeName: "Chelsea FC", probability: 0.24, pregameMark: 0.24, marketId: 604),
            try makeOtherRow(marketName: "Exact Score", outcomeName: "1-0", probability: 0.14, pregameMark: 0.13, marketId: 605),
            try makeOtherRow(marketName: "Exact Score", outcomeName: "1-1", probability: 0.12, pregameMark: 0.12, marketId: 605),
            try makeOtherRow(marketName: "Exact Score", outcomeName: "0-0", probability: 0.09, pregameMark: 0.10, marketId: 605),
            try makeOtherRow(marketName: "Exact Score", outcomeName: "2-1", probability: 0.11, pregameMark: 0.10, marketId: 605)
        ]

        let gm = GameMarketsResponse(
            eventId: 9901,
            homeTeam: "Arsenal FC",
            awayTeam: "Chelsea FC",
            status: "live",
            homeScore: 1,
            awayScore: 1,
            playerProps: [],
            spreads: [],
            totals: [],
            other: rows,
            pace: nil,
            gameQuestionMatrix: nil
        )

        let cards = EventAtlasSoccerCards11666.cards(
            sportKey: "soccer_epl",
            atlasEnabled: true,
            status: "live",
            commenceTime: commencePast,
            homeTeam: "Arsenal FC",
            awayTeam: "Chelsea FC",
            homeShort: "ARS",
            awayShort: "CHE",
            homeScore: 1,
            awayScore: 1,
            gameMarkets: gm,
            now: now
        )

        XCTAssertEqual(
            cards.map { $0.id },
            [
                "soccer:threeWay",
                "soccer:bothTeamsToScore",
                "soccer:firstTeamToScore",
                "soccer:halves",
                "soccer:exactScore"
            ]
        )

        let bttsModel = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: "soccer-btts:yes",
                cards: cards,
                rows: [:],
                awayName: "CHE",
                homeName: "ARS"
            )
        )
        XCTAssertEqual(bttsModel.outcomeTitle, "Both teams to score · Yes")
        XCTAssertEqual(bttsModel.primaryReadingValue, "58%")
        XCTAssertEqual(bttsModel.pregameBaseline, "55%")

        let firstTeamModel = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: "soccer-first-team:noGoal",
                cards: cards,
                rows: [:],
                awayName: "CHE",
                homeName: "ARS"
            )
        )
        XCTAssertEqual(firstTeamModel.outcomeTitle, "First team to score · No goal")
        XCTAssertEqual(firstTeamModel.primaryReadingValue, "14%")

        let halfModel = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: "soccer-half:1H:draw",
                cards: cards,
                rows: [:],
                awayName: "CHE",
                homeName: "ARS"
            )
        )
        XCTAssertEqual(halfModel.outcomeTitle, "1st Half · Draw")
        XCTAssertEqual(halfModel.primaryReadingValue, "36%")
    }

    func testRenderSoccerStoryCardsSnapshots390px() throws {
        let bttsCard = EventAtlasSoccerCards11666.BothTeamsToScoreCard(
            phase: .during,
            legs: [
                EventAtlasSoccerCards11666.BTTSLeg(
                    role: .yes,
                    label: "Yes",
                    rawOutcomeLabel: "Yes",
                    quotedChance: 0.62,
                    pregameChance: 0.55,
                    observedAt: "2026-11-08T19:55:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: nil,
                    source: "kalshi"
                ),
                EventAtlasSoccerCards11666.BTTSLeg(
                    role: .no,
                    label: "No",
                    rawOutcomeLabel: "No",
                    quotedChance: 0.41,
                    pregameChance: 0.46,
                    observedAt: "2026-11-08T19:55:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: nil,
                    source: "kalshi"
                )
            ],
            scoring: .live(homeShort: "ARS", homeGoals: 1, awayShort: "CHE", awayGoals: 1),
            marketTitle: "Both Teams to Score",
            source: "kalshi",
            sourceCount: 1
        )

        let firstTeamCard = EventAtlasSoccerCards11666.FirstTeamToScoreCard(
            phase: .during,
            legs: [
                EventAtlasSoccerCards11666.FirstTeamLeg(
                    role: .home,
                    label: "ARS",
                    rawOutcomeLabel: "Arsenal FC",
                    quotedChance: 0.52,
                    pregameChance: 0.48,
                    observedAt: "2026-11-08T19:55:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: nil,
                    source: "kalshi"
                ),
                EventAtlasSoccerCards11666.FirstTeamLeg(
                    role: .away,
                    label: "CHE",
                    rawOutcomeLabel: "Chelsea FC",
                    quotedChance: 0.36,
                    pregameChance: 0.39,
                    observedAt: "2026-11-08T19:55:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: nil,
                    source: "kalshi"
                ),
                EventAtlasSoccerCards11666.FirstTeamLeg(
                    role: .noGoal,
                    label: "No goal",
                    rawOutcomeLabel: "No goal",
                    quotedChance: 0.14,
                    pregameChance: 0.15,
                    observedAt: "2026-11-08T19:55:00Z",
                    pregameObservedAt: "2026-11-08T18:25:00Z",
                    result: nil,
                    source: "kalshi"
                )
            ],
            checkpoints: [
                EventAtlasSoccerCards11666.ScoreCheckpoint(
                    id: "cp-0",
                    scoreText: "ARS 0 – 0 CHE",
                    observedAtText: "10:35 AM PT"
                ),
                EventAtlasSoccerCards11666.ScoreCheckpoint(
                    id: "cp-1",
                    scoreText: "ARS 1 – 0 CHE",
                    observedAtText: "11:02 AM PT"
                ),
                EventAtlasSoccerCards11666.ScoreCheckpoint(
                    id: "cp-2",
                    scoreText: "ARS 1 – 1 CHE",
                    observedAtText: "11:41 AM PT"
                )
            ],
            marketTitle: "First Team to Score",
            source: "kalshi",
            sourceCount: 1
        )

        let halvesCard = EventAtlasSoccerCards11666.HalvesCard(
            phase: .during,
            sections: [
                EventAtlasSoccerCards11666.HalfSection(
                    period: .firstHalf,
                    legs: [
                        EventAtlasSoccerCards11666.HalfLeg(
                            period: .firstHalf,
                            role: .home,
                            label: "ARS",
                            rawOutcomeLabel: "Arsenal FC",
                            quotedChance: 0.58,
                            pregameChance: 0.42,
                            observedAt: "2026-11-08T19:55:00Z",
                            pregameObservedAt: "2026-11-08T18:25:00Z",
                            result: nil,
                            source: "kalshi"
                        ),
                        EventAtlasSoccerCards11666.HalfLeg(
                            period: .firstHalf,
                            role: .draw,
                            label: "Draw",
                            rawOutcomeLabel: "Draw",
                            quotedChance: 0.28,
                            pregameChance: 0.35,
                            observedAt: "2026-11-08T19:55:00Z",
                            pregameObservedAt: "2026-11-08T18:25:00Z",
                            result: nil,
                            source: "kalshi"
                        ),
                        EventAtlasSoccerCards11666.HalfLeg(
                            period: .firstHalf,
                            role: .away,
                            label: "CHE",
                            rawOutcomeLabel: "Chelsea FC",
                            quotedChance: 0.14,
                            pregameChance: 0.25,
                            observedAt: "2026-11-08T19:55:00Z",
                            pregameObservedAt: "2026-11-08T18:25:00Z",
                            result: nil,
                            source: "kalshi"
                        )
                    ],
                    awayGoals: 0,
                    homeGoals: 1,
                    marketTitle: "1st Half Result",
                    source: "kalshi",
                    sourceCount: 1
                ),
                EventAtlasSoccerCards11666.HalfSection(
                    period: .secondHalf,
                    legs: [
                        EventAtlasSoccerCards11666.HalfLeg(
                            period: .secondHalf,
                            role: .home,
                            label: "ARS",
                            rawOutcomeLabel: "Arsenal FC",
                            quotedChance: 0.44,
                            pregameChance: 0.43,
                            observedAt: "2026-11-08T19:55:00Z",
                            pregameObservedAt: "2026-11-08T18:25:00Z",
                            result: nil,
                            source: "kalshi"
                        ),
                        EventAtlasSoccerCards11666.HalfLeg(
                            period: .secondHalf,
                            role: .draw,
                            label: "Draw",
                            rawOutcomeLabel: "Draw",
                            quotedChance: 0.31,
                            pregameChance: 0.32,
                            observedAt: "2026-11-08T19:55:00Z",
                            pregameObservedAt: "2026-11-08T18:25:00Z",
                            result: nil,
                            source: "kalshi"
                        ),
                        EventAtlasSoccerCards11666.HalfLeg(
                            period: .secondHalf,
                            role: .away,
                            label: "CHE",
                            rawOutcomeLabel: "Chelsea FC",
                            quotedChance: 0.25,
                            pregameChance: 0.26,
                            observedAt: "2026-11-08T19:55:00Z",
                            pregameObservedAt: "2026-11-08T18:25:00Z",
                            result: nil,
                            source: "kalshi"
                        )
                    ],
                    awayGoals: 1,
                    homeGoals: 1,
                    marketTitle: "2nd Half Result",
                    source: "kalshi",
                    sourceCount: 1
                )
            ],
            awayShort: "CHE",
            homeShort: "ARS"
        )

        let state = NFLCardDeckState9483()
        let awayColor = Color(red: 0.01, green: 0.28, blue: 0.58)
        let homeColor = Color(red: 0.85, green: 0.08, blue: 0.15)

        let stack = VStack(spacing: 16) {
            EventAtlasSoccerBothTeamsCardView11666(card: bttsCard, state: state, expanded: true)
                .padding(14)
                .background(Color(UIColor.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
            EventAtlasSoccerFirstTeamCardView11666(card: firstTeamCard, awayColor: awayColor, homeColor: homeColor, state: state, expanded: true)
                .padding(14)
                .background(Color(UIColor.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
            EventAtlasSoccerHalvesCardView11666(card: halvesCard, awayColor: awayColor, homeColor: homeColor, state: state, expanded: true)
                .padding(14)
                .background(Color(UIColor.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(UIColor.systemGroupedBackground))

        let defaultRenderer = rendererForMeasurement(stack.environment(\.colorScheme, .light))
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1)

        let a11yRenderer = rendererForMeasurement(
            stack
                .environment(\.colorScheme, .light)
                .environment(\.dynamicTypeSize, .accessibility3)
        )
        a11yRenderer.scale = 2.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1)

        if let outDir = ProcessInfo.processInfo.environment["SOCCER_STORY_CARDS_SNAP_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            if let png1 = defaultImage.pngData() {
                try png1.write(to: dirURL.appendingPathComponent("soccer-story-cards-default-390px.png"))
            }
            if let png2 = a11yImage.pngData() {
                try png2.write(to: dirURL.appendingPathComponent("soccer-story-cards-a11y-390px.png"))
            }
        }
    }
}
