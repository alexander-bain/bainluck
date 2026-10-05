import Foundation
import XCTest
@testable import Bain_Luck

private actor DiscoveryTestTransport: WatchDiscoveryTransport {
    private var nextID = 0
    private var requests: [Int: CheckedContinuation<[WatchDiscoveryReading], Error>] = [:]
    func fetch() async throws -> [WatchDiscoveryReading] {
        nextID += 1
        let id = nextID
        return try await withCheckedThrowingContinuation { requests[id] = $0 }
    }
    func waitFor(_ id: Int) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while requests[id] == nil {
            guard ContinuousClock.now < deadline else { throw URLError(.timedOut) }
            try Task.checkCancellation()
            try await Task.sleep(for: .milliseconds(10))
        }
    }
    func finish(_ id: Int, _ result: Result<[WatchDiscoveryReading], Error>) {
        requests.removeValue(forKey: id)?.resume(with: result)
    }
}

final class WatchDiscoveryTests: XCTestCase {
    private func decode(_ rows: String) throws -> [WatchDiscoveryReading] {
        try WatchDiscoveryDecoder.decode(Data("{\"items\":[\(rows)]}".utf8))
    }
    private func row(_ id: Int, probability: String = "0.455", extra: String = "") -> String {
        """
        {"type":"futures","data":{"id":\(id),"name":"Will inflation fall below 3%?",
        "top_outcomes":[{"name":"Yes","probability":\(probability),
        "price_observed_at":"2026-10-05T12:00:00Z"}]\(extra)}}
        """
    }

    func testServerOrderTypedIDDedupAndUnsupportedSiblings() throws {
        let rows = ["{\"type\":\"event\",\"data\":{\"id\":1}}", row(3),
                    "{\"type\":\"futures\",\"data\":{\"id\":\"bad\"}}", row(3), row(1), row(2), row(4)]
        XCTAssertEqual(try decode(rows.joined(separator: ",")).map(\.id), [3, 1, 2])
        let distinct = try decode([row(1, extra: ",\"group_id\":\"same\""),
                                   row(2, extra: ",\"group_id\":\"same\"")].joined(separator: ","))
        XCTAssertEqual(distinct.map(\.id), [1, 2], "A shared group is not necessarily one question")
    }

    func testProbabilityBoundsAndMissingObservationDoNotInventFreshness() throws {
        XCTAssertTrue(try decode([row(0), row(1, probability: "1.2"), row(2, probability: "-0.1"),
                                  row(3, probability: "null")].joined(separator: ",")).isEmpty)
        let row = "{\"type\":\"futures\",\"data\":{\"id\":9,\"name\":\"Question\",\"price_observed_at\":\"2026-10-05T12:00:00Z\",\"top_outcomes\":[{\"name\":\"Yes\",\"probability\":0.64}]}}"
        let result = try XCTUnwrap(decode(row).first)
        XCTAssertNil(result.observedAt, "Card age is not proof of the displayed outcome's age")
        XCTAssertEqual(result.observationLabel(), "Observation age unknown")
    }

    func testSettlementComesFromAuthorityAndNeverElapsedDateOrExtremePrice() throws {
        let live = try XCTUnwrap(decode(row(1, probability: "1", extra: ",\"resolution_date\":\"2020-01-01T00:00:00Z\"")).first)
        XCTAssertFalse(live.isSettled)
        let settled = try XCTUnwrap(decode(row(2, extra: ",\"resolved\":true,\"winner\":\"Yes\"")).first)
        XCTAssertNil(settled.probability)
        XCTAssertEqual(settled.resultLabel, "Result: Yes")
        let unavailable = try XCTUnwrap(decode(row(3, extra: ",\"status\":\"resolved\"")).first)
        XCTAssertEqual(unavailable.resultLabel, "Settled · Result unavailable")
    }

    @MainActor func testSavedClockFailureRetryCancellationAndSuccessEmptyClear() async throws {
        let suite = "watch-discovery-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let transport = DiscoveryTestTransport()
        let readings = try decode([row(1), row(2), row(3)].joined(separator: ","))
        let observedAt = try XCTUnwrap(readings.first?.observedAt)
        let receivedAt = observedAt.addingTimeInterval(60)
        let store = WatchDiscoveryStore(transport: transport, defaults: defaults, now: { receivedAt })
        let first = Task { await store.refresh() }
        try await transport.waitFor(1)
        await transport.finish(1, .success(readings))
        await first.value
        XCTAssertEqual(store.visibleReadings(hasSelectedGame: true).count, 2)
        XCTAssertEqual(store.visibleReadings(hasSelectedGame: false).count, 3)
        let restored = WatchDiscoveryStore(transport: transport, defaults: defaults)
        XCTAssertTrue(restored.isSavedReading)
        XCTAssertEqual(restored.readings.first?.observedAt, observedAt)
        XCTAssertEqual(restored.fetchedAt, receivedAt)
        let failure = Task { await store.refresh() }
        try await transport.waitFor(2)
        await transport.finish(2, .failure(URLError(.notConnectedToInternet)))
        await failure.value
        XCTAssertTrue(store.isSavedReading)
        XCTAssertEqual(store.errorMessage, "Offline. Try again.")
        XCTAssertEqual(store.readings.first?.observationLabel(now: observedAt.addingTimeInterval(3600)), "Observed 1h ago")
        let retry = Task { await store.refresh() }
        try await transport.waitFor(3)
        XCTAssertEqual(store.errorMessage, "Offline. Try again.")
        retry.cancel()
        await transport.finish(3, .success([]))
        await retry.value
        XCTAssertEqual(store.readings, readings)
        XCTAssertEqual(store.errorMessage, "Offline. Try again.")
        let recovery = Task { await store.refresh() }
        try await transport.waitFor(4)
        await transport.finish(4, .success([]))
        await recovery.value
        XCTAssertTrue(store.readings.isEmpty, "A successful empty response replaces saved questions")
        XCTAssertFalse(store.isSavedReading)
        XCTAssertNil(store.errorMessage)
        XCTAssertTrue(WatchDiscoveryStore(transport: transport, defaults: defaults).readings.isEmpty)
    }

    @MainActor func testLateDismissedAndSupersededResponsesCannotReplaceCurrentReading() async throws {
        let suite = "watch-discovery-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let transport = DiscoveryTestTransport()
        let store = WatchDiscoveryStore(transport: transport, defaults: defaults)
        let old = Task { await store.refresh() }
        try await transport.waitFor(1)
        let latest = Task { await store.refresh() }
        try await transport.waitFor(2)
        await transport.finish(2, .success(try decode(row(2))))
        await latest.value
        await transport.finish(1, .success(try decode(row(1))))
        await old.value
        XCTAssertEqual(store.readings.map(\.id), [2])
        let dismissed = Task { await store.refresh() }
        try await transport.waitFor(3)
        store.cancelRefresh()
        await transport.finish(3, .success([]))
        await dismissed.value
        XCTAssertEqual(store.readings.map(\.id), [2])
        XCTAssertEqual(WatchDiscoveryStore(transport: transport, defaults: defaults).readings.map(\.id), [2])
        XCTAssertFalse(store.isRefreshing)
    }
}
