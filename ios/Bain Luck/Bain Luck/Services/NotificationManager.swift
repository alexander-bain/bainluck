//
//  NotificationManager.swift
//  Bain Luck
//
//  Created by bain on 5/13/26.
//

import Combine
import Foundation
import os
import UserNotifications
#if canImport(UIKit)
import UIKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "notifications")

/// Manages push notification registration and device token capture.
///
/// Usage: Create as a `@StateObject` in the app entry point and call
/// `requestPermissionAfterDelay()` once the app has loaded. When the user
/// is authenticated, call `setUser(id:)` so the token registration
/// includes the user identity.
final class NotificationManager: ObservableObject {
    static let shared = NotificationManager()

    @Published var isPermissionGranted = false

    /// The raw APNS device token, hex-encoded.
    private(set) var deviceToken: String?

    /// The authenticated user's ID (set after sign-in).
    private var userId: Int?

    /// Whether we've already sent the token to the backend this session.
    private var tokenRegistered = false

    private init() {}

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
        if changed && deviceToken != nil {
            tokenRegistered = false
            Task { await registerTokenWithBackend() }
        }
    }

    /// Called from the AppDelegate when APNS returns a device token.
    func didRegisterForRemoteNotifications(deviceToken data: Data) {
        let hex = data.map { String(format: "%02x", $0) }.joined()
        self.deviceToken = hex
        self.tokenRegistered = false
        logger.info("APNS device token received (\(hex.prefix(8))...)")
        Task { await registerTokenWithBackend() }
    }

    /// Called from the AppDelegate when APNS registration fails.
    func didFailToRegisterForRemoteNotifications(error: Error) {
        logger.error("APNS registration failed: \(error.localizedDescription)")
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

    private func registerTokenWithBackend() async {
        guard let token = deviceToken, !tokenRegistered else { return }

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
                userId: userId
            )
            tokenRegistered = true
            logger.info("Device token registered with backend")
        } catch {
            logger.warning("Failed to register device token: \(error.localizedDescription)")
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
#endif
