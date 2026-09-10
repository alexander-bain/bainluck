import XCTest
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

/// #4044 — A GAME FOUR DAYS AWAY IS SHARED AS "PAUSED".
///
/// `ShareCardRenderer` was the last iOS surface rendering the suspended treatment
/// without asking the clock. It was left out of #4021 deliberately, because
/// `ShareableEventCardView` had no `commenceTime` to ask with, and it was pinned
/// as an explicit carve-out in `frontend/__tests__/ios/eventStatusSingleSource.test.ts`
/// so the debt could not be quietly forgotten. Paying it required editing that
/// list, which is what this ship does.
///
/// THE SPECIMEN is #4021's: event 416569, Ohio State @ Texas, `status='suspended'`
/// four days before kick-off. Shared, its eyebrow read **PAUSED** over a game
/// nobody had started.
///
/// This file exists because the eyebrow was a `private var` on a `View` and so
/// could not be tested at all — `@testable import` does not reach `private`. It is
/// now a static function taking the three values that decide it plus an injected
/// `now`, so these assertions run the production path at a fixed instant rather
/// than a paraphrase of it at CI's wall clock (gotcha #44).
final class ShareCardEyebrowTests: XCTestCase {

    /// A fixed instant, and both fixtures offset FROM it — never `Date()` with a
    /// branch, which is the anchor shape that passes on eleven clocks and fails
    /// on the twelfth.
    private let now = Date(timeIntervalSince1970: 1_757_500_000)
    private var fourDaysOut: Date { now.addingTimeInterval(4 * 24 * 3600) }
    private var anHourAgo: Date { now.addingTimeInterval(-3600) }

    // MARK: - The photographed defect

    func testAFixtureFourDaysOutIsNotLabelledStopped() {
        let eyebrow = ShareableEventCardView.eyebrow(
            status: "suspended", sportName: "NCAAF", commenceTime: fourDaysOut, now: now)
        XCTAssertEqual(eyebrow, "NCAAF")
        XCTAssertNotEqual(eyebrow, "PAUSED")
    }

    /// The other direction, which a clock gate can break just as easily: a match
    /// that really did stop must still say so.
    func testAMatchThatStartedAndStoppedStillSaysNoResult() {
        let eyebrow = ShareableEventCardView.eyebrow(
            status: "suspended", sportName: "MLB", commenceTime: anHourAgo, now: now)
        XCTAssertEqual(eyebrow, "NO RESULT REPORTED")
        XCTAssertNotEqual(eyebrow, "MLB")
    }

    // MARK: - The private word

    /// #4002's root cause in miniature: a surface holding its own copy of the
    /// status vocabulary. The eyebrow must be DERIVED from `EventState`, so that
    /// changing the word in one place changes it everywhere.
    func testTheSuspendedWordComesFromTheSharedVocabulary() {
        let eyebrow = ShareableEventCardView.eyebrow(
            status: "suspended", sportName: "MLB", commenceTime: anHourAgo, now: now)
        XCTAssertEqual(eyebrow, EventState.suspendedLabel.uppercased())
    }

    // MARK: - The arms that must not move

    func testLiveAndFinalAndTheDefaultAreUnchanged() {
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "live", sportName: "NBA", commenceTime: anHourAgo, now: now),
            "LIVE")
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "completed", sportName: "NBA", commenceTime: anHourAgo, now: now),
            "FINAL")
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "scheduled", sportName: "Premier League", commenceTime: fourDaysOut, now: now),
            "PREMIER LEAGUE")
    }

    /// A live match takes the live arm even though its clock says it started —
    /// the order of the branches is part of the behaviour.
    func testLiveOutranksTheClockGate() {
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "live", sportName: "MLB", commenceTime: anHourAgo, now: now),
            "LIVE")
    }

    /// A null `commenceTime` is a real served value, and it takes the SUSPENDED
    /// arm — `hasStarted(commenceTime: nil)` returns true.
    ///
    /// I wrote this assertion the other way round first, reasoning that a card
    /// which cannot date a match should not claim it stopped, and the shipped rule
    /// disagreed. It is right and the assumption was wrong: `EventState.hasStarted`
    /// documents nil→true as a deliberate default, because `suspended` is produced
    /// by something that watched a match begin and never saw it end, so a row with
    /// that status and no date is far likelier to be a started game whose schedule
    /// we lost than a fixture nobody has played. Defaulting the other way would
    /// also put #4002's hero back to a blank badge on every dateless suspended row.
    ///
    /// Pinned in that direction here so the share card cannot drift away from the
    /// helper's choice without this test saying so.
    func testAnUndatedSuspendedRowFollowsTheSharedNilPolicy() {
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "suspended", sportName: "Serie A", commenceTime: nil, now: now),
            EventState.suspendedLabel.uppercased())
        XCTAssertTrue(EventState.hasStarted(commenceTime: nil, now: now),
                      "the policy this card inherits")
    }

    // MARK: - It has to fit

    /// The band is 375pt wide with 22pt of horizontal padding, drawn at 11pt heavy
    /// with 1.0 tracking. The longer string is the whole cost of the decision, so
    /// pin that it is a cost we actually measured rather than assumed.
    func testTheLongestEyebrowFitsTheBand() {
        #if canImport(UIKit)
        let label = EventState.suspendedLabel.uppercased()
        let font = UIFont.systemFont(ofSize: 11, weight: .heavy)
        let width = (label as NSString).size(withAttributes: [.font: font]).width
            + Double(label.count) * 1.0   // tracking
        XCTAssertLessThan(width, 375 - 44, "eyebrow \"\(label)\" is \(width)pt in a 331pt band")
        #endif
    }
}
