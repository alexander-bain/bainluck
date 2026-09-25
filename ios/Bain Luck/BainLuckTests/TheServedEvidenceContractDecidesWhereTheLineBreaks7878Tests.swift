import XCTest
@testable import Bain_Luck

/// #7878 — the phone reads the served evidence contract (`7878.v1`).
///
/// The producer (#8438, live since 2026-09-24 22:13Z) now says what every
/// `win_prob_history` point IS: a plain reading carries no `evidence` key, and
/// everything else is labelled — `observed` (proves coverage through
/// `covered_through`), `candle` / `price_history` (venue backfill), `live_edge`,
/// `terminal_row`, `final`. Codex's card-B decision fixes what a consumer does
/// with that: only plain and `observed` points prove anything, an interval wider
/// than `resolution_s` (G, 300s) is UNKNOWN and the line breaks there,
/// `valid_until` is never read, and without a contract nothing changes.
///
/// The web shipped the same reading in PR #8484 (`chartObservationSupport.ts`,
/// `classifyUnderContract`); this suite pins the phone to the same answers on
/// the same payload, so the two surfaces agree about one game.
///
/// The load-bearing controls are the ones that must NOT move: Kalshi on the real
/// specimen (no in-game interval over G) stays one line, the blend and the
/// sportsbook consensus are never classified, and a response without a contract
/// the phone can read keeps the pre-contract rule.
@MainActor
final class TheServedEvidenceContractDecidesWhereTheLineBreaks7878Tests: XCTestCase {

    // MARK: - Fixture: the real production payload

    private static var testsDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    }

    private static func fixtureData() throws -> Data {
        try Data(contentsOf: testsDir.appendingPathComponent("Fixtures")
            .appendingPathComponent("event-15318166-history-7878-contract.20260925.json"))
    }

    /// The app's own strategy (`APIClient.init`).
    private static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// Mets @ Rangers, 15318166 — finished 21:08Z on 2026-09-24, first pitch 18:35Z.
    private static func specimen() throws -> EventHistoryResponse {
        try decoder.decode(EventHistoryResponse.self, from: fixtureData())
    }

    /// The same bytes with the contract removed — what a pre-#8438 server sent.
    private static func specimenWithoutContract() throws -> EventHistoryResponse {
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: fixtureData()) as? [String: Any])
        object.removeValue(forKey: "evidence_contract")
        return try decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private static let firstPitch = "2026-09-24T18:35:00+00:00".asDate!

    private static func runs(_ source: String, in history: EventHistoryResponse) -> [Int] {
        let points = OddsChartView.chartPoints(from: history).filter { $0.source == source }
        return OddsChartView.observationSegments(points, gameStart: firstPitch).map(\.count)
    }

    // MARK: - Decode

    func testTheSpecimenDecodesItsContract() throws {
        let history = try Self.specimen()
        XCTAssertEqual(history.evidenceContract?.readableResolution, 300)
        let kalshi = try XCTUnwrap(history.winProbHistory?["kalshi"])
        XCTAssertEqual(kalshi.filter { $0.evidence?.kind == "terminal_row" }.count, 1)
        XCTAssertEqual(kalshi.filter { $0.evidence?.kind == "final" }.count, 1)
        XCTAssertEqual(kalshi.filter { $0.evidence == nil }.count, kalshi.count - 2,
                       "every other point is a plain reading — no evidence key")
    }

    // MARK: - The real specimen

    /// MLB's feed goes quiet five times in-game for 6–8 minutes (19:03, 19:11,
    /// 19:21, 19:45, 20:19 UTC). Under the contract each of those is wider than
    /// G and the line lifts there — six runs, the same breaks the web draws.
    func testMLBLiftsAtEachOfItsFiveInGameHoles() throws {
        XCTAssertEqual(Self.runs("mlb", in: try Self.specimen()), [11, 2, 3, 9, 13, 15])
    }

    /// The cadence heuristic joined all five (none is over 600s), which is the
    /// before picture: one unbroken line through five stretches nobody read.
    func testWithoutTheContractTheSameBytesDrawOneLine() throws {
        XCTAssertEqual(Self.runs("mlb", in: try Self.specimenWithoutContract()), [53])
    }

    /// THE SHORT-GAP CONTROL. Kalshi has no in-game interval over G on this
    /// game, so the contract must leave it exactly as it was: one line, every
    /// point kept, including the terminal row and the result.
    func testKalshiWithNoGapOverResolutionIsUnchanged() throws {
        let history = try Self.specimen()
        XCTAssertEqual(Self.runs("kalshi", in: history), [723])
        XCTAssertEqual(Self.runs("polymarket", in: history), [458])
        XCTAssertEqual(Self.runs("kalshi", in: try Self.specimenWithoutContract()), [723])
    }

    /// The stat model recomputes every 5–12 minutes, so under G it is mostly
    /// short runs and lone marks. Pinned so the count is a decision, not an
    /// accident; every one of its 36 points is still drawn.
    func testTheStatModelIsJudgedByTheSameResolution() throws {
        let runs = Self.runs("stat_model", in: try Self.specimen())
        XCTAssertEqual(runs, [1, 3, 3, 2, 2, 4, 2, 4, 1, 3, 2, 4, 2, 2, 1])
        XCTAssertEqual(runs.reduce(0, +), 36, "a break never drops a point")
    }

    /// The blend and the sportsbook consensus are not classified by the
    /// producer, so the contract must never reach them — the blend is the
    /// phone's default line and stays on its own rule.
    func testTheBlendIsNeverClassified() throws {
        let points = OddsChartView.chartPoints(from: try Self.specimen())
        let aggregate = points.filter { $0.source == "aggregate" }
        XCTAssertFalse(aggregate.isEmpty)
        XCTAssertTrue(aggregate.allSatisfy { $0.servedEvidence == nil })
        XCTAssertTrue(points.filter { $0.source == "kalshi" }.allSatisfy { $0.servedEvidence != nil })
    }

    func testWithoutAContractNoPointIsClassified() throws {
        let points = OddsChartView.chartPoints(from: try Self.specimenWithoutContract())
        XCTAssertTrue(points.allSatisfy { $0.servedEvidence == nil })
    }

    // MARK: - Tolerance: a bad contract degrades to "no contract", never to "no chart"

    private static func decodeSpecimen(contract: Any?, kalshiEvidence: Any? = nil) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: fixtureData()) as? [String: Any])
        object["evidence_contract"] = contract ?? NSNull()
        if let kalshiEvidence {
            var wp = try XCTUnwrap(object["win_prob_history"] as? [String: Any])
            var kalshi = try XCTUnwrap(wp["kalshi"] as? [[String: Any]])
            kalshi[0]["evidence"] = kalshiEvidence
            wp["kalshi"] = kalshi
            object["win_prob_history"] = wp
        }
        return try decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    func testAContractThisClientCannotReadKeepsThePreContractRule() throws {
        let unreadable: [Any] = [
            "7878.v1",
            ["v": "7878.v2", "resolution_s": 300],
            ["v": "7878.v1", "resolution_s": 0],
            ["v": "7878.v1", "resolution_s": -300],
            ["v": "7878.v1", "resolution_s": "300"],
            ["v": "7878.v1"],
            ["resolution_s": 300],
        ]
        for contract in unreadable {
            let history = try Self.decodeSpecimen(contract: contract)
            XCTAssertNil(history.evidenceContract?.readableResolution, "\(contract)")
            XCTAssertEqual(Self.runs("mlb", in: history), [53], "\(contract) must keep the old rule")
        }
    }

    /// An `evidence` value the phone cannot read is still drawn, extends no
    /// coverage however far its span claims to reach (fails closed), and the
    /// payload still decodes.
    func testAnUnreadableEvidenceObjectIsDrawnAndProvesNothing() throws {
        let far = "2026-09-25T06:00:00+00:00"
        let unreadable: [Any] = [
            "observed", 7, ["kind": 7, "covered_through": far], ["kind": "mystery", "covered_through": far],
            ["covered_through": far], ["kind": "observed", "covered_through": 7],
        ]
        for evidence in unreadable {
            let history = try Self.decodeSpecimen(
                contract: ["v": "7878.v1", "resolution_s": 300], kalshiEvidence: evidence)
            let wp = try XCTUnwrap(history.winProbHistory?["kalshi"]?.first)
            XCTAssertNotNil(wp.evidence, "\(evidence)")
            XCTAssertNil(OddsChartView.servedEvidence(for: wp, resolution: 300).coveredThrough, "\(evidence)")
            XCTAssertEqual(Self.runs("kalshi", in: history), [723], "\(evidence) is still drawn")
        }
    }

    // MARK: - The rule, one clause at a time

    private static let start = Date(timeIntervalSince1970: 1_758_738_900)

    private func point(
        _ offset: TimeInterval,
        _ kind: String? = nil,
        coveredThrough: TimeInterval? = nil,
        liveEdge: Bool = false
    ) -> ChartDataPoint {
        var evidence: WinProbEvidence?
        if let kind {
            evidence = WinProbEvidence(
                kind: kind,
                coveredThrough: coveredThrough.map {
                    ISO8601DateFormatter().string(from: Self.start.addingTimeInterval($0))
                })
        }
        let wp = WinProbHistoryPoint(
            timestamp: ISO8601DateFormatter().string(from: Self.start.addingTimeInterval(offset)),
            homeProbability: 0.5, gameState: nil, liveEdge: liveEdge ? true : nil, evidence: evidence)
        var p = ChartDataPoint(date: Self.start.addingTimeInterval(offset), probability: 0.5, source: "kalshi")
        p.isLiveEdge = liveEdge
        p.servedEvidence = OddsChartView.servedEvidence(for: wp, resolution: 300)
        return p
    }

    private func runs(_ points: [ChartDataPoint], gameStart: Date? = start) -> [Int] {
        OddsChartView.observationSegments(points, gameStart: gameStart).map(\.count)
    }

    func testExactlyTheResolutionStaysJoinedAndOneSecondMoreBreaks() {
        XCTAssertEqual(runs([point(0), point(300)]), [2])
        XCTAssertEqual(runs([point(0), point(301)]), [1, 1])
    }

    func testObservedCoverageExtendsTheReading() {
        XCTAssertEqual(runs([point(0, "observed", coveredThrough: 1_000), point(1_200)]), [2])
        XCTAssertEqual(runs([point(0, "observed", coveredThrough: 800), point(1_200)]), [1, 1])
    }

    /// A backwards span proves nothing beyond the reading itself — and must not
    /// pull the hole's start back before the reading either (250s after it is
    /// covered; measured from the bogus 100 it would be 650s and break).
    func testABackwardsCoverageSpanIsIgnored() {
        XCTAssertEqual(runs([point(500, "observed", coveredThrough: 100), point(750)]), [2])
        XCTAssertEqual(runs([point(500, "observed", coveredThrough: 100), point(900)]), [1, 1])
    }

    /// Backfill and the result are drawn, but cover nothing past themselves —
    /// even a `covered_through` on one is not coverage.
    func testNonEvidencePointsCoverNothing() {
        for kind in ["candle", "price_history", "terminal_row", "final", "mystery"] {
            XCTAssertEqual(runs([point(0, kind, coveredThrough: 2_000), point(900)]), [1, 1], kind)
            XCTAssertEqual(runs([point(0), point(200, kind), point(400)]), [3], "\(kind) still ends and starts intervals")
        }
    }

    /// Pre-match is never judged, and an interval straddling the start is judged
    /// from the start: 4h of pre-match silence ending 4 minutes after first
    /// pitch is joined; ending 6 minutes after, it breaks.
    func testPreMatchIsUnjudgedAndAStraddleIsJudgedFromTheStart() {
        XCTAssertEqual(runs([point(-14_400), point(-3_600)]), [2])
        XCTAssertEqual(runs([point(-14_400), point(240)]), [2])
        XCTAssertEqual(runs([point(-14_400), point(360)]), [1, 1])
    }

    func testNoStartTimeJudgesNothing() {
        XCTAssertEqual(runs([point(0), point(10_000)], gameStart: nil), [2])
    }

    /// The live edge ends the line when the reading behind it is fresh, and is
    /// dropped — never a lone mark — when it is not.
    func testTheLiveEdgeIsAnAnchorNeverAReading() {
        XCTAssertEqual(runs([point(0), point(60), point(300, liveEdge: true)]), [3])
        let stale = OddsChartView.observationSegments(
            [point(0), point(60), point(1_000, liveEdge: true)], gameStart: Self.start)
        XCTAssertEqual(stale.map(\.count), [2])
        XCTAssertFalse(stale.flatMap { $0 }.contains(where: \.isLiveEdge))
    }

    /// `live_edge` served as an evidence KIND (not the legacy flag) is the same
    /// anchor, through the real transform.
    func testALiveEdgeKindIsTheSameAnchor() throws {
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Self.fixtureData()) as? [String: Any])
        var wp = try XCTUnwrap(object["win_prob_history"] as? [String: Any])
        var mlb = try XCTUnwrap(wp["mlb"] as? [[String: Any]])
        mlb.append(["timestamp": "2026-09-24T23:59:00+00:00", "home_probability": 1.0,
                    "evidence": ["kind": "live_edge"]])
        wp["mlb"] = mlb
        object["win_prob_history"] = wp
        let history = try Self.decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
        let points = OddsChartView.chartPoints(from: history).filter { $0.source == "mlb" }
        XCTAssertEqual(points.filter(\.isLiveEdge).count, 1)
        XCTAssertEqual(Self.runs("mlb", in: history), [11, 2, 3, 9, 13, 15],
                       "an edge 2h51m after the last reading is dropped, not drawn")
    }
}
