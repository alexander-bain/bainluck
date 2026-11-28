import Foundation

/// Typed primitive wrapper so held analytics parameters serialize deterministically
/// to `UserDefaults` without losing `Bool` vs `Int` vs `Double` fidelity (`417: C`).
enum HeldAnalyticsValue417C: Codable, Equatable, Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)

    init?(any value: Any) {
        switch value {
        case let str as String:
            self = .string(str)
        case let b as Bool where type(of: value) == Bool.self:
            self = .bool(b)
        case let num as NSNumber:
            if CFGetTypeID(num) == CFBooleanGetTypeID() {
                self = .bool(num.boolValue)
            } else if let i = value as? Int {
                self = .int(i)
            } else {
                self = .double(num.doubleValue)
            }
        case let i as Int:
            self = .int(i)
        case let d as Double:
            self = .double(d)
        default:
            return nil
        }
    }

    var foundationValue: Any {
        switch self {
        case .string(let s): return s
        case .int(let i): return i
        case .double(let d): return d
        case .bool(let b): return b
        }
    }
}

struct HeldAnalyticsEvent417C: Codable, Equatable, Sendable {
    let name: String
    let parameters: [String: HeldAnalyticsValue417C]
    let occurredAtEpoch: TimeInterval

    func foundationParametersWithOccurredAt() -> [String: Any] {
        var out: [String: Any] = [:]
        out.reserveCapacity(parameters.count + 1)
        for (key, value) in parameters {
            out[key] = value.foundationValue
        }
        out["occurred_at_epoch"] = Int(occurredAtEpoch)
        return out
    }
}

/// On-device pre-consent event queue for `417: C` (`#13261`).
///
/// While the usage-stats choice has not been answered yet (`TelemetryConsent.needsChoice`),
/// events that would have been emitted are scrubbed immediately through `AnalyticsPrivacy`
/// and held locally on device (never touching the network). On **Allow** they are sent once
/// in order with `occurred_at_epoch`; on **No thanks** (or 30 days unanswered after first
/// open) they are deleted permanently.
final class HeldAnalyticsQueue417C: @unchecked Sendable {
    static let shared = HeldAnalyticsQueue417C()

    static let maxEvents = 200
    static let retentionSeconds: TimeInterval = 30 * 86_400
    static let eventsStorageKey = "bainluck_held_analytics_events_417c_v1"
    static let firstOpenStorageKey = "bainluck_held_analytics_first_open_417c_v1"

    private let defaults: UserDefaults
    private let lock = NSLock()
    private let nowProvider: @Sendable () -> Date

    init(
        defaults: UserDefaults = .standard,
        now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.defaults = defaults
        self.nowProvider = now
    }

    /// Anchor the 30-day expiration clock at first open and purge if already expired.
    func recordFirstOpenIfNeeded(now: Date? = nil) {
        let timestamp = (now ?? nowProvider()).timeIntervalSince1970
        lock.lock()
        defer { lock.unlock() }
        if defaults.object(forKey: Self.firstOpenStorageKey) == nil {
            defaults.set(timestamp, forKey: Self.firstOpenStorageKey)
        }
        _ = purgeIfExpiredLocked(nowEpoch: timestamp)
    }

    /// Enqueues a pre-consent event ONLY after passing it through `AnalyticsPrivacy.sanitize`,
    /// guaranteeing dropped keys (raw search queries, `result_id`, emails, URLs, tokens) never
    /// touch on-disk storage either.
    @discardableResult
    func enqueue(event name: String, parameters: [String: Any]? = nil, now: Date? = nil) -> Bool {
        guard let sanitized = AnalyticsPrivacy.sanitize(event: name, parameters: parameters) else {
            return false
        }

        var encodedParams: [String: HeldAnalyticsValue417C] = [:]
        for (key, value) in sanitized {
            if let wrapped = HeldAnalyticsValue417C(any: value) {
                encodedParams[key] = wrapped
            }
        }

        let timestamp = (now ?? nowProvider()).timeIntervalSince1970
        lock.lock()
        defer { lock.unlock() }

        if defaults.object(forKey: Self.firstOpenStorageKey) == nil {
            defaults.set(timestamp, forKey: Self.firstOpenStorageKey)
        }
        if purgeIfExpiredLocked(nowEpoch: timestamp) {
            return false
        }

        var events = loadEventsLocked()
        events.append(
            HeldAnalyticsEvent417C(
                name: name,
                parameters: encodedParams,
                occurredAtEpoch: timestamp
            )
        )
        if events.count > Self.maxEvents {
            events = Array(events.suffix(Self.maxEvents))
        }
        saveEventsLocked(events)
        return true
    }

    /// Atomically drains and clears all unexpired held events in chronological FIFO order.
    func drainForFlush(now: Date? = nil) -> [HeldAnalyticsEvent417C] {
        let timestamp = (now ?? nowProvider()).timeIntervalSince1970
        lock.lock()
        defer { lock.unlock() }

        if purgeIfExpiredLocked(nowEpoch: timestamp) {
            return []
        }

        let events = loadEventsLocked()
        defaults.removeObject(forKey: Self.eventsStorageKey)
        return events
    }

    /// Deletes all held events permanently (used on **No thanks** refusal / revocation).
    func clear() {
        lock.lock()
        defer { lock.unlock() }
        defaults.removeObject(forKey: Self.eventsStorageKey)
    }

    /// Removes held events if 30 days have elapsed since first open without an answer.
    @discardableResult
    func purgeIfExpired(now: Date? = nil) -> Bool {
        let timestamp = (now ?? nowProvider()).timeIntervalSince1970
        lock.lock()
        defer { lock.unlock() }
        return purgeIfExpiredLocked(nowEpoch: timestamp)
    }

    func snapshot(now: Date? = nil) -> [HeldAnalyticsEvent417C] {
        let timestamp = (now ?? nowProvider()).timeIntervalSince1970
        lock.lock()
        defer { lock.unlock() }
        if purgeIfExpiredLocked(nowEpoch: timestamp) {
            return []
        }
        return loadEventsLocked()
    }

    func resetForTests() {
        lock.lock()
        defer { lock.unlock() }
        defaults.removeObject(forKey: Self.eventsStorageKey)
        defaults.removeObject(forKey: Self.firstOpenStorageKey)
    }

    private func purgeIfExpiredLocked(nowEpoch: TimeInterval) -> Bool {
        guard let firstOpen = defaults.object(forKey: Self.firstOpenStorageKey) as? TimeInterval else {
            return false
        }
        guard nowEpoch - firstOpen >= Self.retentionSeconds else {
            return false
        }
        defaults.removeObject(forKey: Self.eventsStorageKey)
        return true
    }

    private func loadEventsLocked() -> [HeldAnalyticsEvent417C] {
        guard let data = defaults.data(forKey: Self.eventsStorageKey),
              let decoded = try? JSONDecoder().decode([HeldAnalyticsEvent417C].self, from: data) else {
            return []
        }
        return decoded
    }

    private func saveEventsLocked(_ events: [HeldAnalyticsEvent417C]) {
        guard let data = try? JSONEncoder().encode(events) else { return }
        defaults.set(data, forKey: Self.eventsStorageKey)
    }
}
