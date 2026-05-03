import SwiftUI

struct ContentView: View {
    @State private var showBugReport = false
    @State private var bugScreenshot: PlatformImage? = nil

    var body: some View {
        MainTabView()
            #if os(iOS)
            .onReceive(NotificationCenter.default.publisher(for: .deviceDidShake)) { _ in
                bugScreenshot = captureScreenshot()
                showBugReport = true
            }
            #endif
            .sheet(isPresented: $showBugReport) {
                BugReportView(screenshot: bugScreenshot)
            }
    }
}
