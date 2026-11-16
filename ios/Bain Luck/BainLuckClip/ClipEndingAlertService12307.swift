import Security
import SwiftUI
import UIKit
import UserNotifications

/// #12307 / 177-A — "Tell me how it ends" for the App Clip: the clip's push
/// token, sent with this one game as its only pin, as a `platform: appclip`
/// row (agreed on #11934; the table is #12766). No account and no prompt: an
/// App Clip may notify for 8 hours if the reader left that on in its card.
///
/// Needs, before it can work end to end (Alex's, not code): the clip's App ID
/// gains Push Notifications, its Info.plist sets
/// `NSAppClipRequestEphemeralUserNotification`, and #12766's table is live.
/// Until then the request fails and the button stays offered.
@Observable
@MainActor
final class ClipEndingAlertService12307 {
    private(set) var state: ClipEndingAlert12307.State = .offered
    private var pendingEventID: Int?
    static let shared = ClipEndingAlertService12307()

    func request(eventID: Int) async {
        guard state != .working else { return }
        state = .working
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .ephemeral, .authorized, .provisional:
            pendingEventID = eventID
            UIApplication.shared.registerForRemoteNotifications()
        default:
            state = .unavailable
        }
    }

    func registered(token: Data) async {
        guard let eventID = pendingEventID else { return }
        pendingEventID = nil
        let hex = token.map { String(format: "%02x", $0) }.joined()
        state = await Self.put(token: hex, eventID: eventID) ? .set : .offered
    }

    func registrationFailed() {
        pendingEventID = nil
        state = .offered
    }

    /// The device row (#12766 `PUT /api/devices/{id}`): the whole state, the
    /// clip's own id and secret. True only on a 2xx.
    static func put(token: String, eventID: Int) async -> Bool {
        let identity = ClipDeviceIdentity12307.current()
        guard let url = URL(string: "\(ClipInvocation12307.apiBase)/api/devices/\(identity.id.uuidString.lowercased())")
        else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(identity.secret, forHTTPHeaderField: "X-Device-Secret")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body(token: token, eventID: eventID))
        guard let (_, response) = try? await URLSession.shared.data(for: request),
              let code = (response as? HTTPURLResponse)?.statusCode else { return false }
        return (200..<300).contains(code)
    }

    nonisolated static func body(token: String, eventID: Int) -> [String: Any] {
        [
            "platform": "appclip",
            "apns_env": apnsEnvironment,
            "notification_token": token,
            "os_major": ProcessInfo.processInfo.operatingSystemVersion.majorVersion,
            "app_version": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
            "pinned_event_ids": [eventID],
            "pinned_market_ids": [Int](),
        ]
    }

    nonisolated static var apnsEnvironment: String {
        #if DEBUG
        "sandbox"
        #else
        "production"
        #endif
    }
}

/// The clip's device id and secret: made once, kept on this phone. The server
/// stores only the secret's SHA-256 (#12766).
struct ClipDeviceIdentity12307: Equatable {
    let id: UUID
    let secret: String

    private static let idKey = "clipDeviceID12307"
    private static let secretKey = "clipDeviceSecret12307"

    static func current(defaults: UserDefaults = .standard) -> ClipDeviceIdentity12307 {
        if let raw = defaults.string(forKey: idKey), let id = UUID(uuidString: raw),
           let secret = defaults.string(forKey: secretKey), secret.count >= 43 {
            return ClipDeviceIdentity12307(id: id, secret: secret)
        }
        let made = ClipDeviceIdentity12307(id: UUID(), secret: makeSecret())
        defaults.set(made.id.uuidString, forKey: idKey)
        defaults.set(made.secret, forKey: secretKey)
        return made
    }

    /// 32 random bytes, base64url without padding: 43 printable characters.
    static func makeSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        if SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) != errSecSuccess {
            bytes = (0..<32).map { _ in UInt8.random(in: 0...255) }
        }
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

/// The clip's app delegate: only the push-token callbacks.
final class ClipAppDelegate12307: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in await ClipEndingAlertService12307.shared.registered(token: deviceToken) }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in ClipEndingAlertService12307.shared.registrationFailed() }
    }
}
