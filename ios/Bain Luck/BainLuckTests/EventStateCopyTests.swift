import XCTest
@testable import Bain_Luck

/// native/052 — #3821: a completed game stops promising prediction markets that
/// can never arrive.
///
/// THE PHOTOGRAPH. Event 15305472 (Cardinals 10 — Rockies 8, status `completed`),
/// iPhone 17 simulator against production, 2026-09-07 —
/// `artifacts-native-051/mlb-15305472-s700.png`. Under a hero reading
/// `FINAL · Cardinals Win`, and under two charts that had correctly flipped to
/// `● Final`, the empty market state read:
///
///     📊  No prediction markets for this game yet.
///
/// "Yet" promises a listing that no venue will ever make. It is #3465's defect
/// one card lower on the same page — that fix tensed the score chart's
/// unit-mismatch note on `isFinished` and this sentence was missed — and it is
/// Alex's standing ruling that settled means settled.
///
/// `EventState` had ten call sites across view models, cards and views and no
/// test file at all before this one.
final class EventStateCopyTests: XCTestCase {

    // MARK: - #3821: the empty market state is tensed

    /// 🔴 THE DEFECT. Both statuses ``EventState/isFinished(_:)`` recognises —
    /// and `closed` is the one the photographed aged-out branch actually carries
    /// — must drop the promise.
    func testASettledGameDoesNotPromiseAMarketThatWillNeverCome() {
        for status in ["completed", "closed"] {
            let line = EventState.noGameMarketsLine(status: status)
            XCTAssertFalse(
                line.lowercased().contains("yet"),
                "\(status) still promises a market that can never arrive: \(line)"
            )
            XCTAssertEqual(line, "No prediction markets for this game.")
        }
    }

    /// 🔴 THE REGRESSION THAT WOULD BE WORSE THAN THE BUG. "Yet" is CORRECT for
    /// a game that has not finished — a venue really can still list it — so a
    /// fix that deletes the word everywhere replaces a false promise with a
    /// false absence on every upcoming game in the app, which is far the larger
    /// population. Pinned first in both directions.
    func testAnUnfinishedGameKeepsItsPromise() {
        for status in ["scheduled", "live", "suspended", nil, "", "some_status_we_have_never_seen"] {
            XCTAssertEqual(
                EventState.noGameMarketsLine(status: status),
                "No prediction markets for this game yet.",
                "status \(status ?? "nil") has not finished and may still be listed"
            )
        }
    }

    /// The tense is decided by ``EventState/isFinished(_:)`` and by nothing else.
    /// Written as a sweep rather than two literals so that a future status added
    /// to `isFinished` — the way `suspended` was added to this enum in live/048 —
    /// carries the copy with it instead of silently keeping "yet".
    func testTheTenseFollowsIsFinishedAndNotAHardCodedStatusList() {
        for status in [
            "scheduled", "live", "suspended", "completed", "closed",
            "postponed", "cancelled", nil
        ] {
            let saysYet = EventState.noGameMarketsLine(status: status).contains("yet")
            XCTAssertEqual(
                saysYet, !EventState.isFinished(status),
                "the sentence disagrees with isFinished about status \(status ?? "nil")"
            )
        }
    }

    /// 🔴 THE SETTLED LINE MUST NOT SAY WHY. This empty state covers two
    /// populations the view cannot tell apart: a game no venue ever listed, and
    /// an aged-out closed game whose markets we HELD and no longer do (#1092,
    /// the comment on the branch itself). Any wording that names a cause —
    /// "no venue covered this game", "never listed", "expired" — is false for
    /// one of the two halves. Asserted so the next person to make this sentence
    /// friendlier has to read the reason first.
    func testTheSettledLineClaimsNoCauseItCannotKnow() {
        let line = EventState.noGameMarketsLine(status: "closed").lowercased()
        for invented in ["cover", "never", "expire", "listed", "aged", "no longer"] {
            XCTAssertFalse(
                line.contains(invented),
                "the settled line claims a cause it cannot distinguish: \(invented)"
            )
        }
    }

    // MARK: - The rest of EventState, which had no test file before #3821

    /// The vocabulary the copy above is tensed on. `suspended` is NOT finished —
    /// it is non-terminal and can go back to `live` — so a suspended match keeps
    /// "yet", which `testAnUnfinishedGameKeepsItsPromise` relies on.
    func testIsFinishedRecognisesExactlyTheTwoSettledStatuses() {
        XCTAssertTrue(EventState.isFinished("completed"))
        XCTAssertTrue(EventState.isFinished("closed"))
        XCTAssertFalse(EventState.isFinished("live"))
        XCTAssertFalse(EventState.isFinished("suspended"))
        XCTAssertFalse(EventState.isFinished("scheduled"))
        XCTAssertFalse(EventState.isFinished(nil))
    }

    /// The bug this enum was created for: an unrecognised status used to match
    /// none of the three grid filters, so a suspended match vanished from
    /// Discover, Sports and My Stuff without leaving a gap anyone could see.
    /// Every status must land in exactly one section, including one nobody has
    /// shipped yet.
    func testEveryStatusLandsInASectionIncludingOneWeHaveNeverSeen() {
        XCTAssertEqual(EventState.section("live"), .live)
        XCTAssertEqual(EventState.section("suspended"), .live)
        XCTAssertEqual(EventState.section("completed"), .finished)
        XCTAssertEqual(EventState.section("closed"), .finished)
        XCTAssertEqual(EventState.section("scheduled"), .upcoming)
        XCTAssertEqual(EventState.section(nil), .upcoming)
        XCTAssertEqual(EventState.section("a_status_from_the_future"), .upcoming)
    }
}
