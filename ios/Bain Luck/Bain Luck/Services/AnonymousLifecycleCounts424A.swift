import Foundation
#if DEBUG
import Darwin
#endif

/// The three closed pre-consent lifecycle counts authorized under Ruling `424: A` (`#13261`).
enum AnonymousLifecycleEvent424A: String, Sendable, CaseIterable {
    case firstOpen = "first_open"
    case firstRunFinished = "first_run_finished"
    case previousSessionCrashed = "previous_session_crashed"

    fileprivate var sentName: String {
        switch self {
        case .firstOpen: return "bl_424a_open_ok"
        case .firstRunFinished: return "bl_424a_setup_ok"
        case .previousSessionCrashed: return "bl_424a_crash_ok"
        }
    }

    fileprivate var pendingName: String {
        switch self {
        case .firstOpen: return "bl_424a_open_p"
        case .firstRunFinished: return "bl_424a_setup_p"
        case .previousSessionCrashed: return "bl_424a_crash_p"
        }
    }

    fileprivate var attemptsName: String {
        switch self {
        case .firstOpen: return "bl_424a_open_n"
        case .firstRunFinished: return "bl_424a_setup_n"
        case .previousSessionCrashed: return "bl_424a_crash_n"
        }
    }
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
    static let sessionCountStorageName = "bainluck_session_count"
    static let maxDeliveryAttempts = 3

    private enum StorageName {
        static let initialized = "bl_424a_init"
        static let sessionActive = "bl_424a_active"
        static let sessionVersion = "bl_424a_ver"
    }

    /// Invokes `completion(true)` only when the server returns HTTP 2xx.
    ///
    /// A count is marked sent strictly after HTTP 2xx so an offline first open or an
    /// unprovisioned endpoint never drops the install count forever. A rare double count
    /// (server counted, HTTP 2xx response lost in transit) is the lesser error (#13820).
    typealias PayloadSender = @Sendable (
        _ payload: [String: String],
        _ url: URL,
        _ completion: @escaping @Sendable (Bool) -> Void
    ) -> Void

    private let defaults: UserDefaults
    private let lock = NSLock()
    private let nowProvider: @Sendable () -> Date
    private let appVersionProvider: @Sendable () -> String?
    private let deliveryAllowed: @Sendable () -> Bool
    private let sender: PayloadSender
    private var inFlightEvents: Set<AnonymousLifecycleEvent424A> = []

    /// Never count DEBUG runs, Xcode/xcodebuild simulator captures, or test runs
    /// against production counts (Fable #13820 ask 3).
    static var isProductionDeliveryAllowed: Bool {
        #if DEBUG || targetEnvironment(simulator)
        return false
        #else
        return ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil
        #endif
    }

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
        deliveryAllowed: @escaping @Sendable () -> Bool = {
            AnonymousLifecycleCounts424A.isProductionDeliveryAllowed
        },
        sender: PayloadSender? = nil
    ) {
        self.defaults = defaults
        self.nowProvider = now
        self.appVersionProvider = appVersionProvider
        self.deliveryAllowed = deliveryAllowed
        self.sender = sender ?? AnonymousLifecycleCounts424A.defaultPayloadSender
    }

    private static let defaultPayloadSender: PayloadSender = { payload, url, completion in
        guard isProductionDeliveryAllowed else {
            completion(false)
            return
        }
        guard let body = try? JSONEncoder().encode(payload) else {
            completion(false)
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpShouldHandleCookies = false
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        defaultSession.dataTask(with: request) { _, response, error in
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            let succeeded = error == nil && (200...299).contains(statusCode)
            completion(succeeded)
        }.resume()
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

    /// Initializes upgrade-safe `first_open` state, records unclean previous exit,
    /// and attempts delivery for any due pending counts (including retries after failed launches).
    func handleAppLaunch(
        appVersion: String? = nil,
        date: Date? = nil,
        isDebuggerAttached: Bool = AnonymousLifecycleCounts424A.isDebuggerAttached()
    ) {
        let resolvedDate = date ?? nowProvider()
        let resolvedVersion = Self.sanitizedAppVersion(appVersion ?? appVersionProvider())
        var eventsToDispatch: [AnonymousLifecycleEvent424A] = []

        lock.lock()
        initializeInstallStateIfNeededLocked()

        let previousActive = defaults.bool(forKey: StorageName.sessionActive)
        let previousVersion = defaults.string(forKey: StorageName.sessionVersion)
        if previousActive,
           previousVersion == resolvedVersion,
           !isDebuggerAttached,
           !isSentLocked(.previousSessionCrashed),
           !isPendingLocked(.previousSessionCrashed),
           !inFlightEvents.contains(.previousSessionCrashed) {
            defaults.set(true, forKey: AnonymousLifecycleEvent424A.previousSessionCrashed.pendingName)
        }

        defaults.set(true, forKey: StorageName.sessionActive)
        defaults.set(resolvedVersion, forKey: StorageName.sessionVersion)

        if deliveryAllowed() {
            for event in AnonymousLifecycleEvent424A.allCases where isPendingDueLocked(event) {
                if attemptBeginLocked(event) {
                    eventsToDispatch.append(event)
                }
            }
        }
        lock.unlock()

        for event in eventsToDispatch {
            let payload = Self.makePayload(event: event, appVersion: resolvedVersion, date: resolvedDate)
            dispatchIfClosed(event: event, payload: payload)
        }
    }

    /// Sends `first_run_finished` at most once per genuinely new install (never when setup
    /// had already been completed on an earlier version or sitting).
    func recordFirstRunFinished(
        wasAlreadyOnboarded: Bool? = nil,
        appVersion: String? = nil,
        date: Date? = nil
    ) {
        let resolvedDate = date ?? nowProvider()
        let resolvedVersion = Self.sanitizedAppVersion(appVersion ?? appVersionProvider())
        var shouldDispatch = false

        lock.lock()
        if isSentLocked(.firstRunFinished)
            || isPendingLocked(.firstRunFinished)
            || inFlightEvents.contains(.firstRunFinished) {
            lock.unlock()
            return
        }

        // Only send `first_run_finished` when setup had not already completed before
        // this finish (upgrade reopening the checklist sends nothing).
        let alreadyOnboarded = wasAlreadyOnboarded ?? defaults.bool(forKey: FirstRunStorageKeys212A.onboardedKey)
        if alreadyOnboarded {
            defaults.set(true, forKey: AnonymousLifecycleEvent424A.firstRunFinished.sentName)
            defaults.set(false, forKey: AnonymousLifecycleEvent424A.firstRunFinished.pendingName)
            lock.unlock()
            return
        }

        defaults.set(true, forKey: AnonymousLifecycleEvent424A.firstRunFinished.pendingName)
        if deliveryAllowed(), isPendingDueLocked(.firstRunFinished) {
            shouldDispatch = attemptBeginLocked(.firstRunFinished)
        }
        lock.unlock()

        if shouldDispatch {
            let payload = Self.makePayload(
                event: .firstRunFinished,
                appVersion: resolvedVersion,
                date: resolvedDate
            )
            dispatchIfClosed(event: .firstRunFinished, payload: payload)
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

    private func initializeInstallStateIfNeededLocked() {
        guard !defaults.bool(forKey: StorageName.initialized) else { return }
        defaults.set(true, forKey: StorageName.initialized)

        let wasOnboarded = defaults.bool(forKey: FirstRunStorageKeys212A.onboardedKey)
        let hadConsentChoice = defaults.string(forKey: TelemetryConsent.storageKey) != nil
        let hadPriorSessions = defaults.integer(forKey: Self.sessionCountStorageName) > 0

        if wasOnboarded || hadConsentChoice || hadPriorSessions {
            // Existing/upgraded phone: suppress `first_open` (and `first_run_finished` if
            // onboarding already completed) so updating to 1.0.8 never inflates new-install counts.
            defaults.set(true, forKey: AnonymousLifecycleEvent424A.firstOpen.sentName)
            defaults.set(false, forKey: AnonymousLifecycleEvent424A.firstOpen.pendingName)
            if wasOnboarded {
                defaults.set(true, forKey: AnonymousLifecycleEvent424A.firstRunFinished.sentName)
                defaults.set(false, forKey: AnonymousLifecycleEvent424A.firstRunFinished.pendingName)
            }
        } else if !isSentLocked(.firstOpen) {
            defaults.set(true, forKey: AnonymousLifecycleEvent424A.firstOpen.pendingName)
        }
    }

    private func isSentLocked(_ event: AnonymousLifecycleEvent424A) -> Bool {
        defaults.bool(forKey: event.sentName)
    }

    private func isPendingLocked(_ event: AnonymousLifecycleEvent424A) -> Bool {
        defaults.bool(forKey: event.pendingName)
    }

    private func isPendingDueLocked(_ event: AnonymousLifecycleEvent424A) -> Bool {
        !isSentLocked(event)
            && isPendingLocked(event)
            && !inFlightEvents.contains(event)
            && defaults.integer(forKey: event.attemptsName) < Self.maxDeliveryAttempts
    }

    private func attemptBeginLocked(_ event: AnonymousLifecycleEvent424A) -> Bool {
        guard isPendingDueLocked(event) else { return false }
        let nextAttempts = defaults.integer(forKey: event.attemptsName) + 1
        defaults.set(nextAttempts, forKey: event.attemptsName)
        inFlightEvents.insert(event)
        return true
    }

    private func finishAttempt(event: AnonymousLifecycleEvent424A, succeeded: Bool) {
        lock.lock()
        inFlightEvents.remove(event)
        if succeeded {
            defaults.set(true, forKey: event.sentName)
            defaults.set(false, forKey: event.pendingName)
        } else if defaults.integer(forKey: event.attemptsName) >= Self.maxDeliveryAttempts {
            defaults.set(false, forKey: event.pendingName)
        }
        lock.unlock()
    }

    private func dispatchIfClosed(event: AnonymousLifecycleEvent424A, payload: [String: String]) {
        guard Set(payload.keys).isSubset(of: Self.allowedPayloadKeys),
              let eventRaw = payload["event"],
              AnonymousLifecycleEvent424A(rawValue: eventRaw) == event else {
            finishAttempt(event: event, succeeded: false)
            return
        }
        sender(payload, Self.endpointURL) { [weak self] succeeded in
            self?.finishAttempt(event: event, succeeded: succeeded)
        }
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
        inFlightEvents.removeAll()
        defaults.removeObject(forKey: StorageName.initialized)
        defaults.removeObject(forKey: StorageName.sessionActive)
        defaults.removeObject(forKey: StorageName.sessionVersion)
        for event in AnonymousLifecycleEvent424A.allCases {
            defaults.removeObject(forKey: event.sentName)
            defaults.removeObject(forKey: event.pendingName)
            defaults.removeObject(forKey: event.attemptsName)
        }
        lock.unlock()
    }
}
