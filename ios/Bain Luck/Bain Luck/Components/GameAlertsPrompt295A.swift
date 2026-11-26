import Combine
import Foundation
import SwiftUI
import UserNotifications
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Contextual Game Alerts Ask (#11934 / #13084 / Rulings 212: A, 261: A, 262: A, 295: A)
//
// Shares the exact `UserDefaults` keys and `Notification.Name` established by #13083:
// - `bainluck.gameAlertsEnabled.13083`
// - `bainluck.gameAlertsPinPromptHandled.13083`
// - `bainluck.gameAlertsPreferenceDidChange.13083`
//
// Offered once — on the first Follow tap or first game Pin — and never nags after decline.

@MainActor
final class GameAlertsPromptController295A: ObservableObject {
    static let shared = GameAlertsPromptController295A()

    static let enabledPrefName = ["bainluck", "gameAlertsEnabled", "13083"].joined(separator: ".")
    static let promptHandledPrefName = ["bainluck", "gameAlertsPinPromptHandled", "13083"].joined(separator: ".")
    static let preferenceDidChangeNotification = Notification.Name(["bainluck", "gameAlertsPreferenceDidChange", "13083"].joined(separator: "."))

    @Published private(set) var inlineOfferContextId: String? = nil
    @Published private(set) var inlineSubjectName: String? = nil
    @Published var isSheetPresented: Bool = false
    @Published private(set) var sheetSubjectName: String? = nil

    private let defaults: UserDefaults
    private let notificationCenter: NotificationCenter
    private let requestPermissionHandler: () async -> Void

    init(
        defaults: UserDefaults = .standard,
        notificationCenter: NotificationCenter = .default,
        requestPermissionHandler: (() async -> Void)? = nil
    ) {
        self.defaults = defaults
        self.notificationCenter = notificationCenter
        self.requestPermissionHandler = requestPermissionHandler ?? {
            await Self.defaultRequestStandardPermission()
        }
    }

    var isEnabled: Bool {
        defaults.bool(forKey: Self.enabledPrefName)
    }

    var hasHandledPrompt: Bool {
        defaults.bool(forKey: Self.promptHandledPrefName)
    }

    var shouldOffer: Bool {
        !isEnabled && !hasHandledPrompt
    }

    /// Triggered when Follow is tapped on a Team, League, or Set page:
    /// displays the inline game-alerts ask directly on that page once.
    @discardableResult
    func offerInlineOnPage(contextId: String, subjectName: String) -> Bool {
        guard shouldOffer else { return false }
        inlineOfferContextId = contextId
        inlineSubjectName = subjectName
        isSheetPresented = false
        return true
    }

    /// Triggered when Follow is tapped on a game card or when Pin is tapped on a game:
    /// presents the compact contextual sheet once if not already handled.
    @discardableResult
    func offerSheet(subjectName: String? = nil) -> Bool {
        guard shouldOffer else { return false }
        sheetSubjectName = subjectName
        isSheetPresented = true
        return true
    }

    func showsInlineOffer(for contextId: String) -> Bool {
        shouldOffer && inlineOfferContextId == contextId
    }

    func acceptOffer() {
        let wasEnabled = isEnabled
        defaults.set(true, forKey: Self.enabledPrefName)
        defaults.set(true, forKey: Self.promptHandledPrefName)
        inlineOfferContextId = nil
        inlineSubjectName = nil
        isSheetPresented = false
        sheetSubjectName = nil
        if !wasEnabled {
            notificationCenter.post(name: Self.preferenceDidChangeNotification, object: self)
        }
        let handler = requestPermissionHandler
        Task { await handler() }
    }

    func declineOffer() {
        defaults.set(true, forKey: Self.promptHandledPrefName)
        inlineOfferContextId = nil
        inlineSubjectName = nil
        isSheetPresented = false
        sheetSubjectName = nil
    }

    /// Standard notification permission only (`.alert`, `.sound`, `.badge` — never Time Sensitive per 261: A).
    private static func defaultRequestStandardPermission() async {
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        guard granted else { return }
        #if os(iOS)
        await MainActor.run {
            UIApplication.shared.registerForRemoteNotifications()
        }
        #endif
    }
}

private struct GameAlertsPromptEnvironmentKey295A: EnvironmentKey {
    static var defaultValue: GameAlertsPromptController295A {
        MainActor.assumeIsolated { GameAlertsPromptController295A.shared }
    }
}

extension EnvironmentValues {
    var gameAlertsPrompt295A: GameAlertsPromptController295A {
        get { self[GameAlertsPromptEnvironmentKey295A.self] }
        set { self[GameAlertsPromptEnvironmentKey295A.self] = newValue }
    }
}

/// Plain-English game-alerts ask shared between inline page offers (after Follow)
/// and the compact sheet (at game Pin or card Follow).
struct GameAlertsOfferCard295A: View {
    var subjectName: String? = nil
    let onTurnOn: () -> Void
    let onNotNow: () -> Void

    @Environment(\.colorScheme) private var colorScheme

    private var bodyCopy: String {
        if let subjectName, !subjectName.isEmpty {
            return "Know when \(subjectName) games start, get close late, or finish. No account needed."
        }
        return "Know when games you follow or pin start, get close late, or finish. No account needed."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "bell.badge.fill")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                    .padding(.top, 2)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Want game alerts?")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(bodyCopy)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) {
                    turnOnButton
                    notNowButton
                    Spacer(minLength: 0)
                }

                VStack(alignment: .leading, spacing: 8) {
                    turnOnButton
                    notNowButton
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(colorScheme == .dark ? Color.white.opacity(0.08) : DS.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(colorScheme == .dark ? Color.white.opacity(0.16) : DS.border, lineWidth: 1)
        )
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("gameAlertsOfferCard295A")
    }

    private var turnOnButton: some View {
        Button(action: onTurnOn) {
            Text("Turn on alerts")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .padding(.horizontal, 14)
                .frame(minHeight: 38)
                .background(
                    Capsule()
                        .fill(colorScheme == .dark ? DS.emerald : DS.textPrimary)
                )
        }
        .buttonStyle(.borderless)
        .accessibilityIdentifier("gameAlertsOffer.turnOn")
    }

    private var notNowButton: some View {
        Button(action: onNotNow) {
            Text("Not now")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(colorScheme == .dark ? Color.white.opacity(0.78) : DS.textSecondaryReadable)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .padding(.horizontal, 12)
                .frame(minHeight: 38)
                .background(
                    Capsule()
                        .fill(Color.primary.opacity(colorScheme == .dark ? 0.10 : 0.06))
                )
        }
        .buttonStyle(.borderless)
        .accessibilityIdentifier("gameAlertsOffer.notNow")
    }
}

struct GameAlertsInlinePageSlot295A: View {
    let contextId: String
    @Environment(\.gameAlertsPrompt295A) private var promptController

    var body: some View {
        GameAlertsInlinePageSlotBody295A(contextId: contextId, controller: promptController)
    }
}

private struct GameAlertsInlinePageSlotBody295A: View {
    let contextId: String
    @ObservedObject var controller: GameAlertsPromptController295A

    var body: some View {
        if controller.showsInlineOffer(for: contextId) {
            GameAlertsOfferCard295A(
                subjectName: controller.inlineSubjectName,
                onTurnOn: { controller.acceptOffer() },
                onNotNow: { controller.declineOffer() }
            )
        }
    }
}
