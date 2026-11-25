import XCTest
@testable import Bain_Luck

/// #12304 — every rule of the rating prompt, on a fixed clock and calendar.
@MainActor
final class ReviewPromptPolicy12304Tests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_790_000_000)
    private var calendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        return c
    }
    private let policy = ReviewPromptPolicy12304()

    private func days(_ n: Int) -> Date { calendar.date(byAdding: .day, value: n, to: now)! }

    /// A reader every rule lets through: installed a month ago, ten sessions, a
    /// good moment, never asked, nothing went wrong.
    private func ready() -> ReviewPromptState12304 {
        ReviewPromptState12304(installDate: days(-30), sessionCount: 10, lastAsked: nil,
                               lastAskedVersion: nil, currentVersion: "1.0.7",
                               goodMomentsSinceAsk: 1, sessionHadTrouble: false)
    }

    private func asks(_ state: ReviewPromptState12304) -> Bool {
        policy.shouldAsk(state, now: now, calendar: calendar)
    }

    func testTheReadyReaderIsAsked() {
        XCTAssertTrue(asks(ready()))
    }

    func testNeverInTheFirstThreeDays() {
        var s = ready()
        s.installDate = days(-2)
        XCTAssertFalse(asks(s))
        s.installDate = days(-3)
        XCTAssertTrue(asks(s), "Day three after install is the first day it may ask")
        s.installDate = nil
        XCTAssertFalse(asks(s), "An unknown install date never asks")
    }

    func testNeverBeforeTheFifthSession() {
        var s = ready()
        s.sessionCount = 4
        XCTAssertFalse(asks(s))
        s.sessionCount = 5
        XCTAssertTrue(asks(s))
    }

    func testNeverTwiceIn120Days() {
        var s = ready()
        s.lastAskedVersion = "1.0.6"
        s.lastAsked = days(-119)
        XCTAssertFalse(asks(s))
        s.lastAsked = days(-120)
        XCTAssertTrue(asks(s))
        s.lastAsked = days(3)
        XCTAssertFalse(asks(s), "An ask dated in the future (a clock change) waits")
    }

    func testNeverTwiceForTheSameVersion() {
        var s = ready()
        s.lastAsked = days(-400)
        s.lastAskedVersion = "1.0.7"
        XCTAssertFalse(asks(s))
        s.lastAskedVersion = "1.0.6"
        XCTAssertTrue(asks(s))
    }

    func testOnlyAfterAGoodMoment() {
        var s = ready()
        s.goodMomentsSinceAsk = 0
        XCTAssertFalse(asks(s))
    }

    func testNeverInARunThatShowedTrouble() {
        var s = ready()
        s.sessionHadTrouble = true
        XCTAssertFalse(asks(s))
    }

    // MARK: - Signals

    private func signals() -> (ReviewPromptSignals12304, UserDefaults) {
        let name = "review-prompt-12304-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        addTeardownBlock { defaults.removePersistentDomain(forName: name) }
        return (ReviewPromptSignals12304(defaults: defaults), defaults)
    }

    func testTheThirdDayOfUseAndEveryLaterDayIsAGoodMoment() {
        let (s, _) = signals()
        s.recordActiveDay(now: days(0), calendar: calendar)
        s.recordActiveDay(now: days(0).addingTimeInterval(3600), calendar: calendar)
        s.recordActiveDay(now: days(1), calendar: calendar)
        XCTAssertEqual(s.state(currentVersion: nil).goodMomentsSinceAsk, 0, "Two days of use is not yet a habit")
        s.recordActiveDay(now: days(5), calendar: calendar)
        XCTAssertEqual(s.state(currentVersion: nil).goodMomentsSinceAsk, 1)
        s.recordActiveDay(now: days(5).addingTimeInterval(60), calendar: calendar)
        XCTAssertEqual(s.state(currentVersion: nil).goodMomentsSinceAsk, 1, "Once per day, however often it opens")
        s.recordActiveDay(now: days(6), calendar: calendar)
        XCTAssertEqual(s.state(currentVersion: nil).goodMomentsSinceAsk, 2)
    }

    func testAskingSpendsTheGoodMomentsAndRemembersTheVersion() {
        let (s, defaults) = signals()
        defaults.set(days(-30), forKey: ReviewPromptSignals12304.Key.installDate)
        defaults.set(10, forKey: ReviewPromptSignals12304.Key.sessionCount)
        s.recordGoodMoment()
        XCTAssertTrue(policy.shouldAsk(s.state(currentVersion: "1.0.7"), now: now, calendar: calendar))
        s.markAsked(now: now, version: "1.0.7")
        XCTAssertTrue(s.askedThisRun)
        let after = s.state(currentVersion: "1.0.7")
        XCTAssertEqual(after.goodMomentsSinceAsk, 0)
        XCTAssertEqual(after.lastAskedVersion, "1.0.7")
        XCTAssertEqual(after.lastAsked, now)
        XCTAssertFalse(policy.shouldAsk(after, now: now, calendar: calendar))
    }

    func testTroubleBlocksTheRestOfTheRun() {
        let (s, defaults) = signals()
        defaults.set(days(-30), forKey: ReviewPromptSignals12304.Key.installDate)
        defaults.set(10, forKey: ReviewPromptSignals12304.Key.sessionCount)
        s.recordGoodMoment()
        s.noteTrouble()
        XCTAssertFalse(policy.shouldAsk(s.state(currentVersion: "1.0.7"), now: now, calendar: calendar))
    }
}
