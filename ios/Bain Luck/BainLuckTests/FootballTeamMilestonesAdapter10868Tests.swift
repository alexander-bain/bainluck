import XCTest
@testable import Bain_Luck

/// #10868 — team sacks and team field goals, paired, on RETAINED REAL bodies
/// (`FootballRetained10868` lists the sources, sha256 and reductions).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The one team-stat market these bodies serve is Kalshi's "Team Field Goals":
///   - Bills at Rams, pregame (market 65113459), read at its own capture
///     05:45:12Z: Rams 1+ 0.755 undated, 2+ 0.55 at 05:40:37Z, 3+ 0.30 at
///     04:54:09Z, 4+ 0.245 at 04:55:09Z; Buffalo 1+ 0.735 at 05:41:55Z, 2+ 0.495
///     at 04:45:51Z, 3+ 0.275 at 05:41:23Z, 4+ 0.255 at 05:41:56Z. Only quotes
///     inside the page's 30-minute window print.
///   - Eagles at Jaguars, live (market 65113446): marks Philadelphia 0.78 / 0.51
///     / 0.27, Jacksonville 0.785 / 0.545 / 0.275; in-play Philadelphia 1+ 0.655
///     at 15:34:44Z, Jacksonville 1+ 0.65 at 15:34:46Z.
///   - the same market final, `api_settlement`: Jacksonville 1+ won, 2+ won,
///     3+ lost, 4+ lost; Philadelphia 1+ won, 2+ 3+ 4+ lost.
/// No sacks market is served in any of them.
@MainActor
final class FootballTeamMilestonesAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias T = FootballTeamMilestonesAdapter10868
    private typealias H3 = HockeyJourneyContributionAdapter10868

    private func befores(_ input: PairedMilestoneInput10868) -> [[Double?]] {
        input.groups.map { [$0.first.original?.before?.probability, $0.second.original?.before?.probability] }
    }

    // MARK: - Live

    func testTheLiveFieldGoalCardPairsBothClubsFromOneMarketInServedOrder() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(F.liveMarkets)
        let input = try XCTUnwrap(T.input(.fieldGoals, event: event, markets: markets, host: F.teamHost(F.liveNow)))

        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.orientation, .columns)
        XCTAssertEqual(input.cardID, "teamFieldGoals")
        XCTAssertEqual(input.eyebrow, "TEAM FIELD GOALS")
        XCTAssertEqual(input.title, "The kicking game")
        XCTAssertEqual(input.definition, T.Words.definition)
        XCTAssertEqual(input.first.name, "Philadelphia")
        XCTAssertEqual(input.second.name, "Jacksonville")
        XCTAssertNil(input.first.countSoFar)
        XCTAssertEqual(input.first.countMissing, H3.Words.countUnavailable)
        XCTAssertEqual(input.groups.map(\.id), ["teamFieldGoals:1+", "teamFieldGoals:2+", "teamFieldGoals:3+"])
        XCTAssertEqual(input.groups.map(\.title), ["1+ field goals", "2+ field goals", "3+ field goals"])
        // No milestone is chosen for the reader.
        XCTAssertNil(input.selectedGroupID)
        XCTAssertEqual(befores(input), [[0.78, 0.785], [0.51, 0.545], [0.27, 0.275]])

        let first = try XCTUnwrap(input.groups.first?.first.original)
        let row = try XCTUnwrap(markets.playerProps?.first { $0.outcomeName == "Philadelphia: 1+" })
        XCTAssertEqual(first.id, H3.milestoneID(row))
        XCTAssertEqual(first.title, "Philadelphia 1+ field goals")
        guard case .recorded(let reading, _) = first.current else {
            return XCTFail("expected the row's own in-play reading, got \(first.current)")
        }
        XCTAssertEqual(reading.probability, 0.655)
        XCTAssertEqual(first.current, H3.inGameReading(row, reachedSoFar: false, event: event,
                                                        host: F.teamHost(F.liveNow).contribution))
        // During play nothing is graded, and no count is claimed.
        XCTAssertTrue(input.groups.allSatisfy {
            $0.first.original?.result == .unconfirmed(H3.Words.unconfirmed)
                && $0.second.original?.result == .unconfirmed(H3.Words.unconfirmed)
        })
    }

    func testNoSacksMarketIsNoSacksCard() throws {
        for (detail, markets, now) in [(F.pregameDetail, F.pregameMarkets, F.pregameNow),
                                       (F.liveDetail, F.liveMarkets, F.liveNow),
                                       (F.finalDetail, F.finalMarkets, F.finalNow)] {
            XCTAssertNil(T.input(.sacks, event: try F.detail(detail), markets: try F.markets(markets),
                                 host: F.teamHost(now)))
        }
    }

    // MARK: - Final

    func testTheFinalFieldGoalCardPrintsEachClubsOwnSettlement() throws {
        let event = try F.detail(F.finalDetail)
        let markets = try F.markets(F.finalMarkets)
        let input = try XCTUnwrap(T.input(.fieldGoals, event: event, markets: markets, host: F.teamHost(F.finalNow)))

        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.first.name, "Jacksonville")
        XCTAssertEqual(input.second.name, "Philadelphia")
        XCTAssertEqual(input.first.countMissing, H3.Words.finalCountUnavailable)
        XCTAssertEqual(input.groups.map(\.target), ["1+", "2+", "3+", "4+"])
        XCTAssertEqual(befores(input), [[0.785, 0.78], [0.545, 0.51], [0.275, 0.27], [0.275, 0.25]])
        let reached = PlayerContributionResult10868.reached(H3.Words.reached)
        let missed = PlayerContributionResult10868.missed(H3.Words.missed)
        XCTAssertEqual(input.groups.map { $0.first.original?.result }, [reached, reached, missed, missed])
        XCTAssertEqual(input.groups.map { $0.second.original?.result }, [reached, missed, missed, missed])
        // A settled row is never an in-game chance.
        XCTAssertTrue(input.groups.allSatisfy {
            $0.first.original?.current == .unavailable(H3.Words.noInGameReading)
        })
    }

    func testAnUnauthoritativeGradeIsUnconfirmedNeverALoss() throws {
        let event = try F.detail(F.finalDetail)
        // CONSTRUCTED: Philadelphia's rows with their resolution source removed.
        let markets = try F.markets(F.editedProps(
            F.finalMarkets, marketName: "Philadelphia vs Jacksonville: Team Field Goals", subject: "Philadelphia",
            setting: ["resolution_source": NSNull()]))
        let input = try XCTUnwrap(T.input(.fieldGoals, event: event, markets: markets, host: F.teamHost(F.finalNow)))
        XCTAssertTrue(input.groups.allSatisfy { $0.second.original?.result == .unconfirmed(H3.Words.unconfirmed) })
        XCTAssertEqual(input.groups.first?.first.original?.result, .reached(H3.Words.reached))
    }

    // MARK: - Before the start

    func testAPregameQuoteOutsideThePagesWindowPrintsItsAbsenceNotItsNumber() throws {
        let event = try F.detail(F.pregameDetail)
        let markets = try F.markets(F.pregameMarkets)
        let input = try XCTUnwrap(T.input(.fieldGoals, event: event, markets: markets,
                                          host: F.teamHost(F.pregameNow)))

        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.first.name, "Los Angeles Rams")
        XCTAssertEqual(input.second.name, "Buffalo")
        XCTAssertEqual(befores(input), [[nil, 0.735], [0.55, nil], [nil, 0.275], [nil, 0.255]])
        let undated = try XCTUnwrap(input.groups.first?.first.original)
        XCTAssertEqual(undated.beforeMissing, H3.Words.noRecentUpdate)
        XCTAssertEqual(undated.current, .unavailable(H3.Words.noInGameReading))
        XCTAssertEqual(undated.result, .unconfirmed(H3.Words.unconfirmed))
    }

    func testTheHeldMilestoneIsPassedThroughExactly() throws {
        let input = try XCTUnwrap(T.input(.fieldGoals, event: try F.detail(F.liveDetail),
                                          markets: try F.markets(F.liveMarkets), host: F.teamHost(F.liveNow),
                                          selectedGroupID: "teamFieldGoals:2+"))
        XCTAssertEqual(input.selectedGroupID, "teamFieldGoals:2+")
    }
}
