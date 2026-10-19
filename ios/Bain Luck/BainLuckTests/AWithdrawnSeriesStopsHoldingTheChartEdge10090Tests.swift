import XCTest
@testable import Bain_Luck

/// #10090 §3 (Root admission 1341Z, after lane1b's reviews of d5c76b127d and
/// fa4489b5f2). The chart takes a payload only if its live edge is not behind
/// the drawn one (#920). When the withdrawn source's series held the drawn
/// payload's latest reading, every later payload sat behind that edge. The
/// chart then drew the withdrawn line until another series passed its last
/// stamp, which on a sparse pre-match chart may never happen. Meanwhile the
/// reconcile floor stayed owed against a payload the reader could not be
/// shown.
///
/// The deciding case: Kalshi and Polymarket at 17:00, Polymarket alone again
/// at 17:02, then Polymarket withdrawn. The complete fresh build after the
/// withdrawal holds Kalshi at 17:00 and nothing else. A single source makes no
/// Bain Luck line, so nothing it retains has moved. Its edge, 17:00, is behind
/// 17:02.
///
/// `EventHistoryFreshness.adoptsSourceRemoval` takes such a payload only when
/// it is provably not older. Every refusal below is a way an older or
/// unproven payload could otherwise get in.
@MainActor
final class AWithdrawnSeriesStopsHoldingTheChartEdge10090Tests: XCTestCase {
    private static func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// `aggregate` / `series` are raw JSON array / object bodies. `read` is the
    /// raw `history_fold_revision` (`nil` leaves the key out).
    static func payload(aggregate: String = "", series: String, read: String? = nil,
                        pinned: Bool = false, eventId: Int = 4242) throws -> EventHistoryResponse {
        let vector = read.map { #""history_fold_revision":\#($0),"# } ?? ""
        let pin = pinned
            ? #""blend_edge_pinned":true,"blend_edge_fold_revision":{"4242":11},"#
            : #""blend_edge_pinned":false,"blend_edge_fold_revision":null,"#
        return try decode("""
        {"event_id":\(eventId),"home_team":"Home","away_team":"Away","status":"scheduled","history":[],\(pin)\(vector)
         "win_prob_history":{\(series)},"aggregate_line":[\(aggregate)]}
        """)
    }

    static func point(_ at: String, _ p: Double = 0.5) -> String {
        #"{"timestamp":"2026-09-27T\#(at)Z","home_probability":\#(p)}"#
    }

    /// Drawn before the withdrawal: the blend and both venues at 17:00, then
    /// Polymarket alone at 17:02. Polymarket holds the latest reading.
    static func drawn(read: String? = nil) throws -> EventHistoryResponse {
        try payload(aggregate: point("17:00:00", 0.66),
                    series: #""kalshi":[\#(point("17:00:00"))],"polymarket":[\#(point("17:00:00", 0.82)),\#(point("17:02:00", 0.84))]"#,
                    read: read)
    }

    /// The complete fresh build after the withdrawal: Kalshi alone, unmoved.
    static func kalshiAlone(at: String = "17:00:00", read: String? = #"{"4242":11}"#,
                            pinned: Bool = false, eventId: Int = 4242) throws -> EventHistoryResponse {
        try payload(series: #""kalshi":[\#(point(at))]"#, read: read, pinned: pinned, eventId: eventId)
    }

    private func adopts(_ fresh: EventHistoryResponse, over held: EventHistoryResponse) -> Bool {
        EventHistoryFreshness.shouldAdopt(fresh, over: held)
    }

    // MARK: - The deciding cases

    func testACompleteBuildThatDropsTheSeriesHoldingTheEdgeIsTaken() throws {
        let held = try Self.drawn(), fresh = try Self.kalshiAlone()
        let heldEdge = try XCTUnwrap(EventHistoryFreshness.lastReading(in: held))
        let freshEdge = try XCTUnwrap(EventHistoryFreshness.lastReading(in: fresh))
        XCTAssertLessThan(freshEdge, heldEdge, "the fresh build sits behind the withdrawn series' stamp")
        XCTAssertFalse(EventHistoryFreshness.shouldAdopt(freshEdge: freshEdge, over: .some(heldEdge)),
                       "so #920's edge rule alone refuses it, for as long as Kalshi does not pass 17:02")
        XCTAssertTrue(adopts(fresh, over: held), "a complete build that retains Kalshi unmoved is taken")
    }

    func testABlendThatMovedOnWithoutTheWithdrawnSeriesIsTaken() throws {
        let held = try Self.payload(
            aggregate: Self.point("17:00:00", 0.66),
            series: #""kalshi":[\#(Self.point("17:00:00"))],"espn":[\#(Self.point("17:00:00", 0.6))],"polymarket":[\#(Self.point("17:02:00", 0.84))]"#)
        let fresh = try Self.payload(
            aggregate: "\(Self.point("17:00:00", 0.66)),\(Self.point("17:01:00", 0.55))",
            series: #""kalshi":[\#(Self.point("17:00:00"))],"espn":[\#(Self.point("17:00:00", 0.6))]"#,
            read: #"{"4242":11}"#)
        XCTAssertFalse(EventHistoryFreshness.shouldAdopt(
            freshEdge: EventHistoryFreshness.lastReading(in: fresh), over: .some(EventHistoryFreshness.lastReading(in: held))))
        XCTAssertTrue(adopts(fresh, over: held))
    }

    /// The real chart model, not only the rule.
    func testTheChartTakesItAndStopsDrawingTheWithdrawnLine() throws {
        let chart = OddsChartViewModel(eventId: 4242, preloaded: try Self.drawn())
        XCTAssertNotNil(chart.history?.winProbHistory?["polymarket"])
        XCTAssertTrue(chart.adopt(try Self.kalshiAlone()))
        XCTAssertNil(chart.history?.winProbHistory?["polymarket"], "the withdrawn line is gone from the chart")
        XCTAssertEqual(chart.history?.winProbHistory?["kalshi"]?.count, 1)

        let older = OddsChartViewModel(eventId: 4242, preloaded: try Self.drawn())
        XCTAssertFalse(older.adopt(try Self.kalshiAlone(at: "16:59:00")))
        XCTAssertNotNil(older.history?.winProbHistory?["polymarket"], "a refused payload changes nothing")
    }

    // MARK: - Refusals: older or unproven payloads

    func testAnOlderRetainedSeriesIsRefused() throws {
        XCTAssertFalse(adopts(try Self.kalshiAlone(at: "16:59:00"), over: try Self.drawn()),
                       "a build from before Kalshi's 17:00 reading is older, whatever it lacks")
        let aggregateBehind = try Self.payload(aggregate: Self.point("16:59:00", 0.66),
                                               series: #""kalshi":[\#(Self.point("17:00:00"))]"#, read: #"{"4242":11}"#)
        XCTAssertFalse(adopts(aggregateBehind, over: try Self.drawn()),
                       "one retained series behind is enough: no drawn endpoint steps back")
        let aggregateOnly = try Self.payload(aggregate: Self.point("16:59:30", 0.66), series: "", read: #"{"4242":11}"#)
        XCTAssertFalse(adopts(aggregateOnly, over: try Self.drawn()), "an older aggregate-only payload")
    }

    func testOnlyACompleteBuildsMissingSeriesCounts() throws {
        XCTAssertFalse(adopts(try Self.kalshiAlone(read: nil), over: try Self.drawn()),
                       "a cacheable or partial build makes no membership claim")
        for malformed in ["null", #""x""#, "{}", #"{"4242":-1}"#, #"{"4242":1.5}"#] {
            XCTAssertFalse(adopts(try Self.kalshiAlone(read: malformed), over: try Self.drawn()),
                           "a malformed vector \(malformed) is no claim")
        }
    }

    func testAPinnedOrOtherEventPayloadIsNeverRescued() throws {
        let pinned = try Self.payload(aggregate: Self.point("17:00:00", 0.5),
                                      series: #""kalshi":[\#(Self.point("17:00:00"))]"#, read: #"{"4242":11}"#, pinned: true)
        XCTAssertFalse(adopts(pinned, over: try Self.drawn()), "a pinned edge is a claim about now")
        XCTAssertFalse(adopts(try Self.kalshiAlone(eventId: 4243), over: try Self.drawn()))
    }

    func testANothingRetainedOrNothingDroppedPayloadKeepsTheEdgeRule() throws {
        let espnOnly = try Self.payload(series: #""espn":[\#(Self.point("17:00:00"))]"#, read: #"{"4242":11}"#)
        XCTAssertFalse(adopts(espnOnly, over: try Self.drawn()), "nothing in common proves no order")
        let sameSeriesBehind = try Self.payload(
            aggregate: Self.point("17:00:00", 0.66),
            series: #""kalshi":[\#(Self.point("17:00:00"))],"polymarket":[\#(Self.point("17:01:00", 0.83))]"#,
            read: #"{"4242":11}"#)
        XCTAssertFalse(adopts(sameSeriesBehind, over: try Self.drawn()), "nothing dropped: #920 alone decides")
    }

    func testWhenBothCarryAReadOrderTheFreshOneMustBeLater() throws {
        let held = try Self.drawn(read: #"{"4242":11}"#)
        XCTAssertFalse(adopts(try Self.kalshiAlone(read: #"{"4242":11}"#), over: held), "the same read order")
        XCTAssertFalse(adopts(try Self.kalshiAlone(read: #"{"4242":10}"#), over: held), "an earlier one")
        XCTAssertFalse(adopts(try Self.kalshiAlone(read: #"{"77":12}"#), over: held), "no row in common")
        XCTAssertFalse(adopts(try Self.kalshiAlone(read: #"{"4242":12,"77":1}"#), over: try Self.drawn(read: #"{"4242":11,"77":2}"#)),
                       "later on one row, earlier on another")
        XCTAssertTrue(adopts(try Self.kalshiAlone(read: #"{"4242":12}"#), over: held))
    }

    // MARK: - The page's mirror reads the same rule

    func testTheDigestCarriesTheSameEdges() throws {
        let held = try Self.drawn()
        XCTAssertEqual(EventHistoryDigest(held).edges, EventHistoryEdges(held))
        XCTAssertEqual(EventHistoryDigest(held).edge, EventHistoryFreshness.lastReading(in: held))
        XCTAssertEqual(Set(EventHistoryEdges(held).series.keys), ["aggregate", "wp:kalshi", "wp:polymarket"])
    }
}
