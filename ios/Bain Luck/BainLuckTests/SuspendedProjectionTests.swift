import XCTest
@testable import Bain_Luck

/// #4018 — A PROJECTION FOR A GAME NOBODY WILL EVER GRADE.
///
/// `bainluck://events/15301312` — Chunichi Dragons v Tokyo Yakult Swallows, an NPB
/// game that started 2026-09-04 and for which no result was ever reported
/// (`status='suspended'`). Photographed 2026-09-08 10:47 PT,
/// `artifacts-native-070/C-4002-suspended-noscore-15301312.png`. One scroll below
/// the hero the Runs map read:
///
///     Runs map
///     Projected total runs
///     PROJECTION  4.8
///
/// A projected total for a match abandoned four days earlier.
///
/// THE MECHANISM WAS A QUESTION ASKED WRONG. Every one of these gates gated on
/// `EventState.isFinished` — "is the game over?" — when the question a forecast has
/// to answer is "can a final still arrive?". `suspended` is the whole gap between
/// them: not finished, and never going to be. #4002 drew the distinction for the
/// HERO and PR #4016 photographed it; it stayed a private property on
/// `EventDetailView` while three market cards below kept their own copy.
///
/// Measured on production over the 7 days to 2026-09-08: **184 suspended games
/// carrying a projection** against 1 live one, mostly `baseball_milb` /
/// `baseball_npb` / `baseball_kbo`.
final class SuspendedProjectionTests: XCTestCase {

    private let started = Date(timeIntervalSince1970: 1_757_000_000)
    private var afterStart: Date { started.addingTimeInterval(4 * 24 * 3600) }
    private var beforeStart: Date { started.addingTimeInterval(-4 * 24 * 3600) }

    // MARK: - The predicate

    func testAnAbandonedGameCanNoLongerBeGraded() {
        XCTAssertFalse(
            EventState.canStillBeGraded("suspended", commenceTime: started, now: afterStart),
            "the photographed specimen: started, never finished, still offered a forecast"
        )
    }

    func testTheStatesThatCanStillBeGradedAreUntouched() {
        for status in ["scheduled", "live", nil] {
            XCTAssertTrue(
                EventState.canStillBeGraded(status, commenceTime: started, now: afterStart),
                "a forecast is still a forecast for \(status ?? "nil")"
            )
        }
    }

    func testAFinishedGameCannotBeGradedAgain() {
        for status in ["completed", "closed"] {
            XCTAssertFalse(
                EventState.canStillBeGraded(status, commenceTime: started, now: afterStart),
                "for \(status)"
            )
        }
    }

    /// 🔴 #4021 — `suspended` IS A STATUS, NOT A PHASE. Event 416569 sat at
    /// `status='suspended'` four days BEFORE kick-off. That fixture will be played,
    /// so its projection is a real projection and must survive. This is the clause
    /// that makes the clock load-bearing rather than decorative, and it is why the
    /// predicate takes a `commenceTime` at all.
    func testAFixtureSuspendedBeforeItHasBeenPlayedKeepsItsProjection() {
        XCTAssertTrue(
            EventState.canStillBeGraded("suspended", commenceTime: started, now: beforeStart),
            "a game that has not started yet can still produce a final"
        )
    }

    /// A dateless suspended row is treated as started — `EventState.hasStarted`
    /// documents why, and this pins that #4018 inherits that default rather than
    /// quietly choosing the other one.
    func testADatelessSuspendedRowIsTreatedAsAbandoned() {
        XCTAssertFalse(EventState.canStillBeGraded("suspended", commenceTime: nil, now: afterStart))
    }

    // MARK: - The gate the map actually reads

    func testTheMapDrawsNoProjectionMarkerForAnAbandonedGame() {
        let canGrade = EventState.canStillBeGraded("suspended", commenceTime: started, now: afterStart)
        XCTAssertFalse(MarketMapRail.drawsPregameMarker(canStillBeGraded: canGrade),
                       "PROJECTION 4.8 is the tile this removes")
    }

    func testTheMapStillDrawsItBeforeTheOff() {
        let canGrade = EventState.canStillBeGraded("scheduled", commenceTime: started, now: beforeStart)
        XCTAssertTrue(MarketMapRail.drawsPregameMarker(canStillBeGraded: canGrade),
                      "the fix must not empty a pre-game card")
    }

    // MARK: - The hero and the cards now agree

    /// The single-source claim, stated as a test rather than as a comment. #4002's
    /// hero rule and the market cards' rule are the same function now; before
    /// #4018 they were two, and they disagreed on exactly this status.
    func testTheHeroAndTheCardsAskOneQuestion() {
        for (status, now) in [("suspended", afterStart), ("suspended", beforeStart),
                              ("live", afterStart), ("completed", afterStart),
                              ("scheduled", beforeStart)] {
            XCTAssertEqual(
                EventDetailView.showsProjection(status: status, commenceTime: started, now: now),
                EventState.canStillBeGraded(status, commenceTime: started, now: now),
                "hero and cards disagree about \(status)"
            )
        }
    }

    // MARK: - Why the ladder needs a local gate as well

    /// THE COUPLING, PINNED SO THE NEXT READER CAN DELETE THE GATE SAFELY.
    ///
    /// Steering an abandoned game to `fullView` lands it on the threshold ladder,
    /// and the ladder captions each rung from `SpectrumTense`, which asks
    /// `isSettled: isDone` — the very "is it over?" question #4018 exists to
    /// replace. A suspended game therefore comes out `.projected` and the shared
    /// helper hands back **`PRE-GAME`**, four times, where the old layout said
    /// `PRE-GAME LINE` once. That is why `ladderRow` gates the caption locally.
    ///
    /// This asserts the helper's answer rather than the card's, so it states the
    /// REASON the local gate exists. If someone later teaches `SpectrumTense`
    /// about ungradeable games — the copy question routed to Alex in
    /// `native-090b-2146PT-…` — this test is the one that will fail, and its
    /// failure is the signal that the gate in `ladderRow` can come out.
    func testTheSharedRungCaptionStillSaysPreGameForAnAbandonedGame() {
        // `finalTotal` is nil for a suspended game: `actualTotal` requires
        // `isDone`, so no final total is ever computed for one.
        XCTAssertEqual(
            MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: false),
            "PRE-GAME",
            "the shared vocabulary has no ungradeable state, so the card suppresses this itself"
        )
        // The two arms the local gate deliberately leaves alone.
        XCTAssertNil(MarketMapRail.spectrumRungCaption(finalTotal: 7, isSettled: true),
                     "a graded rung already draws no caption")
        XCTAssertNotNil(MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: true),
                        "a finished-but-ungradable rung keeps its settled caption")
    }

    /// THE CONTROL THAT KEEPS THIS FROM BECOMING A SETTLED CLAIM. Flipping the
    /// cards' `isDone` would have been the one-line change and it is wrong: those
    /// branches publish `homeScore + awayScore` under the label **FINAL**, so an
    /// abandoned game with a partial score would have that partial announced as
    /// the result. `EventState.suspendedSummary` calls the very same number a
    /// "last score". A forecast and a result are two questions.
    func testAnAbandonedGameIsStillNotFinished() {
        XCTAssertFalse(EventState.isFinished("suspended"),
                       "#4018 must not turn a suspended game into a settled one")
        XCTAssertEqual(EventState.suspendedSummary(away: 3, home: 4),
                       "No result reported · last score 3-4")
    }
}
