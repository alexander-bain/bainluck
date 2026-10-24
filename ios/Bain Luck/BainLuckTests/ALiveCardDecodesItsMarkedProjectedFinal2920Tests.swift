import XCTest
@testable import Bain_Luck

/// #2920 — `CurrentOdds.liveProjection` decodes the producer's marked in-play
/// pair, and nothing about it can cost a card its probability.
///
/// Decoder only. What a live surface may print from the object (kind, boundary,
/// unit and period against the sport, clock order, score reachability) is the
/// reader's rule and is not tested or decided here.
///
/// FIXTURES, AND WHAT THEY ARE:
///
/// * The three `live_projection` objects are the accepted producer's OWN output
///   (`a8df6e34cd`, `card_projected_pair.event_live_projection`) for the rows
///   in its own suite `backend/tests/test_live_projection_2920.py`, serialized
///   with `json.dumps` and pasted unedited (sha256 of the three-object dump
///   `b7262038…3a00fd`). Producer-built, NOT production-served: the object was
///   not on any served payload when this was written.
///     - NFL: `test_a_live_game_carries_one_marked_in_play_pair_with_its_provenance`
///     - soccer: `test_a_soccer_match_in_regulation_carries_goals_on_the_regulation_basis` (67')
///     - pre-kickoff quote confirmed in play:
///       `test_an_unchanged_quote_first_made_before_kickoff_and_confirmed_in_play_is_admitted`
/// * The `current_odds` body around them is event 14870008's served
///   `/api/events/{id}` `current_odds` (Georgia v Oklahoma, live, 2026-09-26),
///   verbatim from UX's retained capture in
///   `frontend/__tests__/fixtures/liveCardProjectedFinal2920.json`. Its legacy
///   pair (36.9 / 10.7) deliberately differs from the object's, so a test can
///   tell which one it read.
///
/// Every malformed case edits ONE thing in those bodies and says what: those
/// are CONSTRUCTED, never claimed as served.
final class ALiveCardDecodesItsMarkedProjectedFinal2920Tests: XCTestCase {

    // MARK: - Fixtures

    private static let nflObject = #"""
    {
     "projected_home_score": 29.5,
     "projected_away_score": 19.0,
     "kind": "in_play",
     "boundary": "commence_time",
     "boundary_at": "2026-10-19T20:25:00+00:00",
     "earliest_confirmed_at": "2026-10-19T21:06:00+00:00",
     "latest_captured_at": "2026-10-19T21:06:00+00:00",
     "source": "sportsbooks",
     "basis": "consensus_spread_total",
     "bookmaker_count": 2,
     "unit": "points",
     "period": "full_game"
    }
    """#

    private static let soccerObject = #"""
    {
     "projected_home_score": 1.5,
     "projected_away_score": 1.0,
     "kind": "in_play",
     "boundary": "commence_time",
     "boundary_at": "2026-10-19T20:25:00+00:00",
     "earliest_confirmed_at": "2026-10-19T21:05:00+00:00",
     "latest_captured_at": "2026-10-19T21:05:00+00:00",
     "source": "sportsbooks",
     "basis": "consensus_spread_total",
     "bookmaker_count": 2,
     "unit": "goals",
     "period": "regulation"
    }
    """#

    private static let preKickoffQuoteObject = #"""
    {
     "projected_home_score": 29.5,
     "projected_away_score": 19.0,
     "kind": "in_play",
     "boundary": "commence_time",
     "boundary_at": "2026-10-19T20:25:00+00:00",
     "earliest_confirmed_at": "2026-10-19T21:07:00+00:00",
     "latest_captured_at": "2026-10-19T20:10:00+00:00",
     "source": "sportsbooks",
     "basis": "consensus_spread_total",
     "bookmaker_count": 2,
     "unit": "points",
     "period": "full_game"
    }
    """#

    /// Event 14870008's served `current_odds`, with `LIVE_PROJECTION` standing
    /// where a `"live_projection": …` member is spliced in (or nothing).
    private static let servedCurrentOdds = #"""
    {"captured_at": "2026-09-26T20:36:31.263891+00:00", "home_probability": 0.9369, "away_probability": 0.0631, "away_rendered_percent": 6, "home_rendered_percent": 94, "spread": -26.1, "over_under": 47.6, "projected_home_score": 36.9, "projected_away_score": 10.7, "bookmaker_count": 3LIVE_PROJECTION}
    """#

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// The served body with `member` spliced in as `"live_projection": member`,
    /// or with no such key when `member` is nil.
    private func currentOddsJSON(liveProjection member: String?) -> String {
        Self.servedCurrentOdds.replacingOccurrences(
            of: "LIVE_PROJECTION",
            with: member.map { #", "live_projection": "# + $0 } ?? "")
    }

    private func odds(liveProjection member: String?, file: StaticString = #filePath,
                      line: UInt = #line) throws -> CurrentOdds {
        let json = currentOddsJSON(liveProjection: member)
        do {
            return try decoder().decode(CurrentOdds.self, from: Data(json.utf8))
        } catch {
            XCTFail("current_odds failed to decode: \(error)", file: file, line: line)
            throw error
        }
    }

    /// The served probability fields, unchanged by anything under `live_projection`.
    private func assertServedProbabilitiesIntact(_ o: CurrentOdds, _ why: String,
                                                 file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(o.capturedAt, "2026-09-26T20:36:31.263891+00:00", why, file: file, line: line)
        XCTAssertEqual(o.homeProbability, 0.9369, why, file: file, line: line)
        XCTAssertEqual(o.awayProbability, 0.0631, why, file: file, line: line)
        XCTAssertEqual(o.homeRenderedPercent, 94, why, file: file, line: line)
        XCTAssertEqual(o.awayRenderedPercent, 6, why, file: file, line: line)
        XCTAssertEqual(o.spread, -26.1, why, file: file, line: line)
        XCTAssertEqual(o.overUnder, 47.6, why, file: file, line: line)
        XCTAssertEqual(o.projectedHomeScore, 36.9, why, file: file, line: line)
        XCTAssertEqual(o.projectedAwayScore, 10.7, why, file: file, line: line)
        XCTAssertEqual(o.bookmakerCount, 3, why, file: file, line: line)
    }

    /// The producer's NFL object, field for field; each argument overrides one.
    private func projection(
        home: Double? = 29.5,
        away: Double? = 19.0,
        kind: String? = "in_play",
        boundary: String? = "commence_time",
        boundaryAt: String? = "2026-10-19T20:25:00+00:00",
        confirmed: String? = "2026-10-19T21:06:00+00:00",
        captured: String? = "2026-10-19T21:06:00+00:00",
        source: String? = "sportsbooks",
        basis: String? = "consensus_spread_total",
        books: Double? = 2,
        unit: String? = "points",
        period: String? = "full_game"
    ) -> LiveProjection {
        LiveProjection(
            projectedHomeScore: home, projectedAwayScore: away, kind: kind,
            boundary: boundary, boundaryAt: boundaryAt, earliestConfirmedAt: confirmed,
            latestCapturedAt: captured, source: source, basis: basis,
            bookmakerCount: books, unit: unit, period: period)
    }

    private static let allNil = LiveProjection(
        projectedHomeScore: nil, projectedAwayScore: nil, kind: nil, boundary: nil,
        boundaryAt: nil, earliestConfirmedAt: nil, latestCapturedAt: nil, source: nil,
        basis: nil, bookmakerCount: nil, unit: nil, period: nil)

    // MARK: - The producer's object actually decodes

    func testTheProducersNFLObjectDecodesFieldForField() throws {
        let o = try odds(liveProjection: Self.nflObject)
        XCTAssertEqual(o.liveProjection, projection(), "every producer field must decode as built")
        assertServedProbabilitiesIntact(o, "the object must not disturb its siblings")
    }

    func testTheMarkedPairIsNotTheLegacyPair() throws {
        // The served body's bare pair is 36.9 / 10.7; the object's is 29.5 / 19.0.
        // Each must come from its own key — the decoder never copies one into the other.
        let o = try odds(liveProjection: Self.nflObject)
        let live = try XCTUnwrap(o.liveProjection)
        XCTAssertEqual(live.projectedHomeScore, 29.5)
        XCTAssertEqual(live.projectedAwayScore, 19.0)
        XCTAssertEqual(o.projectedHomeScore, 36.9)
        XCTAssertEqual(o.projectedAwayScore, 10.7)
        XCTAssertEqual(live.bookmakerCount, 2, "the object's count is its contributors, not current_odds' 3")
        XCTAssertEqual(o.bookmakerCount, 3)
    }

    func testTheSoccerObjectKeepsItsGoalsUnitAndRegulationPeriod() throws {
        let o = try odds(liveProjection: Self.soccerObject)
        XCTAssertEqual(o.liveProjection, projection(
            home: 1.5, away: 1.0,
            confirmed: "2026-10-19T21:05:00+00:00", captured: "2026-10-19T21:05:00+00:00",
            unit: "goals", period: "regulation"))
    }

    func testTheTwoClocksStayTheirOwnWhenACaptureMayPrecedeTheBoundary() throws {
        // Producer C2: quoted at -20/-15 min, still the live price at +44/+42.
        // latest_captured_at (20:10) < boundary_at (20:25) <= earliest_confirmed_at (21:07).
        let o = try odds(liveProjection: Self.preKickoffQuoteObject)
        let live = try XCTUnwrap(o.liveProjection)
        XCTAssertEqual(live.latestCapturedAt, "2026-10-19T20:10:00+00:00")
        XCTAssertEqual(live.earliestConfirmedAt, "2026-10-19T21:07:00+00:00")
        XCTAssertEqual(live.boundaryAt, "2026-10-19T20:25:00+00:00")
        XCTAssertEqual(live.boundary, "commence_time")
        XCTAssertNotEqual(live.latestCapturedAt, live.earliestConfirmedAt,
                          "one clock must never be written into the other")
        XCTAssertEqual(live, projection(confirmed: "2026-10-19T21:07:00+00:00",
                                        captured: "2026-10-19T20:10:00+00:00"))
        XCTAssertEqual(o.capturedAt, "2026-09-26T20:36:31.263891+00:00",
                       "current_odds.captured_at dates the blend, not the object")
    }

    func testTheObjectDecodesWhicheverOrderItsKeysArriveIn() throws {
        // CONSTRUCTED: the NFL object's members reversed. Keys, not position.
        let reversed = """
        {"period": "full_game", "unit": "points", "bookmaker_count": 2,
         "basis": "consensus_spread_total", "source": "sportsbooks",
         "latest_captured_at": "2026-10-19T21:06:00+00:00",
         "earliest_confirmed_at": "2026-10-19T21:06:00+00:00",
         "boundary_at": "2026-10-19T20:25:00+00:00", "boundary": "commence_time",
         "kind": "in_play", "projected_away_score": 19.0, "projected_home_score": 29.5}
        """
        XCTAssertEqual(try odds(liveProjection: reversed).liveProjection, projection())
    }

    // MARK: - Absent and null: nil, and the probability stays

    func testNoKeyDecodesToNilAndKeepsTheProbability() throws {
        let o = try odds(liveProjection: nil)
        XCTAssertNil(o.liveProjection)
        assertServedProbabilitiesIntact(o, "a payload without the key is every payload before #2920")
    }

    func testANullObjectDecodesToNilAndKeepsTheProbability() throws {
        let o = try odds(liveProjection: "null")
        XCTAssertNil(o.liveProjection, "null is withheld, the same as absent")
        assertServedProbabilitiesIntact(o, "null object")
    }

    // MARK: - Wrong type: present, unreadable, and the probability stays

    func testAWrongTypedObjectStaysPresentAndKeepsTheProbability() throws {
        // CONSTRUCTED: the key holds something that is not an object. It must
        // neither throw (dropping the card) nor read as absent (web's reader
        // treats a present value as "do not fall back to the bare pair").
        for member in [#""in_play""#, "29.5", "true", "[29.5, 19.0]", "[]"] {
            let o = try odds(liveProjection: member)
            XCTAssertEqual(o.liveProjection, Self.allNil, "live_projection: \(member)")
            assertServedProbabilitiesIntact(o, "live_projection: \(member)")
        }
    }

    func testAnEmptyObjectIsPresentWithNothingReadable() throws {
        let o = try odds(liveProjection: "{}")
        XCTAssertEqual(o.liveProjection, Self.allNil)
        assertServedProbabilitiesIntact(o, "empty object")
    }

    // MARK: - Malformed fields: that field only

    func testAWrongTypedFieldIsNilAndEveryOtherFieldSurvives() throws {
        // CONSTRUCTED: one field of the NFL object at a time takes the wrong JSON
        // type. Only that field reads nil; the rest decode as built.
        let cases: [(from: String, to: String, expected: LiveProjection)] = [
            (#""projected_home_score": 29.5"#, #""projected_home_score": "29.5""#, projection(home: nil)),
            (#""projected_away_score": 19.0"#, #""projected_away_score": {"v": 19}"#, projection(away: nil)),
            (#""kind": "in_play""#, #""kind": 1"#, projection(kind: nil)),
            (#""boundary": "commence_time""#, #""boundary": ["commence_time"]"#, projection(boundary: nil)),
            (#""boundary_at": "2026-10-19T20:25:00+00:00""#, #""boundary_at": 1792441500"#, projection(boundaryAt: nil)),
            (#""earliest_confirmed_at": "2026-10-19T21:06:00+00:00""#, #""earliest_confirmed_at": false"#,
             projection(confirmed: nil)),
            (#""latest_captured_at": "2026-10-19T21:06:00+00:00""#, #""latest_captured_at": {}"#,
             projection(captured: nil)),
            (#""source": "sportsbooks""#, #""source": 7"#, projection(source: nil)),
            (#""basis": "consensus_spread_total""#, #""basis": []"#, projection(basis: nil)),
            (#""bookmaker_count": 2"#, #""bookmaker_count": "2""#, projection(books: nil)),
            (#""unit": "points""#, #""unit": 0"#, projection(unit: nil)),
            (#""period": "full_game""#, #""period": {"name": "full_game"}"#, projection(period: nil)),
        ]
        for c in cases {
            let edited = Self.nflObject.replacingOccurrences(of: c.from, with: c.to)
            XCTAssertNotEqual(edited, Self.nflObject, "the edit must land: \(c.from)")
            let o = try odds(liveProjection: edited)
            XCTAssertEqual(o.liveProjection, c.expected, c.to)
            assertServedProbabilitiesIntact(o, c.to)
        }
    }

    func testANullOrMissingFieldIsNilAndEveryOtherFieldSurvives() throws {
        // CONSTRUCTED: the confirmation clock nulled, then the capture clock
        // removed. A missing clock is not filled from the other one.
        let nulled = Self.nflObject.replacingOccurrences(
            of: #""earliest_confirmed_at": "2026-10-19T21:06:00+00:00""#,
            with: #""earliest_confirmed_at": null"#)
        XCTAssertNotEqual(nulled, Self.nflObject)
        XCTAssertEqual(try odds(liveProjection: nulled).liveProjection, projection(confirmed: nil))

        let missing = Self.nflObject.replacingOccurrences(
            of: #" "latest_captured_at": "2026-10-19T21:06:00+00:00","#, with: "")
        XCTAssertNotEqual(missing, Self.nflObject)
        XCTAssertEqual(try odds(liveProjection: missing).liveProjection, projection(captured: nil))
    }

    func testValuesTheReaderMustRefuseStillDecodeVerbatim() throws {
        // CONSTRUCTED: a fractional count, an unknown kind, a tennis unit and an
        // extra-time period. Refusing them is admission, which is not the
        // decoder's job: each must reach the reader exactly as served.
        var edited = Self.nflObject
        for (from, to) in [(#""bookmaker_count": 2"#, #""bookmaker_count": 2.5"#),
                           (#""kind": "in_play""#, #""kind": "pregame""#),
                           (#""unit": "points""#, #""unit": "games""#),
                           (#""period": "full_game""#, #""period": "extra_time""#)] {
            let next = edited.replacingOccurrences(of: from, with: to)
            XCTAssertNotEqual(next, edited, "the edit must land: \(from)")
            edited = next
        }
        XCTAssertEqual(try odds(liveProjection: edited).liveProjection,
                       projection(kind: "pregame", books: 2.5, unit: "games", period: "extra_time"))
    }

    func testAnUnknownExtraMemberIsIgnored() throws {
        // CONSTRUCTED: an additive producer field this build does not know.
        let extra = Self.nflObject.replacingOccurrences(
            of: #""period": "full_game""#, with: #""period": "full_game", "future_field": {"x": 1}"#)
        XCTAssertNotEqual(extra, Self.nflObject)
        XCTAssertEqual(try odds(liveProjection: extra).liveProjection, projection())
    }

    // MARK: - Through the real feed path

    private static let feedItems = #"""
    [
      {"type": "event", "score": 35, "reason": "", "headline": null,
       "data": {"id": 14870008, "sport": "americanfootball_ncaaf", "home_team": "Georgia Bulldogs",
                "away_team": "Oklahoma Sooners", "commence_time": "2026-09-26T19:30:00+00:00",
                "status": "live", "home_score": 21, "away_score": 0,
                "current_odds": FIRST_ODDS}},
      {"type": "event", "score": 30, "reason": "", "headline": null,
       "data": {"id": 14870009, "sport": "americanfootball_ncaaf", "home_team": "Home",
                "away_team": "Away", "commence_time": "2026-09-26T19:30:00+00:00",
                "status": "live", "home_score": 7, "away_score": 3,
                "current_odds": SECOND_ODDS}}
    ]
    """#

    func testAFeedCardCarriesTheObjectAndAMalformedSiblingKeepsItsCard() throws {
        // CONSTRUCTED feed items around the served current_odds body: the first
        // carries the producer's object, the second a wrong-typed one.
        let json = Self.feedItems
            .replacingOccurrences(of: "FIRST_ODDS", with: currentOddsJSON(liveProjection: Self.nflObject))
            .replacingOccurrences(of: "SECOND_ODDS", with: currentOddsJSON(liveProjection: #""bad""#))
        let items = try decoder().decode([FeedItem].self, from: Data(json.utf8))
        let events = items.compactMap(\.event)
        XCTAssertEqual(events.map(\.id), [14870008, 14870009], "no card may be dropped")

        let first = try XCTUnwrap(events[0].currentOdds)
        XCTAssertEqual(first.liveProjection, projection())
        assertServedProbabilitiesIntact(first, "feed card with the object")

        let second = try XCTUnwrap(events[1].currentOdds)
        XCTAssertEqual(second.liveProjection, Self.allNil)
        assertServedProbabilitiesIntact(second, "feed card with a malformed object")
    }

    // MARK: - Source compatibility

    func testTheMemberwiseInitializerKeepsItsExistingShape() {
        // Compiles only if the new field has a default: every pre-#2920 call
        // shape must still build.
        let old = CurrentOdds(
            capturedAt: nil, spread: nil, homeSpread: nil, overUnder: nil,
            projectedHomeScore: nil, projectedAwayScore: nil, bookmakerCount: nil)
        XCTAssertNil(old.liveProjection)

        let carried = CurrentOdds(
            capturedAt: nil, spread: nil, homeSpread: nil, overUnder: nil,
            projectedHomeScore: nil, projectedAwayScore: nil, bookmakerCount: nil,
            liveProjection: projection())
        XCTAssertEqual(carried.liveProjection, projection())
    }

    func testAPushedProbabilityStillWritesThroughAndLeavesTheObjectAlone() throws {
        // #2687: the stream writes the probability into the decoded model. The
        // object is not the stream's to touch here.
        var o = try odds(liveProjection: Self.nflObject)
        o.homeProbability = 0.5
        o.awayProbability = 0.5
        o.homeRenderedPercent = nil
        o.awayRenderedPercent = nil
        XCTAssertEqual(o.homeProbability, 0.5)
        XCTAssertEqual(o.liveProjection, projection())
    }
}
