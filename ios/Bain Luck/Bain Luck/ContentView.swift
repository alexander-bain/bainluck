import SwiftUI

struct ScreenshotWrapper: Identifiable {
    let id = UUID()
    let image: PlatformImage
}

struct ContentView: View {
    @EnvironmentObject var navCoordinator: NavigationCoordinator
    @State private var bugScreenshot: ScreenshotWrapper? = nil

    var body: some View {
        MainTabView()
            .onReceive(NotificationCenter.default.publisher(for: .deviceDidShake)) { _ in
                if let image = captureScreenshot() {
                    bugScreenshot = ScreenshotWrapper(image: image)
                }
            }
            .onChange(of: navCoordinator.showBugReport) { _, show in
                if show {
                    let image = captureScreenshot()
                    bugScreenshot = ScreenshotWrapper(image: image ?? PlatformImage())
                    navCoordinator.showBugReport = false
                }
            }
            .sheet(item: $bugScreenshot) { wrapper in
                BugReportView(screenshot: wrapper.image)
            }
    }
}
