import Combine
import SwiftUI

/// Commands receive the focused scene's existing coordinator explicitly.
/// A missing or ineligible scene never falls back to the app's coordinator.
enum MacSceneCommands10878 {
    @MainActor
    static func makeNavigation(initialTab: AppTab = .discover) -> NavigationCoordinator {
        let navigation = NavigationCoordinator()
        navigation.selectedTab = initialTab
        return navigation
    }

    @MainActor
    @discardableResult
    static func selectTab(
        _ tab: AppTab, target: NavigationCoordinator?, permitsBrowsing: Bool
    ) -> Bool {
        guard permitsBrowsing, let target else { return false }
        target.selectedTab = tab
        return true
    }

    /// #4940: Command-K. Arriving at Search is not by itself a focus ask (a
    /// sidebar click keeps the reader's place), so Quick Search selects, then
    /// asks — on the focused eligible window only.
    @MainActor
    @discardableResult
    static func quickSearch(target: NavigationCoordinator?, permitsBrowsing: Bool) -> Bool {
        guard selectTab(.search, target: target, permitsBrowsing: permitsBrowsing) else { return false }
        target?.requestSearchFocus()
        return true
    }

    @MainActor
    @discardableResult
    static func reportBug(target: NavigationCoordinator?) -> Bool {
        guard let target else { return false }
        target.showBugReport = true
        return true
    }
}

#if os(macOS)
private struct MacBrowsingCommandsEnabledKey10878: FocusedValueKey {
    typealias Value = Bool
}

extension FocusedValues {
    var macBrowsingCommandsEnabled: Bool? {
        get { self[MacBrowsingCommandsEnabledKey10878.self] }
        set { self[MacBrowsingCommandsEnabledKey10878.self] = newValue }
    }
}

/// Mounted once inside each WindowGroup. StateObject keeps navigation owned by
/// that scene while shared services and authentication remain app-owned.
struct MacSceneNavigationRoot<Content: View>: View {
    @Environment(\.openWindow) private var openWindow
    @StateObject private var navigation: NavigationCoordinator
    @ObservedObject private var sharedLiveNavigation: NavigationCoordinator
    @State private var bugScreenshot: ScreenshotWrapper?
    private let permitsBrowsingCommands: Bool
    private let content: (NavigationCoordinator) -> Content

    @MainActor
    init(
        sharedLiveNavigation: NavigationCoordinator,
        permitsBrowsingCommands: Bool = true,
        initialTab: AppTab = .discover,
        @ViewBuilder content: @escaping (NavigationCoordinator) -> Content
    ) {
        _navigation = StateObject(
            wrappedValue: MacSceneCommands10878.makeNavigation(initialTab: initialTab)
        )
        _sharedLiveNavigation = ObservedObject(wrappedValue: sharedLiveNavigation)
        self.permitsBrowsingCommands = permitsBrowsingCommands
        self.content = content
    }

    var body: some View {
        content(navigation)
            .environmentObject(navigation)
            .focusedSceneObject(navigation)
            .focusedSceneValue(\.macBrowsingCommandsEnabled, permitsBrowsingCommands)
            .onAppear {
                guard permitsBrowsingCommands else { return }
                let action = openWindow
                MacNotificationDelivery10878.shared.installWindowRequest {
                    action(id: MacNotificationDelivery10878.primaryWindowID)
                }
            }
            .onReceive(sharedLiveNavigation.$liveGameCount) { count in
                guard permitsBrowsingCommands, navigation.liveGameCount != count else { return }
                navigation.liveGameCount = count
            }
            .onReceive(sharedLiveNavigation.$liveGameTitle) { title in
                guard permitsBrowsingCommands, navigation.liveGameTitle != title else { return }
                navigation.liveGameTitle = title
            }
            .onChange(of: navigation.showBugReport) { _, show in
                // Main windows already present this in ContentView. Dedicated
                // game windows need their own sheet, including failed capture.
                guard !permitsBrowsingCommands, show else { return }
                bugScreenshot = ScreenshotWrapper(image: captureScreenshot())
                navigation.showBugReport = false
            }
            .sheet(item: $bugScreenshot) { wrapper in
                BugReportView(screenshot: wrapper.image)
                    .environmentObject(navigation)
            }
    }
}
#endif
