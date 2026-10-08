import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10753 — a game page left open through the finish keeps the pushed movement
/// its chart already drew, until the served history catches up.
///
/// The defect, on the actual path: revised frames adopted by commit order are
/// drawn past the served aggregate edge; the finished history lands before the
/// server's blend includes them; the finished payload is never extended — so
/// the movement the reader watched disappeared. The lifecycle cases below run
/// the real `EventDetailViewModel` stream path (the #9051 seams) into the real
/// chart owner (`OddsChartViewModel`, rendered as `OddsChartView`), with the
/// served JSON shapes and ordinary valid `rev`s.
@MainActor
final class GameChartKeepsDrawnMovementThroughFinish10753Tests: XCTestCase {

    // MARK: - Fixtures

    private static let commence = "2026-09-25T16:00:00Z"
    private static let t0 = "2026-09-25T17:00:00Z"   // the served blend's edge
    private static let t1 = "2026-09-25T17:05:00Z"   // drawn before the finish
    private static let t2 = "2026-09-25T17:10:00Z"   // drawn before the finish
    private static let t3 = "2026-09-25T17:15:00Z"   // admitted, never drawn
    private static let terminalAt = "2026-09-25T17:31:00Z"

    private func date(_ iso: String) throws -> Date { try XCTUnwrap(iso.asDate) }

    private func event(p: Double = 0.6, source: String = "blend", status: String = "live",
                       revision: String? = #"{"4242":10}"#) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Red Sox","away_team":"Cubs","status":"\(status)",
         "commence_time":"\(Self.commence)","home_score":3,"away_score":1,
         "current_odds":{"home_probability":\(p),"away_probability":\(1 - p),
           "home_rendered_percent":\(Int((p * 100).rounded())),"away_rendered_percent":\(Int(((1 - p) * 100).rounded()))},
         "hero_probability":\(p),"hero_probability_source":"\(source)",
         "hero_probability_observed_at":"\(Self.t0)",
         "blend_fold_revision":\(revision ?? "null"),
         "win_probability_sources":{"polymarket":{"value":\(p),"updated_at":"\(Self.t0)"}}}
        """.utf8))
    }

    /// A drawable game: ESPN readings through `espnEnd` and a served blend whose
    /// points are `aggregate`. Finished payloads carry `completed`, a
    /// completion and ESPN through the end of the game (17:30 → game end 17:32).
    private func history(finished: Bool, aggregate: [(String, Double)] = [(t0, 0.55)],
                         espnEnd: String? = nil, completedAt: String? = "2026-09-25T18:10:00Z",
                         withAggregate: Bool = true) throws -> EventHistoryResponse {
        let end = espnEnd ?? (finished ? "2026-09-25T17:30:00Z" : Self.t0)
        let line = ([("2026-09-25T16:05:00Z", 0.5)] + aggregate)
            .map { #"{"timestamp":"\#($0.0)","home_probability":\#($0.1)}"# }.joined(separator: ",")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Red Sox","away_team":"Cubs",
         "status":"\(finished ? "completed" : "live")",
         "completed_at":\(finished ? (completedAt.map { "\"\($0)\"" } ?? "null") : "null"),
         "history":[],
         "win_prob_history":{"espn":[{"timestamp":"2026-09-25T16:05:00Z","home_probability":0.5},
                                     {"timestamp":"\(end)","home_probability":0.9}]},
         "aggregate_line":\(withAggregate ? "[\(line)]" : "null")}
        """.utf8))
    }

    // The #9051 page seams: a real provider and stream handle.
    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func push(p: Double, at: String, rev: String?, status: String = "live") {
            fire("probability", """
            {"event_id":4242,"p":\(p),"source":"polymarket","source_value":\(p),"updated_at":"\(at)","status":"\(status)","rev":\(rev ?? "null")}
            """)
        }
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        var historyResponse: EventHistoryResponse?
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail { response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard let historyResponse else { throw Missing() }
            return historyResponse
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func page(_ client: Client, _ handle: Handle) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
    }

    /// The chart exactly as the event page mounts it, on a shared model.
    private func chart(_ model: OddsChartViewModel, page: EventDetailViewModel) -> some View {
        let event = page.event
        return OddsChartView(
            eventId: 4242, commenceTime: Self.commence, status: event?.status,
            homeTeamName: "Red Sox", awayTeamName: "Cubs",
            homeTeamAbbrev: "BOS", awayTeamAbbrev: "CHC",
            preloadedHistory: page.history,
            liveFrames: page.liveBlend,
            finishedSourceFold: event.flatMap {
                FinishedSourceFold(eventId: $0.id, status: $0.status, revision: $0.blendFoldRevision?.revision)
            },
            model: model
        )
        .frame(width: 390)
    }

    /// Mount the chart (its body builds its points through the model), and
    /// write the raster when the lane asks for evidence.
    @discardableResult
    private func mount(_ model: OddsChartViewModel, page: EventDetailViewModel, artifact: String? = nil) throws -> Data {
        let renderer = rendererForMeasurement(chart(model, page: page))
        renderer.scale = 3
        let png = try XCTUnwrap(renderer.uiImage?.pngData(), "the chart produced no raster")
        if let artifact {
            let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
                ?? FileManager.default.temporaryDirectory.path)
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let url = dir.appendingPathComponent("10753-\(artifact).png")
            try png.write(to: url)
            print("#10753 render artifact [\(artifact)]: \(url.path) (\(png.count) bytes)")
        }
        return png
    }

    /// The blend points the mounted chart draws, as the body asks for them.
    private func blend(_ model: OddsChartViewModel, page: EventDetailViewModel) -> [ChartDataPoint] {
        let event = page.event
        return model.chartPoints(
            liveFrames: page.liveBlend,
            finish: LiveBlendFinishInputs(
                pageStatus: event?.status,
                finishedSourceFold: event.flatMap {
                    FinishedSourceFold(eventId: $0.id, status: $0.status, revision: $0.blendFoldRevision?.revision)
                })
        ).filter { $0.source == "aggregate" }
    }

    private func value(at iso: String, in points: [ChartDataPoint]) throws -> [Double] {
        let at = try date(iso)
        return points.filter { $0.date == at }.map(\.probability)
    }

    /// A live page with two revised frames drawn past the served edge, then a
    /// terminal frame, then the finished detail + a finished history whose
    /// blend still ends at T0.
    private func crossTheFinish(
        finishedRevision: String? = #"{"4242":13}"#, drawBeforeFinish: Bool = true,
        finishedHistory: EventHistoryResponse? = nil, artifactPrefix: String? = nil
    ) async throws -> (page: EventDetailViewModel, chart: OddsChartViewModel, handle: Handle, client: Client) {
        let client = Client(try event())
        client.historyResponse = try history(finished: false)
        let handle = Handle(), page = page(client, handle)
        await page.load(); handle.fire("open")
        let model = OddsChartViewModel(eventId: 4242, preloaded: page.history)

        handle.push(p: 0.65, at: Self.t1, rev: #"{"4242":11}"#)
        handle.push(p: 0.72, at: Self.t2, rev: #"{"4242":12}"#)
        if drawBeforeFinish {
            try mount(model, page: page, artifact: artifactPrefix.map { "\($0)-1-before-finish" })
        }
        // The server says the game ended. Its price is a terminal observation.
        handle.push(p: 0.97, at: Self.terminalAt, rev: #"{"4242":13}"#, status: "completed")
        client.response = try event(p: 1.0, source: "settled", status: "completed", revision: finishedRevision)
        client.historyResponse = try finishedHistory ?? history(finished: true)
        await page.load()
        // `.onChange(of: historyEdge)` → `adopt`, as the mounted chart does.
        XCTAssertTrue(model.adopt(try XCTUnwrap(page.history)), "the finished history passes the chart's own adoption")
        return (page, model, handle, client)
    }

    // MARK: - Author causal RED/GREEN

    /// RED on the base source: the finished history drops the bank whole, so
    /// T1/T2 vanish. GREEN: the drawn, proved movement stays, and the terminal
    /// frame adds nothing. Then the served history catches up and wins.
    func testDrawnMovementSurvivesTheFinishUntilServedHistoryCatchesUp() async throws {
        let run = try await crossTheFinish(artifactPrefix: "lifecycle")
        defer { run.page.stopRefresh() }
        XCTAssertEqual(run.page.event?.status, "completed")
        XCTAssertNotNil(run.page.event?.blendFoldRevision?.revision, "terminal detail serves its source-fold vector")
        XCTAssertNil(LiveEventPriceReconciliation.pairedFoldRevision(in: try XCTUnwrap(run.page.event)),
                     "the settled hero is never read as a paired blend")

        let lagging = blend(run.chart, page: run.page)
        XCTAssertEqual(try value(at: Self.t1, in: lagging), [0.65], "the drawn T1 movement was lost at the finish")
        XCTAssertEqual(try value(at: Self.t2, in: lagging), [0.72], "the drawn T2 movement was lost at the finish")
        XCTAssertEqual(try value(at: Self.terminalAt, in: lagging), [], "a terminal frame adds no movement")
        XCTAssertTrue(lagging.allSatisfy { $0.date <= (try? self.date("2026-09-25T17:32:00Z")) ?? .distantPast },
                      "nothing past the game's end")
        try mount(run.chart, page: run.page, artifact: "lifecycle-2-final-history-lagging")

        // A late frame on the finished page is refused too.
        run.handle.push(p: 0.2, at: "2026-09-25T17:20:00Z", rev: #"{"4242":14}"#)
        XCTAssertEqual(try value(at: "2026-09-25T17:20:00Z", in: blend(run.chart, page: run.page)), [],
                       "a late frame enlarges nothing")
        try mount(run.chart, page: run.page, artifact: "lifecycle-3-late-frame-refused")

        // The served blend catches up at the exact times, with its own values.
        run.client.historyResponse = try history(
            finished: true, aggregate: [(Self.t0, 0.55), (Self.t1, 0.66), (Self.t2, 0.71), ("2026-09-25T17:30:00Z", 0.95)],
            espnEnd: "2026-09-25T17:30:30Z")
        await run.page.load()
        XCTAssertTrue(run.chart.adopt(try XCTUnwrap(run.page.history)))
        let caughtUp = blend(run.chart, page: run.page)
        XCTAssertEqual(try value(at: Self.t1, in: caughtUp), [0.66], "the served point wins its exact time, once")
        XCTAssertEqual(try value(at: Self.t2, in: caughtUp), [0.71])
        try mount(run.chart, page: run.page, artifact: "lifecycle-4-served-caught-up")
    }

    /// The camera's control: the before-finish arm is itself a drawn chart, so
    /// the rasters compare drawn lines and not an empty frame.
    func testTheBeforeFinishArmIsADrawnChart() async throws {
        let client = Client(try event())
        client.historyResponse = try history(finished: false)
        let handle = Handle(), page = page(client, handle)
        defer { page.stopRefresh() }
        await page.load(); handle.fire("open")
        handle.push(p: 0.65, at: Self.t1, rev: #"{"4242":11}"#)
        let model = OddsChartViewModel(eventId: 4242, preloaded: page.history)
        XCTAssertTrue(OddsChartView.hasDrawableLine(in: model.chartPoints(liveFrames: page.liveBlend)))
        XCTAssertGreaterThan(try mount(model, page: page).count, 20_000)
    }

    // MARK: - Lifecycle controls

    func testAPointNeverDrawnBeforeTheFinishGetsNoException() async throws {
        let run = try await crossTheFinish(drawBeforeFinish: false)
        defer { run.page.stopRefresh() }
        let points = blend(run.chart, page: run.page)
        XCTAssertEqual(try value(at: Self.t1, in: points), [])
        XCTAssertEqual(try value(at: Self.t2, in: points), [])
    }

    func testAnAdmittedFrameLandingAfterTheLastPreFinishDrawIsNotKept() async throws {
        let client = Client(try event())
        client.historyResponse = try history(finished: false)
        let handle = Handle(), page = page(client, handle)
        defer { page.stopRefresh() }
        await page.load(); handle.fire("open")
        let model = OddsChartViewModel(eventId: 4242, preloaded: page.history)
        handle.push(p: 0.65, at: Self.t1, rev: #"{"4242":11}"#)
        try mount(model, page: page)
        handle.push(p: 0.80, at: Self.t3, rev: #"{"4242":12}"#)   // admitted, never drawn
        handle.push(p: 0.97, at: Self.terminalAt, rev: #"{"4242":13}"#, status: "completed")
        try mount(model, page: page)                              // page already finished: frozen
        client.response = try event(p: 1.0, source: "settled", status: "completed", revision: #"{"4242":13}"#)
        client.historyResponse = try history(finished: true)
        await page.load()
        XCTAssertTrue(model.adopt(try XCTUnwrap(page.history)))
        let points = blend(model, page: page)
        XCTAssertEqual(try value(at: Self.t1, in: points), [0.65])
        XCTAssertEqual(try value(at: Self.t3, in: points), [], "drawn only after the finish: no exception")
    }

    func testAnOlderChangedOrMissingFinishedVectorRetainsNothing() async throws {
        for revision in [#"{"4242":11}"#, #"{"4242":13,"999":1}"#, #"{"777":13}"#, nil, #""garbage""#] {
            let run = try await crossTheFinish(finishedRevision: revision)
            let points = blend(run.chart, page: run.page)
            XCTAssertEqual(try value(at: Self.t1, in: points), [], revision ?? "nil")
            XCTAssertEqual(try value(at: Self.t2, in: points), [], revision ?? "nil")
            run.page.stopRefresh()
        }
    }

    func testAnEqualFinishedVectorKeepsTheDrawnMovement() async throws {
        let run = try await crossTheFinish(finishedRevision: #"{"4242":12}"#)
        defer { run.page.stopRefresh() }
        XCTAssertEqual(try value(at: Self.t2, in: blend(run.chart, page: run.page)), [0.72])
    }

    func testAFinishedHistoryWithNoServedBlendMintsNone() async throws {
        let run = try await crossTheFinish(finishedHistory: try history(finished: true, withAggregate: false))
        defer { run.page.stopRefresh() }
        XCTAssertTrue(blend(run.chart, page: run.page).isEmpty, "no served blend: the client mints none")
    }

    func testRetainedPointsStayInsideTheGamesEnd() async throws {
        // ESPN ends 17:06 → game end 17:08: T1 fits, T2 does not.
        let run = try await crossTheFinish(finishedHistory: try history(finished: true, espnEnd: "2026-09-25T17:06:00Z"))
        defer { run.page.stopRefresh() }
        let points = blend(run.chart, page: run.page)
        XCTAssertEqual(try value(at: Self.t1, in: points), [0.65])
        XCTAssertEqual(try value(at: Self.t2, in: points), [], "the game end is never widened for a witness")
    }

    func testServedCoverageRetiresEveryRetainedPointAtOrBeforeItsEdge() async throws {
        let run = try await crossTheFinish(finishedHistory: try history(
            finished: true, aggregate: [(Self.t0, 0.55), (Self.t1, 0.64)]))
        defer { run.page.stopRefresh() }
        let points = blend(run.chart, page: run.page)
        XCTAssertEqual(try value(at: Self.t1, in: points), [0.64], "served exact time wins")
        XCTAssertEqual(try value(at: Self.t2, in: points), [0.72])
    }

    func testAPageThatOpensFinishedDrawsNoPushedMovement() async throws {
        let client = Client(try event(p: 1.0, source: "settled", status: "completed", revision: #"{"4242":13}"#))
        client.historyResponse = try history(finished: true)
        let handle = Handle(), page = page(client, handle)
        defer { page.stopRefresh() }
        await page.load()
        let model = OddsChartViewModel(eventId: 4242, preloaded: page.history)
        let proved = LiveBlendPoint(
            date: try date(Self.t1), homeProbability: 0.65,
            admission: LiveBlendAdmission(eventId: 4242, held: FoldRevision(["4242": 10]),
                                          frame: FoldRevision(["4242": 11]), frameStatus: "live"))
        let points = model.chartPoints(
            liveFrames: [proved],
            finish: LiveBlendFinishInputs(pageStatus: "completed",
                                          finishedSourceFold: FinishedSourceFold(eventId: 4242, status: "completed",
                                                                                 revision: FoldRevision(["4242": 13]))))
        XCTAssertEqual(try value(at: Self.t1, in: points.filter { $0.source == "aggregate" }), [])
    }

    // MARK: - Which frames earn the proof (the VM's accepted revised branch)

    func testOnlyAStrictlyNewerOneRowFrameOnAHeldLiveBlendIsAdmitted() async throws {
        let client = Client(try event())
        client.historyResponse = try history(finished: false)
        let handle = Handle(), page = page(client, handle)
        defer { page.stopRefresh() }
        await page.load(); handle.fire("open")
        handle.push(p: 0.65, at: Self.t1, rev: #"{"4242":11}"#)
        XCTAssertEqual(page.liveBlend.last?.admission?.frame.rows, ["4242": 11])
        XCTAssertEqual(page.liveBlend.last?.admission?.held.rows, ["4242": 10])
        XCTAssertEqual(page.liveBlend.last?.admission?.eventId, 4242)
        let count = page.liveBlend.count
        handle.push(p: 0.7, at: "2026-09-25T17:06:00Z", rev: #"{"4242":11}"#)         // equal
        handle.push(p: 0.7, at: "2026-09-25T17:07:00Z", rev: #"{"4242":9}"#)          // older
        handle.push(p: 0.7, at: "2026-09-25T17:08:00Z", rev: nil)                     // missing
        handle.push(p: 0.7, at: "2026-09-25T17:09:00Z", rev: #"{"4242":"x"}"#)        // malformed
        XCTAssertEqual(page.liveBlend.count, count, "refused frames draw nothing and earn nothing")
    }

    func testAFrameOnAPageWithoutAPairedRevisionDrawsButEarnsNoProof() async throws {
        let client = Client(try event(revision: nil))
        client.historyResponse = try history(finished: false)
        let handle = Handle(), page = page(client, handle)
        defer { page.stopRefresh() }
        await page.load(); handle.fire("open")
        handle.push(p: 0.65, at: Self.t1, rev: nil)
        XCTAssertEqual(page.liveBlend.last?.homeProbability, 0.65, "the live edge is unchanged")
        XCTAssertNil(page.liveBlend.last?.admission)
    }

    func testATerminalFrameEarnsNoPreFinishProof() async throws {
        let client = Client(try event())
        client.historyResponse = try history(finished: false)
        let handle = Handle(), page = page(client, handle)
        defer { page.stopRefresh() }
        await page.load(); handle.fire("open")
        handle.push(p: 0.97, at: Self.terminalAt, rev: #"{"4242":11}"#, status: "completed")
        XCTAssertNil(page.liveBlend.last?.admission)
    }

    // MARK: - The pure rules

    private func proved(_ iso: String, event: Int = 4242, held: Int = 10, frame: Int = 11,
                        rows: [String: Int]? = nil) throws -> LiveBlendPoint {
        LiveBlendPoint(date: try date(iso), homeProbability: 0.6,
                       admission: LiveBlendAdmission(eventId: event, held: FoldRevision(["4242": held]),
                                                     frame: FoldRevision(rows ?? ["4242": frame]), frameStatus: "live"))
    }

    func testAdmissionNeedsAStrictlyNewerWriteToTheSameOneRow() {
        let held = FoldRevision(["4242": 10])
        XCTAssertNotNil(LiveBlendAdmission(eventId: 1, held: held, frame: FoldRevision(["4242": 11]), frameStatus: nil))
        XCTAssertNil(LiveBlendAdmission(eventId: 1, held: held, frame: FoldRevision(["4242": 10]), frameStatus: "live"))
        XCTAssertNil(LiveBlendAdmission(eventId: 1, held: held, frame: FoldRevision(["999": 11]), frameStatus: "live"))
        XCTAssertNil(LiveBlendAdmission(eventId: 1, held: FoldRevision(["4242": 10, "999": 1]),
                                        frame: FoldRevision(["4242": 11]), frameStatus: "live"))
        XCTAssertNil(LiveBlendAdmission(eventId: 1, held: nil, frame: FoldRevision(["4242": 11]), frameStatus: "live"))
        XCTAssertNil(LiveBlendAdmission(eventId: 1, held: held, frame: FoldRevision(["4242": 11]), frameStatus: "closed"))
    }

    func testRecordingTakesOnlyThisGamesProvedFramesPastTheServedEdge() throws {
        let edge = try date(Self.t0)
        let frames = [try proved("2026-09-25T16:59:00Z"), try proved(Self.t1, event: 9),
                      LiveBlendPoint(date: try date(Self.t2), homeProbability: 0.7), try proved(Self.t3)]
        let recorded = DrawnBlendRetention.recording(drawn: frames, servedEdge: edge, eventId: 4242, into: [])
        XCTAssertEqual(recorded.map(\.date), [try date(Self.t3)])
        XCTAssertTrue(DrawnBlendRetention.recording(drawn: frames, servedEdge: nil, eventId: 4242, into: []).isEmpty)
    }

    func testRetentionIsAllOrNothingOnTheProof() throws {
        let fold = FinishedSourceFold(eventId: 4242, status: "completed", revision: FoldRevision(["4242": 13]))
        let edge = try date(Self.t0), end = try date("2026-09-25T17:32:00Z")
        let good = [try proved(Self.t1), try proved(Self.t2, held: 11, frame: 12)]
        XCTAssertEqual(DrawnBlendRetention.retained(good, eventId: 4242, finished: fold, servedEdge: edge, gameEnd: end).count, 2)
        XCTAssertTrue(DrawnBlendRetention.retained(good + [LiveBlendPoint(date: try date(Self.t3), homeProbability: 0.7)],
                                                   eventId: 4242, finished: fold, servedEdge: edge, gameEnd: end).isEmpty,
                      "an unproved point refuses the whole snapshot")
        XCTAssertTrue(DrawnBlendRetention.retained(good + [try proved(Self.t3, held: 12, frame: 14)],
                                                   eventId: 4242, finished: fold, servedEdge: edge, gameEnd: end).isEmpty,
                      "a frame newer than the finished read refuses")
        XCTAssertTrue(DrawnBlendRetention.retained(good, eventId: 4242,
                                                   finished: FinishedSourceFold(eventId: 9, status: "completed",
                                                                                revision: FoldRevision(["4242": 13])),
                                                   servedEdge: edge, gameEnd: end).isEmpty, "another game's read")
        XCTAssertTrue(DrawnBlendRetention.retained(good, eventId: 4242, finished: fold, servedEdge: nil, gameEnd: end).isEmpty)
        XCTAssertTrue(DrawnBlendRetention.retained(good, eventId: 4242, finished: fold, servedEdge: edge, gameEnd: nil).isEmpty)
        XCTAssertNil(FinishedSourceFold(eventId: 4242, status: "live", revision: FoldRevision(["4242": 13])),
                     "only a finished detail supplies the context")
    }

    /// The general refusal stays: the pure transform never extends a finished
    /// payload with arbitrary live frames (`LiveChartEdgeTests920`).
    func testTheTransformStillRefusesArbitraryFramesOnAFinishedPayload() throws {
        let points = OddsChartView.chartPoints(from: try history(finished: true), liveFrames: [try proved(Self.t1)])
        XCTAssertEqual(try value(at: Self.t1, in: points), [])
    }
}
