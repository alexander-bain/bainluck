import XCTest
@testable import Bain_Luck

final class WatchTelemetryConsentTests: XCTestCase {
    private final class Sink: TelemetrySink {
        func setAnalyticsCollectionEnabled(_ enabled: Bool) { }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { }
        func resetAnalyticsData() { }
    }

    func testDeferredPacketsCannotCrossConsentEpochs() throws {
        let name = "watch-consent-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let consent = TelemetryConsent(defaults: defaults, sink: Sink())
        consent.initialize()
        XCTAssertNil(consent.analyticsAuthorizationEpoch)
        var emitted = 0
        XCTAssertFalse(consent.withAnalyticsAuthorization(epoch: UUID()) { emitted += 1 })
        consent.set(.analytics)
        let granted = try XCTUnwrap(consent.analyticsAuthorizationEpoch)
        XCTAssertTrue(consent.withAnalyticsAuthorization(epoch: granted) { emitted += 1 })
        let restored = TelemetryConsent(defaults: defaults, sink: Sink())
        restored.initialize()
        XCTAssertEqual(restored.analyticsAuthorizationEpoch, granted, "Phone restart retains a granted offline buffer")
        consent.set(.none)
        XCTAssertNil(consent.analyticsAuthorizationEpoch)
        XCTAssertFalse(consent.withAnalyticsAuthorization(epoch: granted) { emitted += 1 })
        consent.set(.analytics)
        XCTAssertNotEqual(consent.analyticsAuthorizationEpoch, granted)
        XCTAssertFalse(consent.withAnalyticsAuthorization(epoch: granted) { emitted += 1 })
        XCTAssertEqual(emitted, 1)
    }

    func testWatchEventsKeepTypedFieldsAndDropPacketIdentity() throws {
        let event = WatchTelemetryRecord(recordedAt: Date(), kind: .action, surface: .picker, action: .selectGame)
        let parameters = try XCTUnwrap(AnalyticsPrivacy.sanitize(event: event.kind.rawValue,
                                                                parameters: event.analyticsParameters))
        XCTAssertEqual(parameters["device_class"] as? String, "watch")
        XCTAssertEqual(parameters["action"] as? String, "select_game")
        XCTAssertNil(parameters["id"])
        XCTAssertNil(parameters["recordedAt"])
        XCTAssertNil(parameters["watchEpoch"])
        for kind in WatchTelemetryKind.allCases {
            XCTAssertNotNil(AnalyticsPrivacy.sanitize(event: kind.rawValue, parameters: [:]))
        }
    }

    func testIngressRefusesMalformedEnvelopesAndDisposesExpiredRecords() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let epoch = UUID()
        let event = WatchTelemetryRecord(recordedAt: now, kind: .action, surface: .picker, action: .selectGame)
        func wire(schema: Int = 1, records: [WatchTelemetryRecord]? = nil) throws -> Data {
            try JSONEncoder().encode(WatchTelemetryBatch(schema: schema, phoneEpoch: epoch,
                watchEpoch: UUID(), records: records ?? [event]))
        }
        func accepted(_ data: Data, phone: UUID? = nil) -> WatchTelemetryIngress.Accepted {
            WatchTelemetryIngress.accept(data, phoneEpoch: phone ?? epoch, now: now, seen: [])
        }
        let valid = try wire()
        XCTAssertEqual(accepted(valid).records, [event])
        XCTAssertTrue(WatchTelemetryIngress.accept(valid, phoneEpoch: nil, now: now, seen: []).records.isEmpty)
        XCTAssertTrue(accepted(valid, phone: UUID()).acknowledgement.isEmpty)
        XCTAssertTrue(accepted(try wire(schema: 2)).acknowledgement.isEmpty)
        XCTAssertTrue(accepted(try wire(records: Array(repeating: event, count: 13))).acknowledgement.isEmpty)
        XCTAssertTrue(accepted(Data(repeating: 32, count: WatchTelemetryBuffer.maxBatchBytes + 1)).acknowledgement.isEmpty)
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: valid) as? [String: Any])
        var rows = try XCTUnwrap(json["records"] as? [[String: Any]])
        rows[0]["action"] = "unrecognized_action"
        json["records"] = rows
        XCTAssertTrue(accepted(try JSONSerialization.data(withJSONObject: json)).acknowledgement.isEmpty)
        let expired = WatchTelemetryRecord(recordedAt: now.addingTimeInterval(-WatchTelemetryBuffer.maxAge),
                                          kind: .screen, surface: .game)
        let disposal = accepted(try wire(records: [expired]))
        XCTAssertEqual(disposal.acknowledgement, [expired.id])
        XCTAssertTrue(disposal.records.isEmpty)
        let replay = WatchTelemetryIngress.accept(valid, phoneEpoch: epoch, now: now, seen: [event.id])
        XCTAssertEqual(replay.acknowledgement, [event.id])
        XCTAssertTrue(replay.records.isEmpty)
    }

    func testEveryEmittedParameterSurvivesPrivacySanitization() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let records = [
            WatchTelemetryRecord(recordedAt: now, kind: .screen, surface: .game, appBuild: "1.0.3 (38)"),
            WatchTelemetryRecord(recordedAt: now, kind: .timing, surface: .discoveries,
                outcome: .success, durationMS: 1200, firstCardMS: 400, cold: true),
            WatchTelemetryRecord(recordedAt: now, kind: .action, surface: .picker, action: .selectGame),
            WatchTelemetryRecord(recordedAt: now, kind: .refresh, surface: .game,
                outcome: .offline, durationMS: 1500, count: 0),
            WatchTelemetryRecord(recordedAt: now, kind: .reading, surface: .game, outcome: .saved, count: 1),
            WatchTelemetryRecord(recordedAt: now, kind: .appOpen, surface: .diagnostics),
            WatchTelemetryRecord(recordedAt: now, kind: .appBackground, surface: .game)
        ]
        for record in records {
            XCTAssertTrue(record.isWellFormed)
            var input = record.analyticsParameters
            input["transport_delay_ms"] = 1000
            let actual = try XCTUnwrap(AnalyticsPrivacy.sanitize(event: record.kind.rawValue, parameters: input))
            XCTAssertEqual(NSDictionary(dictionary: actual), NSDictionary(dictionary: input), record.kind.rawValue)
        }
    }


    @MainActor func testDiscoveryReceiptsDistinguishOfflineEmptyCancelledAndSuperseded() async throws {
        let suite = "watch-telemetry-discovery-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let transport = TelemetryDiscoveryTransport()
        let store = WatchDiscoveryStore(transport: transport, defaults: defaults)
        var receipts: [String] = []
        store.telemetry = { outcome, ms, count in
            XCTAssertGreaterThanOrEqual(ms, 0)
            XCTAssertEqual(count, 0)
            receipts.append(outcome)
        }
        let offline = Task { await store.refresh() }
        try await transport.waitFor(1)
        await transport.finish(1, .failure(URLError(.notConnectedToInternet)))
        await offline.value
        let old = Task { await store.refresh() }
        try await transport.waitFor(2)
        let latest = Task { await store.refresh() }
        try await transport.waitFor(3)
        await transport.finish(3, .success([]))
        await latest.value
        await transport.finish(2, .failure(URLError(.timedOut)))
        await old.value
        let cancelled = Task { await store.refresh() }
        try await transport.waitFor(4)
        cancelled.cancel()
        await transport.finish(4, .success([]))
        await cancelled.value
        XCTAssertEqual(receipts, ["offline", "empty", "cancelled", "cancelled"])
        XCTAssertNil(store.errorMessage)
    }

}


private actor TelemetryDiscoveryTransport: WatchDiscoveryTransport {
    private var next = 0
    private var pending: [Int: CheckedContinuation<[WatchDiscoveryReading], Error>] = [:]
    func fetch() async throws -> [WatchDiscoveryReading] {
        next += 1
        let id = next
        return try await withCheckedThrowingContinuation { pending[id] = $0 }
    }
    func waitFor(_ id: Int) async throws {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while pending[id] == nil {
            guard ContinuousClock.now < deadline else { throw URLError(.timedOut) }
            try await Task.sleep(for: .milliseconds(10))
        }
    }
    func finish(_ id: Int, _ result: Result<[WatchDiscoveryReading], Error>) {
        pending.removeValue(forKey: id)?.resume(with: result)
    }
}
