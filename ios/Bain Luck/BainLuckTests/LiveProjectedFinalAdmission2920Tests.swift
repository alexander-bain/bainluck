import XCTest
@testable import Bain_Luck

/// #2920 / #9483 — what a native live card and headline may print from
/// `CurrentOdds.liveProjection`, and every case where the answer is nothing.
///
/// Ported gate for gate from the accepted web helper's suite
/// (`frontend/__tests__/liveCardProjectedFinal2920.test.tsx` at `af2d236030`).
/// Every refusal sits beside a positive control that differs from it in the one
/// input under test, so a refusal can only pass because that input refused it.
/// Every object reaches the helper through the real decoder (`CurrentOdds`)
/// unless a test says it builds one.
///
/// FIXTURES, AND WHAT THEY ARE:
///
/// * `nflObject`, `soccerObject`, `preKickoffQuoteObject`: the accepted
///   producer's OWN output (`a8df6e34cd`, `event_live_projection`) for the rows
///   in `backend/tests/test_live_projection_2920.py`, as carried verbatim by the
///   accepted decoder suite (`7cd37aa70a`,
///   `ALiveCardDecodesItsMarkedProjectedFinal2920Tests`). Producer-built, NOT
///   production-served. The producer's rows start at 2026-10-19 20:25Z, are
///   `americanfootball_nfl` (period Q3) and `soccer_epl` (67'). The ROW around
///   them (status, start, actual score, clock) is CONSTRUCTED here and says so.
/// * `servedUGA`: event 14870008's served `/api/events/{id}` `current_odds`
///   (Georgia 21 – 0 Oklahoma, live, start 19:30Z), verbatim from UX's retained
///   capture `frontend/__tests__/fixtures/liveCardProjectedFinal2920.json`. Its
///   bare pair 36.9 / 10.7 differs from the producer object's 29.5 / 19.0, so a
///   test can tell which one was printed. `ugaInPlay` wraps the served values in
///   the producer's shape exactly as web's `inPlay` does (earliest confirmation
///   19:35:32Z, the first book captured after the start) — CONSTRUCTED shape.
/// * `servedKLeague`: event 15306856's served `current_odds` (Sangju Sangmu 1 – 0
///   Gangwon, live, start 07:31Z): 1.8 / 1.0, bovada's 08:02Z quote alone, so
///   the wrapped object's count is 1. Its phase (~31') is CONSTRUCTED: the
///   served ESPN block carried none.
/// * `served49ers`: event 14780563's served `current_odds` (Commanders @ 49ers,
///   start 2026-10-20 00:15Z): the PREGAME pair 29.6 / 22.3 captured 22:20Z. The
///   halftime 20 – 3 live row around it is the one the page photographed,
///   CONSTRUCTED as web's test constructs it.
///
/// Apple compile and run of this file are UNRUN by its author.
@MainActor
final class LiveProjectedFinalAdmission2920Tests: XCTestCase {

    private typealias A = LiveProjectedFinalAdmission2920

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

    /// Event 14870008's served `current_odds`; `LIVE_PROJECTION` marks where a
    /// `"live_projection": …` member is spliced in (or nothing).
    private static let servedUGA = #"""
    {"captured_at": "2026-09-26T20:36:31.263891+00:00", "home_probability": 0.9369, "away_probability": 0.0631, "away_rendered_percent": 6, "home_rendered_percent": 94, "spread": -26.1, "over_under": 47.6, "projected_home_score": 36.9, "projected_away_score": 10.7, "bookmaker_count": 3LIVE_PROJECTION}
    """#

    private static let servedKLeague = #"""
    {"captured_at": "2026-09-13T08:02:03.508636+00:00", "home_probability": 0.7708, "away_probability": 0.2292, "away_rendered_percent": 23, "home_rendered_percent": 77, "spread": -0.8, "over_under": 2.6, "projected_home_score": 1.8, "projected_away_score": 1.0, "bookmaker_count": 4LIVE_PROJECTION}
    """#

    private static let served49ers = #"""
    {"captured_at": "2026-10-19T22:20:24.725508+00:00", "home_probability": 0.7723, "away_probability": 0.2277, "away_rendered_percent": 23, "home_rendered_percent": 77, "spread": -7.3, "over_under": 51.9, "projected_home_score": 29.6, "projected_away_score": 22.3, "bookmaker_count": 21LIVE_PROJECTION}
    """#

    /// Web's `inPlay(UGA, "2026-09-26T19:35:32.134948+00:00")`.
    private static let ugaInPlay = #"""
    {"projected_home_score": 36.9, "projected_away_score": 10.7, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-09-26T19:30:00+00:00", "earliest_confirmed_at": "2026-09-26T19:35:32.134948+00:00", "latest_captured_at": "2026-09-26T20:36:31.263891+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 3, "unit": "points", "period": "full_game"}
    """#

    private static let kLeagueInPlay = #"""
    {"projected_home_score": 1.8, "projected_away_score": 1.0, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-09-13T07:31:00+00:00", "earliest_confirmed_at": "2026-09-13T08:02:03.508636+00:00", "latest_captured_at": "2026-09-13T08:02:03.508636+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 1, "unit": "goals", "period": "regulation"}
    """#

    /// 14780563's pregame pair wrapped as web's test wraps it: confirmed at its
    /// own 22:20Z capture, before the 00:15Z start. The producer never emits this.
    private static let fortyNinersSeeded = #"""
    {"projected_home_score": 29.6, "projected_away_score": 22.3, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-20T00:15:00+00:00", "earliest_confirmed_at": "2026-10-19T22:20:24.725508+00:00", "latest_captured_at": "2026-10-19T22:20:24.725508+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 21, "unit": "points", "period": "full_game"}
    """#

    /// The producer's row start (`_KICKOFF`).
    private static let producerStart = "2026-10-19T20:25:00+00:00"
    /// CONSTRUCTED: 45 minutes after the producer's start.
    private static let producerNow = "2026-10-19T21:10:00+00:00"

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// `body` with `member` spliced in as `"live_projection": member`, or no such
    /// key when nil, decoded through the real `CurrentOdds`.
    private func odds(_ body: String = LiveProjectedFinalAdmission2920Tests.servedUGA,
                      liveProjection member: String?,
                      file: StaticString = #filePath, line: UInt = #line) throws -> CurrentOdds {
        let json = body.replacingOccurrences(
            of: "LIVE_PROJECTION", with: member.map { #", "live_projection": "# + $0 } ?? "")
        do {
            return try decoder().decode(CurrentOdds.self, from: Data(json.utf8))
        } catch {
            XCTFail("current_odds failed to decode: \(error)", file: file, line: line)
            throw error
        }
    }

    /// The decoded object alone.
    private func object(_ json: String, file: StaticString = #filePath, line: UInt = #line) throws -> LiveProjection {
        try XCTUnwrap(odds(liveProjection: json, file: file, line: line).liveProjection,
                      "a present object must decode non-nil", file: file, line: line)
    }

    /// `json` with one top-level member replaced by `value` (raw JSON) — or
    /// removed when `value` is nil. CONSTRUCTED edits only.
    private func edited(_ json: String, _ key: String, _ value: String?) throws -> String {
        var dict = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        if let value {
            dict[key] = try JSONSerialization.jsonObject(with: Data(value.utf8), options: .fragmentsAllowed)
        } else {
            dict.removeValue(forKey: key)
        }
        return String(decoding: try JSONSerialization.data(withJSONObject: dict), as: UTF8.self)
    }

    private func date(_ s: String) throws -> Date { try XCTUnwrap(s.asDate, "unreadable fixture stamp \(s)") }

    /// The producer's NFL row, live, 14 – 10 at +45 min. Each argument overrides one input.
    private func resolve(
        _ projection: LiveProjection?,
        sport: String? = "americanfootball_nfl",
        status: String? = "live",
        start: String? = LiveProjectedFinalAdmission2920Tests.producerStart,
        isTBD: Bool? = false,
        isFromSchedule: Bool? = true,
        home: Int? = 14,
        away: Int? = 10,
        phase: LiveProjectedFinalAdmission2920.Phase? = nil,
        now: String = LiveProjectedFinalAdmission2920Tests.producerNow
    ) throws -> LiveProjectedFinalAdmission2920.Outcome {
        A.resolve(
            projection: projection, sport: sport, status: status,
            rowStart: .init(commenceTime: start, isTBD: isTBD, isFromSchedule: isFromSchedule),
            homeScore: home, awayScore: away, phase: phase, now: try date(now))
    }

    private func printed(_ o: LiveProjectedFinalAdmission2920.Outcome, _ why: String,
                         file: StaticString = #filePath, line: UInt = #line) throws -> A.Printed {
        try XCTUnwrap(o.printed, "\(why) — withheld as \(String(describing: o.refusal))", file: file, line: line)
    }

    private func assertPair(_ o: LiveProjectedFinalAdmission2920.Outcome, home: Int, away: Int, _ why: String,
                            file: StaticString = #filePath, line: UInt = #line) throws {
        let p = try printed(o, why, file: file, line: line)
        XCTAssertEqual(p.home, home, why, file: file, line: line)
        XCTAssertEqual(p.away, away, why, file: file, line: line)
    }

    private func assertWithheld(_ o: LiveProjectedFinalAdmission2920.Outcome, _ why: A.Refusal, _ message: String,
                                file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertNil(o.printed, message, file: file, line: line)
        XCTAssertEqual(o.refusal, why, message, file: file, line: line)
    }

    // MARK: - The fixtures are the readings they claim

    func testTheFixturesAreTheReadingsTheyClaim() throws {
        let nfl = try object(Self.nflObject)
        XCTAssertEqual(nfl.boundaryAt, Self.producerStart)
        let pre = try object(Self.preKickoffQuoteObject)
        XCTAssertLessThan(try date(XCTUnwrap(pre.latestCapturedAt)), try date(Self.producerStart),
                          "the pre-kickoff quote was first captured before the start")
        let served = try odds(liveProjection: nil)
        XCTAssertEqual(served.projectedHomeScore, 36.9)
        XCTAssertEqual(served.projectedAwayScore, 10.7)
        let fortyNiners = try odds(Self.served49ers, liveProjection: nil)
        XCTAssertLessThan(try date(XCTUnwrap(fortyNiners.capturedAt)), try date("2026-10-20T00:15:00+00:00"),
                          "14780563's pair was read before its start")
    }

    // MARK: - Positives on the producer's own objects

    func testTheProducersNFLObjectPrintsItsOwnPairNotTheBarePair() throws {
        // The served body around it carries 36.9 / 10.7 (37 – 11). The object is
        // 29.5 / 19.0, so 30 – 19 can only come from the object.
        let co = try odds(liveProjection: Self.nflObject)
        let p = try printed(try resolve(co.liveProjection), "the producer's NFL object must print")
        XCTAssertEqual([p.home, p.away], [30, 19])
        XCTAssertEqual(p.label, "Projected final")
        XCTAssertEqual(p.admitted.home, 29.5)
        XCTAssertEqual(p.admitted.away, 19.0)
        XCTAssertEqual(p.admitted.provenance, A.Provenance(
            bookmakerCount: 2,
            scheduledStart: try date("2026-10-19T20:25:00+00:00"),
            earliestConfirmedAt: try date("2026-10-19T21:06:00+00:00"),
            latestCapturedAt: try date("2026-10-19T21:06:00+00:00"),
            unit: .points, period: .fullGame))
    }

    func testTheServedGeorgiaRowPrintsWhatWebsCardsPrint() throws {
        // Web: EventCard "37-11 home-away", FeedCard "37-11 away-home", page {36.9, 10.7}.
        let co = try odds(liveProjection: Self.ugaInPlay)
        let o = try resolve(co.liveProjection, sport: "americanfootball_ncaaf",
                            start: "2026-09-26T19:30:00+00:00", isFromSchedule: nil, home: 21, away: 0,
                            now: "2026-09-26T20:40:00+00:00")
        try assertPair(o, home: 37, away: 11, "Georgia 21 – 0 must print 37 – 11, home 37")
        XCTAssertEqual(o.printed?.admitted.provenance.bookmakerCount, 3)
    }

    func testTheProducersSoccerObjectPrintsGoalsOverNinetyMinutes() throws {
        let o = try resolve(try object(Self.soccerObject), sport: "soccer_epl", home: 1, away: 0,
                            phase: A.soccerPhase(servedPeriod: "67'"))
        let p = try printed(o, "the producer's soccer object at 67' must print")
        XCTAssertEqual([p.home, p.away], [2, 1])
        XCTAssertEqual(p.label, "Projected final (90 min)")
        XCTAssertEqual(p.admitted.provenance.unit, .goals)
        XCTAssertEqual(p.admitted.provenance.period, .regulation)
    }

    func testTheServedKLeagueRowPrintsTwoOne() throws {
        let co = try odds(Self.servedKLeague, liveProjection: Self.kLeagueInPlay)
        let o = try resolve(co.liveProjection, sport: "soccer_korea_kleague1",
                            start: "2026-09-13T07:31:00+00:00", isTBD: nil, isFromSchedule: nil,
                            home: 1, away: 0, phase: A.soccerPhase(servedPeriod: "31'"),
                            now: "2026-09-13T08:05:00+00:00")
        try assertPair(o, home: 2, away: 1, "Sangju 1 – 0 at 31' must print 2 – 1")
    }

    // MARK: - Two clocks: original capture vs later confirmation

    func testAQuoteCapturedBeforeKickoffAndReconfirmedInPlayIsAdmitted() throws {
        // latest_captured_at 20:10 < boundary 20:25 <= earliest_confirmed_at 21:07.
        let reconfirmed = try resolve(try object(Self.preKickoffQuoteObject))
        try assertPair(reconfirmed, home: 30, away: 19, "an unchanged quote reconfirmed in play must print")
        let fresh = try resolve(try object(Self.nflObject))
        XCTAssertEqual(reconfirmed.printed?.home, fresh.printed?.home,
                       "the same value reconfirmed prints as the same final as a fresh in-play quote")
        XCTAssertEqual(reconfirmed.printed?.away, fresh.printed?.away)
        let prov = try XCTUnwrap(reconfirmed.printed?.admitted.provenance)
        XCTAssertLessThan(prov.latestCapturedAt, prov.scheduledStart, "the capture clock stays its own")
        XCTAssertGreaterThan(prov.earliestConfirmedAt, prov.latestCapturedAt, "and is never replaced by the confirmation")
    }

    func testTheLatestCaptureIsComparedWithNothing() throws {
        // Positive controls for the one clock with no ordering rule.
        for captured in ["2026-10-19T19:00:00+00:00", "2026-10-19T21:30:00+00:00", "2026-10-19T21:06:00Z"] {
            let o = try resolve(try object(edited(Self.nflObject, "latest_captured_at", "\"\(captured)\"")))
            try assertPair(o, home: 30, away: 19, "latest capture \(captured) must not decide admission")
        }
    }

    func testTheEarliestConfirmationMayEqualButNotPrecedeTheBoundary() throws {
        let atBoundary = try resolve(try object(edited(Self.nflObject, "earliest_confirmed_at", "\"2026-10-19T20:25:00+00:00\"")))
        try assertPair(atBoundary, home: 30, away: 19, "confirmed exactly at the start is in play")
        let before = try resolve(try object(edited(Self.nflObject, "earliest_confirmed_at", "\"2026-10-19T20:24:59+00:00\"")))
        assertWithheld(before, .confirmedBeforeBoundary, "a confirmation one second before the start is pregame")
    }

    func testTheFortyNinersPregamePairNeverPrintsUnderTheHalftimeScore() throws {
        // 29.6 / 22.3 rounds to 30 – 22, reachable from 20 – 3: only the marker refuses it.
        let row = (start: "2026-10-20T00:15:00+00:00", now: "2026-10-20T01:40:00+00:00")
        let bare = try odds(Self.served49ers, liveProjection: nil)
        assertWithheld(try resolve(bare.liveProjection, start: row.start, isFromSchedule: nil, home: 20, away: 3, now: row.now),
                       .absent, "a bare pregame pair with no object never becomes the live forecast")
        let seeded = try odds(Self.served49ers, liveProjection: Self.fortyNinersSeeded)
        assertWithheld(try resolve(seeded.liveProjection, start: row.start, isFromSchedule: nil, home: 20, away: 3, now: row.now),
                       .confirmedBeforeBoundary, "an object confirmed before the start is pregame, whatever its kind says")
    }

    // MARK: - Absent, null, malformed: no current pair, no fallback

    func testAbsentAndNullAreAbsentAndTheBarePairIsNeverRead() throws {
        for member in [nil, "null"] as [String?] {
            let co = try odds(liveProjection: member)
            XCTAssertNotNil(co.projectedHomeScore, "the bare pair is right there")
            assertWithheld(try resolve(co.liveProjection, sport: "americanfootball_ncaaf",
                                       start: "2026-09-26T19:30:00+00:00", isFromSchedule: nil, home: 21, away: 0,
                                       now: "2026-09-26T20:40:00+00:00"),
                           .absent, "absent (\(member ?? "no key")) must not fall back to 36.9 / 10.7")
        }
    }

    func testAMalformedObjectIsRefusedNotAbsentAndNeverFallsBack() throws {
        for member in [#""in_play""#, "29.5", "[]", "{}"] {
            let co = try odds(liveProjection: member)
            XCTAssertNotNil(co.liveProjection, "present-but-malformed stays present (decoder contract)")
            let o = try resolve(co.liveProjection, sport: "americanfootball_ncaaf",
                                start: "2026-09-26T19:30:00+00:00", isFromSchedule: nil, home: 21, away: 0,
                                now: "2026-09-26T20:40:00+00:00")
            XCTAssertNil(o.printed, "\(member) must print nothing — not the bare 37 – 11")
            XCTAssertNotEqual(o.refusal, .absent, "\(member) is refused, not mistaken for absent")
            XCTAssertNotNil(o.refusal)
        }
    }

    func testAWrongTypedFieldRefusesTheWholeObject() throws {
        // Each one field of the producer's object as the wrong JSON type.
        let cases: [(String, String, A.Refusal)] = [
            ("projected_home_score", "\"29.5\"", .pairMalformed),
            ("projected_away_score", "null", .pairMalformed),
            ("bookmaker_count", "\"2\"", .bookmakerCount),
            ("boundary_at", "1760905500", .clockUnreadable),
            ("kind", "1", .kind),
        ]
        try assertPair(try resolve(try object(Self.nflObject)), home: 30, away: 19, "positive control")
        for (key, value, why) in cases {
            assertWithheld(try resolve(try object(edited(Self.nflObject, key, value))), why, "\(key) = \(value)")
        }
    }

    // MARK: - Labels, format, count, clocks

    func testEachLabelMustBeTheProducersOwn() throws {
        let cases: [(String, String, A.Refusal)] = [
            ("kind", "\"pregame\"", .kind),
            ("kind", "\"In_Play\"", .kind),
            ("boundary", "\"scheduled_start\"", .boundary),
            ("source", "\"kalshi\"", .source),
            ("basis", "\"ladder_median\"", .basis),
            ("unit", "\"goals\"", .unit),
            ("unit", "\"runs\"", .unit),
            ("period", "\"regulation\"", .period),
            ("period", "\"first_half\"", .period),
        ]
        for (key, value, why) in cases {
            assertWithheld(try resolve(try object(edited(Self.nflObject, key, value))), why, "\(key) = \(value)")
            assertWithheld(try resolve(try object(edited(Self.nflObject, key, nil))), why, "\(key) missing")
        }
    }

    func testTheCountMustBeAWholeNumberOfSportsbooks() throws {
        try assertPair(try resolve(try object(edited(Self.nflObject, "bookmaker_count", "1"))), home: 30, away: 19,
                       "one sportsbook is enough")
        for value in ["0", "-1", "1.5", "1e300"] {
            assertWithheld(try resolve(try object(edited(Self.nflObject, "bookmaker_count", value))),
                           .bookmakerCount, "bookmaker_count \(value)")
        }
    }

    func testEveryClockMustBeReadable() throws {
        for key in ["boundary_at", "earliest_confirmed_at", "latest_captured_at"] {
            for value in ["\"\"", "\"soon\"", "\"2026-10-19\""] {
                assertWithheld(try resolve(try object(edited(Self.nflObject, key, value))),
                               .clockUnreadable, "\(key) = \(value)")
            }
            assertWithheld(try resolve(try object(edited(Self.nflObject, key, nil))), .clockUnreadable, "\(key) missing")
        }
    }

    // MARK: - Bound to THIS row's start

    func testAnObjectMeasuredFromAnEarlierStartIsRefused() throws {
        // Web R2: boundary 18:30Z, earliest 19:00Z, row 19:30Z.
        var json = try edited(Self.ugaInPlay, "boundary_at", "\"2026-09-26T18:30:00+00:00\"")
        json = try edited(json, "earliest_confirmed_at", "\"2026-09-26T19:00:00+00:00\"")
        let o = try resolve(try object(json), sport: "americanfootball_ncaaf",
                            start: "2026-09-26T19:30:00+00:00", isFromSchedule: nil, home: 21, away: 0,
                            now: "2026-09-26T20:40:00+00:00")
        assertWithheld(o, .boundaryBeforeRowStart, "pregame quotes measured from an earlier start")
    }

    func testTheSameInstantWrittenEitherWayIsTheSameStart() throws {
        for (start, boundary) in [("2026-10-19T20:25:00Z", "2026-10-19T20:25:00+00:00"),
                                  ("2026-10-19T20:25:00+00:00", "2026-10-19T20:25:00Z"),
                                  ("2026-10-19T22:25:00+02:00", "2026-10-19T20:25:00Z")] {
            let o = try resolve(try object(edited(Self.nflObject, "boundary_at", "\"\(boundary)\"")), start: start)
            try assertPair(o, home: 30, away: 19, "row \(start) vs boundary \(boundary)")
        }
        let oneSecondLater = try resolve(try object(Self.nflObject), start: "2026-10-19T20:25:01+00:00",
                                         now: Self.producerNow)
        assertWithheld(oneSecondLater, .boundaryBeforeRowStart, "a row start one second after the boundary")
    }

    func testTheRowsOwnStartMustBeReadableAndAScheduledOne() throws {
        let o = try object(Self.nflObject)
        assertWithheld(try resolve(o, start: nil), .rowStartUnreadable, "no row start")
        assertWithheld(try resolve(o, start: "soon"), .rowStartUnreadable, "an unreadable row start")
        assertWithheld(try resolve(o, isTBD: true), .rowStartPlaceholder, "a placeholder start")
        assertWithheld(try resolve(o, isFromSchedule: false), .rowStartNotFromSchedule, "a market's time")
        // Controls: an absent flag leaves the producer's check to stand.
        try assertPair(try resolve(o, isTBD: nil, isFromSchedule: nil), home: 30, away: 19, "flags absent")
        try assertPair(try resolve(o, isTBD: false, isFromSchedule: true), home: 30, away: 19, "flags affirmative")
    }

    // MARK: - Lifecycle

    func testOnlyALiveRowWhoseStartHasPassedPrints() throws {
        let o = try object(Self.nflObject)
        for status in ["scheduled", "completed", "closed", "suspended", "Live", nil] as [String?] {
            assertWithheld(try resolve(o, status: status), .notLive, "status \(status ?? "nil")")
        }
        // Web R4: live by status, start still ahead.
        assertWithheld(try resolve(o, now: "2026-10-19T20:24:59+00:00"), .notStarted, "start one second ahead")
        try assertPair(try resolve(o, now: Self.producerStart), home: 30, away: 19, "at the start exactly")
    }

    func testALiveObjectNeverBecomesAFinishedGamesForecast() throws {
        // The same valid object, the same reachable score; only the status moved.
        let o = try object(Self.nflObject)
        try assertPair(try resolve(o, home: 24, away: 17), home: 30, away: 19, "control: live")
        for status in ["completed", "closed"] {
            let settled = try resolve(o, status: status, home: 24, away: 17, now: "2026-10-20T00:00:00+00:00")
            assertWithheld(settled, .notLive, "\(status): an in-play reading is not a pregame forecast")
        }
    }

    // MARK: - Actual score and reachability

    func testTheActualScoreMustBeOnTheRow() throws {
        let o = try object(Self.nflObject)
        assertWithheld(try resolve(o, home: nil), .noActualScore, "no home score")
        assertWithheld(try resolve(o, away: nil), .noActualScore, "no away score")
        assertWithheld(try resolve(o, home: -1), .noActualScore, "a negative score")
        try assertPair(try resolve(o, home: 0, away: 0), home: 30, away: 19, "0 – 0 is a score")
    }

    func testEachRoundedHalfMustBeReachableFromTheScore() throws {
        let o = try object(Self.nflObject)
        try assertPair(try resolve(o, home: 30, away: 19), home: 30, away: 19, "equal to the score is reachable")
        assertWithheld(try resolve(o, home: 31, away: 10), .unreachable, "home already past 30")
        assertWithheld(try resolve(o, home: 14, away: 20), .unreachable, "away already past 19")
    }

    // MARK: - Team order and the pair

    func testTeamOrderIsKeyedNeverSorted() throws {
        var json = try edited(Self.nflObject, "projected_home_score", "19.0")
        json = try edited(json, "projected_away_score", "29.5")
        try assertPair(try resolve(try object(json), home: 10, away: 14), home: 19, away: 30,
                       "the underdog-home object prints home 19, away 30")
        try assertPair(try resolve(try object(Self.nflObject)), home: 30, away: 19, "and the producer's, home 30")
    }

    func testThePairMustBeAPrintableScoreline() throws {
        let cases: [(String, String, A.Refusal)] = [
            ("projected_home_score", "-0.5", .pairMalformed),
            ("projected_away_score", "-3", .pairMalformed),
            ("projected_home_score", "0", .pairNotPrintable),
            ("projected_away_score", "0.0", .pairNotPrintable),
            ("projected_home_score", "1e300", .pairNotPrintable),
        ]
        for (key, value, why) in cases {
            assertWithheld(try resolve(try object(edited(Self.nflObject, key, value)), home: 0, away: 0),
                           why, "\(key) = \(value)")
        }
    }

    func testALevelPairPrintsOnlyWhereTheSportCanEndLevel() throws {
        func level(_ h: String, _ a: String) throws -> LiveProjection {
            try object(edited(edited(Self.nflObject, "projected_home_score", h), "projected_away_score", a))
        }
        assertWithheld(try resolve(try level("110.4", "110.2"), sport: "basketball_nba", home: 90, away: 88),
                       .levelPair, "basketball cannot end 110 – 110")
        try assertPair(try resolve(try level("20.2", "19.9"), home: 17, away: 17), home: 20, away: 20,
                       "the NFL can end level")
        let soccerLevel = try object(edited(edited(Self.soccerObject, "projected_home_score", "1.2"),
                                            "projected_away_score", "1.4"))
        try assertPair(try resolve(soccerLevel, sport: "soccer_epl", home: 1, away: 1, phase: .regulation),
                       home: 1, away: 1, "a soccer draw prints")
    }

    // MARK: - Unsupported formats stay unsupported

    func testASportWhosePairIsNotAFinalScoreIsRefused() throws {
        let o = try object(Self.nflObject)
        for sport in ["icehockey_nhl", "baseball_mlb", "tennis_atp_shanghai", "mma_mixed_martial_arts",
                      "golf_masters", "rugbyleague_nrl", "", nil] as [String?] {
            assertWithheld(try resolve(o, sport: sport), .unsupportedSport, "sport \(sport ?? "nil")")
        }
        assertWithheld(try resolve(try object(Self.soccerObject), sport: "americanfootball_nfl"), .unit,
                       "a goals object on a football row")
        assertWithheld(try resolve(o, sport: "soccer_epl", phase: .regulation), .unit,
                       "a points object on a soccer row")
        try assertPair(try resolve(o, sport: "basketball_wnba", home: 14, away: 10), home: 30, away: 19,
                       "control: basketball is points over the full game")
    }

    // MARK: - Soccer phase

    func testSoccerNeedsAKnownRegulationPhase() throws {
        let o = try object(Self.soccerObject)
        func at(_ phase: A.Phase?) throws -> A.Outcome {
            try resolve(o, sport: "soccer_epl", home: 1, away: 0, phase: phase)
        }
        try assertPair(try at(.regulation), home: 2, away: 1, "control: regulation")
        assertWithheld(try at(nil), .phaseUnknown, "unknown phase")
        assertWithheld(try at(.beyondRegulation), .beyondRegulation, "extra time or a shootout")
    }

    func testAHeldRegulationObjectStopsPrintingWhenExtraTimeStarts() throws {
        // The same held object and score; only the served period moves on.
        let o = try object(Self.soccerObject)
        for period in ["90'+4'", "90+3"] {
            try assertPair(try resolve(o, sport: "soccer_epl", home: 1, away: 1, phase: A.soccerPhase(servedPeriod: period)),
                           home: 2, away: 1, "\(period) is still regulation")
        }
        for period in ["91'", "105'", "120'"] {
            assertWithheld(try resolve(o, sport: "soccer_epl", home: 1, away: 1, phase: A.soccerPhase(servedPeriod: period)),
                           .beyondRegulation, "\(period) is extra time")
        }
        for period in ["ET", "AET", "Pen.", "Penalties", "105'+1'", "FT", nil] as [String?] {
            assertWithheld(try resolve(o, sport: "soccer_epl", home: 1, away: 1, phase: A.soccerPhase(servedPeriod: period)),
                           .phaseUnknown, "\(period ?? "nil") is not known regulation")
        }
    }

    func testFullGameSportsDoNotReadThePhase() throws {
        let o = try object(Self.nflObject)
        for phase in [nil, .regulation, .beyondRegulation] as [A.Phase?] {
            try assertPair(try resolve(o, phase: phase), home: 30, away: 19, "football is full game, overtime included")
        }
    }

    func testTheSoccerPhaseReaderIsTheProducersRule() {
        // The producer's own parametrize lists (`test_live_projection_2920.py`).
        for period in ["1'", "45'", "45'+2'", "67'", "67", "90'", "90'+4'", "90+3", "HT", "Halftime",
                       "1st Half", "2nd Half"] {
            XCTAssertEqual(A.soccerPhase(servedPeriod: period), .regulation, period)
        }
        for period in [nil, "", "91'", "105'", "105'+1'", "120'", "46'+1'", "ET", "AET", "Pen.",
                       "Penalties", "FT", "Halftime ET", "End of 2nd Half", "Q3", "22:00"] as [String?] {
            XCTAssertNotEqual(A.soccerPhase(servedPeriod: period), .regulation, period ?? "nil")
        }
        // Past 90 with no stoppage mark is the producer's extra time; the rest is unknown.
        XCTAssertEqual(A.soccerPhase(servedPeriod: "91'"), .beyondRegulation)
        XCTAssertEqual(A.soccerPhase(servedPeriod: "120'"), .beyondRegulation)
        XCTAssertNil(A.soccerPhase(servedPeriod: "46'+1'"))
        XCTAssertNil(A.soccerPhase(servedPeriod: "1000'"), "four digits is not a minute")
        XCTAssertNil(A.soccerPhase(servedPeriod: "90+100"), "three stoppage digits is not a minute")
        XCTAssertEqual(A.soccerPhase(servedPeriod: "  90' + 3'  "), .regulation, "spacing as the pattern allows")
    }

    // MARK: - The raw admission alone

    func testAdmissionAloneReadsNoLifecycleScoreOrPhase() throws {
        let rowStart = A.RowStart(commenceTime: Self.producerStart)
        guard case .admitted(let pair) = A.admit(try object(Self.soccerObject), sport: "soccer_epl", rowStart: rowStart)
        else { return XCTFail("the producer's soccer object is admitted as an object") }
        XCTAssertEqual([pair.home, pair.away], [1.5, 1.0], "raw, unrounded")
        XCTAssertEqual(A.admit(nil, sport: "soccer_epl", rowStart: rowStart), .refused(.absent))
    }
}
