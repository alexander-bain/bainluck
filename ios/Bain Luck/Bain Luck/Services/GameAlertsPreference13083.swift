import Foundation
import UserNotifications
#if canImport(UIKit)
import UIKit
#endif

extension Notification.Name {
    /// Posted on the main actor whenever the on-device "Game alerts" switch changes
    /// so device registration (#13082) immediately syncs or clears `push_devices.notification_token`.
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

    /// Plain-English copy shared by Preferences and Manage pins (zero platform jargon).
    static let subtitle = "For games you pin: when it starts, when it is close late, and the final score."
    /// Shown as a tappable link when the switch is on but iPhone Settings notifications are off.
    static let settingsOffActionTitle = "Notifications are off in iPhone Settings — open Settings"

    #if os(iOS)
    /// Opens Bain Luck's Notifications settings page in iPhone Settings (iOS 16+),
    /// falling back to Bain Luck's top-level iPhone Settings page.
    static var appNotificationSettingsURL: URL? {
        URL(string: UIApplication.openNotificationSettingsURLString)
            ?? URL(string: UIApplication.openSettingsURLString)
    }

    static func openAppNotificationSettings(open: (URL) -> Void = { UIApplication.shared.open($0) }) {
        guard let url = appNotificationSettingsURL else { return }
        open(url)
    }
    #endif

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

    /// Returns the raw APNs token for `PUT /api/devices/{device_id}` (`push_devices.notification_token`)
    /// only when "Game alerts" is on, else nil. Morning Digest and `push_notifications.py` send via FCM
    /// to the separate `device_tokens` table (`token_kind = "fcm"`), which is unaffected when this returns nil.
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
