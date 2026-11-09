import Foundation
#if os(iOS)
import MetricKit
#endif

/// #12309 — one body for `POST /api/telemetry/metrickit`: one MetricKit
/// diagnostic, or one day's metrics, with the version and device fields from
/// its own metadata and MetricKit's JSON untouched. MetricKit carries no user
/// identifier and the body adds none.
nonisolated enum MetricKitRecord12309 {
    /// The server's `ACCEPTED_KINDS`, the same set (`app/routes/metrickit.py`).
    enum Kind: String, CaseIterable, Sendable {
        case crash, hang, launch, metrics
        case cpuException = "cpu_exception"
        case diskWrite = "disk_write"
    }

    /// The largest body sent. The server refuses anything larger
    /// (`MAX_BODY_BYTES`, the same number), so a larger one is never queued.
    static let maxBodyBytes = 512 * 1024

    /// The server's limit on each version and device field.
    static let maxFieldLength = 64

    /// The body, or nil when MetricKit's JSON is not an object or the body
    /// would be over `maxBodyBytes`.
    static func body(kind: Kind, payloadJSON: Data, appVersion: String?, appBuild: String?,
                     osVersion: String?, deviceType: String?) -> Data? {
        guard let payload = try? JSONSerialization.jsonObject(with: payloadJSON) as? [String: Any]
        else { return nil }
        var object: [String: Any] = ["kind": kind.rawValue, "payload": payload]
        let fields = ["app_version": appVersion, "app_build": appBuild,
                      "os_version": osVersion, "device_type": deviceType]
        for (key, value) in fields {
            if let value, !value.isEmpty { object[key] = String(value.prefix(maxFieldLength)) }
        }
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              data.count <= maxBodyBytes else { return nil }
        return data
    }
}

/// #12309 — bodies waiting to be sent, one file each, oldest first, in the
/// app's own Application Support. Held only while consent is granted:
/// `MetricKitForwarder12309` empties it the moment consent goes.
nonisolated struct MetricKitOutbox12309: Sendable {
    let directory: URL

    /// A reader offline for weeks keeps the newest forty, not an unbounded pile.
    static let maxItems = 40

    static var standard: MetricKitOutbox12309 {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return MetricKitOutbox12309(directory: base.appendingPathComponent("MetricKit12309", isDirectory: true))
    }

    func enqueue(_ body: Data) {
        let files = FileManager.default
        try? files.createDirectory(at: directory, withIntermediateDirectories: true)
        // Zero-padded nanoseconds sort as numbers; the UUID breaks a tie.
        let stamp = String(format: "%020llu", UInt64(Date().timeIntervalSince1970 * 1_000_000_000))
        try? body.write(to: directory.appendingPathComponent("\(stamp)-\(UUID().uuidString).json"),
                        options: .atomic)
        for stale in pending().dropLast(Self.maxItems) { remove(stale) }
    }

    /// Waiting bodies, oldest first.
    func pending() -> [URL] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []
        return names.filter { $0.hasSuffix(".json") }.sorted()
            .map { directory.appendingPathComponent($0) }
    }

    func remove(_ url: URL) { try? FileManager.default.removeItem(at: url) }

    func removeAll() { try? FileManager.default.removeItem(at: directory) }
}

/// #12309 — sends Apple's MetricKit diagnostics (hangs, slow launches, the
/// crashes Crashlytics misses) for a reader who granted telemetry consent, and
/// for nobody else.
///
/// Consent is read from the one authority, `TelemetryConsent`, at every step:
/// before a body is written down, before each send, and whenever the choice
/// changes. Without a grant nothing is written, nothing is sent, and anything
/// waiting is deleted — so "no" reaches backwards as well as forwards, as it
/// does for Firebase (`TelemetrySink.resetAnalyticsData`).
///
/// Sending follows `BugReportOutbox`: oldest first, stopping at the first
/// failure that may pass (no network, 5xx, 408, 429) and dropping a body the
/// server refuses outright (any other 4xx), which no retry could change.
nonisolated enum MetricKitForwarder12309 {
    /// Injected by tests. Production reads the one consent authority, on the
    /// main actor it belongs to (MetricKit delivers on a background queue).
    nonisolated(unsafe) static var isGranted: @Sendable () async -> Bool = productionIsGranted

    /// What `isGranted` is outside tests, so a test can put it back.
    static let productionIsGranted: @Sendable () async -> Bool = {
        await MainActor.run { TelemetryConsent.shared.isGranted }
    }

    /// Injected by tests. Production posts to the API and returns the status.
    nonisolated(unsafe) static var send: @Sendable (Data) async throws -> Int = productionSend

    /// What `send` is outside tests, so a test can put it back.
    static let productionSend: @Sendable (Data) async throws -> Int = { try await post($0) }

    /// Injected by tests.
    nonisolated(unsafe) static var outbox = MetricKitOutbox12309.standard

    /// `APIClient`'s origin, the same string (asserted by the tests, so the two
    /// cannot drift apart).
    static let apiOrigin = "https://api.bainluck.com"
    static let path = "/api/telemetry/metrickit"

    static let maxPerFlush = 10

    nonisolated struct FlushResult: Equatable, Sendable {
        /// Bodies the server stored during this flush.
        let sent: Int
        /// Bodies the server refused outright, and unreadable files: deleted.
        let dropped: Int
        /// Bodies still waiting afterwards.
        let remaining: Int

        static let none = FlushResult(sent: 0, dropped: 0, remaining: 0)
    }

    /// New bodies from MetricKit. Without a grant they are not written down,
    /// and whatever was waiting goes.
    @discardableResult
    static func accept(_ bodies: [Data]) async -> FlushResult {
        guard await isGranted() else {
            outbox.removeAll()
            return .none
        }
        bodies.forEach(outbox.enqueue)
        return await flush()
    }

    /// Whether the server's status means "never", as opposed to "not now".
    static func isPermanentRefusal(_ status: Int) -> Bool {
        status != 408 && status != 429 && (400..<500).contains(status)
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var flushing = false

    /// Sends what is waiting, oldest first. A second flush while one runs
    /// returns at once; what it would have sent waits for the next.
    @discardableResult
    static func flush() async -> FlushResult {
        guard await isGranted() else {
            outbox.removeAll()
            return .none
        }
        let claimed: Bool = lock.withLock {
            if flushing { return false }
            flushing = true
            return true
        }
        guard claimed else { return FlushResult(sent: 0, dropped: 0, remaining: outbox.pending().count) }
        defer { lock.withLock { flushing = false } }

        var sent = 0
        var dropped = 0
        for url in outbox.pending().prefix(maxPerFlush) {
            // Consent can go while a send is in flight.
            guard await isGranted() else {
                outbox.removeAll()
                return FlushResult(sent: sent, dropped: dropped, remaining: 0)
            }
            guard let body = try? Data(contentsOf: url) else {
                outbox.remove(url)
                dropped += 1
                continue
            }
            do {
                let status = try await send(body)
                if (200..<300).contains(status) {
                    outbox.remove(url)
                    sent += 1
                } else if isPermanentRefusal(status) {
                    outbox.remove(url)
                    dropped += 1
                } else {
                    break
                }
            } catch {
                break
            }
        }
        return FlushResult(sent: sent, dropped: dropped, remaining: outbox.pending().count)
    }

    /// An ephemeral session: no cookies and no cache, nothing that could tie a
    /// body to the reader.
    private static let session = URLSession(configuration: .ephemeral)

    private static func post(_ body: Data) async throws -> Int {
        guard let url = URL(string: origin + path) else { return 0 }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        request.timeoutInterval = 30
        let (_, response) = try await session.data(for: request)
        return (response as? HTTPURLResponse)?.statusCode ?? 0
    }

    /// `apiOrigin`, or in a DEBUG build the rig's `-BL_METRICKIT_ORIGIN` (a
    /// local server the simulator walk reads the body from).
    private static var origin: String {
        #if DEBUG
        if let i = ProcessInfo.processInfo.arguments.firstIndex(of: "-BL_METRICKIT_ORIGIN"),
           ProcessInfo.processInfo.arguments.indices.contains(i + 1) {
            return ProcessInfo.processInfo.arguments[i + 1]
        }
        #endif
        return apiOrigin
    }
}

#if os(iOS)
/// #12309 — receives MetricKit's deliveries and hands each diagnostic, and
/// each day's metrics, to `MetricKitForwarder12309` as its own body. Apple
/// delivers on its own schedule (diagnostics when they occur, metrics about
/// daily), on a background queue.
nonisolated final class MetricKitSubscriber12309: NSObject, MXMetricManagerSubscriber, @unchecked Sendable {
    static let shared = MetricKitSubscriber12309()

    private let lock = NSLock()
    private var consentObserver: NSObjectProtocol?

    /// Once, at launch, after `TelemetryConsent.initialize()`. Subscribing
    /// sends nothing: each delivery is checked against consent.
    @MainActor
    func start() {
        let first: Bool = lock.withLock {
            guard consentObserver == nil else { return false }
            // A changed choice either empties the outbox (no) or sends what
            // waited (yes); `flush` reads the choice itself.
            consentObserver = NotificationCenter.default.addObserver(
                forName: TelemetryConsent.didChange, object: nil, queue: nil
            ) { _ in
                Task { await MetricKitForwarder12309.flush() }
            }
            return true
        }
        guard first else { return }
        MXMetricManager.shared.add(self)
        Task { await MetricKitForwarder12309.flush() }
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("-BL_METRICKIT_RIG_GRANT") {
            // The walk's stand-in for a grant, for this forwarder alone: the real
            // authority stays "none", so a robot never switches on Firebase.
            MetricKitForwarder12309.isGranted = { true }
        }
        if arguments.contains("-BL_METRICKIT_SAMPLE") {
            Task { await MetricKitForwarder12309.accept(MetricKitSample12309.bodies()) }
        }
        #endif
    }

    // Both deliveries only turn payloads into bodies in memory: `accept` reads
    // consent before anything is written down or sent, and without a grant
    // drops them and empties the outbox.

    func didReceive(_ payloads: [MXMetricPayload]) {
        let bodies = payloads.compactMap { payload in
            MetricKitRecord12309.body(
                kind: .metrics, payloadJSON: payload.jsonRepresentation(),
                appVersion: payload.latestApplicationVersion,
                appBuild: payload.metaData?.applicationBuildVersion,
                osVersion: payload.metaData?.osVersion, deviceType: payload.metaData?.deviceType)
        }
        Task { await MetricKitForwarder12309.accept(bodies) }
    }

    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        var bodies: [Data] = []
        func add(_ kind: MetricKitRecord12309.Kind, _ diagnostic: MXDiagnostic) {
            let meta = diagnostic.metaData
            if let body = MetricKitRecord12309.body(
                kind: kind, payloadJSON: diagnostic.jsonRepresentation(),
                appVersion: diagnostic.applicationVersion, appBuild: meta.applicationBuildVersion,
                osVersion: meta.osVersion, deviceType: meta.deviceType) {
                bodies.append(body)
            }
        }
        for payload in payloads {
            payload.crashDiagnostics?.forEach { add(.crash, $0) }
            payload.hangDiagnostics?.forEach { add(.hang, $0) }
            payload.cpuExceptionDiagnostics?.forEach { add(.cpuException, $0) }
            payload.diskWriteExceptionDiagnostics?.forEach { add(.diskWrite, $0) }
            if #available(iOS 16.0, *) {
                payload.appLaunchDiagnostics?.forEach { add(.launch, $0) }
            }
        }
        Task { await MetricKitForwarder12309.accept(bodies) }
    }
}
#endif

#if DEBUG
/// #12309 — the simulator never delivers MetricKit payloads, so the rig's
/// `-BL_METRICKIT_SAMPLE` hands the forwarder one hang shaped like
/// `MXHangDiagnostic.jsonRepresentation()`, through the same consent gate.
nonisolated enum MetricKitSample12309 {
    static let hangJSON = Data("""
    {"version":"1.0.0","callStackTree":{"callStackPerThread":true,"callStacks":[{"threadAttributed":true,\
    "callStackRootFrames":[{"binaryUUID":"70B89F27-1634-3580-A695-57CDB41D7743","offsetIntoBinaryTextSegment":123456,\
    "sampleCount":20,"binaryName":"Bain Luck","address":74565}]}]},\
    "diagnosticMetaData":{"appBuildVersion":"10","appVersion":"1.0.6","osVersion":"iPhone OS 27.0 (24A5260a)",\
    "deviceType":"iPhone18,2","hangDuration":"2.31 sec"}}
    """.utf8)

    static func bodies() -> [Data] {
        [MetricKitRecord12309.body(kind: .hang, payloadJSON: hangJSON, appVersion: "1.0.6", appBuild: "10",
                                   osVersion: "iPhone OS 27.0 (24A5260a)", deviceType: "iPhone18,2")]
            .compactMap { $0 }
    }
}
#endif
