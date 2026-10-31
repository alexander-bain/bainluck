import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part one (phase, route, state words,
/// matrix, projection), on the RETAINED REAL bodies in
/// `BaseballRetainedAdapter10868Tests` (`BaseballRetained10868`): Chicago White
/// Sox at Houston Astros after its 7–3 final, and the two CONSTRUCTED earlier
/// phases of that same detail (`liveEvent`, `beforeEvent`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// Every expected figure is the production formatter's own output for the
/// served value (`formatProbability`), and every clock or day is the adapter's
/// own words for the served instant, so a test pins the rule, not a spelling a
/// locale could move. CONSTRUCTED variants change exactly the keys they name.
@MainActor
final class BaseballGamePageAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias A = BaseballGamePageAdapter10868

    private static let noProjection = BaseballProjection10868(title: "Projected final",
                                                              reading: .unavailable("Projected final unavailable"))

    // MARK: - Phase and route

    func testEachBodyReadsAsItsOwnPhaseAndOnlyMLBTakesTheRoute() throws {
        XCTAssertEqual(A.phase(try F.finalEvent(), now: F.finalNow), .final)
        XCTAssertEqual(A.phase(try F.liveEvent(), now: F.liveNow), .live)
        XCTAssertEqual(A.phase(try F.beforeEvent(), now: F.beforeNow), .before)
        // The phase is the status, never the clock: a scheduled game past its
        // listed start is still before first pitch.
        XCTAssertEqual(A.phase(try F.beforeEvent(), now: F.liveNow), .before)

        XCTAssertTrue(A.applies(try F.finalEvent()))
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw("baseball_mlb"), "baseball's winner market prices no draw")
        // CONSTRUCTED: only `sport` changed.
        XCTAssertFalse(A.applies(try F.detail(F.edited(F.finalDetail, setting: ["sport": "icehockey_nhl"]))))
        XCTAssertFalse(A.applies(try F.detail(F.edited(F.finalDetail, setting: ["sport": "baseball_ncaa"]))))
    }

    /// CONSTRUCTED: `liveEvent` with `status` `suspended`. A started suspended
    /// game is during play and wears the app's one suspended treatment.
    func testAStartedSuspendedGameWearsTheSuspendedTreatment() throws {
        let event = try F.liveEvent(["status": "suspended"])
        XCTAssertEqual(A.phase(event, now: F.liveNow), .live)
        let headline = A.headline(event, host: F.pageHost(F.liveNow, observedAt: F.liveObservedAt))
        XCTAssertEqual(headline.state, EventState.suspendedLabel(authorityPeriod: nil))
        XCTAssertNil(headline.stateContext, "this body serves no ESPN game state")
    }

    // MARK: - After the final

    func testAfterTheFinalThePregameChanceSitsBesideTheFinalRunsAndTheServedResult() throws {
        let event = try F.finalEvent()
        let host = F.pageHost(F.finalNow, observedAt: nil)
        let headline = A.headline(event, host: host)
        guard case .final(let matrix) = headline.matrix else { return XCTFail("a final matrix") }

        XCTAssertEqual(matrix.pregameChance, BaseballColumn10868(title: "Pregame chance", provenance: "Pre-match · Kalshi"))
        XCTAssertEqual(matrix.home.pregameChance, .value(formatProbability(0.585, renderedPercent: 59), spoken: "59 percent"))
        XCTAssertEqual(matrix.away.pregameChance, .value(formatProbability(0.415, renderedPercent: 41), spoken: "41 percent"))
        XCTAssertEqual(matrix.finalRuns, BaseballColumn10868(title: "Final runs", provenance: "Final score"))
        XCTAssertEqual(matrix.home.finalRuns, .value("3", spoken: "3 runs"))
        XCTAssertEqual(matrix.away.finalRuns, .value("7", spoken: "7 runs"))
        XCTAssertEqual(matrix.home.result, "Lost")
        XCTAssertEqual(matrix.away.result, "Won")
        // The settled hero (0.0 / 1.0) is a result, never a chance.
        XCTAssertFalse([matrix.home.pregameChance.text, matrix.away.pregameChance.text].contains(formatProbability(1.0)))

        XCTAssertEqual(headline.eyebrow, "MLB")
        XCTAssertEqual(headline.state, "Final")
        XCTAssertEqual(headline.stateContext, A.dayWords(F.start, host: host))
        XCTAssertEqual(headline.projection, Self.noProjection, "no projected final is admitted for baseball")
        XCTAssertEqual(headline.spokenLabel, "Baseball win chances and runs")

        let names = A.names(event)
        XCTAssertEqual(headline.home.name, "Houston Astros")
        XCTAssertEqual(headline.away.name, "Chicago White Sox")
        XCTAssertEqual(headline.home.short, names.home == event.homeTeam ? nil : names.home)
        XCTAssertEqual(headline.away.short, names.away == event.awayTeam ? nil : names.away)
        XCTAssertEqual(headline.home.tint, A.tints(event).home)
        XCTAssertEqual(headline.away.tint, A.tints(event).away)
    }

    /// CONSTRUCTED: the final detail with `hero_settled_result` and
    /// `away_score` removed. Unknown is not loss: no side is named either way.
    func testAnUndecidedFinalNamesNoWinnerAndNoLoserAndNoScore() throws {
        let event = try F.detail(F.edited(F.finalDetail, removing: ["hero_settled_result", "away_score"]))
        guard case .final(let matrix) = A.headline(event, host: F.pageHost(F.finalNow, observedAt: nil)).matrix
        else { return XCTFail("a final matrix") }
        XCTAssertNil(matrix.home.result)
        XCTAssertNil(matrix.away.result)
        XCTAssertEqual(matrix.home.finalRuns, .unavailable("Score unavailable"))
        XCTAssertEqual(matrix.away.finalRuns, .unavailable("Score unavailable"))
        XCTAssertNil(matrix.finalRuns.provenance)
    }

    // MARK: - During play

    func testDuringPlayTheServedPairIsCurrentOnlyWhileItsOwnClockIsFresh() throws {
        let event = try F.liveEvent()
        let host = F.pageHost(F.liveNow, observedAt: F.liveObservedAt)
        let headline = A.headline(event, host: host)
        guard case .live(let matrix) = headline.matrix else { return XCTFail("a live matrix") }

        XCTAssertEqual(matrix.currentChance, BaseballColumn10868(
            title: "Current chance", provenance: "Recorded \(A.clockWords(F.liveObservedAt, host: host))"))
        XCTAssertEqual(matrix.home.currentChance, .value(formatProbability(0.001, renderedPercent: 0), spoken: "under 1 percent"))
        XCTAssertEqual(matrix.away.currentChance, .value(formatProbability(0.999, renderedPercent: 100), spoken: "over 99 percent"))
        XCTAssertEqual(matrix.pregameChance, BaseballColumn10868(title: "Pregame chance", provenance: "Pre-match · Kalshi"))
        XCTAssertEqual(matrix.home.pregameChance.text, formatProbability(0.585, renderedPercent: 59))
        // No score clock is served on this body: the runs say no time.
        XCTAssertEqual(matrix.runs, BaseballColumn10868(title: "Runs", provenance: nil))
        XCTAssertEqual(matrix.home.runs, .value("3", spoken: "3 runs"))
        XCTAssertEqual(matrix.away.runs, .value("7", spoken: "7 runs"))
        XCTAssertEqual(headline.state, "Live")
        XCTAssertEqual(headline.stateContext, "Inning unavailable", "this body serves no ESPN period")
        // The served `current_odds` carries no live projection object.
        XCTAssertEqual(headline.projection, Self.noProjection)

        // Undated: never current, and no clock is invented.
        guard case .live(let undated) = A.headline(event, host: F.pageHost(F.liveNow, observedAt: nil)).matrix
        else { return XCTFail("a live matrix") }
        XCTAssertEqual(undated.currentChance, BaseballColumn10868(title: "Last recorded chance", provenance: nil))

        // Stale (31 minutes old) or interrupted: last recorded, with its own clock.
        let late = F.liveObservedAt.addingTimeInterval(31 * 60)
        guard case .live(let stale) = A.headline(event, host: F.pageHost(late, observedAt: F.liveObservedAt)).matrix,
              case .live(let interrupted) = A.headline(
                event, host: F.pageHost(F.liveNow, observedAt: F.liveObservedAt, interrupted: true)).matrix
        else { return XCTFail("live matrices") }
        XCTAssertEqual(stale.currentChance.title, "Last recorded chance")
        XCTAssertEqual(stale.currentChance.provenance, "Recorded \(A.clockWords(F.liveObservedAt, host: host))")
        XCTAssertEqual(interrupted.currentChance.title, "Last recorded chance")
    }

    /// CONSTRUCTED: `liveEvent` with `venue_settled` true. Once the venue has
    /// settled the game, its price is a result and never the current chance.
    func testAVenueSettledGameShowsNoCurrentChance() throws {
        let event = try F.liveEvent(["venue_settled": true])
        guard case .live(let matrix) = A.headline(event, host: F.pageHost(F.liveNow, observedAt: F.liveObservedAt)).matrix
        else { return XCTFail("a live matrix") }
        XCTAssertEqual(matrix.currentChance, BaseballColumn10868(title: "Current chance", provenance: nil))
        XCTAssertEqual(matrix.home.currentChance, .unavailable("Win chance unavailable"))
        XCTAssertEqual(matrix.away.currentChance, .unavailable("Win chance unavailable"))
        XCTAssertTrue(matrix.home.pregameChance.isValue, "the pregame reading is still the pregame reading")
    }

    /// CONSTRUCTED: `liveEvent` with `espn` replaced by its own served
    /// `espn_id`, `broadcast` and `win_probability` plus the period ESPN served
    /// for this game at 22:11:06Z ("Middle 3rd", the live history fixture's last
    /// ESPN row), and `score_observed_at` set to 00:15:00Z.
    func testDuringPlayTheInningIsESPNsOwnWordsAndTheScoreKeepsItsOwnClock() throws {
        let scored = "2026-10-01T00:15:00+00:00"
        let event = try F.liveEvent([
            "espn": ["espn_id": "401907897", "broadcast": "Peacock, NBCSN", "win_probability": 0.043,
                     "period": "Middle 3rd"] as [String: Any],
            "score_observed_at": scored,
        ])
        let host = F.pageHost(F.liveNow, observedAt: F.liveObservedAt)
        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.state, "Middle 3rd", "the app's live status rule keeps an inning whole")
        XCTAssertEqual(headline.stateContext, "Game state from ESPN")
        guard case .live(let matrix) = headline.matrix else { return XCTFail("a live matrix") }
        XCTAssertEqual(matrix.runs.provenance, "Score observed \(A.clockWords(scored.asDate!, host: host))")
    }

    /// CONSTRUCTED: `liveEvent` with `home_score` null. A missing score is the
    /// slot's own words, never a 0.
    func testAMissingScoreIsUnavailableNeverZero() throws {
        let event = try F.liveEvent(["home_score": NSNull()])
        guard case .live(let matrix) = A.headline(event, host: F.pageHost(F.liveNow, observedAt: F.liveObservedAt)).matrix
        else { return XCTFail("a live matrix") }
        XCTAssertEqual(matrix.home.runs, .unavailable("Score unavailable"))
        XCTAssertEqual(matrix.away.runs, .unavailable("Score unavailable"))
        XCTAssertNil(matrix.runs.provenance)
    }

    // MARK: - Before first pitch

    func testBeforeFirstPitchTheChanceIsTheHerosPairAndTheStartIsNamed() throws {
        let event = try F.beforeEvent()
        let host = F.pageHost(F.beforeNow, observedAt: F.beforeObservedAt)
        let headline = A.headline(event, host: host)
        guard case .before(let matrix) = headline.matrix else { return XCTFail("a before matrix") }

        XCTAssertEqual(matrix.chance, BaseballColumn10868(
            title: "Current chance", provenance: "Recorded \(A.clockWords(F.beforeObservedAt, host: host))"))
        XCTAssertEqual(matrix.home.chance, .value("59%", spoken: "59 percent"))
        XCTAssertEqual(matrix.away.chance, .value("41%", spoken: "41 percent"))
        XCTAssertEqual(headline.state, "Before first pitch")
        XCTAssertEqual(headline.stateContext,
                       "\(A.dayWords(F.start, host: host)) · First pitch \(A.timeWords(F.start, host: host))")
        XCTAssertEqual(headline.projection, Self.noProjection)

        // A quote from before the listed start, read after it — ten minutes past
        // first pitch, the quote itself only twelve minutes old — is never current.
        let pastStart = F.start.addingTimeInterval(10 * 60)
        guard case .before(let late) = A.headline(event, host: F.pageHost(pastStart, observedAt: F.beforeObservedAt)).matrix
        else { return XCTFail("a before matrix") }
        XCTAssertEqual(late.chance.title, "Last recorded chance")
    }

    /// CONSTRUCTED: `beforeEvent` with `start_is_tbd` true, then with
    /// `current_odds` null.
    func testAnUnconfirmedStartAndAMissingPairSayTheirOwnWords() throws {
        let host = F.pageHost(F.beforeNow, observedAt: F.beforeObservedAt)
        let tbd = A.headline(try F.beforeEvent(["start_is_tbd": true]), host: host)
        XCTAssertEqual(tbd.stateContext, "\(A.dayWords(F.start, host: host)) · First pitch time to be announced")

        guard case .before(let matrix) = A.headline(try F.beforeEvent(["current_odds": NSNull()]), host: host).matrix
        else { return XCTFail("a before matrix") }
        XCTAssertEqual(matrix.chance, BaseballColumn10868(title: "Win chance", provenance: nil))
        XCTAssertEqual(matrix.home.chance, .unavailable("Win chance unavailable"))
        XCTAssertEqual(matrix.away.chance, .unavailable("Win chance unavailable"))
    }

    // MARK: - Words

    func testFiguresAreSaidInWordsAndOnlyServedSourceNamesArePrinted() throws {
        XCTAssertEqual(A.spokenPercent("<1%"), "under 1 percent")
        XCTAssertEqual(A.spokenPercent(">99%"), "over 99 percent")
        XCTAssertEqual(A.spokenPercent("59%"), "59 percent")

        let event = try F.finalEvent()
        XCTAssertEqual(A.sourceName("mlb", in: event), "MLB Model")
        XCTAssertEqual(A.sourceName("stat_model", in: event), "Bain Luck Model")
        XCTAssertNil(A.sourceName("betting_book_count", in: event), "a display name that is only the key is no name")
        XCTAssertNil(A.sourceName("settled", in: event), "an unserved source is left unnamed")
        XCTAssertNil(A.sourceName(nil, in: event))

        XCTAssertEqual(A.joined([nil, "", "Pre-match", "Kalshi"]), "Pre-match · Kalshi")
        XCTAssertNil(A.joined([nil, ""]))
        XCTAssertEqual(A.scorePair(event)?.home, 3)
        XCTAssertEqual(A.scorePair(event)?.away, 7)
        // CONSTRUCTED: a negative served score is no score.
        XCTAssertNil(A.scorePair(try F.detail(F.edited(F.finalDetail, setting: ["home_score": -1]))))
    }
}
