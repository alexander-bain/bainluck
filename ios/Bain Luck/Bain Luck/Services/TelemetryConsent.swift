import Foundation

/// The single NATIVE telemetry consent authority (Queue 311 Item A3, ruling 007 / #1632).
///
/// This is the native mirror of `lib/analytics/telemetryConsent.ts`. The web rail
/// already had one consent authority, deny-by-default, persisted across reloads,
/// with revocation; native had a privacy *allowlist* (`AnalyticsPrivacy`) but no
/// consent gate at all — it emitted from launch, to everyone, always.
///
/// Two things the native port had to get right that a code-only gate does not:
///
///  1. **`AnalyticsService.log` is not the only door.** The file called itself
///     "the ONE place this app hands an event to Firebase" and was mistaken:
///     `setUserId` and `setUserProperty` called `Analytics` directly. A gate on
///     `log()` alone would still ship a user identifier before any choice. Both
///     now route through this authority.
///
///  2. **Firebase auto-collects before our code runs.** `first_open`,
///     `session_start` and `screen_view` are emitted from SDK init, so no Swift
///     gate can be early enough. Deny-by-default therefore lives in
///     `Bain-Luck-Info.plist` (`FIREBASE_ANALYTICS_COLLECTION_ENABLED = NO`,
///     `FirebaseCrashlyticsCollectionEnabled = NO`) and collection is switched
///     ON here only on an explicit grant. The plist half is load-bearing: remove
///     it and this class becomes a gate on an open door.
///
/// Levels match the web exactly (`all` / `analytics` / `none` / no-choice), and
/// as on the web **no-choice is a denial**, not a soft default.
public enum ConsentLevel: String, Sendable, CaseIterable {
    /// Everything permitted.
    case all
    /// Analytics permitted. Distinct from `all` on the web (which also covers
    /// ad-adjacent providers); kept here so a level chosen on one surface reads
    /// identically on the other.
    case analytics
    /// Explicit refusal.
    case none
}

/// Which telemetry providers may run. Deliberately a struct of named providers
/// rather than a Bool, mirroring the web's `TelemetryDecision`: it is what makes
/// "which providers did this choice actually stop?" answerable in a test.
public struct TelemetryDecision: Equatable, Sendable {
    /// Firebase Analytics — events, screen views, user properties, user id.
    public let firebaseAnalytics: Bool
    /// Firebase Crashlytics — crash and non-fatal reports.
    public let crashlytics: Bool

    public static let nothing = TelemetryDecision(firebaseAnalytics: false, crashlytics: false)
}

/// Durability of the current choice, mirroring the web's `ConsentPersistence`.
public enum ConsentPersistence: String, Sendable {
    /// No explicit choice recorded yet.
    case unknown
    /// Written and read back exactly — it survives a relaunch.
    case saved
    /// Honoured for this launch only; durable storage refused it. The UI must
    /// not claim the choice was saved.
    case unavailable
}

/// The side of the world this authority controls. Injected so the decision logic
/// is testable without linking a live Firebase — the tests assert what the gate
/// DID, not merely what it decided.
public protocol TelemetrySink: AnyObject {
    func setAnalyticsCollectionEnabled(_ enabled: Bool)
    func setCrashlyticsCollectionEnabled(_ enabled: Bool)
    /// Clear analytics state already accumulated on device. Called on revocation
    /// so "no" reaches backwards as well as forwards.
    func resetAnalyticsData()
}

public final class TelemetryConsent: @unchecked Sendable {
    public static let shared = TelemetryConsent()

    /// Same semantic key as the web's `GA_CONFIG.CONSENT_STORAGE_KEY`. The stores
    /// are separate (UserDefaults vs localStorage) — a choice does not travel
    /// between surfaces — but the vocabulary is identical, so a value read on
    /// either side means the same thing.
    static let storageKey = "bainluck_telemetry_consent"

    private let defaults: UserDefaults
    private var sink: TelemetrySink
    private let lock = NSLock()

    private var current: ConsentLevel?
    private var initialized = false
    private var persistenceState: ConsentPersistence = .unknown

    init(defaults: UserDefaults = .standard, sink: TelemetrySink? = nil) {
        self.defaults = defaults
        self.sink = sink ?? FirebaseTelemetrySink()
    }

    // MARK: - Pure decision

    /// Whether a level counts as a grant. `nil` (no choice yet) and `.none` are
    /// BOTH denials — a first launch must produce zero telemetry, exactly like
    /// an explicit refusal.
    public static func isAnalyticsGranted(_ level: ConsentLevel?) -> Bool {
        level == .all || level == .analytics
    }

    /// The pure decision. One grant governs every provider.
    ///
    /// Crashlytics is gated with analytics rather than treated as essential.
    /// That is a deliberate call, and the stricter one: the web gates Speed
    /// Insights — also "just diagnostics" — under the same grant, and ruling 007
    /// asked for parity, not for a native carve-out. The cost is real and worth
    /// stating plainly: a user who never answers sends no crash reports.
    public static func decide(_ level: ConsentLevel?) -> TelemetryDecision {
        guard isAnalyticsGranted(level) else { return .nothing }
        return TelemetryDecision(firebaseAnalytics: true, crashlytics: true)
    }

    // MARK: - Store

    /// Hydrate from the persisted choice and apply it to the SDKs. Idempotent.
    /// Call once, immediately after `FirebaseApp.configure()`.
    @discardableResult
    public func initialize() -> ConsentLevel? {
        lock.lock()
        if initialized {
            let level = current
            lock.unlock()
            return level
        }
        initialized = true
        let stored = defaults.string(forKey: Self.storageKey)
        current = stored.flatMap(ConsentLevel.init(rawValue:))
        // A value read back OUT of storage is durable by definition.
        persistenceState = current == nil ? .unknown : .saved
        let level = current
        lock.unlock()

        apply(level)
        return level
    }

    /// The current level. `nil` means no explicit choice has been made.
    public var level: ConsentLevel? {
        lock.lock(); defer { lock.unlock() }
        return current
    }

    /// The current provider decision.
    public var decision: TelemetryDecision {
        Self.decide(level)
    }

    /// Whether telemetry may be emitted right now. The one question every
    /// emission site asks.
    public var isGranted: Bool {
        decision.firebaseAnalytics
    }

    /// Durability of the current choice.
    public var persistence: ConsentPersistence {
        lock.lock(); defer { lock.unlock() }
        return persistenceState
    }

    /// The recorded choice as it exists IN STORAGE, independent of whether this
    /// authority has been initialized yet (#1937).
    ///
    /// Deliberately touches nothing but `UserDefaults`. `initialize()` cannot be
    /// used for this question because it also APPLIES the choice to the Firebase
    /// SDKs, and must therefore run after `FirebaseApp.configure()` — while the
    /// question "do we still need to ask?" is asked earlier than that, from a
    /// SwiftUI `@State` initializer. Splitting the read from the apply is what
    /// lets both happen at the only time each of them can.
    public var storedLevel: ConsentLevel? {
        defaults.string(forKey: Self.storageKey).flatMap(ConsentLevel.init(rawValue:))
    }

    /// Whether a choice still needs to be asked for.
    ///
    /// Reads through to STORAGE when this authority has not been initialized
    /// yet, and that fallthrough is the whole fix for #1937 (Alex: "iOS asks
    /// every launch").
    ///
    /// The bug was ordering, not persistence — `set()` wrote and verified the
    /// value correctly the entire time. Swift runs a type's stored-property
    /// initializers BEFORE its `init()` body, so
    /// `@State private var showTelemetryConsent = TelemetryConsent.shared.needsChoice`
    /// in `Bain_LuckApp` was evaluated before that same `init()` called
    /// `initialize()`. `current` was still nil, so `needsChoice` answered `true`
    /// unconditionally, and `@State` captured that `true` for the launch. The
    /// comment above that property — "`true` only when no choice has ever been
    /// recorded" — described the intent exactly and the code never implemented it.
    ///
    /// Fixed HERE rather than by reordering the call site, because the call site
    /// could not be reordered: the `@State` seed cannot be moved after `init()`,
    /// and `initialize()` cannot be moved before `FirebaseApp.configure()`. A
    /// question that is safe to ask at any time should not depend on when it is
    /// asked.
    public var needsChoice: Bool {
        lock.lock()
        let hydrated = initialized
        let inMemory = current
        lock.unlock()
        return (hydrated ? inMemory : storedLevel) == nil
    }

    /// Record an explicit choice. The ONLY supported way to change consent.
    ///
    /// Returns whether the choice is DURABLE. The in-force effect is applied
    /// either way — a device that refuses to remember a refusal must still
    /// honour it now — but a caller about to tell the user "saved" has to check.
    @discardableResult
    public func set(_ level: ConsentLevel) -> ConsentPersistence {
        lock.lock()
        initialized = true
        current = level
        defaults.set(level.rawValue, forKey: Self.storageKey)
        // Verified write: `.saved` only after an exact readback, matching the
        // web's `storeConsent`.
        let readBack = defaults.string(forKey: Self.storageKey)
        persistenceState = (readBack == level.rawValue) ? .saved : .unavailable
        let resolved = persistenceState
        lock.unlock()

        apply(level)
        return resolved
    }

    // MARK: - Applying the choice

    private func apply(_ level: ConsentLevel?) {
        let decision = Self.decide(level)
        sink.setAnalyticsCollectionEnabled(decision.firebaseAnalytics)
        sink.setCrashlyticsCollectionEnabled(decision.crashlytics)
        if !decision.firebaseAnalytics {
            // Revocation reaches backwards too: drop the identifiers and events
            // already accumulated on device, rather than merely stopping new
            // ones. This is the native equivalent of the web's reload-to-unload.
            sink.resetAnalyticsData()
        }
    }

    // MARK: - Test seam

    /// Test-only reset. Production never calls this.
    func resetForTests(sink: TelemetrySink? = nil) {
        lock.lock()
        current = nil
        initialized = false
        persistenceState = .unknown
        if let sink { self.sink = sink }
        defaults.removeObject(forKey: Self.storageKey)
        lock.unlock()
    }
}
