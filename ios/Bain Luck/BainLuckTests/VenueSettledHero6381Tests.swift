import XCTest
@testable import Bain_Luck

/// #6381 — what the phone draws for a match the VENUE has already graded while
/// our own row still calls it unplayed.
///
/// THE SPECIMEN, photographed before the fix. `bainluck://events/15310639` —
/// Liverpool FC v Fulham FC, EPL, `tier: 1`. The venue graded
/// `Correct Score · Draw 0-0` with `resolution_source='api_settlement'` on
/// 2026-09-12 and we hold that row. `GET /api/events/15310639` nonetheless
/// serves `status: "scheduled"`, both scores null, no `current_odds`. So on
/// iPhone 17 Pro, 2026-09-15 (`artifacts/native-181/before-01-liverpool-fulham-hero.png`):
///
/// | slot | what it drew | what is true |
/// |---|---|---|
/// | badge | nothing — `formatCountdown` is nil for a past date, so the scheduled arm is `EmptyView` | the venue settled it three days ago |
/// | centre | **vs** | `Draw 0-0` |
/// | meta | `Sep 11 at 5:00 PM` | a kick-off that has been and gone |
/// | market list, one scroll down | `Draw 0-0 · 100%` | the same grade, rendered as a price |
///
/// The web says "No result reported" on this row and the phone does not: that
/// sentence is `EventState.suspendedLabel`, gated on `status == "suspended"`.
/// The suspended arm of the same population — **889 rows against the issue's
/// 426** — does print it over a held grade. Both arms are the same lie told two
/// ways, which is why the fix is one predicate consumed by both.
///
/// WHAT THIS FILE CAN AND CANNOT PROVE. The predicate and the decode, entirely.
/// The WIRING — that the badge chain reaches the new arm before the suspended
/// one, and that the hero's centre slot asks before it prices — is inside
/// SwiftUI bodies that XCTest cannot enter, and CI compiles no Swift at all.
/// That half is `frontend/__tests__/ios/eventStatusSingleSource.test.ts`,
/// "#6381 — the hero stops denying a result the venue already gave us", which
/// runs in CI. Neither half is sufficient alone and both are required by the
/// same ship.
final class VenueSettledHero6381Tests: XCTestCase {

    /// Fixed anchors, offset from a literal instant (gotcha #44 — the anchor is
    /// computed by OFFSET and never by a branch on the real clock, so these do
    /// not straddle a UTC date boundary or read differently at 23:59).
    private static let now = Date(timeIntervalSince1970: 1_789_000_000)
    private static let played = now.addingTimeInterval(-3.6 * 24 * 3600)  // the specimen's gap
    private static let notYet = now.addingTimeInterval(4 * 24 * 3600)

    private func shows(
        _ status: String?, _ venueSettled: Bool?, _ commenceTime: Date?
    ) -> Bool {
        EventState.showsVenueSettledVerdict(
            status, venueSettled: venueSettled, commenceTime: commenceTime, now: Self.now)
    }

    // MARK: - The two arms of the population

    /// THE PHOTOGRAPHED SPECIMEN — `scheduled`, played, graded.
    func testAScheduledRowThatWasPlayedAndGradedGetsTheSettledVoice() {
        XCTAssertTrue(shows("scheduled", true, Self.played))
    }

    /// The BIGGER arm. 889 rows against the issue's own 426, and they are the
    /// ones printing "No result reported" over a result we are holding.
    func testTheSuspendedArmGetsItToo() {
        XCTAssertTrue(shows("suspended", true, Self.played))
    }

    /// The detail page's third arm: a row still claiming `live` with nothing
    /// backing it. 8 rows. It is not excluded here — a page that says a graded
    /// match is in play is wrong in the same direction.
    func testAnUnbackedLiveRowIsNotExcludedByThePredicate() {
        XCTAssertTrue(shows("live", true, Self.played))
    }

    /// Every status the API can put on an event, so that a state added to the
    /// vocabulary cannot quietly miss this predicate the way `suspended` missed
    /// four renders in #4002. Only the two settled words are excluded, and they
    /// are excluded because a Final says this better.
    func testTheWholeVocabularyIsCovered() {
        let vocabulary: [String?] = [
            "scheduled", "live", "suspended", "completed", "closed",
            "postponed", "cancelled", nil,
        ]
        let excluded = vocabulary.filter { !shows($0, true, Self.played) }
        XCTAssertEqual(
            excluded.map { $0 ?? "nil" }, ["completed", "closed"],
            "only the statuses that already print a Final opt out")
    }

    // MARK: - The controls

    func testAFinishedGameKeepsItsFinalAndGainsNoSecondVoice() {
        // A Final has a score and a winner. Two chips making one claim is the
        // defect this ship is removing, not a second copy of it.
        XCTAssertFalse(shows("completed", true, Self.played))
        XCTAssertFalse(shows("closed", true, Self.played))
    }

    func testTheVenueSayingNothingIsNotTheVenueSayingSettled() {
        // `false` is an answer — we asked and there is no graded row.
        XCTAssertFalse(shows("scheduled", false, Self.played))
    }

    func testAnOlderServerThatOmitsTheKeyChangesNothing() {
        // The page keeps exactly what it said before the key existed. This is
        // the state every build in the field is in until the producer's release
        // lands, and it is the one that must not invent a verdict.
        XCTAssertFalse(shows("scheduled", nil, Self.played))
        XCTAssertFalse(shows("suspended", nil, Self.played))
    }

    /// 🔴 #4021's clause, one state along. A row whose kick-off is still ahead
    /// of us must not wear the settled treatment however its attached markets
    /// have been graded — a mis-attached market (#2693) is the one way this key
    /// can be wrong, and the clock is the cheap guard against publishing it.
    func testAFixtureThatHasNotKickedOffYetIsNeverSettled() {
        XCTAssertFalse(shows("scheduled", true, Self.notYet))
        XCTAssertFalse(shows("suspended", true, Self.notYet))
    }

    /// A nil date counts as started, matching `EventState.hasStarted`'s
    /// documented default: a row carrying a venue grade and no date is a played
    /// match we lost the schedule for far more often than a fixture nobody has
    /// played.
    func testADatelessRowFollowsHasStartedRatherThanInventingAThirdRule() {
        XCTAssertTrue(shows("scheduled", true, nil))
        XCTAssertEqual(
            shows("scheduled", true, nil),
            EventState.hasStarted(commenceTime: nil, now: Self.now))
    }

    // MARK: - What the predicate is NOT

    /// It is not `isFinished` and it must never become a settled reading. The
    /// server deliberately did not settle these rows — `status`, the scores and
    /// `started_without_result` are byte-identical beside the new keys, because
    /// settling them is a data write that collides with the rail semantics
    /// #3211 depends on. A caller that reached for this to decide "can this
    /// still be graded" would suppress the forecast cards on 1,471 events off a
    /// signal that was never a status.
    func testItDoesNotMoveTheSettledVocabularyUnderneathIt() {
        XCTAssertFalse(EventState.isFinished("scheduled"))
        XCTAssertFalse(EventState.isFinished("suspended"))
        XCTAssertTrue(
            EventState.canStillBeGraded("scheduled", commenceTime: Self.played, now: Self.now),
            "the forecast gate is unchanged by a venue grade")
    }

    /// Both predicates are TRUE on a suspended graded row, which is exactly why
    /// the badge's arm ORDER is load-bearing and is pinned by the source scan.
    /// If this ever stops being true, that scan is asserting something else.
    func testTheSuspendedAndSettledReadingsOverlapRatherThanPartition() {
        XCTAssertTrue(shows("suspended", true, Self.played))
        XCTAssertTrue(
            EventState.isSuspendedAndStarted(
                "suspended", commenceTime: Self.played, now: Self.now))
    }

    // MARK: - The label

    func testTheLabelIsNeitherFinalNorAMarketWord() {
        XCTAssertEqual(EventState.venueSettledLabel, "Result settled")
        XCTAssertNotEqual(EventState.venueSettledLabel, EventState.suspendedLabel)
    }

    // MARK: - The chart's empty state, one screen below the hero

    /// #3859 drew this distinction for `completed`: a settled game's chart says
    /// "No win probability readings for this game.", because "yet" promises
    /// readings that can never arrive. A venue-graded row is the same sentence
    /// and was still getting the promise — visible in the after-shot of this
    /// very ship, under a hero now reading "Result settled".
    func testAVenueGradedGameDropsTheFalsePromise() {
        XCTAssertEqual(
            OddsChartView.noReadingsLine(
                status: "scheduled", venueSettled: true, commenceTime: Self.played),
            "No win probability readings for this game.")
    }

    func testTheYetSurvivesWhereItIsStillTrue() {
        // A real upcoming fixture, and the pre-fix default — an older server
        // that never sends the key must not have its copy changed.
        XCTAssertEqual(
            OddsChartView.noReadingsLine(
                status: "scheduled", venueSettled: true, commenceTime: Self.notYet),
            "No win probability readings for this game yet.")
        XCTAssertEqual(
            OddsChartView.noReadingsLine(status: "scheduled"),
            "No win probability readings for this game yet.")
    }

    func testTheFinishedReadingIsUnchanged() {
        // #3859's own case, asserted here because this ship rewrote the
        // function that answers it.
        XCTAssertEqual(
            OddsChartView.noReadingsLine(status: "completed"),
            "No win probability readings for this game.")
    }

    // MARK: - The wire

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    func testTheSpecimenPayloadReachesTheModelAndTheHeroReadsItAsSettled() throws {
        let event = try decodeEvent(
            """
            {"id": 15310639, "home_team": "Liverpool FC", "away_team": "Fulham FC",
             "status": "scheduled", "commence_time": "2026-09-12T00:00:00+00:00",
             "home_score": null, "away_score": null,
             "venue_settled": true, "venue_settled_result": "Draw 0-0"}
            """)

        XCTAssertEqual(event.venueSettled, true)
        XCTAssertEqual(event.venueSettledResult, "Draw 0-0")
        XCTAssertTrue(shows(event.status, event.venueSettled, Self.played))
    }

    /// Tennis is 45 of the 68 rows that carry a string at all, and its shape is
    /// not soccer's: these are SETS. The model stores it and nothing parses it
    /// (asserted over the whole app by the source scan) — a split on the dash
    /// would publish "2-0 in sets" as a 2–0 scoreline.
    func testTheTennisShapeArrivesVerbatim() throws {
        let event = try decodeEvent(
            """
            {"id": 15304840, "home_team": "Taylor Townsend", "away_team": "Aryna Sabalenka",
             "status": "scheduled", "venue_settled": true,
             "venue_settled_result": "Aryna Sabalenka wins 2-0"}
            """)

        XCTAssertEqual(event.venueSettledResult, "Aryna Sabalenka wins 2-0")
    }

    /// 370 of the issue's 426 rows are graded on props alone. `venue_settled`
    /// is true and there is no score — the state the hero answers with the word
    /// and no number, because inventing one from a prop grade is the fabricated
    /// verdict the producer refuses on its own side.
    func testSettledWithNoScoreIsAStateAndNotAMissingValue() throws {
        let event = try decodeEvent(
            """
            {"id": 15304840, "home_team": "A", "away_team": "B",
             "status": "scheduled", "venue_settled": true, "venue_settled_result": null}
            """)

        XCTAssertEqual(event.venueSettled, true)
        XCTAssertNil(event.venueSettledResult)
        XCTAssertTrue(shows(event.status, event.venueSettled, Self.played))
    }

    /// The keys are ABSENT, not null, on any server older than the producer's
    /// release — including production at the hour this was written. An absent
    /// key must not fail the event's decode, and it must not read as settled.
    func testAPayloadWithoutTheKeysStillDecodesAndSaysNothing() throws {
        let event = try decodeEvent(
            """
            {"id": 1, "home_team": "A", "away_team": "B", "status": "scheduled"}
            """)

        XCTAssertNil(event.venueSettled)
        XCTAssertNil(event.venueSettledResult)
        XCTAssertFalse(shows(event.status, event.venueSettled, Self.played))
    }
}
