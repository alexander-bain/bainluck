import SwiftUI

@main
struct BainLuckWatchApp: App {
    @Environment(\.scenePhase) private var scenePhase

    init() { _ = WatchTelemetry.shared }

    var body: some Scene {
        WindowGroup {
            WatchTabView()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { WatchTelemetry.shared.foreground() }
            else if phase == .background { WatchTelemetry.shared.background() }
        }
    }
}
