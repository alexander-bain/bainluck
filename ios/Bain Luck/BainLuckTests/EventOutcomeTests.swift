import XCTest

@testable import Bain_Luck

/// #4915 — a draw is a RESULT, and the app had no way to say so.
///
/// Photographed on production 2026-09-10 (master `8ec73a3f`, iPhone 17), two
/// Champions League matches from the same night in the same build:
///
/// | | AS Roma 1 – 1 Fenerbahce | Bodø/Glimt 0 – 5 Bayern |
/// |---|---|---|
/// | hero verdict | `Final`, grey | **`Munich Win`**, bold, team blue |
/// | winner's score | — | `5` in `.primary` |
/// | other score | `1` in `.secondary` | `0` in `.secondary` |
/// | the drawn side's scores | **BOTH `.secondary`** | — |
///
/// The cause is one idiom repeated on every settled surface:
///
///     let homeWon = (event.homeScore ?? 0) > (event.awayScore ?? 0)
///     let awayWon = (event.awayScore ?? 0) > (event.homeScore ?? 0)
///
/// Two booleans, three outcomes. On a level result both are false, and every
/// caller read `!won` as "lost" — so the grey that means *this team lost* was
/// painted on both sides, and the verdict slot that says "Munich Win" degraded
/// to a bare status word. A reader who has learned the page's colour language
/// reads a 1–1 as *both teams lost*.
///
/// WHAT THESE TESTS PIN, and each one is a mutant:
///
/// 1. the three-way rule itself, over the matrix the old pair could not express;
/// 2. `won` and `isLoser` being DIFFERENT questions — `isLoser` is not `!won`;
/// 3. the server's `hero_settled_result` outranking our re-derivation;
/// 4. `undecided ≠ draw` — the `?? 0` trap in reverse, and the reason this
///    ships without newly printing "Draw" on every scoreless settled row.
///
/// WHAT THEY CANNOT PIN. A SwiftUI view BODY is invisible to XCTest, and the
/// hero's verdict and both dim treatments live in bodies. That the views
/// actually CALL this enum — and that the old `?? 0` pair has not grown back —
/// is asserted by `frontend/__tests__/ios/aDrawIsAResult4915.test.ts`, which
/// reads the Swift as text and runs in CI, which compiles no Swift.
final class EventOutcomeTests: XCTestCase {

    // MARK: - The matrix the old pair could not express

    /// The four scorelines from the issue, each asserted as a verdict AND as
    /// both sides' treatment. The two draw rows had no coverage at all before
    /// this file.
    func testTheFourScorelines() {
        // (home, away, expected)
        let matrix: [(Int, Int, EventOutcome)] = [
            (1, 1, .draw),   // AS Roma 1 – 1 Fenerbahce
            (0, 0, .draw),   // a real goalless draw, not a missing score
            (5, 0, .home),
            (0, 5, .away),
        ]

        for (home, away, expected) in matrix {
            let outcome = EventOutcome.resolve(
                status: "completed", homeScore: home, awayScore: away)
            XCTAssertEqual(
                outcome, expected,
                "\(home)–\(away) should read \(expected)")
        }
    }

    func testADecisiveResultHasExactlyOneWinnerAndExactlyOneLoser() {
        let homeWin = EventOutcome.resolve(status: "completed", homeScore: 5, awayScore: 0)

        XCTAssertTrue(homeWin.won(isAway: false))
        XCTAssertFalse(homeWin.won(isAway: true))
        XCTAssertTrue(homeWin.isLoser(isAway: true))
        XCTAssertFalse(homeWin.isLoser(isAway: false))

        let awayWin = EventOutcome.resolve(status: "completed", homeScore: 0, awayScore: 5)

        XCTAssertTrue(awayWin.won(isAway: true))
        XCTAssertFalse(awayWin.won(isAway: false))
        XCTAssertTrue(awayWin.isLoser(isAway: false))
        XCTAssertFalse(awayWin.isLoser(isAway: true))
    }

    /// THE DEFECT, stated as an assertion: on a draw nobody won — which the old
    /// pair also said — and **nobody lost**, which is the half it could not say.
    func testOnADrawNobodyWonAndNobodyLost() {
        let draw = EventOutcome.resolve(status: "completed", homeScore: 1, awayScore: 1)

        XCTAssertFalse(draw.won(isAway: true), "a draw has no winner")
        XCTAssertFalse(draw.won(isAway: false), "a draw has no winner")
        XCTAssertFalse(draw.isLoser(isAway: true), "the loser's grey has no side to sit on")
        XCTAssertFalse(draw.isLoser(isAway: false), "the loser's grey has no side to sit on")
    }

    /// `isLoser` is not `!won`, and this is the assertion that says so: if it
    /// were, the draw rows above would flip and the fix would be a rename.
    func testIsLoserIsNotTheNegationOfWon() {
        for outcome: EventOutcome in [.home, .away, .draw, .undecided] {
            for isAway in [true, false] {
                XCTAssertFalse(
                    outcome.won(isAway: isAway) && outcome.isLoser(isAway: isAway),
                    "\(outcome) cannot both win and lose as \(isAway ? "away" : "home")")
            }
        }

        // …and they genuinely DISAGREE on the draw, or the assertion above is
        // satisfied by `isLoser` simply being `!won` under another name — which
        // is the bug, spelled differently.
        XCTAssertFalse(EventOutcome.draw.won(isAway: true), "not the winner")
        XCTAssertFalse(
            EventOutcome.draw.isLoser(isAway: true),
            "and yet not the loser: `!won` and `isLoser` are different questions")
    }

    func testOnlyADrawCarriesTheWord() {
        XCTAssertEqual(EventOutcome.draw.drawLabel, "Draw")
        XCTAssertNil(EventOutcome.home.drawLabel)
        XCTAssertNil(EventOutcome.away.drawLabel)
        XCTAssertNil(EventOutcome.undecided.drawLabel, "an ungraded final is not a draw")
    }

    // MARK: - The server graded it; we do not re-derive it

    func testTheServedVerdictIsTheAuthority() {
        // Scores that would read `home`, and a server that says otherwise.
        XCTAssertEqual(
            EventOutcome.resolve(
                status: "completed", homeScore: 2, awayScore: 1, servedResult: "away"),
            .away,
            "hero_settled_result outranks our comparison, as `settled` outranks the blend")

        XCTAssertEqual(
            EventOutcome.resolve(
                status: "completed", homeScore: 2, awayScore: 1, servedResult: "draw"),
            .draw)

        XCTAssertEqual(
            EventOutcome.resolve(
                status: "completed", homeScore: 1, awayScore: 1, servedResult: "home"),
            .home)
    }

    /// The route OMITS the key on a game it cannot grade, so absent is ordinary
    /// and must not disable the scores.
    func testAnAbsentVerdictFallsBackToTheScores() {
        XCTAssertEqual(
            EventOutcome.resolve(
                status: "completed", homeScore: 1, awayScore: 1, servedResult: nil),
            .draw)
    }

    /// Open-set discipline: a value we do not know is not a verdict, and it is
    /// also not a reason to print nothing. `EventState` treats `status` the
    /// same way.
    func testAnUnrecognisedVerdictFallsThroughRatherThanWinning() {
        for junk in ["", "tie", "HOME", "abandoned", "null", "0"] {
            XCTAssertEqual(
                EventOutcome.resolve(
                    status: "completed", homeScore: 3, awayScore: 1, servedResult: junk),
                .home,
                "\(junk) is not one of the three verdicts, so the scores decide")
        }
    }

    // MARK: - `undecided` is a real state and never a zero

    /// 🔴 THE TRAP THIS FIX WAS WRITTEN AROUND. Under `?? 0` a game we hold no
    /// score for is `0 == 0`, which is indistinguishable from a genuine goalless
    /// draw — so the naive version of this rule would newly print **Draw** on
    /// every scoreless settled row. Both scores must be present before the word
    /// is earned.
    func testAFinishedGameWithNoScoreIsUndecidedNotADraw() {
        let cases: [(Int?, Int?)] = [(nil, nil), (1, nil), (nil, 1), (0, nil), (nil, 0)]

        for (home, away) in cases {
            let outcome = EventOutcome.resolve(
                status: "completed", homeScore: home, awayScore: away)
            XCTAssertEqual(
                outcome, .undecided,
                "\(String(describing: home))–\(String(describing: away)) names no result")
            XCTAssertNil(outcome.drawLabel, "and it must not borrow the draw's word")
            XCTAssertFalse(outcome.isLoser(isAway: true))
            XCTAssertFalse(outcome.isLoser(isAway: false))
        }
    }

    /// The whole status vocabulary, so a new state cannot quietly start
    /// claiming a verdict the way `suspended` quietly lost one (#4002).
    func testOnlyAFinishedStatusCanCarryAResult() {
        let finished = ["completed", "closed"]
        let notFinished: [String?] = [
            "scheduled", "live", "suspended", "postponed", "cancelled", nil,
        ]

        for status in finished {
            XCTAssertEqual(
                EventOutcome.resolve(status: status, homeScore: 1, awayScore: 1),
                .draw, "\(status) is settled")
            XCTAssertEqual(
                EventOutcome.resolve(status: status, homeScore: 2, awayScore: 1),
                .home, "\(status) is settled")
        }

        for status in notFinished {
            XCTAssertEqual(
                EventOutcome.resolve(status: status, homeScore: 1, awayScore: 1),
                .undecided,
                "\(status ?? "nil") is level, not drawn — the match is not over")
            XCTAssertEqual(
                EventOutcome.resolve(status: status, homeScore: 2, awayScore: 1),
                .undecided,
                "\(status ?? "nil") has a leader, not a winner")
        }
    }

    /// A served verdict does not smuggle the settled treatment onto a row the
    /// client's own status vocabulary says is still running.
    func testAServedVerdictOnAnUnfinishedRowIsStillUndecided() {
        XCTAssertEqual(
            EventOutcome.resolve(
                status: "live", homeScore: 1, awayScore: 1, servedResult: "draw"),
            .undecided)
    }

    // MARK: - The wire

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    /// The photographed specimen, in the orientation production actually serves
    /// it (`GET /api/events/15296761`, read 2026-09-11: Fenerbahce is HOME —
    /// the issue's table names the fixture the other way round).
    private static let romaFenerbahce = """
        {"id": 15296761, "home_team": "Fenerbahce", "away_team": "AS Roma",
         "status": "completed", "home_score": 1, "away_score": 1,
         "hero_settled_result": "draw", "hero_probability_source": "settled"}
        """

    func testHeroSettledResultReachesTheModel() throws {
        let event = try decodeEvent(Self.romaFenerbahce)

        XCTAssertEqual(
            event.heroSettledResult, "draw",
            "`hero_settled_result` arrives via .convertFromSnakeCase")
        XCTAssertEqual(
            EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult),
            .draw,
            "the payload the hero was photographed on now reads as a draw")
    }

    /// The key is OMITTED, not null, on an ungraded game — so its absence must
    /// not fail the event's decode.
    func testAnEventWithNoServedVerdictStillDecodes() throws {
        let event = try decodeEvent(
            """
            {"id": 1, "home_team": "A", "away_team": "B",
             "status": "completed", "home_score": 4, "away_score": 2}
            """)

        XCTAssertNil(event.heroSettledResult)
        XCTAssertEqual(
            EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult),
            .home)
    }
}
