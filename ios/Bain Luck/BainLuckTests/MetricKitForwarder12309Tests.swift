import XCTest

@testable import Bain_Luck

/// #12309 — Apple's MetricKit diagnostics leave the phone only for a reader who
/// granted telemetry consent, as one body per diagnostic, oldest first, and a
/// failure that may pass keeps them for the next try.
///
/// What only a device can show (Apple delivering a real payload, which the
/// simulator never does) is the simulator walk's job through the DEBUG sample,
/// and is said so on the issue rather than claimed here.
final class MetricKitForwarder12309Tests: XCTestCase {
    private var directory: URL!

    /// What the injected consent and sender saw.
    nonisolated private final class Rig: @unchecked Sendable {
        private let lock = NSLock()
        private var _granted: Bool
        private var _sent: [Data] = []
        private var statuses: [Int]
        var afterSend: (() -> Void)?

        init(granted: Bool, statuses: [Int] = []) {
            _granted = granted
            self.statuses = statuses
        }

        var granted: Bool {
            get { lock.withLock { _granted } }
            set { lock.withLock { _granted = newValue } }
        }

        var sent: [Data] { lock.withLock { _sent } }

        func send(_ body: Data) throws -> Int {
            let status: Int = lock.withLock {
                _sent.append(body)
                return statuses.isEmpty ? 202 : statuses.removeFirst()
            }
            afterSend?()
            if status == -1 { throw URLError(.notConnectedToInternet) }
            return status
        }
    }

    private func install(_ rig: Rig) {
        MetricKitForwarder12309.isGranted = { rig.granted }
        MetricKitForwarder12309.send = { try rig.send($0) }
    }

    override func setUp() {
        super.setUp()
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("metrickit-12309-\(UUID().uuidString)", isDirectory: true)
        MetricKitForwarder12309.outbox = MetricKitOutbox12309(directory: directory)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: directory)
        MetricKitForwarder12309.outbox = .standard
        MetricKitForwarder12309.isGranted = MetricKitForwarder12309.productionIsGranted
        MetricKitForwarder12309.send = MetricKitForwarder12309.productionSend
        super.tearDown()
    }

    private static let hang = Data("""
    {"callStackTree":{"callStackPerThread":true,"callStacks":[]},\
    "diagnosticMetaData":{"appVersion":"1.0.6","hangDuration":"2.31 sec"},"version":"1.0.0"}
    """.utf8)

    private func body(_ n: Int) -> Data {
        MetricKitRecord12309.body(kind: .hang, payloadJSON: Data(#"{"n":\#(n)}"#.utf8), appVersion: "1.0.6",
                                  appBuild: "10", osVersion: nil, deviceType: nil)!
    }

    private func n(of body: Data) -> Int? {
        let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any]
        return (object?["payload"] as? [String: Any])?["n"] as? Int
    }

    // MARK: - The body

    func testTheKindsAreTheServersSet() {
        XCTAssertEqual(Set(MetricKitRecord12309.Kind.allCases.map(\.rawValue)),
                       ["crash", "hang", "cpu_exception", "disk_write", "launch", "metrics"],
                       "app/routes/metrickit.py ACCEPTED_KINDS")
    }

    func testABodyCarriesMetricKitsJSONUntouchedAndNoIdentifier() throws {
        let longOS = String(repeating: "x", count: 80)
        let data = try XCTUnwrap(MetricKitRecord12309.body(
            kind: .hang, payloadJSON: Self.hang, appVersion: "1.0.6", appBuild: "10",
            osVersion: longOS, deviceType: "iPhone18,2"))
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? NSDictionary)
        let original = try XCTUnwrap(JSONSerialization.jsonObject(with: Self.hang) as? NSDictionary)

        XCTAssertEqual(object["kind"] as? String, "hang")
        XCTAssertEqual(object["payload"] as? NSDictionary, original, "MetricKit's JSON goes as it came")
        XCTAssertEqual(object["app_version"] as? String, "1.0.6")
        XCTAssertEqual(object["app_build"] as? String, "10")
        XCTAssertEqual(object["device_type"] as? String, "iPhone18,2")
        XCTAssertEqual((object["os_version"] as? String)?.count, MetricKitRecord12309.maxFieldLength,
                       "clipped to the server's 64, not refused for it")
        XCTAssertEqual(Set(object.allKeys.compactMap { $0 as? String }),
                       ["kind", "payload", "app_version", "app_build", "os_version", "device_type"],
                       "nothing else: no user, session or device identifier")
    }

    func testABodyIsNilForANonObjectOrAnOversizedPayload() {
        XCTAssertNil(MetricKitRecord12309.body(kind: .crash, payloadJSON: Data("[1,2]".utf8), appVersion: nil,
                                               appBuild: nil, osVersion: nil, deviceType: nil))
        let pad = String(repeating: "x", count: MetricKitRecord12309.maxBodyBytes)
        XCTAssertNil(MetricKitRecord12309.body(kind: .crash, payloadJSON: Data(#"{"pad":"\#(pad)"}"#.utf8),
                                               appVersion: nil, appBuild: nil, osVersion: nil, deviceType: nil),
                     "the server would refuse it; it is never queued")
    }

    // MARK: - Consent

    func testWithoutConsentNothingIsWrittenOrSentAndWhatWaitedGoes() async {
        MetricKitForwarder12309.outbox.enqueue(body(0))  // held under an earlier grant
        let rig = Rig(granted: false)
        install(rig)

        let result = await MetricKitForwarder12309.accept([body(1), body(2)])

        XCTAssertEqual(result, .none)
        XCTAssertTrue(rig.sent.isEmpty, "a reader who declined sends nothing")
        XCTAssertTrue(MetricKitForwarder12309.outbox.pending().isEmpty, "and keeps nothing on disk")
    }

    func testConsentWithdrawnMidFlushStopsAndEmpties() async {
        let rig = Rig(granted: true)
        rig.afterSend = { rig.granted = false }
        install(rig)

        let result = await MetricKitForwarder12309.accept([body(1), body(2), body(3)])

        XCTAssertEqual(rig.sent.count, 1, "nothing is sent once consent has gone")
        XCTAssertEqual(result, MetricKitForwarder12309.FlushResult(sent: 1, dropped: 0, remaining: 0))
        XCTAssertTrue(MetricKitForwarder12309.outbox.pending().isEmpty)
    }

    // MARK: - Sending

    func testWithConsentBodiesAreSentOldestFirstAndCleared() async {
        let rig = Rig(granted: true)
        install(rig)

        let result = await MetricKitForwarder12309.accept([body(1), body(2), body(3)])

        XCTAssertEqual(result, MetricKitForwarder12309.FlushResult(sent: 3, dropped: 0, remaining: 0))
        XCTAssertEqual(rig.sent.map { n(of: $0) }, [1, 2, 3])
        XCTAssertTrue(MetricKitForwarder12309.outbox.pending().isEmpty)
    }

    func testAFailureThatMayPassStopsAndKeepsTheRestInOrder() async {
        let rig = Rig(granted: true, statuses: [202, 503])
        install(rig)

        let first = await MetricKitForwarder12309.accept([body(1), body(2), body(3)])
        XCTAssertEqual(first, MetricKitForwarder12309.FlushResult(sent: 1, dropped: 0, remaining: 2))

        let second = await MetricKitForwarder12309.flush()
        XCTAssertEqual(second, MetricKitForwarder12309.FlushResult(sent: 2, dropped: 0, remaining: 0))
        XCTAssertEqual(rig.sent.map { n(of: $0) }, [1, 2, 2, 3], "the refused-for-now body goes again, first")
    }

    func testNoNetworkIsAFailureThatMayPass() async {
        let rig = Rig(granted: true, statuses: [-1])
        install(rig)

        let result = await MetricKitForwarder12309.accept([body(1), body(2)])

        XCTAssertEqual(result, MetricKitForwarder12309.FlushResult(sent: 0, dropped: 0, remaining: 2))
    }

    func testARefusalNoRetryCouldChangeIsDroppedAndTheFlushGoesOn() async {
        let rig = Rig(granted: true, statuses: [422, 202])
        install(rig)

        let result = await MetricKitForwarder12309.accept([body(1), body(2)])

        XCTAssertEqual(result, MetricKitForwarder12309.FlushResult(sent: 1, dropped: 1, remaining: 0))
    }

    func testOnly4xxOtherThan408And429IsPermanent() {
        for status in [400, 404, 413, 422] {
            XCTAssertTrue(MetricKitForwarder12309.isPermanentRefusal(status), "\(status)")
        }
        for status in [0, 202, 408, 429, 500, 503] {
            XCTAssertFalse(MetricKitForwarder12309.isPermanentRefusal(status), "\(status)")
        }
    }

    // MARK: - The outbox

    func testTheOutboxKeepsTheNewestFortyForAReaderOfflineForWeeks() throws {
        let outbox = MetricKitForwarder12309.outbox
        for i in 0..<(MetricKitOutbox12309.maxItems + 5) { outbox.enqueue(body(i)) }

        let pending = outbox.pending()
        XCTAssertEqual(pending.count, MetricKitOutbox12309.maxItems)
        XCTAssertEqual(n(of: try Data(contentsOf: pending[0])), 5, "the oldest five went")
        XCTAssertEqual(n(of: try Data(contentsOf: pending[pending.count - 1])), MetricKitOutbox12309.maxItems + 4)
    }

    // MARK: - Where it goes

    func testTheOriginIsAPIClients() throws {
        let here = URL(fileURLWithPath: #filePath)
        let apiClient = here.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Services/APIClient.swift")
        let source = try String(contentsOf: apiClient, encoding: .utf8)
        XCTAssertTrue(source.contains(#"private let baseURL = "\#(MetricKitForwarder12309.apiOrigin)""#),
                      "the forwarder posts to the API's own origin")
        XCTAssertEqual(MetricKitForwarder12309.path, "/api/telemetry/metrickit")
    }
}
