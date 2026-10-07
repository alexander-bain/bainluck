#if os(iOS)
import Foundation
import WatchConnectivity

/// Single iPhone WatchConnectivity owner. Telemetry remains best-effort and
/// consent gated; receiving a packet never enables Firebase or identifies a user.
final class WatchTelemetryReceiver: NSObject, WCSessionDelegate, @unchecked Sendable {
    @MainActor static let shared = WatchTelemetryReceiver()
    @MainActor private var started = false
    @MainActor private var observer: NSObjectProtocol?
    private let defaults: UserDefaults
    private static let seenKey = "bainluck_watch_telemetry_seen_v1"

    private override init() { defaults = .standard; super.init() }

    @MainActor func start() {
        guard !started, WCSession.isSupported() else { return }
        // A future connectivity feature must compose with this owner, not replace it.
        guard WCSession.default.delegate == nil else { return }
        started = true
        WCSession.default.delegate = self
        WCSession.default.activate()
        observer = NotificationCenter.default.addObserver(
            forName: TelemetryConsent.didChange, object: nil, queue: nil
        ) { _ in Task { @MainActor in self.publishGrant() } }
    }

    @MainActor private func grantData() -> Data {
        guard let epoch = TelemetryConsent.shared.analyticsAuthorizationEpoch else { return Data() }
        let grant = WatchTelemetryGrant(epoch: epoch, validUntil: Date().addingTimeInterval(24 * 60 * 60))
        return (try? JSONEncoder().encode(grant)) ?? Data()
    }

    @MainActor private func publishGrant() {
        guard WCSession.default.activationState == .activated else { return }
        var context = WCSession.default.applicationContext
        context["watch_telemetry_grant"] = grantData()
        // The latest context replaces the previous grant; no unlimited transfer queue.
        try? WCSession.default.updateApplicationContext(context)
        if !TelemetryConsent.shared.isGranted { defaults.removeObject(forKey: Self.seenKey) }
    }

    @MainActor private func receive(_ data: Data) -> [String] {
        let now = Date()
        let epoch = TelemetryConsent.shared.analyticsAuthorizationEpoch
        var seen: [String: Double] = [:]
        if let raw = defaults.data(forKey: Self.seenKey), raw.count <= 48 * 1024,
           let decoded = try? JSONDecoder().decode([String: Double].self, from: raw) {
            seen = decoded.filter { UUID(uuidString: $0.key) != nil && $0.value.isFinite
                && now.timeIntervalSince1970 - $0.value >= 0
                && now.timeIntervalSince1970 - $0.value < WatchTelemetryBuffer.maxAge }
        }
        let accepted = WatchTelemetryIngress.accept(data, phoneEpoch: epoch, now: now,
                                                     seen: Set(seen.keys.compactMap(UUID.init(uuidString:))))
        guard !accepted.acknowledgement.isEmpty else { return [] }
        for id in accepted.acknowledgement { seen[id.uuidString] = now.timeIntervalSince1970 }
        let recent = seen.sorted { $0.value > $1.value }.prefix(512)
        let bounded = Dictionary(uniqueKeysWithValues: recent.map { ($0.key, $0.value) })
        guard let stored = try? JSONEncoder().encode(bounded) else { return [] }
        defaults.set(stored, forKey: Self.seenKey)
        guard defaults.data(forKey: Self.seenKey) == stored,
              epoch == TelemetryConsent.shared.analyticsAuthorizationEpoch else { return [] }
        // Record the bounded dedupe receipt before emission. A process crash in
        // this gap may lose diagnostics; retry must not double-count them.
        for event in accepted.records {
            guard epoch == TelemetryConsent.shared.analyticsAuthorizationEpoch else { return [] }
            var parameters = event.analyticsParameters
            parameters["transport_delay_ms"] = Int(min(86_400_000, max(0, now.timeIntervalSince(event.recordedAt) * 1000)))
            AnalyticsService.log(event.kind.rawValue, parameters, authorizationEpoch: epoch)
        }
        return accepted.acknowledgement.map(\.uuidString)
    }

    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                 replyHandler: @escaping ([String: Any]) -> Void) {
        // Extract only the typed, bounded protocol values before crossing actors.
        let handshake = message["watch_telemetry_handshake"] as? Int == 1
        let data = message["watch_telemetry_batch"] as? Data
        Task { @MainActor in
            if handshake { replyHandler(["watch_telemetry_grant": self.grantData()]) }
            else if let data {
                replyHandler(["watch_telemetry_ack": self.receive(data),
                              "watch_telemetry_grant": self.grantData()])
            }
            else { replyHandler([:]) }
        }
    }
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState,
                 error: Error?) {
        Task { @MainActor in self.publishGrant() }
    }
    nonisolated func sessionDidBecomeInactive(_ session: WCSession) { }
    nonisolated func sessionDidDeactivate(_ session: WCSession) { session.activate() }
}
#endif
