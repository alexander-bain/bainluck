import XCTest
@testable import Bain_Luck

/// #4974 — **a finished game's chart answers a scrub only with a value the
/// server actually stored, and draws nothing across what it did not record.**
///
/// The server (`GET /api/events/{id}/publications`, PR #10489) serves one vertex
/// per recorded row and nothing between. Nothing proves two rows were adjacent
/// (a status-only commit can move the price without moving `rev`), so the app
/// must not connect them, hold one forward, or let the old history line bridge
/// the recorded window. These tests pin the decoder and the pure adoption /
/// hit / segment rules the chart will be wired to.
final class PublicationJourney4974Tests: XCTestCase {

    private typealias Journey4974 = PublicationJourney4974
    private typealias Refusal = PublicationJourney4974.Refusal

    // Independently computed epochs (Python `datetime.timestamp()`, UTC).
    private let t201300 = Date(timeIntervalSince1970: 1_791_144_780)
    private let t201400 = Date(timeIntervalSince1970: 1_791_144_840)
    private let t201500 = Date(timeIntervalSince1970: 1_791_144_900)
    private let t201510 = Date(timeIntervalSince1970: 1_791_144_910)
    private let t201530 = Date(timeIntervalSince1970: 1_791_144_930)
    private let t201550 = Date(timeIntervalSince1970: 1_791_144_950)
    private let t201600 = Date(timeIntervalSince1970: 1_791_144_960)
    private let t201700 = Date(timeIntervalSince1970: 1_791_145_020)

    private let eventID = 15_321_333

    // MARK: - Fixtures

    private func vertex(_ rev: Int64, _ t: String, _ p: Double) -> PublicationCheckpointVertex {
        PublicationCheckpointVertex(rev: rev, t: t, p: p)
    }

    private var twoGood: [PublicationCheckpointVertex] {
        [vertex(7, "2026-10-04T20:15:10+00:00", 0.61), vertex(9, "2026-10-04T20:15:50+00:00", 0.58)]
    }

    private func response(
        eventId: Int? = nil,
        schemaVersion: Int = 1,
        timeBasis: String = "recorded_at_insert_before_commit",
        truncated: Bool = false,
        vertices: [PublicationCheckpointVertex]? = nil
    ) -> PublicationCheckpointsResponse {
        PublicationCheckpointsResponse(
            eventId: eventId ?? eventID,
            schemaVersion: schemaVersion,
            timeBasis: timeBasis,
            truncated: truncated,
            vertices: vertices ?? twoGood
        )
    }

    private func refusal(
        _ response: PublicationCheckpointsResponse,
        expected: Int? = nil,
        finished: Bool = true
    ) -> Refusal? {
        if case .failure(let refusal) = Journey4974.adopt(
            response, expectedEventID: expected ?? eventID, finished: finished) {
            return refusal
        }
        return nil
    }

    private func adopted(
        _ response: PublicationCheckpointsResponse,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> PublicationJourney4974.Journey {
        switch Journey4974.adopt(response, expectedEventID: eventID, finished: true) {
        case .success(let journey):
            return journey
        case .failure(let refusal):
            XCTFail("expected adoption, got \(refusal)", file: file, line: line)
            throw refusal
        }
    }

    /// Positions keyed by revision, the way a chart proxy would give them.
    private func positions(_ byRev: [Int64: Double]) -> (PublicationJourney4974.Checkpoint) -> Double? {
        { byRev[$0.vertex.rev] }
    }

    private func apiDecoder() -> JSONDecoder {
        // The strategy `APIClient.init` configures.
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    // MARK: - Decoding the server's exact body

    /// The body `publications_body` serves, byte for byte in shape: five keys,
    /// three per vertex, a six-digit fraction and a no-fraction stamp, and a
    /// revision past Int32.
    private let serverBody = """
    {"event_id": 15321333, "schema_version": 1, "time_basis": "recorded_at_insert_before_commit", \
    "truncated": false, "vertices": [\
    {"rev": 4294967296, "t": "2026-10-04T20:15:10.123456+00:00", "p": 0.6123456789}, \
    {"rev": 4294967301, "t": "2026-10-04T20:15:50+00:00", "p": 0.58}]}
    """

    func testTheServersExactBodyDecodesWithTheAPIClientsStrategy() throws {
        let decoded = try apiDecoder().decode(
            PublicationCheckpointsResponse.self, from: Data(serverBody.utf8))
        XCTAssertEqual(decoded.eventId, 15_321_333)
        XCTAssertEqual(decoded.schemaVersion, 1)
        XCTAssertEqual(decoded.timeBasis, "recorded_at_insert_before_commit")
        XCTAssertFalse(decoded.truncated)
        XCTAssertEqual(decoded.vertices.map(\.rev), [4_294_967_296, 4_294_967_301])
        XCTAssertEqual(decoded.vertices.map(\.t),
                       ["2026-10-04T20:15:10.123456+00:00", "2026-10-04T20:15:50+00:00"])
        XCTAssertEqual(decoded.vertices[0].p.bitPattern, (0.6123456789).bitPattern)
        XCTAssertEqual(decoded.vertices[1].p.bitPattern, (0.58).bitPattern)
    }

    /// Control: the snake-case keys only map through the API's strategy. A
    /// plain decoder cannot find `eventId`, so the test above is testing the
    /// mapping and not a lucky key spelling.
    func testTheBodyDoesNotDecodeWithoutTheSnakeCaseStrategy() {
        XCTAssertThrowsError(try JSONDecoder().decode(
            PublicationCheckpointsResponse.self, from: Data(serverBody.utf8)))
    }

    func testTheEmptyRecordingOffBodyDecodesAndIsRefusedForTooFewVertices() throws {
        let body = """
        {"event_id": 15321333, "schema_version": 1, "time_basis": "recorded_at_insert_before_commit", \
        "truncated": false, "vertices": []}
        """
        let decoded = try apiDecoder().decode(PublicationCheckpointsResponse.self, from: Data(body.utf8))
        XCTAssertEqual(refusal(decoded), .vertexCount(0))
    }

    // MARK: - Adoption keeps every raw value

    func testAdoptionPreservesRevTAndPRawAndInServerOrder() throws {
        let decoded = try apiDecoder().decode(
            PublicationCheckpointsResponse.self, from: Data(serverBody.utf8))
        let journey = try adopted(decoded)
        XCTAssertEqual(journey.eventId, 15_321_333)
        XCTAssertEqual(journey.checkpoints.map(\.vertex), decoded.vertices)
        XCTAssertEqual(journey.checkpoints[0].vertex.t, "2026-10-04T20:15:10.123456+00:00")
        XCTAssertEqual(journey.checkpoints[0].vertex.p.bitPattern, (0.6123456789).bitPattern)
        XCTAssertEqual(journey.checkpoints[0].vertex.rev, 4_294_967_296)
        XCTAssertEqual(journey.checkpoints[0].date.timeIntervalSince1970,
                       t201510.timeIntervalSince1970 + 0.123, accuracy: 0.0005)
        XCTAssertEqual(journey.checkpoints[1].date, t201550)
    }

    func testProbabilityBoundsZeroAndOneAreAdoptedUnchanged() throws {
        let journey = try adopted(response(vertices: [
            vertex(1, "2026-10-04T20:15:10Z", 0), vertex(2, "2026-10-04T20:15:50Z", 1),
        ]))
        XCTAssertEqual(journey.checkpoints.map(\.vertex.p), [0, 1])
        XCTAssertEqual(journey.checkpoints[0].date, t201510)
    }

    // MARK: - Window is min(t)...max(t), not first/last rev

    func testNonMonotonicTimestampsSetTheWindowByClockAndKeepSourceOrder() throws {
        // Insert stamps are taken before commit: rev order 1, 2, 3 is clock
        // order :30, :10, :50. First/last rev would give :30...:50.
        let journey = try adopted(response(vertices: [
            vertex(1, "2026-10-04T20:15:30+00:00", 0.50),
            vertex(2, "2026-10-04T20:15:10+00:00", 0.55),
            vertex(3, "2026-10-04T20:15:50+00:00", 0.60),
        ]))
        XCTAssertEqual(journey.window, t201510...t201550)
        XCTAssertEqual(journey.checkpoints.map(\.vertex.rev), [1, 2, 3])
        XCTAssertEqual(journey.checkpoints.map(\.date), [t201530, t201510, t201550])
    }

    func testEqualTimestampsAreBothKeptNotMerged() throws {
        let journey = try adopted(response(vertices: [
            vertex(4, "2026-10-04T20:15:10+00:00", 0.40),
            vertex(5, "2026-10-04T20:15:10+00:00", 0.70),
        ]))
        XCTAssertEqual(journey.checkpoints.map(\.vertex.p), [0.40, 0.70])
        XCTAssertEqual(journey.window, t201510...t201510)
    }

    // MARK: - Refusals (each alone, against an adoptable base)

    func testTheBaseFixtureIsAdoptable() throws {
        XCTAssertNil(refusal(response()))
        let journey = try adopted(response())
        XCTAssertEqual(journey.window, t201510...t201550)
    }

    func testFinishedAdoptsAndLiveRefusesTheSameBody() {
        XCTAssertNil(refusal(response(), finished: true))
        XCTAssertEqual(refusal(response(), finished: false), .unfinished)
    }

    func testAnotherEventsBodyIsRefusedEvenWhenFinished() {
        XCTAssertEqual(refusal(response(eventId: 15_321_334), expected: eventID, finished: true),
                       .wrongEvent(expected: eventID, served: 15_321_334))
        XCTAssertNil(refusal(response(eventId: 15_321_334), expected: 15_321_334, finished: true))
    }

    func testOnlySchemaVersionOneIsAdopted() {
        XCTAssertEqual(refusal(response(schemaVersion: 2)), .schemaVersion(2))
        XCTAssertEqual(refusal(response(schemaVersion: 0)), .schemaVersion(0))
    }

    func testOnlyTheRecordedAtTimeBasisIsAdopted() {
        XCTAssertEqual(refusal(response(timeBasis: "published_at")), .timeBasis("published_at"))
        XCTAssertEqual(refusal(response(timeBasis: "")), .timeBasis(""))
    }

    func testATruncatedBodyIsRefusedEvenWithVertices() {
        XCTAssertEqual(refusal(response(truncated: true)), .truncated)
        XCTAssertEqual(refusal(response(truncated: true, vertices: [])), .truncated)
    }

    private func vertices(count: Int) -> [PublicationCheckpointVertex] {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return (0..<count).map { i in
            let stamp = formatter.string(from: t201500.addingTimeInterval(Double(i)))
            return vertex(Int64(i + 1), stamp, 0.5)
        }
    }

    func testVertexCountMustBeTwoThroughFiveThousand() {
        XCTAssertEqual(refusal(response(vertices: [])), .vertexCount(0))
        XCTAssertEqual(refusal(response(vertices: vertices(count: 1))), .vertexCount(1))
        XCTAssertNil(refusal(response(vertices: vertices(count: 2))))
        XCTAssertNil(refusal(response(vertices: vertices(count: 5000))))
        XCTAssertEqual(refusal(response(vertices: vertices(count: 5001))), .vertexCount(5001))
    }

    func testANegativeRevisionRefusesTheWholeBody() {
        XCTAssertEqual(refusal(response(vertices: [
            vertex(-1, "2026-10-04T20:15:10Z", 0.5), vertex(2, "2026-10-04T20:15:50Z", 0.5),
        ])), .invalidRevision(index: 0))
        // Control: revision zero is valid.
        XCTAssertNil(refusal(response(vertices: [
            vertex(0, "2026-10-04T20:15:10Z", 0.5), vertex(2, "2026-10-04T20:15:50Z", 0.5),
        ])))
    }

    func testADuplicateOrDecreasingRevisionRefusesRatherThanReordering() {
        XCTAssertEqual(refusal(response(vertices: [
            vertex(5, "2026-10-04T20:15:10Z", 0.5), vertex(5, "2026-10-04T20:15:50Z", 0.6),
        ])), .nonIncreasingRevision(index: 1))
        XCTAssertEqual(refusal(response(vertices: [
            vertex(1, "2026-10-04T20:15:10Z", 0.5), vertex(3, "2026-10-04T20:15:30Z", 0.6),
            vertex(2, "2026-10-04T20:15:50Z", 0.7),
        ])), .nonIncreasingRevision(index: 2))
    }

    func testAMalformedTimestampRefusesTheWholeBodyNotJustItsRow() {
        // No zone, a non-UTC offset, and garbage that carries a UTC suffix.
        for bad in ["", "Z", "garbage", "not-a-date+00:00", "2026-10-04T20:15:30",
                    "2026-10-04T20:15:30-07:00", "2026-10-04T20:15:30+05:30"] {
            XCTAssertEqual(refusal(response(vertices: [
                vertex(1, "2026-10-04T20:15:10+00:00", 0.5), vertex(2, bad, 0.5),
                vertex(3, "2026-10-04T20:15:50+00:00", 0.5),
            ])), .malformedTimestamp(index: 1), "accepted \(bad)")
        }
    }

    func testUTCStampsWithAndWithoutAFractionAreAccepted() {
        for good in ["2026-10-04T20:15:30+00:00", "2026-10-04T20:15:30.5+00:00",
                     "2026-10-04T20:15:30.123456+00:00", "2026-10-04T20:15:30Z",
                     "2026-10-04T20:15:30.250Z"] {
            XCTAssertNotNil(Journey4974.date(ofStamp: good), "refused \(good)")
        }
        XCTAssertEqual(Journey4974.date(ofStamp: "2026-10-04T20:15:30+00:00"), t201530)
        XCTAssertEqual(Journey4974.date(ofStamp: "2026-10-04T20:15:30Z"), t201530)
    }

    func testANonFiniteOrOutOfRangeProbabilityRefusesTheWholeBody() {
        for bad in [Double.nan, Double.infinity, -Double.infinity, -0.0001, 1.0001, 61] {
            XCTAssertEqual(refusal(response(vertices: [
                vertex(1, "2026-10-04T20:15:10Z", 0.5), vertex(2, "2026-10-04T20:15:50Z", bad),
            ])), .invalidProbability(index: 1), "accepted \(bad)")
        }
    }

    // MARK: - Hit testing answers only with a stored vertex

    func testTheNearestVertexWinsAndAnswersWithItsOwnXAndDate() throws {
        let journey = try adopted(response())
        let hit = try XCTUnwrap(journey.hit(cursorX: 103, position: positions([7: 100, 9: 140])))
        XCTAssertEqual(hit.checkpoint.vertex, twoGood[0])
        XCTAssertEqual(hit.x, 100)
        XCTAssertEqual(hit.checkpoint.date, t201510)
        // Nearest beats a greater revision.
        let other = try XCTUnwrap(journey.hit(cursorX: 104, position: positions([7: 100, 9: 109])))
        XCTAssertEqual(other.checkpoint.vertex.rev, 7)
    }

    func testAnEquidistantTieGoesToTheGreatestRevisionOnEitherSide() throws {
        let journey = try adopted(response())
        let left = try XCTUnwrap(journey.hit(cursorX: 100, position: positions([7: 103, 9: 97])))
        XCTAssertEqual(left.checkpoint.vertex.rev, 9)
        XCTAssertEqual(left.x, 97)
        let right = try XCTUnwrap(journey.hit(cursorX: 100, position: positions([7: 97, 9: 103])))
        XCTAssertEqual(right.checkpoint.vertex.rev, 9)
        XCTAssertEqual(right.x, 103)
    }

    func testEqualTimestampsResolveToTheGreatestRevisionNotTheAverage() throws {
        let journey = try adopted(response(vertices: [
            vertex(4, "2026-10-04T20:15:10+00:00", 0.40),
            vertex(5, "2026-10-04T20:15:10+00:00", 0.70),
            vertex(6, "2026-10-04T20:15:50+00:00", 0.10),
        ]))
        let hit = try XCTUnwrap(journey.hit(cursorX: 101, position: positions([4: 100, 5: 100, 6: 200])))
        XCTAssertEqual(hit.checkpoint.vertex.rev, 5)
        XCTAssertEqual(hit.checkpoint.vertex.p, 0.70)
    }

    func testExactlyEightPointsHitsAndJustBeyondDoesNot() throws {
        let journey = try adopted(response())
        XCTAssertEqual(journey.hit(cursorX: 0, position: positions([7: 8, 9: 500]))?.x, 8)
        XCTAssertEqual(journey.hit(cursorX: 0, position: positions([7: -8, 9: 500]))?.x, -8)
        XCTAssertNil(journey.hit(cursorX: 0, position: positions([7: (8.0).nextUp, 9: 500])))
        XCTAssertNil(journey.hit(cursorX: 0, position: positions([7: -(8.0).nextUp, 9: 500])))
    }

    func testTheGapBetweenVerticesAnswersNothingNoHeldValue() throws {
        let journey = try adopted(response())
        let at = positions([7: 0, 9: 100])
        XCTAssertNil(journey.hit(cursorX: 50, position: at))
        XCTAssertNil(journey.hit(cursorX: 9, position: at))
        XCTAssertNil(journey.hit(cursorX: 91, position: at))
        XCTAssertEqual(journey.hit(cursorX: 92, position: at)?.checkpoint.vertex.rev, 9)
        // Past the last vertex is a gap too, not the last value held forward.
        XCTAssertNil(journey.hit(cursorX: 150, position: at))
    }

    func testANonFiniteCursorRefuses() throws {
        let journey = try adopted(response())
        let at = positions([7: 100, 9: 140])
        XCTAssertNotNil(journey.hit(cursorX: 100, position: at))
        XCTAssertNil(journey.hit(cursorX: .nan, position: at))
        XCTAssertNil(journey.hit(cursorX: .infinity, position: at))
        XCTAssertNil(journey.hit(cursorX: -Double.infinity, position: at))
    }

    func testOneBadCoordinateRefusesTheScrubEvenBesideAGoodHit() throws {
        let journey = try adopted(response())
        // rev 7 sits right under the cursor; rev 9's coordinate is unusable.
        XCTAssertNil(journey.hit(cursorX: 100, position: positions([7: 100, 9: .nan])))
        XCTAssertNil(journey.hit(cursorX: 100, position: positions([7: 100, 9: .infinity])))
        XCTAssertNil(journey.hit(cursorX: 100, position: positions([7: 100])))
    }

    func testACoordinateDistanceThatOverflowsRefuses() throws {
        let journey = try adopted(response())
        let huge = Double.greatestFiniteMagnitude
        // Both finite; their difference is not.
        XCTAssertNil(journey.hit(cursorX: huge, position: positions([7: -huge, 9: huge])))
        // Control: the same cursor with no overflowing pair hits.
        XCTAssertEqual(journey.hit(cursorX: huge, position: positions([7: huge, 9: huge]))?.checkpoint.vertex.rev, 9)
    }

    // MARK: - Window membership and legacy segments

    func testWindowMembershipIsClosed() throws {
        let journey = try adopted(response())
        XCTAssertTrue(journey.contains(t201510))
        XCTAssertTrue(journey.contains(t201530))
        XCTAssertTrue(journey.contains(t201550))
        XCTAssertFalse(journey.contains(t201510.addingTimeInterval(-0.001)))
        XCTAssertFalse(journey.contains(t201550.addingTimeInterval(0.001)))
    }

    func testASameMinuteLegacySegmentAroundTheWindowBreaks() throws {
        // Checkpoints 20:15:10...20:15:50, legacy minutes 20:15 and 20:16.
        let journey = try adopted(response())
        XCTAssertFalse(journey.permitsLegacySegment(from: t201500, to: t201600))
        XCTAssertFalse(journey.permitsLegacySegment(from: t201600, to: t201500))
    }

    func testSegmentsTouchingOrInsideTheWindowBreak() throws {
        let journey = try adopted(response())
        XCTAssertFalse(journey.permitsLegacySegment(from: t201500, to: t201510))
        XCTAssertFalse(journey.permitsLegacySegment(from: t201550, to: t201600))
        XCTAssertFalse(journey.permitsLegacySegment(from: t201510, to: t201530))
    }

    func testSegmentsWhollyOutsideTheWindowAreKept() throws {
        let journey = try adopted(response())
        XCTAssertTrue(journey.permitsLegacySegment(from: t201400, to: t201500))
        XCTAssertTrue(journey.permitsLegacySegment(from: t201510.addingTimeInterval(-0.001), to: t201400))
        XCTAssertTrue(journey.permitsLegacySegment(from: t201600, to: t201700))
    }

    private struct LegacyPoint: Equatable {
        let date: Date
        let value: Double
    }

    func testLegacyRunsCutOnlyTheBridgingSegmentAndKeepEveryPointAsIs() throws {
        let journey = try adopted(response())
        let legacy = [
            LegacyPoint(date: t201300, value: 0.40), LegacyPoint(date: t201400, value: 0.41),
            LegacyPoint(date: t201500, value: 0.42), LegacyPoint(date: t201600, value: 0.47),
            LegacyPoint(date: t201700, value: 0.48),
        ]
        let runs = journey.legacyRuns(legacy) { $0.date }
        XCTAssertEqual(runs, [Array(legacy[0...2]), Array(legacy[3...4])])
        // Nothing manufactured at the edges, nothing dropped, nothing re-valued.
        XCTAssertEqual(runs.flatMap { $0 }, legacy)
    }

    func testALegacyPointInsideTheWindowStandsAlone() throws {
        let journey = try adopted(response())
        let legacy = [
            LegacyPoint(date: t201500, value: 0.42), LegacyPoint(date: t201530, value: 0.44),
            LegacyPoint(date: t201600, value: 0.47),
        ]
        let runs = journey.legacyRuns(legacy) { $0.date }
        XCTAssertEqual(runs, [[legacy[0]], [legacy[1]], [legacy[2]]])
    }

    func testLegacyRunsLeaveAnUntouchedSeriesWhole() throws {
        let journey = try adopted(response())
        let legacy = [
            LegacyPoint(date: t201300, value: 0.40), LegacyPoint(date: t201400, value: 0.41),
            LegacyPoint(date: t201500, value: 0.42),
        ]
        XCTAssertEqual(journey.legacyRuns(legacy) { $0.date }, [legacy])
        XCTAssertEqual(journey.legacyRuns([LegacyPoint]()) { $0.date }, [])
    }
}
