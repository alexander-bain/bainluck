import XCTest
@testable import Bain_Luck

/// UX-P115 (#2086) — the settled predicate native's Additional Markets section
/// now keys off, and the words it says when it fires.
///
/// The behaviour these back is a REPLACEMENT, not an addition, so the tests are
/// written against what the old code got wrong. `SpecialEventMarketsView` used
/// to react to a finished game by DELETING rows whose price fell outside
/// `(0.01, 0.99)`, under a comment claiming it hid "100%/0%". Measured over 40
/// settled events on 2026-08-21, that filter passed **117 of 146 `other` rows**
/// straight through to a live-looking bar — 53 of them in the 0.40–0.60
/// coin-flip band — while silently deleting the four rows that had no price at
/// all. It removed what a reader would question and kept what a reader would
/// believe.
///
/// The string parity with `frontend/lib/settledQuote.ts` is asserted from the
/// jest side (`__tests__/lib/settledQuoteParity.test.ts`), which can read both
/// files; this suite covers the part that only runs here.
final class SettledQuoteTests: XCTestCase {

    func testSettledStatusesAreRecognised() {
        for status in ["completed", "closed", "settled", "final", "resolved"] {
            XCTAssertTrue(SettledQuote.isSettled(status), "\(status) must read as settled")
        }
    }

    func testInPlayAndUnknownStatusesAreNotSettled() {
        // The safe direction: anything this list does not recognise keeps its
        // bars. Over-suppression on a live game is the failure the old native
        // code shipped, so it must not be reachable through an unknown status.
        for status in ["scheduled", "live", "in_progress", "halftime", "voided", "", "postponed"] {
            XCTAssertFalse(SettledQuote.isSettled(status), "\(status) must NOT read as settled")
        }
    }

    func testNilStatusIsNotSettled() {
        XCTAssertFalse(SettledQuote.isSettled(nil))
    }

    func testMatchingIsCaseInsensitive() {
        // Web's `isSettledStatus` lowercases before comparing; a provider that
        // starts shouting must not split the two runtimes.
        XCTAssertTrue(SettledQuote.isSettled("CLOSED"))
        XCTAssertTrue(SettledQuote.isSettled("Completed"))
        XCTAssertFalse(SettledQuote.isSettled("LIVE"))
    }

    func testTheWordsAreStatedAndAreNotVerdicts() {
        XCTAssertEqual(SettledQuote.prefix, "last quote")
        XCTAssertEqual(SettledQuote.sectionNote, "settled — showing each market's last quote")

        // This surface states NO verdict, because the grade for these rows is
        // not on the payload — it exists, authoritatively (`api_settlement`),
        // and the game-markets endpoint simply does not serialize it. Claiming
        // "grading unavailable" would be a false statement, and claiming a
        // winner would be a fabricated one.
        for verdict in ["HIT", "MISS", "PUSH", "WON", "LOST", "grading unavailable"] {
            XCTAssertFalse(
                SettledQuote.prefix.contains(verdict) || SettledQuote.sectionNote.contains(verdict),
                "the settled-quote words must not carry the verdict \(verdict)"
            )
        }
    }
}
