import SwiftUI

struct ScreenshotWrapper: Identifiable {
    let id = UUID()
    /// Optional on purpose (#1847). A shake whose screenshot capture fails must
    /// still open the report form — see `ContentView`.
    let image: PlatformImage?
}

struct ContentView: View {
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @State private var bugScreenshot: ScreenshotWrapper? = nil

    var body: some View {
        MainTabView()
            .onReceive(NotificationCenter.default.publisher(for: .deviceDidShake)) { _ in
                // #1847: this used to be `if let image = captureScreenshot()`,
                // so a capture failure made the PRIMARY bug-reporting gesture a
                // silent no-op — shake, nothing happens, no way to tell whether
                // anything was filed. Capture is genuinely best-effort (it needs
                // a foreground-active UIWindowScene and a key window; see gotcha
                // #27 on Stage Manager), and the form works fine without an
                // image. Always present.
                bugScreenshot = ScreenshotWrapper(image: captureScreenshot())
            }
            .onChange(of: navCoordinator.showBugReport) { _, show in
                if show {
                    // Was `image ?? PlatformImage()` — a 0x0 placeholder that
                    // rendered as a zero-height image well. nil now means nil.
                    bugScreenshot = ScreenshotWrapper(image: captureScreenshot())
                    navCoordinator.showBugReport = false
                }
            }
            .sheet(item: $bugScreenshot) { wrapper in
                BugReportView(screenshot: wrapper.image)
            }
            // #10873: a Siri/Shortcuts "open" arrives as the same canonical link
            // a shared URL carries, and goes through the same router. A link
            // posted before this view mounted (cold launch) is replayed once;
            // `consume()` clears it so a remount never replays it.
            .onReceive(IntentRouteHandoff10873.shared.settledPosts) { _ in
                guard let link = IntentRouteHandoff10873.shared.consume() else { return }
                _ = navCoordinator.handleURL(link)
            }
            .task {
                // #1847 defect D: unsent reports used to be retried ONLY when
                // the bug-report sheet re-appeared, so a queued report needed
                // the user to shake again before it was even attempted.
                await BugReportOutbox.flush()
            }
            .onReceive(
                NotificationCenter.default.publisher(for: PlatformApp.didBecomeActiveNotification)
            ) { _ in
                Task { await BugReportOutbox.flush() }
            }
    }
}
