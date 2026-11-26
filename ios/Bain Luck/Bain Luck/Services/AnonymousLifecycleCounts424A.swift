import Foundation
#if DEBUG
import Darwin
#endif

/// The three closed pre-consent lifecycle counts authorized under Ruling `424: A` (`#13261`).
enum AnonymousLifecycleEvent424A: String, Sendable, CaseIterable {
    case firstOpen = "first_open"
    case firstRunFinished = "first_run_finished"
    case previousSessionCrashed = "previous_session_crashed"
}

/// Strictly isolated path for `424: A` anonymous lifecycle counts.
///
/// Separate by construction from `AnalyticsService`, `TelemetryConsent`, `AuthManager`,
/// and `APIClient` so no bug in consent-gated analytics can leak identifiers or fields
/// here, and no user/device/install/vendor/advertising id ever joins these counts.
final class AnonymousLifecycleCounts424A: @unchecked Sendable {
    static let shared = AnonymousLifecycleCounts424A()

    /// Exact reader-facing sentence approved for `424: A` (`#13261#issuecomment-7173621763`).
    static let privacyDisclosureSentence =
        "Without a yes, the app sends only three anonymous counts: that it was opened for the first time, that setup was finished, and whether it crashed. Nothing in them says who you are."

    static let endpointURL = URL(string: "https://api.bainluck.com/api/telemetry/anonymous-counts")!
    static let allowedPayloadKeys: Set<String> = ["event", "app_version", "day"]

    private enum StorageName {
        static let sentFirstOpen = "bl_424a_open"
        static let sentFirstRunFinished = "bl_424a_setup"
        static let sentCrashed = "bl_424a_crash"
        static let sessionActive = "bl_424a_active"
        static let sessionVersion = "bl_424a_ver"
    }

    typealias PayloadSender = @Sendable (_ payload: [String: String], _ url: URL) -> Void

    private let defaults: UserDefaults
    private let lock = NSLock()
    private let nowProvider: @Sendable () -> Date
    private let appVersionProvider: @Sendable () -> String?
    private let sender: PayloadSender

    private static let defaultSession: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.httpShouldSetCookies = false
        config.httpCookieAcceptPolicy = .never
        config.httpCookieStorage = nil
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        config.timeoutIntervalForRequest = 5
        config.timeoutIntervalForResource = 5
        return URLSession(configuration: config)
    }()

    init(
        defaults: UserDefaults = .standard,
        now: @escaping @Sendable () -> Date = { Date() },
        appVersionProvider: @escaping @Sendable () -> String? = {
            Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        },
        sender: PayloadSender? = nil
    ) {
        self.defaults = defaults
        self.nowProvider = now
        self.appVersionProvider = appVersionProvider
        self.sender = sender ?? AnonymousLifecycleCounts424A.defaultPayloadSender
    }

    private static let defaultPayloadSender: PayloadSender = { payload, url in
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil {
            return
        }
        guard let body = try? JSONEncoder().encode(payload) else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpShouldHandleCookies = false
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        defaultSession.dataTask(with: request) { _, _, _ in }.resume()
    }

    // MARK: - Closed payload builders

    static func utcDayString(from date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    static func sanitizedAppVersion(_ raw: String?) -> String {
        guard let raw else { return "unknown" }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let allowed = CharacterSet(charactersIn: "0123456789.")
        let filtered = String(trimmed.unicodeScalars.filter { allowed.contains($0) }.prefix(16))
        return filtered.isEmpty ? "unknown" : filtered
    }

    static func makePayload(
        event: AnonymousLifecycleEvent424A,
        appVersion: String?,
        date: Date
    ) -> [String: String] {
        [
            "event": event.rawValue,
            "app_version": sanitizedAppVersion(appVersion),
            "day": utcDayString(from: date),
        ]
    }

    // MARK: - Lifecycle entry points (at most once per install per event)

    /// Checks whether the previous active session exited abnormally (crashed), marks
    /// the current session active, and sends `first_open` if this install hasn't yet.
    func handleAppLaunch(
        appVersion: String? = nil,
        date: Date? = nil,
        isDebuggerAttached: Bool = AnonymousLifecycleCounts424A.isDebuggerAttached()
    ) {
        let resolvedDate = date ?? nowProvider()
        let resolvedVersion = Self.sanitizedAppVersion(appVersion ?? appVersionProvider())
        var payloadsToSend: [[String: String]] = []

        lock.lock()
        let previousActive = defaults.bool(forKey: StorageName.sessionActive)
        let previousVersion = defaults.string(forKey: StorageName.sessionVersion)
        if previousActive,
           previousVersion == resolvedVersion,
           !isDebuggerAttached,
           !defaults.bool(forKey: StorageName.sentCrashed) {
            defaults.set(true, forKey: StorageName.sentCrashed)
            payloadsToSend.append(
                Self.makePayload(
                    event: .previousSessionCrashed,
                    appVersion: resolvedVersion,
                    date: resolvedDate
                )
            )
        }

        defaults.set(true, forKey: StorageName.sessionActive)
        defaults.set(resolvedVersion, forKey: StorageName.sessionVersion)

        if !defaults.bool(forKey: StorageName.sentFirstOpen) {
            defaults.set(true, forKey: StorageName.sentFirstOpen)
            payloadsToSend.append(
                Self.makePayload(
                    event: .firstOpen,
                    appVersion: resolvedVersion,
                    date: resolvedDate
                )
            )
        }
        lock.unlock()

        for payload in payloadsToSend {
            dispatchIfClosed(payload)
        }
    }

    /// Sends `first_run_finished` at most once per install.
    func recordFirstRunFinished(appVersion: String? = nil, date: Date? = nil) {
        let resolvedDate = date ?? nowProvider()
        let resolvedVersion = Self.sanitizedAppVersion(appVersion ?? appVersionProvider())
        var payload: [String: String]?

        lock.lock()
        if !defaults.bool(forKey: StorageName.sentFirstRunFinished) {
            defaults.set(true, forKey: StorageName.sentFirstRunFinished)
            payload = Self.makePayload(
                event: .firstRunFinished,
                appVersion: resolvedVersion,
                date: resolvedDate
            )
        }
        lock.unlock()

        if let payload {
            dispatchIfClosed(payload)
        }
    }

    /// Clears the unclean-exit marker when the app cleanly leaves the foreground or exits.
    func markSessionCleanBackgroundOrExit() {
        lock.lock()
        defaults.set(false, forKey: StorageName.sessionActive)
        lock.unlock()
    }

    /// Re-arms the active foreground marker when the app returns to foreground.
    func markSessionBecameActive(appVersion: String? = nil) {
        let resolvedVersion = Self.sanitizedAppVersion(appVersion ?? appVersionProvider())
        lock.lock()
        defaults.set(true, forKey: StorageName.sessionActive)
        defaults.set(resolvedVersion, forKey: StorageName.sessionVersion)
        lock.unlock()
    }

    private func dispatchIfClosed(_ payload: [String: String]) {
        guard Set(payload.keys).isSubset(of: Self.allowedPayloadKeys),
              let eventRaw = payload["event"],
              AnonymousLifecycleEvent424A(rawValue: eventRaw) != nil else {
            return
        }
        sender(payload, Self.endpointURL)
    }

    static func isDebuggerAttached() -> Bool {
        #if DEBUG
        var info = kinfo_proc()
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()]
        var size = MemoryLayout<kinfo_proc>.stride
        let result = sysctl(&mib, UInt32(mib.count), &info, &size, nil, 0)
        return result == 0 && (info.kp_proc.p_flag & P_TRACED) != 0
        #else
        return false
        #endif
    }

    func resetForTests() {
        lock.lock()
        defaults.removeObject(forKey: StorageName.sentFirstOpen)
        defaults.removeObject(forKey: StorageName.sentFirstRunFinished)
        defaults.removeObject(forKey: StorageName.sentCrashed)
        defaults.removeObject(forKey: StorageName.sessionActive)
        defaults.removeObject(forKey: StorageName.sessionVersion)
        lock.unlock()
    }
}
