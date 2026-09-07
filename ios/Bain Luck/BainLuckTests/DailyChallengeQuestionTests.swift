import XCTest
@testable import Bain_Luck

/// #3858 — the Daily Challenge asked a question that could not be answered.
///
/// First photograph of `bainluck://daily` on any device
/// (`artifacts-native-053/LOOK-daily-phone.png`, iPhone 17 against production,
/// 2026-09-07 04:32):
///
///     Question 1 of 5
///     Milwaukee Brewers vs Chicago Cubs      <- headline
///     Milwaukee Brewers vs Chicago Cubs      <- subject, identical
///                   56%
///       [ ↑ Higher ]      [ ↓ Lower ]
///
/// Two defects in one card. The 56% is the HOME side's win probability — the view
/// model reaches for `currentOdds.homeProbability` on purpose — but the only text
/// on screen names both clubs, so a reader cannot know whose number they are
/// betting against. And the title is printed twice, which the code guaranteed:
/// `headline` fell back to the very string `subject` was built from.
///
/// `DailyChallengeViewModel` had NO test file. It has one now. The build path was
/// unreachable from a test at all until #3858 lifted the naming out of `load()`,
/// which owns the network call — the copy decisions are now pure and the feed
/// call is all that is left inside.
///
/// THE FUTURES BRANCH IS TESTED AS HEAVILY AS THE EVENT ONE even though only the
/// event card was photographed: it carried the identical defect one `else` later,
/// with the probability belonging to the top OUTCOME while the subject named the
/// MARKET. Fixing only what the camera caught would have left the same card
/// unanswerable on half its questions.
final class DailyChallengeQuestionTests: XCTestCase {

    private func item(_ json: String) throws -> FeedItem {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedItem.self, from: Data(json.utf8))
    }

    /// The photographed card, as the feed actually served it: an event with a
    /// home-side price and NO headline of its own, which is the case the fallback
    /// duplicated.
    private func brewersCubs(headline: String? = nil) throws -> FeedItem {
        let headlineField = headline.map { "\"headline\": \"\($0)\"," } ?? ""
        return try item("""
        {"type": "event", "score": 70, \(headlineField)
         "data": {"id": 15305001, "home_team": "Milwaukee Brewers",
                   "away_team": "Chicago Cubs", "sport": "baseball_mlb",
                   "current_odds": {"home_probability": 0.56}}}
        """)
    }

    private func futures(name: String, outcome: String, probability: Double) throws -> FeedItem {
        try item("""
        {"type": "futures", "score": 70,
         "data": {"id": 4242, "name": "\(name)", "llm_sport_category": "baseball",
                     "top_outcomes": [{"id": 9, "name": "\(outcome)",
                                       "probability": \(probability)}]}}
        """)
    }

    // MARK: - 1. Whose number is it?

    func testAnEventQuestionNamesTheSideTheNumberBelongsTo() throws {
        let q = try XCTUnwrap(DailyChallengeViewModel.question(from: try brewersCubs()))
        // The whole ship: 56% now has an owner.
        XCTAssertEqual(q.subject, "Milwaukee Brewers to win")
        XCTAssertEqual(q.probability, 0.56, accuracy: 0.0001)
    }

    func testTheNamedSideIsTheONEThePriceIsFor() throws {
        // The failure this must never allow back: naming the away side, or naming
        // whichever club the headline happens to mention first, while showing the
        // home price. A reader cannot detect that error, which is why it is pinned
        // against the field the view model actually reads.
        let q = try XCTUnwrap(DailyChallengeViewModel.question(from: try brewersCubs()))
        let subject = try XCTUnwrap(q.subject)
        XCTAssertTrue(subject.hasPrefix("Milwaukee Brewers"), "named the wrong side: \(subject)")
        XCTAssertFalse(subject.contains("Chicago Cubs"), "named both sides again: \(subject)")
    }

    func testAFuturesQuestionNamesTheOutcomeNotTheMarket() throws {
        // The same defect one `else` later, and the one the camera never saw.
        let q = try XCTUnwrap(DailyChallengeViewModel.question(
            from: try futures(name: "World Series 2026 winner",
                              outcome: "Los Angeles Dodgers", probability: 0.22)))
        XCTAssertEqual(q.headline, "World Series 2026 winner")
        XCTAssertEqual(q.subject, "Los Angeles Dodgers")
    }

    func testTheFuturesSubjectIsNotSuffixedWithToWin() throws {
        // A moneyline probability really is a probability of WINNING, so the event
        // subject says so. A futures market may be asking anything at all and its
        // top outcome is very often "Yes" — "Yes to win" would be a new #3858
        // rather than a fix for this one.
        let q = try XCTUnwrap(DailyChallengeViewModel.question(
            from: try futures(name: "Will the Fed cut rates in December?",
                              outcome: "Yes", probability: 0.61)))
        XCTAssertEqual(q.subject, "Yes")
    }

    // MARK: - 2. The title printed twice

    func testAnEventWithNoFeedHeadlineNoLongerPrintsOneStringTwice() throws {
        // THE PHOTOGRAPHED STATE. Before #3858 both lines read
        // "Milwaukee Brewers vs Chicago Cubs", because `headline` fell back to the
        // string `subject` was built from.
        let q = try XCTUnwrap(DailyChallengeViewModel.question(from: try brewersCubs()))
        XCTAssertEqual(q.headline, "Milwaukee Brewers vs Chicago Cubs")
        XCTAssertNotEqual(q.subject, q.headline)
    }

    func testAHeadlineThatAlreadySaysItDropsTheSubjectRatherThanRepeatIt() throws {
        // The remainder the naming fix cannot reach: a feed headline that IS the
        // subject. The card says it once. `nil`, not "", so the view cannot draw a
        // blank line where a sentence belongs.
        let q = try XCTUnwrap(DailyChallengeViewModel.question(
            from: try brewersCubs(headline: "Milwaukee Brewers to win")))
        XCTAssertEqual(q.headline, "Milwaukee Brewers to win")
        XCTAssertNil(q.subject)
    }

    func testNoQuestionEverRepeatsItself() {
        // The sweep, rather than the two cases above: whatever the feed sends, the
        // card never prints the same sentence twice. This is the assertion that
        // survives someone rewriting either string.
        for headline in [nil, "Milwaukee Brewers to win", "Brewers host Cubs",
                         "Milwaukee Brewers vs Chicago Cubs"] {
            guard let q = try? DailyChallengeViewModel.question(
                from: try brewersCubs(headline: headline)) else {
                XCTFail("headline \(headline ?? "nil") produced no question")
                continue
            }
            if let subject = q.subject {
                XCTAssertNotEqual(subject, q.headline,
                                  "headline \(headline ?? "nil") printed twice")
            }
        }
    }

    // MARK: - A real feed headline is still preferred to the fallback

    func testAFeedHeadlineIsKept() throws {
        let q = try XCTUnwrap(DailyChallengeViewModel.question(
            from: try brewersCubs(headline: "Brewers chase the division")))
        XCTAssertEqual(q.headline, "Brewers chase the division")
        XCTAssertEqual(q.subject, "Milwaukee Brewers to win")
    }

    // MARK: - The filters, unchanged by this fix and pinned so they stay that way

    func testAPriceOutsideThePlayableBandIsNotAQuestion() throws {
        for probability in [0.04, 0.05, 0.95, 0.99] {
            let card = try item("""
            {"type": "event", "score": 70,
             "data": {"id": 15305001, "home_team": "A", "away_team": "B",
                       "current_odds": {"home_probability": \(probability)}}}
            """)
            XCTAssertNil(DailyChallengeViewModel.question(from: card),
                         "\(probability) is not a playable Higher/Lower question")
        }
    }

    func testACardWithNoPriceIsNotAQuestion() throws {
        let card = try item("""
        {"type": "event", "score": 70,
         "data": {"id": 15305001, "home_team": "A", "away_team": "B"}}
        """)
        XCTAssertNil(DailyChallengeViewModel.question(from: card))
    }

    func testACardThatIsNeitherAnEventNorFuturesIsNotAQuestion() throws {
        let card = try item("""
        {"type": "tournament", "score": 70,
         "data": {"key": "us-open", "name": "US Open"}}
        """)
        XCTAssertNil(DailyChallengeViewModel.question(from: card))
    }

    func testAFuturesCardWithNoOutcomesIsNotAQuestion() throws {
        let card = try item("""
        {"type": "futures", "score": 70,
         "data": {"id": 4242, "name": "World Series 2026 winner"}}
        """)
        XCTAssertNil(DailyChallengeViewModel.question(from: card))
    }

    // MARK: - #3864 item 2, a decided game is not a question

    /// A fixed instant, so nothing here branches on the clock (gotcha #44):
    /// offset FIRST, then use it. Every `resolution_date` below is written
    /// relative to this and never to "now".
    private let anchor = Date(timeIntervalSince1970: 1_757_000_000)  // 2026-09-04T15:33:20Z

    private func event(status: String?, probability: Double = 0.56) throws -> FeedItem {
        let statusField = status.map { "\"status\": \"\($0)\"," } ?? ""
        return try item("""
        {"type": "event", "score": 70,
         "data": {"id": 15305001, "home_team": "Milwaukee Brewers",
                   "away_team": "Chicago Cubs", \(statusField)
                   "current_odds": {"home_probability": \(probability)}}}
        """)
    }

    /// 🟢 THE SHIP, event half. The deck had no lifecycle test of any kind — its
    /// whole filter was a price band and an id — so a finished game was a
    /// perfectly valid Higher/Lower question with an answer that was already
    /// fixed.
    func testAFinishedGameIsNotAQuestion() throws {
        for status in ["completed", "closed"] {
            XCTAssertNil(DailyChallengeViewModel.question(from: try event(status: status), now: anchor),
                         "\(status) is a decided game and must never be asked")
        }
    }

    /// 🔴 BOTH DIRECTIONS. A guard that empties the deck is a worse bug than the
    /// one it fixes — #3864 names exactly that risk — so the states that MUST
    /// still be asked are pinned beside the ones that must not.
    func testAGameStillBeingPlayedOrNotYetStartedIsStillAQuestion() throws {
        for status in ["scheduled", "live", nil] {
            let q = DailyChallengeViewModel.question(from: try event(status: status), now: anchor)
            XCTAssertNotNil(q, "\(status ?? "nil") is undecided and must stay askable")
        }
    }

    /// `suspended` is deliberately NOT refused, and this is the test that says so
    /// on purpose rather than by omission. It is non-terminal (``EventState``): no
    /// result was ever reported, the match can return to `live`, and the answer is
    /// not fixed. Refusing it would be a hiding rule, not a settled rule.
    func testASuspendedGameIsStillAQuestion() throws {
        XCTAssertNotNil(
            DailyChallengeViewModel.question(from: try event(status: "suspended"), now: anchor))
    }

    private func settledFutures(_ field: String) throws -> FeedItem {
        try item("""
        {"type": "futures", "score": 70,
         "data": {"id": 4242, "name": "World Series 2026 winner", \(field)
                   "top_outcomes": [{"id": 9, "name": "Dodgers", "probability": 0.22}]}}
        """)
    }

    /// 🟢 THE SHIP, futures half — all four of `FeedLifecycle`'s authorities, not
    /// just the obvious one. The `resolution_date` arm is the one that actually
    /// fires in production: gotcha #33 means a settled Kalshi market keeps
    /// `status='open'` forever, so a status-only guard would catch almost nothing.
    func testASettledMarketIsNotAQuestionOnAnyOfItsFourAuthorities() throws {
        let past = ISO8601DateFormatter().string(from: anchor.addingTimeInterval(-3600))
        let cases = [
            "\"resolved\": true,",
            "\"winner\": \"Los Angeles Dodgers\",",
            "\"status\": \"settled\",",
            "\"resolution_date\": \"\(past)\",",
        ]
        for field in cases {
            XCTAssertNil(
                DailyChallengeViewModel.question(from: try settledFutures(field), now: anchor),
                "settled by \(field) and must never be asked")
        }
    }

    /// The other direction again, and the trap inside it: a resolution date in the
    /// FUTURE is the normal state of every open market, so it must stay askable.
    /// An `>=`/`<=` slip here would empty the deck of futures entirely.
    func testAnOpenMarketIsStillAQuestion() throws {
        let future = ISO8601DateFormatter().string(from: anchor.addingTimeInterval(86_400))
        for field in ["", "\"resolved\": false,", "\"status\": \"open\",",
                      "\"resolution_date\": \"\(future)\",", "\"winner\": \"\","] {
            XCTAssertNotNil(
                DailyChallengeViewModel.question(from: try settledFutures(field), now: anchor),
                "\(field.isEmpty ? "(no lifecycle fields)" : field) is an open market")
        }
    }

    /// `now` is injected, so the same fixture is settled or not purely by the
    /// clock it is read against — which is what makes the date arm testable at all
    /// and what stops a fixture drifting into a different verdict next week.
    func testTheResolutionDateArmIsReadAgainstTheInjectedClockAndNotTheWallClock() throws {
        let stamp = ISO8601DateFormatter().string(from: anchor)
        let card = try settledFutures("\"resolution_date\": \"\(stamp)\",")
        XCTAssertNotNil(DailyChallengeViewModel.question(from: card,
                                                         now: anchor.addingTimeInterval(-60)),
                        "one minute BEFORE resolution the market is still open")
        XCTAssertNil(DailyChallengeViewModel.question(from: card,
                                                      now: anchor.addingTimeInterval(60)),
                     "one minute AFTER resolution it is decided")
    }

    /// `category` is submitted to `/api/predictions` and read by the stats
    /// breakdown, so it is pinned: fixing copy must not quietly narrow an
    /// analytics field. Both branches keep the expression they had.
    func testTheAnalyticsCategoryIsUnchanged() throws {
        let event = try XCTUnwrap(DailyChallengeViewModel.question(from: try brewersCubs()))
        XCTAssertEqual(event.category, "baseball_mlb")

        let future = try XCTUnwrap(DailyChallengeViewModel.question(
            from: try futures(name: "M", outcome: "O", probability: 0.5)))
        XCTAssertEqual(future.category, "baseball")
    }
}
