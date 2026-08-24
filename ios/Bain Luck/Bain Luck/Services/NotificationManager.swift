//
//  NotificationManager.swift
//  Bain Luck
//
//  Created by bain on 5/13/26.
//

import Combine
import FirebaseMessaging
import Foundation
import os
import UserNotifications
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "notifications")

/// Manages push notification registration and device token capture.
///
/// Usage: Create as a `@StateObject` in the app entry point and call
/// `requestPermissionAfterDelay()` once the app has loaded. When the user
/// is authenticated, call `setUser(id:)` so the token registration
/// includes the user identity.
final class NotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate, MessagingDelegate {
    static let shared = NotificationManager()

    /// The kinds of push token this app registers. Both are sent to the backend:
    /// the APNS hex is the historical path and the fallback if messaging init
    /// fails, and the FCM registration token is the only one the digest sender
    /// can actually deliver to (#1159).
    enum TokenKind: String {
        case apns
        case fcm
    }

    @Published var isPermissionGranted = false

    /// Why APNS registration failed, if it did — surfaced, not just logged.
    ///
    /// #2109 / UX-P125 item 4. The verdict on the zero-registration bug was
    /// "client side, before the wire", and the reason it took a verdict to
    /// establish that is sitting right here: the failure callback logged at
    /// `.info`, called the failure "skipped", and stored nothing. So a hard
    /// entitlement rejection and a simulator with no APNS at all produced the
    /// same single grey line, in a log nobody reads, on a device nobody is
    /// attached to — and `isPermissionGranted == true` alongside it read as
    /// "push is set up". Permission granted and registration failed is exactly
    /// the state the report described, and nothing in the app could say so.
    ///
    /// Non-nil here means: the OS refused to issue a device token. There will be
    /// no APNS token, therefore no FCM token, therefore no row in
    /// `device_tokens`, therefore no delivery — however green the permission
    /// prompt looked.
    @Published private(set) var apnsRegistrationFailure: String?

    /// True once APNS has handed us a device token. Paired with
    /// `isPermissionGranted` this distinguishes the three states that used to
    /// look alike: not asked, asked-and-refused, and granted-but-unregistered.
    @Published private(set) var isAPNSRegistered = false

    /// The raw APNS device token, hex-encoded. FCM CANNOT send to this.
    private(set) var deviceToken: String?

    /// The Firebase registration token. The digest CAN send to this.
    private(set) var fcmToken: String?

    /// The authenticated user's ID (set after sign-in).
    private var userId: Int?

    /// The token value last successfully registered, PER KIND.
    ///
    /// This used to be a single `tokenRegistered` Bool for a single token, and
    /// leaving it that way would have been the quiet way to lose this whole
    /// item: the second registration would hit the `guard` and return, so the
    /// FCM token — the entire point of the change — would never reach the
    /// backend, while the logs happily reported a successful registration.
    ///
    /// Keyed by value rather than a per-kind Bool so a ROTATED token
    /// re-registers instead of being mistaken for one already sent.
    private var registeredTokenByKind: [TokenKind: String] = [:]

    /// Reference to the nav coordinator for deep linking from notifications.
    weak var navCoordinator: NavigationCoordinator?

    private override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
        registerNotificationCategories()
    }

    // MARK: - Notification routing (#2060 item 6)

    /// Where a notification interaction lands. An explicit `.none` rather than an
    /// Optional: "this payload names nowhere" is a real answer a test should be
    /// able to assert, not an absence.
    nonisolated enum NotificationDestination: Equatable {
        case labeling
        case url(URL)
        case event(id: Int)
        case market(id: Int)
        case none
    }

    // MARK: - Notification categories (#2060 item 6)

    /// The category the morning digest's admin variant declares, and the action
    /// on it. Must match `LABELING_NOTIFICATION_CATEGORY` in
    /// `backend/app/utils/morning_digest.py`; asserted by
    /// `LabelingNudgeContractTests`.
    static let labelingCategoryId = "morning_digest_admin"
    static let labelingActionId = "label_today"

    /// Where one notification interaction should land.
    ///
    /// ── PURE, BECAUSE THE ORDERING IS THE BUG AND A GREP CANNOT CATCH IT ─────
    ///
    /// `UNNotificationResponse` cannot be constructed in a test without private
    /// API, so the delegate method itself is untestable and the only guard on it
    /// was a source grep asserting the action check appears ABOVE the `url` read.
    /// Mutation M14 defanged the condition without moving it and the grep stayed
    /// green — it was checking line order, which is a proxy for the decision, not
    /// the decision.
    ///
    /// So the decision moves here, where a test can execute it. `static` and
    /// `nonisolated` for the same reason `driftRefusalMessage` is: a test should
    /// not need the manager or the main actor to ask what a payload means.
    ///
    /// The action takes precedence over `url` because BOTH keys are present on an
    /// admin digest — the action's destination is the labelling queue, the body
    /// tap's is the market. Reading `url` first sends every action tap to the
    /// market: the button is there, it animates, and it silently does the wrong
    /// thing.
    nonisolated static func notificationDestination(
        actionIdentifier: String,
        userInfo: [AnyHashable: Any]
    ) -> NotificationDestination {
        if actionIdentifier == labelingActionId {
            return .labeling
        }
        if let urlString = userInfo["url"] as? String,
           let url = URL(string: urlString) {
            return .url(url)
        }
        if let eventIdString = userInfo["event_id"] as? String,
           let eventId = Int(eventIdString) {
            return .event(id: eventId)
        }
        if let marketIdString = userInfo["market_id"] as? String,
           let marketId = Int(marketIdString) {
            return .market(id: marketId)
        }
        return .none
    }

    /// Registering the category is what makes the "Label today" button exist.
    ///
    /// ** REGISTERED UNCONDITIONALLY, SURFACED CONDITIONALLY. ** Categories are a
    /// client-side table consulted when a push names one, so registering costs
    /// nothing and shows nobody anything. The server puts `category` on the
    /// payload only for an admin recipient, so on every other device this entry
    /// is simply never referenced — the gate is on the send, where it can be
    /// tested against the recipient's identity, not on the client, where it would
    /// depend on a build flag being right.
    private func registerNotificationCategories() {
        let labelToday = UNNotificationAction(
            identifier: Self.labelingActionId,
            title: "Label today",
            options: [.foreground]
        )
        let digestAdmin = UNNotificationCategory(
            identifier: Self.labelingCategoryId,
            actions: [labelToday],
            intentIdentifiers: [],
            options: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([digestAdmin])
    }

    /// Attach to Firebase Messaging. Must be called AFTER `FirebaseApp.configure()`
    /// — setting the delegate earlier silently does nothing, which would look
    /// exactly like Firebase never issuing a token.
    func startMessaging() {
        Messaging.messaging().delegate = self
        // Ask for the current token as well as subscribing to rotations: the
        // delegate callback fires on issue/refresh, and on a launch where the
        // token is already cached there is nothing to fire.
        Messaging.messaging().token { [weak self] token, error in
            if let error {
                logger.warning("FCM token fetch failed: \(error.localizedDescription)")
                return
            }
            guard let token else { return }
            self?.handleFCMToken(token)
        }
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Show notifications as banners even when the app is in the foreground.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    /// Handle notification taps — deep link into the relevant content.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo

        // Digest funnel step 2 (Queue 311 A4 / #1159): emitted BEFORE the
        // deep-link dispatch, so an open is recorded even if navigation fails
        // or the target no longer resolves. `payload_id` is what joins this to
        // the server's `push_sent`; an open without one is not attributable to
        // a send, so it is not reported as one.
        if let payloadId = userInfo["payload_id"] as? String {
            AnalyticsService.trackPushOpened(payloadId: payloadId)
        }

        // The decision is `notificationDestination`, which is pure and tested.
        // This method's remaining job is dispatch — see that function for why the
        // precedence between the action and `url` is load-bearing.
        switch Self.notificationDestination(
            actionIdentifier: response.actionIdentifier,
            userInfo: userInfo
        ) {
        case .labeling:
            Task { @MainActor in
                navCoordinator?.navigate(to: .discoverLabeling, tab: .feed)
            }
        case .url(let url):
            Task { @MainActor in
                _ = navCoordinator?.handleURL(url)
            }
        case .event(let eventId):
            Task { @MainActor in
                navCoordinator?.navigate(to: .eventDetail(id: eventId), tab: .feed)
            }
        case .market(let marketId):
            Task { @MainActor in
                navCoordinator?.navigate(to: .futuresDetail(id: marketId), tab: .feed)
            }
        case .none:
            break
        }

        completionHandler()
    }

    // MARK: - Public API

    /// Request notification permission after a short delay so the prompt
    /// doesn't fire immediately on first launch — better UX.
    func requestPermissionAfterDelay(seconds: TimeInterval = 5) {
        Task {
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            await requestPermission()
        }
    }

    /// Associate a user ID with this device. Re-registers the token if
    /// we already have one so the backend links token -> user.
    func setUser(id: Int?) {
        let changed = userId != id
        userId = id
        guard changed else { return }
        // Every kind we hold must be re-linked to the new identity, not just
        // the APNS one.
        registeredTokenByKind.removeAll()
        Task { await registerAllTokens() }
    }

    /// Called from the AppDelegate when APNS returns a device token.
    func didRegisterForRemoteNotifications(deviceToken data: Data) {
        let hex = data.map { String(format: "%02x", $0) }.joined()
        self.deviceToken = hex
        registeredTokenByKind[.apns] = nil
        // Success clears the failure: a device that recovers (re-signed build,
        // network back) must not keep reporting the old refusal forever.
        apnsRegistrationFailure = nil
        isAPNSRegistered = true
        logger.info("APNS device token received (\(hex.prefix(8))...)")
        // Hand the raw token to Messaging so it can mint the FCM registration
        // token. Without this the SDK has no APNS token to pair and the fetch
        // in `startMessaging` can hang unresolved.
        Messaging.messaging().apnsToken = data
        Task { await registerAllTokens() }
    }

    /// A new or rotated FCM registration token.
    private func handleFCMToken(_ token: String) {
        guard fcmToken != token else { return }
        fcmToken = token
        registeredTokenByKind[.fcm] = nil
        logger.info("FCM registration token received (\(token.prefix(8))...)")
        Task { await registerAllTokens() }
    }

    // MARK: - MessagingDelegate

    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        guard let fcmToken else { return }
        handleFCMToken(fcmToken)
    }

    /// Called from the AppDelegate when APNS registration FAILS.
    ///
    /// It used to say "APNS registration skipped", at `.info`, and stop there.
    /// Every word of that was wrong in a way that cost #2109 a whole cycle:
    /// "skipped" describes a decision not to try, this is the OS refusing after
    /// we tried; `.info` is the level for things that went to plan; and storing
    /// nothing meant the app's own state said push was fine. Zero device tokens
    /// with permission granted is precisely what this callback firing looks
    /// like from the server — and precisely what it looked like from the client
    /// too, which is to say, like nothing at all.
    ///
    /// So: `.error`, the NSError domain/code (the entitlement rejection and a
    /// simulator's "no APNS" are different codes and the distinction is the
    /// whole diagnosis), and a published field so the failure is legible
    /// somewhere other than a console nobody has attached.
    func didFailToRegisterForRemoteNotifications(error: Error) {
        let ns = error as NSError
        let detail = "\(ns.domain) \(ns.code): \(ns.localizedDescription)"
        apnsRegistrationFailure = detail
        isAPNSRegistered = false
        logger.error(
            """
            APNS registration FAILED — no device token will be issued, so no push \
            can be delivered to this install regardless of permission state. \
            \(detail, privacy: .public)
            """
        )
    }

    // MARK: - Private

    @MainActor
    private func requestPermission() async {
        let center = UNUserNotificationCenter.current()
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .badge, .sound])
            isPermissionGranted = granted
            logger.info("Notification permission \(granted ? "granted" : "denied")")
            if granted {
                registerForRemoteNotifications()
            }
        } catch {
            logger.error("Notification permission request failed: \(error.localizedDescription)")
        }
    }

    @MainActor
    private func registerForRemoteNotifications() {
        #if os(iOS)
        UIApplication.shared.registerForRemoteNotifications()
        #elseif os(macOS)
        NSApplication.shared.registerForRemoteNotifications()
        #endif
    }

    /// Register every token we currently hold, one call per kind.
    ///
    /// Additive by design: the APNS registration is kept exactly as it was.
    /// It is the fallback if messaging init fails, and keeping it is what makes
    /// a partial rollout observable — if the FCM half silently never works,
    /// the backend still shows an `apns` row rather than nothing at all.
    private func registerAllTokens() async {
        if let deviceToken {
            await register(token: deviceToken, kind: .apns)
        }
        if let fcmToken {
            await register(token: fcmToken, kind: .fcm)
        }
    }

    private func register(token: String, kind: TokenKind) async {
        guard registeredTokenByKind[kind] != token else { return }

        #if os(iOS)
        let platform = "ios"
        #elseif os(macOS)
        let platform = "macos"
        #else
        let platform = "unknown"
        #endif

        do {
            let _: NotificationRegisterResponse = try await APIClient.shared.registerDeviceToken(
                deviceToken: token,
                platform: platform,
                userId: userId,
                tokenKind: kind.rawValue
            )
            registeredTokenByKind[kind] = token
            logger.info("Device token registered with backend (kind=\(kind.rawValue))")
        } catch {
            logger.warning(
                "Failed to register \(kind.rawValue) device token: \(error.localizedDescription)"
            )
            // Will retry on next app launch or user change
        }
    }
}

// MARK: - Response Model

nonisolated struct NotificationRegisterResponse: Decodable, Sendable {
    let status: String
}

// MARK: - AppDelegate for APNS Callbacks

#if os(iOS)
class BainLuckAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        NotificationManager.shared.didRegisterForRemoteNotifications(deviceToken: deviceToken)
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        NotificationManager.shared.didFailToRegisterForRemoteNotifications(error: error)
    }
}
#elseif os(macOS)
class BainLuckMacAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        if let iconURL = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let icon = NSImage(contentsOf: iconURL) {
            NSApplication.shared.applicationIconImage = icon
        }
    }

    func application(
        _ application: NSApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        NotificationManager.shared.didRegisterForRemoteNotifications(deviceToken: deviceToken)
    }

    func application(
        _ application: NSApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        NotificationManager.shared.didFailToRegisterForRemoteNotifications(error: error)
    }
}
#endif
