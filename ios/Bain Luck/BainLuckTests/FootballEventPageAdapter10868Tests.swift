import XCTest
@testable import Bain_Luck

/// #10868 — the football screen's page adapter (phase, teams, header and the
/// phase's headline) on RETAINED REAL bodies (`FootballRetained10868`: sources,
/// sha256 and reductions are listed there), decoded through the production
/// models exactly as the app decodes them.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED: the reader's calendar and each `now` (`FootballRetained10868`).
/// Every expected figure below is a served number: the pregame `current_odds`
/// 0.385/0.615 rendered 38/62 with projected 25.4/29.0; the live `current_odds`
/// 0.54412/0.45588 rendered 54/46, score 14–7 and `opening_odds` 0.2381/0.7619;
/// the final `prematch_odds` 0.235/0.765 rendered 23/77, score 17–19,
/// `hero_settled_result` home; the Packers `pregame_projection` 27.6/26.5.
@MainActor
final class FootballEventPageAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias A = FootballEventPageAdapter10868
    private typealias Side = NFLPairedHeadline9483.Side

    // MARK: - Before the start: Bills at Rams

    func testThePregameHeadlineIsTheServedPairWithItsProjectionAndBroadcast() throws {
        let event = try F.detail(F.pregameDetail)
        let host = F.pageHost(F.pregameNow, observedAt: F.pregameObservedAt)

        XCTAssertEqual(A.phase(event, now: F.pregameNow), .before)
        let teams = A.teams(event)
        XCTAssertEqual(teams.away, "Buffalo Bills")
        XCTAssertEqual(teams.home, "Los Angeles Rams")
        // No score is printed before the start, not even its absence.
        XCTAssertNil(A.header(event, phase: .before, host: host).score)

        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.sportKey, "americanfootball_nfl")
        guard case .before(let arm) = headline.arm else { return XCTFail("expected the pregame arm") }
        XCTAssertEqual(arm.paired, NFLPairedHeadline9483(
            away: Side(figure: "38%", pregame: nil, won: nil),
            home: Side(figure: "62%", pregame: nil, won: nil),
            center: .versus))
        XCTAssertFalse(arm.isOpeningLine)
        XCTAssertFalse(arm.hasStarted)
        XCTAssertEqual(arm.projected, FootballPointsPair10868(away: 25, home: 29))
        XCTAssertEqual(arm.forecastLabel, "Projected final")
        let start = try XCTUnwrap(event.commenceTime?.asDate)
        XCTAssertEqual(arm.pregameContext,
                       "ESPN, ABC · " + HockeyJourneyPageAdapter10868.clockWords(start, host: host.words))
        XCTAssertEqual(arm.chancePhase, EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: start, isOpeningLine: false,
            observedAt: F.pregameObservedAt, deliveryInterrupted: false, now: F.pregameNow))
    }

    // MARK: - During play: Eagles at Jaguars, 14–7

    func testTheLiveHeadlineCarriesTheServedPairOpeningLineScoreAndClock() throws {
        let event = try F.detail(F.liveDetail)
        let history = try F.history(F.liveHistory)
        let host = F.pageHost(F.liveNow, observedAt: F.liveObservedAt, history: history)

        XCTAssertEqual(A.phase(event, now: F.liveNow), .live)
        let teams = A.teams(event)
        let header = A.header(event, phase: .live, host: host)
        XCTAssertEqual(header.score, .actual(away: "14", home: "7",
                                             spoken: "\(teams.awayShort) 14, \(teams.homeShort) 7"))
        // The state is the period-and-clock owner's words (via H1), carrying
        // the served clock verbatim — never joined here.
        XCTAssertTrue(header.state.contains("13:31"), header.state)

        guard case .live(let arm) = A.headline(event, host: host).arm else {
            return XCTFail("expected the live arm")
        }
        XCTAssertEqual(arm.paired, NFLPairedHeadline9483(
            away: Side(figure: "54%", pregame: "Opened 24%", won: nil),
            home: Side(figure: "46%", pregame: "Opened 76%", won: nil),
            center: .score(away: 14, home: 7, final: false)))
        XCTAssertEqual(arm.baseline?.captionWord, "Opened")
        XCTAssertEqual(arm.score, .score(away: 14, home: 7, final: false))
        XCTAssertEqual(arm.gameState, header.state)
    }

    // MARK: - After the final

    func testTheFinalHeadlineSaysWhoWonAgainstThePrematchChance() throws {
        let event = try F.detail(F.finalDetail)
        let host = F.pageHost(F.finalNow, observedAt: nil)

        XCTAssertEqual(A.phase(event, now: F.finalNow), .final)
        guard case .final(let arm) = A.headline(event, host: host).arm else {
            return XCTFail("expected the final arm")
        }
        XCTAssertEqual(arm.paired, NFLPairedHeadline9483(
            away: Side(figure: "Lost", pregame: "Pre-match 23%", won: false),
            home: Side(figure: "Won", pregame: "Pre-match 77%", won: true),
            center: .score(away: 17, home: 19, final: true)))
        XCTAssertEqual(arm.baseline?.captionWord, "Pre-match")
        // No pregame projection is served on this detail, so no forecast is
        // printed — never one borrowed from the history.
        XCTAssertNil(arm.forecast)
        let state = HockeyJourneyPageAdapter10868.stateWords(event, phase: .final, host: host.words).state
        XCTAssertTrue(arm.finalContext.hasPrefix(state), arm.finalContext)
    }

    func testAQualifiedPregameProjectionIsTheFinalHeadlinesForecast() throws {
        let event = try F.detail(F.packersDetail)
        let host = F.pageHost(F.packersNow, observedAt: nil)
        guard case .final(let arm) = A.headline(event, host: host).arm else {
            return XCTFail("expected the final arm")
        }
        let forecast = try XCTUnwrap(arm.forecast)
        XCTAssertEqual(forecast.away, 27.6, accuracy: 1e-9)
        XCTAssertEqual(forecast.home, 26.5, accuracy: 1e-9)
        XCTAssertEqual(arm.paired?.home.figure, "Won")
        XCTAssertEqual(arm.paired?.away.figure, "Lost")
    }

    // MARK: - Phase separation

    func testEachPhaseBuildsOnlyItsOwnArm() throws {
        for (json, now, phase) in [(F.pregameDetail, F.pregameNow, FootballEventPagePhase10868.before),
                                   (F.liveDetail, F.liveNow, .live),
                                   (F.finalDetail, F.finalNow, .final)] {
            let event = try F.detail(json)
            let headline = A.headline(event, host: F.pageHost(now, observedAt: nil))
            XCTAssertEqual(headline.arm.phase, phase)
        }
    }
}
