import StoreKit
import SwiftUI
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

/// #12304 — asks for an App Store rating at a calm moment: when the reader moves
/// to another tab, a second and a half after it settles, with nothing presented
/// over it, at most once per run, and only when `ReviewPromptPolicy12304` says
/// yes. Never at launch, which Apple's guidance rules out.
///
/// This is the only caller of `requestReview` in the app.
struct ReviewPromptModifier12304: ViewModifier {
    @ObservedObject var navigation: NavigationCoordinator
    @Environment(\.requestReview) private var requestReview
    @Environment(\.scenePhase) private var scenePhase
    @State private var pending: Task<Void, Never>?

    func body(content: Content) -> some View {
        content
            .task { ReviewPromptSignals12304.shared.recordActiveDay(now: Date()) }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    ReviewPromptSignals12304.shared.recordActiveDay(now: Date())
                } else {
                    pending?.cancel()
                }
            }
            .onChange(of: navigation.selectedTab) { _, _ in askWhenSettled() }
    }

    private func askWhenSettled() {
        let signals = ReviewPromptSignals12304.shared
        guard !signals.askedThisRun else { return }
        pending?.cancel()
        pending = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(1500))
            guard !Task.isCancelled, scenePhase == .active, Self.nothingPresented() else { return }
            let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
            let now = Date()
            guard !signals.askedThisRun,
                  ReviewPromptPolicy12304().shouldAsk(signals.state(currentVersion: version), now: now) else { return }
            signals.markAsked(now: now, version: version)
            requestReview()
        }
    }

    /// No sheet, alert or other modal over the foreground window.
    private static func nothingPresented() -> Bool {
        #if os(iOS)
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .filter { $0.activationState == .foregroundActive }
            .flatMap(\.windows)
            .filter(\.isKeyWindow)
        return !windows.isEmpty && windows.allSatisfy { $0.rootViewController?.presentedViewController == nil }
        #elseif os(macOS)
        return NSApp.modalWindow == nil && NSApp.keyWindow?.attachedSheet == nil
        #else
        return false
        #endif
    }
}

extension View {
    /// #12304 — attach once, at the app's root.
    func reviewPrompt12304(navigation: NavigationCoordinator) -> some View {
        modifier(ReviewPromptModifier12304(navigation: navigation))
    }
}
