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
        // #5697 AC2 — still one question ABOUT GRADABILITY, and that is what
        // this test was always making. The hero now asks a second question the
        // cards do not: is there a score on screen to frame a forecast against.
        // Held at `hasScore: true` so the shared claim stays testable on its own
        // axis; the divergence is asserted deliberately in the test below rather
        // than left to weaken this one.
        for (status, now) in [("suspended", afterStart), ("suspended", beforeStart),
                              ("live", afterStart), ("completed", afterStart),
                              ("scheduled", beforeStart)] {
            XCTAssertEqual(
                EventDetailView.showsProjection(
                    status: status, commenceTime: started, hasScore: true, now: now),
                EventState.canStillBeGraded(status, commenceTime: started, now: now),
                "hero and cards disagree about \(status)"
            )
        }
    }

    /// #5697 AC2 — the ONE place the hero is deliberately stricter than the
    /// cards, pinned so nobody "restores" the identity above by deleting it.
    ///
    /// A market card one scroll below carries its own label and its own context;
    /// the hero's projection sits in the score's slot with nothing beside it. On
    /// an underway game with no score the hero withholds and the cards do not.
    func testOnlyTheHeroWithholdsAProjectionOverAnAbsentScore() {
        XCTAssertTrue(
            EventState.canStillBeGraded("live", commenceTime: started, now: afterStart),
            "the cards' question is unchanged — a live game can still be graded")
        XCTAssertFalse(
            EventDetailView.showsProjection(
                status: "live", commenceTime: started, hasScore: false, now: afterStart),
            "the hero must withhold a projected final over a game with no score")
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
    /// about ungradeable games — call 2 ("Projected margin" / "Projected total
    /// runs") of `alex-inbox/an-abandoned-games-cards-two-wording-calls.md`,
    /// still unanswered; call 1 became D120 = C above — this test is the one that
    /// will fail, and its failure is the signal that the gate in `ladderRow` can
    /// come out.
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

    // MARK: - The third card: the caption, not the number (#4018 / D120 = C)

    /// The ship. On the photographed specimen the props card read
    /// `STRIKEOUTS · chance of hitting · 5+ ▓▓▓░░ 62%` — present tense over a game
    /// that stopped. The 62% is a real quote and stays; three words change.
    func testAnAbandonedGamesPropsCaptionIsPastTense() {
        XCTAssertEqual(
            EventState.propsChanceCaption("suspended", commenceTime: started, now: afterStart),
            "last quoted chance"
        )
    }

    /// 🔴 THE #4021 CLAUSE, AND THE REASON THE VIEW HAD TO GAIN A `commenceTime`.
    /// Reading the bare status would caption event 416569 — suspended four days
    /// BEFORE kick-off — "last quoted chance" about a game nobody has played. This
    /// is the assertion that fails if someone simplifies the helper to
    /// `isSuspended(status)`.
    func testAFixtureSuspendedBeforeItIsPlayedKeepsThePresentTenseCaption() {
        XCTAssertEqual(
            EventState.propsChanceCaption("suspended", commenceTime: started, now: beforeStart),
            "chance of hitting",
            "a fixture still to be played is still a chance of hitting"
        )
    }

    /// THE CONTROL. D120 ruled on ABANDONED games. A finished game's props card
    /// draws the actual value and a ✓/– beside every rung, so its caption reads as
    /// the historical quote it is — and Alex has not been asked about it. This
    /// fails if the predicate is widened to `!canStillBeGraded`, which is the
    /// tempting one-line generalisation.
    func testEveryOtherStateKeepsTheCaptionItHadBeforeD120() {
        for (status, now) in [("completed", afterStart), ("closed", afterStart),
                              ("live", afterStart), ("scheduled", beforeStart)] {
            XCTAssertEqual(
                EventState.propsChanceCaption(status, commenceTime: started, now: now),
                "chance of hitting",
                "D120 did not rule on \(status)"
            )
        }
        XCTAssertEqual(
            EventState.propsChanceCaption(nil, commenceTime: nil, now: afterStart),
            "chance of hitting",
            "a status-less row is not an abandoned one"
        )
    }

    /// A dateless suspended row inherits `hasStarted`'s TRUE default, same as the
    /// projection gate above. Pinned so the two cards cannot drift apart on it.
    func testADatelessSuspendedRowGetsThePastTenseCaptionToo() {
        XCTAssertEqual(
            EventState.propsChanceCaption("suspended", commenceTime: nil, now: afterStart),
            "last quoted chance"
        )
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
