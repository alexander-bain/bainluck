import Foundation

/// #13261 Row 15 — closed entry classification for App Clip telemetry.
/// Never carries URLs, entity IDs, names, or query strings (`181-C`).
nonisolated enum ClipEntryType13261: String, Equatable, Sendable {
    case game
    case market
    case invalid

    init(subject: SavedWidgetSubject10875?) {
        switch subject?.kind {
        case .game:
            self = .game
        case .market:
            self = .market
        case nil:
            self = .invalid
        }
    }
}

/// #13261 Row 15 — allowlisted App Clip event names.
nonisolated enum ClipTelemetryEventName13261: String, CaseIterable, Equatable, Sendable {
    case appClipOpen = "app_clip_open"
    case appClipAlertEnable = "app_clip_alert_enable"
    case appClipGetAppTap = "app_clip_get_app_tap"
}

/// #13261 Row 15 — lightweight, consent-gated App Clip telemetry boundary (`181-C`).
/// Fails closed: `isConsentGranted` defaults to `false` until explicitly set, and
/// emits zero events without consent. Compiled into both `BainLuckClip` and `Bain Luck`
/// (`BainLuckTests`).
nonisolated enum ClipTelemetry13261 {
    static let consentKey = "bainluck_clip_analytics_consent_v1"

    /// Test-only emitter hook so unit tests can observe post-consent packets without network I/O.
    nonisolated(unsafe) static var eventEmitterForTests: ((String, [String: Any]) -> Void)?

    static func isConsentGranted(defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: consentKey)
    }

    static func setConsentGranted(_ granted: Bool, defaults: UserDefaults = .standard) {
        defaults.set(granted, forKey: consentKey)
    }

    static func parameters(subject: SavedWidgetSubject10875?) -> [String: Any] {
        [
            "surface": "app_clip",
            "entry_type": ClipEntryType13261(subject: subject).rawValue,
        ]
    }

    @discardableResult
    static func emit(
        _ event: ClipTelemetryEventName13261,
        subject: SavedWidgetSubject10875?,
        defaults: UserDefaults = .standard,
        sink: ((String, [String: Any]) -> Void)? = nil
    ) -> Bool {
        guard isConsentGranted(defaults: defaults) else { return false }
        let params = parameters(subject: subject)
        (sink ?? eventEmitterForTests)?(event.rawValue, params)
        return true
    }

    @discardableResult
    static func recordOpen(
        subject: SavedWidgetSubject10875?,
        defaults: UserDefaults = .standard,
        sink: ((String, [String: Any]) -> Void)? = nil
    ) -> Bool {
        emit(.appClipOpen, subject: subject, defaults: defaults, sink: sink)
    }

    @discardableResult
    static func recordAlertEnable(
        subject: SavedWidgetSubject10875?,
        defaults: UserDefaults = .standard,
        sink: ((String, [String: Any]) -> Void)? = nil
    ) -> Bool {
        emit(.appClipAlertEnable, subject: subject, defaults: defaults, sink: sink)
    }

    @discardableResult
    static func recordGetAppTap(
        subject: SavedWidgetSubject10875?,
        defaults: UserDefaults = .standard,
        sink: ((String, [String: Any]) -> Void)? = nil
    ) -> Bool {
        emit(.appClipGetAppTap, subject: subject, defaults: defaults, sink: sink)
    }
}
