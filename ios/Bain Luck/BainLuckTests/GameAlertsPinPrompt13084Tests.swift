import SwiftUI
import UIKit
import UserNotifications
import XCTest
@testable import Bain_Luck

/// #13084 (Rulings 212: A, 261: A, 262: A) — contextual opt-in ask shown on
/// first game pin when notifications are `.notDetermined`, plus decline
/// persistence and 390 px Light/Dark × Default/xxxLarge renders.
@MainActor
final class GameAlertsPinPrompt13084Tests: XCTestCase {
    private var suiteName: String!
    private var defaults: UserDefaults!
    private var center: NotificationCenter!

    override func setUp() {
        super.setUp()
        suiteName = "GameAlertsPinPrompt13084Tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
        center = NotificationCenter()
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        center = nil
        super.tearDown()
    }

    private func makePreference() -> GameAlertsPreference13083 {
        GameAlertsPreference13083(defaults: defaults, center: center)
    }

    func testFirstGamePinGuestAndSignedInPresentsWhenNotDeterminedAndTurnOnRequestsPermissionOnce() async {
        // 1. Guest reader pins a game with `.notDetermined` status.
        let guestPref = makePreference()
        var askCount = 0
        let guestPins = PinManager(
            defaults: defaults,
            allowLegacyGuestPins: false,
            gameAlertsConfig: GameAlertsPromptConfig13084(
                preference: guestPref,
                authorizationStatus: { .notDetermined },
                requestPermission: {
                    askCount += 1
                    return .authorized
                }
            )
        )

        guestPins.togglePin(type: "event", id: 1001)
        await guestPins.pendingGameAlertsPromptTask?.value
        XCTAssertEqual(guestPins.gameAlertsOptInPresentation?.eventID, 1001)
        XCTAssertFalse(guestPref.isEnabled)
        XCTAssertEqual(askCount, 0, "system prompt must wait until reader taps Turn on (212: A)")

        let granted = await guestPins.acceptGameAlertsOptInPrompt()
        XCTAssertEqual(granted, .authorized)
        XCTAssertEqual(askCount, 1)
        XCTAssertNil(guestPins.gameAlertsOptInPresentation)
        XCTAssertTrue(guestPref.isEnabled)
        XCTAssertTrue(guestPref.hasHandledPinPrompt)

        // Pinning a second game must not re-prompt.
        guestPins.togglePin(type: "event", id: 1002)
        await guestPins.pendingGameAlertsPromptTask?.value
        XCTAssertNil(guestPins.gameAlertsOptInPresentation)

        // 2. Signed-in reader with fresh preference sees prompt only after server confirms pin.
        let signedSuite = "GameAlertsPinPrompt13084Tests.signed.\(UUID().uuidString)"
        let signedDefaults = UserDefaults(suiteName: signedSuite)!
        defer { signedDefaults.removePersistentDomain(forName: signedSuite) }
        let signedPref = GameAlertsPreference13083(defaults: signedDefaults, center: NotificationCenter())
        let signedPins = PinManager(
            defaults: signedDefaults,
            allowLegacyGuestPins: false,
            initialBinding: PinAccountBinding(userID: "user-42", authenticated: true),
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in },
            gameAlertsConfig: GameAlertsPromptConfig13084(
                preference: signedPref,
                authorizationStatus: { .notDetermined },
                requestPermission: { .authorized }
            )
        )
        await signedPins.loadPins()
        let syncTask = signedPins.togglePin(type: "event", id: 2001)
        await syncTask?.value
        XCTAssertEqual(signedPins.gameAlertsOptInPresentation?.eventID, 2001)
    }

    func testDeclineRemembersChoiceNeverAsksPermissionAndNeverNagsAgain() async {
        let pref = makePreference()
        var askCount = 0
        let pinManager = PinManager(
            defaults: defaults,
            allowLegacyGuestPins: false,
            gameAlertsConfig: GameAlertsPromptConfig13084(
                preference: pref,
                authorizationStatus: { .notDetermined },
                requestPermission: {
                    askCount += 1
                    return .authorized
                }
            )
        )

        pinManager.togglePin(type: "event", id: 101)
        await pinManager.pendingGameAlertsPromptTask?.value
        XCTAssertNotNil(pinManager.gameAlertsOptInPresentation)

        pinManager.declineGameAlertsOptInPrompt()
        XCTAssertNil(pinManager.gameAlertsOptInPresentation)
        XCTAssertFalse(pref.isEnabled)
        XCTAssertTrue(pref.hasHandledPinPrompt)
        XCTAssertEqual(askCount, 0)

        // Later game pins must never show the prompt again.
        pinManager.togglePin(type: "event", id: 102)
        await pinManager.pendingGameAlertsPromptTask?.value
        XCTAssertNil(pinManager.gameAlertsOptInPresentation)
        XCTAssertEqual(askCount, 0)
    }

    func testAlreadyDecidedSystemStatusOrEnabledSwitchNeverPrompts() async {
        for status: UNAuthorizationStatus in [.authorized, .denied, .provisional] {
            let localSuite = "GameAlertsPinPrompt13084Tests.status.\(status.rawValue).\(UUID().uuidString)"
            let localDefaults = UserDefaults(suiteName: localSuite)!
            defer { localDefaults.removePersistentDomain(forName: localSuite) }
            let pref = GameAlertsPreference13083(defaults: localDefaults, center: NotificationCenter())
            let pins = PinManager(
                defaults: localDefaults,
                allowLegacyGuestPins: false,
                gameAlertsConfig: GameAlertsPromptConfig13084(
                    preference: pref,
                    authorizationStatus: { status },
                    requestPermission: nil
                )
            )
            pins.togglePin(type: "event", id: 501)
            await pins.pendingGameAlertsPromptTask?.value
            XCTAssertNil(pins.gameAlertsOptInPresentation, "status \(status) must not prompt")
        }

        let enabledPref = makePreference()
        enabledPref.setEnabled(true)
        let pinsAlreadyOn = PinManager(
            defaults: defaults,
            allowLegacyGuestPins: false,
            gameAlertsConfig: GameAlertsPromptConfig13084(
                preference: enabledPref,
                authorizationStatus: { .notDetermined },
                requestPermission: nil
            )
        )
        pinsAlreadyOn.togglePin(type: "event", id: 601)
        await pinsAlreadyOn.pendingGameAlertsPromptTask?.value
        XCTAssertNil(pinsAlreadyOn.gameAlertsOptInPresentation)
    }

    func testFuturePinUnpinAndPinLimitRejectionNeverPrompt() async {
        let pref = makePreference()
        let pins = PinManager(
            defaults: defaults,
            allowLegacyGuestPins: false,
            gameAlertsConfig: GameAlertsPromptConfig13084(
                preference: pref,
                authorizationStatus: { .notDetermined },
                requestPermission: nil
            )
        )

        // Future market pin must not trigger game alerts prompt.
        pins.togglePin(type: "future", id: 7001)
        await pins.pendingGameAlertsPromptTask?.value
        XCTAssertNil(pins.gameAlertsOptInPresentation)

        // Fill up to max game pins while already handled, then reset handled flag
        // and verify unpin & pin-limit rejection both do not prompt.
        for gameId in 1...PinManager.maxPinsPerType {
            pins.togglePin(type: "event", id: gameId)
            await pins.pendingGameAlertsPromptTask?.value
            if pins.gameAlertsOptInPresentation != nil {
                pins.gameAlertsOptInPresentation = nil
            }
        }
        XCTAssertFalse(pins.canPin(type: "event"))

        // Rejected 7th pin does not present alert opt-in.
        pins.togglePin(type: "event", id: 999)
        await pins.pendingGameAlertsPromptTask?.value
        XCTAssertNil(pins.gameAlertsOptInPresentation)

        // Unpinning an existing game does not present alert opt-in.
        pins.togglePin(type: "event", id: 1)
        await pins.pendingGameAlertsPromptTask?.value
        XCTAssertNil(pins.gameAlertsOptInPresentation)
    }

    func testPromptCopyContainsNoPlatformJargon() {
        let combined = "\(GameAlertsPinPromptSheet13084.titleCopy) \(GameAlertsPinPromptSheet13084.bodyCopy)"
            .lowercased()
        for forbidden in ["apns", "token", "live activity", "entitlement", "push_devices"] {
            XCTAssertFalse(combined.contains(forbidden), "forbidden jargon: \(forbidden)")
        }
        XCTAssertTrue(combined.contains("starts"))
        XCTAssertTrue(combined.contains("close late"))
        XCTAssertTrue(combined.contains("final"))
        XCTAssertTrue(GameAlertsPinPromptSheet13084.bodyCopy.contains("in Preferences"))
        XCTAssertFalse(GameAlertsPinPromptSheet13084.bodyCopy.contains("in Settings"))
    }

    func testContextualAskRenders390pxLightAndDarkAtDefaultAndXXXLarge() async throws {
        let outDir = ProcessInfo.processInfo.environment["EXPORT_13084_RENDER_DIR"]
            ?? ProcessInfo.processInfo.environment["SIMCTL_CHILD_EXPORT_13084_RENDER_DIR"]

        let configs: [(name: String, scheme: ColorScheme, uiStyle: UIUserInterfaceStyle, size: DynamicTypeSize)] = [
            ("13084-prompt-light-default-390.png", .light, .light, .large),
            ("13084-prompt-dark-default-390.png", .dark, .dark, .large),
            ("13084-prompt-light-xxxlarge-390.png", .light, .light, .xxxLarge),
            ("13084-prompt-dark-xxxlarge-390.png", .dark, .dark, .xxxLarge),
        ]

        for cfg in configs {
            let sheet = GameAlertsPinPromptSheet13084(
                onTurnOn: {},
                onNotNow: {}
            )
            .frame(width: 390)
            .background(Color(uiColor: .systemBackground))
            .environment(\.colorScheme, cfg.scheme)

            let host = hostForMeasurement(sheet, at: cfg.size)
            host.additionalSafeAreaInsets = .zero
            host.overrideUserInterfaceStyle = cfg.uiStyle
            let fittedH = max(240, min(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 900)).height), 900))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: fittedH))

            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = cfg.uiStyle
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }

            try await Task.sleep(nanoseconds: 100_000_000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            fmt.opaque = true
            let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                UIColor.systemBackground.setFill()
                ctx.fill(host.view.bounds)
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            XCTAssertGreaterThan(image.size.height, 200)

            let attachment = XCTAttachment(image: image)
            attachment.name = cfg.name
            attachment.lifetime = .keepAlways
            add(attachment)

            if let outDir, !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                try XCTUnwrap(image.pngData()).write(to: dirURL.appendingPathComponent(cfg.name))
            }
        }
    }
}
