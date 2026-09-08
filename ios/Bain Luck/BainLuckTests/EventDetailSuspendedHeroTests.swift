import XCTest
@testable import Bain_Luck

/// #4002 / #3014 — what the event hero draws for a game that started and was
/// never given a result.
///
/// `EventDetailView` carried a PRIVATE COPY of the settled vocabulary
/// (`status == "completed" || status == "closed"`) instead of `EventState`, so
/// `suspended` — added to the vocabulary by live/048 and taught to
/// `EventCardView` under CERT-786 — matched none of the page's arms and fell
/// through every one of them to the pregame default. Four separate renders
/// were wrong at once on the same hero, which is why this file tests four
/// helpers rather than one:
///
/// | render | pre-fix gate | what `15298408` showed |
/// |---|---|---|
/// | status badge | `switch` with no suspended arm, defaulting to a `"scheduled"` countdown that returns nil for a past date | nothing at all |
/// | score | `(isLive \|\| isFinished) && …` | nothing, while the navigation title above it read "Yankees 3 - Padres 4" |
/// | broadcast | ungated | "MLB.TV, Padres.TV, YES", two days after the game |
/// | projection | `!isFinished` | grey `Proj. 3-2` in the score's slot |
///
/// Measured on production over the 7 days to 2026-09-08: **184 suspended games
/// carrying a projection** and 1 live one. The population is real and it is
/// mostly `baseball_milb` / `baseball_npb` / `baseball_kbo`.
///
/// The helpers are `static` and take the status rather than reading `vm` for
/// one reason: a SwiftUI view BODY is invisible to XCTest, so a gate left
/// inside the body is a gate no Swift test can reach. That every gate is
/// actually WIRED to these helpers is asserted by
/// `frontend/__tests__/ios/eventStatusSingleSource.test.ts`, which reads the
/// Swift as text and runs in CI — CI compiles no Swift at all.
final class EventDetailSuspendedHeroTests: XCTestCase {

    /// Every status the API can put on an event. Written as one list so that a
    /// new state cannot be added to `EventState` and quietly miss this page the
    /// way `suspended` did.
    private static let vocabulary: [String?] = [
        "scheduled", "live", "suspended", "completed", "closed",
        "postponed", "cancelled", nil,
    ]

    // MARK: - The score

    /// THE MARQUEE SPECIMEN. `15298408` — Yankees @ Padres, played 2026-09-06,
    /// final 3–4, left at `status='suspended'`. It had both scores and drew
    /// neither, so the page contradicted its own navigation title on one screen.
    func testASuspendedGameWithAScoreDrawsIt() {
        XCTAssertTrue(EventDetailView.showsScore(status: "suspended", away: 3, home: 4))
    }

    func testASuspendedGameWithNoScoreDrawsNothingRatherThanZeroZero() {
        // 15301312 (NPB) — `home_score` and `away_score` are both null. The
        // score Text renders `event.awayScore ?? 0`, so a true here would print
        // a confident 0-0 for a game nobody scored.
        XCTAssertFalse(EventDetailView.showsScore(status: "suspended", away: nil, home: nil))
    }

    func testAHalfScoreIsNotAScore() {
        // Same partial-line trap `EventState.suspendedSummary` refuses: one side
        // known and the other nil renders as "3 - 0" once the `?? 0` lands.
        XCTAssertFalse(EventDetailView.showsScore(status: "suspended", away: 3, home: nil))
        XCTAssertFalse(EventDetailView.showsScore(status: "live", away: nil, home: 4))
    }

    func testTheStatesThatShowAScoreAreExactlyTheOnesThatStarted() {
        let expected: [String?: Bool] = [
            "scheduled": false, "live": true, "suspended": true,
            "completed": true, "closed": true,
            "postponed": false, "cancelled": false,
        ]
        for status in Self.vocabulary {
            XCTAssertEqual(
                EventDetailView.showsScore(status: status, away: 3, home: 4),
                expected[status] ?? false,
                "showsScore disagrees for \(status ?? "nil")"
            )
        }
    }

    // MARK: - The broadcast

    /// A broadcast listing is a promise about the future. `15298408` offered
    /// three channels for a game that had already been abandoned.
    func testAFinishedOrSuspendedGameOffersNoChannels() {
        XCTAssertFalse(EventDetailView.showsBroadcast(status: "suspended"))
        XCTAssertFalse(EventDetailView.showsBroadcast(status: "completed"))
        XCTAssertFalse(EventDetailView.showsBroadcast(status: "closed"))
    }

    func testAGameYouCanStillWatchKeepsItsChannels() {
        // The inverse hazard: a gate that hides the broadcast on a live game
        // removes the single most useful thing on a pregame hero.
        XCTAssertTrue(EventDetailView.showsBroadcast(status: "live"))
        XCTAssertTrue(EventDetailView.showsBroadcast(status: "scheduled"))
        XCTAssertTrue(EventDetailView.showsBroadcast(status: nil))
    }

    // MARK: - The projection

    /// The 184. A projected FINAL score for a match that will never be given
    /// one, printed in the score's slot, on a hero that had no state label.
    func testASuspendedGameDrawsNoProjectedFinal() {
        XCTAssertFalse(EventDetailView.showsProjection(status: "suspended"))
    }

    func testTheProjectionSurvivesWhereItIsStillAProjection() {
        XCTAssertTrue(EventDetailView.showsProjection(status: "live"))
        XCTAssertTrue(EventDetailView.showsProjection(status: "scheduled"))
    }

    func testTheProjectionGateAgreesWithIsFinishedEverywhereElse() {
        // The pre-fix gate was `!isFinished` and nothing else. The fix must
        // differ from it on exactly ONE status — a wider change here would be
        // silently removing the projection from states nobody complained about.
        for status in Self.vocabulary where !EventState.isSuspended(status) {
            XCTAssertEqual(
                EventDetailView.showsProjection(status: status),
                !EventState.isFinished(status),
                "the projection gate moved on \(status ?? "nil"), which #4002 did not ask for"
            )
        }
    }

    // MARK: - The label (#3014)

    /// #3014's specimen: a LIVE game with no score at all, where "Proj. 2-3" is
    /// the only pair of numbers on the hero and reads as the score.
    func testALiveGameWithNoScoreSpellsTheWordOut() {
        XCTAssertEqual(
            EventDetailView.projectionLabel(status: "live", hasScore: false),
            "Projected final"
        )
    }

    func testTheAbbreviationStaysWhereARealScoreIsStandingBesideIt() {
        // With a score on screen the pair cannot be misread, and the centre
        // column is `fixedSize` — a longer label there squeezes the crests.
        XCTAssertEqual(EventDetailView.projectionLabel(status: "live", hasScore: true), "Proj.")
        XCTAssertEqual(EventDetailView.projectionLabel(status: "scheduled", hasScore: false), "Proj.")
    }

    func testTheLabelNeverClaimsAFinalForAGameThatIsNotBeingPlayed() {
        // Before kick-off there is no score slot to be confused with, and after
        // the whistle the projection does not draw at all.
        for status in Self.vocabulary where status != "live" {
            XCTAssertEqual(
                EventDetailView.projectionLabel(status: status, hasScore: false),
                "Proj.",
                "spelled the label out on \(status ?? "nil")"
            )
        }
    }

    // MARK: - The vocabulary itself

    /// The root cause, asserted directly: this page must not be able to hold an
    /// opinion about `suspended` that differs from the cards'.
    func testThePageReadsTheSharedVocabularyAndNotACopyOfIt() {
        for status in Self.vocabulary {
            // Anything the shared enum calls finished must be finished here, in
            // all four renders, without this file naming the strings.
            if EventState.isFinished(status) {
                XCTAssertFalse(EventDetailView.showsProjection(status: status))
                XCTAssertFalse(EventDetailView.showsBroadcast(status: status))
            }
            if EventState.isSuspended(status) {
                XCTAssertFalse(EventDetailView.showsProjection(status: status))
                XCTAssertFalse(EventDetailView.showsBroadcast(status: status))
                XCTAssertTrue(EventDetailView.showsScore(status: status, away: 3, home: 4))
            }
        }
    }
}
