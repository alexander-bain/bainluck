import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

final class EventAtlasCombatCards11666Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-11-08T22:00:00Z")!

    // MARK: - 1. Sport Gating

    func testAppliesGatedByAtlasAndCombatSportKey() {
        XCTAssertTrue(EventAtlasCombatCards11666.applies(sportKey: "mma_mixed_martial_arts", atlasEnabled: true))
        XCTAssertTrue(EventAtlasCombatCards11666.applies(sportKey: "mma_ufc", atlasEnabled: true))
        XCTAssertTrue(EventAtlasCombatCards11666.applies(sportKey: "boxing_boxing", atlasEnabled: true))
        XCTAssertTrue(EventAtlasCombatCards11666.applies(sportKey: "mma", atlasEnabled: true))
        XCTAssertTrue(EventAtlasCombatCards11666.applies(sportKey: "boxing", atlasEnabled: true))

        XCTAssertFalse(EventAtlasCombatCards11666.applies(sportKey: "mma_mixed_martial_arts", atlasEnabled: false))
        XCTAssertFalse(EventAtlasCombatCards11666.applies(sportKey: "basketball_nba", atlasEnabled: true))
        XCTAssertFalse(EventAtlasCombatCards11666.applies(sportKey: "soccer_epl", atlasEnabled: true))
        XCTAssertFalse(EventAtlasCombatCards11666.applies(sportKey: nil, atlasEnabled: true))
    }

    // MARK: - 2. Before-Fight Card Construction

    func testBuildsBeforeFightMethodRoundAndDurationCardsFromGameMarkets() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "scheduled",
            commenceTime: "2026-11-09T03:00:00Z"
        )
        let markets = makeMMAGameMarkets(
            observedAt: "2026-11-08T21:55:00Z",
            settled: false
        )

        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        XCTAssertEqual(cards.count, 3)

        guard case .combatMethod(let methodCard) = cards[0] else {
            return XCTFail("Expected .combatMethod as first card")
        }
        XCTAssertEqual(methodCard.phase, .before)
        XCTAssertEqual(methodCard.tiles.map(\.label), ["KO / TKO", "Submission", "Decision", "Draw"])
        XCTAssertEqual(methodCard.tiles[0].beforeChance ?? -1, 0.46, accuracy: 0.001)
        XCTAssertEqual(methodCard.tiles[1].beforeChance ?? -1, 0.22, accuracy: 0.001)
        XCTAssertEqual(methodCard.tiles[2].beforeChance ?? -1, 0.30, accuracy: 0.001)
        XCTAssertEqual(methodCard.tiles[3].beforeChance ?? -1, 0.02, accuracy: 0.001)
        XCTAssertNotNil(methodCard.scheduledStartSummary)

        guard case .combatRounds(let roundCard) = cards[1] else {
            return XCTFail("Expected .combatRounds as second card")
        }
        XCTAssertEqual(roundCard.phase, .before)
        XCTAssertEqual(roundCard.scheduledRounds, 5)
        XCTAssertEqual(roundCard.fighterAName, "Islam Makhachev")
        XCTAssertEqual(roundCard.fighterBName, "Arman Tsarukyan")
        XCTAssertEqual(roundCard.fighterASlots.count, 5)
        XCTAssertEqual(roundCard.fighterBSlots.count, 5)
        XCTAssertEqual(roundCard.fighterASlots[0].beforeChance ?? -1, 0.14, accuracy: 0.001)
        XCTAssertEqual(roundCard.fighterBSlots[0].beforeChance ?? -1, 0.09, accuracy: 0.001)

        guard case .combatDuration(let durationCard) = cards[2] else {
            return XCTFail("Expected .combatDuration as third card")
        }
        XCTAssertEqual(durationCard.phase, .before)
        XCTAssertEqual(
            durationCard.rows.map(\.title),
            ["Goes the distance", "Inside the distance", "Over 2.5 rounds", "Under 2.5 rounds"]
        )
        XCTAssertEqual(durationCard.rows[0].beforeChance ?? -1, 0.32, accuracy: 0.001)
        XCTAssertEqual(durationCard.rows[2].beforeChance ?? -1, 0.58, accuracy: 0.001)
        XCTAssertEqual(durationCard.rows[3].beforeChance ?? -1, 0.42, accuracy: 0.001)
        let durationInput = durationCard.presentationInput(selectedMarketID: nil, now: now)
        let underOrig = try XCTUnwrap(durationInput.markets[3].originals.first)
        XCTAssertEqual(underOrig.before?.text, "42%")
    }

    func testBeforeFightAgesStaleReadingToNoRecentProbabilityNeverNoPreFightChanceRecorded() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "scheduled",
            commenceTime: "2026-11-12T03:00:00Z"
        )
        // Reading is > 30 minutes old at `now` (2026-11-08T22:00:00Z)
        let staleMarkets = makeMMAGameMarkets(
            observedAt: "2026-11-08T21:10:00Z",
            settled: false
        )
        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: staleMarkets,
            now: now,
            atlasEnabled: true
        )
        guard case .combatMethod(let methodCard) = cards[0],
              case .combatRounds(let roundCard) = cards[1],
              case .combatDuration(let durationCard) = cards[2] else {
            return XCTFail("Expected all 3 combat cards")
        }

        let methodInput = methodCard.presentationInput(selectedMethodID: nil, now: now)
        let methodOrig = try XCTUnwrap(methodInput.methods.first?.originals.first)
        XCTAssertNil(methodOrig.before)
        XCTAssertEqual(methodOrig.beforeMissing, "No recent probability")
        XCTAssertNotEqual(methodOrig.beforeMissing, "No pre-fight chance recorded")

        let roundInput = roundCard.presentationInput(selectedSlotID: nil, now: now)
        let roundOrig = try XCTUnwrap(roundInput.groups.first?.slots.first?.state.market?.originals.first)
        XCTAssertNil(roundOrig.before)
        XCTAssertEqual(roundOrig.beforeMissing, "No recent probability")
        XCTAssertNotEqual(roundOrig.beforeMissing, "No pre-fight chance recorded")

        let durationInput = durationCard.presentationInput(selectedMarketID: nil, now: now)
        let durationOrig = try XCTUnwrap(durationInput.markets[3].originals.first)
        XCTAssertNil(durationOrig.before)
        XCTAssertEqual(durationOrig.beforeMissing, "No recent probability")
        XCTAssertNotEqual(durationOrig.beforeMissing, "No pre-fight chance recorded")
    }

    func testMethodClassificationStripsFighterNamesAndMatchesWordBoundaries() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "live",
            commenceTime: "2026-11-08T21:15:00Z",
            homeTeam: "Alexander Volkov",
            awayTeam: "Kyle Decker",
            gamePeriod: "Round 1"
        )
        let markets = GameMarketsResponse(
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
            other: [
                // Fighter-name outcomes containing "ko" / "dec" substrings must never match
                GameMarketOther(
                    _marketId: 800,
                    marketName: "Method of Victory",
                    outcomeName: "Alexander Volkov",
                    probability: 0.62,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.60
                ),
                GameMarketOther(
                    _marketId: 800,
                    marketName: "Method of Victory",
                    outcomeName: "Kyle Decker",
                    probability: 0.38,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.40
                ),
                // Fight-level method outcomes
                GameMarketOther(
                    _marketId: 801,
                    marketName: "Method of Victory",
                    outcomeName: "Decision",
                    probability: 0.38,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.34
                ),
                GameMarketOther(
                    _marketId: 801,
                    marketName: "Method of Victory",
                    outcomeName: "Submission",
                    probability: 0.16,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.18
                ),
                GameMarketOther(
                    _marketId: 801,
                    marketName: "Method of Victory",
                    outcomeName: "KO/TKO",
                    probability: 0.44,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.46
                ),
            ],
            pace: nil
        )
        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        guard let first = cards.first, case .combatMethod(let methodCard) = first else {
            return XCTFail("Expected method card")
        }
        XCTAssertEqual(methodCard.tiles.map(\.label), ["KO / TKO", "Submission", "Decision"])
        XCTAssertEqual(methodCard.tiles[0].currentChance ?? -1, 0.44, accuracy: 0.001)
        XCTAssertEqual(methodCard.tiles[1].currentChance ?? -1, 0.16, accuracy: 0.001)
        XCTAssertEqual(methodCard.tiles[2].currentChance ?? -1, 0.38, accuracy: 0.001)
    }

    func testFightLevelMethodGridExcludesPerFighterKnockoutAndSubmissionMarketsAndReadsFightLevelMarket() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "scheduled",
            commenceTime: "2026-11-09T03:00:00Z",
            homeTeam: "Ateba Gautier",
            awayTeam: "Roman Kopylov"
        )
        // Per-fighter knockout & submission markets appear BEFORE the fight-level markets
        // so an unfiltered first-match loop would pick Kopylov's 12.5% or Gautier's 40%.
        let markets = GameMarketsResponse(
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
            other: [
                GameMarketOther(
                    _marketId: 63900810,
                    marketName: "Will Roman Kopylov win by KO or TKO?",
                    outcomeName: "Yes",
                    probability: 0.125,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.125
                ),
                GameMarketOther(
                    _marketId: 63786875,
                    marketName: "Will Ateba Gautier win by KO or TKO?",
                    outcomeName: "Yes",
                    probability: 0.40,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.40
                ),
                GameMarketOther(
                    _marketId: 63900811,
                    marketName: "Will Roman Kopylov win by submission?",
                    outcomeName: "Yes",
                    probability: 0.04,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.04
                ),
                GameMarketOther(
                    _marketId: 63786880,
                    marketName: "Will the fight be won by KO or TKO?",
                    outcomeName: "Yes",
                    probability: 0.55,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.55
                ),
                GameMarketOther(
                    _marketId: 63786881,
                    marketName: "Will the fight be won by submission?",
                    outcomeName: "Yes",
                    probability: 0.12,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.12
                ),
            ],
            pace: nil
        )
        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        guard let first = cards.first, case .combatMethod(let methodCard) = first else {
            return XCTFail("Expected fight-level method card")
        }
        XCTAssertEqual(methodCard.tiles.map(\.label), ["KO / TKO", "Submission"])
        XCTAssertEqual(methodCard.tiles[0].marketID, "63786880")
        XCTAssertEqual(methodCard.tiles[0].beforeChance ?? -1, 0.55, accuracy: 0.001)
        XCTAssertEqual(methodCard.tiles[1].marketID, "63786881")
        XCTAssertEqual(methodCard.tiles[1].beforeChance ?? -1, 0.12, accuracy: 0.001)

        // When only per-fighter markets exist, no fight-level method card is fabricated.
        let fighterOnlyMarkets = GameMarketsResponse(
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
            other: [
                GameMarketOther(
                    _marketId: 63900810,
                    marketName: "Will Roman Kopylov win by KO or TKO?",
                    outcomeName: "Yes",
                    probability: 0.125,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.125
                ),
                GameMarketOther(
                    _marketId: 63786875,
                    marketName: "Will Ateba Gautier win by KO or TKO?",
                    outcomeName: "Yes",
                    probability: 0.40,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:56:00Z",
                    pregameMark: 0.40
                ),
            ],
            pace: nil
        )
        XCTAssertTrue(
            EventAtlasCombatCards11666.buildCards(
                event: event,
                gameMarkets: fighterOnlyMarkets,
                now: now,
                atlasEnabled: true
            ).isEmpty
        )
    }

    func testWholePointMovementVenueNeutralProvenanceAndSilentSkipGuards() {
        XCTAssertEqual(
            EventAtlasCombatCards11666.formatMovement(before: 0.40, current: 0.436),
            "+4 pts vs before fight"
        )
        XCTAssertEqual(
            EventAtlasCombatCards11666.formatMovement(before: 0.40, current: 0.391),
            "−1 pt vs before fight"
        )
        XCTAssertEqual(
            EventAtlasCombatCards11666.formatMovement(before: 0.40, current: 0.402),
            "Unchanged vs before fight"
        )

        let provenance = EventAtlasCombatCards11666.formatSourceDetail(
            rawSource: "kalshi",
            sourceCount: 1,
            observedAt: now,
            isStaleLive: false,
            phase: .during,
            now: now
        )
        XCTAssertFalse(provenance.lowercased().contains("kalshi"))
        XCTAssertFalse(provenance.lowercased().contains("polymarket"))

        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "scheduled",
            commenceTime: "2026-11-09T03:00:00Z"
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
            other: [
                GameMarketOther(
                    _marketId: 999,
                    marketName: "Unrelated Prop",
                    outcomeName: "No",
                    probability: 0.50,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.50
                )
            ],
            pace: nil
        )
        XCTAssertTrue(
            EventAtlasCombatCards11666.buildCards(
                event: event,
                gameMarkets: emptyMarkets,
                now: now,
                atlasEnabled: true
            ).isEmpty
        )
    }

    // MARK: - 3. Live Quote 30-Minute Aging ("No recent probability")

    func testAgesLiveQuotesAfter30MinutesToNoRecentProbabilityPreservingBeforeBaseline() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "live",
            commenceTime: "2026-11-08T21:15:00Z",
            gamePeriod: "Round 2"
        )
        // Fresh at 21:56 UTC (4m old at `now` = 22:00 UTC)
        let freshMarkets = makeMMAGameMarkets(
            observedAt: "2026-11-08T21:56:00Z",
            settled: false
        )
        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: freshMarkets,
            now: now,
            atlasEnabled: true
        )
        XCTAssertEqual(cards.count, 3)

        guard case .combatMethod(let methodCard) = cards[0],
              case .combatRounds(let roundCard) = cards[1],
              case .combatDuration(let durationCard) = cards[2] else {
            return XCTFail("Expected all 3 combat cards")
        }

        // At `now` (4m old), live quotes are fresh
        let freshMethodInput = methodCard.presentationInput(selectedMethodID: nil, now: now)
        let freshMethodOrig = try XCTUnwrap(freshMethodInput.methods.first?.originals.first)
        if case .recorded(let obs, _) = freshMethodOrig.current {
            XCTAssertEqual(obs.probability, 0.46, accuracy: 0.001)
        } else {
            XCTFail("Expected recorded current observation")
        }
        XCTAssertEqual(freshMethodOrig.before?.probability ?? -1, 0.40, accuracy: 0.001)

        // Round 1 is elapsed in Round 2
        XCTAssertEqual(roundCard.currentRound, 2)
        XCTAssertEqual(roundCard.completedRounds, 1)
        XCTAssertTrue(roundCard.fighterASlots[0].isElapsedRound)
        XCTAssertFalse(roundCard.fighterASlots[1].isElapsedRound)

        // Advance clock by 32 minutes -> 36 minutes since observation (> 30m limit)
        let later = now.addingTimeInterval(32 * 60)
        let agedMethodInput = methodCard.presentationInput(selectedMethodID: nil, now: later)
        let agedMethodOrig = try XCTUnwrap(agedMethodInput.methods.first?.originals.first)
        if case .withheld(let text) = agedMethodOrig.current {
            XCTAssertTrue(text.contains("No recent probability"))
        } else {
            XCTFail("Expected withheld stale live quote")
        }
        XCTAssertEqual(agedMethodOrig.before?.probability ?? -1, 0.40, accuracy: 0.001)

        let agedRoundInput = roundCard.presentationInput(selectedSlotID: nil, now: later)
        let agedRoundOrig = try XCTUnwrap(agedRoundInput.groups.first?.slots[1].state.market?.originals.first)
        if case .withheld(let text) = agedRoundOrig.current {
            XCTAssertTrue(text.contains("No recent probability"))
        } else {
            XCTFail("Expected withheld stale live round quote")
        }
        XCTAssertEqual(agedRoundOrig.before?.probability ?? -1, 0.11, accuracy: 0.001)

        let agedDurationInput = durationCard.presentationInput(selectedMarketID: nil, now: later)
        let agedDurationOrig = try XCTUnwrap(agedDurationInput.markets.first?.originals.first)
        if case .withheld(let text) = agedDurationOrig.current {
            XCTAssertTrue(text.contains("No recent probability"))
        } else {
            XCTFail("Expected withheld stale live duration quote")
        }
        XCTAssertEqual(agedDurationOrig.before?.probability ?? -1, 0.36, accuracy: 0.001)
    }

    // MARK: - 4. Final Settlement Grading & Unconfirmed Truthfulness

    func testFinalFightGradesOfficialWinnerAndNeverFabricatesLostWhenResultUnknown() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "completed",
            commenceTime: "2026-11-08T19:00:00Z"
        )
        let settledMarkets = makeMMAGameMarkets(
            observedAt: "2026-11-08T21:30:00Z",
            settled: true
        )
        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: settledMarkets,
            now: now,
            atlasEnabled: true
        )
        XCTAssertEqual(cards.count, 3)

        guard case .combatMethod(let methodCard) = cards[0],
              case .combatRounds(let roundCard) = cards[1],
              case .combatDuration(let durationCard) = cards[2] else {
            return XCTFail("Expected all 3 combat cards")
        }

        XCTAssertEqual(methodCard.phase, .final)
        XCTAssertEqual(methodCard.officialFinishSummary, "Official result: Submission")
        XCTAssertNil(methodCard.tiles[0].verdict)
        XCTAssertEqual(methodCard.tiles[1].verdict, .won)
        XCTAssertNil(methodCard.tiles[2].verdict)
        let methodInput = methodCard.presentationInput(selectedMethodID: nil, now: now)
        XCTAssertEqual(methodInput.methods[1].originals.first?.result, .won("✓ Won"))
        XCTAssertEqual(methodInput.methods[0].originals.first?.result, .unconfirmed("Result not confirmed"))

        XCTAssertEqual(roundCard.phase, .final)
        XCTAssertEqual(roundCard.officialFinishSummary, "Official finish: Islam Makhachev in Round 3")
        XCTAssertEqual(roundCard.fighterASlots[2].verdict, .won)
        XCTAssertNil(roundCard.fighterASlots[0].verdict)

        XCTAssertEqual(durationCard.phase, .final)
        XCTAssertEqual(durationCard.officialDurationSummary, "Official duration: Inside the distance")
        XCTAssertNil(durationCard.rows[0].verdict)
        XCTAssertEqual(durationCard.rows[1].verdict, .won)

        // Decide 80-A (#12449): tier 0 (binary_higher_wins), tier 1 (clean_resolution),
        // and tier 2 (game_score) rows with is_winner: false at the final read
        // "Result not confirmed", and never "✓ Won" or "✗ Lost".
        for nonAuthSource in ["binary_higher_wins", "clean_resolution", "game_score"] {
            let nonAuthMarkets = makeMMAGameMarkets(
                observedAt: "2026-11-08T21:30:00Z",
                settled: true,
                resolutionSourceOverride: nonAuthSource
            )
            let nonAuthCards = EventAtlasCombatCards11666.buildCards(
                event: event,
                gameMarkets: nonAuthMarkets,
                now: now,
                atlasEnabled: true
            )
            guard case .combatMethod(let nonAuthMethod) = nonAuthCards[0],
                  case .combatRounds(let nonAuthRounds) = nonAuthCards[1],
                  case .combatDuration(let nonAuthDuration) = nonAuthCards[2] else {
                return XCTFail("Expected all 3 combat cards for \(nonAuthSource)")
            }
            let nonAuthMethodInput = nonAuthMethod.presentationInput(selectedMethodID: nil, now: now)
            XCTAssertTrue(
                nonAuthMethodInput.methods.allSatisfy {
                    $0.originals.first?.result == .unconfirmed("Result not confirmed")
                },
                "Tier 0/1/2 source \(nonAuthSource) must read 'Result not confirmed'"
            )
            let nonAuthRoundsInput = nonAuthRounds.presentationInput(selectedSlotID: nil, now: now)
            XCTAssertTrue(
                nonAuthRoundsInput.groups.allSatisfy { group in
                    group.slots.allSatisfy { slot in
                        guard case .market(let market) = slot.state else { return true }
                        return market.originals.first?.result == .unconfirmed("Result not confirmed")
                    }
                },
                "Tier 0/1/2 source \(nonAuthSource) must read 'Result not confirmed'"
            )
            let nonAuthDurationInput = nonAuthDuration.presentationInput(selectedMarketID: nil, now: now)
            XCTAssertTrue(
                nonAuthDurationInput.markets.allSatisfy {
                    $0.originals.first?.result == .unconfirmed("Result not confirmed")
                },
                "Tier 0/1/2 source \(nonAuthSource) must read 'Result not confirmed'"
            )
        }

        // Verify an unsettled/unconfirmed market on a completed fight yields `nil` (`Result not confirmed`), never `.lost`
        let unconfirmedMarkets = makeMMAGameMarkets(
            observedAt: "2026-11-08T21:30:00Z",
            settled: false
        )
        let unconfirmedCards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: unconfirmedMarkets,
            now: now,
            atlasEnabled: true
        )
        guard case .combatMethod(let unconfirmedMethod) = unconfirmedCards[0] else {
            return XCTFail("Expected method card")
        }
        XCTAssertTrue(unconfirmedMethod.tiles.allSatisfy { $0.verdict == nil })
        XCTAssertNil(unconfirmedMethod.officialFinishSummary)
        let unconfirmedInput = unconfirmedMethod.presentationInput(selectedMethodID: nil, now: now)
        let firstOrig = try XCTUnwrap(unconfirmedInput.methods.first?.originals.first)
        XCTAssertEqual(firstOrig.result, .unconfirmed("Result not confirmed"))
    }

    // MARK: - 5. Boxing 12-Round & 3-Method Layout

    func testBoxingBoutBuildsThreeMethodTilesAnd12RoundGrid() throws {
        let event = makeCombatEvent(
            sport: "boxing_boxing",
            status: "scheduled",
            commenceTime: "2026-11-09T04:00:00Z",
            homeTeam: "Canelo Alvarez",
            awayTeam: "Terence Crawford"
        )
        let boxingMarkets = GameMarketsResponse(
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
            other: [
                GameMarketOther(
                    _marketId: 901,
                    marketName: "Method of Victory",
                    outcomeName: "KO/TKO",
                    probability: 0.34,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.32
                ),
                GameMarketOther(
                    _marketId: 901,
                    marketName: "Method of Victory",
                    outcomeName: "Decision",
                    probability: 0.62,
                    source: "polymarket",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.64
                ),
                GameMarketOther(
                    _marketId: 901,
                    marketName: "Method of Victory",
                    outcomeName: "Draw",
                    probability: 0.04,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.04
                ),
                GameMarketOther(
                    _marketId: 902,
                    marketName: "Round of Victory",
                    outcomeName: "Canelo Alvarez in Round 7",
                    probability: 0.05,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.05
                ),
                GameMarketOther(
                    _marketId: 902,
                    marketName: "Round of Victory",
                    outcomeName: "Canelo Alvarez in Round 11",
                    probability: 0.04,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.04
                ),
                GameMarketOther(
                    _marketId: 902,
                    marketName: "Round of Victory",
                    outcomeName: "Terence Crawford in Round 9",
                    probability: 0.03,
                    source: "kalshi",
                    observedAt: "2026-11-08T21:55:00Z",
                    pregameMark: 0.03
                ),
            ],
            pace: nil
        )

        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: boxingMarkets,
            now: now,
            atlasEnabled: true
        )
        XCTAssertEqual(cards.count, 2)

        guard case .combatMethod(let methodCard) = cards[0],
              case .combatRounds(let roundCard) = cards[1] else {
            return XCTFail("Expected method and round cards for boxing")
        }
        XCTAssertEqual(methodCard.tiles.map(\.label), ["KO / TKO", "Decision", "Draw"])
        XCTAssertEqual(roundCard.scheduledRounds, 12)
        XCTAssertEqual(roundCard.fighterASlots.count, 12)
        XCTAssertEqual(roundCard.fighterBSlots.count, 12)
    }

    // MARK: - 6. 390 px Snapshot Verification (Default + AX3)

    @MainActor
    func testRenders390pxCombatCardsSnapshotsAtDefaultAndAccessibility3() throws {
        let event = makeCombatEvent(
            sport: "mma_mixed_martial_arts",
            status: "live",
            commenceTime: "2026-11-08T21:15:00Z",
            gamePeriod: "Round 2"
        )
        let markets = makeMMAGameMarkets(
            observedAt: "2026-11-08T21:56:00Z",
            settled: false
        )
        let cards = EventAtlasCombatCards11666.buildCards(
            event: event,
            gameMarkets: markets,
            now: now,
            atlasEnabled: true
        )
        guard case .combatMethod(let methodCard) = cards[0],
              case .combatRounds(let roundCard) = cards[1],
              case .combatDuration(let durationCard) = cards[2] else {
            return XCTFail("Expected all 3 combat cards")
        }

        let defaultStack = VStack(spacing: 16) {
            EventAtlasCombatMethodCardView11666(card: methodCard, now: now)
            EventAtlasCombatRoundCardView11666(card: roundCard, now: now)
            EventAtlasCombatDurationCardView11666(card: durationCard, now: now)
        }
        .padding(16)
        .frame(width: 390)
        .background(Color.systemBackground)
        .environment(\.colorScheme, .light)

        let defaultRenderer = rendererForMeasurement(defaultStack)
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(defaultImage.size.height, 600)

        let a11yStack = VStack(spacing: 16) {
            EventAtlasCombatMethodCardView11666(card: methodCard, now: now)
            EventAtlasCombatDurationCardView11666(card: durationCard, now: now)
        }
        .padding(16)
        .frame(width: 390)
        .background(Color.systemBackground)
        .environment(\.colorScheme, .light)

        let a11yRenderer = rendererForMeasurement(a11yStack, at: .accessibility3)
        a11yRenderer.scale = 1.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(a11yImage.size.height, 600)

        if let dir = ProcessInfo.processInfo.environment["COMBAT_CARDS_SNAPSHOT_DIR"], !dir.isEmpty {
            let dirURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try XCTUnwrap(defaultImage.pngData()).write(
                to: dirURL.appendingPathComponent("combat-story-cards-default-390px.png")
            )
            try XCTUnwrap(a11yImage.pngData()).write(
                to: dirURL.appendingPathComponent("combat-story-cards-a11y-390px.png")
            )
        }
    }

    // MARK: - Fixtures

    private func makeCombatEvent(
        sport: String,
        status: String,
        commenceTime: String,
        homeTeam: String = "Islam Makhachev",
        awayTeam: String = "Arman Tsarukyan",
        gamePeriod: String? = nil
    ) -> EventDetail {
        let espnData: ESPNData? = gamePeriod.map { period in
            ESPNData(
                espnId: "77101",
                gameClock: "2:45",
                period: period,
                broadcast: "ESPN+ PPV",
                winProbability: 0.64,
                probabilitySources: nil,
                seriesHomeWins: nil,
                seriesAwayWins: nil
            )
        }
        return EventDetail(
            id: 77101,
            externalId: "ufc-311-makhachev-tsarukyan",
            sport: sport,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            commenceTime: commenceTime,
            startIsTbd: false,
            status: status,
            homeScore: nil,
            awayScore: nil,
            homeTeamData: nil,
            awayTeamData: nil,
            metadata: nil,
            standingsContext: nil,
            currentOdds: nil,
            openingOdds: nil,
            prematchOdds: nil,
            bookmakerOdds: nil,
            highlight: nil,
            espn: espnData,
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

    private func makeMMAGameMarkets(
        observedAt: String,
        settled: Bool,
        resolutionSourceOverride: String? = nil
    ) -> GameMarketsResponse {
        let resSource: String? = settled ? (resolutionSourceOverride ?? "api_settlement") : nil
        return GameMarketsResponse(
            eventId: 77101,
            homeTeam: "Islam Makhachev",
            awayTeam: "Arman Tsarukyan",
            status: settled ? "completed" : "live",
            homeScore: nil,
            awayScore: nil,
            playerProps: [],
            spreads: [],
            totals: [
                GameMarketOutcome(
                    _marketId: 504,
                    marketName: "Total Rounds Over/Under 2.5",
                    outcomeName: "Over",
                    probability: 0.58,
                    source: "polymarket",
                    threshold: 2.5,
                    overProbability: 0.58,
                    marketType: "total_rounds",
                    movement: nil,
                    period: nil,
                    isWinner: settled ? true : nil,
                    resolutionSource: resSource,
                    observedAt: observedAt,
                    pregameMark: 0.54
                ),
                GameMarketOutcome(
                    _marketId: 504,
                    marketName: "Total Rounds Over/Under 2.5",
                    outcomeName: "Under",
                    probability: 0.42,
                    source: "polymarket",
                    threshold: 2.5,
                    overProbability: 0.58,
                    marketType: "total_rounds",
                    movement: nil,
                    period: nil,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    observedAt: observedAt,
                    pregameMark: 0.54
                ),
            ],
            teamTotals: [],
            periodMarkets: [],
            other: [
                // Method of Victory
                GameMarketOther(
                    _marketId: 501,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Method of Victory",
                    outcomeName: "KO/TKO",
                    probability: 0.46,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.40
                ),
                GameMarketOther(
                    _marketId: 501,
                    isWinner: settled ? true : nil,
                    resolutionSource: resSource,
                    marketName: "Method of Victory",
                    outcomeName: "Submission",
                    probability: 0.22,
                    source: "polymarket",
                    observedAt: observedAt,
                    pregameMark: 0.25
                ),
                GameMarketOther(
                    _marketId: 501,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Method of Victory",
                    outcomeName: "Decision",
                    probability: 0.30,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.33
                ),
                GameMarketOther(
                    _marketId: 501,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Method of Victory",
                    outcomeName: "Draw",
                    probability: 0.02,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.02
                ),
                // Round of Victory
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Islam Makhachev in Round 1",
                    probability: 0.14,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.12
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Islam Makhachev in Round 2",
                    probability: 0.13,
                    source: "polymarket",
                    observedAt: observedAt,
                    pregameMark: 0.11
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? true : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Islam Makhachev in Round 3",
                    probability: 0.11,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.10
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Islam Makhachev in Round 4",
                    probability: 0.08,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.07
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Islam Makhachev in Round 5",
                    probability: 0.06,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.05
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Arman Tsarukyan in Round 1",
                    probability: 0.09,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.10
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Arman Tsarukyan in Round 2",
                    probability: 0.07,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.08
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Arman Tsarukyan in Round 3",
                    probability: 0.05,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.06
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Arman Tsarukyan in Round 4",
                    probability: 0.04,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.04
                ),
                GameMarketOther(
                    _marketId: 502,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Round of Victory",
                    outcomeName: "Arman Tsarukyan in Round 5",
                    probability: 0.03,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.03
                ),
                // Fight to Go the Distance
                GameMarketOther(
                    _marketId: 503,
                    isWinner: settled ? false : nil,
                    resolutionSource: resSource,
                    marketName: "Fight to Go the Distance",
                    outcomeName: "Yes",
                    probability: 0.32,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.36
                ),
                GameMarketOther(
                    _marketId: 503,
                    isWinner: settled ? true : nil,
                    resolutionSource: resSource,
                    marketName: "Fight to Go the Distance",
                    outcomeName: "No",
                    probability: 0.68,
                    source: "kalshi",
                    observedAt: observedAt,
                    pregameMark: 0.64
                ),
            ],
            pace: nil
        )
    }
}
