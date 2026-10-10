import Combine
import Foundation
import WatchConnectivity

/// Watch-only runtime. Never assumes that a phone grant grants Watch consent.
/// Sends only to the paired app; that receiver owns the existing GA4 boundary.
final class WatchTelemetry: NSObject, ObservableObject, WCSessionDelegate, @unchecked Sendable {
    @MainActor static let shared = WatchTelemetry()
    @MainActor @Published private(set) var enabled = false
    @MainActor @Published private(set) var consentSaved = true
    @MainActor private var buffer: WatchTelemetryBuffer
    @MainActor private var started = false
    @MainActor private var foregroundActive = false
    @MainActor private var sending = false
    @MainActor private var handshaking = false
    @MainActor private var myStuffTimeout: Task<Void, Never>?
    @MainActor private var readings = WatchTelemetryReadingTracker()
    @MainActor private var shownScreen: WatchTelemetrySurface?
    @MainActor private var currentScreen: WatchTelemetrySurface?
    @MainActor private var pendingContent: [WatchTelemetrySurface: TimeInterval] = [:]
    @MainActor private var launchStart = ProcessInfo.processInfo.systemUptime
    @MainActor private var screenStart: TimeInterval = 0
    @MainActor private var firstCardMS: Int?
    @MainActor private var firstScreen = true
    @MainActor private var screenCold = true
    private let defaults: UserDefaults
    private static let storageKey = "bainluck_watch_telemetry_buffer_v1"

    @MainActor private override init() {
        #if DEBUG
        if let fixture = WatchUIFixture.current {
            defaults = UserDefaults(suiteName: fixture.suite)!
        } else { defaults = .standard }
        #else
        defaults = .standard
        #endif
        buffer = WatchTelemetryBuffer.restore(defaults.data(forKey: Self.storageKey), now: Date())
        super.init()
        enabled = buffer.watchEpoch != nil
    }

    @MainActor func start() {
        #if DEBUG
        if WatchUIFixture.current != nil { return }
        #endif
        guard !started, WCSession.isSupported() else { return }
        guard WCSession.default.delegate == nil else { return }
        started = true
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    @MainActor func setEnabled(_ value: Bool) {
        buffer.setWatchConsent(value)
        enabled = value
        persist()
        if value {
            firstScreen = false // Never count a pre-consent wait as a consented cold launch.
            start(); synchronize()
        } else {
            currentScreen = nil; firstCardMS = nil; pendingContent.removeAll()
            readings.reset()
        }
    }

    @MainActor func foreground() {
        guard !foregroundActive else { return }
        foregroundActive = true
        start()
        if let shownScreen { screen(shownScreen) }
        record(.appOpen, surface: currentScreen ?? .game)
        refreshMyStuff()
        synchronize()
    }

    @MainActor func background() {
        guard foregroundActive else { return }
        foregroundActive = false
        myStuffTimeout?.cancel()
        WatchMyStuffStore.shared.disconnect()
        finishScreen()
        record(.appBackground, surface: currentScreen ?? .game)
        currentScreen = nil
    }

    @MainActor func screen(_ surface: WatchTelemetrySurface) {
        shownScreen = surface
        guard enabled, buffer.phoneGrant?.permits(at: Date()) == true else {
            currentScreen = nil; pendingContent.removeAll(); return
        }
        guard currentScreen != surface else { return }
        finishScreen()
        currentScreen = surface
        screenStart = firstScreen ? launchStart : ProcessInfo.processInfo.systemUptime
        firstCardMS = pendingContent.removeValue(forKey: surface).map {
            Int(min(3_600_000, max(0, ($0 - screenStart) * 1000)))
        }
        pendingContent.removeAll()
        screenCold = firstScreen
        firstScreen = false
        record(.screen, surface: surface)
    }

    @MainActor func content(_ surface: WatchTelemetrySurface) {
        guard enabled, buffer.phoneGrant?.permits(at: Date()) == true else { return }
        guard currentScreen == surface else {
            pendingContent[surface] = ProcessInfo.processInfo.systemUptime
            return
        }
        if firstCardMS == nil { firstCardMS = Self.milliseconds(since: screenStart) }
    }

    @MainActor func action(_ action: WatchTelemetryAction, surface: WatchTelemetrySurface) {
        record(.action, surface: surface, action: action)
    }

    @MainActor func refresh(_ surface: WatchTelemetrySurface, since start: TimeInterval,
                            outcome: WatchTelemetryOutcome, count: Int) {
        record(.refresh, surface: surface, outcome: outcome,
               durationMS: Self.milliseconds(since: start), count: min(100, max(0, count)))
    }

    @MainActor func refreshResult(_ surface: WatchTelemetrySurface, outcome: String, durationMS: Int, count: Int) {
        guard let typed = WatchTelemetryOutcome(rawValue: outcome) else { return }
        record(.refresh, surface: surface, outcome: typed, durationMS: durationMS,
               count: min(100, max(0, count)))
    }

    @MainActor func reading(_ surface: WatchTelemetrySurface, fetchedAt: Date?, saved: Bool, count: Int) {
        guard enabled, buffer.phoneGrant?.permits(at: Date()) == true, count > 0,
              readings.accept(surface, fetchedAt: fetchedAt, saved: saved) else { return }
        record(.reading, surface: surface, outcome: saved ? .saved : .fresh, count: min(100, max(0, count)))
    }

    @MainActor private func finishScreen() {
        guard let surface = currentScreen else { return }
        record(.timing, surface: surface, outcome: firstCardMS == nil ? .unknown : .success,
               durationMS: Self.milliseconds(since: screenStart), firstCard: firstCardMS ?? -1,
               cold: screenCold)
    }

    @MainActor private func record(_ kind: WatchTelemetryKind, surface: WatchTelemetrySurface,
                                   action: WatchTelemetryAction? = nil, outcome: WatchTelemetryOutcome? = nil,
                                   durationMS: Int? = nil, firstCard: Int? = nil,
                                   count: Int? = nil, cold: Bool? = nil) {
        #if DEBUG
        if WatchUIFixture.current != nil { return }
        #endif
        // Disabled telemetry must not encode and rewrite its empty buffer for
        // every foreground refresh. Consent changes persist in setEnabled.
        guard enabled else { return }
        let now = Date()
        buffer.append(WatchTelemetryRecord(recordedAt: now, kind: kind, surface: surface,
                                            action: action, outcome: outcome, durationMS: durationMS,
                                            firstCardMS: firstCard, count: count, cold: cold,
                                            appBuild: Self.appBuild), now: now)
        persist()
        flush()
    }

    private static var appBuild: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? ""
        let value = "\(version) (\(build))"
        guard !version.isEmpty, !build.isEmpty, value.utf8.count <= 64,
              value.unicodeScalars.allSatisfy({ "0123456789. ()".unicodeScalars.contains($0) }) else { return "unknown" }
        return value
    }

    private static func milliseconds(since start: TimeInterval) -> Int {
        let value = (ProcessInfo.processInfo.systemUptime - start) * 1000
        return value.isFinite ? Int(min(3_600_000, max(0, value))) : 0
    }

    @MainActor private func persist() {
        guard let data = try? JSONEncoder().encode(buffer), data.count <= WatchTelemetryBuffer.maxBytes else {
            defaults.removeObject(forKey: Self.storageKey)
            consentSaved = false
            return
        }
        defaults.set(data, forKey: Self.storageKey)
        consentSaved = defaults.data(forKey: Self.storageKey) == data
        // Revocation must not leave an old granted snapshot on disk after failed storage.
        if !enabled && !consentSaved { defaults.removeObject(forKey: Self.storageKey) }
    }

    @MainActor func refreshMyStuff() {
        #if DEBUG
        if WatchUIFixture.current != nil { return }
        #endif
        start()
        guard WCSession.default.activationState == .activated, WCSession.default.isReachable else {
            WatchMyStuffStore.shared.disconnect(); return
        }
        let token = WatchMyStuffStore.shared.beginHandshake()
        myStuffTimeout?.cancel()
        myStuffTimeout = Task {
            do { try await Task.sleep(for: .seconds(15)) } catch { return }
            WatchMyStuffStore.shared.failedHandshake(token)
        }
        WCSession.default.sendMessage([WatchMyStuffSnapshot.handshakeKey: token.uuidString], replyHandler: { reply in
            let echoed = reply[WatchMyStuffSnapshot.handshakeKey] as? String
            let data = reply[WatchMyStuffSnapshot.contextKey] as? Data
            Task { @MainActor in
                guard echoed == token.uuidString, let data else {
                    WatchMyStuffStore.shared.failedHandshake(token); return
                }
                WatchMyStuffStore.shared.receive(data, handshake: token)
            }
        }, errorHandler: { _ in
            Task { @MainActor in WatchMyStuffStore.shared.failedHandshake(token) }
        })
    }

    @MainActor private func synchronize() {
        guard enabled, !handshaking, WCSession.default.activationState == .activated,
              WCSession.default.isReachable else { return }
        handshaking = true
        let localEpoch = buffer.watchEpoch
        WCSession.default.sendMessage(["watch_telemetry_handshake": 1], replyHandler: { reply in
            let data = reply["watch_telemetry_grant"] as? Data
            Task { @MainActor in
                self.handshaking = false
                guard self.enabled, self.buffer.watchEpoch == localEpoch else { return }
                self.applyGrant(data)
            }
        }, errorHandler: { _ in
            Task { @MainActor in self.handshaking = false }
        })
    }

    @MainActor private func applyGrant(_ data: Data?) {
        let grant: WatchTelemetryGrant?
        if let data, data.count <= 512 { grant = try? JSONDecoder().decode(WatchTelemetryGrant.self, from: data) }
        else { grant = nil }
        let previous = buffer.phoneGrant?.epoch
        buffer.setPhoneGrant(grant, now: Date())
        if previous != buffer.phoneGrant?.epoch {
            readings.reset()
            currentScreen = nil; firstCardMS = nil; pendingContent.removeAll()
            firstScreen = false
            if let shownScreen { screen(shownScreen) }
        }
        persist()
        flush()
    }

    @MainActor private func flush() {
        guard enabled, !sending, WCSession.default.activationState == .activated,
              WCSession.default.isReachable, let batch = buffer.batch(now: Date()),
              let bytes = try? JSONEncoder().encode(batch) else { return }
        sending = true
        WCSession.default.sendMessage(["watch_telemetry_batch": bytes], replyHandler: { reply in
            let grant = reply["watch_telemetry_grant"] as? Data
            let ids = (reply["watch_telemetry_ack"] as? [String] ?? []).compactMap(UUID.init(uuidString:))
            Task { @MainActor in
                self.sending = false
                let accepted = Set(ids).intersection(Set(batch.records.map(\.id)))
                self.buffer.acknowledge(accepted, phoneEpoch: batch.phoneEpoch, watchEpoch: batch.watchEpoch)
                // A changed phone epoch immediately discards the stale queue.
                // applyGrant may flush, so only apply a changed grant here.
                if let grant, grant.count <= 512 {
                    let decoded = try? JSONDecoder().decode(WatchTelemetryGrant.self, from: grant)
                    if decoded?.epoch != self.buffer.phoneGrant?.epoch { self.applyGrant(grant) }
                }
                self.persist()
                // Missing/rejected acknowledgements never produce an immediate retry loop.
                if !accepted.isEmpty { self.flush() }
            }
        }, errorHandler: { _ in
            Task { @MainActor in self.sending = false }
        })
    }

    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState,
                 error: Error?) {
        Task { @MainActor in self.refreshMyStuff(); self.synchronize() }
    }
    nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
        Task { @MainActor in self.refreshMyStuff(); self.synchronize() }
    }
    nonisolated func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        let hasGrant = applicationContext.keys.contains("watch_telemetry_grant")
        let data = applicationContext["watch_telemetry_grant"] as? Data
        let product = applicationContext[WatchMyStuffSnapshot.contextKey] as? Data
        Task { @MainActor in
            if hasGrant { self.applyGrant(data) }
            if let product { WatchMyStuffStore.shared.receive(product) }
        }
    }
}
