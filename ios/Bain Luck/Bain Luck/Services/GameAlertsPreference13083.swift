import Foundation
import UserNotifications

extension Notification.Name {
    /// Posted on the main actor whenever the on-device "Game alerts" switch changes
    /// so device registration (#13082) immediately syncs or clears `notification_token`.
    static let gameAlertsPreferenceDidChange13083 = Notification.Name("bainluck.gameAlertsPreferenceDidChange.13083")
}

/// #13083 / Rulings 212: A, 261: A, 262: A — single on-device "Game alerts" switch
/// kept in `UserDefaults` (no server migration), plus the shared opt-in helper for
/// Builder C's contextual ask-at-the-pin (#13084).
@MainActor
final class GameAlertsPreference13083 {
    static let shared = GameAlertsPreference13083()

    static let enabledKey = "bainluck.gameAlertsEnabled.13083"
    static let pinPromptHandledKey = "bainluck.gameAlertsPinPromptHandled.13083"

    private let defaults: UserDefaults
    private let center: NotificationCenter

    init(defaults: UserDefaults = .standard, center: NotificationCenter = .default) {
        self.defaults = defaults
        self.center = center
    }

    /// True when the reader has opted this phone into pinned-game alerts (262: A).
    var isEnabled: Bool {
        defaults.bool(forKey: Self.enabledKey)
    }

    /// True once the reader has either accepted or declined the contextual ask at the pin (212: A).
    var hasHandledPinPrompt: Bool {
        defaults.bool(forKey: Self.pinPromptHandledKey)
    }

    /// True when Builder C's contextual ask at the pin (#13084) should be offered:
    /// the switch is off and the reader has not already responded to the prompt.
    var shouldOfferPinPrompt: Bool {
        !isEnabled && !hasHandledPinPrompt
    }

    /// Returns the raw APNs token only when "Game alerts" is on, else nil so device sync
    /// (#13082) clears `notification_token` on `PUT /api/devices/{device_id}` when off.
    func effectiveNotificationToken(rawToken: String?) -> String? {
        guard isEnabled, let rawToken, !rawToken.isEmpty else { return nil }
        return rawToken
    }

    /// Updates the on-device switch and notifies observers (such as device sync).
    func setEnabled(_ enabled: Bool) {
        let changed = isEnabled != enabled
        defaults.set(enabled, forKey: Self.enabledKey)
        if enabled {
            defaults.set(true, forKey: Self.pinPromptHandledKey)
        }
        if changed {
            center.post(name: .gameAlertsPreferenceDidChange13083, object: self)
        }
    }

    /// Shared opt-in path used by Settings and Builder C's contextual ask at the pin (#13084):
    /// flips the single on-device switch on and requests standard iOS notifications (261: A).
    @discardableResult
    func optInAndRequestPermission(
        requestPermission: () async -> UNAuthorizationStatus = {
            await NotificationManager.shared.requestStandardPermissionForGameAlerts()
        }
    ) async -> UNAuthorizationStatus {
        setEnabled(true)
        return await requestPermission()
    }

    /// Records that the reader declined the contextual ask at the pin so we never nag on later pins.
    func declinePinPrompt() {
        defaults.set(true, forKey: Self.pinPromptHandledKey)
        if isEnabled {
            setEnabled(false)
        }
    }
}
