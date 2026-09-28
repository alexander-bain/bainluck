import XCTest
@testable import Bain_Luck

/// #9051 — after Kalshi is retired from a live game, the iPhone headline must
/// stop folding Kalshi's old price back in.
///
/// Codex executed the pre-fix `LiveEventPriceReconciliation` against this exact
/// shape (native-9051-candidate/RESULT.log: expected 40, actual 60): a held
/// frame blending PM 40 + Kalshi 80 = 60 at 17:10, then a fresh REST read after
/// Kalshi's removal — Polymarket alone, 40, dated by Polymarket's 17:00 quote.
/// Polymarket is still present and 17:00 < 17:10, so every clock rule kept 60.
/// The server now serves the fold revision (`blend_fold_revision`, frame `rev`,
/// history `blend_edge_fold_revision`); these pin the iPhone to web's rules in
/// `frontend/lib/foldRevision.ts` / `reconcileEventPoll.ts`.
@MainActor
final class ARemovedSourceStaysOutOfTheLiveHeadline9051Tests: XCTestCase {
    private static let bothSources = #""kalshi":{"value":0.8,"updated_at":"2026-09-25T17:00:00Z"},"polymarket":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#
    private static let polymarketOnly = #""polymarket":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#

    private func event(
        p: Double = 0.6, heroP: Double? = nil, source: String = "blend", status: String = "live",
        score: Int = 2, away: String? = nil, revision: String? = #"{"4242":10}"#,
        observedAt: String = "2026-09-25T17:00:00Z", sources: String = bothSources
    ) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Red Sox","away_team":"Cubs","status":"\(status)",
         "home_score":\(score),"away_score":1,
         "current_odds":{"home_probability":\(p),"away_probability":\(away ?? String(1 - p)),
           "home_rendered_percent":\(Int((p * 100).rounded())),"away_rendered_percent":\(Int(((1 - p) * 100).rounded()))},
         "hero_probability":\(heroP ?? p),"hero_probability_source":"\(source)",
         "hero_probability_observed_at":"\(observedAt)",
         "blend_fold_revision":\(revision ?? "null"),
         "win_probability_sources":{\(sources)}}
        """.utf8))
    }

    private func rev(_ rows: [String: Int]) -> ServedFoldRevision { ServedFoldRevision(FoldRevision(rows)) }

    private func frame(p: Double = 0.6, source: String = "polymarket", at: String = "2026-09-25T17:10:00Z",
                       rev: ServedFoldRevision? = nil) -> LiveStreamFrame {
        LiveStreamFrame(eventId: 4242, p: p, source: source, sourceValue: 0.4, updatedAt: at, status: "live", rev: rev)
    }

    private func decodeRevision(_ json: String) throws -> FoldRevision? {
        try JSONDecoder().decode(ServedFoldRevision.self, from: Data(json.utf8)).revision
    }

    // MARK: - The served vector

    func testAWellFormedVectorIsAClaimAndEveryMalformedOneIsNone() throws {
        XCTAssertEqual(try decodeRevision(#"{"4242":0,"99":7}"#)?.rows, ["4242": 0, "99": 7])
        XCTAssertEqual(try decodeRevision(#"{"4242":9007199254740991}"#)?.rows, ["4242": 9_007_199_254_740_991])
        for malformed in [#"{}"#, #"{"4242":-1}"#, #"{"4242":true}"#, #"{"4242":"3"}"#,
                          #"{"4242":1.5}"#, #"{"4242":9007199254740992}"#, #"[1]"#, #""x""#, "3"] {
            XCTAssertNil(try decodeRevision(malformed), malformed)
        }
    }

    func testAMalformedVectorNeverCostsThePageItsPayloadOrItsFrame() throws {
        let page = try event(revision: #""garbage""#)
        XCTAssertEqual(page.currentOdds?.homeProbability, 0.6)
        XCTAssertNil(page.blendFoldRevision?.revision)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let pushed = try decoder.decode(LiveStreamFrame.self, from: Data(
            #"{"event_id":4242,"p":0.5,"source":"kalshi","updated_at":"2026-09-25T17:00:00Z","rev":{"4242":false}}"#.utf8))
        XCTAssertEqual(pushed.p, 0.5)
        XCTAssertNil(pushed.rev?.revision)
        let versioned = try decoder.decode(LiveStreamFrame.self, from: Data(
            #"{"event_id":4242,"p":0.5,"source":"kalshi","updated_at":"2026-09-25T17:00:00Z","rev":{"4242":21}}"#.utf8))
        XCTAssertEqual(versioned.rev?.revision?.rows, ["4242": 21])
    }

    func testCommitOrderComparesRowByRow() throws {
        let held = try XCTUnwrap(FoldRevision(["1": 5, "2": 5]))
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 6, "2": 5])), held), .newer)
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 5, "2": 5])), held), .same)
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 4, "2": 5])), held), .older)
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 6, "2": 4])), held), .incomparable)
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 6])), held), .incomparable, "a duplicate left the fold")
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 6, "3": 6])), held), .incomparable, "same size, different rows")
        XCTAssertEqual(FoldRevision.compare(try XCTUnwrap(FoldRevision(["1": 6, "2": 6, "3": 0])), held), .incomparable)
    }

    func testAFrameOrdersOnlyAgainstAOneRowHero() throws {
        let one = try XCTUnwrap(FoldRevision(["4242": 10]))
        let folded = try XCTUnwrap(FoldRevision(["4242": 10, "999": 3]))
        XCTAssertNil(FoldRevision.frameOrder(held: nil, frame: one), "nothing held: no claim, the clocks decide")
        XCTAssertEqual(FoldRevision.frameOrder(held: one, frame: FoldRevision(["4242": 11])), .newer)
        XCTAssertEqual(FoldRevision.frameOrder(held: one, frame: FoldRevision(["4242": 9])), .older)
        XCTAssertEqual(FoldRevision.frameOrder(held: one, frame: nil), .incomparable, "an unversioned price cannot take the held revision")
        XCTAssertEqual(FoldRevision.frameOrder(held: folded, frame: FoldRevision(["4242": 11])), .incomparable)
        XCTAssertEqual(FoldRevision.frameOrder(held: folded, frame: FoldRevision(["4242": 11, "999": 4])), .incomparable,
                       "a folded hero is a value no raw-row frame computed")
    }

    // MARK: - Poll vs held frame (`shouldPreserve` / `applying`)

    func testCodexCounterexampleAFreshRemovalReadBeatsTheOlderRevisionFrameDespiteItsNewerClock() throws {
        let removal = try event(p: 0.4, revision: #"{"4242":14}"#, sources: Self.polymarketOnly)
        let held = frame(rev: rev(["4242": 12]))
        XCTAssertFalse(LiveEventPriceReconciliation.shouldPreserve(held, over: removal, streamRecoverable: true))
        XCTAssertEqual(LiveEventPriceReconciliation.applying(held, to: removal, streamRecoverable: true).currentOdds?.homeProbability, 0.4)
        // A frame from before the contract cannot be ordered against the vector either.
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: removal, streamRecoverable: true).currentOdds?.homeProbability, 0.4)
    }

    func testControlWithNoRevisionAnywhereThePreContractClockRuleStillDecides() throws {
        // The same shape with no vector on either side is exactly the pre-fix
        // behaviour Codex reproduced — kept, because no claim means no change.
        let unversioned = try event(p: 0.4, revision: nil, sources: Self.polymarketOnly)
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: unversioned, streamRecoverable: true).currentOdds?.homeProbability, 0.6)
    }

    func testAStrictlyNewerWriteLandsEvenWithAnOlderClockAndCarriesItsOwnProvenance() throws {
        let polled = try event(p: 0.4, revision: #"{"4242":14}"#, observedAt: "2026-09-25T17:20:00Z")
        let newer = frame(p: 0.55, at: "2026-09-25T17:05:00Z", rev: rev(["4242": 15]))
        let result = LiveEventPriceReconciliation.applying(newer, to: polled, streamRecoverable: true)
        XCTAssertEqual(result.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(result.heroProbability, 0.55)
        XCTAssertEqual(result.heroProbabilityObservedAt, "2026-09-25T17:05:00Z")
        XCTAssertEqual(result.blendFoldRevision?.revision?.rows, ["4242": 15])
        XCTAssertTrue(LiveEventPriceReconciliation.holdsLiveBlend(result), "value and revision stay paired")
        // Same snapshot: refused, however new its clock.
        let same = frame(p: 0.55, at: "2026-09-25T18:00:00Z", rev: rev(["4242": 14]))
        XCTAssertEqual(LiveEventPriceReconciliation.applying(same, to: polled, streamRecoverable: true).currentOdds?.homeProbability, 0.4)
    }

    func testARevisionOnANumberThePageIsNotPrintingIsNoClaim() throws {
        // An opening-line hero, or a payload whose printed number is not the
        // hero, carries a vector that dates some other value.
        for polled in [try event(p: 0.4, source: "opening", revision: #"{"4242":14}"#, sources: Self.polymarketOnly),
                       try event(p: 0.4, heroP: 0.45, revision: #"{"4242":14}"#, sources: Self.polymarketOnly)] {
            XCTAssertNil(LiveEventPriceReconciliation.pairedFoldRevision(in: polled))
            XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(rev: rev(["4242": 12])), to: polled, streamRecoverable: true)
                .currentOdds?.homeProbability, 0.6, "the clock rule decides, as before")
        }
    }

    // MARK: - Poll vs held headline (`keepingNewerHeldHeadline`)

    func testAnOlderCachedReadKeepsTheHeldHeadlineAndTakesTheScore() throws {
        let held = try event(p: 0.4, revision: #"{"4242":14}"#, sources: Self.polymarketOnly)
        for stale in [try event(p: 0.6, score: 3, revision: #"{"4242":12}"#),
                      try event(p: 0.6, score: 3, revision: nil)] {
            let kept = LiveEventPriceReconciliation.keepingNewerHeldHeadline(stale, held: held)
            XCTAssertEqual(kept.currentOdds?.homeProbability, 0.4)
            XCTAssertEqual(kept.currentOdds?.homeRenderedPercent, 40)
            XCTAssertEqual(kept.heroProbability, 0.4)
            XCTAssertEqual(kept.blendFoldRevision?.revision?.rows, ["4242": 14])
            XCTAssertNil(kept.winProbabilitySources?["kalshi"], "the removed source stays removed")
            XCTAssertEqual(kept.homeScore, 3)
        }
    }

    func testANewerEqualOrIncomparableReadIsAuthoritative() throws {
        let held = try event(p: 0.4, revision: #"{"4242":14}"#, sources: Self.polymarketOnly)
        for revision in [#"{"4242":15}"#, #"{"4242":14}"#, #"{"4242":15,"999":1}"#] {
            let polled = try event(p: 0.7, revision: revision)
            XCTAssertEqual(LiveEventPriceReconciliation.keepingNewerHeldHeadline(polled, held: held).currentOdds?.homeProbability, 0.7, revision)
        }
    }

    func testAFinishedReadOrAnUnversionedPageTakesTheResponseWhole() throws {
        let held = try event(p: 0.4, revision: #"{"4242":14}"#)
        let final = try event(p: 1.0, source: "settled", status: "final", revision: #"{"4242":12}"#)
        XCTAssertEqual(LiveEventPriceReconciliation.keepingNewerHeldHeadline(final, held: held).currentOdds?.homeProbability, 1.0)
        let unversionedHeld = try event(p: 0.4, revision: nil)
        let polled = try event(p: 0.6, revision: #"{"4242":12}"#)
        XCTAssertEqual(LiveEventPriceReconciliation.keepingNewerHeldHeadline(polled, held: unversionedHeld).currentOdds?.homeProbability, 0.6)
    }

    func testAWithheldAwaySideStaysWithheld() throws {
        let held = try event(p: 0.4, revision: #"{"4242":14}"#)
        let stale = try event(p: 0.6, away: "null", revision: #"{"4242":12}"#)
        let kept = LiveEventPriceReconciliation.keepingNewerHeldHeadline(stale, held: held)
        XCTAssertEqual(kept.currentOdds?.homeProbability, 0.4)
        XCTAssertNil(kept.currentOdds?.awayProbability)
    }

    // MARK: - Chart catch-up (`chartRevisionRefreshKey`)

    private func history(pinned: Bool = true, revision: String = #"{"4242":12}"#, edge: Double = 0.6) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Red Sox","away_team":"Cubs","status":"live","history":[],
         "aggregate_line":[{"timestamp":"2026-09-25T17:00:00Z","home_probability":0.55},
                           {"timestamp":"2026-09-25T17:11:00Z","home_probability":\(edge)}],
         "blend_edge_pinned":\(pinned),"blend_edge_fold_revision":\(revision)}
        """.utf8))
    }

    func testTheChartAsksOnceWhenTheHeadlineIsOnANewerFoldThanTheDrawnEdge() throws {
        let removal = try event(p: 0.4, revision: #"{"4242":14}"#, sources: Self.polymarketOnly)
        XCTAssertEqual(LiveEventPriceReconciliation.chartRevisionRefreshKey(event: removal, history: try history(), liveBlend: []), "4242:14")
        XCTAssertEqual(LiveEventPriceReconciliation.chartRevisionRefreshKey(
            event: removal, history: try history(revision: #"{"4242":12,"999":1}"#), liveBlend: []), "4242:14")
        // Nothing to catch up: same or older fold, no pin, or the line already ends on the headline.
        XCTAssertNil(LiveEventPriceReconciliation.chartRevisionRefreshKey(event: removal, history: try history(revision: #"{"4242":14}"#), liveBlend: []))
        XCTAssertNil(LiveEventPriceReconciliation.chartRevisionRefreshKey(event: removal, history: try history(revision: #"{"4242":15}"#), liveBlend: []))
        XCTAssertNil(LiveEventPriceReconciliation.chartRevisionRefreshKey(event: removal, history: try history(pinned: false), liveBlend: []))
        XCTAssertNil(LiveEventPriceReconciliation.chartRevisionRefreshKey(event: removal, history: try history(edge: 0.4), liveBlend: []))
        // The drawn edge includes pushed frames past the served one.
        let pushed = LiveBlendPoint(date: try XCTUnwrap("2026-09-25T17:12:00Z".asDate), homeProbability: 0.4,
                                    source: "polymarket", sourceProbability: 0.4)
        XCTAssertNil(LiveEventPriceReconciliation.chartRevisionRefreshKey(event: removal, history: try history(), liveBlend: [pushed]))
    }

    // MARK: - The page (view model, real stream path)

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func push(p: Double, at: String, rev: String?, source: String = "polymarket") {
            fire("probability", """
            {"event_id":4242,"p":\(p),"source":"\(source)","source_value":0.4,"updated_at":"\(at)","status":"live","rev":\(rev ?? "null")}
            """)
        }
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        var historyResponse: EventHistoryResponse?
        var beforeEventResponse: (() async -> Void)?
        var failEvent = false
        private(set) var eventFetches = 0
        private(set) var eventResponses = 0
        private(set) var historyFetches = 0
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail {
            eventFetches += 1
            let result = response
            if let beforeEventResponse { await beforeEventResponse() }
            if failEvent { throw Missing() }
            eventResponses += 1
            return result
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            historyFetches += 1
            guard let historyResponse else { throw Missing() }
            return historyResponse
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func model(_ client: Client, _ handle: Handle) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
    }

    private func settle(until condition: () -> Bool) async {
        for _ in 0..<200 where !condition() { await Task.yield() }
    }

    func testTheRemovalReachesTheHeadlineAndNoReplayOrCachedReadRestoresSixty() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":10}"#))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        // A genuine Polymarket move while Kalshi is still folded in.
        handle.push(p: 0.6, at: "2026-09-25T17:10:00Z", rev: #"{"4242":12}"#)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 12])
        // Kalshi is retired; fresh detail is Polymarket alone, dated by its OLDER quote.
        client.response = try event(p: 0.4, revision: #"{"4242":14}"#, sources: Self.polymarketOnly)
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.4)
        XCTAssertNil(vm.event?.winProbabilitySources?["kalshi"])
        // A delayed copy of the pre-removal frame, and one with no vector, are refused.
        let points = vm.liveBlend.count
        handle.push(p: 0.6, at: "2026-09-25T17:30:00Z", rev: #"{"4242":12}"#)
        handle.push(p: 0.6, at: "2026-09-25T17:30:00Z", rev: nil)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.4)
        XCTAssertEqual(vm.liveBlend.count, points, "a refused frame draws no chart point")
        // A cached pre-removal read cannot restore it either.
        client.response = try event(p: 0.6, score: 5, revision: #"{"4242":12}"#)
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.4)
        XCTAssertNil(vm.event?.winProbabilitySources?["kalshi"])
        XCTAssertEqual(vm.event?.homeScore, 5, "everything but the headline comes from the response")
        // A genuinely newer write still lands.
        handle.push(p: 0.38, at: "2026-09-25T17:31:00Z", rev: #"{"4242":15}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.38)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.38)
    }

    func testAFoldedHeroRefusesRawRowFramesAndReReadsDetail() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        let before = client.eventFetches
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        client.historyResponse = try history(revision: #"{"4242":21,"999":5}"#, edge: 0.52)
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, "a raw-row p is not the folded hero")
        XCTAssertTrue(vm.liveBlend.isEmpty)
        await settle { client.eventFetches > before && vm.event?.currentOdds?.homeProbability == 0.52 }
        XCTAssertEqual(client.eventFetches, before + 1)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52, "the re-read's folded hero lands")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 21, "999": 5])
        XCTAssertEqual(vm.liveUpdateStatus, .live, "the accepted authoritative reread delivers the folded price")
    }

    func testUnchangedOrFailedFoldRereadsDoNotClaimLiveDelivery() async throws {
        for fails in [false, true] {
            let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
            client.historyResponse = try history(revision: #"{"4242":20,"999":5}"#)
            let handle = Handle(), vm = model(client, handle)
            await vm.load(); handle.fire("open")
            client.failEvent = fails
            let before = client.eventFetches
            handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
            await settle { client.eventFetches > before && (!fails || vm.pricePairRefreshFailed) }
            XCTAssertEqual(vm.liveUpdateStatus, fails ? .interrupted : .awaitingUpdate)
            XCTAssertFalse(vm.streamHasPushedPrice)
            vm.stopRefresh()
        }
    }

    func testStaleFoldRereadCannotTakeCreditForAnIndependentPollAdvance() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try history(revision: #"{"4242":21,"999":5}"#, edge: 0.52)
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        var pending: CheckedContinuation<Void, Never>?
        client.beforeEventResponse = { await withCheckedContinuation { pending = $0 } }
        // The stream-triggered read captures old revision20, then stalls.
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        await settle { pending != nil }
        XCTAssertNotNil(pending)
        // An independent regular refresh adopts21 while that read is in flight.
        client.beforeEventResponse = nil
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertFalse(vm.streamHasPushedPrice)
        let responses = client.eventResponses
        pending?.resume()
        await settle { client.eventResponses > responses }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertFalse(vm.streamHasPushedPrice, "the stale stream read delivered no new adopted price")
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
    }

    func testFoldRereadFinishingAfterAnOutageCannotRelightLiveStatus() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try history(revision: #"{"4242":21,"999":5}"#, edge: 0.52)
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        var pending: CheckedContinuation<Void, Never>?
        client.beforeEventResponse = { await withCheckedContinuation { pending = $0 } }
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        await settle { pending != nil }
        XCTAssertNotNil(pending)
        handle.fire("error")
        handle.fire("open")
        pending?.resume()
        await settle { vm.event?.currentOdds?.homeProbability == 0.52 }
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
    }

    func testAPageWithNoRevisionKeepsEveryPreContractRule() async throws {
        let client = Client(try event(p: 0.6, revision: nil))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        let before = client.eventFetches
        handle.push(p: 0.7, at: "2026-09-25T17:10:00Z", rev: nil)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.7)
        handle.push(p: 0.2, at: "2026-09-25T17:05:00Z", rev: nil)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.7, "the clock still refuses an older frame")
        for _ in 0..<20 { await Task.yield() }
        XCTAssertEqual(client.eventFetches, before, "no re-read without a revision")
    }
}
