import XCTest
import SwiftUI
import UIKit
@testable import Bain_Luck

/// #11666 Step E6d — Native Event-page Atlas Tennis story cards (`tennis_*`),
/// mirroring web `#11974` Step E6d (`frontend/lib/tennisEventCards.ts`), gated
/// behind `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasTennisCardsE6d_11666Tests: XCTestCase {

    func testGatesTennisAtlasCardsStrictlyOnAtlasEnabledAndTennisSportPrefix() {
        XCTAssertFalse(EventAtlasTennisCards11666.applies(sportKey: "tennis_atp_paris_masters", atlasEnabled: false))
        XCTAssertTrue(EventAtlasTennisCards11666.applies(sportKey: "tennis_atp_paris_masters", atlasEnabled: true))
        XCTAssertTrue(EventAtlasTennisCards11666.applies(sportKey: "tennis_wta_finals", atlasEnabled: true))
        XCTAssertTrue(EventAtlasTennisCards11666.applies(sportKey: "tennis_other", atlasEnabled: true))
        XCTAssertFalse(EventAtlasTennisCards11666.applies(sportKey: "soccer_epl", atlasEnabled: true))
        XCTAssertFalse(EventAtlasTennisCards11666.applies(sportKey: nil, atlasEnabled: true))
    }

    func testMatchesTennisPlayerSidesAcrossFourTiersRejectsShortSubstringsAndSharedSurnameAmbiguity() {
        // Tier 1: Exact full name (with accents/whitespace)
        XCTAssertEqual(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "  Carlos   Alcaraz ",
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton"
            ),
            .home
        )
        XCTAssertEqual(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Jiří Lehečka",
                homeTeam: "Jiri Lehecka",
                awayTeam: "Ben Shelton",
                homeShort: "Lehecka",
                awayShort: "Shelton"
            ),
            .home
        )

        // Tier 2: Exact short name
        XCTAssertEqual(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Shelton",
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton"
            ),
            .away
        )

        // Tier 3: Substring (>= 3 chars) vs < 3 chars rejected
        XCTAssertEqual(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Carlos Alcaraz Garfia",
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton"
            ),
            .home
        )
        XCTAssertNil(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Al",
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton"
            )
        )

        // Tier 4: Surname token match & shared-surname ambiguity rejected
        XCTAssertEqual(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "B. Shelton",
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton"
            ),
            .away
        )
        XCTAssertNil(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Williams",
                homeTeam: "Venus Williams",
                awayTeam: "Serena Williams",
                homeShort: "V. Williams",
                awayShort: "S. Williams"
            )
        )
    }

    @MainActor
    func testBuildsFinishedSetsExactScoreAndTotalGamesDeckWithoutInventingUnquotedSetsOrGamesActual() throws {
        let now = try XCTUnwrap("2026-11-08T15:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let gmJSON = """
        {
            "event_id": 15343950,
            "home_team": "Carlos Alcaraz",
            "away_team": "Ben Shelton",
            "status": "completed",
            "home_score": 2,
            "away_score": 1,
            "game_question_matrix": {
                "contract": "10238.v1",
                "event_id": 15343950,
                "status": "completed",
                "questions": [
                    {
                        "question_key": "m:701",
                        "typed": false,
                        "kind": "named_options",
                        "label": "Set 1 Winner",
                        "market_name": "Set 1 Winner",
                        "options": [
                            {
                                "option_key": "o:701-home",
                                "label": "Carlos Alcaraz",
                                "side": "home",
                                "contributor_outcome_ids": [7011],
                                "published": {
                                    "value": 0.68,
                                    "value_state": "quoted",
                                    "basis": "recent_quote",
                                    "source": "kalshi",
                                    "observed_at": "2026-11-08T11:55:00Z"
                                },
                                "pregame_reading": {
                                    "state": "available",
                                    "basis": "pregame_pin",
                                    "probability": 0.68,
                                    "observed_at": "2026-11-08T11:55:00Z",
                                    "outcome_id": 7011,
                                    "source": "kalshi"
                                },
                                "result": {
                                    "state": "won",
                                    "is_winner": true,
                                    "evidence_kind": "authoritative"
                                }
                            },
                            {
                                "option_key": "o:701-away",
                                "label": "Ben Shelton",
                                "side": "away",
                                "contributor_outcome_ids": [7012],
                                "published": {
                                    "value": 0.32,
                                    "value_state": "quoted",
                                    "basis": "recent_quote",
                                    "source": "kalshi",
                                    "observed_at": "2026-11-08T11:55:00Z"
                                },
                                "pregame_reading": {
                                    "state": "available",
                                    "basis": "pregame_pin",
                                    "probability": 0.32,
                                    "observed_at": "2026-11-08T11:55:00Z",
                                    "outcome_id": 7012,
                                    "source": "kalshi"
                                },
                                "result": {
                                    "state": "lost",
                                    "is_winner": false,
                                    "evidence_kind": "authoritative"
                                }
                            }
                        ]
                    },
                    {
                        "question_key": "m:702",
                        "typed": false,
                        "kind": "named_options",
                        "label": "Exact Match Score",
                        "market_name": "Exact Match Score",
                        "options": [
                            {
                                "option_key": "o:702-20",
                                "label": "Carlos Alcaraz wins 2-0",
                                "contributor_outcome_ids": [7021],
                                "published": {
                                    "value": 0.45,
                                    "value_state": "quoted",
                                    "basis": "recent_quote",
                                    "source": "kalshi",
                                    "observed_at": "2026-11-08T11:55:00Z"
                                },
                                "pregame_reading": {
                                    "state": "available",
                                    "basis": "pregame_pin",
                                    "probability": 0.45,
                                    "observed_at": "2026-11-08T11:55:00Z",
                                    "outcome_id": 7021,
                                    "source": "kalshi"
                                },
                                "result": {
                                    "state": "lost",
                                    "is_winner": false,
                                    "evidence_kind": "authoritative"
                                }
                            },
                            {
                                "option_key": "o:702-21",
                                "label": "Carlos Alcaraz wins 2-1",
                                "contributor_outcome_ids": [7022],
                                "published": {
                                    "value": 0.24,
                                    "value_state": "quoted",
                                    "basis": "recent_quote",
                                    "source": "kalshi",
                                    "observed_at": "2026-11-08T11:55:00Z"
                                },
                                "pregame_reading": {
                                    "state": "available",
                                    "basis": "pregame_pin",
                                    "probability": 0.24,
                                    "observed_at": "2026-11-08T11:55:00Z",
                                    "outcome_id": 7022,
                                    "source": "kalshi"
                                },
                                "result": {
                                    "state": "won",
                                    "is_winner": true,
                                    "evidence_kind": "authoritative"
                                }
                            }
                        ]
                    },
                    {
                        "question_key": "m:703",
                        "typing": { "state": "typed" },
                        "kind": "count_threshold",
                        "label": "Total Games Over/Under 21.5",
                        "market_name": "Match O/U 21.5",
                        "subject": { "side": "game" },
                        "period": { "key": "full_game" },
                        "quantity": { "key": "games" },
                        "predicate": { "relation": "ge", "line": 21.5 },
                        "options": [
                            {
                                "option_key": "o:703-over",
                                "label": "Over 21.5 games",
                                "side": "over",
                                "contributor_outcome_ids": [7031],
                                "published": {
                                    "value": 0.58,
                                    "value_state": "quoted",
                                    "basis": "recent_quote",
                                    "source": "kalshi",
                                    "observed_at": "2026-11-08T11:55:00Z"
                                },
                                "pregame_reading": {
                                    "state": "available",
                                    "basis": "pregame_pin",
                                    "probability": 0.58,
                                    "observed_at": "2026-11-08T11:55:00Z",
                                    "outcome_id": 7031,
                                    "source": "kalshi"
                                },
                                "result": {
                                    "state": "won",
                                    "is_winner": true,
                                    "evidence_kind": "authoritative"
                                }
                            }
                        ]
                    },
                    {
                        "question_key": "m:704",
                        "typing": { "state": "typed" },
                        "kind": "count_threshold",
                        "label": "Total Games Over/Under 23.5",
                        "market_name": "Match O/U 23.5",
                        "subject": { "side": "game" },
                        "period": { "key": "full_game" },
                        "quantity": { "key": "games" },
                        "predicate": { "relation": "ge", "line": 23.5 },
                        "options": [
                            {
                                "option_key": "o:704-over",
                                "label": "Over 23.5 games",
                                "side": "over",
                                "contributor_outcome_ids": [7041],
                                "published": {
                                    "value": 0.41,
                                    "value_state": "quoted",
                                    "basis": "recent_quote",
                                    "source": "kalshi",
                                    "observed_at": "2026-11-08T11:55:00Z"
                                },
                                "pregame_reading": {
                                    "state": "available",
                                    "basis": "pregame_pin",
                                    "probability": 0.41,
                                    "observed_at": "2026-11-08T11:55:00Z",
                                    "outcome_id": 7041,
                                    "source": "kalshi"
                                },
                                "result": {
                                    "state": "won",
                                    "is_winner": true,
                                    "evidence_kind": "authoritative"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        """
        let gm = try decoder.decode(GameMarketsResponse.self, from: Data(gmJSON.utf8))
        let deck = EventAtlasTennisCards11666.cards(
            sportKey: "tennis_atp_paris_masters",
            atlasEnabled: true,
            status: "completed",
            commenceTime: "2026-11-08T12:00:00Z".asDate,
            homeTeam: "Carlos Alcaraz",
            awayTeam: "Ben Shelton",
            homeShort: "Alcaraz",
            awayShort: "Shelton",
            homeScore: 2,
            awayScore: 1,
            gameMarkets: gm,
            now: now
        )
        XCTAssertEqual(deck.count, 3)

        // Slot 1: Sets card (only Set 1 was quoted; Sets 2 and 3 are NOT invented)
        guard case .tennisSets(let setsCard) = deck[0] else {
            return XCTFail("Expected .tennisSets in slot 0")
        }
        XCTAssertEqual(setsCard.title, "The match, set by set")
        XCTAssertEqual(setsCard.sets.map(\.setNumber), [1])
        XCTAssertEqual(setsCard.sets[0].winnerSide, .home)
        XCTAssertEqual(setsCard.sets[0].home.pregameChance ?? -1, 0.68, accuracy: 1e-6)
        XCTAssertEqual(setsCard.sets[0].home.result, .won)
        XCTAssertEqual(setsCard.sets[0].away.result, .lost)

        // Slot 2: Exact match score in sets
        guard case .tennisExactScore(let exactCard) = deck[1] else {
            return XCTFail("Expected .tennisExactScore in slot 1")
        }
        XCTAssertEqual(exactCard.title, "Alcaraz in three sets")
        XCTAssertEqual(exactCard.reason, "Two sets to one is the match result")
        XCTAssertFalse(exactCard.reason.contains("%"))
        XCTAssertEqual(exactCard.outcomes.map(\.scoreLabel), ["Alcaraz 2–0", "Alcaraz 2–1"])
        XCTAssertEqual(exactCard.winningOutcome?.scoreLabel, "Alcaraz 2–1")

        // Slot 3: Total games ladder (`unit: "games"`, `startWord: "first serve"`, `actual == nil`)
        guard case .ladder(let ladderCard) = deck[2] else {
            return XCTFail("Expected .ladder in slot 2")
        }
        XCTAssertEqual(ladderCard.unit, "games")
        XCTAssertEqual(ladderCard.startWord, "first serve")
        XCTAssertNil(ladderCard.actual, "Tennis set score 2-1 must never be used as total games actual")
        XCTAssertNil(ladderCard.forecast)
        XCTAssertEqual(ladderCard.points.map(\.x), [21.5, 23.5])

        // Details sheet routing via EventAtlasStoryCards11666.readerDetailsModel
        let setSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: "o:701-home",
                cards: deck,
                rows: [:],
                awayName: "Ben Shelton",
                homeName: "Carlos Alcaraz"
            )
        )
        XCTAssertEqual(setSheet.outcomeTitle, "Set 1 · Carlos Alcaraz")
        XCTAssertEqual(setSheet.primaryReadingValue, "✓ Won")
        XCTAssertEqual(setSheet.pregameBaseline, "68%")

        let exactSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: "o:702-21",
                cards: deck,
                rows: [:],
                awayName: "Ben Shelton",
                homeName: "Carlos Alcaraz"
            )
        )
        XCTAssertEqual(exactSheet.outcomeTitle, "Alcaraz 2–1")
        XCTAssertEqual(exactSheet.primaryReadingValue, "✓ Won")
        XCTAssertEqual(exactSheet.pregameBaseline, "24%")
    }

    @MainActor
    func testDedupesSameSourceCandidatesWithholdsUnblendedMultiSourceAndAgesLiveQuotes() throws {
        let now = try XCTUnwrap("2026-11-08T13:00:00Z".asDate)
        let laterStale = try XCTUnwrap("2026-11-08T14:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Same-source duplicates ("Kalshi" + " kalshi ") collapse to sourceCount 1 and print probability
        let sameSourceJSON = """
        [
            {
                "_market_id": 801,
                "market_name": "Exact Match Score",
                "outcome_name": "Carlos Alcaraz wins 2-0",
                "probability": 0.44,
                "pregame_mark": 0.40,
                "observed_at": "2026-11-08T12:55:00Z",
                "source": "Kalshi"
            },
            {
                "_market_id": 801,
                "market_name": "Exact Match Score",
                "outcome_name": "Carlos Alcaraz wins 2-0",
                "probability": 0.44,
                "pregame_mark": 0.40,
                "observed_at": "2026-11-08T12:55:00Z",
                "source": " kalshi "
            },
            {
                "_market_id": 801,
                "market_name": "Exact Match Score",
                "outcome_name": "Ben Shelton wins 2-1",
                "probability": 0.22,
                "pregame_mark": 0.20,
                "observed_at": "2026-11-08T12:55:00Z",
                "source": "kalshi"
            }
        ]
        """
        let sameSourceRows = try decoder.decode([GameMarketOther].self, from: Data(sameSourceJSON.utf8))
        let liveCard = try XCTUnwrap(
            EventAtlasTennisCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: sameSourceRows,
                status: "live",
                commenceTime: "2026-11-08T12:00:00Z".asDate,
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton",
                now: now
            )
        )
        XCTAssertEqual(liveCard.outcomes[0].quotedChance ?? -1, 0.44, accuracy: 1e-6)
        XCTAssertEqual(liveCard.outcomes[0].pregameChance ?? -1, 0.40, accuracy: 1e-6)
        XCTAssertEqual(liveCard.outcomes[0].sourceCount, 1)

        // Aging past 30-minute liveStaleAfter drops quotedChance to nil while keeping pregameChance during play
        let agedDeckCard = NFLEventCard9483.tennisExactScore(liveCard).current(at: laterStale)
        guard case .tennisExactScore(let agedCard) = agedDeckCard else {
            return XCTFail("Expected .tennisExactScore")
        }
        XCTAssertNil(agedCard.outcomes[0].quotedChance)
        XCTAssertEqual(agedCard.outcomes[0].pregameChance ?? -1, 0.40, accuracy: 1e-6)

        // 2. Two distinct unblended sources ("kalshi" + "polymarket") withhold probabilities and report "2 sources, not blended"
        let multiUnblendedTotalsJSON = """
        [
            {
                "market_name": "Match O/U 21.5",
                "outcome_name": "Over 21.5",
                "threshold": 21.5,
                "over_probability": 0.56,
                "pregame_mark": 0.54,
                "observed_at": "2026-11-08T12:55:00Z",
                "source": "kalshi"
            },
            {
                "market_name": "Match O/U 22.5",
                "outcome_name": "Over 22.5",
                "threshold": 22.5,
                "over_probability": 0.48,
                "pregame_mark": 0.47,
                "observed_at": "2026-11-08T12:55:00Z",
                "source": "kalshi"
            },
            {
                "market_name": "Match O/U 22.5",
                "outcome_name": "Over 22.5",
                "threshold": 22.5,
                "over_probability": 0.45,
                "pregame_mark": 0.44,
                "observed_at": "2026-11-08T12:55:00Z",
                "source": "polymarket"
            }
        ]
        """
        let totalRows = try decoder.decode([GameMarketOutcome].self, from: Data(multiUnblendedTotalsJSON.utf8))
        let totalCard = try XCTUnwrap(
            EventAtlasTennisCards11666.buildTotalGamesCard(
                matrix: nil,
                totals: totalRows,
                status: "live",
                commenceTime: "2026-11-08T12:00:00Z".asDate,
                homeShort: "Alcaraz",
                awayShort: "Shelton",
                now: now
            )
        )
        let pt215 = try XCTUnwrap(totalCard.points.first { $0.x == 21.5 })
        let pt225 = try XCTUnwrap(totalCard.points.first { $0.x == 22.5 })
        XCTAssertEqual(pt215.now ?? -1, 0.56, accuracy: 1e-6)
        XCTAssertNil(pt225.chance)
        XCTAssertNil(pt225.now)
        XCTAssertEqual(pt225.detail.sourceCount, 2)
        XCTAssertNil(pt225.detail.source)

        let sheet225 = EventAtlasStoryCards11666.detailsModel(for: pt225.detail, card: totalCard, point: pt225)
        XCTAssertEqual(sheet225.sourceLabel, "2 sources, not blended")
        XCTAssertEqual(sheet225.primaryReadingValue, "No recent probability")
    }

    @MainActor
    func testDecide80AFallbackRowsNeverMintLostAndDisagreeingVenuesRenderPending() throws {
        let now = try XCTUnwrap("2026-11-08T16:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // Fallback `other` rows: `is_winner: true` + `api_settlement` -> `.won`,
        // `is_winner: false` + `clob_never_graded` / `api_settlement` -> `nil` (never `.lost` under 80-A).
        let fallbackRowsJSON = """
        [
            {
                "_market_id": 901,
                "market_name": "Set 1 Winner",
                "outcome_name": "Carlos Alcaraz",
                "probability": 1.0,
                "pregame_mark": 0.65,
                "is_winner": true,
                "resolution_source": "api_settlement",
                "source": "kalshi"
            },
            {
                "_market_id": 901,
                "market_name": "Set 1 Winner",
                "outcome_name": "Ben Shelton",
                "probability": 0.0,
                "pregame_mark": 0.35,
                "is_winner": false,
                "resolution_source": "clob_never_graded",
                "source": "kalshi"
            }
        ]
        """
        let rows = try decoder.decode([GameMarketOther].self, from: Data(fallbackRowsJSON.utf8))
        let setsCard = try XCTUnwrap(
            EventAtlasTennisCards11666.buildSetsCard(
                matrix: nil,
                otherMarkets: rows,
                status: "completed",
                commenceTime: "2026-11-08T12:00:00Z".asDate,
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton",
                now: now
            )
        )
        XCTAssertEqual(setsCard.sets[0].home.result, .won)
        XCTAssertNil(setsCard.sets[0].away.result, "Decide 80-A: fallback row must not mint .lost from clob_never_graded")
        let awaySheet = EventAtlasTennisCards11666.detailsModel(for: setsCard.sets[0].away, card: setsCard)
        XCTAssertEqual(awaySheet.primaryReadingValue, "Pending")
    }

    @MainActor
    func testRendersTennisStoryCardsAt390Width() throws {
        let now = try XCTUnwrap("2026-11-08T12:15:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let otherJSON = """
        [
            {"_market_id": 801, "market_name": "Set 1 Winner", "outcome_name": "Carlos Alcaraz", "probability": 0.68, "pregame_mark": 0.64, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 801, "market_name": "Set 1 Winner", "outcome_name": "Ben Shelton", "probability": 0.32, "pregame_mark": 0.36, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 802, "market_name": "Set Betting", "outcome_name": "Carlos Alcaraz 2-0", "probability": 0.44, "pregame_mark": 0.41, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 802, "market_name": "Set Betting", "outcome_name": "Carlos Alcaraz 2-1", "probability": 0.24, "pregame_mark": 0.23, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 802, "market_name": "Set Betting", "outcome_name": "Ben Shelton 2-0", "probability": 0.14, "pregame_mark": 0.16, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 802, "market_name": "Set Betting", "outcome_name": "Ben Shelton 2-1", "probability": 0.18, "pregame_mark": 0.20, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"}
        ]
        """
        let otherRows = try decoder.decode([GameMarketOther].self, from: Data(otherJSON.utf8))
        let setsCard = try XCTUnwrap(
            EventAtlasTennisCards11666.buildSetsCard(
                matrix: nil,
                otherMarkets: otherRows,
                status: "in_progress",
                commenceTime: "2026-11-08T12:00:00Z".asDate,
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton",
                now: now
            )
        )
        let exactCard = try XCTUnwrap(
            EventAtlasTennisCards11666.buildExactScoreCard(
                matrix: nil,
                otherMarkets: otherRows,
                status: "in_progress",
                commenceTime: "2026-11-08T12:00:00Z".asDate,
                homeTeam: "Carlos Alcaraz",
                awayTeam: "Ben Shelton",
                homeShort: "Alcaraz",
                awayShort: "Shelton",
                now: now
            )
        )

        let state = NFLCardDeckState9483()
        let setsView = EventAtlasTennisSetsCardView11666(
            card: setsCard,
            awayColor: .orange,
            homeColor: .blue,
            state: state
        )
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let exactView = EventAtlasTennisExactScoreCardView11666(
            card: exactCard,
            awayColor: .orange,
            homeColor: .blue,
            state: state
        )
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let r1 = rendererForMeasurement(setsView)
        r1.scale = 2.0
        let img1 = try XCTUnwrap(r1.uiImage)
        XCTAssertEqual(Int(img1.size.width), 390)

        let r2 = rendererForMeasurement(exactView)
        r2.scale = 2.0
        let img2 = try XCTUnwrap(r2.uiImage)
        XCTAssertEqual(Int(img2.size.width), 390)

        if let outDir = ProcessInfo.processInfo.environment["ATLAS_TENNIS_E6D_SCREENSHOT_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try XCTUnwrap(img1.pngData()).write(to: dirURL.appendingPathComponent("tennis-e6d-sets-card-390px.png"))
            try XCTUnwrap(img2.pngData()).write(to: dirURL.appendingPathComponent("tennis-e6d-exact-score-card-390px.png"))
        }
    }

    @MainActor
    func testTotalGamesFallbackIgnoresUnderAndInvertedRowsAndRequiresWordBoundaryOnSubstringMatch() throws {
        let now = try XCTUnwrap("2026-11-08T12:15:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Word boundary on tier-3/4 player matching: "Alex" does not false-match "Alexander Zverev".
        XCTAssertNil(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Alex",
                homeTeam: "Alexander Zverev",
                awayTeam: "Carlos Alcaraz",
                homeShort: "Zverev",
                awayShort: "Alcaraz"
            )
        )
        XCTAssertEqual(
            EventAtlasTennisCards11666.matchTennisPlayerSide(
                candidate: "Alexander Zverev",
                homeTeam: "Alexander Zverev",
                awayTeam: "Carlos Alcaraz",
                homeShort: "Zverev",
                awayShort: "Alcaraz"
            ),
            .home
        )

        // 2. Fallback totals: Under row comes first for line 21.5 + blended Under row + _inverted Over row;
        // line 24.5 has only an Under row.
        let totalsJSON = """
        [
            {"_market_id": 910, "market_name": "Match O/U 21.5", "outcome_name": "Under 21.5", "threshold": 21.5, "probability": 0.38, "pregame_mark": 0.36, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 910, "market_name": "Match O/U 21.5", "outcome_name": "Under 21.5", "threshold": 21.5, "probability": 0.39, "pregame_mark": 0.37, "observed_at": "2026-11-08T12:12:00Z", "source": "blend"},
            {"_market_id": 910, "market_name": "Match O/U 21.5", "outcome_name": "Over 21.5", "threshold": 21.5, "probability": 0.41, "pregame_mark": 0.40, "observed_at": "2026-11-08T12:12:00Z", "source": "polymarket", "_inverted": true},
            {"_market_id": 910, "market_name": "Match O/U 21.5", "outcome_name": "Over 21.5", "threshold": 21.5, "probability": 0.62, "pregame_mark": 0.64, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 911, "market_name": "Match O/U 22.5", "outcome_name": "Over 22.5", "threshold": 22.5, "probability": 0.51, "pregame_mark": 0.53, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 912, "market_name": "Match O/U 23.5", "outcome_name": "Over 23.5", "threshold": 23.5, "probability": 0.39, "pregame_mark": 0.41, "observed_at": "2026-11-08T12:12:00Z", "source": "kalshi"},
            {"_market_id": 913, "market_name": "Match O/U 24.5", "outcome_name": "Under 24.5", "threshold": 24.5, "probability": 0.72, "pregame_mark": 0.70, "observed_at": "2026-11-08T12:12:00Z", "source": "blend"}
        ]
        """
        let totals = try decoder.decode([GameMarketOutcome].self, from: Data(totalsJSON.utf8))
        let ladder = try XCTUnwrap(
            EventAtlasTennisCards11666.buildTotalGamesCard(
                matrix: nil,
                totals: totals,
                status: "in_progress",
                commenceTime: "2026-11-08T12:00:00Z".asDate,
                homeShort: "Zverev",
                awayShort: "Alcaraz",
                now: now
            )
        )
        XCTAssertEqual(ladder.points.map(\.x), [21.5, 22.5, 23.5], "line 24.5 with only an Under row must not be plotted")
        let point215 = try XCTUnwrap(ladder.points.first(where: { $0.x == 21.5 }))
        XCTAssertEqual(point215.now ?? -1, 0.62, accuracy: 1e-6, "must use the Over row's probability (0.62), never the Under row (0.38/0.39) or _inverted row (0.41)")
        XCTAssertEqual(point215.chance ?? -1, 0.64, accuracy: 1e-6, "must use the Over row's pregameMark (0.64)")
    }
}
