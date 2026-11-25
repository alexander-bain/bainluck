import SwiftUI
import UserNotifications
import XCTest
#if canImport(UIKit)
import UIKit
import Vision
#endif

@testable import Bain_Luck

/// #13083 / Rulings 212: A, 261: A, 262: A — single on-device "Game alerts" switch,
/// retired cold-launch notification ask, and integer/string `event_id` tap routing
/// matching Speed's #13088 `GameAlertPush` payload.
@MainActor
final class GameAlertsPreference13083Tests: XCTestCase {
    private var suiteName: String!
    private var defaults: UserDefaults!
    private var center: NotificationCenter!

    override func setUp() {
        super.setUp()
        suiteName = "GameAlertsPreference13083Tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
        center = NotificationCenter()
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        center = nil
        super.tearDown()
    }

    private static func repoFile(_ relative: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
    }

    func testSwitchDefaultsOffPersistsOnDeviceAndGatesNotificationToken() {
        let pref = GameAlertsPreference13083(defaults: defaults, center: center)
        XCTAssertFalse(pref.isEnabled)
        XCTAssertTrue(pref.shouldOfferPinPrompt)
        XCTAssertNil(pref.effectiveNotificationToken(rawToken: "deadbeef"))

        var notifications = 0
        let token = center.addObserver(forName: .gameAlertsPreferenceDidChange13083, object: pref, queue: nil) { _ in
            notifications += 1
        }
        defer { center.removeObserver(token) }

        pref.setEnabled(true)
        XCTAssertTrue(pref.isEnabled)
        XCTAssertFalse(pref.shouldOfferPinPrompt)
        XCTAssertEqual(pref.effectiveNotificationToken(rawToken: "deadbeef"), "deadbeef")
        XCTAssertEqual(notifications, 1)

        // Setting the same value again does not fire a redundant sync notification.
        pref.setEnabled(true)
        XCTAssertEqual(notifications, 1)

        // Persists on-device across a fresh instance (no server migration, 262: A).
        let reloaded = GameAlertsPreference13083(defaults: defaults, center: center)
        XCTAssertTrue(reloaded.isEnabled)

        // Turning off clears the effective notification token and broadcasts change.
        pref.setEnabled(false)
        XCTAssertFalse(pref.isEnabled)
        XCTAssertNil(pref.effectiveNotificationToken(rawToken: "deadbeef"))
        XCTAssertEqual(notifications, 2)
    }

    func testPinPromptOptInAndDeclineHelpersRespectUserChoice() async {
        let pref = GameAlertsPreference13083(defaults: defaults, center: center)
        XCTAssertTrue(pref.shouldOfferPinPrompt)

        pref.declinePinPrompt()
        XCTAssertFalse(pref.isEnabled)
        XCTAssertTrue(pref.hasHandledPinPrompt)
        XCTAssertFalse(pref.shouldOfferPinPrompt, "declining once must not nag on later pins")

        var asked = 0
        let status = await pref.optInAndRequestPermission {
            asked += 1
            return .authorized
        }
        XCTAssertEqual(status, .authorized)
        XCTAssertEqual(asked, 1)
        XCTAssertTrue(pref.isEnabled)
        XCTAssertTrue(pref.hasHandledPinPrompt)
    }

    func testNotificationDestinationAcceptsIntegerAndStringEventIDsFromGameAlerts() {
        // Speed's #13088 `GameAlertPush.to_apns_dict()` sends integer `event_id`.
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": 15351478, "trigger_kind": "close_late"]
            ),
            .event(id: 15351478)
        )
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": NSNumber(value: 15349937)]
            ),
            .event(id: 15349937)
        )
        // Legacy string payloads keep working.
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": "14780576"]
            ),
            .event(id: 14780576)
        )
        // Booleans and non-positive numbers are rejected (never misread `true` as event 1).
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": true]
            ),
            .none
        )
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["event_id": 0]
            ),
            .none
        )
        // Integer market_id also routes cleanly.
        XCTAssertEqual(
            NotificationManager.notificationDestination(
                actionIdentifier: UNNotificationDefaultActionIdentifier,
                userInfo: ["market_id": 70848200]
            ),
            .market(id: 70848200)
        )
    }

    func testColdLaunchPromptIsRetiredAndNoTimeSensitiveEntitlementIsRequested() throws {
        let appSource = try String(contentsOf: Self.repoFile("Bain Luck/Bain_LuckApp.swift"), encoding: .utf8)
        XCTAssertFalse(appSource.contains("requestPermissionAfterDelay"),
                       "Bain_LuckApp must not trigger a cold-launch notification permission dialog (#13083 / 212: A)")
        XCTAssertTrue(appSource.contains("registerIfAlreadyAuthorized"),
                      "Bain_LuckApp should still register APNs silently for already-authorized readers")

        let managerSource = try String(contentsOf: Self.repoFile("Bain Luck/Services/NotificationManager.swift"), encoding: .utf8)
        XCTAssertFalse(managerSource.contains("timeSensitive"),
                       "Ruling 261: A forbids Time Sensitive notifications")
    }

    #if os(iOS)
    func testOpenSettingsHelperOpensBainLuckNotificationSettingsAndCopyIsPlainEnglish() {
        XCTAssertFalse(GameAlertsPreference13083.subtitle.localizedCaseInsensitiveContains("Live Activity"),
                       "Reader-facing copy must stay plain English without platform jargon")
        var opened: URL?
        GameAlertsPreference13083.openAppNotificationSettings { opened = $0 }
        XCTAssertNotNil(opened)
        XCTAssertEqual(opened, GameAlertsPreference13083.appNotificationSettingsURL)
    }

    func testGameAlertsSwitchRendersAt390PxAcrossLightDarkAndDynamicType() throws {
        let outDir = ProcessInfo.processInfo.environment["EXPORT_GAME_ALERTS_13083_DIR"]
        let variants: [(name: String, style: UIUserInterfaceStyle, scheme: ColorScheme, dynamicType: DynamicTypeSize, uiSize: UIContentSizeCategory)] = [
            ("light_default", .light, .light, .large, .large),
            ("dark_default", .dark, .dark, .large, .large),
            ("light_xxxl", .light, .light, .accessibility3, .accessibilityExtraExtraExtraLarge),
            ("dark_xxxl", .dark, .dark, .accessibility3, .accessibilityExtraExtraExtraLarge),
        ]

        let signedOutAuth = AuthManager()
        signedOutAuth.user = nil
        let nav = NavigationCoordinator()

        for v in variants {
            // 1. Default OFF state in Preferences
            let view = NavigationStack {
                PreferencesView(gameAlertsEnabledForTest: false, notificationAuthStatusForTest: .notDetermined)
            }
            .environmentObject(signedOutAuth)
            .environmentObject(nav)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, v.scheme)

            let height: CGFloat = v.dynamicType.isAccessibilitySize ? 844 : 620
            let img = Self.renderPhoneView(view, width: 390, height: height, style: v.style, dynamicType: v.dynamicType, contentSize: v.uiSize)
            let ocr = try Self.recognizeText(in: XCTUnwrap(img.cgImage))
            let flatOCR = ocr.replacingOccurrences(of: " | ", with: " ")
            XCTAssertTrue(flatOCR.localizedCaseInsensitiveContains("Game alerts"),
                          "\(v.name) PreferencesView must show Game alerts; OCR=\(ocr)")
            XCTAssertTrue(flatOCR.localizedCaseInsensitiveContains("final score"),
                          "\(v.name) PreferencesView must show plain-English subtitle; OCR=\(ocr)")
            XCTAssertFalse(flatOCR.localizedCaseInsensitiveContains("Live Activity"),
                           "\(v.name) PreferencesView must not contain platform jargon; OCR=\(ocr)")
            XCTAssertFalse(flatOCR.localizedCaseInsensitiveContains("Couldn't Load Preferences"),
                           "\(v.name) signed-out PreferencesView must not block on account load; OCR=\(ocr)")
            XCTAssertFalse(ocr.contains("…") || ocr.contains("..."),
                           "\(v.name) PreferencesView must not truncate text; OCR=\(ocr)")

            if let outDir, !outDir.isEmpty {
                let url = URL(fileURLWithPath: outDir).appendingPathComponent("prefs_\(v.name).png")
                try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
                try XCTUnwrap(img.pngData()).write(to: url)
            }

            // 2. Refused iPhone notifications state in Preferences (switch ON + tappable orange Settings row)
            let deniedPrefs = NavigationStack {
                PreferencesView(gameAlertsEnabledForTest: true, notificationAuthStatusForTest: .denied)
            }
            .environmentObject(signedOutAuth)
            .environmentObject(nav)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, v.scheme)

            let deniedHeight: CGFloat = v.dynamicType.isAccessibilitySize ? 980 : 620
            let deniedImg = Self.renderPhoneView(deniedPrefs, width: 390, height: deniedHeight, style: v.style, dynamicType: v.dynamicType, contentSize: v.uiSize)
            let deniedOCR = try Self.recognizeText(in: XCTUnwrap(deniedImg.cgImage))
            let flatDenied = deniedOCR.replacingOccurrences(of: " | ", with: " ")
            XCTAssertTrue(flatDenied.localizedCaseInsensitiveContains("open Settings"),
                          "\(v.name) denied PreferencesView must show tappable open Settings row; OCR=\(deniedOCR)")
            XCTAssertFalse(deniedOCR.contains("…") || deniedOCR.contains("..."),
                           "\(v.name) denied PreferencesView must not truncate text; OCR=\(deniedOCR)")

            if let outDir, !outDir.isEmpty {
                let url = URL(fileURLWithPath: outDir).appendingPathComponent("prefs_denied_\(v.name).png")
                try XCTUnwrap(deniedImg.pngData()).write(to: url)
            }
        }

        // 3. Manage pins (signed-out iPhone path): normal + denied at default and xxxLarge
        let pins = PinManager()
        for v in variants {
            let pinView = PinManagementView(gameAlertsEnabledForTest: true, notificationAuthStatusForTest: .denied)
                .environmentObject(pins)
                .environment(\.horizontalSizeClass, .compact)
                .environment(\.colorScheme, v.scheme)
            let pinHeight: CGFloat = v.dynamicType.isAccessibilitySize ? 1_120 : 640
            let img = Self.renderPhoneView(pinView, width: 390, height: pinHeight, style: v.style, dynamicType: v.dynamicType, contentSize: v.uiSize)
            let ocr = try Self.recognizeText(in: XCTUnwrap(img.cgImage))
            let flatOCR = ocr.replacingOccurrences(of: " | ", with: " ")
            XCTAssertTrue(flatOCR.localizedCaseInsensitiveContains("Game alerts"),
                          "\(v.name) PinManagementView must show Game alerts; OCR=\(ocr)")
            XCTAssertTrue(flatOCR.localizedCaseInsensitiveContains("open Settings"),
                          "\(v.name) denied PinManagementView must show tappable open Settings row; OCR=\(ocr)")
            XCTAssertFalse(ocr.contains("…") || ocr.contains("..."),
                           "\(v.name) PinManagementView must not truncate text; OCR=\(ocr)")
            if let outDir, !outDir.isEmpty {
                let url = URL(fileURLWithPath: outDir).appendingPathComponent("pins_denied_\(v.name).png")
                try XCTUnwrap(img.pngData()).write(to: url)
            }
        }
    }

    private static func renderPhoneView<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat,
        style: UIUserInterfaceStyle,
        dynamicType: DynamicTypeSize,
        contentSize: UIContentSizeCategory
    ) -> UIImage {
        let host = hostForMeasurement(view, at: dynamicType)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = style
        host.traitOverrides.horizontalSizeClass = .compact
        host.traitOverrides.preferredContentSizeCategory = contentSize
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = bounds

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: bounds)
        }
        window.frame = bounds
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let deadline = Date().addingTimeInterval(0.25)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < deadline

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private static func recognizeText(in cgImage: CGImage) throws -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return (request.results ?? [])
            .compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: " | ")
    }
    #endif
}
