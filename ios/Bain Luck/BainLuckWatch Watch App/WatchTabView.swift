import SwiftUI

struct WatchTabView: View {
    var body: some View {
        NavigationStack {
            #if DEBUG
            if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_SEED_URL"] == "1",
               WatchUIFixture.current != nil {
                // Seed configuration only; do not initialize selection or networking.
                Text("URL fixture ready").accessibilityIdentifier("watch.url-fixture-ready")
            } else if WatchUIFixture.current != nil,
                      let scenario = ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_COMPLICATION"],
                      ["live", "final", "empty"].contains(scenario) {
                WatchComplicationLayoutFixture(scenario: scenario)
            } else if WatchUIFixture.current != nil,
               ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_LARGE_TEXT"] == "1" {
                // Layout stress only: watchOS Simulator cannot apply simctl content_size.
                WatchSelectedGameView().dynamicTypeSize(.accessibility5)
            } else {
                WatchSelectedGameView()
            }
            #else
            WatchSelectedGameView()
            #endif
        }
    }
}
