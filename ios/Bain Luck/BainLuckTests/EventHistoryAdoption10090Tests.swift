import XCTest
import Combine
@testable import Bain_Luck

/// #10090 / #8651 — the chart keeps the points it already built when it is
/// handed the SAME history again, and rebuilds for every real correction.
///
/// The page and the chart receive one `/history` response: the chart writes it,
/// then the page's `adopt` hands it over a second time. Before #10090 every
/// write to `OddsChartViewModel.history` bumped the memo generation, so the
/// second, identical write threw away the chart points and the game-state
/// enrichment that payload had just paid for. Now the bump needs
/// `oldValue != history`, over a SYNTHESIZED `Equatable` that reads every
/// stored field.
///
/// Two directions, and both are the point:
///   * an equal payload — decoded separately, sources in another key order,
///     written directly or adopted — keeps the point ids and the enrichment
///     count. `ChartDataPoint.id` is a fresh `UUID` per build, so a rebuild
///     cannot fake this. The unconditional bump (the pre-#10090 source) fails
///     every test in "Equal payloads keep the memo".
///   * a payload that differs ANYWHERE at the same live edge — interior price,
///     score, clock, attribution, evidence, marker provenance, play text,
///     moment, aggregate away side, pin and its revision, nil vs empty, array
///     order — rebuilds. Equality on the edge, a count, a revision or a hash
///     fails "Changes at the same edge rebuild".
///
/// `adopt` is unchanged: its freshness fence, its `true`, and its clearing of
/// `loading` / `error` on an accepted payload all hold for an equal one.
@MainActor
final class EventHistoryAdoption10090Tests: XCTestCase {

    // MARK: - Fixture: one live payload with every field populated

    /// The two win-probability sources, as separate strings so the fixture can
    /// list them in either key order (dictionary order must not matter).
    private static let espnSeries = """
    "espn": [{"timestamp": "2026-09-21T12:02:00Z", "home_probability": 0.47, "game_state": {"period": "Q1", "clock": "10:01", "inning": null, "home_score": 0, "away_score": 0}}, {"timestamp": "2026-09-21T12:06:00Z", "home_probability": 0.53, "evidence": {"kind": "observed", "covered_through": "2026-09-21T12:06:30Z"}}]
    """
    private static let kalshiSeries = """
    "kalshi": [{"timestamp": "2026-09-21T12:07:00Z", "home_probability": 0.55, "live_edge": true}]
    """
    private static let espnSource = """
    "espn": {"display_name": "ESPN", "type": "model", "color": "#D00000", "dash_pattern": "4,2", "methodology": "ESPN win probability model", "attribution": "ESPN Analytics"}
    """
    private static let kalshiSource = """
    "kalshi": {"display_name": "Kalshi", "type": "market"}
    """
    /// The two moments, separate so a test can reorder or remove the array.
    private static let touchdownMoment = """
    {"ts": "2026-09-21T12:03:00Z", "label": "Touchdown swings it", "confidence": 0.8, "moment_type": "score", "actor_team": "H", "prob_delta": 0.12, "period": "Q1"}
    """
    private static let pickMoment = """
    {"ts": "2026-09-21T12:06:00Z", "label": "Pick", "confidence": 0.7, "moment_type": "turnover", "actor_team": "A", "prob_delta": -0.05, "period": "Q1"}
    """

    /// Live edge 12:10 (the aggregate line's last point). Every mutation below
    /// leaves that edge where it is, and `assertSameEdge` proves it each time.
    private static func fixture(sourcesReversed: Bool = false) -> String {
        let winProb = sourcesReversed ? "\(espnSeries), \(kalshiSeries)" : "\(kalshiSeries), \(espnSeries)"
        let sources = sourcesReversed ? "\(espnSource), \(kalshiSource)" : "\(kalshiSource), \(espnSource)"
        return """
        {
          "event_id": 1, "home_team": "H", "away_team": "A", "completed_at": null, "status": "live",
          "history": [
            {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.40, "away_probability": 0.60, "bookmaker_count": 7, "projected_home_score": 24.5, "projected_away_score": 21.5},
            {"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.44, "away_probability": 0.56, "bookmaker_count": 7}
          ],
          "bookmaker_history": {"draftkings": [{"timestamp": "2026-09-21T12:01:00Z", "home_probability": 0.41, "away_probability": 0.59, "home_moneyline": 140, "away_moneyline": -160, "kind": "recorded", "observed_at": "2026-09-21T12:01:00+00:00"}]},
          "score_history": [{"timestamp": "2026-09-21T12:03:00Z", "home_score": 7, "away_score": 3}],
          "espn_history": [{"timestamp": "2026-09-21T12:04:00Z", "home_probability": 0.52, "game_clock": "8:12", "period": "Q1", "home_score": 7, "away_score": 3}],
          "win_prob_history": {\(winProb)},
          "win_prob_sources": {\(sources)},
          "scoring_plays": [{"timestamp": "2026-09-21T12:03:00Z", "team": "H", "description": "Touchdown pass", "type": "TD", "short_text": "TD H", "home_score": 7, "away_score": 3, "period": "Q1", "game_clock": "9:00"}],
          "period_markers": [{"timestamp": "2026-09-21T12:00:00Z", "period": "Q1", "source": "statpal", "precision": "boundary_observed", "not_before": "2026-09-21T11:59:30Z"}],
          "moments": [\(touchdownMoment), \(pickMoment)],
          "aggregate_line": [
            {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.41, "away_probability": 0.59},
            {"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.45, "away_probability": 0.55},
            {"timestamp": "2026-09-21T12:10:00Z", "home_probability": 0.46, "away_probability": 0.54}
          ],
          "commence_time_is_kickoff": true,
          "evidence_contract": {"v": "7878.v1", "resolution_s": 300},
          "blend_edge_pinned": true,
          "blend_edge_fold_revision": {"11": 5, "12": 9},
          "pm_spread_data": {"projected_final": {"home_score": 24.0, "away_score": 20.0, "spread_source": "kalshi", "total_source": "polymarket"}},
          "points": 3, "bookmaker_count": 7, "snapshot_count": 12, "espn_snapshot_count": 1
        }
        """
    }

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// The fixture with `find` replaced by `replace`, which must hit EXACTLY one
    /// site — a find that misses would make its "change" the unchanged payload,
    /// and the rebuild assertion would then be testing nothing.
    private func changed(_ find: String, _ replace: String,
                         file: StaticString = #filePath, line: UInt = #line) -> String {
        let json = Self.fixture()
        XCTAssertEqual(json.components(separatedBy: find).count, 2,
                       "fixture edit must hit exactly one site: \(find)", file: file, line: line)
        return json.replacingOccurrences(of: find, with: replace)
    }

    private func assertSameEdge(_ a: EventHistoryResponse, _ b: EventHistoryResponse, _ what: String,
                                file: StaticString = #filePath, line: UInt = #line) {
        let edge = EventHistoryFreshness.lastReading(in: a)
        XCTAssertNotNil(edge, "\(what): the fixture has no live edge", file: file, line: line)
        XCTAssertEqual(edge, EventHistoryFreshness.lastReading(in: b),
                       "\(what): the edit moved the live edge, so this is not a same-edge correction",
                       file: file, line: line)
    }

    /// A view model holding `payload` with both memos built, and what they hold.
    private func primed(_ payload: EventHistoryResponse)
        -> (vm: OddsChartViewModel, points: [UUID], enriched: [UUID], builds: Int) {
        let vm = OddsChartViewModel(eventId: 1, preloaded: payload)
        let points = vm.chartPoints(liveFrames: []).map(\.id)
        let enriched = vm.enrichedChartPoints(liveFrames: []).map(\.id)
        return (vm, points, enriched, vm.enrichmentBuildCount)
    }

    // MARK: - Equality is whole-content

    func testTwoSeparateDecodesOfOnePayloadAreEqual() throws {
        XCTAssertEqual(try decode(Self.fixture()), try decode(Self.fixture()))
    }

    func testSourceKeyOrderDoesNotMakeAPayloadDifferent() throws {
        XCTAssertNotEqual(Self.fixture(), Self.fixture(sourcesReversed: true),
                          "the two fixtures must differ as text, or this proves nothing about order")
        XCTAssertEqual(try decode(Self.fixture()), try decode(Self.fixture(sourcesReversed: true)))
    }

    /// NaN is not equal to itself, so a payload carrying one reads as changed —
    /// a rebuild, never a missed correction.
    func testNaNNeverComparesEqual() {
        XCTAssertNotEqual(EvidenceContract(v: EvidenceContract.knownVersion, resolutionS: .nan),
                          EvidenceContract(v: EvidenceContract.knownVersion, resolutionS: .nan))
    }

    // MARK: - Equal payloads keep the memo

    /// The #10090 path: the page adopts the response the chart already holds.
    func testAdoptingASeparatelyDecodedEqualPayloadKeepsPointsAndEnrichment() throws {
        let (vm, points, enriched, builds) = primed(try decode(Self.fixture()))
        XCTAssertFalse(points.isEmpty, "no points were built — the id comparison below would be vacuous")
        XCTAssertFalse(enriched.isEmpty)

        XCTAssertTrue(vm.adopt(try decode(Self.fixture())), "an equal payload at the same edge is still ACCEPTED")

        XCTAssertEqual(vm.chartPoints(liveFrames: []).map(\.id), points, "an identical payload rebuilt the points")
        XCTAssertEqual(vm.enrichedChartPoints(liveFrames: []).map(\.id), enriched)
        XCTAssertEqual(vm.enrichmentBuildCount, builds, "an identical payload re-ran the game-state enrichment")
    }

    func testAdoptingTheEqualPayloadWithSourcesInAnotherOrderKeepsTheMemo() throws {
        let (vm, points, enriched, builds) = primed(try decode(Self.fixture()))

        XCTAssertTrue(vm.adopt(try decode(Self.fixture(sourcesReversed: true))))

        XCTAssertEqual(vm.chartPoints(liveFrames: []).map(\.id), points)
        XCTAssertEqual(vm.enrichedChartPoints(liveFrames: []).map(\.id), enriched)
        XCTAssertEqual(vm.enrichmentBuildCount, builds)
    }

    /// `load()` and the preload write `history` directly, not through `adopt`.
    func testWritingAnEqualPayloadDirectlyKeepsTheMemo() throws {
        let (vm, points, enriched, builds) = primed(try decode(Self.fixture()))

        vm.history = try decode(Self.fixture())

        XCTAssertEqual(vm.chartPoints(liveFrames: []).map(\.id), points)
        XCTAssertEqual(vm.enrichedChartPoints(liveFrames: []).map(\.id), enriched)
        XCTAssertEqual(vm.enrichmentBuildCount, builds)
    }

    /// An equal payload is still a successful adoption: it recovers a chart a
    /// failed first fetch left under "couldn't load" (LiveChartEdgeTests920).
    func testAnEqualAdoptionStillClearsErrorAndLoading() throws {
        let (vm, _, _, _) = primed(try decode(Self.fixture()))
        vm.error = "We couldn't load that just now. Try again in a moment."
        vm.loading = true

        XCTAssertTrue(vm.adopt(try decode(Self.fixture())))

        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.loading)
    }

    /// The write is not suppressed — only the memo keys survive it. Observers
    /// of `history` still hear an equal write exactly as before.
    func testAnEqualWriteStillPublishes() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try decode(Self.fixture()))
        var heard = 0
        let subscription = vm.$history.dropFirst().sink { _ in heard += 1 }
        defer { subscription.cancel() }

        XCTAssertTrue(vm.adopt(try decode(Self.fixture())))

        XCTAssertEqual(heard, 1)
    }

    // MARK: - Changes at the same edge rebuild

    /// Every one of these is a correction the server can serve without moving
    /// the live edge. Each must reach the reader: adopted, both memos rebuilt,
    /// and the held payload IS the corrected one.
    func testEveryCorrectionAtTheSameEdgeRebuildsAndIsHeld() throws {
        let corrections: [(what: String, find: String, replace: String)] = [
            ("interior blend probability",
             #""home_probability": 0.45,"#, #""home_probability": 0.48,"#),
            ("aggregate away side",
             #""home_probability": 0.46, "away_probability": 0.54"#, #""home_probability": 0.46, "away_probability": 0.52"#),
            ("consensus probability",
             #""home_probability": 0.44, "away_probability": 0.56"#, #""home_probability": 0.43, "away_probability": 0.57"#),
            ("score correction",
             #"{"timestamp": "2026-09-21T12:03:00Z", "home_score": 7, "away_score": 3}"#,
             #"{"timestamp": "2026-09-21T12:03:00Z", "home_score": 7, "away_score": 0}"#),
            ("game clock", #""game_clock": "8:12""#, #""game_clock": "8:02""#),
            ("source game state", #""clock": "10:01""#, #""clock": "10:00""#),
            ("source attribution", #""attribution": "ESPN Analytics""#, #""attribution": "ESPN Stats & Info""#),
            ("source withdrawn", "\(Self.kalshiSeries), ", ""),
            ("live-edge flag", #""live_edge": true"#, #""live_edge": false"#),
            ("evidence coverage",
             #""covered_through": "2026-09-21T12:06:30Z""#, #""covered_through": "2026-09-21T12:08:30Z""#),
            ("evidence contract", #""resolution_s": 300"#, #""resolution_s": 600"#),
            ("period marker provenance", #""source": "statpal""#, #""source": "estimated""#),
            ("scoring play text", #""short_text": "TD H""#, #""short_text": "FG H""#),
            ("moment label", #""label": "Pick""#, #""label": "Pick six""#),
            ("pinned revision", #"{"11": 5, "12": 9}"#, #"{"11": 5, "12": 10}"#),
            ("pin flag", #""blend_edge_pinned": true"#, #""blend_edge_pinned": false"#),
            ("sportsbook row provenance", #""kind": "recorded""#, #""kind": "synthetic""#),
            ("projected final", #""home_score": 24.0"#, #""home_score": 27.0"#),
            ("kickoff flag", #""commence_time_is_kickoff": true"#, #""commence_time_is_kickoff": false"#),
            ("status", #""completed_at": null, "status": "live""#,
             #""completed_at": "2026-09-21T12:10:00Z", "status": "final""#),
            ("snapshot count", #""snapshot_count": 12"#, #""snapshot_count": 13"#),
        ]

        let base = try decode(Self.fixture())
        for c in corrections {
            let corrected = try decode(changed(c.find, c.replace))
            assertSameEdge(base, corrected, c.what)
            XCTAssertNotEqual(base, corrected, "\(c.what): the payloads compare equal")

            let (vm, points, enriched, builds) = primed(base)
            XCTAssertTrue(vm.adopt(corrected), "\(c.what): a same-edge correction was refused")
            XCTAssertEqual(vm.history, corrected, "\(c.what): the corrected payload is not the one held")
            XCTAssertNotEqual(vm.chartPoints(liveFrames: []).map(\.id), points,
                              "\(c.what): the correction was answered from the points memo")
            XCTAssertNotEqual(vm.enrichedChartPoints(liveFrames: []).map(\.id), enriched,
                              "\(c.what): the correction was answered from the enrichment memo")
            XCTAssertEqual(vm.enrichmentBuildCount, builds + 1, "\(c.what)")
        }
    }

    /// The corrections above are held; these two prove they are DRAWN.
    func testASameEdgePriceCorrectionIsOnTheChart() throws {
        let (vm, _, _, _) = primed(try decode(Self.fixture()))
        XCTAssertTrue(vm.chartPoints(liveFrames: []).contains { $0.source == "aggregate" && $0.probability == 0.45 })

        XCTAssertTrue(vm.adopt(try decode(changed(#""home_probability": 0.45,"#, #""home_probability": 0.48,"#))))

        let points = vm.chartPoints(liveFrames: [])
        XCTAssertTrue(points.contains { $0.source == "aggregate" && $0.probability == 0.48 })
        XCTAssertFalse(points.contains { $0.source == "aggregate" && $0.probability == 0.45 })
    }

    func testASameEdgeClockCorrectionReachesTheEnrichedPoints() throws {
        let (vm, _, _, _) = primed(try decode(Self.fixture()))
        XCTAssertTrue(vm.enrichedChartPoints(liveFrames: []).contains { $0.clock == "8:12" },
                      "the fixture's clock never reached a point — the after-check would be vacuous")

        XCTAssertTrue(vm.adopt(try decode(changed(#""game_clock": "8:12""#, #""game_clock": "8:02""#))))

        let enriched = vm.enrichedChartPoints(liveFrames: [])
        XCTAssertTrue(enriched.contains { $0.clock == "8:02" })
        XCTAssertFalse(enriched.contains { $0.clock == "8:12" })
    }

    func testNilAndEmptyAreDifferentPayloads() throws {
        let moments = "\"moments\": [\(Self.touchdownMoment), \(Self.pickMoment)]"
        let empty = try decode(changed(moments, "\"moments\": []"))
        let absent = try decode(changed(moments, "\"moments\": null"))
        XCTAssertEqual(empty.moments?.count, 0, "the edit must leave an EMPTY array")
        XCTAssertNil(absent.moments, "the edit must leave NO array")
        assertSameEdge(empty, absent, "nil vs empty")
        XCTAssertNotEqual(empty, absent)

        let (vm, points, _, builds) = primed(empty)
        XCTAssertTrue(vm.adopt(absent))
        XCTAssertNotEqual(vm.chartPoints(liveFrames: []).map(\.id), points)
        _ = vm.enrichedChartPoints(liveFrames: [])
        XCTAssertEqual(vm.enrichmentBuildCount, builds + 1)
    }

    func testTheSameElementsInAnotherOrderAreADifferentPayload() throws {
        let base = try decode(Self.fixture())
        let reordered = try decode(changed("[\(Self.touchdownMoment), \(Self.pickMoment)]", "[\(Self.pickMoment), \(Self.touchdownMoment)]"))
        assertSameEdge(base, reordered, "array reorder")
        XCTAssertNotEqual(base, reordered)

        let (vm, points, _, builds) = primed(base)
        XCTAssertTrue(vm.adopt(reordered))
        XCTAssertNotEqual(vm.chartPoints(liveFrames: []).map(\.id), points)
        _ = vm.enrichedChartPoints(liveFrames: [])
        XCTAssertEqual(vm.enrichmentBuildCount, builds + 1)
    }

    // MARK: - The freshness fence is unchanged

    func testAnOlderPayloadIsStillRefusedAndTheMemoKept() throws {
        let base = try decode(Self.fixture())
        let older = try decode(changed(#""timestamp": "2026-09-21T12:10:00Z""#, #""timestamp": "2026-09-21T12:09:00Z""#))
        let (vm, points, enriched, builds) = primed(base)
        vm.error = "sentinel"

        XCTAssertFalse(vm.adopt(older))

        XCTAssertEqual(vm.history, base)
        XCTAssertEqual(vm.error, "sentinel", "a refused payload is not a recovery")
        XCTAssertEqual(vm.chartPoints(liveFrames: []).map(\.id), points)
        XCTAssertEqual(vm.enrichedChartPoints(liveFrames: []).map(\.id), enriched)
        XCTAssertEqual(vm.enrichmentBuildCount, builds)
    }

    func testAnEmptyPayloadIsStillRefused() throws {
        let base = try decode(Self.fixture())
        let empty = try decode(#"{"event_id": 1, "home_team": "H", "away_team": "A", "history": []}"#)
        let (vm, points, _, builds) = primed(base)

        XCTAssertFalse(vm.adopt(empty))

        XCTAssertEqual(vm.history, base)
        XCTAssertEqual(vm.chartPoints(liveFrames: []).map(\.id), points)
        _ = vm.enrichedChartPoints(liveFrames: [])
        XCTAssertEqual(vm.enrichmentBuildCount, builds)
    }
}
