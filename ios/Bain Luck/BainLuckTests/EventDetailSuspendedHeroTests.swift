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

    /// Fixed anchors, offset from a literal instant. Gotcha #44 — the anchor is
    /// computed by OFFSET, never by a branch on the real clock, so these do not
    /// straddle a date boundary or behave differently at 23:59.
    private static let now = Date(timeIntervalSince1970: 1_788_000_000)  // 2026-09-08ish
    private static let started = now.addingTimeInterval(-4 * 24 * 3600)
    private static let notYet = now.addingTimeInterval(4 * 24 * 3600)

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
        XCTAssertFalse(EventDetailView.showsBroadcast(status: "suspended", commenceTime: Self.started, now: Self.now))
        XCTAssertFalse(EventDetailView.showsBroadcast(status: "completed", commenceTime: Self.started, now: Self.now))
        XCTAssertFalse(EventDetailView.showsBroadcast(status: "closed", commenceTime: Self.started, now: Self.now))
    }

    func testAGameYouCanStillWatchKeepsItsChannels() {
        // The inverse hazard: a gate that hides the broadcast on a live game
        // removes the single most useful thing on a pregame hero.
        XCTAssertTrue(EventDetailView.showsBroadcast(status: "live", commenceTime: Self.started, now: Self.now))
        XCTAssertTrue(EventDetailView.showsBroadcast(status: "scheduled", commenceTime: Self.notYet, now: Self.now))
        XCTAssertTrue(EventDetailView.showsBroadcast(status: nil, commenceTime: Self.notYet, now: Self.now))
    }

    // MARK: - The projection

    /// The 184. A projected FINAL score for a match that will never be given
    /// one, printed in the score's slot, on a hero that had no state label.
    func testASuspendedGameDrawsNoProjectedFinal() {
        XCTAssertFalse(EventDetailView.showsProjection(status: "suspended", commenceTime: Self.started, now: Self.now))
    }

    func testTheProjectionSurvivesWhereItIsStillAProjection() {
        XCTAssertTrue(EventDetailView.showsProjection(status: "live", commenceTime: Self.started, now: Self.now))
        XCTAssertTrue(EventDetailView.showsProjection(status: "scheduled", commenceTime: Self.notYet, now: Self.now))
    }

    func testTheProjectionGateAgreesWithIsFinishedEverywhereElse() {
        // The pre-fix gate was `!isFinished` and nothing else. The fix must
        // differ from it on exactly ONE status — a wider change here would be
        // silently removing the projection from states nobody complained about.
        for status in Self.vocabulary where !EventState.isSuspended(status) {
            XCTAssertEqual(
                EventDetailView.showsProjection(
                    status: status, commenceTime: Self.started, now: Self.now),
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

    // MARK: - #4021 — the clock, and the regression this ship nearly shipped

    /// 🔴 THE ONE THAT CAUGHT ME. `suspended` is a STATUS, NOT A PHASE.
    ///
    /// Event **416569** — Ohio State @ Texas, kick-off 2026-09-12 — sat at
    /// `status='suspended'` FOUR DAYS BEFORE it was due to be played. Filed as
    /// #4021 by lane1b/084 against `/sports`; I re-measured it independently
    /// (`WHERE status='suspended' AND commence_time > now()` → exactly 1 row).
    ///
    /// The first draft of this ship routed every `suspended` row to the settled
    /// treatment without asking the clock, which on that row was a REGRESSION
    /// against master, not a fix: master's pregame default still produced a
    /// correct "In 4d" countdown, because `formatCountdown` works fine on a
    /// FUTURE date — it is only a PAST one it returns nil for. So the shipped
    /// version would have replaced a right answer with "No result reported",
    /// hidden the broadcast, and printed "Started" about a date four days out,
    /// on an Ohio State – Texas game.
    func testAFutureDatedSuspendedGameIsNotTreatedAsAbandoned() {
        XCTAssertTrue(
            EventDetailView.showsBroadcast(
                status: "suspended", commenceTime: Self.notYet, now: Self.now),
            "a game nobody has played lost its broadcast listing"
        )
        XCTAssertTrue(
            EventDetailView.showsProjection(
                status: "suspended", commenceTime: Self.notYet, now: Self.now),
            "a game nobody has played lost its projection"
        )
        XCTAssertFalse(
            EventState.isSuspendedAndStarted(
                "suspended", commenceTime: Self.notYet, now: Self.now),
            "the settled treatment reached a fixture"
        )
    }

    /// …and the fix must not undo #4002. The same status, a PAST date.
    func testAStartedSuspendedGameStillGetsTheWholeRepair() {
        XCTAssertTrue(EventState.isSuspendedAndStarted(
            "suspended", commenceTime: Self.started, now: Self.now))
        XCTAssertFalse(EventDetailView.showsBroadcast(
            status: "suspended", commenceTime: Self.started, now: Self.now))
        XCTAssertFalse(EventDetailView.showsProjection(
            status: "suspended", commenceTime: Self.started, now: Self.now))
    }

    /// A dateless suspended row keeps the repair. Stated as a test because the
    /// default is a judgement, not an accident: `suspended` is produced by
    /// something that watched a match begin and never saw it end, so no date is
    /// far more likely to be a lost schedule than an unplayed fixture — and
    /// defaulting the other way would put the #4002 hero back to a blank badge
    /// on every one of them.
    func testNoCommenceTimeIsTreatedAsStarted() {
        XCTAssertTrue(EventState.hasStarted(commenceTime: nil, now: Self.now))
        XCTAssertTrue(EventState.isSuspendedAndStarted(
            "suspended", commenceTime: nil, now: Self.now))
    }

    /// The boundary. Exactly at kick-off counts as started — a match at its own
    /// commence time has begun, and the alternative leaves a one-instant hole.
    func testTheBoundaryIsInclusive() {
        XCTAssertTrue(EventState.hasStarted(commenceTime: Self.now, now: Self.now))
        XCTAssertFalse(EventState.hasStarted(
            commenceTime: Self.now.addingTimeInterval(1), now: Self.now))
    }

    /// The clock gate is scoped to `suspended` and must not leak. A FINISHED
    /// game with a future commence_time is a data bug of a different kind, and
    /// this ship does not get to decide it is unfinished.
    func testTheClockGateDoesNotReachTheFinishedStates() {
        for status in ["completed", "closed"] {
            XCTAssertFalse(EventDetailView.showsBroadcast(
                status: status, commenceTime: Self.notYet, now: Self.now))
            XCTAssertFalse(EventDetailView.showsProjection(
                status: status, commenceTime: Self.notYet, now: Self.now))
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
                XCTAssertFalse(EventDetailView.showsProjection(
                    status: status, commenceTime: Self.started, now: Self.now))
                XCTAssertFalse(EventDetailView.showsBroadcast(
                    status: status, commenceTime: Self.started, now: Self.now))
            }
            if EventState.isSuspended(status) {
                XCTAssertFalse(EventDetailView.showsProjection(
                    status: status, commenceTime: Self.started, now: Self.now))
                XCTAssertFalse(EventDetailView.showsBroadcast(
                    status: status, commenceTime: Self.started, now: Self.now))
                XCTAssertTrue(EventDetailView.showsScore(status: status, away: 3, home: 4))
            }
        }
    }
}
